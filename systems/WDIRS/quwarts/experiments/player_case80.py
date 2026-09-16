"""Player case-study 80/20 eval on source_data/Player with OpenRouter Qwen.

Corpus and queries match ``case study/``: Wikipedia-style
``source_data/Player/{player,team,owner,city}`` and the five 20-query packs
(player_agg20 + join/groupby/multiagg/filterjoin). Gold is ``Data/Player``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.ledger import TokenLedger
from quwarts.core.llm.openrouter import DEFAULT_MODEL, load_env_file, make_caller
from quwarts.experiments.extract_util import schema_context

load_env_file(ROOT / ".env")

CASE = ROOT / "case study"
CORPUS = ROOT / "source_data" / "Player"
GOLD_DIR = ROOT / "Data" / "Player"
ATTR_PATH = ROOT / "Query" / "Player" / "Player_attributes.json"

PACKS = [
    CASE / "docetl_Player_v7" / "query_manifest.json",
    CASE / "workloads" / "player_join20" / "query_manifest.json",
    CASE / "workloads" / "player_groupby20" / "query_manifest.json",
    CASE / "workloads" / "player_multiagg20" / "query_manifest.json",
    CASE / "workloads" / "player_filterjoin20" / "query_manifest.json",
]

ENTITY_FIELDS = {
    "player": [
        "name", "birth_date", "nationality", "age", "team", "position",
        "draft_pick", "draft_year", "college", "nba_championships",
        "mvp_awards", "olympic_gold_medals", "fiba_world_cup",
    ],
    "team": ["team_name", "founded_year", "location", "ownership", "championship"],
    "owner": ["name", "age", "nationality", "nba_team", "own_year"],
    "city": ["city_name", "state_name", "population", "area", "gdp"],
}

NUMERIC = {
    "age", "draft_pick", "draft_year", "nba_championships", "mvp_awards",
    "olympic_gold_medals", "fiba_world_cup", "founded_year", "championship",
    "own_year", "population", "area", "gdp",
}

FRONTCOURT = {"forward", "center", "power forward", "small forward", "pf", "sf", "c", "frontcourt"}
BACKCOURT = {"guard", "point guard", "shooting guard", "pg", "sg", "g", "backcourt"}


def load_queries() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in PACKS:
        payload = json.loads(path.read_text())
        pack = path.parent.name
        for index, row in enumerate(payload):
            sql = str(row.get("sql") or "").strip()
            if not sql or sql in seen:
                continue
            seen.add(sql)
            rows.append({
                "query_id": f"{pack}:{row.get('query_id', f'q{index}')}",
                "sql": sql,
                "pack": pack,
            })
    return rows


def split_80_20(rows: list[dict[str, str]], seed: int) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    ordered = list(rows)
    random.Random(seed).shuffle(ordered)
    cut = int(round(0.8 * len(ordered)))
    return ordered[:cut], ordered[cut:]


def load_documents() -> list[dict[str, str]]:
    docs = []
    for entity in ("city", "owner", "team", "player"):
        folder = CORPUS / entity
        for path in sorted(folder.glob("*.txt")):
            docs.append({
                "doc_id": f"{entity}/{path.name}",
                "entity": entity,
                "text": path.read_text(encoding="utf-8", errors="replace"),
            })
    return docs


def useful_context(text: str, fields: list[str] | None = None, limit: int = 7000) -> str:
    return schema_context(text, fields or [], limit=limit)


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            return {}
        try:
            payload = json.loads(match.group())
        except json.JSONDecodeError:
            try:
                from json_repair import repair_json
                payload = json.loads(repair_json(match.group()))
            except Exception:
                return {}
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    return payload if isinstance(payload, dict) else {}


def _as_scalar(value: Any) -> Any:
    if isinstance(value, list):
        value = next((item for item in value if item not in (None, "")), None)
    if isinstance(value, dict):
        for key in ("name", "team_name", "city_name", "value"):
            if value.get(key) not in (None, ""):
                return value[key]
        return None
    return value


def coerce(entity: str, row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field in ENTITY_FIELDS[entity]:
        value = _as_scalar(row.get(field))
        if value in ("", "null", "None", "unknown", "n/a", "N/A", -1, "-1"):
            value = None
        if field == "position" and value:
            token = str(value).strip().lower()
            if token in FRONTCOURT or any(part in token for part in FRONTCOURT):
                value = "Frontcourt"
            elif token in BACKCOURT or any(part in token for part in BACKCOURT):
                value = "Backcourt"
            else:
                value = None
        if field in NUMERIC and value is not None:
            text = str(value).replace(",", "").replace("$", "").strip()
            match = re.search(r"-?\d+(?:\.\d+)?", text)
            if match:
                number = match.group()
                value = float(number) if "." in number else int(number)
            else:
                value = None
        if isinstance(value, str):
            value = value.strip() or None
        out[field] = value
    return out


def prompt_for(entity: str, text: str, hints: dict[str, list[str]]) -> str:
    fields = ENTITY_FIELDS[entity]
    extra = ""
    if entity == "player" and hints.get("teams"):
        extra = "Known team names (copy one exactly if present): " + ", ".join(hints["teams"][:40])
    if entity == "team" and hints.get("cities"):
        extra = "Known cities: " + ", ".join(hints["cities"][:40])
    if entity == "team" and hints.get("owners"):
        extra += "\nKnown owners: " + ", ".join(hints["owners"][:40])
    if entity == "owner" and hints.get("teams"):
        extra = "Known team names: " + ", ".join(hints["teams"][:40])
    instructions = {
        "player": (
            "This is one basketball player biography. Extract that player only. "
            "position must be Frontcourt or Backcourt (forwards/centers = Frontcourt, "
            "guards = Backcourt). Use 0 when the document says the player won none. "
            "birth_date as YYYY/M/D if possible."
        ),
        "team": (
            "This is one NBA franchise article. Extract that team only. "
            "championship is the number of NBA titles. location is the current city."
        ),
        "owner": "This is about an NBA team owner. nba_team is the franchise they own.",
        "city": "This is a city article. Extract city_name, state_name, population, area, gdp.",
    }
    return (
        f"{instructions[entity]}\n{extra}\n"
        f"Return a single JSON object with keys: {fields}.\n"
        f"Use null when the document does not state a value.\n\nDOCUMENT:\n{text}"
    )


def cache_key(entity: str, doc_id: str, model: str, text: str) -> str:
    payload = f"{entity}|{doc_id}|{model}|{hashlib.sha256(text.encode()).hexdigest()}"
    return hashlib.sha256(payload.encode()).hexdigest()


def extract_one(caller, entity: str, doc: dict[str, str], hints: dict[str, list[str]], cache_dir: Path, model: str) -> dict[str, Any]:
    context = useful_context(doc["text"], ENTITY_FIELDS[entity])
    key = cache_key(entity, doc["doc_id"], model, context)
    path = cache_dir / f"{key}.json"
    if path.exists():
        cached = json.loads(path.read_text())
        doc_id = cached.get("_doc_id", doc["doc_id"])
        row = coerce(entity, cached)
        row["_doc_id"] = doc_id
        return row
    text = caller.complete(
        prompt_for(entity, context, hints),
        purpose="extract",
        attribute=entity,
        model=model,
        system="Extract grounded JSON facts. No commentary.",
    )
    row = coerce(entity, parse_json_object(text))
    row["_doc_id"] = doc["doc_id"]
    path.write_text(json.dumps(row, ensure_ascii=False, indent=2))
    return row


def align_names(value: Any, candidates: list[str]) -> str | None:
    value = _as_scalar(value)
    if not value:
        return None
    compact = re.sub(r"\s+", " ", str(value)).strip()
    lookup = {re.sub(r"\s+", " ", item).strip().lower(): item for item in candidates if item}
    if compact.lower() in lookup:
        return lookup[compact.lower()]
    for key, item in lookup.items():
        if compact.lower() in key or key in compact.lower():
            return item
    return compact


def materialize(tables: dict[str, list[dict[str, Any]]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        for table, rows in tables.items():
            fields = ENTITY_FIELDS[table]
            cols = ", ".join(f'"{field}" TEXT' for field in fields)
            conn.execute(f'CREATE TABLE "{table}" ({cols})')
            marks = ", ".join("?" for _ in fields)
            for row in rows:
                conn.execute(
                    f'INSERT INTO "{table}" VALUES ({marks})',
                    [None if row.get(field) is None else str(row.get(field)) for field in fields],
                )
        conn.commit()
    finally:
        conn.close()
    return path


def load_gold() -> dict[str, list[dict[str, Any]]]:
    sys.path.insert(0, str(WDIRS))
    from diagnostics.run_config_grid import load_ground_truth
    return load_ground_truth("Player")


def execute(conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    try:
        cur = conn.execute(sql)
        cols = [item[0] for item in cur.description] if cur.description else []
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    except sqlite3.Error:
        return []


def score_split(
    test_rows: list[dict[str, str]],
    pred_db: Path,
    gold_tables: dict[str, list[dict[str, Any]]],
    *,
    dataset: str = "Player",
) -> dict[str, Any]:
    sys.path.insert(0, str(WDIRS))
    from diagnostics.run_config_grid import load_attributes
    from spp.aggregation_metrics import (
        MetricConfig,
        evaluate_aggregation_tables,
        gold_table_from_sql,
        json_ready_metrics,
        predicted_table_from_rows,
        schema_from_sql,
    )
    from spp.config_grid import _build_in_memory_db, official_query_error

    attributes = load_attributes(dataset)
    gold_conn = _build_in_memory_db(gold_tables)
    pred_conn = sqlite3.connect(pred_db)
    config = MetricConfig()
    per_query = []
    official = []
    structure = []
    cell = []
    query_scores = []
    for row in test_rows:
        sql = row["sql"]
        if "pred_sql" in row:
            pred_sql = row.get("pred_sql")
        else:
            pred_sql = sql
        gold_rows = execute(gold_conn, sql)
        query_db = row.get("pred_db")
        local = sqlite3.connect(query_db) if query_db else pred_conn
        try:
            pred_rows = execute(local, pred_sql) if pred_sql else []
        finally:
            if query_db:
                local.close()
        err = official_query_error(sql, gold_rows, pred_rows, attributes)
        acc = 1.0 - float(err)
        official.append(acc)
        item = {
            "query_id": row["query_id"],
            "pack": row["pack"],
            "official_accuracy": acc,
            "gold_rows": len(gold_rows),
            "pred_rows": len(pred_rows),
        }
        schema = schema_from_sql(sql)
        if schema.get("is_aggregation"):
            try:
                gold = gold_table_from_sql(gold_rows, sql)
                pred = predicted_table_from_rows(pred_rows, gold=gold)
                metrics = json_ready_metrics(evaluate_aggregation_tables(pred, gold, config=config))
                s = float(metrics["rank"]["structure_fbeta_score"])
                cell_map = metrics["rank"]["cell_f1"]
                query_map = metrics["rank"]["query_score"]
                cell_key = next(
                    (key for key in cell_map if abs(float(key) - 0.05) < 1e-9),
                    next(iter(cell_map)),
                )
                query_key = next(
                    (key for key in query_map if abs(float(key) - 0.05) < 1e-9),
                    next(iter(query_map)),
                )
                c = float(cell_map[cell_key])
                q = float(query_map[query_key])
                item.update({
                    "structure_f2": s,
                    "cell_f1_05": c,
                    "query_score_05": q,
                })
                structure.append(s)
                cell.append(c)
                query_scores.append(q)
            except Exception as exc:  # noqa: BLE001
                item["metric_error"] = str(exc)
        per_query.append(item)
    pred_conn.close()
    gold_conn.close()

    def mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    return {
        "n_test": len(test_rows),
        "mean_official_accuracy": mean(official),
        "mean_structure_f2": mean(structure),
        "mean_cell_f1_05": mean(cell),
        "mean_query_score_05": mean(query_scores),
        "per_query": per_query,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    out = Path(args.output)
    cache_dir = out / "extract_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    queries = load_queries()
    train, test = split_80_20(queries, args.seed)
    documents = load_documents()
    ledger = TokenLedger(theta=args.budget, seed=args.seed)
    caller = make_caller(ledger, model=args.model, max_tokens=700)

    grouped: dict[str, list[dict[str, str]]] = {"city": [], "owner": [], "team": [], "player": []}
    for doc in documents:
        grouped[doc["entity"]].append(doc)

    tables: dict[str, list[dict[str, Any]]] = {name: [] for name in ENTITY_FIELDS}
    hints: dict[str, list[str]] = {"cities": [], "teams": [], "owners": []}

    def extract_group(entity: str) -> list[dict[str, Any]]:
        rows = []
        docs = grouped[entity]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [
                pool.submit(extract_one, caller, entity, doc, hints, cache_dir, args.model)
                for doc in docs
            ]
            for future in as_completed(futures):
                rows.append(future.result())
        return rows

    print(f"corpus={CORPUS} docs={len(documents)} queries={len(queries)} train={len(train)} test={len(test)}", flush=True)
    tables["city"] = extract_group("city")
    hints["cities"] = [row.get("city_name") for row in tables["city"] if row.get("city_name")]
    tables["owner"] = extract_group("owner")
    hints["owners"] = [row.get("name") for row in tables["owner"] if row.get("name")]
    tables["team"] = extract_group("team")
    for row in tables["team"]:
        row["location"] = align_names(row.get("location"), hints["cities"])
        row["ownership"] = align_names(row.get("ownership"), hints["owners"])
    hints["teams"] = [row.get("team_name") for row in tables["team"] if row.get("team_name")]
    tables["player"] = extract_group("player")
    for row in tables["player"]:
        row["team"] = align_names(row.get("team"), hints["teams"])

    db_path = materialize(tables, out / "player.sqlite")
    counts = {name: len(rows) for name, rows in tables.items()}
    report = score_split(test, db_path, load_gold())
    summary = {
        "corpus": str(CORPUS),
        "model": args.model,
        "seed": args.seed,
        "train_ids": [row["query_id"] for row in train],
        "test_ids": [row["query_id"] for row in test],
        "row_counts": counts,
        "tokens_spent": ledger.spent,
        "theta": ledger.theta,
        **report,
    }
    (out / "report.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps({
        "mean_official_accuracy": summary["mean_official_accuracy"],
        "mean_structure_f2": summary["mean_structure_f2"],
        "mean_cell_f1_05": summary["mean_cell_f1_05"],
        "mean_query_score_05": summary["mean_query_score_05"],
        "tokens_spent": summary["tokens_spent"],
        "row_counts": counts,
    }, indent=2), flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "quwarts_player_case80")
    parser.add_argument("--budget", type=int, default=2_000_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
