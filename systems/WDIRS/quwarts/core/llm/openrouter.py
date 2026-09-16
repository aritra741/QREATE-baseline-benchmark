"""OpenRouter client. Every completion is metered through TokenLedger."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from quwarts.core.ledger import BudgetedCaller, TokenLedger

OPENROUTER_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "qwen/qwen-2.5-7b-instruct"


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def openrouter_client(api_key: str | None = None) -> OpenAI:
    key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    return OpenAI(base_url=OPENROUTER_URL, api_key=key, timeout=60.0)


def make_caller(
    ledger: TokenLedger,
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.1,
    max_tokens: int = 800,
    api_key: str | None = None,
) -> BudgetedCaller:
    client = openrouter_client(api_key)

    def complete(prompt: str, metadata: dict[str, Any]) -> tuple[str, int]:
        delay = 5.0
        response = None
        for attempt in range(8):
            try:
                response = client.chat.completions.create(
                    model=metadata.get("model") or model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    messages=[
                        {
                            "role": "system",
                            "content": metadata.get("system")
                            or "Extract only facts stated in the document. Return JSON.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                )
                break
            except (RateLimitError, APIStatusError, APITimeoutError, APIConnectionError) as exc:
                status = getattr(exc, "status_code", None)
                retryable = isinstance(exc, (RateLimitError, APITimeoutError, APIConnectionError)) or status in {400, 429, 502, 503}
                if not retryable:
                    raise
                if attempt == 7:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 120)
        assert response is not None
        text = (response.choices[0].message.content or "").strip()
        usage = getattr(response, "usage", None)
        tokens = 0
        if usage is not None:
            tokens = int(getattr(usage, "prompt_tokens", 0) or 0) + int(
                getattr(usage, "completion_tokens", 0) or 0
            )
        if tokens <= 0:
            tokens = max(1, (len(prompt) + len(text)) // 4)
        return text, tokens

    return BudgetedCaller(ledger, complete)
