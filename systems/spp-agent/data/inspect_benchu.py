#!/usr/bin/env python3
"""Inspect Bench-U directory layout and save a JSON report."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

SPP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SPP_ROOT))

from utils.config import load_config


def _first_records(path: Path, n: int = 2) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        import pandas as pd

        df = pd.read_csv(path, nrows=n)
        return df.to_dict(orient="records")
    if suffix == ".txt":
        text = path.read_text(encoding="utf-8", errors="replace")
        return [{"doc_id": path.stem, "text_preview": text[:500]}]
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data[:n]
        return [data]
    return []


def _inspect_dir(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path), "files": []}

    files: list[dict[str, Any]] = []
    for item in sorted(path.rglob("*")):
        if item.is_file():
            files.append(
                {
                    "relative_path": str(item.relative_to(path)),
                    "extension": item.suffix,
                    "size_bytes": item.stat().st_size,
                }
            )
    return {"exists": True, "path": str(path), "file_count": len(files), "files": files}


def _inspect_corpus(benchu_root: Path, dataset: str) -> dict[str, Any]:
    data_dir = benchu_root / "Data" / dataset
    synthetic_dir = benchu_root / "source_data" / f"Synthetic{dataset}"

    corpus_sources: list[dict[str, Any]] = []
    for label, root in [("Data", data_dir), ("SyntheticText", synthetic_dir)]:
        if not root.exists():
            continue
        text_files = sorted(root.rglob("*.txt"))
        csv_files = sorted(root.rglob("*.csv"))
        sample_files = text_files or csv_files
        samples = []
        for fp in sample_files[:2]:
            samples.append({"file": str(fp.relative_to(benchu_root)), "records": _first_records(fp)})
        corpus_sources.append(
            {
                "label": label,
                "path": str(root),
                "txt_count": len(text_files),
                "csv_count": len(csv_files),
                "first_two_records": samples,
            }
        )
    return {"sources": corpus_sources}


def _inspect_queries(benchu_root: Path, dataset: str) -> dict[str, Any]:
    query_dir = benchu_root / "Query" / dataset
    if not query_dir.exists():
        return {"exists": False, "path": str(query_dir)}

    sql_files = sorted(query_dir.rglob("*.sql"))
    structure: list[dict[str, Any]] = []
    for sql_file in sql_files[:5]:
        content = sql_file.read_text(encoding="utf-8")
        first_lines = content.splitlines()[:5]
        structure.append(
            {
                "file": str(sql_file.relative_to(benchu_root)),
                "first_lines": first_lines,
                "query_count_estimate": content.count("-- Query"),
            }
        )
    return {
        "exists": True,
        "path": str(query_dir),
        "sql_file_count": len(sql_files),
        "sample_files": structure,
        "attribute_json_files": [str(p.relative_to(benchu_root)) for p in sorted(query_dir.glob("*_attributes.json"))],
    }


def _inspect_ground_truth(benchu_root: Path, dataset: str) -> dict[str, Any]:
    gt_primary = benchu_root / "GroundTruth" / dataset
    gt_fallback = benchu_root / "Query" / dataset

    resolved = gt_primary if gt_primary.exists() else gt_fallback
    if not resolved.exists():
        return {
            "exists": False,
            "primary_path": str(gt_primary),
            "fallback_path": str(gt_fallback),
            "tables": {},
        }

    import pandas as pd

    tables: dict[str, Any] = {}
    for csv_path in sorted(resolved.glob("*.csv")):
        df = pd.read_csv(csv_path, nrows=0)
        full_df = pd.read_csv(csv_path)
        tables[csv_path.stem] = {
            "path": str(csv_path.relative_to(benchu_root)),
            "columns": list(df.columns),
            "dtypes": {col: str(full_df[col].dtype) for col in full_df.columns},
            "row_count": len(full_df),
        }

    return {
        "exists": True,
        "resolved_path": str(resolved),
        "used_fallback": not gt_primary.exists(),
        "note": (
            "GroundTruth/Player/ not found; using Query/Player/*.csv as ground-truth tables."
            if not gt_primary.exists()
            else None
        ),
        "tables": tables,
    }


def _inspect_evaluation(benchu_root: Path) -> dict[str, Any]:
    eval_dir = benchu_root / "evaluation"
    if not eval_dir.exists():
        return {"exists": False, "path": str(eval_dir)}

    py_files = sorted(eval_dir.glob("*.py"))
    functions: dict[str, list[str]] = {}
    for py_file in py_files:
        spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
            funcs = [name for name in dir(module) if callable(getattr(module, name, None)) and not name.startswith("_")]
            functions[py_file.name] = sorted(funcs)[:20]
        except Exception as exc:
            functions[py_file.name] = [f"<import error: {exc}>"]

    return {
        "exists": True,
        "path": str(eval_dir),
        "python_modules": [p.name for p in py_files],
        "public_functions_sample": functions,
        "entry_points": ["evaluation.run_eval", "evaluation.gt_runner.GtRunner", "evaluation.metrics.MetricCalculator"],
    }


def inspect_dataset(dataset: str = "Player") -> dict[str, Any]:
    cfg = load_config()
    benchu_root = Path(cfg["paths"]["benchu_root"])

    report = {
        "dataset": dataset,
        "benchu_root": str(benchu_root),
        "data_player": _inspect_dir(benchu_root / "Data" / dataset),
        "corpus": _inspect_corpus(benchu_root, dataset),
        "query_player": _inspect_queries(benchu_root, dataset),
        "ground_truth_player": _inspect_ground_truth(benchu_root, dataset),
        "evaluation": _inspect_evaluation(benchu_root),
    }
    return report


def main() -> None:
    dataset = sys.argv[1] if len(sys.argv) > 1 else "Player"
    report = inspect_dataset(dataset)

    cfg = load_config()
    out_path = Path(cfg["paths"]["results_dir"]) / f"benchu_inspection_{dataset}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nSaved report to {out_path}")


if __name__ == "__main__":
    main()
