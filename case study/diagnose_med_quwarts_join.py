#!/usr/bin/env python3
"""Diagnose Med join coverage in completed QuWARTS serving bundles.

This is a read-only, post-run diagnostic. It compares per-query evaluation
metrics, selected SQLite relation coverage, blank rates, and join-key overlap
without loading benchmark ground truth into synthesis.

Example:
  python3 "case study/diagnose_med_quwarts_join.py" \
    --run "25pct=case study/workloads/runs/20260815T055947Z" \
    --run "50pct=case study/workloads/runs/20260815T131909Z"
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_ID = "med_join20"
TABLE_COLUMNS = {
    "disease": (
        "id",
        "disease_name",
        "disease_type",
        "treatments",
        "diagnostic_methods",
        "prognosis",
        "pathogenesis",
    ),
    "drug": (
        "id",
        "disease_name",
        "pharmaceutical_form",
        "administration_route",
        "prescription_status",
        "manufacturer",
    ),
    "institution": (
        "id",
        "research_diseases",
        "institution_country",
        "institution_type",
        "research_fields",
        "funding_sources",
    ),
}
SOURCE_SUBDIRS = {
    "disease": "disease_small",
    "drug": "drug_small",
    "institution": "institutes_small",
}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _resolve_result_dir(raw: Path) -> Path:
    path = raw.expanduser()
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    candidates = (
        path,
        path / "results" / WORKLOAD_ID,
        path.parent if path.name == "serving_bundle" else path,
    )
    for candidate in candidates:
        if (
            (candidate / "evaluation.json").is_file()
            and (candidate / "serving_bundle" / "manifest.json").is_file()
        ):
            return candidate.resolve()
    raise FileNotFoundError(
        f"{path}: could not find evaluation.json and serving_bundle/manifest.json "
        f"for {WORKLOAD_ID}"
    )


def _parse_run(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--run must be LABEL=PATH")
    label, raw_path = value.split("=", 1)
    if not label.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("--run must be LABEL=PATH")
    try:
        result_dir = _resolve_result_dir(Path(raw_path.strip()))
    except (FileNotFoundError, OSError) as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return label.strip(), result_dir


def _tau(mapping: Any, target: float = 0.2) -> float | None:
    if not isinstance(mapping, dict):
        return None
    for key, value in mapping.items():
        try:
            if abs(float(key) - target) < 1e-12:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _fmt(value: Any, digits: int = 3) -> str:
    numeric = _number(value)
    return "—" if numeric is None else f"{numeric:.{digits}f}"


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    rows = connection.execute(
        f"PRAGMA table_info({_quote(table)})"
    ).fetchall()
    return {str(row[1]) for row in rows}


def _count(connection: sqlite3.Connection, sql: str) -> int:
    value = connection.execute(sql).fetchone()[0]
    return int(value or 0)


def _values(
    connection: sqlite3.Connection,
    table: str,
    column: str,
) -> list[Any]:
    return [
        row[0]
        for row in connection.execute(
            f"SELECT {_quote(column)} FROM {_quote(table)}"
        )
    ]


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def _tokens(value: Any) -> set[str]:
    whole = _normalized(value)
    if not whole:
        return set()
    return {part.strip() for part in whole.split("||") if part.strip()} | {whole}


def _join_coverage(
    connection: sqlite3.Connection,
    source_table: str,
    source_column: str,
) -> dict[str, int] | None:
    tables = _table_names(connection)
    if "disease" not in tables or source_table not in tables:
        return None
    disease_columns = _columns(connection, "disease")
    source_columns = _columns(connection, source_table)
    if "disease_name" not in disease_columns or source_column not in source_columns:
        return None
    disease_names = {
        _normalized(value)
        for value in _values(connection, "disease", "disease_name")
        if _normalized(value)
    }
    source_values = _values(connection, source_table, source_column)
    nonblank = [value for value in source_values if _normalized(value)]
    matched = [
        value
        for value in nonblank
        if _tokens(value) & disease_names
    ]
    return {
        "all_rows": len(source_values),
        "nonblank_rows": len(nonblank),
        "matched_rows": len(matched),
        "distinct_disease_names": len(disease_names),
    }


def _source_counts(source_root: Path) -> dict[str, int | None]:
    counts: dict[str, int | None] = {}
    for table, subdir in SOURCE_SUBDIRS.items():
        path = source_root / subdir
        counts[table] = (
            sum(1 for _ in path.rglob("*.txt")) if path.is_dir() else None
        )
    return counts


def _config_short(config_id: str) -> str:
    fields = {}
    for part in config_id.split("|"):
        if "=" in part:
            key, value = part.split("=", 1)
            fields[key] = value
    rendered = ",".join(
        f"{key}={fields[key]}"
        for key in ("er", "norm", "miss", "coerce")
        if key in fields
    )
    return rendered or config_id[:48]


def _database_report(
    bundle: Path,
    manifest: dict[str, Any],
    source_counts: dict[str, int | None],
) -> list[dict[str, Any]]:
    query_to_config = manifest.get("portfolio", {}).get("query_to_config", {})
    config_query_counts = Counter(query_to_config.values())
    reports = []
    for artifact in manifest.get("databases", []):
        config_id = str(artifact["config_id"])
        db_path = bundle / str(artifact["filename"])
        uri = f"file:{db_path.resolve()}?mode=ro&immutable=1"
        report: dict[str, Any] = {
            "config_id": config_id,
            "short_config": _config_short(config_id),
            "database": str(db_path),
            "queries": int(config_query_counts.get(config_id, 0)),
            "tables": {},
            "joins": {},
        }
        with sqlite3.connect(uri, uri=True) as connection:
            tables = _table_names(connection)
            for table, wanted_columns in TABLE_COLUMNS.items():
                if table not in tables:
                    report["tables"][table] = {"missing": True}
                    continue
                present = _columns(connection, table)
                row_count = _count(
                    connection, f"SELECT COUNT(*) FROM {_quote(table)}"
                )
                table_report: dict[str, Any] = {
                    "rows": row_count,
                    "source_documents": source_counts.get(table),
                    "columns": {},
                }
                if "id" in present:
                    table_report["distinct_ids"] = _count(
                        connection,
                        f"SELECT COUNT(DISTINCT {_quote('id')}) "
                        f"FROM {_quote(table)} "
                        f"WHERE TRIM(CAST({_quote('id')} AS TEXT)) <> ''",
                    )
                for column in wanted_columns:
                    if column not in present:
                        table_report["columns"][column] = None
                        continue
                    nonblank = _count(
                        connection,
                        "SELECT SUM(CASE WHEN "
                        f"{_quote(column)} IS NOT NULL AND "
                        f"TRIM(CAST({_quote(column)} AS TEXT)) <> '' "
                        f"THEN 1 ELSE 0 END) FROM {_quote(table)}",
                    )
                    table_report["columns"][column] = {
                        "nonblank": nonblank,
                        "rate": nonblank / row_count if row_count else 0.0,
                    }
                report["tables"][table] = table_report
            report["joins"]["drug_to_disease"] = _join_coverage(
                connection, "drug", "disease_name"
            )
            report["joins"]["institution_to_disease"] = _join_coverage(
                connection, "institution", "research_diseases"
            )
        reports.append(report)
    return reports


def _extraction_report(
    result_dir: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    synthesis_path = result_dir / "synthesis_manifest.json"
    if not synthesis_path.is_file():
        return {"status": "missing_synthesis_manifest"}
    synthesis = _read_json(synthesis_path)
    backend = synthesis.get("backend", {})
    if not isinstance(backend, dict):
        backend = {}
    bulk = backend.get("bulk_extraction", {})
    if not isinstance(bulk, dict):
        bulk = {}
    summary = bulk.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    coverage = summary.get("column_coverage", {})
    targets = summary.get("column_coverage_targets", {})
    routing = summary.get("document_routing", {})
    if not isinstance(coverage, dict):
        coverage = {}
    if not isinstance(targets, dict):
        targets = {}
    if not isinstance(routing, dict):
        routing = {}

    selected = set(
        manifest.get("portfolio", {}).get("selected_config_ids", [])
    )
    pilots = synthesis.get("progressive_search", {}).get("pilots", {})
    selected_pilot_rows = {}
    if isinstance(pilots, dict):
        for config_id, pilot in pilots.items():
            if config_id not in selected or not isinstance(pilot, dict):
                continue
            metadata = pilot.get("metadata", {})
            if isinstance(metadata, dict):
                selected_pilot_rows[config_id] = metadata.get(
                    "rows_by_relation", {}
                )

    output_support = synthesis.get("compiled_output_support", {})
    if not isinstance(output_support, dict):
        output_support = {}
    return {
        "status": "ok",
        "column_coverage": coverage,
        "column_coverage_targets": targets,
        "document_counts": routing.get("document_counts", {}),
        "document_routing": routing,
        "compiled_output_support": output_support,
        "selected_pilot_rows": selected_pilot_rows,
        "shared_extraction_key": backend.get("shared_extraction_key"),
    }


def _run_report(
    label: str,
    result_dir: Path,
    source_counts: dict[str, int | None],
) -> dict[str, Any]:
    evaluation = _read_json(result_dir / "evaluation.json")
    bundle = result_dir / "serving_bundle"
    manifest = _read_json(bundle / "manifest.json")
    return {
        "label": label,
        "result_dir": str(result_dir),
        "evaluation": evaluation,
        "manifest": manifest,
        "extraction": _extraction_report(result_dir, manifest),
        "databases": _database_report(bundle, manifest, source_counts),
    }


def _print_summary(reports: list[dict[str, Any]]) -> None:
    print("\nRUN SUMMARY")
    print(
        f"{'run':<12} {'structure':>10} {'f1@0.2':>9} {'main@0.2':>10} "
        f"{'spent':>12} {'budget':>12} {'unused':>12} {'dbs':>4}"
    )
    for report in reports:
        evaluation = report["evaluation"]
        print(
            f"{report['label']:<12} "
            f"{_fmt(evaluation.get('mean_structure_score')):>10} "
            f"{_fmt(_tau(evaluation.get('mean_cell_f1'))):>9} "
            f"{_fmt(_tau(evaluation.get('mean_query_score'))):>10} "
            f"{str(evaluation.get('construction_tokens', '—')):>12} "
            f"{str(evaluation.get('total_token_budget', '—')):>12} "
            f"{str(evaluation.get('unused_tokens', '—')):>12} "
            f"{len(report['databases']):>4}"
        )


def _print_databases(reports: list[dict[str, Any]]) -> None:
    for report in reports:
        print(f"\nRELATION COVERAGE — {report['label']}")
        for index, database in enumerate(report["databases"], 1):
            print(
                f"\n  DB {index}: queries={database['queries']} "
                f"{database['short_config']}"
            )
            for table, stats in database["tables"].items():
                if stats.get("missing"):
                    print(f"    {table}: MISSING TABLE")
                    continue
                source = stats.get("source_documents")
                coverage = (
                    f"{stats['rows'] / source:.1%}"
                    if source
                    else "unknown"
                )
                print(
                    f"    {table}: rows={stats['rows']} "
                    f"distinct_ids={stats.get('distinct_ids', '—')} "
                    f"source_docs={source if source is not None else '—'} "
                    f"rows/source={coverage}"
                )
                column_text = []
                for column, values in stats["columns"].items():
                    if values is None:
                        column_text.append(f"{column}=MISSING")
                    else:
                        column_text.append(
                            f"{column}={values['nonblank']}/{stats['rows']} "
                            f"({values['rate']:.0%})"
                        )
                print("      " + "; ".join(column_text))
            for join_name, stats in database["joins"].items():
                if stats is None:
                    print(f"    {join_name}: unavailable")
                    continue
                denominator = stats["nonblank_rows"]
                rate = (
                    stats["matched_rows"] / denominator if denominator else 0.0
                )
                print(
                    f"    {join_name}: matched={stats['matched_rows']}/"
                    f"{denominator} nonblank ({rate:.1%}); "
                    f"all_rows={stats['all_rows']}; "
                    f"disease_names={stats['distinct_disease_names']}"
                )


def _print_extraction(reports: list[dict[str, Any]]) -> None:
    for report in reports:
        extraction = report["extraction"]
        print(f"\nPRE-POPULATION EXTRACTION — {report['label']}")
        if extraction.get("status") != "ok":
            print("  synthesis_manifest.json unavailable")
            continue
        coverage = extraction.get("column_coverage", {})
        targets = extraction.get("column_coverage_targets", {})
        document_counts = extraction.get("document_counts", {})
        for table, wanted_columns in TABLE_COLUMNS.items():
            table_coverage = coverage.get(table, {})
            table_targets = targets.get(table, {})
            if not isinstance(table_coverage, dict):
                table_coverage = {}
            if not isinstance(table_targets, dict):
                table_targets = {}
            print(
                f"  {table}: routed_documents="
                f"{document_counts.get(table, '—')}"
            )
            rendered = []
            for column in wanted_columns:
                value = _number(table_coverage.get(column))
                target = _number(table_targets.get(column))
                if value is None:
                    rendered.append(f"{column}=missing")
                    continue
                target_text = (
                    f"/{target:.0%}" if target is not None else ""
                )
                marker = (
                    " BELOW_TARGET"
                    if target is not None and value + 1e-12 < target
                    else ""
                )
                rendered.append(
                    f"{column}={value:.0%}{target_text}{marker}"
                )
            print("    " + "; ".join(rendered))
        output_support = extraction.get("compiled_output_support", {})
        numeric_support = [
            (query_id, float(value))
            for query_id, value in output_support.items()
            if _number(value) is not None
        ]
        if numeric_support:
            mean_support = sum(value for _, value in numeric_support) / len(
                numeric_support
            )
            lowest = sorted(numeric_support, key=lambda item: item[1])[:5]
            print(
                f"  compiled_output_support: mean={mean_support:.1%}; "
                "lowest="
                + ", ".join(
                    f"{query_id}={value:.1%}"
                    for query_id, value in lowest
                )
            )


def _per_query(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    value = report["evaluation"].get("per_query", {})
    return value if isinstance(value, dict) else {}


def _print_query_comparison(reports: list[dict[str, Any]]) -> None:
    if len(reports) < 2:
        return
    baseline, current = reports[0], reports[-1]
    left, right = _per_query(baseline), _per_query(current)
    query_ids = sorted(
        set(left) | set(right),
        key=lambda value: int(value[1:]) if value[1:].isdigit() else value,
    )
    print(
        f"\nPER-QUERY CHANGE — {baseline['label']} → {current['label']}"
    )
    print(
        f"{'qid':>4} {'gold':>5} {'rows':>9} {'structure':>17} "
        f"{'f1@0.2':>17} {'main@0.2':>17}"
    )
    for query_id in query_ids:
        old, new = left.get(query_id, {}), right.get(query_id, {})
        old_rows = old.get("predicted_row_count")
        new_rows = new.get("predicted_row_count")
        gold = new.get("gold_row_count", old.get("gold_row_count"))
        old_structure = old.get("structure_score")
        new_structure = new.get("structure_score")
        old_f1 = _tau(old.get("cell_f1"))
        new_f1 = _tau(new.get("cell_f1"))
        old_main = _tau(old.get("query_score"))
        new_main = _tau(new.get("query_score"))
        print(
            f"{query_id:>4} {str(gold):>5} "
            f"{str(old_rows):>3}→{str(new_rows):<3} "
            f"{_fmt(old_structure):>7}→{_fmt(new_structure):<7} "
            f"{_fmt(old_f1):>7}→{_fmt(new_f1):<7} "
            f"{_fmt(old_main):>7}→{_fmt(new_main):<7}"
        )


def _write_output(path: Path, reports: Iterable[dict[str, Any]]) -> None:
    output = path.expanduser()
    if not output.is_absolute():
        output = (ROOT / output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    serializable = []
    for report in reports:
        serializable.append(
            {
                "label": report["label"],
                "result_dir": report["result_dir"],
                "summary": {
                    key: report["evaluation"].get(key)
                    for key in (
                        "mean_structure_score",
                        "mean_cell_f1",
                        "mean_query_score",
                        "construction_tokens",
                        "total_token_budget",
                        "unused_tokens",
                    )
                },
                "extraction": report["extraction"],
                "databases": report["databases"],
            }
        )
    output.write_text(
        json.dumps({"runs": serializable}, indent=2),
        encoding="utf-8",
    )
    print(f"\nJSON report: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        metavar="LABEL=PATH",
        help=(
            "Completed QuWARTS run root or med_join20 result directory. "
            "Repeat to compare runs; first is the baseline."
        ),
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=ROOT / "source_data" / "Healthcare",
        help="Healthcare source document root used only for document counts.",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    parsed_runs = [_parse_run(value) for value in args.run]
    labels = [label for label, _ in parsed_runs]
    if len(labels) != len(set(labels)):
        raise SystemExit("--run labels must be unique")
    source_root = args.source_root.expanduser()
    if not source_root.is_absolute():
        source_root = (ROOT / source_root).resolve()
    source_counts = _source_counts(source_root)
    reports = [
        _run_report(label, result_dir, source_counts)
        for label, result_dir in parsed_runs
    ]
    _print_summary(reports)
    _print_extraction(reports)
    _print_databases(reports)
    _print_query_comparison(reports)
    if args.output is not None:
        _write_output(args.output, reports)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
