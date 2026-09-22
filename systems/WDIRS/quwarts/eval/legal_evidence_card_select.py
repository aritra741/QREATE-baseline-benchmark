"""Legal deterministic evidence-card selection arm. No gold. No reachability artifacts."""

from __future__ import annotations

import builtins
import hashlib
import json
import random
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
for path in (ROOT / "systems" / "WDIRS", ROOT, ROOT / "systems" / "docetl-main"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

BLOCKED_SUFFIXES = ("/quwarts_legal_shared_reachability", "/quwarts_legal_cost_aware_reachability")
_REAL_OPEN = builtins.open


def _blocked(path: Any) -> bool:
    text = str(path).replace("\\", "/")
    return any(token in text for token in BLOCKED_SUFFIXES)


def _guarded_open(file, *args, **kwargs):
    if _blocked(file):
        raise RuntimeError(f"reachability artifact access blocked: {file}")
    return _REAL_OPEN(file, *args, **kwargs)


def assert_no_reachability_access() -> None:
    for name, mod in list(sys.modules.items()):
        path = str(getattr(mod, "__file__", "") or "")
        if _blocked(path):
            raise SystemExit(f"run invalid: imported reachability module {name}")
    source = Path(__file__).read_text()
    needle = "quwarts_legal_" + "shared_reachability/"
    if needle in source:
        raise SystemExit("run invalid: selection runner references reachability assignments")


builtins.open = _guarded_open

from quwarts.core.amortized_select.config import COMPLETION_RESERVATION
from quwarts.core.amortized_select.prompt import assemble_tools
from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog
from quwarts.core.docetl_exact_message.adapter import DOCETL_SYSTEM
from quwarts.core.full_window_additive.overlay import apply_overlay, copy_plumbing, official_bag
from quwarts.core.ledger import BudgetExhausted, TokenLedger
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

FROZEN = ROOT / "results" / "quwarts_legal_multichannel_candidates"
PLUMBING = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
DOCETL_DIR = ROOT / "results" / "docetl_legal_case80"
SOURCE_DIR = ROOT / "source_data" / "Legal" / "legal_case"
SCHEMA_PATH = ROOT / "Query" / "Legal" / "Legal_attributes.json"
OUT = ROOT / "results" / "quwarts_legal_evidence_card_select"
THETA_25 = 12_610_011
THETA_5 = 2_522_002
THETA_10 = 5_044_004
KEEP = "KEEP_PLUMBING"
DET = {"surface", "normalized", "workload_label"}
SCHEMA = {"candidate_id": "str"}
CARD_LIMIT = 11_000 - COMPLETION_RESERVATION - 700
WORKERS = 6
TABLE = "legal"
SEED = 42

PASS_A = (
    "Select the listed candidate that most directly is the official attribute value for this entity.\n"
    "Check that the evidence is about the correct subject, the correct period, and the requested field.\n"
    "Distinguish a total from a component; a reported value from a citation, example, or page number; "
    "and a current status from a historical statement.\n"
    "You may choose KEEP_PLUMBING if the card does not determine the attribute.\n"
    "Output only one listed candidate_id or KEEP_PLUMBING."
)
PASS_B = (
    "Eliminate listed candidates that have the wrong entity or party, the wrong date or reporting period, "
    "the wrong semantic role, the wrong unit or scale, are heading or example text rather than a value, "
    "or have insufficient evidence.\n"
    "After elimination, output exactly one surviving listed candidate_id, or KEEP_PLUMBING if none survive.\n"
    "Do not explain. Output only the identifier."
)
PASS_C = (
    "From the evidence card, determine the requested attribute value for this entity.\n"
    "Then map that conclusion to the closest listed candidate_id. Do not invent a value that is not listed.\n"
    "If the evidence does not determine a listed value, output KEEP_PLUMBING.\n"
    "Output only one listed candidate_id or KEEP_PLUMBING."
)
ADJ_PROMPT = (
    "Independent selectors disagreed. Compare only the listed options against the evidence card.\n"
    "Vote counts are provided without selector identity. Ignore majority as authority; use the evidence.\n"
    "Output one listed candidate_id or KEEP_PLUMBING."
)
REPAIR = (
    "Repair the response so it is exactly one allowed identifier.\n"
    "Allowed: {allowed}\n"
    "Output only the identifier. No explanation.\n"
    "Malformed output:\n{raw}"
)


def sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def channel_of(item: dict[str, Any]) -> str:
    raw = str(item.get("channel") or item.get("derivation") or "surface")
    return "composed" if raw.startswith("composed") else raw


def clip(text: Any, n: int = 72) -> str:
    body = " ".join(str(text or "").split())
    return body if len(body) <= n else body[: n - 1].rstrip() + "…"


CHAN = {"surface": "S", "normalized": "N", "workload_label": "L"}


def load_plumbing_rows() -> list[dict[str, Any]]:
    import sqlite3

    conn = sqlite3.connect(f"file:{PLUMBING}?mode=ro", uri=True)
    cols = [row[1] for row in conn.execute(f'PRAGMA table_info("{TABLE}")')]
    rows = [dict(zip(cols, rec)) for rec in conn.execute(f'SELECT * FROM "{TABLE}"')]
    conn.close()
    return rows


def parse_choice(parsed: dict[str, Any], allowed: list[str]) -> str | None:
    raw = parsed.get("candidate_id")
    if raw is None:
        raw = parsed.get("id") or parsed.get("choice")
    token = str(raw or "").strip()
    if token in set(allowed):
        return token
    return None


def candidate_line(item: dict[str, Any], spec_name: str, source: str) -> str:
    ch = channel_of(item)
    val = clip(item.get("normalized"), 72)
    spans = item.get("evidence_spans") or []
    snippet = ""
    if spans:
        snippet = str((spans[0] or {}).get("text") or "")
    if not snippet:
        snippet = str(item.get("local_text") or item.get("raw_span") or "")
    ev = clip(snippet, 80)
    parts = [str(item.get("id")), CHAN.get(ch, ch), f"`{val}`"]
    if item.get("period"):
        parts.append(f"p={item.get('period')}")
    if item.get("unit"):
        parts.append(f"u={item.get('unit')}")
    if item.get("component_scope"):
        parts.append(f"c={item.get('component_scope')}")
    hd = clip(item.get("heading") or item.get("table_title") or item.get("column_header"), 36)
    if hd and hd != "document":
        parts.append(f"hd={hd}")
    trace = [str(x) for x in (item.get("normalization_trace") or [])[:2] if x]
    if trace:
        parts.append("tr=" + ",".join(trace))
    if ev and ev != val:
        parts.append(f"ev={ev}")
    return " ".join(parts)


def label_pack(item: dict[str, Any], spec, document_id: str, source: str, layouts) -> str:
    if channel_of(item) != "workload_label":
        return ""
    spans = item.get("evidence_spans") or []
    if spans:
        texts = [str((row or {}).get("text") or "") for row in spans[:2]]
        return ""
    terms = {spec.name: list(dict.fromkeys(field_terms(spec.name) + field_terms(spec.official_description) + field_terms(str(item.get("normalized") or ""))))}
    packed = pack_c1(layouts, terms, 400)
    return f"{item.get('id')} L-pack meaning={clip(item.get('normalized'), 40)} src={clip(packed.get('text') or '', 140)}"


def build_card(rec: dict[str, Any], spec, source: str, layouts, heading: str) -> dict[str, Any]:
    det = [item for item in rec.get("candidates") or [] if channel_of(item) in DET and not _null(item.get("normalized"))]
    keep_line = f"{KEEP}: keep existing NULL"
    lines = [candidate_line(item, spec.name, source) for item in det]
    packs = [label_pack(item, spec, rec["document_id"], source, layouts) for item in det if channel_of(item) == "workload_label"]
    packs = [p for p in packs if p]
    header = (
        f"cell={rec['cell_id']} attr={spec.name} type={spec.dtype}/{spec.sql_type} card=1\n"
        f"desc={spec.official_description}\n"
        f"entity={rec['document_id']} heading={clip(heading, 60)}\n"
        "cands:\n"
    )
    body = header + "\n".join(lines + ([keep_line] if lines or True else []))
    if packs:
        body += "\nWorkload-label notes:\n" + "\n".join(p for p in packs if p)
    pruned = []
    listed = [str(item.get("id")) for item in det] + [KEEP]
    if count_tokens(DOCETL_SYSTEM + PASS_A + "\n" + body) > CARD_LIMIT:
        wl = [item for item in det if channel_of(item) == "workload_label"]
        nm = [item for item in det if channel_of(item) == "normalized"]
        surf = sorted([item for item in det if channel_of(item) == "surface"], key=lambda item: (-float(item.get("score") or 0.0), int(item.get("start") or 0), str(item.get("id"))))
        kept_surf = []
        for item in surf:
            trial = wl + nm + kept_surf + [item]
            trial_lines = [candidate_line(c, spec.name, source) for c in trial]
            trial_body = header + "\n".join(trial_lines + [keep_line])
            if count_tokens(DOCETL_SYSTEM + PASS_A + "\n" + trial_body) <= CARD_LIMIT:
                kept_surf.append(item)
            else:
                pruned.append({"id": item.get("id"), "channel": "surface", "reason": "card_over_effective_input", "rule": "drop_lowest_ranked_surface_after_keeping_all_workload_and_normalized"})
        det = wl + nm + kept_surf
        lines = [candidate_line(item, spec.name, source) for item in det]
        body = header + "\n".join(lines + [keep_line])
        listed = [str(item.get("id")) for item in det] + [KEEP]
    return {
        "cell_id": rec["cell_id"],
        "entity_id": rec["entity_id"],
        "document_id": rec["document_id"],
        "attribute": rec["attribute"],
        "n_candidates": len(det),
        "listed_ids": listed,
        "body": body,
        "pruned": pruned,
        "channels": dict(Counter(channel_of(item) for item in det)),
    }


def schedule_cells(cards: list[dict[str, Any]], records, reserved: dict[str, int]) -> list[str]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in cards:
        rec = records[card["attribute"]]
        amp = 1 + sum(int(rec.roles.get(role) or 0) for role in ("WHERE", "CASE", "GROUP BY", "aggregate input", "HAVING"))
        cost = max(reserved[card["cell_id"]], 1)
        priority = (rec.occurrence_count * amp * max(card["n_candidates"], 1)) / cost
        groups[card["attribute"]].append({**card, "priority": priority})
    for name in groups:
        groups[name].sort(key=lambda row: (-row["priority"], row["document_id"], row["attribute"], row["cell_id"]))
    order = []
    attrs = sorted(groups)
    indexes = {name: 0 for name in attrs}
    while True:
        progressed = False
        for name in attrs:
            i = indexes[name]
            if i < len(groups[name]):
                order.append(groups[name][i]["cell_id"])
                indexes[name] = i + 1
                progressed = True
        if not progressed:
            break
    return order


def charge(ledger: TokenLedger, purpose: str, reserved: int, response: Any, meta: dict[str, Any]) -> tuple[int, int, int] | None:
    prompt, completion, actual = usage_of(response, reserved)
    if ledger.spent + actual > ledger.theta:
        return None
    ledger.spend(actual, purpose, reserved=reserved, **meta)
    return prompt, completion, actual


def run_one(card: dict[str, Any], instruction: str, perm: list[str], ledger: TokenLedger, purpose: str, lock: threading.Lock) -> dict[str, Any]:
    listed = list(perm)
    body = card["body"]
    # present candidates in permuted order, KEEP last
    user = instruction + "\n\n" + body + "\nOrder: " + ", ".join(listed)
    bundled = assemble_tools(SCHEMA, user)
    _pt, reserved = reserved_of(bundled["user"], bundled["tools"])
    with lock:
        if ledger.spent + reserved > ledger.theta:
            return {"choice": None, "malformed": False, "repaired": False, "actual": 0, "reserved": reserved, "raw": "", "reason": "budget_unattempted", "attempted": False}
    try:
        response = issue_call(bundled["request"])
    except Exception as exc:
        return {"choice": None, "malformed": True, "repaired": False, "actual": 0, "reserved": reserved, "raw": str(exc), "reason": "call_error", "attempted": True}
    used = charge(ledger, purpose, reserved, response, {"cell_id": card["cell_id"], "attribute": card["attribute"]})
    if used is None:
        return {"choice": None, "malformed": False, "repaired": False, "actual": 0, "reserved": reserved, "raw": "", "reason": "budget_exhausted", "attempted": True}
    parsed = parse_tool(response)
    repaired = False
    choice = parse_choice(parsed["parsed"], listed) if not parsed["malformed"] else None
    raw = parsed["raw"]
    actual = used[2]
    if parsed["malformed"] or choice is None:
        repair_user = REPAIR.format(allowed=", ".join(listed), raw=(raw or "")[:400])
        repair = assemble_tools(SCHEMA, repair_user)
        _rp, r_reserved = reserved_of(repair["user"], repair["tools"])
        with lock:
            can_repair = ledger.spent + r_reserved <= ledger.theta
        if can_repair:
            try:
                r_resp = issue_call(repair["request"])
            except Exception:
                r_resp = None
            if r_resp is not None:
                r_used = charge(ledger, purpose + "_repair", r_reserved, r_resp, {"cell_id": card["cell_id"], "stage": "repair"})
                if r_used is not None:
                    repaired = True
                    actual += r_used[2]
                    r_parsed = parse_tool(r_resp)
                    raw = r_parsed["raw"]
                    choice = parse_choice(r_parsed["parsed"], listed) if not r_parsed["malformed"] else None
    return {"choice": choice, "malformed": parsed["malformed"], "repaired": repaired, "actual": actual, "reserved": reserved, "raw": raw, "reason": "ok" if choice else "invalid_or_malformed", "attempted": True, "prompt_tokens": used[0], "completion_tokens": used[1]}


def majority(votes: list[str | None]) -> tuple[str | None, str]:
    present = [v for v in votes if v]
    if not present:
        return None, "all_missing"
    counts = Counter(present)
    top, n = counts.most_common(1)[0]
    if n >= 2:
        return top, "majority"
    if len(present) == 1:
        return None, "single_abstention"
    return None, "three_way"


def materialize(dest: Path, fills: dict[str, dict[str, Any]], mapping, statements, predicates, query_ids) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    copy_plumbing(PLUMBING, dest)
    overlay = apply_overlay(dest, fills, mapping, table=TABLE)
    bags = {qid: official_bag(dest, statements[qid], predicates, qid) for qid in query_ids}
    return {"overlay": overlay, "bags": bags, "bag_sha256": _hash(bags), "db_sha256": file_sha256(dest)}


def fills_from_choices(choices: dict[str, str | None], cards_by: dict[str, dict[str, Any]], by_id: dict[tuple[str, str, str], Any]) -> dict[str, dict[str, Any]]:
    fills: dict[str, dict[str, Any]] = defaultdict(dict)
    for cell_id, cid in choices.items():
        if not cid or cid == KEEP:
            continue
        card = cards_by[cell_id]
        item = by_id.get((card["document_id"], card["attribute"], cid))
        if item is None or _null(item.get("normalized")):
            continue
        fills[card["document_id"]][card["attribute"]] = item.get("normalized")
    return dict(fills)


def main() -> int:
    assert_no_reachability_access()
    OUT.mkdir(parents=True, exist_ok=True)
    inventory = json.loads((FROZEN / "candidate_inventory.json").read_text())
    manifest = json.loads((DOCETL_DIR / "query_manifest.json").read_text())
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    records = compile_attribute_inventory(statements)
    specs = compile_specs(load_official_catalog(SCHEMA_PATH), records)
    plumbing_rows = load_plumbing_rows()
    mapping = mapping_from_rows(plumbing_rows)
    plumbing_by = {str(row.get("__entity_id")): row for row in plumbing_rows}
    texts = {path.stem: path.read_text(encoding="utf-8", errors="replace") for path in sorted(SOURCE_DIR.glob("*.txt"))}
    layouts = {doc: parse_layout(doc, text) for doc, text in texts.items()}
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))

    cells = []
    by_id = {}
    for rec in inventory:
        prow = plumbing_by[rec["entity_id"]]
        if prow.get(rec["attribute"]) not in (None, ""):
            continue
        det = []
        for item in rec.get("all_candidates") or rec.get("candidates") or []:
            if channel_of(item) in DET and not _null(item.get("normalized")):
                det.append(item)
                by_id[(rec["document_id"], rec["attribute"], str(item.get("id")))] = item
        heading = ""
        for block in layouts.get(rec["document_id"]) or []:
            if getattr(block, "kind", "") == "section_heading":
                heading = str(getattr(block, "heading", "") or getattr(block, "text", ""))
                break
        cell_id = hashlib.sha256(f"{rec['entity_id']}:{rec['attribute']}".encode()).hexdigest()[:16]
        cells.append({**rec, "candidates": det, "cell_id": cell_id, "heading": heading})

    cards = []
    prune_log = []
    for rec in cells:
        spec = specs[rec["attribute"]]
        card = build_card(rec, spec, texts.get(rec["document_id"], ""), layouts.get(rec["document_id"]) or [], rec["heading"])
        cards.append(card)
        prune_log.extend([{**row, "cell_id": card["cell_id"], "attribute": rec["attribute"]} for row in card["pruned"]])
    cards_by = {card["cell_id"]: card for card in cards}
    reserved = {}
    for card in cards:
        bundled = assemble_tools(SCHEMA, PASS_A + "\n\n" + card["body"])
        _pt, reserved[card["cell_id"]] = reserved_of(bundled["user"], bundled["tools"])
    schedule = schedule_cells(cards, records, reserved)
    selectable = [cid for cid in schedule if cards_by[cid]["n_candidates"] > 0]
    auto_keep = [cid for cid in schedule if cards_by[cid]["n_candidates"] == 0]

    perms = {"A": {}, "B": {}, "C": {}}
    for pass_i, name in enumerate(("A", "B", "C")):
        for idx, cell_id in enumerate(schedule):
            rng = random.Random(1009 + 97 * pass_i + 13 * idx)
            ids = [cid for cid in cards_by[cell_id]["listed_ids"] if cid != KEEP]
            rng.shuffle(ids)
            perms[name][cell_id] = ids + [KEEP]

    policy = {
        "theta_25": THETA_25,
        "theta_5": THETA_5,
        "theta_10": THETA_10,
        "channels": sorted(DET) + [KEEP],
        "card_limit": CARD_LIMIT,
        "prune_rule": "keep_all_workload_labels_and_normalized_then_highest_score_surface",
        "schedule": "occurrence * sql_amplification * ambiguity / reserved; round-robin attributes",
        "workers": WORKERS,
        "seed": SEED,
        "model": "openrouter/qwen/qwen-2.5-7b-instruct",
    }
    freeze_pre = {
        "query_manifest": _hash(manifest),
        "inventory": file_sha256(FROZEN / "candidate_inventory.json"),
        "cards": sha([{k: card[k] for k in ("cell_id", "entity_id", "attribute", "listed_ids", "body", "pruned")} for card in cards]),
        "policy": sha(policy),
        "permutations": sha(perms),
        "prompts": sha({"A": PASS_A, "B": PASS_B, "C": PASS_C, "ADJ": ADJ_PROMPT, "REPAIR": REPAIR}),
        "schedule": sha(schedule),
    }
    (OUT / "policy.json").write_text(json.dumps(policy, indent=2))
    (OUT / "cards.json").write_text(json.dumps(cards, indent=2, default=str))
    (OUT / "card_pruning.json").write_text(json.dumps(prune_log, indent=2))
    (OUT / "permutations.json").write_text(json.dumps(perms, indent=2))
    (OUT / "schedule.json").write_text(json.dumps(schedule, indent=2))
    (OUT / "prompts.json").write_text(json.dumps({"A": PASS_A, "B": PASS_B, "C": PASS_C, "ADJ": ADJ_PROMPT, "REPAIR": REPAIR}, indent=2))
    (OUT / "pre_call_freeze.json").write_text(json.dumps(freeze_pre, indent=2))
    print(json.dumps({"cards_frozen": True, "n_cards": len(cards), "selectable": len(selectable), "auto_keep": len(auto_keep), "pruned": len(prune_log), "est_pass_a": sum(reserved[c] for c in selectable)}, indent=2), flush=True)

    journal_path = OUT / "response_journal.jsonl"
    done: set[tuple[str, str]] = set()
    if journal_path.is_file():
        for line in journal_path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                done.add((row["stage"], row["cell_id"]))

    ledger = TokenLedger(theta=THETA_25, seed=SEED)
    if (OUT / "live_ledger.json").is_file():
        snap = json.loads((OUT / "live_ledger.json").read_text())
        ledger.spent = int(snap.get("spent") or 0)
        from quwarts.core.ledger import SpendRecord
        ledger.records = [SpendRecord(row["purpose"], row["tokens"], row.get("metadata") or {}) for row in snap.get("records") or []]

    lock = threading.Lock()

    def persist_ledger() -> None:
        (OUT / "live_ledger.json").write_text(json.dumps(ledger.snapshot(), indent=2, default=str))

    decisions: dict[str, dict[str, str | None]] = {"A": {}, "B": {}, "C": {}}
    if journal_path.is_file():
        for line in journal_path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row["stage"] in decisions:
                decisions[row["stage"]][row["cell_id"]] = row.get("choice")

    def append_journal(row: dict[str, Any]) -> None:
        with _REAL_OPEN(journal_path, "a") as handle:
            handle.write(json.dumps(row, default=str) + "\n")

    def run_pass(name: str, instruction: str, cell_ids: list[str]) -> None:
        pending = [cid for cid in cell_ids if (name, cid) not in done]
        print(json.dumps({"pass_start": name, "remaining": len(pending), "spent": ledger.spent}, indent=2), flush=True)

        def work(cell_id: str) -> dict[str, Any]:
            card = cards_by[cell_id]
            got = run_one(card, instruction, perms[name][cell_id], ledger, f"pass_{name}", lock)
            return {"stage": name, "cell_id": cell_id, "entity_id": card["entity_id"], "document_id": card["document_id"], "attribute": card["attribute"], "permutation": perms[name][cell_id], **got, "spent_after": ledger.spent}

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            inflight: dict[str, Future] = {}
            submit_i = 0
            complete_i = 0
            while complete_i < len(pending):
                while submit_i < len(pending) and len(inflight) < WORKERS:
                    cid = pending[submit_i]
                    inflight[cid] = pool.submit(work, cid)
                    submit_i += 1
                next_id = pending[complete_i]
                while next_id not in inflight or not inflight[next_id].done():
                    time.sleep(0.05)
                    if ledger.spent >= THETA_25 and next_id not in inflight:
                        break
                if next_id in inflight:
                    row = inflight.pop(next_id).result()
                    append_journal(row)
                    decisions[name][next_id] = row.get("choice")
                    done.add((name, next_id))
                    persist_ledger()
                    complete_i += 1
                    if complete_i % 50 == 0:
                        print(json.dumps({"pass": name, "done": complete_i, "spent": ledger.spent}, indent=2), flush=True)
                else:
                    break

    run_pass("A", PASS_A, selectable)
    run_pass("B", PASS_B, selectable)
    run_pass("C", PASS_C, selectable)

    conflicts = []
    majority_choice: dict[str, str | None] = {}
    consensus = {}
    for cell_id in schedule:
        votes = [decisions["A"].get(cell_id), decisions["B"].get(cell_id), decisions["C"].get(cell_id)]
        winner, kind = majority(votes)
        majority_choice[cell_id] = winner if winner else KEEP
        consensus[cell_id] = {"votes": votes, "kind": kind, "winner": majority_choice[cell_id]}
        if kind == "three_way" or (kind == "single_abstention" and sum(v is not None for v in votes) >= 2 and len(set(v for v in votes if v)) > 1):
            conflicts.append(cell_id)
        if kind == "three_way":
            pass
    # three-way only: all three present and all different
    conflicts = []
    for cell_id in schedule:
        votes = [decisions["A"].get(cell_id), decisions["B"].get(cell_id), decisions["C"].get(cell_id)]
        present = [v for v in votes if v]
        if len(present) >= 2 and len(set(present)) >= 2 and Counter(present).most_common(1)[0][1] < 2:
            conflicts.append(cell_id)

    adj_choice: dict[str, str | None] = {}
    print(json.dumps({"adjudicate_start": len(conflicts), "spent": ledger.spent}, indent=2), flush=True)
    for cell_id in conflicts:
        if ("ADJ", cell_id) in done:
            continue
        card = cards_by[cell_id]
        votes = [decisions["A"].get(cell_id), decisions["B"].get(cell_id), decisions["C"].get(cell_id)]
        options = []
        for cid in dict.fromkeys([v for v in votes if v] + [KEEP]):
            options.append(cid)
        user = ADJ_PROMPT + f"\nVote counts: {dict(Counter(v for v in votes if v))}\nListed options: {options}\n\n" + card["body"]
        got = run_one({**card, "body": user}, ADJ_PROMPT, options, ledger, "adjudicate", lock)
        row = {"stage": "ADJ", "cell_id": cell_id, "entity_id": card["entity_id"], "document_id": card["document_id"], "attribute": card["attribute"], "permutation": options, **got, "spent_after": ledger.spent}
        append_journal(row)
        adj_choice[cell_id] = got.get("choice") if got.get("choice") in set(options) else KEEP
        done.add(("ADJ", cell_id))
        persist_ledger()

    official: dict[str, str | None] = {}
    for cell_id in schedule:
        if cell_id in adj_choice:
            official[cell_id] = adj_choice[cell_id] or KEEP
        else:
            official[cell_id] = majority_choice.get(cell_id) or KEEP
    for cell_id in auto_keep:
        official[cell_id] = KEEP
        majority_choice[cell_id] = KEEP

    parsed = {
        "A": decisions["A"],
        "B": decisions["B"],
        "C": decisions["C"],
        "majority": majority_choice,
        "adjudication": adj_choice,
        "official": official,
        "consensus": consensus,
    }
    (OUT / "parsed_decisions.json").write_text(json.dumps(parsed, indent=2, default=str))

    def choices_at_spent(cap: int) -> dict[str, str | None]:
        a: dict[str, str | None] = {}
        b: dict[str, str | None] = {}
        c: dict[str, str | None] = {}
        adj: dict[str, str | None] = {}
        if journal_path.is_file():
            for line in journal_path.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if int(row.get("spent_after") or 0) > cap:
                    break
                if row.get("attempted") is False:
                    continue
                stage = row["stage"]
                if stage == "A":
                    a[row["cell_id"]] = row.get("choice")
                elif stage == "B":
                    b[row["cell_id"]] = row.get("choice")
                elif stage == "C":
                    c[row["cell_id"]] = row.get("choice")
                elif stage == "ADJ":
                    adj[row["cell_id"]] = row.get("choice")
        out = {}
        for cell_id in schedule:
            winner, kind = majority([a.get(cell_id), b.get(cell_id), c.get(cell_id)])
            if winner:
                out[cell_id] = winner
            elif cell_id in adj and a.get(cell_id) and b.get(cell_id) and c.get(cell_id):
                out[cell_id] = adj[cell_id] or KEEP
            else:
                out[cell_id] = KEEP
        return out

    arms = {
        "pass_a": {cid: decisions["A"].get(cid) or KEEP for cid in schedule},
        "pass_b": {cid: decisions["B"].get(cid) or KEEP for cid in schedule},
        "pass_c": {cid: decisions["C"].get(cid) or KEEP for cid in schedule},
        "majority": majority_choice,
        "adjudication_only": {cid: (adj_choice.get(cid) or KEEP) if cid in adj_choice else KEEP for cid in schedule},
        "official": official,
        "theta_5": choices_at_spent(THETA_5),
        "theta_10": choices_at_spent(THETA_10),
        "theta_25": official,
    }
    for name, mapping_choices in arms.items():
        dest = OUT / "databases" / f"{name}.db"
        mat = materialize(dest, fills_from_choices(mapping_choices, cards_by, by_id), mapping, statements, predicates, query_ids)
        (OUT / "bags" / f"{name}.json").parent.mkdir(parents=True, exist_ok=True)
        (OUT / "bags" / f"{name}.json").write_text(json.dumps(mat["bags"], indent=2, default=str))
        (OUT / "fills" / f"{name}.json").parent.mkdir(parents=True, exist_ok=True)
        (OUT / "fills" / f"{name}.json").write_text(json.dumps(fills_from_choices(mapping_choices, cards_by, by_id), indent=2, default=str))
        (OUT / "arm_meta" / f"{name}.json").parent.mkdir(parents=True, exist_ok=True)
        accepted = sum(1 for cid, choice in mapping_choices.items() if choice and choice != KEEP)
        (OUT / "arm_meta" / f"{name}.json").write_text(json.dumps({"accepted": accepted, "changed_cells": mat["overlay"].get("changed_cells"), "bag_sha256": mat["bag_sha256"], "db_sha256": mat["db_sha256"]}, indent=2))

    kinds = Counter(row["kind"] for row in consensus.values())
    pre = {
        "selectable_cells": len(selectable),
        "auto_keep_cells": len(auto_keep),
        "candidate_count": {"min": min((c["n_candidates"] for c in cards), default=0), "max": max((c["n_candidates"] for c in cards), default=0), "mean": sum(c["n_candidates"] for c in cards) / max(len(cards), 1)},
        "cards_pruned": len(prune_log),
        "tokens_estimated_pass_a": sum(reserved[c] for c in selectable),
        "tokens_spent": ledger.spent,
        "spent_by_purpose": dict(Counter((row.purpose, row.tokens)[0] and row.purpose for row in ledger.records)),
        "purpose_tokens": {k: sum(r.tokens for r in ledger.records if r.purpose == k) for k in {r.purpose for r in ledger.records}},
        "completed_A": sum(1 for cid in selectable if decisions["A"].get(cid) is not None or ( "A", cid) in done),
        "completed_B": sum(1 for cid in selectable if ("B", cid) in done),
        "completed_C": sum(1 for cid in selectable if ("C", cid) in done),
        "consensus": dict(kinds),
        "unanimous": sum(1 for row in consensus.values() if len(set(v for v in row["votes"] if v)) == 1 and sum(v is not None for v in row["votes"]) == 3),
        "two_of_three": sum(1 for row in consensus.values() if row["kind"] == "majority" and len(set(v for v in row["votes"] if v)) > 1),
        "majority_keep": sum(1 for cid, choice in majority_choice.items() if choice == KEEP),
        "three_way_conflicts": len(conflicts),
        "adjudicator_candidate": sum(1 for cid, choice in adj_choice.items() if choice and choice != KEEP),
        "adjudicator_keep": sum(1 for cid, choice in adj_choice.items() if (choice or KEEP) == KEEP),
        "malformed": sum(1 for line in journal_path.read_text().splitlines() if line.strip() and json.loads(line).get("malformed")),
        "repairs": sum(1 for line in journal_path.read_text().splitlines() if line.strip() and json.loads(line).get("repaired")),
        "official_accepted": sum(1 for choice in official.values() if choice and choice != KEEP),
        "reachability_inaccessible": True,
    }
    (OUT / "pre_gold.json").write_text(json.dumps(pre, indent=2, default=str))
    (OUT / "theta25_ledger.json").write_text(json.dumps(ledger.snapshot(), indent=2, default=str))
    freeze = {
        **freeze_pre,
        "journal": file_sha256(journal_path) if journal_path.is_file() else None,
        "parsed": sha(parsed),
        "ledger": ledger.fingerprint(),
        "spent": ledger.spent,
        "official_accepted": pre["official_accepted"],
        "reachability_inaccessible": True,
        "gold_loaded": False,
    }
    (OUT / "generation_frozen.json").write_text(json.dumps(freeze, indent=2))
    print(json.dumps({"frozen": True, "spent": ledger.spent, "accepted": pre["official_accepted"], "conflicts": len(conflicts)}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
