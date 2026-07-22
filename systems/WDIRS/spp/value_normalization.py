"""Deterministic, domain-independent relational value normalization."""

from __future__ import annotations

import re
from typing import Optional


def canonical_date(value: object) -> Optional[str]:
    """Normalize common date surfaces to the benchmark-neutral Y/M/D form."""
    rendered = str(value).strip()
    numeric = re.fullmatch(
        r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", rendered
    )
    if numeric:
        return (
            f"{int(numeric.group(1))}/{int(numeric.group(2))}/"
            f"{int(numeric.group(3))}"
        )
    months = {
        name.lower(): index
        for index, name in enumerate(
            (
                "",
                "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November",
                "December",
            )
        )
        if name
    }
    named = re.fullmatch(
        r"(" + "|".join(months) + r")\s+(\d{1,2}),\s*(\d{4})",
        rendered,
        re.IGNORECASE,
    )
    if named:
        return (
            f"{int(named.group(3))}/{months[named.group(1).lower()]}/"
            f"{int(named.group(2))}"
        )
    return None
