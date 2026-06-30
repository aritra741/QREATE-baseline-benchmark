"""Dataset-specific paths, corpus table aliases, and experiment artifact names."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from data.aggregation_slices import AGGREGATION_SLICE_ORDER
from utils.config import load_config

MED_DATASET = "Med"
PLAYER_DATASET = "Player"
FINAN_DATASET = "Finan"
ART_DATASET = "Art"
CSPAPER_DATASET = "CSPaper"
SEC_DATASET = "SEC"

# Healthcare corpus folders -> SQL / ground-truth table names.
MED_CORPUS_FOLDER_TO_TABLE: dict[str, str] = {
    "disease_small": "disease",
    "drug_small": "drug",
    "institutes_small": "institution",
}

MED_TABLE_TO_CORPUS_FOLDER: dict[str, str] = {
    v: k for k, v in MED_CORPUS_FOLDER_TO_TABLE.items()
}

SUPPORTED_MULTI_TABLE_DATASETS = frozenset({PLAYER_DATASET, MED_DATASET})

# Finan is a single-table dataset — one corpus folder maps to one table.
# The GT CSV is named "Finan.csv" so the GT table is "Finan", but SQL queries
# reference "finance". Both names map to the same table.
FINAN_CORPUS_FOLDER_TO_TABLE: dict[str, str] = {
    "finance": "finance",
    "finan": "finance",
}
FINAN_TABLE_TO_CORPUS_FOLDER: dict[str, str] = {
    "finance": "finance",
    "finan": "finance",
}
# Canonical SQL table name for Finan (used in queries)
FINAN_SQL_TABLE = "finance"
FINAN_GT_TABLE = "Finan"

ART_CORPUS_FOLDER_TO_TABLE: dict[str, str] = {
    "wikiart": "art",
    "art": "art",
}
ART_TABLE_TO_CORPUS_FOLDER: dict[str, str] = {
    "art": "wikiart",
}
ART_SQL_TABLE = "art"
ART_GT_TABLE = "Art"

# CSPaper: single-table dataset. GT CSV = CSPaper.csv → table "cspaper".
# Corpus docs are in source_data/CSPaper/txt/ (PDF stems as filenames).
CSPAPER_CORPUS_FOLDER_TO_TABLE: dict[str, str] = {
    "txt": "cspaper",
    "cspaper": "cspaper",
}
CSPAPER_TABLE_TO_CORPUS_FOLDER: dict[str, str] = {
    "cspaper": "txt",
}
CSPAPER_SQL_TABLE = "cspaper"
CSPAPER_GT_TABLE = "CSPaper"

SEC_CORPUS_FOLDER_TO_TABLE: dict[str, str] = {
    "company": "company",
    "filing": "filing",
    "filing_metrics": "filing_metrics",
}
SEC_TABLE_TO_CORPUS_FOLDER: dict[str, str] = {
    v: k for k, v in SEC_CORPUS_FOLDER_TO_TABLE.items()
}


def normalize_dataset_name(name: str) -> str:
    aliases = {
        "med": MED_DATASET,
        "medical": MED_DATASET,
        "healthcare": MED_DATASET,
        "player": PLAYER_DATASET,
        "finan": FINAN_DATASET,
        "finance": FINAN_DATASET,
        "financial": FINAN_DATASET,
        "art": ART_DATASET,
        "wikiart": ART_DATASET,
        "cspaper": CSPAPER_DATASET,
        "cs_paper": CSPAPER_DATASET,
        "cspapers": CSPAPER_DATASET,
        "sec": SEC_DATASET,
        "secbench": SEC_DATASET,
    }
    key = (name or PLAYER_DATASET).strip()
    return aliases.get(key.lower(), key)


def corpus_folder_to_table(dataset: str, folder: str) -> str:
    ds = normalize_dataset_name(dataset)
    if ds == MED_DATASET:
        return MED_CORPUS_FOLDER_TO_TABLE.get(folder.lower(), folder.lower())
    if ds == FINAN_DATASET:
        return FINAN_CORPUS_FOLDER_TO_TABLE.get(folder.lower(), folder.lower())
    if ds == ART_DATASET:
        return ART_CORPUS_FOLDER_TO_TABLE.get(folder.lower(), folder.lower())
    if ds == CSPAPER_DATASET:
        return CSPAPER_CORPUS_FOLDER_TO_TABLE.get(folder.lower(), folder.lower())
    if ds == SEC_DATASET:
        return SEC_CORPUS_FOLDER_TO_TABLE.get(folder.lower(), folder.lower())
    return folder.lower()


def table_to_corpus_folder(dataset: str, table: str) -> str:
    ds = normalize_dataset_name(dataset)
    if ds == MED_DATASET:
        return MED_TABLE_TO_CORPUS_FOLDER.get(table.lower(), table.lower())
    if ds == FINAN_DATASET:
        return FINAN_TABLE_TO_CORPUS_FOLDER.get(table.lower(), table.lower())
    if ds == ART_DATASET:
        return ART_TABLE_TO_CORPUS_FOLDER.get(table.lower(), table.lower())
    if ds == CSPAPER_DATASET:
        return CSPAPER_TABLE_TO_CORPUS_FOLDER.get(table.lower(), table.lower())
    if ds == SEC_DATASET:
        return SEC_TABLE_TO_CORPUS_FOLDER.get(table.lower(), table.lower())
    return table.lower()


def schema_tables_from_corpus(corpus: list[dict], *, dataset: str) -> set[str]:
    """Map corpus doc prefixes / hints to schema table names."""
    tables: set[str] = set()
    for doc in corpus:
        doc_id = doc.get("doc_id", "")
        prefix = doc_id.split("/")[0].lower() if "/" in doc_id else doc_id.split("_")[0].lower()
        if prefix:
            tables.add(corpus_folder_to_table(dataset, prefix))
        hint = str(doc.get("metadata", {}).get("table_hint", "")).lower()
        if hint:
            tables.add(corpus_folder_to_table(dataset, hint))
    return tables


def default_table_filter(dataset: str) -> set[str]:
    dataset = normalize_dataset_name(dataset)
    cfg = load_config()
    ds_cfg = cfg.get("datasets", {}).get(dataset, {})
    if isinstance(ds_cfg, dict) and ds_cfg.get("table_filter"):
        return set(ds_cfg["table_filter"])
    phase0 = cfg.get("phase0", {})
    if dataset == MED_DATASET:
        return set(phase0.get("med_table_filter", ["disease", "drug", "institution"]))
    if dataset == FINAN_DATASET:
        return {"finance"}
    if dataset == ART_DATASET:
        return {"art"}
    if dataset == CSPAPER_DATASET:
        return {"cspaper"}
    if dataset == SEC_DATASET:
        return {"filing_metrics"}
    return set(phase0.get("table_filter", ["player"]))


def workload_slices_for_dataset(dataset: str, *, feasible_counts: dict[str, int] | None = None) -> list[str]:
    """Aggregation slices to use for a dataset (skip empty slices)."""
    dataset = normalize_dataset_name(dataset)
    cfg = load_config()
    ds_cfg = cfg.get("datasets", {}).get(dataset, {})
    configured = ds_cfg.get("workload_slices") if isinstance(ds_cfg, dict) else None
    if not configured:
        configured = cfg.get("phase0", {}).get("workload_slices", list(AGGREGATION_SLICE_ORDER))
    if feasible_counts is None:
        return list(configured)
    return [name for name in configured if feasible_counts.get(name, 0) > 0]


def dataset_phase0_settings(dataset: str) -> dict[str, Any]:
    """Merge global phase0 settings with per-dataset overrides."""
    cfg = load_config()
    phase0 = dict(cfg.get("phase0", {}))
    ds_key = normalize_dataset_name(dataset)
    ds_block = cfg.get("datasets", {}).get(ds_key, {})
    if isinstance(ds_block, dict):
        for key in (
            "num_docs",
            "num_probe_configs",
            "num_judge_pairs",
            "num_eval_queries",
            "queries_per_slice",
            "min_queries_per_slice",
            "budget_levels",
            "workload_slices",
            "table_filter",
            "workload_split",
            "restrict_gt_to_corpus",
        ):
            if key in ds_block:
                phase0[key] = ds_block[key]
    if ds_key == MED_DATASET and "table_filter" not in phase0:
        phase0["table_filter"] = list(default_table_filter(ds_key))
    return phase0


def dataset_phase1_settings(dataset: str) -> dict[str, Any]:
    cfg = load_config()
    phase1 = dict(cfg.get("phase1", {}))
    ds_key = normalize_dataset_name(dataset)
    ds_block = cfg.get("datasets", {}).get(ds_key, {})
    if isinstance(ds_block, dict):
        for key in ("slice", "glass_box_spread_threshold"):
            if key in ds_block:
                phase1[key] = ds_block[key]
        if ds_block.get("source_phase0"):
            phase1["source_phase0"] = ds_block["source_phase0"]
        if ds_block.get("output_file"):
            phase1["output_file"] = ds_block["output_file"]
        if ds_block.get("probe_context_cache"):
            phase1["probe_context_cache"] = ds_block["probe_context_cache"]
    else:
        suffix = "" if ds_key == PLAYER_DATASET else f"_{ds_key}"
        phase1.setdefault("source_phase0", f"phase0_reward_table{suffix}.json")
        phase1.setdefault("output_file", f"phase1_comparison{suffix}_agg_only.json")
        phase1.setdefault("probe_context_cache", f"phase1{suffix}_agg_only_probe_context.json")
    return phase1


def results_dir_for_dataset(dataset: str, *, base: Path | None = None) -> Path:
    """Per-dataset results directory (Player uses the root results dir)."""
    cfg = load_config()
    root = base or Path(cfg["paths"]["results_dir"])
    ds_key = normalize_dataset_name(dataset)
    if ds_key == PLAYER_DATASET:
        path = root
    else:
        path = root / ds_key
    path.mkdir(parents=True, exist_ok=True)
    return path


def phase0_reward_table_path(results_dir: Path, dataset: str) -> Path:
    ds_key = normalize_dataset_name(dataset)
    return results_dir / f"phase0_reward_table_{ds_key}.json"


def phase0_checkpoint_path(results_dir: Path, dataset: str) -> Path:
    return phase0_reward_table_path(results_dir, dataset).with_suffix(".checkpoint.json")


def phase1_comparison_path(results_dir: Path, dataset: str) -> Path:
    phase1 = dataset_phase1_settings(dataset)
    return results_dir / phase1.get("output_file", "phase1_comparison_Player_agg_only.json")


def phase1_probe_cache_path(results_dir: Path, dataset: str) -> Path:
    phase1 = dataset_phase1_settings(dataset)
    return results_dir / phase1.get("probe_context_cache", "phase1_agg_only_probe_context.json")


def smoke_test_path(results_dir: Path, dataset: str) -> Path:
    ds_key = normalize_dataset_name(dataset)
    suffix = "" if ds_key == PLAYER_DATASET else f"_{ds_key}"
    return results_dir / f"smoke_test{suffix}.json"


def precheck_path(results_dir: Path, dataset: str) -> Path:
    ds_key = normalize_dataset_name(dataset)
    suffix = "" if ds_key == PLAYER_DATASET else f"_{ds_key}"
    return results_dir / f"precheck{suffix}.json"


def config_grid_output_dir(results_dir: Path, dataset: str) -> str:
    ds_key = normalize_dataset_name(dataset)
    if ds_key == PLAYER_DATASET:
        return "config_grid_test"
    return f"config_grid_test_{ds_key}"


def workload_split_targets(dataset: str) -> dict[str, int]:
    phase0 = dataset_phase0_settings(dataset)
    split_cfg = phase0.get("workload_split") or {}
    return {
        "train": int(split_cfg.get("train_per_slice", 20)),
        "dev": int(split_cfg.get("dev_per_slice", 5)),
        "test": int(split_cfg.get("test_per_slice", 5)),
        "min_train_total": int(split_cfg.get("min_train_total", 100)),
    }
