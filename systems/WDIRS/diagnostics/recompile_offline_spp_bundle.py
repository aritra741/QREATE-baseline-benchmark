"""Recompile a sealed SPP bundle without repeating data population or LLM calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Mapping

WDIRS_ROOT = Path(__file__).resolve().parents[1]
if str(WDIRS_ROOT) not in sys.path:
    sys.path.insert(0, str(WDIRS_ROOT))

from spp.query_plan_compiler import compile_query_plan  # noqa: E402
from spp.serving import OfflineQueryServer, _validate_readonly_sql  # noqa: E402
from spp.spec import (  # noqa: E402
    AttributeRef,
    PopulationConfig,
    PreprocessingPolicy,
    RelationSpec,
    SchemaDesign,
    SynthesisConfig,
)
from spp.workload_intent import (  # noqa: E402
    _normalize_plan_with_schema,
    _query_plan,
    _repair_plan_aggregate,
    schema_vocabulary_from_sql,
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _schema_design(payload: Mapping[str, object]) -> SchemaDesign:
    relations = tuple(
        RelationSpec(
            name=str(relation["name"]),
            attributes=tuple(relation.get("attributes", ())),
            primary_key=relation.get("primary_key"),
            foreign_keys=tuple(
                tuple(foreign_key)
                for foreign_key in relation.get("foreign_keys", ())
            ),
            semantic_types=tuple(
                tuple(semantic_type)
                for semantic_type in relation.get("semantic_types", ())
            ),
        )
        for relation in payload.get("relations", ())
    )
    return SchemaDesign(
        pattern=str(payload["pattern"]),
        relations=relations,
        covered_query_ids=tuple(payload.get("covered_query_ids", ())),
        description=str(payload.get("description", "")),
    )


def _configs(synthesis: Mapping[str, object]) -> Dict[str, SynthesisConfig]:
    candidate_space = synthesis["candidate_space"]
    schemas = {
        schema_id: _schema_design(payload)
        for schema_id, payload in candidate_space["schemas"].items()
    }
    population_configs = candidate_space["population_configs"]
    preprocessing_policies = candidate_space["preprocessing_policies"]
    return {
        row["config_id"]: SynthesisConfig(
            schema=schemas[row["schema_id"]],
            population=PopulationConfig(
                **population_configs[row["population_config_id"]]
            ),
            preprocessing=PreprocessingPolicy(
                **preprocessing_policies[row["preprocessing_policy_id"]]
            ),
        )
        for row in candidate_space["configs"]
    }


def _compile(
    synthesis: dict,
    serving: Mapping[str, object],
    bundle_dir: Path,
    schema_workload: Path,
) -> list[dict]:
    schema_queries = [
        statement.strip()
        for statement in schema_workload.read_text().split(";")
        if statement.strip() and "select" in statement.lower()
    ]
    vocabulary = schema_vocabulary_from_sql(schema_queries)
    configs = _configs(synthesis)
    routes = serving["portfolio"]["query_to_config"]
    database_paths = {
        artifact["config_id"]: bundle_dir / artifact["filename"]
        for artifact in serving["databases"]
    }
    compiled = []
    for requirement in synthesis["workload_intent"]["requirements"]:
        query_id = requirement["query_id"]
        context = tuple(
            AttributeRef(entity, attribute)
            for entity, attribute in requirement.get("attribute_bindings", ())
        )
        plan = _query_plan(
            requirement.get("plan"),
            vocabulary.entities,
            vocabulary.attributes,
        )
        plan = _repair_plan_aggregate(
            plan,
            requirement["text"],
            context_references=context,
            attribute_vocabulary=vocabulary.attributes,
        )
        plan = _normalize_plan_with_schema(
            plan,
            requirement["text"],
            attribute_vocabulary=vocabulary.attributes,
            join_vocabulary=vocabulary.joins,
            context_references=context,
        )
        if plan is None:
            raise ValueError(f"query {query_id!r} has no compilable plan")
        config_id = routes[query_id]
        sql = compile_query_plan(plan, configs[config_id])
        _validate_readonly_sql(sql)
        uri = f"file:{database_paths[config_id].resolve()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall()
        requirement["plan"] = asdict(plan)
        compiled.append(
            {
                "query_id": query_id,
                "natural_language_query": requirement["text"],
                "config_id": config_id,
                "sql": sql,
                "sql_sha256": _sha256_bytes(sql.encode("utf-8")),
            }
        )
    return compiled


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Apply the current deterministic intent repairs and SQL compiler "
            "to an existing sealed run without LLM calls or repopulation."
        )
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--schema-workload", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    source = args.run_dir.expanduser().resolve()
    source_bundle = source / "serving_bundle"
    OfflineQueryServer(source_bundle)
    output = args.output_dir.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    output.mkdir(parents=True)
    destination_bundle = output / "serving_bundle"
    shutil.copytree(source_bundle, destination_bundle)
    for optional_name in ("run_manifest.json",):
        source_path = source / optional_name
        if source_path.exists():
            shutil.copy2(source_path, output / optional_name)

    source_synthesis = source / "synthesis_manifest.json"
    synthesis = json.loads(source_synthesis.read_text())
    serving_path = destination_bundle / "manifest.json"
    serving = json.loads(serving_path.read_text())
    compiled = _compile(
        synthesis,
        serving,
        destination_bundle,
        args.schema_workload.expanduser().resolve(),
    )
    synthesis["compiled_queries"] = compiled
    synthesis["compiled_output_support"] = {}
    synthesis["deterministic_recompilation"] = {
        "source_synthesis_manifest_sha256": _sha256_file(source_synthesis),
        "source_serving_manifest_sha256": _sha256_file(
            source_bundle / "manifest.json"
        ),
        "schema_workload_sha256": _sha256_file(
            args.schema_workload.expanduser().resolve()
        ),
        "llm_tokens_spent": 0,
        "data_population_reused": True,
        "compiled_output_support_recomputed": False,
    }
    synthesis_path = output / "synthesis_manifest.json"
    synthesis_path.write_text(json.dumps(synthesis, indent=2, default=str))

    serving["queries"] = compiled
    serving["synthesis_manifest_sha256"] = _sha256_file(synthesis_path)
    os.chmod(serving_path, 0o644)
    serving_path.write_text(json.dumps(serving, indent=2))
    sealed_path = destination_bundle / "SEALED"
    os.chmod(sealed_path, 0o644)
    sealed_path.write_text(_sha256_file(serving_path) + "\n")
    os.chmod(serving_path, 0o444)
    os.chmod(sealed_path, 0o444)
    os.chmod(synthesis_path, 0o444)
    OfflineQueryServer(destination_bundle)
    print(
        json.dumps(
            {
                "source_run": str(source),
                "output_run": str(output),
                "query_count": len(compiled),
                "additional_llm_tokens": 0,
                "serving_manifest": str(serving_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
