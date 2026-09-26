"""Routing rules and the cost model.

Each rule is a redundancy argument. A 25%-budget system cannot repeat DocETL's
one query-conditioned read per (query, document); it must exploit redundancy
that DocETL leaves unused:

R1 repair         residual redundancy: the incumbent already answers most cells
                  and its existing values are trustworthy, so work is
                  proportional to the SQL-unknown residue, not to the corpus.
R2 program        cross-document redundancy: the value is a source span (g high),
                  means the same thing in every query (delta low), and sits
                  behind a stable textual cue (r high), so one reusable program
                  per attribute serves every document and every query.
R2' canonical_map cross-query redundancy for spans without a stable cue: read
                  each document once, query-independently, and share the value.
R3 fused_map      the value is interpretive, query-dependent, or found only under
                  query context (recall gap), so values cannot
                  be shared, but reads can: fuse compatible queries into one
                  whole-document transmission. Requires documents to fit.
R4 retrieval_map  as R3 when documents do not fit one call; read retrieved windows.
R5 keep           the required reads do not fit the budget; keep the incumbent
                  (and predict the loss) rather than spread budget thin.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from quwarts.core.router.constants import FROZEN
from quwarts.core.router.workload_features import AttributeUse

ROUTES = ("repair", "program", "canonical_map", "fused_map", "retrieval_map", "keep")
_COUNT_LIKE = re.compile(r"\b(number of|count of|how many|amount of)\b|_num$|_count$|_amount$")


@dataclass
class Decision:
    qualified: str
    table: str
    route: str
    rule: str
    reasons: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    query_ids: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def extractiveness_prior(use: AttributeUse, label_surface: float | None) -> tuple[str, str]:
    """Zero-token prior used only when the probe is unaffordable or silent."""

    text = f"{use.name} {use.description}".lower()
    if _COUNT_LIKE.search(use.name.lower()) or _COUNT_LIKE.search(text):
        return "interpretive", "count-like attribute: the value is computed over the document, not copied"
    if use.closed_label:
        if label_surface is not None and label_surface >= float(FROZEN["label_surface_min"]):
            return "extractive", f"closed labels occur verbatim in the corpus (surface={label_surface:.2f})"
        return "interpretive", "closed label set not written in the corpus: classification, not copying"
    # Match whole words and snake_case parts ("company_id" has the part "id").
    if use.numeric or re.search(r"(^|[\s_])(year|date|id|code)($|[\s_])", text):
        return "extractive", "numeric/date/identifier values are written as spans"
    if re.search(r"(^|_)name\b|\bname of\b", text):
        return "extractive", "named entities are written verbatim"
    return "interpretive", "no evidence the value is a span; default to query-conditioned reading"


def repair_decision(use: AttributeUse, residue: dict[str, Any] | None) -> Decision | None:
    """R1. Zero tokens: decided before any probe."""

    if not residue or not residue.get("present"):
        return None
    fraction = residue["residue_fraction"]
    trust = residue.get("incumbent_trust")
    evidence = {"residue_rows": residue["residue_rows"], "residue_fraction": fraction, "incumbent_trust": trust}
    if fraction > float(FROZEN["residue_fraction_max"]):
        return None
    if trust is None or trust < float(FROZEN["incumbent_grounding_min"]):
        return None
    return Decision(
        qualified=use.qualified,
        table=use.table,
        route="repair",
        rule="R1",
        reasons=[
            f"SQL-unknown residue is {fraction:.1%} of rows (<= {FROZEN['residue_fraction_max']:.0%})",
            f"incumbent values are trustworthy ({residue.get('incumbent_trust_kind')}={trust:.2f})",
        ],
        evidence=evidence,
        query_ids=list(use.query_ids),
    )


def route_decision(
    use: AttributeUse,
    table: dict[str, Any],
    probe: dict[str, Any] | None,
) -> Decision:
    """R2-R4 from context fit, extractiveness, query sensitivity, and regularity."""

    lam = float(table["context_fit_lambda"])
    surface = (table.get("label_surface") or {}).get(use.qualified)
    prior, prior_reason = extractiveness_prior(use, surface)
    probe = probe or {}
    g, delta, r = probe.get("g"), probe.get("delta"), probe.get("r")
    reasons: list[str] = []

    if g is not None:
        extractive = g >= float(FROZEN["extractive_min"])
        reasons.append(f"probe g={g:.2f} ({'extractive' if extractive else 'not extractive'})")
    else:
        extractive = prior == "extractive"
        reasons.append(f"prior: {prior_reason}")
    if delta is not None:
        sharable = delta <= float(FROZEN["sensitivity_max"])
        reasons.append(f"probe delta={delta:.2f} ({'shareable' if sharable else 'query-dependent'})")
    else:
        sharable = extractive
        reasons.append("no query-sensitivity estimate: shareable only if extractive")
    fits = lam <= 1.0
    reasons.append(f"context fit lambda={lam:.2f} ({'fits' if fits else 'does not fit'})")

    recall_gap = probe.get("recall_gap")
    loses_recall = recall_gap is not None and recall_gap > float(FROZEN["recall_gap_max"])
    if recall_gap is not None:
        reasons.append(f"probe recall_gap={recall_gap:.2f}")

    if extractive and sharable and loses_recall and fits:
        route, rule = "fused_map", "R3"
        reasons.append("query context recovers values a shared read misses")
    elif extractive and sharable:
        if not fits:
            route, rule = "program", "R2"
            reasons.append("long documents: amortize with one program per attribute")
        elif r is not None and r >= float(FROZEN["regularity_min"]):
            route, rule = "program", "R2"
            reasons.append(f"stable anchor r={r:.2f}")
        else:
            route, rule = "canonical_map", "R2'"
            reasons.append("no stable anchor" if r is None else f"irregular anchor r={r:.2f}")
    elif fits:
        route, rule = "fused_map", "R3"
    else:
        route, rule = "retrieval_map", "R4"

    return Decision(
        qualified=use.qualified,
        table=use.table,
        route=route,
        rule=rule,
        reasons=reasons,
        evidence={
            "lambda": lam,
            "label_surface": surface,
            "prior": prior,
            "g": g,
            "delta": delta,
            "delta_cross": probe.get("delta_cross"),
            "recall_gap": recall_gap,
            "r": r,
            "kappa": probe.get("kappa"),
            "probe_docs": probe.get("n_docs"),
        },
        query_ids=list(use.query_ids),
    )


# ---------------------------------------------------------------------------
# Cost model
# ---------------------------------------------------------------------------

def _call(tokens: int) -> int:
    return tokens + int(FROZEN["call_overhead_tokens"])


def operator_costs(decisions: list[Decision], tables: dict[str, Any], queries_by_table: dict[str, list[str]],
                   map_queries: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Estimated tokens per (table, route). ``map_queries`` overrides the query set served by maps."""

    window = int(FROZEN["window_tokens"])
    width = int(FROZEN["fusion_width"])
    bundle = int(FROZEN["canonical_bundle_size"])
    per_table: dict[str, dict[str, int]] = {}
    for table, info in tables.items():
        mine = [d for d in decisions if d.table == table]
        costs: dict[str, int] = {}
        repair_rows = sum(int(d.evidence.get("residue_rows", 0)) for d in mine if d.route == "repair")
        costs["repair"] = repair_rows * _call(window)
        n_program = sum(1 for d in mine if d.route == "program")
        costs["program"] = n_program * int(FROZEN["program_calls_per_attribute"]) * _call(window)
        n_canonical = sum(1 for d in mine if d.route == "canonical_map")
        costs["canonical_map"] = math.ceil(n_canonical / bundle) * int(info["full_read_cost"])
        for route, read_key in (("fused_map", "full_read_cost"), ("retrieval_map", "window_read_cost")):
            attrs = [d for d in mine if d.route == route]
            if map_queries is not None:
                served = [q for q in map_queries.get(f"{table}:{route}", [])]
            else:
                served = sorted({q for d in attrs for q in d.query_ids})
            costs[route] = math.ceil(len(served) / width) * int(info[read_key]) if attrs else 0
        per_table[table] = costs
    total = sum(sum(costs.values()) for costs in per_table.values())
    return {"per_table": per_table, "total": total}


def docetl_equivalent_cost(tables: dict[str, Any], queries_by_table: dict[str, list[str]]) -> int:
    """One query-conditioned whole-document read per (query, table document)."""

    return sum(len(queries_by_table.get(table, [])) * int(info["full_read_cost"]) for table, info in tables.items())


def _group_options(decisions: list[Decision], tables: dict[str, Any]) -> list[dict[str, Any]]:
    """Each group offers options (cost, value, selection); value = served (query, attribute) uses.

    Within a group, the best selection of a given size is always a prefix of a
    value-ordered list, so each group contributes at most n+1 options.
    """

    window_call = _call(int(FROZEN["window_tokens"]))
    width = int(FROZEN["fusion_width"])
    bundle = int(FROZEN["canonical_bundle_size"])
    groups: list[dict[str, Any]] = []
    for table, info in sorted(tables.items()):
        mine = [d for d in decisions if d.table == table]
        for route, read_key in (("fused_map", "full_read_cost"), ("retrieval_map", "window_read_cost")):
            attrs = [d for d in mine if d.route == route]
            if not attrs:
                continue
            value: dict[str, int] = {}
            for d in attrs:
                for q in d.query_ids:
                    value[q] = value.get(q, 0) + 1
            order = sorted(value, key=lambda q: (-value[q], q))
            options = [
                (math.ceil(k / width) * int(info[read_key]), sum(value[q] for q in order[:k]), tuple(order[:k]))
                for k in range(len(order) + 1)
            ]
            groups.append({"key": f"{table}:{route}", "kind": "map", "options": options})
        for route in ("canonical_map", "program", "repair"):
            attrs = sorted((d for d in mine if d.route == route), key=lambda d: (-len(d.query_ids), d.qualified))
            if not attrs:
                continue
            options = []
            for m in range(len(attrs) + 1):
                chosen = attrs[:m]
                if route == "canonical_map":
                    cost = math.ceil(m / bundle) * int(info["full_read_cost"])
                elif route == "program":
                    cost = m * int(FROZEN["program_calls_per_attribute"]) * window_call
                else:
                    cost = sum(int(d.evidence.get("residue_rows", 0)) for d in chosen) * window_call
                options.append((cost, sum(len(d.query_ids) for d in chosen), tuple(d.qualified for d in chosen)))
            groups.append({"key": f"{table}:{route}", "kind": "attrs", "options": options})
    return groups


def _frontier(groups: list[dict[str, Any]], available: int) -> tuple[int, int, dict[str, tuple]]:
    """Exact max-value selection under the budget via a Pareto frontier over groups."""

    frontier: list[tuple[int, int, dict[str, tuple]]] = [(0, 0, {})]
    for group in groups:
        merged: list[tuple[int, int, dict[str, tuple]]] = []
        for cost, value, picks in frontier:
            for o_cost, o_value, selection in group["options"]:
                total = cost + o_cost
                if total <= available:
                    merged.append((total, value + o_value, {**picks, group["key"]: selection}))
        merged.sort(key=lambda row: (row[0], -row[1]))
        frontier = []
        best = -1
        for row in merged:
            if row[1] > best:  # strictly more value for more cost
                frontier.append(row)
                best = row[1]
    return max(frontier, key=lambda row: (row[1], -row[0]))


def fit_budget(decisions: list[Decision], tables: dict[str, Any], queries_by_table: dict[str, list[str]],
               available: int) -> dict[str, Any]:
    """R5. Choose the served (query, attribute) uses that maximize workload coverage within budget.

    Solved exactly: every operator group (map query slots, canonical bundles,
    programs, repairs) offers prefix options, and a Pareto frontier over groups
    finds the best combination. Unselected uses keep the incumbent value.
    """

    groups = _group_options(decisions, tables)
    wanted = sum(group["options"][-1][1] for group in groups)
    _cost, value, picks = _frontier(groups, available)
    map_queries = {key: list(sel) for key, sel in picks.items() if any(g["key"] == key and g["kind"] == "map" for g in groups)}
    chosen_attrs = {name for key, sel in picks.items() for name in sel if key not in map_queries}

    dropped: list[tuple[str, str]] = []
    for group in groups:
        if group["kind"] == "map":
            full = group["options"][-1][2]
            dropped.extend((group["key"], q) for q in full if q not in set(map_queries.get(group["key"], [])))
    demoted: list[str] = []
    for d in decisions:
        if d.route in ("fused_map", "retrieval_map"):
            served = set(map_queries.get(f"{d.table}:{d.route}", []))
            d.evidence["served_queries"] = sorted(served & set(d.query_ids))
            d.evidence["kept_queries"] = sorted(set(d.query_ids) - served)
            if not served & set(d.query_ids):
                d.reasons.append(f"R5: no affordable {d.route} slot; keep incumbent")
                d.route, d.rule = "keep", "R5"
        elif d.route in ("canonical_map", "program", "repair") and d.qualified not in chosen_attrs:
            d.reasons.append(f"R5: {d.route} not affordable; keep incumbent")
            d.route, d.rule = "keep", "R5"
            demoted.append(d.qualified)
    costs = operator_costs(decisions, tables, queries_by_table, map_queries)
    return {
        "costs": costs,
        "map_queries": map_queries,
        "dropped": dropped,
        "demoted": demoted,
        "fits": costs["total"] <= available,
        "served_value": value,
        "wanted_value": wanted,
    }


def coverage(decisions: list[Decision]) -> dict[str, Any]:
    """Share of (query, attribute) uses served by a non-keep operator.

    ``measured_fraction`` is the share of decisions resting on zero-token
    residue or probe measurements rather than on priors alone.
    """

    total = served = 0
    measured = sum(
        1 for d in decisions if d.rule == "R1" or d.evidence.get("g") is not None or d.evidence.get("delta") is not None
    )
    by_route: dict[str, int] = {}
    for d in decisions:
        uses = len(d.query_ids)
        total += uses
        if d.route == "keep":
            n = 0
        elif d.route in ("fused_map", "retrieval_map"):
            n = len(d.evidence.get("served_queries", d.query_ids))
        else:
            n = uses
        served += n
        by_route[d.route] = by_route.get(d.route, 0) + n
    return {
        "uses": total,
        "served": served,
        "fraction": served / total if total else 0.0,
        "by_route": by_route,
        "measured_fraction": measured / len(decisions) if decisions else 0.0,
    }
