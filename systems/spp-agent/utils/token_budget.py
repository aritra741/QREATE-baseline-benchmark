from __future__ import annotations

"""Token budget tracking and cost model for the SPP pipeline.

The key insight: the number of configs to select is NOT a parameter — it is
derived from whatever token budget remains after the probe run.  Adding more
configs to the selected set can only lower SPP error (because the formula
takes the minimum across all selected configs), so we always want as many
as the budget allows.

Token costs in the pipeline
---------------------------
1. Extraction (one-time, shared across ALL selected configs)
   cost = N_docs × avg_tokens_per_doc

2. Probe judging (one-time per probe run)
   cost ≈ N_pairs × avg_judge_tokens_per_pair

3. Per-config marginal cost after extraction
   - norm_strategy = "dictionary"  →  0 tokens (pure CPU transforms)
   - norm_strategy = "llm"         →  N_docs × C_llm_norm  (LLM normalization call)
   - er_strategy, unit_strategy, miss_strategy  →  0 tokens (CPU only)

Since extraction is shared, the dominant decision is whether to run LLM
normalization for a config.  Dictionary-norm configs cost nothing extra;
llm-norm configs cost proportionally to corpus size.

Budget-aware selection
----------------------
Sort all candidate configs by surrogate score (descending).
For each config in order:
    if remaining_budget >= marginal_cost(config):
        select it, deduct cost
    else:
        stop
Return selected configs.

This means:
- With a large budget you may select many or all 16 configs.
- With a tight budget you select only dictionary-norm configs, or just 1.
- You NEVER select fewer than 1 (at least one config is always affordable
  because extraction has already been paid for during probing).
"""

from dataclasses import dataclass, field
from typing import Any

from utils.logging import setup_logger

logger = setup_logger("spp.token_budget")

# Approximate token overhead per LLM judge call (prompt + response)
_DEFAULT_JUDGE_TOKENS_PER_PAIR: float = 2000.0

# Fraction of extraction tokens used by LLM normalization pass
_LLM_NORM_FRACTION: float = 0.15


@dataclass
class CostModel:
    """Estimates token costs for each step of the SPP pipeline.

    All estimates are derived from tier0 signals (corpus size, avg doc length)
    that are available without ground-truth access.
    """

    avg_doc_tokens: float = 512.0
    judge_tokens_per_pair: float = _DEFAULT_JUDGE_TOKENS_PER_PAIR

    @classmethod
    def from_tier0(cls, tier0: dict[str, Any]) -> CostModel:
        """Build a CostModel from deployment-visible tier0 signals."""
        avg = float(tier0.get("avg_doc_tokens", 512.0))
        return cls(avg_doc_tokens=avg)

    def extraction_cost(self, n_docs: int) -> float:
        """Token cost for one shared extraction pass over n_docs documents."""
        return float(n_docs) * self.avg_doc_tokens

    def probe_cost(self, n_docs: int, n_judge_pairs: int) -> float:
        """Total cost of one probe run: extraction + all judge calls."""
        return self.extraction_cost(n_docs) + n_judge_pairs * self.judge_tokens_per_pair

    def config_marginal_cost(self, config_id: str, n_docs: int) -> float:
        """Marginal token cost of adding one more config to the selected set,
        AFTER extraction has already been paid for.

        Only LLM normalization (norm_strategy=llm) incurs additional tokens.
        All other axes (er, unit, miss) are CPU-only.
        """
        parts = dict(p.split("=", 1) for p in config_id.split("|") if "=" in p)
        if parts.get("norm", "dictionary") == "llm":
            # LLM normalization: proportional to corpus size
            return self.extraction_cost(n_docs) * _LLM_NORM_FRACTION
        return 0.0  # dictionary normalization: pure CPU, no tokens

    def max_affordable_configs(
        self,
        candidate_ids: list[str],
        n_docs: int,
        remaining_budget: float,
    ) -> int:
        """Return how many configs can be selected given the remaining budget.

        Always returns at least 1 (extraction was already paid for in the
        probe run, so the cheapest config is always affordable).
        """
        if not candidate_ids:
            return 0
        count = 0
        budget = remaining_budget
        # Count how many fit; dictionary-norm configs are free, llm-norm cost tokens
        free = sum(1 for c in candidate_ids
                   if self.config_marginal_cost(c, n_docs) == 0.0)
        paid = [(c, self.config_marginal_cost(c, n_docs))
                for c in candidate_ids
                if self.config_marginal_cost(c, n_docs) > 0.0]

        count += free  # all free configs are always affordable
        for _, cost in sorted(paid, key=lambda x: x[1]):
            if budget >= cost:
                count += 1
                budget -= cost
            else:
                break

        return max(1, count)


@dataclass
class TokenBudget:
    """Tracks token consumption through the SPP pipeline.

    Usage
    -----
    budget = TokenBudget(total=50_000)
    budget.spend(probe_cost, label="probe_run")
    n_configs = budget.affordable_configs(candidate_ids, n_docs, cost_model)
    """

    total: int          # token budget is a whole number of tokens
    _spent: float = field(default=0.0, init=False)   # float internally for fractional cost sums
    _ledger: list[dict[str, Any]] = field(default_factory=list, init=False)

    @property
    def spent(self) -> int:
        return int(self._spent)

    @property
    def remaining(self) -> int:
        return max(0, self.total - int(self._spent))

    @property
    def fraction_used(self) -> float:
        return self._spent / self.total if self.total > 0 else 0.0

    def spend(self, tokens: float, label: str = "") -> int:
        """Deduct tokens from the budget. Returns actual tokens deducted (as int)."""
        deducted = min(tokens, self.remaining)
        self._spent += deducted
        self._ledger.append({"label": label, "tokens": int(deducted), "remaining": self.remaining})
        logger.info(
            "Budget: spent=%d label=%s  remaining=%d / total=%d (%.1f%%)",
            int(deducted), label, self.remaining, self.total, 100 * self.fraction_used,
        )
        return int(deducted)

    def affordable_configs(
        self,
        candidate_ids: list[str],
        n_docs: int,
        cost_model: CostModel,
    ) -> int:
        """How many configs can be selected given the remaining budget."""
        return cost_model.max_affordable_configs(candidate_ids, n_docs, self.remaining)

    def summary(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "spent": self.spent,
            "remaining": self.remaining,
            "fraction_used": round(self.fraction_used, 4),
            "ledger": list(self._ledger),
        }


def budget_aware_select(
    surrogate,
    candidate_ids: list[str],
    token_budget: TokenBudget,   # total is int; remaining is int
    cost_model: CostModel,
    n_docs: int,
    *,
    min_configs: int = 1,
) -> list[str]:
    """Select as many configs as the remaining token budget allows.

    Configs are considered in descending surrogate-score order.
    Free configs (dictionary norm) are always included.
    LLM-norm configs are included only if budget permits.

    The count is DERIVED from the budget — it is never specified upfront.
    This is the correct model: more configs always helps SPP error, so we
    take as many as we can afford.

    Parameters
    ----------
    surrogate:
        Fitted BaseSurrogate instance.
    candidate_ids:
        All 16 config IDs.
    token_budget:
        Live budget tracker (remaining tokens after probe run).
    cost_model:
        CostModel with per-config marginal cost estimates.
    n_docs:
        Number of corpus documents (for cost estimation).
    min_configs:
        Minimum configs to return regardless of budget (default 1).
    """
    ranked = surrogate.rank(candidate_ids)

    selected: list[str] = []
    deferred: list[str] = []  # llm-norm configs we couldn't afford

    for cid in ranked:
        cost = cost_model.config_marginal_cost(cid, n_docs)
        if cost == 0.0:
            # Dictionary norm: always free, always include
            selected.append(cid)
            logger.debug("Selected config (free): %s", cid)
        elif token_budget.remaining >= cost:
            token_budget.spend(cost, label=f"config_llm_norm:{cid}")
            selected.append(cid)
            logger.debug("Selected config (llm-norm, cost=%.0f): %s", cost, cid)
        else:
            deferred.append(cid)
            logger.debug(
                "Deferred config (llm-norm, cost=%.0f > remaining=%.0f): %s",
                cost, token_budget.remaining, cid,
            )

    if not selected and deferred:
        # Guarantee at least min_configs by taking the cheapest deferred
        for cid in deferred[:min_configs]:
            selected.append(cid)
            logger.info("Forced selection of deferred config (budget exhausted): %s", cid)

    logger.info(
        "Budget-aware selection: selected=%d deferred=%d remaining_budget=%.0f",
        len(selected), len(deferred), token_budget.remaining,
    )
    return selected
