#!/usr/bin/env python3
"""Mix-and-match subsets across a dataset's contrast workloads.

Usage:
  python3 "case study/mix_contrast_workloads.py"
  python3 "case study/mix_contrast_workloads.py" --dataset art
  python3 "case study/mix_contrast_workloads.py" --dataset sec --only mix20_balanced
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from pathlib import Path
from typing import Any

CASE = Path(__file__).resolve().parent
WORKLOADS = CASE / "workloads"
GENERATOR_VERSION = 1

DATASET_SOURCES: dict[str, dict[str, Path]] = {
    "Art": {
        "agg": WORKLOADS / "art_agg20",
        "filter": WORKLOADS / "art_filter20",
        "groupby": WORKLOADS / "art_groupby20",
        "multiagg": WORKLOADS / "art_multiagg20",
    },
    "CSPaper": {
        "agg": WORKLOADS / "cspaper_agg20",
        "filter": WORKLOADS / "cspaper_filter20",
        "groupby": WORKLOADS / "cspaper_groupby20",
        "multiagg": WORKLOADS / "cspaper_multiagg20",
    },
    "Finan": {
        "agg": WORKLOADS / "finan_agg20",
        "filter": WORKLOADS / "finan_filter20",
        "groupby": WORKLOADS / "finan_groupby20",
        "multiagg": WORKLOADS / "finan_multiagg20",
    },
    "Legal": {
        "agg": WORKLOADS / "legal_agg20",
        "filter": WORKLOADS / "legal_filter20",
        "groupby": WORKLOADS / "legal_groupby20",
        "multiagg": WORKLOADS / "legal_multiagg20",
    },
    "Med": {
        "agg": WORKLOADS / "med_agg20",
        "join": WORKLOADS / "med_join20",
        "groupby": WORKLOADS / "med_groupby20",
        "multiagg": WORKLOADS / "med_multiagg20",
        "filterjoin": WORKLOADS / "med_filterjoin20",
    },
    "SEC": {
        "agg": WORKLOADS / "sec_agg20",
        "join": WORKLOADS / "sec_join20",
        "groupby": WORKLOADS / "sec_groupby20",
        "multiagg": WORKLOADS / "sec_multiagg20",
        "filterjoin": WORKLOADS / "sec_filterjoin20",
    },
}

SINGLE_TABLE_RECIPES = {
    "mix20_balanced": {"filtered": 6, "multigroup": 7, "multiagg": 7},
    "mix10_smoke": {"filtered": 3, "multigroup": 4, "multiagg": 3},
    "mix20_agg_heavy": {"filtered": 4, "multigroup": 4, "multiagg": 12},
    "mix20_filter_heavy": {"filtered": 12, "multigroup": 4, "multiagg": 4},
    "mix20_groupby_heavy": {"filtered": 4, "multigroup": 12, "multiagg": 4},
    "mix15_spread": {"filtered": 5, "multigroup": 5, "multiagg": 5},
    "mix20_groupby_filter": {"filtered": 10, "multigroup": 8, "multiagg": 2},
}

JOIN_RECIPES = {
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

# Med has only three tables, so two JOIN keywords is the maximum depth.
MED_RECIPES = {
    "mix20_balanced": {"filtered": 4, "multigroup": 3, "multiagg": 3, "join1": 5, "join2": 5},
    "mix10_smoke": {"filtered": 2, "multigroup": 1, "multiagg": 1, "join1": 3, "join2": 3},
    "mix20_join_heavy": {"filtered": 1, "multigroup": 1, "multiagg": 1, "join1": 7, "join2": 10},
    "mix20_agg_heavy": {"filtered": 4, "multigroup": 4, "multiagg": 9, "join1": 2, "join2": 1},
    "mix20_groupby_heavy": {"filtered": 3, "multigroup": 8, "multiagg": 4, "join1": 3, "join2": 2},
    "mix20_filter_heavy": {"filtered": 12, "multigroup": 2, "multiagg": 2, "join1": 2, "join2": 2},
    "mix15_spread": {"filtered": 3, "multigroup": 2, "multiagg": 2, "join1": 4, "join2": 4},
    "mix20_join_multiagg": {"multigroup": 1, "multiagg": 7, "join1": 5, "join2": 7},
    "mix20_groupby_filter": {"filtered": 8, "multigroup": 7, "multiagg": 2, "join1": 2, "join2": 1},
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
    "join2": "join2",
    "join3": "join3",
    "basic": "basic",
}


def query_properties(sql: str) -> dict[str, Any]:
    joins = len(re.findall(r"\bJOIN\b", sql, re.IGNORECASE))
    aggregates = len(re.findall(r"\b(?:AVG|COUNT|SUM|MIN|MAX)\s*\(", sql, re.IGNORECASE))
    group_match = re.search(r"\bGROUP BY\s+(.+?)(?:\bHAVING\b|$)", sql, re.IGNORECASE)
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
    return {str(row.get("query_id") or "").strip(): row for row in rows if row.get("query_id")}


def load_pools(dataset: str) -> dict[str, list[dict[str, Any]]]:
    pools: dict[str, list[dict[str, Any]]] = {}
    for key, directory in DATASET_SOURCES[dataset].items():
        sql_rows = _load_json(directory / "query_manifest.json")
        nl_rows = _load_json(directory / "query_manifest_nl.json")
        nl_by_id = _index_by_id(nl_rows)
        pooled = []
        for row in sql_rows:
            qid = str(row.get("query_id") or "").strip()
            sql = str(row.get("sql") or "").strip()
            text = str((nl_by_id.get(qid) or {}).get("text") or "").strip()
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


def deterministic_child_seed(global_seed: int, name: str, recipe: dict[str, int], dataset: str) -> int:
    payload = json.dumps(
        {"seed": global_seed, "name": name, "recipe": recipe, "dataset": dataset},
        sort_keys=True,
        separators=(",", ":"),
    )
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")


def sample_from_pool(pool, n, rng, used):
    available = [q for q in pool if q["fingerprint"] not in used]
    if n > len(available):
        raise ValueError(f"Requested {n} unique queries but stratum only has {len(available)} available")
    chosen = rng.sample(available, n)
    for q in chosen:
        used.add(q["fingerprint"])
    return chosen


def build_mixture(name, counts, pools, rng):
    all_queries = [query for pool in pools.values() for query in pool]
    strata = {stratum: [q for q in all_queries if q["stratum"] == stratum] for stratum in STRATUM_ALIASES.values()}
    used: set[str] = set()
    picked = []
    composition = []
    for stratum in ("filtered", "multigroup", "multiagg", "join1", "join2", "join3", "basic"):
        n = int(counts.get(stratum, 0) or 0)
        if n <= 0:
            continue
        for q in sample_from_pool(strata[stratum], n, rng, used):
            item = {
                "query_id": f"q{len(picked)}",
                "sql": q["sql"],
                "text": q["text"],
                "source": q["source"],
                "source_query_id": q["source_query_id"],
                "stratum": q["stratum"],
                "properties": q["properties"],
            }
            picked.append(item)
            composition.append({k: item[k] for k in ("query_id", "source", "source_query_id", "stratum", "properties")})
    order = list(range(len(picked)))
    rng.shuffle(order)
    shuffled, shuffled_comp = [], []
    for new_pos, old_pos in enumerate(order):
        item = dict(picked[old_pos])
        item["query_id"] = f"q{new_pos}"
        shuffled.append(item)
        comp = dict(composition[old_pos])
        comp["query_id"] = f"q{new_pos}"
        shuffled_comp.append(comp)
    return {
        "name": name,
        "stratum_counts": {k: int(v) for k, v in counts.items() if int(v) > 0},
        "source_counts": dict(
            sorted({source: sum(q["source"] == source for q in shuffled) for source in pools}.items())
        ),
        "queries": shuffled,
        "composition": shuffled_comp,
    }


def write_mixture(dataset: str, mixture: dict[str, Any], seed: int) -> Path:
    out_dir = WORKLOADS / "mixtures" / dataset.lower() / mixture["name"]
    out_dir.mkdir(parents=True, exist_ok=True)
    sql_manifest = [{"query_id": q["query_id"], "sql": q["sql"]} for q in mixture["queries"]]
    nl_manifest = [{"query_id": q["query_id"], "text": q["text"]} for q in mixture["queries"]]
    meta = {
        "workload_id": f"{dataset.lower()}_{mixture['name']}",
        "title": f"{dataset} mixture ({mixture['name']})",
        "dataset": dataset,
        "n_queries": len(mixture["queries"]),
        "stratum_counts": mixture["stratum_counts"],
        "source_counts": mixture["source_counts"],
        "seed": seed,
        "child_seed": mixture["child_seed"],
        "generator_version": GENERATOR_VERSION,
        "kind": "mixture",
    }
    composition = {
        "workload_id": meta["workload_id"],
        "seed": seed,
        "stratum_counts": mixture["stratum_counts"],
        "source_counts": mixture["source_counts"],
        "picks": mixture["composition"],
    }
    (out_dir / "query_manifest.json").write_text(json.dumps(sql_manifest, indent=2) + "\n", encoding="utf-8")
    (out_dir / "query_manifest_nl.json").write_text(json.dumps(nl_manifest, indent=2) + "\n", encoding="utf-8")
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    (out_dir / "composition.json").write_text(json.dumps(composition, indent=2) + "\n", encoding="utf-8")
    return out_dir


def write_inventory() -> Path:
    path = WORKLOADS / "contrast_workloads.csv"
    rows = []
    if (WORKLOADS / "player_contrast_workloads.csv").exists():
        with (WORKLOADS / "player_contrast_workloads.csv").open(encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle))
    for directory in sorted(WORKLOADS.iterdir()):
        if not directory.is_dir() or directory.name in {"mixtures", "runs"}:
            continue
        meta_path = directory / "meta.json"
        if not meta_path.exists():
            continue
        meta = _load_json(meta_path)
        if meta.get("dataset") == "Player":
            continue
        rows.append(
            {
                "workload_id": meta.get("workload_id", directory.name),
                "kind": meta.get("kind", "pure"),
                "focus": meta.get("focus", ""),
                "n_queries": meta.get("n_queries", ""),
                "sql_manifest": f"case study/workloads/{directory.name}/query_manifest.json",
                "nl_manifest": f"case study/workloads/{directory.name}/query_manifest_nl.json",
                "dataset": meta.get("dataset", ""),
                "enabled": 1 if meta.get("kind") != "mixture" else 0,
                "notes": meta.get("contrast_with", ""),
            }
        )
    mix_root = WORKLOADS / "mixtures"
    if mix_root.exists():
        for dataset_dir in sorted(p for p in mix_root.iterdir() if p.is_dir()):
            if dataset_dir.name in {
                "mix10_smoke",
                "mix15_spread",
                "mix20_agg_heavy",
                "mix20_balanced",
                "mix20_filter_heavy",
                "mix20_groupby_filter",
                "mix20_groupby_heavy",
                "mix20_join_heavy",
                "mix20_join_multiagg",
                "mix25_roundrobin",
            }:
                continue
            for directory in sorted(p for p in dataset_dir.iterdir() if p.is_dir()):
                meta_path = directory / "meta.json"
                if not meta_path.exists():
                    continue
                meta = _load_json(meta_path)
                rel = directory.relative_to(CASE)
                rows.append(
                    {
                        "workload_id": meta.get("workload_id", directory.name),
                        "kind": "mixture",
                        "focus": meta.get("title", ""),
                        "n_queries": meta.get("n_queries", ""),
                        "sql_manifest": f"{rel}/query_manifest.json",
                        "nl_manifest": f"{rel}/query_manifest_nl.json",
                        "dataset": meta.get("dataset", ""),
                        "enabled": 0,
                        "notes": "disabled by default; set enabled=1 to include",
                    }
                )
    fieldnames = [
        "workload_id",
        "kind",
        "focus",
        "n_queries",
        "sql_manifest",
        "nl_manifest",
        "dataset",
        "enabled",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def mix_dataset(dataset: str, seed: int, only: str) -> None:
    if dataset == "Med":
        recipes = dict(MED_RECIPES)
    elif dataset == "SEC":
        recipes = dict(JOIN_RECIPES)
    else:
        recipes = dict(SINGLE_TABLE_RECIPES)
    if only.strip():
        recipes = {name: recipes[name] for name in only.split(",") if name.strip()}
    pools = load_pools(dataset)
    for name, counts in recipes.items():
        child_seed = deterministic_child_seed(seed, name, counts, dataset)
        mixture = build_mixture(name, counts, pools, random.Random(child_seed))
        mixture["child_seed"] = child_seed
        out_dir = write_mixture(dataset, mixture, seed)
        print(f"wrote {out_dir} ({len(mixture['queries'])} queries) {mixture['stratum_counts']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="all", help="Art, CSPaper, Finan, Legal, Med, SEC, or all")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--only", default="", help="Comma-separated mixture names")
    args = parser.parse_args()
    names = list(DATASET_SOURCES) if args.dataset.lower() == "all" else [args.dataset]
    lookup = {name.lower(): name for name in DATASET_SOURCES}
    for raw in names:
        key = lookup.get(raw.lower())
        if not key:
            raise SystemExit(f"Unknown dataset {raw!r}. Expected {sorted(DATASET_SOURCES)}")
        print(f"=== {key} ===")
        mix_dataset(key, args.seed, args.only)
    path = write_inventory()
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
