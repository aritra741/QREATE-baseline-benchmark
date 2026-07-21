#!/usr/bin/env python3
"""Run the native offline SPP system (WDIRS is not a candidate/fallback)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

WDIRS_ROOT = Path(__file__).resolve().parents[1]
if str(WDIRS_ROOT) not in sys.path:
    sys.path.insert(0, str(WDIRS_ROOT))

from extractor import OllamaClient  # noqa: E402
from spp.budget_ledger import GlobalBudgetLedger  # noqa: E402
from spp.native_backend import (  # noqa: E402
    NativeSPPBackend,
    SourceDocument,
    infer_source_entity_vocabulary,
)
from spp.nl2sql import make_nl2sql_compiler  # noqa: E402
from spp.system import OfflineSynthesisSystem  # noqa: E402
from spp.workload_intent import make_budgeted_intent_analyzer  # noqa: E402


def _load_queries(path: Path) -> list[dict]:
    payload = json.loads(path.read_text())
    if isinstance(payload, dict):
        payload = payload.get("queries", [])
    queries = []
    for index, row in enumerate(payload):
        if isinstance(row, str):
            queries.append({"query_id": f"q{index}", "text": row})
        else:
            queries.append(
                {
                    "query_id": str(row.get("query_id", f"q{index}")),
                    "text": str(
                        row.get("text")
                        or row.get("nl_query")
                        or row.get("sql")
                        or ""
                    ),
                }
            )
    if not queries or any(not row["text"].strip() for row in queries):
        raise ValueError("workload contains an empty query")
    return queries


def _load_documents(corpus_dir: Path) -> list[SourceDocument]:
    root = corpus_dir.expanduser().resolve()
    documents = [
        SourceDocument(
            document_id=str(path.relative_to(root)),
            text=path.read_text(encoding="utf-8", errors="replace"),
            metadata={"source_file": str(path)},
        )
        for path in sorted(root.glob("**/*.txt"))
    ]
    if not documents:
        raise ValueError(f"no .txt documents found under {root}")
    return documents


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--token-budget", type=int, required=True)
    parser.add_argument("--quality-floor", type=float, default=0.0)
    parser.add_argument("--beta", type=float, default=1.0)
    parser.add_argument(
        "--intent-only",
        action="store_true",
        help="Analyze and save the workload IR without materializing databases.",
    )
    parser.add_argument("--base-url", "--ollama-url", dest="base_url")
    parser.add_argument("--model")
    parser.add_argument(
        "--api-key-env",
        default=None,
        help="Environment variable containing the hosted-provider API key.",
    )
    parser.add_argument(
        "--disable-thinking",
        action="store_true",
        help="Send DeepSeek-compatible non-thinking mode.",
    )
    args = parser.parse_args()

    client_kwargs = {}
    if args.base_url:
        client_kwargs["base_url"] = args.base_url
    if args.model:
        client_kwargs["model"] = args.model
    if args.api_key_env:
        api_key = os.getenv(args.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"API key environment variable is unset: {args.api_key_env}"
            )
        client_kwargs["api_key"] = api_key
    if args.disable_thinking:
        client_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    client = OllamaClient(**client_kwargs)
    documents = _load_documents(args.corpus_dir)
    queries = _load_queries(args.workload)
    entity_vocabulary = infer_source_entity_vocabulary(documents)
    intent_analyzer = make_budgeted_intent_analyzer(
        client,
        entity_vocabulary=entity_vocabulary,
    )
    if args.intent_only:
        output = args.output.expanduser().resolve()
        if output.exists() and any(output.iterdir()):
            raise FileExistsError(f"intent output is not empty: {output}")
        output.mkdir(parents=True, exist_ok=True)
        ledger = GlobalBudgetLedger(args.token_budget)
        intent = intent_analyzer(queries, ledger)
        payload = {
            "entity_vocabulary": list(entity_vocabulary),
            "workload_intent": asdict(intent),
            "tokens": ledger.summary(),
        }
        (output / "intent_preview.json").write_text(
            json.dumps(payload, indent=2, default=str)
        )
        ledger.save(output / "token_ledger.json")
        print(json.dumps(payload, indent=2, default=str))
        return 0
    backend = NativeSPPBackend(documents, client)
    system = OfflineSynthesisSystem(
        backend,
        make_nl2sql_compiler(client),
        intent_analyzer=intent_analyzer,
        beta=args.beta,
        quality_floor=args.quality_floor,
    )
    result = system.synthesize(
        queries=queries,
        token_budget=args.token_budget,
        output_dir=args.output,
        observed_document_lengths=[
            len(document.text) for document in backend.documents
        ],
    )
    summary = {
        "serving_manifest": str(result.serving_manifest),
        "selected_config_ids": list(result.portfolio.selected_config_ids),
        "candidate_count": result.candidate_count,
        "tokens": result.token_summary,
    }
    (Path(args.output) / "run_manifest.json").write_text(
        json.dumps(summary, indent=2)
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
