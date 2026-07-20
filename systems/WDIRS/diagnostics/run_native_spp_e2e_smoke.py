#!/usr/bin/env python3
"""Self-validating end-to-end smoke test for the native SPP pipeline."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

WDIRS_ROOT = Path(__file__).resolve().parents[1]
if str(WDIRS_ROOT) not in sys.path:
    sys.path.insert(0, str(WDIRS_ROOT))

from extractor import OllamaClient  # noqa: E402
from spp.native_backend import NativeSPPBackend, SourceDocument  # noqa: E402
from spp.nl2sql import make_nl2sql_compiler  # noqa: E402
from spp.serving import OfflineQueryServer  # noqa: E402
from spp.system import OfflineSynthesisSystem  # noqa: E402
from spp.workload_intent import make_budgeted_intent_analyzer  # noqa: E402


_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'-]*")
_STOPWORDS = {
    "about", "after", "all", "also", "among", "and", "are", "based", "been",
    "before", "below", "between", "both", "combination", "considering", "count",
    "dataset", "each", "either", "every", "for", "from", "group", "have", "held",
    "highest", "how", "into", "least", "lowest", "matching", "more", "most",
    "number", "one", "only", "other", "players", "player", "report", "team",
    "teams", "tell", "than", "that", "their", "there", "these", "they", "those",
    "total", "what", "when", "where", "which", "whose", "with", "won",
}


def _load_queries(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text())
    rows = payload.get("queries", []) if isinstance(payload, dict) else payload
    queries: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        if isinstance(row, str):
            query_id, text = f"q{index}", row
        else:
            query_id = str(row.get("query_id", f"q{index}"))
            text = str(row.get("text") or row.get("nl_query") or "")
        if not text.strip():
            raise ValueError(f"workload query {query_id!r} has no NL text")
        queries.append({"query_id": query_id, "text": text})
    if not queries:
        raise ValueError("workload is empty")
    if len({row["query_id"] for row in queries}) != len(queries):
        raise ValueError("workload query IDs must be unique")
    return queries


def _terms(text: str) -> set[str]:
    words = [word.lower() for word in _WORD.findall(text)]
    terms = {
        word for word in words if len(word) >= 4 and word not in _STOPWORDS
    }
    terms.update(
        f"{left} {right}"
        for left, right in zip(words, words[1:])
        if left not in _STOPWORDS and right not in _STOPWORDS
    )
    return terms


def select_representative_documents(
    corpus_dir: Path,
    queries: Iterable[dict[str, str]],
    *,
    max_documents: int,
) -> list[SourceDocument]:
    root = corpus_dir.expanduser().resolve()
    paths = sorted(root.glob("**/*.txt"))
    if not paths:
        raise ValueError(f"no .txt documents found under {root}")
    if max_documents < 1:
        raise ValueError("max_documents must be positive")

    texts = {
        path: path.read_text(encoding="utf-8", errors="replace") for path in paths
    }
    workload_terms = set().union(*(_terms(row["text"]) for row in queries))
    document_terms = {
        path: _terms(text) & workload_terms for path, text in texts.items()
    }
    frequencies = Counter(
        term for terms in document_terms.values() for term in terms
    )
    weights = {
        term: math.log((len(paths) + 1) / (count + 1)) + 1.0
        for term, count in frequencies.items()
    }

    selected: list[Path] = []
    # Exercise every source relation/directory before relevance-based filling.
    groups: dict[str, list[Path]] = {}
    for path in paths:
        relative = path.relative_to(root)
        group = relative.parts[0] if len(relative.parts) > 1 else "."
        groups.setdefault(group, []).append(path)
    for group in sorted(groups):
        selected.append(groups[group][0])
        if len(selected) >= max_documents:
            break

    covered = set().union(*(document_terms[path] for path in selected))
    remaining = [path for path in paths if path not in selected]
    while remaining and len(selected) < min(max_documents, len(paths)):
        best = max(
            remaining,
            key=lambda path: (
                sum(weights.get(term, 0.0) for term in document_terms[path] - covered),
                len(document_terms[path]),
                str(path),
            ),
        )
        selected.append(best)
        covered.update(document_terms[best])
        remaining.remove(best)

    return [
        SourceDocument(
            document_id=str(path.relative_to(root)),
            text=texts[path],
            metadata={"source_file": str(path)},
        )
        for path in selected
    ]


def _client(args: argparse.Namespace) -> OllamaClient:
    kwargs: dict[str, Any] = {
        "base_url": args.base_url,
        "model": args.model,
    }
    if args.api_key_env:
        api_key = os.getenv(args.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"API key environment variable is unset: {args.api_key_env}"
            )
        kwargs["api_key"] = api_key
    if args.disable_thinking:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    return OllamaClient(**kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run and verify a representative native-SPP smoke test."
    )
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--token-budget", type=int, default=2_000_000)
    parser.add_argument("--max-documents", type=int, default=24)
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--model", default="qwen2.5:7b-instruct")
    parser.add_argument("--api-key-env")
    parser.add_argument("--disable-thinking", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and print selected documents without calling an LLM.",
    )
    args = parser.parse_args()

    queries = _load_queries(args.workload)
    documents = select_representative_documents(
        args.corpus_dir,
        queries,
        max_documents=args.max_documents,
    )
    selection = {
        "query_count": len(queries),
        "document_count": len(documents),
        "documents": [document.document_id for document in documents],
    }
    if args.dry_run:
        print(json.dumps({"status": "DRY_RUN_PASS", **selection}, indent=2))
        return 0

    output = args.output.expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"smoke output is not empty: {output}")

    client = _client(args)
    backend = NativeSPPBackend(documents, client)
    system = OfflineSynthesisSystem(
        backend,
        make_nl2sql_compiler(client),
        intent_analyzer=make_budgeted_intent_analyzer(client),
    )
    result = system.synthesize(
        queries=queries,
        token_budget=args.token_budget,
        output_dir=output,
        observed_document_lengths=[len(document.text) for document in documents],
    )

    bundle = result.serving_manifest.parent
    server = OfflineQueryServer(bundle)
    query_results: dict[str, dict[str, Any]] = {}
    for query in queries:
        rows = server.execute(query["query_id"])
        query_results[query["query_id"]] = {
            "row_count": len(rows),
            "sample_rows": rows[:3],
        }

    manifest = json.loads(result.serving_manifest.read_text())
    compiled_ids = {row["query_id"] for row in manifest.get("queries", [])}
    expected_ids = {row["query_id"] for row in queries}
    token_summary = result.token_summary
    checks = {
        "sealed": (bundle / "SEALED").is_file(),
        "all_queries_compiled": compiled_ids == expected_ids,
        "all_queries_executed": set(query_results) == expected_ids,
        "budget_reconciled": token_summary["reserved_outstanding"] == 0,
        "within_budget": (
            token_summary["actual_spent"] <= token_summary["total_budget"]
        ),
    }
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "selection": selection,
        "serving_manifest": str(result.serving_manifest),
        "selected_config_ids": list(result.portfolio.selected_config_ids),
        "tokens": token_summary,
        "query_results": query_results,
    }
    report_path = output / "e2e_smoke_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    if report["status"] != "PASS":
        raise RuntimeError(f"end-to-end smoke checks failed; see {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
