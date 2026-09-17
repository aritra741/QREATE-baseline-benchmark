"""Single token ledger. Every model call must go through ``TokenLedger.spend``."""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from typing import Any, Callable


class BudgetExhausted(RuntimeError):
    """Raised when a spend would exceed ``theta``."""


@dataclass
class SpendRecord:
    purpose: str
    tokens: int
    metadata: dict[str, Any]


@dataclass
class TokenLedger:
    """Global token budget. ``theta`` is the cap; ``seed`` is recorded for replay."""

    theta: int
    seed: int = 0
    spent: int = 0
    records: list[SpendRecord] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def remaining(self) -> int:
        return self.theta - self.spent

    def spend(self, tokens: int, purpose: str, **metadata: Any) -> None:
        if tokens < 0:
            raise ValueError("tokens must be non-negative")
        with self._lock:
            if self.spent + tokens > self.theta:
                raise BudgetExhausted(
                    f"spend {tokens} for {purpose} exceeds remaining {self.remaining()}"
                )
            self.spent += tokens
            self.records.append(SpendRecord(purpose=purpose, tokens=tokens, metadata=dict(metadata)))

    def snapshot(self) -> dict[str, Any]:
        return {
            "theta": self.theta,
            "seed": self.seed,
            "spent": self.spent,
            "records": [
                {"purpose": row.purpose, "tokens": row.tokens, "metadata": row.metadata}
                for row in self.records
            ],
        }

    def fingerprint(self) -> str:
        payload = json.dumps(self.snapshot(), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class BudgetedCaller:
    """The only allowed way to invoke a model. No module talks to a client directly."""

    def __init__(self, ledger: TokenLedger, client: Callable[[str, dict[str, Any]], tuple[str, int]]):
        self.ledger = ledger
        self.client = client

    def complete(self, prompt: str, purpose: str, **metadata: Any) -> str:
        text, tokens = self.client(prompt, metadata)
        self.ledger.spend(tokens, purpose, **metadata)
        return text
