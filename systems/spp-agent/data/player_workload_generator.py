"""Generate corpus-grounded Player aggregation queries for balanced workloads."""

from __future__ import annotations

import re
from itertools import product
from pathlib import Path
from typing import Any

from data.aggregation_slices import AGGREGATION_SLICE_ORDER as SLICE_ORDER
from data.balanced_workload import build_balanced_slice_pool, summarize_workload_balance
from data.instance_builder import build_instance
from data.loader import _benchu_root, load_corpus, load_ground_truth
from utils.config import load_config

AGG_ONLY_GROUP_COLS = ["position", "nationality", "team", "college"]
AGG_ONLY_GROUP_PAIRS = [
    ("position", "nationality"),
    ("position", "team"),
    ("nationality", "team"),
    ("team", "college"),
    ("position", "college"),
    ("nationality", "college"),
]
AGG_ONLY_METRICS = [
    ("COUNT", "*", "count_all"),
    ("COUNT", "age", "count_age"),
    ("COUNT", "mvp_awards", "count_mvp_awards"),
    ("SUM", "olympic_gold_medals", "sum_olympic_gold_medals"),
    ("SUM", "nba_championships", "sum_nba_championships"),
    ("AVG", "age", "avg_age"),
    ("AVG", "draft_pick", "avg_draft_pick"),
    ("MIN", "mvp_awards", "min_mvp_awards"),
    ("MIN", "olympic_gold_medals", "min_olympic_gold_medals"),
    ("MAX", "nba_championships", "max_nba_championships"),
    ("MAX", "age", "max_age"),
    ("AVG", "fiba_world_cup", "avg_fiba_world_cup"),
    ("MIN", "draft_pick", "min_draft_pick"),
    ("SUM", "mvp_awards", "sum_mvp_awards"),
    ("MAX", "fiba_world_cup", "max_fiba_world_cup"),
]

FILTER_TEMPLATES = [
    ("eq_string", "{col} = '{val}'"),
    ("neq_string", "{col} != '{val}'"),
    ("lt_num", "{col} < {val}"),
    ("gt_num", "{col} > {val}"),
    ("lte_num", "{col} <= {val}"),
    ("gte_num", "{col} >= {val}"),
    ("and_two", "({p1}) AND ({p2})"),
    ("or_two", "({p1}) OR ({p2})"),
    ("mixed", "({p1} AND {p2}) OR ({p3})"),
]

JOIN_PATHS = [
    ("player_team", "player JOIN team ON player.team = team.team_name"),
    (
        "player_team_city",
        "player JOIN team ON player.team = team.team_name "
        "JOIN city ON team.location = city.city_name",
    ),
]


def _corpus_texts(corpus: list[dict]) -> list[str]:
    return [doc.get("text", "").lower() for doc in corpus]


def _value_in_corpus(value: str, corpus: list[dict]) -> bool:
    needle = str(value).strip().lower()
    if not needle:
        return False
    return any(needle in text for text in _corpus_texts(corpus))


def mine_corpus_literals(corpus: list[dict], gt: dict) -> dict[str, dict[str, list[str]]]:
    """GT column values that appear as substrings in corpus text."""
    mined: dict[str, dict[str, list[str]]] = {
        "player": defaultdict_list(),
        "team": defaultdict_list(),
        "city": defaultdict_list(),
    }
    string_cols = {
        "player": ["nationality", "team", "position", "college", "name"],
        "team": ["team_name", "location", "ownership"],
        "city": ["city_name", "state_name"],
    }
    for table, cols in string_cols.items():
        if table not in gt:
            continue
        df = gt[table]
        for col in cols:
            if col not in df.columns:
                continue
            for raw in df[col].dropna().unique():
                val = str(raw).strip()
                if _value_in_corpus(val, corpus):
                    mined[table][col].append(val)
    dates = set()
    for doc in corpus:
        for match in re.findall(r"\b(\d{4}/\d{1,2}/\d{1,2})\b", doc.get("text", "")):
            dates.add(match)
    mined["player"]["birth_date"] = sorted(dates)
    return mined


def defaultdict_list():
    from collections import defaultdict

    return defaultdict(list)


def _agg_select(group_col: str, func: str, metric: str, alias: str) -> str:
    if func == "COUNT" and metric == "*":
        expr = "COUNT(*) AS count_all"
    else:
        expr = f"{func}({metric}) AS {alias}"
    return f"SELECT {group_col}, {expr} FROM player GROUP BY {group_col};"


def _agg_select_multi(group_cols: tuple[str, ...], func: str, metric: str, alias: str) -> str:
    group_sql = ", ".join(group_cols)
    select_cols = ", ".join(group_cols)
    if func == "COUNT" and metric == "*":
        expr = "COUNT(*) AS count_all"
    else:
        expr = f"{func}({metric}) AS {alias}"
    return f"SELECT {select_cols}, {expr} FROM player GROUP BY {group_sql};"


def generate_agg_only_candidates() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for group_col, (func, metric, alias) in product(AGG_ONLY_GROUP_COLS, AGG_ONLY_METRICS):
        sql = _agg_select(group_col, func, metric, alias)
        out.append(
            {
                "template": f"agg_only|{group_col}|{func}|{metric}",
                "sql": sql,
            }
        )
    for group_cols, (func, metric, alias) in product(AGG_ONLY_GROUP_PAIRS, AGG_ONLY_METRICS):
        sql = _agg_select_multi(group_cols, func, metric, alias)
        out.append(
            {
                "template": f"agg_only|{group_cols[0]}+{group_cols[1]}|{func}|{metric}",
                "sql": sql,
            }
        )
    return out


def generate_agg_filter_candidates(literals: dict) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    player = literals.get("player", {})
    string_specs = [
        ("nationality", player.get("nationality", [])[:12]),
        ("team", player.get("team", [])[:12]),
        ("position", player.get("position", [])[:8]),
        ("college", player.get("college", [])[:8]),
    ]
    numeric_specs = [
        ("age", [25, 30, 35, 40]),
        ("draft_pick", [0, 1, 10, 30]),
        ("olympic_gold_medals", [0, 1, 2]),
        ("mvp_awards", [0, 1]),
        ("nba_championships", [0, 1, 2]),
        ("fiba_world_cup", [0, 1]),
    ]
    group_cols = ["nationality", "position", "team"]
    agg_variants = [
        ("COUNT(*)", "count_all"),
        ("AVG(age)", "avg_age"),
        ("SUM(olympic_gold_medals)", "sum_olympic_gold_medals"),
        ("MIN(mvp_awards)", "min_mvp_awards"),
        ("MAX(nba_championships)", "max_nba_championships"),
    ]

    preds: list[str] = []
    for col, vals in string_specs:
        for val in vals:
            preds.append(f"{col} = '{val}'")
            preds.append(f"{col} != '{val}'")
    for col, vals in numeric_specs:
        for val in vals:
            preds.append(f"{col} < {val}")
            preds.append(f"{col} > {val}")
            preds.append(f"{col} <= {val}")
            preds.append(f"{col} >= {val}")

    idx = 0
    for group_col, (agg_expr, alias) in product(group_cols, agg_variants):
        for offset in range(4):
            p1 = preds[(idx + offset) % len(preds)]
            p2 = preds[(idx + offset + 11) % len(preds)]
            p3 = preds[(idx + offset + 23) % len(preds)]
            where_variants = [
                ("single", p1),
                ("and_two", f"({p1}) AND ({p2})"),
                ("or_two", f"({p1}) OR ({p2})"),
                ("mixed", f"({p1} AND {p2}) OR ({p3})"),
            ]
            for mode, where in where_variants:
                sql = (
                    f"SELECT {group_col}, {agg_expr} AS {alias} "
                    f"FROM player WHERE {where} GROUP BY {group_col};"
                )
                out.append({"template": f"agg_filter|{group_col}|{mode}|{idx}", "sql": sql})
        idx += 1
    return out


def generate_agg_join_candidates() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    specs = [
        ("player.position", "MIN(player.olympic_gold_medals)", "min_player_olympic_gold_medals"),
        ("player.nationality", "COUNT(*)", "count_all"),
        ("player.team", "AVG(player.age)", "avg_player_age"),
        ("player.position", "MAX(player.mvp_awards)", "max_player_mvp_awards"),
        ("player.nationality", "SUM(player.nba_championships)", "sum_player_nba_championships"),
        ("team.location", "AVG(player.fiba_world_cup)", "avg_player_fiba_world_cup"),
        ("team.location", "MIN(team.championship)", "min_team_championship"),
        ("player.college", "COUNT(player.age)", "count_player_age"),
        ("player.position", "AVG(team.championship)", "avg_team_championship"),
        ("player.nationality", "MAX(player.age)", "max_player_age"),
        ("player.team", "SUM(player.olympic_gold_medals)", "sum_player_olympic_gold_medals"),
        ("team.location", "COUNT(*)", "count_all"),
        ("player.college", "MIN(player.draft_pick)", "min_player_draft_pick"),
        ("player.position", "SUM(team.championship)", "sum_team_championship"),
        ("player.nationality", "AVG(player.mvp_awards)", "avg_player_mvp_awards"),
        ("player.team", "MAX(player.olympic_gold_medals)", "max_player_olympic_gold_medals"),
        ("team.location", "SUM(player.mvp_awards)", "sum_player_mvp_awards"),
        ("player.college", "AVG(player.nba_championships)", "avg_player_nba_championships"),
        ("player.position", "COUNT(player.mvp_awards)", "count_player_mvp_awards"),
        ("player.nationality", "MIN(team.championship)", "min_team_championship"),
    ]
    for path_name, join_clause in JOIN_PATHS:
        for group_col, agg_expr, alias in specs:
            sql = (
                f"SELECT {group_col}, {agg_expr} AS {alias} "
                f"FROM {join_clause} GROUP BY {group_col};"
            )
            out.append({"template": f"agg_join|{path_name}|{group_col}|{alias}", "sql": sql})
    return out


def generate_agg_filter_join_candidates(literals: dict) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    player = literals.get("player", {})
    team = literals.get("team", {})
    city = literals.get("city", {})
    string_filters = [
        f"player.nationality = '{v}'" for v in player.get("nationality", [])[:8]
    ] + [f"player.team = '{v}'" for v in player.get("team", [])[:6]]
    string_filters += [f"team.location = '{v}'" for v in team.get("location", [])[:6]]
    string_filters += [f"city.city_name = '{v}'" for v in city.get("city_name", [])[:6]]
    numeric_filters = [
        "player.age < 35",
        "player.age > 28",
        "player.draft_pick <= 20",
        "player.olympic_gold_medals = 0",
        "player.mvp_awards >= 1",
        "team.championship > 0",
        "city.population < 2000000",
        "city.gdp > 100",
        "player.nba_championships != 2",
        "player.fiba_world_cup <= 1",
    ]
    filters = string_filters + numeric_filters
    group_cols = ["player.nationality", "player.position", "player.team", "team.location"]
    agg_exprs = [
        ("MIN(player.olympic_gold_medals)", "min_player_olympic_gold_medals"),
        ("AVG(player.age)", "avg_player_age"),
        ("COUNT(*)", "count_all"),
        ("SUM(player.mvp_awards)", "sum_player_mvp_awards"),
        ("MAX(team.championship)", "max_team_championship"),
    ]

    idx = 0
    for path_name, join_clause in JOIN_PATHS:
        for group_col, (agg_expr, alias) in product(group_cols, agg_exprs):
            for offset in range(3):
                f1 = filters[(idx + offset) % len(filters)]
                f2 = filters[(idx + offset + 5) % len(filters)]
                for mode in ("single", "and", "or"):
                    if mode == "single":
                        where = f1
                    elif mode == "and":
                        where = f"({f1}) AND ({f2})"
                    else:
                        where = f"({f1}) OR ({f2})"
                    sql = (
                        f"SELECT {group_col}, {agg_expr} AS {alias} "
                        f"FROM {join_clause} WHERE {where} GROUP BY {group_col};"
                    )
                    out.append(
                        {
                            "template": f"agg_filter_join|{path_name}|{mode}|{idx}",
                            "sql": sql,
                        }
                    )
                idx += 1
    return out


def generate_agg_temporal_candidates(literals: dict) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    dates = literals.get("player", {}).get("birth_date", [])[:15]
    draft_years = [1985, 1990, 1995, 2000, 2005, 2010, 2015, 2018]
    founded_years = [1946, 1960, 1970, 1980, 1990, 2000, 2010]
    group_cols = ["player.nationality", "player.position", "player.team"]
    agg_exprs = [
        ("COUNT(*)", "count_all"),
        ("AVG(player.age)", "avg_player_age"),
        ("MIN(player.draft_year)", "min_player_draft_year"),
        ("MAX(player.draft_pick)", "max_player_draft_pick"),
    ]

    for date in dates:
        for group_col, (agg_expr, alias) in product(group_cols, agg_exprs):
            sql = (
                f"SELECT {group_col}, {agg_expr} AS {alias} "
                f"FROM player WHERE player.birth_date = '{date}' GROUP BY {group_col};"
            )
            out.append({"template": f"agg_temporal|birth_eq|{date}", "sql": sql})
            sql = (
                f"SELECT {group_col}, {agg_expr} AS {alias} "
                f"FROM player JOIN team ON player.team = team.team_name "
                f"WHERE player.birth_date = '{date}' GROUP BY {group_col};"
            )
            out.append({"template": f"agg_temporal|birth_eq_join|{date}", "sql": sql})

    for year in draft_years:
        for group_col, (agg_expr, alias) in product(group_cols[:2], agg_exprs[:3]):
            for op, sym in (("gt", ">"), ("lt", "<"), ("eq", "=")):
                sql = (
                    f"SELECT {group_col}, {agg_expr} AS {alias} "
                    f"FROM player WHERE player.draft_year {sym} {year} GROUP BY {group_col};"
                )
                out.append({"template": f"agg_temporal|draft_{op}|{year}", "sql": sql})

    join_clause = "player JOIN team ON player.team = team.team_name"
    for year in founded_years:
        for group_col, (agg_expr, alias) in product(group_cols, agg_exprs[:2]):
            sql = (
                f"SELECT {group_col}, {agg_expr} AS {alias} "
                f"FROM {join_clause} WHERE team.founded_year > {year} GROUP BY {group_col};"
            )
            out.append({"template": f"agg_temporal|founded_gt|{year}", "sql": sql})
            sql = (
                f"SELECT {group_col}, {agg_expr} AS {alias} "
                f"FROM {join_clause} WHERE team.founded_year <= {year} GROUP BY {group_col};"
            )
            out.append({"template": f"agg_temporal|founded_lte|{year}", "sql": sql})

    for date in dates[:8]:
        sql = (
            f"SELECT player.draft_year, COUNT(*) AS count_all "
            f"FROM player WHERE player.birth_date >= '{date}' GROUP BY player.draft_year;"
        )
        out.append({"template": f"agg_temporal|group_draft_year|{date}", "sql": sql})
    return out


def _candidate_to_query(candidate: dict[str, str], query_id: str) -> dict:
    return {
        "query_id": query_id,
        "sql_query": candidate["sql"],
        "nl_query": None,
        "category": "Expanded",
        "metadata": {
            "generated": True,
            "template": candidate.get("template"),
        },
    }


def generate_all_candidates(literals: dict) -> dict[str, list[dict]]:
    generators = {
        "agg_only": generate_agg_only_candidates,
        "agg_filter": lambda: generate_agg_filter_candidates(literals),
        "agg_join": generate_agg_join_candidates,
        "agg_filter_join": lambda: generate_agg_filter_join_candidates(literals),
        "agg_temporal": lambda: generate_agg_temporal_candidates(literals),
    }
    out: dict[str, list[dict]] = {}
    for slice_name, gen in generators.items():
        candidates = gen()
        out[slice_name] = [
            _candidate_to_query(c, f"{slice_name}_expanded_{i}")
            for i, c in enumerate(candidates, start=1)
        ]
    return out


def write_slice_sql_file(
    path: Path,
    slice_name: str,
    queries: list[dict],
) -> None:
    lines: list[str] = []
    for idx, query in enumerate(queries, start=1):
        tables = sorted(
            set(re.findall(r"\b(player|team|city)\b", query["sql_query"].lower()))
        )
        table_note = ", ".join(tables) if tables else "player"
        lines.append(f"-- Query {idx}: {slice_name} ({table_note})")
        lines.append(query["sql_query"].rstrip(";") + ";")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def expand_player_workload(
    *,
    target_per_slice: int = 20,
    seed: int = 42,
    table_filter: set[str] | None = None,
    write_sql: bool = True,
) -> dict[str, Any]:
    table_filter = table_filter or {"player"}
    corpus = load_corpus("Player")
    gt = load_ground_truth("Player")
    instance = build_instance("Player", include_ground_truth=False)
    literals = mine_corpus_literals(corpus, gt)

    generated = generate_all_candidates(literals)
    all_new: list[dict] = []
    for qs in generated.values():
        all_new.extend(qs)
    combined_queries = list(instance.queries) + all_new

    slice_reports: list[dict[str, Any]] = []
    selected_by_slice: dict[str, list[dict]] = {}
    added_ids: list[str] = []
    removed_all: list[dict] = []

    for slice_name in SLICE_ORDER:
        report = build_balanced_slice_pool(
            combined_queries,
            slice_name=slice_name,
            schema=instance.schema,
            corpus=corpus,
            table_filter=table_filter,
            target_count=target_per_slice,
            seed=seed + sum(ord(c) for c in slice_name),
        )
        slice_reports.append(report)
        selected_by_slice[slice_name] = report["selected_queries"]
        for q in report["selected_queries"]:
            if q.get("metadata", {}).get("generated"):
                added_ids.append(q["query_id"])
        removed_all.extend(report["removed_duplicates"])
        removed_all.extend(report["removed_infeasible"])

    expanded_dir = _benchu_root() / "Query" / "Player" / "Expanded"
    written_files: list[str] = []
    if write_sql:
        for slice_name in SLICE_ORDER:
            report = next(r for r in slice_reports if r["slice"] == slice_name)
            to_write = [
                q
                for q in report["selected_queries"]
                if q.get("metadata", {}).get("generated")
            ]
            if not to_write:
                to_write = [q for q in report["selected_queries"]]
            path = expanded_dir / f"{slice_name}_expanded.sql"
            write_slice_sql_file(path, slice_name, to_write)
            written_files.append(str(path))

    balance = summarize_workload_balance(slice_reports)
    shortfalls = {
        r["slice"]: {
            "max_feasible": r["max_feasible"],
            "reason": (
                "insufficient unique corpus-feasible templates after deduplication"
                if not r["reached_target"]
                else None
            ),
        }
        for r in slice_reports
        if not r["reached_target"]
    }

    return {
        "target_per_slice": target_per_slice,
        "balance": balance,
        "per_slice_reports": slice_reports,
        "added_query_ids": sorted(set(added_ids)),
        "removed_duplicates_or_infeasible": removed_all[:200],
        "sql_files_written": written_files,
        "balance_note": (
            "Each slice is filled by round-robin across difficulty bins "
            "(group key / agg function, predicate type, join path, temporal operator). "
            "Exact and near-duplicate SQL signatures are removed before selection. "
            "String WHERE literals must appear in corpus text; only player/team/city tables are used."
        ),
        "shortfalls": shortfalls,
    }


def main() -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Expand Player aggregation workload")
    parser.add_argument("--target", type=int, default=20)
    parser.add_argument("--seed", type=int, default=int(load_config()["experiment"]["seed"]))
    parser.add_argument("--no-write-sql", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(load_config()["paths"]["results_dir"]) / "workload_expansion_report.json",
    )
    args = parser.parse_args()

    report = expand_player_workload(
        target_per_slice=args.target,
        seed=args.seed,
        write_sql=not args.no_write_sql,
    )
    payload = {
        "final_query_count_per_slice": {
            r["slice"]: r["selected_count"] for r in report["per_slice_reports"]
        },
        "max_feasible_per_slice": {
            r["slice"]: r["max_feasible"] for r in report["per_slice_reports"]
        },
        "total_count": report["balance"]["total_selected"],
        "selected_query_ids_by_slice": {
            r["slice"]: [q["query_id"] for q in r["selected_queries"]]
            for r in report["per_slice_reports"]
        },
        "added_query_ids": report["added_query_ids"],
        "query_templates_by_slice": {
            "agg_only": "GROUP BY {position|nationality|team|college} x {COUNT|SUM|AVG|MIN|MAX}(metrics)",
            "agg_filter": "WHERE corpus-grounded string/numeric predicates (single/AND/OR/mixed) + GROUP BY",
            "agg_join": "player-team and player-team-city join paths x varied group/agg pairs",
            "agg_filter_join": "join paths x single/AND/OR filters on player/team/city columns",
            "agg_temporal": "birth_date equality, draft_year comparisons, team.founded_year ranges",
        },
        "removed_duplicates_or_infeasible_count": len(report["removed_duplicates_or_infeasible"]),
        "removed_duplicates_or_infeasible_sample": report["removed_duplicates_or_infeasible"][:50],
        "balance_note": report["balance_note"],
        "shortfalls": report["shortfalls"],
        "sql_files_written": report["sql_files_written"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(json.dumps(payload, indent=2))
    print(f"\nReport saved to {args.output}")


if __name__ == "__main__":
    main()
