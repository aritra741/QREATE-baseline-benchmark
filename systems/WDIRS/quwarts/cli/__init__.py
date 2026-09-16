"""Command-line entry points."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from quwarts.core.pipeline import load_documents, load_workload_sql, synthesize


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quwarts")
    sub = parser.add_subparsers(dest="cmd", required=True)

    syn = sub.add_parser("synthesize")
    syn.add_argument("--corpus", type=Path, required=True)
    syn.add_argument("--workload", type=Path, required=True)
    syn.add_argument("--budget", type=int, required=True)
    syn.add_argument("--seed", type=int, default=0)
    syn.add_argument("--artifacts", type=Path, default=Path("artifacts"))

    ev = sub.add_parser("eval")
    ev.add_argument("--manifest", type=Path, required=True)
    ev.add_argument("--gold", type=Path, required=True)
    ev.add_argument("--keys", default="name")
    ev.add_argument("--columns", default="name")

    args = parser.parse_args(argv)
    if args.cmd == "synthesize":
        documents = load_documents(args.corpus)
        statements = load_workload_sql(args.workload)
        portfolio = synthesize(
            documents, statements, args.budget, seed=args.seed, artifact_root=args.artifacts
        )
        print(json.dumps({
            "tokens_spent": portfolio.tokens_spent,
            "cache_hit_rate": portfolio.cache_hit_rate,
            "databases": [db.sha256 for db in portfolio.databases],
            "route": portfolio.route,
        }, indent=2))
        return 0
    if args.cmd == "eval":
        from quwarts.eval import evaluate_portfolio, load_gold
        from quwarts.core.models import FrozenPortfolio

        payload = json.loads(args.manifest.read_text())
        portfolio = FrozenPortfolio.model_validate(
            {key: payload[key] for key in FrozenPortfolio.model_fields if key in payload}
        )
        gold = load_gold(args.gold)
        report = evaluate_portfolio(
            portfolio,
            gold,
            key_fields=[part.strip() for part in args.keys.split(",") if part.strip()],
            columns=[part.strip() for part in args.columns.split(",") if part.strip()],
        )
        print(json.dumps(report, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
