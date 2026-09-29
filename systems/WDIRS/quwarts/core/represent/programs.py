"""The program tier (T1): string-transformation programs synthesized from examples (no model).

A small FlashFill-style DSL (Gulwani, POPL 2011). A value is split into tokens (words, and numbers with a
suffix such as ``20th``); its *pattern class* is its token signature (``Justice Flick`` and ``Justice
Bennett`` are both ``Aa Aa``; ``BUCHANAN J`` is ``A A``). A program is a conditional over classes; in a
class it keeps the original text spanning tokens ``i..j`` and applies one case transform (identity,
title, lower, upper). Because a class fixes the number of tokens, a span is unambiguous within it.

Examples come for free from T0: every value T0 mapped to a vocabulary value that occurs inside it
(``Justice Flick`` -> ``Flick``, ``MARSHALL J`` -> ``Marshall``). The version space of a class is the
set of programs consistent with all of its examples; the simplest survivor (shortest span, identity case
first) is applied to the class's residual values that no vocabulary value explains
(``Justice Bennett`` -> ``Bennett``). Its output must fit the column's target (vocabulary or the
literals' shape family); otherwise the value stays residual for the model tier.

Examples can also come from the model: label one representative per uncovered class (T2), learn the
class's program, apply it to the rest. That turns a cost linear in distinct values into one linear in
pattern classes; ``coverage`` measures how much of a column's residual that saves.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from quwarts.core.represent.grammar import shape
from quwarts.core.represent.normalize import Target, status

TOKEN = re.compile(r"\d+(?:st|nd|rd|th)?|[A-Za-z][A-Za-z'’]*")
CASES = ("id", "title", "lower", "upper")


def tokens(text: str) -> list[re.Match]:
    return list(TOKEN.finditer(text))


def pattern_class(text: str) -> str:
    return " ".join(shape(m.group(0)) for m in tokens(text)) or "∅"


@dataclass(frozen=True)
class Program:
    i: int
    j: int  # tokens i..j-1
    case: str

    def run(self, text: str) -> str | None:
        ts = tokens(text)
        if self.j > len(ts) or self.i >= self.j:
            return None
        out = text[ts[self.i].start():ts[self.j - 1].end()]
        return {"id": out, "title": re.sub(r"[A-Za-z]+", lambda m: m.group(0).capitalize(), out),
                "lower": out.lower(), "upper": out.upper()}[self.case]

    @property
    def cost(self) -> tuple[int, int]:
        return (self.j - self.i, CASES.index(self.case))


def candidates(source: str, output: str) -> set[Program]:
    ts = tokens(source)
    out = set()
    for i in range(len(ts)):
        for j in range(i + 1, len(ts) + 1):
            for case in CASES:
                p = Program(i, j, case)
                if p.run(source) == output:
                    out.add(p)
    return out


def learn(examples: Iterable[tuple[str, str]]) -> dict[str, Program]:
    """One program per pattern class: the simplest consistent with every example of the class."""

    space: dict[str, set[Program] | None] = {}
    for source, output in examples:
        c = pattern_class(source)
        cands = candidates(source, output)
        space[c] = cands if c not in space else (space[c] & cands if space[c] is not None else None)
    return {c: min(ps, key=lambda p: p.cost) for c, ps in space.items() if ps}


def apply(programs: dict[str, Program], residual: Iterable[str], target: Target) -> dict[str, str]:
    """Residual value -> program output, where a class program exists and its output fits the target."""

    out = {}
    for value in residual:
        p = programs.get(pattern_class(value))
        if p is None:
            continue
        new = p.run(value)
        if new and status(new, target) != "off":
            out[value] = new
    return out


def coverage(residual: Iterable[str], programs: dict[str, Program]) -> dict[str, float]:
    residual = list(residual)
    classes = defaultdict(int)
    for v in residual:
        classes[pattern_class(v)] += 1
    covered = sum(n for c, n in classes.items() if c in programs)
    return {"distinct": len(residual), "classes": len(classes),
            "covered_share": round(covered / len(residual), 3) if residual else 0.0,
            "redundancy": round(len(residual) / len(classes), 2) if classes else 0.0}
