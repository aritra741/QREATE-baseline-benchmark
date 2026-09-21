"""Candidate-aligned checked extraction plus a deterministic ranker. No gold. No free-form silver labels."""

from __future__ import annotations

import builtins
import hashlib
import json
import pickle
import random
import re
import sqlite3
import sys
import threading
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
    "/quwarts_legal_corpus_probe",
    "/ground_truth",
)
_REAL_OPEN = builtins.open


def _blocked(path: Any) -> bool:
    text = str(path).replace("\\", "/")
    if any(token in text for token in BLOCKED):
        return True
    if "docetl_legal" in text and not text.endswith("query_manifest.json"):
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
        ("quwarts_legal_", "corpus_probe/"),
    ):
        if left + right in source:
            raise SystemExit("run invalid: runner references a forbidden result path")


builtins.open = _guarded_open

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import GroupKFold

from quwarts.core.amortized_select.prompt import assemble_tools
from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog
from quwarts.core.corpus_probe.context import exhaustive_chunks, inspect_record, route_context, whole_document_budget
from quwarts.core.full_window_additive.overlay import apply_overlay, copy_plumbing, official_bag
from quwarts.core.ledger import BudgetExhausted, SpendRecord, TokenLedger
from quwarts.core.llm.openrouter import load_env_file
from quwarts.core.materialize import file_sha256
from quwarts.core.provenance import document_stem
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.shared_bundle.inventory import compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.finan_amortized_select_arm import issue_call, mapping_from_rows, parse_tool, reserved_of, usage_of, _hash, _null

load_env_file(ROOT / ".env")

FROZEN_INV = ROOT / "results" / "quwarts_legal_multichannel_candidates"
PLUMBING = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
DOCETL_DIR = ROOT / "results" / "docetl_legal_case80"
SOURCE_DIR = ROOT / "source_data" / "Legal" / "legal_case"
SCHEMA_PATH = ROOT / "Query" / "Legal" / "Legal_attributes.json"
OUT = ROOT / "results" / "quwarts_legal_checked_rank"
THETA = 12_610_011
SEED = 120
TABLE = "legal"
KEEP = "KEEP_PLUMBING"
UNCERTAIN = "UNCERTAIN"
DET = {"surface", "normalized", "workload_label"}
N_SAMPLE = 120
N_TRAIN = 80
N_VAL = 40
ALLOC = {"scan": 0.65, "verify": 0.25, "adjudicate": 0.05, "reserve": 0.05}
GRID = {"n_estimators": [50, 100], "max_depth": [2, 3], "learning_rate": [0.05, 0.1]}
THRESHOLDS = [0.55, 0.65, 0.75, 0.85]
MARGINS = [0.02, 0.05, 0.10]
AMP_FLOOR = 0.75

SCAN_PROMPT = (
    "Read only the supplied source. Do not invent. For each requested attribute, list every plausible fact: "
    "party role, period, heading or table, canonical value, aliases, whether the fact is stated or inferred, "
    "and exact character offsets. If a section has no usable fact, say so for that attribute. "
    "NO_EVIDENCE is allowed. It is not a decision to leave the cell empty. Return JSON with one object per attribute."
)
MATCH_PROMPT = (
    "You are matching frozen source evidence to candidate IDs. Output IDs only, never a newly written value. "
    "Classify each candidate as directly_supported, observationally_supported, wrong_entity, wrong_period, "
    "wrong_component, wrong_type, workload_literal_copy, or unsupported. "
    "A workload-label candidate is acceptable only when the evidence supports that label, not because the label appears in SQL. "
    "decision must be one candidate_id, KEEP_PLUMBING, or UNCERTAIN. "
    "Use KEEP_PLUMBING only if you reject every candidate. Use UNCERTAIN when support is incomplete."
)
ABSENCE_PROMPT = (
    "Decide whether absence is established. Agree only when the coverage report shows every section was scanned, "
    "the evidence ledger has no usable fact, and every candidate was rejected. Otherwise disagree. "
    "A missing tail of the document is not absence."
)
VERIFY_PROMPT = (
    "Independently check which candidate IDs the evidence supports for this attribute. "
    "Agree on entity/role, period, attribute meaning, and a supporting span. Output IDs only. "
    "decision is one candidate_id, KEEP_PLUMBING, or UNCERTAIN."
)
ADJ_PROMPT = (
    "Two analyses disagree. Using only the evidence ledger and the candidate list, choose the supported ID set, "
    "KEEP_PLUMBING, or UNCERTAIN. Do not invent a value. Output IDs only."
)

DECISION_SCHEMA = {
    "decision": "str",
    "supported_candidate_ids": "str",
    "rejected_candidate_ids": "str",
    "observable_signature": "str",
    "evidence_spans": "str",
    "absence_checked": "str",
    "confidence": "str",
    "reason": "str",
    "candidate_judgments": "str",
}
SCAN_SCHEMA = {"ledger": "str"}
ABSENCE_SCHEMA = {"agree_absent": "str", "reason": "str"}
FEATURE_NAMES = [
    "channel_surface", "channel_normalized", "channel_workload_label", "channel_keep",
    "has_span", "desc_overlap", "heading_overlap", "role_overlap", "period_present",
    "type_numeric", "value_len", "occurrence", "position", "context_overlap",
    "workload_literal", "ambiguity", "plumbing_null", "role_where", "role_group",
    "role_having", "role_agg", "amplification", "keep",
]


class RowEvaluator:
    def __init__(self, columns: list[str], statements: dict[str, str]):
        self.columns = columns
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        cols = ", ".join(f'"{c}" TEXT' for c in columns)
        self.conn.execute(f'CREATE TABLE "{TABLE}" ({cols})')
        self.insert = f'INSERT INTO "{TABLE}" ({", ".join(chr(34)+c+chr(34) for c in columns)}) VALUES ({", ".join("?" for _ in columns)})'
        self.statements = statements
        self.cache: dict[tuple, tuple] = {}
        self._lock = threading.Lock()

    def run(self, query_id: str, row: dict[str, Any]) -> tuple:
        payload = tuple(None if row.get(c) in (None, "") else str(row.get(c)) for c in self.columns)
        key = (query_id, payload)
        with self._lock:
            if key in self.cache:
                return self.cache[key]
            self.conn.execute(f'DELETE FROM "{TABLE}"')
            self.conn.execute(self.insert, payload)
            try:
                rows = tuple(self.conn.execute(self.statements[query_id]).fetchall())
            except sqlite3.Error:
                rows = (("__error__",),)
            self.cache[key] = rows
            return rows


def sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def clip(text: Any, n: int = 160) -> str:
    body = " ".join(str(text or "").split())
    return body if len(body) <= n else body[: n - 1].rstrip() + "…"


def channel_of(item: dict[str, Any]) -> str:
    raw = str(item.get("channel") or item.get("derivation") or "surface")
    return "composed" if raw.startswith("composed") else raw


def det_items(rec: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in (rec.get("all_candidates") or rec.get("candidates") or []) if channel_of(item) in DET]


def tokens(text: str) -> set[str]:
    return {part for part in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(part) > 2}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    text = str(value or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            pass
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def norm_text(value: Any, dtype: str) -> str:
    if value in (None, ""):
        return ""
    got, _, err = normalize_value(value, dtype)
    if err or got is None:
        return str(value).strip().lower()
    return str(got).strip().lower()


def parse_decision(parsed: dict[str, Any], raw: str, allowed: set[str]) -> dict[str, Any]:
    decision = str(parsed.get("decision") or "").strip()
    supported = [item for item in as_list(parsed.get("supported_candidate_ids")) if item in allowed]
    if decision in allowed or decision in {KEEP, UNCERTAIN}:
        pass
    else:
        found = [item for item in (KEEP, UNCERTAIN, *sorted(allowed)) if re.search(r"(?<![A-Za-z0-9_])" + re.escape(item) + r"(?![A-Za-z0-9_])", raw or "")]
        decision = found[0] if len(set(found)) == 1 else UNCERTAIN
    if decision in allowed and decision not in supported:
        supported = [decision, *supported]
    if decision == KEEP:
        supported = []
    return {
        "decision": decision if decision in allowed or decision in {KEEP, UNCERTAIN} else UNCERTAIN,
        "supported_candidate_ids": supported,
        "rejected_candidate_ids": [item for item in as_list(parsed.get("rejected_candidate_ids")) if item in allowed],
        "observable_signature": parsed.get("observable_signature") or {},
        "evidence_spans": as_list(parsed.get("evidence_spans")),
        "absence_checked": str(parsed.get("absence_checked") or "").lower() in {"1", "true", "yes"},
        "confidence": as_float(parsed.get("confidence")),
        "reason": clip(parsed.get("reason"), 240),
        "candidate_judgments": parsed.get("candidate_judgments") or "",
    }


def candidate_line(item: dict[str, Any]) -> str:
    spans = item.get("evidence_spans") or []
    snippet = ""
    if spans and isinstance(spans[0], dict):
        snippet = spans[0].get("text") or ""
    snippet = snippet or item.get("local_text") or item.get("raw_span") or ""
    return " ".join(
        [
            f"id={item.get('id')}",
            f"channel={channel_of(item)}",
            f"value={clip(item.get('normalized'), 48)}",
            f"period={clip(item.get('period'), 24)}",
            f"heading={clip(item.get('heading') or item.get('column_header') or item.get('table_title'), 40)}",
            f"span={clip(snippet, 80)}",
        ]
    )


def feature_row(item: dict[str, Any] | None, spec, rec_items: list[dict[str, Any]], plumbing_null: bool, roles: dict[str, int], amp: bool, desc_tokens: set[str], doc_len: int = 1) -> list[float]:
    if item is None:
        return [
            0, 0, 0, 1,
            0, 0, 0, 0, 0,
            1 if spec.dtype == "numeric" else 0, 0, 0, 0, 0,
            0, float(len(rec_items)), 1 if plumbing_null else 0,
            float(roles.get("WHERE") or 0), float(roles.get("GROUP BY") or 0),
            float(roles.get("HAVING") or 0), float(roles.get("aggregate input") or 0), 1 if amp else 0, 1,
        ]
    ch = channel_of(item)
    blob = " ".join(str(item.get(key) or "") for key in ("local_text", "raw_span", "heading", "column_header", "table_title"))
    blob_tokens = tokens(blob)
    value = str(item.get("normalized") or "")
    start = float(item.get("start") or 0) / max(doc_len, 1)
    return [
        1 if ch == "surface" else 0,
        1 if ch == "normalized" else 0,
        1 if ch == "workload_label" else 0,
        0,
        1 if (item.get("evidence_spans") or item.get("raw_span")) else 0,
        jaccard(desc_tokens, blob_tokens),
        jaccard(desc_tokens, tokens(item.get("heading") or item.get("table_title") or "")),
        jaccard(tokens(spec.name), blob_tokens),
        1 if item.get("period") else 0,
        1 if spec.dtype == "numeric" else 0,
        float(len(value)),
        float(item.get("occurrence") or item.get("count") or 1),
        start,
        jaccard(desc_tokens, tokens(item.get("local_text") or "")),
        1 if ch == "workload_label" else 0,
        float(len(rec_items)),
        1 if plumbing_null else 0,
        float(roles.get("WHERE") or 0),
        float(roles.get("GROUP BY") or 0),
        float(roles.get("HAVING") or 0),
        float(roles.get("aggregate input") or 0),
        1 if amp else 0,
        0,
    ]


def equivalent_ids(chosen: list[str], items: list[dict[str, Any]], spec, evaluator: RowEvaluator, queries: list[str], row: dict[str, Any]) -> set[str]:
    by_id = {str(item.get("id")): item for item in items}
    out = {cid for cid in chosen if cid in by_id}
    anchors = [by_id[cid] for cid in out]
    for item in items:
        cid = str(item.get("id"))
        if cid in out:
            continue
        if any(norm_text(item.get("normalized"), spec.dtype) == norm_text(anchor.get("normalized"), spec.dtype) and norm_text(anchor.get("normalized"), spec.dtype) for anchor in anchors):
            out.add(cid)
            continue
        if anchors and queries and all(
            evaluator.run(qid, {**row, spec.name: item.get("normalized")}) == evaluator.run(qid, {**row, spec.name: anchor.get("normalized")})
            for qid in queries
            for anchor in anchors[:1]
        ):
            out.add(cid)
    return out


def main() -> int:
    assert_access_closed()
    for token in BLOCKED:
        probe = ROOT / "results" / token.strip("/") if token.startswith("/quwarts") else ROOT / token.strip("/")
        try:
            _guarded_open(probe, "r")
        except RuntimeError:
            continue
        except FileNotFoundError:
            continue
        else:
            if probe.exists():
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
    plumbing_by = {str(row.get("__entity_id")): row for row in plumbing_rows}
    by_ent = {(rec["entity_id"], rec["attribute"]): rec for rec in inventory}
    evaluator = RowEvaluator(list(plumbing_rows[0]), statements)
    queries_by_attr = {name: list(records[name].queries) for name in records}
    amp_attrs = set()
    for name, rec in records.items():
        sql_blob = "\n".join(statements[qid] for qid in rec.queries)
        if any(rec.roles.get(role) for role in ("WHERE", "GROUP BY", "HAVING", "aggregate input")):
            amp_attrs.add(name)
        if re.search(rf"\b{name}\b\s+IS\s+NOT\s+NULL", sql_blob, re.I) or re.search(rf"\b{name}\b\s*(!=|<>)\s*''", sql_blob, re.I):
            amp_attrs.add(name)
        if re.search(rf"\b(COUNT|AVG|SUM|MAX|MIN)\s*\([^)]*\b{name}\b", sql_blob, re.I):
            amp_attrs.add(name)
    prompts = {"scan": SCAN_PROMPT, "match": MATCH_PROMPT, "absence": ABSENCE_PROMPT, "verify": VERIFY_PROMPT, "adjudicate": ADJ_PROMPT}
    design = {
        "query_ids": query_ids,
        "inventory": file_sha256(FROZEN_INV / "candidate_inventory.json"),
        "plumbing": file_sha256(PLUMBING),
        "prompts": sha(prompts),
        "features": FEATURE_NAMES,
        "grid": GRID,
        "thresholds": THRESHOLDS,
        "margins": MARGINS,
        "model": "openrouter/qwen/qwen-2.5-7b-instruct",
        "ranker": "sklearn.ensemble.GradientBoostingClassifier",
        "seed": SEED,
        "theta": THETA,
        "allocation": {name: int(THETA * frac) for name, frac in ALLOC.items()},
        "deterministic_channels": sorted(DET),
        "amplification_attributes": sorted(amp_attrs),
        "n_sample": N_SAMPLE,
        "n_train": N_TRAIN,
        "n_val": N_VAL,
    }
    (OUT / "design.json").write_text(json.dumps(design, indent=2))
    (OUT / "prompts.json").write_text(json.dumps(prompts, indent=2))

    whole_budget = whole_document_budget()
    lengths = sorted(len(texts.get(str(row.get("__provenance_label") or document_stem(str(row.get("doc_id") or ""))), "")) for row in plumbing_rows)

    def quartile(n: int) -> int:
        if n <= lengths[len(lengths) // 4]:
            return 1
        if n <= lengths[len(lengths) // 2]:
            return 2
        if n <= lengths[(3 * len(lengths)) // 4]:
            return 3
        return 4

    entities = []
    for row in plumbing_rows:
        eid = str(row.get("__entity_id"))
        doc = str(row.get("__provenance_label") or document_stem(str(row.get("doc_id") or "")))
        text = texts.get(doc) or ""
        recs = [rec for rec in inventory if rec["entity_id"] == eid]
        n_cand = sum(len(det_items(rec)) for rec in recs)
        chans = Counter(channel_of(item) for rec in recs for item in det_items(rec))
        nulls = sum(1 for name in attr_names if row.get(name) in (None, ""))
        amp_nulls = sum(1 for name in amp_attrs if row.get(name) in (None, ""))
        tok = count_tokens(text)
        entities.append({
            "entity_id": eid,
            "document_id": doc,
            "doc_tokens": tok,
            "len_q": quartile(len(text)),
            "fit": "whole" if tok <= whole_budget else "chunk",
            "cand_b": 0 if n_cand <= 8 else 1 if n_cand <= 24 else 2,
            "null_b": 0 if nulls <= 2 else 1 if nulls <= 5 else 2,
            "chan_b": int(chans.get("surface", 0) > 0) + 2 * int(chans.get("normalized", 0) > 0) + 4 * int(chans.get("workload_label", 0) > 0),
            "amp_b": 0 if amp_nulls == 0 else 1 if amp_nulls <= 2 else 2,
            "n_cand": n_cand,
            "nulls": nulls,
        })
    groups: dict[tuple, list] = defaultdict(list)
    for feat in entities:
        groups[(feat["len_q"], feat["fit"], feat["cand_b"], feat["null_b"], feat["chan_b"], feat["amp_b"])].append(feat)
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

    def estimate(rows: list[dict[str, Any]]) -> int:
        total = 0
        for row in rows:
            text = texts.get(row["document_id"]) or ""
            if row["fit"] == "whole":
                total += row["doc_tokens"] + 500
            else:
                total += max(1, len(exhaustive_chunks(text))) * 900 + 700
            total += len(attr_names) * (900 + 40 * max(1, row["n_cand"] // len(attr_names)))
        return total

    while sampled and estimate(sampled) > int(0.90 * THETA):
        sampled.pop()
    train, held = [], []
    by_stratum: dict[tuple, list] = defaultdict(list)
    for row in sampled:
        by_stratum[(row["len_q"], row["fit"], row["amp_b"])].append(row)
    for key, rows in sorted(by_stratum.items()):
        cut = max(1, int(round(len(rows) * (N_TRAIN / max(N_SAMPLE, 1))))) if len(rows) > 1 else 1
        train.extend(rows[:cut])
        held.extend(rows[cut:])
    target_train = min(max(int(round(len(sampled) * N_TRAIN / N_SAMPLE)), 1), max(len(sampled) - 1, 1))
    while len(train) > target_train:
        held.append(train.pop())
    while len(train) < target_train and held:
        train.append(held.pop())
    train_ids = {row["entity_id"] for row in train}
    held_ids = {row["entity_id"] for row in held}
    sample_payload = {"train": train, "heldout": held, "estimate_tokens": estimate(sampled), "n": len(sampled)}
    (OUT / "sample_split.json").write_text(json.dumps(sample_payload, indent=2, default=str))
    (OUT / "phase0_hashes.json").write_text(json.dumps({"design": sha(design), "sample": sha(sample_payload), "prompts": sha(prompts), "features": sha(FEATURE_NAMES), "grid": sha(GRID)}, indent=2))
    print(json.dumps({"phase0": True, "n": len(sampled), "train": len(train), "heldout": len(held), "estimate": sample_payload["estimate_tokens"], "amp": sorted(amp_attrs)}, indent=2), flush=True)

    ledger = TokenLedger(theta=THETA, seed=SEED)
    if (OUT / "live_ledger.json").is_file():
        snap = json.loads((OUT / "live_ledger.json").read_text())
        ledger.spent = int(snap.get("spent") or 0)
        ledger.records = [SpendRecord(row["purpose"], row["tokens"], row.get("metadata") or {}) for row in snap.get("records") or []]

    io_lock = threading.Lock()

    def persist() -> None:
        with io_lock:
            (OUT / "live_ledger.json").write_text(json.dumps(ledger.snapshot(), indent=2, default=str))

    caps = design["allocation"]

    def purpose_spent(prefix: str) -> int:
        with ledger._lock:
            return sum(rec.tokens for rec in ledger.records if rec.purpose.startswith(prefix))

    def one_call(schema: dict[str, str], instruction: str, user: str, purpose: str, meta: dict[str, Any], cap_key: str) -> dict[str, Any]:
        bundled = assemble_tools(schema, instruction + "\n\n" + user)
        _pt, reserved = reserved_of(bundled["user"], bundled["tools"])
        if purpose_spent(cap_key) + reserved > caps[cap_key] or ledger.spent + reserved > ledger.theta:
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

    scan_path = OUT / "scan_journal.jsonl"
    cell_path = OUT / "cell_journal.jsonl"
    scans: dict[str, dict[str, Any]] = {}
    if scan_path.is_file():
        for line in scan_path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                scans[row["entity_id"]] = row
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    if cell_path.is_file():
        for line in cell_path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                cells[(row["entity_id"], row["attribute"])] = row

    def scan_entity(ent: dict[str, Any]) -> dict[str, Any]:
        text = texts.get(ent["document_id"]) or ""
        wrapper = count_tokens(SCAN_PROMPT + " ".join(attr_names)) + 200
        mode = route_context(wrapper, ent["doc_tokens"])
        header = "attributes=" + ",".join(f"{name}: {specs[name].official_description}" for name in attr_names)
        if mode == "whole_document":
            got = one_call(SCAN_SCHEMA, SCAN_PROMPT, header + "\n\nsource:\n" + text, "scan", {"entity_id": ent["entity_id"]}, "scan")
            return {"entity_id": ent["entity_id"], "document_id": ent["document_id"], "mode": mode, "coverage": inspect_record(mode, [{"index": 0, "start": 0, "end": len(text), "tokens": ent["doc_tokens"]}]), "ledger": (got.get("parsed") or {}).get("ledger") or got.get("raw") or "", "incomplete": got.get("reason") != "ok"}
        chunks = exhaustive_chunks(text)
        reserved = len(chunks) * 1200
        if ledger.spent + reserved > THETA or purpose_spent("scan") + reserved > caps["scan"]:
            return {"entity_id": ent["entity_id"], "document_id": ent["document_id"], "mode": mode, "coverage": inspect_record(mode, chunks), "ledger": "", "incomplete": True, "reason": "would_partial_scan"}
        parts = []
        for chunk in chunks:
            got = one_call(SCAN_SCHEMA, SCAN_PROMPT, header + f"\nchunk={chunk['index']} offsets={chunk['start']}:{chunk['end']}\n\nsource:\n{chunk['text']}", "scan_chunk", {"entity_id": ent["entity_id"], "chunk": chunk["index"]}, "scan")
            parts.append(clip((got.get("parsed") or {}).get("ledger") or got.get("raw") or "", 800))
            if got.get("reason") != "ok":
                return {"entity_id": ent["entity_id"], "document_id": ent["document_id"], "mode": mode, "coverage": inspect_record(mode, chunks), "ledger": "", "incomplete": True, "reason": got.get("reason")}
        reduced = one_call(SCAN_SCHEMA, SCAN_PROMPT, header + "\n\nchunk_ledgers:\n" + "\n".join(parts), "scan_reduce", {"entity_id": ent["entity_id"]}, "scan")
        return {"entity_id": ent["entity_id"], "document_id": ent["document_id"], "mode": mode, "coverage": inspect_record(mode, chunks), "ledger": (reduced.get("parsed") or {}).get("ledger") or reduced.get("raw") or "", "incomplete": reduced.get("reason") != "ok", "n_chunks": len(chunks)}

    pending_scan = [ent for ent in sampled if ent["entity_id"] not in scans]

    def _store_scan(ent: dict[str, Any]) -> None:
        row = scan_entity(ent)
        with io_lock:
            scans[ent["entity_id"]] = row
            with _REAL_OPEN(scan_path, "a") as handle:
                handle.write(json.dumps(row, default=str) + "\n")
        print(json.dumps({"scanned": ent["document_id"], "incomplete": row.get("incomplete"), "spent": ledger.spent}, indent=2), flush=True)

    if pending_scan:
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(_store_scan, pending_scan))

    def cell_user(ent, name, order: list[dict[str, Any]], ledger_text: str) -> str:
        spec = specs[name]
        lines = [
            f"attr={name}",
            f"desc={spec.official_description}",
            f"type={spec.dtype}/{spec.sql_type}",
            f"workload_roles={records[name].roles}",
            f"workload_literals={records[name].predicate_literals[:12]}",
            f"plumbing={'NULL' if plumbing_by[ent['entity_id']].get(name) in (None, '') else 'INCUMBENT_NON_NULL'}",
            "evidence_ledger:",
            clip(ledger_text, 2500),
            "candidates:",
        ]
        lines.extend(candidate_line(item) for item in order)
        lines.append("KEEP_PLUMBING means write nothing.")
        return "\n".join(lines)

    def finalize_cell(ent: dict[str, Any], name: str) -> dict[str, Any]:
        scan = scans[ent["entity_id"]]
        items = det_items(by_ent.get((ent["entity_id"], name)) or {})
        allowed = {str(item.get("id")) for item in items}
        base = {"entity_id": ent["entity_id"], "document_id": ent["document_id"], "attribute": name, "split": "train" if ent["entity_id"] in train_ids else "heldout"}
        if scan.get("incomplete"):
            return {**base, "decision": UNCERTAIN, "supported_candidate_ids": [], "reason": "incomplete_scan", "coverage": scan.get("coverage")}
        rng = random.Random(SEED + int(hashlib.sha256(f"{ent['entity_id']}:{name}".encode()).hexdigest()[:8], 16))
        order = list(items)
        rng.shuffle(order)
        user = cell_user(ent, name, order, scan.get("ledger") or "")
        matched = one_call(DECISION_SCHEMA, MATCH_PROMPT, user, "verify_match", {"attribute": name, "split": base["split"]}, "verify")
        match = parse_decision(matched.get("parsed") or {}, matched.get("raw") or "", allowed)
        order2 = list(items)
        rng.shuffle(order2)
        verified = one_call(DECISION_SCHEMA, VERIFY_PROMPT, cell_user(ent, name, order2, scan.get("ledger") or ""), "verify_check", {"attribute": name}, "verify")
        verify = parse_decision(verified.get("parsed") or {}, verified.get("raw") or "", allowed)
        support_m = equivalent_ids(match["supported_candidate_ids"], items, specs[name], evaluator, queries_by_attr.get(name) or [], plumbing_by[ent["entity_id"]])
        support_v = equivalent_ids(verify["supported_candidate_ids"], items, specs[name], evaluator, queries_by_attr.get(name) or [], plumbing_by[ent["entity_id"]])
        adjudicated = None
        if match["decision"] == verify["decision"] == KEEP or (support_m and support_m == support_v):
            decision = KEEP if match["decision"] == KEEP else sorted(support_m)[0]
            supported = [] if decision == KEEP else sorted(support_m)
        else:
            adjudicated = one_call(DECISION_SCHEMA, ADJ_PROMPT, user + f"\n\nanalysis_A={match['decision']} {match['supported_candidate_ids']}\nanalysis_B={verify['decision']} {verify['supported_candidate_ids']}", "adjudicate", {"attribute": name}, "adjudicate")
            adjud = parse_decision(adjudicated.get("parsed") or {}, adjudicated.get("raw") or "", allowed)
            supported = sorted(equivalent_ids(adjud["supported_candidate_ids"], items, specs[name], evaluator, queries_by_attr.get(name) or [], plumbing_by[ent["entity_id"]]))
            decision = adjud["decision"] if adjud["decision"] in {KEEP, UNCERTAIN} or adjud["decision"] in allowed else (supported[0] if supported else UNCERTAIN)
            if decision == KEEP:
                supported = []
        absence = None
        if decision == KEEP:
            no_fact = "NO_EVIDENCE" in str(scan.get("ledger") or "").upper() or name not in str(scan.get("ledger") or "")
            all_rejected = not supported
            absence = one_call(ABSENCE_SCHEMA, ABSENCE_PROMPT, f"coverage={json.dumps(scan.get('coverage'), default=str)}\nledger={clip(scan.get('ledger'), 1200)}\nrejected={sorted(allowed)}", "verify_absence", {"attribute": name}, "verify")
            agree = str((absence.get("parsed") or {}).get("agree_absent") or "").lower() in {"1", "true", "yes"}
            if not (no_fact and all_rejected and agree and not scan.get("incomplete")):
                decision = UNCERTAIN
                supported = []
        return {
            **base,
            "decision": decision if decision != KEEP else KEEP,
            "supported_candidate_ids": supported,
            "rejected_candidate_ids": sorted(allowed - set(supported)),
            "match": match,
            "verify": verify,
            "adjudicate": adjudicated,
            "absence": absence,
            "coverage": scan.get("coverage"),
            "mode": scan.get("mode"),
            "confidence": max(match["confidence"], verify["confidence"]),
        }

    jobs = []
    for ent in sampled:
        for name in attr_names:
            if (ent["entity_id"], name) in cells:
                continue
            if plumbing_by[ent["entity_id"]].get(name) not in (None, ""):
                cells[(ent["entity_id"], name)] = {"entity_id": ent["entity_id"], "document_id": ent["document_id"], "attribute": name, "decision": KEEP, "supported_candidate_ids": [], "reason": "incumbent_non_null", "split": "train" if ent["entity_id"] in train_ids else "heldout"}
                with io_lock:
                    with _REAL_OPEN(cell_path, "a") as handle:
                        handle.write(json.dumps(cells[(ent["entity_id"], name)], default=str) + "\n")
            else:
                jobs.append((ent, name))

    def _store_cell(job: tuple[dict[str, Any], str]) -> None:
        ent, name = job
        row = finalize_cell(ent, name)
        with io_lock:
            cells[(ent["entity_id"], name)] = row
            with _REAL_OPEN(cell_path, "a") as handle:
                handle.write(json.dumps(row, default=str) + "\n")
        print(json.dumps({"cell": ent["document_id"], "attribute": name, "decision": row.get("decision"), "spent": ledger.spent}, indent=2), flush=True)

    if jobs:
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(_store_cell, jobs))

    label_counts = Counter(row.get("decision") if row.get("decision") in {KEEP, UNCERTAIN} else "candidate" for row in cells.values())
    (OUT / "checked_stats.json").write_text(json.dumps({"n": len(cells), "counts": dict(label_counts), "coverage_incomplete": sum(1 for row in scans.values() if row.get("incomplete"))}, indent=2))
    print(json.dumps({"phase1": True, "counts": dict(label_counts), "spent": ledger.spent}, indent=2), flush=True)

    desc_tokens = {name: tokens(specs[name].official_description + " " + name) for name in attr_names}
    doc_len = {row["entity_id"]: max(len(texts.get(row["document_id"]) or " "), 1) for row in entities}

    def group_rows(entity_ids: set[str]) -> tuple[list[list[float]], list[int], list[str], list[str]]:
        xs, ys, groups, ids = [], [], [], []
        for (eid, name), label in cells.items():
            if eid not in entity_ids or label.get("reason") == "incumbent_non_null":
                continue
            if label.get("decision") == UNCERTAIN:
                continue
            items = det_items(by_ent.get((eid, name)) or {})
            supported = set(label.get("supported_candidate_ids") or [])
            if label.get("decision") not in {KEEP, UNCERTAIN} and label.get("decision"):
                supported.add(label["decision"])
            supported = equivalent_ids(list(supported), items, specs[name], evaluator, queries_by_attr.get(name) or [], plumbing_by[eid])
            options: list[tuple[dict[str, Any] | None, int]] = [(None, 1 if label.get("decision") == KEEP else 0)]
            for item in items:
                options.append((item, 1 if str(item.get("id")) in supported else 0))
            if sum(flag for _item, flag in options) == 0 and label.get("decision") != KEEP:
                continue
            for item, flag in options:
                xs.append(feature_row(item, specs[name], items, True, records[name].roles, name in amp_attrs, desc_tokens[name], doc_len.get(eid, 1)))
                ys.append(flag)
                groups.append(eid)
                ids.append(KEEP if item is None else str(item.get("id")))
        return xs, ys, groups, ids

    import numpy as np

    class _KeepOnly:
        classes_ = np.array([0])

        def fit(self, xs, ys):
            return self

        def predict(self, xs):
            return np.zeros(len(xs), dtype=int)

        def predict_proba(self, xs):
            return np.zeros((len(xs), 1))

    def positive_scores(model, rows: list[list[float]]):
        proba = model.predict_proba(np.asarray(rows, dtype=float))
        classes = list(getattr(model, "classes_", []))
        if 1 not in classes:
            return np.zeros(len(rows))
        return proba[:, classes.index(1)]

    def make_model(params: dict[str, Any]):
        return GradientBoostingClassifier(n_estimators=params["n_estimators"], max_depth=params["max_depth"], learning_rate=params["learning_rate"], random_state=SEED)

    x_train, y_train, g_train, _ids = group_rows(train_ids)
    (OUT / "feature_names.json").write_text(json.dumps(FEATURE_NAMES, indent=2))
    grid_rows = []
    degenerate = len(set(y_train)) < 2 or len(set(g_train)) < 2
    if not degenerate:
        x_arr = np.array(x_train, dtype=float)
        y_arr = np.array(y_train, dtype=int)
        g_arr = np.array(g_train)
        splitter = GroupKFold(n_splits=min(4, len(set(g_train))))
        for n_estimators in GRID["n_estimators"]:
            for depth in GRID["max_depth"]:
                for rate in GRID["learning_rate"]:
                    params = {"n_estimators": n_estimators, "max_depth": depth, "learning_rate": rate}
                    fold_scores = []
                    for train_ix, test_ix in splitter.split(x_arr, y_arr, g_arr):
                        if len(set(y_arr[train_ix])) < 2:
                            fold_scores.append(0.0)
                            continue
                        model = make_model(params)
                        model.fit(x_arr[train_ix], y_arr[train_ix])
                        pred = model.predict(x_arr[test_ix])
                        fold_scores.append(float((pred == y_arr[test_ix]).mean()))
                    grid_rows.append({**params, "cv_accuracy": sum(fold_scores) / max(len(fold_scores), 1)})
    (OUT / "cv_grid.json").write_text(json.dumps(grid_rows, indent=2))

    def predict_groups(model, entity_ids: set[str], threshold: float, margin: float, amp_threshold: float, collect: list | None = None) -> dict[tuple[str, str], str]:
        choice = {}
        for eid in entity_ids:
            for name in attr_names:
                if plumbing_by[eid].get(name) not in (None, ""):
                    choice[(eid, name)] = KEEP
                    continue
                items = det_items(by_ent.get((eid, name)) or {})
                rows = [feature_row(None, specs[name], items, True, records[name].roles, name in amp_attrs, desc_tokens[name], doc_len.get(eid, 1))]
                ids = [KEEP]
                for item in items:
                    rows.append(feature_row(item, specs[name], items, True, records[name].roles, name in amp_attrs, desc_tokens[name], doc_len.get(eid, 1)))
                    ids.append(str(item.get("id")))
                scores = positive_scores(model, rows)
                order = sorted(range(len(ids)), key=lambda i: (-float(scores[i]), ids[i]))
                best, second = order[0], order[1] if len(order) > 1 else order[0]
                gap = float(scores[best] - scores[second])
                need = amp_threshold if name in amp_attrs else threshold
                reason = "below_threshold"
                chosen = KEEP
                if name in amp_attrs and ids[best] != KEEP:
                    item = next((item for item in items if str(item.get("id")) == ids[best]), None)
                    if item is None or channel_of(item) == "workload_label" or not (item.get("evidence_spans") or item.get("raw_span")):
                        reason = "amplification_requires_source_span"
                    elif float(scores[best]) >= need and gap >= margin:
                        chosen = ids[best]
                        reason = "ranker_amp"
                    else:
                        reason = "amplification_margin"
                elif float(scores[best]) >= need and gap >= margin:
                    chosen = ids[best]
                    reason = "ranker"
                choice[(eid, name)] = chosen
                if collect is not None and plumbing_by[eid].get(name) in (None, ""):
                    collect.append({"entity_id": eid, "attribute": name, "candidate_id": chosen, "score": float(scores[best]), "second": float(scores[second]), "margin": gap, "features": rows[best], "reason": reason})
        return choice

    def val_metrics(choice: dict[tuple[str, str], str]) -> dict[str, float]:
        obs = exact = prec_n = prec_d = fp = writes = n = contrib = amp_n = 0
        for (eid, name), pred in choice.items():
            if eid not in held_ids:
                continue
            label = cells.get((eid, name))
            if not label or label.get("reason") == "incumbent_non_null" or label.get("decision") == UNCERTAIN:
                continue
            n += 1
            supported = set(label.get("supported_candidate_ids") or [])
            if label.get("decision") not in {KEEP, UNCERTAIN}:
                supported.add(label["decision"])
            ref_decision = KEEP if label.get("decision") == KEEP else (sorted(supported)[0] if supported else UNCERTAIN)
            if pred == KEEP and ref_decision == KEEP:
                obs += 1
                exact += 1
            elif pred in supported:
                obs += 1
                exact += 1
            elif pred != KEEP and ref_decision != KEEP:
                items = det_items(by_ent.get((eid, name)) or {})
                by_id = {str(item.get("id")): item for item in items}
                if pred in by_id and any(norm_text(by_id[pred].get("normalized"), specs[name].dtype) == norm_text(by_id[cid].get("normalized"), specs[name].dtype) for cid in supported if cid in by_id):
                    obs += 1
            if pred != KEEP:
                writes += 1
                prec_d += 1
                if pred in supported:
                    prec_n += 1
                else:
                    fp += 1
            if name in amp_attrs:
                amp_n += 1
                ref = None if ref_decision == KEEP else next((item.get("normalized") for item in det_items(by_ent.get((eid, name)) or {}) if str(item.get("id")) == ref_decision), None)
                got = None if pred == KEEP else next((item.get("normalized") for item in det_items(by_ent.get((eid, name)) or {}) if str(item.get("id")) == pred), None)
                same = all(evaluator.run(qid, {**plumbing_by[eid], name: got}) == evaluator.run(qid, {**plumbing_by[eid], name: ref}) for qid in (queries_by_attr.get(name) or [query_ids[0]]))
                contrib += int(same)
        objective = (obs / max(n, 1), exact / max(n, 1), prec_n / max(prec_d, 1), -fp / max(n, 1), -writes)
        return {"objective": objective, "writes": writes, "amp_contrib": contrib / max(amp_n, 1), "n": n}

    def inflation_fixture(threshold: float) -> dict[str, Any]:
        conn = sqlite3.connect(":memory:")
        conn.execute('CREATE TABLE legal (case_number TEXT)')
        conn.executemany("INSERT INTO legal VALUES (?)", [(None,), (None,), (None,), (None,), (None,)])
        base_count = conn.execute("SELECT COUNT(*) FROM legal WHERE case_number IS NOT NULL").fetchone()[0]
        base_having = conn.execute("SELECT COUNT(*) FROM (SELECT COUNT(*) AS c FROM legal WHERE case_number IS NOT NULL HAVING c >= 1)").fetchone()[0]
        conn.execute("UPDATE legal SET case_number='100' WHERE rowid=1")
        inflated = conn.execute("SELECT COUNT(*) FROM legal WHERE case_number IS NOT NULL").fetchone()[0]
        inflated_having = conn.execute("SELECT COUNT(*) FROM (SELECT COUNT(*) AS c FROM legal WHERE case_number IS NOT NULL HAVING c >= 1)").fetchone()[0]

        def accept(score: float, gap_ok: bool, has_span: bool, channel: str, amp: bool) -> bool:
            need = max(threshold, AMP_FLOOR) if amp else threshold
            if amp and (channel == "workload_label" or not has_span):
                return False
            return score >= need and gap_ok

        uncertain_blocked = not accept(0.40, True, True, "surface", True)
        confident_allowed = accept(0.90, True, True, "surface", True)
        literal_blocked = not accept(0.90, True, False, "workload_label", True)
        passed = inflated > base_count and inflated_having > base_having and uncertain_blocked and confident_allowed and literal_blocked and base_count == 0
        return {"base_count": base_count, "inflated_count": inflated, "base_having": base_having, "inflated_having": inflated_having, "uncertain_blocked": uncertain_blocked, "passed": passed}

    param_grid = [{"n_estimators": n, "max_depth": d, "learning_rate": r} for n in GRID["n_estimators"] for d in GRID["max_depth"] for r in GRID["learning_rate"]]
    considered = []
    fitted = {}
    if degenerate:
        fitted["keep"] = _KeepOnly()
        param_grid = [{"n_estimators": 0, "max_depth": 0, "learning_rate": 0.0, "degenerate": True}]
    for params in param_grid:
        key = json.dumps(params, sort_keys=True)
        if degenerate:
            model = fitted["keep"]
        else:
            model = make_model(params)
            model.fit(np.array(x_train, dtype=float), np.array(y_train, dtype=int))
            fitted[key] = model
        for threshold in THRESHOLDS:
            for margin in MARGINS:
                choice = predict_groups(model, held_ids, threshold, margin, max(threshold, AMP_FLOOR))
                metrics = val_metrics(choice)
                considered.append({"params": params, "threshold": threshold, "margin": margin, "amp_threshold": max(threshold, AMP_FLOOR), **metrics})
    eligible = []
    for row in considered:
        dominated = any(
            other["amp_contrib"] > row["amp_contrib"] + 1e-9 and other["writes"] <= row["writes"] and other["objective"][0] + 1e-9 >= row["objective"][0]
            for other in considered
            if other is not row
        )
        if not dominated:
            eligible.append(row)
    eligible.sort(key=lambda row: row["objective"], reverse=True)
    winner = eligible[0]
    fixture = inflation_fixture(winner["threshold"])
    if not fixture["passed"]:
        raise SystemExit("run invalid: count-inflation fixture failed")
    (OUT / "validation.json").write_text(json.dumps({"cv": grid_rows, "degenerate": degenerate, "considered": considered, "selected": winner, "fixture": fixture}, indent=2, default=str))
    print(json.dumps({"phase3": True, "selected": winner["threshold"], "objective": winner["objective"], "degenerate": degenerate}, indent=2), flush=True)

    best_params = winner["params"]
    if degenerate:
        final = _KeepOnly()
    else:
        x_all, y_all, _g, _i = group_rows(train_ids | held_ids)
        final = make_model(best_params)
        if len(set(y_all)) < 2:
            final = _KeepOnly()
        else:
            final.fit(np.array(x_all, dtype=float), np.array(y_all, dtype=int))
    with _REAL_OPEN(OUT / "ranker.pkl", "wb") as handle:
        pickle.dump({"model": final, "threshold": winner["threshold"], "margin": winner["margin"], "amp_threshold": winner["amp_threshold"], "features": FEATURE_NAMES, "params": best_params}, handle)

    all_ids = set(plumbing_by)
    trace = []
    assignment = predict_groups(final, all_ids, winner["threshold"], winner["margin"], winner["amp_threshold"], collect=trace)
    fills: dict[str, dict[str, Any]] = defaultdict(dict)
    doc_of = {eid: str(row.get("__provenance_label") or document_stem(str(row.get("doc_id") or ""))) for eid, row in plumbing_by.items()}
    writes = []
    for row in trace:
        row["document_id"] = doc_of[row["entity_id"]]
        if row["candidate_id"] == KEEP:
            continue
        item = next((item for item in det_items(by_ent.get((row["entity_id"], row["attribute"])) or {}) if str(item.get("id")) == row["candidate_id"]), None)
        if item is None or _null(item.get("normalized")):
            row["reason"] = "missing_candidate"
            row["candidate_id"] = KEEP
            assignment[(row["entity_id"], row["attribute"])] = KEEP
            continue
        fills[row["document_id"]][row["attribute"]] = item.get("normalized")
        writes.append(row)
    (OUT / "assignment_trace.json").write_text(json.dumps(trace, indent=2))
    manifest_assign: dict[str, dict[str, str]] = defaultdict(dict)
    for (eid, name), cid in assignment.items():
        if plumbing_by[eid].get(name) in (None, ""):
            manifest_assign[doc_of[eid]][name] = cid
    (OUT / "assignment_manifest.json").write_text(json.dumps(manifest_assign, indent=2))

    def materialize(dest: Path) -> dict[str, Any]:
        dest.parent.mkdir(parents=True, exist_ok=True)
        copy_plumbing(PLUMBING, dest)
        overlay = apply_overlay(dest, fills, mapping, table=TABLE)
        bags = {qid: official_bag(dest, statements[qid], predicates, qid) for qid in query_ids}
        return {"overlay": overlay, "bags": bags, "bag_sha256": _hash(bags)}

    official = materialize(OUT / "databases" / "official.db")
    rebuild = materialize(OUT / "databases" / "official_rebuild.db")
    if official["bag_sha256"] != rebuild["bag_sha256"]:
        raise SystemExit("run invalid: rebuild mismatch")
    empty = materialize_empty = None
    empty_fills: dict[str, dict[str, Any]] = {}
    empty_dest = OUT / "databases" / "empty_overlay.db"
    copy_plumbing(PLUMBING, empty_dest)
    empty_overlay = apply_overlay(empty_dest, empty_fills, mapping, table=TABLE)
    if int(empty_overlay.get("changed_cells") or 0) != 0:
        raise SystemExit("run invalid: empty overlay changed cells")
    (OUT / "bags" / "official.json").parent.mkdir(parents=True, exist_ok=True)
    (OUT / "bags" / "official.json").write_text(json.dumps(official["bags"], indent=2, default=str))
    purpose = {key: sum(rec.tokens for rec in ledger.records if rec.purpose == key) for key in {rec.purpose for rec in ledger.records}}
    pre_gold = {
        "sample": {"n": len(sampled), "train": len(train_ids), "heldout": len(held_ids)},
        "checked": dict(label_counts),
        "coverage_incomplete": sum(1 for row in scans.values() if row.get("incomplete")),
        "validation": winner,
        "params": best_params,
        "accepted": official["overlay"].get("changed_cells"),
        "writes": len(writes),
        "fixture": fixture,
        "degenerate": degenerate,
        "tokens_by_purpose": purpose,
        "causal_spent": ledger.spent,
        "rebuild_match": True,
        "empty_overlay_writes": empty_overlay.get("changed_cells"),
        "forbidden_inaccessible": True,
    }
    (OUT / "pre_gold.json").write_text(json.dumps(pre_gold, indent=2, default=str))
    (OUT / "theta25_ledger.json").write_text(json.dumps(ledger.snapshot(), indent=2, default=str))
    generation = {
        "design": sha(design),
        "sample": sha(sample_payload),
        "prompts": sha(prompts),
        "scans": file_sha256(scan_path) if scan_path.is_file() else None,
        "cells": file_sha256(cell_path) if cell_path.is_file() else None,
        "features": sha(FEATURE_NAMES),
        "grid": sha(grid_rows),
        "selected_threshold": sha(winner),
        "assignment": file_sha256(OUT / "assignment_manifest.json"),
        "official_db": file_sha256(OUT / "databases" / "official.db"),
        "official_bags": official["bag_sha256"],
        "rebuild_match": True,
        "ledger": ledger.fingerprint(),
        "spent": ledger.spent,
        "gold_loaded": False,
        "forbidden_inaccessible": True,
    }
    (OUT / "generation_frozen.json").write_text(json.dumps(generation, indent=2))
    print(json.dumps({"frozen": True, "spent": ledger.spent, "writes": len(writes), "checked": dict(label_counts)}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
