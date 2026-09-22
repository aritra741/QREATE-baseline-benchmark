"""Legal forced binary A/B aggregation. No KEEP output. No gold. No reachability. No prior pairwise judgments."""

from __future__ import annotations

import builtins
import hashlib
import json
import random
import re
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
)
_REAL_OPEN = builtins.open


def _blocked(path: Any) -> bool:
    text = str(path).replace("\\", "/")
    if any(token in text for token in BLOCKED):
        return True
    if "quwarts_legal" in text and (text.endswith("post_freeze.json") or text.endswith("/REPORT.md")):
        if "/quwarts_legal_forced_binary" not in text:
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
    ):
        if left + right in source:
            raise SystemExit("run invalid: runner references a forbidden result path")


builtins.open = _guarded_open

from quwarts.core.amortized_select.prompt import assemble_tools
from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog
from quwarts.core.full_window_additive.overlay import apply_overlay, copy_plumbing, official_bag
from quwarts.core.ledger import BudgetExhausted, SpendRecord, TokenLedger
from quwarts.core.llm.openrouter import load_env_file
from quwarts.core.materialize import file_sha256
from quwarts.core.shared_bundle.context_blocks import pack_c1, parse_layout
from quwarts.core.shared_bundle.inventory import compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.finan_amortized_select_arm import issue_call, mapping_from_rows, parse_tool, reserved_of, usage_of, _hash, _null
from quwarts.experiments.extract_util import field_terms

load_env_file(ROOT / ".env")

FROZEN_SELECT = ROOT / "results" / "quwarts_legal_evidence_card_select"
FROZEN_INV = ROOT / "results" / "quwarts_legal_multichannel_candidates"
PLUMBING = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
DOCETL_DIR = ROOT / "results" / "docetl_legal_case80"
SOURCE_DIR = ROOT / "source_data" / "Legal" / "legal_case"
SCHEMA_PATH = ROOT / "Query" / "Legal" / "Legal_attributes.json"
OUT = ROOT / "results" / "quwarts_legal_forced_binary"
THETA_25 = 12_610_011
FROZEN_A = 3_468_542
FROZEN_B_CUMULATIVE = 7_491_088
FROZEN_B = FROZEN_B_CUMULATIVE - FROZEN_A
KEEP = "KEEP_PLUMBING"
SCHEMA = {"choice": "str"}
TABLE = "legal"
SEED = 42
WEIGHTS = {"A_cand_B_cand": 3, "A_cand_B_keep": 2, "A_keep_B_cand": 2}
ALT_KEYS = ("Value", "Meaning", "Evidence", "Heading", "Period", "Unit", "Component", "Normalization", "Channel")

PROMPT = (
    "Choose which of X or Y is more likely to be the correct value of the requested attribute "
    "for this entity, given the supplied evidence. You must choose the better of the two even "
    "when evidence is imperfect.\n"
    "Compare subject/entity, attribute meaning, period, current versus historical status, "
    "total versus component, type, unit, and scale, table row and column, and direct evidential support.\n"
    "Do not ask whether either alternative is perfectly proven.\n"
    "Output exactly one of: X, Y."
)

EMPTY_ALT = {key: "" for key in ALT_KEYS}


def plumbing_alt() -> dict[str, str]:
    alt = dict(EMPTY_ALT)
    alt["Value"] = "NULL / no value written"
    alt["Meaning"] = "the document does not support assigning a value to this attribute"
    alt["Channel"] = "plumbing"
    return alt


def sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def clip(text: Any, n: int = 72) -> str:
    body = " ".join(str(text or "").split())
    return body if len(body) <= n else body[: n - 1].rstrip() + "…"


def channel_of(item: dict[str, Any]) -> str:
    raw = str(item.get("channel") or item.get("derivation") or "surface")
    return "composed" if raw.startswith("composed") else raw


def norm_choice(token: str | None, listed: set[str]) -> str:
    if token and token in listed:
        return token
    if token == KEEP:
        return KEEP
    return KEEP


def parse_choice(raw: str) -> str | None:
    found = []
    for label in ("X", "Y"):
        if re.search(r"(?<![A-Za-z0-9_])" + label + r"(?![A-Za-z0-9_])", raw or ""):
            found.append(label)
    if len(set(found)) == 1:
        return found[0]
    return None


def candidate_alt(item: dict[str, Any], spec, layouts) -> dict[str, str]:
    alt = dict(EMPTY_ALT)
    val = clip(item.get("normalized"), 72)
    alt["Value"] = val
    alt["Meaning"] = "typed candidate value for the requested attribute"
    spans = item.get("evidence_spans") or []
    snippet = str((spans[0] or {}).get("text") or "") if spans else ""
    if not snippet:
        snippet = str(item.get("local_text") or item.get("raw_span") or "")
    alt["Evidence"] = clip(snippet, 80)
    alt["Heading"] = clip(item.get("heading") or item.get("table_title") or item.get("column_header"), 40)
    alt["Period"] = clip(item.get("period"), 24)
    alt["Unit"] = clip(item.get("unit"), 24)
    alt["Component"] = clip(item.get("component_scope"), 40)
    trace = [str(x) for x in (item.get("normalization_trace") or [])[:2] if x]
    alt["Normalization"] = ",".join(trace)
    ch = channel_of(item)
    alt["Channel"] = ch
    if ch == "workload_label":
        alt["Meaning"] = "closed vocabulary token, not proof"
        if not spans:
            terms = {spec.name: list(dict.fromkeys(field_terms(spec.name) + field_terms(spec.official_description) + field_terms(str(item.get("normalized") or ""))))}
            packed = pack_c1(layouts, terms, 280)
            extra = clip(packed.get("text") or "", 120)
            if extra:
                alt["Evidence"] = (alt["Evidence"] + " support=" + extra).strip()
    return alt


def format_alt(label: str, alt: dict[str, str]) -> str:
    lines = [f"{label}:"]
    for key in ALT_KEYS:
        lines.append(f"{key}: {alt.get(key, '')}")
    return "\n".join(lines)


def card_user(header: str, x_alt: dict[str, str], y_alt: dict[str, str]) -> str:
    return header + "\n\n" + format_alt("X", x_alt) + "\n\n" + format_alt("Y", y_alt)


def synthetic_fixtures() -> list[dict[str, Any]]:
    def alt(**kwargs: str) -> dict[str, str]:
        row = dict(EMPTY_ALT)
        row.update(kwargs)
        return row

    return [
        {
            "id": "year_fy_vs_baseline",
            "class": "year",
            "attr": "fiscal_year",
            "dtype": "numeric/INTEGER",
            "desc": "The fiscal year of the report being described.",
            "entity": "Helios Labs annual report H-17",
            "supported": alt(Value="2022", Meaning="report fiscal year", Evidence="Helios Labs Annual Report for Fiscal Year 2022", Heading="Fiscal Year 2022", Period="2022", Channel="surface"),
            "foil": alt(Value="2018", Meaning="comparison baseline year", Evidence="compared with the 2018 baseline", Heading="Historical comparison", Period="2018", Channel="surface"),
        },
        {
            "id": "year_filing_vs_incorporation",
            "class": "year",
            "attr": "filing_year",
            "dtype": "numeric/INTEGER",
            "desc": "The year this filing was submitted.",
            "entity": "Orion Packing Form 10-K, document O-4",
            "supported": alt(Value="2021", Meaning="filing year on the cover", Evidence="Filed with the commission on 12 March 2021", Heading="Cover page", Period="2021", Channel="surface"),
            "foil": alt(Value="1996", Meaning="year the company was incorporated", Evidence="Orion Packing was incorporated in 1996", Heading="Corporate history", Period="1996", Channel="surface"),
        },
        {
            "id": "entity_helios_vs_orion",
            "class": "entity",
            "attr": "chief_executive",
            "dtype": "text/TEXT",
            "desc": "Name of the chief executive of the entity described by this document.",
            "entity": "Helios Labs, document H-17",
            "supported": alt(Value="Mara Chen", Meaning="CEO of Helios Labs", Evidence="Mara Chen, Chief Executive Officer of Helios Labs, signed the report", Heading="Signatures", Channel="surface"),
            "foil": alt(Value="Jon Hale", Meaning="CEO of a different company", Evidence="Jon Hale, Chief Executive Officer of Orion Packing", Heading="Industry peers", Channel="surface"),
        },
        {
            "id": "entity_parent_vs_subsidiary",
            "class": "entity",
            "attr": "employee_count",
            "dtype": "numeric/INTEGER",
            "desc": "Headcount of the reporting parent entity.",
            "entity": "Northwind Mills parent company, document N-2",
            "supported": alt(Value="4100", Meaning="parent company employees", Evidence="Northwind Mills employed 4,100 people at year end", Heading="Employees", Unit="people", Channel="surface"),
            "foil": alt(Value="180", Meaning="subsidiary headcount", Evidence="the Cedar Ridge mill, a subsidiary, employed 180 people", Heading="Subsidiary operations", Unit="people", Component="Cedar Ridge mill", Channel="surface"),
        },
        {
            "id": "total_revenue_vs_segment",
            "class": "total_vs_component",
            "attr": "total_revenue",
            "dtype": "numeric/REAL",
            "desc": "Consolidated total revenue for the reporting period, not a segment.",
            "entity": "Helios Labs, document H-17",
            "supported": alt(Value="1280000000", Meaning="consolidated total revenue", Evidence="Total revenue $1,280 million", Heading="Consolidated statements", Period="2022", Unit="USD", Component="total", Channel="surface"),
            "foil": alt(Value="210000000", Meaning="one product segment", Evidence="Optics segment revenue $210 million", Heading="Segment results", Period="2022", Unit="USD", Component="optics", Channel="surface"),
        },
        {
            "id": "total_headcount_vs_department",
            "class": "total_vs_component",
            "attr": "staff_total",
            "dtype": "numeric/INTEGER",
            "desc": "Total staff of the entity, not a single department.",
            "entity": "Orion Packing, document O-4",
            "supported": alt(Value="960", Meaning="company-wide staff", Evidence="Total staff 960", Heading="Workforce", Period="2021", Unit="people", Component="total", Channel="surface"),
            "foil": alt(Value="40", Meaning="warehouse department only", Evidence="Warehouse department: 40 staff", Heading="Department table", Period="2021", Unit="people", Component="warehouse", Channel="surface"),
        },
        {
            "id": "current_status_vs_former",
            "class": "current_vs_historical",
            "attr": "operating_status",
            "dtype": "text/TEXT",
            "desc": "Current operating status of the entity, not a past status.",
            "entity": "Cedar Ridge mill, document N-2",
            "supported": alt(Value="operating", Meaning="current status", Evidence="The Cedar Ridge mill is currently operating at full capacity", Heading="Current operations", Period="2022", Channel="surface"),
            "foil": alt(Value="idled", Meaning="historical status", Evidence="The mill was idled during 2015 maintenance", Heading="History", Period="2015", Channel="surface"),
        },
        {
            "id": "current_ceo_vs_retired",
            "class": "current_vs_historical",
            "attr": "current_chair",
            "dtype": "text/TEXT",
            "desc": "The person who currently chairs the board.",
            "entity": "Helios Labs, document H-17",
            "supported": alt(Value="Ruth Okoye", Meaning="current board chair", Evidence="Ruth Okoye currently serves as Chair of the Board", Heading="Board of directors", Period="2022", Channel="surface"),
            "foil": alt(Value="Paul Nye", Meaning="retired former chair", Evidence="Paul Nye retired as chair in 2019", Heading="Former officers", Period="2019", Channel="surface"),
        },
        {
            "id": "table_cell_vs_page_number",
            "class": "table_vs_heading",
            "attr": "net_income",
            "dtype": "numeric/REAL",
            "desc": "Net income from the financial table, not a page number or heading numeral.",
            "entity": "Orion Packing, document O-4",
            "supported": alt(Value="47000000", Meaning="net income table cell", Evidence="Net income 47,000,000", Heading="Income statement / Net income", Period="2021", Unit="USD", Channel="surface"),
            "foil": alt(Value="47", Meaning="page number", Evidence="— 47 —", Heading="Page footer", Channel="surface"),
        },
        {
            "id": "table_amount_vs_section_heading",
            "class": "table_vs_heading",
            "attr": "store_count",
            "dtype": "numeric/INTEGER",
            "desc": "Number of stores from the operations table, not a section number.",
            "entity": "Northwind Mills, document N-2",
            "supported": alt(Value="86", Meaning="store count in the table", Evidence="Retail stores 86", Heading="Store footprint table", Period="2022", Channel="surface"),
            "foil": alt(Value="12", Meaning="section heading number", Evidence="12 Retail footprint", Heading="Section 12", Channel="surface"),
        },
        {
            "id": "supported_amount_vs_null",
            "class": "supported_vs_null",
            "attr": "cash_balance",
            "dtype": "numeric/REAL",
            "desc": "Cash and cash equivalents at period end.",
            "entity": "Helios Labs, document H-17",
            "supported": alt(Value="88000000", Meaning="cash balance stated in the table", Evidence="Cash and cash equivalents $88 million", Heading="Balance sheet", Period="2022", Unit="USD", Channel="surface"),
            "foil": plumbing_alt(),
        },
        {
            "id": "supported_name_vs_null",
            "class": "supported_vs_null",
            "attr": "auditor_name",
            "dtype": "text/TEXT",
            "desc": "Name of the independent auditor who signed the opinion.",
            "entity": "Orion Packing, document O-4",
            "supported": alt(Value="Pine & Co", Meaning="auditor named in the opinion", Evidence="Pine & Co, independent auditor, signed the opinion", Heading="Auditor's report", Period="2021", Channel="surface"),
            "foil": plumbing_alt(),
        },
    ]


def fixture_header(fix: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"cell={fix['id']} attr={fix['attr']} type={fix['dtype']}",
            f"desc={fix['desc']}",
            f"entity={fix['entity']}",
        ]
    )


def fills_from_ids(choices: dict[str, str], cells: dict[str, dict[str, Any]], by_id) -> dict[str, dict[str, Any]]:
    fills: dict[str, dict[str, Any]] = defaultdict(dict)
    for cell_id, cid in choices.items():
        if not cid or cid == KEEP:
            continue
        cell = cells[cell_id]
        item = by_id.get((cell["document_id"], cell["attribute"], cid))
        if item is None or _null(item.get("normalized")):
            continue
        fills[cell["document_id"]][cell["attribute"]] = item.get("normalized")
    return dict(fills)


def materialize(dest: Path, fills, mapping, statements, predicates, query_ids) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    copy_plumbing(PLUMBING, dest)
    overlay = apply_overlay(dest, fills, mapping, table=TABLE)
    bags = {qid: official_bag(dest, statements[qid], predicates, qid) for qid in query_ids}
    return {"overlay": overlay, "bags": bags, "bag_sha256": _hash(bags), "db_sha256": file_sha256(dest)}


def decide_label(response: Any, raw_fallback: str) -> tuple[str | None, str, bool]:
    parsed_tool = parse_tool(response)
    raw = parsed_tool["raw"] or raw_fallback
    label = None
    if not parsed_tool["malformed"]:
        token = str(parsed_tool["parsed"].get("choice") or "").strip().upper()
        if token in {"X", "Y"}:
            label = token
    if label is None:
        label = parse_choice(raw)
    return label, raw, bool(parsed_tool["malformed"] or label is None)


def main() -> int:
    assert_access_closed()
    for token in BLOCKED:
        probe = ROOT / "results" / token.strip("/")
        try:
            _guarded_open(probe, "r")
        except RuntimeError:
            continue
        raise SystemExit(f"run invalid: forbidden path was readable: {probe}")
    OUT.mkdir(parents=True, exist_ok=True)
    freeze_src = json.loads((FROZEN_SELECT / "generation_frozen.json").read_text())
    parsed_src = json.loads((FROZEN_SELECT / "parsed_decisions.json").read_text())
    cards_src = json.loads((FROZEN_SELECT / "cards.json").read_text())
    inventory = json.loads((FROZEN_INV / "candidate_inventory.json").read_text())
    manifest = json.loads((DOCETL_DIR / "query_manifest.json").read_text())
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    records = compile_attribute_inventory(statements)
    specs = compile_specs(load_official_catalog(SCHEMA_PATH), records)
    import sqlite3

    conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    cols = [row[1] for row in conn.execute(f'PRAGMA table_info("{TABLE}")')]
    plumbing_rows = [dict(zip(cols, rec)) for rec in conn.execute(f'SELECT * FROM "{TABLE}"')]
    conn.close()
    mapping = mapping_from_rows(plumbing_rows)
    texts = {path.stem: path.read_text(encoding="utf-8", errors="replace") for path in sorted(SOURCE_DIR.glob("*.txt"))}
    layouts = {doc: parse_layout(doc, text) for doc, text in texts.items()}
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))

    by_id = {}
    for rec in inventory:
        for item in rec.get("all_candidates") or rec.get("candidates") or []:
            by_id[(rec["document_id"], rec["attribute"], str(item.get("id")))] = item

    cells: dict[str, dict[str, Any]] = {}
    for card in cards_src:
        listed = set(card["listed_ids"])
        a = norm_choice(parsed_src.get("A", {}).get(card["cell_id"]), listed)
        b = norm_choice(parsed_src.get("B", {}).get(card["cell_id"]), listed)
        heading = ""
        for block in layouts.get(card["document_id"]) or []:
            if getattr(block, "kind", "") == "section_heading":
                heading = str(getattr(block, "heading", "") or getattr(block, "text", ""))
                break
        if a == b:
            kind = "A=B candidate" if a != KEEP else "A=B plumbing"
        elif a != KEEP and b != KEEP:
            kind = "A_cand_B_cand"
        elif a != KEEP and b == KEEP:
            kind = "A_cand_B_keep"
        else:
            kind = "A_keep_B_cand"
        cells[card["cell_id"]] = {
            **{k: card[k] for k in ("cell_id", "entity_id", "document_id", "attribute", "listed_ids", "n_candidates")},
            "A": a,
            "B": b,
            "kind": kind,
            "heading": heading,
        }
    cohorts = Counter(cell["kind"] for cell in cells.values())
    disagreements = [cid for cid, cell in cells.items() if cell["kind"] in WEIGHTS]
    print(json.dumps({"cohorts": dict(cohorts), "disagreements": len(disagreements)}, indent=2), flush=True)

    policy = {
        "theta_25": THETA_25,
        "frozen_A": FROZEN_A,
        "frozen_B_cumulative": FROZEN_B_CUMULATIVE,
        "headroom": THETA_25 - FROZEN_B_CUMULATIVE,
        "resolution": "if A==B use A; else if both order-reversed calls map to B use B; else A",
        "weights": WEIGHTS,
        "no_keep_output": True,
        "no_repair_calls": True,
        "model": "openrouter/qwen/qwen-2.5-7b-instruct",
        "seed": SEED,
        "prompt": PROMPT,
    }
    fixtures = synthetic_fixtures()
    (OUT / "policy.json").write_text(json.dumps(policy, indent=2))
    (OUT / "prompts.json").write_text(json.dumps({"binary": PROMPT}, indent=2))
    (OUT / "synthetic_fixtures.json").write_text(json.dumps(fixtures, indent=2))
    prompt_hash = sha(PROMPT)
    fixture_hash = sha(fixtures)
    print(json.dumps({"prompt_frozen": True, "prompt": prompt_hash, "fixtures": fixture_hash}, indent=2), flush=True)

    ledger = TokenLedger(theta=THETA_25, seed=SEED)
    journal_path = OUT / "response_journal.jsonl"
    gate_journal = OUT / "gate_journal.jsonl"
    if (OUT / "live_ledger.json").is_file():
        snap = json.loads((OUT / "live_ledger.json").read_text())
        ledger.spent = int(snap.get("spent") or 0)
        ledger.records = [SpendRecord(row["purpose"], row["tokens"], row.get("metadata") or {}) for row in snap.get("records") or []]
    else:
        ledger.spend(FROZEN_A, "frozen_pass_A")
        ledger.spend(FROZEN_B, "frozen_pass_B")

    def persist() -> None:
        (OUT / "live_ledger.json").write_text(json.dumps(ledger.snapshot(), indent=2, default=str))

    def one_call(user: str, purpose: str, meta: dict[str, Any]) -> dict[str, Any]:
        bundled = assemble_tools(SCHEMA, PROMPT + "\n\n" + user)
        _pt, reserved = reserved_of(bundled["user"], bundled["tools"])
        try:
            response = issue_call(bundled["request"])
        except Exception as exc:
            return {"label": None, "raw": str(exc), "malformed": True, "actual": 0, "reserved": reserved, "reason": "call_error"}
        prompt_tokens, completion, actual = usage_of(response, reserved)
        try:
            ledger.spend(actual, purpose, reserved=reserved, **meta)
        except BudgetExhausted:
            return {"label": None, "raw": "", "malformed": True, "actual": 0, "reserved": reserved, "reason": "budget_exhausted"}
        label, raw, malformed = decide_label(response, "")
        return {
            "label": label,
            "raw": raw,
            "malformed": malformed,
            "actual": actual,
            "reserved": reserved,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion,
            "reason": "ok" if label in {"X", "Y"} else "invalid_or_malformed",
        }

    gate_rows = []
    if gate_journal.is_file() and (OUT / "gate_result.json").is_file():
        gate_rows = [json.loads(line) for line in gate_journal.read_text().splitlines() if line.strip()]
    if len(gate_rows) < 12:
        gate_rows = []
        if gate_journal.is_file():
            gate_journal.unlink()
        for fix in fixtures:
            header = fixture_header(fix)
            fwd_user = card_user(header, fix["supported"], fix["foil"])
            rev_user = card_user(header, fix["foil"], fix["supported"])
            with ThreadPoolExecutor(max_workers=2) as pool:
                f1 = pool.submit(one_call, fwd_user, "synthetic_gate_forward", {"fixture": fix["id"]})
                f2 = pool.submit(one_call, rev_user, "synthetic_gate_reverse", {"fixture": fix["id"]})
                g1, g2 = f1.result(), f2.result()
            row = {
                "fixture_id": fix["id"],
                "class": fix["class"],
                "forward": g1,
                "reverse": g2,
                "forward_supported_label": "X",
                "reverse_supported_label": "Y",
                "forward_correct": g1.get("label") == "X",
                "reverse_correct": g2.get("label") == "Y",
                "order_consistent": g1.get("label") == "X" and g2.get("label") == "Y" or (g1.get("label") == "Y" and g2.get("label") == "X"),
                "parsed": not g1.get("malformed") and not g2.get("malformed") and g1.get("label") in {"X", "Y"} and g2.get("label") in {"X", "Y"},
            }
            if g1.get("label") == "X" and g2.get("label") == "Y":
                row["order_consistent"] = True
                row["consistent_side"] = "supported"
            elif g1.get("label") == "Y" and g2.get("label") == "X":
                row["order_consistent"] = True
                row["consistent_side"] = "foil"
            else:
                row["order_consistent"] = False
                row["consistent_side"] = None
            gate_rows.append(row)
            with _REAL_OPEN(gate_journal, "a") as handle:
                handle.write(json.dumps(row, default=str) + "\n")
            persist()

    n_correct = sum(int(row["forward_correct"]) + int(row["reverse_correct"]) for row in gate_rows)
    n_consistent = sum(int(row["order_consistent"]) for row in gate_rows)
    n_parsed = sum(int(row["parsed"]) for row in gate_rows)
    gate_pass = n_correct >= 22 and n_consistent >= 11 and n_parsed == 12
    gate_result = {
        "n_calls": 24,
        "correct": n_correct,
        "order_consistent_fixtures": n_consistent,
        "parsed_fixtures": n_parsed,
        "passed": gate_pass,
        "threshold_correct": 22,
        "threshold_consistent": 11,
        "rows": [{k: row[k] for k in row if k not in {"forward", "reverse"}} | {"forward_label": row["forward"].get("label"), "reverse_label": row["reverse"].get("label"), "forward_malformed": row["forward"].get("malformed"), "reverse_malformed": row["reverse"].get("malformed")} for row in gate_rows],
    }
    (OUT / "gate_result.json").write_text(json.dumps(gate_result, indent=2, default=str))
    print(json.dumps({"gate_passed": gate_pass, "correct": n_correct, "order_consistent": n_consistent, "parsed": n_parsed, "spent": ledger.spent}, indent=2), flush=True)
    persist()

    if not gate_pass:
        pre_gold = {
            "gate_passed": False,
            "synthetic_correct": n_correct,
            "synthetic_order_consistent": n_consistent,
            "synthetic_parsed_fixtures": n_parsed,
            "causal_spent": ledger.spent,
            "legal_calls": 0,
            "decision": "forced binary prompt failed synthetic gate",
        }
        (OUT / "pre_gold.json").write_text(json.dumps(pre_gold, indent=2))
        (OUT / "theta25_ledger.json").write_text(json.dumps(ledger.snapshot(), indent=2, default=str))
        generation = {
            "select_freeze": freeze_src,
            "inventory": file_sha256(FROZEN_INV / "candidate_inventory.json"),
            "prompt": prompt_hash,
            "fixtures": fixture_hash,
            "gate": sha(gate_result),
            "ledger": ledger.fingerprint(),
            "spent": ledger.spent,
            "gate_passed": False,
            "gold_loaded": False,
            "forbidden_inaccessible": True,
        }
        (OUT / "generation_frozen.json").write_text(json.dumps(generation, indent=2))
        (OUT / "REPORT.md").write_text(
            "\n".join(
                [
                    "# Legal forced binary A/B aggregation",
                    "",
                    f"Synthetic gate: {n_correct}/24 correct, {n_consistent}/12 order-consistent, {n_parsed}/12 parsed.",
                    "The frozen prompt was not edited. No Legal calls were made.",
                    "",
                    "forced binary prompt failed synthetic gate",
                    "",
                ]
            )
        )
        print(json.dumps({"frozen": True, "decision": "forced binary prompt failed synthetic gate"}, indent=2), flush=True)
        return 0

    pair_cards = {}
    perms = {}
    reserved_pair = {}
    for idx, cell_id in enumerate(sorted(disagreements)):
        cell = cells[cell_id]
        spec = specs[cell["attribute"]]
        rng = random.Random(1009 + 17 * idx + SEED)
        a_first = rng.random() < 0.5
        fwd_map = {"X": "A", "Y": "B"} if a_first else {"X": "B", "Y": "A"}
        rev_map = {"X": fwd_map["Y"], "Y": fwd_map["X"]}
        def alt_for(pass_id: str) -> dict[str, str]:
            if pass_id == KEEP:
                return plumbing_alt()
            item = by_id.get((cell["document_id"], cell["attribute"], pass_id))
            if item is None:
                return plumbing_alt()
            return candidate_alt(item, spec, layouts.get(cell["document_id"]) or [])

        alts = {"A": alt_for(cell["A"]), "B": alt_for(cell["B"])}
        header = "\n".join(
            [
                f"cell={cell['cell_id']} attr={spec.name} type={spec.dtype}/{spec.sql_type}",
                f"desc={spec.official_description}",
                f"entity={cell['document_id']} heading={clip(cell['heading'], 60)}",
            ]
        )
        fwd_user = card_user(header, alts[fwd_map["X"]], alts[fwd_map["Y"]])
        rev_user = card_user(header, alts[rev_map["X"]], alts[rev_map["Y"]])
        b1 = assemble_tools(SCHEMA, PROMPT + "\n\n" + fwd_user)
        b2 = assemble_tools(SCHEMA, PROMPT + "\n\n" + rev_user)
        _p1, r1 = reserved_of(b1["user"], b1["tools"])
        _p2, r2 = reserved_of(b2["user"], b2["tools"])
        reserved_pair[cell_id] = r1 + r2
        pair_cards[cell_id] = {
            "cell_id": cell_id,
            "attribute": cell["attribute"],
            "kind": cell["kind"],
            "header": header,
            "fwd_user": fwd_user,
            "rev_user": rev_user,
            "fwd_map": fwd_map,
            "rev_map": rev_map,
            "reserved": reserved_pair[cell_id],
            "reserved_fwd": r1,
            "reserved_rev": r2,
        }
        perms[cell_id] = {"forward": fwd_map, "reverse": rev_map}

    groups: dict[str, list[str]] = defaultdict(list)
    scored = []
    for cell_id in disagreements:
        rec = records[cells[cell_id]["attribute"]]
        amp = 1 + sum(int(rec.roles.get(role) or 0) for role in ("WHERE", "CASE", "GROUP BY", "aggregate input", "HAVING"))
        weight = WEIGHTS[cells[cell_id]["kind"]]
        cost = max(reserved_pair[cell_id], 1)
        priority = (rec.occurrence_count * amp * weight) / cost
        scored.append((priority, cells[cell_id]["attribute"], cell_id))
        groups[cells[cell_id]["attribute"]].append(cell_id)
    for name in groups:
        groups[name].sort(key=lambda cid: (-next(p for p, a, c in scored if c == cid), cid))
    schedule = []
    attrs = sorted(groups)
    indexes = {name: 0 for name in attrs}
    while True:
        progressed = False
        for name in attrs:
            i = indexes[name]
            if i < len(groups[name]):
                schedule.append(groups[name][i])
                indexes[name] = i + 1
                progressed = True
        if not progressed:
            break

    pre = {
        "select_freeze": freeze_src,
        "inventory": file_sha256(FROZEN_INV / "candidate_inventory.json"),
        "prompt": prompt_hash,
        "fixtures": fixture_hash,
        "gate": sha(gate_result),
        "cards": sha([{k: pair_cards[cid][k] for k in ("cell_id", "header", "fwd_user", "rev_user", "fwd_map", "rev_map")} for cid in schedule]),
        "permutations": sha(perms),
        "policy": sha(policy),
        "schedule": sha(schedule),
        "reservations": sha(reserved_pair),
        "cohorts": dict(cohorts),
        "n_disagreement": len(schedule),
        "est_all_pairs": sum(reserved_pair[cid] for cid in schedule),
        "fits_remaining": ledger.spent + sum(reserved_pair[cid] for cid in schedule) <= THETA_25,
    }
    (OUT / "cohorts_pre_spend.json").write_text(json.dumps({"cohorts": dict(cohorts), "disagreements": len(schedule)}, indent=2))
    (OUT / "pair_cards.json").write_text(json.dumps(pair_cards, indent=2))
    (OUT / "permutations.json").write_text(json.dumps(perms, indent=2))
    (OUT / "schedule.json").write_text(json.dumps(schedule, indent=2))
    (OUT / "reservations.json").write_text(json.dumps(reserved_pair, indent=2))
    (OUT / "pre_call_freeze.json").write_text(json.dumps(pre, indent=2))
    print(json.dumps({"cards_frozen": True, "n_disagreement": len(schedule), "est_all_pairs": pre["est_all_pairs"], "fits_remaining": pre["fits_remaining"], "spent": ledger.spent}, indent=2), flush=True)

    done: set[str] = set()
    fwd_choice: dict[str, str | None] = {}
    rev_choice: dict[str, str | None] = {}
    if journal_path.is_file():
        for line in journal_path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            done.add(row["cell_id"])
            fwd_choice[row["cell_id"]] = row.get("fwd_pass")
            rev_choice[row["cell_id"]] = row.get("rev_pass")

    scheduled_ok = []
    unscheduled = []
    for i, cell_id in enumerate(schedule):
        if cell_id in done:
            scheduled_ok.append(cell_id)
            continue
        need = pair_cards[cell_id]["reserved"]
        if ledger.spent + need > ledger.theta:
            unscheduled.append(cell_id)
            continue
        card = pair_cards[cell_id]
        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(one_call, card["fwd_user"], "forced_binary_forward", {"cell_id": cell_id, "attribute": cells[cell_id]["attribute"], "direction": "forward"})
            f2 = pool.submit(one_call, card["rev_user"], "forced_binary_reverse", {"cell_id": cell_id, "attribute": cells[cell_id]["attribute"], "direction": "reverse"})
            g1, g2 = f1.result(), f2.result()
        if g1.get("reason") == "budget_exhausted" or g2.get("reason") == "budget_exhausted":
            unscheduled.append(cell_id)
            continue
        fwd_pass = card["fwd_map"].get(g1.get("label")) if g1.get("label") in {"X", "Y"} else None
        rev_pass = card["rev_map"].get(g2.get("label")) if g2.get("label") in {"X", "Y"} else None
        fwd_choice[cell_id] = fwd_pass
        rev_choice[cell_id] = rev_pass
        scheduled_ok.append(cell_id)
        with _REAL_OPEN(journal_path, "a") as handle:
            handle.write(
                json.dumps(
                    {
                        "cell_id": cell_id,
                        "attribute": cells[cell_id]["attribute"],
                        "kind": cells[cell_id]["kind"],
                        "A": cells[cell_id]["A"],
                        "B": cells[cell_id]["B"],
                        "fwd": g1,
                        "rev": g2,
                        "fwd_pass": fwd_pass,
                        "rev_pass": rev_pass,
                        "spent_after": ledger.spent,
                    },
                    default=str,
                )
                + "\n"
            )
        persist()
        if (i + 1) % 50 == 0:
            print(json.dumps({"done": i + 1, "spent": ledger.spent, "remaining": THETA_25 - ledger.spent}, indent=2), flush=True)

    def resolve(cell_id: str, mode: str, completed: set[str] | None = None) -> str:
        cell = cells[cell_id]
        if cell["A"] == cell["B"]:
            return cell["A"]
        if completed is not None and cell_id not in completed:
            return cell["A"]
        fwd = fwd_choice.get(cell_id)
        rev = rev_choice.get(cell_id)
        if mode == "A":
            return cell["A"]
        if mode == "B":
            return cell["B"]
        if mode == "forward":
            return cell[fwd] if fwd in {"A", "B"} else cell["A"]
        if mode == "reverse":
            return cell[rev] if rev in {"A", "B"} else cell["A"]
        if mode == "consistent_A":
            if fwd == "A" and rev == "A":
                return cell["A"]
            return cell["B"] if cell["B"] else cell["A"]
        if mode == "consistent_B":
            if fwd == "B" and rev == "B":
                return cell["B"]
            return cell["A"]
        if fwd == "B" and rev == "B":
            return cell["B"]
        return cell["A"]

    completed = set(scheduled_ok)
    official = {cid: resolve(cid, "official", completed) for cid in cells}
    arms = {
        "A": {cid: resolve(cid, "A") for cid in cells},
        "B": {cid: resolve(cid, "B") for cid in cells},
        "forward": {cid: resolve(cid, "forward", completed) for cid in cells},
        "reverse": {cid: resolve(cid, "reverse", completed) for cid in cells},
        "consistent_A_replacements": {cid: resolve(cid, "consistent_A", completed) for cid in cells},
        "consistent_B_replacements": {cid: resolve(cid, "consistent_B", completed) for cid in cells},
        "official": official,
    }
    n_sched = max(len(schedule), 1)
    for frac, name in ((0.25, "prefix_25"), (0.50, "prefix_50"), (0.75, "prefix_75"), (1.0, "prefix_100")):
        cutoff = set(schedule[: int(frac * n_sched)])
        arms[name] = {cid: resolve(cid, "official", completed & cutoff) for cid in cells}

    parsed_out = {
        "A": {cid: cells[cid]["A"] for cid in cells},
        "B": {cid: cells[cid]["B"] for cid in cells},
        "forward": fwd_choice,
        "reverse": rev_choice,
        "official": official,
        "completed": sorted(completed),
        "unscheduled": unscheduled,
    }
    (OUT / "parsed_decisions.json").write_text(json.dumps(parsed_out, indent=2, default=str))

    arm_hashes = {}
    for name, mapping_choices in arms.items():
        dest = OUT / "databases" / f"{name}.db"
        fills = fills_from_ids(mapping_choices, cells, by_id)
        mat = materialize(dest, fills, mapping, statements, predicates, query_ids)
        dest2 = OUT / "databases" / f"{name}_rebuild.db"
        mat2 = materialize(dest2, fills, mapping, statements, predicates, query_ids)
        if mat["bag_sha256"] != mat2["bag_sha256"]:
            raise SystemExit(f"run invalid: rebuild mismatch for {name}")
        accepted = sum(1 for choice in mapping_choices.values() if choice and choice != KEEP)
        (OUT / "bags" / f"{name}.json").parent.mkdir(parents=True, exist_ok=True)
        (OUT / "bags" / f"{name}.json").write_text(json.dumps(mat["bags"], indent=2, default=str))
        (OUT / "fills" / f"{name}.json").parent.mkdir(parents=True, exist_ok=True)
        (OUT / "fills" / f"{name}.json").write_text(json.dumps(fills, indent=2, default=str))
        (OUT / "arm_meta" / f"{name}.json").parent.mkdir(parents=True, exist_ok=True)
        (OUT / "arm_meta" / f"{name}.json").write_text(
            json.dumps({"accepted": accepted, "changed_cells": mat["overlay"].get("changed_cells"), "bag_sha256": mat["bag_sha256"], "rebuild_match": True, "db_sha256": mat["db_sha256"]}, indent=2)
        )
        arm_hashes[name] = {"db": mat["db_sha256"], "bags": mat["bag_sha256"]}

    consistent_a = consistent_b = order_dis = malformed = 0
    for cell_id in completed:
        fwd, rev = fwd_choice.get(cell_id), rev_choice.get(cell_id)
        if fwd is None or rev is None:
            malformed += 1
            order_dis += 1
            continue
        if fwd == rev == "A":
            consistent_a += 1
        elif fwd == rev == "B":
            consistent_b += 1
        else:
            order_dis += 1
    tokens_by_direction = {
        "forward": sum(r.tokens for r in ledger.records if r.purpose == "forced_binary_forward"),
        "reverse": sum(r.tokens for r in ledger.records if r.purpose == "forced_binary_reverse"),
        "gate": sum(r.tokens for r in ledger.records if r.purpose.startswith("synthetic_gate")),
    }
    tokens_by_attribute: dict[str, int] = defaultdict(int)
    for rec in ledger.records:
        if rec.purpose.startswith("forced_binary_"):
            tokens_by_attribute[str((rec.metadata or {}).get("attribute") or "unknown")] += rec.tokens
    purpose = {k: sum(r.tokens for r in ledger.records if r.purpose == k) for k in {r.purpose for r in ledger.records}}
    pre_gold = {
        "gate_passed": True,
        "synthetic_correct": n_correct,
        "synthetic_order_consistent": n_consistent,
        "synthetic_parsed_fixtures": n_parsed,
        "A_eq_B_candidate": cohorts.get("A=B candidate", 0),
        "A_eq_B_plumbing": cohorts.get("A=B plumbing", 0),
        "A_cand_B_cand": cohorts.get("A_cand_B_cand", 0),
        "A_cand_B_plumbing": cohorts.get("A_cand_B_keep", 0),
        "A_plumbing_B_cand": cohorts.get("A_keep_B_cand", 0),
        "scheduled_disagreements": len(schedule),
        "completed_pairs": len(completed),
        "unscheduled_A_fallback": len(unscheduled),
        "consistent_A": consistent_a,
        "consistent_B": consistent_b,
        "order_disagreements": order_dis,
        "malformed_responses": malformed,
        "tokens_by_purpose": purpose,
        "tokens_by_direction": tokens_by_direction,
        "tokens_by_attribute": dict(tokens_by_attribute),
        "causal_spent": ledger.spent,
        "pairwise_spent": ledger.spent - FROZEN_B_CUMULATIVE,
        "official_accepted": sum(1 for choice in official.values() if choice and choice != KEEP),
        "forbidden_inaccessible": True,
    }
    (OUT / "pre_gold.json").write_text(json.dumps(pre_gold, indent=2, default=str))
    (OUT / "theta25_ledger.json").write_text(json.dumps(ledger.snapshot(), indent=2, default=str))
    generation = {
        **pre,
        "journal": file_sha256(journal_path) if journal_path.is_file() else None,
        "parsed": sha(parsed_out),
        "ledger": ledger.fingerprint(),
        "spent": ledger.spent,
        "official_accepted": pre_gold["official_accepted"],
        "arm_hashes": arm_hashes,
        "gate_passed": True,
        "gold_loaded": False,
        "forbidden_inaccessible": True,
    }
    (OUT / "generation_frozen.json").write_text(json.dumps(generation, indent=2))
    print(json.dumps({"frozen": True, **{k: pre_gold[k] for k in ("completed_pairs", "unscheduled_A_fallback", "consistent_A", "consistent_B", "order_disagreements", "causal_spent", "official_accepted")}}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
