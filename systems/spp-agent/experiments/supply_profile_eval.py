#!/usr/bin/env python3
"""Report real corpus supply profiles and compare recommendations to empirical bests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))
sys.path.insert(0, str(SPP_ROOT.parent.parent))

from agent.phases.supply_profile import build_supply_profile
from data.instance_builder import build_instance

# Empirical best configs from prior five-slice / norm-llm probes (Player workload).
EMPIRICAL_BEST = {
    "agg_only": "er=embedding_0.7|norm=dictionary|unit=none|miss=constant|coerce=llm",
    "agg_filter": "er=embedding_0.8|norm=llm|unit=unit|miss=drop|coerce=llm",
    "agg_join": "er=embedding_0.7|norm=dictionary|unit=none|miss=constant|coerce=llm",
    "agg_filter_join": "er=embedding_0.8|norm=llm|unit=unit|miss=drop|coerce=llm",
    "agg_temporal": "er=embedding_0.7|norm=dictionary|unit=none|miss=constant|coerce=llm",
}


def _player_column_demand() -> dict:
    return {
        "columns": [
            {
                "column": "nationality",
                "roles": ["group_key", "filter"],
                "aggregation_functions": ["COUNT"],
                "query_ids": [],
            },
            {
                "column": "position",
                "roles": ["group_key"],
                "aggregation_functions": ["COUNT"],
                "query_ids": [],
            },
            {
                "column": "player.team",
                "roles": ["group_key", "join_key"],
                "aggregation_functions": [],
                "query_ids": [],
            },
            {
                "column": "team.team_name",
                "roles": ["join_key"],
                "aggregation_functions": [],
                "query_ids": [],
            },
        ],
        "has_join": True,
        "has_temporal": True,
    }


def _config_matches_recommendations(config_id: str, rec: dict) -> dict[str, bool]:
    parts = dict(p.split("=", 1) for p in config_id.split("|") if "=" in p)
    return {
        "norm": parts.get("norm") == rec.get("norm_recommendation"),
        "coerce": parts.get("coerce") == rec.get("coerce_recommendation"),
        "er": (
            parts.get("er", "").startswith("llm")
            if rec.get("er_recommendation") == "llm"
            else parts.get("er", "").startswith("embedding")
        ),
    }


def main() -> None:
    instance = build_instance("Player", include_ground_truth=False)
    demand = _player_column_demand()
    profile = build_supply_profile(instance.corpus, demand, instance.schema)

    target_cols = {"nationality", "position", "player.team", "team"}
    print("=== Supply profiles (nationality, position, team) ===\n")
    for col_entry in profile["columns"]:
        bare = col_entry["column"].split(".")[-1]
        if col_entry["column"] not in target_cols and bare not in target_cols:
            continue
        print(json.dumps(col_entry, indent=2))
        print()

    slice_columns = {
        "agg_only": {"nationality", "position"},
        "agg_filter": {"nationality"},
        "agg_join": {"position", "team", "player.team"},
        "agg_filter_join": {"nationality", "team", "player.team"},
        "agg_temporal": {"birth_date", "age"},
    }

    print("=== Recommendation vs empirical best configs ===\n")
    for slice_name, config_id in EMPIRICAL_BEST.items():
        relevant = slice_columns.get(slice_name, set())
        agg_rec = {
            "norm_recommendation": "dictionary",
            "coerce_recommendation": "strict",
            "er_recommendation": "embedding",
        }
        votes = {"norm": {}, "coerce": {}, "er": {}}
        for col_entry in profile["columns"]:
            bare = col_entry["column"].split(".")[-1]
            if bare not in relevant and col_entry["column"] not in relevant:
                continue
            rec = col_entry.get("recommendations", {})
            for dim in ("norm", "coerce", "er"):
                val = rec.get(f"{dim}_recommendation", agg_rec[f"{dim}_recommendation"])
                votes[dim][val] = votes[dim].get(val, 0) + 1
        for dim in ("norm", "coerce", "er"):
            if votes[dim]:
                agg_rec[f"{dim}_recommendation"] = max(votes[dim], key=votes[dim].get)
        match = _config_matches_recommendations(config_id, agg_rec)
        print(f"{slice_name}: {config_id}")
        print(f"  slice-relevant profiler prefs: {agg_rec}")
        print(f"  matches: {match}")
        print()

    out_path = SPP_ROOT / "results" / "supply_profile_player.json"
    out_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    print(f"Wrote full profile to {out_path}")


if __name__ == "__main__":
    main()
