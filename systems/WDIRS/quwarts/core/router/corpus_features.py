"""Zero-token corpus features per table: context fit, read cost, label-surface gap."""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.router.constants import FROZEN
from quwarts.core.router.registry import CorpusSpec, TableSpec
from quwarts.core.router.text import prepare_document


def _doc_key(path: Path) -> tuple[int, str]:
    return (int(path.stem), "") if path.stem.isdigit() else (1 << 60, path.stem)


def list_documents(table: TableSpec) -> list[Path]:
    return sorted(table.doc_dir.glob("*.txt"), key=_doc_key)


def read_document(path: Path) -> str:
    return path.read_text(errors="replace")


def deterministic_sample(items: list[Any], k: int, salt: str) -> list[Any]:
    rng = random.Random(f"{FROZEN['probe_seed']}:{salt}")
    if len(items) <= k:
        return list(items)
    return sorted(rng.sample(items, k), key=items.index)


def length_stratified_sample(paths: list[Path], tokens: dict[str, int], k: int, salt: str) -> list[Path]:
    """One document from each of ``k`` equal-size length strata (short to long)."""

    if len(paths) <= k:
        return list(paths)
    ordered = sorted(paths, key=lambda path: (tokens[path.name], path.name))
    rng = random.Random(f"{FROZEN['probe_seed']}:{salt}")
    picks = []
    for index in range(k):
        lo = index * len(ordered) // k
        hi = max(lo + 1, (index + 1) * len(ordered) // k)
        picks.append(ordered[rng.randrange(lo, hi)])
    return picks


@dataclass
class TableCorpus:
    table: str
    n_docs: int
    tokens: dict[str, int]

    def read_tokens(self, doc: str) -> int:
        """Tokens one whole-document (truncated to the window) call spends on ``doc``."""

        return min(self.tokens[doc], int(FROZEN["context_window_tokens"])) + int(FROZEN["call_overhead_tokens"])

    def window_tokens(self, doc: str) -> int:
        return min(self.tokens[doc], int(FROZEN["window_tokens"])) + int(FROZEN["call_overhead_tokens"])

    def full_read_cost(self) -> int:
        return sum(self.read_tokens(doc) for doc in self.tokens)

    def window_read_cost(self) -> int:
        return sum(self.window_tokens(doc) for doc in self.tokens)

    def summary(self) -> dict[str, Any]:
        values = sorted(self.tokens.values()) or [0]
        window = int(FROZEN["context_window_tokens"])
        median = statistics.median(values)
        return {
            "n_docs": self.n_docs,
            "tokens_total": sum(values),
            "tokens_median": median,
            "tokens_p90": values[min(len(values) - 1, int(0.9 * len(values)))],
            # lambda > 1: a typical document does not fit one call.
            "context_fit_lambda": median / window,
            "fit_fraction": sum(1 for value in values if value <= window) / len(values),
            "full_read_cost": self.full_read_cost(),
            "window_read_cost": self.window_read_cost(),
        }


def table_corpus(table: TableSpec) -> TableCorpus:
    paths = list_documents(table)
    tokens = {path.name: count_tokens(read_document(path)) for path in paths}
    return TableCorpus(table=table.sql_name, n_docs=len(paths), tokens=tokens)


def label_surface(literals: list[str], documents_lower: list[str]) -> float | None:
    """Share of workload labels that occur verbatim in sampled documents.

    A low value means the workload's vocabulary is not the corpus's vocabulary:
    values must be interpreted or normalized, not copied.
    """

    labels = [label.lower() for label in literals if label and not label.replace(".", "").isdigit()]
    if not labels:
        return None
    joined = "\n".join(documents_lower)
    variants = lambda label: {label, label.replace("_", " "), label.replace("_", "-")}  # noqa: E731
    hits = sum(1 for label in labels if any(variant in joined for variant in variants(label)))
    return hits / len(labels)


def corpus_features(spec: CorpusSpec, workload: dict[str, Any]) -> dict[str, Any]:
    tables: dict[str, Any] = {}
    corpora: dict[str, TableCorpus] = {}
    for table in spec.tables:
        corpus = table_corpus(table)
        corpora[table.sql_name] = corpus
        paths = list_documents(table)
        sample = deterministic_sample(paths, int(FROZEN["corpus_sample_docs"]), f"surface:{table.sql_name}")
        lowered = [prepare_document(read_document(path)) for path in sample]
        surface = {}
        for use in workload["attributes"].values():
            if use.table == table.sql_name:
                surface[use.qualified] = label_surface(use.literals, lowered)
        tables[table.sql_name] = {**corpus.summary(), "label_surface": surface}
    return {"tables": tables, "corpora": corpora}
