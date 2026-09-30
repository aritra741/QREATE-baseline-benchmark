"""Local model calls through Ollama's native API (``/api/chat``), for runs on a GPU node (e.g. CHPC).

Same contract as ``openrouter.make_caller``: a ``BudgetedCaller`` whose client returns ``(text, tokens)``.
``on_usage`` (optional) receives each call's record: input/output tokens as Ollama counts them, the
context size, whether the prompt may have been cut to fit it, and the call's seconds.

Why the native API and not Ollama's OpenAI-compatible one: the context window (``num_ctx``) can only be
set per request here. Ollama's default window is small (2048 tokens in many versions) and it drops the
start of a longer prompt without an error; our prompts carry up to ``V3["window_tokens"]`` (~10k) document
tokens plus the field list, so the window is set explicitly and every call is checked against it.

Environment: ``OLLAMA_HOST`` (``host:port`` or a URL; default 127.0.0.1:11434), ``OLLAMA_MODEL``
(default ``qwen2.5:7b-instruct``; ``qwen2.5:7b-instruct-fp16`` is the unquantized weights, closest to the
OpenRouter runs), ``OLLAMA_NUM_CTX`` (default 16384).
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable

from quwarts.core.ledger import BudgetedCaller, TokenLedger

DEFAULT_MODEL = "qwen2.5:7b-instruct"
DEFAULT_SYSTEM = "Extract only facts stated in the document. Return JSON."


def base_url(host: str | None = None) -> str:
    host = host or os.environ.get("OLLAMA_HOST") or "127.0.0.1:11434"
    if not host.startswith("http"):
        host = "http://" + host
    return host.rstrip("/")


def ping(host: str | None = None, timeout: float = 5.0) -> list[str]:
    """Names of the models the server has (raises if it is not reachable)."""

    import httpx

    r = httpx.get(base_url(host) + "/api/tags", timeout=timeout)
    r.raise_for_status()
    return [m["name"] for m in r.json().get("models", [])]


def make_caller(
    ledger: TokenLedger | None = None,
    *,
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 800,
    num_ctx: int | None = None,
    host: str | None = None,
    on_usage: Callable[[str, dict[str, Any]], None] | None = None,
    timeout: float = 900.0,
) -> BudgetedCaller:
    import httpx

    model = model or os.environ.get("OLLAMA_MODEL") or DEFAULT_MODEL
    num_ctx = int(num_ctx or os.environ.get("OLLAMA_NUM_CTX") or 16384)
    url = base_url(host) + "/api/chat"
    client = httpx.Client(timeout=timeout)

    def complete(prompt: str, metadata: dict[str, Any]) -> tuple[str, int]:
        body = {
            "model": metadata.get("model") or model,
            "messages": [{"role": "system", "content": metadata.get("system") or DEFAULT_SYSTEM},
                         {"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": num_ctx},
            "keep_alive": "60m",
        }
        delay, start, data = 5.0, time.monotonic(), None
        for attempt in range(8):
            try:
                r = client.post(url, json=body)
                if r.status_code in (429, 500, 502, 503) and attempt < 7:
                    raise httpx.HTTPStatusError("retry", request=r.request, response=r)
                r.raise_for_status()
                data = r.json()
                break
            except (httpx.TransportError, httpx.HTTPStatusError):
                if attempt == 7:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 120)
        text = ((data.get("message") or {}).get("content") or "").strip()
        pin = int(data.get("prompt_eval_count") or 0)
        pout = int(data.get("eval_count") or 0)
        if pin <= 0:  # a fully cached prompt can report 0 evaluated tokens
            pin = max(1, len(prompt) // 4)
        if on_usage is not None:
            on_usage(prompt, {"input": pin, "output": pout, "num_ctx": num_ctx,
                              # Ollama keeps the last num_ctx tokens of a longer prompt: flag any call at the limit
                              "maybe_truncated": pin + max_tokens >= num_ctx,
                              "seconds": round(time.monotonic() - start, 2), "model": body["model"]})
        return text, pin + pout

    return BudgetedCaller(ledger or TokenLedger(theta=10**13), complete)
