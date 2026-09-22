"""Query-local witness additions. Official SQL is original_condition OR EXISTS."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from sqlglot import exp

from quwarts.core.query_filter import _outer_tables, alias_order, encode_witness_key, witness_key_sql
from quwarts.core.workload import parse_sql

DDL = """
CREATE TABLE IF NOT EXISTS query_witness_additions (
  program_id TEXT NOT NULL,
  witness_key TEXT NOT NULL,
  resolved INTEGER NOT NULL,
  truth INTEGER NOT NULL,
  group_value TEXT,
  aggregate_value TEXT,
  counted_value_present INTEGER,
  entity_id TEXT,
  query_ids TEXT,
  evidence TEXT,
  PRIMARY KEY (program_id, witness_key)
)
"""

PROGRAM_DDL = """
CREATE TABLE IF NOT EXISTS query_witness_programs (
  query_id TEXT PRIMARY KEY,
  program_id TEXT NOT NULL,
  condition_id TEXT NOT NULL
)
"""


def _q(name: str) -> str:
    return "'" + str(name).replace("'", "''") + "'"


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(DDL)
    conn.execute(PROGRAM_DDL)


def has_tables(path: str | Path) -> bool:
    conn = sqlite3.connect(str(path))
    try:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return "query_witness_additions" in names
    finally:
        conn.close()


def register_programs(conn: sqlite3.Connection, programs) -> None:
    ensure_tables(conn)
    for program in programs:
        for qid in program.query_ids:
            conn.execute(
                "INSERT OR REPLACE INTO query_witness_programs(query_id, program_id, condition_id) VALUES (?,?,?)",
                [qid, program.program_id, program.condition_id],
            )


def insert_addition(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    ensure_tables(conn)
    conn.execute(
        "INSERT OR REPLACE INTO query_witness_additions("
        "program_id, witness_key, resolved, truth, group_value, aggregate_value, "
        "counted_value_present, entity_id, query_ids, evidence) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            row["program_id"],
            row["witness_key"],
            1,
            1 if row.get("truth") else 0,
            row.get("group_value"),
            None if row.get("aggregate_value") is None else str(row.get("aggregate_value")),
            None if row.get("counted_value_present") is None else int(bool(row.get("counted_value_present"))),
            row.get("entity_id"),
            ",".join(row.get("query_ids") or []),
            row.get("evidence"),
        ],
    )


def delete_addition(conn: sqlite3.Connection, program_id: str, witness_key: str) -> None:
    conn.execute(
        "DELETE FROM query_witness_additions WHERE program_id = ? AND witness_key = ?",
        [program_id, witness_key],
    )


def program_id_from_sql(sql: str) -> str:
    from quwarts.core.query_filter import canonicalize_filter
    from quwarts.core.query_witness import compile_witness_spec
    from quwarts.core.query_witness_acq.programs import _agg_sql, _digest

    cond = canonicalize_filter(sql)
    spec = compile_witness_spec("_", sql)
    group = spec.group_sql[0] if spec.group_sql else None
    return _digest(f"{cond}||{group or ''}||{_agg_sql(sql)}")


def rewrite_witness_sql(
    sql: str,
    sqlite_path: str | Path,
    original_sql: str | None = None,
    query_id: str | None = None,
) -> str:
    if not has_tables(sqlite_path):
        return sql
    program_id = program_id_from_sql(original_sql or sql)
    if query_id:
        conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT program_id FROM query_witness_programs WHERE query_id = ?", [query_id]
            ).fetchone()
            if row:
                program_id = str(row[0])
        except sqlite3.Error:
            pass
        finally:
            conn.close()
    if not program_id:
        return sql
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        hit = conn.execute(
            "SELECT 1 FROM query_witness_additions WHERE program_id = ? AND resolved = 1 AND truth = 1 LIMIT 1",
            [program_id],
        ).fetchone()
    except sqlite3.Error:
        hit = None
    finally:
        conn.close()
    if hit is None:
        return sql
    try:
        tree = parse_sql(sql)
    except Exception:
        return sql
    if not isinstance(tree, exp.Select):
        return sql
    key_sql = witness_key_sql(tree)
    exists = (
        "EXISTS (SELECT 1 FROM query_witness_additions qa "
        f"WHERE qa.program_id = {_q(program_id)} "
        f"AND qa.witness_key = {key_sql} "
        "AND qa.resolved = 1 AND qa.truth = 1)"
    )
    where = tree.args.get("where")
    current = where.this.sql(dialect="sqlite") if where is not None else None
    if current and "query_witness_additions" not in current.lower():
        tree.set("where", exp.Where(this=parse_sql(f"({current}) OR ({exists})")))
    group_lookup = (
        f"(SELECT qa.group_value FROM query_witness_additions qa "
        f"WHERE qa.program_id = {_q(program_id)} AND qa.witness_key = {key_sql} "
        f"AND qa.resolved = 1 AND qa.truth = 1 AND qa.group_value IS NOT NULL LIMIT 1)"
    )
    agg_lookup = (
        f"(SELECT qa.aggregate_value FROM query_witness_additions qa "
        f"WHERE qa.program_id = {_q(program_id)} AND qa.witness_key = {key_sql} "
        f"AND qa.resolved = 1 AND qa.truth = 1 AND qa.aggregate_value IS NOT NULL LIMIT 1)"
    )

    def wrap_group(expr: exp.Expression) -> exp.Expression:
        if expr.find((exp.Count, exp.Sum, exp.Avg, exp.Max, exp.Min)):
            return expr
        if "query_witness_additions" in expr.sql(dialect="sqlite").lower():
            return expr
        return parse_sql(f"COALESCE({group_lookup}, {expr.sql(dialect='sqlite')})")

    changed = False
    new_proj = []
    for proj in tree.expressions:
        alias = proj.alias if isinstance(proj, exp.Alias) else None
        expr = proj.this if isinstance(proj, exp.Alias) else proj
        if expr.find((exp.Count, exp.Sum, exp.Avg, exp.Max, exp.Min)):
            inner = expr.find((exp.Sum, exp.Avg, exp.Max, exp.Min))
            if inner is not None and inner.this is not None:
                col_sql = inner.this.sql(dialect="sqlite")
                inner.set("this", parse_sql(f"COALESCE({agg_lookup}, {col_sql})"))
                changed = True
            new_proj.append(proj)
            continue
        wrapped = wrap_group(expr)
        if wrapped is not expr:
            changed = True
        new_proj.append(exp.alias_(wrapped, alias) if alias else wrapped)
    if changed:
        tree.set("expressions", new_proj)
    group = tree.args.get("group")
    if group is not None:
        exprs = list(group.expressions) if hasattr(group, "expressions") else []
        if exprs:
            group.set("expressions", [wrap_group(item) for item in exprs])
    return tree.sql(dialect="sqlite")


def original_where_sql(sql: str) -> str | None:
    try:
        tree = parse_sql(sql)
    except Exception:
        return None
    where = tree.args.get("where") if isinstance(tree, exp.Select) else None
    if where is None:
        return None
    return where.this.sql(dialect="sqlite")


def runtime_program_id(sql: str, sqlite_path: str | Path, query_id: str | None = None) -> str:
    """Program ID official_sql will bind at the WHERE EXISTS site."""

    if query_id and has_tables(sqlite_path):
        conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT program_id FROM query_witness_programs WHERE query_id = ?", [query_id]
            ).fetchone()
            if row:
                return str(row[0])
        except sqlite3.Error:
            pass
        finally:
            conn.close()
    return program_id_from_sql(sql)


def row_visible_sql(official: str) -> str:
    """Row-level probe: outer FROM/JOIN/WHERE only. Nested sidecar tables are excluded."""

    tree = parse_sql(official)
    if not isinstance(tree, exp.Select):
        return official
    kept: list[exp.Expression] = []
    for table in _outer_tables(tree):
        qual = table.alias or table.name
        kept.append(
            exp.alias_(
                exp.Column(this=exp.to_identifier("rowid"), table=exp.to_identifier(qual)),
                f"{qual}__rid",
            )
        )
    if not kept:
        kept.append(exp.Literal.number(1))
    tree.set("expressions", kept)
    tree.set("group", None)
    tree.set("having", None)
    tree.set("order", None)
    return tree.sql(dialect="sqlite")


def _rid_from_row(row: dict[str, Any]) -> int | None:
    for key, value in row.items():
        if str(key).endswith("__rid") and value not in (None, ""):
            return int(value)
    if row.get("rowid") not in (None, ""):
        return int(row["rowid"])
    return None


def fetch_rows(conn: sqlite3.Connection, sql: str) -> tuple[list[dict[str, Any]], str | None]:
    try:
        cur = conn.execute(sql)
    except sqlite3.Error as err:
        return [], f"{type(err).__name__}: {err}"
    cols = [item[0] for item in cur.description] if cur.description else []
    return [dict(zip(cols, rec)) for rec in cur.fetchall()], None


def write_witness_gate_fixture(sqlite_path: str | Path) -> Path:
    path = Path(sqlite_path)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE company (name TEXT, flag TEXT, amount INTEGER, grp TEXT)")
    conn.execute("CREATE TABLE extra (name TEXT)")
    conn.execute("INSERT INTO company VALUES ('keep', 'yes', 10, 'A')")
    conn.execute("INSERT INTO company VALUES ('excluded', 'no', 20, 'B')")
    conn.execute("INSERT INTO company VALUES ('nullamt', 'yes', NULL, 'A')")
    conn.execute("INSERT INTO extra VALUES ('keep')")
    ensure_tables(conn)
    conn.commit()
    conn.close()
    return path


def probe_witness_additivity(sqlite_path: str | Path) -> dict[str, Any]:
    from quwarts.core.pipeline import official_sql

    path = Path(sqlite_path)
    conn = sqlite3.connect(str(path))
    ensure_tables(conn)
    conn.commit()
    findings: dict[str, Any] = {"ok": True, "checks": []}

    def _bag(sql: str, query_id: str | None = None) -> list:
        wrapped = official_sql(sql, path, [], query_id=query_id)
        rows, err = fetch_rows(conn, wrapped)
        return rows if err is None else [{"_error": err, "_sql": wrapped}]

    def _count(sql: str, query_id: str | None = None) -> int:
        rows = _bag(sql, query_id)
        if not rows or "_error" in rows[0]:
            return -1
        first = rows[0]
        for key in ("n", "company_count", "c"):
            if key in first and first[key] is not None:
                return int(first[key])
        return int(next(iter(first.values())))

    def record(name: str, ok: bool, **extra: Any) -> None:
        findings["checks"].append({"name": name, "ok": ok, **extra})
        if not ok:
            findings["ok"] = False

    simple = "SELECT COUNT(*) AS n FROM company WHERE flag = 'yes'"
    grouped = "SELECT grp, COUNT(*) AS n FROM company WHERE flag = 'yes' GROUP BY grp"
    count_col = "SELECT COUNT(amount) AS n FROM company WHERE flag = 'yes'"
    distinct = "SELECT COUNT(DISTINCT name) AS n FROM company WHERE flag = 'yes'"
    aliased = "SELECT COUNT(*) AS n FROM company c WHERE c.flag = 'yes'"
    joined = (
        "SELECT COUNT(*) AS n FROM company c JOIN extra e ON c.name = e.name WHERE c.flag = 'yes'"
    )
    left_join = (
        "SELECT COUNT(*) AS n FROM company c LEFT JOIN extra e ON c.name = e.name "
        "WHERE c.flag = 'yes'"
    )
    reuse_a = "SELECT COUNT(*) AS n FROM company WHERE flag = 'yes'"
    reuse_b = "SELECT grp, COUNT(*) AS n FROM company WHERE flag = 'yes' GROUP BY grp"

    excluded = int(conn.execute("SELECT rowid FROM company WHERE name = 'excluded'").fetchone()[0])
    keep = int(conn.execute("SELECT rowid FROM company WHERE name = 'keep'").fetchone()[0])
    pid_simple = program_id_from_sql(simple)
    empty_n = _count(simple)
    record("empty_sidecar_original_count", empty_n == 2, value=empty_n)
    empty_sql = official_sql(simple, path, [])
    record(
        "empty_exists_is_semantic_noop",
        empty_n == 2 and ("query_witness_additions" not in empty_sql.lower() or empty_n == 2),
        sql_has_exists="query_witness_additions" in empty_sql.lower(),
    )

    insert_addition(
        conn,
        {
            "program_id": pid_simple,
            "witness_key": encode_witness_key([excluded]),
            "truth": True,
            "query_ids": ["simple"],
        },
    )
    conn.commit()
    plus = _count(simple)
    official_plus = official_sql(simple, path, [])
    record(
        "positive_sidecar_count_plus_one",
        plus == empty_n + 1,
        before=empty_n,
        after=plus,
        official_has_sidecar="query_witness_additions" in official_plus.lower(),
    )
    row_sql = row_visible_sql(official_plus)
    grain, grain_err = fetch_rows(conn, row_sql)
    rids = {_rid_from_row(row) for row in grain}
    record(
        "positive_survives_commit_via_official_sql",
        grain_err is None and excluded in rids and plus == empty_n + 1,
        grain_error=grain_err,
        rids=sorted(x for x in rids if x is not None),
        row_sql=row_sql,
    )

    delete_addition(conn, pid_simple, encode_witness_key([excluded]))
    conn.commit()
    restored = _count(simple)
    record("removing_sidecar_restores_count", restored == empty_n, value=restored)

    insert_addition(
        conn,
        {
            "program_id": program_id_from_sql(grouped),
            "witness_key": encode_witness_key([excluded]),
            "truth": True,
            "group_value": "B",
            "query_ids": ["grouped"],
        },
    )
    conn.commit()
    grouped_rows = _bag(grouped)
    grouped_n = sum(int(row.get("n") or 0) for row in grouped_rows if "_error" not in row)
    record("grouped_count_admits_excluded", grouped_n == 3, bag=grouped_rows)
    delete_addition(conn, program_id_from_sql(grouped), encode_witness_key([excluded]))
    conn.commit()

    insert_addition(
        conn,
        {
            "program_id": program_id_from_sql(count_col),
            "witness_key": encode_witness_key([excluded]),
            "truth": True,
            "counted_value_present": True,
            "query_ids": ["count_col"],
        },
    )
    conn.commit()
    record("count_column_plus_one", _count(count_col) == 2, value=_count(count_col))
    delete_addition(conn, program_id_from_sql(count_col), encode_witness_key([excluded]))
    conn.commit()

    before_distinct = _count(distinct)
    insert_addition(
        conn,
        {
            "program_id": program_id_from_sql(distinct),
            "witness_key": encode_witness_key([excluded]),
            "truth": True,
            "query_ids": ["distinct"],
        },
    )
    conn.commit()
    after_distinct = _count(distinct)
    record(
        "count_distinct_new_name",
        after_distinct == before_distinct + 1,
        before=before_distinct,
        after=after_distinct,
    )
    delete_addition(conn, program_id_from_sql(distinct), encode_witness_key([excluded]))
    conn.commit()

    insert_addition(
        conn,
        {
            "program_id": program_id_from_sql(aliased),
            "witness_key": encode_witness_key([excluded]),
            "truth": True,
            "query_ids": ["aliased"],
        },
    )
    conn.commit()
    record("table_alias_count_plus_one", _count(aliased) == 3, value=_count(aliased))
    delete_addition(conn, program_id_from_sql(aliased), encode_witness_key([excluded]))
    conn.commit()

    join_key = encode_witness_key([excluded, None])
    insert_addition(
        conn,
        {
            "program_id": program_id_from_sql(joined),
            "witness_key": encode_witness_key([excluded]),
            "truth": True,
            "query_ids": ["joined_wrong_key"],
        },
    )
    conn.commit()
    # INNER JOIN does not admit excluded (no extra row); join grain must not invent an edge.
    record("join_does_not_invent_edge", _count(joined) == 1, value=_count(joined))
    delete_addition(conn, program_id_from_sql(joined), encode_witness_key([excluded]))
    conn.commit()

    extra_rid = conn.execute("SELECT rowid FROM extra WHERE name = 'keep'").fetchone()
    insert_addition(
        conn,
        {
            "program_id": program_id_from_sql(joined),
            "witness_key": encode_witness_key([keep, int(extra_rid[0]) if extra_rid else 1]),
            "truth": True,
            "query_ids": ["joined"],
        },
    )
    conn.commit()
    record("composite_join_key_incumbent_noop", _count(joined) == 1, value=_count(joined), key=join_key)
    delete_addition(
        conn,
        program_id_from_sql(joined),
        encode_witness_key([keep, int(extra_rid[0]) if extra_rid else 1]),
    )
    conn.commit()

    left_key = encode_witness_key([excluded, None])
    insert_addition(
        conn,
        {
            "program_id": program_id_from_sql(left_join),
            "witness_key": left_key,
            "truth": True,
            "query_ids": ["left_join"],
        },
    )
    conn.commit()
    record(
        "null_sentinel_left_join",
        _count(left_join) == 3,
        value=_count(left_join),
        key=left_key,
    )
    delete_addition(conn, program_id_from_sql(left_join), left_key)
    conn.commit()

    pid_a = program_id_from_sql(reuse_a)
    pid_b = program_id_from_sql(reuse_b)
    record("reuse_same_condition_distinct_programs", pid_a != pid_b, pid_a=pid_a, pid_b=pid_b)
    conn.execute(
        "INSERT OR REPLACE INTO query_witness_programs(query_id, program_id, condition_id) VALUES (?,?,?)",
        ["reuse_a", pid_a, pid_a],
    )
    conn.execute(
        "INSERT OR REPLACE INTO query_witness_programs(query_id, program_id, condition_id) VALUES (?,?,?)",
        ["reuse_b", pid_b, pid_b],
    )
    insert_addition(
        conn,
        {
            "program_id": pid_a,
            "witness_key": encode_witness_key([excluded]),
            "truth": True,
            "query_ids": ["reuse_a"],
        },
    )
    conn.commit()
    def _sum_n(sql: str, query_id: str | None = None) -> int:
        return sum(int(row.get("n") or 0) for row in _bag(sql, query_id) if "_error" not in row)

    record("reuse_a_only_sees_own_program", _count(reuse_a, "reuse_a") == 3, a=_count(reuse_a, "reuse_a"), b=_sum_n(reuse_b, "reuse_b"))
    record("reuse_b_unaffected_by_a", _sum_n(reuse_b, "reuse_b") == 2, value=_sum_n(reuse_b, "reuse_b"))
    insert_addition(
        conn,
        {
            "program_id": pid_b,
            "witness_key": encode_witness_key([excluded]),
            "truth": True,
            "group_value": "B",
            "query_ids": ["reuse_b"],
        },
    )
    conn.commit()
    record("reuse_b_own_materialization", _sum_n(reuse_b, "reuse_b") == 3, value=_sum_n(reuse_b, "reuse_b"))
    conn.close()
    return findings
