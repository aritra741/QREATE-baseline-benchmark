"""Art repair-agent report. Gold-schema extract is not in the main table."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def mean_per_query_product(report: dict[str, Any]) -> float:
    """mean_q [structure_F2(q) × cell_F1@0.20(q)]. Not a product of means."""

    products: list[float] = []
    for row in report.get("per_query") or []:
        structure = float(row.get("structure_f2") or 0.0)
        cell = row.get("cell_f1_20")
        if cell is None:
            cell = row.get("cell_f1_05") or 0.0
        products.append(structure * float(cell or 0.0))
    return _mean(products)


def mean_cell_f1_20(report: dict[str, Any]) -> float:
    values: list[float] = []
    for row in report.get("per_query") or []:
        cell = row.get("cell_f1_20")
        if cell is None:
            cell = row.get("cell_f1_05")
        if cell is None:
            continue
        values.append(float(cell))
    if values:
        return _mean(values)
    return float(report.get("mean_cell_f1_20") or report.get("mean_cell_f1_05") or 0.0)


def empty_query_count(report: dict[str, Any]) -> int:
    return sum(1 for row in report.get("per_query") or [] if int(row.get("pred_rows") or 0) == 0)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.is_file() else {}


def row_from_report(
    label: str,
    report: dict[str, Any],
    *,
    tokens: int | None = None,
    detectors_before: dict[str, Any] | None = None,
    detectors_after: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "system": label,
        "mean_structure_f2": float(report.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_at_0.20": mean_cell_f1_20(report),
        "mean_per_query_product": mean_per_query_product(report),
        "tokens_spent": tokens if tokens is not None else report.get("tokens_spent"),
        "empty_query_count": empty_query_count(report),
        "detectors_before": detectors_before,
        "detectors_after": detectors_after,
    }


def build_table(args: argparse.Namespace) -> dict[str, Any]:
    compiler = load_json(args.compiler_report)
    docetl = load_json(args.docetl_report)
    repair = load_json(args.repair_report) if args.repair_report else {}
    manifest = load_json(args.manifest) if args.manifest else {}
    quality = manifest.get("quality") or {}
    repair_quality = (quality.get("repair") or repair.get("repair") or {})
    before = repair_quality.get("before")
    after = repair_quality.get("after")
    compiler_row = row_from_report(
        "QuWARTS compiler",
        compiler,
        tokens=compiler.get("tokens_spent"),
        detectors_before=before,
        detectors_after=None if after else before,
    )
    rows = [compiler_row]
    if repair.get("per_query") or repair.get("mean_structure_f2") is not None:
        rows.append(
            row_from_report(
                "QuWARTS repair agent",
                repair,
                tokens=repair.get("tokens_spent") or repair_quality.get("tokens_spent"),
                detectors_before=before,
                detectors_after=after,
            )
        )
    if docetl:
        rows.append(
            row_from_report(
                "DocETL",
                docetl,
                tokens=int((load_json(args.docetl_summary) or {}).get("total_tokens") or 0) or None,
            )
        )
    return {
        "dataset": "Art",
        "metric": "mean_q[structure_F2(q) × cell_F1@0.20(q)]",
        "excluded": ["gold-schema extract", "official accuracy", "product of corpus-level averages"],
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--compiler-report",
        type=Path,
        default=ROOT / "results" / "quwarts_art_compiler80" / "report.json",
    )
    parser.add_argument(
        "--docetl-report",
        type=Path,
        default=ROOT / "results" / "docetl_art_case80" / "report.json",
    )
    parser.add_argument(
        "--docetl-summary",
        type=Path,
        default=ROOT / "results" / "docetl_art_case80" / "summary.json",
    )
    parser.add_argument(
        "--repair-report",
        type=Path,
        default=ROOT / "results" / "quwarts_art_repair80" / "report.json",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "results" / "quwarts_art_compiler80" / "artifacts" / "runs" / "manifest.json",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    table = build_table(args)
    text = json.dumps(table, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
