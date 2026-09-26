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
R3 fused_map      the value is interpretive or query-dependent, so values cannot
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
    if use.numeric or re.search(r"\b(year|date|id|code)\b", text):
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

    if extractive and sharable:
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


def fit_budget(decisions: list[Decision], tables: dict[str, Any], queries_by_table: dict[str, list[str]],
               available: int) -> dict[str, Any]:
    """R5. Drop map-served queries with the least workload value per token until the plan fits.

    Value of a query slot = number of map-routed, SQL-sensitive attributes it
    needs. Dropped (query, attribute) uses keep the incumbent value.
    """

    map_queries: dict[str, list[str]] = {}
    value: dict[tuple[str, str], int] = {}
    for d in decisions:
        if d.route in ("fused_map", "retrieval_map"):
            key = f"{d.table}:{d.route}"
            for q in d.query_ids:
                map_queries.setdefault(key, [])
                if q not in map_queries[key]:
                    map_queries[key].append(q)
                value[(key, q)] = value.get((key, q), 0) + 1
    dropped: list[tuple[str, str]] = []
    costs = operator_costs(decisions, tables, queries_by_table, map_queries)
    while costs["total"] > available:
        candidates = [(value[(key, q)], key, q) for key, qs in map_queries.items() for q in qs]
        if not candidates:
            break
        # Lowest value first; among equals drop from the most expensive read.
        candidates.sort(key=lambda row: (row[0], -int(tables[row[1].split(":")[0]]["full_read_cost"]), row[2]))
        _v, key, q = candidates[0]
        map_queries[key].remove(q)
        dropped.append((key, q))
        costs = operator_costs(decisions, tables, queries_by_table, map_queries)

    demoted: list[str] = []
    if costs["total"] > available:
        # Even without maps the plan does not fit: drop programs/canonical maps, least-used first.
        for d in sorted(decisions, key=lambda item: (len(item.query_ids), item.qualified)):
            if costs["total"] <= available:
                break
            if d.route in ("program", "canonical_map", "repair"):
                d.reasons.append(f"R5: demoted from {d.route} to keep (budget)")
                d.route, d.rule = "keep", "R5"
                demoted.append(d.qualified)
                costs = operator_costs(decisions, tables, queries_by_table, map_queries)

    for d in decisions:
        if d.route in ("fused_map", "retrieval_map"):
            served = set(map_queries.get(f"{d.table}:{d.route}", []))
            d.evidence["served_queries"] = sorted(served & set(d.query_ids))
            d.evidence["kept_queries"] = sorted(set(d.query_ids) - served)
            if not served & set(d.query_ids):
                d.reasons.append(f"R5: no affordable {d.route} slot; keep incumbent")
                d.route, d.rule = "keep", "R5"
    return {"costs": costs, "map_queries": map_queries, "dropped": dropped, "demoted": demoted, "fits": costs["total"] <= available}


def coverage(decisions: list[Decision]) -> dict[str, Any]:
    """Share of (query, attribute) uses served by a non-keep operator."""

    total = served = 0
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
    return {"uses": total, "served": served, "fraction": served / total if total else 0.0, "by_route": by_route}
