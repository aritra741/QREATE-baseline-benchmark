"""
Run Q1..Q10 query-awareness trend benchmarking with Unify on Player.

This mirrors the benchmark contract used by WDIRS/DocETL:
1) Parse Q1..Q10 SQL trend queries from Query/Player/query_aware_trend_queries.sql
2) Execute equivalent natural-language queries through Unify
3) Evaluate with the official framework
4) Save per-query outputs + run-level metrics/plots/token-cost
"""

import argparse
import csv
import json
import logging
import math
import os
import pickle
import shutil
import sys
import time
import types
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from openai import OpenAI

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except Exception:
    MATPLOTLIB_AVAILABLE = False


logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.parent
WDIRS_DIR = PROJECT_ROOT / "systems" / "WDIRS"
UNIFY_MAIN_DIR = PROJECT_ROOT / "systems" / "Unify" / "main"
TREND_SQL_FILE = PROJECT_ROOT / "Query" / "Player" / "query_aware_trend_queries.sql"
GROUND_TRUTH_DIR = PROJECT_ROOT / "Data" / "Player"
ATTRIBUTES_FILE = PROJECT_ROOT / "Query" / "Player" / "Player_attributes.json"
SOURCE_DATA_PLAYER_DIR = PROJECT_ROOT / "source_data" / "Player"
RESULTS_BASE_DIR = PROJECT_ROOT / "results" / "player_query_awareness_trend_unify"
PREPROCESS_INDEXES_DIR = PROJECT_ROOT / "preprocess_unify" / "indexes" / "Player"

PLAYER_TABLES = ("player", "team", "city", "owner")
IDENTITY_COLUMNS = {"city": "city_name", "player": "name", "team": "team_name", "owner": "name"}

# Q1..Q10 NL queries aligned with the trend SQL workload.
NL_QUERY_SPECS: Dict[str, str] = {
    "Q1": "List each player's name, nationality, and age with their team name and team location.",
    "Q2": "For players older than 25, list player name, position, team name, and team founded year.",
    "Q3": "For players with draft pick at least 0, list player name, draft pick, college, and team name.",
    "Q4": "List team name and location with matched city name and state name.",
    "Q5": "List player name with team name, city name, and city state by linking player, team, and city.",
    "Q6": "For players younger than 35, list player name, position, city name, and city population via player, team, city.",
    "Q7": "For players with draft pick greater than 0, list player name, college, team name, and city GDP.",
    "Q8": "For cities with area greater than 100, list player name, player birth date, team name, and city area.",
    "Q9": "Starting from city and traversing city, team, player, list city name, state, team name, and player name for players younger than 40.",
    "Q10": "Starting from city and traversing city, team, player, list city name, state, team name, player name, and player college for players older than 20.",
}


sys.path.insert(0, str(WDIRS_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from token_counter import GLOBAL_COUNTER, ensure_precise_tokenizer_ready, count_tokens  # type: ignore
from evaluation.config import EvalSettings as _EvalSettings, load_json as _load_json  # type: ignore
from evaluation.gt_runner import GtRunner as _GtRunner  # type: ignore
from evaluation.row_matcher import RowMatcher as _RowMatcher  # type: ignore
from evaluation.sql_parser import SqlParser as _SqlParser  # type: ignore
from test_player_query_awareness_trend import (  # type: ignore
    parse_trend_queries,
    evaluate_with_official_framework,
    _infer_identity_col_for_query,
)


# Unify imports need cwd safety because prompt modules read local files at import time.
if "vllm" not in sys.modules:
    try:
        import vllm  # noqa: F401
    except Exception:
        sys.modules["vllm"] = types.ModuleType("vllm")

sys.path.insert(0, str(UNIFY_MAIN_DIR))
_ORIG_CWD = os.getcwd()
os.chdir(str(UNIFY_MAIN_DIR))
try:
    from unify import recursive_plan_generation  # type: ignore
    from PlanManager import planManager  # type: ignore
    from semanticParse import semantic_parse, replace_parsed_elements_with_identifiers, BQMatcher  # type: ignore
    from chunk import load_process_data_chunks, ChunkExtractor  # type: ignore
    from embed import EmbedModel  # type: ignore
    from index import indexHNSW  # type: ignore
    from utils.llm_config import ModelConfig  # type: ignore
finally:
    os.chdir(_ORIG_CWD)


@dataclass
class TrendQueryMetrics:
    query_id: str
    query_text: str
    nl_query: str
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


class TokenTracker:
    """Tracks token usage across Unify LLM calls."""

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


def _messages_token_count(messages: Optional[List[Dict[str, Any]]]) -> int:
    if not messages:
        return 0
    total = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total += count_tokens(content)
        else:
            total += count_tokens(str(content))
    return total


def patch_unify_for_token_tracking(token_tracker: TokenTracker) -> None:
    """Monkey-patch Unify ModelConfig.create_completion for global token tracking."""
    original = ModelConfig.create_completion

    def wrapped_create_completion(self, client, temperature=0.1, top_p=0.9, max_tokens=1000, messages=None):  # noqa: ANN001
        prompt_toks = _messages_token_count(messages)
        response = original(
            self,
            client,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            messages=messages,
        )
        completion_toks = count_tokens(response or "")
        token_tracker.add(prompt_toks, completion_toks)
        GLOBAL_COUNTER.record(
            input_tokens=prompt_toks,
            output_tokens=completion_toks,
            operation="unify",
        )
        return response

    ModelConfig.create_completion = wrapped_create_completion


def _save_rows_csv(rows: List[Dict[str, Any]], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with out_csv.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["_empty"])
        return
    cols: List[str] = []
    for row in rows:
        for k in row.keys():
            if k not in cols:
                cols.append(k)
    with out_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


def _build_run_paths() -> Tuple[Path, Path, Path, Path]:
    run_tag = time.strftime("%Y%m%d_%H%M%S")
    run_dir = RESULTS_BASE_DIR / f"run_{run_tag}"
    query_results_dir = run_dir / "query_results"
    query_tables_dir = run_dir / "query_tables"
    plots_dir = run_dir / "plots"
    return run_dir, query_results_dir, query_tables_dir, plots_dir


def _copy_player_corpus_to_single_dir(dst_dir: Path) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for table in PLAYER_TABLES:
        src = SOURCE_DATA_PLAYER_DIR / table
        if not src.exists():
            logger.warning("Player table dir missing, skipping: %s", src)
            continue
        for p in sorted(src.glob("*.txt"), key=lambda x: int(x.stem)):
            # Prefix table name to avoid collisions between 1.txt, 2.txt, ...
            dst = dst_dir / f"{table}__{p.stem}.txt"
            if not dst.exists():
                shutil.copy2(p, dst)
                copied += 1
    logger.info("Prepared combined corpus at %s (%d files copied this run)", dst_dir, copied)
    return dst_dir


def _try_load_preprocessed_index(run_dir: Path) -> Optional[Dict[str, Any]]:
    if not PREPROCESS_INDEXES_DIR.exists():
        return None
    merged_cache = run_dir / "cache" / "player_preprocessed_merged.pkl"
    if merged_cache.exists():
        try:
            with merged_cache.open("rb") as f:
                return pickle.load(f)
        except Exception as exc:
            logger.warning("Could not load merged preprocess cache: %s", exc)

    all_chunks: List[Any] = []
    all_ids: List[Any] = []
    all_embeds: List[Any] = []
    all_chunk_locs: List[Any] = []
    all_file_data: Dict[str, str] = {}
    found = False

    for table in PLAYER_TABLES:
        pkl = PREPROCESS_INDEXES_DIR / table / "preprocessed_data.pkl"
        if not pkl.exists():
            continue
        try:
            with pkl.open("rb") as f:
                data = pickle.load(f)
            found = True
            all_file_data.update(data.get("all_file_data", {}))
            all_chunks.extend(list(data.get("all_chunks", [])))
            all_ids.extend(list(data.get("all_ids", [])))
            all_embeds.extend(list(data.get("all_embeds", [])))
            all_chunk_locs.extend(list(data.get("all_chunk_locs", [])))
        except Exception as exc:
            logger.warning("Could not load preprocess index for %s: %s", table, exc)

    if not found or not all_chunks:
        return None

    merged = {
        "all_file_data": all_file_data,
        "all_chunks": np.array(all_chunks),
        "all_ids": np.array(all_ids),
        "all_embeds": np.array(all_embeds),
        "all_chunk_locs": all_chunk_locs,
    }
    merged_cache.parent.mkdir(parents=True, exist_ok=True)
    try:
        with merged_cache.open("wb") as f:
            pickle.dump(merged, f)
    except Exception as exc:
        logger.warning("Could not write merged preprocess cache: %s", exc)
    return merged


def _build_unify_data_index(
    run_dir: Path,
    embed_model: "EmbedModel",
    doc_path: Path,
    *,
    prefer_preprocessed: bool,
) -> Tuple[Dict[str, str], Any]:
    if prefer_preprocessed:
        pre = _try_load_preprocessed_index(run_dir)
        if pre is not None:
            logger.info("Using merged preprocess_unify cache for Player.")
            idx = indexHNSW(pre["all_chunks"], pre["all_embeds"], pre["all_ids"], pre["all_chunk_locs"])
            return pre["all_file_data"], idx
        logger.warning("Preprocessed cache unavailable/incomplete; falling back to on-the-fly chunk+embed.")

    chunk_extractor = ChunkExtractor()
    all_file_data, all_chunks, all_ids, all_embeds, all_chunk_locs = load_process_data_chunks(
        embed_model, chunk_extractor, str(doc_path)
    )
    idx = indexHNSW(all_chunks, all_embeds, all_ids, all_chunk_locs)
    return all_file_data, idx


def _extract_unify_final_result(pm: "planManager") -> Any:
    if pm.BQ_list and "IDPlan" in pm.BQ_list[-1] and pm.BQ_list[-1]["IDPlan"]:
        return pm.BQ_list[-1]["IDPlan"][0].get("Result")
    return None


def _to_rows(raw_result: Any, identity_col: str) -> List[Dict[str, Any]]:
    """
    Coerce Unify output to list-of-dicts for evaluator compatibility.
    """
    if raw_result is None:
        return []
    if isinstance(raw_result, str):
        s = raw_result.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            return _to_rows(parsed, identity_col)
        except Exception:
            return [{"value": s}]
    if isinstance(raw_result, dict):
        if all(not isinstance(v, (dict, list, tuple, set)) for v in raw_result.values()):
            return [dict(raw_result)]
        rows: List[Dict[str, Any]] = []
        for k, v in raw_result.items():
            if isinstance(v, dict):
                row = {identity_col: k}
                row.update(v)
                rows.append(row)
            elif isinstance(v, (list, tuple, set)):
                for item in v:
                    if isinstance(item, dict):
                        row = {identity_col: k}
                        row.update(item)
                        rows.append(row)
                    else:
                        rows.append({identity_col: k, "value": str(item)})
            else:
                rows.append({identity_col: k, "value": v})
        return rows
    if isinstance(raw_result, (list, tuple, set)):
        rows: List[Dict[str, Any]] = []
        for item in raw_result:
            if isinstance(item, dict):
                rows.append(dict(item))
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                rows.append({identity_col: item[0], "value": item[1]})
            else:
                rows.append({identity_col: str(item)})
        return rows
    if isinstance(raw_result, (int, float, bool)):
        return [{"value": raw_result}]
    return [{"value": str(raw_result)}]


def _run_single_unify_query(
    question: str,
    client: "OpenAI",
    chat_model: "ModelConfig",
    embed_model: "EmbedModel",
    all_file_data: Dict[str, str],
    idx: Any,
) -> Tuple[Any, bool, str]:
    parsed_result = semantic_parse(question, client, chat_model)
    transformed_question = replace_parsed_elements_with_identifiers(question, parsed_result)
    bq_matcher = BQMatcher(embed_model)

    final_flag, final_plan, final_bq_list, partial_question_list = recursive_plan_generation(
        question,
        transformed_question,
        bq_matcher,
        client,
        chat_model,
        embed_model,
        current_plan=[],
        use_BQ_list=[],
        partial_question_list=[],
        depth=0,
    )

    pm = planManager(
        question,
        final_plan,
        client,
        chat_model,
        final_bq_list,
        all_file_data,
        parsed_result,
        partial_question_list,
        embed_model,
        idx,
    )
    pm.execute_with_plan()
    result = _extract_unify_final_result(pm)
    delta_type = "UNIFY_PLAN" if final_flag else "UNIFY_PARTIAL_PLAN"
    success = result is not None
    return result, success, delta_type


def run_trend_queries_unify(
    run_dir: Path,
    *,
    llm_model_path: str,
    tokenizer_path: str,
    sentence_model_path: str,
    api_key: str,
    api_base: str,
    prefer_preprocessed: bool,
) -> List[TrendQueryMetrics]:
    query_results_dir = run_dir / "query_results"
    query_tables_dir = run_dir / "query_tables"
    plots_dir = run_dir / "plots"
    corpus_dir = run_dir / "corpus" / "player_all_docs"

    run_dir.mkdir(parents=True, exist_ok=True)
    query_results_dir.mkdir(parents=True, exist_ok=True)
    query_tables_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    doc_path = _copy_player_corpus_to_single_dir(corpus_dir)
    client = OpenAI(api_key=api_key, base_url=api_base)
    chat_model = ModelConfig(llm_model_path)
    embed_model = EmbedModel(tokenizer_path=tokenizer_path, sentence_model_path=sentence_model_path)
    all_file_data, idx = _build_unify_data_index(
        run_dir, embed_model, doc_path, prefer_preprocessed=prefer_preprocessed
    )

    token_tracker = TokenTracker()
    patch_unify_for_token_tracking(token_tracker)

    eval_attributes: Dict[str, Any] = _load_json(ATTRIBUTES_FILE) if ATTRIBUTES_FILE.exists() else {}
    eval_settings = _EvalSettings(llm_provider="none")
    eval_gt_runner = _GtRunner(gt_dir=GROUND_TRUTH_DIR, attributes=eval_attributes)
    eval_sql_parser = _SqlParser()
    eval_row_matcher = _RowMatcher(settings=eval_settings)

    trend_queries = parse_trend_queries(TREND_SQL_FILE)
    if not trend_queries:
        raise RuntimeError(f"No trend queries found in {TREND_SQL_FILE}")

    metrics: List[TrendQueryMetrics] = []
    for query_id, query_text in trend_queries:
        logger.info("=" * 70)
        logger.info("Executing %s with Unify", query_id)
        nl_query = NL_QUERY_SPECS.get(
            query_id,
            f"Answer this query over the player dataset: {query_text}",
        )
        logger.info("[NL] %s", nl_query)
        before = token_tracker.snapshot()
        t0 = time.time()

        try:
            raw_result, success, delta_type = _run_single_unify_query(
                nl_query, client, chat_model, embed_model, all_file_data, idx
            )
            latency = time.time() - t0
            d_prompt, d_completion = token_tracker.delta(before)
            d_total = d_prompt + d_completion

            identity_col = _infer_identity_col_for_query(query_text, IDENTITY_COLUMNS)
            rows = _to_rows(raw_result, identity_col or "name")

            out_csv = query_tables_dir / f"{query_id}.csv"
            out_json = query_tables_dir / f"{query_id}.json"
            _save_rows_csv(rows, out_csv)
            out_json.write_text(json.dumps(rows, indent=2, default=str))

            eval_out: Dict[str, Any] = {}
            if success:
                eval_out = evaluate_with_official_framework(
                    query_text,
                    rows,
                    gt_runner=eval_gt_runner,
                    sql_parser=eval_sql_parser,
                    row_matcher=eval_row_matcher,
                    settings=eval_settings,
                    attributes=eval_attributes,
                    identity_col=identity_col,
                    # Aggregation/augmentation paths are sqlite-specific in some baselines.
                    # For Unify output we provide existing project DB as fallback if needed.
                    phase2_db=WDIRS_DIR / ".databases" / "wdirs.db",
                    output_dir=query_results_dir / query_id,
                )

            item = TrendQueryMetrics(
                query_id=query_id,
                query_text=query_text,
                nl_query=nl_query,
                success=success,
                delta_type=delta_type,
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
                error=None if success else "No final result from Unify",
            )
            metrics.append(item)

            acc_path = query_results_dir / query_id / "acc.json"
            acc_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                acc_data = {}
                if acc_path.exists():
                    acc_data = json.loads(acc_path.read_text())
                acc_data["query_id"] = query_id
                acc_data["latency_s"] = round(latency, 4)
                acc_data["prompt_tokens"] = d_prompt
                acc_data["completion_tokens"] = d_completion
                acc_data["total_tokens"] = d_total
                acc_data["result_rows"] = len(rows)
                acc_data["success"] = bool(success)
                acc_data.setdefault("macro_f1", eval_out.get("macro_f1", 0.0))
                acc_data.setdefault("macro_precision", eval_out.get("macro_precision", 0.0))
                acc_data.setdefault("macro_recall", eval_out.get("macro_recall", 0.0))
                acc_path.write_text(json.dumps(acc_data, indent=2))
            except Exception as acc_err:
                logger.warning("Could not augment %s with token/latency: %s", acc_path, acc_err)

            logger.info(
                "%s: success=%s rows=%d latency=%.3fs tokens=%d F1=%.3f",
                query_id,
                item.success,
                item.result_rows,
                item.latency_s,
                item.total_tokens,
                item.macro_f1,
            )
        except Exception as exc:
            latency = time.time() - t0
            d_prompt, d_completion = token_tracker.delta(before)
            metrics.append(
                TrendQueryMetrics(
                    query_id=query_id,
                    query_text=query_text,
                    nl_query=nl_query,
                    success=False,
                    delta_type="ERROR",
                    latency_s=latency,
                    result_rows=0,
                    prompt_tokens=d_prompt,
                    completion_tokens=d_completion,
                    total_tokens=d_prompt + d_completion,
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
    logger.info("Saved metrics JSON: %s", out_json)
    logger.info("Saved metrics CSV:  %s", out_csv)


def plot_metrics(metrics: List[TrendQueryMetrics], plots_dir: Path) -> None:
    if not MATPLOTLIB_AVAILABLE:
        logger.warning("matplotlib not available - skipping plot generation")
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
    p = [m.macro_precision for m in ordered]
    r = [m.macro_recall for m in ordered]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Player Query-Awareness Trend with Unify (Q1..Q10)", fontsize=16, fontweight="bold")

    axes[0, 0].plot(x, result_rows, marker="o", color="#7f8c8d")
    axes[0, 0].set_title("Result Table Size (rows)")
    axes[0, 0].set_xticks(x)
    axes[0, 0].set_xticklabels(x_labels)
    axes[0, 0].set_ylabel("rows")
    axes[0, 0].grid(alpha=0.3)

    axes[0, 1].plot(x, token_cost, marker="o", color="#8e44ad")
    axes[0, 1].set_title("Token Cost")
    axes[0, 1].set_xticks(x)
    axes[0, 1].set_xticklabels(x_labels)
    axes[0, 1].set_ylabel("tokens")
    axes[0, 1].grid(alpha=0.3)

    axes[1, 0].plot(x, latency, marker="o", color="#2980b9")
    axes[1, 0].set_title("Latency")
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

    plots_dir.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    summary_plot = plots_dir / "query_awareness_trend_summary.png"
    plt.savefig(summary_plot, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved trend summary plot: %s", summary_plot)

    fig2, ax2 = plt.subplots(figsize=(12, 5))
    ax2.plot(x, p, marker="o", label="Precision")
    ax2.plot(x, r, marker="o", label="Recall")
    ax2.plot(x, f1, marker="o", label="F1")
    ax2.set_xticks(x)
    ax2.set_xticklabels(x_labels)
    ax2.set_ylim(0.0, 1.0)
    ax2.set_title("Macro Precision/Recall/F1 by Query")
    ax2.set_ylabel("score")
    ax2.grid(alpha=0.3)
    ax2.legend()
    plt.tight_layout()
    prf_plot = plots_dir / "query_awareness_trend_prf.png"
    plt.savefig(prf_plot, dpi=300, bbox_inches="tight")
    plt.close(fig2)
    logger.info("Saved trend PRF plot: %s", prf_plot)


def main() -> int:
    ensure_precise_tokenizer_ready()
    RESULTS_BASE_DIR.mkdir(parents=True, exist_ok=True)

    run_dir, query_results_dir, query_tables_dir, plots_dir = _build_run_paths()
    setup_logging(run_dir / "query_awareness_trend_unify.log")

    ap = argparse.ArgumentParser(description="Run Player query-awareness trend test with Unify")
    ap.add_argument("--llm-model-path", type=str, default="qwen2.5:7b-instruct")
    ap.add_argument("--tokenizer-path", type=str, default=str(UNIFY_MAIN_DIR / "models" / "tokenizer"))
    ap.add_argument("--sentence-model-path", type=str, default=str(UNIFY_MAIN_DIR / "models" / "embedding"))
    ap.add_argument("--api-key", type=str, default="EMPTY")
    ap.add_argument("--api-base", type=str, default="http://localhost:11434/v1")
    ap.add_argument(
        "--disable-preprocessed-index",
        action="store_true",
        help="Force on-the-fly chunk+embed instead of preprocess_unify cache.",
    )
    args = ap.parse_args()

    logger.info("Starting Player query-awareness trend test (Unify)...")
    logger.info("Run directory: %s", run_dir)
    logger.info("Trend query source: %s", TREND_SQL_FILE)
    logger.info("Model: %s @ %s", args.llm_model_path, args.api_base)
    logger.info("Use preprocess_unify cache: %s", not args.disable_preprocessed_index)
    logger.info("Results dirs: %s | %s | %s", query_results_dir, query_tables_dir, plots_dir)

    try:
        metrics = run_trend_queries_unify(
            run_dir=run_dir,
            llm_model_path=args.llm_model_path,
            tokenizer_path=args.tokenizer_path,
            sentence_model_path=args.sentence_model_path,
            api_key=args.api_key,
            api_base=args.api_base,
            prefer_preprocessed=not args.disable_preprocessed_index,
        )
        save_metrics(metrics, run_dir)
        plot_metrics(metrics, plots_dir)

        success_count = sum(1 for m in metrics if m.success)
        avg_f1 = sum(m.macro_f1 for m in metrics) / len(metrics) if metrics else 0.0
        if not math.isfinite(avg_f1):
            avg_f1 = 0.0
        logger.info("=" * 80)
        logger.info(
            "Completed: %d/%d queries succeeded, avg macro F1=%.3f",
            success_count,
            len(metrics),
            avg_f1,
        )
        token_summary = GLOBAL_COUNTER.summary_str()
        logger.info(token_summary)
        token_json_path = run_dir / "token_cost.json"
        GLOBAL_COUNTER.save_json(token_json_path)
        logger.info("Token cost JSON saved to: %s", token_json_path)
        logger.info("Outputs under: %s", run_dir)
        logger.info("=" * 80)
        return 0
    except Exception as exc:
        logger.exception("Unify trend test failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
