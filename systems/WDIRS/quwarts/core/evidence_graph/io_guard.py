"""Block gold, scorers, DocETL answers, and prior Legal diagnostics."""

from __future__ import annotations

import builtins
from pathlib import Path

_OPEN = builtins.open

_BLOCK_FRAGMENTS = (
    "ground_truth",
    "/gold/",
    "gold.json",
    "official_bags",
    "query_tables",
    "docetl_legal",
    "shared_reachability",
    "cost_aware_reachability",
    "evidence_card_aggregation_audit",
    "quwarts_legal_pairwise_ab",
    "quwarts_legal_forced_binary",
    "quwarts_legal_corpus_probe",
    "quwarts_legal_checked_rank",
    "observable_sidecar/live",
    "observable_sidecar/decisions",
    "generation_live",
    "legal.csv",
)

_ALLOW_SUFFIXES = (
    "observables.json",
    "legal_attributes.json",
)


def is_blocked(path: str | Path) -> bool:
    text = str(path).replace("\\", "/").lower()
    if any(text.endswith(suffix) for suffix in _ALLOW_SUFFIXES):
        return False
    return any(fragment in text for fragment in _BLOCK_FRAGMENTS)


def guard_open(path, *args, **kwargs):
    if is_blocked(path):
        raise PermissionError(f"gold_or_diagnostic_blocked:{path}")
    return _OPEN(path, *args, **kwargs)


def install() -> None:
    builtins.open = guard_open
