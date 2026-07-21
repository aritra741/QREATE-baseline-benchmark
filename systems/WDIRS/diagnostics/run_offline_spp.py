#!/usr/bin/env python3
"""Run the deployable offline SPP track on a SQL workload manifest."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import sqlglot

WDIRS_ROOT = Path(__file__).resolve().parents[1]
if str(WDIRS_ROOT) not in sys.path:
    sys.path.insert(0, str(WDIRS_ROOT))

from extractor import OllamaClient  # noqa: E402
from spp.corpus_subset import build_representative_subset  # noqa: E402
from spp.nl2sql import make_nl2sql_compiler  # noqa: E402
from spp.serving import OfflineQueryServer  # noqa: E402
from spp.system import OfflineSynthesisSystem  # noqa: E402
from spp.wdirs_backend import WDIRSPrimitiveBackend  # noqa: E402
from spp.workload_intent import (  # noqa: E402
    make_budgeted_intent_analyzer,
    schema_vocabulary_from_sql,
)
from wdirs_runner import WDIRSRunner  # noqa: E402


def _load_queries(path: Path) -> list[dict]:
    payload = json.loads(path.read_text())
    if isinstance(payload, dict):
        payload = payload.get("queries", [])
    if not isinstance(payload, list):
        raise ValueError("workload manifest must be a list or {'queries': [...]}")
    queries = []
    for index, row in enumerate(payload):
        if isinstance(row, str):
            queries.append({"query_id": f"q{index}", "sql": row})
        else:
            queries.append(
                {
                    "query_id": str(row.get("query_id", f"q{index}")),
                    "sql": str(row.get("sql") or row.get("text") or ""),
                }
            )
    if any(not row["sql"].strip() for row in queries):
        raise ValueError("every workload entry must contain SQL/text")
    return queries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument(
        "--schema-workload",
        type=Path,
        default=None,
        help="SQL training workload used by WDIRS for canonical extraction schema.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--token-budget", type=int, required=True)
    parser.add_argument("--quality-floor", type=float, default=0.0)
    parser.add_argument("--beta", type=float, default=1.0)
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument(
        "--projection-fastpath",
        action="store_true",
        help="Use WDIRS table-partitioned projection extraction.",
    )
    parser.add_argument(
        "--projection-fastpath-col-batch-size",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-documents-per-entity",
        type=int,
        default=None,
        help="Run an isolated relevance-ranked corpus subset smoke test.",
    )
    args = parser.parse_args()

    output = args.output.expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(output)
    scratch = output.parent / f".{output.name}_backend"
    scratch.mkdir(parents=True, exist_ok=False)
    os.environ["WDIRS_DB_PATH"] = str(scratch / "shared_extraction.sqlite")
    queries = _load_queries(args.workload)
    selected_documents: list[str] = []
    if args.max_documents_per_entity is not None:
        import config as config_module
        import wdirs_runner as runner_module

        subset_root, selected_documents = build_representative_subset(
            config_module.SOURCE_DATA_DIR / args.dataset,
            [query["sql"] for query in queries],
            scratch / "source_data",
            max_documents_per_entity=args.max_documents_per_entity,
        )
        config_module.SOURCE_DATA_DIR = subset_root
        runner_module.SOURCE_DATA_DIR = subset_root

    runner = WDIRSRunner(
        args.dataset,
        cache_dir=scratch / "cache",
        use_projection_fastpath=args.projection_fastpath,
        projection_fastpath_col_batch_size=(
            args.projection_fastpath_col_batch_size
        ),
    )
    try:
        client_kwargs = {}
        if args.base_url:
            client_kwargs["base_url"] = args.base_url
        if args.model:
            client_kwargs["model"] = args.model
        original_client = OllamaClient(**client_kwargs)
        runner.llm_client = original_client
        for component_name in (
            "extractor",
            "sieve_synthesizer",
            "entity_resolver",
            "entity_anchor",
            "lattice_planner",
        ):
            component = getattr(runner, component_name, None)
            if component is not None and hasattr(component, "llm_client"):
                component.llm_client = original_client

        schema_queries = []
        schema_vocabulary = None
        if args.schema_workload:
            schema_queries = [
                expression.sql()
                for expression in sqlglot.parse(
                    args.schema_workload.read_text(encoding="utf-8")
                )
                if expression is not None
            ]
            schema_vocabulary = schema_vocabulary_from_sql(
                schema_queries
            )
        backend = WDIRSPrimitiveBackend(
            runner,
            schema_workload_queries=schema_queries,
        )
        system = OfflineSynthesisSystem(
            backend,
            make_nl2sql_compiler(original_client),
            intent_analyzer=make_budgeted_intent_analyzer(
                original_client,
                entity_vocabulary=(
                    schema_vocabulary.entities
                    if schema_vocabulary
                    else ()
                ),
                attribute_vocabulary=(
                    schema_vocabulary.attributes
                    if schema_vocabulary
                    else None
                ),
                join_vocabulary=(
                    schema_vocabulary.joins
                    if schema_vocabulary
                    else ()
                ),
            ),
            beta=args.beta,
            quality_floor=args.quality_floor,
        )
        result = system.synthesize(
            queries=queries,
            token_budget=args.token_budget,
            output_dir=output,
        )
        run_manifest = {
            "dataset": args.dataset,
            "workload": str(args.workload.resolve()),
            "schema_workload": (
                str(args.schema_workload.resolve())
                if args.schema_workload
                else None
            ),
            "token_budget": args.token_budget,
            "candidate_count": result.candidate_count,
            "selected_config_ids": list(result.portfolio.selected_config_ids),
            "serving_manifest": str(result.serving_manifest),
            "token_summary": result.token_summary,
            "backend_scratch": str(scratch),
            "selected_source_documents": selected_documents,
        }
        if selected_documents:
            server = OfflineQueryServer(result.serving_manifest.parent)
            manifest = json.loads(result.serving_manifest.read_text())
            row_counts = {
                query["query_id"]: len(server.execute(query["query_id"]))
                for query in manifest["queries"]
            }
            nonempty = sum(count > 0 for count in row_counts.values())
            run_manifest["smoke_validation"] = {
                "executed_query_count": len(row_counts),
                "nonempty_query_count": nonempty,
                "row_counts": row_counts,
            }
            if nonempty == 0:
                raise RuntimeError(
                    "WDIRS-backed smoke produced no non-empty query results"
                )
        (output / "run_manifest.json").write_text(
            json.dumps(run_manifest, indent=2)
        )
        print(json.dumps(run_manifest, indent=2))
    finally:
        runner.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
