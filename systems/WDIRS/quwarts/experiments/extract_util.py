"""Shared extract helpers. Field names drive context; no gold-value hints."""

from __future__ import annotations

import re
from pathlib import Path

_STOP = {
    "a", "an", "the", "of", "on", "in", "to", "for", "and", "or",
    "is", "are", "use", "uses", "used", "amount",
}


def field_terms(name: str) -> list[str]:
    parts = [part for part in re.split(r"[_\W]+", name.lower()) if part and part not in _STOP]
    terms = list(parts)
    if len(parts) >= 2:
        terms.append(" ".join(parts))
        terms.append("-".join(parts))
    return list(dict.fromkeys(term for term in terms if len(term) > 1))


def schema_context(text: str, fields: list[str], limit: int = 12000) -> str:
    """Keep the head/tail plus windows around schema field tokens."""
    if len(text) <= limit:
        return text
    head_n = int(limit * 0.35)
    tail_n = int(limit * 0.12)
    budget = limit - head_n - tail_n
    extras: list[str] = []
    used = 0
    lower = text.lower()
    for field in fields:
        for term in field_terms(field):
            pos = 0
            found = 0
            while found < 3:
                idx = lower.find(term, pos)
                if idx < 0:
                    break
                start = max(0, idx - 240)
                chunk = text[start : idx + 520]
                extras.append(chunk)
                used += len(chunk)
                found += 1
                pos = idx + max(len(term), 48)
                if used >= budget:
                    break
            if used >= budget:
                break
        if used >= budget:
            break
    body = "\n...\n".join(extras)
    return (text[:head_n] + "\n...\n" + body + "\n...\n" + text[-tail_n:])[:limit]


def extract_pdf_text(path: Path) -> str:
    text = ""
    try:
        from pdfminer.high_level import extract_text
        text = extract_text(str(path)) or ""
    except Exception:
        try:
            from pypdf import PdfReader
            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        except Exception:
            text = ""
    return re.sub(r"[ \t]+", " ", text).strip()


def cached_pdf_text(pdf_path: Path, cache_dir: Path) -> str:
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / f"{pdf_path.stem}.txt"
    if dest.exists() and dest.stat().st_size > 0:
        return dest.read_text(encoding="utf-8", errors="replace")
    text = extract_pdf_text(pdf_path)
    if text:
        dest.write_text(text, encoding="utf-8")
    return text


def longer_text(*candidates: str) -> str:
    return max(candidates, key=len) if candidates else ""
