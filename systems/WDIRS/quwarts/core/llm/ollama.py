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
from quwarts.core.retrieve_extract.tokens import count_tokens

DEFAULT_MODEL = "qwen2.5:7b-instruct"
DEFAULT_SYSTEM = "Extract only facts stated in the document. Return JSON."
CHAT_TEMPLATE_TOKENS = 13  # Qwen 2.5's <|im_start|>/<|im_end|> markers for a system and a user turn and the reply


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
        evaluated = int(data.get("prompt_eval_count") or 0)
        pout = int(data.get("eval_count") or 0)
        # Ollama reports only the prompt tokens it evaluated: a prefix reused from its cache (the system prompt and
        # instructions, or a document a slot has just read) is not counted. The prompt is counted here with the
        # exact Qwen 2.5 tokenizer instead (plus the chat template's role markers), and the larger count is kept.
        counted = count_tokens(body["messages"][0]["content"]) + count_tokens(prompt) + CHAT_TEMPLATE_TOKENS
        pin = max(evaluated, counted)
        if on_usage is not None:
            on_usage(prompt, {"input": pin, "output": pout, "ollama_prompt_eval_count": evaluated, "num_ctx": num_ctx,
                              # Ollama drops the start of a prompt longer than its window, without an error
                              "maybe_truncated": counted + max_tokens > num_ctx,
                              # the answer hit num_predict: its JSON may be cut off
                              "cut_off": data.get("done_reason") == "length",
                              "seconds": round(time.monotonic() - start, 2), "model": body["model"]})
        return text, pin + pout

    return BudgetedCaller(ledger or TokenLedger(theta=10**13), complete)
