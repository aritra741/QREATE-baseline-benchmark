"""Deterministic relevance-ranked corpus subsets for smoke testing."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Sequence


def build_representative_subset(
    source_dataset: Path,
    query_texts: Sequence[str],
    destination_root: Path,
    *,
    max_documents_per_entity: int,
) -> tuple[Path, list[str]]:
    if max_documents_per_entity < 1:
        raise ValueError("max documents per entity must be positive")
    source_dataset = Path(source_dataset).expanduser().resolve()
    terms = {
        token.lower()
        for query in query_texts
        for token in re.findall(r"[A-Za-z][A-Za-z0-9'-]*", query)
        if len(token) > 2
    }
    selected: list[str] = []
    target_dataset = destination_root / source_dataset.name
    for entity_dir in sorted(
        path for path in source_dataset.iterdir() if path.is_dir()
    ):
        ranked = []
        for path in sorted(entity_dir.glob("**/*.txt")):
            text = path.read_text(
                encoding="utf-8", errors="replace"
            ).lower()
            score = sum(term in text for term in terms)
            ranked.append((score, path))
        chosen = [
            path
            for _score, path in sorted(
                ranked, key=lambda item: (-item[0], str(item[1]))
            )[:max_documents_per_entity]
        ]
        for path in chosen:
            relative = path.relative_to(source_dataset)
            target = target_dataset / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            selected.append(str(relative))
    if not selected:
        raise ValueError(f"no source documents found under {source_dataset}")
    return Path(destination_root), selected
