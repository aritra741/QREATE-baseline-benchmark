"""Detector-guided repair. The compiler plan is frozen. Routing is not re-chosen."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quwarts.core.extract import StagedExtractor, allocate_tiers
from quwarts.core.ledger import BudgetExhausted
from quwarts.core.models import FrozenPortfolio, PreprocessPolicy, SourceDocument, Workload
from quwarts.core.repair.actions import eligible_repairs, execute
from quwarts.core.repair.detectors import issues_from_snapshot, proxy_score, snapshot
from quwarts.core.repair.diagnose import (
    diagnose_empty_queries,
    diagnose_filter_failures,
    group_diagnoses,
    issues_from_filter_failures,
)
from quwarts.core.repair.er import resolve_shared_ids, stamp_shared_ids
from quwarts.core.repair.models import RepairReport
from quwarts.core.repair.rank import rank_repairs


MIN_REPAIR_TOKENS = 2000
RESERVE_FRACTION = 0.10
N_NO_IMPROVE = 3


def run_repair_agent(
    extractor: StagedExtractor,
    documents: list[SourceDocument],
    workload: Workload,
    portfolio: FrozenPortfolio,
    statements: dict[str, str],
    *,
    logical=None,
    identity_report: dict[str, Any] | None = None,
    maps: dict[str, dict[str, str]] | None = None,
    artifact_root: Path | None = None,
    policy: PreprocessPolicy | None = None,
    n_no_improve: int = N_NO_IMPROVE,
) -> RepairReport:
    """Spend leftover theta on ranked repairs. Do not pick among feasible DBs."""

    _ = maps
    ledger = extractor.ledger
    policy = policy or PreprocessPolicy(mode="whole_document")
    tiers = allocate_tiers(workload)
    identity_report = identity_report if identity_report is not None else {}
    routing = dict(portfolio.route)
    reserve = max(MIN_REPAIR_TOKENS, int(ledger.theta * RESERVE_FRACTION))
    bugfix_log: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []

    if ledger.remaining() < MIN_REPAIR_TOKENS:
        empty = snapshot(extractor.store, workload, portfolio, statements)
        return RepairReport(
            stopped="below_min_repair_tokens",
            before=empty.as_dict(),
            after=empty.as_dict(),
            steps=[],
            tokens_spent=0,
            bugfix_log=bugfix_log,
            routing=routing,
            shared_er=identity_report.get("shared_er") or {},
            infeasible=[],
        )

    start = ledger.spent
    before = snapshot(extractor.store, workload, portfolio, statements)
    best = proxy_score(before)
    no_improve = 0
    blocked: set[str] = set()
    infeasible: list[dict[str, Any]] = []
    stopped = "budget"

    while ledger.remaining() > reserve:
        current = snapshot(extractor.store, workload, portfolio, statements)
        found = issues_from_snapshot(current, workload, statements)
        if current.empty_query_ids:
            from quwarts.core.pipeline import serve_plans

            plans = serve_plans(portfolio, statements)
            diagnoses = diagnose_empty_queries(
                current.empty_query_ids, statements, plans,
                store=extractor.store, workload=workload,
            )
            empty_ids = set(current.empty_query_ids)
            found = [
                issue
                for issue in found
                if issue.kind != "empty_query"
                and not (issue.kind == "join_yield" and empty_ids >= set(issue.query_ids))
            ]
            found.extend(group_diagnoses(diagnoses, workload))
            filter_reports = diagnose_filter_failures(diagnoses, extractor.store, workload)
            found.extend(issues_from_filter_failures(filter_reports, workload))
        if not found:
            stopped = "no_issues"
            break
        candidates = eligible_repairs(found, extractor.store, blocked, ledger=ledger)
        ranked = rank_repairs(candidates, workload, len(statements))
        if not ranked:
            stopped = "no_compatible_repairs"
            break
        repair = ranked[0]
        if ledger.remaining() < max(repair.estimated_cost, MIN_REPAIR_TOKENS):
            stopped = "budget"
            break
        try:
            result = execute(
                repair,
                extractor=extractor,
                documents=documents,
                workload=workload,
                policy=policy,
                tiers=tiers,
                logical=logical,
                identity_report=identity_report,
            )
        except BudgetExhausted:
            stopped = "budget"
            steps.append({"repair": repair.action, "kind": repair.issue.kind, "stopped": "budget"})
            break
        if result.get("infeasible"):
            infeasible.append(result)
            blocked.add(repair.action)
        if result.get("bugfix"):
            bugfix_log.append(result)
        rematerialized = 0
        if not result.get("infeasible"):
            rematerialized = rematerialize_same_route(
                extractor, documents, workload, portfolio, identity_report, artifact_root,
            )
        after_step = snapshot(extractor.store, workload, portfolio, statements)
        score = proxy_score(after_step)
        improved = score > best + 1e-9
        if improved:
            best = score
            no_improve = 0
        else:
            blocked.add(repair.action)
            no_improve += 1
        steps.append(
            {
                "repair": repair.action,
                "kind": repair.issue.kind,
                "cause": (repair.issue.detail or {}).get("cause"),
                "priority": repair.priority,
                "result": {key: result.get(key) for key in result if key != "vote"},
                "proxy": score,
                "improved": improved,
                "blocked_after": repair.action if not improved else None,
                "rematerialized": rematerialized,
            }
        )
        if no_improve >= n_no_improve:
            stopped = "no_improvement"
            break
    else:
        stopped = "reserve"

    after = snapshot(extractor.store, workload, portfolio, statements)
    return RepairReport(
        stopped=stopped,
        before=before.as_dict(),
        after=after.as_dict(),
        steps=steps,
        tokens_spent=ledger.spent - start,
        bugfix_log=bugfix_log,
        routing=routing,
        shared_er=identity_report.get("shared_er") or {},
        infeasible=infeasible,
    )


def rematerialize_same_route(
    extractor: StagedExtractor,
    documents: list[SourceDocument],
    workload: Workload,
    portfolio: FrozenPortfolio,
    identity_report: dict[str, Any],
    artifact_root: Path | None,
) -> int:
    """Rewrite the existing databases. Do not re-rank routing."""

    from quwarts.core.pipeline import rematerialize_databases

    if not portfolio.configurations:
        return 0
    db_dir = Path(artifact_root or Path("artifacts")) / "databases"
    if portfolio.databases:
        db_dir = Path(portfolio.databases[0].sqlite_path).parent
    shared = resolve_shared_ids(list(extractor.store.records.values()), workload, extractor.caller)
    identity_report.update(stamp_shared_ids(identity_report, shared))
    databases = rematerialize_databases(
        store=extractor.store,
        workload=workload,
        documents=documents,
        configs=portfolio.configurations,
        db_dir=db_dir,
        ledger=extractor.ledger,
        identity_report=identity_report,
        overwrite=True,
    )
    if databases:
        portfolio.databases[:] = databases
    return len(databases)
