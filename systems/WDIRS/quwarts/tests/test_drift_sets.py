from __future__ import annotations

import random
import sqlite3

from quwarts.core.adapt import drift as D
from quwarts.eval import drift_sets as DS


def toy():
    gold = sqlite3.connect(":memory:")
    gold.execute("CREATE TABLE c (verdict TEXT, judge TEXT, hearing_year REAL, fee REAL)")
    rows = [("A" if i % 3 else "B", ["Smith", "Jones", "Lee"][i % 3], 2000 + i % 10, 100.0 * (i % 7)) for i in range(60)]
    gold.executemany("INSERT INTO c VALUES (?,?,?,?)", rows)
    kinds = {"c": {"verdict": "categorical", "judge": "categorical", "hearing_year": "numeric", "fee": "numeric"}}
    return gold, kinds


TRAIN = ["SELECT verdict, COUNT(*) FROM c GROUP BY verdict",
         "SELECT AVG(hearing_year) FROM c WHERE verdict = 'A'"]


def test_mutants_are_novel_valid_and_regrounded():
    gold, kinds = toy()
    feats = set().union(*(D.representation(s) for s in TRAIN))
    out = DS.mutants(TRAIN[1], kinds, feats, DS.Values(gold), gold, random.Random(0), 10)
    assert out
    for m in out:
        assert D.representation(m["sql"]) - feats
        assert gold.execute(m["sql"]).fetchall()
    judge = [m for m in out if m["operator"] == "replace" and m["by"] == "judge"]
    assert judge and "'A'" not in judge[0]["sql"]  # the constant was re-drawn from the new column's values
    assert any(m["operator"] == "add_filter" for m in out) or len(out) == 10


def test_feature_drift_grows_with_the_share_of_drifted_queries():
    gold, kinds = toy()
    feats = set().union(*(D.representation(s) for s in TRAIN))
    pool = [m["sql"] for m in DS.mutants(TRAIN[1], kinds, feats, DS.Values(gold), gold, random.Random(1), 10)]
    shares = [DS.feature_drift(TRAIN, TRAIN * 2 + pool[:k]) for k in (0, 1, 2, 4)]
    assert shares[0] == 0 and shares == sorted(shares)
