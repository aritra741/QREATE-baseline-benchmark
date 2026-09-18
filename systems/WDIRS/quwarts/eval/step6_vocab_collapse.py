"""Step 6. Trace __vocab / __like collapse from stored artifacts. Zero tokens."""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.extract import EvidenceStore

OUT = ROOT / "results" / "quwarts_med_signatures"
STORES = [
    ROOT / "results" / "quwarts_med_repair80_diag" / "artifacts" / "evidence",
    ROOT / "results" / "quwarts_med_phase2" / "arm_b" / "artifacts" / "evidence",
    ROOT / "results" / "quwarts_med_aprime" / "artifacts" / "evidence",
]
APRIME = next((ROOT / "results" / "quwarts_med_aprime" / "artifacts" / "databases").glob("*.db"))
REPAIR = next((ROOT / "results" / "quwarts_med_repair_round" / "artifacts" / "databases").glob("*.db"))
LIKE_CLASSIFY = ROOT / "systems" / "WDIRS" / "quwarts" / "core" / "repair" / "like_vocab.py"
CONSTRAINED = ROOT / "systems" / "WDIRS" / "quwarts" / "core" / "extract" / "__init__.py"


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def column_values(db: Path, table: str, col: str) -> list[str | None]:
    con = sqlite3.connect(db)
    try:
        cols = [row[1] for row in con.execute(f"PRAGMA table_info({_q(table)})")]
        if col not in cols:
            return []
        return [row[0] for row in con.execute(f"SELECT {_q(col)} FROM {_q(table)}")]
    finally:
        con.close()


def instruction_hits() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path, needles in (
        (LIKE_CLASSIFY, ("exactly one vocabulary token", "exactly one")),
        (CONSTRAINED, ("exactly one of the allowed values", "exactly one")),
    ):
        text = path.read_text()
        hits = [needle for needle in needles if needle in text]
        found[str(path)] = hits
    return found


def evidence_scan(root: Path) -> dict:
    if not root.is_dir():
        return {"path": str(root), "present": False}
    store = EvidenceStore(root)
    raw_fields = ("raw", "raw_response", "completion", "response", "llm")
    n_raw = 0
    vocab = Counter()
    like = Counter()
    surfaces = Counter()
    multi_surface = 0
    multi_vocab = 0
    for rec in store.records.values():
        if rec.attribute.split(".")[-1] != "research_fields":
            continue
        keys = rec.candidate_keys or {}
        if any(key in keys for key in raw_fields):
            n_raw += 1
        if rec.surface_value:
            surfaces[str(rec.surface_value)] += 1
            if "|" in str(rec.surface_value) or "," in str(rec.surface_value):
                multi_surface += 1
        if keys.get("vocab"):
            vocab[keys["vocab"]] += 1
            if "|" in keys["vocab"]:
                multi_vocab += 1
        if keys.get("like_vocab"):
            like[keys["like_vocab"]] += 1
    return {
        "path": str(root),
        "present": True,
        "n_records": len(store.records),
        "n_research_fields": sum(
            1 for rec in store.records.values()
            if rec.attribute.split(".")[-1] == "research_fields"
        ),
        "n_raw_response_fields": n_raw,
        "like_vocab": dict(like),
        "contract_vocab": dict(vocab),
        "n_multi_token_vocab": multi_vocab,
        "n_multi_surface": multi_surface,
        "n_distinct_surfaces": len(surfaces),
    }


def main() -> int:
    like_vals = [v for v in column_values(APRIME, "institution", "research_fields__like") if v]
    vocab_vals = [v for v in column_values(APRIME, "institution", "research_fields__vocab") if v]
    surface = [v for v in column_values(APRIME, "institution", "research_fields") if v]
    repair_like = [v for v in column_values(REPAIR, "institution", "research_fields__like") if v]
    payload = {
        "step": 6,
        "repair_round_research_fields__like": {
            "n_distinct": len(set(repair_like)),
            "values": sorted(set(repair_like)),
        },
        "aprime_research_fields": {
            "n_surface_distinct": len(set(surface)),
            "n_like_distinct": len(set(like_vals)),
            "like_values": sorted(set(like_vals)),
            "n_vocab_distinct": len(set(vocab_vals)),
            "vocab_values": sorted(set(vocab_vals)),
        },
        "instructions_in_pipeline": instruction_hits(),
        "stores": [evidence_scan(path) for path in STORES],
        "hypothesis": None,
    }
    instructed = any(payload["instructions_in_pipeline"].values())
    any_raw = any(item.get("n_raw_response_fields") for item in payload["stores"])
    multi = any(item.get("n_multi_token_vocab") for item in payload["stores"])
    if instructed and not multi:
        payload["hypothesis"] = "instructed_exactly_one"
        payload["note"] = (
            "No stored raw completions. Live prompts require exactly one token. "
            "dictionary_map keeps a value only when token_hits==1; _classify asks "
            "for exactly one vocabulary token. Constrained extract asks for exactly "
            "one allowed value. This is an instruction/contract, not a silent drop "
            "of a multi-label model output."
        )
    elif multi and not instructed:
        payload["hypothesis"] = "multi_label_dropped"
    else:
        payload["hypothesis"] = "instructed_exactly_one" if instructed else "inconclusive"
        payload["note"] = (
            "Raw completions are not stored on evidence records. "
            f"instruction_exactly_one={instructed} stored_raw={any_raw} "
            f"multi_token_vocab_assignments={multi}."
        )
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "step6_vocab_collapse.json"
    path.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
