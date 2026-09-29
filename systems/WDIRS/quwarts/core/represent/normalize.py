"""Targets and the deterministic tier (T0): the representation a column must have, and the free rewrites.

A column's target comes from the workload grammar and the column's declared field (description, allowed
values, multi-valued or not, type):

* ``vocabulary``: declared allowed values and every literal the workload compares the column with exactly
  (``=``, ``!=``, ``IN``). These spellings are the ones queries can see.
* ``cores``: ``LIKE`` pattern cores; a stored value should contain them.
* ``case`` / ``separator``: the literals' conventions, for values the workload has not named yet.
* ``multi``: declared multi-valued; otherwise a stored value is one value.

T0, applied to every text cell of a targeted column (no model, no corpus rules):

1. clean: Unicode NFKC, dashes and quotes unified, whitespace collapsed, wrapping quotes and trailing
   punctuation dropped
2. vocabulary spelling: a part equal to a vocabulary value up to case, spacing and ``_``/space takes the
   vocabulary's spelling
3. conventions: a part takes the literals' separator and case convention; if it then fits the literals'
   shape family it is a new value written the workload's way and is kept
4. containment: otherwise, a part that contains exactly one vocabulary value as whole words (the longest
   when several nest; a hyphen joins words) takes that value (``Justice Flick`` -> ``Flick``,
   ``calm and neutral`` -> ``Neutral``)
5. one value or a set: a single-valued column keeps the one part in the vocabulary, else its first part;
   a multi-valued column keeps its parts once, in a canonical (sorted) order. A column declared
   multi-valued that the workload only compares with constants by ``=``/``IN`` (never ``LIKE``) is read
   as single-valued: the workload's operators state the cardinality it expects.

``status(part, target)`` says whether a part is in the vocabulary, fits the literals' shape family, or
neither (``off``): the residual that the program tier (T1) and the model tier (T2) work on.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from quwarts.core.represent.grammar import ColumnUse, shape

_DASHES = re.compile(r"[‐‑‒–—―−]")
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
SEP = " || "


@dataclass
class Target:
    table: str
    column: str
    description: str = ""
    vocabulary: list[str] = field(default_factory=list)
    declared: bool = False  # the vocabulary is a declared closed set
    cores: list[str] = field(default_factory=list)
    case: str | None = None
    separator: str | None = None
    shapes: Counter = field(default_factory=Counter)
    multi: bool = False
    numeric: bool = False
    exact_uses: int = 0
    uses: int = 0

    @property
    def key(self) -> tuple[str, str]:
        return (self.table, self.column)

    def fold(self, text: str) -> str:
        return re.sub(r"[\s_]+", " ", text).strip().casefold()

    @property
    def by_fold(self) -> dict[str, str]:
        return {self.fold(v): v for v in self.vocabulary}


def targets(uses: dict[tuple[str, str], ColumnUse], fields: dict[str, Any]) -> dict[tuple[str, str], Target]:
    out = {}
    for key, u in uses.items():
        f = fields.get(f"{key[0]}.{key[1]}")
        choices = list(getattr(f, "choices", ()) or ())
        vocab = list(dict.fromkeys(choices + sorted(x for x in u.equality if x)))
        numeric = bool(f and f.value_type in ("int", "float")) or (u.numeric > 0 and not vocab)
        declared_multi = bool(f and (f.value_type.startswith("multi") or f.multi_choice))
        # The workload's operators imply cardinality: a column it only ever compares with constants by
        # equality or IN (never LIKE) is read as one value per row, whatever the declaration allows.
        multi = declared_multi and not (u.equality and not u.like)
        out[key] = Target(key[0], key[1], getattr(f, "description", "") or "", vocab, bool(choices),
                          sorted(x for x in u.like if x), u.case_convention, u.separator, u.shapes,
                          multi, numeric, u.exact_uses,
                          u.exact_uses + sum(u.like.values()) + u.grouped_via_case + u.projected)
    return out


def clean(text: str) -> str:
    t = unicodedata.normalize("NFKC", str(text)).translate(_QUOTES)
    t = _DASHES.sub("-", t)
    t = re.sub(r"\s+", " ", t).strip().strip("\"'").strip()
    t = re.sub(r"[.,;:]+$", "", t) if t.count(".") <= 1 else t.rstrip(",;:")
    return t.strip()


def parts(value: Any) -> list[str]:
    return [p for p in (clean(x) for x in str(value).split("||")) if p]


def _words(text: str) -> str:
    """Whole words for containment; a hyphen joins (``Neo-Expressionism``, ``19th-20th`` are one word)."""

    return " " + re.sub(r"[^\w-]+|_", " ", text.casefold()).strip() + " "


def contained(part: str, target: Target) -> str | None:
    """The one vocabulary value the part contains as whole words (the longest if several nest)."""

    w = _words(part)
    hits = [v for v in target.vocabulary if _words(v).strip() and _words(v) in w]
    if not hits:
        return None
    hits.sort(key=lambda v: -len(_words(v)))
    longest = [h for h in hits if len(_words(h)) == len(_words(hits[0]))]
    others = [h for h in hits if _words(h) not in _words(hits[0])]
    if len(longest) == 1 and not others:
        return hits[0]
    return None


def convention(part: str, target: Target) -> str:
    t = part
    if target.separator == "_" and re.fullmatch(r"[A-Za-z][A-Za-z ]*[A-Za-z]", t):
        t = t.replace(" ", "_")
    elif target.separator == " " and re.fullmatch(r"[A-Za-z][A-Za-z_]*[A-Za-z]", t):
        t = t.replace("_", " ")
    if target.case and len(re.findall(r"[A-Za-z]+", t)) <= 4:
        if target.case == "lower":
            t = t.lower()
        elif target.case == "upper":
            t = t.upper()
        elif target.case == "title" and (t.islower() or t.isupper()):
            t = re.sub(r"[A-Za-z]+", lambda m: m.group(0).capitalize(), t)
    return t


def t0_part(part: str, target: Target) -> tuple[str, str]:
    """(rewritten part, rule) for one part."""

    by_fold = target.by_fold
    if target.fold(part) in by_fold:
        v = by_fold[target.fold(part)]
        return v, "vocabulary" if v != part else "same"
    conv = convention(part, target)
    if target.fold(conv) in by_fold:
        return by_fold[target.fold(conv)], "vocabulary"
    if status(conv, target) != "off":  # a new value already written the workload's way
        return conv, "convention" if conv != part else "same"
    hit = contained(part, target)
    if hit is not None:
        return hit, "contains"
    return conv, "convention" if conv != part else "same"


def status(part: str, target: Target) -> str:
    if part in target.vocabulary:
        return "vocabulary"
    if not target.vocabulary and not target.shapes:
        return "unconstrained"
    if target.shapes and shape(part) in target.shapes:
        return "shape"
    if not target.declared and len(target.vocabulary) + len(target.cores) < 3 and len(part.split()) <= 3:
        return "shape"  # one or two literals are examples, not a form: short values stand
    if target.cores and any(c.casefold() in part.casefold() for c in target.cores) and not target.declared:
        return "shape"
    return "off"


def combine(values: list[str], target: Target) -> str | None:
    values = list(dict.fromkeys(v for v in values if v))
    if not values:
        return None
    if target.multi:
        return SEP.join(sorted(values, key=lambda v: (v.casefold(), v)))
    inside = [v for v in values if v in target.vocabulary]
    return inside[0] if len(inside) == 1 else values[0]


def t0(value: Any, target: Target) -> tuple[Any, list[tuple[str, str, str]]]:
    """(new cell, [(raw part, new part, rule)]) for one cell."""

    if value is None or target.numeric or not isinstance(value, str):
        return value, []
    trace = []
    out = []
    for p in parts(value):
        new, rule = t0_part(p, target)
        trace.append((p, new, rule))
        out.append(new)
    return combine(out, target), trace
