"""Workload drift between a database's build workload and the recent queries (CliffGuard's distance).

A query is represented by the set of (column, clause) pairs it uses: CliffGuard's ``delta_separate``
(Mozafari, Goh & Yoon, SIGMOD 2015), which keeps a column's occurrences in different clauses apart.
Clauses are select, where and group by; the clause of an occurrence comes from
``templates.role_signature`` (aggregates and CASE count as select, comparisons in WHERE / HAVING as
where). A workload is the normalized frequency vector V over the distinct query representations, and

    delta(W1, W2) = |V1 - V2| S |V1 - V2|^T,   S_ij = |q_i xor q_j| / (2 n),

with n the number of (column, clause) features in play: the magnitude of the drift.

Whether the recent workload has moved into territory the build workload did not cover is tested on the
same representation. A query is novel if it uses a (column, clause) feature that no build query uses. The
build workload's own novelty rate is estimated leave-one-out: the share of build queries with a feature
no other build query has (the Good-Turing estimate of the unseen mass, Good 1953; as in distinct-value
estimation, Haas et al. VLDB 1995), add-one smoothed. Under "the window comes from the build workload's
process" the number of novel window queries is Binomial(window, rate); the p-value is its upper tail. A
workload whose own queries are often one of a kind therefore does not make every novel query look like a
shift, and one whose queries recur does. (A permutation or resampling test on delta is not used: stream
queries that repeat build queries make the window look closer than exchangeable splits, and a
resampling null gives novel queries zero mass, so it flags any single novel query.) Query templates follow
QueryBot 5000 (Ma et al., SIGMOD 2018): the statement with its constants replaced by placeholders.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Iterable

from quwarts.core.router.templates import literal_template, role_signature


def clause(role: str) -> str:
    if role.startswith("filter:"):
        return "where"
    if role == "group":
        return "group"
    return "select"  # select, case, agg:*


def representation(sql: str) -> frozenset[str]:
    return frozenset(f"{col}@{clause(role)}" for col, role in role_signature(sql) if col != "*")


def template(sql: str) -> str:
    return literal_template(sql)


def vector(reps: Iterable[frozenset[str]]) -> dict[frozenset[str], float]:
    counts = Counter(reps)
    total = sum(counts.values())
    return {k: v / total for k, v in counts.items()} if total else {}


def distance(v1: dict, v2: dict, n: int) -> float:
    keys = list(set(v1) | set(v2))
    d = [abs(v1.get(k, 0.0) - v2.get(k, 0.0)) for k in keys]
    out = 0.0
    for i, a in enumerate(keys):
        if not d[i]:
            continue
        for j, b in enumerate(keys):
            if d[j]:
                out += d[i] * d[j] * len(a ^ b) / (2 * n)
    return out


def binomial_tail(k: int, n: int, p: float) -> float:
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1))


def drift_test(reference: list[str], window: list[str]) -> dict:
    """CliffGuard distance of ``window`` from ``reference``, and the novelty test's p-value."""

    ref = [representation(s) for s in reference]
    win = [representation(s) for s in window]
    if not ref or not win:
        return {"delta": 0.0, "p": 1.0, "n_window": len(win)}
    n = max(1, len(set().union(*ref, *win)))
    counts = Counter(f for fs in ref for f in fs)
    singletons = sum(any(counts[f] == 1 for f in fs) for fs in ref)
    rate = (singletons + 1) / (len(ref) + 2)
    novel = sum(bool(fs - set(counts)) for fs in win)
    return {"delta": round(distance(vector(ref), vector(win), n), 5), "novel": novel, "n_window": len(win),
            "build_novelty_rate": round(rate, 4), "p": round(binomial_tail(novel, len(win), rate), 5), "features": n}
