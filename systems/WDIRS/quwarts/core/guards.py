"""Runtime guards for Section 3 invariants."""

from __future__ import annotations

from pathlib import Path


GOLD_MARKERS = ("data/gold", "data\\gold")


def assert_not_gold(path: Path | str, *, kind: str = "path") -> Path:
    """Core code must not open gold answers."""

    resolved = Path(path)
    text = str(resolved).replace("\\", "/").lower()
    if "data/gold" in text or resolved.name.lower() in {"gold.csv", "answers.csv"}:
        raise PermissionError(f"{kind} crosses the evaluation firewall: {resolved}")
    return resolved
