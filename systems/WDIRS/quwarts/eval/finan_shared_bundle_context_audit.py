"""Zero-Qwen evidence-location audit of the frozen shared-bundle Finan arm."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.full_window_additive.overlay import apply_overlay, copy_plumbing, official_bag
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.provenance import document_stem
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.shared_bundle.context_blocks import (
    dedupe_overlap,
    head_tail_midcut,
    overlap_report,
    pack_c1,
    parse_layout,
    retrieval_terms,
    tokens_of,
)
from quwarts.core.shared_bundle.inventory import compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites

SHARED = ROOT / "results" / "quwarts_finan_shared_bundle"
EXACT = ROOT / "results" / "quwarts_finan_exact_message_additive"
PLUMBING = ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
DOCETL_DIR = ROOT / "results" / "docetl_finan_case80"
SOURCE_DIR = ROOT / "source_data" / "Finance" / "finance"
OUT = ROOT / "results" / "finan_shared_bundle_context_audit"
INPUT_CAP = 12000
EXPECTED_PRODUCT = 0.0411
DOCETL_PRODUCT = 0.084
PLUMBING_PRODUCT = 0.0158
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
PUNCT = re.compile(r"[^a-z0-9]+")
UNIT_WORD = re.compile(r"\b(million|billion|thousand|percent|pct)\b", re.I)


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _score(dest: Path, rows, rewrites, gold) -> dict[str, Any]:
    report = score_with_rewrites(rows, rewrites, dest, gold, "Finan")
    return {
        "mean_structure_f2": float(report.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_at_0.20": mean_cell_f1_20(report),
        "mean_per_query_product": mean_per_query_product(report),
        "per_query": [
            {
                "query_id": row["query_id"],
                "structure_f2": row.get("structure_f2"),
                "cell_f1_20": row.get("cell_f1_20"),
                "product": float(row.get("structure_f2") or 0.0) * float(row.get("cell_f1_20") or 0.0),
            }
            for row in report.get("per_query") or []
        ],
    }


def mapping_from_db() -> dict[str, str]:
    conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(finance)")]
    mapping = {}
    for rec in conn.execute("SELECT * FROM finance"):
        row = dict(zip(cols, rec))
        stem = str(row.get("__provenance_label") or document_stem(str(row.get("doc_id") or "")))
        mapping[stem] = str(row.get("doc_id") or f"{stem}.txt")
    conn.close()
    return mapping


def document_of_prompt(user: str) -> str:
    marker = "\nDocument:\n"
    if marker in user:
        return user.split(marker, 1)[1]
    return user


def load_task_prompts(keys: set[tuple[str, str]]) -> dict[tuple[str, str], dict[str, Any]]:
    found: dict[tuple[str, str], dict[str, Any]] = {}
    with (SHARED / "rendered_prompts.jsonl").open() as handle:
        for line in handle:
            row = json.loads(line)
            key = (row["entity_id"], row["bundle_signature"])
            if key in keys:
                found[key] = row
                if len(found) == len(keys):
                    break
    missing = keys - set(found)
    if missing:
        raise SystemExit(f"missing rendered prompts: {list(missing)[:3]}")
    return found


def numeric_forms(value: Any, nearby: str = "") -> list[str]:
    norm, _, err = normalize_value(value, "numeric")
    if err or not isinstance(norm, (int, float)):
        return []
    n = float(norm)
    whole = int(n) if float(n) == int(n) else n
    forms = {str(whole), f"{whole:,}" if isinstance(whole, int) else str(whole)}
    if isinstance(whole, int):
        forms.add(f"${whole}")
        forms.add(f"${whole:,}")
        if whole < 0:
            forms.add(f"({abs(whole)})")
            forms.add(f"({abs(whole):,})")
    if 0 < abs(n) <= 100:
        forms.add(f"{n:g}%")
        forms.add(f"{n/100:g}" if abs(n) > 1 else f"{n*100:g}%")
    nearby_l = nearby.lower()
    scaled = []
    if "million" in nearby_l:
        scaled.append(n / 1_000_000)
        scaled.append(n * 1_000_000)
    if "billion" in nearby_l:
        scaled.append(n / 1_000_000_000)
        scaled.append(n * 1_000_000_000)
    if "thousand" in nearby_l:
        scaled.append(n / 1_000)
        scaled.append(n * 1_000)
    for item in scaled:
        if abs(item) >= 0.001:
            body = int(item) if float(item) == int(item) else item
            forms.add(str(body) if not isinstance(body, float) else f"{body:g}")
            if isinstance(body, int):
                forms.add(f"{body:,}")
    return [item for item in forms if item not in {"", "0"}]


def find_span(text: str, needle: str) -> int:
    if not text or not needle:
        return -1
    return text.lower().find(str(needle).lower())


def string_coverage(text: str, gold: Any, aliases: list[str]) -> str:
    if gold in (None, ""):
        return "no_gold"
    raw = str(gold).strip()
    if not raw or not text:
        return "no_match"
    if raw.lower() in text.lower():
        return "exact_normalized"
    compact_t = PUNCT.sub("", text.lower())
    compact_g = PUNCT.sub("", raw.lower())
    if compact_g and compact_g in compact_t:
        return "case_punct_normalized"
    g_tokens = [tok for tok in tokens_of(raw) if len(tok) > 2]
    t_tokens = set(tokens_of(text))
    if g_tokens and all(tok in t_tokens for tok in g_tokens):
        return "token_or_alias"
    for alias in aliases:
        if alias and str(alias).lower() in text.lower() and (
            str(alias).lower() in raw.lower() or raw.lower() in str(alias).lower() or compact_g[:4] == PUNCT.sub("", str(alias).lower())[:4]
        ):
            return "token_or_alias"
    return "no_match"


def numeric_coverage(text: str, gold: Any) -> tuple[str, str | None]:
    if gold in (None, ""):
        return "no_gold", None
    windows = [text]
    for match in UNIT_WORD.finditer(text):
        lo = max(0, match.start() - 240)
        hi = min(len(text), match.end() + 240)
        windows.append(text[lo:hi])
    for window in windows:
        for form in numeric_forms(gold, window):
            if form and form.lower() in window.lower():
                return "exact_normalized", form
    return "no_match", None


def nearby_header(text: str, pos: int) -> str:
    if pos < 0:
        return ""
    lo = max(0, pos - 200)
    hi = min(len(text), pos + 80)
    return " ".join(text[lo:hi].split())[:240]


def classify_fill(
    *,
    pred: Any,
    gold: Any,
    dtype: str,
    c0: str,
    source: str,
    aliases: list[str],
    literals: list[str],
) -> dict[str, Any]:
    gnorm, _, _ = normalize_value(gold, dtype) if gold not in (None, "") else (None, None, "missing")
    pnorm, _, _ = normalize_value(pred, dtype) if pred not in (None, "") else (None, None, "missing")
    exact = gnorm is not None and gnorm == pnorm
    if exact:
        return {"category": "correct", "evidence": "normalized values equal", "gold_in_c0": True, "gold_in_source": True}
    if gnorm is None:
        return {"category": "gold internally inconsistent or unalignable", "evidence": "gold missing or unnormalizable", "gold_in_c0": False, "gold_in_source": False}

    if dtype == "numeric":
        src_hit, src_form = numeric_coverage(source, gold)
        c0_hit, c0_form = numeric_coverage(c0, gold)
        gold_in_source = src_hit != "no_match"
        gold_in_c0 = c0_hit != "no_match"
    else:
        src_hit = string_coverage(source, gold, aliases)
        c0_hit = string_coverage(c0, gold, aliases)
        src_form = str(gold)
        c0_form = str(gold)
        gold_in_source = src_hit != "no_match"
        gold_in_c0 = c0_hit != "no_match"

    pred_in_c0 = False
    pred_pos = -1
    if pnorm is not None:
        if dtype == "numeric":
            for form in numeric_forms(pnorm, c0):
                pred_pos = find_span(c0, form)
                if pred_pos >= 0:
                    pred_in_c0 = True
                    break
        else:
            pred_pos = find_span(c0, str(pnorm))
            pred_in_c0 = pred_pos >= 0

    if not gold_in_source:
        return {"category": "gold value unavailable in the full document", "evidence": f"source_match={src_hit}", "gold_in_c0": False, "gold_in_source": False}

    if not gold_in_c0 and gold_in_source:
        return {
            "category": "correct gold value absent from C0 but present in full document",
            "evidence": f"source_form={src_form}",
            "gold_in_c0": False,
            "gold_in_source": True,
            "source_header": nearby_header(source, find_span(source, str(src_form or gold))),
        }

    if dtype == "numeric" and isinstance(pnorm, (int, float)) and isinstance(gnorm, (int, float)):
        for scale, label in ((1000, "thousand"), (1_000_000, "million"), (1_000_000_000, "billion"), (100, "percent")):
            if abs(float(pnorm) * scale - float(gnorm)) <= max(1.0, abs(float(gnorm)) * 1e-6) or abs(float(pnorm) / scale - float(gnorm)) <= max(1.0, abs(float(gnorm)) * 1e-6):
                header = nearby_header(c0, pred_pos)
                if label in header.lower() or label in UNIT_WORD.findall(header.lower() and header or " "):
                    return {"category": "correct occurrence returned but wrong unit scaling", "evidence": f"scale={label} header={header}", "gold_in_c0": True, "gold_in_source": True, "c0_offset": pred_pos}
        if pnorm == -gnorm or (isinstance(pnorm, (int, float)) and isinstance(gnorm, (int, float)) and abs(abs(pnorm) - abs(gnorm)) <= 1e-6 and pnorm != gnorm):
            return {"category": "sign or percentage conversion error", "evidence": f"pred={pnorm} gold={gnorm}", "gold_in_c0": True, "gold_in_source": True}
        gy = YEAR.findall(nearby_header(source, find_span(source, str(src_form or ""))))
        py = YEAR.findall(nearby_header(c0, pred_pos))
        if gy and py and set(gy) != set(py):
            return {"category": "wrong reporting period/year", "evidence": f"gold_years={gy} pred_years={py}", "gold_in_c0": True, "gold_in_source": True, "c0_offset": pred_pos, "c0_header": nearby_header(c0, pred_pos)}
        if pred_in_c0 and gold_in_c0 and pnorm != gnorm:
            if abs(float(pnorm)) < abs(float(gnorm)) * 0.6:
                return {"category": "component value chosen instead of total", "evidence": nearby_header(c0, pred_pos), "gold_in_c0": True, "gold_in_source": True, "c0_offset": pred_pos}
            if abs(float(pnorm)) > abs(float(gnorm)) * 1.4:
                return {"category": "total chosen instead of component", "evidence": nearby_header(c0, pred_pos), "gold_in_c0": True, "gold_in_source": True, "c0_offset": pred_pos}
            return {"category": "correct gold value present in C0, wrong occurrence selected", "evidence": f"pred_form_in_c0={pred_in_c0} gold_form={c0_form}", "gold_in_c0": True, "gold_in_source": True, "c0_offset": pred_pos, "c0_header": nearby_header(c0, pred_pos)}

    pred_text = str(pnorm)
    if any(str(lit).strip() == pred_text or str(lit).replace("%", "") == pred_text for lit in literals):
        return {"category": "other", "evidence": f"prediction equals workload predicate literal {pred_text}", "gold_in_c0": gold_in_c0, "gold_in_source": True}
    if dtype != "numeric":
        if any(str(alias).lower() == pred_text.lower() for alias in aliases) and gold_in_c0:
            return {"category": "categorical semantic error", "evidence": f"pred={pred_text} is a CASE/workload label; gold={gnorm}", "gold_in_c0": True, "gold_in_source": True}
        if pred_in_c0 and gold_in_c0:
            return {"category": "entity/name alias mismatch" if string_coverage(c0, gold, aliases) == "token_or_alias" else "correct gold value present in C0, wrong occurrence selected", "evidence": f"pred={pred_text} gold={gnorm}", "gold_in_c0": True, "gold_in_source": True, "c0_offset": pred_pos, "c0_header": nearby_header(c0, pred_pos)}
        if gold_in_c0:
            return {"category": "categorical semantic error", "evidence": f"gold present ({c0_hit}) pred={pred_text}", "gold_in_c0": True, "gold_in_source": True}
    return {"category": "other", "evidence": f"src={src_hit} c0={c0_hit} pred={pnorm} gold={gnorm}", "gold_in_c0": gold_in_c0, "gold_in_source": gold_in_source}


def classify_effect(before: dict[str, Any], after: dict[str, Any], plumbing: dict[str, Any]) -> str:
    b16 = before["score_16"]
    a16 = after["score_16"]
    if abs(a16["mean_per_query_product"] - b16["mean_per_query_product"]) > 1e-12:
        return "change product"
    bag_changed = False
    scored_changed = False
    count_changed = False
    for left, right, base in zip(before["score_16"]["per_query"], after["score_16"]["per_query"], plumbing["score_16"]["per_query"]):
        if abs(left["product"] - right["product"]) > 1e-12:
            scored_changed = True
        if abs((left.get("structure_f2") or 0) - (right.get("structure_f2") or 0)) > 1e-12:
            return "change test structure"
        if abs((left.get("cell_f1_20") or 0) - (right.get("cell_f1_20") or 0)) > 1e-12:
            count_changed = True
    if scored_changed and count_changed:
        return "change a count cell"
    if count_changed:
        return "move a count within tolerance"
    return "change only an unscored bag" if bag_changed else "change no bag"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    journal = json.loads((SHARED / "theta100_journal.json").read_text())
    fills = json.loads((SHARED / "theta100_fills.json").read_text())
    frozen_bags = json.loads((SHARED / "theta100_bags.json").read_text())
    frozen_report = json.loads((SHARED / "finan_shared_bundle_arm.json").read_text())
    manifest = [{"query_id": str(row["query_id"]), "sql": str(row["sql"])} for row in json.loads((DOCETL_DIR / "query_manifest.json").read_text())]
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    records = compile_attribute_inventory(statements)
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    mapping = mapping_from_db()
    texts = {path.stem: path.read_text(encoding="utf-8", errors="replace") for path in sorted(SOURCE_DIR.glob("*.txt"))}

    dest = OUT / "reproduced_theta100.db"
    copy_plumbing(PLUMBING, dest)
    overlay = apply_overlay(dest, fills, mapping)
    bags = {qid: official_bag(dest, statements[qid], predicates, qid) for qid in query_ids}
    bag_ok = _hash(bags) == _hash(frozen_bags)
    if not bag_ok:
        raise SystemExit("reproduction gate failed: bags do not match frozen shared-bundle bags")
    if overlay["changed_cells"] != 79:
        raise SystemExit(f"reproduction gate failed: fills {overlay['changed_cells']} != 79")
    if len(journal) != 115:
        raise SystemExit(f"reproduction gate failed: journal {len(journal)} != 115")
    print(json.dumps({"reproduced_bags": True, "fills": overlay["changed_cells"], "calls": len(journal)}, indent=2), flush=True)

    keys = {(row["entity_id"], row["bundle_signature"]) for row in journal}
    prompts = load_task_prompts(keys)
    layouts = {doc_id: parse_layout(doc_id, texts[doc_id]) for doc_id in sorted({row["document_id"] for row in journal})}
    contexts = []
    token_stats = {label: [] for label in ("C0", "C1", "C2")}
    kind_counts = Counter()
    for row in journal:
        prompt = prompts[(row["entity_id"], row["bundle_signature"])]
        c0 = document_of_prompt(prompt["user"])
        instr = int(prompt.get("instruction_tokens") or 0)
        budget = max(1, INPUT_CAP - instr)
        terms = {name: retrieval_terms(name, records[name]) for name in row["attributes"]}
        packed = pack_c1(layouts[row["document_id"]], terms, budget)
        c1 = packed["text"]
        half = max(1, budget // 2)
        mid = head_tail_midcut(texts[row["document_id"]], half)
        packed_half = pack_c1(layouts[row["document_id"]], terms, budget - count_tokens(mid))
        c2 = dedupe_overlap(mid, packed_half["text"])
        item = {
            "entity_id": row["entity_id"],
            "document_id": row["document_id"],
            "bundle_signature": row["bundle_signature"],
            "attributes": list(row["attributes"]),
            "instruction_tokens": instr,
            "document_budget": budget,
            "C0": {"text": c0, "tokens": count_tokens(c0), "route": row.get("route"), "request_sha256": prompt.get("request_sha256")},
            "C1": {"text": c1, "tokens": packed["used_tokens"] or count_tokens(c1), "kinds": packed["kinds"], "blocks": packed["blocks"]},
            "C2": {"text": c2, "tokens": count_tokens(c2), "midcut_tokens": count_tokens(mid), "retrieval_tokens": packed_half["used_tokens"]},
            "overlap": {
                "C0_C1": overlap_report(c0, c1),
                "C0_C2": overlap_report(c0, c2),
                "C1_C2": overlap_report(c1, c2),
            },
        }
        contexts.append(item)
        for label in ("C0", "C1", "C2"):
            token_stats[label].append(item[label]["tokens"])
        kind_counts.update(packed["kinds"])
    context_meta = [{k: row[k] for k in row if k not in {"C0", "C1", "C2"}} | {
        "C0": {k: row["C0"][k] for k in row["C0"] if k != "text"} | {"sha256": hashlib.sha256(row["C0"]["text"].encode()).hexdigest()},
        "C1": {k: row["C1"][k] for k in row["C1"] if k not in {"text", "blocks"}} | {"sha256": hashlib.sha256(row["C1"]["text"].encode()).hexdigest(), "n_blocks": len(row["C1"]["blocks"])},
        "C2": {k: row["C2"][k] for k in row["C2"] if k != "text"} | {"sha256": hashlib.sha256(row["C2"]["text"].encode()).hexdigest()},
        "overlap": row["overlap"],
    } for row in contexts]
    hashes = {
        "C0": _hash([row["C0"]["sha256"] for row in context_meta]),
        "C1": _hash([row["C1"]["sha256"] for row in context_meta]),
        "C2": _hash([row["C2"]["sha256"] for row in context_meta]),
        "contexts": _hash(context_meta),
        "reproduced_bags": _hash(bags),
        "frozen_bags": _hash(frozen_bags),
        "plumbing": file_sha256(PLUMBING),
        "shared_frozen": file_sha256(SHARED / "frozen.json"),
        "exact_frozen": file_sha256(EXACT / "frozen.json"),
    }
    with (OUT / "contexts.jsonl").open("w") as handle:
        for row in contexts:
            handle.write(json.dumps(row, default=str) + "\n")
    (OUT / "context_index.json").write_text(json.dumps({"hashes": hashes, "n": len(contexts), "token_stats": {k: {"min": min(v), "max": max(v), "mean": sum(v)/len(v)} for k, v in token_stats.items()}, "c1_kinds": dict(kind_counts)}, indent=2, default=str))
    (OUT / "freeze.json").write_text(json.dumps({"hashes": hashes, "n_tasks": len(contexts), "gold_loaded": False, "bags_reproduced": True}, indent=2))
    print(json.dumps({"frozen_contexts": True, "hashes": hashes, "token_stats": {k: {"min": min(v), "max": max(v), "mean": round(sum(v)/len(v), 1)} for k, v in token_stats.items()}}, indent=2), flush=True)

    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Finan"))
    full = {row["query_id"]: row for row in queries_for("Finan")}
    score_rows = [{"query_id": qid, "sql": statements[qid], "pack": (full.get(qid) or {}).get("pack")} for qid in query_ids]
    count_rows = [row for row in score_rows if is_count_query(query_shape(row["query_id"], row["sql"]))]
    gold_rows = gold.get("finance") or gold.get("Finance") or []
    gold_by: dict[str, dict[str, Any]] = {}
    for row in gold_rows:
        for key in (str(row.get("doc_id") or ""), Path(str(row.get("doc_id") or "")).stem, str(row.get("id") or "")):
            if key:
                gold_by[key] = row

    def score_path(db: Path) -> dict[str, Any]:
        rewrites = {qid: {"sql": official_sql(statements[qid], db, predicates, query_id=qid), "sqlite_path": str(db)} for qid in query_ids}
        return {
            "score_16": _score(db, score_rows, rewrites, gold),
            "score_15": _score(db, count_rows, {row["query_id"]: rewrites[row["query_id"]] for row in count_rows}, gold),
        }

    reproduced = score_path(dest)
    product = reproduced["score_16"]["mean_per_query_product"]
    if abs(product - float(frozen_report["score_100"]["score_16"]["mean_per_query_product"])) > 1e-9:
        raise SystemExit(f"reproduction gate failed: product {product} != frozen")
    if round(product + 1e-10, 4) != EXPECTED_PRODUCT:
        raise SystemExit(f"reproduction gate failed: rounded product {round(product, 4)} != {EXPECTED_PRODUCT}")
    print(json.dumps({"product_gate": True, "product": product}, indent=2), flush=True)

    ctx_by = {(row["document_id"], row["bundle_signature"]): row for row in contexts}
    aliases = {name: list(records[name].categorical_literals) for name in records}
    coverage_rows = []
    for grow in gold_rows:
        doc_id = str(grow.get("id") or Path(str(grow.get("doc_id") or "")).stem)
        source = texts.get(doc_id, "")
        for name, rec in records.items():
            raw = grow.get(name)
            if raw is None and name == "total_debt":
                raw = grow.get("total_Debt")
            if raw in (None, ""):
                continue
            task = next((row for row in contexts if row["document_id"] == doc_id and name in row["attributes"]), None)
            if rec.dtype == "numeric":
                src, _ = numeric_coverage(source, raw)
                c0 = c1 = c2 = "no_task"
                if task:
                    c0, _ = numeric_coverage(task["C0"]["text"], raw)
                    c1, _ = numeric_coverage(task["C1"]["text"], raw)
                    c2, _ = numeric_coverage(task["C2"]["text"], raw)
            else:
                src = string_coverage(source, raw, aliases[name])
                c0 = c1 = c2 = "no_task"
                if task:
                    c0 = string_coverage(task["C0"]["text"], raw, aliases[name])
                    c1 = string_coverage(task["C1"]["text"], raw, aliases[name])
                    c2 = string_coverage(task["C2"]["text"], raw, aliases[name])
            accepted = None
            if task:
                accepted = (fills.get(doc_id) or {}).get(name) is not None
            coverage_rows.append(
                {
                    "document_id": doc_id,
                    "attribute": name,
                    "bundle": task["bundle_signature"] if task else None,
                    "roles": dict(rec.roles),
                    "source": src,
                    "C0": c0,
                    "C1": c1,
                    "C2": c2,
                    "accepted": accepted,
                    "has_task": task is not None,
                }
            )

    def cov_summary(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
        counts = Counter(row[key] for row in rows)
        n = sum(counts[k] for k in counts if k not in {"no_gold", "no_task"})
        present = sum(counts[k] for k in counts if k not in {"no_gold", "no_task", "no_match"})
        return {"counts": dict(counts), "present_rate": (present / n) if n else None, "n": n}

    coverage = {
        "overall": {key: cov_summary(coverage_rows, key) for key in ("source", "C0", "C1", "C2")},
        "by_attribute": {},
        "by_document": {},
        "by_bundle": {},
        "by_role": {},
        "accepted_vs_missing": {},
    }
    for name in sorted(records):
        coverage["by_attribute"][name] = {key: cov_summary([row for row in coverage_rows if row["attribute"] == name], key) for key in ("source", "C0", "C1", "C2")}
    for doc_id in sorted({row["document_id"] for row in coverage_rows if row["has_task"]}):
        coverage["by_document"][doc_id] = {key: cov_summary([row for row in coverage_rows if row["document_id"] == doc_id], key) for key in ("source", "C0", "C1", "C2")}
    for bundle in sorted({row["bundle"] for row in coverage_rows if row["bundle"]}):
        coverage["by_bundle"][bundle] = {key: cov_summary([row for row in coverage_rows if row["bundle"] == bundle], key) for key in ("C0", "C1", "C2")}
    for role in ("WHERE", "CASE", "GROUP BY", "aggregate input", "projection"):
        subset = [row for row in coverage_rows if (records[row["attribute"]].roles or {}).get(role)]
        coverage["by_role"][role] = {key: cov_summary(subset, key) for key in ("source", "C0", "C1", "C2")}
    for label, flag in (("accepted", True), ("missing_or_unattempted", False)):
        subset = [row for row in coverage_rows if row["has_task"] and bool(row["accepted"]) is flag]
        coverage["accepted_vs_missing"][label] = {key: cov_summary(subset, key) for key in ("source", "C0", "C1", "C2")}

    taxonomy = []
    for doc_id, values in fills.items():
        source = texts.get(doc_id, "")
        grow = gold_by.get(doc_id) or gold_by.get(f"{doc_id}.txt") or {}
        for name, pred in values.items():
            task = next(row for row in contexts if row["document_id"] == doc_id and name in row["attributes"])
            gold_v = grow.get(name)
            if gold_v is None and name == "total_debt":
                gold_v = grow.get("total_Debt")
            label = classify_fill(
                pred=pred,
                gold=gold_v,
                dtype=records[name].dtype,
                c0=task["C0"]["text"],
                source=source,
                aliases=aliases[name],
                literals=list(records[name].predicate_literals) + list(records[name].categorical_literals),
            )
            taxonomy.append({"document_id": doc_id, "attribute": name, "bundle": task["bundle_signature"], "pred": pred, "gold": gold_v, **label})

    by_cat = Counter(row["category"] for row in taxonomy)
    by_attr_cat = defaultdict(Counter)
    for row in taxonomy:
        by_attr_cat[row["attribute"]][row["category"]] += 1

    def gold_ok(doc_id: str, attr: str, value: Any) -> bool:
        grow = gold_by.get(doc_id) or gold_by.get(f"{doc_id}.txt") or {}
        raw = grow.get(attr)
        if raw is None and attr == "total_debt":
            raw = grow.get("total_Debt")
        dtype = records[attr].dtype
        gnorm, _, _ = normalize_value(raw, dtype) if raw not in (None, "") else (None, None, None)
        vnorm, _, _ = normalize_value(value, dtype) if value is not None else (None, None, None)
        if gnorm is None or vnorm is None:
            return False
        if gnorm == vnorm:
            return True
        if dtype == "numeric" and isinstance(gnorm, (int, float)) and isinstance(vnorm, (int, float)) and gnorm != 0:
            return abs(float(vnorm) - float(gnorm)) / abs(float(gnorm)) <= 0.20
        return False

    journal_cells = []
    for row in journal:
        for name, item in (row.get("items") or {}).items():
            c0_present = False
            grow = gold_by.get(row["document_id"]) or {}
            gold_v = grow.get(name) if name != "total_debt" else grow.get(name, grow.get("total_Debt"))
            task = ctx_by[(row["document_id"], row["bundle_signature"])]
            if records[name].dtype == "numeric":
                c0_present = numeric_coverage(task["C0"]["text"], gold_v)[0] != "no_match" if gold_v not in (None, "") else False
            else:
                c0_present = string_coverage(task["C0"]["text"], gold_v, aliases[name]) != "no_match" if gold_v not in (None, "") else False
            journal_cells.append(
                {
                    "document_id": row["document_id"],
                    "attribute": name,
                    "bundle": row["bundle_signature"],
                    "bundle_size": len(row["attributes"]),
                    "n_fields": len(row["attributes"]),
                    "mixed": len({records[a].dtype for a in row["attributes"]}) > 1,
                    "cooccur": max((records[name].n_queries for _ in [0]), default=0),
                    "gold_in_c0": c0_present,
                    "route": row.get("route"),
                    "accepted": item.get("accepted") is not None,
                    "correct": gold_ok(row["document_id"], name, item.get("accepted")) if item.get("accepted") is not None else False,
                    "repeated": sum(1 for other in journal if name in other.get("attributes") or []) > 1,
                }
            )

    def rate(rows: list[dict[str, Any]]) -> dict[str, Any]:
        accepted = [row for row in rows if row["accepted"]]
        return {"n": len(rows), "accepted": len(accepted), "correct": sum(int(row["correct"]) for row in accepted), "exact_rate": (sum(int(row["correct"]) for row in accepted) / len(accepted)) if accepted else None}

    bundling = {
        "by_size": {str(size): rate([row for row in journal_cells if row["bundle_size"] == size]) for size in (1, 2, 3)},
        "mixed_vs_homo": {
            "mixed": rate([row for row in journal_cells if row["mixed"]]),
            "homogeneous": rate([row for row in journal_cells if not row["mixed"]]),
        },
        "gold_in_c0": {
            "present": rate([row for row in journal_cells if row["gold_in_c0"]]),
            "absent": rate([row for row in journal_cells if not row["gold_in_c0"]]),
        },
        "route": {
            "whole_document": rate([row for row in journal_cells if row["route"] == "whole_document"]),
            "mid_cut": rate([row for row in journal_cells if row["route"] == "mid_cut"]),
        },
        "repeated": {
            "repeated": rate([row for row in journal_cells if row["repeated"]]),
            "singleton": rate([row for row in journal_cells if not row["repeated"]]),
        },
    }
    present_size = {str(size): rate([row for row in journal_cells if row["gold_in_c0"] and row["bundle_size"] == size]) for size in (1, 2, 3)}
    bundling["size_holding_gold_in_c0"] = present_size

    exact_journal = json.loads((EXACT / "theta100_journal.json").read_text())
    exact_cells = {}
    for row in exact_journal:
        for name, item in (row.get("items") or {}).items():
            if item.get("accepted") is None:
                continue
            exact_cells[(row["document_id"], name)] = item["accepted"]
    overlap = {"shared_correct_exact_wrong": 0, "exact_correct_shared_wrong": 0, "both_correct": 0, "both_wrong": 0, "n": 0, "examples": []}
    for row in journal_cells:
        key = (row["document_id"], row["attribute"])
        if key not in exact_cells or not row["accepted"]:
            continue
        s_ok = row["correct"]
        e_ok = gold_ok(row["document_id"], row["attribute"], exact_cells[key])
        overlap["n"] += 1
        if s_ok and e_ok:
            overlap["both_correct"] += 1
        elif s_ok and not e_ok:
            overlap["shared_correct_exact_wrong"] += 1
        elif e_ok and not s_ok:
            overlap["exact_correct_shared_wrong"] += 1
            if len(overlap["examples"]) < 8:
                overlap["examples"].append({"document_id": row["document_id"], "attribute": row["attribute"], "shared": fills.get(row["document_id"], {}).get(row["attribute"]), "exact": exact_cells[key], "gold_in_c0": row["gold_in_c0"], "bundle": row["bundle"]})
        else:
            overlap["both_wrong"] += 1

    plumbing_score = score_path(PLUMBING)
    base_score = reproduced
    sql_visible = Counter()
    attr_visible = Counter()
    effects = []
    attempted_wrong = []
    for row in journal_cells:
        grow = gold_by.get(row["document_id"]) or {}
        gold_v = grow.get(row["attribute"])
        if gold_v is None and row["attribute"] == "total_debt":
            gold_v = grow.get("total_Debt")
        if gold_v in (None, ""):
            continue
        if row["correct"]:
            continue
        attempted_wrong.append(row)
    for row in attempted_wrong:
        grow = gold_by.get(row["document_id"]) or {}
        gold_v = grow.get(row["attribute"]) if row["attribute"] != "total_debt" else grow.get(row["attribute"], grow.get("total_Debt"))
        gnorm, _, _ = normalize_value(gold_v, records[row["attribute"]].dtype)
        if gnorm is None:
            continue
        trial = OUT / "loo.db"
        copy_plumbing(PLUMBING, trial)
        trial_fills = {doc: dict(vals) for doc, vals in fills.items()}
        trial_fills.setdefault(row["document_id"], {})[row["attribute"]] = gnorm
        apply_overlay(trial, trial_fills, mapping)
        after = score_path(trial)
        effect = classify_effect(base_score, after, plumbing_score)
        if effect == "change no bag":
            # bags may change without score
            if _hash({qid: official_bag(trial, statements[qid], predicates, qid) for qid in query_ids}) != _hash(bags):
                effect = "change only an unscored bag"
        effects.append({"document_id": row["document_id"], "attribute": row["attribute"], "effect": effect, "accepted": row["accepted"]})
        if effect != "change no bag":
            sql_visible[row["attribute"]] += 1
            attr_visible[row["attribute"]] += 1

    def oracle_fills(label: str) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = defaultdict(dict)
        writes = []
        for row in coverage_rows:
            if not row["has_task"] or row[label] in {"no_match", "no_task", "no_gold"}:
                continue
            grow = gold_by.get(row["document_id"]) or {}
            gold_v = grow.get(row["attribute"])
            if gold_v is None and row["attribute"] == "total_debt":
                gold_v = grow.get("total_Debt")
            gnorm, _, _ = normalize_value(gold_v, records[row["attribute"]].dtype)
            if gnorm is None:
                continue
            out[row["document_id"]][row["attribute"]] = gnorm
            writes.append({"document_id": row["document_id"], "attribute": row["attribute"], "context": label, "match": row[label]})
        return dict(out), writes

    oracle_scores = {}
    oracle_writes = {}
    for label in ("C0", "C1", "C2"):
        ofills, writes = oracle_fills(label)
        oracle_writes[label] = writes
        odb = OUT / f"oracle_{label}.db"
        copy_plumbing(PLUMBING, odb)
        apply_overlay(odb, ofills, mapping)
        scored = score_path(odb)
        oracle_scores[label] = {
            "n_writes": len(writes),
            "score_16": {k: scored["score_16"][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")},
            "score_15": {k: scored["score_15"][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")},
        }

    present_rates = bundling["size_holding_gold_in_c0"]
    size1_n = int((present_rates.get("1") or {}).get("accepted") or 0)
    size3_n = int((present_rates.get("3") or {}).get("accepted") or 0)
    bundling_dominates = (
        size1_n >= 8
        and size3_n >= 8
        and present_rates["3"]["exact_rate"] is not None
        and present_rates["1"]["exact_rate"] is not None
        and present_rates["3"]["exact_rate"] + 0.05 < present_rates["1"]["exact_rate"]
    )

    location = by_cat.get("correct gold value absent from C0 but present in full document", 0)
    selection = (
        by_cat.get("correct gold value present in C0, wrong occurrence selected", 0)
        + by_cat.get("component value chosen instead of total", 0)
        + by_cat.get("total chosen instead of component", 0)
        + by_cat.get("categorical semantic error", 0)
        + by_cat.get("entity/name alias mismatch", 0)
        + by_cat.get("other", 0)
    )
    norm = by_cat.get("correct occurrence returned but wrong unit scaling", 0) + by_cat.get("sign or percentage conversion error", 0)
    unavailable = by_cat.get("gold value unavailable in the full document", 0)
    if bundling_dominates:
        decision = "bundling itself reduces quality after controlling for context"
    elif location > selection and location > norm and location > unavailable:
        decision = "evidence location dominates"
    elif selection >= max(location, norm, unavailable):
        decision = "selection among present candidates dominates"
    elif norm >= max(location, selection, unavailable):
        decision = "normalization or unit handling dominates"
    elif unavailable >= max(location, selection, norm):
        decision = "gold values are often unavailable in source"
    else:
        decision = "selection among present candidates dominates"

    report = {
        "decision": decision,
        "secondary": {
            "location": location,
            "selection": selection,
            "normalization": norm,
            "unavailable": unavailable,
            "categorical": by_cat.get("categorical semantic error", 0),
            "prompt_literal_or_other": by_cat.get("other", 0),
            "bundling_after_context_control": present_rates,
        },
        "reproduction": {
            "bags_match": True,
            "fills": 79,
            "calls": 115,
            "product": product,
            "product_rounded": round(product, 4),
        },
        "context_hashes": hashes,
        "context_token_distributions": {k: {"min": min(v), "max": max(v), "mean": sum(v) / len(v)} for k, v in token_stats.items()},
        "c1_block_kinds": dict(kind_counts),
        "coverage": coverage,
        "error_taxonomy": dict(by_cat),
        "error_taxonomy_by_attribute": {name: dict(by_attr_cat[name]) for name in sorted(by_attr_cat)},
        "focus": {name: dict(by_attr_cat[name]) for name in ("auditor", "revenue", "total_debt") if name in by_attr_cat},
        "bundling": bundling,
        "exact_message_overlap": overlap,
        "sql_visible_error_counts": dict(sql_visible),
        "sql_effects": Counter(row["effect"] for row in effects),
        "availability_oracles": oracle_scores,
        "oracle_write_counts": {k: len(v) for k, v in oracle_writes.items()},
        "comparators": {
            "plumbing": PLUMBING_PRODUCT,
            "shared_bundle": product,
            "docetl": DOCETL_PRODUCT,
        },
        "unalignable": sum(1 for row in taxonomy if row["category"] == "gold internally inconsistent or unalignable"),
        "prior_unmodified": {
            "shared": file_sha256(SHARED / "frozen.json") == hashes["shared_frozen"],
            "exact": file_sha256(EXACT / "frozen.json") == hashes["exact_frozen"],
            "plumbing": file_sha256(PLUMBING) == hashes["plumbing"],
        },
    }
    (OUT / "coverage.json").write_text(json.dumps(coverage_rows, indent=2, default=str))
    (OUT / "taxonomy.json").write_text(json.dumps(taxonomy, indent=2, default=str))
    (OUT / "sql_effects.json").write_text(json.dumps(effects, indent=2, default=str))
    (OUT / "oracle_writes.json").write_text(json.dumps(oracle_writes, indent=2, default=str))
    (OUT / "finan_shared_bundle_context_audit.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({"wrote": str(OUT / "finan_shared_bundle_context_audit.json"), "decision": decision, "product": product, "taxonomy": dict(by_cat), "oracles": {k: v["score_16"]["mean_per_query_product"] for k, v in oracle_scores.items()}}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
