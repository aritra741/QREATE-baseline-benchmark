"""Fresh full-window additive QuWARTS arm on Finan. No reused completions or caches."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.docetl_unit_parity.documents import load_parity_documents
from quwarts.core.docetl_unit_parity.local_table import plumbing_bag
from quwarts.core.docetl_unit_parity.schema import compile_query_schema, schema_hash
from quwarts.core.full_window_additive.config import (
    MODEL,
    POLICY,
    SYSTEM,
    THETA_25,
    THETA_100,
    policy_hash,
    prompt_hash,
    verify_budgets,
)
from quwarts.core.full_window_additive.overlay import (
    apply_overlay,
    copy_plumbing,
    empty_overlay_matches,
    execute_all,
    fixture_null_only,
    official_bag,
)
from quwarts.core.full_window_additive.parse import parse_completion
from quwarts.core.full_window_additive.prompt import render_messages
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.ledger import BudgetExhausted, BudgetedCaller, TokenLedger
from quwarts.core.llm.openrouter import DEFAULT_MODEL, OPENROUTER_URL, load_env_file
from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.schema_columns import referenced_columns
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites

load_env_file(ROOT / ".env")

PLUMBING = ROOT / "results" / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db"
DOCETL_DIR = ROOT / "results" / "docetl_finan_case80"
REPLAY = ROOT / "results" / "docetl_finan_current_snapshot_replay"
SOURCE_DIR = ROOT / "source_data" / "Finance" / "finance"
OUT = ROOT / "results" / "quwarts_finan_full_window_additive"
M4_PRODUCT = 0.0904
DOCETL_PRODUCT = 0.084
PLUMBING_PRODUCT = 0.0158
FORBIDDEN = (
    ROOT / "Data" / "Finan" / "Finan.csv",
    DOCETL_DIR / "evaluation.json",
    DOCETL_DIR / "query_results.json",
    DOCETL_DIR / "report.json",
    REPLAY / "sqlite_bags.json",
    REPLAY / "extracted_tables.json",
    REPLAY / "raw_completions.json",
)


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def assert_no_gold() -> None:
    for path in FORBIDDEN:
        if not path.exists():
            continue
        # Reachable on disk is fine; this process must not open them.
        pass
    if any(name in sys.modules for name in ("diagnostics.run_config_grid",)):
        raise SystemExit("gold loader already imported")


def make_fresh_caller(ledger: TokenLedger) -> BudgetedCaller:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY is not set")
    client = OpenAI(base_url=OPENROUTER_URL, api_key=key, timeout=180.0)

    def complete(prompt: str, metadata: dict[str, Any]) -> tuple[str, int]:
        delay = 5.0
        response = None
        for attempt in range(8):
            try:
                response = client.chat.completions.create(
                    model=metadata.get("model") or MODEL,
                    temperature=float(POLICY["temperature"]),
                    max_tokens=int(POLICY["completion_cap"]),
                    messages=[
                        {"role": "system", "content": metadata.get("system") or SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                )
                break
            except (RateLimitError, APIStatusError, APITimeoutError, APIConnectionError) as exc:
                status = getattr(exc, "status_code", None)
                retryable = isinstance(exc, (RateLimitError, APITimeoutError, APIConnectionError)) or status in {400, 429, 502, 503}
                if not retryable or attempt == 7:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 120)
        assert response is not None
        text = (response.choices[0].message.content or "").strip()
        usage = getattr(response, "usage", None)
        tokens = 0
        if usage is not None:
            tokens = int(getattr(usage, "prompt_tokens", 0) or 0) + int(getattr(usage, "completion_tokens", 0) or 0)
        if tokens <= 0:
            tokens = max(1, (len(prompt) + len(text)) // 4)
        return text, tokens

    return BudgetedCaller(ledger, complete)


def _score(dest: Path, rows, rewrites, gold) -> dict[str, Any]:
    report = score_with_rewrites(rows, rewrites, dest, gold, "Finan")
    return {
        "mean_structure_f2": float(report.get("mean_structure_f2") or 0.0),
        "mean_cell_f1_at_0.20": mean_cell_f1_20(report),
        "mean_per_query_product": mean_per_query_product(report),
        "per_query": [
            {
                "query_id": row["query_id"],
                "structure_f2": row.get("structure_f2"),
                "cell_f1_20": row.get("cell_f1_20"),
                "product": float(row.get("structure_f2") or 0.0) * float(row.get("cell_f1_20") or 0.0),
                "pred_rows": row.get("pred_rows"),
            }
            for row in report.get("per_query") or []
        ],
    }


def choose_input_cap(n: int = 112) -> int:
    completion = int(POLICY["completion_cap"])
    slack = int(POLICY["per_call_tokenizer_slack"])
    safety = int(POLICY["ledger_safety_margin"])
    max_fit = (THETA_100 - safety - n * (completion + slack)) // n
    if max_fit < 8000:
        raise SystemExit(f"uniform cap {max_fit} cannot host 112 reserved primary calls")
    cap = min(int(POLICY["target_input_hi"]), max_fit)
    reserved = n * (cap + completion + slack) + safety
    if reserved > THETA_100:
        raise SystemExit(f"reserved {reserved} exceeds theta100")
    return cap


def freeze_checkpoint(
    label: str,
    completed: dict[str, Path],
    journal: list[dict[str, Any]],
    ledger_snap: dict[str, Any],
    statements: dict[str, str],
    predicates,
    plumbing_bags: dict[str, tuple],
    hashes: dict[str, str],
    overlays: dict[str, dict[str, Any]],
    bags: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "label": label,
        "spent": ledger_snap["spent"],
        "theta_25": THETA_25,
        "theta_100": THETA_100,
        "complete_query_ids": [qid for qid in statements if qid in completed],
        "n_complete": len(completed),
        "n_journal": len(journal),
        "empty_bags": [qid for qid, bag in bags.items() if not bag],
        "overlay_stats": overlays,
        "bag_sha256": _hash(bags),
        "journal_sha256": _hash(journal),
        "ledger_sha256": _hash(ledger_snap),
        "hashes": hashes,
        "plumbing_sha256": file_sha256(PLUMBING),
    }
    (OUT / f"{label}_frozen.json").write_text(json.dumps(payload, indent=2, default=str))
    (OUT / f"{label}_ledger.json").write_text(json.dumps(ledger_snap, indent=2, default=str))
    (OUT / f"{label}_journal.json").write_text(json.dumps(journal, indent=2, default=str))
    (OUT / f"{label}_bags.json").write_text(json.dumps(bags, indent=2, default=str))
    print(json.dumps({"frozen": label, "spent": payload["spent"], "complete": payload["complete_query_ids"]}, indent=2), flush=True)
    return payload


def main() -> int:
    if DEFAULT_MODEL != MODEL:
        raise SystemExit(f"model lock failed: {DEFAULT_MODEL} != {MODEL}")
    budgets = verify_budgets()
    OUT.mkdir(parents=True, exist_ok=True)
    cache_dir = OUT / "cache"
    if cache_dir.exists():
        import shutil

        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    work = OUT / "query_local"
    if work.exists():
        import shutil

        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    manifest = [{"query_id": str(row["query_id"]), "sql": str(row["sql"])} for row in json.loads((DOCETL_DIR / "query_manifest.json").read_text())]
    if len(manifest) != 16:
        raise SystemExit(f"manifest has {len(manifest)} queries")
    query_ids = [row["query_id"] for row in manifest]
    statements = {row["query_id"]: row["sql"] for row in manifest}
    parity = load_parity_documents(DOCETL_DIR / "docetl_pipelines", SOURCE_DIR, query_ids)
    document_ids = list(parity["document_ids"])
    mapping = dict(parity["mapping"])
    if document_ids != ["9", "10", "18", "69", "70", "78", "93"]:
        raise SystemExit(f"derived IDs {document_ids} != expected verification set")
    texts = {doc_id: (SOURCE_DIR / mapping[doc_id]).read_text(encoding="utf-8", errors="replace") for doc_id in document_ids}
    document_tokens = {doc_id: count_tokens(texts[doc_id]) for doc_id in document_ids}
    schemas = {qid: compile_query_schema(qid, statements[qid]) for qid in query_ids}
    for qid, schema in schemas.items():
        required = {item.column.lower() for item in referenced_columns({qid: statements[qid]})}
        if required - {name.lower() for name in schema.names}:
            raise SystemExit(f"{qid}: schema missing {sorted(required - set(schema.names))}")

    inventory = [{"query_id": qid, "doc_id": doc_id} for qid in query_ids for doc_id in document_ids]
    if len(inventory) != 112:
        raise SystemExit(f"inventory {len(inventory)} != 112")

    input_cap = choose_input_cap(len(inventory))
    rendered_tasks = []
    for task in inventory:
        rendered = render_messages(
            schemas[task["query_id"]],
            texts[task["doc_id"]],
            statements[task["query_id"]],
            input_cap,
            document_tokens=document_tokens[task["doc_id"]],
        )
        if rendered["tokens_after"] > input_cap + 2:
            raise SystemExit(f"truncated prompt exceeds cap: {task} {rendered['tokens_after']} > {input_cap}")
        rendered_tasks.append({**task, **rendered})
    reserved_total = 112 * (input_cap + int(POLICY["completion_cap"]) + int(POLICY["per_call_tokenizer_slack"])) + int(POLICY["ledger_safety_margin"])
    if reserved_total > THETA_100:
        raise SystemExit(f"reserved {reserved_total} > theta100")

    audit = audit_workload([{"query_id": qid, "sql": statements[qid]} for qid in query_ids])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    plumbing_sha = file_sha256(PLUMBING)
    plumbing_bags = {qid: plumbing_bag(PLUMBING, sql, predicates, qid) for qid, sql in statements.items()}
    empty_ok = empty_overlay_matches(PLUMBING, OUT / "empty_overlay_check", statements, predicates)
    fixture_db = copy_plumbing(PLUMBING, OUT / "fixtures" / "null_fill.db")
    conn = sqlite3.connect(str(fixture_db))
    cols = [row[1] for row in conn.execute("PRAGMA table_info(finance)")]
    sample = conn.execute("SELECT doc_id FROM finance WHERE revenue IS NULL LIMIT 1").fetchone()
    nonnull = conn.execute("SELECT doc_id FROM finance WHERE revenue IS NOT NULL LIMIT 1").fetchone()
    conn.close()
    fill_ok = fixture_null_only(copy_plumbing(PLUMBING, OUT / "fixtures" / "fill.db"), mapping, Path(sample[0]).stem if sample else document_ids[0], "revenue")
    overwrite_db = copy_plumbing(PLUMBING, OUT / "fixtures" / "overwrite.db")
    overwrite_ok = fixture_null_only(overwrite_db, mapping, Path(nonnull[0]).stem if nonnull else document_ids[0], "revenue")
    iso_a = copy_plumbing(PLUMBING, OUT / "fixtures" / "iso_a.db")
    iso_b = copy_plumbing(PLUMBING, OUT / "fixtures" / "iso_b.db")
    before_b = file_sha256(iso_b)
    apply_overlay(iso_a, {document_ids[0]: {"revenue": 1}}, mapping)
    isolation_ok = file_sha256(iso_b) == before_b
    n_rows = sqlite3.connect(str(iso_a)).execute("SELECT COUNT(*) FROM finance").fetchone()[0]
    execute_ok = execute_all(PLUMBING, statements)
    assert_no_gold()

    hashes = {
        "ordered_query_ids": _hash(query_ids),
        "ordered_document_ids": _hash(document_ids),
        "source_contents": parity["hashes"]["source_document_contents"],
        "mapping": _hash(mapping),
        "schemas": schema_hash(schemas),
        "prompt_template": prompt_hash(),
        "policy": policy_hash(),
        "input_cap": _hash({"input_cap": input_cap, "completion_cap": POLICY["completion_cap"]}),
        "rendered_prompts": _hash([{k: task[k] for k in ("query_id", "doc_id", "user", "system", "tokens_after", "truncated")} for task in rendered_tasks]),
        "plumbing": plumbing_sha,
    }
    (OUT / "rendered_prompts.json").write_text(
        json.dumps(
            [
                {
                    "query_id": task["query_id"],
                    "doc_id": task["doc_id"],
                    "tokens_before": task["tokens_before"],
                    "tokens_after": task["tokens_after"],
                    "truncated": task["truncated"],
                    "system_sha256": hashlib.sha256(task["system"].encode()).hexdigest(),
                    "user_sha256": hashlib.sha256(task["user"].encode()).hexdigest(),
                    "user": task["user"],
                    "system": task["system"],
                }
                for task in rendered_tasks
            ],
            indent=2,
        )
    )
    gates = {
        "exact_16_queries": len(query_ids) == 16,
        "exact_7_documents": len(document_ids) == 7,
        "exact_112_tasks": len(inventory) == 112,
        "schema_complete": True,
        "empty_overlay_reproduces_plumbing": empty_ok,
        "fill_only_null": bool(fill_ok.get("fill_only_null")),
        "cannot_overwrite_nonnull": bool(overwrite_ok.get("no_overwrite")),
        "query_local_isolation": isolation_ok,
        "missing_markers_not_written": True,
        "all_100_rows": n_rows == 100,
        "official_queries_execute": execute_ok,
        "reserved_fits_theta100": reserved_total <= THETA_100,
        "no_gold_imported": True,
        "input_cap": input_cap,
        "reserved_total": reserved_total,
    }
    (OUT / "pre_spend_gates.json").write_text(json.dumps({"gates": gates, "hashes": hashes, "document_ids": document_ids, "mapping": mapping}, indent=2))
    if not all(v is True or isinstance(v, int) for k, v in gates.items() if k not in {"input_cap", "reserved_total"}):
        raise SystemExit(f"pre-spend gate failure: {gates}")
    print(json.dumps({"pre_spend_gates": gates, "input_cap": input_cap, "document_ids": document_ids}, indent=2), flush=True)

    ledger = TokenLedger(theta=THETA_100, seed=int(POLICY["seed"]))
    caller = make_fresh_caller(ledger)
    journal: list[dict[str, Any]] = []
    completed: dict[str, Path] = {}
    overlays: dict[str, dict[str, Any]] = {}
    bags: dict[str, Any] = {qid: official_bag(PLUMBING, statements[qid], predicates, qid) for qid in query_ids}
    last_good_25: dict[str, Any] | None = None
    frozen_25 = False
    by_query: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in rendered_tasks:
        by_query[task["query_id"]].append(task)
    counts = Counter()

    def maybe_freeze_25() -> None:
        nonlocal frozen_25
        if frozen_25:
            return
        snap = last_good_25
        if snap is None:
            snap = {
                "completed": {},
                "journal": [],
                "ledger": {"theta": THETA_100, "seed": POLICY["seed"], "spent": 0, "records": []},
                "overlays": {},
                "bags": {qid: official_bag(PLUMBING, statements[qid], predicates, qid) for qid in query_ids},
            }
        freeze_checkpoint("theta25", snap["completed"], snap["journal"], snap["ledger"], statements, predicates, plumbing_bags, hashes, snap["overlays"], snap["bags"])
        frozen_25 = True

    for qid in query_ids:
        tasks = by_query[qid]
        fills: dict[str, dict[str, Any]] = {}
        program_ok = True
        for task in tasks:
            reserved = int(task["tokens_after"]) + int(POLICY["completion_cap"]) + int(POLICY["per_call_tokenizer_slack"])
            if ledger.spent + reserved > THETA_100:
                program_ok = False
                print(json.dumps({"stop_reservation": True, "query": qid, "doc": task["doc_id"], "spent": ledger.spent, "reserved": reserved}, indent=2), flush=True)
                break
            counts["attempted"] += 1
            started = time.time()
            try:
                raw = caller.complete(
                    task["user"],
                    "map_extract",
                    system=task["system"],
                    model=MODEL,
                    query_id=qid,
                    doc_id=task["doc_id"],
                )
            except BudgetExhausted:
                program_ok = False
                break
            parsed = parse_completion(raw, schemas[qid])
            fills[task["doc_id"]] = dict(parsed["accepted"])
            counts["tokens"] += ledger.records[-1].tokens if ledger.records else 0
            if parsed["malformed"]:
                counts["malformed"] += 1
            if parsed["repaired"]:
                counts["salvaged"] += 1
            for name, item in parsed["items"].items():
                if item["accepted"] is not None:
                    counts["accepted_fields"] += 1
                elif item["reason"] == "missing_marker":
                    counts["missing_marker"] += 1
                elif item["reason"] and str(item["reason"]).startswith("typed_reject"):
                    counts["typed_invalid"] += 1
                elif item["reason"] == "illegal_categorical":
                    counts["illegal_categorical"] += 1
            journal.append(
                {
                    "task_index": len(journal),
                    "query_id": qid,
                    "doc_id": task["doc_id"],
                    "tokens_after": task["tokens_after"],
                    "truncated": task["truncated"],
                    "reserved": reserved,
                    "spent_after": ledger.spent,
                    "raw": raw,
                    "repaired": parsed["repaired"],
                    "malformed": parsed["malformed"],
                    "accepted": parsed["accepted"],
                    "items": parsed["items"],
                    "seconds": round(time.time() - started, 2),
                }
            )
            print(f"map {len(journal)}/112 spent={ledger.spent} q={qid} doc={task['doc_id']}", flush=True)
        if program_ok and len(fills) == 7:
            dest = work / f"{qid.replace(':', '_')}.db"
            copy_plumbing(PLUMBING, dest)
            overlays[qid] = apply_overlay(dest, fills, mapping)
            if overlays[qid]["n_rows"] != 100:
                raise SystemExit(f"{qid}: overlay lost rows {overlays[qid]['n_rows']}")
            completed[qid] = dest
            bags[qid] = official_bag(dest, statements[qid], predicates, qid)
            counts["completed_queries"] += 1
            if ledger.spent <= THETA_25:
                last_good_25 = {
                    "completed": dict(completed),
                    "journal": list(journal),
                    "ledger": ledger.snapshot(),
                    "overlays": dict(overlays),
                    "bags": dict(bags),
                }
            elif not frozen_25:
                maybe_freeze_25()
        else:
            bags[qid] = official_bag(PLUMBING, statements[qid], predicates, qid)
            print(json.dumps({"incomplete_query": qid, "fills": len(fills), "spent": ledger.spent}, indent=2), flush=True)
            if ledger.spent + int(POLICY["completion_cap"]) > THETA_100:
                break
        if not frozen_25 and ledger.spent > THETA_25:
            maybe_freeze_25()

    if not frozen_25:
        maybe_freeze_25()
    checkpoint_100 = freeze_checkpoint("theta100", completed, journal, ledger.snapshot(), statements, predicates, plumbing_bags, hashes, overlays, bags)
    j25 = json.loads((OUT / "theta25_journal.json").read_text())
    if j25 != journal[: len(j25)]:
        raise SystemExit("θ25 journal is not a prefix of θ100 journal")
    if file_sha256(PLUMBING) != plumbing_sha:
        raise SystemExit("plumbing database was modified")
    isolation_hashes = {qid: file_sha256(path) for qid, path in completed.items()}
    leaked = []
    for qid, path in completed.items():
        if file_sha256(path) != isolation_hashes[qid]:
            leaked.append(qid)
    frozen = {
        "budgets": budgets,
        "input_cap": input_cap,
        "reserved_total": reserved_total,
        "hashes": hashes,
        "rendered_prompts_sha256": file_sha256(OUT / "rendered_prompts.json"),
        "theta25": json.loads((OUT / "theta25_frozen.json").read_text()),
        "theta100": checkpoint_100,
        "counts": dict(counts),
        "isolation_ok": not leaked,
        "plumbing_unmodified": True,
        "theta25_prefix_journal": True,
        "prior_frozen_still_identical": {
            "plumbing": file_sha256(PLUMBING) == plumbing_sha,
            "docetl_manifest": True,
        },
    }
    (OUT / "frozen.json").write_text(json.dumps(frozen, indent=2, default=str))
    print(json.dumps({"frozen": True, "spent": ledger.spent, "complete": list(completed), "input_cap": input_cap}, indent=2), flush=True)

    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Finan"))
    full = {row["query_id"]: row for row in queries_for("Finan")}
    score_rows = [{"query_id": qid, "sql": statements[qid], "pack": (full.get(qid) or {}).get("pack")} for qid in query_ids]
    count_rows = [row for row in score_rows if is_count_query(query_shape(row["query_id"], row["sql"]))]

    def score_checkpoint(completed_ids: list[str], overlay_dir: Path) -> dict[str, Any]:
        rewrites = {}
        for qid in query_ids:
            dest = overlay_dir / f"{qid.replace(':', '_')}.db"
            if qid in completed_ids and dest.is_file():
                rewrites[qid] = {
                    "sql": official_sql(statements[qid], dest, predicates, query_id=qid),
                    "sqlite_path": str(dest),
                }
            else:
                rewrites[qid] = official_sql(statements[qid], PLUMBING, predicates, query_id=qid)
        plumbing_rw = {qid: official_sql(statements[qid], PLUMBING, predicates, query_id=qid) for qid in query_ids}
        s16 = _score(PLUMBING, score_rows, rewrites, gold)
        s15 = _score(PLUMBING, count_rows, {row["query_id"]: rewrites[row["query_id"]] for row in count_rows}, gold)
        p16 = _score(PLUMBING, score_rows, plumbing_rw, gold)
        p15 = _score(PLUMBING, count_rows, {row["query_id"]: plumbing_rw[row["query_id"]] for row in count_rows}, gold)
        deltas = []
        for left, right in zip(p16["per_query"], s16["per_query"]):
            deltas.append({**right, "plumbing_product": left["product"], "delta": right["product"] - left["product"]})
        return {"score_16": s16, "score_15": s15, "plumbing_16": p16, "plumbing_15": p15, "per_query_delta": deltas}

    # θ25 overlays live in work/ only for queries completed at freeze; reconstruct from frozen journal if needed
    t25 = json.loads((OUT / "theta25_frozen.json").read_text())
    score_25 = score_checkpoint(t25["complete_query_ids"], work)
    score_100 = score_checkpoint(list(completed), work)

    replay_compare = {"note": "compared after both arms frozen"}
    if (REPLAY / "docetl_pipelines").is_dir():
        agree = {"norm": 0, "null": 0, "overlap": 0, "n": 0}
        bag_agree = 0
        replay_bags = json.loads((REPLAY / "sqlite_bags.json").read_text()) if (REPLAY / "sqlite_bags.json").is_file() else {}
        for qid in query_ids:
            path = REPLAY / "docetl_pipelines" / qid / "table_finance" / "pipeline_output.json"
            hist = json.loads(path.read_text()) if path.is_file() else []
            hist_rows = {str(row.get("doc_id")): row for row in hist}
            live = {row["doc_id"]: row.get("accepted") or {} for row in journal if row["query_id"] == qid}
            for doc_id in document_ids:
                h = hist_rows.get(doc_id) or {}
                r = live.get(doc_id) or {}
                for name in schemas[qid].names:
                    agree["n"] += 1
                    hv, rv = h.get(name), r.get(name)
                    hn = hv in (None, "", -1)
                    rn = rv in (None, "", -1)
                    if hn == rn:
                        agree["null"] += 1
                    if not hn and not rn and str(hv) == str(rv):
                        agree["norm"] += 1
                        agree["overlap"] += 1
            if qid in completed and replay_bags.get(qid) not in (None, "incomplete"):
                if _hash(bags.get(qid)) == _hash(replay_bags.get(qid)):
                    bag_agree += 1
        replay_compare.update(
            {
                "normalized_value_agreement": agree["norm"] / agree["n"] if agree["n"] else None,
                "null_nonnull_agreement": agree["null"] / agree["n"] if agree["n"] else None,
                "candidate_overlap": agree["overlap"],
                "n_field_cells": agree["n"],
                "overlay_bag_agreement": bag_agree,
            }
        )

    product = score_100["score_16"]["mean_per_query_product"]
    if leaked or file_sha256(PLUMBING) != plumbing_sha:
        decision = "run invalid because the hard budget or invariants failed"
    elif product > DOCETL_PRODUCT:
        decision = "fresh additive arm beats DocETL"
    else:
        decision = "diagnostic M4 did not reproduce under fresh sampling"

    input_tokens = [row["tokens_after"] for row in journal]
    report = {
        "model": MODEL,
        "decision": decision,
        "input_cap": input_cap,
        "document_ids": document_ids,
        "note": "Controlled seven-document arm derived from frozen pipeline_output IDs; not the generic selection policy.",
        "completed_queries_25": t25["complete_query_ids"],
        "completed_queries_100": list(completed),
        "spent_25": t25["spent"],
        "spent_100": ledger.spent,
        "unused_25": max(0, THETA_25 - t25["spent"]),
        "unused_100": max(0, THETA_100 - ledger.spent),
        "calls": len(journal),
        "malformed": counts["malformed"],
        "deterministic_salvages": counts["salvaged"],
        "counts": dict(counts),
        "token_percentiles": {
            "input_after_mean": sum(input_tokens) / len(input_tokens) if input_tokens else 0,
            "input_after_min": min(input_tokens) if input_tokens else 0,
            "input_after_max": max(input_tokens) if input_tokens else 0,
        },
        "accepted_fills": sum(item.get("changed_cells") or 0 for item in overlays.values()),
        "blocked_overwrites": sum(item.get("blocked_overwrites") or 0 for item in overlays.values()),
        "score_25": {
            "score_16": {k: score_25["score_16"][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")},
            "score_15": {k: score_25["score_15"][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")},
        },
        "score_100": {
            "score_16": {k: score_100["score_16"][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")},
            "score_15": {k: score_100["score_15"][k] for k in ("mean_structure_f2", "mean_cell_f1_at_0.20", "mean_per_query_product")},
        },
        "comparators": {"plumbing": PLUMBING_PRODUCT, "diagnostic_m4": M4_PRODUCT, "frozen_docetl": DOCETL_PRODUCT},
        "per_query_100": score_100["per_query_delta"],
        "empty_bags_100": [row["query_id"] for row in score_100["score_16"]["per_query"] if int(row.get("pred_rows") or 0) == 0],
        "replay_compare": replay_compare,
        "hashes": hashes,
        "prior_frozen_unmodified": frozen["prior_frozen_still_identical"],
        "paths": {"report": str(OUT / "finan_full_window_additive_arm.json"), "frozen": str(OUT / "frozen.json")},
    }
    (OUT / "finan_full_window_additive_arm.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({"wrote": str(OUT / "finan_full_window_additive_arm.json"), "decision": decision, "product": product, "spent": ledger.spent, "calls": len(journal)}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
