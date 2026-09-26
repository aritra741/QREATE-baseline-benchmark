"""Text utilities shared by zero-token features and probes: grounding and anchors."""

from __future__ import annotations

import re
from typing import Any

_WS = re.compile(r"\s+")
_NUM = re.compile(r"^[+-]?\d[\d,]*(?:\.\d+)?$")
_DIGITS = re.compile(r"\d+")
_ANCHOR_MAX = 40


def normalize(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    return _WS.sub(" ", text)


def is_null(value: Any) -> bool:
    if value is None:
        return True
    text = normalize(value)
    return text in {"", "null", "none", "n/a", "na", "not found", "not_present", "unknown"}


def numeric_forms(text: str) -> list[str]:
    """Surface spellings of a number that may appear in a document."""

    raw = text.replace(",", "")
    try:
        number = float(raw)
    except ValueError:
        return [text]
    forms = {text, raw}
    if number.is_integer():
        whole = int(number)
        forms.add(str(whole))
        forms.add(f"{whole:,}")
    else:
        forms.add(f"{number:g}")
    return sorted(forms, key=len, reverse=True)


def find_span(value: Any, document_lower: str) -> int:
    """Offset of the value in the lowercased, whitespace-collapsed document, or -1."""

    text = normalize(value)
    if not text:
        return -1
    candidates = numeric_forms(text) if _NUM.match(text) else [text]
    for candidate in candidates:
        if not candidate:
            continue
        if _NUM.match(candidate):
            # Numbers must not be a fragment of a longer number ("0" inside "2008").
            pattern = re.compile(r"(?<![\d.,])" + re.escape(candidate) + r"(?![\d])")
            match = pattern.search(document_lower)
            if match:
                return match.start()
            continue
        index = document_lower.find(candidate)
        if index >= 0:
            return index
    return -1


def prepare_document(text: str) -> str:
    return _WS.sub(" ", (text or "").lower())


def grounded(value: Any, document_lower: str) -> bool:
    return find_span(value, document_lower) >= 0


def anchor(document_lower: str, offset: int) -> str:
    """Normalized textual cue immediately before a span: the label a program would key on."""

    if offset < 0:
        return ""
    left = document_lower[max(0, offset - 120):offset]
    for sep in (" | ", ": ", " - ", ". ", "\n"):
        cut = left.rfind(sep.strip()) if sep.strip() else -1
        if cut >= 0 and len(left) - cut <= _ANCHOR_MAX + 5:
            left = left[max(0, cut - _ANCHOR_MAX):]
            break
    left = left[-_ANCHOR_MAX:]
    left = _DIGITS.sub("#", left)
    words = left.split(" ")
    if len(words) > 1:
        words = words[1:]  # drop a possibly truncated first word
    return " ".join(word for word in words if word).strip()
