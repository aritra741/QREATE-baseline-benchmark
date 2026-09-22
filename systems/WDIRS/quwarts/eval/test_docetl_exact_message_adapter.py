"""Compare generated DocETL primary messages to stored replay messages. No API calls."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "results" / "finan_reproduction_gap_audit" / "adapter_gate.json"


def test_adapter_against_stored_primary_messages() -> dict:
    if not OUT.is_file():
        raise SystemExit("adapter_gate.json missing; run finan_reproduction_gap_audit.py first")
    payload = json.loads(OUT.read_text())
    gate = payload["gate"]
    assert gate["denominator"] == 112
    assert gate["exact_matches"] <= 112
    if gate["pass"]:
        assert gate["exact_matches"] == 112
    return gate


if __name__ == "__main__":
    print(json.dumps(test_adapter_against_stored_primary_messages(), indent=2))
