"""Compare original vs fallback-rewritten SQL on the stored A' artifact. No gold."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.pipeline import _join_aware_sql
from quwarts.core.signature import audit_workload, enumerate_predicates, rewrite_sql
from quwarts.core.signature_populate import ensure_signature_columns
from quwarts.core.signature_realize import live_predicates
from quwarts.core.workload import parse_sql
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.synthesize_case80 import queries_for

APRIME = next((ROOT / "results" / "quwarts_med_aprime" / "artifacts" / "databases").glob("*.db"))
OUT = ROOT / "results" / "quwarts_med_signatures" / "fallback_equivalence.json"


def _sha_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _bag(conn: sqlite3.Connection, sql: str) -> tuple[str, str | None, list]:
    try:
        rows = conn.execute(sql).fetchall()
    except sqlite3.Error as exc:
        return "error", str(exc), []
    payload = repr(rows)
    return _sha_text(payload), None, rows


def _pragma(conn: sqlite3.Connection) -> dict:
    tables = {}
    for (name,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%' ORDER BY 1"
    ):
        info = list(conn.execute(f'PRAGMA table_info("{name}")'))
        tables[name] = {
            "cols": [(row[1], row[2]) for row in info],
            "n": conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0],
        }
    return tables


def main() -> int:
    queries = queries_for("Med")
    train, test = split_80_20(queries, 42)
    report = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(report.occurrences, report.signature_eligible))
    dest = APRIME.parent / "_fallback_eq.db"
    shutil.copy2(APRIME, dest)
    orig_conn = sqlite3.connect(str(APRIME))
    fb_conn = sqlite3.connect(str(dest))
    ensure_signature_columns(fb_conn, predicates)
    fb_conn.commit()
    diffs = []
    parse_drift = []
    counter_diffs = []
    parse_bag_diffs = []
    join_bag_diffs = []
    test_ids = {item["query_id"] for item in test}
    for row in queries:
        qid = row["query_id"]
        original = row["sql"]
        parsed = parse_sql(original).sql(dialect="sqlite")
        rewritten = rewrite_sql(original, predicates)
        join_orig = _join_aware_sql(original, str(APRIME))
        join_fb = _join_aware_sql(rewritten, str(dest))
        o_hash, o_err, o_rows = _bag(orig_conn, original)
        r_hash, r_err, r_rows = _bag(fb_conn, rewritten)
        p_hash, p_err, p_rows = _bag(orig_conn, parsed)
        j_hash, j_err, j_rows = _bag(orig_conn, join_orig)
        jf_hash, jf_err, jf_rows = _bag(fb_conn, join_fb)
        if parsed != original:
            parse_drift.append(qid)
        if Counter(o_rows) != Counter(r_rows) or o_err or r_err:
            counter_diffs.append(qid)
        if Counter(o_rows) != Counter(p_rows) or p_err:
            parse_bag_diffs.append(qid)
        if Counter(o_rows) != Counter(j_rows) or j_err:
            join_bag_diffs.append(qid)
        if o_hash != r_hash or o_err or r_err:
            diffs.append(
                {
                    "query_id": qid,
                    "split": "test" if qid in test_ids else "train",
                    "orig_n": len(o_rows),
                    "rewrite_n": len(r_rows),
                    "parse_n": len(p_rows),
                    "join_orig_n": len(j_rows),
                    "join_fb_n": len(jf_rows),
                    "orig_hash": o_hash,
                    "rewrite_hash": r_hash,
                    "parse_hash": p_hash,
                    "join_orig_hash": j_hash,
                    "join_fb_hash": jf_hash,
                    "orig_err": o_err,
                    "rewrite_err": r_err,
                    "sql_changed": rewritten != original,
                    "parse_changed": parsed != original,
                    "join_changed": join_orig != original,
                    "original_sql": original,
                    "parsed_sql": parsed,
                    "rewritten_sql": rewritten,
                    "join_orig_sql": join_orig,
                    "orig_sample": [list(item) for item in o_rows[:5]],
                    "rewrite_sample": [list(item) for item in r_rows[:5]],
                }
            )
    orig_conn.close()
    fb_conn.close()
    dest.unlink(missing_ok=True)
    payload = {
        "aprime": str(APRIME),
        "aprime_sha": _sha_bytes(APRIME),
        "n_queries": len(queries),
        "n_train": len(train),
        "n_test": len(test),
        "n_predicates": len(predicates),
        "split_ids": {
            "train": [row["query_id"] for row in train],
            "test": [row["query_id"] for row in test],
        },
        "n_sql_parse_drift": len(parse_drift),
        "parse_drift_ids": parse_drift,
        "n_ordered_bag_diffs": len(diffs),
        "n_counter_bag_diffs": len(counter_diffs),
        "n_parse_bag_diffs": len(parse_bag_diffs),
        "n_join_bag_diffs": len(join_bag_diffs),
        "counter_diff_ids": counter_diffs,
        "parse_bag_diff_ids": parse_bag_diffs,
        "join_bag_diff_ids": join_bag_diffs,
        "n_bag_diffs": len(diffs),
        "diff_ids": [item["query_id"] for item in diffs],
        "diffs": diffs,
        "pragma": _pragma(sqlite3.connect(str(APRIME))),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, default=str))
    print(
        json.dumps(
            {
                "aprime_sha": payload["aprime_sha"],
                "n_queries": payload["n_queries"],
                "n_predicates": payload["n_predicates"],
                "n_sql_parse_drift": payload["n_sql_parse_drift"],
                "n_ordered_bag_diffs": payload["n_ordered_bag_diffs"],
                "n_counter_bag_diffs": payload["n_counter_bag_diffs"],
                "n_parse_bag_diffs": payload["n_parse_bag_diffs"],
                "n_join_bag_diffs": payload["n_join_bag_diffs"],
                "counter_diff_ids": payload["counter_diff_ids"],
                "join_bag_diff_ids": payload["join_bag_diff_ids"],
                "diff_ids": payload["diff_ids"],
            },
            indent=2,
        )
    )
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
