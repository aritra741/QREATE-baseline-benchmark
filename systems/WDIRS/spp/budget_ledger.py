"""Auditable end-to-end token ledger for deployable SPP synthesis.

Unlike the legacy row-count cost proxy, this ledger reserves real token
allowances before calls and reconciles them with provider-reported usage.
Every synthesis-time LLM call, including pilots, verification, retries and
failures, must pass through the same ledger.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional


class BudgetExhausted(RuntimeError):
    """Raised before dispatch when a reservation cannot fit."""


@dataclass
class TokenCharge:
    reservation_id: str
    stage: str
    operation: str
    reserved_tokens: int
    input_tokens: int = 0
    output_tokens: int = 0
    status: str = "reserved"
    config_id: Optional[str] = None
    query_id: Optional[str] = None
    shared_key: Optional[str] = None
    error: Optional[str] = None
    created_at: float = 0.0
    reconciled_at: Optional[float] = None

    @property
    def actual_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class GlobalBudgetLedger:
    """Thread-safe reservation and actual-usage ledger."""

    def __init__(self, total_tokens: int):
        if total_tokens < 0:
            raise ValueError("total_tokens cannot be negative")
        self.total_tokens = int(total_tokens)
        self._lock = threading.RLock()
        self._charges: Dict[str, TokenCharge] = {}
        self._shared_completed: Dict[str, str] = {}
        self._shared_reserved: Dict[str, str] = {}

    @property
    def actual_spent(self) -> int:
        with self._lock:
            return sum(c.actual_tokens for c in self._charges.values())

    @property
    def reserved_outstanding(self) -> int:
        with self._lock:
            return sum(
                c.reserved_tokens
                for c in self._charges.values()
                if c.status == "reserved"
            )

    @property
    def available(self) -> int:
        with self._lock:
            return self.total_tokens - self.actual_spent - self.reserved_outstanding

    def reserve(
        self,
        *,
        stage: str,
        operation: str,
        input_tokens: int,
        max_output_tokens: int,
        config_id: Optional[str] = None,
        query_id: Optional[str] = None,
        shared_key: Optional[str] = None,
    ) -> Optional[str]:
        """Reserve a worst-case call allowance.

        Returns ``None`` when an identical shared artifact was already produced;
        such cache hits consume no new tokens and are not charged twice.
        """
        requested = int(input_tokens) + int(max_output_tokens)
        if requested < 0:
            raise ValueError("token reservation cannot be negative")
        with self._lock:
            if shared_key and shared_key in self._shared_completed:
                return None
            if shared_key and shared_key in self._shared_reserved:
                raise RuntimeError(
                    f"shared artifact is already being produced: {shared_key}"
                )
            if requested > self.available:
                raise BudgetExhausted(
                    f"cannot reserve {requested} tokens for {stage}:{operation}; "
                    f"available={self.available}, total={self.total_tokens}"
                )
            reservation_id = uuid.uuid4().hex
            self._charges[reservation_id] = TokenCharge(
                reservation_id=reservation_id,
                stage=stage,
                operation=operation,
                reserved_tokens=requested,
                config_id=config_id,
                query_id=query_id,
                shared_key=shared_key,
                created_at=time.time(),
            )
            if shared_key:
                self._shared_reserved[shared_key] = reservation_id
            return reservation_id

    def reconcile(
        self,
        reservation_id: str,
        *,
        input_tokens: int,
        output_tokens: int,
        error: Optional[str] = None,
    ) -> None:
        """Replace a reservation with actual provider usage.

        Failed calls are still reconciled and charged for any reported usage.
        """
        with self._lock:
            charge = self._charges.get(reservation_id)
            if charge is None:
                raise KeyError(f"unknown reservation: {reservation_id}")
            if charge.status != "reserved":
                raise ValueError(f"reservation already reconciled: {reservation_id}")
            actual = int(input_tokens) + int(output_tokens)
            if actual < 0:
                raise ValueError("actual token usage cannot be negative")
            other_reserved = self.reserved_outstanding - charge.reserved_tokens
            exceeded = (
                self.actual_spent + actual + other_reserved > self.total_tokens
            )
            charge.input_tokens = int(input_tokens)
            charge.output_tokens = int(output_tokens)
            charge.error = error
            charge.status = "failed" if error else "completed"
            charge.reconciled_at = time.time()
            if charge.shared_key:
                self._shared_reserved.pop(charge.shared_key, None)
            if charge.shared_key and not error:
                self._shared_completed[charge.shared_key] = reservation_id
            if exceeded:
                raise BudgetExhausted(
                    "provider usage exceeded reservation and global budget"
                )

    def cancel(self, reservation_id: str, *, reason: str) -> None:
        """Cancel a call that was never dispatched; it incurs no usage."""
        with self._lock:
            charge = self._charges.get(reservation_id)
            if charge is None:
                raise KeyError(f"unknown reservation: {reservation_id}")
            if charge.status != "reserved":
                raise ValueError(f"reservation already finalized: {reservation_id}")
            charge.status = "cancelled"
            charge.error = reason
            charge.reconciled_at = time.time()
            if charge.shared_key:
                self._shared_reserved.pop(charge.shared_key, None)

    def can_complete(self, upper_bound_tokens: int) -> bool:
        return self.available >= int(upper_bound_tokens)

    def charges(self) -> List[TokenCharge]:
        with self._lock:
            return [TokenCharge(**asdict(c)) for c in self._charges.values()]

    def summary(self) -> dict:
        with self._lock:
            by_stage: Dict[str, int] = {}
            by_config: Dict[str, int] = {}
            by_query: Dict[str, int] = {}
            for charge in self._charges.values():
                actual = charge.actual_tokens
                by_stage[charge.stage] = by_stage.get(charge.stage, 0) + actual
                if charge.config_id:
                    by_config[charge.config_id] = (
                        by_config.get(charge.config_id, 0) + actual
                    )
                if charge.query_id:
                    by_query[charge.query_id] = (
                        by_query.get(charge.query_id, 0) + actual
                    )
            return {
                "total_budget": self.total_tokens,
                "actual_spent": self.actual_spent,
                "reserved_outstanding": self.reserved_outstanding,
                "available": self.available,
                "by_stage": dict(sorted(by_stage.items())),
                "by_config": dict(sorted(by_config.items())),
                "by_query": dict(sorted(by_query.items())),
                "charges": [asdict(c) for c in self._charges.values()],
            }

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.summary(), indent=2))
        tmp.replace(path)
