"""Logical schema inference and statement binding."""

from __future__ import annotations

import hashlib
import re
from typing import Iterable

import sqlglot
from sqlglot import exp

from quwarts.core.models import (
    DerivedExpression,
    LogicalAttribute,
    LogicalRelationship,
    LogicalSchema,
)

_COARSENING_TOKENS = frozenset({"decade", "band", "cohort", "status", "group"})

_IDENT = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")
_FROM = re.compile(r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_JOIN = re.compile(r"\bJOIN\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_JOIN_ON = re.compile(
    r"\bJOIN\s+([A-Za-z_][A-Za-z0-9_]*)\s+ON\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
    r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)

def _dtype_for(name: str) -> str:
    """Types come from SQL or evidence, never from the attribute name."""

    _ = name
    return "unknown"


def _unit_domain(name: str) -> str | None:
    _ = name
    return None


def is_coarsening(name: str) -> bool:
    tokens = name.lower().replace("-", "_").split("_")
    return any(token in _COARSENING_TOKENS for token in tokens)


def identity_name(entity: str, attribute_names: list[str]) -> str | None:
    """Do not infer keys from ``id`` / ``*_name`` / ``*_id``.

    Physical keys come from declared relationships or remain unset.
    """

    _ = entity
    _ = attribute_names
    return None


def expression_aliases(tree: exp.Expression, default_entity: str | None = None) -> dict[str, DerivedExpression]:
    """SELECT aliases that wrap expressions, not base columns or aggregates."""

    found: dict[str, DerivedExpression] = {}
    if not isinstance(tree, exp.Select):
        return found
    tables = [node.name.lower() for node in tree.find_all(exp.Table) if node.name]
    default = default_entity or (tables[0] if len(tables) == 1 else None)
    table_aliases = {
        (node.alias or node.name).lower(): node.name.lower()
        for node in tree.find_all(exp.Table)
        if node.name
    }
    for projection in tree.expressions:
        inner = projection.this if isinstance(projection, exp.Alias) else projection
        alias = (projection.alias or "").lower() if isinstance(projection, exp.Alias) else ""
        if not alias or isinstance(inner, (exp.Column, exp.AggFunc)):
            continue
        bases: list[str] = []
        for column in projection.find_all(exp.Column):
            if not column.name:
                continue
            raw_table = column.table.lower() if column.table else default
            entity = table_aliases.get(raw_table, raw_table) if raw_table else default
            if entity:
                bases.append(qualify(entity, column.name))
        entity = default or (bases[0].split(".", 1)[0] if bases else "entity")
        found[alias] = DerivedExpression(
            alias=alias,
            entity_type=entity,
            base_attributes=sorted(set(bases)),
            sql=inner.sql(dialect="sqlite") if hasattr(inner, "sql") else alias,
        )
    return found


def infer_logical_schema(statements: Iterable[str], schema_id: str = "L") -> LogicalSchema:
    """Induce ``L`` from identifiers referenced by raw SQL statements."""

    entities: set[str] = set()
    attributes: dict[tuple[str, str], LogicalAttribute] = {}
    relationships: list[LogicalRelationship] = []
    expressions: dict[str, DerivedExpression] = {}

    def _add_attr(entity: str, attr: str) -> None:
        entity, attr = entity.lower(), attr.lower()
        if not entity or not attr:
            return
        if attr in expressions:
            return
        entities.add(entity)
        key = (entity, attr)
        if key not in attributes:
            attributes[key] = LogicalAttribute(
                name=attr,
                entity_type=entity,
                dtype=_dtype_for(attr),
                unit_domain=_unit_domain(attr),
                nullable=True,
            )

    for sql in statements:
        try:
            tree = sqlglot.parse_one(sql, read="sqlite")
        except Exception:
            tree = None
        if tree is not None:
            tables = [node.name.lower() for node in tree.find_all(exp.Table) if node.name]
            entities.update(tables)
            default = tables[0] if len(tables) == 1 else None
            aliases = {
                (node.alias or node.name).lower(): node.name.lower()
                for node in tree.find_all(exp.Table)
                if node.name
            }
            derived = expression_aliases(tree, default)
            expressions.update(derived)
            skip = set(derived)
            for column in tree.find_all(exp.Column):
                if not column.name:
                    continue
                if column.name.lower() in skip:
                    continue
                raw_table = column.table.lower() if column.table else default
                entity = aliases.get(raw_table, raw_table) if raw_table else default
                if entity:
                    _add_attr(entity, column.name)
            for match in _JOIN_ON.finditer(sql):
                relationships.append(
                    LogicalRelationship(
                        name=f"{match.group(2).lower()}_{match.group(4).lower()}",
                        from_entity=match.group(2).lower(),
                        to_entity=match.group(4).lower(),
                        from_attribute=match.group(3).lower(),
                        to_attribute=match.group(5).lower(),
                    )
                )
            continue
        for match in _FROM.finditer(sql):
            entities.add(match.group(1).lower())
        for match in _JOIN.finditer(sql):
            entities.add(match.group(1).lower())
        for match in _IDENT.finditer(sql):
            entity, attr = match.group(1).lower(), match.group(2).lower()
            if entity in {"select", "where", "group", "order", "having", "count", "sum", "avg", "min", "max"}:
                continue
            _add_attr(entity, attr)
        for match in _JOIN_ON.finditer(sql):
            relationships.append(
                LogicalRelationship(
                    name=f"{match.group(2).lower()}_{match.group(4).lower()}",
                    from_entity=match.group(2).lower(),
                    to_entity=match.group(4).lower(),
                    from_attribute=match.group(3).lower(),
                    to_attribute=match.group(5).lower(),
                )
            )

    entity_list = sorted(entities)
    identity_grain = {entity: "mention" for entity in entity_list}
    digest = hashlib.sha256("|".join(sorted(f"{e}.{a}" for e, a in attributes)).encode()).hexdigest()[:12]
    return LogicalSchema(
        id=f"{schema_id}-{digest}",
        entity_types=entity_list,
        attributes=sorted(attributes.values(), key=lambda row: (row.entity_type, row.name)),
        relationships=relationships,
        identity_grain=identity_grain,
        expressions=sorted(expressions.values(), key=lambda row: (row.entity_type, row.alias)),
    )


class SchemaConflict(ValueError):
    """Identifier does not bind to the published logical schema."""


def bind_identifier(logical: LogicalSchema, entity: str, attribute: str | None = None) -> str:
    entity = entity.lower()
    if entity not in {name.lower() for name in logical.entity_types}:
        raise SchemaConflict(f"unbound entity {entity}")
    if attribute is None:
        return entity
    attribute = attribute.lower()
    for item in logical.attributes:
        if item.entity_type.lower() == entity and item.name.lower() == attribute:
            return f"{entity}.{attribute}"
    for item in logical.expressions:
        if item.alias.lower() == attribute and item.entity_type.lower() in {entity, ""}:
            return f"{entity}.{attribute}"
    raise SchemaConflict(f"unbound attribute {entity}.{attribute}")


def resolve_bases(logical: LogicalSchema, attribute: str) -> list[str]:
    bare = attribute.split(".")[-1].lower()
    for item in logical.expressions:
        if item.alias.lower() == bare:
            return list(item.base_attributes)
    return [attribute]


def qualify(entity: str, attribute: str) -> str:
    return f"{entity.lower()}.{attribute.lower()}"


def extend_logical_schema(logical: LogicalSchema, statements: Iterable[str]) -> LogicalSchema:
    """Add AST columns that were omitted when L was first induced."""

    extra = infer_logical_schema(statements, schema_id=logical.id)
    have = {(item.entity_type, item.name) for item in logical.attributes}
    attrs = list(logical.attributes)
    for item in extra.attributes:
        key = (item.entity_type, item.name)
        if key in have:
            continue
        attrs.append(item)
        have.add(key)
    entities = sorted({*logical.entity_types, *extra.entity_types})
    grain = dict(logical.identity_grain)
    for entity in entities:
        grain.setdefault(entity, "mention")
    return logical.model_copy(
        update={
            "entity_types": entities,
            "attributes": attrs,
            "identity_grain": grain,
        }
    )
