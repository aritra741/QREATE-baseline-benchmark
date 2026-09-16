"""QuWARTS search eval: induce L from train SQL, search, score held-out SQL.

Gold CSVs are read only after the portfolio is frozen.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.ledger import TokenLedger
from quwarts.core.llm.openrouter import DEFAULT_MODEL, load_env_file, make_caller
from quwarts.core.models import SourceDocument
from quwarts.core.pipeline import compile_workload, serve_plans, synthesize
from quwarts.core.workload import mentions_from_sql
from quwarts.experiments.player_case80 import score_split, split_80_20
from quwarts.experiments.single_table_case80 import DATASETS, load_documents, load_queries

load_env_file(ROOT / ".env")

CORPORA = {
    "Player": ROOT / "source_data" / "Player",
    **{name: spec["txt"] for name, spec in DATASETS.items()},
}


def load_player_docs() -> list[dict[str, str]]:
    from quwarts.experiments.player_case80 import load_documents as load_player
    return load_player()


def documents_for(dataset: str) -> list[SourceDocument]:
    if dataset == "Player":
        raw = load_player_docs()
    elif dataset == "Med":
        from quwarts.experiments.med_case80 import load_documents as load_med
        raw = load_med()
    elif dataset == "CSPaper":
        from quwarts.experiments.cspaper_case80 import load_documents as load_cs
        cache = ROOT / "results" / "quwarts_cspaper_case80_eng" / "pdf_text"
        raw = load_cs(cache) if cache.exists() else [
            {"doc_id": p.name, "text": p.read_text(encoding="utf-8", errors="replace")}
            for p in sorted((ROOT / "source_data" / "CSPaper" / "txt").glob("*.txt"))
        ]
    else:
        raw = load_documents(dataset)
    return [
        SourceDocument(
            doc_id=row["doc_id"],
            text=row["text"],
            metadata={"entity": row.get("entity")} if row.get("entity") else {},
        )
        for row in raw
    ]


def queries_for(dataset: str) -> list[dict[str, str]]:
    if dataset == "Player":
        from quwarts.experiments.player_case80 import load_queries as load_player_q
        return load_player_q()
    if dataset == "Med":
        from quwarts.experiments.med_case80 import load_queries as load_med_q
        return load_med_q()
    if dataset == "CSPaper":
        from quwarts.experiments.cspaper_case80 import load_queries as load_cs_q
        return load_cs_q()
    return load_queries(dataset)


def docetl_tokens(dataset: str) -> int:
    slug = dataset.lower()
    total = 0
    for path in (
        ROOT / "results" / f"docetl_{slug}_case80" / "summary.json",
        ROOT / "results" / f"docetl_{slug}_case80_train" / "summary.json",
    ):
        if not path.is_file():
            continue
        payload = json.loads(path.read_text())
        total += int(payload.get("total_tokens") or 0)
    return total


def budget_from_docetl(dataset: str, fraction: float = 0.25) -> int:
    used = docetl_tokens(dataset)
    if used <= 0:
        raise SystemExit(f"no DocETL token total for {dataset}")
    return max(1, int(round(used * fraction)))


def gold_name(dataset: str) -> str:
    return DATASETS[dataset]["eval"] if dataset in DATASETS else dataset


def write_pred_db(rewrites: dict[str, str | None], sqlite_path: Path, dest: Path, rows: list[dict[str, str]]) -> Path:
    """Execute rewrites and stash per-query tables is unnecessary; score_split
    runs SQL on one DB. Point it at the synthesized sqlite and replace SQL
    with the rewrite when scoring.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    src = sqlite3.connect(sqlite_path)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
        dst.commit()
    finally:
        src.close()
        dst.close()
    return dest


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def frozen_score(train_report: dict[str, Any], frozen_ids: list[str]) -> dict[str, Any]:
    """Score a report on a fixed query set. Empty predictions count as zero."""

    by_id = {row["query_id"]: row for row in train_report.get("per_query", [])}
    scores: list[float] = []
    empty = 0
    for query_id in frozen_ids:
        item = by_id.get(query_id, {})
        if int(item.get("pred_rows") or 0) == 0:
            scores.append(0.0)
            empty += 1
        else:
            scores.append(float(item.get("official_accuracy") or 0))
    return {
        "n": len(frozen_ids),
        "empty": empty,
        "mean_official": _mean(scores),
    }


def diagnose_empties(
    train: list[dict[str, str]],
    train_report: dict[str, Any],
    dataset: str,
    rewrites: dict[str, Any] | None = None,
    frozen_ids: list[str] | None = None,
    other_report: dict[str, Any] | None = None,
    other_label: str = "other",
) -> dict[str, Any]:
    gold_path = ROOT / "results" / f"quwarts_{dataset.lower()}_case80" / "train_report.json"
    gold_per = {}
    if gold_path.is_file():
        gold_payload = json.loads(gold_path.read_text())
        gold_per = {row["query_id"]: row for row in gold_payload.get("per_query", [])}

    by_id = {row["query_id"]: row for row in train_report.get("per_query", [])}
    compiler_empty = []
    gold_empty = []
    empty_detail = []
    empty_with_join = []
    empty_with_in = []
    for row in train:
        item = by_id.get(row["query_id"], {})
        gold_item = gold_per.get(row["query_id"], {})
        pred_rows = int(item.get("pred_rows") or 0)
        gold_rows = int(gold_item.get("gold_rows") or item.get("gold_rows") or 0)
        if gold_rows == 0:
            gold_empty.append(row["query_id"])
        if pred_rows == 0:
            compiler_empty.append(row["query_id"])
            mentions = mentions_from_sql(row["sql"])
            if mentions["join_pairs"]:
                empty_with_join.append(row["query_id"])
            if mentions["in_attributes"]:
                empty_with_in.append(row["query_id"])
            empty_detail.append({
                "query_id": row["query_id"],
                "pack": row.get("pack"),
                "join_pairs": mentions["join_pairs"],
                "in_attributes": mentions["in_attributes"],
                "official": item.get("official_accuracy"),
                "gold_rows": gold_rows,
                "gold_official": gold_item.get("official_accuracy"),
            })

    both_nonempty = []
    compiler_on_gold_nonempty = []
    for row in train:
        item = by_id.get(row["query_id"], {})
        gold_item = gold_per.get(row["query_id"], {})
        pred_rows = int(item.get("pred_rows") or 0)
        gold_rows = int(gold_item.get("gold_rows") or 0)
        if gold_rows > 0:
            compiler_on_gold_nonempty.append(float(item.get("official_accuracy") or 0))
        if pred_rows > 0 and gold_rows > 0:
            both_nonempty.append({
                "query_id": row["query_id"],
                "compiler": float(item.get("official_accuracy") or 0),
                "gold": float(gold_item.get("official_accuracy") or 0),
            })

    yields: list[dict[str, Any]] = []
    if rewrites:
        from quwarts.core.rewrite import join_yield

        for row in train:
            plan = rewrites.get(row["query_id"]) or {}
            sql = plan.get("sql") if isinstance(plan, dict) else None
            path = plan.get("sqlite_path") if isinstance(plan, dict) else None
            if not sql or not path:
                continue
            yields.append(
                {
                    "query_id": row["query_id"],
                    "join_yield": join_yield(sql, path),
                    "empty": int((by_id.get(row["query_id"]) or {}).get("pred_rows") or 0) == 0,
                }
            )

    nonempty_ids = [
        row["query_id"]
        for row in train
        if int((by_id.get(row["query_id"]) or {}).get("pred_rows") or 0) > 0
    ]
    frozen = frozen_ids or nonempty_ids
    payload = {
        "gold_empty": len(gold_empty),
        "gold_empty_ids": gold_empty,
        "compiler_empty": len(compiler_empty),
        "empty_with_join": len(empty_with_join),
        "empty_with_in": len(empty_with_in),
        "empty_detail": empty_detail,
        "gold_n_nonempty": sum(1 for row in train if int(gold_per.get(row["query_id"], {}).get("gold_rows") or 0) > 0),
        "mean_compiler_on_gold_nonempty": _mean(compiler_on_gold_nonempty),
        "mean_compiler_on_common_nonempty": _mean([row["compiler"] for row in both_nonempty]),
        "mean_gold_on_common_nonempty": _mean([row["gold"] for row in both_nonempty]),
        "n_common_nonempty": len(both_nonempty),
        "nonempty_ids": nonempty_ids,
        "frozen": frozen_score(train_report, frozen),
        "join_yields": yields,
    }
    if other_report is not None:
        payload[f"frozen_{other_label}"] = frozen_score(other_report, frozen)
    return payload


def score_with_rewrites(
    rows: list[dict[str, str]],
    rewrites: dict[str, str | None],
    pred_db: Path,
    gold_tables: dict[str, list[dict[str, Any]]],
    dataset: str,
) -> dict[str, Any]:
    rewritten = []
    missing = 0
    for row in rows:
        plan = rewrites.get(row["query_id"]) or {}
        sql = plan.get("sql") if isinstance(plan, dict) else plan
        path = plan.get("sqlite_path") if isinstance(plan, dict) else None
        if not sql:
            missing += 1
        rewritten.append({**row, "pred_sql": sql, "pred_db": path or str(pred_db)})
    report = score_split(rewritten, pred_db, gold_tables, dataset=gold_name(dataset))
    report["rewrite_failures"] = missing
    return report


def run(args: argparse.Namespace) -> dict[str, Any]:
    from diagnostics.run_config_grid import load_ground_truth

    queries = queries_for(args.dataset)
    train, test = split_80_20(queries, args.seed)
    documents = documents_for(args.dataset)
    ledger = TokenLedger(theta=args.budget, seed=args.seed)
    caller = make_caller(ledger, model=args.model, max_tokens=1200)
    train_sql = {row["query_id"]: row["sql"] for row in train}
    mode = getattr(args, "mode", "search")
    print(
        f"{mode} {args.dataset} docs={len(documents)} train={len(train)} "
        f"test={len(test)} theta={args.budget}",
        flush=True,
    )
    out = Path(args.output)
    extract = mode != "rematerialize"
    if mode == "search":
        portfolio = synthesize(
            documents,
            train_sql,
            args.budget,
            seed=args.seed,
            artifact_root=out / "artifacts",
            caller=caller,
        )
    else:
        portfolio = compile_workload(
            documents,
            train_sql,
            args.budget,
            seed=args.seed,
            artifact_root=out / "artifacts",
            caller=caller,
            extract=extract,
        )
    if not portfolio.databases:
        raise SystemExit("produced no databases")
    pred_sqlite = Path(portfolio.databases[0].sqlite_path)
    pred_copy = write_pred_db({}, pred_sqlite, out / "synthesized.sqlite", train)
    train_rewrites = serve_plans(portfolio, train_sql)
    test_rewrites = serve_plans(portfolio, {row["query_id"]: row["sql"] for row in test})
    gold = load_ground_truth(gold_name(args.dataset))
    test_report = score_with_rewrites(test, test_rewrites, pred_copy, gold, args.dataset)
    train_report = score_with_rewrites(train, train_rewrites, pred_copy, gold, args.dataset)
    (out / "train_report.json").write_text(json.dumps(train_report, indent=2, default=str))
    frozen_path = out / "frozen_nonempty.json"
    other_path = out / "train_report_1db.json"
    frozen_ids = None
    other_report = None
    if frozen_path.is_file():
        frozen_ids = json.loads(frozen_path.read_text()).get("query_ids")
    else:
        frozen_ids = [
            row["query_id"]
            for row in train_report.get("per_query", [])
            if int(row.get("pred_rows") or 0) > 0
        ]
        frozen_path.write_text(json.dumps({"query_ids": frozen_ids, "source": "headline"}, indent=2))
    if other_path.is_file():
        other_report = json.loads(other_path.read_text())
    diagnosis = diagnose_empties(
        train,
        train_report,
        gold_name(args.dataset),
        rewrites=train_rewrites,
        frozen_ids=frozen_ids,
        other_report=other_report,
        other_label="1db",
    )
    (out / "diagnosis.json").write_text(json.dumps(diagnosis, indent=2, default=str))
    summary = {
        "dataset": args.dataset,
        "model": args.model,
        "seed": args.seed,
        "theta": args.budget,
        "tokens_spent": portfolio.tokens_spent,
        "logical_entities": portfolio.logical_schema.entity_types,
        "logical_attributes": [
            f"{item.entity_type}.{item.name}" for item in portfolio.logical_schema.attributes
        ],
        "mode": mode,
        "n_configs": len(portfolio.configurations),
        "expressions": [
            f"{item.alias}->{item.base_attributes}" for item in portfolio.logical_schema.expressions
        ],
        "cache_hit_rate": portfolio.cache_hit_rate,
        **test_report,
        "train": {
            "n_train": train_report["n_test"],
            "mean_official_accuracy": train_report["mean_official_accuracy"],
            "mean_structure_f2": train_report["mean_structure_f2"],
            "mean_cell_f1_05": train_report["mean_cell_f1_05"],
            "mean_query_score_05": train_report["mean_query_score_05"],
            "rewrite_failures": train_report.get("rewrite_failures"),
        },
    }
    (out / "report.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps({
        "dataset": args.dataset,
        "tokens_spent": summary["tokens_spent"],
        "logical_attributes": summary["logical_attributes"],
        "mean_official_accuracy": summary["mean_official_accuracy"],
        "mean_cell_f1_05": summary["mean_cell_f1_05"],
        "rewrite_failures": summary.get("rewrite_failures"),
        "train": summary["train"],
    }, indent=2), flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--budget", type=int, default=None)
    parser.add_argument("--budget-fraction", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--mode", choices=("compile", "search", "rematerialize"), default="compile")
    args = parser.parse_args()
    if args.budget is None:
        args.budget = budget_from_docetl(args.dataset, args.budget_fraction)
        print(
            f"theta={args.budget} ({args.budget_fraction:.0%} of DocETL "
            f"{docetl_tokens(args.dataset)} tokens)",
            flush=True,
        )
    if args.output is None:
        suffix = "compiler80" if args.mode == "compile" else "search80"
        args.output = ROOT / "results" / f"quwarts_{args.dataset.lower()}_{suffix}"
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
