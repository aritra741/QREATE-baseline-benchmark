"""Run the contract-centric, workload-shared QuWARTS pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config as config_module
from extractor import OllamaClient
from spp.budget_ledger import GlobalBudgetLedger
from spp.contract_backend import ContractBackend
from spp.contract_extractor import route_documents_by_content
from spp.native_backend import SourceDocument
from spp.nl2sql import make_nl2sql_compiler
from spp.system import OfflineSynthesisSystem
from spp.workload_intent import (
    WorkloadIntent,
    _plan_contract_diagnostics,
    analyze_sql_contract_workload,
    make_budgeted_intent_analyzer,
    workload_intent_from_payload,
    workload_intent_to_payload,
)
from spp.workload_contract import compile_workload_contract

CONTRACT_INTENT_CACHE_VERSION = 5

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
    """Load text without exposing filesystem names to synthesis."""

    root = _assert_allowed_input(root, kind="source corpus")
    payloads = []
    for path in root.glob("**/*.txt"):
        text = path.read_text(encoding="utf-8", errors="replace")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        payloads.append((digest, text))
    payloads.sort()
    occurrences: dict[str, int] = {}
    documents = []
    for digest, text in payloads:
        occurrence = occurrences.get(digest, 0)
        occurrences[digest] = occurrence + 1
        documents.append(
            SourceDocument(
                document_id=f"doc-{digest[:24]}-{occurrence}",
                text=text,
                metadata={"content_sha256": digest},
            )
        )
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


def _load_sql_contract_queries(path: Path) -> list[dict[str, str]]:
    """Load benchmark query semantics without loading expected result data."""

    path = _assert_allowed_input(path, kind="SQL contract workload")
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("queries", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError(
            "SQL contract workload must be a list or {'queries': [...]}"
        )
    queries = []
    forbidden_names = {
        "answer",
        "answers",
        "expected",
        "expected_answer",
        "expected_rows",
        "gold",
        "ground_truth",
        "oracle",
        "result",
        "results",
    }
    for index, row in enumerate(rows):
        if isinstance(row, str):
            query_id, sql, text = f"q{index}", row, row
        elif isinstance(row, dict):
            forbidden_keys = {
                str(key)
                for key in row
                if str(key).lower() in forbidden_names
            }
            if forbidden_keys:
                raise ValueError(
                    "SQL contract workload contains answer-bearing fields: "
                    + ", ".join(sorted(forbidden_keys))
                )
            query_id = str(row.get("query_id", f"q{index}"))
            sql = str(row.get("sql") or row.get("sql_query") or "")
            text = str(row.get("text") or row.get("nl_query") or sql)
        else:
            raise ValueError(
                "SQL contract workload entries must be strings or objects"
            )
        if not sql.strip():
            raise ValueError(f"SQL contract query {query_id!r} is empty")
        queries.append({"query_id": query_id, "text": text, "sql": sql})
    if not queries:
        raise ValueError("SQL contract workload is empty")
    return queries


def _content_supported_entity_vocabulary(
    documents: list[SourceDocument],
    intent: WorkloadIntent,
) -> tuple[str, ...]:
    """Retain candidate entities independently supported by source content."""

    contract = compile_workload_contract(intent)
    routes = route_documents_by_content(documents, contract)
    return tuple(
        entity.name
        for entity in contract.entities
        if routes.get(entity.name)
    )


def _representative_documents(
    documents: list[SourceDocument],
    queries: list[dict[str, str]],
    *,
    limit: int,
    character_limit: int,
) -> list[SourceDocument]:
    """Build a path-agnostic, workload-ranked in-memory smoke subset."""
    if limit < 1 or character_limit < 1:
        raise ValueError("smoke subset limits must be positive")
    terms = {
        token.lower()
        for query in queries
        for token in re.findall(r"[A-Za-z][A-Za-z0-9'-]*", query["text"])
        if len(token) > 2
    }
    ranked = sorted(
        documents,
        key=lambda document: (
            -sum(term in document.text.lower() for term in terms),
            document.document_id,
        ),
    )
    return [
        SourceDocument(
            document.document_id,
            document.text[:character_limit],
            document.metadata,
        )
        for document in ranked[:limit]
    ]


def run_contract_pipeline(args: Any) -> int:
    """Execute NL-only or explicit SQL-contract native-interface synthesis."""
    started_at = datetime.now(timezone.utc)
    started_monotonic = time.monotonic()
    output = Path(args.output).expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(output)

    intent_source = str(getattr(args, "intent_source", "nl"))
    if intent_source not in {"nl", "sql-contract"}:
        raise ValueError(f"unsupported contract intent source: {intent_source}")
    controlled_prefix = bool(
        getattr(args, "controlled_prefix", False)
    )
    if controlled_prefix:
        if getattr(args, "seed", None) is None:
            raise ValueError("--controlled-prefix requires --seed")
        required_environment = {
            "MAX_PARALLEL_REQUESTS": "1",
            "SPP_CONTRACT_MAX_WORKERS": "1",
            "SPP_INTENT_MAX_WORKERS": "1",
            "SPP_APPEND_ONLY_EVIDENCE": "1",
            "SPP_CONTROLLED_PREFIX": "1",
        }
        mismatches = {
            name: os.getenv(name)
            for name, expected in required_environment.items()
            if os.getenv(name) != expected
        }
        if mismatches:
            raise ValueError(
                "controlled-prefix environment is incomplete: "
                + ", ".join(
                    f"{name}={value!r}"
                    for name, value in sorted(mismatches.items())
                )
            )
    source_root = Path(config_module.SOURCE_DATA_DIR) / str(args.dataset)
    documents = _load_documents(source_root)
    queries = (
        _load_sql_contract_queries(args.workload)
        if intent_source == "sql-contract"
        else _load_queries(args.workload)
    )
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
    if getattr(args, "seed", None) is not None:
        client_kwargs["seed"] = int(args.seed)
    if getattr(args, "llm_replay_path", None) is not None:
        client_kwargs["replay_path"] = args.llm_replay_path
    client = OllamaClient(**client_kwargs)
    if intent_source == "sql-contract":
        exact_sql_intent = analyze_sql_contract_workload(queries)

        def analyze_selected_intent(_workload, _ledger):
            return exact_sql_intent

    else:
        analyze_uncached_intent = make_budgeted_intent_analyzer(
            client,
            entity_vocabulary=(),
            attribute_vocabulary=None,
            join_vocabulary=(),
            intent_max_workers=args.intent_workers,
        )

        def analyze_selected_intent(workload, ledger):
            draft = analyze_uncached_intent(workload, ledger)
            content_entities = _content_supported_entity_vocabulary(
                documents,
                draft,
            )
            draft_entities = tuple(
                dict.fromkeys(
                    entity
                    for requirement in draft.requirements
                    for entity in requirement.entities
                )
            )
            if content_entities and set(content_entities) != set(
                draft_entities
            ):
                analyze_bounded_intent = make_budgeted_intent_analyzer(
                    client,
                    entity_vocabulary=content_entities,
                    attribute_vocabulary=None,
                    join_vocabulary=(),
                    intent_max_workers=args.intent_workers,
                )
                intent = analyze_bounded_intent(workload, ledger)
            else:
                intent = draft
            return replace(
                intent,
                analysis_diagnostics={
                    **dict(intent.analysis_diagnostics),
                    "content_entity_vocabulary": {
                        "policy": "candidate_contract_content_support",
                        "uses_document_identifiers": False,
                        "draft_entities": list(draft_entities),
                        "supported_entities": list(content_entities),
                    },
                },
            )

    if args.intent_only:
        output.mkdir(parents=True, exist_ok=True)
        ledger = GlobalBudgetLedger(args.token_budget)
        intent = analyze_selected_intent(queries, ledger)
        (output / "workload_intent.json").write_text(
            json.dumps(
                workload_intent_to_payload(intent),
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        ledger.save(output / "budget_ledger.json")
        contract_failures = {
            requirement.query_id: list(violations)
            for requirement in intent.requirements
            if (
                violations := _plan_contract_diagnostics(requirement)
            )
        }
        print(
            json.dumps(
                {
                    "pipeline": "contract",
                    "intent_source": intent_source,
                    "intent_only": True,
                    "requirements": len(intent.requirements),
                    "output": str(output),
                    "tokens": ledger.summary(),
                    "plan_contract_failures": contract_failures,
                },
                indent=2,
                default=str,
            )
        )
        if contract_failures:
            raise ValueError(
                "intent-only workload plan contract failed: "
                + "; ".join(
                    f"{query_id}: {', '.join(violations)}"
                    for query_id, violations
                    in sorted(contract_failures.items())
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
    intent_cache = scratch_dir / "canonical_workload_intent.json"
    intent_fingerprint = hashlib.sha256(
        json.dumps(
            {
                "cache_version": CONTRACT_INTENT_CACHE_VERSION,
                "intent_source": intent_source,
                "queries": queries,
                "model": args.model,
                "intent_workers": args.intent_workers,
                "base_seed": getattr(args, "seed", None),
                "controlled_prefix": controlled_prefix,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    def intent_analyzer(workload, ledger):
        if intent_cache.exists():
            cached = json.loads(intent_cache.read_text(encoding="utf-8"))
            if (
                cached.get("cache_version")
                == CONTRACT_INTENT_CACHE_VERSION
                and cached.get("fingerprint") == intent_fingerprint
            ):
                return workload_intent_from_payload(cached["intent"])
        intent = analyze_selected_intent(workload, ledger)
        temporary = intent_cache.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "cache_version": CONTRACT_INTENT_CACHE_VERSION,
                    "fingerprint": intent_fingerprint,
                    "intent": workload_intent_to_payload(intent),
                },
                indent=2,
                sort_keys=True,
                default=str,
            ),
            encoding="utf-8",
        )
        temporary.replace(intent_cache)
        return intent

    backend = ContractBackend(
        documents,
        client,
        scratch_dir=scratch_dir,
        use_bulk_extraction=True,
        semantic_document_routing=True,
        bulk_column_batch_size=args.bulk_column_batch_size,
        bulk_min_column_coverage=args.bulk_min_column_coverage,
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
    response_cache_path = client.save_response_cache(
        output / "llm_response_cache.jsonl"
    )
    call_audit = client.call_audit()
    call_audit_payload = {
        "version": 1,
        "seed_policy": (
            "sha256(base_seed + NUL + call_key), first 32 bits masked to 31"
            if getattr(args, "seed", None) is not None
            else "provider default"
        ),
        "base_seed": getattr(args, "seed", None),
        "controlled_prefix": controlled_prefix,
        "calls": call_audit,
    }
    call_audit_text = json.dumps(
        call_audit_payload,
        indent=2,
        sort_keys=True,
        default=str,
    )
    call_audit_path = output / "llm_call_manifest.json"
    call_audit_path.write_text(call_audit_text, encoding="utf-8")
    call_sequence_digest = hashlib.sha256(
        json.dumps(
            [
                {
                    "request_key": row.get("request_key"),
                    "seed": row.get("seed"),
                    "prompt_sha256": row.get("prompt_sha256"),
                    "response_sha256": row.get("response_sha256"),
                }
                for row in call_audit
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    summary = {
        "pipeline": "contract",
        "intent_source": intent_source,
        "dataset": args.dataset,
        "workload": str(Path(args.workload).resolve()),
        "serving_manifest": str(result.serving_manifest),
        "selected_config_ids": list(result.portfolio.selected_config_ids),
        "candidate_count": result.candidate_count,
        "tokens": result.token_summary,
        "controlled_prefix": {
            "enabled": controlled_prefix,
            "base_seed": getattr(args, "seed", None),
            "call_count": len(call_audit),
            "call_sequence_sha256": call_sequence_digest,
            "call_manifest": str(call_audit_path),
            "response_cache": str(response_cache_path),
            "replay_source": (
                str(Path(args.llm_replay_path).expanduser().resolve())
                if getattr(args, "llm_replay_path", None) is not None
                else None
            ),
            "append_only_evidence": (
                os.getenv("SPP_APPEND_ONLY_EVIDENCE", "0") == "1"
            ),
        },
        "intent_cache": {
            "version": CONTRACT_INTENT_CACHE_VERSION,
            "fingerprint": intent_fingerprint,
            "path": str(intent_cache),
        },
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
