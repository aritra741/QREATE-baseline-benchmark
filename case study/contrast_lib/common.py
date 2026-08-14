#!/usr/bin/env python3
"""Load datasets, validate contrast workloads, and write manifests."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "Data"
OUT_ROOT = Path(__file__).resolve().parents[1] / "workloads"


def num(value: str | None):
    text = (value or "").strip().replace(",", "").replace(" ", "")
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = []
        for raw in csv.DictReader(handle):
            row: dict[str, str] = {}
            for key, value in raw.items():
                if key is None or str(key).strip() == "":
                    continue
                row[str(key).strip().lower()] = (value or "").strip()
            rows.append(row)
        return rows


def create_table(
    conn: sqlite3.Connection,
    table: str,
    rows: list[dict[str, str]],
    columns: list[str],
    numeric: Iterable[str] = (),
) -> None:
    numeric_set = {name.lower() for name in numeric}
    col_sql = ", ".join(
        f"{col} {'REAL' if col in numeric_set else 'TEXT'}" for col in columns
    )
    conn.execute(f"CREATE TABLE {table} ({col_sql})")
    placeholders = ",".join("?" for _ in columns)
    payload = []
    for row in rows:
        values = []
        for col in columns:
            raw = row.get(col, "")
            values.append(num(raw) if col in numeric_set else raw)
        payload.append(tuple(values))
    conn.executemany(f"INSERT INTO {table} VALUES ({placeholders})", payload)


def load_art() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    rows = read_csv(DATA / "Art" / "Art.csv")
    create_table(
        conn,
        "art",
        rows,
        [
            "id",
            "name",
            "nationality",
            "art_movement",
            "birth_date",
            "death_date",
            "age",
            "century",
            "zodiac",
            "birth_country",
            "birth_city",
            "birth_continent",
            "death_country",
            "death_city",
            "field",
            "genre",
            "marriage",
            "art_institution",
            "teaching",
            "awards",
            "style",
            "image_genre",
            "object",
            "color",
            "tone",
            "composition",
        ],
        numeric=("age", "teaching", "awards"),
    )
    return conn


def load_cspaper() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    rows = read_csv(DATA / "CSPaper" / "CSPaper.csv")
    for row in rows:
        baseline = row.get("baseline", "")
        row["baseline_amount"] = "" if baseline == "" else str(baseline.count("||") + 1)
    create_table(
        conn,
        "cspaper",
        rows,
        [
            "pdf_filename",
            "paper_name",
            "author",
            "institute",
            "topic",
            "uses_knowledge_graph",
            "reasoning_depth",
            "baseline",
            "baseline_amount",
            "retrieval_method",
            "generator_model",
            "uses_reranker",
            "data_modality",
            "evaluation_dataset",
            "evaluation_metric",
            "application_domain",
            "use_agent",
            "agent_framework",
            "multi_turn_retrieval",
        ],
        numeric=("baseline_amount",),
    )
    return conn


def load_finan() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    rows = read_csv(DATA / "Finan" / "Finan.csv")
    create_table(
        conn,
        "finance",
        rows,
        [
            "company_name",
            "registered_office",
            "exchange_code",
            "principal_activities",
            "revenue",
            "net_profit_or_loss",
            "total_debt",
            "total_assets",
            "cash_reserves",
            "net_assets",
            "earnings_per_share",
            "dividend_per_share",
            "largest_shareholder",
            "the_highest_ownership_stake",
            "major_equity_changes",
            "major_events",
            "bussiness_sales",
            "bussiness_profit",
            "bussiness_cost",
            "business_segments_num",
            "business_risks",
            "remuneration_policy",
            "auditor",
            "id",
        ],
        numeric=(
            "revenue",
            "net_profit_or_loss",
            "total_debt",
            "total_assets",
            "cash_reserves",
            "net_assets",
            "earnings_per_share",
            "dividend_per_share",
            "the_highest_ownership_stake",
            "bussiness_sales",
            "bussiness_profit",
            "bussiness_cost",
            "business_segments_num",
        ),
    )
    return conn


def load_legal() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    rows = read_csv(DATA / "Legal" / "Legal.csv")
    create_table(
        conn,
        "legal",
        rows,
        [
            "id",
            "judge_name",
            "plaintiff",
            "defendant",
            "hearing_year",
            "judgment_year",
            "charges",
            "case_type",
            "verdict",
            "legal_basis_num",
            "case_number",
            "counsel_for_applicant",
            "counsel_for_respondent",
            "nationality_for_applicant",
            "fine_amount",
            "legal_fees",
            "plaintiff_current_status",
            "defendant_current_status",
            "evidence",
            "first_judge",
        ],
        numeric=(
            "hearing_year",
            "judgment_year",
            "legal_basis_num",
            "case_number",
            "fine_amount",
            "legal_fees",
            "evidence",
            "first_judge",
        ),
    )
    return conn


def load_med() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_table(
        conn,
        "disease",
        read_csv(DATA / "Med" / "disease.csv"),
        [
            "disease_name",
            "disease_type",
            "pathogenesis",
            "etiology",
            "diagnostic_methods",
            "common_symptoms",
            "complications",
            "affected_organs",
            "treatments",
            "drugs",
            "prognosis",
            "sequelae",
            "epidemiology",
            "risk_factors",
            "preventive_measures",
            "diagnosis_challenges",
            "treatment_challenges",
            "quality_of_life_impact",
            "id",
        ],
    )
    create_table(
        conn,
        "drug",
        read_csv(DATA / "Med" / "drug.csv"),
        [
            "generic_name",
            "brand_name",
            "disease_name",
            "indication",
            "active_ingredients",
            "pharmaceutical_form",
            "manufacturer",
            "administration_route",
            "recommended_usage",
            "single_dose",
            "dosage_frequency",
            "mechanism_of_action",
            "side_effects",
            "activation_conditions",
            "prescription_status",
            "unsuitable_population",
            "storage_conditions",
            "id",
        ],
    )
    create_table(
        conn,
        "institution",
        read_csv(DATA / "Med" / "institution.csv"),
        [
            "institution_name",
            "institution_type",
            "parent_organization",
            "leadership",
            "institution_country",
            "institution_city",
            "research_diseases",
            "research_fields",
            "key_technologies",
            "key_achievements",
            "international_collaboration",
            "funding_sources",
            "technology_application",
            "id",
        ],
    )
    return conn


def load_sec() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_table(
        conn,
        "company",
        read_csv(DATA / "SEC" / "company.csv"),
        [
            "company_id",
            "cik",
            "ticker",
            "name",
            "sic",
            "sic_description",
            "state_of_incorporation",
            "fiscal_year_end",
            "entity_type",
        ],
    )
    create_table(
        conn,
        "filing",
        read_csv(DATA / "SEC" / "filing.csv"),
        [
            "filing_id",
            "company_id",
            "ticker",
            "company_name",
            "accession_number",
            "form_type",
            "filing_date",
            "report_date",
            "fiscal_year",
            "fiscal_period",
            "fiscal_quarter",
            "sic",
            "sic_description",
            "state_of_incorporation",
            "is_xbrl",
            "is_inline_xbrl",
        ],
        numeric=("fiscal_year", "fiscal_quarter", "is_xbrl", "is_inline_xbrl"),
    )
    create_table(
        conn,
        "filing_metrics",
        read_csv(DATA / "SEC" / "filing_metrics.csv"),
        [
            "filing_id",
            "company_id",
            "ticker",
            "company_name",
            "form_type",
            "filing_date",
            "report_date",
            "fiscal_year",
            "fiscal_period",
            "fiscal_quarter",
            "sic",
            "sic_description",
            "state_of_incorporation",
            "revenue_usd",
            "revenue_usd_concept_id",
            "assets_usd",
            "assets_usd_concept_id",
            "liabilities_usd",
            "net_income_usd",
            "operating_cash_flow_usd",
            "investing_cash_flow_usd",
            "financing_cash_flow_usd",
            "shares_outstanding",
        ],
        numeric=(
            "fiscal_year",
            "fiscal_quarter",
            "revenue_usd",
            "assets_usd",
            "liabilities_usd",
            "net_income_usd",
            "operating_cash_flow_usd",
            "investing_cash_flow_usd",
            "financing_cash_flow_usd",
            "shares_outstanding",
        ),
    )
    create_table(
        conn,
        "concept",
        read_csv(DATA / "SEC" / "concept.csv"),
        ["concept_id", "taxonomy", "concept_name", "label", "description"],
    )
    return conn


LOADERS = {
    "Art": load_art,
    "CSPaper": load_cspaper,
    "Finan": load_finan,
    "Legal": load_legal,
    "Med": load_med,
    "SEC": load_sec,
}


def validate(conn: sqlite3.Connection, workloads: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for name, spec in workloads.items():
        queries = spec["queries"]
        expected = int(spec.get("n_queries") or 20)
        if len(queries) != expected:
            errors.append(f"{name}: expected {expected} queries, found {len(queries)}")
        seen_ids: set[str] = set()
        seen_sql: set[str] = set()
        for qid, sql, text in queries:
            if qid in seen_ids:
                errors.append(f"{name}/{qid}: duplicate query id")
            seen_ids.add(qid)
            fingerprint = re.sub(r"\s+", " ", sql.lower()).strip()
            if fingerprint in seen_sql:
                errors.append(f"{name}/{qid}: duplicate SQL")
            seen_sql.add(fingerprint)
            if not text.strip():
                errors.append(f"{name}/{qid}: empty natural-language question")
            if re.search(r"HAVING\s+COUNT\([^)]*\)\s*>=\s*1\b", sql, re.IGNORECASE):
                errors.append(f"{name}/{qid}: tautological HAVING COUNT >= 1")
            try:
                cursor = conn.execute(sql)
                rows = cursor.fetchall()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{name}/{qid}: {exc}\n  SQL: {sql}")
                continue
            if len(rows) == 0:
                errors.append(f"{name}/{qid}: empty result")
            if len(rows) == 1 and "GROUP BY" in sql.upper():
                errors.append(f"{name}/{qid}: GROUP BY produces only one group")
            group_match = re.search(
                r"\bGROUP BY\s+(.+?)(?:\bHAVING\b|$)", sql, re.IGNORECASE
            )
            column_names = [item[0].lower() for item in cursor.description or []]
            count_indexes = [
                index for index, column in enumerate(column_names) if "count" in column
            ]
            if (
                group_match
                and "," in group_match.group(1)
                and len(rows) >= 3
                and count_indexes
                and any(all(row[index] == 1 for row in rows) for index in count_indexes)
            ):
                errors.append(
                    f"{name}/{qid}: multi-column GROUP BY only reproduces singleton rows"
                )
    return errors


def write_workloads(
    dataset: str,
    workloads: dict[str, dict[str, Any]],
    *,
    join_notes: dict[str, str] | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> list[Path]:
    written: list[Path] = []
    for name, spec in workloads.items():
        out_dir = OUT_ROOT / name
        out_dir.mkdir(parents=True, exist_ok=True)
        sql_manifest = [{"query_id": qid, "sql": sql} for qid, sql, _ in spec["queries"]]
        nl_manifest = [{"query_id": qid, "text": text} for qid, _, text in spec["queries"]]
        meta = {
            "workload_id": name,
            "title": spec["title"],
            "focus": spec["focus"],
            "dataset": dataset,
            "n_queries": len(spec["queries"]),
            "kind": spec.get("kind", "pure"),
        }
        if spec.get("contrast_with"):
            meta["contrast_with"] = spec["contrast_with"]
        if join_notes:
            meta["join_notes"] = join_notes
        if extra_meta:
            meta.update(extra_meta)
        (out_dir / "query_manifest.json").write_text(
            json.dumps(sql_manifest, indent=2) + "\n", encoding="utf-8"
        )
        (out_dir / "query_manifest_nl.json").write_text(
            json.dumps(nl_manifest, indent=2) + "\n", encoding="utf-8"
        )
        (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        written.append(out_dir)
        print(f"wrote {out_dir}")
    return written


def q(qid: str, sql: str, text: str) -> tuple[str, str, str]:
    return (qid, " ".join(sql.split()), text)
