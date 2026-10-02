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


def llm_caller(ledger: TokenLedger, max_tokens: int):
    """OpenRouter by default; the local Ollama server when ``QUWARTS_LLM=ollama`` (same model, Qwen 2.5 7B)."""

    import os

    if os.environ.get("QUWARTS_LLM", "openrouter") == "ollama":
        from quwarts.core.llm import ollama

        log = os.environ.get("QUWARTS_USAGE_LOG")  # one row per call: input/output tokens, seconds, model
        on_usage = None
        if log:
            import hashlib
            import json
            import threading
            from pathlib import Path

            lock = threading.Lock()
            Path(log).parent.mkdir(parents=True, exist_ok=True)

            def on_usage(prompt: str, u: dict) -> None:
                row = {"sha": hashlib.sha256(prompt.encode()).hexdigest(), "input": u["input"], "output": u["output"],
                       "seconds": u["seconds"], "model": u["model"], "num_ctx": u["num_ctx"],
                       "maybe_truncated": u["maybe_truncated"], "cut_off": u["cut_off"]}
                with lock, open(log, "a") as h:
                    h.write(json.dumps(row) + "\n")

        return ollama.make_caller(ledger, max_tokens=max_tokens, on_usage=on_usage)
    from quwarts.core.llm.openrouter import load_env_file, make_caller

    load_env_file(PROJECT / ".env")
    return make_caller(ledger, max_tokens=max_tokens)


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
        ledger = TokenLedger(theta=theta)
        caller = llm_caller(ledger, max_tokens=280)
        journal = out / "probe_journal.jsonl"
        if journal.exists():
            parser.error(f"{journal} exists; use --replay or remove it")
    if args.replay:
        payload = json.loads((out / "observations.json").read_text())
        observations = Observations.from_json(payload["observations"])

    plan, obs = build_plan_v3(spec, theta, caller=caller, journal=out / "probe_journal.jsonl",
                              observations=observations, probe_spent=payload["spent"] if args.replay else 0)
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
