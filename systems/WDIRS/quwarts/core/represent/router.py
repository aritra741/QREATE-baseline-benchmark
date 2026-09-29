"""Which columns get the model tier under a token budget (gold-free).

For each targeted column, after the free tiers (T0 rules, T1 programs):

* ``benefit``: how many workload uses depend on the stored spelling (equality, ``IN``, raw grouping,
  joins, ``LIKE``) times the share of the column's non-null cells that still hold an off-form value.
  Both come from the workload and the extracted values; no gold.
* ``cost``: estimated tokens of the model tier on the column's residual distinct values, either all of
  them (``all``) or one representative per uncovered pattern class plus the values its program does not
  explain (``cascade``: model labels, programs generalize).

Columns are chosen by benefit per token until the budget is spent (the greedy order of the fractional
knapsack; each column is one item). With no budget only the free tiers run.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ColumnPlan:
    key: tuple[str, str]
    uses: int
    residual_rows: int
    rows: int
    residual_distinct: int
    cost: int

    @property
    def benefit(self) -> float:
        return self.uses * (self.residual_rows / self.rows) if self.rows else 0.0


def choose(plans: list[ColumnPlan], budget: int | None) -> tuple[set[tuple[str, str]], int]:
    if budget is None:
        return {p.key for p in plans if p.residual_distinct}, sum(p.cost for p in plans if p.residual_distinct)
    order = sorted((p for p in plans if p.residual_distinct and p.benefit > 0),
                   key=lambda p: (-p.benefit / max(1, p.cost), p.key))
    chosen, spent = set(), 0
    for p in order:
        if spent + p.cost <= budget:
            chosen.add(p.key)
            spent += p.cost
    return chosen, spent
