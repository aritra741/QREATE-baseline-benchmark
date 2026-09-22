"""Zero-Qwen reproduction-gap audit and cross-query consistency replay. No model calls."""

from __future__ import annotations

import difflib
import hashlib
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import quantiles
from typing import Any

from sqlglot import exp

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.docetl_exact_message.adapter import (
    DOCETL_MODEL,
    DOCETL_SYSTEM,
    first_differing_byte,
    generate_primary_messages,
    numeric_fields_from_attributes,
    schema_from_ast,
    strip_transport,
)
from quwarts.core.docetl_unit_parity.schema import compile_query_schema
from quwarts.core.full_window_additive.config import MODEL as QUWARTS_MODEL
from quwarts.core.full_window_additive.config import POLICY, SYSTEM as QUWARTS_SYSTEM
from quwarts.core.full_window_additive.overlay import apply_overlay, copy_plumbing, official_bag
from quwarts.core.full_window_additive.parse import MISSING
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.core.workload import parse_sql
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites

REPLAY = ROOT / "results" / "docetl_finan_current_snapshot_replay"
FRESH = ROOT / "results" / "quwarts_finan_full_window_additive"
PLUMBING = ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
DOCETL_CASE = ROOT / "results" / "docetl_finan_case80"
ATTR_PATH = ROOT / "Query" / "Finan" / "Finan_attributes.json"
SOURCE_DIR = ROOT / "source_data" / "Finance" / "finance"
OUT = ROOT / "results" / "finan_reproduction_gap_audit"
DOCS = ["9", "10", "18", "69", "70", "78", "93"]
EXPECTED_R0 = 0.029229085972507028
PLUMBING_PRODUCT = 0.0158
DOCETL_PRODUCT = 0.084
M4_PRODUCT = 0.0904
M4_IMPROVED = {
    "finan_multiagg20:q4",
    "finan_multiagg20:q11",
    "finan_groupby20:q14",
    "finan_agg20:q11",
    "finan_filter20:q8",
    "finan_agg20:q14",
}
FRESH_IMPROVED = {"finan_multiagg20:q4", "finan_groupby20:q14", "finan_filter20:q8"}
REPLAY_RULES = {
    "R0": "Local replay of frozen fresh-arm accepted fills. No sharing.",
    "R1": "Share unanimous repeated non-missing values into every referencing query-local NULL cell.",
    "R2": "R1, then abstain every conflicting canonical key back to plumbing.",
    "R3": "Share a unique strict majority of at least two votes. Ties abstain. Singletons stay local.",
}


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def split_user(user: str) -> tuple[str, str]:
    marker = "Document:\n"
    if marker in (user or ""):
        wrap, doc = user.split(marker, 1)
        return wrap + marker, doc
    return user or "", ""


def load_primary_docetl(journal: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    first: dict[tuple[str, str], dict[str, Any]] = {}
    for row in journal:
        doc_id = row.get("document_id")
        if doc_id in (None, ""):
            continue
        key = (str(row.get("query_id")), str(doc_id))
        if key not in first:
            first[key] = row
    return first


def wrapper_class(d_wrap: str, q_wrap: str) -> str:
    if d_wrap == q_wrap:
        return "byte_identical"
    d_core = "You are building a structured" in d_wrap and "If a numeric field is unknown, return -1." in d_wrap
    q_core = "You are building a structured" in q_wrap and "If a numeric field is unknown, return -1." in q_wrap
    if d_core and q_core and d_wrap.split("Document:\n")[0].strip() == q_wrap.split("Document:\n")[0].strip():
        return "semantically_identical_byte_different"
    return "different"


def token_window(text: str) -> list[int]:
    from quwarts.core.retrieve_extract.tokens import qwen_tokenizer

    return list(qwen_tokenizer().encode(text or "").ids)


def overlap_stats(left: list[int], right: list[int]) -> dict[str, Any]:
    sl, sr = set(left), set(right)
    union = sl | sr
    inter = sl & sr
    return {
        "jaccard": (len(inter) / len(union)) if union else 1.0,
        "only_docetl": len(sl - sr),
        "only_quwarts": len(sr - sl),
        "shared": len(inter),
        "n_docetl": len(left),
        "n_quwarts": len(right),
    }


def plumbing_cells() -> tuple[dict[tuple[str, str], Any], dict[str, str]]:
    conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(finance)")]
    rows = [dict(zip(cols, rec)) for rec in conn.execute("SELECT * FROM finance")]
    conn.close()
    mapping: dict[str, str] = {}
    cells: dict[tuple[str, str], Any] = {}
    for row in rows:
        raw = str(row.get("doc_id") or "")
        stem = Path(raw).stem
        mapping[stem] = raw
        for col, value in row.items():
            cells[(stem, col)] = value
            cells[(raw, col)] = value
    return cells, mapping


def build_canonical(journal: list[dict[str, Any]], schemas: dict[str, Any], cells: dict[tuple[str, str], Any]) -> dict[str, Any]:
    keys: dict[tuple[str, str], dict[str, Any]] = {}
    for row in journal:
        qid = row["query_id"]
        doc_id = str(row["doc_id"])
        for name, item in (row.get("items") or {}).items():
            key = (doc_id, name)
            slot = keys.setdefault(
                key,
                {
                    "document_id": doc_id,
                    "attribute": name,
                    "judgments": [],
                    "values": [],
                    "queries": [],
                },
            )
            accepted = item.get("accepted")
            slot["judgments"].append({"query_id": qid, "accepted": accepted, "reason": item.get("reason")})
            slot["queries"].append(qid)
            if accepted is not None and accepted not in MISSING:
                slot["values"].append(accepted)
    inventory = []
    for (doc_id, name), slot in sorted(keys.items()):
        values = slot["values"]
        counts = Counter(json.dumps(v, sort_keys=True, default=str) for v in values)
        distinct = []
        seen = set()
        for value in values:
            mark = json.dumps(value, sort_keys=True, default=str)
            if mark not in seen:
                seen.add(mark)
                distinct.append(value)
        majority_n = max(counts.values()) if counts else 0
        majority_keys = [k for k, n in counts.items() if n == majority_n]
        majority = json.loads(majority_keys[0]) if len(majority_keys) == 1 and majority_n >= 2 else None
        unanimous = distinct[0] if len(distinct) == 1 and len(values) >= 2 else None
        plumbing = cells.get((doc_id, name), cells.get((f"{doc_id}.txt", name)))
        overlay_values = {}
        for qid in dict.fromkeys(slot["queries"]):
            if name not in {item.name for item in schemas[qid].fields}:
                continue
            accepted = next((j["accepted"] for j in slot["judgments"] if j["query_id"] == qid), None)
            overlay_values[qid] = accepted
        inventory.append(
            {
                "document_id": doc_id,
                "attribute": name,
                "n_judgments": len(slot["judgments"]),
                "n_nonmissing": len(values),
                "distinct": distinct,
                "unanimous": unanimous,
                "majority": majority,
                "majority_n": majority_n if majority is not None else 0,
                "conflict": len(distinct) > 1,
                "queries": list(dict.fromkeys(slot["queries"])),
                "judgments": slot["judgments"],
                "plumbing_null": plumbing is None,
                "plumbing_value": plumbing,
                "overlay_values": overlay_values,
                "overlays_agree": len({json.dumps(v, default=str) for v in overlay_values.values()}) <= 1,
            }
        )
    return {
        "keys": inventory,
        "singleton": sum(1 for row in inventory if row["n_judgments"] == 1),
        "repeated": sum(1 for row in inventory if row["n_judgments"] > 1),
        "unanimous_repeated": sum(1 for row in inventory if row["unanimous"] is not None),
        "conflicting_repeated": sum(1 for row in inventory if row["conflict"] and row["n_judgments"] > 1),
        "majority_resolved": sum(1 for row in inventory if row["majority"] is not None),
        "missing_only": sum(1 for row in inventory if row["n_nonmissing"] == 0),
    }


def rule_fills(rule: str, journal: list[dict[str, Any]], canonical: dict[str, Any], schemas: dict[str, Any]) -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, int]]:
    fills: dict[str, dict[str, dict[str, Any]]] = defaultdict(lambda: defaultdict(dict))
    for row in journal:
        fills[row["query_id"]][str(row["doc_id"])] = {k: v for k, v in (row.get("accepted") or {}).items() if v not in MISSING}
    stats = {"shared": 0, "abstained": 0, "local": 0}
    index = {(row["document_id"], row["attribute"]): row for row in canonical["keys"]}
    if rule == "R0":
        stats["local"] = sum(len(doc) for q in fills.values() for doc in q.values())
        return fills, stats
    for (doc_id, attr), inv in index.items():
        refs = [qid for qid, schema in schemas.items() if attr in schema.names]
        if rule == "R1":
            if inv["unanimous"] is not None and inv["plumbing_null"]:
                for qid in refs:
                    fills[qid][doc_id][attr] = inv["unanimous"]
                    stats["shared"] += 1
        elif rule == "R2":
            if inv["conflict"]:
                for qid in refs:
                    if attr in fills[qid][doc_id]:
                        fills[qid][doc_id].pop(attr, None)
                        stats["abstained"] += 1
            elif inv["unanimous"] is not None and inv["plumbing_null"]:
                for qid in refs:
                    fills[qid][doc_id][attr] = inv["unanimous"]
                    stats["shared"] += 1
        elif rule == "R3":
            if inv["majority"] is not None and inv["plumbing_null"]:
                for qid in refs:
                    fills[qid][doc_id][attr] = inv["majority"]
                    stats["shared"] += 1
    stats["local"] = sum(len(doc) for q in fills.values() for doc in q.values())
    return fills, stats


def materialize(label: str, fills: dict[str, dict[str, dict[str, Any]]], mapping: dict[str, str], statements: dict[str, str], predicates) -> dict[str, Any]:
    dest_dir = OUT / "overlays" / label
    dest_dir.mkdir(parents=True, exist_ok=True)
    overlays = {}
    bags = {}
    for qid, sql in statements.items():
        dest = dest_dir / f"{qid.replace(':', '_')}.db"
        copy_plumbing(PLUMBING, dest)
        overlays[qid] = apply_overlay(dest, fills.get(qid, {}), mapping)
        bags[qid] = official_bag(dest, sql, predicates, qid)
    return {"overlays": overlays, "bags": bags, "dir": dest_dir}


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
                "pred_rows": row.get("pred_rows"),
            }
            for row in report.get("per_query") or []
        ],
    }


def score_dir(overlay_dir: Path, statements: dict[str, str], predicates, score_rows, count_rows, gold) -> dict[str, Any]:
    rewrites = {}
    for qid, sql in statements.items():
        dest = overlay_dir / f"{qid.replace(':', '_')}.db"
        rewrites[qid] = {
            "sql": official_sql(sql, dest, predicates, query_id=qid),
            "sqlite_path": str(dest),
        }
    s16 = _score(PLUMBING, score_rows, rewrites, gold)
    s15 = _score(PLUMBING, count_rows, {row["query_id"]: rewrites[row["query_id"]] for row in count_rows}, gold)
    return {"score_16": s16, "score_15": s15}


def row_for(db: Path, doc_id: str, mapping: dict[str, str]) -> dict[str, Any] | None:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cols = [item[1] for item in conn.execute("PRAGMA table_info(finance)")]
    found = None
    for key in (mapping.get(doc_id, f"{doc_id}.txt"), f"{doc_id}.txt", doc_id):
        rec = conn.execute("SELECT * FROM finance WHERE CAST(doc_id AS TEXT)=?", (key,)).fetchone()
        if rec is not None:
            found = dict(zip(cols, rec))
            break
    conn.close()
    return found


def truth_changed(db_a: Path, db_b: Path, sql: str, doc_id: str, mapping: dict[str, str]) -> dict[str, bool]:
    tree = parse_sql(sql)
    where = tree.args.get("where")
    group = tree.args.get("group")
    cases = list(tree.find_all(exp.Case))
    out = {"predicate": False, "case": False, "group": False, "support": False}
    keys = (mapping.get(doc_id, f"{doc_id}.txt"), f"{doc_id}.txt", doc_id)

    def eval_flag(db: Path, expr: str) -> Any:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            for key in keys:
                rec = conn.execute(f"SELECT ({expr}) FROM finance WHERE CAST(doc_id AS TEXT)=?", (key,)).fetchone()
                if rec is not None:
                    return rec[0]
            return None
        except sqlite3.Error:
            return "err"
        finally:
            conn.close()

    if where is not None:
        expr = where.this.sql(dialect="sqlite")
        out["predicate"] = eval_flag(db_a, expr) != eval_flag(db_b, expr)
        out["support"] = bool(eval_flag(db_b, expr)) != bool(eval_flag(db_a, expr))
    for node in cases:
        expr = node.sql(dialect="sqlite")
        if eval_flag(db_a, expr) != eval_flag(db_b, expr):
            out["case"] = True
    if group is not None:
        parts = [item.sql(dialect="sqlite") for item in group.expressions]
        left = tuple(eval_flag(db_a, p) for p in parts)
        right = tuple(eval_flag(db_b, p) for p in parts)
        out["group"] = left != right
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    plumbing_sha = file_sha256(PLUMBING)
    replay_frozen_sha = file_sha256(REPLAY / "frozen.json")
    fresh_frozen_sha = file_sha256(FRESH / "frozen.json")
    fresh_journal_sha = file_sha256(FRESH / "theta100_journal.json")
    replay_journal_sha = file_sha256(REPLAY / "call_journal.json")

    manifest = [{"query_id": str(row["query_id"]), "sql": str(row["sql"])} for row in json.loads((DOCETL_CASE / "query_manifest.json").read_text())]
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    schemas = {qid: compile_query_schema(qid, statements[qid]) for qid in query_ids}
    numeric = numeric_fields_from_attributes(ATTR_PATH)
    mapping = {doc_id: f"{doc_id}.txt" for doc_id in DOCS}
    texts = {doc_id: (SOURCE_DIR / mapping[doc_id]).read_text(encoding="utf-8", errors="replace") for doc_id in DOCS}
    cells, live_map = plumbing_cells()
    mapping.update(live_map)

    fresh_prompts = json.loads((FRESH / "rendered_prompts.json").read_text())
    fresh_journal = json.loads((FRESH / "theta100_journal.json").read_text())
    docetl_journal = json.loads((REPLAY / "call_journal.json").read_text())
    docetl_primary = load_primary_docetl(docetl_journal)
    replay_frozen = json.loads((REPLAY / "frozen.json").read_text())
    fresh_frozen = json.loads((FRESH / "frozen.json").read_text())

    audit_rows = []
    jaccards = []
    only_d = []
    only_q = []
    classes = Counter()
    window_identical = 0
    prompt_byte = 0
    prompt_semantic = 0
    prompt_different = 0
    cause = Counter()
    for qid in query_ids:
        q_schema = schemas[qid]
        for doc_id in DOCS:
            q_prompt = next(row for row in fresh_prompts if row["query_id"] == qid and row["doc_id"] == doc_id)
            d_row = docetl_primary.get((qid, doc_id))
            q_sys, q_user = q_prompt.get("system") or QUWARTS_SYSTEM, q_prompt.get("user") or ""
            q_wrap, q_doc = split_user(q_user)
            if d_row is None:
                audit_rows.append({"query_id": qid, "document_id": doc_id, "status": "docetl_primary_missing"})
                cause["docetl_primary_missing"] += 1
                prompt_different += 1
                classes["different"] += 1
                continue
            d_sys, d_user = d_row.get("system_message") or "", d_row.get("user_message") or ""
            d_wrap, d_doc = split_user(d_user)
            if not d_doc:
                d_doc = d_row.get("included_document_text") or ""
            fields_d = list((d_row.get("output_schema") or replay_frozen.get("schemas", {}).get(qid) or q_schema.names))
            fields_q = list(q_schema.names)
            d_types = d_row.get("output_schema") or {name: ("number" if name in numeric else "str") for name in fields_d}
            q_types = {item.name: item.dtype for item in q_schema.fields}
            sys_eq = d_sys == q_sys
            wrap_eq = d_wrap == q_wrap
            fields_eq = fields_d == fields_q
            prompt_eq = (d_sys, d_user) == (q_sys, q_user)
            win_eq = d_doc == q_doc
            klass = "byte_identical" if prompt_eq else wrapper_class(d_wrap, q_wrap)
            if not sys_eq:
                klass = "different"
                cause["system_message"] += 1
            if klass == "different" and not wrap_eq:
                cause["user_wrapper"] += 1
            if not fields_eq:
                cause["field_names_or_order"] += 1
            if (d_row.get("temperature") != POLICY["temperature"]) or (d_row.get("completion_cap") != POLICY["completion_cap"]):
                cause["generation_parameters"] += 1
            if str(d_row.get("model") or "") != QUWARTS_MODEL:
                cause["model_identifier"] += 1
            if not win_eq:
                cause["document_window"] += 1
            if d_row.get("surviving_portion") != "middle_cut" or True:
                if bool(d_row.get("truncated")) != bool(q_prompt.get("truncated")):
                    cause["truncation_flag"] += 1
            cause["json_vs_tool_schema"] += 1
            if prompt_eq:
                prompt_byte += 1
            elif klass == "semantically_identical_byte_different":
                prompt_semantic += 1
            else:
                prompt_different += 1
            if win_eq:
                window_identical += 1
            q_ids = token_window(q_doc)
            d_ids = token_window(d_doc)
            ov = overlap_stats(d_ids, q_ids)
            jaccards.append(ov["jaccard"])
            only_d.append(ov["only_docetl"])
            only_q.append(ov["only_quwarts"])
            d_off = d_row.get("source_offsets") or {}
            q_start = texts[doc_id].find(q_doc[: min(len(q_doc), 200)]) if q_doc else -1
            audit_rows.append(
                {
                    "query_id": qid,
                    "document_id": doc_id,
                    "prompt_class": klass,
                    "system_equal": sys_eq,
                    "wrapper_equal": wrap_eq,
                    "fields_equal": fields_eq,
                    "field_names_docetl": fields_d,
                    "field_names_quwarts": fields_q,
                    "types_docetl": d_types,
                    "types_quwarts": q_types,
                    "missing_value_instructions_both": ("return -1" in d_wrap and "return -1" in q_wrap),
                    "evidence_instructions": {"docetl": "none_in_user", "quwarts": "none_in_user"},
                    "query_literals": "sql_as_nl_query",
                    "temperature": {"docetl": d_row.get("temperature"), "quwarts": POLICY["temperature"]},
                    "completion_cap": {"docetl": d_row.get("completion_cap"), "quwarts": POLICY["completion_cap"]},
                    "model": {"docetl": d_row.get("model"), "quwarts": QUWARTS_MODEL},
                    "window_byte_identical": win_eq,
                    "docetl_input_tokens": d_row.get("model_tokens_after"),
                    "quwarts_input_tokens": q_prompt.get("tokens_after"),
                    "truncation": {"docetl": d_row.get("surviving_portion"), "quwarts": "qwen_mid_cut" if q_prompt.get("truncated") else "none"},
                    "source_offsets_docetl": d_off,
                    "source_offsets_quwarts": {"start": q_start if q_start >= 0 else None, "end": (q_start + len(q_doc)) if q_start >= 0 else None},
                    "bytes_covered_docetl": len(d_doc),
                    "bytes_covered_quwarts": len(q_doc),
                    "window": ov,
                }
            )
            classes[klass] += 1

    def pct(values: list[float]) -> dict[str, float]:
        if not values:
            return {}
        ordered = sorted(values)
        pts = quantiles(ordered, n=4) if len(ordered) >= 4 else [ordered[0], ordered[len(ordered) // 2], ordered[-1]]
        return {"mean": sum(values) / len(values), "min": ordered[0], "p25": pts[0], "p50": pts[1] if len(pts) > 1 else pts[0], "p75": pts[-1], "max": ordered[-1]}

    identical_prompt_and_window = sum(1 for row in audit_rows if row.get("prompt_class") == "byte_identical" and row.get("window_byte_identical"))
    sampling_isolated = identical_prompt_and_window > 0

    def pick_pair(pred):
        return next((row for row in audit_rows if pred(row)), audit_rows[0] if audit_rows else None)

    closest = min((row for row in audit_rows if "window" in row), key=lambda r: (-int(r.get("wrapper_equal")), -r["window"]["jaccard"]), default=None)
    high = min((row for row in audit_rows if "window" in row), key=lambda r: r["window"]["jaccard"], default=None)
    improved = pick_pair(lambda r: r["query_id"] in FRESH_IMPROVED)
    m4_only = pick_pair(lambda r: r["query_id"] in (M4_IMPROVED - FRESH_IMPROVED))

    def udiff(row: dict[str, Any] | None, label: str) -> str:
        if row is None:
            return ""
        q_prompt = next(p for p in fresh_prompts if p["query_id"] == row["query_id"] and p["doc_id"] == row["document_id"])
        d_row = docetl_primary.get((row["query_id"], row["document_id"]))
        q_wrap, q_doc = split_user(q_prompt.get("user") or "")
        d_wrap, d_doc = split_user((d_row or {}).get("user_message") or "")
        d_view = ((d_row or {}).get("system_message") or "") + "\n---\n" + d_wrap + (d_doc[:400] + "\n…\n" + d_doc[-200:] if d_doc else "")
        q_view = (q_prompt.get("system") or "") + "\n---\n" + q_wrap + (q_doc[:400] + "\n…\n" + q_doc[-200:] if q_doc else "")
        text = "".join(
            difflib.unified_diff(
                d_view.splitlines(True),
                q_view.splitlines(True),
                fromfile=f"docetl/{row['query_id']}/{row['document_id']}",
                tofile=f"quwarts/{row['query_id']}/{row['document_id']}",
                n=2,
            )
        )
        (OUT / f"diff_{label}.txt").write_text(text)
        return text[:4000]

    diffs = {
        "closest": {"pair": closest, "diff": udiff(closest, "closest")},
        "high_disagreement": {"pair": high, "diff": udiff(high, "high_disagreement")},
        "fresh_improved": {"pair": improved, "diff": udiff(improved, "fresh_improved")},
        "m4_only": {"pair": m4_only, "diff": udiff(m4_only, "m4_only")},
    }

    # Adapter tests against stored primary DocETL messages.
    adapter_rows = []
    exact = 0
    for qid in query_ids:
        for doc_id in DOCS:
            stored = docetl_primary.get((qid, doc_id))
            generated = generate_primary_messages(statements[qid], texts[doc_id], numeric)
            stored_s = strip_transport(stored) if stored else None
            match_sys = stored is not None and generated["system"] == stored["system_message"]
            match_user = stored is not None and generated["user"] == stored["user_message"]
            match = bool(match_sys and match_user)
            exact += int(match)
            schema_mismatch = stored is not None and list((stored.get("output_schema") or {})) != generated["fields"]
            adapter_rows.append(
                {
                    "query_id": qid,
                    "document_id": doc_id,
                    "stored": stored is not None,
                    "exact": match,
                    "first_differing_byte": None
                    if match or stored is None
                    else {
                        "system": first_differing_byte(generated["system"], stored.get("system_message") or ""),
                        "user": first_differing_byte(generated["user"], stored.get("user_message") or ""),
                    },
                    "schema_mismatch": schema_mismatch,
                    "context_window_mismatch": stored is not None and split_user(generated["user"])[1] != split_user(stored.get("user_message") or "")[1],
                    "parameter_mismatch": stored is not None
                    and (
                        generated["temperature"] != stored.get("temperature")
                        or generated["completion_cap"] != stored.get("completion_cap")
                        or generated["model"] != stored.get("model")
                    ),
                    "generated_fields": generated["fields"],
                }
            )
    adapter_gate = {
        "exact_matches": exact,
        "denominator": 112,
        "stored_primaries": len(docetl_primary),
        "pass": exact == 112,
        "schema_mismatches": sum(1 for row in adapter_rows if row["schema_mismatch"]),
        "context_window_mismatches": sum(1 for row in adapter_rows if row["context_window_mismatch"]),
        "parameter_mismatches": sum(1 for row in adapter_rows if row["parameter_mismatch"]),
        "missing_stored": sum(1 for row in adapter_rows if not row["stored"]),
        "reason_if_failed": None
        if exact == 112
        else (
            "Stored replay journal has only "
            f"{len(docetl_primary)} attributed primary (query, document) pairs; "
            "q3/q14 were incomplete. Several stored user messages are over-truncated "
            "live artifacts (tiktoken vs count_tokens), so generated full-document "
            "truncate_messages output need not equal the recorded string. "
            "The adapter is therefore not claimed equivalent."
        ),
    }

    canonical = build_canonical(fresh_journal, schemas, cells)
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))

    replay_specs = {
        "rules": REPLAY_RULES,
        "never_overwrite_nonnull": True,
        "never_write_sentinels": True,
        "preserve_rows_identities_sql": True,
        "query_isolation": True,
        "diagnostic_only": True,
    }
    materialized = {}
    fill_stats = {}
    for label in ("R0", "R1", "R2", "R3"):
        fills, stats = rule_fills(label, fresh_journal, canonical, schemas)
        materialized[label] = materialize(label, fills, mapping, statements, predicates)
        fill_stats[label] = {
            **stats,
            "changed_cells": sum(item["changed_cells"] for item in materialized[label]["overlays"].values()),
            "blocked_overwrites": sum(item["blocked_overwrites"] for item in materialized[label]["overlays"].values()),
            "n_rows_ok": all(item["n_rows"] == 100 for item in materialized[label]["overlays"].values()),
            "identity_unique": len({item["identity_sha256"] for item in materialized[label]["overlays"].values()}) == 1,
        }

    r0_bags = materialized["R0"]["bags"]
    stored_bags = json.loads((FRESH / "theta100_bags.json").read_text())
    r0_reproduces = _hash(r0_bags) == _hash(stored_bags)

    # Gold-free waterfall through bag change.
    r0_dir = materialized["R0"]["dir"]
    fills_r0, _ = rule_fills("R0", fresh_journal, canonical, schemas)
    fill_list = []
    for qid, docs in fills_r0.items():
        for doc_id, values in docs.items():
            for attr, value in values.items():
                fill_list.append({"query_id": qid, "document_id": doc_id, "attribute": attr, "value": value})

    plumbing_bags = {qid: official_bag(PLUMBING, statements[qid], predicates, qid) for qid in query_ids}
    waterfall = []
    for fill in fill_list:
        qid, doc_id, attr, value = fill["query_id"], fill["document_id"], fill["attribute"], fill["value"]
        dest = OUT / "overlays" / "loo" / f"{qid.replace(':', '_')}_{doc_id}_{attr}.db"
        copy_plumbing(PLUMBING, dest)
        leftover = {d: dict(vals) for d, vals in fills_r0[qid].items()}
        leftover.get(doc_id, {}).pop(attr, None)
        apply_overlay(dest, leftover, mapping)
        overlay_db = r0_dir / f"{qid.replace(':', '_')}.db"
        before = row_for(PLUMBING, doc_id, mapping) or {}
        after = row_for(overlay_db, doc_id, mapping) or {}
        written = after.get(attr) == value and before.get(attr) is None
        expr_changed = before.get(attr) != after.get(attr)
        flags = truth_changed(PLUMBING, overlay_db, statements[qid], doc_id, mapping)
        bag_with = r0_bags[qid]
        bag_without = official_bag(dest, statements[qid], predicates, qid)
        bag_changed = _hash(bag_with) != _hash(bag_without)
        vs_plumbing = _hash(bag_with) != _hash(plumbing_bags[qid])
        if not written:
            reason = "not_written"
        elif not expr_changed:
            reason = "redundant_with_another_condition"
        elif bag_changed:
            reason = "official_bag_changed"
        elif flags["predicate"] is False and flags["case"] is False and flags["support"] is False:
            reason = "blocked_by_another_missing_conjunct" if before.get(attr) is None else "branch_unchanged"
        elif flags["case"] and not bag_changed:
            reason = "branch_unchanged"
        elif flags["group"] is False and not bag_changed:
            reason = "group_unchanged"
        elif expr_changed and not bag_changed:
            reason = "aggregate_insensitive"
        else:
            reason = "bag_changed_outside_scored_cells" if vs_plumbing else "official_bag_unchanged"
        waterfall.append({**fill, "written": written, "expression_changed": expr_changed, **flags, "bag_changed": bag_changed, "bag_vs_plumbing": vs_plumbing, "terminal_reason_pre_gold": reason})

    isolation_ok = all(item["n_rows"] == 100 for label in materialized for item in materialized[label]["overlays"].values())
    freeze = {
        "note": "diagnostic M4 did not reproduce under a fresh QuWARTS execution",
        "sampling_isolated": sampling_isolated,
        "identical_prompt_and_window": identical_prompt_and_window,
        "canonical": {k: canonical[k] for k in canonical if k != "keys"},
        "canonical_sha256": _hash(canonical),
        "replay_specs": replay_specs,
        "replay_specs_sha256": _hash(replay_specs),
        "adapter_gate": adapter_gate,
        "r0_reproduces_fresh_bags": r0_reproduces,
        "fill_stats": fill_stats,
        "empty_bags": {label: [qid for qid, bag in materialized[label]["bags"].items() if not bag] for label in materialized},
        "base_checksums": {
            "plumbing": plumbing_sha,
            "replay_frozen": replay_frozen_sha,
            "fresh_frozen": fresh_frozen_sha,
            "fresh_journal": fresh_journal_sha,
            "replay_journal": replay_journal_sha,
        },
        "prior_unmodified_at_freeze": {
            "plumbing": file_sha256(PLUMBING) == plumbing_sha,
            "replay_frozen": file_sha256(REPLAY / "frozen.json") == replay_frozen_sha,
            "fresh_frozen": file_sha256(FRESH / "frozen.json") == fresh_frozen_sha,
        },
        "isolation_ok": isolation_ok,
        "hashes": {
            "prompt_audit": _hash(audit_rows),
            "adapter_rows": _hash(adapter_rows),
            "r0_bags": _hash(materialized["R0"]["bags"]),
            "r1_bags": _hash(materialized["R1"]["bags"]),
            "r2_bags": _hash(materialized["R2"]["bags"]),
            "r3_bags": _hash(materialized["R3"]["bags"]),
            "waterfall_pre_gold": _hash(waterfall),
        },
    }
    (OUT / "canonical_inventory.json").write_text(json.dumps(canonical, indent=2, default=str))
    (OUT / "prompt_audit.json").write_text(json.dumps({"rows": audit_rows, "classes": dict(classes)}, indent=2, default=str))
    (OUT / "adapter_gate.json").write_text(json.dumps({"gate": adapter_gate, "rows": adapter_rows}, indent=2, default=str))
    (OUT / "waterfall_pre_gold.json").write_text(json.dumps(waterfall, indent=2, default=str))
    for label in materialized:
        (OUT / f"{label}_bags.json").write_text(json.dumps(materialized[label]["bags"], indent=2, default=str))
        (OUT / f"{label}_overlays.json").write_text(json.dumps(materialized[label]["overlays"], indent=2, default=str))
    (OUT / "freeze.json").write_text(json.dumps(freeze, indent=2, default=str))
    print(json.dumps({"frozen": True, "r0_reproduces": r0_reproduces, "adapter_exact": exact, "sampling_isolated": sampling_isolated}, indent=2), flush=True)

    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Finan"))
    full = {row["query_id"]: row for row in queries_for("Finan")}
    score_rows = [{"query_id": qid, "sql": statements[qid], "pack": (full.get(qid) or {}).get("pack")} for qid in query_ids]
    count_rows = [row for row in score_rows if is_count_query(query_shape(row["query_id"], row["sql"]))]
    gold_finance = gold.get("finance") or gold.get("Finance") or []
    gold_by_id = {}
    for row in gold_finance:
        for key in (str(row.get("doc_id") or ""), str(row.get("id") or ""), Path(str(row.get("doc_id") or "")).stem):
            if key:
                gold_by_id[key] = row

    scores = {label: score_dir(materialized[label]["dir"], statements, predicates, score_rows, count_rows, gold) for label in ("R0", "R1", "R2", "R3")}
    plumbing_score = _score(PLUMBING, score_rows, {qid: official_sql(statements[qid], PLUMBING, predicates, query_id=qid) for qid in query_ids}, gold)

    r0_prod = scores["R0"]["score_16"]["mean_per_query_product"]
    if abs(r0_prod - EXPECTED_R0) > 1e-9 and not r0_reproduces:
        raise SystemExit(f"R0 product {r0_prod} != {EXPECTED_R0}")

    # Post-gold waterfall terminals for bag-changing fills.
    r0_per = {row["query_id"]: row for row in scores["R0"]["score_16"]["per_query"]}
    plumb_per = {row["query_id"]: row for row in plumbing_score["per_query"]}
    reason_counts = Counter(row["terminal_reason_pre_gold"] for row in waterfall)
    for row in waterfall:
        qid = row["query_id"]
        if row["terminal_reason_pre_gold"] != "official_bag_changed":
            continue
        delta = float(r0_per[qid]["product"]) - float(plumb_per[qid]["product"])
        if delta > 1e-12:
            row["terminal_reason"] = "correct_and_score_improving"
        elif delta < -1e-12:
            row["terminal_reason"] = "incorrect_and_score_harming"
        else:
            row["terminal_reason"] = "bag_changed_outside_scored_cells"
        reason_counts[row["terminal_reason"]] += 1
    for row in waterfall:
        row.setdefault("terminal_reason", row["terminal_reason_pre_gold"])

    def label_value(doc_id: str, attr: str, value: Any) -> dict[str, Any]:
        gold_row = gold_by_id.get(doc_id) or gold_by_id.get(f"{doc_id}.txt") or {}
        gold_raw = gold_row.get(attr)
        if gold_raw is None and attr == "total_debt":
            gold_raw = gold_row.get("total_Debt")
        dtype = "numeric" if attr in numeric else "string"
        gnorm, _, gerr = normalize_value(gold_raw, dtype) if gold_raw not in (None, "") else (None, None, "missing")
        vnorm, _, verr = normalize_value(value, dtype) if value not in MISSING else (None, None, "missing")
        exact = gnorm == vnorm and gnorm is not None
        numeric_ok = False
        if dtype == "numeric" and isinstance(gnorm, (int, float)) and isinstance(vnorm, (int, float)) and gnorm != 0:
            numeric_ok = abs(float(vnorm) - float(gnorm)) / abs(float(gnorm)) <= 0.20
        elif dtype == "numeric" and gnorm == 0 and vnorm == 0:
            numeric_ok = True
        return {"exact_or_normalized": exact, "numeric_tolerance": numeric_ok or exact, "gold": gnorm, "pred": vnorm, "gold_err": gerr, "pred_err": verr}

    def key_bucket(inv: dict[str, Any]) -> str:
        if inv["n_judgments"] == 1:
            return "singleton"
        if inv["conflict"]:
            return "conflicting"
        if inv["unanimous"] is not None:
            return "unanimous_repeated"
        if inv["majority"] is not None:
            return "majority"
        return "repeated_other"

    acc = defaultdict(lambda: Counter())
    for inv in canonical["keys"]:
        bucket = key_bucket(inv)
        for judgment in inv["judgments"]:
            if judgment["accepted"] is None:
                acc[bucket]["missing"] += 1
                continue
            lab = label_value(inv["document_id"], inv["attribute"], judgment["accepted"])
            acc[bucket]["n"] += 1
            acc[bucket]["exact"] += int(lab["exact_or_normalized"])
            acc[bucket]["tol"] += int(lab["numeric_tolerance"])
    bag_acc = {"changed": Counter(), "unchanged": Counter()}
    for row in waterfall:
        lab = label_value(row["document_id"], row["attribute"], row["value"])
        dest = bag_acc["changed" if row["bag_changed"] else "unchanged"]
        dest["n"] += 1
        dest["exact"] += int(lab["exact_or_normalized"])
        dest["tol"] += int(lab["numeric_tolerance"])

    r0_ok = abs(r0_prod - EXPECTED_R0) <= 1e-6 or r0_reproduces
    lifts = {label: scores[label]["score_16"]["mean_per_query_product"] - r0_prod for label in ("R1", "R2", "R3")}
    material_consistency = any(v >= 0.01 for v in lifts.values())
    n_labeled = sum(acc[b]["n"] for b in acc)
    n_exact = sum(acc[b]["exact"] for b in acc)
    mostly_wrong = n_labeled > 0 and (n_exact / n_labeled) < 0.5
    n_fills = len(waterfall)
    n_inert = sum(1 for row in waterfall if not row["bag_changed"])
    mostly_inert = n_fills > 0 and (n_inert / n_fills) >= 0.5 and not mostly_wrong

    if not sampling_isolated:
        decision = "prompt/window mismatch prevented sampling isolation"
    elif material_consistency:
        decision = "cross-query consistency materially improves the fresh arm"
    elif mostly_wrong:
        decision = "fresh values are mostly semantically wrong despite full context"
    else:
        decision = "fresh values are mostly correct but SQL-inert"

    secondary = []
    if sampling_isolated is False:
        if material_consistency:
            secondary.append("cross-query consistency materially improves the fresh arm")
        if mostly_wrong:
            secondary.append("fresh values are mostly semantically wrong despite full context")
        elif mostly_inert:
            secondary.append("fresh values are mostly correct but SQL-inert")
        else:
            secondary.append("fresh values are mostly semantically wrong despite full context" if n_labeled and n_exact / max(n_labeled, 1) < 0.5 else "fresh values are mostly correct but SQL-inert")

    per_query_changes = []
    for row in scores["R0"]["score_16"]["per_query"]:
        qid = row["query_id"]
        per_query_changes.append(
            {
                "query_id": qid,
                "plumbing": plumb_per[qid]["product"],
                "R0": row["product"],
                "R1": next(x["product"] for x in scores["R1"]["score_16"]["per_query"] if x["query_id"] == qid),
                "R2": next(x["product"] for x in scores["R2"]["score_16"]["per_query"] if x["query_id"] == qid),
                "R3": next(x["product"] for x in scores["R3"]["score_16"]["per_query"] if x["query_id"] == qid),
                "empty_R0": qid in freeze["empty_bags"]["R0"],
            }
        )

    report = {
        "framing": "diagnostic M4 did not reproduce under a fresh QuWARTS execution",
        "decision": decision,
        "secondary_findings": secondary,
        "prompt_audit": {
            "byte_identical_prompts": prompt_byte,
            "semantically_identical_byte_different": prompt_semantic,
            "different_prompts": prompt_different,
            "byte_identical_document_windows": window_identical,
            "window_overlap": pct(jaccards),
            "tokens_only_docetl": pct([float(x) for x in only_d]),
            "tokens_only_quwarts": pct([float(x) for x in only_q]),
            "causes": dict(cause),
            "identical_prompt_and_window": identical_prompt_and_window,
            "sampling_cannot_be_isolated": not sampling_isolated,
        },
        "adapter": adapter_gate,
        "canonical_summary": {k: canonical[k] for k in canonical if k != "keys"},
        "r0_product": r0_prod,
        "r0_reproduces_fresh_bags": r0_reproduces,
        "scores": {
            label: {
                "score_16": {k: scores[label]["score_16"][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")},
                "score_15": {k: scores[label]["score_15"][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")},
            }
            for label in scores
        },
        "comparators": {"plumbing": PLUMBING_PRODUCT, "fresh_R0": 0.0292, "frozen_docetl": DOCETL_PRODUCT, "diagnostic_m4": M4_PRODUCT},
        "fill_stats": fill_stats,
        "empty_bags": freeze["empty_bags"],
        "per_query": per_query_changes,
        "waterfall_reasons": dict(reason_counts),
        "accuracy": {
            "by_key_class": {k: dict(v) for k, v in acc.items()},
            "fills_bag_changed": dict(bag_acc["changed"]),
            "fills_bag_unchanged": dict(bag_acc["unchanged"]),
        },
        "isolation_failures": 0 if isolation_ok else 1,
        "prior_unmodified": {
            "plumbing": file_sha256(PLUMBING) == plumbing_sha,
            "replay": file_sha256(REPLAY / "frozen.json") == replay_frozen_sha,
            "fresh": file_sha256(FRESH / "frozen.json") == fresh_frozen_sha,
        },
        "hashes": freeze["hashes"],
        "base_checksums": freeze["base_checksums"],
        "diffs": {k: {"query_id": (v["pair"] or {}).get("query_id"), "document_id": (v["pair"] or {}).get("document_id")} for k, v in diffs.items()},
    }
    (OUT / "waterfall.json").write_text(json.dumps(waterfall, indent=2, default=str))
    (OUT / "reproduction_gap_audit.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({"wrote": str(OUT / "reproduction_gap_audit.json"), "decision": decision, "r0": r0_prod, "r1": scores["R1"]["score_16"]["mean_per_query_product"], "r2": scores["R2"]["score_16"]["mean_per_query_product"], "r3": scores["R3"]["score_16"]["mean_per_query_product"]}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
