"""Synthesis-time NL2SQL compiler for frozen offline serving."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Any

from json_repair import repair_json
from sqlglot import exp, parse_one

from spp.budget_ledger import GlobalBudgetLedger
from spp.budgeted_llm import BudgetedLLMClient
from spp.population import repair_join_columns_from_overlap
from spp.query_plan_compiler import compile_query_plan
from spp.sql_validator import validate_sql
from spp.spec import AttributeRef, QueryRequirement, SynthesisConfig
from spp.workload_intent import _expected_aggregate


_SQL_START = re.compile(r"\b(SELECT|WITH)\b", re.IGNORECASE)


def _extract_sql(response: str) -> str:
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", response, re.I | re.S)
    candidate = fenced.group(1).strip() if fenced else response.strip()
    match = _SQL_START.search(candidate)
    if not match:
        raise ValueError("NL2SQL response contains no SELECT/WITH statement")
    sql = candidate[match.start() :].strip()
    # Strip explanatory text after the first semicolon.
    if ";" in sql:
        sql = sql.split(";", 1)[0].strip()
    return sql


def _verification_payload(response: str) -> dict:
    start, end = response.find("{"), response.rfind("}")
    if start < 0:
        raise ValueError("NL2SQL verifier returned no JSON object")
    candidate = response[start : end + 1] if end >= start else response[start:]
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        # Smaller/local models frequently emit SQL backslashes or literal
        # newlines inside JSON strings. Repair only JSON-invalid escapes and
        # control characters; preserve valid escapes and all SQL text.
        repaired: list[str] = []
        in_string = False
        index = 0
        while index < len(candidate):
            character = candidate[index]
            preceding_backslashes = 0
            cursor = index - 1
            while cursor >= 0 and candidate[cursor] == "\\":
                preceding_backslashes += 1
                cursor -= 1
            if character == '"' and preceding_backslashes % 2 == 0:
                in_string = not in_string
                repaired.append(character)
            elif in_string and character == "\\":
                following = (
                    candidate[index + 1]
                    if index + 1 < len(candidate)
                    else ""
                )
                if following not in '"\\/bfnrtu':
                    repaired.append("\\\\")
                else:
                    repaired.append(character)
            elif in_string and character == "\n":
                repaired.append("\\n")
            elif in_string and character == "\r":
                repaired.append("\\r")
            elif in_string and character == "\t":
                repaired.append("\\t")
            else:
                repaired.append(character)
            index += 1
        try:
            payload = json.loads("".join(repaired))
        except json.JSONDecodeError:
            try:
                payload = repair_json(candidate, return_objects=True)
            except Exception as exc:
                raise ValueError(
                    "NL2SQL verifier returned malformed JSON"
                ) from exc
    if not isinstance(payload, dict) or not isinstance(
        payload.get("consistent"), bool
    ):
        raise ValueError("NL2SQL verifier omitted boolean 'consistent'")
    return payload


def _database_profile(database_path: Path, config: SynthesisConfig) -> list[dict]:
    profile = []
    uri = f"file:{Path(database_path).resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        for relation in config.schema.relations:
            quoted = relation.name.replace('"', '""')
            row_count = connection.execute(
                f'SELECT COUNT(*) FROM "{quoted}"'
            ).fetchone()[0]
            samples = [
                dict(row)
                for row in connection.execute(
                    f'SELECT * FROM "{quoted}" LIMIT 3'
                ).fetchall()
            ]
            non_null_counts = {}
            for column in relation.attributes:
                quoted_column = column.replace('"', '""')
                non_null_counts[column] = connection.execute(
                    f'SELECT COUNT("{quoted_column}") FROM "{quoted}"'
                ).fetchone()[0]
            profile.append(
                {
                    "table": relation.name,
                    "row_count": row_count,
                    "non_null_counts": non_null_counts,
                    "sample_rows": samples,
                }
            )
    return profile


def _query_is_informative(database_path: Path, sql: str) -> bool:
    uri = f"file:{Path(database_path).resolve()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            cursor = connection.execute(sql)
            rows = cursor.fetchmany(20)
            return bool(rows) and any(
                value is not None
                for row in rows
                for value in row
            )
    except sqlite3.Error:
        return False


def _query_validation_error(database_path: Path, sql: str) -> str | None:
    normalized = sql.strip().rstrip(";").strip()
    first = normalized.split(None, 1)[0].lower() if normalized else ""
    if first not in {"select", "with"}:
        return "query must begin with SELECT or WITH"
    forbidden = (
        " insert ", " update ", " delete ", " drop ", " alter ", " create ",
        " attach ", " detach ", " pragma ", " vacuum ",
    )
    if any(token in f" {normalized.lower()} " for token in forbidden):
        return "query contains a forbidden mutating statement"
    uri = f"file:{Path(database_path).resolve()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            connection.execute(
                f"EXPLAIN QUERY PLAN {normalized}"
            ).fetchall()
    except sqlite3.Error as exc:
        return str(exc)
    return None


def _semantic_validation_errors(
    requirement: QueryRequirement,
    config: SynthesisConfig,
    sql: str,
) -> list[str]:
    """Check NL/IR atoms that SQLite syntax validation cannot detect."""
    lowered_text = requirement.text.lower()
    normalized_sql = re.sub(r'["`]', "", sql.lower())
    errors: list[str] = []

    expected_function = _expected_aggregate(requirement.text)
    if expected_function and not re.search(
        rf"\b{expected_function}\s*\(", normalized_sql
    ):
        errors.append(f"missing {expected_function.upper()} aggregate")

    if requirement.plan is not None:
        for aggregate in requirement.plan.aggregates:
            if aggregate.attribute is None:
                continue
            pattern = (
                rf"\b{aggregate.function}\s*\(\s*(?:distinct\s+)?"
                rf"(?:[a-z_][a-z0-9_]*\.)?{re.escape(aggregate.attribute.attribute)}\b"
            )
            if not re.search(pattern, normalized_sql):
                errors.append(
                    "aggregate target must be "
                    f"{aggregate.attribute.entity}.{aggregate.attribute.attribute}"
                )
        group_match = re.search(
            r"\bgroup\s+by\b(.+?)(?:\border\s+by\b|\blimit\b|$)",
            normalized_sql,
            re.DOTALL,
        )
        group_sql = group_match.group(1) if group_match else ""
        equivalence_edges = [
            (join.left, join.right)
            for join in requirement.plan.joins
            if join.join_type == "inner"
        ]
        equivalence_edges.extend(
            (
                AttributeRef(relation.name, column),
                AttributeRef(target_table, target_column),
            )
            for relation in config.schema.relations
            for column, target_table, target_column in relation.foreign_keys
        )
        for reference in requirement.plan.group_by:
            equivalent_refs = {reference}
            changed = True
            while changed:
                changed = False
                for left, right in equivalence_edges:
                    if left in equivalent_refs and right not in equivalent_refs:
                        equivalent_refs.add(right)
                        changed = True
                    if right in equivalent_refs and left not in equivalent_refs:
                        equivalent_refs.add(left)
                        changed = True
            if not any(
                re.search(
                    rf"\b{re.escape(candidate.attribute)}\b", group_sql
                )
                for candidate in equivalent_refs
            ):
                errors.append(
                    f"missing GROUP BY dimension {reference.entity}.{reference.attribute}"
                )
        for join in requirement.plan.joins:
            if join.left.entity == join.right.entity:
                continue
            left = re.escape(join.left.attribute)
            right = re.escape(join.right.attribute)
            if not (
                re.search(
                    rf"\b{left}\b\s*=\s*(?:[a-z_][a-z0-9_]*\.)?\b{right}\b",
                    normalized_sql,
                )
                or re.search(
                    rf"\b{right}\b\s*=\s*(?:[a-z_][a-z0-9_]*\.)?\b{left}\b",
                    normalized_sql,
                )
            ):
                errors.append(
                    "missing join edge "
                    f"{join.left.entity}.{join.left.attribute}="
                    f"{join.right.entity}.{join.right.attribute}"
                )

        def check_predicate(predicate) -> None:
            if predicate is None:
                return
            if predicate.kind in {"and", "or"}:
                for child in predicate.children:
                    check_predicate(child)
                return
            attribute = predicate.attribute.attribute
            value = predicate.value
            value_rendered = str(value).strip().lower()
            value_is_explicit = (
                isinstance(value, (int, float))
                or value_rendered in lowered_text
            )
            if value_is_explicit and not re.search(
                rf"\b{re.escape(attribute)}\b", normalized_sql
            ):
                errors.append(f"missing predicate attribute {attribute}")
            if (
                value_is_explicit
                and predicate.operator not in {"is_null", "is_not_null", "contains"}
                and value_rendered not in normalized_sql
            ):
                errors.append(f"missing predicate literal {value!r}")

        check_predicate(requirement.plan.predicate)

    if "matching" in lowered_text and len(requirement.entities) > 1:
        referenced_tables = set(
            re.findall(
                r"\b(?:from|join)\s+([a-z_][a-z0-9_]*)",
                normalized_sql,
            )
        )
        for entity in requirement.entities:
            if entity.lower() not in referenced_tables:
                errors.append(f"missing matched entity {entity}")

    # Preserve explicit numeric restrictions even when the LLM omitted the
    # entire predicate from its plan.
    numeric_literals = re.findall(
        r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d+(?:\.\d+)?\b",
        lowered_text,
    )
    for rendered_number in numeric_literals:
        number = rendered_number.replace(",", "")
        if not re.search(
            rf"(?<![a-z0-9_]){re.escape(number)}(?![a-z0-9_])",
            normalized_sql,
        ):
            errors.append(f"missing numeric literal {rendered_number}")
    word_numbers = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }
    for word, value in word_numbers.items():
        if re.search(rf"\b{word}\s+million\b", lowered_text):
            rendered = str(value * 1_000_000)
            if rendered not in normalized_sql:
                errors.append(f"missing numeric literal {rendered}")

    all_columns = {
        column.lower()
        for relation in config.schema.relations
        for column in relation.attributes
    }
    for _attribute, literal in re.findall(
        r"\b([a-z_][a-z0-9_.]*)\s*(?:=|!=|<>|<=|>=|<|>)\s*'([^']*)'",
        normalized_sql,
    ):
        if literal in all_columns and literal.replace("_", " ") not in lowered_text:
            errors.append(f"invented schema-name literal {literal!r}")

    # "No <measure>" means equality to zero, not a non-negative range.
    if (
        " no " in f" {lowered_text} "
        and not re.search(
            r"\bno\s+(?:more|fewer|less)\s+than\b", lowered_text
        )
    ):
        for relation in config.schema.relations:
            for column in relation.attributes:
                phrase = column.replace("_", " ")
                if phrase in lowered_text and re.search(
                    rf"\bno\b[^,.?]*\b{re.escape(phrase.split()[-1])}\b",
                    lowered_text,
                ):
                    if not re.search(
                        rf"\b{re.escape(column)}\b\s*=\s*0\b",
                        normalized_sql,
                    ):
                        errors.append(f"{column} must equal zero")

    return list(dict.fromkeys(errors))


def _candidate_validation_error(
    requirement: QueryRequirement,
    config: SynthesisConfig,
    database_path: Path,
    sql: str,
) -> str | None:
    """Return one deterministic syntax/plan-contract error, if any."""
    structural_error = _query_validation_error(database_path, sql)
    if structural_error is not None:
        return structural_error
    errors = list(validate_sql(requirement, config, database_path, sql).errors)
    if requirement.plan is None:
        errors.extend(_semantic_validation_errors(requirement, config, sql))
    errors = list(dict.fromkeys(errors))
    return "semantic mismatch: " + "; ".join(errors) if errors else None


def _repair_sql_joins_from_database(
    sql: str,
    requirement: QueryRequirement,
    config: SynthesisConfig,
    database_path: Path,
) -> str | None:
    """Rebind invalid join columns using strongest synthesized-data overlap."""

    try:
        expression = parse_one(sql, read="sqlite")
    except Exception:
        return None
    aliases = {
        table.alias_or_name: table.name
        for table in expression.find_all(exp.Table)
    }
    if not aliases:
        return None

    def quoted(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    rows_by_table = {}
    try:
        with sqlite3.connect(database_path) as connection:
            connection.row_factory = sqlite3.Row
            for table_name in set(aliases.values()):
                rows_by_table[table_name] = [
                    dict(row)
                    for row in connection.execute(
                        f"SELECT * FROM {quoted(table_name)}"
                    ).fetchall()
                ]
    except sqlite3.Error:
        return None

    rebindings = {}
    changed = False
    for join in expression.find_all(exp.Join):
        predicate = join.args.get("on")
        if predicate is None:
            continue
        for equality in predicate.find_all(exp.EQ):
            left = equality.left
            right = equality.right
            if not isinstance(left, exp.Column) or not isinstance(
                right, exp.Column
            ):
                continue
            left_table = aliases.get(left.table)
            right_table = aliases.get(right.table)
            if (
                not left_table
                or not right_table
                or left_table == right_table
            ):
                continue
            rebound = repair_join_columns_from_overlap(
                [dict(row) for row in rows_by_table.get(left_table, ())],
                left.name,
                [dict(row) for row in rows_by_table.get(right_table, ())],
                right.name,
                left_table=left_table,
                right_table=right_table,
            )
            if rebound is None:
                continue
            left_column, right_column = rebound
            rebindings[(left_table, left.name)] = left_column
            rebindings[(right_table, right.name)] = right_column
            left.set("this", exp.to_identifier(left_column))
            right.set("this", exp.to_identifier(right_column))
            changed = True
    if not changed:
        return None

    rebound_requirement = requirement
    if requirement.plan is not None:
        joins = []
        for join in requirement.plan.joins:
            joins.append(
                replace(
                    join,
                    left=replace(
                        join.left,
                        attribute=rebindings.get(
                            (join.left.entity, join.left.attribute),
                            join.left.attribute,
                        ),
                    ),
                    right=replace(
                        join.right,
                        attribute=rebindings.get(
                            (join.right.entity, join.right.attribute),
                            join.right.attribute,
                        ),
                    ),
                )
            )
        rebound_requirement = replace(
            requirement,
            plan=replace(requirement.plan, joins=tuple(joins)),
        )
    repaired = expression.sql(dialect="sqlite")
    return (
        repaired
        if _candidate_validation_error(
            rebound_requirement,
            config,
            database_path,
            repaired,
        )
        is None
        else None
    )


def make_nl2sql_compiler(llm_client: Any):
    """Return an ``OfflineSynthesisSystem`` compiler callback."""

    def compile_query(
        requirement: QueryRequirement,
        config: SynthesisConfig,
        database_path: Path,
        ledger: GlobalBudgetLedger,
    ) -> str:
        deterministic_fallback: str | None = None
        is_sql = bool(
            re.match(r"^\s*(select|with)\b", requirement.text, re.IGNORECASE)
        )
        if is_sql:
            referenced_tables = {
                match.lower()
                for match in re.findall(
                    r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*)",
                    requirement.text,
                    re.IGNORECASE,
                )
            }
            candidate_tables = {
                relation.name.lower() for relation in config.schema.relations
            }
            original_sql = requirement.text.strip().rstrip(";")
            if (
                referenced_tables <= candidate_tables
                and _candidate_validation_error(
                    requirement, config, database_path, original_sql
                )
                is None
            ):
                return original_sql
        if requirement.plan is not None:
            operators = set(requirement.operators)
            aggregate_ops = {"count", "sum", "avg", "min", "max"}
            plan_complete = not (
                (operators & aggregate_ops and not requirement.plan.aggregates)
                or (
                    "filter" in operators
                    and requirement.plan.predicate is None
                    and not requirement.plan.having
                )
                or ("having" in operators and not requirement.plan.having)
            )
            deterministic_sql = (
                compile_query_plan(requirement.plan, config)
                if plan_complete
                else None
            )
            if (
                deterministic_sql
                and _candidate_validation_error(
                    requirement, config, database_path, deterministic_sql
                ) is None
            ):
                deterministic_fallback = deterministic_sql
            if deterministic_fallback:
                return deterministic_fallback
        schema_payload = [
            {
                "table": relation.name,
                "columns": list(relation.attributes),
                "semantic_types": dict(relation.semantic_types),
                "primary_key": relation.primary_key,
                "foreign_keys": [
                    {
                        "column": column,
                        "target_table": target_table,
                        "target_column": target_column,
                    }
                    for column, target_table, target_column in relation.foreign_keys
                ],
            }
            for relation in config.schema.relations
        ]
        data_profile = _database_profile(database_path, config)
        prompt = (
            "Compile the analytical question into one read-only SQLite query. "
            "Use only the provided schema. Return SQL only; never create, modify, "
            "attach, or populate data.\n\nSchema:\n"
            f"{json.dumps(schema_payload, indent=2)}\n\n"
            "Gold-free database profile (use populated columns and avoid empty "
            f"join paths):\n{json.dumps(data_profile, indent=2, default=str)}\n\n"
            + (
                "Original SQL expressing the intended query (rewrite it for "
                "the candidate schema):\n"
                if is_sql
                else "Question:\n"
            )
            + requirement.text
        )
        budgeted = BudgetedLLMClient(
            llm_client,
            ledger,
            default_stage="nl2sql",
            config_id=config.config_id,
            query_id=requirement.query_id,
        )
        response = budgeted.generate(
            prompt,
            max_tokens=1024,
            temperature=0.0,
            operation="compile_query",
        )
        try:
            sql = _extract_sql(response)
        except ValueError:
            sql = response.strip()
        initial_error = _candidate_validation_error(
            requirement, config, database_path, sql
        )
        if initial_error is not None:
            physically_repaired = _repair_sql_joins_from_database(
                sql,
                requirement,
                config,
                database_path,
            )
            if physically_repaired is not None:
                return physically_repaired
        verification_prompt = (
            "Check whether the SQLite query exactly answers the stated "
            "analytical intent using the supplied schema. Verify requested "
            "entities, attributes, predicates, grouping, and aggregates. "
            "Return ONLY JSON: {\"consistent\": true|false, \"reason\": "
            "\"...\", \"corrected_sql\": \"...\"}. If inconsistent, provide "
            "a corrected read-only query; otherwise corrected_sql may be null."
            f"\n\nIntent:\n{requirement.text}"
            f"\n\nStructured requirements:\n"
            f"{json.dumps({'entities': requirement.entities, 'attributes': requirement.attributes, 'relationships': requirement.relationships, 'operators': requirement.operators, 'units': requirement.units})}"
            f"\n\nSchema:\n{json.dumps(schema_payload)}"
            f"\n\nGold-free database profile:\n"
            f"{json.dumps(data_profile, default=str)}"
            f"\n\nCandidate SQL:\n{sql}"
            f"\n\nSQLite validation: "
            f"{'valid' if initial_error is None else f'invalid: {initial_error}'}"
        )
        verification_response = budgeted.generate(
            verification_prompt,
            max_tokens=1024,
            temperature=0.0,
            operation="verify_compiled_query",
        )
        try:
            verification = _verification_payload(verification_response)
        except ValueError:
            # Verification is advisory evidence. A malformed response cannot
            # veto a query that SQLite itself validates.
            if initial_error is None:
                return sql
            verification = {
                "consistent": False,
                "reason": "verifier returned malformed JSON",
                "corrected_sql": None,
            }
        if verification["consistent"] and initial_error is None:
            return sql

        corrected = verification.get("corrected_sql")
        corrected_sql = ""
        corrected_error = "verifier supplied no corrected SQL"
        if isinstance(corrected, str) and corrected.strip():
            try:
                corrected_sql = _extract_sql(corrected)
                corrected_error = _candidate_validation_error(
                    requirement, config, database_path, corrected_sql
                )
            except ValueError:
                corrected_error = "corrected response contains no SQL"
        elif (
            initial_error is None
            and _query_is_informative(database_path, sql)
        ):
            return sql
        if corrected_sql and corrected_error is None:
            # Never let a semantic repair destroy an informative executable
            # result in favor of an empty one.
            if (
                initial_error is None
                and _query_is_informative(database_path, sql)
                and not _query_is_informative(database_path, corrected_sql)
            ):
                return sql
            return corrected_sql

        repair_source = corrected_sql or sql
        repair_error = corrected_error if corrected_sql else initial_error
        repair_prompt = (
            "Repair the candidate into one syntactically valid, read-only "
            "SQLite query that answers the analytical intent. Use only the "
            "provided schema, use populated columns, and avoid empty join "
            "paths. Return SQL only.\n\n"
            f"Intent:\n{requirement.text}\n\n"
            f"Schema:\n{json.dumps(schema_payload)}\n\n"
            "Gold-free database profile:\n"
            f"{json.dumps(data_profile, default=str)}\n\n"
            f"Candidate SQL:\n{repair_source}\n\n"
            f"SQLite error:\n{repair_error or 'none'}\n\n"
            "Verifier objection:\n"
            f"{verification.get('reason', 'unspecified inconsistency')}"
        )
        repaired_sql = ""
        repaired_error = "repair response contains no SQL"
        try:
            repaired_sql = _extract_sql(
                budgeted.generate(
                    repair_prompt,
                    max_tokens=1024,
                    temperature=0.0,
                    operation="repair_compiled_query",
                )
            )
            repaired_error = _candidate_validation_error(
                requirement, config, database_path, repaired_sql
            )
        except ValueError:
            pass
        if repaired_sql and repaired_error is None:
            if (
                initial_error is None
                and _query_is_informative(database_path, sql)
                and not _query_is_informative(database_path, repaired_sql)
            ):
                return sql
            return repaired_sql
        for candidate in (repaired_sql, corrected_sql, sql):
            if not candidate:
                continue
            physically_repaired = _repair_sql_joins_from_database(
                candidate,
                requirement,
                config,
                database_path,
            )
            if physically_repaired is not None:
                return physically_repaired
        if initial_error is None:
            return sql
        raise ValueError(
            "NL2SQL could not produce valid SQLite after repair: "
            f"{repaired_error or initial_error}"
        )

    return compile_query
