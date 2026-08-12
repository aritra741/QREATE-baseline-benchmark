#!/usr/bin/env python3
"""Run and audit a controlled pair of fresh QuWARTS budget experiments."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CASE = Path(__file__).resolve().parent
RUNNER = CASE / "run_player_contrast_workloads.py"
COMPARATOR = CASE / "compare_quwarts_budget_runs.py"
EVALUATOR = (
    ROOT
    / "systems"
    / "WDIRS"
    / "diagnostics"
    / "evaluate_native_spp_bundle.py"
)


def _command(
    *,
    budget: int,
    output_root: Path,
    args: argparse.Namespace,
    replay_root: Path | None = None,
) -> list[str]:
    command = [
        sys.executable,
        str(RUNNER),
        "--run",
        "--only",
        args.only,
        "--token-budget",
        str(budget),
        "--seed",
        str(args.seed),
        "--controlled-prefix",
        "--continue-on-error",
        "--output-root",
        str(output_root),
        "--quality-floor",
        str(args.quality_floor),
        "--dataset",
        args.dataset,
        "--bulk-column-batch-size",
        str(args.bulk_column_batch_size),
        "--bulk-min-column-coverage",
        str(args.bulk_min_column_coverage),
    ]
    if args.model:
        command.extend(["--model", args.model])
    if args.base_url:
        command.extend(["--base-url", args.base_url])
    if args.force:
        command.append("--force")
    if replay_root is not None:
        command.extend(["--replay-root", str(replay_root)])
    return command


def _evaluation_command(
    *,
    root: Path,
    workload_id: str,
    dataset: str,
) -> list[str]:
    result_dir = root / "results" / workload_id
    return [
        sys.executable,
        str(EVALUATOR),
        "--bundle",
        str(result_dir / "serving_bundle"),
        "--reference-workload",
        str(CASE / "workloads" / workload_id / "query_manifest.json"),
        "--dataset",
        dataset,
        "--output",
        str(result_dir / "evaluation.json"),
    ]


def _load_calls(root: Path, workload_id: str) -> list[dict[str, Any]]:
    path = (
        root
        / "results"
        / workload_id
        / "llm_call_manifest.json"
    )
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    calls = payload.get("calls", [])
    return [dict(call) for call in calls if isinstance(call, dict)]


def _identified_calls(
    calls: list[dict[str, Any]],
) -> list[tuple[tuple[str, int], dict[str, Any]]]:
    occurrences: defaultdict[str, int] = defaultdict(int)
    identified = []
    for call in calls:
        key = str(call.get("request_key") or "")
        identity = (key, occurrences[key])
        occurrences[key] += 1
        identified.append((identity, call))
    return identified


def _audit_workload(
    low_root: Path,
    high_root: Path,
    workload_id: str,
) -> dict[str, Any]:
    low_calls = _identified_calls(_load_calls(low_root, workload_id))
    high_calls = _identified_calls(_load_calls(high_root, workload_id))
    low_by_id = dict(low_calls)
    high_by_id = dict(high_calls)
    shared = set(low_by_id) & set(high_by_id)
    compared_fields = (
        "seed",
        "prompt_sha256",
        "response_sha256",
        "input_tokens",
        "output_tokens",
    )
    mismatches = []
    for identity in sorted(shared):
        differing = [
            field
            for field in compared_fields
            if low_by_id[identity].get(field)
            != high_by_id[identity].get(field)
        ]
        if differing:
            mismatches.append(
                {
                    "request_key": identity[0],
                    "occurrence": identity[1],
                    "fields": differing,
                }
            )
    low_shared_order = [
        identity for identity, _call in low_calls if identity in shared
    ]
    high_shared_order = [
        identity for identity, _call in high_calls if identity in shared
    ]
    low_only = set(low_by_id) - shared
    high_only = set(high_by_id) - shared
    shared_replayed = sum(
        bool(high_by_id[identity].get("replayed"))
        for identity in shared
    )
    manifests_present = bool(low_calls) and bool(high_calls)
    return {
        "workload_id": workload_id,
        "low_call_count": len(low_calls),
        "high_call_count": len(high_calls),
        "shared_call_count": len(shared),
        "low_only_call_count": len(low_only),
        "high_only_call_count": len(high_only),
        "shared_replayed_call_count": shared_replayed,
        "shared_order_identical": low_shared_order == high_shared_order,
        "shared_response_mismatches": mismatches,
        "verified": (
            manifests_present
            and not mismatches
            and low_shared_order == high_shared_order
            and shared_replayed == len(shared)
        ),
        "note": (
            "verified requires every call shared by both runs to have "
            "identical seed, prompt, response, usage, and relative order; "
            "the high run must replay each shared response; budget-dependent "
            "prompts are reported as low-only/high-only"
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run low/high budgets under the controlled-prefix protocol and "
            "verify every LLM call shared by the two executions."
        )
    )
    parser.add_argument("--low-budget", type=int, required=True)
    parser.add_argument("--high-budget", type=int, required=True)
    parser.add_argument("--only", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--dataset", default="Player")
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--quality-floor", type=float, default=0.0)
    parser.add_argument("--bulk-column-batch-size", type=int, default=10)
    parser.add_argument("--bulk-min-column-coverage", type=float, default=0.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.low_budget <= 0 or args.high_budget <= args.low_budget:
        raise SystemExit("--high-budget must be greater than --low-budget > 0")
    workloads = tuple(
        part.strip() for part in args.only.split(",") if part.strip()
    )
    if not workloads:
        raise SystemExit("--only must contain at least one workload id")
    if args.output_root is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        pair_root = (
            CASE / "workloads" / "runs" / f"quwarts_paired_{stamp}"
        )
    else:
        pair_root = args.output_root.expanduser()
        if not pair_root.is_absolute():
            pair_root = (ROOT / pair_root).resolve()
    low_root = pair_root / "low"
    high_root = pair_root / "high"
    low_command = _command(
        budget=args.low_budget,
        output_root=low_root,
        args=args,
    )
    high_command = _command(
        budget=args.high_budget,
        output_root=high_root,
        args=args,
        replay_root=low_root,
    )
    evaluation_commands = [
        _evaluation_command(
            root=root,
            workload_id=workload_id,
            dataset=args.dataset,
        )
        for root in (low_root, high_root)
        for workload_id in workloads
    ]
    if args.dry_run:
        print(" ".join(low_command))
        print(" ".join(high_command))
        for command in evaluation_commands:
            print(" ".join(command))
        return 0

    pair_root.mkdir(parents=True, exist_ok=True)
    low_result = subprocess.run(low_command, cwd=ROOT, check=False)
    high_result = subprocess.run(high_command, cwd=ROOT, check=False)
    evaluation_return_codes = []
    if low_result.returncode == 0 and high_result.returncode == 0:
        for command in evaluation_commands:
            completed = subprocess.run(command, cwd=ROOT, check=False)
            evaluation_return_codes.append(completed.returncode)
    audits = [
        _audit_workload(low_root, high_root, workload_id)
        for workload_id in workloads
    ]
    comparison_path = pair_root / "budget_compare.json"
    compare_command = [
        sys.executable,
        str(COMPARATOR),
        "--baseline-root",
        str(low_root),
        "--new-root",
        str(high_root),
        "--only",
        ",".join(workloads),
        "--baseline-label",
        f"low_{args.low_budget}",
        "--new-label",
        f"high_{args.high_budget}",
        "--output",
        str(comparison_path),
    ]
    evaluations_ok = (
        len(evaluation_return_codes) == len(evaluation_commands)
        and all(code == 0 for code in evaluation_return_codes)
    )
    compare_result = (
        subprocess.run(compare_command, cwd=ROOT, check=False)
        if evaluations_ok
        else None
    )
    payload = {
        "version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "controlled_prefix": True,
            "serial_dispatch": True,
            "call_key_derived_seeds": True,
            "append_only_evidence_merge": True,
            "shared_response_replay": True,
            "base_seed": args.seed,
        },
        "low_budget": args.low_budget,
        "high_budget": args.high_budget,
        "workloads": list(workloads),
        "low_root": str(low_root),
        "high_root": str(high_root),
        "commands": {
            "low": low_command,
            "high": high_command,
            "evaluations": evaluation_commands,
            "compare": compare_command,
        },
        "return_codes": {
            "low": low_result.returncode,
            "high": high_result.returncode,
            "evaluations": evaluation_return_codes,
            "compare": (
                compare_result.returncode
                if compare_result is not None
                else None
            ),
        },
        "call_audits": audits,
        "verified": (
            low_result.returncode == 0
            and high_result.returncode == 0
            and evaluations_ok
            and compare_result is not None
            and compare_result.returncode == 0
            and all(audit["verified"] for audit in audits)
        ),
    }
    manifest_path = pair_root / "paired_budget_manifest.json"
    manifest_path.write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, default=str))
    return 0 if payload["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
