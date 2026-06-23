"""Generate corpus-grounded Med aggregation queries for balanced workloads.

Mirrors the structure of player_workload_generator.py but targets the Healthcare
(Med) schema: disease, drug, institution tables.

Join path
---------
drug JOIN disease ON drug.disease_name = disease.disease_name
(drug.disease_name is often pipe-separated so the join produces a sparse result —
this is realistic sparse-extraction behaviour and is kept intentionally.)

agg_temporal is excluded — Med has no structured temporal column.

Quality constraints applied
---------------------------
* No tautological filters: WHERE col = 'val' GROUP BY col is excluded when
  the filter equality is on the same column as the GROUP BY key.
* No AVG on VARCHAR columns: quality_of_life_impact is text, not numeric.
* MIN/MAX restricted to columns where alphabetical ordering carries meaning
  (e.g. brand_name as a proxy for the "earliest" drug alphabetically is dropped;
  MIN/MAX on dosage_frequency is kept because it mirrors the original benchmark).
"""

from __future__ import annotations

from itertools import product
from typing import Any

# ── GROUP BY columns ───────────────────────────────────────────────────────────

DRUG_GROUP_COLS = ["prescription_status", "administration_route", "pharmaceutical_form"]

INST_GROUP_COLS = ["institution_type", "institution_country"]

# ── Aggregate expressions per table ───────────────────────────────────────────
# Only COUNT and MIN/MAX on columns where the ordering is interpretable.
# No AVG/SUM on VARCHAR columns.

DRUG_AGG_EXPRS = [
    ("COUNT(*)", "count_all"),
    ("COUNT(generic_name)", "count_generic_name"),
    ("COUNT(manufacturer)", "count_manufacturer"),
    ("COUNT(side_effects)", "count_side_effects"),
    ("MIN(dosage_frequency)", "min_dosage_frequency"),
    ("MAX(dosage_frequency)", "max_dosage_frequency"),
    ("MIN(storage_conditions)", "min_storage_conditions"),
    ("MAX(storage_conditions)", "max_storage_conditions"),
]

INST_AGG_EXPRS = [
    ("COUNT(*)", "count_all"),
    ("COUNT(institution_name)", "count_institution_name"),
    ("COUNT(funding_sources)", "count_funding_sources"),
    ("MIN(research_fields)", "min_research_fields"),
    ("MAX(research_fields)", "max_research_fields"),
]

# ── Filter predicates (column -> [values]) ────────────────────────────────────
# Keyed by column so tautological combinations can be detected and skipped.

DRUG_FILTER_SPECS: list[tuple[str, list[str]]] = [
    ("prescription_status", [
        "prescription_only",
        "over_the_counter",
        "unclassified",
    ]),
    ("administration_route", [
        "oral",
        "intravenous",
        "injection",
        "topical",
        "inhalation",
        "subcutaneous",
    ]),
    ("pharmaceutical_form", [
        "tablet",
        "capsule",
        "injection",
        "solution",
        "cream",
        "gel",
        "spray",
    ]),
    ("activation_conditions", [
        "no special condition",
    ]),
]

INST_FILTER_SPECS: list[tuple[str, list[str]]] = [
    ("institution_type", [
        "university-affiliated",
        "private",
        "public",
        "not-for-profit charity",
    ]),
    ("institution_country", [
        "USA",
        "Germany",
        "France",
        "Australia",
        "China",
        "India",
    ]),
    ("research_fields", [
        "clinical_research",
        "immunology",
        "pharmacology",
        "microbiology",
    ]),
]

# Join path for agg_join and agg_filter_join
_DRUG_DISEASE_JOIN = (
    "drug_disease",
    "drug JOIN disease ON drug.disease_name = disease.disease_name",
)

JOIN_GROUP_COLS = [
    "drug.prescription_status",
    "drug.administration_route",
    "drug.pharmaceutical_form",
    "disease.disease_type",
]

# Only COUNT and MIN/MAX — no AVG/SUM because all candidate columns are VARCHAR
JOIN_AGG_EXPRS = [
    ("COUNT(*)", "count_all"),
    ("COUNT(drug.generic_name)", "count_drug_generic_name"),
    ("COUNT(disease.disease_name)", "count_disease_disease_name"),
    ("MIN(drug.dosage_frequency)", "min_drug_dosage_frequency"),
    ("MAX(drug.dosage_frequency)", "max_drug_dosage_frequency"),
    ("MIN(drug.storage_conditions)", "min_drug_storage_conditions"),
    ("COUNT(disease.treatments)", "count_disease_treatments"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_all_preds(specs: list[tuple[str, list[str]]]) -> list[tuple[str, str]]:
    """Return (column, predicate_sql) pairs."""
    out: list[tuple[str, str]] = []
    for col, vals in specs:
        for val in vals:
            out.append((col, f"{col} = '{val}'"))
            out.append((col, f"{col} != '{val}'"))
    return out


def _is_tautological(pred_col: str, group_col: str) -> bool:
    """True when an equality filter is on the same column as the GROUP BY."""
    bare_pred_col = pred_col.split(".")[-1]
    bare_group_col = group_col.split(".")[-1]
    return bare_pred_col == bare_group_col


def _cross_preds(
    all_preds: list[tuple[str, str]],
    group_col: str,
) -> list[str]:
    """Filter predicates that are NOT on the same column as the GROUP BY."""
    return [sql for col, sql in all_preds if not _is_tautological(col, group_col)]


# ── Slice generators ──────────────────────────────────────────────────────────

def generate_agg_only_candidates() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for group_col, (agg_expr, alias) in product(DRUG_GROUP_COLS, DRUG_AGG_EXPRS):
        sql = f"SELECT {group_col}, {agg_expr} AS {alias} FROM drug GROUP BY {group_col};"
        out.append({"template": f"agg_only|drug|{group_col}|{alias}", "sql": sql})
    for group_col, (agg_expr, alias) in product(INST_GROUP_COLS, INST_AGG_EXPRS):
        sql = f"SELECT {group_col}, {agg_expr} AS {alias} FROM institution GROUP BY {group_col};"
        out.append({"template": f"agg_only|institution|{group_col}|{alias}", "sql": sql})
    return out


def generate_agg_filter_candidates() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    all_drug_preds = _build_all_preds(DRUG_FILTER_SPECS)
    all_inst_preds = _build_all_preds(INST_FILTER_SPECS)

    # Drug: only use predicates on columns different from the GROUP BY column
    for idx, (group_col, (agg_expr, alias)) in enumerate(
        product(DRUG_GROUP_COLS, DRUG_AGG_EXPRS[:5])
    ):
        preds = _cross_preds(all_drug_preds, group_col)
        if not preds:
            continue
        for offset in range(5):
            p1 = preds[(idx * 3 + offset) % len(preds)]
            p2 = preds[(idx * 3 + offset + 7) % len(preds)]
            p3 = preds[(idx * 3 + offset + 13) % len(preds)]
            for mode, where in (
                ("single", p1),
                ("and", f"({p1}) AND ({p2})"),
                ("or", f"({p1}) OR ({p2})"),
                ("mixed", f"({p1} AND {p2}) OR ({p3})"),
            ):
                sql = (
                    f"SELECT {group_col}, {agg_expr} AS {alias} "
                    f"FROM drug WHERE {where} GROUP BY {group_col};"
                )
                out.append(
                    {"template": f"agg_filter|drug|{group_col}|{mode}|{idx}_{offset}", "sql": sql}
                )

    # Institution: cross-column filters only
    for idx, (group_col, (agg_expr, alias)) in enumerate(
        product(INST_GROUP_COLS, INST_AGG_EXPRS[:4])
    ):
        preds = _cross_preds(all_inst_preds, group_col)
        if not preds:
            continue
        for offset in range(3):
            p1 = preds[(idx * 2 + offset) % len(preds)]
            p2 = preds[(idx * 2 + offset + 5) % len(preds)]
            for mode, where in (
                ("single", p1),
                ("and", f"({p1}) AND ({p2})"),
                ("or", f"({p1}) OR ({p2})"),
            ):
                sql = (
                    f"SELECT {group_col}, {agg_expr} AS {alias} "
                    f"FROM institution WHERE {where} GROUP BY {group_col};"
                )
                out.append(
                    {
                        "template": f"agg_filter|institution|{group_col}|{mode}|{idx}_{offset}",
                        "sql": sql,
                    }
                )

    return out


def generate_agg_join_candidates() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    path_name, join_clause = _DRUG_DISEASE_JOIN
    for group_col, (agg_expr, alias) in product(JOIN_GROUP_COLS, JOIN_AGG_EXPRS):
        sql = (
            f"SELECT {group_col}, {agg_expr} AS {alias} "
            f"FROM {join_clause} GROUP BY {group_col};"
        )
        out.append({"template": f"agg_join|{path_name}|{group_col}|{alias}", "sql": sql})
    return out


def generate_agg_filter_join_candidates() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    path_name, join_clause = _DRUG_DISEASE_JOIN

    drug_preds = [
        (col, f"drug.{col} = '{val}'")
        for col, vals in DRUG_FILTER_SPECS
        for val in vals[:3]
    ]
    disease_preds = [
        ("disease_type", "disease.disease_type = 'metabolic'"),
        ("disease_type", "disease.disease_type = 'infectious'"),
        ("disease_type", "disease.disease_type = 'degenerative'"),
        ("pathogenesis", "disease.pathogenesis != 'traumatic'"),
        ("prognosis", "disease.prognosis = 'full_recovery'"),
        ("disease_type", "disease.disease_type = 'autoimmune'"),
    ]
    all_preds = drug_preds + disease_preds  # list of (col, sql)

    idx = 0
    for group_col, (agg_expr, alias) in product(JOIN_GROUP_COLS[:3], JOIN_AGG_EXPRS[:5]):
        for offset in range(4):
            # filter preds that are not tautological with group_col
            valid = [(c, s) for c, s in all_preds if not _is_tautological(c, group_col)]
            if not valid:
                continue
            p1 = valid[(idx + offset) % len(valid)][1]
            p2 = valid[(idx + offset + 6) % len(valid)][1]
            for mode, where in (
                ("single", p1),
                ("and", f"({p1}) AND ({p2})"),
                ("or", f"({p1}) OR ({p2})"),
            ):
                sql = (
                    f"SELECT {group_col}, {agg_expr} AS {alias} "
                    f"FROM {join_clause} WHERE {where} GROUP BY {group_col};"
                )
                out.append(
                    {
                        "template": f"agg_filter_join|{path_name}|{mode}|{idx}_{offset}",
                        "sql": sql,
                    }
                )
        idx += 1
    return out


# ── Public entry point ────────────────────────────────────────────────────────

def _candidate_to_query(candidate: dict[str, str], query_id: str) -> dict[str, Any]:
    return {
        "query_id": query_id,
        "sql_query": candidate["sql"],
        "nl_query": None,
        "category": "Generated",
        "metadata": {
            "generated": True,
            "template": candidate.get("template"),
        },
    }


def generate_all_candidates_med() -> dict[str, list[dict[str, Any]]]:
    """Return {slice_name: [query_dict, ...]} for Med."""
    generators = {
        "agg_only": generate_agg_only_candidates,
        "agg_filter": generate_agg_filter_candidates,
        "agg_join": generate_agg_join_candidates,
        "agg_filter_join": generate_agg_filter_join_candidates,
    }
    out: dict[str, list[dict[str, Any]]] = {}
    for slice_name, gen in generators.items():
        candidates = gen()
        out[slice_name] = [
            _candidate_to_query(c, f"{slice_name}_med_gen_{i}")
            for i, c in enumerate(candidates, start=1)
        ]
    return out


if __name__ == "__main__":
    result = generate_all_candidates_med()
    for slice_name, queries in result.items():
        print(f"{slice_name}: {len(queries)} candidates")
        for q in queries[:3]:
            print(f"  {q['sql_query']}")
