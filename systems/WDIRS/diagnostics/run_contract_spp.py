"""Run the contract-centric, workload-shared QuWARTS pipeline."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config as config_module
from extractor import OllamaClient
from spp.budget_ledger import GlobalBudgetLedger
from spp.contract_backend import ContractBackend
from spp.native_backend import SourceDocument, infer_source_entity_vocabulary
from spp.nl2sql import make_nl2sql_compiler
from spp.system import OfflineSynthesisSystem
from spp.workload_intent import (
    make_budgeted_intent_analyzer,
    workload_intent_to_payload,
)

_FORBIDDEN_INPUT_PARTS = {
    "answers",
    "data",
    "evaluation",
    "ground_truth",
    "oracle",
    "reference",
}


def _assert_allowed_input(path: Path, *, kind: str) -> Path:
    """Reject known benchmark-answer channels before any file is opened."""
    resolved = Path(path).expanduser().resolve()
    parts = {part.lower() for part in resolved.parts}
    forbidden = sorted(parts & _FORBIDDEN_INPUT_PARTS)
    if forbidden:
        raise ValueError(
            f"{kind} path crosses forbidden synthesis namespace(s): "
            f"{', '.join(forbidden)}"
        )
    if resolved.suffix.lower() == ".csv":
        raise ValueError(f"{kind} must not be loaded from CSV")
    return resolved


def _load_documents(root: Path) -> list[SourceDocument]:
    root = _assert_allowed_input(root, kind="source corpus")
    documents = [
        SourceDocument(
            document_id=str(path.relative_to(root)),
            text=path.read_text(encoding="utf-8", errors="replace"),
            metadata={"source_file": str(path)},
        )
        for path in sorted(root.glob("**/*.txt"))
    ]
    if not documents:
        raise ValueError(f"no source documents found under {root}")
    return documents


def _load_queries(path: Path) -> list[dict[str, str]]:
    path = _assert_allowed_input(path, kind="NL workload")
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("queries", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("workload must be a list or {'queries': [...]}")
    queries = []
    for index, row in enumerate(rows):
        if isinstance(row, str):
            query_id, text = f"q{index}", row
        elif isinstance(row, dict):
            forbidden_keys = {
                key
                for key in row
                if str(key).lower()
                in {
                    "answer",
                    "expected",
                    "expected_answer",
                    "gold",
                    "oracle",
                    "reference_sql",
                    "sql",
                }
            }
            if forbidden_keys:
                raise ValueError(
                    "NL-only workload contains forbidden fields: "
                    + ", ".join(sorted(map(str, forbidden_keys)))
                )
            query_id = str(row.get("query_id", f"q{index}"))
            text = str(row.get("text") or row.get("nl_query") or "")
        else:
            raise ValueError("workload entries must be strings or objects")
        if not text.strip():
            raise ValueError(f"workload query {query_id!r} is empty")
        queries.append({"query_id": query_id, "text": text})
    if not queries:
        raise ValueError("workload is empty")
    return queries


def _representative_documents(
    documents: list[SourceDocument],
    queries: list[dict[str, str]],
    *,
    limit: int,
    character_limit: int,
) -> list[SourceDocument]:
    """Build a deterministic, workload-ranked in-memory smoke subset."""
    if limit < 1 or character_limit < 1:
        raise ValueError("smoke subset limits must be positive")
    terms = {
        token.lower()
        for query in queries
        for token in re.findall(r"[A-Za-z][A-Za-z0-9'-]*", query["text"])
        if len(token) > 2
    }
    by_partition: dict[str, list[SourceDocument]] = {}
    for document in documents:
        partition = document.document_id.replace("\\", "/").split("/", 1)[0]
        by_partition.setdefault(partition, []).append(document)
    selected: list[SourceDocument] = []
    for partition in sorted(by_partition):
        ranked = sorted(
            by_partition[partition],
            key=lambda document: (
                -sum(term in document.text.lower() for term in terms),
                document.document_id,
            ),
        )
        selected.extend(
            SourceDocument(
                document.document_id,
                document.text[:character_limit],
                document.metadata,
            )
            for document in ranked[:limit]
        )
    return selected


def run_contract_pipeline(args: Any) -> int:
    """Execute using only NL workload, source corpus, model, and budget."""
    started_at = datetime.now(timezone.utc)
    started_monotonic = time.monotonic()
    output = Path(args.output).expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(output)

    source_root = Path(config_module.SOURCE_DATA_DIR) / str(args.dataset)
    documents = _load_documents(source_root)
    queries = _load_queries(args.workload)
    if args.max_documents_per_entity is not None:
        documents = _representative_documents(
            documents,
            queries,
            limit=args.max_documents_per_entity,
            character_limit=args.max_document_characters,
        )
    client_kwargs = {}
    if args.base_url:
        client_kwargs["base_url"] = args.base_url
    if args.model:
        client_kwargs["model"] = args.model
    client = OllamaClient(**client_kwargs)
    intent_analyzer = make_budgeted_intent_analyzer(
        client,
        entity_vocabulary=infer_source_entity_vocabulary(documents),
        attribute_vocabulary=None,
        join_vocabulary=(),
        intent_max_workers=args.intent_workers,
    )
    if args.intent_only:
        output.mkdir(parents=True, exist_ok=True)
        ledger = GlobalBudgetLedger(args.token_budget)
        intent = intent_analyzer(queries, ledger)
        (output / "workload_intent.json").write_text(
            json.dumps(
                workload_intent_to_payload(intent),
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        ledger.save(output / "budget_ledger.json")
        print(
            json.dumps(
                {
                    "pipeline": "contract",
                    "intent_only": True,
                    "requirements": len(intent.requirements),
                    "output": str(output),
                    "tokens": ledger.summary(),
                },
                indent=2,
                default=str,
            )
        )
        return 0
    scratch_parent = (
        Path(args.scratch_dir).expanduser().resolve()
        if args.scratch_dir is not None
        else output.parent
    )
    scratch_dir = scratch_parent / f".{output.name}_contract"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    backend = ContractBackend(
        documents,
        client,
        scratch_dir=scratch_dir,
    )
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
        output_dir=output,
        observed_document_lengths=[
            len(document.text) for document in documents
        ],
    )
    finished_at = datetime.now(timezone.utc)
    summary = {
        "pipeline": "contract",
        "dataset": args.dataset,
        "workload": str(Path(args.workload).resolve()),
        "serving_manifest": str(result.serving_manifest),
        "selected_config_ids": list(result.portfolio.selected_config_ids),
        "candidate_count": result.candidate_count,
        "tokens": result.token_summary,
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": finished_at.isoformat(),
        "wall_clock_seconds": time.monotonic() - started_monotonic,
        "portfolio": asdict(result.portfolio),
    }
    (output / "run_manifest.json").write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, default=str))
    return 0
