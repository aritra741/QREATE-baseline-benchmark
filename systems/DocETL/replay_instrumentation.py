"""Append-only DocETL call recorder. Applied at runtime; does not change outputs."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

LEDGER_ENV = "DOCETL_CALL_LEDGER"
QUERY_ENV = "DOCETL_QUERY_ID"
TABLE_ENV = "DOCETL_TABLE"

_lock = threading.Lock()
_tls = threading.local()
_state = {
    "applied": False,
    "original_call": None,
    "original_truncate": None,
    "spent": 0,
    "theta": 10**18,
    "stop": False,
    "n_calls": 0,
    "doc_texts": {},
}


def _hash(payload: Any) -> str:
    if isinstance(payload, (bytes, bytearray)):
        return hashlib.sha256(payload).hexdigest()
    if not isinstance(payload, str):
        payload = json.dumps(payload, sort_keys=True, default=str)
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


def _raw_text(response: Any) -> str:
    try:
        choice = response.choices[0]
        message = choice.message
        if getattr(message, "tool_calls", None):
            call = message.tool_calls[0]
            return str(getattr(call.function, "arguments", "") or "")
        return str(getattr(message, "content", "") or "")
    except Exception:
        return str(response)


def _count_qwen(text: str) -> int:
    try:
        from quwarts.core.retrieve_extract.tokens import count_tokens

        return count_tokens(text or "")
    except Exception:
        return max(0, len(text or "") // 4)


def _roles(messages: list[dict[str, Any]] | None) -> tuple[str, str]:
    system = ""
    user = ""
    for row in messages or []:
        role = str(row.get("role") or "")
        content = row.get("content")
        text = content if isinstance(content, str) else json.dumps(content, default=str)
        if role == "system":
            system += text
        elif role == "user":
            user += text
    return system, user


def _match_doc(user_text: str) -> str | None:
    marker = "Document:\n"
    blob = user_text
    if marker in user_text:
        blob = user_text.split(marker, 1)[1]
    docs: dict[str, str] = _state["doc_texts"]
    for doc_id, text in docs.items():
        if blob == text or text[:400] in blob or blob[:400] in text:
            return doc_id
    best = None
    best_n = 0
    head = blob[:200]
    for doc_id, text in docs.items():
        if head and head in text:
            return doc_id
        n = 0
        for size in (80, 160, 240):
            if blob[:size] and blob[:size] in text:
                n = size
        if n > best_n:
            best, best_n = doc_id, n
    return best


def _offsets(doc_id: str | None, included: str) -> dict[str, Any]:
    if not doc_id or doc_id not in _state["doc_texts"] or not included:
        return {"start": None, "end": None}
    text = _state["doc_texts"][doc_id]
    start = text.find(included[: min(len(included), 200)] if included else "")
    if start < 0:
        start = text.find(included[:80]) if len(included) >= 80 else -1
    if start < 0:
        return {"start": None, "end": None}
    return {"start": start, "end": min(len(text), start + len(included))}


def apply_instrumentation(*, theta: int, doc_texts: dict[str, str]) -> None:
    if _state["applied"]:
        _state["theta"] = theta
        _state["doc_texts"] = dict(doc_texts)
        return
    from docetl.operations.utils import api as api_mod
    from docetl.operations.utils import llm as llm_mod

    original_call = api_mod.APIWrapper._call_llm_with_cache
    original_truncate = llm_mod.truncate_messages

    def wrapped_truncate(messages, model, from_agent: bool = False):
        before = copy.deepcopy(messages)
        after = original_truncate(messages, model, from_agent)
        _tls.trunc = {
            "before": before,
            "after": copy.deepcopy(after),
            "model": model,
        }
        return after

    def wrapped_call(self, *args, **kwargs):
        if _state["stop"]:
            raise RuntimeError("budget_ceiling")
        started = time.time()
        error = None
        try:
            response = original_call(self, *args, **kwargs)
            return response
        except Exception as exc:
            error = exc
            response = None
            raise
        finally:
            _record_after(args, kwargs, response, started, error)

    llm_mod.truncate_messages = wrapped_truncate
    api_mod.truncate_messages = wrapped_truncate
    api_mod.APIWrapper._call_llm_with_cache = wrapped_call
    _state.update(
        {
            "applied": True,
            "original_call": original_call,
            "original_truncate": original_truncate,
            "theta": theta,
            "doc_texts": dict(doc_texts),
            "spent": 0,
            "stop": False,
            "n_calls": 0,
        }
    )


def _record_after(args, kwargs, response, started: float, error: Exception | None) -> None:
    model = args[0] if args else kwargs.get("model")
    op_type = args[1] if len(args) > 1 else kwargs.get("op_type")
    messages = args[2] if len(args) > 2 else kwargs.get("messages")
    schema = args[3] if len(args) > 3 else kwargs.get("output_schema")
    extra = kwargs.get("litellm_completion_kwargs") or (args[6] if len(args) > 6 else {})
    trunc = getattr(_tls, "trunc", None) or {}
    before_msgs = trunc.get("before") or (
        [{"role": "user", "content": ""}] + list(messages or [])
    )
    after_msgs = trunc.get("after") or before_msgs
    sys_b, user_b = _roles(before_msgs)
    sys_a, user_a = _roles(after_msgs)
    included = ""
    if "Document:\n" in user_a:
        included = user_a.split("Document:\n", 1)[1]
    elif "Document:\n" in user_b:
        included = user_b.split("Document:\n", 1)[1]
    else:
        included = user_a
    doc_id = _match_doc(user_b) or _match_doc(user_a)
    usage = _usage(response) if response is not None else {"prompt_tokens": 0, "completion_tokens": 0}
    prompt_toks = int(usage["prompt_tokens"] or 0)
    completion_toks = int(usage["completion_tokens"] or 0)
    raw = _raw_text(response) if response is not None else ""
    parsed = None
    parse_error = None
    if response is not None:
        try:
            from docetl.operations.utils.api import APIWrapper

            parsed = APIWrapper.parse_llm_response(
                APIWrapper.__new__(APIWrapper),
                response,
                schema=schema or {},
            )
        except Exception as exc:
            parse_error = str(exc)
    with _lock:
        _state["n_calls"] += 1
        call_index = _state["n_calls"]
        _state["spent"] += prompt_toks + completion_toks
        if _state["spent"] >= _state["theta"]:
            _state["stop"] = True
        spent = _state["spent"]
    rec = {
        "ts": time.time(),
        "latency_s": time.time() - started,
        "query_id": os.environ.get(QUERY_ENV),
        "table": os.environ.get(TABLE_ENV),
        "document_id": doc_id,
        "operator": "map:extract_fields",
        "stage": str(op_type or "map"),
        "call_index": call_index,
        "retry_index": 0,
        "model": model,
        "temperature": (extra or {}).get("temperature"),
        "completion_cap": (extra or {}).get("max_tokens"),
        "system_message": sys_a,
        "user_message": user_a,
        "system_message_before": sys_b if len(sys_b) <= 20000 else sys_b[:10000] + "\n…\n" + sys_b[-10000:],
        "user_message_before": user_b if len(user_b) <= 20000 else user_b[:10000] + "\n…\n" + user_b[-10000:],
        "system_sha256": _hash(sys_a),
        "user_sha256": _hash(user_a),
        "system_before_sha256": _hash(sys_b),
        "user_before_sha256": _hash(user_b),
        "chars_before": len(sys_b) + len(user_b),
        "chars_after": len(sys_a) + len(user_a),
        "model_tokens_before": _count_qwen(sys_b) + _count_qwen(user_b),
        "model_tokens_after": _count_qwen(sys_a) + _count_qwen(user_a),
        "included_document_text": included,
        "included_document_sha256": _hash(included),
        "source_offsets": _offsets(doc_id, included),
        "truncated": (sys_b, user_b) != (sys_a, user_a) or "tokens truncated" in (user_a + sys_a),
        "surviving_portion": "middle_cut" if "tokens truncated" in (user_a + sys_a) else "full_or_unmarked",
        "api_prompt_tokens": usage["prompt_tokens"],
        "api_completion_tokens": usage["completion_tokens"],
        "raw_response": raw,
        "raw_response_sha256": _hash(raw),
        "parsed_response": parsed,
        "parse_validation_failure": parse_error,
        "cache_status": "bypass",
        "provider_error": None if error is None else str(error),
        "output_schema": schema,
        "spent_after": spent,
        "bypass_cache": True,
    }
    dest = os.environ.get(LEDGER_ENV)
    if dest:
        path = Path(dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            with path.open("a") as handle:
                handle.write(json.dumps(rec, default=str) + "\n")


def spent() -> int:
    return int(_state["spent"])


def stopped() -> bool:
    return bool(_state["stop"])


def fixture_unchanged(original_result: Any, instrumented_result: Any) -> bool:
    return original_result == instrumented_result
