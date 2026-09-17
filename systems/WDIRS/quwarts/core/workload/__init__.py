"""SQL parsing, canonicalization, templating, roles, slices, grain, forms."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

import sqlglot
from sqlglot import exp

from quwarts.core.logical import (
    SchemaConflict,
    bind_identifier,
    expression_aliases,
    infer_logical_schema,
    qualify,
    resolve_bases,
)
from quwarts.core.models import (
    AttributeRequirement,
    LogicalSchema,
    ParamSlot,
    PredicateRange,
    Role,
    SliceSpec,
    Template,
    TemplateShape,
    Workload,
)

_AGG_ADDITIVE = {"SUM", "AVG"}
_AGG_EXTREMAL = {"MAX", "MIN"}
_ANTI_HINTS = (
    exp.Not,
    exp.Exists,
    exp.Except,
)


def parse_sql(sql: str) -> exp.Expression:
    return sqlglot.parse_one(sql, read="sqlite")


def _table_name(node: exp.Table) -> str:
    return node.name.lower()


def _col_name(node: exp.Column, default_entity: str | None = None) -> str | None:
    table = node.table.lower() if node.table else default_entity
    name = node.name.lower() if node.name else None
    if not name:
        return None
    if table:
        return qualify(table, name)
    return name


def _default_entity(tree: exp.Expression) -> str | None:
    tables = [node for node in tree.find_all(exp.Table)]
    if len(tables) == 1:
        return _table_name(tables[0])
    return None


def canonicalize(tree: exp.Expression) -> exp.Expression:
    """Alias-independent form, sorted conjuncts, folded constants."""

    rewritten = tree.copy()
    aliases: dict[str, str] = {}
    for table in rewritten.find_all(exp.Table):
        if table.alias:
            aliases[table.alias.lower()] = table.name.lower()
            table.set("alias", None)
    for column in rewritten.find_all(exp.Column):
        if column.table and column.table.lower() in aliases:
            column.set("table", aliases[column.table.lower()])
    if isinstance(rewritten, exp.Select) and rewritten.args.get("where"):
        where = rewritten.args["where"]
        if isinstance(where.this, exp.And):
            parts = list(where.this.flatten())
            parts_sorted = sorted(parts, key=lambda node: node.sql())
            folded = parts_sorted[0]
            for part in parts_sorted[1:]:
                folded = exp.and_(folded, part)
            where.set("this", folded)
    return rewritten


def _is_anti_join(tree: exp.Expression) -> bool:
    sql = tree.sql(dialect="sqlite").upper()
    if "NOT EXISTS" in sql or "NOT IN" in sql or " EXCEPT " in sql:
        return True
    for join in tree.find_all(exp.Join):
        kind = (join.args.get("kind") or "").upper()
        if kind == "LEFT":
            for predicate in tree.find_all(exp.Is):
                if isinstance(predicate.expression, exp.Null):
                    return True
    for node in tree.find_all(exp.Not):
        if isinstance(node.this, (exp.Exists, exp.In)):
            return True
    return False


def _has_restricting_predicate(tree: exp.Expression, entity: str | None) -> bool:
    where = tree.find(exp.Where)
    if where is None:
        return False
    if entity is None:
        return True
    for column in where.find_all(exp.Column):
        table = (column.table or entity).lower()
        if table == entity:
            return True
    return False


def classify_shape(tree: exp.Expression) -> tuple[TemplateShape, bool]:
    """Fail closed: unrecognized constructs are slice-unsafe."""

    if _is_anti_join(tree):
        return TemplateShape.ANTI_JOIN, False

    default_entity = _default_entity(tree)
    aggregates = list(tree.find_all(exp.AggFunc))
    has_count_star = any(
        isinstance(node, exp.Count) and (node.this is None or isinstance(node.this, exp.Star))
        for node in tree.find_all(exp.Count)
    )
    predicate_attrs = _predicate_attributes(tree, default_entity)
    agg_attrs = _aggregate_attributes(tree, default_entity)
    project_attrs = _project_attributes(tree, default_entity)

    if has_count_star and not _has_restricting_predicate(tree, default_entity):
        return TemplateShape.BASE_CARDINALITY, False

    if aggregates and not _has_restricting_predicate(tree, default_entity):
        return TemplateShape.UNFILTERED_AGGREGATE, False

    if predicate_attrs and agg_attrs and not predicate_attrs.issubset(agg_attrs):
        return TemplateShape.CROSS_ATTRIBUTE_FILTER, True

    if aggregates and predicate_attrs:
        return TemplateShape.FILTERED_AGGREGATE, True

    if predicate_attrs and project_attrs and not aggregates:
        return TemplateShape.FILTERED_PROJECTION, True

    if aggregates:
        return TemplateShape.UNFILTERED_AGGREGATE, False

    return TemplateShape.UNKNOWN, False


def _predicate_attributes(tree: exp.Expression, default_entity: str | None) -> set[str]:
    attrs: set[str] = set()
    for clause in list(tree.find_all(exp.Where)) + list(tree.find_all(exp.Having)):
        for column in clause.find_all(exp.Column):
            name = _col_name(column, default_entity)
            if name:
                attrs.add(name)
    return attrs


def _aggregate_attributes(tree: exp.Expression, default_entity: str | None) -> set[str]:
    attrs: set[str] = set()
    for agg in tree.find_all(exp.AggFunc):
        for column in agg.find_all(exp.Column):
            name = _col_name(column, default_entity)
            if name:
                attrs.add(name)
    return attrs


def _project_attributes(tree: exp.Expression, default_entity: str | None) -> set[str]:
    attrs: set[str] = set()
    if not isinstance(tree, exp.Select):
        return attrs
    for projection in tree.expressions:
        if isinstance(projection, exp.AggFunc):
            continue
        for column in projection.find_all(exp.Column):
            name = _col_name(column, default_entity)
            if name:
                attrs.add(name)
    return attrs


def _roles_from_ast(tree: exp.Expression, default_entity: str | None) -> dict[str, set[Role]]:
    roles: dict[str, set[Role]] = {}

    def add(name: str | None, role: Role) -> None:
        if not name:
            return
        roles.setdefault(name, set()).add(role)

    for join in tree.find_all(exp.Join):
        on = join.args.get("on")
        if on is None:
            continue
        for column in on.find_all(exp.Column):
            add(_col_name(column, default_entity), Role.JOIN)
            add(_col_name(column, default_entity), Role.KEY)

    for group in tree.find_all(exp.Group):
        for column in group.find_all(exp.Column):
            add(_col_name(column, default_entity), Role.GROUP)

    for clause in list(tree.find_all(exp.Where)) + list(tree.find_all(exp.Having)):
        for column in clause.find_all(exp.Column):
            add(_col_name(column, default_entity), Role.PREDICATE)

    for agg in tree.find_all(exp.AggFunc):
        kind = agg.key.upper() if hasattr(agg, "key") else agg.__class__.__name__.upper()
        distinct = bool(agg.args.get("distinct"))
        for column in agg.find_all(exp.Column):
            name = _col_name(column, default_entity)
            if kind in _AGG_ADDITIVE:
                add(name, Role.AGG_ADDITIVE)
            elif kind in _AGG_EXTREMAL:
                add(name, Role.AGG_EXTREMAL)
            elif kind == "COUNT" and distinct:
                add(name, Role.AGG_DISTINCT)
            elif kind == "COUNT":
                add(name, Role.AGG_ADDITIVE)
            else:
                add(name, Role.AGG_EXTREMAL)

    for order in tree.find_all(exp.Order):
        limit = tree.args.get("limit")
        if limit is None:
            continue
        for column in order.find_all(exp.Column):
            add(_col_name(column, default_entity), Role.AGG_EXTREMAL)

    if isinstance(tree, exp.Select):
        used = {role for assigned in roles.values() for role in assigned}
        for projection in tree.expressions:
            for column in projection.find_all(exp.Column):
                name = _col_name(column, default_entity)
                if name and name not in roles:
                    add(name, Role.PROJECT)

    return roles


def _param_slots(tree: exp.Expression, default_entity: str | None) -> list[ParamSlot]:
    slots: list[ParamSlot] = []
    index = 0
    comparators = (
        exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE,
        exp.Like, exp.In, exp.Between,
    )
    for node in tree.walk():
        if not isinstance(node, comparators):
            continue
        column = node.find(exp.Column)
        if column is None:
            continue
        attribute = _col_name(column, default_entity)
        if attribute is None:
            continue
        values: list[Any] = []
        op = node.key
        if isinstance(node, exp.Between):
            op = "BETWEEN"
            for part in (node.args.get("low"), node.args.get("high")):
                if isinstance(part, exp.Literal):
                    values.append(_literal_value(part))
        elif isinstance(node, exp.In):
            op = "IN"
            for part in node.expressions:
                if isinstance(part, exp.Literal):
                    values.append(_literal_value(part))
        else:
            literal = node.find(exp.Literal)
            if literal is not None:
                values.append(_literal_value(literal))
            if isinstance(node, exp.Like):
                op = "LIKE"
            elif isinstance(node, (exp.EQ,)):
                op = "="
            elif isinstance(node, exp.GT):
                op = ">"
            elif isinstance(node, exp.GTE):
                op = ">="
            elif isinstance(node, exp.LT):
                op = "<"
            elif isinstance(node, exp.LTE):
                op = "<="
            elif isinstance(node, exp.NEQ):
                op = "!="
        if not values:
            continue
        slots.append(
            ParamSlot(
                slot_id=f"p{index}",
                attribute=attribute,
                op=op,
                dtype="string",
                observed_constants=values,
            )
        )
        index += 1
    return slots


def _literal_value(node: exp.Literal) -> Any:
    raw = node.this
    if node.is_number:
        try:
            return float(raw) if "." in str(raw) else int(raw)
        except ValueError:
            return raw
    return str(raw).strip("'\"")


def _expand_bases(names: Iterable[str], logical: LogicalSchema, derived: dict) -> set[str]:
    expanded: set[str] = set()
    for name in names:
        bare = name.split(".")[-1].lower()
        if bare in derived:
            expanded.update(derived[bare].base_attributes)
        else:
            expanded.update(resolve_bases(logical, name))
    return expanded


def _template_hash(canonical_sql: str, slot_attrs: list[str]) -> str:
    payload = json.dumps({"sql": canonical_sql, "slots": slot_attrs}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _parameterize(canonical_sql: str, slots: list[ParamSlot]) -> str:
    sql = canonical_sql
    for slot in slots:
        for constant in slot.observed_constants:
            token = f"'{constant}'" if isinstance(constant, str) else str(constant)
            sql = sql.replace(token, f":{slot.slot_id}", 1)
    return sql


def _slice_for_template(template: Template) -> dict[str, SliceSpec]:
    slices: dict[str, SliceSpec] = {}
    if not template.slice_safe:
        for attribute in template.roles_by_attribute:
            slices[attribute] = SliceSpec(kind="full")
        for attribute in template.aggregated_attributes:
            slices[attribute] = SliceSpec(kind="full")
        return slices
    for slot in template.param_slots:
        rng = PredicateRange(attribute=slot.attribute, op=slot.op, values=list(slot.observed_constants))
        current = slices.get(slot.attribute, SliceSpec(kind="ranges"))
        slices[slot.attribute] = current.union(SliceSpec(kind="ranges", ranges=[rng]))
    if template.shape == TemplateShape.CROSS_ATTRIBUTE_FILTER:
        pred_slice = SliceSpec(kind="ranges")
        for slot in template.param_slots:
            pred_slice = pred_slice.union(
                SliceSpec(
                    kind="ranges",
                    ranges=[PredicateRange(attribute=slot.attribute, op=slot.op, values=list(slot.observed_constants))],
                )
            )
        for attribute in template.aggregated_attributes:
            current = slices.get(attribute, SliceSpec(kind="ranges"))
            slices[attribute] = current.union(pred_slice)
    return slices


def _forms_for(attribute: str, logical: LogicalSchema, roles: set[Role]) -> set[str]:
    forms = {"surface", "parsed"}
    for item in logical.attributes:
        if qualify(item.entity_type, item.name) == attribute and item.unit_domain:
            forms.add(f"unit:{item.unit_domain}")
    if Role.AGG_ADDITIVE in roles or Role.AGG_EXTREMAL in roles or Role.AGG_DISTINCT in roles:
        forms.add("parsed")
    if Role.PREDICATE in roles:
        forms.add("surface")
    return forms


def _finest_grain(roles: set[Role], logical: LogicalSchema, entity: str) -> str:
    declared = logical.identity_grain.get(entity, "mention")
    if Role.KEY in roles or Role.JOIN in roles:
        return "mention"
    return declared


def case_literal_aliases(tree: exp.Expression) -> dict[str, str]:
    """WHEN 'a' THEN 'b' in a join CASE is a declared identity alias."""

    aliases: dict[str, str] = {}
    for case in tree.find_all(exp.Case):
        for iff in case.args.get("ifs") or []:
            when, then = iff.this, iff.args.get("true")
            source = None
            dest = None
            if isinstance(when, exp.Literal):
                source = str(_literal_value(when))
            elif when is not None:
                literal = when.find(exp.Literal)
                if literal is not None:
                    source = str(_literal_value(literal))
            if isinstance(then, exp.Literal):
                dest = str(_literal_value(then))
            if source and dest:
                aliases[source] = dest
    return aliases


def mentions_from_sql(sql: str) -> dict[str, Any]:
    """Alias-resolved join pairs and IN attributes for a single statement."""

    tree = parse_sql(sql)
    canonical = canonicalize(tree)
    default = _default_entity(canonical)
    pairs: list[tuple[str, str]] = []
    for join in canonical.find_all(exp.Join):
        on = join.args.get("on")
        if on is None:
            continue
        cols = [_col_name(col, default) for col in on.find_all(exp.Column)]
        cols = [col for col in cols if col]
        if len(cols) >= 2:
            pairs.append((cols[0], cols[1]))
    slots = _param_slots(canonical, default)
    return {
        "join_pairs": pairs,
        "in_attributes": [slot.attribute for slot in slots if slot.op == "IN"],
    }


def analyze_workload(
    statements: Iterable[str] | dict[str, str],
    logical: LogicalSchema | None = None,
) -> tuple[LogicalSchema, Workload]:
    if isinstance(statements, dict):
        items = list(statements.items())
    else:
        items = [(f"q{index}", sql) for index, sql in enumerate(statements)]

    raw_sqls = [sql for _, sql in items]
    if logical is None:
        logical = infer_logical_schema(raw_sqls)

    templates_by_id: dict[str, Template] = {}
    binding_failures: list[str] = []
    in_lists: dict[str, list[frozenset[str]]] = {}
    literal_aliases: dict[str, str] = {}

    for stmt_id, sql in items:
        try:
            tree = parse_sql(sql)
        except Exception as exc:  # noqa: BLE001
            binding_failures.append(f"{stmt_id}: parse failed: {exc}")
            continue
        canonical = canonicalize(tree)
        default_entity = _default_entity(canonical)
        derived = expression_aliases(canonical, default_entity)
        derived_names = {item.alias for item in derived.values()} | {
            item.alias for item in logical.expressions
        }
        errors: list[str] = []
        for table in canonical.find_all(exp.Table):
            try:
                bind_identifier(logical, table.name)
            except SchemaConflict as exc:
                errors.append(str(exc))
        for column in canonical.find_all(exp.Column):
            if column.name and column.name.lower() in derived_names:
                continue
            table = column.table or default_entity
            if table is None:
                continue
            try:
                bind_identifier(logical, table, column.name)
            except SchemaConflict as exc:
                errors.append(str(exc))
        if errors:
            binding_failures.extend(f"{stmt_id}: {err}" for err in errors)
        shape, slice_safe = classify_shape(canonical)
        roles = _roles_from_ast(canonical, default_entity)
        resolved: dict[str, set[Role]] = {}
        for name, assigned in roles.items():
            bases = resolve_bases(logical, name)
            if name.split(".")[-1].lower() in derived:
                bases = derived[name.split(".")[-1].lower()].base_attributes or bases
            for base in bases:
                resolved.setdefault(base, set()).update(assigned)
        roles = resolved
        slots = _param_slots(canonical, default_entity)
        for slot in slots:
            if slot.op != "IN":
                continue
            values = frozenset(
                value.strip()
                for value in slot.observed_constants
                if isinstance(value, str) and value.strip()
            )
            if len(values) < 2:
                continue
            in_lists.setdefault(slot.attribute, []).append(values)
            bare = slot.attribute.split(".")[-1]
            if bare != slot.attribute:
                in_lists.setdefault(bare, []).append(values)
        for join in canonical.find_all(exp.Join):
            on = join.args.get("on")
            if on is not None:
                literal_aliases.update(case_literal_aliases(on))
        canonical_sql = canonical.sql(dialect="sqlite")
        parameterized = _parameterize(canonical_sql, slots)
        template_id = _template_hash(parameterized, [slot.attribute for slot in slots])
        entities = {_table_name(node) for node in canonical.find_all(exp.Table)}
        join_pairs: list[tuple[str, str]] = []
        for join in canonical.find_all(exp.Join):
            on = join.args.get("on")
            if on is None:
                continue
            cols = [_col_name(col, default_entity) for col in on.find_all(exp.Column)]
            cols = [col for col in cols if col]
            if len(cols) >= 2:
                join_pairs.append((cols[0], cols[1]))
        if template_id in templates_by_id:
            existing = templates_by_id[template_id]
            existing.statement_ids.append(stmt_id)
            existing.freq += 1
            for slot, new_slot in zip(existing.param_slots, slots):
                for value in new_slot.observed_constants:
                    if value not in slot.observed_constants:
                        slot.observed_constants.append(value)
            for pair in join_pairs:
                if pair not in existing.join_pairs:
                    existing.join_pairs.append(pair)
            continue
        templates_by_id[template_id] = Template(
            id=template_id,
            canonical_sql=parameterized,
            param_slots=slots,
            statement_ids=[stmt_id],
            freq=1,
            roles_by_attribute=roles,
            slice_safe=slice_safe,
            shape=shape,
            raw_sql=sql,
            entity_types=entities,
            aggregated_attributes=_expand_bases(
                _aggregate_attributes(canonical, default_entity), logical, derived
            ),
            predicate_attributes=_expand_bases(
                _predicate_attributes(canonical, default_entity), logical, derived
            ),
            join_pairs=join_pairs,
            group_attributes=[
                name for name, assigned in roles.items() if Role.GROUP in assigned
            ],
            project_attributes=[
                name for name, assigned in roles.items() if Role.PROJECT in assigned
            ],
            has_count_star=any(
                isinstance(node, exp.Count)
                and (node.this is None or isinstance(node.this, exp.Star))
                for node in canonical.find_all(exp.Count)
            ),
            binding_errors=errors,
        )

    requirements: dict[str, AttributeRequirement] = {}
    for template in templates_by_id.values():
        slices = _slice_for_template(template)
        for attribute, roles in template.roles_by_attribute.items():
            if "." in attribute:
                entity, name = attribute.split(".", 1)
            else:
                entity, name = next(iter(template.entity_types), "entity"), attribute
            dtype = "unknown"
            for item in logical.attributes:
                if qualify(item.entity_type, item.name) == attribute:
                    dtype = item.dtype
                    break
            current = requirements.get(attribute)
            attr_slice = slices.get(
                attribute,
                SliceSpec(kind="full" if not template.slice_safe else "ranges"),
            )
            if current is None:
                requirements[attribute] = AttributeRequirement(
                    name=attribute,
                    entity_type=entity,
                    dtype=dtype,
                    roles=set(roles),
                    templates=[template.id],
                    freq_weight=float(template.freq),
                    finest_grain=_finest_grain(roles, logical, entity),
                    required_forms=_forms_for(attribute, logical, roles),
                    slice=attr_slice,
                )
            else:
                current.roles.update(roles)
                current.templates.append(template.id)
                current.freq_weight += float(template.freq)
                current.required_forms.update(_forms_for(attribute, logical, roles))
                current.slice = current.slice.union(attr_slice)
                if _finest_grain(roles, logical, entity) == "mention":
                    current.finest_grain = "mention"

    stored_lists = {
        name: [sorted(item) for item in values]
        for name, values in in_lists.items()
    }
    workload = Workload(
        templates=sorted(templates_by_id.values(), key=lambda row: row.id),
        requirements=requirements,
        binding_failures=binding_failures,
        in_lists=stored_lists,
        literal_aliases=literal_aliases,
    )
    from quwarts.core.domain import apply_predicate_types

    apply_predicate_types(workload, logical)
    return logical, workload
