"""Investigate whether ER has real work to do on Med.

For each key entity column (generic_name, disease_name, institution_name, etc.),
compare the raw extracted values against the ground-truth values to see:
  - How many extracted values are exact-match GT names
  - How many are novel / variant forms
  - Concrete examples of non-canonical names that ER could in principle merge

Run from systems/spp-agent/:
    python -m diagnostics.inspect_er_canonicality [--dataset Med] [--slice agg_only]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from data.dataset_registry import results_dir_for_dataset

# ── config ────────────────────────────────────────────────────────────────────
# GT paths are relative to the repo root (two levels above systems/spp-agent)
DATASET_GT = {
    "Med": {
        "drug":        ("Data/Med/drug.csv",        "generic_name"),
        "disease":     ("Data/Med/disease.csv",     "disease_name"),
        "institution": ("Data/Med/institution.csv", "institution_name"),
    }
}


def _load_gt_names(gt_path: Path, col: str) -> set[str]:
    df = pd.read_csv(gt_path, low_memory=False)
    # GT names may be pipe-separated multi-values; normalise each part
    names: set[str] = set()
    for raw in df[col].dropna():
        for part in str(raw).split("||"):
            names.add(part.strip().lower())
    return names


def _load_extracted_names(cache_path: Path, table: str, col: str) -> list[str]:
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    tuples = payload.get("extraction", {}).get("tuples_by_table", {}).get(table, [])
    values: list[str] = []
    for row in tuples:
        if isinstance(row, dict):
            val = row.get(col)
        elif isinstance(row, list) and len(row) > 0:
            val = row[0]
        else:
            continue
        if val is not None:
            values.append(str(val).strip())
    return values


def _analyse(dataset: str) -> None:
    gt_specs = DATASET_GT.get(dataset)
    if gt_specs is None:
        print(f"No GT spec for dataset '{dataset}'. Available: {list(DATASET_GT)}")
        return

    results_dir = results_dir_for_dataset(dataset)
    # test_config_grid writes extraction_cache.json inside its output dir
    grid_dir = next(results_dir.glob("config_grid_test_*"), None)
    if grid_dir is None:
        print(f"No config_grid_test_* directory found under {results_dir}")
        print("Run test_config_grid first.")
        return
    cache_path = grid_dir / "extraction_cache.json"
    if not cache_path.exists():
        print(f"Cache not found: {cache_path}")
        print("Run test_config_grid first so extraction is cached.")
        return

    print(f"\n{'='*70}")
    print(f"ER Canonicality Audit  |  dataset={dataset}")
    print(f"Cache: {cache_path}")
    print(f"{'='*70}")

    for table, (gt_rel, key_col) in gt_specs.items():
        # GT CSVs live two directories above systems/spp-agent (i.e., the repo root)
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        gt_path = repo_root / gt_rel
        if not gt_path.exists():
            print(f"\n[{table}] GT file not found: {gt_path}")
            continue

        gt_names = _load_gt_names(gt_path, key_col)
        extracted = _load_extracted_names(cache_path, table, key_col)

        if not extracted:
            print(f"\n[{table}] No extracted rows found for column '{key_col}'.")
            continue

        exact_hits = [v for v in extracted if v.lower() in gt_names]
        misses     = [v for v in extracted if v.lower() not in gt_names]
        unique_ext = list(dict.fromkeys(extracted))       # deduplicated, order-preserved
        unique_hits = [v for v in unique_ext if v.lower() in gt_names]
        unique_miss = [v for v in unique_ext if v.lower() not in gt_names]

        print(f"\n[{table}.{key_col}]")
        print(f"  GT distinct names      : {len(gt_names)}")
        print(f"  Extracted rows         : {len(extracted)}")
        print(f"  Exact-match rows       : {len(exact_hits)}  ({100*len(exact_hits)/max(len(extracted),1):.1f}%)")
        print(f"  Non-canonical rows     : {len(misses)}  ({100*len(misses)/max(len(extracted),1):.1f}%)")
        print(f"  Unique extracted       : {len(unique_ext)}")
        print(f"  Unique exact-match     : {len(unique_hits)}")
        print(f"  Unique non-canonical   : {len(unique_miss)}")

        if unique_miss:
            print(f"\n  Sample non-canonical values (up to 20):")
            for v in unique_miss[:20]:
                # Try to find the closest GT name by simple token overlap
                v_tokens = set(v.lower().split())
                best = max(gt_names, key=lambda g: len(v_tokens & set(g.split())), default="?")
                print(f"    extracted : {v!r}")
                print(f"    closest GT: {best!r}")
                print()
        else:
            print("  All extracted values match GT names exactly — ER has no work to do here.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="Med", help="Dataset key (default: Med)")
    args = parser.parse_args()

    _analyse(args.dataset)


if __name__ == "__main__":
    main()
