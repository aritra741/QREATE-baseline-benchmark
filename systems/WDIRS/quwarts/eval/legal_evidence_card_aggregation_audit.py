"""Zero-Qwen aggregation audit over frozen Legal evidence-card decisions."""

from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

logging.getLogger().setLevel(logging.ERROR)

ROOT = Path(__file__).resolve().parents[4]
for path in (ROOT / "systems" / "WDIRS", ROOT, ROOT / "systems" / "docetl-main"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from quwarts.core.candidate_select.schema_spec import compile_specs, load_official_catalog
from quwarts.core.full_window_additive.overlay import apply_overlay, copy_plumbing, official_bag
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.shared_bundle.inventory import compile_attribute_inventory
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.eval.finan_amortized_select_arm import mapping_from_rows, _hash, _null
from quwarts.eval.legal_coverage_transfer import (
    DOCETL_DIR,
    DOCETL_F1,
    DOCETL_F2,
    DOCETL_PRODUCT,
    DOCETL_TOKENS,
    PLUMBING,
    SCHEMA_PATH,
    TABLE,
    gold_index,
    gold_value,
    load_plumbing_rows,
    materialize_fills,
    score_db,
)
from quwarts.eval.legal_multichannel_availability_audit import RowEvaluator, channel_of, exact_gold, observational_match
from quwarts.eval.legal_shared_reachability_search import (
    ANNEAL_SEEDS,
    KEEP_ID,
    RANDOM_SEEDS,
    Cell,
    Choice,
    SharedEngine,
    sha,
    typed_key,
)
from quwarts.experiments.synthesize_case80 import gold_name
from diagnostics.run_config_grid import load_ground_truth

FROZEN_SELECT = ROOT / "results" / "quwarts_legal_evidence_card_select"
FROZEN_INV = ROOT / "results" / "quwarts_legal_multichannel_candidates"
OUT = ROOT / "results" / "quwarts_legal_evidence_card_aggregation_audit"
KEEP = "KEEP_PLUMBING"

PASS_A = 3_452_863 + 15_679
PASS_B = 3_376_185 + 646_361
PASS_C = 3_359_962 + 22_862
ADJ = 1_178_367 + 3_887
COST = {"A": PASS_A, "B": PASS_B, "C": PASS_C, "J": ADJ}


def sha_text(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def is_cand(token: str | None, listed: set[str]) -> bool:
    return bool(token) and token != KEEP and token in listed


def token_ok(token: str | None, listed: set[str]) -> bool:
    return token == KEEP or is_cand(token, listed)


def find_ids(raw: str, listed: list[str]) -> list[str]:
    found = []
    for cid in sorted(set(listed + [KEEP]), key=len, reverse=True):
        if re.search(r"(?<![A-Za-z0-9_])" + re.escape(cid) + r"(?![A-Za-z0-9_])", raw or ""):
            found.append(cid)
    return found


def causal(sources: set[str]) -> int:
    if "J" in sources:
        return PASS_A + PASS_B + PASS_C + ADJ
    if "C" in sources:
        return PASS_A + PASS_B + PASS_C
    if "B" in sources:
        return PASS_A + PASS_B
    if "A" in sources:
        return PASS_A
    return 0


RULE_DEFS: dict[str, dict[str, Any]] = {
    "A": {"family": "single", "sources": ["A"], "text": "Use stored Pass A if valid, else KEEP_PLUMBING."},
    "B": {"family": "single", "sources": ["B"], "text": "Use stored Pass B if valid, else KEEP_PLUMBING."},
    "C": {"family": "single", "sources": ["C"], "text": "Use stored Pass C if valid, else KEEP_PLUMBING."},
    "J_only": {"family": "single", "sources": ["A", "B", "C", "J"], "text": "Use stored adjudicator J if the cell was adjudicated and J is a valid candidate; otherwise KEEP_PLUMBING."},
    "majority_original": {
        "family": "original",
        "sources": ["A", "B", "C"],
        "text": "Among present A/B/C votes (KEEP counts as a vote; missing is abstention), accept an identifier with at least two votes; otherwise KEEP_PLUMBING.",
    },
    "official_original": {
        "family": "original",
        "sources": ["A", "B", "C", "J"],
        "text": "If the cell was originally adjudicated, use valid J else KEEP. Otherwise use majority_original.",
    },
    "A_backbone": {"family": "a_backbone", "sources": ["A"], "text": "Use A exactly (valid candidate or KEEP). Invalid A becomes KEEP."},
    "A_fill_BC": {
        "family": "a_backbone",
        "sources": ["A", "B", "C"],
        "text": "If A is a candidate, use A. Else if B == C and that value is a non-KEEP candidate, use B. Else KEEP.",
    },
    "A_fill_J": {
        "family": "a_backbone",
        "sources": ["A", "B", "C", "J"],
        "text": "If A is a candidate, use A. Else if J is a candidate, use J. Else KEEP.",
    },
    "A_fill_BC_then_J": {
        "family": "a_backbone",
        "sources": ["A", "B", "C", "J"],
        "text": "If A is a candidate, use A. Else if B == C and non-KEEP candidate, use B. Else if J is a candidate, use J. Else KEEP.",
    },
    "A_replace_BC": {
        "family": "a_backbone",
        "sources": ["A", "B", "C"],
        "text": "If B == C and non-KEEP candidate, use B. Else use A (or KEEP if A invalid).",
    },
    "A_replace_J": {
        "family": "a_backbone",
        "sources": ["A", "B", "C", "J"],
        "text": "If J is a candidate, use J. Else use A.",
    },
    "A_replace_BC_then_J": {
        "family": "a_backbone",
        "sources": ["A", "B", "C", "J"],
        "text": "If B == C and non-KEEP candidate, use B. Else if J is a candidate, use J. Else use A.",
    },
    "A_veto_double_keep": {
        "family": "a_backbone",
        "sources": ["A", "B", "C"],
        "text": "If B == KEEP and C == KEEP, KEEP. Else use A.",
    },
    "nonkeep_plurality": {
        "family": "consensus",
        "sources": ["A", "B", "C"],
        "text": "Ignore KEEP votes. If a candidate has at least two of the remaining votes, use it. Else KEEP.",
    },
    "nonkeep_plurality_A_tiebreak": {
        "family": "consensus",
        "sources": ["A", "B", "C"],
        "text": "Ignore KEEP votes. Choose the unique candidate with strictly most votes. On a candidate tie, use A if A is among the tied candidates. Else KEEP.",
    },
    "any_two_then_A": {
        "family": "consensus",
        "sources": ["A", "B", "C"],
        "text": "If any candidate (KEEP ignored) has two votes, use it. Else use A.",
    },
    "J_on_three_way_only": {
        "family": "consensus",
        "sources": ["A", "B", "C", "J"],
        "text": "If a candidate has two A/B/C votes, use it. Else if A, B, and C are three distinct present outcomes and J is a candidate, use J. Else use A.",
    },
    "prio_A_J_C_B": {"family": "priority", "sources": ["A", "B", "C", "J"], "text": "First non-KEEP valid candidate in order A, J, C, B, else KEEP."},
    "prio_A_C_B_J": {"family": "priority", "sources": ["A", "B", "C", "J"], "text": "First non-KEEP valid candidate in order A, C, B, J, else KEEP."},
    "prio_J_A_C_B": {"family": "priority", "sources": ["A", "B", "C", "J"], "text": "First non-KEEP valid candidate in order J, A, C, B, else KEEP."},
    "prio_C_A_B_J": {"family": "priority", "sources": ["A", "B", "C", "J"], "text": "First non-KEEP valid candidate in order C, A, B, J, else KEEP."},
    "unanimous_candidate_else_A": {
        "family": "conservative",
        "sources": ["A", "B", "C"],
        "text": "If A, B, and C are the same non-KEEP candidate, use it. Else use A.",
    },
    "unanimous_or_two_candidate_else_A": {
        "family": "conservative",
        "sources": ["A", "B", "C"],
        "text": "If a non-KEEP candidate has two or three A/B/C votes, use it. Else use A.",
    },
    "A_only_when_another_pass_agrees": {
        "family": "conservative",
        "sources": ["A", "B", "C"],
        "text": "If A is a candidate and A equals B or A equals C, use A. Else KEEP.",
    },
    "A_or_J_only_when_supported_by_another_pass": {
        "family": "conservative",
        "sources": ["A", "B", "C", "J"],
        "text": "If A is a candidate and A equals B, C, or J, use A. Else if J is a candidate and J equals B or C, use J. Else KEEP.",
    },
}


def apply_rule(name: str, cell: dict[str, Any]) -> str:
    listed = set(cell["listed_ids"])
    a, b, c, j = cell.get("A"), cell.get("B"), cell.get("C"), cell.get("J")

    def A_or_keep() -> str:
        return a if token_ok(a, listed) else KEEP

    def first_prio(order: list[str | None]) -> str:
        for token in order:
            if is_cand(token, listed):
                return token
        return KEEP

    if name == "A" or name == "A_backbone":
        return A_or_keep()
    if name == "B":
        return b if token_ok(b, listed) else KEEP
    if name == "C":
        return c if token_ok(c, listed) else KEEP
    if name == "J_only":
        return j if is_cand(j, listed) else KEEP
    if name in {"majority_original", "official_original"}:
        present = [v for v in (a, b, c) if v]
        winner = KEEP
        if present:
            top, n = Counter(present).most_common(1)[0]
            if n >= 2 and token_ok(top, listed):
                winner = top
        if name == "official_original" and cell.get("adjudicated"):
            return j if token_ok(j, listed) else KEEP
        return winner
    if name == "A_fill_BC":
        if is_cand(a, listed):
            return a
        if b == c and is_cand(b, listed):
            return b
        return KEEP
    if name == "A_fill_J":
        if is_cand(a, listed):
            return a
        if is_cand(j, listed):
            return j
        return KEEP
    if name == "A_fill_BC_then_J":
        if is_cand(a, listed):
            return a
        if b == c and is_cand(b, listed):
            return b
        if is_cand(j, listed):
            return j
        return KEEP
    if name == "A_replace_BC":
        if b == c and is_cand(b, listed):
            return b
        return A_or_keep()
    if name == "A_replace_J":
        if is_cand(j, listed):
            return j
        return A_or_keep()
    if name == "A_replace_BC_then_J":
        if b == c and is_cand(b, listed):
            return b
        if is_cand(j, listed):
            return j
        return A_or_keep()
    if name == "A_veto_double_keep":
        if b == KEEP and c == KEEP:
            return KEEP
        return A_or_keep()
    if name == "nonkeep_plurality":
        cand_votes = [v for v in (a, b, c) if is_cand(v, listed)]
        if not cand_votes:
            return KEEP
        top, n = Counter(cand_votes).most_common(1)[0]
        return top if n >= 2 else KEEP
    if name == "nonkeep_plurality_A_tiebreak":
        cand_votes = [v for v in (a, b, c) if is_cand(v, listed)]
        if not cand_votes:
            return KEEP
        counts = Counter(cand_votes)
        best = counts.most_common(1)[0][1]
        tied = [cid for cid, n in counts.items() if n == best]
        if len(tied) == 1:
            return tied[0]
        if a in tied:
            return a
        return KEEP
    if name == "any_two_then_A":
        cand_votes = [v for v in (a, b, c) if is_cand(v, listed)]
        if cand_votes:
            top, n = Counter(cand_votes).most_common(1)[0]
            if n >= 2:
                return top
        return A_or_keep()
    if name == "J_on_three_way_only":
        present = [v for v in (a, b, c) if v]
        cand_votes = [v for v in present if is_cand(v, listed)]
        if cand_votes:
            top, n = Counter(cand_votes).most_common(1)[0]
            if n >= 2:
                return top
        if len(present) == 3 and len(set(present)) == 3 and is_cand(j, listed):
            return j
        return A_or_keep()
    if name == "prio_A_J_C_B":
        return first_prio([a, j, c, b])
    if name == "prio_A_C_B_J":
        return first_prio([a, c, b, j])
    if name == "prio_J_A_C_B":
        return first_prio([j, a, c, b])
    if name == "prio_C_A_B_J":
        return first_prio([c, a, b, j])
    if name == "unanimous_candidate_else_A":
        if a == b == c and is_cand(a, listed):
            return a
        return A_or_keep()
    if name == "unanimous_or_two_candidate_else_A":
        cand_votes = [v for v in (a, b, c) if is_cand(v, listed)]
        if cand_votes:
            top, n = Counter(cand_votes).most_common(1)[0]
            if n >= 2:
                return top
        return A_or_keep()
    if name == "A_only_when_another_pass_agrees":
        if is_cand(a, listed) and a in {b, c}:
            return a
        return KEEP
    if name == "A_or_J_only_when_supported_by_another_pass":
        if is_cand(a, listed) and a in {b, c, j}:
            return a
        if is_cand(j, listed) and j in {b, c}:
            return j
        return KEEP
    raise KeyError(name)


class AuditEngine(SharedEngine):
    def checkpoint(self, score: dict[str, Any], phase: str) -> None:
        dest = Path(getattr(self, "ckpt_dir", OUT / "reachability" / "full" / "best"))
        dest.mkdir(parents=True, exist_ok=True)
        manifest = self.manifest()
        fills = self.fills()
        db = dest / "shared.db"
        mat = materialize_fills(db, fills, self.mapping, self.statements, self.predicates, self.query_ids)
        rebuilt = score_db(db, self.statements, self.predicates, self.query_ids, self.gold)
        rebuilt_p = rebuilt["mean_per_query_product"]
        if rebuilt_p + 1e-12 < getattr(self, "disk_best", -1.0):
            return
        self.disk_best = rebuilt_p
        payload = {
            "phase": phase,
            "product_incremental": score["mean_per_query_product"],
            "product_rebuilt": rebuilt_p,
            "mean_structure_f2": rebuilt["mean_structure_f2"],
            "mean_cell_f1_at_0.20": rebuilt["mean_cell_f1_at_0.20"],
            "changed_cells": mat["overlay"].get("changed_cells"),
            "assignment_hash": self.assignment_hash(),
            "bag_sha256": mat["bag_sha256"],
            "db_sha256": file_sha256(db),
            "manifest_sha256": sha(manifest),
            "per_query": rebuilt["per_query"],
        }
        (dest / "assignment_manifest.json").write_text(json.dumps(manifest, indent=2))
        (dest / "fills.json").write_text(json.dumps(fills, indent=2, default=str))
        (dest / "bags.json").write_text(json.dumps(mat["bags"], indent=2, default=str))
        (dest / "checkpoint.json").write_text(json.dumps(payload, indent=2, default=str))
        snap = dest.parent / "snapshots"
        snap.mkdir(parents=True, exist_ok=True)
        (snap / f"{self.n_bests:04d}_{rebuilt_p:.6f}.json").write_text(json.dumps({"phase": phase, "product_rebuilt": rebuilt_p, "changed_cells": payload["changed_cells"], "assignment_hash": payload["assignment_hash"]}, indent=2))


def fills_from_choices(choices: dict[str, str], cells: dict[str, dict[str, Any]], by_id: dict[tuple[str, str, str], Any]) -> dict[str, dict[str, Any]]:
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


def verify_db(dest: Path, fills: dict[str, dict[str, Any]], mapping, plumbing_rows) -> dict[str, bool]:
    conn = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
    cols = [row[1] for row in conn.execute(f'PRAGMA table_info("{TABLE}")')]
    rows = [dict(zip(cols, rec)) for rec in conn.execute(f'SELECT * FROM "{TABLE}"')]
    conn.close()
    plumbing_by = {str(row["__entity_id"]): row for row in plumbing_rows}
    n = len(rows) == 570
    ids = [row.get("__entity_id") for row in rows] == [row.get("__entity_id") for row in plumbing_rows]
    no_overwrite = True
    unrelated = True
    for row in rows:
        eid = str(row["__entity_id"])
        base = plumbing_by[eid]
        doc = str(base.get("__provenance_label") or "")
        for col in cols:
            if col in {"__entity_id", "__provenance_label"}:
                continue
            written = (fills.get(doc) or {}).get(col)
            if written is not None:
                if base.get(col) not in (None, "") and str(base.get(col)) != str(row.get(col)):
                    no_overwrite = False
            else:
                if str(base.get(col) or "") != str(row.get(col) or ""):
                    unrelated = False
    return {"n570": n, "stable_ids": ids, "no_incumbent_overwrite": no_overwrite, "unrelated_unchanged": unrelated}


def reconstruct() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    cards = json.loads((FROZEN_SELECT / "cards.json").read_text())
    parsed = json.loads((FROZEN_SELECT / "parsed_decisions.json").read_text())
    inventory = json.loads((FROZEN_INV / "candidate_inventory.json").read_text())
    cells: dict[str, dict[str, Any]] = {}
    by_id: dict[tuple[str, str, str], Any] = {}
    for rec in inventory:
        for item in rec.get("all_candidates") or rec.get("candidates") or []:
            by_id[(rec["document_id"], rec["attribute"], str(item.get("id")))] = item
    for card in cards:
        cells[card["cell_id"]] = {
            "cell_id": card["cell_id"],
            "entity_id": card["entity_id"],
            "document_id": card["document_id"],
            "attribute": card["attribute"],
            "listed_ids": list(card["listed_ids"]),
            "n_candidates": card["n_candidates"],
            "A": None,
            "B": None,
            "C": None,
            "J": None,
            "adjudicated": False,
            "salvage": None,
            "journal": {},
        }
    invalid: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    repaired: list[dict[str, Any]] = []
    unique_raw: list[dict[str, Any]] = []
    salvage_rows: list[dict[str, Any]] = []
    repair_changed: list[dict[str, Any]] = []
    outside_card: list[dict[str, Any]] = []
    for line in (FROZEN_SELECT / "response_journal.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cell = cells.get(row["cell_id"])
        if cell is None:
            continue
        stage = {"A": "A", "B": "B", "C": "C", "ADJ": "J"}.get(row["stage"])
        if not stage:
            continue
        listed = list(cell["listed_ids"])
        listed_set = set(listed)
        raw = str(row.get("raw") or "")
        choice = row.get("choice")
        if choice is not None:
            choice = str(choice)
        if row.get("repaired"):
            repaired.append({"stage": stage, "cell_id": row["cell_id"], "choice": choice})
        found = find_ids(raw, listed)
        if len(set(found)) == 1:
            unique_raw.append({"stage": stage, "cell_id": row["cell_id"], "id": found[0], "malformed": bool(row.get("malformed")), "repaired": bool(row.get("repaired"))})
        if choice and choice not in listed_set and choice != KEEP:
            invalid.append({"stage": stage, "cell_id": row["cell_id"], "choice": choice})
            outside_card.append({"stage": stage, "cell_id": row["cell_id"], "choice": choice})
            choice = None
        if row.get("malformed") or choice is None:
            if len(set(found)) == 1:
                salvage_rows.append({"stage": stage, "cell_id": row["cell_id"], "salvage": found[0], "raw_ids": found})
                prev = cell.get("salvage_ids") or []
                prev.append(found[0])
                cell["salvage_ids"] = prev
                uniq = set(prev)
                cell["salvage"] = next(iter(uniq)) if len(uniq) == 1 else None
        if row.get("repaired") and choice and len(set(found)) == 1 and found[0] != choice:
            repair_changed.append({"stage": stage, "cell_id": row["cell_id"], "stored_choice": choice, "raw_id": found[0]})
        cell[stage] = choice
        if stage == "J":
            cell["adjudicated"] = True
        cell["journal"][stage] = {"choice": choice, "malformed": bool(row.get("malformed")), "repaired": bool(row.get("repaired")), "reason": row.get("reason")}
    selectable = [cid for cid, cell in cells.items() if cell["n_candidates"] > 0]
    for cell_id in selectable:
        cell = cells[cell_id]
        for stage in ("A", "B", "C"):
            if stage not in cell["journal"]:
                missing.append({"stage": stage, "cell_id": cell_id})
    frozen_A = parsed.get("A") or {}
    mismatch_parsed = sum(1 for cid, cell in cells.items() if frozen_A.get(cid) != cell["A"] and cid in frozen_A)
    report = {
        "n_cells": len(cells),
        "selectable": len(selectable),
        "invalid_candidate_ids": invalid,
        "n_invalid": len(invalid),
        "missing_decisions": missing,
        "n_missing": len(missing),
        "repaired_responses": len(repaired),
        "unique_raw_recoverable": len(unique_raw),
        "salvaged": salvage_rows,
        "n_salvaged": len(salvage_rows),
        "repair_changed_apparent_choice": repair_changed,
        "n_repair_changed": len(repair_changed),
        "outside_final_card": outside_card,
        "n_outside_card": len(outside_card),
        "parsed_A_mismatches": mismatch_parsed,
        "adjudicated_cells": sum(1 for cell in cells.values() if cell["adjudicated"]),
        "journal_overwrite_note": "Repaired rows store the repair raw, not the pre-repair malformed text. Salvage uses the stored raw only.",
    }
    return cells, {"report": report, "by_id": by_id, "selectable": selectable}


def assignment_from_manifest(engine: AuditEngine, manifest: dict[str, dict[str, str]]) -> dict[int, int]:
    mapping = {idx: 0 for idx in range(len(engine.cells))}
    for cell in engine.cells:
        cid = (manifest.get(cell.document_id) or {}).get(cell.attribute)
        if not cid or cid == KEEP:
            continue
        for i, ch in enumerate(cell.choices):
            if cid == ch.choice_id or cid in ch.ids:
                mapping[cell.index] = i
                break
    return mapping


def assignment_from_ids(engine: AuditEngine, id_map: dict[str, str], cell_index: dict[str, int]) -> dict[int, int]:
    mapping = {idx: 0 for idx in range(len(engine.cells))}
    for cell_id, cid in id_map.items():
        idx = cell_index.get(cell_id)
        if idx is None:
            continue
        if not cid or cid == KEEP:
            mapping[idx] = 0
            continue
        cell = engine.cells[idx]
        for i, ch in enumerate(cell.choices):
            if cid == ch.choice_id or cid in ch.ids:
                mapping[idx] = i
                break
    return mapping


def build_engine(cells, by_id, plumbing_rows, mapping, statements, predicates, query_ids, gold, records, specs, gold_by, domain_ids: dict[str, set[str]]):
    queries_by_attr = {name: list(records[name].queries) for name in records}
    engine = AuditEngine(plumbing_rows, mapping, statements, predicates, query_ids, gold, records, specs, gold_by)
    engine.disk_best = -1.0
    cell_index: dict[str, int] = {}
    plumbing_by = {str(row["__entity_id"]): row for row in plumbing_rows}
    for cell in cells.values():
        prow = plumbing_by[cell["entity_id"]]
        if prow.get(cell["attribute"]) not in (None, ""):
            continue
        gold_v = gold_value(gold_by, cell["document_id"], cell["attribute"])
        allowed = domain_ids[cell["cell_id"]]
        choices = [Choice(KEEP_ID, None, KEEP, False, [KEEP_ID])]
        seen = {("null", None)}
        for cid in sorted(allowed):
            if cid == KEEP:
                continue
            item = by_id.get((cell["document_id"], cell["attribute"], cid))
            if item is None or _null(item.get("normalized")):
                continue
            value = item.get("normalized")
            key = typed_key(specs[cell["attribute"]], value)
            if key in seen:
                for ch in choices:
                    if typed_key(specs[cell["attribute"]], ch.value) == key:
                        ch.ids.append(cid)
                        break
                continue
            seen.add(key)
            choices.append(Choice(cid, value, channel_of(item), False, [cid]))
        engine.add_cell(
            Cell(0, cell["entity_id"], cell["document_id"], cell["attribute"], queries_by_attr.get(cell["attribute"]) or [], choices, gold_v, cell["attribute"])
        )
        cell_index[cell["cell_id"]] = engine.cells[-1].index
    return engine, cell_index


def coordinate(engine: AuditEngine, order: list[int], phase: str, max_passes: int = 4) -> None:
    cache = engine.full_bags()
    score = engine.score_bags(cache)
    engine.consider_best(score, phase)
    for _ in range(max_passes):
        improved = False
        for idx in order:
            cell = engine.cells[idx]
            if len(cell.choices) <= 1:
                continue
            best_i, best_score, best_tie = engine.assignment[idx], score, engine.tie_key(idx, engine.assignment[idx])
            for choice_i in range(len(cell.choices)):
                trial = engine.try_choice(idx, choice_i, cache)
                product = trial["mean_per_query_product"]
                tie = engine.tie_key(idx, choice_i)
                if product > best_score["mean_per_query_product"] + 1e-12 or (
                    abs(product - best_score["mean_per_query_product"]) <= 1e-12 and tie < best_tie
                ):
                    best_i, best_score, best_tie = choice_i, trial, tie
            if best_i != engine.assignment[idx] and best_score["mean_per_query_product"] > score["mean_per_query_product"] + 1e-12:
                engine.commit_choice(idx, best_i, cache, best_score, phase, "single_cell")
                score = best_score
                improved = True
        if not improved:
            break


def goldish(engine: AuditEngine, idx: int) -> int | None:
    cell = engine.cells[idx]
    for i, ch in enumerate(cell.choices):
        if i and exact_gold(engine.specs, cell.attribute, ch.value, cell.gold):
            return i
    return None


def apply_block(engine: AuditEngine, indices: list[int], choice_fn: Callable[[int], int | None], phase: str, reason: str) -> bool:
    cache = engine.full_bags()
    before = engine.score_bags(cache)
    prev = dict(engine.assignment)
    for idx in indices:
        choice_i = choice_fn(idx)
        if choice_i is not None:
            engine.apply_choice(idx, choice_i)
    after = engine.score_bags(engine.full_bags())
    if after["mean_per_query_product"] > before["mean_per_query_product"] + 1e-12:
        engine.consider_best(after, phase)
        engine.moves.append({"phase": phase, "reason": reason, "n": len(indices), "previous_product": before["mean_per_query_product"], "new_product": after["mean_per_query_product"]})
        return True
    engine.load_assignment(prev)
    return False


def run_search(engine: AuditEngine, starts: dict[str, dict[int, int]], thorough: bool, ckpt_dir: Path, skip_start_ascent: bool = False) -> dict[str, Any]:
    engine.ckpt_dir = ckpt_dir
    engine.best_product = -1.0
    engine.best_assignment = {idx: 0 for idx in range(len(engine.cells))}
    engine.disk_best = -1.0
    engine.n_bests = 0
    start_scores = {}
    seen_starts: set[str] = set()
    for name, assign in starts.items():
        engine.load_assignment(assign)
        score = engine.score_bags(engine.full_bags())
        engine.consider_best(score, "A")
        start_scores[name] = score["mean_per_query_product"]
        print(json.dumps({"start": name, "product": score["mean_per_query_product"], "writes": engine.n_changed()}, indent=2), flush=True)
        ah = sha(sorted(assign.items()))
        if skip_start_ascent or ah in seen_starts:
            print(json.dumps({"skip_start_ascent": name, "duplicate": ah in seen_starts}, indent=2), flush=True)
            seen_starts.add(ah)
            continue
        seen_starts.add(ah)
        order = list(range(len(engine.cells)))
        coordinate(engine, order, "A", max_passes=4 if thorough else 2)
        coordinate(engine, list(reversed(order)), "A", max_passes=2)
        engine.load_assignment(dict(engine.best_assignment))
    seeds = RANDOM_SEEDS[:8] if skip_start_ascent or not thorough else RANDOM_SEEDS
    for seed in seeds:
        rng = random.Random(seed)
        order = list(range(len(engine.cells)))
        rng.shuffle(order)
        coordinate(engine, order, "A", max_passes=2 if thorough else 1)
        engine.load_assignment(dict(engine.best_assignment))
    engine.load_assignment(dict(engine.best_assignment))
    changed = True
    rounds = 0
    while changed and rounds < (6 if thorough else 3):
        changed = False
        rounds += 1
        for attr, indices in engine.by_attr.items():
            if apply_block(engine, indices, lambda i: goldish(engine, i), "B", f"attribute:{attr}"):
                changed = True
        for qid, indices in engine.by_query.items():
            if apply_block(engine, indices, lambda i: goldish(engine, i), "B", f"query:{qid}"):
                changed = True
        if not skip_start_ascent:
            for entity, indices in engine.by_entity.items():
                if apply_block(engine, indices, lambda i: goldish(engine, i), "B", f"entity:{entity[:8]}"):
                    changed = True
        pairs = set()
        for qid in engine.query_ids:
            attrs = [name for name in engine.records if qid in engine.records[name].queries]
            for i, left in enumerate(attrs):
                for right in attrs[i + 1 :]:
                    pairs.add((left, right))
        for left, right in sorted(pairs):
            if apply_block(engine, engine.by_attr[left] + engine.by_attr[right], lambda i: goldish(engine, i), "B", f"pair:{left}+{right}"):
                changed = True
    coordinate(engine, list(range(len(engine.cells))), "B", max_passes=2)
    engine.load_assignment(dict(engine.best_assignment))
    beam: list[tuple[float, dict[int, int], str]] = [(engine.best_product, dict(engine.assignment), engine.assignment_hash())]
    deficit = sorted(engine.query_ids, key=lambda qid: next(row["product"] for row in engine.best_score["per_query"] if row["query_id"] == qid))
    sweeps = 2 if skip_start_ascent else (3 if thorough else 1)
    for sweep in range(sweeps):
        qorder = list(engine.query_ids) if sweep % 2 == 0 else list(deficit)
        for qid in qorder:
            frontier = sorted(beam, key=lambda item: -item[0])[:64 if thorough else 24]
            expansions = []
            for _product, assign, _h in frontier[:16 if thorough else 8]:
                engine.load_assignment(assign)
                cache = engine.full_bags()
                for idx in engine.by_query[qid][:48]:
                    for choice_i in range(len(engine.cells[idx].choices)):
                        if choice_i == engine.assignment[idx]:
                            continue
                        trial = engine.try_choice(idx, choice_i, cache)
                        trial_assign = dict(engine.assignment)
                        trial_assign[idx] = choice_i
                        expansions.append((trial["mean_per_query_product"], trial_assign, sha(sorted(trial_assign.items())), trial))
            expansions.sort(key=lambda item: -item[0])
            seen = {item[2] for item in beam}
            for product, assign, hsh, trial in expansions:
                if hsh in seen:
                    continue
                seen.add(hsh)
                beam.append((product, assign, hsh))
                engine.load_assignment(assign)
                engine.consider_best(trial, "C")
                if len(beam) > 160:
                    beam = sorted(beam, key=lambda item: -item[0])[:80]
                    break
        beam = sorted(beam, key=lambda item: -item[0])[:80]
        print(json.dumps({"phase_C_sweep": sweep, "best": engine.best_product, "beam": len(beam)}, indent=2), flush=True)
    coordinate(engine, list(range(len(engine.cells))), "C", max_passes=2)
    anneal_seeds = ANNEAL_SEEDS[:8] if skip_start_ascent or not thorough else ANNEAL_SEEDS
    for seed in anneal_seeds:
        engine.load_assignment(dict(engine.best_assignment))
        cache = engine.full_bags()
        current = engine.score_bags(cache)
        current_assign = dict(engine.assignment)
        rng = random.Random(seed)
        temp = 0.02
        for _ in range(80 if skip_start_ascent or not thorough else 250):
            idx = rng.randrange(len(engine.cells))
            choice_i = rng.randrange(len(engine.cells[idx].choices))
            trial = engine.try_choice(idx, choice_i, cache)
            delta = trial["mean_per_query_product"] - current["mean_per_query_product"]
            if delta > 1e-12 or rng.random() < pow(2.718281828, min(50.0, delta / max(temp, 1e-6))):
                engine.apply_choice(idx, choice_i)
                cache.update(engine.bags(engine.cells[idx].queries))
                current = trial
                current_assign = dict(engine.assignment)
                engine.consider_best(current, "D")
            temp *= 0.97
        engine.load_assignment(current_assign)
        coordinate(engine, list(range(len(engine.cells))), "D", max_passes=1)
    engine.load_assignment(dict(engine.best_assignment))
    final = engine.score_bags(engine.full_bags())
    engine.consider_best(final, "exact")
    engine.checkpoint(final, "final")
    return {"best": engine.best_product, "start_scores": start_scores, "evals": engine.n_eval, "writes": engine.n_changed(), "assignment": dict(engine.best_assignment)}


def domain_for(cell: dict[str, Any], sources: set[str], include_salvage: bool) -> set[str]:
    listed = set(cell["listed_ids"])
    out = {KEEP}
    for src in sources:
        token = cell.get(src)
        if is_cand(token, listed):
            out.add(token)
    if include_salvage and is_cand(cell.get("salvage"), listed):
        out.add(cell["salvage"])
    return out


def cohort_label(cell: dict[str, Any]) -> list[str]:
    listed = set(cell["listed_ids"])
    a, b, c, j = cell.get("A"), cell.get("B"), cell.get("C"), cell.get("J")
    labels = []
    if is_cand(a, listed) and a == b == c:
        labels.append("A=B=C candidate")
    cand_votes = [v for v in (a, b, c) if is_cand(v, listed)]
    if cand_votes and Counter(cand_votes).most_common(1)[0][1] == 2 and len(set(cand_votes)) >= 1:
        if not (is_cand(a, listed) and a == b == c):
            labels.append("exactly two candidate votes")
    if is_cand(a, listed) and b == KEEP and c == KEEP:
        labels.append("A candidate, B=C=KEEP")
    if is_cand(a, listed) and {b, c} != {KEEP} and not (b == c == a) and not (b == c and is_cand(b, listed) and b != a):
        if b != c or not is_cand(b, listed):
            labels.append("A candidate with B/C disagreement")
    if a == KEEP and b == c and is_cand(b, listed):
        labels.append("A=KEEP with B=C candidate")
    present = [v for v in (a, b, c) if v]
    if len(present) == 3 and len(set(present)) == 3 and all(is_cand(v, listed) for v in present):
        labels.append("three distinct candidate votes")
    if len({a, b, c}) == 3 and KEEP in {a, b, c} and sum(is_cand(v, listed) for v in (a, b, c)) == 2:
        labels.append("candidate/KEEP/candidate splits")
    if cell.get("adjudicated") and is_cand(j, listed) and j == a:
        labels.append("adjudicator agrees with A")
    if cell.get("adjudicated") and j is not None and j != a:
        labels.append("adjudicator disagrees with A")
    if cell.get("adjudicated") and a == KEEP and is_cand(j, listed):
        labels.append("adjudicator selects candidate after A=KEEP")
    if any((cell.get("journal") or {}).get(st, {}).get("repaired") for st in ("A", "B", "C", "J")):
        labels.append("repaired")
    else:
        labels.append("unrepaired")
    return labels


def main() -> int:
    freeze = json.loads((FROZEN_SELECT / "generation_frozen.json").read_text())
    if not freeze:
        raise SystemExit("audit invalid: missing evidence-card freeze")
    OUT.mkdir(parents=True, exist_ok=True)
    cells, recon_pack = reconstruct()
    recon = recon_pack["report"]
    by_id = recon_pack["by_id"]
    (OUT / "reconstruction.json").write_text(json.dumps(recon, indent=2, default=str))
    (OUT / "salvage.json").write_text(json.dumps(recon["salvaged"], indent=2))
    print(json.dumps({k: recon[k] for k in recon if k.startswith("n_") or k in {"selectable", "repaired_responses", "unique_raw_recoverable", "adjudicated_cells"}}, indent=2), flush=True)

    rule_freeze = {
        "definitions": RULE_DEFS,
        "rule_order": list(RULE_DEFS),
        "cost_policy": {
            "A_only": "Pass A ledger including repairs",
            "A_plus_B": "Pass A + Pass B, because B is generated only after A",
            "A_plus_B_plus_C": "Pass A + B + C",
            "any_J": "Pass A + B + C + adjudication, because J exists only after all three passes",
            "salvage": "no extra tokens; derived from stored raw",
        },
        "no_post_hoc_rules": True,
    }
    rule_freeze["hash"] = sha_text(rule_freeze)
    (OUT / "rules.json").write_text(json.dumps(rule_freeze, indent=2))
    (OUT / "pre_score_freeze.json").write_text(json.dumps({"rules": rule_freeze["hash"], "reconstruction": sha_text(recon), "select_freeze": freeze}, indent=2))
    print(json.dumps({"rules_frozen": True, "hash": rule_freeze["hash"]}, indent=2), flush=True)

    manifest = json.loads((DOCETL_DIR / "query_manifest.json").read_text())
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    records = compile_attribute_inventory(statements)
    specs = compile_specs(load_official_catalog(SCHEMA_PATH), records)
    plumbing_rows = load_plumbing_rows()
    mapping = mapping_from_rows(plumbing_rows)
    gold = load_ground_truth(gold_name("Legal"))
    gold_by = gold_index(gold)
    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    plumbing_by = {str(row["__entity_id"]): row for row in plumbing_rows}
    evaluator = RowEvaluator(list(plumbing_rows[0]), statements)
    queries_by_attr = {name: list(records[name].queries) for name in records}

    replay_rows = []
    rule_choices: dict[str, dict[str, str]] = {}
    search_only = (OUT / "replay_table.json").is_file()
    if search_only:
        replay_rows = json.loads((OUT / "replay_table.json").read_text())
        for name in RULE_DEFS:
            rule_choices[name] = {cid: apply_rule(name, cell) for cid, cell in cells.items()}
        print(json.dumps({"search_only": True, "n_rules": len(replay_rows)}, indent=2), flush=True)
    for name in RULE_DEFS:
        if search_only:
            continue
        choices = {cid: apply_rule(name, cell) for cid, cell in cells.items()}
        rule_choices[name] = choices
        fills = fills_from_choices(choices, cells, by_id)
        dest = OUT / "replays" / name / f"{name}.db"
        dest.parent.mkdir(parents=True, exist_ok=True)
        mat = materialize_fills(dest, fills, mapping, statements, predicates, query_ids)
        rebuilt = score_db(dest, statements, predicates, query_ids, gold)
        verify = verify_db(dest, fills, mapping, plumbing_rows)
        dest2 = OUT / "replays" / name / f"{name}_rebuild.db"
        mat2 = materialize_fills(dest2, fills, mapping, statements, predicates, query_ids)
        accepted = sum(1 for cid, choice in choices.items() if choice and choice != KEEP)
        row = {
            "rule": name,
            "family": RULE_DEFS[name]["family"],
            "tokens": causal(set(RULE_DEFS[name]["sources"])),
            "accepted": accepted,
            "sql_visible": mat["overlay"].get("changed_cells"),
            "f2": rebuilt["mean_structure_f2"],
            "f1": rebuilt["mean_cell_f1_at_0.20"],
            "product": rebuilt["mean_per_query_product"],
            "bag_sha256": mat["bag_sha256"],
            "rebuild_bag_sha256": mat2["bag_sha256"],
            "rebuild_match": mat["bag_sha256"] == mat2["bag_sha256"],
            "verify": verify,
            "per_query": rebuilt["per_query"],
        }
        replay_rows.append(row)
        (OUT / "replays" / name / "meta.json").write_text(json.dumps({k: row[k] for k in row if k != "per_query"}, indent=2, default=str))
        print(json.dumps({"rule": name, "product": row["product"], "accepted": accepted, "tokens": row["tokens"]}, indent=2), flush=True)
    if not search_only:
        (OUT / "replay_table.json").write_text(json.dumps(replay_rows, indent=2, default=str))

    plumbing_score = score_db(PLUMBING, statements, predicates, query_ids, gold)
    plumbing_pq = {row["query_id"]: row["product"] for row in plumbing_score["per_query"]}

    def score_sparse(choice_fn) -> dict[str, Any]:
        fills = fills_from_choices({cid: choice_fn(cell) for cid, cell in cells.items()}, cells, by_id)
        dest = OUT / "_sparse.db"
        mat = materialize_fills(dest, fills, mapping, statements, predicates, query_ids)
        sc = score_db(dest, statements, predicates, query_ids, gold)
        changed_q = [row["query_id"] for row in sc["per_query"] if abs(row["product"] - plumbing_pq[row["query_id"]]) > 1e-12]
        return {"product": sc["mean_per_query_product"], "sql_visible": mat["overlay"].get("changed_cells"), "queries_changed": changed_q, "delta": sc["mean_per_query_product"] - plumbing_score["mean_per_query_product"]}

    if search_only and (OUT / "cohorts.json").is_file():
        cohort_report = json.loads((OUT / "cohorts.json").read_text())
        print(json.dumps({"cohorts_reused": True}, indent=2), flush=True)
    else:
        cohorts = defaultdict(list)
        for cid, cell in cells.items():
            for label in cohort_label(cell):
                cohorts[label].append(cid)
        cohort_report = {}
        for label, cids in sorted(cohorts.items()):
            exact = obs = sql_vis = 0
            for cid in cids:
                cell = cells[cid]
                listed = set(cell["listed_ids"])
                token = cell["A"] if token_ok(cell.get("A"), listed) else KEEP
                if label.startswith("adjudicator"):
                    token = cell["J"] if token_ok(cell.get("J"), listed) else KEEP
                item = by_id.get((cell["document_id"], cell["attribute"], token)) if token != KEEP else None
                pred = None if item is None else item.get("normalized")
                gold_v = gold_value(gold_by, cell["document_id"], cell["attribute"])
                if pred is not None and exact_gold(specs, cell["attribute"], pred, gold_v):
                    exact += 1
                if pred is not None and observational_match(evaluator, queries_by_attr.get(cell["attribute"]) or [], plumbing_by[cell["entity_id"]], cell["attribute"], pred, gold_v):
                    obs += 1
                if pred is not None:
                    sql_vis += 1
            sparse = score_sparse(lambda cell, group=set(cids), lab=label: (
                (cell["J"] if token_ok(cell.get("J"), set(cell["listed_ids"])) else KEEP)
                if lab.startswith("adjudicator") and cell["cell_id"] in group
                else (cell["A"] if token_ok(cell.get("A"), set(cell["listed_ids"])) else KEEP) if cell["cell_id"] in group else KEEP
            ))
            cohort_report[label] = {
                "cells": len(cids),
                "exact_accuracy": exact / max(len(cids), 1),
                "observational_accuracy": obs / max(len(cids), 1),
                "SQL-visible cells": sparse["sql_visible"],
                "queries_changed": sparse["queries_changed"],
                "mean_product_contribution": sparse["delta"],
                "sparse_product": sparse["product"],
            }
        (OUT / "cohorts.json").write_text(json.dumps(cohort_report, indent=2))
        print(json.dumps({"cohorts": {k: v["cells"] for k, v in cohort_report.items()}}, indent=2), flush=True)

    full_domain = {cid: domain_for(cell, {"A", "B", "C", "J"}, True) for cid, cell in cells.items()}
    engine, cell_index = build_engine(cells, by_id, plumbing_rows, mapping, statements, predicates, query_ids, gold, records, specs, gold_by, full_domain)
    print(json.dumps({"engine_cells": len(engine.cells), "mean_domain": sum(len(c.choices) for c in engine.cells) / max(len(engine.cells), 1)}, indent=2), flush=True)

    a_backbone_names = [name for name, spec in RULE_DEFS.items() if spec["family"] == "a_backbone"]
    best_fixed = max(replay_rows, key=lambda row: row["product"])
    starts = {
        "best_fixed_rule": assignment_from_ids(engine, rule_choices[best_fixed["rule"]], cell_index),
        "prio_A_J_C_B": assignment_from_ids(engine, rule_choices["prio_A_J_C_B"], cell_index),
        "prio_A_C_B_J": assignment_from_ids(engine, rule_choices["prio_A_C_B_J"], cell_index),
        "A": assignment_from_ids(engine, rule_choices["A"], cell_index),
        "B": assignment_from_ids(engine, rule_choices["B"], cell_index),
        "C": assignment_from_ids(engine, rule_choices["C"], cell_index),
        "majority": assignment_from_ids(engine, rule_choices["majority_original"], cell_index),
        "official": assignment_from_ids(engine, rule_choices["official_original"], cell_index),
        "plumbing": {idx: 0 for idx in range(len(engine.cells))},
    }
    for name in a_backbone_names:
        starts[name] = assignment_from_ids(engine, rule_choices[name], cell_index)

    saved = OUT / "reachability" / "full" / "best" / "assignment_manifest.json"
    if saved.is_file():
        resume = assignment_from_manifest(engine, json.loads(saved.read_text()))
        starts = {"resume_saved_best": resume, **starts}
        print(json.dumps({"resume": True, "saved": str(saved)}, indent=2), flush=True)
        reach = run_search(engine, starts, thorough=True, ckpt_dir=OUT / "reachability" / "full" / "best", skip_start_ascent=True)
    else:
        reach = run_search(engine, starts, thorough=True, ckpt_dir=OUT / "reachability" / "full" / "best")
    (OUT / "reachability" / "full" / "search.json").parent.mkdir(parents=True, exist_ok=True)
    (OUT / "reachability" / "full" / "search.json").write_text(json.dumps({k: reach[k] for k in reach if k != "assignment"}, indent=2, default=str))
    (OUT / "reachability" / "full" / "assignment.json").write_text(json.dumps({str(k): v for k, v in reach["assignment"].items()}))

    id_sources = {
        "A only": ({"A"}, False, {"A"}),
        "A + B": ({"A", "B"}, False, {"A", "B"}),
        "A + C": ({"A", "C"}, False, {"A", "B", "C"}),
        "A + J where J was already generated": ({"A", "J"}, False, {"A", "B", "C", "J"}),
        "A + B + C": ({"A", "B", "C"}, False, {"A", "B", "C"}),
        "A + B + C + J": ({"A", "B", "C", "J"}, True, {"A", "B", "C", "J"}),
    }
    restricted = []
    for label, (sources, salvage, cost_src) in id_sources.items():
        domain = {cid: domain_for(cell, sources, salvage) for cid, cell in cells.items()}
        eng, idxmap = build_engine(cells, by_id, plumbing_rows, mapping, statements, predicates, query_ids, gold, records, specs, gold_by, domain)
        local_starts = {"plumbing": {i: 0 for i in range(len(eng.cells))}}
        for src in sources:
            if src in rule_choices:
                local_starts[src] = assignment_from_ids(eng, rule_choices[src], idxmap)
        if saved.is_file():
            local_starts["projected_full_best"] = assignment_from_manifest(eng, json.loads(saved.read_text()))
        dest = OUT / "reachability" / "restricted" / label.replace(" ", "_")
        dest.mkdir(parents=True, exist_ok=True)
        got = run_search(eng, local_starts, thorough=False, ckpt_dir=dest / "best", skip_start_ascent=True)
        fills = eng.fills()
        mat = materialize_fills(dest / "shared.db", fills, mapping, statements, predicates, query_ids)
        rebuilt = score_db(dest / "shared.db", statements, predicates, query_ids, gold)
        restricted.append({
            "available_judgments": label,
            "causal_tokens": causal(cost_src),
            "best_reachable_product": rebuilt["mean_per_query_product"],
            "beats_docetl": rebuilt["mean_per_query_product"] > DOCETL_PRODUCT,
            "accepted": mat["overlay"].get("changed_cells"),
            "f2": rebuilt["mean_structure_f2"],
            "f1": rebuilt["mean_cell_f1_at_0.20"],
            "evals": got["evals"],
        })
        print(json.dumps(restricted[-1], indent=2), flush=True)
    (OUT / "cost_restricted.json").write_text(json.dumps(restricted, indent=2))

    rebuilt_best = json.loads((OUT / "reachability" / "full" / "best" / "checkpoint.json").read_text())
    reach_product = rebuilt_best["product_rebuilt"]
    best_rule = max(replay_rows, key=lambda row: row["product"])
    any_rule_win = best_rule["product"] > DOCETL_PRODUCT
    reach_win = reach_product > DOCETL_PRODUCT
    if any_rule_win:
        decision = "a simple stored-decision rule beats Legal DocETL"
    elif reach_win:
        decision = "stored judgments contain a Legal win but aggregation cannot identify it"
    else:
        decision = "stored judgments cannot reach Legal DocETL"

    decisive = Counter()
    best_manifest = json.loads((OUT / "reachability" / "full" / "best" / "assignment_manifest.json").read_text()) if (OUT / "reachability" / "full" / "best" / "assignment_manifest.json").is_file() else {}
    for cell in cells.values():
        cid = (best_manifest.get(cell["document_id"]) or {}).get(cell["attribute"])
        if not cid:
            continue
        for src in ("A", "B", "C", "J"):
            if cell.get(src) == cid:
                decisive[src] += 1
        if cell.get("salvage") == cid:
            decisive["salvage"] += 1

    report = {
        "decision": decision,
        "reconstruction": {k: recon[k] for k in recon if not isinstance(recon[k], list) or k.endswith("note")},
        "best_fixed_rule": {k: best_rule[k] for k in ("rule", "product", "tokens", "accepted", "f2", "f1")},
        "best_reachable": reach_product,
        "docetl": DOCETL_PRODUCT,
        "decisive_sources_in_search_best": dict(decisive),
        "restricted": restricted,
    }
    (OUT / "audit.json").write_text(json.dumps(report, indent=2, default=str))

    lines = [
        "# Legal evidence-card aggregation audit",
        "",
        "Zero Qwen. Frozen evidence-card artifacts were not modified. Gold was used only to score diagnostic replays. Reachability-assignment candidates were not admitted to any domain.",
        "",
        "## Decision reconstruction",
        "",
        json.dumps({k: recon[k] for k in recon if k not in {"invalid_candidate_ids", "missing_decisions", "salvaged", "repair_changed_apparent_choice", "outside_final_card", "unique_raw_recoverable"} or not isinstance(recon[k], list)}, indent=2),
        "",
        f"Invalid IDs: {recon['n_invalid']}. Missing pass decisions: {recon['n_missing']}. Repaired responses: {recon['repaired_responses']}. Raw texts with a unique listed ID: {recon['unique_raw_recoverable']}. Salvaged (malformed/invalid raw with exactly one listed ID): {recon['n_salvaged']}. Repair changed apparent choice vs stored raw: {recon['n_repair_changed']}. Selections outside the final card: {recon['n_outside_card']}.",
        "",
        f"Rule lattice frozen before replay: `{rule_freeze['hash']}`.",
        "",
        "## Fixed-rule replays",
        "",
        "| Rule | Required stored-call cost | Accepted | SQL-visible | F2 | F1@0.20 | Product |",
        "| ---- | ------------------------: | -------: | ----------: | -: | ------: | ------: |",
    ]
    for row in replay_rows:
        lines.append(f"| {row['rule']} | {row['tokens']} | {row['accepted']} | {row['sql_visible']} | {row['f2']:.4f} | {row['f1']:.4f} | {row['product']:.4f} |")
    lines += [
        f"| Legal DocETL | {DOCETL_TOKENS} |  |  | {DOCETL_F2:.4f} | {DOCETL_F1:.4f} | {DOCETL_PRODUCT:.4f} |",
        "",
        f"Best fixed rule: `{best_rule['rule']}` at {best_rule['product']:.4f} (post-hoc among the predeclared lattice).",
        f"Independent rebuild bag match on every rule: {all(row['rebuild_match'] for row in replay_rows)}.",
        "",
        "## Agreement cohorts",
        "",
        "| Cohort | Cells | Exact | Observational | SQL-visible | Queries changed | Product contribution |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, row in cohort_report.items():
        lines.append(
            f"| {label} | {row['cells']} | {row['exact_accuracy']:.4f} | {row['observational_accuracy']:.4f} | {row['SQL-visible cells']} | {len(row['queries_changed'])} | {row['mean_product_contribution']:+.4f} |"
        )
    lines += [
        "",
        "## Stored-output reachability",
        "",
        f"Best shared database over KEEP + A/B/C/J + unique raw-salvage: **{reach_product:.4f}**.",
        f"Search starts included plumbing, A, B, C, majority, official, every A-backbone replay, and `{best_fixed['rule']}`.",
        f"Decisive stored IDs in the search best: {dict(decisive)}.",
        "",
        "## Cost-restricted output reachability",
        "",
        "| Available judgments | Causal tokens | Best reachable product | Beats DocETL |",
        "| ------------------- | ------------: | ---------------------: | -----------: |",
    ]
    for row in restricted:
        lines.append(f"| {row['available_judgments']} | {row['causal_tokens']} | {row['best_reachable_product']:.4f} | {str(row['beats_docetl']).lower()} |")
    lines += [
        "",
        "## Interpretation",
        "",
        f"1. Fixed label-free aggregation beat 0.1235: {str(any_rule_win).lower()} (best `{best_rule['rule']}` = {best_rule['product']:.4f}).",
        f"2. Stored judgments contain a realizable assignment above 0.1235: {str(reach_win).lower()} (best reachable {reach_product:.4f}).",
        f"3. Decisive IDs in the search best came from {dict(decisive)}.",
        "",
        decision,
        "",
    ]
    (OUT / "REPORT.md").write_text("\n".join(lines))
    print(json.dumps({"decision": decision, "best_rule": best_rule["rule"], "best_rule_product": best_rule["product"], "reach": reach_product, "docetl": DOCETL_PRODUCT}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
