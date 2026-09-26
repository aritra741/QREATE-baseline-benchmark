"""Build a router-v3 plan (context-split schema discovery) for one corpus.

    python -m quwarts.eval.router_plan_v3 --corpus cspaper            # zero-token: no sharing measured
    python -m quwarts.eval.router_plan_v3 --corpus cspaper --probe    # paired sampling within 20% of theta
    python -m quwarts.eval.router_plan_v3 --corpus cspaper --replay   # re-plan from saved observations

Gold, stored baseline predictions, and evaluation files are blocked for the whole
process; the DocETL token total is read only to define theta.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import quwarts.eval.router_plan as _guard  # noqa: F401  installs the gold/baseline read guard

from quwarts.core.ledger import TokenLedger
from quwarts.core.router.context_probe import Observations
from quwarts.core.router.plan import canonical_json
from quwarts.core.router.plan_v3 import build_plan_v3, summarize_v3
from quwarts.core.router.registry import PROJECT, RESULTS, get_corpus


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--theta", type=int, default=None)
    parser.add_argument("--fraction", type=float, default=0.25)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--probe", action="store_true")
    mode.add_argument("--replay", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    spec = get_corpus(args.corpus)
    theta = args.theta or spec.theta(args.fraction)
    if not theta:
        parser.error("no DocETL token total for this corpus; pass --theta")
    base = args.out or (RESULTS / "quwarts_router_v3" / spec.name)
    out = base / ("dry_run" if not (args.probe or args.replay) else "probe")
    out.mkdir(parents=True, exist_ok=True)

    caller = ledger = observations = None
    if args.probe:
        from quwarts.core.llm.openrouter import load_env_file, make_caller

        load_env_file(PROJECT / ".env")
        ledger = TokenLedger(theta=theta)
        caller = make_caller(ledger, max_tokens=280)
        journal = out / "probe_journal.jsonl"
        if journal.exists():
            parser.error(f"{journal} exists; use --replay or remove it")
    if args.replay:
        payload = json.loads((out / "observations.json").read_text())
        observations = Observations.from_json(payload["observations"])

    plan, obs = build_plan_v3(spec, theta, caller=caller, journal=out / "probe_journal.jsonl",
                              observations=observations)
    if args.replay:
        plan["budget"]["probe_spent"] = payload["spent"]
    if args.probe:
        (out / "observations.json").write_text(json.dumps(
            {"spent": plan["budget"]["probe_spent"], "observations": obs.to_json()}, sort_keys=True))
        (out / "ledger.json").write_text(canonical_json(ledger.snapshot()))
    name = "plan_replay.json" if args.replay else "plan.json"
    (out / name).write_text(json.dumps(plan, indent=2, sort_keys=True, default=str))
    summary = summarize_v3(plan)
    (out / name.replace(".json", "_summary.txt")).write_text(summary + "\n")
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
