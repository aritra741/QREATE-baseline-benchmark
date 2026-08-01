"""Static guardrails for the synthesis/evaluation data firewall."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


WDIRS_ROOT = Path(__file__).resolve().parent
SYNTHESIS_MODULES = (
    WDIRS_ROOT / "diagnostics" / "run_offline_spp.py",
    WDIRS_ROOT / "spp" / "system.py",
    WDIRS_ROOT / "spp" / "workload_intent.py",
    WDIRS_ROOT / "spp" / "schema_design.py",
    WDIRS_ROOT / "spp" / "wdirs_backend.py",
    WDIRS_ROOT / "spp" / "query_plan_compiler.py",
    WDIRS_ROOT / "spp" / "sql_validator.py",
    WDIRS_ROOT / "spp" / "nl2sql.py",
    WDIRS_ROOT / "spp" / "serving.py",
)
FORBIDDEN_IMPORT_PREFIXES = (
    "evaluation",
    "diagnostics.run_config_grid",
    "spp.aggregation_metrics",
    "spp.evaluation",
    "spp.oracle_evaluation",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize("path", SYNTHESIS_MODULES, ids=lambda path: path.name)
def test_synthesis_modules_do_not_import_evaluation_or_ground_truth(
    path: Path,
) -> None:
    imports = _imports(path)
    violations = sorted(
        module
        for module in imports
        if any(
            module == prefix or module.startswith(f"{prefix}.")
            for prefix in FORBIDDEN_IMPORT_PREFIXES
        )
    )
    assert violations == []


def test_synthesis_entrypoint_does_not_name_reference_answer_artifacts() -> None:
    source = SYNTHESIS_MODULES[0].read_text(encoding="utf-8").lower()
    assert "query_manifest.json" not in source
    assert "evaluation.json" not in source
    assert "load_ground_truth" not in source
