"""Check a file of realistic questions before it is used (gate 2 and 3 of the realistic workload).

Per query: it parses and runs on the correct data; the answer is non-empty; whether it is a single number; the
realism rules (exp_realism: R1-R6); the scorer gives the correct answer against itself 1.0 at 0% and 20% tolerance
(group keys that are lists or empty, and NULL result cells, score below 1 even when right); which columns it uses that
the initial build does not read. With --role build, using any column outside the initial build is an error.

File format: blocks "-- Qn: question" followed by one SQL statement ending in ";".

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        ~/venvs/quwarts/bin/python -m quwarts.eval.validate_queries <corpus> <file.sql> [--role build|test] [--out report.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import tempfile
from pathlib import Path


def load_file(path: Path, prefix: str) -> list[tuple[str, str, str]]:
    out = []
    for block in re.split(r";\s*\n", path.read_text()):
        m = re.search(r"--\s*(Q[A-Z]*\d+):\s*(.*)", block)
        sql = "\n".join(x for x in block.splitlines() if not x.strip().startswith("--")).strip()
        if m and sql:
            out.append((f"{prefix}#{m.group(1)}", m.group(2).strip(), sql))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("file")
    ap.add_argument("--role", choices=["build", "test"], default="test")
    ap.add_argument("--out", help="write the JSON report here (stdout also carries library log lines)")
    a = ap.parse_args(argv)

    from quwarts.core.adapt import controller as C
    from quwarts.eval import drift_live as D
    from quwarts.eval.exp_context import fields_of
    from quwarts.eval.exp_realism import audit
    from quwarts.eval.exp_tau import score_multi
    from spp.aggregation_metrics import schema_from_sql
    from spp.config_grid import _build_in_memory_db

    c = a.corpus
    ctx = D.R.context(c)
    fields = fields_of(c)
    qs = load_file(Path(a.file), f"check:{c}:{Path(a.file).stem}")
    for qid, _q, sql in qs:
        ctx.catalog[qid] = sql
    gold, _ = D.R.Scorer(c).gold()
    g = _build_in_memory_db(gold)
    tmp = Path(tempfile.mkdtemp(dir="/scratch/general/vast/u1592362"))
    gf = tmp / "gold.db"
    dst = sqlite3.connect(gf)
    g.backup(dst)
    dst.close()
    D.R.complete(c, gf)
    w0 = {f"{r.table}.{x}" for r in ctx.lean_reads for x in r.attributes}
    try:
        scores = score_multi(c, [(qid, gf) for qid, _, _ in qs])
    except Exception as exc:  # noqa: BLE001
        scores = {qid: {"error": f"scorer failed: {exc}"} for qid, _, _ in qs}
    report, problems = [], 0
    for qid, q, sql in qs:
        r = {"id": qid.split("#")[1], "question": q}
        try:
            rows = g.execute(sql).fetchall()
        except Exception as exc:  # noqa: BLE001
            r.update({"ok": False, "problems": [f"does not run on the correct data: {exc}"]})
            report.append(r)
            problems += 1
            continue
        issues = []
        if not rows:
            issues.append("empty answer on the correct data")
        if not schema_from_sql(sql).get("is_aggregation"):
            issues.append("not an aggregation query (the scorer only scores aggregations)")
        flags = audit(sql, fields, {}, None)["unrealistic"]
        issues += [f"realism rule {f}" for f in flags]
        s = scores.get(qid, {})
        if s.get("error"):
            issues.append(f"scorer error: {s['error']}")
        elif min(s.get(0.0, 0), s.get(0.2, 0)) < 0.999:
            issues.append(f"the correct answer scores {s.get(0.0)} against itself (must be 1.0): check for list-valued or empty group keys and NULL result cells")
        try:
            used = {f"{rd.table}.{x}" for rd in C.design(ctx.spec, {qid: sql})[1] for x in rd.attributes}
        except Exception as exc:  # noqa: BLE001
            used = set()
            issues.append(f"the system cannot plan this query: {exc}")
        outside = sorted(used - w0)
        if a.role == "build" and outside:
            issues.append(f"build question uses columns outside the initial build: {outside}")
        single = len(rows) == 1 and len(rows[0]) == 1
        r.update({"ok": not issues, "problems": issues, "result_rows": len(rows), "single_number": single,
                  "columns_outside_initial_build": outside, "sample_answer": [list(x) for x in rows[:3]]})
        problems += bool(issues)
        report.append(r)
    summary = {"corpus": c, "file": a.file, "role": a.role, "queries": len(qs), "with_problems": problems,
               "single_numbers": sum(r.get("single_number", False) for r in report),
               "needing_columns_outside_initial_build": sum(bool(r.get("columns_outside_initial_build")) for r in report)}
    text = json.dumps({"summary": summary, "queries": report}, indent=1, default=str)
    if a.out:
        Path(a.out).write_text(text)
        print("REPORT", json.dumps(summary))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
