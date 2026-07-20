"""Immutable SQL-only serving artifacts for a frozen SPP portfolio."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence

from spp.budget_ledger import GlobalBudgetLedger
from spp.spec import FrozenPortfolio, QueryRequirement, SynthesisConfig


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_readonly_sql(sql: str) -> None:
    normalized = sql.strip().rstrip(";").strip()
    first = normalized.split(None, 1)[0].lower() if normalized else ""
    if first not in {"select", "with"}:
        raise ValueError("serving SQL must be a SELECT or WITH query")
    forbidden = (
        " insert ", " update ", " delete ", " drop ", " alter ", " create ",
        " attach ", " detach ", " pragma ", " vacuum ",
    )
    padded = f" {normalized.lower()} "
    if any(token in padded for token in forbidden):
        raise ValueError("serving SQL contains a mutating statement")


@dataclass(frozen=True)
class CompiledQuery:
    query_id: str
    natural_language_query: str
    config_id: str
    sql: str
    sql_sha256: str


@dataclass(frozen=True)
class DatabaseArtifact:
    config_id: str
    filename: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ServingManifest:
    version: int
    portfolio: dict
    databases: List[dict]
    queries: List[dict]
    token_ledger_sha256: str
    synthesis_manifest_sha256: Optional[str] = None
    evidence_manifest: Optional[dict] = None


def compile_workload_sql(
    requirements: Sequence[QueryRequirement],
    portfolio: FrozenPortfolio,
    configs: Mapping[str, SynthesisConfig],
    database_paths: Mapping[str, Path],
    compiler: Callable[
        [QueryRequirement, SynthesisConfig, Path, GlobalBudgetLedger], str
    ],
    ledger: GlobalBudgetLedger,
) -> List[CompiledQuery]:
    """Compile and validate every NL query during synthesis, never at serving."""
    compiled: List[CompiledQuery] = []
    for requirement in requirements:
        config_id = portfolio.query_to_config[requirement.query_id]
        config = configs[config_id]
        db_path = Path(database_paths[config_id])
        before = ledger.actual_spent
        sql = compiler(requirement, config, db_path, ledger)
        if ledger.actual_spent < before:
            raise AssertionError("compiler moved token ledger backwards")
        _validate_readonly_sql(sql)
        uri = f"file:{db_path.resolve()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall()
        compiled.append(
            CompiledQuery(
                query_id=requirement.query_id,
                natural_language_query=requirement.text,
                config_id=config_id,
                sql=sql,
                sql_sha256=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
            )
        )
    return compiled


def freeze_serving_bundle(
    output_dir: Path,
    portfolio: FrozenPortfolio,
    compiled_queries: Sequence[CompiledQuery],
    database_paths: Mapping[str, Path],
    ledger: GlobalBudgetLedger,
    *,
    evidence_manifest: Optional[dict] = None,
    synthesis_manifest_sha256: Optional[str] = None,
) -> Path:
    """Copy selected DBs and atomically seal a reproducible serving bundle."""
    output_dir = Path(output_dir).expanduser().resolve()
    if portfolio.construction_tokens != ledger.actual_spent:
        raise ValueError(
            "portfolio construction token count does not match global ledger"
        )
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"serving bundle is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    db_dir = output_dir / "databases"
    db_dir.mkdir()

    artifacts: List[DatabaseArtifact] = []
    for config_id in portfolio.selected_config_ids:
        source = Path(database_paths[config_id]).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(source)
        filename = f"{hashlib.sha256(config_id.encode()).hexdigest()[:16]}.sqlite"
        destination = db_dir / filename
        shutil.copy2(source, destination)
        os.chmod(destination, 0o444)
        artifacts.append(
            DatabaseArtifact(
                config_id=config_id,
                filename=str(Path("databases") / filename),
                sha256=_sha256(destination),
                size_bytes=destination.stat().st_size,
            )
        )

    ledger_path = output_dir / "token_ledger.json"
    ledger.save(ledger_path)
    manifest = ServingManifest(
        version=1,
        portfolio={
            "selected_config_ids": list(portfolio.selected_config_ids),
            "query_to_config": dict(portfolio.query_to_config),
            "query_scores": dict(portfolio.query_scores),
            "construction_tokens": portfolio.construction_tokens,
            "objective_value": portfolio.objective_value,
        },
        databases=[asdict(artifact) for artifact in artifacts],
        queries=[asdict(query) for query in compiled_queries],
        token_ledger_sha256=_sha256(ledger_path),
        synthesis_manifest_sha256=synthesis_manifest_sha256,
        evidence_manifest=evidence_manifest,
    )
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(asdict(manifest), indent=2))
    (output_dir / "SEALED").write_text(_sha256(manifest_path) + "\n")
    os.chmod(manifest_path, 0o444)
    os.chmod(ledger_path, 0o444)
    os.chmod(output_dir / "SEALED", 0o444)
    return manifest_path


class OfflineQueryServer:
    """Executes only precompiled SQL against checksum-verified read-only DBs."""

    def __init__(self, bundle_dir: Path):
        self.bundle_dir = Path(bundle_dir).expanduser().resolve()
        manifest_path = self.bundle_dir / "manifest.json"
        sealed_path = self.bundle_dir / "SEALED"
        if not manifest_path.exists() or not sealed_path.exists():
            raise ValueError("serving bundle is not sealed")
        expected_manifest = sealed_path.read_text().strip()
        if _sha256(manifest_path) != expected_manifest:
            raise ValueError("serving manifest checksum mismatch")
        self.manifest = json.loads(manifest_path.read_text())
        self._queries = {
            row["query_id"]: CompiledQuery(**row)
            for row in self.manifest["queries"]
        }
        self._databases: Dict[str, Path] = {}
        for artifact in self.manifest["databases"]:
            path = self.bundle_dir / artifact["filename"]
            if _sha256(path) != artifact["sha256"]:
                raise ValueError(f"database checksum mismatch: {path}")
            self._databases[artifact["config_id"]] = path

    def execute(self, query_id: str) -> List[dict]:
        compiled = self._queries.get(query_id)
        if compiled is None:
            raise KeyError(f"query not in frozen workload: {query_id}")
        if hashlib.sha256(compiled.sql.encode("utf-8")).hexdigest() != compiled.sql_sha256:
            raise ValueError("compiled SQL checksum mismatch")
        _validate_readonly_sql(compiled.sql)
        db_path = self._databases[compiled.config_id]
        uri = f"file:{db_path}?mode=ro&immutable=1"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.row_factory = sqlite3.Row
            cursor = connection.execute(compiled.sql)
            return [dict(row) for row in cursor.fetchall()]
