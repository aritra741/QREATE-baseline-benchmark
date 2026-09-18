"""End-to-end synthesis. Evaluation stays outside this module."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from quwarts.core.amplify import attach_amplification, allocation_weights
from quwarts.core.conflict import cluster_templates, conflict_graph, conflict_mix
from quwarts.core.domain import (
    TypeUnificationError,
    apply_evidence_types,
    apply_predicate_types,
    build_domain_maps,
    classify_declared_domains,
    disjoint_attributes,
    restore_sql_string_cells,
    unify_join_types,
)
from quwarts.core.extract import (
    EvidenceStore,
    StagedExtractor,
    allocate_tiers,
    authority_domains,
    complete_authority,
    ground_constrained_records,
    carry_derived_keys,
    prefer_constrained_records,
)
from quwarts.core.quality import CELL_CHANGE_STOP
from quwarts.core.repair import resolve_shared_ids, run_repair_agent, stamp_shared_ids
from quwarts.core.ledger import BudgetExhausted, BudgetedCaller, TokenLedger
from quwarts.core.logical import infer_logical_schema
from quwarts.core.materialize import materialize
from quwarts.core.models import (
    Configuration,
    FrozenPortfolio,
    LogicalSchema,
    ModuleConfig,
    PopulationPolicy,
    PreprocessPolicy,
    SourceDocument,
    Workload,
)
from quwarts.core.pilot import run_pilot
from quwarts.core.population import apply_population, refresh_population_types, policy_from_demands
from quwarts.core.rewrite import (
    apply_identity_keys,
    apply_like_derived,
    apply_vocab_derived,
    join_yield,
    rewritable,
)
from quwarts.core.route import route_workload
from quwarts.core.schema import canonical_schema
from quwarts.core.search import config_id, generate_candidates, marginal_cost, select_portfolio
from quwarts.core.surrogate import U_hat
from quwarts.core.workload import analyze_workload
from quwarts.core.signature import rewrite_sql, statements_as_queries, audit_workload, enumerate_predicates
from quwarts.core.signature_populate import apply_live_signatures
from quwarts.core.signature_realize import live_predicates

EMPTY_RESULT_REJECT = 0.25


def _signature_predicates(statements: dict[str, str]):
    report = audit_workload(statements_as_queries(statements))
    return live_predicates(enumerate_predicates(report.occurrences, report.signature_eligible))


def _rewrite_with_signatures(sql: str, sqlite_path: str, predicates) -> str:
    if predicates:
        sql = rewrite_sql(sql, predicates)
    return _join_aware_sql(sql, sqlite_path)


def load_documents(root: Path) -> list[SourceDocument]:
    documents = []
    for path in sorted(root.rglob("*.txt")):
        documents.append(
            SourceDocument(doc_id=path.stem, text=path.read_text(encoding="utf-8", errors="replace"))
        )
    return documents


def load_workload_sql(path: Path) -> dict[str, str]:
    if path.suffix == ".json":
        payload = json.loads(path.read_text())
        if isinstance(payload, dict) and "queries" in payload:
            payload = payload["queries"]
        if isinstance(payload, dict):
            return {str(key): str(value) for key, value in payload.items()}
        statements = {}
        for index, row in enumerate(payload):
            if isinstance(row, str):
                statements[f"q{index}"] = row
            else:
                statements[str(row.get("query_id", f"q{index}"))] = str(row.get("sql") or row.get("query"))
        return statements
    text = path.read_text()
    parts = [part.strip() for part in text.split(";") if part.strip()]
    return {f"q{index}": part for index, part in enumerate(parts)}


def synthesize(
    documents: list[SourceDocument],
    statements: dict[str, str] | Iterable[str],
    theta: int,
    *,
    seed: int = 0,
    artifact_root: Path | None = None,
    logical: LogicalSchema | None = None,
    caller: BudgetedCaller | None = None,
) -> FrozenPortfolio:
    artifact_root = Path(artifact_root or Path("artifacts"))
    evidence_dir = artifact_root / "evidence"
    db_dir = artifact_root / "databases"
    run_dir = artifact_root / "runs"
    for path in (evidence_dir, db_dir, run_dir):
        path.mkdir(parents=True, exist_ok=True)

    ledger = caller.ledger if caller is not None else TokenLedger(theta=theta, seed=seed)
    if not isinstance(statements, dict):
        statements = {f"q{index}": sql for index, sql in enumerate(statements)}
    if logical is None:
        logical = infer_logical_schema(statements.values())
    logical, workload = analyze_workload(statements, logical)

    clusters = cluster_templates(workload, logical.expressions)
    cluster_map = {
        template_id: cluster.id
        for cluster in clusters
        for template_id in cluster.template_ids
    }
    edges = conflict_graph(workload, logical.expressions)
    mix = conflict_mix(edges)

    store = EvidenceStore(evidence_dir)
    run_pilot(documents, workload, ledger, store, sample_fraction=0.25, seed=seed, caller=caller)
    attach_amplification(workload)
    _ = allocation_weights(workload)
    tiers = allocate_tiers(workload)

    pops = {cluster.id: policy_from_demands(cluster.resolved_demands, workload) for cluster in clusters}
    candidates = generate_candidates(logical, workload, clusters, pops)
    if not candidates:
        raise RuntimeError("no admissible configurations")

    seen_pre: set[str] = set()
    seen_attrs: set[str] = set()
    databases = []
    utilities: dict[str, float] = {}
    costs: dict[str, float] = {}
    extractor = StagedExtractor(store=store, ledger=ledger, caller=caller, seed=seed)

    # Materialize a diverse cheap prefix, then greedily select.
    ordered = sorted(candidates, key=lambda config: (config.pre.mode != "whole_document", config.schema_.pattern, config.id))
    materialized_configs = []
    for config in ordered:
        new_attrs = set(workload.requirements)
        cost = marginal_cost(config, seen_pre, seen_attrs, new_attrs)
        try:
            extractor.extract(documents, workload, config.pre, tiers, logical=logical)
        except Exception:
            continue
        records = complete_authority(
            ground_constrained_records(
                prefer_constrained_records(list(store.records.values()), workload, logical),
                documents,
            ),
            workload,
            logical,
        )
        db = materialize(
            config, records, workload, documents, db_dir, tokens_spent=ledger.spent,
            authority=authority_domains(records, workload, logical),
        )
        report = U_hat(db, config, documents, workload, stage1_rate=extractor.stage1_rate)
        db.surrogate = report
        databases.append(db)
        utilities[config.id] = report.U_hat
        costs[config.id] = cost
        materialized_configs.append(config)
        seen_pre.add(f"{config.pre.mode}|{config.pre.chunk_tokens}")
        seen_attrs.update(new_attrs)
        if ledger.remaining() < max(8, theta * 0.02) and materialized_configs:
            break

    selected = select_portfolio(
        materialized_configs, utilities, costs, clusters, theta_remaining=float(max(ledger.remaining(), 1))
    )
    if not selected:
        selected = materialized_configs[:1]
    selected_ids = {config.id for config in selected}
    selected_dbs = [db for db in databases if db.config_id in selected_ids]
    selected_configs = [config for config in materialized_configs if config.id in selected_ids]

    routing = route_workload(workload, selected_configs, selected_dbs, cluster_map)
    rewrites: dict[str, str] = {}
    db_by_config = {db.config_id: db for db in selected_dbs}
    config_by_id = {config.id: config for config in selected_configs}
    for template in workload.templates:
        config_id = routing.get(template.id)
        if config_id is None:
            continue
        config = config_by_id[config_id]
        result = rewritable(template, config.schema_, db_by_config[config_id].coverage, workload.requirements)
        if not result.ok or result.sql is None:
            continue
        rewrites[template.id] = result.sql
        for stmt_id in template.statement_ids:
            rewrites[stmt_id] = result.sql

    portfolio = FrozenPortfolio(
        configurations=selected_configs,
        route=routing,
        rewrites=rewrites,
        databases=selected_dbs,
        tokens_spent=ledger.spent,
        cache_hit_rate=store.cache_hit_rate(),
        seed=seed,
        logical_schema=logical,
    )
    manifest = run_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                **json.loads(portfolio.model_dump_json(by_alias=True)),
                "conflict_mix": mix,
                "cluster_count": len(clusters),
                "binding_failures": workload.binding_failures,
                "requirements": {name: json.loads(req.model_dump_json()) for name, req in workload.requirements.items()},
                "templates": [json.loads(row.model_dump_json()) for row in workload.templates],
            },
            indent=2,
        )
    )
    return portfolio


def _stamp_domain_norms(
    pop: PopulationPolicy,
    workload: Workload,
    maps: dict[str, dict[str, str]],
    identity_report: dict[str, object] | None = None,
) -> None:
    identity_maps = (identity_report or {}).get("maps") or {}
    names = set(maps) | set(workload.requirements)
    for name in names:
        req = workload.requirements.get(name)
        mapping = maps.get(name) or maps.get(name.split(".")[-1])
        domain = list(req.declared_domain) if req is not None else []
        if mapping is None and len(domain) < 2:
            continue
        pop.norm[name] = ModuleConfig(
            strategy="domain",
            params={
                "map": mapping or {},
                "domain": domain,
            },
        )
        pop.norm[name.split(".")[-1]] = pop.norm[name]
    for name, mapping in identity_maps.items():
        pop.er[name] = ModuleConfig(strategy="identity", params={"map": mapping})
        pop.er[name.split(".")[-1]] = pop.er[name]
        if name not in pop.norm or pop.norm[name].strategy != "domain":
            pop.norm[name] = ModuleConfig(strategy="identity", params={"map": mapping})
            pop.norm[name.split(".")[-1]] = pop.norm[name]


def compile_workload(
    documents: list[SourceDocument],
    statements: dict[str, str] | Iterable[str],
    theta: int,
    *,
    seed: int = 0,
    artifact_root: Path | None = None,
    logical: LogicalSchema | None = None,
    caller: BudgetedCaller | None = None,
    extract: bool = True,
    workers: int = 16,
    use_contracts: bool = False,
) -> FrozenPortfolio:
    """Compile Q to a shared extraction plan. No search, no surrogate."""

    artifact_root = Path(artifact_root or Path("artifacts"))
    evidence_dir = artifact_root / "evidence"
    db_dir = artifact_root / "databases"
    run_dir = artifact_root / "runs"
    for path in (evidence_dir, db_dir, run_dir):
        path.mkdir(parents=True, exist_ok=True)

    ledger = caller.ledger if caller is not None else TokenLedger(theta=theta, seed=seed)
    if not isinstance(statements, dict):
        statements = {f"q{index}": sql for index, sql in enumerate(statements)}
    if logical is None:
        logical = infer_logical_schema(statements.values())
    logical, workload = analyze_workload(statements, logical)

    clusters = cluster_templates(workload, logical.expressions)
    cluster_map = {
        template_id: cluster.id
        for cluster in clusters
        for template_id in cluster.template_ids
    }
    edges = conflict_graph(workload, logical.expressions)
    mix = conflict_mix(edges)

    store = EvidenceStore(evidence_dir)
    attach_amplification(workload)
    _ = allocation_weights(workload)
    tiers = allocate_tiers(workload)
    policy = PreprocessPolicy(mode="whole_document")
    extractor = None
    if extract:
        extractor = StagedExtractor(
            store=store, ledger=ledger, caller=caller, seed=seed, workers=workers,
        )
        extractor.use_contracts = use_contracts
        extractor.extract(documents, workload, policy, tiers, logical=logical)

    records = list(store.records.values())
    apply_evidence_types(workload, records)
    classify_declared_domains(workload, records)
    try:
        unify_join_types(workload, records)
    except TypeUnificationError:
        # Do not abort a corpus. Irreconcilable joins stay infeasible and score 0.
        pass
    quality_report: dict = {}
    bugfix_log: list[dict] = []
    if extract and extractor is not None:
        n_coerced = extractor.reextract_coerced(documents, workload, policy, tiers, logical=logical)
        bugfix_log.append({"kind": "reextract_coerced", "n": n_coerced})
        quality_report = {"compile_extract": "once", "bugfix": bugfix_log}

    schema = canonical_schema(logical)
    records = complete_authority(
        ground_constrained_records(
            prefer_constrained_records(list(store.records.values()), workload, logical),
            documents,
        ),
        workload,
        logical,
    )
    authority = authority_domains(records, workload, logical)
    classify_declared_domains(workload, records)
    try:
        maps, identity_report = build_domain_maps(records, workload, caller, logical)
    except BudgetExhausted:
        maps, identity_report = {}, {}
    try:
        shared = resolve_shared_ids(records, workload, caller)
        identity_report = stamp_shared_ids(identity_report, shared)
    except BudgetExhausted:
        pass
    selected_configs: list[Configuration] = []
    selected_dbs = []
    rejected_disjoint: list[dict[str, object]] = []
    pending: list[tuple[Configuration, object]] = []

    for cluster in clusters:
        pop = policy_from_demands(cluster.resolved_demands, workload)
        _stamp_domain_norms(pop, workload, maps, identity_report)
        config = Configuration(
            id=config_id(schema, pop, policy, cluster.id),
            schema=schema,
            pop=pop,
            pre=policy,
            cluster_id=cluster.id,
        )
        rows = apply_population(records, config, workload)
        flagged = disjoint_attributes(rows, workload)
        if flagged:
            rejected_disjoint.append({"cluster": cluster.id, "attributes": flagged})
            continue
        pending.append((config, cluster))

    if not pending and clusters:
        # Gate rejected every candidate; keep them so serve still has a DB.
        for cluster in clusters:
            pop = policy_from_demands(cluster.resolved_demands, workload)
            _stamp_domain_norms(pop, workload, maps, identity_report)
            pending.append(
                (
                    Configuration(
                        id=config_id(schema, pop, policy, cluster.id),
                        schema=schema,
                        pop=pop,
                        pre=policy,
                        cluster_id=cluster.id,
                    ),
                    cluster,
                )
            )

    for config, _cluster in pending:
        db = materialize(
            config, records, workload, documents, db_dir, tokens_spent=ledger.spent,
            authority=authority,
        )
        selected_configs.append(config)
        selected_dbs.append(db)

    routing = route_workload(workload, selected_configs, selected_dbs, cluster_map)
    rewrites: dict[str, str] = {}
    db_by_config = {db.config_id: db for db in selected_dbs}
    config_by_id = {config.id: config for config in selected_configs}
    needed_pairs = _all_join_pairs(workload)
    zero_yield_pairs = _zero_yield_pairs(workload, routing, config_by_id, db_by_config)
    bridges: dict = {}
    signature_predicates = apply_live_signatures(
        [db.sqlite_path for db in selected_dbs],
        statements,
        documents,
        caller,
        workload,
        workers=workers,
    )
    for template in workload.templates:
        chosen = routing.get(template.id)
        if chosen is None and selected_configs:
            chosen = selected_configs[0].id
        if chosen is None or chosen not in config_by_id:
            continue
        result = rewritable(
            template,
            config_by_id[chosen].schema_,
            db_by_config[chosen].coverage,
            workload.requirements,
        )
        sql = result.sql if result.ok and result.sql else (template.raw_sql or template.canonical_sql)
        if not sql:
            continue
        sql = _rewrite_with_signatures(
            sql, db_by_config[chosen].sqlite_path, signature_predicates,
        )
        rewrites[template.id] = sql
        for stmt_id in template.statement_ids:
            rewrites[stmt_id] = sql

    portfolio = FrozenPortfolio(
        configurations=selected_configs,
        route=routing,
        rewrites=rewrites,
        databases=selected_dbs,
        tokens_spent=ledger.spent,
        cache_hit_rate=store.cache_hit_rate(),
        seed=seed,
        logical_schema=logical,
    )
    repair_report = None
    if extract and extractor is not None and caller is not None:
        try:
            repair_report = run_repair_agent(
                extractor,
                documents,
                workload,
                portfolio,
                statements,
                logical=logical,
                identity_report=identity_report,
                maps=maps,
                artifact_root=artifact_root,
                policy=policy,
            )
            selected_dbs = list(portfolio.databases)
            selected_configs = list(portfolio.configurations)
            db_by_config = {db.config_id: db for db in selected_dbs}
            config_by_id = {config.id: config for config in selected_configs}
            routing = dict(portfolio.route)
            signature_predicates = apply_live_signatures(
                [db.sqlite_path for db in selected_dbs],
                statements,
                documents,
                caller,
                workload,
                workers=workers,
            )
            rewrites = {}
            for template in workload.templates:
                chosen = routing.get(template.id)
                if chosen is None and selected_configs:
                    chosen = selected_configs[0].id
                if chosen is None or chosen not in config_by_id:
                    continue
                result = rewritable(
                    template,
                    config_by_id[chosen].schema_,
                    db_by_config[chosen].coverage,
                    workload.requirements,
                )
                sql = result.sql if result.ok and result.sql else (template.raw_sql or template.canonical_sql)
                if not sql:
                    continue
                sql = _rewrite_with_signatures(
                    sql, db_by_config[chosen].sqlite_path, signature_predicates,
                )
                rewrites[template.id] = sql
                for stmt_id in template.statement_ids:
                    rewrites[stmt_id] = sql
            quality_report = {
                "compile_extract": "once",
                "bugfix": bugfix_log + list(repair_report.bugfix_log),
                "repair": {
                    "stopped": repair_report.stopped,
                    "tokens_spent": repair_report.tokens_spent,
                    "steps": repair_report.steps,
                    "before": repair_report.before,
                    "after": repair_report.after,
                },
            }
        except BudgetExhausted:
            quality_report = {
                "compile_extract": "once",
                "bugfix": bugfix_log,
                "repair": {"stopped": "budget"},
            }

    rejected_empty: list[dict[str, object]] = []
    if selected_dbs:
        rate, empty_ids = _empty_result_rate(
            rewrites, selected_dbs[0].sqlite_path, workload.templates,
        )
        if rate > EMPTY_RESULT_REJECT:
            rejected_empty.append(
                {
                    "reason": "empty_result_rate",
                    "empty_rate": rate,
                    "threshold": EMPTY_RESULT_REJECT,
                    "empty_ids": empty_ids,
                    "cluster": selected_configs[0].cluster_id if selected_configs else None,
                }
            )

    portfolio = FrozenPortfolio(
        configurations=selected_configs,
        route=routing,
        rewrites=rewrites,
        databases=selected_dbs,
        tokens_spent=ledger.spent,
        cache_hit_rate=store.cache_hit_rate(),
        seed=seed,
        logical_schema=logical,
    )
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                **json.loads(portfolio.model_dump_json(by_alias=True)),
                "mode": "compile",
                "domain_maps": maps,
                "identity_report": identity_report,
                "domain_disjoint_rejections": rejected_disjoint,
                "empty_result_rejections": rejected_empty,
                "empty_result_threshold": EMPTY_RESULT_REJECT,
                "quality": quality_report,
                "cell_change_stop": CELL_CHANGE_STOP,
                "conflict_mix": mix,
                "cluster_count": len(clusters),
                "bridges": {},
                "shared_er": (identity_report or {}).get("shared_er") or {},
                "zero_yield_pairs": [list(pair) for pair in zero_yield_pairs],
                "binding_failures": workload.binding_failures,
                "requirements": {
                    name: json.loads(req.model_dump_json())
                    for name, req in workload.requirements.items()
                },
                "expressions": [
                    json.loads(item.model_dump_json()) for item in logical.expressions
                ],
            },
            indent=2,
        )
    )
    return portfolio


def serve_sql(portfolio: FrozenPortfolio, statements: dict[str, str]) -> dict[str, str | None]:
    return {key: value["sql"] for key, value in serve_plans(portfolio, statements).items()}


def serve_plans(
    portfolio: FrozenPortfolio, statements: dict[str, str]
) -> dict[str, dict[str, str | None]]:
    """Rewrite held-out SQL and name the database each statement should hit."""

    _, workload = analyze_workload(statements, portfolio.logical_schema)
    clusters = cluster_templates(workload, portfolio.logical_schema.expressions)
    cluster_map = {
        template_id: cluster.id
        for cluster in clusters
        for template_id in cluster.template_ids
    }
    routing = route_workload(
        workload, portfolio.configurations, portfolio.databases, cluster_map,
    )
    config_by_id = {config.id: config for config in portfolio.configurations}
    db_by_id = {db.config_id: db for db in portfolio.databases}
    plans: dict[str, dict[str, str | None]] = {
        stmt_id: {"sql": None, "sqlite_path": None} for stmt_id in statements
    }
    for template in workload.templates:
        chosen = routing.get(template.id)
        if chosen is None and portfolio.configurations:
            chosen = portfolio.configurations[0].id
        if chosen is None or chosen not in config_by_id:
            continue
        result = rewritable(
            template,
            config_by_id[chosen].schema_,
            db_by_id[chosen].coverage,
            workload.requirements,
        )
        sql = result.sql if result.ok and result.sql else (template.raw_sql or template.canonical_sql)
        path = db_by_id[chosen].sqlite_path
        if sql and path:
            sql = _rewrite_with_signatures(sql, path, _signature_predicates(statements))
        for stmt_id in template.statement_ids:
            plans[stmt_id] = {"sql": sql, "sqlite_path": path}
    return plans


def _canonical_columns(sqlite_path: str) -> set[str]:
    import sqlite3

    names: set[str] = set()
    conn = sqlite3.connect(sqlite_path)
    try:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            for col in conn.execute(f'PRAGMA table_info("{table}")'):
                name = str(col[1])
                if name.endswith("__canonical"):
                    names.add(name[: -len("__canonical")].lower())
    finally:
        conn.close()
    return names


def rematerialize_databases(
    *,
    store: EvidenceStore,
    workload: Workload,
    documents: list[SourceDocument],
    configs: list[Configuration],
    db_dir: Path,
    ledger: TokenLedger,
    identity_report: dict | None = None,
    overwrite: bool = True,
) -> list:
    """Write the same configurations again. Routing is left to the caller."""

    apply_predicate_types(workload)
    records = list(store.records.values())
    restore_sql_string_cells(records, workload)
    for config in configs:
        refresh_population_types(config.pop, workload)
    records = complete_authority(
        ground_constrained_records(
            carry_derived_keys(
                prefer_constrained_records(records, workload, None),
                records,
            ),
            documents,
        ),
        workload,
        None,
    )
    authority = authority_domains(records, workload, None)
    maps, _ignored = {}, identity_report or {}
    try:
        maps, built = build_domain_maps(records, workload, None, None)
        identity_report = stamp_shared_ids(identity_report or built, resolve_shared_ids(records, workload, None))
    except BudgetExhausted:
        identity_report = identity_report or {}
    selected = []
    for config in configs:
        _stamp_domain_norms(config.pop, workload, maps, identity_report)
        if overwrite:
            stale = db_dir / f"{config.id}.db"
            if stale.exists():
                stale.unlink()
        db = materialize(
            config, records, workload, documents, db_dir, tokens_spent=ledger.spent,
            authority=authority,
        )
        selected.append(db)
    statements = {
        stmt_id: (template.raw_sql or template.canonical_sql)
        for template in workload.templates
        for stmt_id in (template.statement_ids or [template.id])
    }
    if statements and selected:
        apply_live_signatures(
            [db.sqlite_path for db in selected],
            statements,
            documents,
            None,
            workload,
        )
    return selected


def _derived_columns(sqlite_path: str, suffix: str) -> dict[str, set[str]]:
    import sqlite3

    found: dict[str, set[str]] = {}
    conn = sqlite3.connect(sqlite_path)
    try:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            for col in conn.execute(f'PRAGMA table_info("{table}")'):
                name = str(col[1])
                if name.endswith(suffix):
                    found.setdefault(table.lower(), set()).add(name[: -len(suffix)].lower())
    finally:
        conn.close()
    return found


def _like_columns(sqlite_path: str) -> dict[str, set[str]]:
    return _derived_columns(sqlite_path, "__like")


def _vocab_columns(sqlite_path: str) -> dict[str, set[str]]:
    return _derived_columns(sqlite_path, "__vocab")


def _join_aware_sql(sql: str, sqlite_path: str) -> str:
    """Joins use the shared canonical ID. LIKE/CASE read derived vocab columns."""

    sql = apply_like_derived(sql, _like_columns(sqlite_path))
    sql = apply_vocab_derived(sql, _vocab_columns(sqlite_path))
    canons = _canonical_columns(sqlite_path)
    if not canons:
        return sql
    return apply_identity_keys(sql, "canonical", "canonical", canons)


def _empty_result_rate(
    rewrites: dict[str, str],
    sqlite_path: str,
    templates,
) -> tuple[float, list[str]]:
    empty: list[str] = []
    if not templates:
        return 0.0, empty
    con = sqlite3.connect(sqlite_path)
    try:
        for template in templates:
            sql = rewrites.get(template.id)
            if not sql:
                empty.append(template.id)
                continue
            try:
                rows = con.execute(sql).fetchall()
            except sqlite3.Error:
                empty.append(template.id)
                continue
            if not rows:
                empty.append(template.id)
    finally:
        con.close()
    return len(empty) / max(len(list(templates)), 1), empty


def _all_join_pairs(workload) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for template in workload.templates:
        for left, right in template.join_pairs:
            key = tuple(sorted((left, right)))
            if key in seen or left == right:
                continue
            seen.add(key)
            pairs.append((left, right))
    return pairs


def _zero_yield_pairs(
    workload,
    routing: dict[str, str],
    config_by_id: dict,
    db_by_config: dict,
) -> list[tuple[str, str]]:
    needed: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for template in workload.templates:
        if not template.join_pairs:
            continue
        chosen = routing.get(template.id)
        if chosen is None and config_by_id:
            chosen = next(iter(config_by_id))
        if chosen is None or chosen not in config_by_id:
            continue
        result = rewritable(
            template,
            config_by_id[chosen].schema_,
            db_by_config[chosen].coverage,
            workload.requirements,
        )
        if not result.ok or result.sql is None:
            continue
        path = db_by_config[chosen].sqlite_path
        canons = _canonical_columns(path)
        sql = apply_identity_keys(result.sql, "surface", "canonical", canons) if canons else result.sql
        if join_yield(sql, path) > 0:
            continue
        for left, right in template.join_pairs:
            key = (left, right)
            rev = (right, left)
            if key in seen or rev in seen:
                continue
            seen.add(key)
            needed.append((left, right))
    return needed

