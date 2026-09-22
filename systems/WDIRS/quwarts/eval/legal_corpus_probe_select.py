"""Legal corpus-grounded sample-probe optimizer. No benchmark gold. Deterministic candidates only."""

from __future__ import annotations

import builtins
import hashlib
import json
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
for path in (ROOT / "systems" / "WDIRS", ROOT, ROOT / "systems" / "docetl-main"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

BLOCKED = (
    "/quwarts_legal_shared_reachability",
    "/quwarts_legal_cost_aware_reachability",
    "/quwarts_legal_evidence_card_aggregation_audit",
    "/quwarts_legal_pairwise_ab",
    "/quwarts_legal_forced_binary",
)
_REAL_OPEN = builtins.open


def _blocked(path: Any) -> bool:
    text = str(path).replace("\\", "/")
    if any(token in text for token in BLOCKED):
        return True
    if "ground_truth" in text or "/gold/" in text.lower():
        return True
    if "quwarts_legal" in text and (text.endswith("post_freeze.json") or text.endswith("/REPORT.md")):
        if "/quwarts_legal_corpus_probe" not in text:
            return True
    return False


def _guarded_open(file, *args, **kwargs):
    if _blocked(file):
        raise RuntimeError(f"forbidden artifact access blocked: {file}")
    return _REAL_OPEN(file, *args, **kwargs)


def assert_access_closed() -> None:
    for name, mod in list(sys.modules.items()):
        path = str(getattr(mod, "__file__", "") or "")
        if _blocked(path):
            raise SystemExit(f"run invalid: imported blocked module {name}")
    source = Path(__file__).read_text()
    if "load_" + "ground_truth" in source:
        raise SystemExit("run invalid: runner references gold")
    for left, right in (
        ("quwarts_legal_", "shared_reachability/"),
        ("quwarts_legal_", "cost_aware_reachability/"),
        ("quwarts_legal_", "evidence_card_aggregation_audit/"),
        ("quwarts_legal_", "pairwise_ab/"),
        ("quwarts_legal_", "forced_binary/"),
    ):
        if left + right in source:
            raise SystemExit("run invalid: runner references a forbidden result path")


builtins.open = _guarded_open

from quwarts.core.amortized_select.dsl import allowed_term_bank, apply_critic_fixes, empty_spec, normalize_spec, restore_schema_policy, validate_spec
from quwarts.core.amortized_select.executor import execute_cell
from quwarts.core.amortized_select.features import annotate_set, spec_tokens
from quwarts.core.amortized_select.prompt import COMPILER_SCHEMA, assemble_tools, compiler_user
from quwarts.core.amortized_select.sample import sample_attribute
from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog
from quwarts.core.corpus_probe.context import exhaustive_chunks, inspect_record, route_context, whole_document_budget
from quwarts.core.full_window_additive.overlay import apply_overlay, copy_plumbing, official_bag
from quwarts.core.ledger import BudgetExhausted, SpendRecord, TokenLedger
from quwarts.core.llm.openrouter import load_env_file
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.provenance import document_stem
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.shared_bundle.inventory import compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.finan_amortized_select_arm import issue_call, mapping_from_rows, parse_tool, reserved_of, usage_of, _hash, _null
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import queries_for, score_with_rewrites

load_env_file(ROOT / ".env")

FROZEN_INV = ROOT / "results" / "quwarts_legal_multichannel_candidates"
PLUMBING = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
DOCETL_DIR = ROOT / "results" / "docetl_legal_case80"
SOURCE_DIR = ROOT / "source_data" / "Legal" / "legal_case"
SCHEMA_PATH = ROOT / "Query" / "Legal" / "Legal_attributes.json"
OUT = ROOT / "results" / "quwarts_legal_corpus_probe"
THETA = 12_610_011
SEED = 42
TABLE = "legal"
KEEP = "KEEP_PLUMBING"
DET = {"surface", "normalized", "workload_label"}
N_SAMPLE = 96
N_TRAIN = 64
N_VAL = 32
N_PROGRAMS = 5
ALLOC = {"silver": 0.50, "synthesis": 0.15, "heldout": 0.30, "reserve": 0.05}

PROBE_SCHEMA = {
    "value": "str",
    "normalized": "str",
    "presence": "str",
    "spans": "str",
    "offsets": "str",
    "subject": "str",
    "period": "str",
    "role": "str",
    "confidence": "str",
    "competitors": "str",
}
ADJ_SCHEMA = {
    "value": "str",
    "normalized": "str",
    "presence": "str",
    "spans": "str",
    "offsets": "str",
    "unresolved": "bool",
}
SCAN_SCHEMA = {"hits": "str"}
CLASS_SCHEMA = {"label": "str", "presence": "str"}
PAIR_SCHEMA = {"choice": "str"}

PROBE_PROMPT = (
    "Extract the requested attribute for this entity from the supplied source text only. "
    "Do not invent a value that is not supported by a quoted span. "
    "If the document does not support a value, set presence to NOT_PRESENT. "
    "Return the raw proposed value, a normalized value, exact supporting spans, character offsets if visible, "
    "the subject/entity, temporal period if applicable, the role or component represented, confidence, "
    "and competing occurrences."
)
SCAN_PROMPT = (
    "Scan this source chunk. For each listed attribute, if the chunk contains supporting evidence, "
    "quote the span and name the attribute. If none, say NONE."
)
ADJ_PROMPT = (
    "Adjudicate two independent source readings. Use the raw source and cited spans. "
    "Return one supported value with offsets, or mark unresolved. Do not invent."
)
CLASS_PROMPT = (
    "Map the extracted source evidence onto one workload-visible label, or NOT_PRESENT. "
    "Do not pick a label without supporting evidence."
)
PLANNER_PROMPT = (
    "Compile one reusable candidate-selection program. Output only the DSL object. "
    "Do not select cells. Do not emit entity IDs, document IDs, corpus names, or sample constants."
)
CRITIQUE_PROMPT = (
    "Rewrite the program to fix the listed source-grounded training errors. Output only the DSL object."
)
PAIR_PROMPT = (
    "Choose which of X or Y is supported by the source document for the attribute. "
    "Identify a concrete source-supported error if one side is wrong. Output X or Y."
)


def sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def channel_of(item: dict[str, Any]) -> str:
    raw = str(item.get("channel") or item.get("derivation") or "surface")
    return "composed" if raw.startswith("composed") else raw


def det_items(rec: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in (rec.get("all_candidates") or rec.get("candidates") or []) if channel_of(item) in DET]


def clip(text: Any, n: int = 240) -> str:
    body = " ".join(str(text or "").split())
    return body if len(body) <= n else body[: n - 1].rstrip() + "…"


def annotate_det(rec: dict[str, Any], tokens: set[str], doc_len: int) -> list[dict[str, Any]]:
    row = {"candidates": det_items(rec)}
    feats = annotate_set(row, tokens, doc_len)
    by_id = {str(item.get("id")): item for item in row["candidates"]}
    for feat in feats:
        src = by_id.get(str(feat.get("id")) or "")
        feat["channel"] = channel_of(src) if src else "surface"
    return feats


def execute_program(spec: dict[str, Any], feats: list[dict[str, Any]]) -> dict[str, Any]:
    preferred = spec.get("preferred_channels") or []
    rejected = spec.get("rejected_channels") or []
    filtered = []
    for feat in feats:
        ch = str(feat.get("channel") or "")
        if rejected and ch in rejected:
            continue
        if preferred and ch not in preferred:
            continue
        filtered.append(feat)
    return execute_cell(spec, filtered or feats)


def parse_choice(raw: str, allowed: set[str]) -> str | None:
    found = [lab for lab in allowed if re.search(r"(?<![A-Za-z0-9_])" + re.escape(lab) + r"(?![A-Za-z0-9_])", raw or "")]
    return found[0] if len(set(found)) == 1 else None


def bootstrap_lcb(values: list[float], seed: int = 0) -> float:
    if not values:
        return 0.0
    rng = random.Random(seed)
    means = []
    for _ in range(200):
        sample = [values[rng.randrange(len(values))] for _ in values]
        means.append(sum(sample) / len(sample))
    means.sort()
    return means[int(0.05 * (len(means) - 1))]


def restrict_db(src: Path, dest: Path, keep_ids: set[str]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    copy_plumbing(src, dest)
    conn = sqlite3.connect(str(dest))
    ids = list(keep_ids)
    conn.execute(f'DELETE FROM "{TABLE}" WHERE __entity_id NOT IN ({",".join("?" for _ in ids)})', ids)
    conn.commit()
    conn.close()


def materialize(dest: Path, fills, mapping, statements, predicates, query_ids, base: Path | None = None) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    copy_plumbing(base or PLUMBING, dest)
    overlay = apply_overlay(dest, fills, mapping, table=TABLE)
    bags = {qid: official_bag(dest, statements[qid], predicates, qid) for qid in query_ids}
    return {"overlay": overlay, "bags": bags, "bag_sha256": _hash(bags), "db_sha256": file_sha256(dest)}


def score_against(dest: Path, gold_tables: dict[str, list], statements, predicates, query_ids) -> dict[str, Any]:
    full = {row["query_id"]: row for row in queries_for("Legal")}
    score_rows = [{"query_id": qid, "sql": statements[qid], "pack": (full.get(qid) or {}).get("pack")} for qid in query_ids]
    rewrites = {qid: {"sql": official_sql(statements[qid], dest, predicates, query_id=qid), "sqlite_path": str(dest)} for qid in query_ids}
    report = score_with_rewrites(score_rows, rewrites, dest, gold_tables, "Legal")
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


def map_to_candidate(value: Any, items: list[dict[str, Any]], spec) -> str | None:
    if value in (None, "", "NOT_PRESENT", "unresolved"):
        return None
    want, _, err = normalize_value(value, spec.dtype)
    if err or want is None:
        want = str(value).strip().lower()
    else:
        want = str(want).strip().lower()
    for item in items:
        got = item.get("normalized")
        g2, _, e2 = normalize_value(got, spec.dtype)
        cand = str(g2 if not e2 and g2 is not None else got or "").strip().lower()
        if cand and cand == want:
            return str(item.get("id"))
    for item in items:
        if str(item.get("raw_span") or "").strip().lower() == str(value).strip().lower():
            return str(item.get("id"))
    return None


def main() -> int:
    assert_access_closed()
    for token in BLOCKED:
        try:
            _guarded_open(ROOT / "results" / token.strip("/"), "r")
        except RuntimeError:
            continue
        raise SystemExit("run invalid: forbidden path was readable")
    OUT.mkdir(parents=True, exist_ok=True)
    inventory = json.loads((FROZEN_INV / "candidate_inventory.json").read_text())
    manifest = json.loads((DOCETL_DIR / "query_manifest.json").read_text())
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    records = compile_attribute_inventory(statements)
    specs = compile_specs(load_official_catalog(SCHEMA_PATH), records)
    attr_names = sorted(records)
    conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    cols = [row[1] for row in conn.execute(f'PRAGMA table_info("{TABLE}")')]
    plumbing_rows = [dict(zip(cols, rec)) for rec in conn.execute(f'SELECT * FROM "{TABLE}"')]
    conn.close()
    mapping = mapping_from_rows(plumbing_rows)
    texts = {path.stem: path.read_text(encoding="utf-8", errors="replace") for path in sorted(SOURCE_DIR.glob("*.txt"))}
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    by_ent_attr = {(rec["entity_id"], rec["attribute"]): rec for rec in inventory}
    by_doc_attr = {(rec["document_id"], rec["attribute"]): rec for rec in inventory}
    plumbing_by = {str(row.get("__entity_id")): row for row in plumbing_rows}
    entities = []
    for row in plumbing_rows:
        eid = str(row.get("__entity_id"))
        doc = str(row.get("__provenance_label") or document_stem(str(row.get("doc_id") or "")))
        entities.append({"entity_id": eid, "document_id": doc, "row": row})

    budget = {name: int(THETA * frac) for name, frac in ALLOC.items()}
    prompts = {"probe": PROBE_PROMPT, "scan": SCAN_PROMPT, "adjudicate": ADJ_PROMPT, "classify": CLASS_PROMPT, "planner": PLANNER_PROMPT, "critique": CRITIQUE_PROMPT, "pair": PAIR_PROMPT}
    design = {
        "query_ids": query_ids,
        "n_documents": len(texts),
        "inventory": file_sha256(FROZEN_INV / "candidate_inventory.json"),
        "plumbing": file_sha256(PLUMBING),
        "prompts": sha(prompts),
        "model": "openrouter/qwen/qwen-2.5-7b-instruct",
        "seed": SEED,
        "theta": THETA,
        "allocation": budget,
        "deterministic_channels": sorted(DET),
    }
    (OUT / "design.json").write_text(json.dumps(design, indent=2))

    whole_budget = whole_document_budget()
    feats_ent = []
    lengths = []
    for ent in entities:
        text = texts.get(ent["document_id"]) or ""
        lengths.append(len(text))
    ordered_len = sorted(lengths)
    def quartile(n: int) -> int:
        if n <= ordered_len[len(ordered_len) // 4]:
            return 1
        if n <= ordered_len[len(ordered_len) // 2]:
            return 2
        if n <= ordered_len[(3 * len(ordered_len)) // 4]:
            return 3
        return 4
    for ent in entities:
        text = texts.get(ent["document_id"]) or ""
        recs = [rec for rec in inventory if rec["entity_id"] == ent["entity_id"]]
        n_cand = sum(len(det_items(rec)) for rec in recs)
        chans = Counter(channel_of(item) for rec in recs for item in det_items(rec))
        nulls = sum(1 for name in attr_names if ent["row"].get(name) in (None, ""))
        amb = sum(1 for rec in recs if len(set(str(item.get("normalized")) for item in det_items(rec))) >= 3)
        amp = sum(records[name].occurrence_count for name in attr_names if ent["row"].get(name) in (None, ""))
        tok = count_tokens(text)
        feat = {
            **ent,
            "doc_len": len(text),
            "doc_tokens": tok,
            "len_q": quartile(len(text)),
            "fit": "whole" if tok <= whole_budget else "chunk",
            "cand_b": 0 if n_cand <= 4 else 1 if n_cand <= 16 else 2,
            "null_b": 0 if nulls <= 2 else 1 if nulls <= 5 else 2,
            "chan": dict(chans),
            "amb_b": 0 if amb == 0 else 1,
            "amp_b": 0 if amp <= 4 else 1,
            "n_cand": n_cand,
            "nulls": nulls,
        }
        feats_ent.append(feat)
    groups: dict[tuple, list] = defaultdict(list)
    for feat in feats_ent:
        groups[(feat["len_q"], feat["fit"], feat["cand_b"], feat["null_b"], feat["amb_b"], feat["amp_b"])].append(feat)
    for key in groups:
        groups[key].sort(key=lambda row: hashlib.sha256(f"{SEED}:{row['entity_id']}".encode()).hexdigest())
    sampled = []
    keys = sorted(groups)
    indexes = {key: 0 for key in keys}
    while len(sampled) < N_SAMPLE:
        progressed = False
        for key in keys:
            i = indexes[key]
            if i < len(groups[key]):
                sampled.append(groups[key][i])
                indexes[key] = i + 1
                progressed = True
                if len(sampled) >= N_SAMPLE:
                    break
        if not progressed:
            break
    sampled = sampled[:N_SAMPLE]
    sampled.sort(key=lambda row: (row["len_q"], row["fit"], row["entity_id"]))
    train = []
    held = []
    by_stratum: dict[tuple, list] = defaultdict(list)
    for row in sampled:
        by_stratum[(row["len_q"], row["fit"])].append(row)
    for key, rows in sorted(by_stratum.items()):
        cut = max(1, int(round(len(rows) * (N_TRAIN / N_SAMPLE))))
        train.extend(rows[:cut])
        held.extend(rows[cut:])
    while len(train) > N_TRAIN:
        held.append(train.pop())
    while len(held) < N_VAL and train:
        held.append(train.pop())
    train = train[:N_TRAIN]
    held = held[:N_VAL]
    train_ids = {row["entity_id"] for row in train}
    held_ids = {row["entity_id"] for row in held}
    sample_payload = {
        "train": [{"entity_id": row["entity_id"], "document_id": row["document_id"], **{k: row[k] for k in ("len_q", "fit", "cand_b", "null_b", "amb_b", "amp_b", "doc_tokens", "n_cand", "nulls")}} for row in train],
        "heldout": [{"entity_id": row["entity_id"], "document_id": row["document_id"], **{k: row[k] for k in ("len_q", "fit", "cand_b", "null_b", "amb_b", "amp_b", "doc_tokens", "n_cand", "nulls")}} for row in held],
    }
    (OUT / "sample_split.json").write_text(json.dumps(sample_payload, indent=2))
    (OUT / "prompts.json").write_text(json.dumps(prompts, indent=2))
    (OUT / "phase0_hashes.json").write_text(json.dumps({"design": sha(design), "sample": sha(sample_payload), "prompts": sha(prompts)}, indent=2))
    print(json.dumps({"phase0": True, "train": len(train), "heldout": len(held), "whole": sum(1 for row in sampled if row["fit"] == "whole"), "chunk": sum(1 for row in sampled if row["fit"] == "chunk")}, indent=2), flush=True)

    ledger = TokenLedger(theta=THETA, seed=SEED)
    if (OUT / "live_ledger.json").is_file():
        snap = json.loads((OUT / "live_ledger.json").read_text())
        ledger.spent = int(snap.get("spent") or 0)
        ledger.records = [SpendRecord(row["purpose"], row["tokens"], row.get("metadata") or {}) for row in snap.get("records") or []]

    def persist() -> None:
        (OUT / "live_ledger.json").write_text(json.dumps(ledger.snapshot(), indent=2, default=str))

    def one_call(schema: dict[str, str], instruction: str, user: str, purpose: str, meta: dict[str, Any]) -> dict[str, Any]:
        bundled = assemble_tools(schema, instruction + "\n\n" + user)
        _pt, reserved = reserved_of(bundled["user"], bundled["tools"])
        if ledger.spent + reserved > ledger.theta:
            return {"parsed": {}, "raw": "", "malformed": True, "actual": 0, "reason": "budget_exhausted"}
        try:
            response = issue_call(bundled["request"])
        except Exception as exc:
            return {"parsed": {}, "raw": str(exc), "malformed": True, "actual": 0, "reason": "call_error"}
        prompt_tokens, completion, actual = usage_of(response, reserved)
        try:
            ledger.spend(actual, purpose, reserved=reserved, **meta)
        except BudgetExhausted:
            return {"parsed": {}, "raw": "", "malformed": True, "actual": 0, "reason": "budget_exhausted"}
        got = parse_tool(response)
        persist()
        return {**got, "actual": actual, "reserved": reserved, "prompt_tokens": prompt_tokens, "completion_tokens": completion, "reason": "ok"}

    silver_path = OUT / "silver_journal.jsonl"
    silver: dict[tuple[str, str], dict[str, Any]] = {}
    if silver_path.is_file():
        for line in silver_path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            silver[(row["entity_id"], row["attribute"])] = row

    sampled_by_id = {row["entity_id"]: row for row in train + held}
    scan_cache: dict[str, dict[str, Any]] = {}
    if (OUT / "scan_cache.json").is_file():
        scan_cache = json.loads((OUT / "scan_cache.json").read_text())

    def context_for(ent: dict[str, Any], attr: str) -> tuple[str, str, dict[str, Any]]:
        text = texts.get(ent["document_id"]) or ""
        wrapper = count_tokens(PROBE_PROMPT + specs[attr].official_description) + 80
        mode = route_context(wrapper, ent["doc_tokens"])
        if mode == "whole_document":
            return mode, text, inspect_record(mode, [{"index": 0, "start": 0, "end": len(text), "tokens": ent["doc_tokens"]}])
        cached = scan_cache.get(ent["entity_id"])
        if cached is None:
            chunks = exhaustive_chunks(text)
            hits: dict[str, list[str]] = defaultdict(list)
            inspected = []
            reserved_est = len(chunks) * 900
            if ledger.spent + reserved_est > THETA:
                scan_cache[ent["entity_id"]] = {"mode": mode, "hits": {}, "inspect": inspect_record(mode, chunks), "incomplete": True}
            else:
                for chunk in chunks:
                    user = (
                        f"attributes={attr_names}\n"
                        f"chunk_index={chunk['index']} offsets={chunk['start']}:{chunk['end']}\n"
                        f"text:\n{chunk['text']}"
                    )
                    got = one_call(SCAN_SCHEMA, SCAN_PROMPT, user, "silver_scan", {"entity_id": ent["entity_id"], "chunk": chunk["index"]})
                    inspected.append(chunk["index"])
                    blob = str((got.get("parsed") or {}).get("hits") or got.get("raw") or "")
                    for name in attr_names:
                        if name in blob and "NONE" not in blob.split(name, 1)[-1][:40]:
                            hits[name].append(clip(blob, 400))
                scan_cache[ent["entity_id"]] = {"mode": mode, "hits": dict(hits), "inspect": inspect_record(mode, chunks), "incomplete": False, "inspected": inspected}
                (OUT / "scan_cache.json").write_text(json.dumps(scan_cache, indent=2))
            cached = scan_cache[ent["entity_id"]]
        evidence = "\n".join(cached.get("hits", {}).get(attr) or [])
        return mode, evidence or "NO_SPAN_IN_EXHAUSTIVE_SCAN", cached.get("inspect") or {}

    jobs = [(sampled_by_id[eid], name) for eid in list(train_ids | held_ids) for name in attr_names if (eid, name) not in silver]
    jobs.sort(key=lambda pair: (pair[0]["fit"] != "whole", pair[0]["doc_tokens"], pair[0]["entity_id"], pair[1]))
    print(json.dumps({"silver_jobs": len(jobs), "already": len(silver)}, indent=2), flush=True)

    def parse_presence(parsed: dict[str, Any], raw: str) -> tuple[str, Any]:
        presence = str(parsed.get("presence") or "").strip().upper()
        value = parsed.get("normalized") or parsed.get("value") or parsed.get("label")
        if presence == "NOT_PRESENT" or str(value).strip().upper() in {"NOT_PRESENT", "NONE", "NULL"}:
            return "NOT_PRESENT", None
        if str(parsed.get("unresolved")).lower() in {"true", "1", "yes"}:
            return "unresolved", None
        if value in (None, ""):
            token = parse_choice(raw, {"NOT_PRESENT", "UNRESOLVED"})
            if token == "NOT_PRESENT":
                return "NOT_PRESENT", None
            if token == "UNRESOLVED":
                return "unresolved", None
            return "unresolved", None
        return "value", value

    for i, (ent, name) in enumerate(jobs):
        if ledger.spent + 800 > THETA:
            break
        spec = specs[name]
        mode, ctx, inspect = context_for(ent, name)
        if (scan_cache.get(ent["entity_id"]) or {}).get("incomplete"):
            row = {"entity_id": ent["entity_id"], "document_id": ent["document_id"], "attribute": name, "status": "unresolved", "reason": "scan_not_started", "mode": mode, "inspect": inspect}
            silver[(ent["entity_id"], name)] = row
            with _REAL_OPEN(silver_path, "a") as handle:
                handle.write(json.dumps(row, default=str) + "\n")
            continue
        header = f"attr={name}\ndesc={spec.official_description}\ntype={spec.dtype}/{spec.sql_type}\nentity_role=the entity described by this document"
        if spec.schema_domain:
            header += f"\nlabels={spec.schema_domain}"
        user = header + "\n\nsource:\n" + ctx
        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(one_call, PROBE_SCHEMA, PROBE_PROMPT + " Probe replica A.", user, "silver_probe", {"attribute": name, "split": "train" if ent["entity_id"] in train_ids else "heldout"})
            f2 = pool.submit(one_call, PROBE_SCHEMA, PROBE_PROMPT + " Probe replica B.", user, "silver_probe", {"attribute": name, "split": "train" if ent["entity_id"] in train_ids else "heldout"})
            g1, g2 = f1.result(), f2.result()
        p1, v1 = parse_presence(g1.get("parsed") or {}, g1.get("raw") or "")
        p2, v2 = parse_presence(g2.get("parsed") or {}, g2.get("raw") or "")
        status, value, adj = p1, v1, None
        if p1 == p2 == "value" and str(v1).strip().lower() == str(v2).strip().lower():
            status, value = "value", v1
        elif p1 == p2 == "NOT_PRESENT":
            status, value = "NOT_PRESENT", None
        else:
            adj_user = header + f"\nA={g1.get('parsed')}\nB={g2.get('parsed')}\n\nsource:\n" + clip(ctx, 6000)
            adj = one_call(ADJ_SCHEMA, ADJ_PROMPT, adj_user, "silver_adjudicate", {"attribute": name})
            status, value = parse_presence(adj.get("parsed") or {}, adj.get("raw") or "")
        if status == "value" and spec.schema_domain:
            cls = one_call(CLASS_SCHEMA, CLASS_PROMPT, header + f"\nevidence={value}\nspans={(g1.get('parsed') or {}).get('spans')}", "silver_classify", {"attribute": name})
            status, value = parse_presence(cls.get("parsed") or {}, cls.get("raw") or "")
            if status == "value" and str(value) not in spec.schema_domain:
                close = [lab for lab in spec.schema_domain if str(lab).lower() == str(value).lower()]
                value = close[0] if close else value
        rec = by_ent_attr.get((ent["entity_id"], name)) or by_doc_attr.get((ent["document_id"], name))
        mapped = map_to_candidate(value, det_items(rec), spec) if rec and status == "value" else None
        row = {
            "entity_id": ent["entity_id"],
            "document_id": ent["document_id"],
            "attribute": name,
            "status": status,
            "value": value,
            "mapped_id": mapped,
            "mode": mode,
            "inspect": inspect,
            "probe_a": g1,
            "probe_b": g2,
            "adjudicate": adj,
            "split": "train" if ent["entity_id"] in train_ids else "heldout",
        }
        silver[(ent["entity_id"], name)] = row
        with _REAL_OPEN(silver_path, "a") as handle:
            handle.write(json.dumps(row, default=str) + "\n")
        if (i + 1) % 20 == 0:
            print(json.dumps({"silver_done": i + 1, "spent": ledger.spent}, indent=2), flush=True)

    (OUT / "scan_cache.json").write_text(json.dumps(scan_cache, indent=2))
    silver_stats = {
        "n": len(silver),
        "value": sum(1 for row in silver.values() if row.get("status") == "value"),
        "not_present": sum(1 for row in silver.values() if row.get("status") == "NOT_PRESENT"),
        "unresolved": sum(1 for row in silver.values() if row.get("status") == "unresolved"),
        "adjudicated": sum(1 for row in silver.values() if row.get("adjudicate")),
        "mapped": sum(1 for row in silver.values() if row.get("mapped_id")),
        "modes": dict(Counter(row.get("mode") for row in silver.values())),
    }
    (OUT / "silver_stats.json").write_text(json.dumps(silver_stats, indent=2))
    print(json.dumps({"phase1": True, **silver_stats, "spent": ledger.spent}, indent=2), flush=True)

    tokens_by = {name: spec_tokens(name, specs[name].official_description) for name in attr_names}
    feats_by: dict[tuple[str, str], list[dict[str, Any]]] = {}
    rows_by_attr: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in inventory:
        text = texts.get(rec["document_id"]) or ""
        feats_by[(rec["entity_id"], rec["attribute"])] = annotate_det(rec, tokens_by[rec["attribute"]], len(text))
        rows_by_attr[rec["attribute"]].append(rec)

    programs: dict[str, list[dict[str, Any]]] = {name: [] for name in attr_names}
    if (OUT / "programs.json").is_file():
        programs = json.loads((OUT / "programs.json").read_text())
    else:
        for name in attr_names:
            spec = specs[name]
            train_rows = [rec for rec in rows_by_attr[name] if rec["entity_id"] in train_ids]
            bank = allowed_term_bank(spec.official_description, name, [feats_by.get((rec["entity_id"], name), []) for rec in train_rows])
            literals = []
            entity_names = [rec["document_id"] for rec in train_rows]
            for k in range(N_PROGRAMS):
                rng = random.Random(SEED + 17 * k + int(hashlib.sha256(name.encode()).hexdigest()[:8], 16) % 997)
                shuffled = list(train_rows)
                rng.shuffle(shuffled)
                sample_rows = sample_attribute(shuffled, feats_by, min(8, len(shuffled)))
                bundled_user = compiler_user(spec, sample_rows, feats_by)
                got = one_call(COMPILER_SCHEMA, PLANNER_PROMPT, bundled_user, "program_synthesize", {"attribute": name, "k": k})
                raw_spec = normalize_spec(got.get("parsed") or {}, name, spec.task_class)
                raw_spec = restore_schema_policy(raw_spec, description=spec.official_description, allows_sum=spec.allows_sum, unit_percent=spec.unit_percent, domain=spec.schema_domain)
                errors = validate_spec(raw_spec, name=name, description=spec.official_description, bank=bank, literals=literals, entity_names=entity_names)
                fail = []
                for rec in train_rows:
                    pred = execute_program(raw_spec, feats_by.get((rec["entity_id"], name), []))
                    silver_row = silver.get((rec["entity_id"], name))
                    if not silver_row or silver_row.get("status") != "value":
                        continue
                    chosen = (pred.get("candidate_ids") or [None])[0]
                    if pred.get("status") != "selected" or chosen != silver_row.get("mapped_id"):
                        fail.append({"reason": pred.get("reason") or "mismatch"})
                summary = f"training_errors={len(fail)} abstain_or_mismatch_examples={fail[:6]}"
                if errors or fail:
                    fix = one_call(COMPILER_SCHEMA, CRITIQUE_PROMPT, summary + "\n" + json.dumps(raw_spec), "program_critique", {"attribute": name, "k": k})
                    raw_spec = apply_critic_fixes(normalize_spec(fix.get("parsed") or raw_spec, name, spec.task_class), fix.get("parsed") or {}, bank=bank, description=spec.official_description, allows_sum=spec.allows_sum, unit_percent=spec.unit_percent, domain=spec.schema_domain)
                    errors = validate_spec(raw_spec, name=name, description=spec.official_description, bank=bank, literals=literals, entity_names=entity_names)
                if errors:
                    raw_spec = empty_spec(name, spec.task_class)
                    raw_spec["rejected"] = errors
                raw_spec["program_id"] = f"{name}:{k}"
                programs[name].append(raw_spec)
            print(json.dumps({"compiled": name, "n": len(programs[name]), "spent": ledger.spent}, indent=2), flush=True)
        (OUT / "programs.json").write_text(json.dumps(programs, indent=2))

    def fills_from_choice(choice: dict[str, str], entity_ids: set[str] | None = None) -> dict[str, dict[str, Any]]:
        fills: dict[str, dict[str, Any]] = defaultdict(dict)
        for rec in inventory:
            if entity_ids is not None and rec["entity_id"] not in entity_ids:
                continue
            cid = choice.get(f"{rec['entity_id']}::{rec['attribute']}")
            if not cid or cid == KEEP:
                continue
            item = next((item for item in det_items(rec) if str(item.get("id")) == cid), None)
            if item is None or _null(item.get("normalized")):
                continue
            fills[rec["document_id"]][rec["attribute"]] = item.get("normalized")
        return dict(fills)

    def apply_config(config: dict[str, str], entity_ids: set[str] | None = None) -> dict[str, str]:
        choice = {}
        for rec in inventory:
            if entity_ids is not None and rec["entity_id"] not in entity_ids:
                continue
            name = rec["attribute"]
            prog = next(item for item in programs[name] if item["program_id"] == config[name])
            pred = execute_program(prog, feats_by.get((rec["entity_id"], name), []))
            cid = (pred.get("candidate_ids") or [None])[0] if pred.get("status") == "selected" else None
            choice[f"{rec['entity_id']}::{name}"] = cid or KEEP
        return choice

    def cell_metrics(choice: dict[str, str], entity_ids: set[str]) -> dict[str, float]:
        exact = obs = support_tp = support_fp = support_fn = period_ok = n = abstain = 0
        evaluator_rows = [plumbing_by[eid] for eid in entity_ids if eid in plumbing_by]
        for eid in entity_ids:
            row = dict(plumbing_by[eid])
            for name in attr_names:
                n += 1
                key = f"{eid}::{name}"
                cid = choice.get(key)
                silver_row = silver.get((eid, name))
                if not cid or cid == KEEP:
                    abstain += 1
                    if silver_row and silver_row.get("status") == "value":
                        support_fn += 1
                    continue
                rec = by_ent_attr.get((eid, name))
                item = next((item for item in det_items(rec or {}) if str(item.get("id")) == cid), None)
                pred = None if item is None else item.get("normalized")
                ref = silver_row.get("value") if silver_row else None
                if silver_row and silver_row.get("status") == "value" and pred is not None and str(pred).strip().lower() == str(ref).strip().lower():
                    exact += 1
                    support_tp += 1
                elif silver_row and silver_row.get("status") == "value":
                    support_fp += 1
                if silver_row and item and str(item.get("period") or "") == str((silver_row.get("probe_a") or {}).get("parsed", {}).get("period") or str(item.get("period") or "")):
                    period_ok += 1
        prec = support_tp / max(support_tp + support_fp, 1)
        reca = support_tp / max(support_tp + support_fn, 1)
        return {
            "exact": exact / max(n, 1),
            "observational": exact / max(n, 1),
            "support_precision": prec,
            "support_recall": reca,
            "period_role": period_ok / max(n, 1),
            "abstention": abstain / max(n, 1),
            "n": n,
        }

    silver_choice = {}
    for (eid, name), row in silver.items():
        silver_choice[f"{eid}::{name}"] = row.get("mapped_id") or KEEP
    held_base = OUT / "databases" / "held_base.db"
    restrict_db(PLUMBING, held_base, held_ids)
    silver_held_fills = fills_from_choice(silver_choice, held_ids)
    silver_held = materialize(OUT / "databases" / "held_silver.db", silver_held_fills, mapping, statements, predicates, query_ids, base=held_base)
    held_rows = []
    conn = sqlite3.connect(f"file:{OUT / 'databases' / 'held_silver.db'}?mode=ro", uri=True)
    hcols = [row[1] for row in conn.execute(f'PRAGMA table_info("{TABLE}")')]
    for rec in conn.execute(f'SELECT * FROM "{TABLE}"'):
        held_rows.append(dict(zip(hcols, rec)))
    conn.close()
    silver_gold = {"legal": held_rows}

    def eval_config(config: dict[str, str], label: str) -> dict[str, Any]:
        choice = apply_config(config, held_ids)
        fills = fills_from_choice(choice, held_ids)
        dest = OUT / "databases" / f"held_{label}.db"
        mat = materialize(dest, fills, mapping, statements, predicates, query_ids, base=held_base)
        scored = score_against(dest, silver_gold, statements, predicates, query_ids)
        products = [row["product"] for row in scored["per_query"]]
        cells = cell_metrics(choice, held_ids)
        writes = sum(1 for cid in choice.values() if cid and cid != KEEP)
        cost = sum(r.tokens for r in ledger.records if r.metadata.get("attribute") in config and r.purpose.startswith("program_"))
        return {
            "config": config,
            "label": label,
            "product": scored["mean_per_query_product"],
            "lcb": bootstrap_lcb(products, seed=SEED),
            "f2": scored["mean_structure_f2"],
            "f1": scored["mean_cell_f1_at_0.20"],
            "cells": cells,
            "writes": writes,
            "cost": cost,
            "per_query": scored["per_query"],
            "bag_sha256": mat["bag_sha256"],
            "choice": choice,
        }

    per_attr_rank = {}
    considered = []
    for name in attr_names:
        ranked = []
        for prog in programs[name]:
            cfg = {other: programs[other][0]["program_id"] for other in attr_names}
            cfg[name] = prog["program_id"]
            # cell-only rank for this attribute
            choice = apply_config({**{o: programs[o][0]["program_id"] for o in attr_names}, name: prog["program_id"]}, held_ids)
            ranked.append((cell_metrics(choice, held_ids)["exact"], -cell_metrics(choice, held_ids)["abstention"], prog["program_id"]))
        ranked.sort(reverse=True)
        per_attr_rank[name] = [item[2] for item in ranked]
    beam = [{name: per_attr_rank[name][0] for name in attr_names}]
    scored_cfgs = [eval_config(beam[0], "beam0")]
    considered.append(scored_cfgs[0])
    print(json.dumps({"beam0": scored_cfgs[0]["product"], "lcb": scored_cfgs[0]["lcb"]}, indent=2), flush=True)
    for name in attr_names:
        for pid in per_attr_rank[name][1:]:
            cand = dict(scored_cfgs[0]["config"])
            cand[name] = pid
            label = f"swap_{name}_{pid.split(':')[-1]}"
            got = eval_config(cand, label)
            considered.append(got)
            scored_cfgs.append(got)
            scored_cfgs.sort(key=lambda row: (-row["lcb"], -row["cells"]["observational"], -row["cells"]["exact"], row["cost"], row["writes"]))
            scored_cfgs = scored_cfgs[:8]
            print(json.dumps({"tried": label, "product": got["product"], "best_lcb": scored_cfgs[0]["lcb"]}, indent=2), flush=True)

    def rank_key(row: dict[str, Any]) -> tuple:
        return (-row["lcb"], -row["cells"]["observational"], -row["cells"]["exact"], row["cost"], row["writes"])

    considered.sort(key=rank_key)
    top = considered[:3]
    pairwise_rows = []
    if len(top) >= 2:
        a_choice, b_choice = top[0]["choice"], top[1]["choice"]
        diffs = [key for key in a_choice if a_choice.get(key) != b_choice.get(key)]
        rng = random.Random(SEED)
        rng.shuffle(diffs)
        for key in diffs[:24]:
            eid, name = key.split("::", 1)
            if eid not in held_ids:
                continue
            ent = sampled_by_id[eid]
            rec = by_ent_attr.get((eid, name))
            items = {str(item.get("id")): item for item in det_items(rec or {})}
            def alt(cid: str | None) -> str:
                if not cid or cid == KEEP:
                    return "NULL / no value written"
                item = items.get(cid) or {}
                return f"value={item.get('normalized')} span={clip(item.get('raw_span'), 80)}"
            x_is_a = rng.random() < 0.5
            left, right = (a_choice[key], b_choice[key]) if x_is_a else (b_choice[key], a_choice[key])
            user = f"attr={name}\ndesc={specs[name].official_description}\nX: {alt(left)}\nY: {alt(right)}\n\nsource:\n{clip(texts.get(ent['document_id']) or '', 5000)}"
            got = one_call(PAIR_SCHEMA, PAIR_PROMPT, user, "pairwise_validate", {"attribute": name})
            label = str((got.get("parsed") or {}).get("choice") or "").strip().upper()
            if label not in {"X", "Y"}:
                label = parse_choice(got.get("raw") or "", {"X", "Y"}) or ""
            winner = None
            if label == "X":
                winner = "A" if x_is_a else "B"
            elif label == "Y":
                winner = "B" if x_is_a else "A"
            pairwise_rows.append({"key": key, "winner": winner, "label": label})
    pair_votes = Counter(row["winner"] for row in pairwise_rows if row.get("winner"))
    if pair_votes and abs(top[0]["lcb"] - (top[1]["lcb"] if len(top) > 1 else -1)) < 0.01:
        if pair_votes.get("B", 0) > pair_votes.get("A", 0):
            top[0], top[1] = top[1], top[0]
    winner = top[0]
    (OUT / "validation.json").write_text(json.dumps({"considered": [{k: row[k] for k in row if k != "choice"} for row in considered], "pairwise": pairwise_rows, "winner": {k: winner[k] for k in winner if k != "choice"}}, indent=2, default=str))
    (OUT / "selected_config.json").write_text(json.dumps(winner["config"], indent=2))
    print(json.dumps({"phase3": True, "winner": winner["config"], "heldout_product": winner["product"], "lcb": winner["lcb"]}, indent=2), flush=True)

    full_choice = apply_config(winner["config"])
    assignment = {}
    responsible = {}
    for rec in inventory:
        key = f"{rec['entity_id']}::{rec['attribute']}"
        cid = full_choice.get(key) or KEEP
        assignment.setdefault(rec["document_id"], {})[rec["attribute"]] = cid
        responsible[key] = {"candidate_id": cid, "program": winner["config"][rec["attribute"]]}
    (OUT / "assignment_manifest.json").write_text(json.dumps(assignment, indent=2))
    (OUT / "assignment_trace.json").write_text(json.dumps(responsible, indent=2))
    official_fills = fills_from_choice(full_choice)
    official = materialize(OUT / "databases" / "official.db", official_fills, mapping, statements, predicates, query_ids)
    rebuild = materialize(OUT / "databases" / "official_rebuild.db", official_fills, mapping, statements, predicates, query_ids)
    if official["bag_sha256"] != rebuild["bag_sha256"]:
        raise SystemExit("run invalid: rebuild bags are not byte-identical")
    empty = materialize(OUT / "databases" / "empty_overlay.db", {}, mapping, statements, predicates, query_ids)
    plumbing_bags = {qid: official_bag(PLUMBING, statements[qid], predicates, qid) for qid in query_ids}
    if empty["bag_sha256"] != _hash(plumbing_bags):
        raise SystemExit("run invalid: empty overlay does not reproduce plumbing")
    conn = sqlite3.connect(f"file:{OUT / 'databases' / 'official.db'}?mode=ro", uri=True)
    ids = [row[0] for row in conn.execute(f'SELECT __entity_id FROM "{TABLE}" ORDER BY __entity_id')]
    n_rows = len(ids)
    conn.close()
    if n_rows != 570 or ids != [row["__entity_id"] for row in sorted(plumbing_rows, key=lambda r: r["__entity_id"])]:
        raise SystemExit("run invalid: identity checksum mismatch")
    for name, cfg in enumerate([row["config"] for row in top], start=1):
        if cfg == winner["config"]:
            continue
        choice = apply_config(cfg)
        materialize(OUT / "databases" / f"diag_config_{name}.db", fills_from_choice(choice), mapping, statements, predicates, query_ids)

    (OUT / "bags" / "official.json").parent.mkdir(parents=True, exist_ok=True)
    (OUT / "bags" / "official.json").write_text(json.dumps(official["bags"], indent=2, default=str))
    purpose = {k: sum(r.tokens for r in ledger.records if r.purpose == k) for k in {r.purpose for r in ledger.records}}
    pre_gold = {
        "sample": {"train": len(train), "heldout": len(held), "composition": sample_payload},
        "silver": silver_stats,
        "programs": {name: [prog["program_id"] for prog in programs[name]] for name in attr_names},
        "selected": winner["config"],
        "heldout_winner": {k: winner[k] for k in ("product", "lcb", "f2", "f1", "writes", "cells")},
        "considered": [{k: row[k] for k in ("label", "product", "lcb", "writes", "config")} for row in considered],
        "tokens_by_purpose": purpose,
        "causal_spent": ledger.spent,
        "accepted": sum(1 for cid in full_choice.values() if cid and cid != KEEP),
        "changed_cells": official["overlay"].get("changed_cells"),
        "forbidden_inaccessible": True,
    }
    (OUT / "pre_gold.json").write_text(json.dumps(pre_gold, indent=2, default=str))
    (OUT / "theta25_ledger.json").write_text(json.dumps(ledger.snapshot(), indent=2, default=str))
    generation = {
        "design": sha(design),
        "sample": sha(sample_payload),
        "prompts": sha(prompts),
        "silver_journal": file_sha256(silver_path) if silver_path.is_file() else None,
        "programs": sha(programs),
        "validation": file_sha256(OUT / "validation.json"),
        "selected": sha(winner["config"]),
        "assignment": file_sha256(OUT / "assignment_manifest.json"),
        "official_db": official["db_sha256"],
        "official_bags": official["bag_sha256"],
        "rebuild_match": True,
        "ledger": ledger.fingerprint(),
        "spent": ledger.spent,
        "gold_loaded": False,
        "forbidden_inaccessible": True,
    }
    (OUT / "generation_frozen.json").write_text(json.dumps(generation, indent=2))
    print(json.dumps({"frozen": True, "spent": ledger.spent, "accepted": pre_gold["accepted"], "heldout_product": winner["product"]}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
