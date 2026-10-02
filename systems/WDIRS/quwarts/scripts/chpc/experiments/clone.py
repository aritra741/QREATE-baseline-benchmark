"""Set up an isolated drift_live root for one corpus, copied from the recorded run (results/drift_live_ollama).

  repeat  the builds (their databases, reads and usage) and the designs, but not the patch journal or the
          streams: a stream re-reads every patch, so two runs measure run-to-run variance of patching.
  replay  everything but the stream states and outputs: every read is in the journals, so the streams re-run
          with no model calls (run with QUWARTS_LIVE_REPLAY=1, which refuses any call) and can keep their views.
  fresh   the designs only: the builds and patches are read anew (e.g. with another model).

The original run is never written to. Idempotent: a finished clone (its ``.cloned`` marker) is left as it is.

    python clone.py --mode repeat --corpus player --root results/experiments/E1.1-stream-rep/live \\
        --scratch /scratch/general/vast/u1592362/quwarts_exp/E1.1-stream-rep
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[6]
SRC = REPO / "results" / "drift_live_ollama"
SRC_SCRATCH = Path.home() / "quwarts_scratch" / "drift_live_ollama"
DESIGNS = ["fixed4_attribute_pool_design.json", "fixed_attribute_pool_design.json", "fixed_attribute_design.json"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["repeat", "replay", "fresh"], required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--root", required=True, help="the new QUWARTS_LIVE_ROOT")
    ap.add_argument("--scratch", required=True, help="the new QUWARTS_SCRATCH")
    a = ap.parse_args()
    root = (REPO / a.root) if not a.root.startswith("/") else Path(a.root)
    src, dst = SRC / a.corpus, root / a.corpus
    sdst = Path(a.scratch) / "drift_live_ollama" / a.corpus
    marker = dst / ".cloned"
    if marker.exists():
        print(f"{dst}: already cloned ({json.loads(marker.read_text())['mode']})")
        return 0
    dst.mkdir(parents=True, exist_ok=True)
    sdst.mkdir(parents=True, exist_ok=True)
    files = list(DESIGNS)
    if a.mode in ("repeat", "replay"):
        files += ["build.json", "build_reads.jsonl", "usage.jsonl", "scores.json"]
    if a.mode == "replay":
        files += ["patch_reads.jsonl"]
    copied = []
    for f in files:
        if (src / f).exists():
            shutil.copy2(src / f, dst / f)
            copied.append(f)
    if a.mode in ("repeat", "replay"):
        shutil.copytree(src / "builds", dst / "builds", dirs_exist_ok=True)
        for f in ("build.db", "static.db"):
            shutil.copy2(SRC_SCRATCH / a.corpus / f, sdst / f)
        for d in sorted((SRC_SCRATCH / a.corpus / "builds").glob("fixed4_*")):
            shutil.copytree(d, sdst / "builds" / d.name, dirs_exist_ok=True)
        copied += ["builds/", "scratch build databases"]
    marker.write_text(json.dumps({"mode": a.mode, "from": str(src), "copied": copied}, indent=1))
    print(f"{dst}: {a.mode} clone, copied {copied}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
