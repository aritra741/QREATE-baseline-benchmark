"""Corpus registry: file locations only.

Nothing in this module is read by a routing rule. Dataset names appear only
here, to locate documents, attribute descriptions, the workload manifest, the
DocETL token total (used only to define theta), and an optional incumbent
database built without gold.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[5]
RESULTS = PROJECT / "results"
SOURCE = PROJECT / "source_data"
QUERY = PROJECT / "Query"


@dataclass(frozen=True)
class TableSpec:
    sql_name: str
    attributes_key: str
    doc_dir: Path


@dataclass(frozen=True)
class CorpusSpec:
    name: str
    tables: tuple[TableSpec, ...]
    attributes_json: tuple[Path, ...]
    manifest: Path
    docetl_cost: Path | None = None
    incumbent_db: Path | None = None
    notes: dict[str, str] = field(default_factory=dict)

    def table(self, sql_name: str) -> TableSpec | None:
        for table in self.tables:
            if table.sql_name == sql_name:
                return table
        return None

    def docetl_tokens(self) -> int | None:
        if self.docetl_cost is None or not self.docetl_cost.is_file():
            return None
        payload = json.loads(self.docetl_cost.read_text())
        return int(payload.get("total_tokens") or 0) or None

    def theta(self, fraction: float = 0.25) -> int | None:
        total = self.docetl_tokens()
        return None if total is None else round(total * fraction)

    def queries(self) -> dict[str, str]:
        if self.manifest.suffix == ".sql":
            return parse_split_sql(self.manifest.read_text())
        payload = json.loads(self.manifest.read_text())
        return {str(item["query_id"]): str(item["sql"]) for item in payload}

    def descriptions(self) -> dict[str, dict[str, dict]]:
        """Not a system input. The system sees documents, the SQL workload and theta only."""

        raise PermissionError(
            "benchmark attribute descriptions are not a system input (RULES.md: T, Q, theta only); "
            "scoring and audit code must call benchmark_attribute_descriptions(purpose=...)"
        )

    def benchmark_attribute_descriptions(self, *, purpose: str) -> dict[str, dict[str, dict]]:
        """``{attributes_key: {attribute: record}}``, for scoring and audits only, never for reads."""

        if purpose not in {"scoring", "audit"}:
            raise PermissionError(f"attribute descriptions requested for {purpose!r}")
        merged: dict[str, dict[str, dict]] = {}
        for path in self.attributes_json:
            payload = json.loads(path.read_text())
            for key, attrs in payload.items():
                merged.setdefault(key, {}).update(attrs)
        return merged


_SPLIT_HEADER = re.compile(r"^-- Query \d+:.*?id=(\S+)\s*$", re.M)


def parse_split_sql(text: str) -> dict[str, str]:
    """``-- Query N: <split> (<slice>) id=<id>`` blocks, each followed by one statement."""

    matches = list(_SPLIT_HEADER.finditer(text))
    out: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = " ".join(line for line in text[match.end():end].splitlines() if line.strip() and not line.startswith("--"))
        out[match.group(1)] = body.strip().rstrip(";").strip()
    return out


def _case80(tag: str) -> tuple[Path, Path]:
    base = RESULTS / f"docetl_{tag}_case80"
    return base / "query_manifest.json", base / "session_token_cost.json"


def _spec(name, tag, tables, attrs, incumbent=None) -> CorpusSpec:
    manifest, cost = _case80(tag)
    return CorpusSpec(
        name=name,
        tables=tuple(TableSpec(*row) for row in tables),
        attributes_json=tuple(attrs),
        manifest=manifest,
        docetl_cost=cost,
        incumbent_db=incumbent,
    )


REGISTRY: dict[str, CorpusSpec] = {
    "med": _spec(
        "med",
        "med",
        [
            ("disease", "disease", SOURCE / "Healthcare" / "disease_small"),
            ("drug", "drug", SOURCE / "Healthcare" / "drug_small"),
            ("institution", "institution", SOURCE / "Healthcare" / "institutes_small"),
        ],
        [QUERY / "Med" / "Med_attributes.json"],
        RESULTS / "quwarts_med_repair80" / "artifacts" / "databases" / "ab189be670f0c82c.db",
    ),
    "finan": _spec(
        "finan",
        "finan",
        [("finance", "finance", SOURCE / "Finance" / "finance")],
        [QUERY / "Finan" / "Finan_attributes.json"],
        RESULTS / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db",
    ),
    "legal": _spec(
        "legal",
        "legal",
        [("legal", "legal_case", SOURCE / "Legal" / "legal_case")],
        [QUERY / "Legal" / "Legal_attributes.json"],
        RESULTS / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db",
    ),
    "art": _spec(
        "art",
        "art",
        [("art", "Art", SOURCE / "Art" / "wikiart")],
        [QUERY / "Art" / "Art_attributes.json"],
    ),
    "cspaper": _spec(
        "cspaper",
        "cspaper",
        [("cspaper", "paper", SOURCE / "CSPaper" / "txt")],
        [QUERY / "CSPaper" / "CSPaper_attributes.json"],
    ),
    "player": _spec(
        "player",
        "player",
        [
            ("player", "player", SOURCE / "Player" / "player"),
            ("team", "team", SOURCE / "Player" / "team"),
            ("owner", "owner", SOURCE / "Player" / "owner"),
            ("city", "city", SOURCE / "Player" / "city"),
        ],
        [QUERY / "Player" / "Player_attributes.json"],
    ),
}


def get_corpus(name: str) -> CorpusSpec:
    try:
        return REGISTRY[name.lower()]
    except KeyError as exc:
        raise KeyError(f"unknown corpus {name!r}; known: {sorted(REGISTRY)}") from exc
