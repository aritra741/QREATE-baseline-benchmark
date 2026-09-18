"""Live signature population. AST-typed operators only. No gold, no corpus names."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from quwarts.core.ledger import BudgetExhausted, BudgetedCaller
from quwarts.core.models import SourceDocument, Workload
from quwarts.core.signature import AtomicPredicate
from quwarts.core.signature_classify import (
    membership_prompt,
    nonempty_prompt,
    parse_nonempty,
    parse_v2,
    value_is_missing,
)
from quwarts.core.signature_realize import (
    close_attribute,
    is_membership,
    is_presence,
    live_predicates,
)
from quwarts.core.truth import (
    PredicateLabel,
    is_label_resolved,
    merge_atoms,
    rewrite_cell,
)

_NAME_KEYS = ("name", "generic_name")


@dataclass
class PopulateReport:
    n_rows: int = 0
    n_presence_jobs: int = 0
    n_membership_jobs: int = 0
    n_presence_true: int = 0
    n_presence_null: int = 0
    n_membership_true: int = 0
    n_membership_false: int = 0
    n_membership_null: int = 0
    n_conflicts: int = 0
    n_closed: int = 0
    closed: bool = False
    tokens_presence: int = 0
    tokens_membership: int = 0


@dataclass
class _RowJob:
    table: str
    doc_id: Any
    rowid: int
    attribute: str
    cell: Any
    predicates: list[AtomicPredicate]
    labels: dict[str, PredicateLabel]
    priority: float
    document: str
    entity_name: str
    surfaces: list[str]


def clip_document(text: str, limit: int = 4000) -> str:
    return (text or "")[:limit]


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _like_match(value: str, pattern: str) -> bool:
    escaped = ""
    for char in pattern:
        if char == "%":
            escaped += ".*"
        elif char == "_":
            escaped += "."
        elif char in {".", "^", "$", "*", "+", "?", "{", "}", "[", "]", "\\", "|", "(", ")"}:
            escaped += "\\" + char
        else:
            escaped += char
    import re

    return re.fullmatch(escaped, value, flags=re.DOTALL) is not None


def cell_matches_membership(pred: AtomicPredicate, value: Any) -> bool:
    if value_is_missing(value):
        return False
    text = str(value)
    for transform in pred.transforms:
        if transform == "lower":
            text = text.lower()
        elif transform == "upper":
            text = text.upper()
        elif transform == "trim":
            text = text.strip()
    literal = pred.literal or ""
    if pred.operator == "LIKE":
        return _like_match(text, literal)
    if pred.operator == "=":
        return text == literal
    if pred.operator == "IN":
        return text in literal.split("|")
    return False


def deterministic_labels(
    predicates: Iterable[AtomicPredicate],
    value: Any,
) -> dict[str, PredicateLabel]:
    labels: dict[str, PredicateLabel] = {}
    missing = value_is_missing(value)
    for pred in predicates:
        if is_presence(pred) and not missing:
            labels[pred.pred_id] = PredicateLabel("TRUE", "known", provenance=("cell",))
        elif is_membership(pred) and not missing and cell_matches_membership(pred, value):
            labels[pred.pred_id] = PredicateLabel("TRUE", "known", provenance=("cell_match",))
    return labels


def label_from_stored(value: Any, resolved: Any = 1) -> PredicateLabel | None:
    if resolved != 1:
        return None
    if value == 1:
        return PredicateLabel("TRUE", "known", provenance=("stored",))
    if value == 0:
        return PredicateLabel("FALSE", "known", provenance=("stored",))
    if value is None:
        return PredicateLabel("NULL", "known", provenance=("stored_null",))
    return None


def atom_unresolved(labels: dict[str, PredicateLabel], pred: AtomicPredicate) -> bool:
    return not is_label_resolved(labels.get(pred.pred_id))


def atom_priority(pred: AtomicPredicate, workload: Workload | None) -> float:
    freq = float(len(pred.query_ids) or pred.raw_occurrences or 1)
    amp_val = 1.0
    if workload is not None:
        req = workload.requirements.get(pred.attribute)
        if req is not None:
            amp_val = float(req.amp if req.amp is not None else 1.0)
    return freq * amp_val


def job_priority(
    predicates: Iterable[AtomicPredicate],
    labels: dict[str, PredicateLabel],
    workload: Workload | None,
) -> float:
    total = 0.0
    for pred in predicates:
        if not atom_unresolved(labels, pred):
            continue
        total += atom_priority(pred, workload)
    return total


def populate_nonempty(
    attribute: str,
    cell: Any,
    document: str,
    caller: BudgetedCaller | None,
) -> PredicateLabel:
    """Presence only. Existing cell → TRUE. No grounded span → NULL, never FALSE."""

    if not value_is_missing(cell):
        return PredicateLabel("TRUE", "known", provenance=("cell",))
    if caller is None or not document:
        return PredicateLabel("NULL", "uncertain", provenance=("nonempty_abstain",))
    try:
        text = caller.complete(
            nonempty_prompt(attribute, clip_document(document)),
            purpose="sig_nonempty",
            attribute=attribute,
            system="Extract a grounded attribute span. JSON only.",
            max_tokens=120,
        )
    except BudgetExhausted:
        return PredicateLabel("NULL", "failed", provenance=("budget",))
    except Exception:
        return PredicateLabel("NULL", "failed", provenance=("error",))
    return parse_nonempty(text, document)


def populate_membership(
    attribute: str,
    predicates: list[AtomicPredicate],
    *,
    entity_name: str | None,
    surfaces: list[str],
    document: str | None,
    caller: BudgetedCaller | None,
) -> dict[str, PredicateLabel]:
    """Membership only. Literal absence does not gate the answer."""

    members = [pred for pred in predicates if is_membership(pred)]
    if not members:
        return {}
    if caller is None:
        return {
            pred.pred_id: PredicateLabel("NULL", "uncertain", provenance=("membership_abstain",))
            for pred in members
        }
    try:
        text = caller.complete(
            membership_prompt(
                attribute,
                members,
                entity_name=entity_name,
                surfaces=surfaces,
                document=clip_document(document or "") if document else None,
            ),
            purpose="sig_membership",
            attribute=attribute,
            system="Classify membership concepts. JSON only. Multiple may apply.",
            max_tokens=280,
        )
    except BudgetExhausted:
        return {
            pred.pred_id: PredicateLabel("NULL", "failed", provenance=("budget",))
            for pred in members
        }
    except Exception:
        return {
            pred.pred_id: PredicateLabel("NULL", "failed", provenance=("error",))
            for pred in members
        }
    return parse_v2(text, members)


def _doc_text(documents: dict[str, str], doc_id: Any) -> str:
    if doc_id is None:
        return ""
    key = str(doc_id)
    if key in documents:
        return documents[key]
    stem = Path(key).stem
    if stem in documents:
        return documents[stem]
    for doc_key, text in documents.items():
        if Path(str(doc_key)).stem == stem or str(doc_key).endswith(key):
            return text
    return ""


def _entity_name(row: dict[str, Any], table: str) -> str:
    for key in (f"{table}_name", *_NAME_KEYS):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return Path(str(row.get("doc_id") or "")).stem


def _surfaces(row: dict[str, Any], column: str) -> list[str]:
    found: list[str] = []
    value = row.get(column)
    if value not in (None, ""):
        found.append(str(value))
    for key, item in row.items():
        name = str(key)
        if name.endswith("_name") and item not in (None, ""):
            found.append(str(item))
    return list(dict.fromkeys(found))


def _tables(conn: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite%'"
        )
    ]


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({_quote(table)})")}


def resolve_table(conn: sqlite3.Connection, pred: AtomicPredicate) -> str | None:
    tables = _tables(conn)
    wanted = pred.table
    for table in tables:
        if table.lower() == wanted.lower():
            cols = _columns(conn, table)
            if pred.column in cols or pred.sig_name in cols:
                return table
    for table in tables:
        cols = _columns(conn, table)
        if pred.column in cols:
            return table
    return None


def ensure_signature_columns(conn: sqlite3.Connection, predicates: Iterable[AtomicPredicate]) -> dict[str, set[str]]:
    existing = {table: _columns(conn, table) for table in _tables(conn)}
    for pred in predicates:
        table = resolve_table(conn, pred)
        if table is None:
            continue
        if pred.sig_name not in existing[table]:
            conn.execute(f"ALTER TABLE {_quote(table)} ADD COLUMN {_quote(pred.sig_name)} INTEGER")
            existing[table].add(pred.sig_name)
        if pred.resolved_name not in existing[table]:
            conn.execute(
                f"ALTER TABLE {_quote(table)} ADD COLUMN {_quote(pred.resolved_name)} INTEGER DEFAULT 0"
            )
            existing[table].add(pred.resolved_name)
    return existing


def _write_row(
    conn: sqlite3.Connection,
    table: str,
    rowid: int,
    predicates: list[AtomicPredicate],
    labels: dict[str, PredicateLabel],
    columns: set[str],
) -> None:
    writable = [pred for pred in predicates if pred.sig_name in columns]
    if not writable:
        return
    assignments = ", ".join(
        f"{_quote(pred.sig_name)} = ?, {_quote(pred.resolved_name)} = ?" for pred in writable
    )
    values: list[Any] = []
    for pred in writable:
        label = labels.get(pred.pred_id)
        resolved = is_label_resolved(label)
        values.append(rewrite_cell(label) if label is not None and resolved else None)
        values.append(1 if resolved else 0)
    conn.execute(
        f"UPDATE {_quote(table)} SET {assignments} WHERE rowid = ?",
        values + [rowid],
    )


def _close_labels(
    labels: dict[str, PredicateLabel],
    predicates: list[AtomicPredicate],
) -> tuple[dict[str, PredicateLabel], list[str]]:
    cells = {pred.pred_id: rewrite_cell(labels[pred.pred_id]) if pred.pred_id in labels else None for pred in predicates}
    closed, violations = close_attribute(cells, predicates)
    updated = dict(labels)
    for pred in predicates:
        value = closed.get(pred.pred_id)
        if value == 1:
            current = updated.get(pred.pred_id)
            if current is None or current.sql_truth != "TRUE":
                updated[pred.pred_id] = PredicateLabel(
                    "TRUE",
                    "known",
                    provenance=(*(current.provenance if current else ()), "closure"),
                )
        elif value == 0:
            current = updated.get(pred.pred_id)
            if current is None or current.sql_truth != "FALSE":
                updated[pred.pred_id] = PredicateLabel(
                    "FALSE",
                    "known",
                    provenance=(*(current.provenance if current else ()), "closure"),
                )
    return updated, violations


def apply_row_operators(
    labels: dict[str, PredicateLabel],
    predicates: list[AtomicPredicate],
    *,
    attribute: str,
    cell: Any,
    document: str,
    entity_name: str,
    surfaces: list[str],
    caller: BudgetedCaller | None,
    run_presence: bool = True,
    run_membership: bool = True,
) -> dict[str, PredicateLabel]:
    presence = [pred for pred in predicates if is_presence(pred)]
    members = [pred for pred in predicates if is_membership(pred)]
    merged = dict(labels)
    if run_presence and presence:
        unresolved = [pred for pred in presence if atom_unresolved(merged, pred)]
        if unresolved:
            label = populate_nonempty(attribute, cell, document, caller)
            incoming = {pred.pred_id: label for pred in unresolved}
            merged = merge_atoms(merged, incoming, {pred.pred_id for pred in presence})
    if run_membership and members:
        unresolved = [pred for pred in members if atom_unresolved(merged, pred)]
        if unresolved:
            incoming = populate_membership(
                attribute,
                unresolved,
                entity_name=entity_name,
                surfaces=surfaces,
                document=document,
                caller=caller,
            )
            merged = merge_atoms(merged, incoming, {pred.pred_id for pred in members})
    return merged


def populate_signatures(
    sqlite_path: str | Path,
    predicates: Iterable[AtomicPredicate],
    documents: list[SourceDocument] | dict[str, str] | None = None,
    caller: BudgetedCaller | None = None,
    workload: Workload | None = None,
    *,
    workers: int = 1,
) -> PopulateReport:
    """Write sig_* columns. Leaves rows, keys, and non-signature cells unchanged."""

    live = live_predicates(predicates)
    report = PopulateReport()
    if not live:
        report.closed = True
        return report
    texts: dict[str, str] = {}
    if isinstance(documents, dict):
        texts = {str(key): value for key, value in documents.items()}
    elif documents:
        texts = {doc.doc_id: doc.text for doc in documents}

    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        existing = ensure_signature_columns(conn, live)
        by_attr: dict[str, list[AtomicPredicate]] = defaultdict(list)
        table_for: dict[str, str] = {}
        for pred in live:
            table = resolve_table(conn, pred)
            if table is None:
                continue
            by_attr[pred.attribute].append(pred)
            table_for[pred.attribute] = table

        jobs: list[_RowJob] = []
        for attr, preds in by_attr.items():
            table = table_for[attr]
            column = preds[0].column
            cols = existing[table]
            has_doc = "doc_id" in cols
            for row in conn.execute(f"SELECT rowid AS _rid, * FROM {_quote(table)}"):
                payload = dict(row)
                rowid = int(payload.pop("_rid"))
                doc_id = payload.get("doc_id") if has_doc else rowid
                cell = payload.get(column)
                labels: dict[str, PredicateLabel] = {}
                for pred in preds:
                    stored = label_from_stored(
                        payload.get(pred.sig_name),
                        payload.get(pred.resolved_name),
                    )
                    if stored is not None:
                        labels[pred.pred_id] = stored
                labels = merge_atoms(
                    labels,
                    deterministic_labels(preds, cell),
                    {pred.pred_id for pred in preds},
                )
                jobs.append(
                    _RowJob(
                        table=table,
                        doc_id=doc_id,
                        rowid=rowid,
                        attribute=attr,
                        cell=cell,
                        predicates=preds,
                        labels=labels,
                        priority=job_priority(preds, labels, workload),
                        document=_doc_text(texts, doc_id),
                        entity_name=_entity_name(payload, table),
                        surfaces=_surfaces(payload, column),
                    )
                )

        jobs.sort(key=lambda item: item.priority, reverse=True)
        report.n_rows = len(jobs)

        def _fill(job: _RowJob) -> _RowJob:
            presence_needed = any(
                is_presence(pred) and atom_unresolved(job.labels, pred)
                for pred in job.predicates
            )
            member_needed = any(
                is_membership(pred) and atom_unresolved(job.labels, pred)
                for pred in job.predicates
            )
            job.labels = apply_row_operators(
                job.labels,
                job.predicates,
                attribute=job.attribute,
                cell=job.cell,
                document=job.document,
                entity_name=job.entity_name,
                surfaces=job.surfaces,
                caller=caller,
                run_presence=presence_needed,
                run_membership=member_needed,
            )
            return job

        filled: list[_RowJob] = []
        total = len(jobs)
        if caller is not None and workers > 1:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_fill, job) for job in jobs]
                for index, future in enumerate(as_completed(futures), 1):
                    filled.append(future.result())
                    if index == 1 or index % 50 == 0 or index == total:
                        spent = caller.ledger.spent if caller is not None else 0
                        print(f"sig populate {index}/{total} spent={spent}", flush=True)
        else:
            for index, job in enumerate(jobs, 1):
                filled.append(_fill(job))
                if caller is not None and (index == 1 or index % 50 == 0 or index == total):
                    print(f"sig populate {index}/{total} spent={caller.ledger.spent}", flush=True)

        for job in filled:
            presence_needed = any(is_presence(pred) for pred in job.predicates)
            member_needed = any(is_membership(pred) for pred in job.predicates)
            if presence_needed:
                report.n_presence_jobs += 1
            if member_needed:
                report.n_membership_jobs += 1
            job.labels, violations = _close_labels(job.labels, job.predicates)
            if violations:
                report.n_closed += 1
            report.n_conflicts += sum(1 for lab in job.labels.values() if lab.conflict)
            _write_row(conn, job.table, job.rowid, job.predicates, job.labels, existing[job.table])
            for pred in job.predicates:
                lab = job.labels.get(pred.pred_id)
                if lab is None or lab.sql_truth == "NULL":
                    if is_presence(pred):
                        report.n_presence_null += 1
                    elif is_membership(pred):
                        report.n_membership_null += 1
                elif lab.sql_truth == "TRUE":
                    if is_presence(pred):
                        report.n_presence_true += 1
                    elif is_membership(pred):
                        report.n_membership_true += 1
                elif is_membership(pred):
                    report.n_membership_false += 1

        if caller is not None:
            report.tokens_presence = sum(
                rec.tokens for rec in caller.ledger.records if rec.purpose == "sig_nonempty"
            )
            report.tokens_membership = sum(
                rec.tokens for rec in caller.ledger.records if rec.purpose == "sig_membership"
            )
        report.closed = True
        conn.commit()
    finally:
        conn.close()
    return report


def apply_live_signatures(
    sqlite_paths: Iterable[str | Path],
    statements: dict[str, str],
    documents: list[SourceDocument] | dict[str, str] | None = None,
    caller: BudgetedCaller | None = None,
    workload: Workload | None = None,
    *,
    workers: int = 1,
) -> list[AtomicPredicate]:
    from quwarts.core.signature import audit_workload, enumerate_predicates, statements_as_queries

    report = audit_workload(statements_as_queries(statements))
    predicates = live_predicates(enumerate_predicates(report.occurrences, report.signature_eligible))
    for path in sqlite_paths:
        populate_signatures(path, predicates, documents, caller, workload, workers=workers)
    return predicates
