"""Zero-token cross-query consensus over stored group votes. No model calls."""

from __future__ import annotations

import hashlib
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sqlglot import exp

from quwarts.core.component_oracle import base_checksums
from quwarts.core.group_replay import _upsert, is_sql_null, load_group_votes, replay_group_rule, vote_resolved
from quwarts.core.pipeline import official_sql
from quwarts.core.query_filter import alias_order, decode_witness_key, outer_alias_tables
from quwarts.core.query_group import (
    _fetch,
    _join_pairs,
    _norm_bag,
    _support_keys,
    apply_official_group,
    ensure_group_table,
    extract_group_expressions,
    grain_sql,
    group_bags,
    parse_allowed,
    parse_sql,
    witness_key_sql,
)
from quwarts.core.query_witness import normalize_group
from quwarts.core.signature import table_aliases

CONSENSUS_RULES = ("cross_query_unanimous", "cross_query_majority", "full_original")
OFFICIAL_RULE = "cross_query_unanimous"


def role_canonicalize(expr_sql: str, alias_to_table: dict[str, str] | None = None, default_table: str | None = None) -> str:
    aliases = {str(key).lower(): str(value).lower() for key, value in (alias_to_table or {}).items()}
    default = (default_table or "").lower() or None
    try:
        tree = parse_sql(expr_sql)
    except Exception:
        return " ".join((expr_sql or "").lower().split())
    for col in tree.find_all(exp.Column):
        raw = (col.table or "").lower()
        table = aliases.get(raw) if raw else None
        if table is None and raw and raw in set(aliases.values()):
            table = raw
        if table is None and not raw:
            table = default
        if table:
            col.set("table", exp.to_identifier(f"#{table}"))
        elif raw:
            col.set("table", exp.to_identifier(f"#{raw}"))
    return " ".join(tree.sql(dialect="sqlite").lower().split())


def canonical_expr_id(expr_sql: str, alias_to_table: dict[str, str] | None = None, default_table: str | None = None) -> str:
    return hashlib.sha256(role_canonicalize(expr_sql, alias_to_table, default_table).encode()).hexdigest()[:16]


def participating_tables(expr_sql: str, alias_to_table: dict[str, str], default_table: str | None) -> tuple[str, ...]:
    aliases = {str(key).lower(): str(value).lower() for key, value in alias_to_table.items()}
    default = (default_table or "").lower() or None
    found: list[str] = []
    try:
        tree = parse_sql(expr_sql)
    except Exception:
        return tuple(sorted(set(aliases.values()) or ([default] if default else [])))
    for col in tree.find_all(exp.Column):
        raw = (col.table or "").lower()
        table = aliases.get(raw) if raw else None
        if table is None and raw and raw in set(aliases.values()):
            table = raw
        if table is None and not raw:
            table = default
        if table:
            found.append(table)
    if not found:
        found.extend(aliases.values() or ([default] if default else []))
    return tuple(sorted(set(found)))


def stable_row_key(
    expr_sql: str,
    alias_to_table: dict[str, str],
    default_table: str | None,
    order: list[str],
    witness_key: str,
) -> str:
    rids = decode_witness_key(witness_key)
    alias_rid = {str(alias).lower(): rid for alias, rid in zip(order, rids)}
    parts = []
    for table in participating_tables(expr_sql, alias_to_table, default_table):
        rid = None
        for alias, mapped in alias_to_table.items():
            if mapped.lower() == table and alias.lower() in alias_rid:
                rid = alias_rid[alias.lower()]
                break
        if rid is None and table in alias_rid:
            rid = alias_rid[table]
        parts.append(f"{table}:{rid if rid is not None else 'NULL'}")
    return "|".join(parts)


def _default_table(sql: str, aliases: dict[str, str]) -> str | None:
    values = list(dict.fromkeys(aliases.values()))
    if len(values) == 1:
        return values[0]
    try:
        tree = parse_sql(sql)
    except Exception:
        return values[0] if values else None
    for table in tree.find_all(exp.Table):
        return (table.name or "").lower() or None
    return values[0] if values else None


def query_expr_map(
    query_id: str,
    sql: str,
    sqlite_path: str | Path,
    predicates: list[Any],
) -> dict[str, dict[str, Any]]:
    official = official_sql(sql, sqlite_path, predicates)
    orig = extract_group_expressions(sql)
    off = extract_group_expressions(official) or orig
    aliases = table_aliases(parse_sql(sql))
    default = _default_table(sql, aliases)
    by_alias = {item.alias.lower(): item for item in orig}
    out = {}
    for item in off:
        source = by_alias.get((item.alias or "").lower()) or item
        canon = canonical_expr_id(source.sql, aliases, default)
        out[item.expr_id] = {
            "official": item,
            "original": source,
            "canonical_expr_id": canon,
            "alias": item.alias,
            "allowed": list(source.allowed or item.allowed),
            "alias_to_table": aliases,
            "default_table": default,
            "official_sql": official,
        }
    return out


def enumerate_sites(
    sqlite_path: str | Path,
    query_id: str,
    sql: str,
    predicates: list[Any],
) -> list[dict[str, Any]]:
    from quwarts.core.query_group import encode_witness_key

    mapping = query_expr_map(query_id, sql, sqlite_path, predicates)
    if not mapping:
        return []
    official = next(iter(mapping.values()))["official_sql"]
    tree = parse_sql(official)
    order = alias_order(tree)
    aliases = outer_alias_tables(tree) or table_aliases(tree)
    grain_tree = parse_sql(grain_sql(official))
    if isinstance(grain_tree, exp.Select):
        grain_tree.set(
            "expressions",
            list(grain_tree.expressions) + [exp.alias_(parse_sql(witness_key_sql(tree)), "__wk")],
        )
        grain = grain_tree.sql(dialect="sqlite")
    else:
        grain = grain_sql(official)
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        rows = _fetch(conn, grain)
    finally:
        conn.close()
    seen: set[tuple[str, str]] = set()
    out = []
    for row in rows:
        key = str(row.get("__wk") or encode_witness_key([0]))
        for expr_id, meta in mapping.items():
            pair = (expr_id, key)
            if pair in seen:
                continue
            seen.add(pair)
            item = meta["official"]
            if not item.eligible and not meta["original"].eligible:
                continue
            stable = stable_row_key(
                meta["original"].sql,
                meta["alias_to_table"],
                meta["default_table"],
                order,
                key,
            )
            out.append(
                {
                    "query_id": query_id,
                    "official_expr_id": expr_id,
                    "canonical_expr_id": meta["canonical_expr_id"],
                    "alias": meta["alias"],
                    "witness_key": key,
                    "stable_row": stable,
                    "canonical_key": f"{meta['canonical_expr_id']}|{stable}",
                    "old_label": row.get(item.alias),
                    "allowed": list(meta["allowed"]),
                    "expr_sql": meta["original"].sql,
                }
            )
    return out


def collect_sites(
    sqlite_path: str | Path,
    queries: list[dict[str, str]],
    predicates: list[Any],
) -> list[dict[str, Any]]:
    sites = []
    for row in queries:
        sites.extend(enumerate_sites(sqlite_path, row["query_id"], row["sql"], predicates))
    return sites


def query_votes_for_key(
    votes: list[dict[str, Any]],
    sites_by_vote: dict[tuple[str, str, str], dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Collapse to one label per (canonical_key, query). Conflicts abstain."""
    raw: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for vote in votes:
        if not vote_resolved(vote) or is_sql_null(vote.get("group_value")):
            continue
        site = sites_by_vote.get((str(vote.get("query_id")), str(vote.get("expr_id")), str(vote.get("witness_key"))))
        if site is None:
            continue
        raw[site["canonical_key"]][str(vote.get("query_id"))].add(normalize_group(vote.get("group_value")))
    out: dict[str, dict[str, Any]] = {}
    for key, by_query in raw.items():
        labels = {}
        abstain = []
        for qid, values in by_query.items():
            if len(values) != 1:
                abstain.append(qid)
                continue
            labels[qid] = next(iter(values))
        out[key] = {"votes": labels, "abstain": abstain, "n_queries": len(labels)}
    return out


def _legal_everywhere(label: str, sites: list[dict[str, Any]]) -> bool:
    if is_sql_null(label):
        return False
    for site in sites:
        if parse_allowed(label, site.get("allowed") or []) is None:
            return False
    return True


def accept_unanimous(entry: dict[str, Any], sites: list[dict[str, Any]]) -> str | None:
    labels = list(entry["votes"].values())
    if len(entry["votes"]) < 2:
        return None
    if len(set(labels)) != 1:
        return None
    label = labels[0]
    if is_sql_null(label) or not _legal_everywhere(label, sites):
        return None
    return label


def accept_majority(entry: dict[str, Any], sites: list[dict[str, Any]]) -> str | None:
    labels = list(entry["votes"].values())
    if len(labels) < 3:
        return None
    counts = Counter(labels)
    top, n = counts.most_common(1)[0]
    second = counts.most_common(2)[1][1] if len(counts) > 1 else 0
    if n < (2 * len(labels) + 2) // 3:
        return None
    if n < (2 * len(labels)) / 3:
        return None
    if n - second < 2:
        return None
    if is_sql_null(top) or not _legal_everywhere(top, sites):
        return None
    return top


def build_consensus(
    votes: list[dict[str, Any]],
    sites: list[dict[str, Any]],
) -> dict[str, Any]:
    by_site_key = {(s["query_id"], s["official_expr_id"], s["witness_key"]): s for s in sites}
    vote_index = {}
    for vote in votes:
        loc = (str(vote.get("query_id")), str(vote.get("expr_id")), str(vote.get("witness_key")))
        if loc in by_site_key:
            vote_index[loc] = by_site_key[loc]
    per_key = query_votes_for_key(votes, vote_index)
    sites_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for site in sites:
        sites_by_key[site["canonical_key"]].append(site)
    n_queries = Counter(len(entry["votes"]) for entry in per_key.values())
    agree = conflict = 0
    unanimous: dict[str, str] = {}
    majority: dict[str, str] = {}
    single = []
    conflicting = []
    for key, entry in per_key.items():
        labels = set(entry["votes"].values())
        if entry["abstain"] or len(labels) > 1:
            conflict += 1
            conflicting.append(key)
        elif len(entry["votes"]) == 1:
            agree += 1
            single.append(key)
        elif len(entry["votes"]) >= 2 and len(labels) == 1:
            agree += 1
        sites_for = sites_by_key.get(key) or []
        uni = accept_unanimous(entry, sites_for)
        if uni is not None:
            unanimous[key] = uni
        maj = accept_majority(entry, sites_for)
        if maj is not None:
            majority[key] = maj
    return {
        "per_key": per_key,
        "sites_by_key": dict(sites_by_key),
        "n_keys": len(per_key),
        "n_sites": len(sites),
        "query_frequency": {str(k): int(v) for k, v in sorted(n_queries.items())},
        "n_single": n_queries.get(1, 0),
        "n_two": n_queries.get(2, 0),
        "n_three": n_queries.get(3, 0),
        "n_more": sum(v for k, v in n_queries.items() if k >= 4),
        "n_agree": agree,
        "n_conflict": conflict,
        "agreement_rate": (agree / len(per_key)) if per_key else None,
        "conflict_rate": (conflict / len(per_key)) if per_key else None,
        "unanimous": unanimous,
        "majority": majority,
        "single_keys": single,
        "conflicting_keys": conflicting,
    }


def writes_for_labels(accepted: dict[str, str], sites_by_key: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    writes = []
    for key, label in accepted.items():
        for site in sites_by_key.get(key) or []:
            if parse_allowed(label, site.get("allowed") or []) is None:
                continue
            if normalize_group(label) == normalize_group(site.get("old_label")):
                continue
            writes.append(
                {
                    "query_id": site["query_id"],
                    "expr_id": site["official_expr_id"],
                    "witness_key": site["witness_key"],
                    "group_value": label,
                    "old_label": site.get("old_label"),
                    "canonical_key": key,
                    "resolved": True,
                    "agreement": "consensus",
                    "direct_decision": None,
                    "branch_decision": None,
                    "adjudicator_decision": None,
                    "raw": {},
                    "context_hash": "",
                    "token_cost": 0,
                }
            )
    return writes


def replay_consensus(
    dest: Path,
    statements: dict[str, str],
    predicates: list[Any],
    writes: list[dict[str, Any]],
) -> dict[str, Any]:
    conn = sqlite3.connect(str(dest))
    ensure_group_table(conn, site_local=True)
    conn.commit()
    checksums = base_checksums(conn)
    bags = group_bags(dest, statements, predicates, conn=conn, site_local=True)
    before_bags = dict(bags)
    support = {qid: _support_keys(conn, dest, qid, sql, predicates) for qid, sql in statements.items()}
    joins = {qid: _join_pairs(conn, dest, sql, predicates) for qid, sql in statements.items()}
    by_query: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in writes:
        by_query[str(item["query_id"])].append(item)
    attempted = materialized = visible = rolled = isolation_fail = 0
    accepted: list[dict[str, Any]] = []
    try:
        for qid, chunk in by_query.items():
            attempted += len(chunk)
            conn.execute("SAVEPOINT group_consensus")
            kept = []
            for item in chunk:
                if normalize_group(item.get("group_value")) == normalize_group(item.get("old_label")):
                    rolled += 1
                    continue
                _upsert(conn, item)
                kept.append(item)
            if not kept:
                conn.execute("ROLLBACK TO group_consensus")
                conn.execute("RELEASE group_consensus")
                continue
            after = group_bags(dest, statements, predicates, conn=conn, site_local=True)
            changed = [item for item, bag in after.items() if bag != bags.get(item)]
            leak = [item for item in changed if item != qid]
            support_broken = any(
                _support_keys(conn, dest, item, statements[item], predicates) != support[item] for item in changed or [qid]
            )
            join_broken = any(
                _join_pairs(conn, dest, statements[item], predicates) != joins[item] for item in changed or [qid]
            )
            if leak or support_broken or join_broken or base_checksums(conn) != checksums or qid not in changed:
                conn.execute("ROLLBACK TO group_consensus")
                conn.execute("RELEASE group_consensus")
                rolled += len(kept)
                if leak:
                    isolation_fail += 1
                continue
            conn.execute("RELEASE group_consensus")
            bags = after
            materialized += len(kept)
            visible += len(kept)
            accepted.extend(kept)
        conn.commit()
    finally:
        conn.close()
    after_bags = group_bags(dest, statements, predicates, site_local=True)
    frozen = sqlite3.connect(str(dest))
    try:
        n_sidecar = int(frozen.execute("SELECT COUNT(*) FROM group_labels WHERE resolved = 1").fetchone()[0])
        checksums_after = base_checksums(frozen)
    finally:
        frozen.close()
    return {
        "site_local": True,
        "n_attempted": attempted,
        "n_materialized": materialized,
        "n_sql_visible": visible,
        "n_propagated": attempted,
        "n_sidecar_rows": n_sidecar,
        "n_rolled_back": rolled,
        "n_isolation_fail": isolation_fail,
        "accepted": accepted,
        "before_bags": before_bags,
        "bags": after_bags,
        "checksums": checksums_after,
    }
