"""Budget-aware semantic verification for extracted relational cells."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import os
from typing import Dict, Mapping, Optional, Sequence, Tuple

from spp.budget_ledger import BudgetExhausted, GlobalBudgetLedger
from spp.budgeted_llm import BudgetedLLMClient

logger = logging.getLogger(__name__)

_VERIFIER_VERSION = 2
_ALLOWED_STATUSES = {
    "entailed",
    "contradicted",
    "unsupported",
    "abstain",
}


@dataclass(frozen=True)
class CellClaim:
    claim_id: str
    relation: str
    row_identity: str
    identity: str
    attribute: str
    value: object
    semantic_types: Tuple[str, ...]
    query_hints: Tuple[Tuple[str, str], ...]
    evidence_excerpt: str
    derivation_lineage: Mapping[str, object] = field(default_factory=dict)

    @property
    def hypothesis(self) -> str:
        attribute = self.attribute.replace("_", " ")
        return (
            f"{self.identity}'s {attribute} is "
            f"{json.dumps(self.value, ensure_ascii=False)}."
        )

    def prompt_payload(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "entity": self.relation,
            "identity": self.identity,
            "attribute": self.attribute,
            "value": self.value,
            "semantic_types": list(self.semantic_types),
            "natural_language_query_hints": dict(self.query_hints),
            "evidence_excerpt": self.evidence_excerpt,
            "derivation_lineage": dict(self.derivation_lineage),
            "hypothesis": self.hypothesis,
        }

    @property
    def nli_premise(self) -> str:
        if not self.derivation_lineage:
            return self.evidence_excerpt
        return (
            f"Source evidence: {self.evidence_excerpt}\n"
            "Deterministically checked derivation lineage: "
            + json.dumps(
                dict(self.derivation_lineage),
                ensure_ascii=False,
                sort_keys=True,
            )
        )


@dataclass(frozen=True)
class VerificationDecision:
    claim_id: str
    status: str
    confidence: float
    method: str
    reason: str = ""

    @property
    def accepted(self) -> bool:
        return self.status == "entailed"


@dataclass(frozen=True)
class VerificationReport:
    decisions: Tuple[VerificationDecision, ...]
    llm_claims: int
    nli_claims: int
    unverified_claims: int
    verifier_version: int = _VERIFIER_VERSION


def _parse_rows(response: str) -> Sequence[Mapping[str, object]]:
    rendered = str(response or "").strip()
    if not rendered:
        return ()
    candidates = [rendered]
    start, end = rendered.find("["), rendered.rfind("]")
    if start >= 0 and end >= start:
        candidates.insert(0, rendered[start : end + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            try:
                from json_repair import repair_json

                payload = json.loads(repair_json(candidate))
            except Exception:
                continue
        if isinstance(payload, Mapping):
            payload = payload.get("decisions", payload.get("records", ()))
        if isinstance(payload, list):
            return tuple(row for row in payload if isinstance(row, Mapping))
    return ()


class BudgetAwareCellVerifier:
    """Use an LLM first and an independent NLI encoder when budget is scarce."""

    def __init__(
        self,
        llm_client: object,
        ledger: GlobalBudgetLedger,
        *,
        completion_reserve: Optional[int] = None,
        batch_size: Optional[int] = None,
        nli_model: Optional[str] = None,
        nli_local_only: Optional[bool] = None,
        llm_confidence_threshold: Optional[float] = None,
    ):
        self.ledger = ledger
        self.client = BudgetedLLMClient(
            llm_client,
            ledger,
            default_stage="contract_cell_verification",
        )
        self.completion_reserve = max(
            0,
            int(
                completion_reserve
                if completion_reserve is not None
                else os.getenv(
                    "SPP_CELL_VERIFIER_RESERVE",
                    str(max(100_000, ledger.total_tokens // 20)),
                )
            ),
        )
        self.batch_size = max(
            1,
            int(
                batch_size
                if batch_size is not None
                else os.getenv("SPP_CELL_VERIFIER_BATCH_SIZE", "12")
            ),
        )
        self.nli_model = (
            nli_model
            if nli_model is not None
            else os.getenv(
                "SPP_NLI_MODEL",
                "cross-encoder/nli-deberta-v3-small",
            )
        )
        self.nli_local_only = (
            bool(nli_local_only)
            if nli_local_only is not None
            else os.getenv("SPP_NLI_LOCAL_ONLY", "1").strip().lower()
            not in {"0", "false", "no"}
        )
        self.llm_confidence_threshold = float(
            llm_confidence_threshold
            if llm_confidence_threshold is not None
            else os.getenv("SPP_CELL_VERIFIER_LLM_CONFIDENCE", "0.70")
        )
        if not 0.0 <= self.llm_confidence_threshold <= 1.0:
            raise ValueError(
                "cell verifier LLM confidence threshold must be in [0, 1]"
            )
        self._nli = None
        self._nli_unavailable = False

    @staticmethod
    def _prompt(claims: Sequence[CellClaim]) -> str:
        return (
            "Verify proposed structured-data cells against their source "
            "evidence. This is verification, not extraction. For each claim, "
            "decide whether the excerpt supports the exact identity, attribute "
            "role, and value. A nearby number belonging to another field, an "
            "event year used as a count, a historical value used as a current "
            "value, or a value supported only by world knowledge is not "
            "entailed. Calculations are valid only when the excerpt explicitly "
            "supplies the semantically correct operands. Do not repair or invent "
            "values.\n\n"
            "Return only a JSON array with exactly one object per claim. Each "
            "object must have exactly claim_id, status, confidence, and reason. "
            "status must be entailed, contradicted, unsupported, or abstain. "
            "confidence is a number from 0 to 1. Use entailed only for direct "
            "or unambiguous derived support; use abstain when uncertain.\n\n"
            "Claims:\n"
            + json.dumps(
                [claim.prompt_payload() for claim in claims],
                ensure_ascii=False,
                sort_keys=True,
            )
        )

    def _llm_batch(
        self,
        claims: Sequence[CellClaim],
    ) -> Dict[str, VerificationDecision]:
        prompt = self._prompt(claims)
        max_tokens = max(256, 96 * len(claims))
        conservative_cost = (len(prompt.encode("utf-8")) + 1) // 2 + max_tokens
        if self.ledger.available - self.completion_reserve < conservative_cost:
            return {}
        try:
            response = self.client.generate(
                prompt,
                max_tokens=max_tokens,
                temperature=0.0,
                operation="verify_cells",
            )
        except BudgetExhausted:
            return {}
        except Exception as exc:
            logger.warning("Cell-verification LLM call failed: %s", exc)
            return {}
        expected = {claim.claim_id for claim in claims}
        decisions: Dict[str, VerificationDecision] = {}
        for row in _parse_rows(response):
            claim_id = str(row.get("claim_id", ""))
            status = str(row.get("status", "")).strip().lower()
            try:
                confidence = float(row.get("confidence", 0.0))
            except (TypeError, ValueError):
                continue
            if (
                claim_id not in expected
                or status not in _ALLOWED_STATUSES
                or not 0.0 <= confidence <= 1.0
                or claim_id in decisions
            ):
                continue
            if confidence < self.llm_confidence_threshold:
                status = "abstain"
            decisions[claim_id] = VerificationDecision(
                claim_id=claim_id,
                status=status,
                confidence=confidence,
                method="llm",
                reason=str(row.get("reason", "")),
            )
        return decisions

    def _load_nli(self) -> object:
        if self._nli is not None:
            return self._nli
        if self._nli_unavailable:
            return None
        try:
            from sentence_transformers import CrossEncoder

            self._nli = CrossEncoder(
                self.nli_model,
                local_files_only=self.nli_local_only,
            )
        except Exception as exc:
            self._nli_unavailable = True
            logger.warning(
                "NLI verifier unavailable (%s); unresolved cells remain "
                "unverified",
                exc,
            )
            return None
        return self._nli

    def _nli_decisions(
        self,
        claims: Sequence[CellClaim],
    ) -> Dict[str, VerificationDecision]:
        model = self._load_nli()
        if model is None or not claims:
            return {}
        try:
            scores = model.predict(
                [
                    (claim.nli_premise, claim.hypothesis)
                    for claim in claims
                ],
                convert_to_numpy=True,
            )
            import numpy as np
        except Exception as exc:
            logger.warning("NLI cell verification failed: %s", exc)
            return {}
        labels = getattr(model.model.config, "id2label", {}) or {
            0: "contradiction",
            1: "entailment",
            2: "neutral",
        }
        decisions: Dict[str, VerificationDecision] = {}
        for claim, score in zip(claims, scores):
            logits = np.asarray(score, dtype=float)
            probabilities = np.exp(logits - logits.max())
            probabilities /= probabilities.sum()
            by_label = {
                str(labels[index]).lower(): float(probabilities[index])
                for index in range(len(probabilities))
            }
            entailment = by_label.get("entailment", 0.0)
            contradiction = by_label.get("contradiction", 0.0)
            neutral = by_label.get("neutral", 0.0)
            if entailment >= 0.90 and contradiction <= 0.05:
                status = "entailed"
                confidence = entailment
            elif contradiction >= 0.80:
                status = "contradicted"
                confidence = contradiction
            else:
                status = "abstain"
                confidence = max(entailment, contradiction, neutral)
            decisions[claim.claim_id] = VerificationDecision(
                claim_id=claim.claim_id,
                status=status,
                confidence=confidence,
                method="nli",
                reason="independent NLI fallback",
            )
        return decisions

    def verify(
        self,
        claims: Sequence[CellClaim],
    ) -> VerificationReport:
        ordered = tuple(claims)
        decisions: Dict[str, VerificationDecision] = {}
        llm_claims = 0
        for start in range(0, len(ordered), self.batch_size):
            batch = ordered[start : start + self.batch_size]
            resolved = self._llm_batch(batch)
            decisions.update(resolved)
            llm_claims += len(resolved)

        unresolved = tuple(
            claim for claim in ordered if claim.claim_id not in decisions
        )
        nli = self._nli_decisions(unresolved)
        decisions.update(nli)
        unresolved_count = len(ordered) - len(decisions)
        return VerificationReport(
            decisions=tuple(
                decisions[claim.claim_id]
                for claim in ordered
                if claim.claim_id in decisions
            ),
            llm_claims=llm_claims,
            nli_claims=len(nli),
            unverified_claims=unresolved_count,
        )


__all__ = [
    "BudgetAwareCellVerifier",
    "CellClaim",
    "VerificationDecision",
    "VerificationReport",
]
