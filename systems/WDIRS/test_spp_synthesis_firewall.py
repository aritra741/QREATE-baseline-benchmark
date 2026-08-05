"""Static guardrails for the synthesis/evaluation data firewall."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest


WDIRS_ROOT = Path(__file__).resolve().parent
SYNTHESIS_MODULES = (
    WDIRS_ROOT / "diagnostics" / "run_offline_spp.py",
    WDIRS_ROOT / "diagnostics" / "run_contract_spp.py",
    WDIRS_ROOT / "spp" / "system.py",
    WDIRS_ROOT / "spp" / "workload_contract.py",
    WDIRS_ROOT / "spp" / "contract_extractor.py",
    WDIRS_ROOT / "spp" / "cell_verifier.py",
    WDIRS_ROOT / "spp" / "contract_validation.py",
    WDIRS_ROOT / "spp" / "contract_backend.py",
    WDIRS_ROOT / "spp" / "query_quality.py",
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
    for path in SYNTHESIS_MODULES[:2]:
        source = path.read_text(encoding="utf-8").lower()
        assert "query_manifest.json" not in source
        assert "evaluation.json" not in source
        assert "load_ground_truth" not in source


def test_contract_runtime_loader_rejects_reference_channels(
    tmp_path: Path,
) -> None:
    from diagnostics.run_contract_spp import _load_documents, _load_queries

    source = tmp_path / "source"
    (source / "entity").mkdir(parents=True)
    (source / "entity" / "one.txt").write_text(
        "An evidence-backed entity.", encoding="utf-8"
    )
    workload = tmp_path / "workload.json"
    workload.write_text(
        '{"queries":[{"query_id":"q0","text":"List the entities."}]}',
        encoding="utf-8",
    )
    documents = _load_documents(source)
    assert len(documents) == 1
    assert documents[0].document_id.startswith("doc-")
    assert "/" not in documents[0].document_id
    assert documents[0].metadata == {
        "content_sha256": hashlib.sha256(
            b"An evidence-backed entity."
        ).hexdigest()
    }
    assert _load_queries(workload)[0]["text"] == "List the entities."

    forbidden = tmp_path / "Data"
    forbidden.mkdir()
    with pytest.raises(ValueError, match="forbidden"):
        _load_documents(forbidden)

    workload.write_text(
        '{"queries":[{"query_id":"q0","text":"List them.",'
        '"sql":"SELECT secret FROM answers"}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="forbidden fields"):
        _load_queries(workload)


def test_contract_entity_vocabulary_is_supported_by_content() -> None:
    from diagnostics.run_contract_spp import (
        _content_supported_entity_vocabulary,
    )
    from spp.native_backend import SourceDocument
    from spp.spec import QueryRequirement
    from spp.workload_intent import WorkloadIntent

    documents = [
        SourceDocument(
            "opaque-1",
            "Roadster vehicle with four wheels.",
            {},
        ),
        SourceDocument(
            "opaque-2",
            "Harbor place with a large population.",
            {},
        ),
    ]
    intent = WorkloadIntent(
        requirements=(
            QueryRequirement(
                "q0",
                "List vehicle wheel counts.",
                entities=("vehicle", "accolade"),
                attributes=("wheel_count",),
            ),
            QueryRequirement(
                "q1",
                "List place populations.",
                entities=("place",),
                attributes=("population",),
            ),
        ),
        entity_frequency={},
        attribute_frequency={},
        operator_frequency={},
    )

    assert _content_supported_entity_vocabulary(documents, intent) == (
        "place",
        "vehicle",
    )


def test_contract_entrypoint_does_not_derive_schema_from_paths() -> None:
    path = WDIRS_ROOT / "diagnostics" / "run_contract_spp.py"
    source = path.read_text(encoding="utf-8")
    assert "infer_source_entity_vocabulary" not in source
    assert '"source_file"' not in source
    assert "relative_to(root)" not in source
