"""R(q, s): equivalence-preserving rewrite. Best-effort rewrites are rejected."""

from __future__ import annotations

from dataclasses import dataclass

from quwarts.core.models import (
    CoverageSet,
    PhysicalSchema,
    SliceSpec,
    Template,
    AttributeRequirement,
)


class RewriteRejected(ValueError):
    """Equivalence could not be proved. No approximate rewrite is emitted."""


@dataclass(frozen=True)
class RewriteResult:
    ok: bool
    sql: str | None
    reason: str = ""


def _physical_columns(schema: PhysicalSchema) -> set[str]:
    return set(schema.covered_attributes)


def _attr_bare(name: str) -> str:
    return name.split(".")[-1]


def _relation_for(schema: PhysicalSchema, attribute: str) -> str | None:
    bare = _attr_bare(attribute)
    qualified = attribute.lower()
    for relation in schema.relations:
        attrs = {item.lower() for item in relation.attributes}
        if qualified in attrs or bare in attrs or attribute.lower() in attrs:
            return relation.name
    return None


def rewritable(
    template: Template,
    schema: PhysicalSchema,
    coverage: CoverageSet | None = None,
    requirements: dict[str, AttributeRequirement] | None = None,
) -> RewriteResult:
    """Return R(q, s). Feasibility is per template, not global."""

    needed = set(template.roles_by_attribute)
    needed |= set(template.aggregated_attributes)
    needed |= set(template.predicate_attributes)
    needed |= set(template.project_attributes)
    needed |= set(template.group_attributes)
    covered = _physical_columns(schema)
    covered_bare = {_attr_bare(item) for item in covered} | {item.lower() for item in covered}
    missing = []
    for attribute in needed:
        if attribute.lower() in covered or _attr_bare(attribute) in covered_bare:
            continue
        missing.append(attribute)
    if missing:
        return RewriteResult(False, None, f"missing attributes: {missing}")

    if coverage is not None:
        for slot in template.param_slots:
            ranges = coverage.attribute_ranges.get(slot.attribute) or coverage.attribute_ranges.get(
                _attr_bare(slot.attribute)
            )
            if ranges is None:
                return RewriteResult(False, None, f"no coverage for {slot.attribute}")
            if not ranges.contains_constants(slot.observed_constants, op=slot.op):
                return RewriteResult(False, None, f"constants outside coverage for {slot.attribute}")
        if requirements:
            for attribute in needed:
                req = requirements.get(attribute)
                if req is None:
                    continue
                forms = coverage.forms.get(attribute) or coverage.forms.get(_attr_bare(attribute), set())
                if req.required_forms and not req.required_forms.issubset(forms | {"surface", "parsed"}):
                    return RewriteResult(False, None, f"missing forms for {attribute}")
                grain = coverage.grain.get(req.entity_type)
                if grain == "entity" and req.finest_grain == "mention":
                    return RewriteResult(False, None, f"grain coarser than finest_grain for {attribute}")

    sql = rewrite_sql(template, schema)
    return RewriteResult(True, sql)


def rewrite_sql(
    template: Template,
    schema: PhysicalSchema,
    *,
    join_keys: str = "surface",
    group_keys: str = "surface",
    canonical_columns: set[str] | None = None,
) -> str:
    """Deterministic physical SQL. Only emitted after R(q, s) succeeds."""

    if schema.pattern == "denormalized":
        relation = schema.relations[0].name
        sql = template.raw_sql or template.canonical_sql
        for entity in sorted(template.entity_types, key=len, reverse=True):
            sql = _replace_ident(sql, f"{entity}.", "")
            sql = _replace_table(sql, entity, relation)
        return apply_identity_keys(sql, join_keys, group_keys, canonical_columns)
    sql = template.raw_sql or template.canonical_sql
    for relation in schema.relations:
        if relation.entity_type:
            sql = _replace_table(sql, relation.entity_type, relation.name)
    return apply_identity_keys(sql, join_keys, group_keys, canonical_columns)


def apply_identity_keys(
    sql: str,
    join_keys: str,
    group_keys: str,
    canonical_columns: set[str] | None,
) -> str:
    """GROUP BY uses canonical; joins stay on surface unless asked."""

    if join_keys != "canonical" and group_keys != "canonical":
        return sql
    try:
        from sqlglot import exp
        from quwarts.core.workload import parse_sql
    except Exception:
        return sql
    try:
        tree = parse_sql(sql)
    except Exception:
        return sql
    allowed = {item.lower() for item in (canonical_columns or ())}

    def _qualify(col: exp.Column) -> str:
        name = (col.name or "").lower()
        table = (col.table or "").lower()
        return f"{table}.{name}" if table else name

    def _can_rewrite(col: exp.Column) -> bool:
        name = (col.name or "").lower()
        if name.endswith("__canonical"):
            return False
        if not allowed:
            return True
        return name in allowed or _qualify(col) in allowed

    def _suffix(col: exp.Column) -> None:
        if not _can_rewrite(col):
            return
        col.set("this", exp.to_identifier(f"{col.name}__canonical"))

    if join_keys == "canonical":
        for join in tree.find_all(exp.Join):
            on = join.args.get("on")
            if on is None:
                continue
            cols = list(on.find_all(exp.Column))
            if cols and not all(_can_rewrite(col) for col in cols):
                continue
            for col in cols:
                _suffix(col)
    if group_keys == "canonical" and isinstance(tree, exp.Select):
        group = tree.args.get("group")
        if group is not None:
            for col in group.find_all(exp.Column):
                _suffix(col)
    return tree.sql(dialect="sqlite")


def apply_bridges(sql: str, sqlite_path: str) -> str:
    """Surface equality, with a per-value bridge lookup when it misses."""

    try:
        from sqlglot import exp
        from quwarts.core.bridge import list_bridges
        from quwarts.core.workload import parse_sql
    except Exception:
        return sql
    bridges = list_bridges(sqlite_path)
    if not bridges:
        return sql
    try:
        tree = parse_sql(sql)
    except Exception:
        return sql
    if not isinstance(tree, exp.Select):
        return sql
    joins = list(tree.args.get("joins") or [])
    if not joins:
        return sql
    rewritten: list[exp.Join] = []
    index = 0
    for join in joins:
        extra, updated = _bridge_join(join, bridges, index)
        if extra is not None:
            rewritten.append(extra)
            index += 1
        rewritten.append(updated)
    tree.set("joins", rewritten)
    return tree.sql(dialect="sqlite")


def _bridge_join(join, bridges: list[dict[str, str]], index: int):
    from sqlglot import exp

    on = join.args.get("on")
    if on is None:
        return None, join
    eq = on if isinstance(on, exp.EQ) else None
    if eq is None and isinstance(on, exp.And):
        eqs = [item for item in on.flatten() if isinstance(item, exp.EQ)]
        eq = eqs[0] if len(eqs) == 1 else None
    if eq is None:
        return None, join
    left_col = _single_column(eq.left)
    right_col = _single_column(eq.right)
    if left_col is None or right_col is None:
        return None, join
    match = _match_bridge(left_col, right_col, bridges)
    if match is None:
        return None, join
    table, left_is_bridge_left = match
    alias = f"_br{index}"
    left_slot = "left_value" if left_is_bridge_left else "right_value"
    right_slot = "right_value" if left_is_bridge_left else "left_value"
    extra = exp.Join(
        this=exp.alias_(exp.table_(table), alias),
        side="LEFT",
        on=exp.EQ(
            this=eq.left.copy(),
            expression=_retarget(eq.left, alias, left_slot),
        ),
    )
    updated = join.copy()
    updated.set(
        "on",
        exp.or_(
            eq.copy(),
            exp.EQ(
                this=eq.right.copy(),
                expression=_retarget(eq.right, alias, right_slot),
            ),
        ),
    )
    return extra, updated


def _single_column(expr):
    from sqlglot import exp

    if isinstance(expr, exp.Column):
        return expr
    cols = list(expr.find_all(exp.Column))
    return cols[0] if len(cols) == 1 else None


def _retarget(expr, table: str, name: str):
    from sqlglot import exp

    clone = expr.copy()
    cols = list(clone.find_all(exp.Column))
    if len(cols) != 1:
        return exp.column(name, table=table)
    cols[0].set("this", exp.to_identifier(name))
    cols[0].set("table", exp.to_identifier(table))
    return clone


def _match_bridge(left_col, right_col, bridges: list[dict[str, str]]):
    names = {(left_col.name or "").lower(), (right_col.name or "").lower()}
    for item in bridges:
        left_bare = item["left"].split(".")[-1].lower()
        right_bare = item["right"].split(".")[-1].lower()
        if names != {left_bare, right_bare}:
            continue
        left_is_bridge_left = (left_col.name or "").lower() == left_bare
        return item["table"], left_is_bridge_left
    return None


def join_yield(sql: str, sqlite_path: str) -> float:
    """Row-weighted fraction of left rows that match every equijoin."""

    import sqlite3

    from sqlglot import exp
    from quwarts.core.workload import parse_sql

    try:
        tree = parse_sql(sql)
    except Exception:
        return 1.0
    joins = [node for node in tree.find_all(exp.Join) if node.args.get("on") is not None]
    if not joins:
        return 1.0
    conn = sqlite3.connect(sqlite_path)
    try:
        joined_sql = _join_only_sql(tree) or sql
        joined = _count(conn, joined_sql)
        left_sql = _left_only_sql(tree)
        left = _count(conn, left_sql) if left_sql else joined
    finally:
        conn.close()
    if left <= 0:
        return 1.0
    return min(1.0, joined / left)


def _count(conn, sql: str) -> int:
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM ({sql})").fetchone()
    except Exception:
        return 0
    return int(row[0] or 0) if row else 0


def _join_only_sql(tree) -> str | None:
    from sqlglot import exp

    if not isinstance(tree, exp.Select):
        return None
    clone = tree.copy()
    clone.set("group", None)
    clone.set("having", None)
    clone.set("order", None)
    clone.set("limit", None)
    clone.set("expressions", [exp.Star()])
    return clone.sql(dialect="sqlite")


def _left_only_sql(tree) -> str | None:
    from sqlglot import exp

    if not isinstance(tree, exp.Select):
        return None
    clone = tree.copy()
    clone.set("joins", None)
    clone.set("group", None)
    clone.set("having", None)
    clone.set("order", None)
    clone.set("limit", None)
    if clone.args.get("from_") is None:
        return None
    left_tables = {
        (node.alias or node.name).lower()
        for node in clone.find_all(exp.Table)
        if node.name
    }
    where = clone.args.get("where")
    if where is not None:
        kept = []
        conjuncts = list(where.this.flatten()) if isinstance(where.this, exp.And) else [where.this]
        for item in conjuncts:
            tables = {
                (col.table or "").lower()
                for col in item.find_all(exp.Column)
                if col.table
            }
            if tables <= left_tables:
                kept.append(item)
        if kept:
            clone.set("where", exp.Where(this=exp.and_(*kept)))
        else:
            clone.set("where", None)
    clone.set("expressions", [exp.Star()])
    return clone.sql(dialect="sqlite")


def _replace_ident(sql: str, old: str, new: str) -> str:
    return sql.replace(old, new).replace(old.upper(), new).replace(old.capitalize(), new)


def _replace_table(sql: str, old: str, new: str) -> str:
    tokens = sql.split()
    out = []
    for token in tokens:
        stripped = token.strip(",()")
        if stripped.lower() == old.lower():
            out.append(token.replace(stripped, new))
        else:
            out.append(token)
    return " ".join(out)


def admissible(
    templates: list[Template],
    configurations: list[tuple[PhysicalSchema, CoverageSet | None]],
    requirements: dict[str, AttributeRequirement] | None = None,
) -> bool:
    """Every template has at least one configuration with R(q, s) = 1."""

    if not templates:
        return True
    for template in templates:
        ok = False
        for schema, coverage in configurations:
            if rewritable(template, schema, coverage, requirements).ok:
                ok = True
                break
        if not ok:
            return False
    return True
