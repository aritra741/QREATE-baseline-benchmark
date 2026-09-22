"""
PREPARED ONLY — do not import, apply, or execute.

Future-run telemetry hook for missing DocETL facts. It records one JSONL
line per `_call_llm_with_cache` return. It must not change prompts, plans,
batching, ordering, caching, model arguments, or outputs.

Intended attach point (not applied):
    systems/docetl-main/docetl/operations/utils/api.py
    APIWrapper._call_llm_with_cache

The existing token patch in
    systems/DocETL/test_player_query_awareness_trend_docetl.py
    (patch_docetl_for_token_tracking)
already wraps this method. A future run should compose this recorder
*after* the original call returns, using the same response object.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any


LEDGER_ENV = "DOCETL_CALL_LEDGER"
# Default unused path; only written if DOCETL_CALL_LEDGER is set at runtime.
DEFAULT_LEDGER = Path("/dev/null")


def _prompt_hash(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    payload = json.dumps(
        {"args_repr": [type(a).__name__ for a in args], "keys": sorted(kwargs)},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _usage(response: Any) -> dict[str, int | None]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {"prompt_tokens": None, "completion_tokens": None}
    if isinstance(usage, dict):
        return {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
        }
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
    }


def record_call(
    *,
    query_id: str | None,
    table: str | None,
    operator: str,
    response: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    work_dir: str | None,
) -> None:
    """Append-only. Never mutates response, args, or kwargs."""
    dest = os.environ.get(LEDGER_ENV)
    if not dest:
        return
    rec = {
        "ts": time.time(),
        "query_id": query_id,
        "table": table,
        "operator": operator,
        "work_dir": work_dir,
        "cwd": os.getcwd(),
        "prompt_hash": _prompt_hash(args, kwargs),
        "model": kwargs.get("model") or getattr(response, "model", None),
        **_usage(response),
        "n_messages": None,
        "documents_in_payload": "unavailable_without_parsing_messages",
        "retry_index": "unavailable_unless_caller_passes_it",
    }
    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(rec, default=str) + "\n")


# Apply recipe (not executed):
#
# original = APIWrapper._call_llm_with_cache
# def wrapped(self, *args, **kwargs):
#     response = original(self, *args, **kwargs)
#     record_call(
#         query_id=os.environ.get("DOCETL_QUERY_ID"),
#         table=os.environ.get("DOCETL_TABLE"),
#         operator="map:extract_fields",
#         response=response,
#         args=args,
#         kwargs=kwargs,
#         work_dir=os.getcwd(),
#     )
#     return response
# APIWrapper._call_llm_with_cache = wrapped
#
# Also snapshot, once per (query, table), before pipeline.run:
#   json of input doc_ids and char lengths (dataset snapshot).
# Also after SQLite:
#   n_rows_in, n_rows_out (already reconstructable from query_tables + extract_fields).
#
# Do not set bypass_cache differently. Do not change MapOp config.
