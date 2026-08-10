#!/usr/bin/env python3
"""Harvest four Player contrast workloads into a validated website bundle.

Strict mode is the HPC/publishing path. It requires eight evaluation artifacts
(two systems × four workloads), matching manifests, and all 80 query records.
The output is replaced atomically only after the complete bundle validates.
``--allow-summary-fallback`` is intended solely for local UI builds.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CASE = Path(__file__).resolve().parent
WORKLOADS = (
    "player_join20",
    "player_groupby20",
    "player_multiagg20",
    "player_filterjoin20",
)
EXPECTED_QUERY_COUNT = 20


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _validate_numeric_tree(value: Any, label: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _validate_numeric_tree(child, f"{label}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_numeric_tree(child, f"{label}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{label} must be finite")


def _score_block(evaluation: dict[str, Any]) -> dict[str, Any]:
    return {
        key: evaluation.get(key)
        for key in (
            "mean_official_accuracy",
            "mean_structure_score",
            "mean_structure_f1_score",
            "mean_cell_f1",
            "mean_query_score",
            "aggregation_query_count",
        )
    }


def _load_manifest(workload_id: str) -> list[dict[str, str]]:
    directory = CASE / "workloads" / workload_id
    sql_path = directory / "query_manifest.json"
    nl_path = directory / "query_manifest_nl.json"
    sql_rows, nl_rows = _read_json(sql_path), _read_json(nl_path)
    if not isinstance(sql_rows, list) or not isinstance(nl_rows, list):
        raise ValueError(f"{workload_id}: manifests must be arrays")
    if len(sql_rows) != EXPECTED_QUERY_COUNT or len(nl_rows) != EXPECTED_QUERY_COUNT:
        raise ValueError(f"{workload_id}: both manifests must contain 20 queries")
    sql = {row.get("query_id"): row.get("sql") for row in sql_rows}
    nl = {row.get("query_id"): row.get("text") for row in nl_rows}
    if None in sql or None in nl or len(sql) != EXPECTED_QUERY_COUNT:
        raise ValueError(f"{workload_id}: query IDs must be present and unique")
    if set(sql) != set(nl):
        raise ValueError(f"{workload_id}: SQL and natural-language IDs differ")
    if any(not isinstance(value, str) or not value.strip() for value in sql.values()):
        raise ValueError(f"{workload_id}: every query must include SQL")
    return [
        {"query_id": row["query_id"], "sql": row["sql"], "text": nl[row["query_id"]]}
        for row in sql_rows
    ]


def _actual_tokens(result_dir: Path) -> int | None:
    for name in (
        "budget_ledger.json",
        "token_ledger.json",
        "run_manifest.json",
        "synthesis_manifest.json",
    ):
        path = result_dir / name
        if not path.is_file():
            continue
        payload = _read_json(path)
        for key in ("actual_spent", "actual_tokens", "total_tokens", "tokens_spent"):
            if payload.get(key) is not None:
                return int(payload[key])
        tokens = payload.get("tokens")
        if isinstance(tokens, dict):
            for key in ("actual_spent", "actual_tokens", "total"):
                if tokens.get(key) is not None:
                    return int(tokens[key])
        if isinstance(tokens, (int, float)):
            return int(tokens)
    return None


def _find_evaluation(root: Path, workload_id: str) -> Path | None:
    candidates = (
        root / "results" / workload_id / "evaluation.json",
        root / workload_id / "evaluation.json",
        root / workload_id / "results" / "evaluation.json",
    )
    for path in candidates:
        if path.is_file():
            return path
    matches = sorted(root.rglob(f"*/{workload_id}/evaluation.json"))
    return matches[0] if matches else None


def _normalise_per_query(value: Any, workload_id: str, system: str) -> dict[str, Any]:
    if isinstance(value, dict):
        records = value
    elif isinstance(value, list):
        records = {}
        for row in value:
            if not isinstance(row, dict) or not row.get("query_id"):
                raise ValueError(f"{workload_id}/{system}: malformed per-query list")
            query_id = row["query_id"]
            if query_id in records:
                raise ValueError(f"{workload_id}/{system}: duplicate query ID {query_id}")
            records[query_id] = {key: item for key, item in row.items() if key != "query_id"}
    else:
        raise ValueError(f"{workload_id}/{system}: per_query must be an object or list")
    if len(records) != EXPECTED_QUERY_COUNT:
        raise ValueError(f"{workload_id}/{system}: expected 20 per-query records")
    for query_id, record in records.items():
        if not isinstance(query_id, str) or not isinstance(record, dict):
            raise ValueError(f"{workload_id}/{system}: malformed per-query record")
        _validate_numeric_tree(record, f"{workload_id}/{system}/{query_id}")
    return records


def _validate_system(
    entry: dict[str, Any], workload_id: str, system: str, detailed: bool
) -> None:
    scores = entry.get("scores")
    if not isinstance(scores, dict):
        raise ValueError(f"{workload_id}/{system}: missing aggregate scores")
    for key in ("mean_official_accuracy", "mean_structure_score"):
        _finite(scores.get(key), f"{workload_id}/{system}/{key}")
    for key in ("mean_cell_f1", "mean_query_score"):
        values = scores.get(key)
        if detailed and not isinstance(values, dict):
            raise ValueError(f"{workload_id}/{system}: missing {key}")
        if isinstance(values, dict):
            for level, value in values.items():
                _finite(value, f"{workload_id}/{system}/{key}.{level}")
    if entry.get("tokens_actual") is not None:
        if _finite(entry["tokens_actual"], f"{workload_id}/{system}/tokens") < 0:
            raise ValueError(f"{workload_id}/{system}: tokens cannot be negative")
    if detailed and len(entry.get("per_query") or {}) != EXPECTED_QUERY_COUNT:
        raise ValueError(f"{workload_id}/{system}: expected 20 per-query records")


def _system_entry(root: Path | None, workload_id: str, system: str) -> dict[str, Any]:
    if root is None:
        return {"status": "missing_root"}
    path = _find_evaluation(root, workload_id)
    if path is None:
        return {"status": "missing_evaluation", "searched_under": str(root)}
    evaluation = _read_json(path)
    entry = {
        "status": "ok",
        "evaluation_json": str(path),
        "result_dir": str(path.parent),
        "scores": _score_block(evaluation),
        "tokens_actual": _actual_tokens(path.parent),
        "per_query": _normalise_per_query(
            evaluation.get("per_query"), workload_id, system
        ),
    }
    _validate_system(entry, workload_id, system, detailed=True)
    return entry


def _fallback_entry(row: dict[str, Any], system: str) -> dict[str, Any]:
    source = row[system]
    return {
        "status": "summary_fallback",
        "scores": {
            key: source.get(key)
            for key in (
                "mean_official_accuracy",
                "mean_structure_score",
                "mean_structure_f1_score",
                "mean_cell_f1",
                "mean_query_score",
            )
            if source.get(key) is not None
        },
        "tokens_actual": source.get("token_budget", source.get("tokens")),
        "evaluation_json": source.get("evaluation_json"),
        "per_query": None,
    }


def _query_score(record: dict[str, Any] | None) -> float | None:
    if not record:
        return None
    scores = record.get("query_score") or (record.get("rank") or {}).get("query_score")
    if not isinstance(scores, dict) or scores.get("0.2") is None:
        return None
    return _finite(scores["0.2"], "query_score.0.2")


def _structure_score(record: dict[str, Any] | None) -> float | None:
    if not record:
        return None
    value = record.get("structure_score")
    if value is None:
        value = (record.get("rank") or {}).get("structure_score")
    return None if value is None else _finite(value, "structure_score")


def _evidence(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if not record:
        return None
    return {
        key: record.get(key)
        for key in (
            "gold_row_count",
            "predicted_row_count",
            "schema",
            "structure",
            "value",
            "grouping",
        )
    }


def _explain_query(q: dict[str, Any] | None, d: dict[str, Any] | None) -> str:
    q_score, d_score = _query_score(q), _query_score(d)
    if q_score is None or d_score is None:
        return "Per-query system metrics are unavailable in this local aggregate fallback."
    winner = "QuWARTS" if q_score > d_score else "DocETL" if d_score > q_score else "Neither system"
    difference = abs(q_score - d_score)
    explanation = (
        f"{winner} had the higher 20% query score"
        f"{f' by {difference:.3f}' if difference else ''} "
        f"(QuWARTS {q_score:.3f}; DocETL {d_score:.3f})."
    )
    q_structure, d_structure = _structure_score(q), _structure_score(d)
    if q_structure is not None and d_structure is not None:
        explanation += (
            f" Structure scores were {q_structure:.3f} and {d_structure:.3f}, respectively."
        )
    return explanation


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--quwarts-root",
        type=Path,
        default=CASE / "workloads" / "runs" / "quwarts_forced_taxonomy_25pct_20260810",
    )
    parser.add_argument(
        "--groupby-root",
        type=Path,
        default=CASE / "workloads" / "runs" / "quwarts_forced_taxonomy_25pct_20260809",
    )
    parser.add_argument("--docetl-root", type=Path, default=None)
    parser.add_argument(
        "--summary",
        type=Path,
        default=CASE / "workloads" / "contrast_results_summary.json",
    )
    parser.add_argument(
        "--allow-summary-fallback",
        action="store_true",
        help="Local-only: permit audited aggregates without detailed evaluations.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "player-agg20-case-site" / "src" / "contrast-data.json",
    )
    args = parser.parse_args()

    summary = _read_json(args.summary) if args.summary.is_file() else {"workloads": {}}
    workloads: dict[str, Any] = {}
    for workload_id in WORKLOADS:
        manifest = _load_manifest(workload_id)
        quwarts_root = args.groupby_root if workload_id == "player_groupby20" else args.quwarts_root
        quwarts = _system_entry(quwarts_root, workload_id, "quwarts")
        docetl = _system_entry(args.docetl_root, workload_id, "docetl")
        fallback = summary.get("workloads", {}).get(workload_id, {})
        for system, entry in (("quwarts", quwarts), ("docetl", docetl)):
            if entry.get("status") != "ok":
                if not args.allow_summary_fallback or system not in fallback:
                    raise ValueError(f"{workload_id}/{system}: evaluation.json is required")
                if system == "quwarts":
                    quwarts = _fallback_entry(fallback, system)
                else:
                    docetl = _fallback_entry(fallback, system)
        _validate_system(quwarts, workload_id, "quwarts", not args.allow_summary_fallback)
        _validate_system(docetl, workload_id, "docetl", not args.allow_summary_fallback)
        q_records, d_records = quwarts.get("per_query") or {}, docetl.get("per_query") or {}
        queries = []
        for row in manifest:
            query_id = row["query_id"]
            q_record, d_record = q_records.get(query_id), d_records.get(query_id)
            if not args.allow_summary_fallback and (q_record is None or d_record is None):
                raise ValueError(f"{workload_id}/{query_id}: missing system record")
            queries.append(
                {
                    **row,
                    "metrics": {"quwarts": q_record, "docetl": d_record},
                    "evidence": {
                        "quwarts": _evidence(q_record),
                        "docetl": _evidence(d_record),
                    },
                    "explanation": _explain_query(q_record, d_record),
                }
            )
        q_mean = (quwarts["scores"].get("mean_query_score") or {}).get("0.2")
        d_mean = (docetl["scores"].get("mean_query_score") or {}).get("0.2")
        explanation = (
            f"At 20% tolerance, QuWARTS' mean query score is {q_mean:.3f} "
            f"and DocETL's is {d_mean:.3f}."
            if q_mean is not None and d_mean is not None
            else "Only the available aggregate metrics are shown."
        )
        workloads[workload_id] = {
            "focus": fallback.get("focus"),
            "manifest": {
                "sql": str(CASE / "workloads" / workload_id / "query_manifest.json"),
                "natural_language": str(
                    CASE / "workloads" / workload_id / "query_manifest_nl.json"
                ),
            },
            "quwarts": quwarts,
            "docetl": docetl,
            "prior_quwarts": fallback.get("prior_quwarts"),
            "explanation": explanation,
            "queries": queries,
        }

    bundle = {
        "title": "Player contrast workloads",
        "subtitle": "QuWARTS vs DocETL across join, groupby, multiagg, and filterjoin",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "primary_error_level": "0.2",
        "error_levels": ["0.01", "0.05", "0.2"],
        "score_note": summary.get(
            "score_note", "Main ranking score is query_score = structure × cell_f1."
        ),
        "mode": "fallback" if args.allow_summary_fallback else "strict",
        "query_count": sum(len(row["queries"]) for row in workloads.values()),
        "per_query_metrics_complete": all(
            row["quwarts"]["status"] == "ok" and row["docetl"]["status"] == "ok"
            for row in workloads.values()
        ),
        "workloads": workloads,
        "headline": summary.get("headline"),
    }
    ids = {
        f"{workload_id}:{query['query_id']}"
        for workload_id, row in workloads.items()
        for query in row["queries"]
    }
    if bundle["query_count"] != 80 or len(ids) != 80:
        raise ValueError("site bundle must contain exactly 80 unique workload queries")
    _validate_numeric_tree(bundle, "bundle")
    _atomic_write(args.output, bundle)
    print(f"wrote {args.output} ({bundle['mode']}, {bundle['query_count']} queries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
