"""Need distances and budgeted context selection for router-v3.

Distance (after Chaudhuri, Gupta and Narasayya's workload compression): the
asymmetric loss D(i <- p) of serving need i with the value read under context p
instead of i's own query context, in benchmark cell-score units, measured on
documents read under both, minus i's noise floor (two identical reads of i's
own context). Providers are the canonical read, the other query contexts that
read the same attribute, and the incumbent database (cost zero; a missing
incumbent is a null value, which is also measurable).

Planning minimizes expected loss (point estimates net of noise). A provider
with fewer than MIN_PAIRS paired documents is infeasible. Among affordable
plans, the router takes the *cheapest plan statistically indistinguishable from
the best one*: expected loss within Z standard errors of the minimum. Without
that rule, any spare budget would buy per-query reads whose advantage is noise.

Selection is budgeted facility location: choose the set of contexts to
materialize per table (the "views"), assign every need to its best open
provider, and minimize total need-weighted loss within the token budget. Each
table is solved exactly over context subsets; tables are combined through a
Pareto frontier of (tokens, loss).
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Any

from quwarts.core.router.comparator import need_score
from quwarts.core.router.context_probe import FieldSpec, Observations, V3, conform
from quwarts.core.router.needs import CANONICAL, Need

INCUMBENT = "__incumbent__"
MIN_PAIRS = 3
Z = 1.96
MAX_EXACT_CONTEXTS = 16
BUNDLE = 6


@dataclass
class Distance:
    consumer: str
    provider: str
    n: int
    mean: float
    noise: float
    ucb: float
    point: float = math.inf
    se: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _wilson_upper(mean: float, n: int) -> float:
    if n == 0:
        return 1.0
    denom = 1 + Z * Z / n
    centre = (mean + Z * Z / (2 * n)) / denom
    half = Z * math.sqrt(max(0.0, mean * (1 - mean)) / n + Z * Z / (4 * n * n)) / denom
    return min(1.0, centre + half)


def noise_floor(need: Need, obs: Observations, fields: dict[str, FieldSpec]) -> tuple[float, int]:
    """Loss between two identical reads, for this need's scoring rule.

    Uses repeats of the need's own context; if there are none, pools repeats of
    every context that reads the same attribute on this table.
    """

    value_type = fields[need.qualified].value_type
    own, pooled = [], []
    for (table, _doc), ctx in obs.reads.items():
        if table != need.table:
            continue
        for context, rows in ctx.items():
            if len(rows) < 2 or need.attribute not in rows[0]:
                continue
            f = fields[need.qualified]
            loss = 1.0 - need_score(need, conform(rows[0].get(need.attribute), f), conform(rows[1].get(need.attribute), f), value_type)
            (own if context == need.query_id else pooled).append(loss)
    sample = own or pooled
    return (sum(sample) / len(sample), len(sample)) if sample else (0.0, 0)


def need_distances(
    needs: list[Need],
    obs: Observations,
    fields: dict[str, FieldSpec],
    incumbent: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> dict[tuple[str, str], Distance]:
    by_attr: dict[str, list[Need]] = {}
    for need in needs:
        by_attr.setdefault(need.qualified, []).append(need)
    out: dict[tuple[str, str], Distance] = {}
    for need in needs:
        value_type = fields[need.qualified].value_type
        noise, _n_noise = noise_floor(need, obs, fields)
        providers = [CANONICAL] + sorted({n.query_id for n in by_attr[need.qualified] if n.query_id != need.query_id})
        if incumbent is not None:
            providers.append(INCUMBENT)
        for provider in providers:
            losses = []
            for (table, doc), ctx in obs.reads.items():
                if table != need.table or need.query_id not in ctx:
                    continue
                field = fields[need.qualified]
                mine = conform(ctx[need.query_id][0].get(need.attribute), field)
                if provider == INCUMBENT:
                    theirs = conform((incumbent.get((table, doc)) or {}).get(need.attribute), field)
                elif provider in ctx and need.attribute in ctx[provider][0]:
                    theirs = conform(ctx[provider][0].get(need.attribute), field)
                else:
                    continue
                losses.append(1.0 - need_score(need, theirs, mine, value_type))
            n = len(losses)
            mean = sum(losses) / n if n else 1.0
            upper = _wilson_upper(mean, n) if n >= MIN_PAIRS else 1.0
            measured = n >= MIN_PAIRS
            out[(need.key, provider)] = Distance(
                consumer=need.key,
                provider=provider,
                n=n,
                mean=mean,
                noise=noise,
                point=max(0.0, mean - noise) if measured else (1.0 if provider == INCUMBENT else math.inf),
                se=math.sqrt(max(mean * (1 - mean), 1.0 / max(n, 1)) / n) if measured else 0.0,
                # Unmeasured sharing is infeasible; an unmeasured incumbent is assumed worthless.
                ucb=max(0.0, upper - noise) if n >= MIN_PAIRS else (1.0 if provider == INCUMBENT else math.inf),
            )
    return out


@dataclass
class TableOption:
    cost: int
    loss: float
    contexts: tuple[str, ...]
    var: float = 0.0
    assignment: dict[str, tuple[str, float]] = field(default_factory=dict)


def _context_cost(context: str, table_needs: list[Need], assigned_attrs: int, read_cost: int) -> int:
    if context == CANONICAL:
        return math.ceil(max(1, assigned_attrs) / BUNDLE) * read_cost
    return read_cost


def table_frontier(
    table: str,
    table_needs: list[Need],
    distances: dict[tuple[str, str], Distance],
    read_cost: int,
) -> list[TableOption]:
    """Exact Pareto frontier of (tokens, weighted loss) over subsets of contexts for one table."""

    contexts = sorted({n.query_id for n in table_needs}) + [CANONICAL]
    if len(contexts) > MAX_EXACT_CONTEXTS + 1:
        raise ValueError(f"{table}: {len(contexts)} contexts exceeds exact search limit")

    # Per need, providers ordered by loss: own context (0), incumbent, then measured others.
    ranked: dict[str, list[tuple[float, str]]] = {}
    for need in table_needs:
        rows = [(0.0, 0.0, need.query_id)]
        inc = distances.get((need.key, INCUMBENT))
        rows.append((inc.point if inc else 1.0, inc.se if inc else 0.0, INCUMBENT))
        for (key, provider), d in distances.items():
            if key == need.key and provider not in (INCUMBENT, need.query_id) and not math.isinf(d.point):
                rows.append((d.point, d.se, provider))
        ranked[need.key] = sorted(rows)

    options: list[TableOption] = []
    for size in range(len(contexts) + 1):
        for subset in itertools.combinations(contexts, size):
            open_set = set(subset)
            assignment: dict[str, tuple[str, float]] = {}
            total = 0.0
            var = 0.0
            for need in table_needs:
                for loss, se, provider in ranked[need.key]:
                    if provider == INCUMBENT or provider in open_set:
                        assignment[need.key] = (provider, loss)
                        total += need.weight * loss
                        var += (need.weight * se) ** 2
                        break
            canonical_attrs = len({k.split("|", 1)[1] for k, (p, _l) in assignment.items() if p == CANONICAL})
            # A context nobody is assigned to is not opened (and not paid for).
            used = {p for p, _l in assignment.values()} & open_set
            if used != open_set:
                continue  # the same plan appears as the smaller subset
            cost = sum(_context_cost(c, table_needs, canonical_attrs, read_cost) for c in used)
            options.append(TableOption(cost, total, tuple(sorted(used)), var, assignment))
    options.sort(key=lambda o: (o.cost, o.loss, o.contexts))
    frontier: list[TableOption] = []
    best = math.inf
    for option in options:
        if option.loss < best - 1e-12:
            frontier.append(option)
            best = option.loss
    return frontier


def combine(frontiers: dict[str, list[TableOption]], budget: int) -> tuple[int, float, dict[str, TableOption]]:
    """Cheapest plan within budget whose loss is within Z standard errors of the best plan."""

    merged: list[tuple[int, float, float, dict[str, TableOption]]] = [(0, 0.0, 0.0, {})]
    for table, options in sorted(frontiers.items()):
        rows = []
        for cost, loss, var, picks in merged:
            for option in options:
                if cost + option.cost <= budget:
                    rows.append((cost + option.cost, loss + option.loss, var + option.var, {**picks, table: option}))
        rows.sort(key=lambda row: (row[0], row[1]))
        merged, best = [], math.inf
        for row in rows:
            if row[1] < best - 1e-12:
                merged.append(row)
                best = row[1]
        if not merged:
            raise ValueError("no feasible plan within budget (every need must at least keep the incumbent)")
    best = min(merged, key=lambda row: (row[1], row[0]))
    tolerance = Z * math.sqrt(best[2])
    chosen = min((row for row in merged if row[1] <= best[1] + tolerance + 1e-12), key=lambda row: (row[0], row[1]))
    return chosen[0], chosen[1], chosen[3]
