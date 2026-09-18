"""Response cache keyed by plan-and-input hash. Hits do not spend tokens."""

from __future__ import annotations

import hashlib
from typing import Any

from quwarts.core.ledger import BudgetedCaller


class ResponseCache:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.hits = 0
        self.misses = 0

    def key(self, prompt: str, purpose: str, **metadata: Any) -> str:
        payload = "|".join(
            [
                purpose,
                str(metadata.get("plan") or ""),
                str(metadata.get("system") or ""),
                str(metadata.get("model") or ""),
                prompt,
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def complete(self, caller: BudgetedCaller, prompt: str, purpose: str, **metadata: Any) -> str:
        digest = self.key(prompt, purpose, **metadata)
        if digest in self.store:
            self.hits += 1
            return self.store[digest]
        text = caller.complete(prompt, purpose=purpose, **metadata)
        self.store[digest] = text
        self.misses += 1
        return text


class CachedCaller:
    """BudgetedCaller-compatible wrapper. Same prompt+plan hash is reused."""

    def __init__(self, caller: BudgetedCaller, cache: ResponseCache, plan: str = "") -> None:
        self.ledger = caller.ledger
        self._inner = caller
        self._cache = cache
        self.plan = plan

    def bind(self, plan: str) -> "CachedCaller":
        return CachedCaller(self._inner, self._cache, plan=plan)

    def complete(self, prompt: str, purpose: str, **metadata: Any) -> str:
        if self.plan and "plan" not in metadata:
            metadata = {**metadata, "plan": self.plan}
        return self._cache.complete(self._inner, prompt, purpose, **metadata)
