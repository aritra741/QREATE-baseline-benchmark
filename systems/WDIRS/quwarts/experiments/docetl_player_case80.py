"""Run DocETL on the same Player 80/20 test split as QuWARTS."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))

from quwarts.core.llm.openrouter import load_env_file
from quwarts.experiments.player_case80 import (
    load_queries as load_player_queries,
    split_80_20,
)

load_env_file(ROOT / ".env")

RUNNER = ROOT / "systems" / "DocETL" / "run_player_grid_test_docetl.py"
EVALUATOR = ROOT / "systems" / "DocETL" / "evaluate_docetl_result_dir.py"


def _tau(mapping: dict, target: float = 0.05) -> float | None:
    if not mapping:
        return None
    for key, value in mapping.items():
        if abs(float(key) - target) < 1e-9:
            return float(value)
    return float(next(iter(mapping.values())))


def write_shim(test_rows: list[dict[str, str]], path: Path) -> Path:
    payload = {
        "per_config": {
            "player_case80": {
                "per_query": [
                    {"query_id": row["query_id"], "sql": row["sql"]}
                    for row in test_rows
                ]
            }
        }
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    path.with_name("test_workload.json").write_text(
        json.dumps([{"query_id": row["query_id"], "sql": row["sql"]} for row in test_rows], indent=2)
    )
    return path


def summarize(eval_path: Path, out_path: Path) -> dict:
    report = json.loads(eval_path.read_text())
    per_query = report.get("per_query") or {}
    official = []
    structure = []
    cell = []
    query_scores = []
    rows = []
    for query_id, item in per_query.items():
        acc = float(item.get("official_accuracy") or 0.0)
        official.append(acc)
        s = item.get("structure_fbeta_score")
        c = _tau(item.get("cell_f1") or {})
        q = _tau(item.get("query_score") or {})
        if s is not None:
            structure.append(float(s))
        if c is not None:
            cell.append(c)
        if q is not None:
            query_scores.append(q)
        rows.append({
            "query_id": query_id,
            "official_accuracy": acc,
            "structure_f2": s,
            "cell_f1_05": c,
            "query_score_05": q,
            "gold_rows": item.get("gold_row_count"),
            "pred_rows": item.get("predicted_row_count"),
        })

    def mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    summary = {
        "n_test": len(rows),
        "mean_official_accuracy": mean(official),
        "mean_structure_f2": mean(structure),
        "mean_cell_f1_05": mean(cell),
        "mean_query_score_05": mean(query_scores),
        "per_query": rows,
        "evaluation": str(eval_path),
    }
    out_path.write_text(json.dumps(summary, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        choices=("Player", "Med", "CSPaper", "Art", "Finan", "Legal"),
        default="Player",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--split", choices=("test", "train", "all"), default="test")
    parser.add_argument("--model", default="openrouter/qwen/qwen-2.5-7b-instruct")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--eval-only", action="store_true")
    args = parser.parse_args()

    if not os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit("OPENROUTER_API_KEY is not set")

    if args.dataset == "Med":
        from quwarts.experiments.med_case80 import load_queries as load_dataset_queries
        slug = "med"
    elif args.dataset == "CSPaper":
        from quwarts.experiments.cspaper_case80 import load_queries as load_dataset_queries
        slug = "cspaper"
    elif args.dataset in {"Art", "Finan", "Legal"}:
        from quwarts.experiments.single_table_case80 import load_queries as load_named_queries
        load_dataset_queries = lambda: load_named_queries(args.dataset)
        slug = args.dataset.lower()
    else:
        load_dataset_queries = load_player_queries
        slug = "player"
    train, test = split_80_20(load_dataset_queries(), args.seed)
    if args.split == "train":
        rows = train
    elif args.split == "all":
        rows = train + test
    else:
        rows = test
    if args.output is None:
        suffix = "" if args.split == "test" else f"_{args.split}"
        args.output = ROOT / "results" / f"docetl_{slug}_case80{suffix}"
    print(
        f"docetl case80 dataset={args.dataset} split={args.split} n={len(rows)} seed={args.seed}",
        flush=True,
    )
    for row in rows:
        print(f"  {row['query_id']}", flush=True)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    shim = write_shim(rows, out / "docetl_shim.json")
    workload = out / "test_workload.json"
    eval_path = out / "evaluation.json"

    if not args.eval_only:
        command = [
            sys.executable,
            str(RUNNER),
            "--grid-results",
            str(shim),
            "--out",
            str(out),
            "--dataset",
            args.dataset,
            "--model",
            args.model,
            "--ollama-base-url",
            "",
            "--api-key-env",
            "OPENROUTER_API_KEY",
            "--threads",
            str(args.threads),
        ]
        print(" ".join(command), flush=True)
        completed = subprocess.run(command, cwd=str(ROOT), check=False)
        if completed.returncode != 0:
            print(f"DocETL runner exited {completed.returncode}; scoring whatever finished", flush=True)

    eval_cmd = [
        sys.executable,
        str(EVALUATOR),
        "--result-dir",
        str(out),
        "--reference-workload",
        str(workload),
        "--dataset",
        args.dataset,
        "--output",
        str(eval_path),
    ]
    print(" ".join(eval_cmd), flush=True)
    evaluated = subprocess.run(eval_cmd, cwd=str(ROOT), check=False)
    if evaluated.returncode != 0:
        return evaluated.returncode
    summary = summarize(eval_path, out / "report.json")
    print(json.dumps({
        "mean_official_accuracy": summary["mean_official_accuracy"],
        "mean_structure_f2": summary["mean_structure_f2"],
        "mean_cell_f1_05": summary["mean_cell_f1_05"],
        "mean_query_score_05": summary["mean_query_score_05"],
        "n_test": summary["n_test"],
    }, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
