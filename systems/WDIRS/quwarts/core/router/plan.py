"""Build a frozen, hashed router plan for one corpus."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from quwarts.core.ledger import BudgetedCaller
from quwarts.core.router.constants import FROZEN, FROZEN_HASH
from quwarts.core.router.corpus_features import corpus_features
from quwarts.core.router.policy import (
    Decision,
    coverage,
    docetl_equivalent_cost,
    fit_budget,
    repair_decision,
    route_decision,
)
from quwarts.core.router.probes import plan_probe, run_probe
from quwarts.core.router.registry import CorpusSpec
from quwarts.core.router.residue import residue_features
from quwarts.core.router.workload_features import workload_features


def file_sha(path: Path | None) -> str | None:
    if path is None or not Path(path).is_file():
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))


def verdict(cov: dict[str, Any], fits: bool) -> str:
    fraction = cov["fraction"]
    if not fits:
        label = "infeasible_at_theta"
    elif fraction >= float(FROZEN["coverage_serve_min"]):
        label = "workload_served"
    elif fraction < float(FROZEN["coverage_loss_max"]):
        label = "predicted_loss"
    else:
        label = "partially_served"
    # A verdict built on priors alone is provisional until the probe runs.
    return label if cov.get("measured_fraction", 0.0) >= 0.5 else f"{label}(provisional)"


def build_plan(
    spec: CorpusSpec,
    theta: int,
    caller: BudgetedCaller | None = None,
    journal: Path | None = None,
    incumbent_db: Path | None = None,
) -> dict[str, Any]:
    queries = spec.queries()
    workload = workload_features(spec, queries)
    corpus = corpus_features(spec, workload)
    residue = residue_features(spec, workload, incumbent_db)
    tables = corpus["tables"]
    doc_tokens = {name: tc.tokens for name, tc in corpus["corpora"].items()}
    queries_by_table = {name: info["queries"] for name, info in workload["tables"].items()}

    uses = sorted(workload["attributes"].values(), key=lambda use: use.qualified)
    decisions: dict[str, Decision] = {}
    to_probe = []
    for use in uses:
        if use.table not in tables:
            continue
        decision = repair_decision(use, residue["attributes"].get(use.qualified))
        if decision is not None:
            decisions[use.qualified] = decision
        else:
            to_probe.append(use)

    probe_budget = int(theta * float(FROZEN["probe_budget_fraction"]))
    probe_out: dict[str, Any]
    if caller is not None and to_probe:
        probe_out = run_probe(spec, to_probe, queries, doc_tokens, caller, journal=journal, budget=probe_budget)
        probe_spent = caller.ledger.spent
    else:
        probe_out = {
            "budget": probe_budget,
            "dry_run": True,
            "tables": {t: {"plan": p, "metrics": {}} for t, p in plan_probe(spec, to_probe, queries, doc_tokens, probe_budget).items()},
        }
        # A dry run reserves the probe budget it would spend.
        probe_spent = sum(
            int(entry["plan"]["docs"]) * int(entry["plan"]["calls_per_doc"]) * int(entry["plan"]["mean_call_tokens"])
            for entry in probe_out["tables"].values()
            if entry["plan"]["affordable"]
        )

    for use in to_probe:
        metrics = probe_out["tables"].get(use.table, {}).get("metrics", {}).get(use.qualified)
        decisions[use.qualified] = route_decision(use, tables[use.table], metrics)

    ordered = [decisions[key] for key in sorted(decisions)]
    available = max(0, theta - probe_spent)
    budget = fit_budget(ordered, tables, queries_by_table, available)
    cov = coverage(ordered)
    docetl_est = docetl_equivalent_cost(tables, queries_by_table)

    plan = {
        "router": {"version": FROZEN["version"], "frozen_hash": FROZEN_HASH, "constants": FROZEN},
        "corpus": spec.name,
        "inputs": {
            "manifest_sha": file_sha(spec.manifest),
            "incumbent_db": str(incumbent_db or spec.incumbent_db) if residue["available"] else None,
            "incumbent_sha": file_sha(incumbent_db or spec.incumbent_db) if residue["available"] else None,
            "corpus_fingerprint": hashlib.sha256(canonical_json(doc_tokens).encode()).hexdigest(),
            "n_queries": len(queries),
        },
        "budget": {
            "theta": theta,
            "probe_budget": probe_budget,
            "probe_spent": probe_spent,
            "available_for_operators": available,
            "planned_operator_tokens": budget["costs"]["total"],
            "fits": budget["fits"],
            "docetl_equivalent_estimate": docetl_est,
            "rho": theta / docetl_est if docetl_est else None,
        },
        "tables": {
            name: {k: v for k, v in info.items() if k != "label_surface"} | {"workload": workload["tables"].get(name)}
            for name, info in tables.items()
        },
        "attributes": {use.qualified: use.to_json() for use in uses},
        "residue": residue,
        "probe": probe_out,
        "decisions": [d.to_json() for d in ordered],
        "costs": budget["costs"],
        "map_queries": budget["map_queries"],
        "dropped_map_queries": budget["dropped"],
        "coverage": cov,
        "verdict": verdict(cov, budget["fits"]),
    }
    plan["plan_hash"] = hashlib.sha256(canonical_json({k: v for k, v in plan.items() if k != "probe"}).encode()).hexdigest()
    return plan


def summarize(plan: dict[str, Any]) -> str:
    lines = [
        f"corpus={plan['corpus']} verdict={plan['verdict']} coverage={plan['coverage']['fraction']:.2f} "
        f"measured={plan['coverage']['measured_fraction']:.2f} rho={plan['budget']['rho']:.3f} planned={plan['budget']['planned_operator_tokens']:,}/"
        f"{plan['budget']['available_for_operators']:,} (theta={plan['budget']['theta']:,}) plan={plan['plan_hash'][:12]}",
    ]
    for name, info in plan["tables"].items():
        lines.append(
            f"  table {name}: docs={info['n_docs']} median_tokens={info['tokens_median']:.0f} "
            f"lambda={info['context_fit_lambda']:.2f} queries={info['workload']['n_queries'] if info['workload'] else 0}"
        )
    for d in plan["decisions"]:
        ev = d["evidence"]
        extra = ""
        if d["route"] in ("fused_map", "retrieval_map"):
            extra = f" served={len(ev.get('served_queries', []))}/{len(d['query_ids'])}"
        lines.append(f"  {d['qualified']:<42} {d['route']:<14} {d['rule']:<3} uses={len(d['query_ids'])}{extra} | {d['reasons'][0]}")
    return "\n".join(lines)
