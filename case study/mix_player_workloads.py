#!/usr/bin/env python3
"""Mix-and-match subsets across Player contrast workloads.

Builds mixture workloads from:
  - player_agg20        (case study/docetl_Player_v7)
  - player_join20
  - player_groupby20
  - player_multiagg20
  - player_filterjoin20

Each mixture is written as:
  case study/workloads/mixtures/<name>/
    query_manifest.json
    query_manifest_nl.json
    meta.json
    composition.json   # exact source picks

Examples:
  python3 "case study/mix_player_workloads.py"
  python3 "case study/mix_player_workloads.py" --list
  python3 "case study/mix_player_workloads.py" --only mix20_balanced,mix10_smoke
  python3 "case study/mix_player_workloads.py" --custom "mix12_custom=filtered:2,multigroup:2,multiagg:2,join1:2,join2:2,join3:2"
  python3 "case study/mix_player_workloads.py" --seed 7 --size 20 --round-robin
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CASE = Path(__file__).resolve().parent
WORKLOADS = CASE / "workloads"
OUT_ROOT = WORKLOADS / "mixtures"
GENERATOR_VERSION = 2

SOURCE_DIRS: dict[str, Path] = {
    "agg": CASE / "docetl_Player_v7",
    "join": WORKLOADS / "player_join20",
    "groupby": WORKLOADS / "player_groupby20",
    "multiagg": WORKLOADS / "player_multiagg20",
    "filterjoin": WORKLOADS / "player_filterjoin20",
}

# The original case-study workload is preserved for reproducibility, but these
# audited queries are not eligible for new mixtures: they rely on incomplete
# joins, singleton team/owner groupings, the malformed owner-age value, or
# unit-inconsistent GDP.
EXCLUDED_SOURCE_QUERIES: dict[str, set[str]] = {
    "agg": {"q2", "q7", "q10", "q12", "q14", "q16", "q19"}
}

STRATUM_ALIASES = {
    "filter": "filtered",
    "filtered": "filtered",
    "group": "multigroup",
    "groupby": "multigroup",
    "multigroup": "multigroup",
    "agg": "multiagg",
    "multiagg": "multiagg",
    "join1": "join1",
    "one_join": "join1",
    "join2": "join2",
    "two_joins": "join2",
    "join3": "join3",
    "three_joins": "join3",
    "basic": "basic",
}

# Built-in recipes use mutually exclusive, measured SQL strata—not source files.
# Precedence is join depth, then multi-aggregation, multi-column GROUP BY,
# filtered single-table aggregation, and finally basic aggregation.
RECIPES: dict[str, dict[str, int]] = {
    "mix20_balanced": {"filtered": 4, "multigroup": 3, "multiagg": 3, "join1": 4, "join2": 4, "join3": 2},
    "mix10_smoke": {"filtered": 2, "multigroup": 1, "multiagg": 1, "join1": 2, "join2": 2, "join3": 2},
    "mix20_join_heavy": {"filtered": 1, "multigroup": 1, "multiagg": 1, "join1": 6, "join2": 7, "join3": 4},
    "mix20_agg_heavy": {"filtered": 4, "multigroup": 4, "multiagg": 9, "join1": 1, "join2": 1, "join3": 1},
    "mix20_groupby_heavy": {"filtered": 3, "multigroup": 8, "multiagg": 4, "join1": 2, "join2": 2, "join3": 1},
    "mix20_filter_heavy": {"filtered": 12, "multigroup": 2, "multiagg": 2, "join1": 2, "join2": 1, "join3": 1},
    "mix15_spread": {"filtered": 3, "multigroup": 2, "multiagg": 2, "join1": 3, "join2": 3, "join3": 2},
    "mix20_join_multiagg": {"multigroup": 1, "multiagg": 7, "join1": 4, "join2": 5, "join3": 3},
    "mix20_groupby_filter": {"filtered": 8, "multigroup": 7, "multiagg": 2, "join1": 1, "join2": 1, "join3": 1},
}


def query_properties(sql: str) -> dict[str, Any]:
    joins = len(re.findall(r"\bJOIN\b", sql, re.IGNORECASE))
    aggregates = len(
        re.findall(r"\b(?:AVG|COUNT|SUM|MIN|MAX)\s*\(", sql, re.IGNORECASE)
    )
    group_match = re.search(
        r"\bGROUP BY\s+(.+?)(?:\bHAVING\b|$)", sql, re.IGNORECASE
    )
    group_keys = (
        len([part for part in group_match.group(1).split(",") if part.strip()])
        if group_match
        else 0
    )
    return {
        "join_depth": joins,
        "aggregate_count": aggregates,
        "group_key_count": group_keys,
        "has_where": bool(re.search(r"\bWHERE\b", sql, re.IGNORECASE)),
        "has_having": bool(re.search(r"\bHAVING\b", sql, re.IGNORECASE)),
    }


def primary_stratum(properties: dict[str, Any]) -> str:
    joins = int(properties["join_depth"])
    if joins >= 3:
        return "join3"
    if joins == 2:
        return "join2"
    if joins == 1:
        return "join1"
    if int(properties["aggregate_count"]) >= 3:
        return "multiagg"
    if int(properties["group_key_count"]) >= 2:
        return "multigroup"
    if properties["has_where"]:
        return "filtered"
    return "basic"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _index_by_id(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in rows:
        qid = str(row.get("query_id") or "").strip()
        if qid:
            out[qid] = row
    return out


def load_pools() -> dict[str, list[dict[str, Any]]]:
    pools: dict[str, list[dict[str, Any]]] = {}
    for key, directory in SOURCE_DIRS.items():
        sql_path = directory / "query_manifest.json"
        nl_path = directory / "query_manifest_nl.json"
        if not sql_path.exists() or not nl_path.exists():
            raise FileNotFoundError(
                f"Missing manifests for source '{key}' under {directory}. "
                f"Run: python3 \"case study/build_player_contrast_workloads.py\""
            )
        sql_rows = _load_json(sql_path)
        nl_rows = _load_json(nl_path)
        if isinstance(sql_rows, dict):
            sql_rows = sql_rows.get("queries") or []
        if isinstance(nl_rows, dict):
            nl_rows = nl_rows.get("queries") or []
        nl_by_id = _index_by_id(nl_rows)
        pooled: list[dict[str, Any]] = []
        for row in sql_rows:
            qid = str(row.get("query_id") or "").strip()
            if qid in EXCLUDED_SOURCE_QUERIES.get(key, set()):
                continue
            sql = str(row.get("sql") or "").strip()
            text = str((nl_by_id.get(qid) or {}).get("text") or "").strip()
            if not qid or not sql or not text:
                raise ValueError(f"Incomplete query in {key}: {qid!r}")
            properties = query_properties(sql)
            pooled.append(
                {
                    "source": key,
                    "source_query_id": qid,
                    "sql": sql,
                    "text": text,
                    "fingerprint": re.sub(r"\s+", " ", sql.lower()).strip(),
                    "properties": properties,
                    "stratum": primary_stratum(properties),
                }
            )
        pools[key] = pooled
    return pools


def resolve_stratum(name: str) -> str:
    key = STRATUM_ALIASES.get(name.strip().lower())
    if not key:
        raise ValueError(
            f"Unknown stratum {name!r}. Expected one of: {', '.join(sorted(STRATUM_ALIASES))}"
        )
    return key


def parse_recipe_spec(spec: str) -> tuple[str, dict[str, int]]:
    """Parse name=filtered:2,multigroup:2,multiagg:2,join1:2,..."""
    if "=" not in spec:
        raise ValueError(f"Custom recipe must look like name=agg:4,join:4,... got {spec!r}")
    name, body = spec.split("=", 1)
    name = name.strip()
    if not name:
        raise ValueError("Custom recipe name is empty")
    counts: dict[str, int] = {}
    for part in body.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError(f"Bad count token {part!r} in {spec!r}")
        stratum, raw_n = part.split(":", 1)
        stratum = resolve_stratum(stratum)
        n = int(raw_n.strip())
        if n < 0:
            raise ValueError(f"Negative count for {stratum}")
        counts[stratum] = counts.get(stratum, 0) + n
    if not counts or sum(counts.values()) == 0:
        raise ValueError(f"Custom recipe {name!r} has no queries")
    return name, counts


def deterministic_child_seed(
    global_seed: int, name: str, recipe: dict[str, int]
) -> int:
    """Make a recipe's picks independent of invocation order and --only."""
    payload = json.dumps(
        {"seed": global_seed, "name": name, "recipe": recipe},
        sort_keys=True,
        separators=(",", ":"),
    )
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")


def source_pool_hashes(pools: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    return {
        source: hashlib.sha256(
            "\n".join(sorted(query["fingerprint"] for query in pool)).encode("utf-8")
        ).hexdigest()
        for source, pool in pools.items()
    }


def property_summary(queries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "join_depth": {
            str(depth): sum(q["properties"]["join_depth"] == depth for q in queries)
            for depth in range(4)
        },
        "multi_column_groupby": sum(
            q["properties"]["group_key_count"] >= 2 for q in queries
        ),
        "multi_aggregate": sum(
            q["properties"]["aggregate_count"] >= 3 for q in queries
        ),
        "with_where": sum(q["properties"]["has_where"] for q in queries),
        "with_having": sum(q["properties"]["has_having"] for q in queries),
    }


def sample_from_pool(
    pool: list[dict[str, Any]],
    n: int,
    rng: random.Random,
    used_fingerprints: set[str],
    *,
    prefer_unused: bool = True,
) -> list[dict[str, Any]]:
    if n <= 0:
        return []
    available = [q for q in pool if (not prefer_unused) or q["fingerprint"] not in used_fingerprints]
    if n > len(available):
        raise ValueError(
            f"Requested {n} unique queries but stratum only has {len(available)} available"
        )
    chosen = rng.sample(available, n)
    for q in chosen:
        used_fingerprints.add(q["fingerprint"])
    return chosen


def build_mixture(
    name: str,
    counts: dict[str, int],
    pools: dict[str, list[dict[str, Any]]],
    rng: random.Random,
) -> dict[str, Any]:
    all_queries = [query for pool in pools.values() for query in pool]
    strata = {
        stratum: [query for query in all_queries if query["stratum"] == stratum]
        for stratum in STRATUM_ALIASES.values()
    }
    used: set[str] = set()
    picked: list[dict[str, Any]] = []
    composition: list[dict[str, Any]] = []

    # Stable structural-stratum order for reproducible composition listings.
    for stratum in ("filtered", "multigroup", "multiagg", "join1", "join2", "join3", "basic"):
        n = int(counts.get(stratum, 0) or 0)
        if n <= 0:
            continue
        chosen = sample_from_pool(strata[stratum], n, rng, used)
        for q in chosen:
            new_id = f"q{len(picked)}"
            item = {
                "query_id": new_id,
                "sql": q["sql"],
                "text": q["text"],
                "source": q["source"],
                "source_query_id": q["source_query_id"],
                "stratum": q["stratum"],
                "properties": q["properties"],
            }
            picked.append(item)
            composition.append(
                {
                    "query_id": new_id,
                    "source": q["source"],
                    "source_query_id": q["source_query_id"],
                    "stratum": q["stratum"],
                    "properties": q["properties"],
                }
            )

    # Shuffle final order so adjacent queries are not always same-family blocks.
    order = list(range(len(picked)))
    rng.shuffle(order)
    shuffled = []
    shuffled_composition = []
    for new_pos, old_pos in enumerate(order):
        item = dict(picked[old_pos])
        item["query_id"] = f"q{new_pos}"
        shuffled.append(item)
        comp = dict(composition[old_pos])
        comp["query_id"] = f"q{new_pos}"
        shuffled_composition.append(comp)

    return {
        "name": name,
        "stratum_counts": {k: int(v) for k, v in counts.items() if int(v) > 0},
        "source_counts": dict(
            sorted(
                {
                    source: sum(q["source"] == source for q in shuffled)
                    for source in SOURCE_DIRS
                }.items()
            )
        ),
        "queries": shuffled,
        "composition": shuffled_composition,
    }


def build_round_robin(
    name: str,
    size: int,
    pools: dict[str, list[dict[str, Any]]],
    rng: random.Random,
) -> dict[str, Any]:
    """Take queries round-robin across measured structural strata."""
    strata = ["filtered", "multigroup", "multiagg", "join1", "join2", "join3"]
    all_queries = [query for pool in pools.values() for query in pool]
    decks = {
        stratum: [query for query in all_queries if query["stratum"] == stratum]
        for stratum in strata
    }
    for stratum in strata:
        rng.shuffle(decks[stratum])
    idxs = {stratum: 0 for stratum in strata}
    used: set[str] = set()
    picked: list[dict[str, Any]] = []
    composition: list[dict[str, Any]] = []
    counts = {stratum: 0 for stratum in strata}

    guard = 0
    while len(picked) < size and guard < size * 20:
        guard += 1
        progress = False
        for stratum in strata:
            if len(picked) >= size:
                break
            deck = decks[stratum]
            i = idxs[stratum]
            while i < len(deck) and deck[i]["fingerprint"] in used:
                i += 1
            idxs[stratum] = i
            if i >= len(deck):
                continue
            q = deck[i]
            idxs[stratum] = i + 1
            used.add(q["fingerprint"])
            new_id = f"q{len(picked)}"
            picked.append(
                {
                    "query_id": new_id,
                    "sql": q["sql"],
                    "text": q["text"],
                    "source": q["source"],
                    "source_query_id": q["source_query_id"],
                    "stratum": q["stratum"],
                    "properties": q["properties"],
                }
            )
            composition.append(
                {
                    "query_id": new_id,
                    "source": q["source"],
                    "source_query_id": q["source_query_id"],
                    "stratum": q["stratum"],
                    "properties": q["properties"],
                }
            )
            counts[stratum] += 1
            progress = True
        if not progress:
            break

    if len(picked) < size:
        raise ValueError(
            f"Could only build {len(picked)} unique queries for round-robin size={size}"
        )

    return {
        "name": name,
        "stratum_counts": {k: v for k, v in counts.items() if v > 0},
        "source_counts": {
            source: sum(q["source"] == source for q in picked)
            for source in SOURCE_DIRS
        },
        "queries": picked,
        "composition": composition,
    }


def write_mixture(mixture: dict[str, Any], seed: int) -> Path:
    out_dir = OUT_ROOT / mixture["name"]
    out_dir.mkdir(parents=True, exist_ok=True)
    sql_manifest = [{"query_id": q["query_id"], "sql": q["sql"]} for q in mixture["queries"]]
    nl_manifest = [{"query_id": q["query_id"], "text": q["text"]} for q in mixture["queries"]]
    meta = {
        "workload_id": mixture["name"],
        "title": f"Mixture workload ({mixture['name']})",
        "dataset": "Player",
        "n_queries": len(mixture["queries"]),
        "stratum_counts": mixture["stratum_counts"],
        "source_counts": mixture["source_counts"],
        "seed": seed,
        "child_seed": mixture["child_seed"],
        "generator_version": GENERATOR_VERSION,
        "source_pool_hashes": mixture["source_pool_hashes"],
        "property_summary": property_summary(mixture["queries"]),
        "kind": "mixture",
        "stratification": "exclusive measured SQL properties",
    }
    composition = {
        "workload_id": mixture["name"],
        "seed": seed,
        "stratum_counts": mixture["stratum_counts"],
        "source_counts": mixture["source_counts"],
        "child_seed": mixture["child_seed"],
        "generator_version": GENERATOR_VERSION,
        "source_pool_hashes": mixture["source_pool_hashes"],
        "picks": mixture["composition"],
    }
    (out_dir / "query_manifest.json").write_text(
        json.dumps(sql_manifest, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "query_manifest_nl.json").write_text(
        json.dumps(nl_manifest, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    (out_dir / "composition.json").write_text(
        json.dumps(composition, indent=2) + "\n", encoding="utf-8"
    )
    return out_dir


def update_readme() -> None:
    readme = WORKLOADS / "README.md"
    base = readme.read_text(encoding="utf-8") if readme.exists() else ""
    marker = "## Mixture subsets"
    body_lines = [
        marker,
        "",
        "Generated by `case study/mix_player_workloads.py` from the pure workloads above.",
        "Queries are stratified by mutually exclusive measured SQL properties, not by source file.",
        "",
        "```bash",
        'python3 "case study/mix_player_workloads.py"',
        'python3 "case study/mix_player_workloads.py" --only mix20_balanced,mix10_smoke',
        'python3 "case study/mix_player_workloads.py" --custom "mix12_custom=filtered:2,multigroup:2,multiagg:2,join1:2,join2:2,join3:2"',
        "```",
        "",
        "| Mixture | Size | Composition |",
        "|---|---:|---|",
    ]
    existing: list[tuple[str, dict[str, int], int]] = []
    if OUT_ROOT.exists():
        for directory in sorted(path for path in OUT_ROOT.iterdir() if path.is_dir()):
            meta_path = directory / "meta.json"
            if not meta_path.exists():
                continue
            meta = _load_json(meta_path)
            counts = meta.get("stratum_counts") or {}
            existing.append((directory.name, counts, int(meta.get("n_queries") or 0)))
    for name, counts, size in existing:
        parts = ", ".join(f"{k}:{v}" for k, v in counts.items())
        body_lines.append(f"| **{name}** | {size} | {parts} |")
    body_lines.extend(
        [
            "",
            "Each mixture folder under `workloads/mixtures/<name>/` contains the usual manifests plus `composition.json` (exact source query ids).",
            "",
        ]
    )
    section = "\n".join(body_lines)
    if marker in base:
        pre = base.split(marker)[0].rstrip() + "\n\n"
        text = pre + section
    else:
        text = base.rstrip() + "\n\n" + section
    readme.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducible picks")
    parser.add_argument("--list", action="store_true", help="List built-in recipes and exit")
    parser.add_argument(
        "--only",
        type=str,
        default="",
        help="Comma-separated recipe names to build (default: all built-ins)",
    )
    parser.add_argument(
        "--custom",
        action="append",
        default=[],
        help='Custom structural recipe, e.g. "mix12_custom=filtered:2,multigroup:2,multiagg:2,join1:2,join2:2,join3:2"',
    )
    parser.add_argument(
        "--round-robin",
        action="store_true",
        help="Also build a round-robin mixture across structural strata",
    )
    parser.add_argument("--size", type=int, default=20, help="Size for --round-robin mixture")
    parser.add_argument(
        "--name",
        type=str,
        default="",
        help="Name override for --round-robin (default: mix{size}_roundrobin)",
    )
    args = parser.parse_args()

    if args.list:
        print("Built-in recipes:")
        for name, counts in RECIPES.items():
            size = sum(counts.values())
            parts = ", ".join(f"{k}:{v}" for k, v in counts.items())
            print(f"  {name} (n={size}) :: {parts}")
        return

    pools = load_pools()
    for key, pool in pools.items():
        print(f"loaded {key}: {len(pool)} queries")

    recipes: dict[str, dict[str, int]] = {}
    if args.only.strip():
        for name in args.only.split(","):
            name = name.strip()
            if not name:
                continue
            if name not in RECIPES:
                raise SystemExit(f"Unknown recipe {name!r}. Use --list to see built-ins.")
            recipes[name] = RECIPES[name]
    else:
        recipes = dict(RECIPES)

    for spec in args.custom:
        name, counts = parse_recipe_spec(spec)
        recipes[name] = counts

    for name, counts in recipes.items():
        child_seed = deterministic_child_seed(args.seed, name, counts)
        child = random.Random(child_seed)
        mixture = build_mixture(name, counts, pools, child)
        mixture["child_seed"] = child_seed
        mixture["source_pool_hashes"] = source_pool_hashes(pools)
        out_dir = write_mixture(mixture, seed=args.seed)
        print(
            f"wrote {out_dir} ({len(mixture['queries'])} queries) "
            f"{mixture['stratum_counts']}"
        )

    if args.round_robin:
        rr_name = args.name.strip() or f"mix{args.size}_roundrobin"
        rr_recipe = {"round_robin_size": args.size}
        child_seed = deterministic_child_seed(args.seed, rr_name, rr_recipe)
        child = random.Random(child_seed)
        mixture = build_round_robin(rr_name, args.size, pools, child)
        mixture["child_seed"] = child_seed
        mixture["source_pool_hashes"] = source_pool_hashes(pools)
        out_dir = write_mixture(mixture, seed=args.seed)
        print(
            f"wrote {out_dir} ({len(mixture['queries'])} queries) "
            f"{mixture['stratum_counts']}"
        )

    update_readme()
    print(f"updated {WORKLOADS / 'README.md'}")


if __name__ == "__main__":
    main()
