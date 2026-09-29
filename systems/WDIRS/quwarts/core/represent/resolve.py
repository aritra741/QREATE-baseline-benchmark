"""Entity resolution where the workload needs one domain: join columns and raw grouping columns.

Only the correspondences the SQL declares are resolved (RULES.md rule 3 and 4: a shared canonical id for
every equijoin; keys come from the join structure, never from column names).

Joins. For ``a.x = b.y`` the side with the larger share of distinct values per row is the entity side
(one row per entity: ``team.team_name``); the other is the reference side (``player.team``). A reference
surface with no exact partner is compared with the entity surfaces:

* equal after folding case, punctuation and spacing: merged (free)
* one's words contained in the other's, one candidate: merged (free; ``Lakers`` / ``Los Angeles Lakers``)
* otherwise candidates with word overlap go to the model as a multiple-choice question with "none"
  (budgeted, batched, memoized)

A reference surface may map to at most one entity surface; entity surfaces are never rewritten (they are
the canonical spelling). Surfaces with no match stay as they are: a player's non-NBA club must not join.

Grouping. Surfaces of a raw GROUP BY column that are equal after folding form one group, spelled as its
most frequent member.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from typing import Any, Callable

from quwarts.core.represent.normalize import SEP, parts

STOP = {"the", "of", "and", "a", "an", "fc", "bc", "club", "inc", "ltd", "co"}


def fold(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(text).casefold())).strip()


def words(text: str) -> set[str]:
    return {w for w in fold(text).split() if w not in STOP}


def surfaces(conn: sqlite3.Connection, table: str, column: str) -> Counter:
    out = Counter()
    for (v,) in conn.execute(f'SELECT "{column}" FROM "{table}"'):
        if isinstance(v, str):
            for p in parts(v):
                out[p] += 1
    return out


def entity_side(conn, a: tuple[str, str], b: tuple[str, str]) -> tuple[tuple[str, str], tuple[str, str]]:
    """The side that names one entity per row: fewer values per cell, then more distinct cells per row
    (``disease.disease_name`` against a drug's list of diseases; ``team.team_name`` against players' teams)."""

    def profile(side):
        cells = [v for (v,) in conn.execute(f'SELECT "{side[1]}" FROM "{side[0]}" WHERE "{side[1]}" IS NOT NULL')]
        if not cells:
            return (float("inf"), 0.0, 0)
        per_cell = sum(len(parts(v)) if isinstance(v, str) else 1 for v in cells) / len(cells)
        return (round(per_cell, 2), -len(set(cells)) / len(cells), -len(set(cells)))
    return (a, b) if profile(a) <= profile(b) else (b, a)


def match_join(conn, entity: tuple[str, str], reference: tuple[str, str], caller: Callable | None, journal,
               use_model: bool) -> tuple[dict[str, str], dict[str, Any]]:
    from quwarts.core.represent.llm import verify_matches

    ent = surfaces(conn, *entity)
    ref = surfaces(conn, *reference)
    by_fold = defaultdict(list)
    for e in ent:
        by_fold[fold(e)].append(e)
    mapping: dict[str, str] = {}
    ask: list[tuple[str, list[str]]] = []
    stats = Counter()
    for r in ref:
        if r in ent:
            stats["exact"] += 1
            continue
        same = by_fold.get(fold(r), [])
        if len(same) == 1:
            mapping[r] = same[0]
            stats["folded"] += 1
            continue
        wr = words(r)
        if not wr:
            continue
        contain = [e for e in ent if (words(e) and (wr <= words(e) or words(e) <= wr))]
        if len(contain) == 1:
            mapping[r] = contain[0]
            stats["contained"] += 1
            continue
        overlap = sorted((e for e in ent if wr & words(e)), key=lambda e: -len(wr & words(e)) / len(wr | words(e)))[:5]
        if overlap:
            ask.append((r, overlap))
        else:
            stats["no_candidate"] += 1
    model_stats = {}
    if ask and use_model:
        got, model_stats = verify_matches(ask, f"{reference[0]}.{reference[1]} (joined with {entity[0]}.{entity[1]})", caller, journal)
        mapping.update(got)
        stats["model_matched"] += len(got)
    stats["asked"] += len(ask) if use_model else 0
    stats["unresolved"] += (len(ask) - stats["model_matched"]) if use_model else len(ask)
    return mapping, {**dict(stats), "model": model_stats}


def group_merges(conn, table: str, column: str) -> dict[str, str]:
    counts = surfaces(conn, table, column)
    groups = defaultdict(list)
    for s in counts:
        groups[fold(s)].append(s)
    out = {}
    for members in groups.values():
        if len(members) > 1:
            best = max(sorted(members), key=lambda m: counts[m])
            for m in members:
                if m != best:
                    out[m] = best
    return out


def rewrite(conn, table: str, column: str, mapping: dict[str, str]) -> int:
    """Apply a part-level mapping to every cell of a column; returns the number of changed cells."""

    if not mapping:
        return 0
    changed = 0
    for rowid, v in conn.execute(f'SELECT rowid, "{column}" FROM "{table}" WHERE typeof("{column}") = \'text\'').fetchall():
        ps = parts(v)
        new_parts = list(dict.fromkeys(mapping.get(p, p) for p in ps))
        new = SEP.join(new_parts) if len(ps) > 1 else (new_parts[0] if new_parts else None)
        if new != v:
            conn.execute(f'UPDATE "{table}" SET "{column}" = ? WHERE rowid = ?', (new, rowid))
            changed += 1
    return changed
