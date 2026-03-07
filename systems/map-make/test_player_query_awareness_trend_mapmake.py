"""
Run Q1..Q10 query-awareness trend benchmarking with Map&Make prompts.

This runner executes a practical 3-stage Map&Make pipeline for Player:
1) Atomization
2) Schema extraction
3) Table generation

To keep the comparison fair for Map&Make constraints, this script targets
single-table SELECT/FILTER queries (no JOIN).
"""

import csv
import hashlib
import json
import logging
import math
import re
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
import sqlglot
from openai import OpenAI
from sqlglot import exp

logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
WDIRS_DIR = PROJECT_ROOT / "systems" / "WDIRS"
MAPMAKE_DIR = PROJECT_ROOT / "systems" / "map-make"

sys.path.insert(0, str(WDIRS_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from config import QUERY_DIR, RESULTS_DIR  # type: ignore
from evaluation.config import EvalSettings as _EvalSettings, load_json as _load_json
from evaluation.gt_runner import GtRunner as _GtRunner
from evaluation.row_matcher import RowMatcher as _RowMatcher
from evaluation.sql_parser import SqlParser as _SqlParser
from test_player_query_awareness_trend import (  # type: ignore
    _infer_identity_col_for_query,
    evaluate_with_official_framework,
    parse_trend_queries,
)


DATASET_QUERY = "Player"
DEFAULT_TREND_SQL_FILE = QUERY_DIR / DATASET_QUERY / "query_aware_trend_queries_select_filter.sql"
GROUND_TRUTH_DIR = PROJECT_ROOT / "Data" / "Player"
ATTRIBUTES_FILE = PROJECT_ROOT / "Query" / DATASET_QUERY / "Player_attributes.json"
SOURCE_DATA_PLAYER_DIR = PROJECT_ROOT / "source_data" / "Player"

RESULTS_BASE_DIR = RESULTS_DIR / "player_query_awareness_trend_mapmake"
CACHE_DIR = MAPMAKE_DIR / ".cache" / "player_query_awareness_trend_mapmake"

PROMPT_ATOMIZATION = MAPMAKE_DIR / "code" / "prompts" / "Rotowire" / "Atomization.txt"
PROMPT_SCHEMA = MAPMAKE_DIR / "code" / "prompts" / "Rotowire" / "Schema_Extraction.txt"
PROMPT_TABLE = MAPMAKE_DIR / "code" / "prompts" / "Rotowire" / "Table_Generation.txt"


@dataclass
class TrendQueryMetrics:
    query_id: str
    query_text: str
    success: bool
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


class TokenTracker:
    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def snapshot(self) -> Tuple[int, int]:
        return self.prompt_tokens, self.completion_tokens

    def delta(self, before: Tuple[int, int]) -> Tuple[int, int]:
        return self.prompt_tokens - before[0], self.completion_tokens - before[1]

    def add(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens += max(0, int(prompt_tokens))
        self.completion_tokens += max(0, int(completion_tokens))


def setup_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
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


def _extract_usage_tokens(resp: Any) -> Tuple[int, int]:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return 0, 0
    p = getattr(usage, "prompt_tokens", None)
    c = getattr(usage, "completion_tokens", None)
    if p is not None and c is not None:
        return int(p), int(c)
    t = getattr(usage, "total_tokens", None)
    if p is not None and t is not None:
        return int(p), max(0, int(t) - int(p))
    return 0, 0


def _extract_json_payload(text: str) -> Optional[str]:
    start = None
    start_ch = ""
    for i, ch in enumerate(text):
        if ch in "{[":
            start = i
            start_ch = ch
            break
    if start is None:
        return None
    stack: List[str] = []
    in_string = False
    escape = False
    expected_end = "}" if start_ch == "{" else "]"
    for j in range(start, len(text)):
        ch = text[j]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if not stack:
                return None
            top = stack.pop()
            if (top == "{" and ch != "}") or (top == "[" and ch != "]"):
                return None
            if not stack and ch == expected_end:
                return text[start : j + 1]
    return None


class MapMakePipeline:
    def __init__(
        self,
        model: str,
        base_url: str,
        token_tracker: TokenTracker,
    ) -> None:
        self.model = model
        self.client = OpenAI(api_key="ollama", base_url=base_url.rstrip("/"))
        self.token_tracker = token_tracker
        self.prompt_atom = PROMPT_ATOMIZATION.read_text()
        self.prompt_schema = PROMPT_SCHEMA.read_text()
        self.prompt_table = PROMPT_TABLE.read_text()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.atom_cache_dir = CACHE_DIR / "atomization"
        self.atom_cache_dir.mkdir(parents=True, exist_ok=True)

    def _call_llm(
        self,
        prompt: str,
        *,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        retries: int = 2,
    ) -> str:
        last_err: Optional[Exception] = None
        for _ in range(retries + 1):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                p_toks, c_toks = _extract_usage_tokens(resp)
                self.token_tracker.add(p_toks, c_toks)
                return (resp.choices[0].message.content or "").strip()
            except Exception as exc:
                last_err = exc
                time.sleep(1.0)
        raise RuntimeError(f"LLM call failed after retries: {last_err}")

    def _atom_cache_path(self, table: str, doc_id: str, text: str) -> Path:
        h = hashlib.md5(text.encode("utf-8")).hexdigest()[:12]
        return self.atom_cache_dir / f"{table}_{doc_id}_{h}.json"

    def atomize(self, table: str, doc_id: str, text: str) -> List[str]:
        cache_path = self._atom_cache_path(table, doc_id, text)
        if cache_path.exists():
            return json.loads(cache_path.read_text())
        prompt = (
            f"{self.prompt_atom}\n\n"
            "Input Text:\n"
            f"{text}\n\n"
            "Return output in the required format."
        )
        out = self._call_llm(prompt, max_tokens=4096, temperature=0.0)
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        start_idx = 0
        for i, ln in enumerate(lines):
            if "atomic statements" in ln.lower():
                start_idx = i + 1
                break
        statements: List[str] = []
        for ln in lines[start_idx:]:
            if ln.startswith("###"):
                continue
            s = re.sub(r"^\d+[\).\s-]+", "", ln).strip("- ").strip()
            if not s:
                continue
            statements.append(s)
        if not statements:
            statements = [x.strip() for x in re.split(r"[.\n]+", text) if x.strip()]
        cache_path.write_text(json.dumps(statements, indent=2))
        return statements

    def schema_extract(
        self,
        table: str,
        sample_statements: List[str],
        required_columns: List[str],
    ) -> Dict[str, Any]:
        joined = "\n".join(sample_statements[:200])
        prompt = (
            f"{self.prompt_schema}\n\n"
            "Use this context to infer schema:\n"
            f"{joined}\n\n"
            f"Target table name: {table}\n"
            f"For this benchmark query, ensure at least these columns are covered: {required_columns}\n"
            "Return schema JSON exactly as requested in your format."
        )
        out = self._call_llm(prompt, max_tokens=4096, temperature=0.0)
        payload = _extract_json_payload(out)
        if not payload:
            return {table: {"row_headers": [], "column_headers": required_columns}}
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return {table: {"row_headers": [], "column_headers": required_columns}}

    def table_generate_row(
        self,
        table: str,
        statements: List[str],
        schema_obj: Dict[str, Any],
        required_columns: List[str],
    ) -> Dict[str, Any]:
        stmts = "\n".join(statements[:120])
        prompt = (
            f"{self.prompt_table}\n\n"
            "Statements:\n"
            f"{stmts}\n\n"
            "Schema:\n"
            f"{json.dumps(schema_obj, indent=2)}\n\n"
            "Additional constraints for this benchmark:\n"
            f"- Return exactly one JSON object with keys: {required_columns}\n"
            "- Use scalar values only (string, number, null).\n"
            "- If value is unavailable, return null.\n"
            "- Return ONLY the JSON object and nothing else."
        )
        out = self._call_llm(prompt, max_tokens=2048, temperature=0.0)
        payload = _extract_json_payload(out)
        if not payload:
            return {c: None for c in required_columns}
        try:
            obj = json.loads(payload)
            if isinstance(obj, list) and obj and isinstance(obj[0], dict):
                obj = obj[0]
            if not isinstance(obj, dict):
                return {c: None for c in required_columns}
            return {c: obj.get(c, None) for c in required_columns}
        except Exception:
            return {c: None for c in required_columns}


def _load_docs(table: str) -> List[Tuple[str, str]]:
    table_dir = SOURCE_DATA_PLAYER_DIR / table
    if not table_dir.exists():
        raise FileNotFoundError(f"Missing source table directory: {table_dir}")
    docs: List[Tuple[str, str]] = []
    for p in sorted(table_dir.glob("*.txt"), key=lambda x: int(x.stem)):
        docs.append((p.stem, p.read_text(errors="ignore")))
    if not docs:
        raise RuntimeError(f"No source files found for table: {table}")
    return docs


def _query_single_table_requirements(sql: str) -> Tuple[str, Set[str]]:
    parsed = sqlglot.parse_one(sql, error_level="ignore")
    if parsed is None:
        raise ValueError("Could not parse SQL query")
    if any(parsed.find_all(exp.Join)):
        raise ValueError("Map&Make trend runner supports SELECT/FILTER only (no JOIN)")
    tables = {t.name.lower() for t in parsed.find_all(exp.Table)}
    if len(tables) != 1:
        raise ValueError(f"Expected exactly one table, found: {sorted(tables)}")
    table = next(iter(tables))
    needed_cols: Set[str] = set()
    for col in parsed.find_all(exp.Column):
        needed_cols.add(col.name.lower())
    if not needed_cols:
        raise ValueError("No referenced columns in query")
    return table, needed_cols


def _coerce_types(table: str, df: pd.DataFrame, attrs: Dict[str, Any]) -> pd.DataFrame:
    out = df.copy()
    table_meta = {k.lower(): v for k, v in attrs.get(table, {}).items()}
    for col in out.columns:
        meta = table_meta.get(str(col).lower(), {})
        vt = str(meta.get("value_type", "")).lower()
        if vt in {"int", "integer", "float", "double", "number"}:
            out[col] = (
                out[col]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.replace(" ", "", regex=False)
            )
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _write_sqlite(table_name: str, df: pd.DataFrame, db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    with sqlite3.connect(db_path) as conn:
        df.to_sql(table_name, conn, if_exists="replace", index=False)


def _run_sql(db_path: Path, query_text: str) -> List[Dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(query_text)
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def _save_rows_csv(rows: List[Dict[str, Any]], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with out_csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["_empty"])
        return
    cols: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in cols:
                cols.append(key)
    with out_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


def run_trend_queries_mapmake(
    run_dir: Path,
    trend_sql_file: Path,
    model: str,
    ollama_base_url: str,
) -> List[TrendQueryMetrics]:
    query_results_dir = run_dir / "query_results"
    query_tables_dir = run_dir / "query_tables"
    query_eval_db_dir = run_dir / "query_eval_dbs"
    run_dir.mkdir(parents=True, exist_ok=True)
    query_results_dir.mkdir(parents=True, exist_ok=True)
    query_tables_dir.mkdir(parents=True, exist_ok=True)
    query_eval_db_dir.mkdir(parents=True, exist_ok=True)

    token_tracker = TokenTracker()
    pipeline = MapMakePipeline(model=model, base_url=ollama_base_url, token_tracker=token_tracker)
    attrs = _load_json(ATTRIBUTES_FILE) if ATTRIBUTES_FILE.exists() else {}
    identity_columns = {"city": "city_name", "player": "name", "team": "team_name", "owner": "name"}

    eval_attributes: Dict[str, Any] = attrs
    eval_settings = _EvalSettings(llm_provider="none")
    eval_gt_runner = _GtRunner(gt_dir=GROUND_TRUTH_DIR, attributes=eval_attributes)
    eval_sql_parser = _SqlParser()
    eval_row_matcher = _RowMatcher(settings=eval_settings)

    trend_queries = parse_trend_queries(trend_sql_file)
    if not trend_queries:
        raise RuntimeError(f"No trend queries found in {trend_sql_file}")

    metrics: List[TrendQueryMetrics] = []
    for query_id, query_text in trend_queries:
        logger.info("=" * 70)
        logger.info("Executing %s with Map&Make", query_id)
        before = token_tracker.snapshot()
        t0 = time.time()
        try:
            table, needed_cols = _query_single_table_requirements(query_text)
            identity_col = identity_columns.get(table, "name")
            needed_cols.add(identity_col)
            docs = _load_docs(table)

            atomized_docs: List[Tuple[str, List[str]]] = []
            for doc_id, txt in docs:
                atomized_docs.append((doc_id, pipeline.atomize(table=table, doc_id=doc_id, text=txt)))

            sample_statements: List[str] = []
            for _, statements in atomized_docs[:30]:
                sample_statements.extend(statements[:8])
            schema_obj = pipeline.schema_extract(
                table=table,
                sample_statements=sample_statements,
                required_columns=sorted(needed_cols),
            )

            records: List[Dict[str, Any]] = []
            for _, statements in atomized_docs:
                records.append(
                    pipeline.table_generate_row(
                        table=table,
                        statements=statements,
                        schema_obj=schema_obj,
                        required_columns=sorted(needed_cols),
                    )
                )

            table_df = pd.DataFrame(records)
            if table_df.empty:
                table_df = pd.DataFrame(columns=sorted(needed_cols))
            table_df = _coerce_types(table, table_df, attrs)

            query_eval_db = query_eval_db_dir / f"{query_id}.db"
            _write_sqlite(table, table_df, query_eval_db)
            rows = _run_sql(query_eval_db, query_text)

            out_csv = query_tables_dir / f"{query_id}.csv"
            out_json = query_tables_dir / f"{query_id}.json"
            _save_rows_csv(rows, out_csv)
            out_json.write_text(json.dumps(rows, indent=2, default=str))

            eval_out = evaluate_with_official_framework(
                query_text,
                rows,
                gt_runner=eval_gt_runner,
                sql_parser=eval_sql_parser,
                row_matcher=eval_row_matcher,
                settings=eval_settings,
                attributes=eval_attributes,
                identity_col=_infer_identity_col_for_query(query_text, identity_columns),
                phase2_db=query_eval_db,
                output_dir=query_results_dir / query_id,
            )

            latency = time.time() - t0
            d_prompt, d_completion = token_tracker.delta(before)
            d_total = d_prompt + d_completion

            item = TrendQueryMetrics(
                query_id=query_id,
                query_text=query_text,
                success=True,
                latency_s=latency,
                result_rows=len(rows),
                prompt_tokens=d_prompt,
                completion_tokens=d_completion,
                total_tokens=d_total,
                macro_f1=eval_out.get("macro_f1", 0.0),
                macro_precision=eval_out.get("macro_precision", 0.0),
                macro_recall=eval_out.get("macro_recall", 0.0),
                gt_result_count=eval_out.get("gt_result_count", 0),
                matched_rows=eval_out.get("matched_rows", 0),
                is_agg=eval_out.get("is_agg", False),
            )
            metrics.append(item)

            acc_path = query_results_dir / query_id / "acc.json"
            acc_path.parent.mkdir(parents=True, exist_ok=True)
            acc = {
                "query_id": query_id,
                "latency_s": round(latency, 4),
                "prompt_tokens": d_prompt,
                "completion_tokens": d_completion,
                "total_tokens": d_total,
                "result_rows": len(rows),
                "success": True,
                "macro_f1": item.macro_f1,
                "macro_precision": item.macro_precision,
                "macro_recall": item.macro_recall,
            }
            acc_path.write_text(json.dumps(acc, indent=2))

            logger.info(
                "%s: rows=%d latency=%.3fs tokens=%d F1=%.3f",
                query_id,
                item.result_rows,
                item.latency_s,
                item.total_tokens,
                item.macro_f1,
            )
        except Exception as exc:
            latency = time.time() - t0
            d_prompt, d_completion = token_tracker.delta(before)
            d_total = d_prompt + d_completion
            metrics.append(
                TrendQueryMetrics(
                    query_id=query_id,
                    query_text=query_text,
                    success=False,
                    latency_s=latency,
                    result_rows=0,
                    prompt_tokens=d_prompt,
                    completion_tokens=d_completion,
                    total_tokens=d_total,
                    macro_f1=0.0,
                    macro_precision=0.0,
                    macro_recall=0.0,
                    gt_result_count=0,
                    matched_rows=0,
                    is_agg=False,
                    error=str(exc),
                )
            )
            logger.exception("%s failed: %s", query_id, exc)

    return metrics


def save_metrics(metrics: List[TrendQueryMetrics], run_dir: Path) -> None:
    rows = [asdict(m) for m in metrics]
    out_json = run_dir / "trend_metrics.json"
    out_csv = run_dir / "trend_metrics.csv"
    out_json.write_text(json.dumps(rows, indent=2))
    with out_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)

    avg_f1 = sum(m.macro_f1 for m in metrics) / len(metrics) if metrics else 0.0
    if not math.isfinite(avg_f1):
        avg_f1 = 0.0
    token_summary = {
        "num_queries": len(metrics),
        "successful_queries": sum(1 for m in metrics if m.success),
        "total_prompt_tokens": sum(m.prompt_tokens for m in metrics),
        "total_completion_tokens": sum(m.completion_tokens for m in metrics),
        "total_tokens": sum(m.total_tokens for m in metrics),
        "avg_macro_f1": avg_f1,
    }
    (run_dir / "token_cost.json").write_text(json.dumps(token_summary, indent=2))
    logger.info("Saved metrics JSON: %s", out_json)
    logger.info("Saved metrics CSV:  %s", out_csv)


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Run Player query-awareness trend test with Map&Make prompts.")
    ap.add_argument(
        "--trend-sql-file",
        type=str,
        default=str(DEFAULT_TREND_SQL_FILE),
        help="Path to Q1..Q10 SQL file (must be single-table SELECT/FILTER queries).",
    )
    ap.add_argument(
        "--model",
        type=str,
        default="qwen2.5:7b-instruct",
        help="Ollama model name.",
    )
    ap.add_argument(
        "--ollama-base-url",
        type=str,
        default="http://localhost:11434/v1",
        help="OpenAI-compatible Ollama endpoint.",
    )
    args = ap.parse_args()

    run_tag = time.strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_BASE_DIR / f"run_{run_tag}"
    run_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(run_dir / "query_awareness_trend_mapmake.log")

    trend_sql_file = Path(args.trend_sql_file)
    logger.info("Starting Player query-awareness trend test (Map&Make)...")
    logger.info("Run directory: %s", run_dir)
    logger.info("Trend query source: %s", trend_sql_file)
    logger.info("Model: %s @ %s", args.model, args.ollama_base_url)
    logger.info("Prompt files: %s | %s | %s", PROMPT_ATOMIZATION, PROMPT_SCHEMA, PROMPT_TABLE)

    try:
        metrics = run_trend_queries_mapmake(
            run_dir=run_dir,
            trend_sql_file=trend_sql_file,
            model=args.model,
            ollama_base_url=args.ollama_base_url,
        )
        save_metrics(metrics, run_dir)
        logger.info("Outputs under: %s", run_dir)
        return 0
    except Exception as exc:
        logger.exception("Map&Make trend test failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
