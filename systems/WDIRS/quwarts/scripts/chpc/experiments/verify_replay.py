"""Check that a replayed corpus reproduces the recorded streams: per query the same action, missing columns,
tokens charged and score. Writes ``<root>/<corpus>/verify.json``; exits 1 on any difference (the replay's
views then do not describe the recorded run, and the analyses built on them would be wrong).

    python verify_replay.py --root results/experiments/E2-replay/live --corpus legal
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[6]
SRC = REPO / "results" / "drift_live_ollama"
KEYS = ("qid", "action", "missing", "input_tokens", "output_tokens", "benchmark")


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--corpus", required=True)
    a = ap.parse_args()
    root = REPO / a.root / a.corpus
    report, bad = {}, 0
    for orig in sorted((SRC / a.corpus / "streams").glob("fixed4*-attribute_pool_*.jsonl")):
        rep = root / "streams" / orig.name
        if not rep.exists():
            report[orig.name] = "not replayed"
            bad += 1
            continue
        o, r = rows(orig), rows(rep)
        diffs = [{"pos": i, "field": k, "recorded": x.get(k), "replayed": y.get(k)}
                 for i, (x, y) in enumerate(zip(o, r)) for k in KEYS if x.get(k) != y.get(k)]
        if len(o) != len(r):
            diffs.append({"field": "length", "recorded": len(o), "replayed": len(r)})
        report[orig.name] = {"queries": len(o), "differences": diffs}
        bad += bool(diffs)
    (root / "verify.json").write_text(json.dumps({"streams_with_differences": bad, "streams": report}, indent=1))
    print(f"{a.corpus}: {len(report)} streams, {bad} with differences")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
