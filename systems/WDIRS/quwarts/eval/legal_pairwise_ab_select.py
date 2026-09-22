"""Legal A/B pairwise aggregation arm. Frozen A/B only. No gold. No reachability artifacts."""

from __future__ import annotations

import builtins
import hashlib
import json
import random
import re
import sys
import time
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
)
_REAL_OPEN = builtins.open


def _blocked(path: Any) -> bool:
    text = str(path).replace("\\", "/")
    return any(token in text for token in BLOCKED)


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
    for left, right in (
        ("quwarts_legal_", "shared_reachability/"),
        ("quwarts_legal_", "cost_aware_reachability/"),
        ("quwarts_legal_", "evidence_card_aggregation_audit/"),
    ):
        if left + right in source:
            raise SystemExit("run invalid: runner references a forbidden result path")


builtins.open = _guarded_open

from quwarts.core.amortized_select.prompt import assemble_tools
from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog
from quwarts.core.docetl_exact_message.adapter import DOCETL_SYSTEM
from quwarts.core.full_window_additive.overlay import apply_overlay, copy_plumbing, official_bag
from quwarts.core.ledger import TokenLedger
from quwarts.core.llm.openrouter import load_env_file
from quwarts.core.materialize import file_sha256
from quwarts.core.retrieve_extract.tokens import count_tokens
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
OUT = ROOT / "results" / "quwarts_legal_pairwise_ab"
THETA_25 = 12_610_011
FROZEN_A = 3_468_542
FROZEN_B_CUMULATIVE = 7_491_088
FROZEN_B = FROZEN_B_CUMULATIVE - FROZEN_A
KEEP = "KEEP_PLUMBING"
SCHEMA = {"choice": "str"}
TABLE = "legal"
SEED = 42
WEIGHTS = {"A_cand_B_cand": 3, "A_cand_B_keep": 2, "A_keep_B_cand": 2}

JUDGE1 = (
    "Compare option X, option Y if present, and KEEP.\n"
    "Select the option that best answers the official attribute description for this entity.\n"
    "Check correct subject, correct period, correct semantic role, total versus component, "
    "value versus heading or example or citation, unit and scale, and whether the evidence "
    "actually supports writing a value.\n"
    "Output exactly one of: X, Y, KEEP."
)
JUDGE2 = (
    "Try to falsify each listed option.\n"
    "Reject an option if it is the wrong entity, the wrong period, the wrong field, "
    "a historical statement rather than current status, the wrong table row or column, "
    "an unsupported workload label, or an incidental number or name.\n"
    "Keep only an option that survives those checks. If none survive, output KEEP.\n"
    "Output exactly one of: X, Y, KEEP."
)


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


def parse_judge(raw: str, allowed: set[str]) -> str | None:
    found = []
    for label in ("KEEP", "X", "Y"):
        if label in allowed and re.search(r"(?<![A-Za-z0-9_])" + label + r"(?![A-Za-z0-9_])", raw or ""):
            found.append(label)
    if len(set(found)) == 1:
        return found[0]
    return None


def evidence_line(item: dict[str, Any], spec, layouts) -> str:
    ch = channel_of(item)
    val = clip(item.get("normalized"), 72)
    spans = item.get("evidence_spans") or []
    snippet = ""
    if spans:
        snippet = str((spans[0] or {}).get("text") or "")
    if not snippet:
        snippet = str(item.get("local_text") or item.get("raw_span") or "")
    ev = clip(snippet, 80)
    parts = [ch, f"`{val}`"]
    if item.get("period"):
        parts.append(f"period={item.get('period')}")
    if item.get("unit"):
        parts.append(f"unit={item.get('unit')}")
    if item.get("component_scope"):
        parts.append(f"component={item.get('component_scope')}")
    hd = clip(item.get("heading") or item.get("table_title") or item.get("column_header"), 40)
    if hd and hd != "document":
        parts.append(f"heading={hd}")
    trace = [str(x) for x in (item.get("normalization_trace") or [])[:2] if x]
    if trace:
        parts.append("norm=" + ",".join(trace))
    if ev and ev != val:
        parts.append(f"evidence={ev}")
    if ch == "workload_label":
        if spans:
            parts.append("label_meaning=closed vocabulary token, not proof")
        else:
            terms = {spec.name: list(dict.fromkeys(field_terms(spec.name) + field_terms(spec.official_description) + field_terms(str(item.get("normalized") or ""))))}
            packed = pack_c1(layouts, terms, 280)
            parts.append("label_meaning=closed vocabulary token, not proof")
            parts.append("support=" + clip(packed.get("text") or "", 120))
    return " ".join(parts)


def pair_body(cell: dict[str, Any], spec, heading: str, label_map: dict[str, str], by_id, layouts) -> str:
    lines = [
        f"cell={cell['cell_id']} attr={spec.name} type={spec.dtype}/{spec.sql_type}",
        f"desc={spec.official_description}",
        f"entity={cell['document_id']} heading={clip(heading, 60)}",
    ]
    for label in ("X", "Y"):
        cid = label_map.get(label)
        if not cid or cid == KEEP:
            continue
        item = by_id.get((cell["document_id"], cell["attribute"], cid))
        if item is None:
            continue
        lines.append(f"{label}: {evidence_line(item, spec, layouts)}")
    lines.append("KEEP: leave the existing NULL; write nothing")
    return "\n".join(lines)


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
    freeze = json.loads((FROZEN_SELECT / "generation_frozen.json").read_text())
    parsed = json.loads((FROZEN_SELECT / "parsed_decisions.json").read_text())
    cards = json.loads((FROZEN_SELECT / "cards.json").read_text())
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
    for card in cards:
        listed = set(card["listed_ids"])
        a = norm_choice(parsed.get("A", {}).get(card["cell_id"]), listed)
        b = norm_choice(parsed.get("B", {}).get(card["cell_id"]), listed)
        heading = ""
        for block in layouts.get(card["document_id"]) or []:
            if getattr(block, "kind", "") == "section_heading":
                heading = str(getattr(block, "heading", "") or getattr(block, "text", ""))
                break
        if a == b:
            kind = "A=B candidate" if a != KEEP else "A=B KEEP"
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

    pair_cards = {}
    perms = {"J1": {}, "J2": {}}
    reserved_pair = {}
    for idx, cell_id in enumerate(sorted(disagreements)):
        cell = cells[cell_id]
        spec = specs[cell["attribute"]]
        cands = [cid for cid in (cell["A"], cell["B"]) if cid != KEEP]
        cands = list(dict.fromkeys(cands))
        rng = random.Random(1009 + 17 * idx)
        order = list(cands)
        rng.shuffle(order)
        perms["J1"][cell_id] = list(order)
        perms["J2"][cell_id] = list(reversed(order)) if len(order) == 2 else list(order)
        if len(order) == 1:
            j1_map = {"X": order[0], "KEEP": KEEP}
            j2_map = {"Y": order[0], "KEEP": KEEP}
        else:
            j1_map = {"X": order[0], "Y": order[1], "KEEP": KEEP}
            j2_map = {"X": order[1], "Y": order[0], "KEEP": KEEP}
        perms["J1"][cell_id] = {k: v for k, v in j1_map.items() if k != "KEEP"}
        perms["J2"][cell_id] = {k: v for k, v in j2_map.items() if k != "KEEP"}
        body1 = pair_body(cell, spec, cell["heading"], j1_map, by_id, layouts.get(cell["document_id"]) or [])
        body2 = pair_body(cell, spec, cell["heading"], j2_map, by_id, layouts.get(cell["document_id"]) or [])
        b1 = assemble_tools(SCHEMA, JUDGE1 + "\n\n" + body1)
        b2 = assemble_tools(SCHEMA, JUDGE2 + "\n\n" + body2)
        _p1, r1 = reserved_of(b1["user"], b1["tools"])
        _p2, r2 = reserved_of(b2["user"], b2["tools"])
        reserved_pair[cell_id] = r1 + r2
        pair_cards[cell_id] = {
            "cell_id": cell_id,
            "attribute": cell["attribute"],
            "kind": cell["kind"],
            "j1_body": body1,
            "j2_body": body2,
            "j1_map": j1_map,
            "j2_map": j2_map,
            "j1_allowed": sorted(j1_map),
            "j2_allowed": sorted(j2_map),
            "reserved": reserved_pair[cell_id],
            "reserved_j1": r1,
            "reserved_j2": r2,
        }

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

    policy = {
        "theta_25": THETA_25,
        "frozen_A": FROZEN_A,
        "frozen_B_cumulative": FROZEN_B_CUMULATIVE,
        "headroom": THETA_25 - FROZEN_B_CUMULATIVE,
        "resolution": "if A==B use A; else if J1 and J2 map to the same frozen ID use it; elif both KEEP use KEEP; else A",
        "weights": WEIGHTS,
        "schedule": "occurrence * sql_amplification * disagreement_weight / reserved_pair; round-robin attributes",
        "no_repair_calls": True,
        "model": "openrouter/qwen/qwen-2.5-7b-instruct",
        "seed": SEED,
    }
    pre = {
        "select_freeze": freeze,
        "inventory": file_sha256(FROZEN_INV / "candidate_inventory.json"),
        "cards": sha([{k: pair_cards[cid][k] for k in ("cell_id", "j1_body", "j2_body", "j1_map", "j2_map")} for cid in schedule]),
        "permutations": sha(perms),
        "prompts": sha({"J1": JUDGE1, "J2": JUDGE2}),
        "policy": sha(policy),
        "schedule": sha(schedule),
        "reservations": sha(reserved_pair),
        "cohorts": dict(cohorts),
        "n_disagreement": len(schedule),
        "est_all_pairs": sum(reserved_pair[cid] for cid in schedule),
    }
    (OUT / "policy.json").write_text(json.dumps(policy, indent=2))
    (OUT / "cohorts_pre_spend.json").write_text(json.dumps({"cohorts": dict(cohorts), "disagreements": len(schedule), "kinds": {k: sum(1 for cid in schedule if cells[cid]["kind"] == k) for k in WEIGHTS}}, indent=2))
    (OUT / "pair_cards.json").write_text(json.dumps(pair_cards, indent=2))
    (OUT / "permutations.json").write_text(json.dumps(perms, indent=2))
    (OUT / "schedule.json").write_text(json.dumps(schedule, indent=2))
    (OUT / "reservations.json").write_text(json.dumps(reserved_pair, indent=2))
    (OUT / "prompts.json").write_text(json.dumps({"J1": JUDGE1, "J2": JUDGE2}, indent=2))
    (OUT / "pre_call_freeze.json").write_text(json.dumps(pre, indent=2))
    print(json.dumps({"cards_frozen": True, **pre, "est_all_pairs": pre["est_all_pairs"]}, indent=2), flush=True)

    from quwarts.core.ledger import BudgetExhausted, SpendRecord

    ledger = TokenLedger(theta=THETA_25, seed=SEED)
    journal_path = OUT / "response_journal.jsonl"
    done: set[str] = set()
    j1_choice: dict[str, str | None] = {}
    j2_choice: dict[str, str | None] = {}
    if journal_path.is_file():
        for line in journal_path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            done.add(row["cell_id"])
            j1_choice[row["cell_id"]] = row.get("j1_id")
            j2_choice[row["cell_id"]] = row.get("j2_id")
    if (OUT / "live_ledger.json").is_file():
        snap = json.loads((OUT / "live_ledger.json").read_text())
        ledger.spent = int(snap.get("spent") or 0)
        ledger.records = [SpendRecord(row["purpose"], row["tokens"], row.get("metadata") or {}) for row in snap.get("records") or []]
    else:
        ledger.spend(FROZEN_A, "frozen_pass_A")
        ledger.spend(FROZEN_B, "frozen_pass_B")
        if journal_path.is_file():
            for line in journal_path.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                for which in ("j1", "j2"):
                    actual = int((row.get(which) or {}).get("actual") or 0)
                    if actual:
                        ledger.spend(actual, f"pairwise_{which.upper()}", cell_id=row["cell_id"], attribute=row.get("attribute"), replay=True)

    def persist() -> None:
        (OUT / "live_ledger.json").write_text(json.dumps(ledger.snapshot(), indent=2, default=str))

    def one_judge(cell_id: str, which: str) -> dict[str, Any]:
        card = pair_cards[cell_id]
        instruction = JUDGE1 if which == "J1" else JUDGE2
        body = card["j1_body"] if which == "J1" else card["j2_body"]
        mapping = card["j1_map"] if which == "J1" else card["j2_map"]
        allowed = set(card["j1_allowed"] if which == "J1" else card["j2_allowed"])
        bundled = assemble_tools(SCHEMA, instruction + "\n\n" + body)
        _pt, reserved = reserved_of(bundled["user"], bundled["tools"])
        try:
            response = issue_call(bundled["request"])
        except Exception as exc:
            return {"label": None, "id": None, "raw": str(exc), "malformed": True, "actual": 0, "reserved": reserved, "reason": "call_error"}
        prompt, completion, actual = usage_of(response, reserved)
        try:
            ledger.spend(actual, f"pairwise_{which}", reserved=reserved, cell_id=cell_id, attribute=cells[cell_id]["attribute"])
        except BudgetExhausted:
            return {"label": None, "id": None, "raw": "", "malformed": False, "actual": 0, "reserved": reserved, "reason": "budget_exhausted"}
        parsed_tool = parse_tool(response)
        raw = parsed_tool["raw"]
        label = None
        if not parsed_tool["malformed"]:
            token = str(parsed_tool["parsed"].get("choice") or parsed_tool["parsed"].get("candidate_id") or "").strip().upper()
            if token == "KEEP_PLUMBING":
                token = "KEEP"
            if token in allowed:
                label = token
        if label is None:
            label = parse_judge(raw, allowed)
        mapped = mapping.get(label) if label else None
        return {
            "label": label,
            "id": mapped,
            "raw": raw,
            "malformed": parsed_tool["malformed"] or label is None,
            "actual": actual,
            "reserved": reserved,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "reason": "ok" if mapped else "invalid_or_malformed",
        }

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
        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(one_judge, cell_id, "J1")
            f2 = pool.submit(one_judge, cell_id, "J2")
            g1 = f1.result()
            g2 = f2.result()
        if g1.get("reason") == "budget_exhausted" or g2.get("reason") == "budget_exhausted":
            unscheduled.append(cell_id)
            continue
        j1_choice[cell_id] = g1.get("id")
        j2_choice[cell_id] = g2.get("id")
        scheduled_ok.append(cell_id)
        row = {
            "cell_id": cell_id,
            "attribute": cells[cell_id]["attribute"],
            "kind": cells[cell_id]["kind"],
            "A": cells[cell_id]["A"],
            "B": cells[cell_id]["B"],
            "j1": g1,
            "j2": g2,
            "j1_id": g1.get("id"),
            "j2_id": g2.get("id"),
            "spent_after": ledger.spent,
        }
        with _REAL_OPEN(journal_path, "a") as handle:
            handle.write(json.dumps(row, default=str) + "\n")
        persist()
        if (i + 1) % 50 == 0:
            print(json.dumps({"done": i + 1, "spent": ledger.spent, "remaining": THETA_25 - ledger.spent}, indent=2), flush=True)

    def resolve(cell_id: str, mode: str, completed: set[str] | None = None) -> str:
        cell = cells[cell_id]
        if cell["A"] == cell["B"]:
            return cell["A"]
        if completed is not None and cell_id not in completed:
            return cell["A"]
        j1 = j1_choice.get(cell_id)
        j2 = j2_choice.get(cell_id)
        if mode == "A":
            return cell["A"]
        if mode == "B":
            return cell["B"]
        if mode == "J1":
            return j1 if j1 else cell["A"]
        if mode == "J2":
            return j2 if j2 else cell["A"]
        if mode == "agree_replace":
            if j1 and j2 and j1 == j2 and cell["A"] != KEEP:
                return j1
            return cell["A"]
        if mode == "agree_add":
            if j1 and j2 and j1 == j2 and j1 != KEEP and cell["A"] == KEEP:
                return j1
            return cell["A"]
        if j1 and j2 and j1 == j2:
            return j1
        return cell["A"]

    completed = set(scheduled_ok)
    official = {cid: resolve(cid, "official", completed) for cid in cells}
    arms = {
        "A": {cid: resolve(cid, "A") for cid in cells},
        "B": {cid: resolve(cid, "B") for cid in cells},
        "judge1_A_fallback": {cid: resolve(cid, "J1", completed) for cid in cells},
        "judge2_A_fallback": {cid: resolve(cid, "J2", completed) for cid in cells},
        "agreement_replacements": {cid: resolve(cid, "agree_replace", completed) for cid in cells},
        "agreement_additions": {cid: resolve(cid, "agree_add", completed) for cid in cells},
        "official": official,
    }
    n_sched = max(len(schedule), 1)
    for frac, name in ((0.25, "prefix_25"), (0.50, "prefix_50"), (0.75, "prefix_75"), (1.0, "prefix_100")):
        cutoff = set(schedule[: int(frac * n_sched)])
        arms[name] = {cid: resolve(cid, "official", completed & cutoff) for cid in cells}

    parsed_out = {
        "A": {cid: cells[cid]["A"] for cid in cells},
        "B": {cid: cells[cid]["B"] for cid in cells},
        "J1": j1_choice,
        "J2": j2_choice,
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
        (OUT / "bags" / f"{name}.json").parent.mkdir(parents=True, exist_ok=True)
        (OUT / "bags" / f"{name}.json").write_text(json.dumps(mat["bags"], indent=2, default=str))
        (OUT / "fills" / f"{name}.json").parent.mkdir(parents=True, exist_ok=True)
        (OUT / "fills" / f"{name}.json").write_text(json.dumps(fills, indent=2, default=str))
        accepted = sum(1 for choice in mapping_choices.values() if choice and choice != KEEP)
        rebuild_match = mat["bag_sha256"] == mat2["bag_sha256"]
        if not rebuild_match:
            raise SystemExit(f"run invalid: rebuild mismatch for {name}")
        meta = {
            "accepted": accepted,
            "changed_cells": mat["overlay"].get("changed_cells"),
            "bag_sha256": mat["bag_sha256"],
            "rebuild_match": rebuild_match,
            "db_sha256": mat["db_sha256"],
        }
        (OUT / "arm_meta" / f"{name}.json").parent.mkdir(parents=True, exist_ok=True)
        (OUT / "arm_meta" / f"{name}.json").write_text(json.dumps(meta, indent=2))
        arm_hashes[name] = {"db": mat["db_sha256"], "bags": mat["bag_sha256"]}

    agree = disagree = agree_a = agree_b = agree_keep = parse_fail = 0
    for cell_id in completed:
        j1, j2 = j1_choice.get(cell_id), j2_choice.get(cell_id)
        if j1 is None or j2 is None:
            parse_fail += 1
            disagree += 1
            continue
        if j1 == j2:
            agree += 1
            if j1 == KEEP:
                agree_keep += 1
            elif j1 == cells[cell_id]["A"]:
                agree_a += 1
            elif j1 == cells[cell_id]["B"]:
                agree_b += 1
        else:
            disagree += 1
    purpose = {k: sum(r.tokens for r in ledger.records if r.purpose == k) for k in {r.purpose for r in ledger.records}}
    tokens_by_judge = {
        "J1": sum(r.tokens for r in ledger.records if r.purpose == "pairwise_J1"),
        "J2": sum(r.tokens for r in ledger.records if r.purpose == "pairwise_J2"),
    }
    tokens_by_attribute: dict[str, int] = defaultdict(int)
    for rec in ledger.records:
        if rec.purpose.startswith("pairwise_"):
            tokens_by_attribute[str((rec.metadata or {}).get("attribute") or "unknown")] += rec.tokens
    pre_gold = {
        "A_eq_B_candidate": cohorts.get("A=B candidate", 0),
        "A_eq_B_KEEP": cohorts.get("A=B KEEP", 0),
        "A_cand_B_cand": cohorts.get("A_cand_B_cand", 0),
        "A_cand_B_KEEP": cohorts.get("A_cand_B_keep", 0),
        "A_KEEP_B_cand": cohorts.get("A_keep_B_cand", 0),
        "scheduled_disagreements": len(schedule),
        "completed_pairs": len(completed),
        "unscheduled": len(unscheduled),
        "judge_agreement": agree,
        "agreed_A": agree_a,
        "agreed_B": agree_b,
        "agreed_KEEP": agree_keep,
        "judge_disagreement_fallback_A": disagree,
        "parse_failures": parse_fail,
        "tokens_by_purpose": purpose,
        "tokens_by_judge": tokens_by_judge,
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
        "gold_loaded": False,
        "forbidden_inaccessible": True,
    }
    (OUT / "generation_frozen.json").write_text(json.dumps(generation, indent=2))
    print(json.dumps({"frozen": True, **{k: pre_gold[k] for k in ("completed_pairs", "unscheduled", "causal_spent", "official_accepted", "judge_agreement", "judge_disagreement_fallback_A")}}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
