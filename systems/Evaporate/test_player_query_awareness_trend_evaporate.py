"""
Run Q1..Q10 query-awareness trend benchmarking with Evaporate extraction.

This runner intentionally uses the original Evaporate code under
`systems/evaporate-main` and evaluates query answers with the same official
framework used by other system trend scripts in this repository.
"""

import json
import logging
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
EVAPORATE_MAIN_DIR = PROJECT_ROOT / "systems" / "evaporate-main"

sys.path.insert(0, str(EVAPORATE_MAIN_DIR))
sys.path.insert(0, str(WDIRS_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from config import QUERY_DIR, RESULTS_DIR  # type: ignore
from evaporate.configs import set_profiler_args  # type: ignore
from evaporate.run_profiler import prerun_profiler, get_attribute_function  # type: ignore

from evaluation.config import EvalSettings as _EvalSettings, load_json as _load_json
from evaluation.gt_runner import GtRunner as _GtRunner
from evaluation.row_matcher import RowMatcher as _RowMatcher
from evaluation.sql_parser import SqlParser as _SqlParser
from test_player_query_awareness_trend import (  # type: ignore
    parse_trend_queries,
    evaluate_with_official_framework,
    _infer_identity_col_for_query,
)


DATASET_QUERY = "Player"
TREND_SQL_FILE = QUERY_DIR / DATASET_QUERY / "query_aware_trend_queries.sql"
GROUND_TRUTH_DIR = PROJECT_ROOT / "Data" / "Player"
ATTRIBUTES_FILE = PROJECT_ROOT / "Query" / DATASET_QUERY / "Player_attributes.json"
SOURCE_DATA_PLAYER_DIR = PROJECT_ROOT / "source_data" / "Player"

RESULTS_BASE_DIR = RESULTS_DIR / "player_query_awareness_trend_evaporate"

# Keep total-token pricing explicit and configurable for fair reporting.
TOTAL_TOKEN_COST_PER_1K_USD = 0.0
_OLLAMA_LAST_TOTAL_TOKENS = 0


@dataclass
class TrendQueryMetrics:
    query_id: str
    query_text: str
    success: bool
    latency_s: float
    result_rows: int
    total_tokens: int
    total_cost_usd: float
    macro_f1: float
    macro_precision: float
    macro_recall: float
    gt_result_count: int
    matched_rows: int
    is_agg: bool
    extracted_attributes: int
    error: Optional[str] = None


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


def patch_evaporate_for_ollama(ollama_model: str, ollama_base_url: str) -> None:
    """
    Patch evaporate-main's non-OpenAI inference branch to call Ollama and
    propagate total token usage back through Evaporate's get_response().
    """
    import evaporate.utils as evap_utils  # type: ignore

    def _ollama_together_call(prompt: str, model: str, streaming: bool = False, max_tokens: int = 1024) -> str:
        del streaming, model
        global _OLLAMA_LAST_TOTAL_TOKENS
        client = OpenAI(api_key="ollama", base_url=ollama_base_url.rstrip("/"))
        messages = [
            {"role": "system", "content": "You are an AI assistant."},
            {"role": "user", "content": prompt},
        ]
        resp = client.chat.completions.create(
            model=ollama_model,
            messages=messages,
            max_tokens=max_tokens,
            stream=False,
        )
        usage = getattr(resp, "usage", None)
        if usage is not None:
            _OLLAMA_LAST_TOTAL_TOKENS = int(getattr(usage, "total_tokens", 0) or 0)
        else:
            _OLLAMA_LAST_TOTAL_TOKENS = 0
        return (resp.choices[0].message.content or "").strip()

    def _patched_get_response(
        prompt: str,
        manifest: Any,
        overwrite: bool = False,
        max_toks: int = 10,
        stop_token: Optional[str] = None,
        gold_choices: List[str] = [],
        verbose: bool = False,
    ) -> Tuple[Any, Any]:
        del overwrite
        prompt = prompt.strip()
        if gold_choices:
            gold_choices = [" " + g.strip() for g in gold_choices]
            if isinstance(manifest, dict) and manifest.get("__name") != "openai":
                response = _ollama_together_call(prompt, manifest.get("__name", ollama_model), max_tokens=max_toks)
                num_tokens = _OLLAMA_LAST_TOTAL_TOKENS
            else:
                response_obj = manifest.run(
                    prompt,
                    gold_choices=gold_choices,
                    overwrite_cache=False,
                    return_response=True,
                )
                response_obj = response_obj.get_json_response()["choices"][0]
                log_prob = response_obj["text_logprob"]
                response = response_obj["text"]
                num_tokens = response_obj["usage"]["total_tokens"]
                if verbose:
                    print("\n***Prompt***\n", prompt)
                    print("\n***Response***\n", response)
                return response, log_prob
            if verbose:
                print("\n***Prompt***\n", prompt)
                print("\n***Response***\n", response)
            return response, num_tokens
        else:
            if isinstance(manifest, dict) and manifest.get("__name") != "openai":
                response = _ollama_together_call(prompt, manifest.get("__name", ollama_model), max_tokens=max_toks)
                num_tokens = _OLLAMA_LAST_TOTAL_TOKENS
            else:
                response_obj = manifest.run(
                    prompt,
                    max_tokens=max_toks,
                    stop_token=stop_token,
                    overwrite_cache=False,
                    return_response=True,
                )
                try:
                    num_tokens = response_obj.get_usage_obj().usages[0].total_tokens
                except Exception:
                    num_tokens = 0
                response_obj = response_obj.get_json_response()
                response = response_obj["choices"][0]["text"]
            stop = "---"
            response = response.strip().split(stop)[0].strip() if stop else response.strip()
            if verbose:
                print("\n***Prompt***\n", prompt)
                print("\n***Response***\n", response)
            return response, num_tokens

    evap_utils.together_call = _ollama_together_call
    evap_utils.get_response = _patched_get_response


def _table_attr_map() -> Dict[str, Dict[str, Any]]:
    attrs = _load_json(ATTRIBUTES_FILE) if ATTRIBUTES_FILE.exists() else {}
    out: Dict[str, Dict[str, Any]] = {}
    for table, cols in attrs.items():
        out[table.lower()] = {k.lower(): v for k, v in cols.items()}
    return out


def _build_gold_extractions_json(table: str, output_path: Path, table_attrs: Dict[str, Dict[str, Any]]) -> None:
    gt_csv = GROUND_TRUTH_DIR / f"{table}.csv"
    src_dir = SOURCE_DATA_PLAYER_DIR / table
    if not gt_csv.exists():
        raise FileNotFoundError(f"Missing ground truth table: {gt_csv}")
    if not src_dir.exists():
        raise FileNotFoundError(f"Missing source data directory: {src_dir}")

    df = pd.read_csv(gt_csv)
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "id" not in df.columns:
        raise ValueError(f"Ground truth table must contain ID column: {gt_csv}")

    known_files = {p.name for p in src_dir.glob("*.txt")}
    allowed_cols = set(table_attrs.get(table, {}).keys())

    payload: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        row_id_raw = row.get("id")
        if pd.isna(row_id_raw):
            continue
        try:
            row_id = int(row_id_raw)
        except Exception:
            row_id = int(float(row_id_raw))
        file_name = f"{row_id}.txt"
        if file_name not in known_files:
            continue
        rec: Dict[str, Any] = {}
        for col in allowed_cols:
            val = row.get(col, "")
            if pd.isna(val):
                val = ""
            rec[col] = val
        payload[file_name] = rec

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, default=str))


def _query_requirements(sql: str) -> Dict[str, Set[str]]:
    expr = sqlglot.parse_one(sql, error_level="ignore")

    alias_to_table: Dict[str, str] = {}
    tables: Set[str] = set()
    for table_node in expr.find_all(exp.Table):
        tname = table_node.name.lower()
        tables.add(tname)
        alias = table_node.alias
        if alias:
            alias_to_table[alias.lower()] = tname
        alias_to_table[tname] = tname

    required: Dict[str, Set[str]] = {t: set() for t in tables}
    for col in expr.find_all(exp.Column):
        cname = col.name.lower()
        if col.table:
            tkey = col.table.lower()
            table = alias_to_table.get(tkey, tkey)
            required.setdefault(table, set()).add(cname)
        elif len(tables) == 1:
            only_table = next(iter(tables))
            required.setdefault(only_table, set()).add(cname)

    return required


def _coerce_types(table: str, df: pd.DataFrame, table_attrs: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
    out = df.copy()
    attrs = table_attrs.get(table, {})
    for col in out.columns:
        meta = attrs.get(col.lower())
        if not meta:
            continue
        value_type = str(meta.get("value_type", "")).lower()
        if value_type in {"int", "integer", "float", "double", "number"}:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _write_tables_sqlite(table_to_df: Dict[str, pd.DataFrame], db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(str(db_path))
    try:
        for table, df in table_to_df.items():
            df.to_sql(table, con, if_exists="replace", index=False)
        con.commit()
    finally:
        con.close()


def _run_sql(db_path: Path, query_text: str) -> List[Dict[str, Any]]:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(query_text)
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def _safe_file_attribute(attr: str) -> str:
    x = attr.lower().replace("/", "_").replace(")", "").replace("-", "_")
    x = x.replace("(", "").replace(" ", "_")
    return x[:30] if len(x) > 30 else x


class EvaporateTableRunner:
    def __init__(
        self,
        table: str,
        run_dir: Path,
        model_name: str,
        api_keys: List[str],
        table_attrs: Dict[str, Dict[str, Any]],
    ) -> None:
        self.table = table
        self.table_attrs = table_attrs
        self.base_dir = run_dir / "evaporate_artifacts" / table
        self.base_dir.mkdir(parents=True, exist_ok=True)

        gold_json = self.base_dir / f"{table}_gold_extractions.json"
        _build_gold_extractions_json(table, gold_json, table_attrs)

        profiler_info: Dict[str, Any] = {
            "data_lake": f"player_{table}",
            "data_dir": str(SOURCE_DATA_PLAYER_DIR / table),
            "base_data_dir": str(self.base_dir),
            "gold_extractions_file": str(gold_json),
            "do_end_to_end": False,
            "num_attr_to_cascade": 50,
            "num_top_k_scripts": 10,
            "train_size": 10,
            "combiner_mode": "ws",
            "use_dynamic_backoff": True,
            "KEYS": api_keys,
            "MODELS": [model_name],
            "EXTRACTION_MODELS": [model_name],
            "GOLD_KEY": model_name,
            "overwrite_cache": False,
            "extraction_fraction_thresh": 0.9,
            "use_abstension": True,
            "remove_tables": False,
            "body_only": False,
            "chunk_size": 3000,
            "max_chunks_per_file": -1,
            "slice_results": False,
            "set_dicts": "",
            "topic": [],
        }

        self.profiler_args = set_profiler_args(profiler_info)
        self.data_dict = prerun_profiler(self.profiler_args)
        self.extracted_attrs: Set[str] = set()

    def ensure_attr_extracted(self, attr: str) -> int:
        attr = attr.lower()
        if attr in self.extracted_attrs:
            return 0
        _, _, _, num_toks = get_attribute_function(self.profiler_args, self.data_dict, attr)
        self.extracted_attrs.add(attr)
        return int(num_toks)

    def load_attr_predictions(self, attr: str) -> Dict[str, Any]:
        file_attr = _safe_file_attribute(attr)
        p = Path(self.profiler_args.generative_index_path) / (
            f"{self.profiler_args.run_string}_{file_attr}_file2metadata.json"
        )
        if not p.exists():
            return {}
        raw = json.loads(p.read_text())
        out: Dict[str, Any] = {}
        for full_path, value in raw.items():
            out[Path(full_path).name] = value
        return out

    def build_pred_table(self, attrs: Set[str]) -> pd.DataFrame:
        src_dir = SOURCE_DATA_PLAYER_DIR / self.table
        files = sorted(src_dir.glob("*.txt"), key=lambda p: int(p.stem))
        rows: List[Dict[str, Any]] = []
        attr_to_pred = {a: self.load_attr_predictions(a) for a in attrs}

        for p in files:
            row: Dict[str, Any] = {}
            for attr in attrs:
                val = attr_to_pred[attr].get(p.name, "")
                if isinstance(val, list):
                    val = ", ".join([str(v) for v in val])
                row[attr] = val
            rows.append(row)

        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame(columns=sorted(attrs))
        return _coerce_types(self.table, df, self.table_attrs)


def run_trend_queries_evaporate(
    run_dir: Path,
    model_name: str,
    api_keys: List[str],
) -> List[TrendQueryMetrics]:
    query_results_dir = run_dir / "query_results"
    query_tables_dir = run_dir / "query_tables"
    query_eval_db_dir = run_dir / "query_eval_dbs"
    run_dir.mkdir(parents=True, exist_ok=True)
    query_results_dir.mkdir(parents=True, exist_ok=True)
    query_tables_dir.mkdir(parents=True, exist_ok=True)
    query_eval_db_dir.mkdir(parents=True, exist_ok=True)

    table_attrs = _table_attr_map()
    table_runners: Dict[str, EvaporateTableRunner] = {}
    for table in table_attrs.keys():
        table_runners[table] = EvaporateTableRunner(
            table=table,
            run_dir=run_dir,
            model_name=model_name,
            api_keys=api_keys,
            table_attrs=table_attrs,
        )

    eval_attributes: Dict[str, Any] = _load_json(ATTRIBUTES_FILE) if ATTRIBUTES_FILE.exists() else {}
    eval_settings = _EvalSettings(llm_provider="none")
    eval_gt_runner = _GtRunner(gt_dir=GROUND_TRUTH_DIR, attributes=eval_attributes)
    eval_sql_parser = _SqlParser()
    eval_row_matcher = _RowMatcher(settings=eval_settings)

    identity_columns = {
        "city": "city_name",
        "player": "name",
        "team": "team_name",
        "owner": "name",
    }

    trend_queries = parse_trend_queries(TREND_SQL_FILE)
    if not trend_queries:
        raise RuntimeError(f"No trend queries found in {TREND_SQL_FILE}")

    metrics: List[TrendQueryMetrics] = []
    for query_id, query_text in trend_queries:
        logger.info("=" * 70)
        logger.info("Executing %s with Evaporate extraction", query_id)
        t0 = time.time()
        query_tokens = 0
        new_attr_count = 0
        try:
            req = _query_requirements(query_text)
            table_to_df: Dict[str, pd.DataFrame] = {}

            for table, attrs in req.items():
                if table not in table_runners:
                    raise ValueError(f"Unsupported table in query: {table}")
                valid_attrs = {a for a in attrs if a in table_attrs.get(table, {})}
                if not valid_attrs:
                    valid_attrs = set(table_attrs.get(table, {}).keys())

                runner = table_runners[table]
                for attr in sorted(valid_attrs):
                    if attr not in runner.extracted_attrs:
                        toks = runner.ensure_attr_extracted(attr)
                        query_tokens += toks
                        new_attr_count += 1
                table_to_df[table] = runner.build_pred_table(valid_attrs)

            query_db = query_eval_db_dir / f"{query_id}.db"
            _write_tables_sqlite(table_to_df, query_db)
            pred_rows = _run_sql(query_db, query_text)

            out_csv = query_tables_dir / f"{query_id}.csv"
            out_json = query_tables_dir / f"{query_id}.json"
            pd.DataFrame(pred_rows).to_csv(out_csv, index=False)
            out_json.write_text(json.dumps(pred_rows, indent=2, default=str))

            eval_out = evaluate_with_official_framework(
                query_text,
                pred_rows,
                gt_runner=eval_gt_runner,
                sql_parser=eval_sql_parser,
                row_matcher=eval_row_matcher,
                settings=eval_settings,
                attributes=eval_attributes,
                identity_col=_infer_identity_col_for_query(query_text, identity_columns),
                phase2_db=query_db,
                output_dir=query_results_dir / query_id,
            )

            latency = time.time() - t0
            query_cost = (query_tokens / 1000.0) * TOTAL_TOKEN_COST_PER_1K_USD
            item = TrendQueryMetrics(
                query_id=query_id,
                query_text=query_text,
                success=True,
                latency_s=latency,
                result_rows=len(pred_rows),
                total_tokens=query_tokens,
                total_cost_usd=query_cost,
                macro_f1=eval_out.get("macro_f1", 0.0),
                macro_precision=eval_out.get("macro_precision", 0.0),
                macro_recall=eval_out.get("macro_recall", 0.0),
                gt_result_count=eval_out.get("gt_result_count", 0),
                matched_rows=eval_out.get("matched_rows", 0),
                is_agg=eval_out.get("is_agg", False),
                extracted_attributes=new_attr_count,
            )
            metrics.append(item)

            acc_path = query_results_dir / query_id / "acc.json"
            acc_path.parent.mkdir(parents=True, exist_ok=True)
            acc = {
                "query_id": query_id,
                "latency_s": round(latency, 4),
                "total_tokens": query_tokens,
                "total_cost_usd": query_cost,
                "new_extracted_attributes": new_attr_count,
                "result_rows": len(pred_rows),
                "success": True,
                "macro_f1": item.macro_f1,
                "macro_precision": item.macro_precision,
                "macro_recall": item.macro_recall,
            }
            acc_path.write_text(json.dumps(acc, indent=2))

            logger.info(
                "%s: rows=%d latency=%.3fs tokens=%d cost=$%.4f F1=%.3f",
                query_id,
                item.result_rows,
                item.latency_s,
                item.total_tokens,
                item.total_cost_usd,
                item.macro_f1,
            )
        except Exception as exc:
            latency = time.time() - t0
            item = TrendQueryMetrics(
                query_id=query_id,
                query_text=query_text,
                success=False,
                latency_s=latency,
                result_rows=0,
                total_tokens=query_tokens,
                total_cost_usd=(query_tokens / 1000.0) * TOTAL_TOKEN_COST_PER_1K_USD,
                macro_f1=0.0,
                macro_precision=0.0,
                macro_recall=0.0,
                gt_result_count=0,
                matched_rows=0,
                is_agg=False,
                extracted_attributes=new_attr_count,
                error=str(exc),
            )
            metrics.append(item)
            logger.exception("%s failed: %s", query_id, exc)

    return metrics


def save_metrics(metrics: List[TrendQueryMetrics], run_dir: Path) -> None:
    rows = [asdict(m) for m in metrics]
    (run_dir / "trend_metrics.json").write_text(json.dumps(rows, indent=2))
    pd.DataFrame(rows).to_csv(run_dir / "trend_metrics.csv", index=False)

    total_tokens = int(sum(m.total_tokens for m in metrics))
    total_cost = float(sum(m.total_cost_usd for m in metrics))
    avg_f1 = float(sum(m.macro_f1 for m in metrics) / max(1, len(metrics)))
    summary = {
        "num_queries": len(metrics),
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
        "avg_macro_f1": avg_f1,
        "successful_queries": sum(1 for m in metrics if m.success),
    }
    (run_dir / "token_cost.json").write_text(json.dumps(summary, indent=2))


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Run Player query-awareness trend with Evaporate extraction.")
    ap.add_argument(
        "--model",
        type=str,
        default="qwen2.5:7b-instruct",
        help="Evaporate model name. For Ollama path use qwen2.5:7b-instruct.",
    )
    ap.add_argument(
        "--api-keys",
        type=str,
        default="",
        help="Comma-separated API keys for Manifest/OpenAI clients.",
    )
    ap.add_argument(
        "--ollama-base-url",
        type=str,
        default="http://localhost:11434/v1",
        help="OpenAI-compatible Ollama endpoint.",
    )
    ap.add_argument(
        "--total-token-cost-per-1k",
        type=float,
        default=0.0,
        help="USD cost per 1k total tokens for reporting.",
    )
    args = ap.parse_args()

    global TOTAL_TOKEN_COST_PER_1K_USD
    TOTAL_TOKEN_COST_PER_1K_USD = float(args.total_token_cost_per_1k)
    api_keys = [k.strip() for k in args.api_keys.split(",") if k.strip()]
    patch_evaporate_for_ollama(ollama_model=args.model, ollama_base_url=args.ollama_base_url)

    run_tag = time.strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_BASE_DIR / f"run_{run_tag}"
    run_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(run_dir / "query_awareness_trend_evaporate.log")

    logger.info("Run directory: %s", run_dir)
    logger.info("Evaporate model: %s", args.model)
    logger.info("Ollama base URL: %s", args.ollama_base_url)
    logger.info("Token cost per 1k: $%.6f", TOTAL_TOKEN_COST_PER_1K_USD)

    try:
        metrics = run_trend_queries_evaporate(
            run_dir=run_dir,
            model_name=args.model,
            api_keys=api_keys,
        )
        save_metrics(metrics, run_dir)
        logger.info("Outputs under: %s", run_dir)
        return 0
    except Exception as exc:
        logger.exception("Trend run failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
