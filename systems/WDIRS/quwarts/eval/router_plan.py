"""Build a frozen router plan for one corpus.

Usage (from systems/WDIRS):
    python -m quwarts.eval.router_plan --corpus legal            # zero-token dry run
    python -m quwarts.eval.router_plan --corpus legal --probe    # spend the probe budget

Gold, stored baseline predictions, and evaluation files are blocked for the
whole process. The DocETL session token total is read only to define theta.
"""

from __future__ import annotations

import argparse
import builtins
import json
import sys
from pathlib import Path

_FORBIDDEN = (
    "ground_truth",
    "/gold/",
    "gold.json",
    "query_results.json",
    "query_tables",
    "evaluation.json",
    "summary.json",
    "report.json",
    "pipeline_output.json",
    "extract_fields.json",
    "docetl_cache",
    "diagnostic_scores",
)
_ORIGINAL_OPEN = builtins.open


def _guard_open(file, mode="r", *args, **kwargs):
    text = str(file)
    if any(flag in mode for flag in ("r", "+")) and any(part in text for part in _FORBIDDEN):
        raise PermissionError(f"router: blocked gold/baseline read: {text}")
    return _ORIGINAL_OPEN(file, mode, *args, **kwargs)


builtins.open = _guard_open

from quwarts.core.ledger import TokenLedger  # noqa: E402
from quwarts.core.router.plan import build_plan, canonical_json, estimate_theta, summarize  # noqa: E402
from quwarts.core.router.registry import RESULTS, get_corpus  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--theta", type=int, default=None, help="token budget; default 25%% of DocETL")
    parser.add_argument("--fraction", type=float, default=0.25)
    parser.add_argument("--probe", action="store_true", help="spend the probe budget with Qwen")
    parser.add_argument("--incumbent", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    spec = get_corpus(args.corpus)
    theta = args.theta or spec.theta(args.fraction)
    theta_source = "argument" if args.theta else "docetl_total"
    if not theta:
        theta = estimate_theta(spec, args.fraction)
        theta_source = "docetl_equivalent_estimate"
        print(f"no DocETL run: theta = {args.fraction:.0%} of the estimated DocETL cost = {theta:,}")
    out = args.out or (RESULTS / "quwarts_router" / spec.name / ("probe" if args.probe else "dry_run"))
    out.mkdir(parents=True, exist_ok=True)

    caller = None
    ledger = None
    if args.probe:
        from quwarts.core.llm.openrouter import load_env_file, make_caller
        from quwarts.core.router.registry import PROJECT

        load_env_file(PROJECT / ".env")
        ledger = TokenLedger(theta=theta, seed=0)
        caller = make_caller(ledger, max_tokens=280)

    plan = build_plan(spec, theta, caller=caller, journal=out / "probe_journal.jsonl", incumbent_db=args.incumbent)
    plan["budget"]["theta_source"] = theta_source
    (out / "plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True, default=str))
    if ledger is not None:
        (out / "ledger.json").write_text(canonical_json(ledger.snapshot()))
    (out / "plan_hash.txt").write_text(plan["plan_hash"] + "\n")
    print(summarize(plan))
    print(f"wrote {out / 'plan.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
