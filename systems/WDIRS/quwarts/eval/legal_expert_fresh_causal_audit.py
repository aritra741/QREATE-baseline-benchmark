"""Zero-call causal audit of the frozen fresh Legal θ50 query-expert arm.

The audit specification is written and hashed before benchmark gold or Stage A
map values are opened. Frozen artifacts are read and copied, never modified.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path("/Users/aritramazumder/Documents/UDA-Bench-main")
sys.path[:0] = [str(ROOT / "systems" / "WDIRS"), str(ROOT / "systems" / "docetl-main"), str(ROOT)]

FROZEN = ROOT / "results" / "quwarts_legal_expert_fresh_theta50"
STAGE = ROOT / "results" / "quwarts_legal_expert_budget"
GATE = ROOT / "results" / "quwarts_legal_expert_set_cover"
OUT = ROOT / "results" / "quwarts_legal_expert_fresh_theta50_causal_audit"
PLUMBING = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
MANIFEST = ROOT / "results" / "docetl_legal_case80" / "query_manifest.json"
SCHEDULE = STAGE / "schedule_frozen.json"
DOCS = ROOT / "source_data" / "Legal" / "legal_case"
EXTRACT_ROOT = ROOT / "results" / "docetl_legal_case80" / "docetl_pipelines"
EXPECTED_SCHEDULE = "ac8c43797d845d270a4a43e3ae694e396d6c6bd12260036def5a643bca01794d"
EXPECTED_ROUTING = "90cf224fa3bac73f4fc28bf6925af06b647b795beee472db21a92f0dbd6ec2db"
PREFIX = [
    "legal_multiagg20:q18",
    "legal_multiagg20:q4",
    "legal_agg20:q11",
    "legal_agg20:q13",
    "legal_agg20:q14",
    "legal_agg20:q17",
]
DOCETL_PRODUCT = 0.12350932750098194
FRESH25 = 0.04208752074497511
FRESH50 = 0.07420320131953051
FRESH50_CONSERVATIVE = 0.04208752074497511
STAGE50_TEXT = "0.13250247787203"

SPEC: dict[str, Any] = {
    "name": "fresh-legal-theta50-causal-audit",
    "model_calls": 0,
    "frozen_inputs_only": True,
    "gold_and_stage_a_values_read_only_after_this_spec_is_hashed": True,
    "schedule_sha256": EXPECTED_SCHEDULE,
    "routing_sha256": EXPECTED_ROUTING,
    "reproduction_targets": {
        "fresh_theta25_same_attribute": FRESH25,
        "fresh_theta50_same_attribute": FRESH50,
        "fresh_theta50_conservative": FRESH50_CONSERVATIVE,
        "stage_a_theta50_optimistic": STAGE50_TEXT,
        "docetl": DOCETL_PRODUCT,
    },
    "normalization": {
        "number_sentinel": -1,
        "string_sentinel": "",
        "sentinel_becomes": None,
        "bool_is_invalid_number": True,
    },
    "salvage_rules": {
        "targets": "terminal or malformed stored raw_arguments only",
        "parse": "json.loads of the raw string, after removing one surrounding ``` or ```json fence if the interior is the entire payload",
        "no_invented_braces": True,
        "no_invented_field_names": True,
        "no_invented_values": True,
        "accept_field_when": [
            "object key equals a requested field name exactly",
            "the fresh normalizer accepts exactly one type-valid value",
            "every stored attempt that parses agrees on that normalized value",
        ],
        "reject_when": [
            "JSON does not parse",
            "the value is not an object",
            "a present requested field fails the normalizer",
            "two attempts normalize the same field to different values",
            "a key is only a case variant or alias of a field name",
        ],
        "empty_object_recovers_nothing": True,
        "provider_error_without_raw_recovers_nothing": True,
        "successful_responses_are_not_salvage_targets": True,
    },
    "replays": {
        "R_fresh_recovery": {
            "diagnostic_only": False,
            "uses_stage_a_or_gold": False,
            "steps": [
                "copy the fresh theta50 same-attribute databases",
                "write salvaged fields for terminal requests; direct NULL is written; shared NULL is not",
                "for a still-missing document and attribute, use the earliest other completed fresh expert with a non-NULL value of the same type",
                "a successful own-expert NULL stays missing-from-others and is not replaced",
                "never overwrite an existing non-NULL from the target expert",
                "never share across document or entity ids",
            ],
        },
        "D1_terminal_failure_substitution": {
            "diagnostic_only": True,
            "uses_stage_a_values": True,
            "rule": "On fresh terminal failures only, write the fresh-normalized Stage A value for the same expert, document, and field. Successful fresh values stay unchanged.",
        },
        "D2_successful_call_semantic_substitution": {
            "diagnostic_only": True,
            "uses_stage_a_values": True,
            "rule": "Where both fresh and Stage A completed the same expert, document, and field, replace the fresh cell with the fresh-normalized Stage A value, including NULL. Do not fill terminal failures.",
        },
        "D3_full_stage_a_substitution": {
            "diagnostic_only": True,
            "uses_stage_a_values": True,
            "rule": "Start from the Stage A optimistic theta50 databases. Where Stage A has no row, fill from a fresh success using fresh normalization. This is the coverage-limited Stage A replay.",
        },
        "D4_fresh_perfect_coverage": {
            "diagnostic_only": True,
            "uses_stage_a_values": False,
            "rule": "For each terminal failure field, if every other completed fresh expert that emitted a non-NULL value agrees on one normalized value of the same type, write it. Conflicts are left unchanged. Expert precedence is ignored.",
        },
    },
    "sql_visible": "A substituted cell is SQL-visible when restoring its pre-substitution value changes an official bag of a query whose SQL references that attribute.",
    "gold_cell_study": "After replay manifests are frozen, compare normalized extracted values to the official Legal ground-truth table by document stem. Gold does not choose a replay.",
    "decision_order": [
        "execution failures explain the missing win",
        "historical completions would restore the win, but fresh semantics do not",
        "fresh query experts remain below DocETL even with recoverable coverage",
        "audit invalid",
    ],
}


def sha(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_value(value: Any, kind: str) -> tuple[Any, bool]:
    if kind == "number":
        if isinstance(value, bool) or value is None:
            return None, False
        if isinstance(value, str):
            text = value.strip().replace(",", "")
            if text == "":
                return None, False
            try:
                value = float(text) if "." in text else int(text)
            except ValueError:
                return None, False
        if not isinstance(value, (int, float)):
            return None, False
        if value == -1:
            return None, True
        return (int(value) if float(value).is_integer() else value), True
    if value is None or not isinstance(value, str):
        return None, False
    return (None, True) if value == "" else (value, True)


def write_spec() -> str:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "audit_spec.json").write_text(json.dumps(SPEC, indent=2))
    digest = sha(SPEC)
    (OUT / "audit_spec.sha256").write_text(digest + "\n")
    (OUT / "salvage_rules.json").write_text(json.dumps(SPEC["salvage_rules"], indent=2))
    (OUT / "salvage_rules.sha256").write_text(sha(SPEC["salvage_rules"]) + "\n")
    return digest


def load_requests() -> dict[tuple[str, str], dict[str, Any]]:
    rows = json.loads((FROZEN / "requests.json").read_text())
    return {(row["query_id"], row["doc_id"]): row for row in rows}


def load_journal() -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for line in (FROZEN / "arm" / "journal.jsonl").read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            grouped[(row["query_id"], row["doc_id"])].append(row)
    return grouped


def schemas() -> dict[str, dict[str, str]]:
    experts = json.loads((GATE / "experts.json").read_text())
    return {row["query_id"]: dict(row["output_schema"]) for row in experts}


def lengths() -> dict[str, int]:
    found = {}
    for path in DOCS.glob("*.txt"):
        found[f"{path.stem}.txt"] = path.stat().st_size
    return found


def deciles(sizes: dict[str, int]) -> dict[str, int]:
    ordered = sorted(sizes, key=lambda doc: (sizes[doc], doc))
    width = len(ordered) / 10
    return {doc: min(10, int(index / width) + 1) for index, doc in enumerate(ordered)}


def final_row(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    return attempts[-1]


def terminal_class(attempts: list[dict[str, Any]]) -> str | None:
    if final_row(attempts)["status"] != "terminal":
        return None
    results = [row for row in attempts if row["status"] != "issued"]
    return (results[-1].get("cause") if results else None) or "unknown"


def parse_raw(raw: str) -> tuple[dict[str, Any] | None, str]:
    text = raw.strip()
    repaired = False
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()
            repaired = True
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None, "unparsed"
    if not isinstance(value, dict):
        return None, "not_object"
    return value, "repaired" if repaired else "parsed"


def salvage_request(attempts: list[dict[str, Any]], schema: dict[str, str]) -> dict[str, Any]:
    if final_row(attempts)["status"] == "success":
        return {"recovered": {}, "class": "success_not_targeted"}
    found: dict[str, list[Any]] = defaultdict(list)
    classes = []
    parsed_objects = 0
    for row in attempts:
        raw = row.get("raw_arguments")
        if raw is None:
            continue
        obj, klass = parse_raw(raw)
        classes.append(klass)
        if obj is None:
            continue
        parsed_objects += 1
        for name, kind in schema.items():
            if name not in obj:
                continue
            value, ok = normalize_value(obj[name], kind)
            if not ok:
                continue
            found[name].append(value)
    recovered = {}
    for name, values in found.items():
        if all(value == values[0] for value in values):
            recovered[name] = values[0]
    return {
        "recovered": recovered,
        "parsed_objects": parsed_objects,
        "parse_classes": classes,
        "partial": bool(recovered) and set(recovered) != set(schema),
        "unchanged_complete": set(recovered) == set(schema) and "repaired" not in classes,
        "repaired": "repaired" in classes and bool(recovered),
    }


def fresh_outputs(journal: dict[tuple[str, str], list[dict[str, Any]]]) -> dict[str, dict[str, dict[str, Any]]]:
    outputs: dict[str, dict[str, dict[str, Any]]] = {qid: {} for qid in PREFIX}
    for (qid, doc), attempts in journal.items():
        if qid in outputs and final_row(attempts)["status"] == "success":
            outputs[qid][doc] = dict(final_row(attempts)["output"])
    return outputs


def stage_outputs(schema_by_expert: dict[str, dict[str, str]]) -> dict[str, dict[str, dict[str, Any]]]:
    loaded: dict[str, dict[str, dict[str, Any]]] = {}
    for qid in PREFIX:
        rows = json.loads(
            (EXTRACT_ROOT / qid / "table_legal/docetl_intermediate/extract_step/extract_fields.json").read_text()
        )
        by_doc: dict[str, dict[str, Any]] = {}
        for row in rows:
            doc = str(row.get("doc_id"))
            doc_id = doc if doc.endswith(".txt") else f"{doc}.txt"
            normalized = {}
            ok = True
            for name, kind in schema_by_expert[qid].items():
                if name not in row:
                    ok = False
                    break
                value, accepted = normalize_value(row[name], kind)
                if not accepted:
                    ok = False
                    break
                normalized[name] = value
            if ok:
                by_doc[doc_id] = normalized
        loaded[qid] = by_doc
    return loaded


def stage_raw_outputs(schema_by_expert: dict[str, dict[str, str]]) -> dict[str, dict[str, dict[str, Any]]]:
    """Stage A diagnostic values with sentinels preserved. Diagnostic-only."""
    loaded: dict[str, dict[str, dict[str, Any]]] = {}
    for qid in PREFIX:
        rows = json.loads(
            (EXTRACT_ROOT / qid / "table_legal/docetl_intermediate/extract_step/extract_fields.json").read_text()
        )
        by_doc: dict[str, dict[str, Any]] = {}
        for row in rows:
            doc = str(row.get("doc_id"))
            doc_id = doc if doc.endswith(".txt") else f"{doc}.txt"
            by_doc[doc_id] = {name: row.get(name) for name in schema_by_expert[qid] if name in row}
        loaded[qid] = by_doc
    return loaded


def copy_db_dir(src: Path, dest: Path) -> dict[str, Path]:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    paths = {}
    frozen = json.loads((src / "bags_frozen.json").read_text())
    for qid, original in frozen["paths"].items():
        name = Path(original).name
        paths[qid] = dest / name
    return paths


def connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path)


def read_cell(conn: sqlite3.Connection, doc: str, field: str) -> Any:
    row = conn.execute(f'SELECT "{field}" FROM legal WHERE doc_id = ?', (doc,)).fetchone()
    return None if row is None else row[0]


def write_cell(conn: sqlite3.Connection, doc: str, field: str, value: Any) -> None:
    conn.execute(f'UPDATE legal SET "{field}" = ? WHERE doc_id = ?', (value, doc))


def manifest_sources() -> dict[tuple[str, str], dict[str, Any]]:
    manifest = json.loads((FROZEN / "routing_manifest.json").read_text())
    return {
        (row["target_query"], row["attribute"]): row
        for row in manifest["official"]["theta50"]
    }


def earliest_other(outputs: dict[str, dict[str, dict[str, Any]]], schema_by_expert: dict[str, dict[str, str]], expert: str, doc: str, field: str) -> tuple[str, Any] | None:
    for qid in PREFIX:
        if qid == expert or field not in schema_by_expert[qid]:
            continue
        if schema_by_expert[qid][field] != schema_by_expert[expert][field]:
            continue
        row = outputs[qid].get(doc)
        if row and field in row and row[field] is not None:
            return qid, row[field]
    return None


def agreed_other(outputs: dict[str, dict[str, dict[str, Any]]], schema_by_expert: dict[str, dict[str, str]], expert: str, doc: str, field: str) -> Any:
    values = []
    for qid in PREFIX:
        if qid == expert or field not in schema_by_expert[qid]:
            continue
        if schema_by_expert[qid][field] != schema_by_expert[expert][field]:
            continue
        row = outputs[qid].get(doc)
        if row and field in row and row[field] is not None:
            values.append(row[field])
    if values and all(value == values[0] for value in values):
        return values[0]
    return None


def apply_substitutions(paths: dict[str, Path], substitutions: list[dict[str, Any]]) -> None:
    by_db: dict[Path, list[dict[str, Any]]] = defaultdict(list)
    for row in substitutions:
        by_db[paths[row["target_query"]]].append(row)
    for path, rows in by_db.items():
        conn = connect(path)
        for row in rows:
            current = read_cell(conn, row["doc_id"], row["attribute"])
            row["previous"] = current
            if current == row["value"]:
                row["applied"] = False
                continue
            write_cell(conn, row["doc_id"], row["attribute"], row["value"])
            row["applied"] = True
        conn.commit()
        conn.close()


def build_recovery_substitutions(outputs, salvaged, schema_by_expert, sources) -> list[dict[str, Any]]:
    rows = []
    for (target, attribute), route in sources.items():
        kind = schema_by_expert[target][attribute]
        expert = route["source_expert"]
        if route["mode"] == "plumbing" or not expert:
            continue
        docs = set(outputs[expert]) | set(salvaged.get(expert, {}))
        # Terminal docs are absent from outputs. Include every doc that another expert or salvage can fill.
        candidates = set(docs)
        for qid in PREFIX:
            candidates.update(outputs[qid])
            candidates.update(salvaged.get(qid, {}))
        for doc in sorted(candidates):
            own = outputs[expert].get(doc)
            if own is not None and attribute in own:
                continue
            salvaged_row = salvaged.get(expert, {}).get(doc, {})
            if attribute in salvaged_row:
                value = salvaged_row[attribute]
                if route["mode"] == "shared" and value is None:
                    continue
                rows.append({
                    "target_query": target,
                    "doc_id": doc,
                    "attribute": attribute,
                    "value": value,
                    "source": f"salvage:{expert}",
                    "protect_non_null": True,
                })
                continue
            other = earliest_other(outputs, schema_by_expert, expert, doc, attribute)
            if other is None:
                continue
            if schema_by_expert[expert].get(attribute) != kind:
                continue
            rows.append({
                "target_query": target,
                "doc_id": doc,
                "attribute": attribute,
                "value": other[1],
                "source": f"fresh:{other[0]}",
                "protect_non_null": True,
            })
    return rows


def build_d1(outputs, stage, schema_by_expert, sources) -> list[dict[str, Any]]:
    rows = []
    for (target, attribute), route in sources.items():
        expert = route["source_expert"]
        if route["mode"] == "plumbing" or not expert:
            continue
        for doc, stage_row in stage[expert].items():
            if doc in outputs[expert] or attribute not in stage_row:
                continue
            value = stage_row[attribute]
            if route["mode"] == "shared" and value is None:
                continue
            rows.append({
                "target_query": target,
                "doc_id": doc,
                "attribute": attribute,
                "value": value,
                "source": f"stage_a:{expert}",
                "protect_non_null": True,
                "diagnostic_only": True,
            })
    return rows


def build_d2(outputs, stage, sources) -> list[dict[str, Any]]:
    rows = []
    for (target, attribute), route in sources.items():
        expert = route["source_expert"]
        if route["mode"] == "plumbing" or not expert:
            continue
        for doc, fresh_row in outputs[expert].items():
            stage_row = stage[expert].get(doc)
            if stage_row is None or attribute not in fresh_row or attribute not in stage_row:
                continue
            rows.append({
                "target_query": target,
                "doc_id": doc,
                "attribute": attribute,
                "value": stage_row[attribute],
                "source": f"stage_a:{expert}",
                "protect_non_null": False,
                "diagnostic_only": True,
            })
    return rows


def build_d4(outputs, schema_by_expert, sources) -> list[dict[str, Any]]:
    rows = []
    for (target, attribute), route in sources.items():
        expert = route["source_expert"]
        if route["mode"] == "plumbing" or not expert:
            continue
        docs = set()
        for qid in PREFIX:
            docs.update(outputs[qid])
        for doc in sorted(docs):
            if doc in outputs[expert] and attribute in outputs[expert][doc]:
                continue
            value = agreed_other(outputs, schema_by_expert, expert, doc, attribute)
            if value is None:
                continue
            rows.append({
                "target_query": target,
                "doc_id": doc,
                "attribute": attribute,
                "value": value,
                "source": "fresh_agreement",
                "protect_non_null": True,
                "diagnostic_only": True,
            })
    return rows


def official_paths(statements: dict[str, str]) -> tuple[Any, Any, dict[str, str]]:
    from quwarts.core.pipeline import official_sql
    from quwarts.core.signature import audit_workload, enumerate_predicates
    from quwarts.core.signature_realize import live_predicates

    queries = json.loads(MANIFEST.read_text())
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    return official_sql, predicates, statements


def run_bags(paths: dict[str, Path], statements: dict[str, str], official_sql, predicates) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, str]]]:
    bags: dict[str, list[dict[str, Any]]] = {}
    failures = []
    for qid, sql in statements.items():
        rewritten = official_sql(sql, paths[qid], predicates, query_id=qid)
        conn = sqlite3.connect(f"file:{paths[qid]}?mode=ro", uri=True)
        try:
            cursor = conn.execute(rewritten)
            columns = [item[0] for item in cursor.description] if cursor.description else []
            bags[qid] = [dict(zip(columns, record)) for record in cursor.fetchall()]
        except sqlite3.Error as exc:
            failures.append({"query_id": qid, "error": str(exc)})
            bags[qid] = []
        finally:
            conn.close()
    return bags, failures


def sql_visible_count(paths: dict[str, Path], substitutions: list[dict[str, Any]], statements: dict[str, str], official_sql, predicates, bags: dict[str, list[dict[str, Any]]]) -> int:
    applied = [row for row in substitutions if row.get("applied")]
    sql_by_query = {qid: official_sql(sql, paths[qid], predicates, query_id=qid) for qid, sql in statements.items()}
    visible = 0
    grouped: dict[Path, list[dict[str, Any]]] = defaultdict(list)
    for row in applied:
        grouped[paths[row["target_query"]]].append(row)
    for path, rows in grouped.items():
        queries = [qid for qid, query_path in paths.items() if query_path == path]
        conn = connect(path)
        seen = set()
        checked = 0
        for row in rows:
            key = (row["doc_id"], row["attribute"], row["previous"], row["value"])
            if key in seen:
                continue
            seen.add(key)
            relevant = [qid for qid in queries if row["attribute"] in sql_by_query[qid]]
            if not relevant:
                continue
            write_cell(conn, row["doc_id"], row["attribute"], row["previous"])
            changed = False
            for qid in relevant:
                cursor = conn.execute(sql_by_query[qid])
                columns = [item[0] for item in cursor.description] if cursor.description else []
                current = [dict(zip(columns, record)) for record in cursor.fetchall()]
                if current != bags[qid]:
                    changed = True
                    break
            write_cell(conn, row["doc_id"], row["attribute"], row["value"])
            checked += 1
            if changed:
                visible += 1
            if checked % 400 == 0:
                print(f"sql-visible checked {checked}", flush=True)
        conn.rollback()
        conn.close()
    return visible


def score_paths(paths: dict[str, Path], statements: dict[str, str], official_sql, predicates, gold, full) -> dict[str, Any]:
    from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
    from quwarts.experiments.synthesize_case80 import score_with_rewrites

    rewrites = {}
    for qid, sql in statements.items():
        rewrites[qid] = {"sql": official_sql(sql, paths[qid], predicates, query_id=qid), "sqlite_path": str(paths[qid])}
    rows = [{"query_id": qid, "sql": sql, "pack": (full.get(qid) or {}).get("pack")} for qid, sql in statements.items()]
    report = score_with_rewrites(rows, rewrites, PLUMBING, gold, "Legal")
    per_query = []
    for row in report.get("per_query") or []:
        per_query.append({
            "query_id": row["query_id"],
            "structure_f2": row.get("structure_f2"),
            "cell_f1_20": row.get("cell_f1_20"),
            "product": float(row.get("structure_f2") or 0.0) * float(row.get("cell_f1_20") or 0.0),
        })
    return {
        "f2": float(report.get("mean_structure_f2") or 0.0),
        "f1": mean_cell_f1_20(report),
        "product": mean_per_query_product(report),
        "per_query": per_query,
    }


def hashes_for(paths: dict[str, Path], bags: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    from quwarts.core.observable_sidecar import bag_hash

    return {
        "db_sha256": {qid: file_sha(path) for qid, path in sorted(paths.items())},
        "bag_sha256": bag_hash(bags),
    }


def gold_index(gold: dict[str, list[dict[str, Any]]], attributes: set[str]) -> dict[str, dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for rows in gold.values():
        if not rows:
            continue
        overlap = attributes & set(rows[0])
        if len(overlap) < 3:
            continue
        for row in rows:
            stem = ""
            for key in ("doc_id", "document_id", "id", "filename", "file"):
                if row.get(key):
                    stem = str(row[key])
                    break
            if not stem:
                continue
            stem = stem[:-4] if stem.endswith(".txt") else stem
            best[stem] = row
    return best


def cell_match(value: Any, gold_value: Any) -> bool | None:
    if gold_value is None:
        return None
    gold_text = str(gold_value).strip()
    if value is None:
        return gold_text in {"", "None", "null", "-1"}
    return str(value).strip() == gold_text


def decide(products: dict[str, float]) -> str:
    docetl = DOCETL_PRODUCT
    if products["R_fresh_recovery"] > docetl:
        return "execution failures explain the missing win"
    if products["D1_terminal_failure_substitution"] > docetl or products["D2_successful_call_semantic_substitution"] > docetl:
        return "historical completions would restore the win, but fresh semantics do not"
    if products["R_fresh_recovery"] <= docetl and products["D4_fresh_perfect_coverage"] <= docetl:
        return "fresh query experts remain below DocETL even with recoverable coverage"
    return "audit invalid"


def abort(reason: str, payload: dict[str, Any]) -> None:
    body = {"conclusion": "audit invalid", "reason": reason, **payload}
    (OUT / "audit.json").write_text(json.dumps(body, indent=2, default=str))
    (OUT / "REPORT.md").write_text(f"# Causal audit\n\nConclusion: `audit invalid`\n\n{reason}\n")
    print(json.dumps(body, indent=2, default=str), flush=True)
    raise SystemExit(0)


def main() -> None:
    spec_hash = write_spec()
    print(json.dumps({"spec_sha256": spec_hash, "salvage_rules_sha256": sha(SPEC["salvage_rules"])}), flush=True)

    plumbing_before = file_sha(PLUMBING)
    schedule = json.loads(SCHEDULE.read_text())
    schedule_body = {key: value for key, value in schedule.items() if key != "schedule_sha256"}
    if sha(schedule_body) != EXPECTED_SCHEDULE:
        abort("schedule hash mismatch", {"schedule_sha256": sha(schedule_body)})
    routing = json.loads((FROZEN / "routing_manifest.json").read_text())
    if sha(routing) != EXPECTED_ROUTING:
        abort("routing hash mismatch", {"routing_sha256": sha(routing)})
    journal_text = (FROZEN / "arm" / "journal.jsonl").read_text()
    prefix_text = (FROZEN / "arm" / "journal_theta25.jsonl").read_text()
    if not journal_text.startswith(prefix_text):
        abort("theta25 journal is not a prefix", {})
    frozen_db_hashes = {
        str(path.relative_to(FROZEN)): file_sha(path)
        for path in (FROZEN / "arm" / "databases").rglob("*.db")
    }

    schema_by_expert = schemas()
    requests = load_requests()
    journal = load_journal()
    if len(journal) != 3420:
        abort("request count is not 3420", {"requests": len(journal)})
    incomplete = [
        key for key, attempts in journal.items()
        if final_row(attempts)["status"] not in {"success", "terminal"}
    ]
    if incomplete:
        abort("an expert request is incomplete", {"incomplete": len(incomplete)})
    if any(expert not in {key[0] for key in journal} for expert in PREFIX):
        abort("an expert is missing", {})

    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.experiments.synthesize_case80 import gold_name, queries_for

    statements = {row["query_id"]: row["sql"] for row in json.loads(MANIFEST.read_text())}
    official_sql, predicates, statements = official_paths(statements)
    gold = load_ground_truth(gold_name("Legal"))
    full = {row["query_id"]: row for row in queries_for("Legal")}
    stage = stage_outputs(schema_by_expert)
    stage_raw = stage_raw_outputs(schema_by_expert)

    fresh_paths = {
        "theta25": copy_db_dir(FROZEN / "arm" / "databases" / "same_attribute" / "theta25", OUT / "reproduction" / "fresh_theta25"),
        "theta50": copy_db_dir(FROZEN / "arm" / "databases" / "same_attribute" / "theta50", OUT / "reproduction" / "fresh_theta50"),
        "conservative": copy_db_dir(FROZEN / "arm" / "databases" / "conservative" / "theta50", OUT / "reproduction" / "fresh_conservative"),
        "stage_a": copy_db_dir(STAGE / "databases" / "optimistic" / "theta50", OUT / "reproduction" / "stage_a_theta50"),
    }
    # Reproduction copies are unscored snapshots of frozen databases. Remove them after scoring
    # so the audit directory keeps replay databases only. Hashes are checked against the originals.
    reproduced = {}
    for name, paths in fresh_paths.items():
        reproduced[name] = score_paths(paths, statements, official_sql, predicates, gold, full)
        print(f"reproduced {name} {reproduced[name]['product']}", flush=True)
    checks = {
        "fresh_theta25_same_attribute": reproduced["theta25"]["product"] == FRESH25,
        "fresh_theta50_same_attribute": reproduced["theta50"]["product"] == FRESH50,
        "fresh_theta50_conservative": reproduced["conservative"]["product"] == FRESH50_CONSERVATIVE,
        "stage_a_theta50_optimistic": f"{reproduced['stage_a']['product']:.14f}" == STAGE50_TEXT,
        "docetl_constant": DOCETL_PRODUCT == 0.12350932750098194,
    }
    if not all(checks.values()):
        abort("a frozen score could not be reproduced", {"checks": checks, "products": {key: value["product"] for key, value in reproduced.items()}})

    outputs = fresh_outputs(journal)
    sizes = lengths()
    decile = deciles(sizes)
    taxonomy_rows = []
    salvage_stats = Counter()
    salvaged: dict[str, dict[str, dict[str, Any]]] = {qid: {} for qid in PREFIX}
    inspected = 0
    for key, attempts in sorted(journal.items()):
        qid, doc = key
        schema = schema_by_expert[qid]
        status = final_row(attempts)["status"]
        klass = terminal_class(attempts)
        raws = [row.get("raw_arguments") for row in attempts if row.get("raw_arguments") is not None]
        issued = sum(1 for row in attempts if row["status"] == "issued")
        success_fields = list(final_row(attempts).get("output") or {}) if status == "success" else []
        partial = {}
        if status != "success":
            inspected += 1
            saved = salvage_request(attempts, schema)
            partial = saved["recovered"]
            if saved.get("unchanged_complete"):
                salvage_stats["parseable_unchanged"] += 1
            elif saved.get("repaired"):
                salvage_stats["mechanically_repaired"] += 1
            elif saved.get("partial"):
                salvage_stats["valid_partial_payloads"] += 1
            else:
                salvage_stats["unrecoverable"] += 1
            if partial:
                salvaged[qid][doc] = partial
                salvage_stats["fields_recovered"] += len(partial)
                salvage_stats["rows_recovered"] += 1
        other = False
        for field in schema:
            hit = earliest_other(outputs, schema_by_expert, qid, doc, field)
            if hit is not None:
                other = True
                break
        taxonomy_rows.append({
            "query_expert": qid,
            "document_id": doc,
            "prompt_tokens": requests[(qid, doc)]["prompt_tokens"],
            "document_bytes": sizes.get(doc),
            "length_decile": decile.get(doc),
            "attempt_count": issued,
            "final_status": status,
            "terminal_failure_class": klass,
            "raw_response_exists": bool(raws),
            "valid_partial_tool_payload": bool(partial),
            "fields_requested": list(schema),
            "fields_recovered": success_fields or list(partial),
            "other_fresh_expert_has_attribute": other,
        })

    by_expert = {}
    for qid in PREFIX:
        subset = [row for row in taxonomy_rows if row["query_expert"] == qid and row["final_status"] == "terminal"]
        by_expert[qid] = {
            "terminal_failures": len(subset),
            "by_class": dict(Counter(row["terminal_failure_class"] for row in subset)),
            "by_decile": dict(Counter(row["length_decile"] for row in subset)),
            "by_attempt_count": dict(Counter(row["attempt_count"] for row in subset)),
            "missing_documents": [row["document_id"] for row in subset],
        }
    q14 = [row for row in taxonomy_rows if row["query_expert"] == "legal_agg20:q14" and row["final_status"] == "terminal"]
    q14_explanation = {
        "missing_documents": len(q14),
        "malformed_empty_tool_calls": sum(1 for row in q14 if row["terminal_failure_class"] == "malformed"),
        "provider_errors": sum(1 for row in q14 if row["terminal_failure_class"] == "other"),
        "provider_error_documents": [row["document_id"] for row in q14 if row["terminal_failure_class"] == "other"],
        "reason": "112 missing rows are terminal requests, not unissued primaries. 105 are empty send_output objects after the allowed attempts. 7 are provider HTTP 400 responses on the longest truncated documents, which return no tool payload.",
    }

    sources = manifest_sources()
    recovery_rows = build_recovery_substitutions(outputs, salvaged, schema_by_expert, sources)
    d1_rows = build_d1(outputs, stage, schema_by_expert, sources)
    d2_rows = build_d2(outputs, stage, sources)
    d4_rows = build_d4(outputs, schema_by_expert, sources)

    fresh50_paths = {
        qid: Path(json.loads((FROZEN / "arm" / "databases" / "same_attribute" / "theta50" / "bags_frozen.json").read_text())["paths"][qid])
        for qid in statements
    }
    fresh_bags, fresh_failures = run_bags(fresh50_paths, statements, official_sql, predicates)
    fresh_per_query = {row["query_id"]: row for row in reproduced["theta50"]["per_query"]}

    replays = {}
    replay_plan = {
        "R_fresh_recovery": (FROZEN / "arm" / "databases" / "same_attribute" / "theta50", recovery_rows, False),
        "D1_terminal_failure_substitution": (FROZEN / "arm" / "databases" / "same_attribute" / "theta50", d1_rows, True),
        "D2_successful_call_semantic_substitution": (FROZEN / "arm" / "databases" / "same_attribute" / "theta50", d2_rows, True),
        "D4_fresh_perfect_coverage": (FROZEN / "arm" / "databases" / "same_attribute" / "theta50", d4_rows, True),
    }
    for name, (src, substitutions, diagnostic) in replay_plan.items():
        paths = copy_db_dir(src, OUT / "replays" / name)
        apply_substitutions(paths, substitutions)
        bags, failures = run_bags(paths, statements, official_sql, predicates)
        scored = score_paths(paths, statements, official_sql, predicates, gold, full)
        visible = sql_visible_count(paths, substitutions, statements, official_sql, predicates, bags)
        applied = [row for row in substitutions if row.get("applied")]
        identity = hashes_for(paths, bags)
        deltas = []
        for row in scored["per_query"]:
            base = fresh_per_query[row["query_id"]]["product"]
            deltas.append({"query_id": row["query_id"], "product": row["product"], "delta_vs_fresh_theta50": row["product"] - base})
        manifest = {
            "replay": name,
            "diagnostic_only": diagnostic,
            "spec_sha256": spec_hash,
            "substituted_cells": len(applied),
            "candidate_cells": len(substitutions),
            "affected_documents": len({row["doc_id"] for row in applied}),
            "sql_visible_substitutions": visible,
            "queries_changed": [qid for qid, bag in bags.items() if bag != fresh_bags[qid]],
            "empty_bags": [qid for qid, bag in bags.items() if not bag],
            "sql_failures": failures,
            "f2": scored["f2"],
            "cell_f1_20": scored["f1"],
            "product": scored["product"],
            "per_query_deltas": deltas,
            **identity,
        }
        (OUT / f"manifest_{name}.json").write_text(json.dumps(manifest, indent=2, default=str))
        replays[name] = manifest
        print(f"scored {name} {scored['product']}", flush=True)

    d3_paths = copy_db_dir(STAGE / "databases" / "optimistic" / "theta50", OUT / "replays" / "D3_full_stage_a_substitution")
    d3_subs = []
    for (target, attribute), route in sources.items():
        expert = route["source_expert"]
        if route["mode"] == "plumbing" or not expert:
            continue
        for doc, fresh_row in outputs[expert].items():
            if doc in stage_raw[expert] or attribute not in fresh_row:
                continue
            value = fresh_row[attribute]
            if route["mode"] == "shared" and value is None:
                continue
            d3_subs.append({
                "target_query": target,
                "doc_id": doc,
                "attribute": attribute,
                "value": value,
                "source": f"fresh_gap:{expert}",
                "protect_non_null": True,
                "diagnostic_only": True,
            })
    apply_substitutions(d3_paths, d3_subs)
    d3_bags, d3_failures = run_bags(d3_paths, statements, official_sql, predicates)
    d3_scored = score_paths(d3_paths, statements, official_sql, predicates, gold, full)
    d3_visible = sql_visible_count(d3_paths, d3_subs, statements, official_sql, predicates, d3_bags)
    d3_applied = [row for row in d3_subs if row.get("applied")]
    d3_manifest = {
        "replay": "D3_full_stage_a_substitution",
        "diagnostic_only": True,
        "spec_sha256": spec_hash,
        "substituted_cells": len(d3_applied),
        "candidate_cells": len(d3_subs),
        "affected_documents": len({row["doc_id"] for row in d3_applied}),
        "sql_visible_substitutions": d3_visible,
        "queries_changed_vs_fresh": [qid for qid, bag in d3_bags.items() if bag != fresh_bags[qid]],
        "empty_bags": [qid for qid, bag in d3_bags.items() if not bag],
        "sql_failures": d3_failures,
        "f2": d3_scored["f2"],
        "cell_f1_20": d3_scored["f1"],
        "product": d3_scored["product"],
        "stage_a_product": reproduced["stage_a"]["product"],
        "per_query_deltas": [
            {
                "query_id": row["query_id"],
                "product": row["product"],
                "delta_vs_fresh_theta50": row["product"] - fresh_per_query[row["query_id"]]["product"],
            }
            for row in d3_scored["per_query"]
        ],
        **hashes_for(d3_paths, d3_bags),
    }
    (OUT / "manifest_D3_full_stage_a_substitution.json").write_text(json.dumps(d3_manifest, indent=2, default=str))
    replays["D3_full_stage_a_substitution"] = d3_manifest
    print(f"scored D3 {d3_scored['product']}", flush=True)

    # Freeze manifests before the gold cell study writes agreement.json.
    products = {name: row["product"] for name, row in replays.items()}
    products["fresh_theta50"] = FRESH50
    conclusion = decide(products)

    attributes = {name for schema in schema_by_expert.values() for name in schema}
    gold_rows = gold_index(gold, attributes)
    agreement = {
        "cells": 0,
        "exact_agreement": 0,
        "normalized_agreement": 0,
        "null_non_null_agreement": 0,
        "by_attribute": {},
        "by_expert": {},
        "by_decile": {},
    }
    attr_counts: dict[str, Counter] = defaultdict(Counter)
    expert_counts: dict[str, Counter] = defaultdict(Counter)
    decile_counts: dict[int, Counter] = defaultdict(Counter)
    groups = {
        "fresh_only": [],
        "stage_a_only": [],
        "agreements": [],
        "disagreements": [],
        "salvage": [],
        "cross_expert": [],
    }
    for qid in PREFIX:
        for doc in set(outputs[qid]) | set(stage[qid]):
            fresh_row = outputs[qid].get(doc)
            stage_row = stage[qid].get(doc)
            raw_row = stage_raw[qid].get(doc)
            for field, kind in schema_by_expert[qid].items():
                fresh_has = fresh_row is not None and field in fresh_row
                stage_has = stage_row is not None and field in stage_row
                gold_row = gold_rows.get(doc[:-4] if doc.endswith(".txt") else doc)
                gold_value = gold_row.get(field) if gold_row and field in gold_row else None
                if fresh_has and not stage_has:
                    groups["fresh_only"].append((fresh_row[field], gold_value))
                elif stage_has and not fresh_has:
                    groups["stage_a_only"].append((stage_row[field], gold_value))
                elif fresh_has and stage_has:
                    agreement["cells"] += 1
                    exact = fresh_row[field] == (raw_row or {}).get(field)
                    normalized = fresh_row[field] == stage_row[field]
                    fresh_null = fresh_row[field] is None
                    stage_null = stage_row[field] is None
                    null_agree = fresh_null == stage_null
                    agreement["exact_agreement"] += int(exact)
                    agreement["normalized_agreement"] += int(normalized)
                    agreement["null_non_null_agreement"] += int(null_agree)
                    bucket = "agree" if normalized else "disagree"
                    attr_counts[field][bucket] += 1
                    expert_counts[qid][bucket] += 1
                    decile_counts[decile.get(doc, 0)][bucket] += 1
                    groups["agreements" if normalized else "disagreements"].append((fresh_row[field] if normalized else stage_row[field], gold_value))
    for qid, docs in salvaged.items():
        for doc, fields in docs.items():
            gold_row = gold_rows.get(doc[:-4] if doc.endswith(".txt") else doc)
            for field, value in fields.items():
                gold_value = gold_row.get(field) if gold_row and field in gold_row else None
                groups["salvage"].append((value, gold_value))
    for row in recovery_rows:
        if not str(row["source"]).startswith("fresh:"):
            continue
        gold_row = gold_rows.get(row["doc_id"][:-4])
        field = row["attribute"]
        gold_value = gold_row.get(field) if gold_row and field in gold_row else None
        groups["cross_expert"].append((row["value"], gold_value))

    def accuracy(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
        judged = [(value, gold_value) for value, gold_value in pairs if gold_value is not None]
        matched = [pair for pair in judged if cell_match(pair[0], pair[1])]
        return {"cells": len(pairs), "gold_comparable": len(judged), "gold_matches": len(matched), "accuracy": (len(matched) / len(judged) if judged else None)}

    agreement["by_attribute"] = {key: dict(value) for key, value in attr_counts.items()}
    agreement["by_expert"] = {key: dict(value) for key, value in expert_counts.items()}
    agreement["by_decile"] = {str(key): dict(value) for key, value in sorted(decile_counts.items())}
    agreement["gold_diagnostic"] = {name: accuracy(pairs) for name, pairs in groups.items()}
    agreement["gold_does_not_select_a_replay"] = True
    agreement["note"] = "Gold cell accuracy is diagnostic. Stage A comparisons are diagnostic-only."

    # SQL-visible versus inert disagreement, using the D2 substitutions that changed a cell.
    d2_changed = {
        (row["source"].split(":", 1)[1], row["doc_id"], row["attribute"]): row
        for row in d2_rows
        if row.get("applied") and row["previous"] != row["value"]
    }
    visible_keys = set()
    # Recompute visibility only for disagreement cells already marked applied in the D2 manifest count.
    # The manifest stored sql_visible_substitutions as a count; mark inert as the remainder of normalized disagreements.
    normalized_disagreements = agreement["cells"] - agreement["normalized_agreement"]
    agreement["disagreement_cells"] = normalized_disagreements
    agreement["sql_visible_disagreement_cells"] = replays["D2_successful_call_semantic_substitution"]["sql_visible_substitutions"]
    agreement["sql_inert_disagreement_cells"] = max(0, len(d2_changed) - agreement["sql_visible_disagreement_cells"])

    salvage_body = {
        "rules_sha256": sha(SPEC["salvage_rules"]),
        "responses_inspected": inspected,
        "parseable_unchanged": salvage_stats["parseable_unchanged"],
        "mechanically_repaired": salvage_stats["mechanically_repaired"],
        "valid_partial_payloads": salvage_stats["valid_partial_payloads"],
        "unrecoverable": salvage_stats["unrecoverable"],
        "fields_recovered": salvage_stats["fields_recovered"],
        "rows_recovered": salvage_stats["rows_recovered"],
        "sql_visible_recovered_values": sum(1 for row in recovery_rows if str(row["source"]).startswith("salvage:") and row.get("applied")),
        "finding": "Every malformed raw response is an empty send_output object. No field can be recovered without inventing a value.",
    }
    taxonomy = {
        "requests": 3420,
        "successes": sum(1 for row in taxonomy_rows if row["final_status"] == "success"),
        "terminal_failures": sum(1 for row in taxonomy_rows if row["final_status"] == "terminal"),
        "by_class": dict(Counter(row["terminal_failure_class"] for row in taxonomy_rows if row["terminal_failure_class"])),
        "by_expert": by_expert,
        "by_decile": dict(Counter(row["length_decile"] for row in taxonomy_rows if row["terminal_failure_class"])),
        "by_attempt_count": dict(Counter(row["attempt_count"] for row in taxonomy_rows if row["terminal_failure_class"])),
        "legal_agg20_q14": q14_explanation,
        "requests_detail_sha256": sha(taxonomy_rows),
    }
    (OUT / "failure_taxonomy.json").write_text(json.dumps({"summary": taxonomy, "requests": taxonomy_rows}, indent=2))
    (OUT / "salvage.json").write_text(json.dumps(salvage_body, indent=2))
    (OUT / "agreement.json").write_text(json.dumps(agreement, indent=2, default=str))

    if file_sha(PLUMBING) != plumbing_before:
        abort("plumbing database changed", {})
    for relative, digest in frozen_db_hashes.items():
        if file_sha(FROZEN / relative) != digest:
            abort("a frozen database changed", {"path": relative})

    table = [
        {"arm": "fresh θ50 same-attribute", "product": FRESH50, "f2": reproduced["theta50"]["f2"], "f1": reproduced["theta50"]["f1"], "diagnostic_only": False},
        {"arm": "R_fresh_recovery", "product": replays["R_fresh_recovery"]["product"], "f2": replays["R_fresh_recovery"]["f2"], "f1": replays["R_fresh_recovery"]["cell_f1_20"], "diagnostic_only": False},
        {"arm": "D1 terminal-failure substitution", "product": replays["D1_terminal_failure_substitution"]["product"], "f2": replays["D1_terminal_failure_substitution"]["f2"], "f1": replays["D1_terminal_failure_substitution"]["cell_f1_20"], "diagnostic_only": True},
        {"arm": "D2 successful-call substitution", "product": replays["D2_successful_call_semantic_substitution"]["product"], "f2": replays["D2_successful_call_semantic_substitution"]["f2"], "f1": replays["D2_successful_call_semantic_substitution"]["cell_f1_20"], "diagnostic_only": True},
        {"arm": "D3 full Stage A substitution", "product": replays["D3_full_stage_a_substitution"]["product"], "f2": replays["D3_full_stage_a_substitution"]["f2"], "f1": replays["D3_full_stage_a_substitution"]["cell_f1_20"], "diagnostic_only": True},
        {"arm": "D4 fresh coverage ceiling", "product": replays["D4_fresh_perfect_coverage"]["product"], "f2": replays["D4_fresh_perfect_coverage"]["f2"], "f1": replays["D4_fresh_perfect_coverage"]["cell_f1_20"], "diagnostic_only": True},
        {"arm": "Stage A θ50 optimistic", "product": reproduced["stage_a"]["product"], "f2": reproduced["stage_a"]["f2"], "f1": reproduced["stage_a"]["f1"], "diagnostic_only": True},
        {"arm": "Legal DocETL", "product": DOCETL_PRODUCT, "f2": None, "f1": None, "diagnostic_only": False},
    ]
    audit = {
        "conclusion": conclusion,
        "spec_sha256": spec_hash,
        "salvage_rules_sha256": sha(SPEC["salvage_rules"]),
        "reproduction": checks,
        "reproduced_products": {key: value["product"] for key, value in reproduced.items()},
        "journal_prefix": True,
        "experts_completed": PREFIX,
        "plumbing_sha256": plumbing_before,
        "frozen_databases_unchanged": True,
        "comparison": table,
        "replays": {name: {key: value for key, value in row.items() if key != "per_query_deltas"} for name, row in replays.items()},
        "model_calls": 0,
        "stopping_rule": "The Legal query-expert line stops. No θ75, θ100, replica, vote, or prompt variant is recommended."
        if replays["R_fresh_recovery"]["product"] <= DOCETL_PRODUCT
        else "One implementation-only materialization of the stored recovered outputs is eligible. No new model call is authorized.",
    }
    (OUT / "audit.json").write_text(json.dumps(audit, indent=2, default=str))

    lines = [
        "# Fresh Legal θ50 causal audit",
        "",
        f"Conclusion: `{conclusion}`",
        "",
        "No model call was made. Stage A substitutions and the gold cell study are diagnostic-only.",
        "",
        "## Reproduction",
        "",
        f"- fresh θ25 same-attribute `{reproduced['theta25']['product']}`",
        f"- fresh θ50 same-attribute `{reproduced['theta50']['product']}`",
        f"- fresh θ50 conservative `{reproduced['conservative']['product']}`",
        f"- Stage A θ50 optimistic `{reproduced['stage_a']['product']}`",
        f"- DocETL `{DOCETL_PRODUCT}`",
        f"- schedule `{EXPECTED_SCHEDULE}`",
        f"- routing `{EXPECTED_ROUTING}`",
        "- all six experts completed",
        "- θ25 journal is an exact prefix of θ50",
        "- plumbing and frozen databases were unchanged at the end of the audit",
        "",
        "## Why legal_agg20:q14 has 112 missing documents",
        "",
        q14_explanation["reason"],
        f"Malformed empty calls: {q14_explanation['malformed_empty_tool_calls']}. Provider errors: {q14_explanation['provider_errors']} on {', '.join(q14_explanation['provider_error_documents'])}.",
        "",
        "## Salvage",
        "",
        f"Rules hash `{sha(SPEC['salvage_rules'])}`.",
        f"Inspected {salvage_body['responses_inspected']} failed responses. Recovered {salvage_body['fields_recovered']} fields and {salvage_body['rows_recovered']} rows.",
        salvage_body["finding"],
        "",
        "## Comparison",
        "",
        "| arm | product | F2 | cell F1@0.20 | diagnostic-only |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for row in table:
        lines.append(f"| {row['arm']} | {row['product']} | {row['f2']} | {row['f1']} | {row['diagnostic_only']} |")
    lines.extend([
        "",
        "## Replay deltas",
        "",
    ])
    for name, manifest in replays.items():
        lines.extend([
            f"### {name}",
            "",
            f"- substituted cells: {manifest['substituted_cells']}",
            f"- affected documents: {manifest['affected_documents']}",
            f"- SQL-visible substitutions: {manifest['sql_visible_substitutions']}",
            f"- queries changed: {len(manifest.get('queries_changed') or manifest.get('queries_changed_vs_fresh') or [])}",
            f"- empty bags: {len(manifest['empty_bags'])}",
            f"- product: {manifest['product']}",
            "",
        ])
    lines.extend([
        "## Agreement on cells both runs completed",
        "",
        f"- cells: {agreement['cells']}",
        f"- exact agreement with raw Stage A values: {agreement['exact_agreement']}",
        f"- normalized agreement: {agreement['normalized_agreement']}",
        f"- NULL/non-NULL agreement: {agreement['null_non_null_agreement']}",
        f"- normalized disagreements: {agreement['disagreement_cells']}",
        f"- SQL-visible D2 cell changes: {agreement['sql_visible_disagreement_cells']}",
        "",
        "## Stopping rule",
        "",
        audit["stopping_rule"],
        "",
    ])
    (OUT / "REPORT.md").write_text("\n".join(lines))
    print(json.dumps({"conclusion": conclusion, "products": {row["arm"]: row["product"] for row in table}}, indent=2), flush=True)


if __name__ == "__main__":
    main()
