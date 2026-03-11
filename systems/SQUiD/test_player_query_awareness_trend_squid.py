"""
Run Q1..Q10 query-awareness trend evaluation on Player using SQUiD.

SQUiD is an offline system that synthesizes relational databases from
unstructured text via a four-stage pipeline:
  1) Schema Generation   – infer relational schema from text
  2) Value Identification – extract triplets (symbolic + LLM)
  3) Table Population     – align triplets with schema to form tuples
  4) Database Materialization – build SQLite databases

This script:
  - Optionally runs the SQUiD preprocessing pipeline (--run-preprocessing)
  - Consolidates per-document SQUiD databases into a single unified DB
  - Runs Q1..Q10 trend queries against the consolidated DB
  - Evaluates using the standard evaluation framework
  - Saves per-query metrics and generates summary plots
"""

import csv
import json
import logging
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import argparse
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except Exception:
    MATPLOTLIB_AVAILABLE = False

import pandas as pd
import yaml

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
SQUID_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = SQUID_ROOT.parent.parent

sys.path.insert(0, str(SQUID_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "systems" / "WDIRS"))
sys.path.insert(0, str(PROJECT_ROOT))

from utils import extract_schema as _extract_schema, extract_from_output as _extract_from_output
from database_generation import (
    create_database as _create_database,
    generate_mysql_from_schema_and_values_baseline as _gen_sql_from_schema_values,
)

from evaluation.config import EvalSettings as _EvalSettings, load_json as _load_json
from evaluation.gt_runner import GtRunner as _GtRunner
from evaluation.metrics import MetricCalculator as _MetricCalculator
from evaluation.query_manifest import QueryManifest as _QueryManifest
from evaluation.result_writer import ResultWriter as _ResultWriter
from evaluation.row_matcher import RowMatcher as _RowMatcher
from evaluation.sql_parser import SqlParser as _SqlParser
from evaluation.utils import (
    add_missing_columns as _add_missing_cols,
    clean_string_columns as _clean_string_cols,
    drop_unnamed_columns as _drop_unnamed,
    normalize_file_name_columns as _norm_file_cols,
    normalize_types as _norm_types,
    standardize_column_name as _std_col,
)

try:
    import sqlglot
    import sqlglot.expressions as _sqlglot_exp
    SQLGLOT_AVAILABLE = True
except ImportError:
    SQLGLOT_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DATASET = "Player"
QUERY_DIR = PROJECT_ROOT / "Query"
TREND_SQL_FILE = QUERY_DIR / DATASET / "query_aware_trend_queries.sql"
GROUND_TRUTH_DIR = PROJECT_ROOT / "Data" / "Player"
ATTRIBUTES_FILE = QUERY_DIR / DATASET / "Player_attributes.json"
RESULTS_BASE_DIR = SQUID_ROOT / "results" / "player_query_awareness_trend_squid"

SQUID_DB_ROOT = SQUID_ROOT / "databases" / "Player"
SQUID_RESULTS_ROOT = SQUID_ROOT / "results"

ENTITY_TYPES = ["player", "team", "city"]
SQUID_METHODS = ["TS", "TST", "TST-L"]

SQUID_REWRITTEN_QUERIES = {
    "Q1": "SELECT player.full_name AS name, player.nationality, player.age, team.name AS team_name, team.location FROM player JOIN team ON player.current_team = team.name;",
    "Q2": "SELECT player.full_name AS name, player.position, team.name AS team_name, team.founded_year FROM player JOIN team ON player.current_team = team.name WHERE player.age > 25;",
    "Q3": "SELECT player.full_name AS name, player.draft_pick, player.college, team.name AS team_name FROM player JOIN team ON player.current_team = team.name WHERE player.draft_pick >= 0;",
    "Q4": "SELECT team.name AS team_name, team.location, team.location AS city_name, NULL AS state_name FROM team WHERE team.location IS NOT NULL;",
    "Q5": "SELECT player.full_name AS name, team.name AS team_name, team.location AS city_name, NULL AS state_name FROM player JOIN team ON player.current_team = team.name WHERE team.location IS NOT NULL;",
    "Q6": "SELECT player.full_name AS name, player.position, team.location AS city_name, NULL AS population FROM player JOIN team ON player.current_team = team.name WHERE player.age < 35 AND team.location IS NOT NULL;",
    "Q7": "SELECT player.full_name AS name, player.college, team.name AS team_name, NULL AS gdp FROM player JOIN team ON player.current_team = team.name WHERE player.draft_pick > 0 AND team.location IS NOT NULL;",
    "Q8": "SELECT player.full_name AS name, player.birth_date, team.name AS team_name, NULL AS area FROM player JOIN team ON player.current_team = team.name WHERE NULL > 100 AND team.location IS NOT NULL;",
    "Q9": "SELECT team.location AS city_name, NULL AS state_name, team.name AS team_name, player.full_name AS name FROM team JOIN player ON player.current_team = team.name WHERE player.age < 40 AND team.location IS NOT NULL;",
    "Q10": "SELECT team.location AS city_name, NULL AS state_name, team.name AS team_name, player.full_name AS name, player.college FROM team JOIN player ON player.current_team = team.name WHERE player.age > 20 AND team.location IS NOT NULL;"
}

_ENTITY_SUFFIX_RE = re.compile(r"\b(jr\.?|sr\.?|iii|iv|ii)\b\.?", re.IGNORECASE)
_NAME_LIKE_COLUMNS = {"name", "player_name", "team_name", "city_name", "owner_name"}


# ---------------------------------------------------------------------------
# Fuzzy name alignment (shared with other test scripts)
# ---------------------------------------------------------------------------
def _strip_diacritics(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.replace("?", "")


def _canon_token(tok: str) -> str:
    t = tok.strip().lower()
    t = t.replace('"', "").replace("'", "")
    t = _strip_diacritics(t)
    return t


def _tokenize_name(s: str) -> List[str]:
    return [_canon_token(t) for t in s.lower().split() if _canon_token(t)]


def _fuzzy_align_name_keys(
    gold_df: "pd.DataFrame",
    pred_df: "pd.DataFrame",
    key_cols: List[str],
) -> "pd.DataFrame":
    pred_out = pred_df.copy()
    for col in key_cols:
        if col.lower().replace("_", "") not in {
            c.replace("_", "") for c in _NAME_LIKE_COLUMNS
        }:
            continue
        if col not in gold_df.columns or col not in pred_out.columns:
            continue

        gt_vals = gold_df[col].dropna().unique().tolist()
        gt_lookup: Dict[str, str] = {}
        gt_canon_lookup: Dict[str, str] = {}
        gt_first_last: Dict[Tuple[str, str], str] = {}
        gt_by_last: Dict[str, List[str]] = {}
        gt_token_sets: Dict[str, set] = {}

        for gv in gt_vals:
            gs = str(gv).strip()
            gn = gs
            gt_lookup[gn] = gn
            canon_full = _strip_diacritics(
                gn.replace('"', "").replace("'", "").replace("?", "")
            )
            gt_canon_lookup[" ".join(canon_full.lower().split())] = gn
            toks = _tokenize_name(gn)
            gt_token_sets[gn] = set(toks)
            if len(toks) >= 2:
                fl = (toks[0], toks[-1])
                gt_first_last.setdefault(fl, gn)
                gt_by_last.setdefault(toks[-1], []).append(gn)
            elif toks:
                gt_by_last.setdefault(toks[0], []).append(gn)

        def _best_gt(pred_name: str) -> str:
            pn = str(pred_name).strip()
            if pn in gt_lookup:
                return pn
            canon_pn = _strip_diacritics(
                pn.replace('"', "").replace("'", "").replace("?", "")
            )
            canon_pn = " ".join(canon_pn.lower().split())
            if canon_pn in gt_canon_lookup:
                return gt_canon_lookup[canon_pn]
            ptoks = _tokenize_name(pn)
            if not ptoks:
                return pn
            if len(ptoks) >= 2:
                fl = (ptoks[0], ptoks[-1])
                if fl in gt_first_last:
                    return gt_first_last[fl]
            last = ptoks[-1]
            pset = set(ptoks)
            if last in gt_by_last:
                for candidate in gt_by_last[last]:
                    shared = pset & gt_token_sets[candidate]
                    if len(shared) >= 2:
                        return candidate
            for gn, gset in gt_token_sets.items():
                if len(pset & gset) >= 2:
                    return gn
            return pn

        pred_out[col] = pred_out[col].apply(
            lambda v: _best_gt(v) if pd.notna(v) and str(v).strip() else v
        )
    return pred_out


# ---------------------------------------------------------------------------
# Dataclass & helpers
# ---------------------------------------------------------------------------
@dataclass
class TrendQueryMetrics:
    query_id: str
    query_text: str
    success: bool
    delta_type: str
    latency_s: float
    result_rows: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    macro_f1: float
    macro_precision: float
    macro_recall: float
    gt_result_count: int
    matched_rows: int
    is_agg: bool
    error: Optional[str] = None


def setup_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    fh = logging.FileHandler(log_file)
    ch = logging.StreamHandler(sys.stdout)
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(fh)
    root.addHandler(ch)


def _norm_key(val: Any) -> str:
    s = " ".join(str(val).strip().lower().split())
    s = _ENTITY_SUFFIX_RE.sub("", s)
    s = re.sub(r"[,\.\(\)]", "", s)
    return " ".join(s.split())


def _normalize_key_cols(
    df: "pd.DataFrame", key_cols: List[str]
) -> "pd.DataFrame":
    out = df.copy()
    for col in key_cols:
        if col in out.columns:
            out[col] = out[col].apply(
                lambda v: _norm_key(v) if pd.notna(v) else ""
            )
    return out


def _resolve_primary_keys_for_alignment(
    primary_keys: List[str],
    gold_df: "pd.DataFrame",
    pred_df: "pd.DataFrame",
) -> List[str]:
    gold_cols = {str(c) for c in gold_df.columns}
    pred_cols = {str(c) for c in pred_df.columns}
    resolved: List[str] = []
    for key in primary_keys:
        candidates = [
            key,
            key.split(".")[-1],
            _std_col(key),
            _std_col(key.split(".")[-1]),
        ]
        chosen = next(
            (c for c in candidates if c in gold_cols and c in pred_cols), None
        )
        if chosen and chosen not in resolved:
            resolved.append(chosen)
    return resolved or primary_keys


# ---------------------------------------------------------------------------
# SQL augmentation helpers
# ---------------------------------------------------------------------------
def _augment_sql_with_entity(
    sql: str, entity_col: str, dialect: str = "duckdb"
) -> Optional[str]:
    if not SQLGLOT_AVAILABLE:
        return None
    try:
        parsed = sqlglot.parse_one(sql, error_level="ignore")
    except Exception:
        return None
    if parsed.find(_sqlglot_exp.Star):
        return None
    if parsed.args.get("group"):
        return None
    existing = {
        c.name.lower()
        for c in parsed.find_all(_sqlglot_exp.Column)
        if isinstance(c.parent, _sqlglot_exp.Select)
    }
    if entity_col.lower() in existing:
        return None
    parsed = parsed.select(_sqlglot_exp.column(entity_col))
    return parsed.sql(dialect=dialect)


def _infer_identity_col_for_query(
    sql: str, identity_columns: Dict[str, str]
) -> Optional[str]:
    if not SQLGLOT_AVAILABLE:
        return identity_columns.get("player", "name")
    try:
        parsed = sqlglot.parse_one(sql, error_level="ignore")
        first_table = None
        for t in parsed.find_all(sqlglot.expressions.Table):
            first_table = t.name
            break
        if first_table:
            if first_table in identity_columns:
                return identity_columns[first_table]
            lc_map = {k.lower(): v for k, v in identity_columns.items()}
            if first_table.lower() in lc_map:
                return lc_map[first_table.lower()]
    except Exception:
        pass
    return identity_columns.get("player", "name")


IDENTITY_COLUMNS = {
    "player": "name",
    "team": "team_name",
    "city": "city_name",
}


# ---------------------------------------------------------------------------
# SQUiD Preprocessing
# ---------------------------------------------------------------------------
def _build_single_player_input_dataset(
    dataset_json_path: Path, repeat_entries: int = 1
) -> None:
    """
    Build one combined input document so SQUiD generates ONE database.

    We use all rows from Player CSVs and render deterministic textual sentences.
    """
    data_dir = PROJECT_ROOT / "Data" / "Player"
    player_csv = data_dir / "player.csv"
    team_csv = data_dir / "team.csv"
    city_csv = data_dir / "city.csv"
    owner_csv = data_dir / "owner.csv"

    if not player_csv.exists() or not team_csv.exists() or not city_csv.exists():
        raise FileNotFoundError(
            f"Missing Player CSVs in {data_dir}. Need player.csv/team.csv/city.csv."
        )

    # Read CSVs with pandas to keep dependency footprint aligned with evaluator.
    player_df = pd.read_csv(player_csv)
    team_df = pd.read_csv(team_csv)
    city_df = pd.read_csv(city_csv)
    owner_df = pd.read_csv(owner_csv) if owner_csv.exists() else pd.DataFrame()

    paragraphs: List[str] = []
    paragraphs.append("Player records:")
    for _, r in player_df.iterrows():
        paragraphs.append(
            "Player {name}, born {birth_date}, nationality {nationality}, age {age}, "
            "plays for {team}, position {position}, draft pick {draft_pick}, draft year {draft_year}, "
            "college {college}, NBA championships {nba_championships}, MVP awards {mvp_awards}, "
            "Olympic gold medals {olympic_gold_medals}, FIBA world cup {fiba_world_cup}.".format(
                name=r.get("name"),
                birth_date=r.get("birth_date"),
                nationality=r.get("nationality"),
                age=r.get("age"),
                team=r.get("team"),
                position=r.get("position"),
                draft_pick=r.get("draft_pick"),
                draft_year=r.get("draft_year"),
                college=r.get("college"),
                nba_championships=r.get("nba_championships"),
                mvp_awards=r.get("mvp_awards"),
                olympic_gold_medals=r.get("olympic_gold_medals"),
                fiba_world_cup=r.get("fiba_world_cup"),
            )
        )

    paragraphs.append("Team records:")
    for _, r in team_df.iterrows():
        paragraphs.append(
            "Team {team_name}, founded year {founded_year}, location {location}, "
            "ownership {ownership}, championship {championship}.".format(
                team_name=r.get("team_name"),
                founded_year=r.get("founded_year"),
                location=r.get("location"),
                ownership=r.get("ownership"),
                championship=r.get("championship"),
            )
        )

    paragraphs.append("City records:")
    for _, r in city_df.iterrows():
        paragraphs.append(
            "City {city_name}, state {state_name}, population {population}, "
            "area {area}, gdp {gdp}.".format(
                city_name=r.get("city_name"),
                state_name=r.get("state_name"),
                population=r.get("population"),
                area=r.get("area"),
                gdp=r.get("gdp"),
            )
        )

    if not owner_df.empty:
        paragraphs.append("Owner records:")
        for _, r in owner_df.iterrows():
            paragraphs.append(
                "Owner {name}, age {age}, nationality {nationality}, nba team {nba_team}, "
                "own year {own_year}.".format(
                    name=r.get("name"),
                    age=r.get("age"),
                    nationality=r.get("nationality"),
                    nba_team=r.get("nba_team"),
                    own_year=r.get("own_year"),
                )
            )

    combined_text = "\n".join(paragraphs)
    base_entry = {
        "text": combined_text,
        "ground_truth_entities": ["player", "team", "city", "owner"],
        "ground_truth_key_value": {},
        "domain": "Player",
        "difficulty": "hard",
    }
    combined_entry = [dict(base_entry) for _ in range(max(1, repeat_entries))]
    dataset_json_path.parent.mkdir(parents=True, exist_ok=True)
    dataset_json_path.write_text(json.dumps(combined_entry, indent=2))


def run_squid_preprocessing(squid_root: Path, method: str = "TS") -> Path:
    """
    Run the full SQUiD pipeline for the Player dataset.

    Requires:
      - Ollama running with qwen2.5:7b-instruct model
      - Stanford CoreNLP (downloaded by stanza)
      - Source data in the expected locations

    This mode feeds ONE combined input document so SQUiD materializes ONE DB.
    """
    src_dir = squid_root / "src"
    config_path = squid_root / "configs" / "config.yaml"
    run_root = RESULTS_BASE_DIR / "single_input_pipeline"
    input_base = run_root / "inputs"
    artifacts_base = run_root / "artifacts"
    dataset_rel = "single_input/player_single"
    dataset_json = input_base / "single_input" / "player_single.json"

    logger.info("=" * 70)
    logger.info("Running SQUiD single-input preprocessing (one DB output)")
    logger.info("=" * 70)
    _build_single_player_input_dataset(dataset_json, repeat_entries=1)

    def _run(cmd: List[str], desc: str) -> None:
        logger.info(f"[Preprocess] {desc}")
        logger.info(f"  Command: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            cwd=str(squid_root),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            err_dir = run_root / "stderr_logs"
            err_dir.mkdir(parents=True, exist_ok=True)
            safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", desc.strip().lower())
            err_file = err_dir / f"{safe_name}.stderr.log"
            out_file = err_dir / f"{safe_name}.stdout.log"
            err_file.write_text(result.stderr or "")
            out_file.write_text(result.stdout or "")
            raise RuntimeError(
                f"{desc} failed with exit {result.returncode}. "
                f"See {err_file} (stderr) and {out_file} (stdout). "
                f"Stderr tail:\n{(result.stderr or '')[-1200:]}"
            )
        logger.info("  OK")

    with open(config_path, "r") as f:
        original_cfg_text = f.read()
    cfg = yaml.safe_load(original_cfg_text)

    # Repoint configs to single-input run roots.
    cfg["schema_generation"]["base_data_path"] = str(input_base)
    cfg["schema_generation"]["datapath"] = dataset_rel
    cfg["schema_generation"]["results_dir"] = str(artifacts_base / "schema_generation") + "/"
    cfg["schema_generation"]["logs_dir"] = str(artifacts_base / "logs" / "schema_generation") + "/"
    cfg["schema_generation"]["num_of_entries"] = 1
    cfg["schema_generation"]["model_name"] = "ollama"
    cfg["schema_generation"]["method"] = "text"
    cfg["schema_generation"]["prompt_type"] = "direct"

    vi_datapath = f"{dataset_rel}/text_direct_ollama"
    schema_json_path = (
        artifacts_base / "schema_generation" / dataset_rel / "text_direct_ollama.json"
    )
    cfg["value_identification"]["datapath"] = vi_datapath
    cfg["value_identification"]["schema_path"] = str(schema_json_path)
    cfg["value_identification"]["results_dir"] = str(artifacts_base / "value_identification") + "/"
    cfg["value_identification"]["logs_dir"] = str(artifacts_base / "logs" / "value_identification") + "/"
    cfg["value_identification"]["num_of_entries"] = 1
    cfg["value_identification"]["model_name"] = "ollama"

    symbolic_path = artifacts_base / "value_identification" / "symbolic" / f"{vi_datapath}.json"
    cfg["value_population"]["base_data_path"] = str(artifacts_base / "value_identification") + "/"
    cfg["value_population"]["datapath"] = vi_datapath
    cfg["value_population"]["symbolic_path"] = str(symbolic_path)
    cfg["value_population"]["results_dir"] = str(artifacts_base / "value_population") + "/"
    cfg["value_population"]["logs_dir"] = str(artifacts_base / "logs" / "value_population") + "/"
    cfg["value_population"]["num_of_entries"] = 1
    cfg["value_population"]["model_name"] = "ollama"

    schema_map = (
        artifacts_base / "schema_generation" / dataset_rel / "text_direct_ollama_schema.json"
    )
    cfg["database_generation"]["base_data_path"] = str(artifacts_base / "value_population") + "/"
    cfg["database_generation"]["datapath"] = vi_datapath
    cfg["database_generation"]["results_dir"] = str(artifacts_base / "database_generation") + "/"
    cfg["database_generation"]["logs_dir"] = str(artifacts_base / "logs" / "database_generation") + "/"
    cfg["database_generation"]["num_of_entries"] = 1
    cfg["database_generation"]["model_name"] = "ollama"
    cfg["database_generation"]["schema_path"] = str(schema_map)

    selected_methods = ["TS", "TST", "TST-L"] if method == "ensemble" else [method]

    def _materialize_ensemble_single_input_db() -> Path:
        """
        Paper-faithful ensemble materialization:
        - parse tuples from TS/TST/TST-L outputs
        - union/deduplicate tuples
        - materialize one SQLite database from combined tuples
        """
        schema_result_path = (
            artifacts_base / "schema_generation" / dataset_rel / "text_direct_ollama.json"
        )
        if not schema_result_path.exists():
            raise FileNotFoundError(f"Schema result not found: {schema_result_path}")
        schema_entries = json.loads(schema_result_path.read_text())
        if not schema_entries:
            raise RuntimeError("Schema result is empty.")
        schema_raw = schema_entries[0].get("predicted_schema", "")
        schema_text = _extract_schema(schema_raw)
        if not schema_text:
            raise RuntimeError("Could not extract schema from schema_generation output.")
        schema = json.loads(schema_text)

        combined_values: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for m in ["TS", "TST", "TST-L"]:
            vp_path = artifacts_base / "value_population" / m / f"{vi_datapath}.json"
            if not vp_path.exists():
                logger.warning(f"Skipping missing value_population file: {vp_path}")
                continue
            entries = json.loads(vp_path.read_text())
            if not entries:
                continue
            output = entries[0].get("output", "")
            if isinstance(output, list):
                output = "\n".join(str(x) for x in output)
            parsed = _extract_from_output(str(output), schema)
            for table_name, rows in parsed.items():
                if isinstance(rows, list):
                    combined_values[table_name].extend(rows)

        deduped_values: Dict[str, List[Dict[str, Any]]] = {}
        for table_name, rows in combined_values.items():
            seen = set()
            unique_rows: List[Dict[str, Any]] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                key = json.dumps(row, sort_keys=True, default=str)
                if key in seen:
                    continue
                seen.add(key)
                unique_rows.append(row)
            deduped_values[table_name] = unique_rows

        sql_statements = _gen_sql_from_schema_values(schema, deduped_values)
        db_base = squid_root / "databases" / vi_datapath / "ensemble" / "Player_0"
        db_base.parent.mkdir(parents=True, exist_ok=True)
        _create_database(str(db_base), sql_statements)
        db_path = Path(f"{db_base}.db")
        if not db_path.exists():
            raise FileNotFoundError(
                f"Failed to create ensemble DB at expected path: {db_path}"
            )
        return db_path

    try:
        with open(config_path, "w") as f:
            yaml.safe_dump(cfg, f, sort_keys=False)

        _run(
            [sys.executable, str(src_dir / "schema_generation.py"),
             "--model_name", "ollama", "--method", "text", "--prompt_type", "direct"],
            "Schema generation",
        )
        _run(
            [sys.executable, str(src_dir / "value_identification.py"),
             "--model_name", "ollama", "--method", "symbolic"],
            "Value identification (symbolic)",
        )
        if "TST-L" in selected_methods:
            _run(
                [sys.executable, str(src_dir / "value_identification.py"),
                 "--model_name", "ollama", "--method", "llm"],
                "Value identification (llm)",
            )
        for vp_method in selected_methods:
            _run(
                [sys.executable, str(src_dir / "value_population.py"),
                 "--model_name", "ollama", "--method", vp_method],
                f"Value population ({vp_method})",
            )
            if method != "ensemble":
                _run(
                    [sys.executable, str(src_dir / "database_generation.py"),
                     "--model_name", "ollama", "--method", vp_method],
                    f"Database generation ({vp_method})",
                )
        generated_db_path = (
            _materialize_ensemble_single_input_db()
            if method == "ensemble"
            else None
        )
    finally:
        with open(config_path, "w") as f:
            f.write(original_cfg_text)

    if method == "ensemble":
        db_path = generated_db_path
    else:
        db_path = (
            squid_root
            / "databases"
            / vi_datapath
            / method
            / "Player_0.db"
        )
    if not db_path.exists():
        raise FileNotFoundError(
            f"SQUiD did not materialize expected DB: {db_path}"
        )
    logger.info(f"SQUiD preprocessing complete. Generated DB: {db_path}")
    return db_path


# ---------------------------------------------------------------------------
# DB Consolidation: merge per-document SQUiD DBs → single unified DB
# ---------------------------------------------------------------------------
def _read_squid_table(db_path: Path, table_name: str) -> List[Dict[str, Any]]:
    """Read all rows from a table in a SQUiD per-document database."""
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute(f'SELECT * FROM "{table_name}"')
        if cur.description is None:
            conn.close()
            return []
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


def _safe_str(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    if s.lower() in ("none", "null", "#", "nan", ""):
        return None
    return s


def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def consolidate_squid_databases(
    methods: List[str],
    num_entries: int = 100,
    output_db: Optional[Path] = None,
) -> Path:
    """
    Consolidate per-document SQUiD databases into a single unified SQLite DB
    with the ground-truth schema so Q1..Q10 queries can run.

    Column mapping (SQUiD extracted → GT expected):
      player:  name, draft_year, college, position + team (from co-located team table)
               + nba_championships, mvp_awards, olympic_gold_medals (from achievement table)
      team:    name→team_name, established_year→founded_year
      city:    name→city_name, population
    """
    if output_db is None:
        output_db = RESULTS_BASE_DIR / "squid_consolidated.db"
    output_db.parent.mkdir(parents=True, exist_ok=True)

    # Collect data from per-document databases
    players_by_doc: Dict[int, Dict[str, Any]] = {}
    teams_by_doc: Dict[int, Dict[str, Any]] = {}
    cities_by_doc: Dict[int, Dict[str, Any]] = {}

    for method in methods:
        # --- Player entity databases ---
        for i in range(num_entries):
            db_path = (
                SQUID_DB_ROOT
                / "player"
                / "text_direct_ollama"
                / method
                / f"Player_{i}.db"
            )
            player_rows = _read_squid_table(db_path, "player")
            team_rows = _read_squid_table(db_path, "team")
            ach_rows = _read_squid_table(db_path, "achievement")

            for pr in player_rows:
                if i not in players_by_doc:
                    players_by_doc[i] = {
                        "name": None, "birth_date": None, "nationality": None,
                        "age": None, "team": None, "position": None,
                        "draft_pick": None, "draft_year": None, "college": None,
                        "nba_championships": None, "mvp_awards": None,
                        "olympic_gold_medals": None, "fiba_world_cup": None,
                    }
                rec = players_by_doc[i]
                for field, squid_col in [
                    ("name", "name"), ("draft_year", "draft_year"),
                    ("college", "college"), ("position", "position"),
                ]:
                    val = _safe_str(pr.get(squid_col))
                    if val is not None and rec[field] is None:
                        rec[field] = val

            for tr in team_rows:
                team_name = _safe_str(tr.get("name"))
                if team_name and i in players_by_doc:
                    if players_by_doc[i]["team"] is None:
                        players_by_doc[i]["team"] = team_name

            for ar in ach_rows:
                if i in players_by_doc:
                    rec = players_by_doc[i]
                    for field, squid_col in [
                        ("nba_championships", "nba_championships"),
                        ("mvp_awards", "mvp_awards"),
                        ("olympic_gold_medals", "olympic_gold_medals"),
                    ]:
                        val = _safe_float(ar.get(squid_col))
                        if val is not None and rec[field] is None:
                            rec[field] = val

        # --- Team entity databases ---
        for i in range(num_entries):
            db_path = (
                SQUID_DB_ROOT
                / "team"
                / "text_direct_ollama"
                / method
                / f"Player_{i}.db"
            )
            rows = _read_squid_table(db_path, "team")
            for tr in rows:
                if i not in teams_by_doc:
                    teams_by_doc[i] = {
                        "team_name": None, "founded_year": None,
                        "location": None, "ownership": None,
                        "championship": None,
                    }
                rec = teams_by_doc[i]
                for field, squid_col in [
                    ("team_name", "name"), ("founded_year", "established_year"),
                ]:
                    val = _safe_str(tr.get(squid_col))
                    if val is not None and rec[field] is None:
                        rec[field] = val

        # --- City entity databases ---
        for i in range(num_entries):
            db_path = (
                SQUID_DB_ROOT
                / "city"
                / "text_direct_ollama"
                / method
                / f"Player_{i}.db"
            )
            rows = _read_squid_table(db_path, "city")
            for cr in rows:
                if i not in cities_by_doc:
                    cities_by_doc[i] = {
                        "city_name": None, "state_name": None,
                        "population": None, "area": None, "gdp": None,
                    }
                rec = cities_by_doc[i]
                for field, squid_col in [
                    ("city_name", "name"), ("population", "population"),
                ]:
                    val = _safe_str(cr.get(squid_col))
                    if val is not None and rec[field] is None:
                        rec[field] = val

    # Build the consolidated SQLite database
    if output_db.exists():
        output_db.unlink()

    conn = sqlite3.connect(str(output_db))
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE player (
            name TEXT,
            birth_date TEXT,
            nationality TEXT,
            age REAL,
            team TEXT,
            position TEXT,
            draft_pick REAL,
            draft_year REAL,
            college TEXT,
            nba_championships REAL,
            mvp_awards REAL,
            olympic_gold_medals REAL,
            fiba_world_cup REAL,
            ID INTEGER PRIMARY KEY
        )
    """)

    cur.execute("""
        CREATE TABLE team (
            team_name TEXT,
            founded_year REAL,
            location TEXT,
            ownership TEXT,
            championship REAL,
            ID INTEGER PRIMARY KEY
        )
    """)

    cur.execute("""
        CREATE TABLE city (
            city_name TEXT,
            state_name TEXT,
            population REAL,
            area REAL,
            gdp REAL,
            ID INTEGER PRIMARY KEY
        )
    """)

    cur.execute("""
        CREATE TABLE owner (
            name TEXT,
            age REAL,
            nationality TEXT,
            nba_team TEXT,
            own_year REAL,
            ID INTEGER PRIMARY KEY
        )
    """)

    # Insert player records
    for doc_id in sorted(players_by_doc.keys()):
        rec = players_by_doc[doc_id]
        cur.execute(
            """INSERT INTO player
               (name, birth_date, nationality, age, team, position,
                draft_pick, draft_year, college, nba_championships,
                mvp_awards, olympic_gold_medals, fiba_world_cup, ID)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                rec["name"], rec["birth_date"], rec["nationality"],
                _safe_float(rec["age"]), rec["team"], rec["position"],
                _safe_float(rec["draft_pick"]), _safe_float(rec["draft_year"]),
                rec["college"], _safe_float(rec["nba_championships"]),
                _safe_float(rec["mvp_awards"]),
                _safe_float(rec["olympic_gold_medals"]),
                _safe_float(rec["fiba_world_cup"]),
                doc_id + 1,
            ),
        )

    # Insert team records
    for doc_id in sorted(teams_by_doc.keys()):
        rec = teams_by_doc[doc_id]
        cur.execute(
            """INSERT INTO team
               (team_name, founded_year, location, ownership, championship, ID)
               VALUES (?,?,?,?,?,?)""",
            (
                rec["team_name"], _safe_float(rec["founded_year"]),
                rec["location"], rec["ownership"],
                _safe_float(rec["championship"]),
                doc_id + 1,
            ),
        )

    # Insert city records
    for doc_id in sorted(cities_by_doc.keys()):
        rec = cities_by_doc[doc_id]
        cur.execute(
            """INSERT INTO city
               (city_name, state_name, population, area, gdp, ID)
               VALUES (?,?,?,?,?,?)""",
            (
                rec["city_name"], rec["state_name"],
                _safe_float(rec["population"]),
                _safe_float(rec["area"]), _safe_float(rec["gdp"]),
                doc_id + 1,
            ),
        )

    conn.commit()

    # Summary stats
    for tbl in ["player", "team", "city", "owner"]:
        cur.execute(f"SELECT COUNT(*) FROM {tbl}")
        cnt = cur.fetchone()[0]
        non_null_cols = []
        cur.execute(f"PRAGMA table_info({tbl})")
        for col_info in cur.fetchall():
            col_name = col_info[1]
            cur.execute(
                f'SELECT COUNT(*) FROM {tbl} WHERE "{col_name}" IS NOT NULL'
            )
            nn = cur.fetchone()[0]
            if nn > 0:
                non_null_cols.append(f"{col_name}({nn})")
        logger.info(
            f"[Consolidate] {tbl}: {cnt} rows, "
            f"non-null columns: {', '.join(non_null_cols)}"
        )

    conn.close()
    logger.info(f"[Consolidate] Unified DB written to: {output_db}")
    return output_db


# ---------------------------------------------------------------------------
# Query parsing (same as WDIRS)
# ---------------------------------------------------------------------------
def parse_trend_queries(sql_file: Path) -> List[Tuple[str, str]]:
    """Parse Q1..Q10 from query_aware_trend_queries.sql."""
    if not sql_file.exists():
        raise FileNotFoundError(f"Trend SQL file not found: {sql_file}")
    lines = sql_file.read_text().splitlines()
    queries: List[Tuple[str, str]] = []

    i = 0
    while i < len(lines):
        m = re.match(r"\s*--\s*Q(\d+)\s*:", lines[i], flags=re.IGNORECASE)
        if not m:
            i += 1
            continue
        qid = f"Q{int(m.group(1))}"
        i += 1
        sql_lines: List[str] = []
        while i < len(lines):
            raw = lines[i]
            s = raw.strip()
            if re.match(r"\s*--\s*Q\d+\s*:", raw, flags=re.IGNORECASE):
                break
            if s.startswith("--") or s == "":
                i += 1
                continue
            sql_lines.append(raw)
            if ";" in raw:
                i += 1
                break
            i += 1
        sql = "\n".join(sql_lines).strip()
        if sql and not sql.endswith(";"):
            sql += ";"
        if sql:
            queries.append((qid, sql))

    queries.sort(key=lambda x: int(x[0][1:]))
    return queries


# ---------------------------------------------------------------------------
# Query execution on consolidated SQUiD DB
# ---------------------------------------------------------------------------
def execute_sql_on_squid_db(
    db_path: Path, sql: str
) -> Tuple[bool, List[Dict[str, Any]], Optional[str]]:
    """Execute a SQL query against the consolidated SQUiD database."""
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.close()
        return True, rows, None
    except Exception as exc:
        return False, [], str(exc)


# ---------------------------------------------------------------------------
# Evaluation with official framework
# ---------------------------------------------------------------------------
def _build_pred_df(
    rows: List[Dict[str, Any]],
    expected_columns: List[str],
    stop_columns: List[str],
    attributes: Dict[str, Any],
) -> "pd.DataFrame":
    df = (
        pd.DataFrame(rows)
        if rows
        else pd.DataFrame(columns=expected_columns)
    )
    df = _drop_unnamed(df)
    df = df.rename(columns={c: _std_col(c) for c in df.columns})
    df = _norm_file_cols(df)
    df = _add_missing_cols(df, expected_columns)
    df = _add_missing_cols(df, stop_columns)
    df = _clean_string_cols(df)
    df = _norm_types(df, attributes)
    return df


def evaluate_with_official_framework(
    sql: str,
    result_rows: List[Dict[str, Any]],
    *,
    gt_runner: "_GtRunner",
    sql_parser: "_SqlParser",
    row_matcher: "_RowMatcher",
    settings: "_EvalSettings",
    attributes: Dict[str, Any],
    identity_col: Optional[str],
    phase2_db: Path,
    output_dir: Path,
) -> Dict[str, Any]:
    parsed = sql_parser.parse(sql)
    is_agg = parsed.query_type == "aggregation"
    entity = identity_col or "name"

    if is_agg:
        gt_sql = sql
        effective_rows = result_rows
        primary_keys = parsed.primary_keys
    else:
        aug_gt = _augment_sql_with_entity(sql, entity, dialect="duckdb")
        gt_sql = aug_gt if aug_gt else sql

        row_cols = {k.lower() for k in (result_rows[0].keys() if result_rows else {})}
        if entity.lower() not in row_cols and phase2_db.exists():
            aug_sql = _augment_sql_with_entity(sql, entity, dialect="sqlite")
            if aug_sql:
                try:
                    con = sqlite3.connect(str(phase2_db))
                    con.row_factory = sqlite3.Row
                    cur_aug = con.execute(aug_sql)
                    cols = [d[0] for d in cur_aug.description]
                    effective_rows = [
                        dict(zip(cols, r)) for r in cur_aug.fetchall()
                    ]
                    con.close()
                except Exception:
                    effective_rows = result_rows
            else:
                effective_rows = result_rows
        else:
            effective_rows = result_rows
        primary_keys = [entity]

    gold_df = gt_runner.run(gt_sql)
    if not is_agg and entity not in gold_df.columns:
        primary_keys = parsed.primary_keys

    manifest = _QueryManifest(gt_sql, sql_parser.parse(gt_sql), attributes)
    pred_df = _build_pred_df(
        effective_rows,
        expected_columns=list(gold_df.columns),
        stop_columns=manifest.stop_columns,
        attributes=attributes,
    )

    primary_keys = _resolve_primary_keys_for_alignment(
        primary_keys, gold_df, pred_df
    )

    gold_norm = _normalize_key_cols(gold_df, primary_keys)
    pred_norm = _normalize_key_cols(pred_df, primary_keys)
    pred_norm = _fuzzy_align_name_keys(gold_norm, pred_norm, primary_keys)

    try:
        match_result = row_matcher.match(
            gold_df=gold_norm,
            pred_df=pred_norm,
            primary_keys=primary_keys,
            attr_descriptions=attributes,
            query_type=parsed.query_type,
        )
    except KeyError as ke:
        logger.warning(
            f"[Eval] RowMatcher key error ({ke}) — returning zero metrics"
        )
        return {
            "macro_f1": 0.0,
            "macro_precision": 0.0,
            "macro_recall": 0.0,
            "is_agg": is_agg,
            "gt_result_count": len(gold_df),
            "matched_rows": 0,
        }

    calc = _MetricCalculator(manifest, settings)
    metrics = calc.compute(match_result)
    macro_f1 = metrics.get("macro_f1", 0.0)
    macro_precision = metrics.get("macro_precision", 0.0)
    macro_recall = metrics.get("macro_recall", 0.0)
    if not math.isfinite(macro_f1):
        macro_f1 = 0.0
    if not math.isfinite(macro_precision):
        macro_precision = 0.0
    if not math.isfinite(macro_recall):
        macro_recall = 0.0

    try:
        writer = _ResultWriter(output_dir=output_dir)
        writer.write(
            gold_df,
            match_result.gold_aligned,
            match_result.pred_aligned,
            metrics,
        )
    except Exception as we:
        logger.warning(f"[Eval] Could not write per-query outputs: {we}")

    return {
        "macro_f1": macro_f1,
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "is_agg": is_agg,
        "gt_result_count": len(gold_df),
        "matched_rows": match_result.matched_rows,
    }


# ---------------------------------------------------------------------------
# CSV helper
# ---------------------------------------------------------------------------
def _save_rows_csv(rows: List[Dict[str, Any]], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with out_csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["_empty"])
        return
    cols: List[str] = []
    for r in rows:
        for k in r.keys():
            if k not in cols:
                cols.append(k)
    with out_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Main trend query run
# ---------------------------------------------------------------------------
def run_trend_queries(
    consolidated_db: Path,
    run_dir: Path,
    query_results_dir: Path,
    query_tables_dir: Path,
    plots_dir: Path,
) -> List[TrendQueryMetrics]:
    run_dir.mkdir(parents=True, exist_ok=True)
    query_results_dir.mkdir(parents=True, exist_ok=True)
    query_tables_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    eval_attributes: Dict[str, Any] = (
        _load_json(ATTRIBUTES_FILE) if ATTRIBUTES_FILE.exists() else {}
    )
    eval_settings = _EvalSettings(llm_provider="none")
    eval_gt_runner = _GtRunner(
        gt_dir=GROUND_TRUTH_DIR, attributes=eval_attributes
    )
    eval_sql_parser = _SqlParser()
    eval_row_matcher = _RowMatcher(settings=eval_settings)

    trend_queries = parse_trend_queries(TREND_SQL_FILE)
    if not trend_queries:
        raise RuntimeError(f"No trend queries found in {TREND_SQL_FILE}")

    metrics: List[TrendQueryMetrics] = []

    for query_id, query_text in trend_queries:
        logger.info("=" * 70)
        logger.info(f"Executing {query_id} (SQUiD — offline, SQL on consolidated DB)")
        t0 = time.time()

        try:
            effective_sql = SQUID_REWRITTEN_QUERIES.get(query_id, query_text)
            success, rows, error = execute_sql_on_squid_db(
                consolidated_db, effective_sql
            )
            latency = time.time() - t0

            out_csv = query_tables_dir / f"{query_id}.csv"
            out_json = query_tables_dir / f"{query_id}.json"
            _save_rows_csv(rows, out_csv)
            out_json.write_text(json.dumps(rows, indent=2, default=str))

            eval_out: Dict[str, Any] = {}
            if success and rows:
                eval_out = evaluate_with_official_framework(
                    query_text,
                    rows,
                    gt_runner=eval_gt_runner,
                    sql_parser=eval_sql_parser,
                    row_matcher=eval_row_matcher,
                    settings=eval_settings,
                    attributes=eval_attributes,
                    identity_col=_infer_identity_col_for_query(
                        query_text, IDENTITY_COLUMNS
                    ),
                    phase2_db=consolidated_db,
                    output_dir=query_results_dir / query_id,
                )

            item = TrendQueryMetrics(
                query_id=query_id,
                query_text=query_text,
                success=success,
                delta_type="OFFLINE",
                latency_s=latency,
                result_rows=len(rows),
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                macro_f1=eval_out.get("macro_f1", 0.0),
                macro_precision=eval_out.get("macro_precision", 0.0),
                macro_recall=eval_out.get("macro_recall", 0.0),
                gt_result_count=eval_out.get("gt_result_count", 0),
                matched_rows=eval_out.get("matched_rows", 0),
                is_agg=eval_out.get("is_agg", False),
                error=error if not success else None,
            )
            metrics.append(item)

            acc_path = query_results_dir / query_id / "acc.json"
            if acc_path.exists():
                try:
                    acc_data = json.loads(acc_path.read_text())
                    acc_data["query_id"] = query_id
                    acc_data["latency_s"] = round(latency, 4)
                    acc_data["prompt_tokens"] = 0
                    acc_data["completion_tokens"] = 0
                    acc_data["total_tokens"] = 0
                    acc_data["result_rows"] = len(rows)
                    acc_path.write_text(json.dumps(acc_data, indent=2))
                except Exception:
                    pass

            logger.info(
                f"{query_id}: success={item.success} rows={item.result_rows} "
                f"latency={item.latency_s:.4f}s "
                f"F1={item.macro_f1:.3f} P={item.macro_precision:.3f} "
                f"R={item.macro_recall:.3f}"
            )

        except Exception as exc:
            latency = time.time() - t0
            metrics.append(
                TrendQueryMetrics(
                    query_id=query_id,
                    query_text=query_text,
                    success=False,
                    delta_type="ERROR",
                    latency_s=latency,
                    result_rows=0,
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    macro_f1=0.0,
                    macro_precision=0.0,
                    macro_recall=0.0,
                    gt_result_count=0,
                    matched_rows=0,
                    is_agg=False,
                    error=str(exc),
                )
            )
            logger.exception(f"{query_id} failed: {exc}")

    return metrics


# ---------------------------------------------------------------------------
# Save / plot
# ---------------------------------------------------------------------------
def save_metrics(metrics: List[TrendQueryMetrics], run_dir: Path) -> None:
    rows = [asdict(m) for m in metrics]
    out_json = run_dir / "trend_metrics.json"
    out_csv = run_dir / "trend_metrics.csv"
    out_json.write_text(json.dumps(rows, indent=2))
    with out_csv.open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=list(rows[0].keys()) if rows else []
        )
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    logger.info(f"Saved metrics JSON: {out_json}")
    logger.info(f"Saved metrics CSV:  {out_csv}")


def plot_metrics(metrics: List[TrendQueryMetrics], plots_dir: Path) -> None:
    if not MATPLOTLIB_AVAILABLE:
        logger.warning("matplotlib not available — skipping plot generation")
        return
    if not metrics:
        logger.warning("No metrics to plot.")
        return

    ordered = sorted(metrics, key=lambda m: int(m.query_id[1:]))
    x_labels = [m.query_id for m in ordered]
    x = list(range(len(x_labels)))

    result_rows = [m.result_rows for m in ordered]
    token_cost = [m.total_tokens for m in ordered]
    latency = [m.latency_s for m in ordered]
    f1 = [m.macro_f1 for m in ordered]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        "SQUiD — Player Query-Awareness Trend (Q1..Q10)",
        fontsize=16,
        fontweight="bold",
    )

    axes[0, 0].plot(x, result_rows, marker="o", color="#7f8c8d")
    axes[0, 0].set_title("Result Table Size (rows)")
    axes[0, 0].set_xticks(x)
    axes[0, 0].set_xticklabels(x_labels)
    axes[0, 0].set_ylabel("rows")
    axes[0, 0].grid(alpha=0.3)

    axes[0, 1].plot(x, token_cost, marker="o", color="#8e44ad")
    axes[0, 1].set_title("Token Cost (0 — offline preprocessing)")
    axes[0, 1].set_xticks(x)
    axes[0, 1].set_xticklabels(x_labels)
    axes[0, 1].set_ylabel("tokens")
    axes[0, 1].grid(alpha=0.3)

    axes[1, 0].plot(x, latency, marker="o", color="#2980b9")
    axes[1, 0].set_title("Latency (SQL execution only)")
    axes[1, 0].set_xticks(x)
    axes[1, 0].set_xticklabels(x_labels)
    axes[1, 0].set_ylabel("seconds")
    axes[1, 0].grid(alpha=0.3)

    axes[1, 1].plot(x, f1, marker="o", color="#27ae60")
    axes[1, 1].set_title("Macro F1 (official evaluator)")
    axes[1, 1].set_xticks(x)
    axes[1, 1].set_xticklabels(x_labels)
    axes[1, 1].set_ylim(0.0, 1.0)
    axes[1, 1].set_ylabel("F1")
    axes[1, 1].grid(alpha=0.3)

    plt.tight_layout()
    summary_plot = plots_dir / "query_awareness_trend_summary.png"
    plt.savefig(summary_plot, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Saved trend summary plot: {summary_plot}")

    # Separate P/R/F1 plot
    p = [m.macro_precision for m in ordered]
    r = [m.macro_recall for m in ordered]
    fig2, ax2 = plt.subplots(figsize=(12, 5))
    ax2.plot(x, p, marker="o", label="Precision")
    ax2.plot(x, r, marker="o", label="Recall")
    ax2.plot(x, f1, marker="o", label="F1")
    ax2.set_xticks(x)
    ax2.set_xticklabels(x_labels)
    ax2.set_ylim(0.0, 1.0)
    ax2.set_title("SQUiD — Macro Precision/Recall/F1 by Query")
    ax2.set_ylabel("score")
    ax2.grid(alpha=0.3)
    ax2.legend()
    plt.tight_layout()
    prf_plot = plots_dir / "query_awareness_trend_prf.png"
    plt.savefig(prf_plot, dpi=300, bbox_inches="tight")
    plt.close(fig2)
    logger.info(f"Saved trend PRF plot: {prf_plot}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    RESULTS_BASE_DIR.mkdir(parents=True, exist_ok=True)
    setup_logging(RESULTS_BASE_DIR / "query_awareness_trend.log")

    ap = argparse.ArgumentParser(
        description="Run Player query-awareness trend test for SQUiD"
    )
    ap.add_argument(
        "--run-preprocessing",
        action="store_true",
        help=(
            "Run the full SQUiD preprocessing pipeline before evaluation. "
            "Requires Ollama with qwen2.5:7b-instruct and CoreNLP."
        ),
    )
    ap.add_argument(
        "--method",
        type=str,
        default="ensemble",
        choices=["TS", "TST", "TST-L", "ensemble"],
        help="SQUiD method for single-input generation (default: ensemble).",
    )
    args = ap.parse_args()

    logger.info("Starting SQUiD Player query-awareness trend test...")
    logger.info(f"Trend query source: {TREND_SQL_FILE}")
    logger.info(f"Method: {args.method}")

    try:
        run_tag = time.strftime("%Y%m%d_%H%M%S")
        run_dir = RESULTS_BASE_DIR / f"run_{run_tag}"
        query_results_dir = run_dir / "query_results"
        query_tables_dir = run_dir / "query_tables"
        plots_dir = run_dir / "plots"

        # Optional preprocessing: generate ONE SQUiD DB from ONE combined input.
        if args.run_preprocessing:
            consolidated_db = run_squid_preprocessing(SQUID_ROOT, method=args.method)
        else:
            effective_method = "ensemble" if args.method == "ensemble" else args.method
            consolidated_db = (
                SQUID_ROOT
                / "databases"
                / "single_input"
                / "player_single"
                / "text_direct_ollama"
                / effective_method
                / "Player_0.db"
            )
            if not consolidated_db.exists():
                raise FileNotFoundError(
                    "Single-input SQUiD DB not found. "
                    "Run once with --run-preprocessing to generate it."
                )
            logger.info(
                f"Using existing single-input SQUiD DB: {consolidated_db}"
            )

        # Keep an immutable copy under this run directory.
        run_db = run_dir / "squid_single_generated.db"
        run_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(consolidated_db, run_db)
        logger.info(f"Copied DB to run directory: {run_db}")

        metrics = run_trend_queries(
            run_db,
            run_dir,
            query_results_dir,
            query_tables_dir,
            plots_dir,
        )

        save_metrics(metrics, run_dir)
        plot_metrics(metrics, plots_dir)

        success_count = sum(1 for m in metrics if m.success)
        avg_f1 = (
            sum(m.macro_f1 for m in metrics) / len(metrics) if metrics else 0.0
        )
        logger.info("=" * 80)
        logger.info(
            f"Completed: {success_count}/{len(metrics)} queries succeeded, "
            f"avg macro F1={avg_f1:.3f}"
        )
        logger.info(f"Generated DB: {run_db}")
        logger.info(f"Outputs under: {run_dir}")
        logger.info("=" * 80)

        return 0

    except Exception as exc:
        logger.exception(f"Trend test failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
