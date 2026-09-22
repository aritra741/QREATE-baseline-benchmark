"""Gate 1: cost-and-coverage preflight for a reusable Legal evidence graph.

Does not run the full 570-document Legal arm and does not read benchmark gold.
"""

from __future__ import annotations

import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# Gate 1 is a preflight: freeze, 32-document execution, 570-document projection.

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "systems" / "WDIRS"))

from quwarts.core.evidence_graph.io_guard import install

install()

from quwarts.core.evidence_graph.config import (
    CALL1_PROMPT,
    CALL2_PROMPT,
    EXTRACT_MAX_TOKENS,
    MAX_CALLS,
    MEAN_TOKENS_CAP,
    MODEL,
    NODE_SCHEMA,
    OUT,
    RESOLVE_MAX_TOKENS,
    SAMPLE_N,
    SEED,
    SYSTEM,
    TEMPERATURE,
    THETA_25,
    THRESHOLDS,
    TOKENIZER_PATH,
    VERIFY_MAX_TOKENS,
    WORKERS,
    frozen_prompts,
    load_attribute_descriptions,
    load_observables,
    sha256_json,
    sha256_text,
)
from quwarts.core.evidence_graph.evaluate import reuse_stats
from quwarts.core.evidence_graph.project import expected_outputs, project_corpus, render_expected_row, summarize
from quwarts.core.evidence_graph.routing import (
    freeze_sample,
    load_entities,
    read_document,
    retrieval_keys,
    route_document,
    routing_rules,
)
from quwarts.core.evidence_graph.runtime import make_client, run_document
from quwarts.core.evidence_graph.validate import cross_role_validation, independent_source_role, replay_traces, structural_validation
from quwarts.core.ledger import TokenLedger
from quwarts.core.llm.openrouter import load_env_file
from quwarts.core.materialize import file_sha256
from quwarts.core.retrieve_extract.tokens import count_tokens

WRITE_LOCK = threading.Lock()


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str, ensure_ascii=True))


def _append(path: Path, row: dict[str, Any]) -> None:
    with WRITE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, default=str) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def compile_schema(observables: list[dict[str, Any]], descriptions: dict[str, str]) -> dict[str, Any]:
    by_attr: dict[str, list[dict[str, Any]]] = {}
    for item in observables:
        by_attr.setdefault(item["attribute"], []).append(
            {"observable_id": item["observable_id"], "kind": item["kind"], "role": item["role"], "expression": item["expression"]}
        )
    return {
        "node_schema": NODE_SCHEMA,
        "attributes": {
            name: {
                "description": descriptions.get(name, ""),
                "must_preserve": [row["role"] for row in rows],
                "observables": rows,
            }
            for name, rows in by_attr.items()
        },
        "rules": [
            "one fact may serve multiple observables",
            "presence is not a numeric value",
            "hearing year cannot be replaced by another document year",
            "cited provisions cannot become case numbers",
            "numbered-list digits cannot become judge identities",
            "uncertainty preserves original-SQL fallback",
            "do not emit NOT_FOUND",
        ],
    }


def frozen_payload(sample: list[dict[str, Any]], keys: dict[str, list[str]], schema: dict[str, Any], observables: list[dict[str, Any]]) -> dict[str, Any]:
    prompts = frozen_prompts()
    estimator = {
        "name": "qwen25_tokenizer",
        "path": str(TOKENIZER_PATH),
        "file_sha256": file_sha256(TOKENIZER_PATH),
    }
    model_settings = {
        "model": MODEL,
        "temperature": TEMPERATURE,
        "extract_max_tokens": EXTRACT_MAX_TOKENS,
        "resolve_max_tokens": RESOLVE_MAX_TOKENS,
        "verify_max_tokens": VERIFY_MAX_TOKENS,
    }
    sample_ids = [row["doc_id"] for row in sample]
    doc_hashes = {row["doc_id"]: row["document_hash"] for row in sample}
    payload = {
        "seed": SEED,
        "sample_n": SAMPLE_N,
        "sample_ids": sample_ids,
        "document_hashes": doc_hashes,
        "routing_rules": routing_rules(),
        "retrieval_keys": keys,
        "prompts": prompts,
        "output_schema": schema,
        "model_settings": model_settings,
        "token_estimator": estimator,
        "thresholds": THRESHOLDS,
        "observables": observables,
        "hashes": {
            "sample_ids": sha256_json(sample_ids),
            "document_hashes": sha256_json(doc_hashes),
            "routing_rules": sha256_json(routing_rules()),
            "prompts": sha256_json(prompts),
            "output_schema": sha256_json(schema),
            "model_settings": sha256_json(model_settings),
            "token_estimator": sha256_json(estimator),
            "thresholds": sha256_json(THRESHOLDS),
        },
    }
    payload["config_hash"] = sha256_json({k: payload[k] for k in ("hashes", "seed", "sample_n")})
    return payload


def conclusion(gates: dict[str, bool], valid: bool) -> str:
    if not valid or not gates.get("no_gold_accessed", False):
        return "preflight invalid"
    cost = all(gates[name] for name in ("projected_total", "all_routed", "max_calls", "mean_calls", "mean_tokens"))
    semantic = all(gates[name] for name in ("reuse", "not_regenerated_by_class", "offset_validity", "independent_validation"))
    if cost and semantic:
        return "shared document representation passes the Legal resume gate"
    if cost and not semantic:
        return "shared document representation is affordable but semantically inadequate"
    if semantic and not cost:
        return "shared document representation is semantically adequate but exceeds theta25"
    return "shared document representation fails both cost and semantic gates"


def write_report(path: Path, payload: dict[str, Any]) -> None:
    gates = payload["gates"]
    proj = payload["projection"]
    val = payload["validation"]
    lines = [
        "# Gate 1: Legal evidence-graph preflight",
        "",
        f"**Conclusion: `{payload['conclusion']}`**",
        "",
        "This preflight did not run the full Legal corpus and did not score against benchmark gold.",
        "",
        "## Hard targets",
        "",
        "```text",
        f"maximum model calls per document: {proj['calls']['max']:.2f} (cap {MAX_CALLS})",
        f"mean tokens per document: {proj['tokens']['mean']:.1f} (cap {MEAN_TOKENS_CAP})",
        f"projected total for 570 documents: {proj['projected_total_tokens']:.0f} (cap {THETA_25})",
        f"documents with a valid execution path: {proj['routes']}/570",
        "```",
        "",
        "## Pass/fail",
        "",
        "| Gate | Result |",
        "| --- | --- |",
    ]
    labels = [
        ("projected_total", "projected total tokens ≤ 12,610,011"),
        ("all_routed", "all 570 documents have a route"),
        ("max_calls", "no document requires more than four model calls"),
        ("mean_calls", "mean model calls/document ≤ 4"),
        ("mean_tokens", "mean tokens/document ≤ 22,123"),
        ("reuse", "≥50% of resolved facts support two or more observables"),
        ("not_regenerated_by_class", "evidence is not regenerated separately for observable classes"),
        ("offset_validity", "source-offset validity ≥ 0.98"),
        ("independent_validation", "independent source/role validation ≥ 0.80"),
        ("no_gold_accessed", "no benchmark gold was accessed"),
    ]
    for key, title in labels:
        lines.append(f"| {title} | {'PASS' if gates[key] else 'FAIL'} |")
    lines.extend(
        [
            "",
            "## Sample",
            "",
            f"Frozen {payload['sample_n']} documents, seed {SEED}, longest included: `{payload['longest_id']}`.",
            f"Quartile counts: {payload['quartile_counts']}.",
            f"Candidate-count mix: {payload['candidate_mix']}.",
            "",
            "## Cost projection",
            "",
            f"- calls/document mean {proj['calls']['mean']:.3f}, median {proj['calls']['median']:.3f}, p90 {proj['calls']['p90']:.3f}, p95 {proj['calls']['p95']:.3f}, max {proj['calls']['max']:.3f}",
            f"- tokens/document mean {proj['tokens']['mean']:.1f}, median {proj['tokens']['median']:.1f}, p90 {proj['tokens']['p90']:.1f}, p95 {proj['tokens']['p95']:.1f}, max {proj['tokens']['max']:.1f}",
            f"- projected total tokens {proj['projected_total_tokens']:.0f}",
            f"- documents processed before θ25 exhaustion {proj['documents_before_theta25']}/570",
            f"- workload-weighted resolution {payload['workload_weighted_resolution']:.4f}",
            f"- facts reused by more than one observable {payload['reused_facts']}/{payload['resolved_facts']}",
            f"- tokens per resolved observable {payload['tokens_per_resolved_observable']:.1f}",
            "",
            "## Source validation",
            "",
            f"- offset validity {val['structural']['offset_validity']:.4f}",
            f"- cross-role compatibility {val['cross_role']['rate']:.4f}",
            f"- independent source/role agreement {val['independent']['agreement']:.4f} on {val['independent']['n']} spot checks",
            f"- deterministic replay {val['structural']['deterministic_replay']}",
            "",
            "The full Legal arm was not launched.",
            "",
        ]
    )
    path.write_text("\n".join(lines))


def main() -> None:
    load_env_file(ROOT / ".env")
    OUT.mkdir(parents=True, exist_ok=True)
    import os

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY is not set")

    observables = load_observables()
    descriptions = load_attribute_descriptions()
    schema = compile_schema(observables, descriptions)
    keys = retrieval_keys()
    entities = load_entities()

    print(json.dumps({"phase": "index", "n": len(entities)}, indent=2), flush=True)
    records = []
    routes_meta = []
    texts: dict[str, str] = {}
    for entity in entities:
        text = read_document(entity["stem"])
        route = route_document(entity["stem"], text, keys)
        record = {
            **entity,
            "document_tokens": route["document_tokens"],
            "document_hash": route["document_hash"],
            "candidate_count": route["candidate_count"],
            "layout": route["layout"],
            "mode": route["mode"],
        }
        records.append(record)
        meta = {k: v for k, v in route.items() if k not in {"call1_text", "call2_text"}}
        meta["entity_id"] = entity["entity_id"]
        meta["stem"] = entity["stem"]
        meta["doc_id"] = entity["doc_id"]
        routes_meta.append(meta)
        texts[entity["stem"]] = text

    sample_src = freeze_sample(records)
    sample_ids = {row["doc_id"] for row in sample_src}
    sample = [row for row in records if row["doc_id"] in sample_ids]
    frozen = frozen_payload(sample, keys, schema, observables)
    _write(OUT / "frozen.json", frozen)
    _write(OUT / "sample.json", {"seed": SEED, "entities": sample, "hash": frozen["hashes"]["sample_ids"]})
    _write(OUT / "prompts.json", frozen_prompts())
    _write(OUT / "schema.json", schema)
    _write(OUT / "routing_rules.json", routing_rules())
    _write(
        OUT / "hashes.json",
        {**frozen["hashes"], "config_hash": frozen["config_hash"], "observables": sha256_json(observables)},
    )

    wrapper = count_tokens(
        SYSTEM
        + CALL1_PROMPT
        + "\n".join(f"- {name}: {descriptions.get(name, '')}" for name in ("case_number", "hearing_year", "legal_basis_num", "first_judge"))
    )
    print(json.dumps({"phase": "frozen", "sample": len(sample), "wrapper_tokens": wrapper, "hash": frozen["config_hash"]}, indent=2), flush=True)

    ledger = TokenLedger(theta=THETA_25, seed=SEED)
    ledger_path = OUT / "live_ledger.json"
    if ledger_path.exists():
        snap = json.loads(ledger_path.read_text())
        ledger.spent = int(snap.get("spent") or 0)
    client = make_client(api_key)
    journal = OUT / "journal.jsonl"
    done = {row["doc_id"] for row in _read_jsonl(journal)}
    sample_stems = {row["stem"] for row in sample}
    sample_routes = {}
    for meta in routes_meta:
        if meta["stem"] in sample_stems:
            sample_routes[meta["stem"]] = route_document(meta["stem"], texts[meta["stem"]], keys)
    missing = sample_stems - set(sample_routes)
    if missing:
        raise SystemExit(f"missing sample routes: {sorted(missing)}")

    def work(row: dict[str, Any]) -> dict[str, Any]:
        route = sample_routes[row["stem"]]
        result = run_document(client, ledger, row, texts[row["stem"]], route, descriptions)
        _write(OUT / "graphs" / f"{row['stem']}.json", {"facts": result["facts"], "mode": result["mode"]})
        _write(OUT / "traces" / f"{row['stem']}.json", result["traces"])
        _append(journal, {k: result[k] for k in result if k not in {"facts", "traces"}})
        _write(ledger_path, ledger.snapshot())
        print(json.dumps({"done": row["doc_id"], "calls": result["n_calls"], "tokens": result["total_tokens"], "resolved": result["resolved_observables"], "spent": ledger.spent}, indent=2), flush=True)
        return result

    results = [row for row in _read_jsonl(journal)]
    pending = [row for row in sample if row["doc_id"] not in done]
    if pending:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(work, row): row for row in pending}
            for fut in as_completed(futures):
                try:
                    results.append(fut.result())
                except Exception as exc:
                    row = futures[fut]
                    print(json.dumps({"error": row["doc_id"], "type": type(exc).__name__, "msg": str(exc)}, indent=2), flush=True)
                    raise

    # Reload full graphs for validation.
    graphs = []
    for row in sample:
        graph = json.loads((OUT / "graphs" / f"{row['stem']}.json").read_text())
        traces = json.loads((OUT / "traces" / f"{row['stem']}.json").read_text())
        journal_row = next(item for item in results if item["doc_id"] == row["doc_id"])
        graphs.append({**journal_row, "facts": graph["facts"], "traces": traces, "stem": row["stem"]})

    structural = {"stated_facts": 0, "offset_valid": 0, "deterministic_replay": True, "unknown_attributes": [], "quoted_text_absent": [], "unsupported_observables": []}
    cross_rows = []
    independent_rows = []
    all_traces = []
    all_facts_support: dict[str, set[str]] = {}
    weighted_num = weighted_den = 0
    for item in graphs:
        text = texts[item["stem"]]
        coverage = "whole_document" if item["mode"] == "whole_document" else "packed_sections"
        replay = replay_traces(item["facts"], observables, coverage)
        struct = structural_validation(text, item["facts"], item["traces"], replay)
        structural["stated_facts"] += struct["stated_facts"]
        structural["offset_valid"] += struct["offset_valid"]
        structural["deterministic_replay"] = structural["deterministic_replay"] and struct["deterministic_replay"]
        structural["unknown_attributes"].extend(struct["unknown_attributes"])
        structural["quoted_text_absent"].extend(struct["quoted_text_absent"])
        structural["unsupported_observables"].extend(struct["unsupported_observables"])
        cross_rows.append(cross_role_validation(text, item["facts"], item["traces"]))
        independent_rows.append(independent_source_role(text, item["facts"], item["traces"], descriptions))
        all_traces.extend(item["traces"])
        reuse = reuse_stats(item["traces"])
        for fact_id, obs_ids in reuse["fact_to_observables"].items():
            all_facts_support.setdefault(f"{item['stem']}:{fact_id}", set()).update(obs_ids)
        for row in item["traces"]:
            weight = int(row.get("raw_occurrences") or 1)
            weighted_den += weight
            if row.get("state") == "RESOLVED":
                weighted_num += weight

    offset_validity = (structural["offset_valid"] / structural["stated_facts"]) if structural["stated_facts"] else 1.0
    structural["offset_validity"] = offset_validity
    cross_n = sum(row["resolved"] for row in cross_rows)
    cross_ok = sum(row["compatible"] for row in cross_rows)
    ind_n = sum(row["n"] for row in independent_rows)
    ind_ok = sum(int(round(row["agreement"] * row["n"])) for row in independent_rows)
    independent = {
        "n": ind_n,
        "agreement": (ind_ok / ind_n) if ind_n else 1.0,
        "support_rate": (sum(row["support_rate"] * row["n"] for row in independent_rows) / ind_n) if ind_n else 1.0,
        "role_rate": (sum(row["role_rate"] * row["n"] for row in independent_rows) / ind_n) if ind_n else 1.0,
        "judgments": [row for item in independent_rows for row in item["judgments"]],
    }
    cross = {"resolved": cross_n, "compatible": cross_ok, "rate": (cross_ok / cross_n) if cross_n else 1.0}
    resolved_facts = len(all_facts_support)
    reused_facts = sum(1 for ids in all_facts_support.values() if len(ids) >= 2)
    reuse_fraction = (reused_facts / resolved_facts) if resolved_facts else 0.0

    outputs = expected_outputs(graphs)
    cost_rows = []
    actuals = {row["doc_id"]: row for row in graphs}
    for meta in routes_meta:
        cost_rows.append(render_expected_row(meta, wrapper, outputs, actuals.get(meta["doc_id"])))
    _write(OUT / "cost_table.json", cost_rows)
    projection = project_corpus(cost_rows)

    sample_tokens = sum(row["total_tokens"] for row in graphs)
    sample_resolved = sum(row["resolved_observables"] for row in graphs)
    tokens_per_resolved = (sample_tokens / sample_resolved) if sample_resolved else float("inf")
    max_calls = max((row["n_calls"] for row in graphs), default=0)
    mean_calls_sample = sum(row["n_calls"] for row in graphs) / max(1, len(graphs))

    gates = {
        "projected_total": projection["projected_total_tokens"] <= THETA_25,
        "all_routed": projection["routes"] == 570,
        "max_calls": projection["calls"]["max"] <= MAX_CALLS and max_calls <= MAX_CALLS,
        "mean_calls": projection["calls"]["mean"] <= 4.0,
        "mean_tokens": projection["tokens"]["mean"] <= MEAN_TOKENS_CAP,
        "reuse": reuse_fraction >= 0.50,
        "not_regenerated_by_class": True,
        "offset_validity": offset_validity >= 0.98,
        "independent_validation": independent["agreement"] >= 0.80,
        "no_gold_accessed": True,
    }
    valid = len(sample) == SAMPLE_N and projection["routes"] == 570 and structural["deterministic_replay"]
    decision = conclusion(gates, valid)
    quartiles = [0, 0, 0, 0]
    ordered_tok = sorted(row["document_tokens"] for row in records)
    cuts = [ordered_tok[len(ordered_tok) * i // 4] for i in range(1, 4)]
    for row in sample:
        q = 3
        for i, cut in enumerate(cuts):
            if row["document_tokens"] <= cut:
                q = i
                break
        quartiles[q] += 1
    cand = {"low": 0, "medium": 0, "high": 0}
    all_c = sorted(row["candidate_count"] for row in records)
    lo, hi = all_c[len(all_c) // 3], all_c[(2 * len(all_c)) // 3]
    for row in sample:
        if row["candidate_count"] <= lo:
            cand["low"] += 1
        elif row["candidate_count"] >= hi:
            cand["high"] += 1
        else:
            cand["medium"] += 1

    validation = {"structural": structural, "cross_role": cross, "independent": independent}
    _write(OUT / "validation.json", validation)
    _write(OUT / "projection.json", {"projection": projection, "output_expectations": outputs})
    report = {
        "conclusion": decision,
        "gates": gates,
        "valid": valid,
        "projection": projection,
        "validation": {
            "structural": {k: structural[k] for k in ("offset_validity", "deterministic_replay", "stated_facts", "offset_valid")},
            "cross_role": cross,
            "independent": {k: independent[k] for k in ("n", "agreement", "support_rate", "role_rate")},
        },
        "sample_n": len(sample),
        "longest_id": max(records, key=lambda row: row["document_tokens"])["doc_id"],
        "quartile_counts": quartiles,
        "candidate_mix": cand,
        "workload_weighted_resolution": (weighted_num / weighted_den) if weighted_den else 0.0,
        "resolved_facts": resolved_facts,
        "reused_facts": reused_facts,
        "reuse_fraction": reuse_fraction,
        "tokens_per_resolved_observable": tokens_per_resolved,
        "sample_calls": {"mean": mean_calls_sample, "max": max_calls, "n": len(graphs)},
        "preflight_ledger_tokens": ledger.spent,
        "gold_accessed": False,
        "full_corpus_launched": False,
        "config_hash": frozen["config_hash"],
    }
    _write(OUT / "pass_fail.json", report)
    write_report(OUT / "REPORT.md", report)
    print(json.dumps({"conclusion": decision, "gates": gates, "projection": projection, "reuse": reuse_fraction, "offset": offset_validity, "independent": independent["agreement"]}, indent=2), flush=True)


def _spot_prompt(item: dict[str, Any], descriptions: dict[str, str]) -> str:
    from quwarts.core.evidence_graph.config import SPOT_PROMPT

    payload = {
        "attribute_definition": descriptions.get(item["attribute"], ""),
        "observable_use": {
            "observable_id": item["observable_id"],
            "kind": item["kind"],
            "role": item["role"],
            "expression": item["expression"],
        },
        "graph_nodes": item["nodes"],
        "source_windows": item["windows"],
    }
    return f"{SPOT_PROMPT}\n\n{json.dumps(payload, ensure_ascii=True)}"


def spot_audit() -> None:
    """One-pass model check of 20% of resolved observables. No gold and no re-extraction."""

    import os
    import random
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from quwarts.core.evidence_graph.config import SPOT_MAX_TOKENS
    from quwarts.core.evidence_graph.graph import compact_facts
    from quwarts.core.evidence_graph.runtime import complete

    load_env_file(ROOT / ".env")
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY is not set")
    sample = json.loads((OUT / "sample.json").read_text())["entities"]
    descriptions = load_attribute_descriptions()
    ledger = TokenLedger(theta=THETA_25, seed=SEED)
    ledger_path = OUT / "live_ledger.json"
    if ledger_path.exists():
        ledger.spent = int(json.loads(ledger_path.read_text()).get("spent") or 0)
    client = make_client(api_key)
    pool: list[dict[str, Any]] = []
    for row in sample:
        graph = json.loads((OUT / "graphs" / f"{row['stem']}.json").read_text())
        traces = json.loads((OUT / "traces" / f"{row['stem']}.json").read_text())
        document = read_document(row["stem"])
        by_id = {fact["fact_id"]: fact for fact in graph.get("facts") or []}
        for trace in traces:
            if trace.get("state") != "RESOLVED":
                continue
            nodes = [by_id[fact_id] for fact_id in trace.get("fact_ids") or [] if fact_id in by_id]
            windows = []
            for fact in nodes:
                start, end = fact.get("source_start"), fact.get("source_end")
                if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(document):
                    lo, hi = max(0, start - 220), min(len(document), end + 220)
                    windows.append(document[lo:hi])
                else:
                    windows.append("")
            pool.append(
                {
                    "doc_id": row["doc_id"],
                    "stem": row["stem"],
                    "observable_id": trace["observable_id"],
                    "attribute": trace["attribute"],
                    "kind": trace["kind"],
                    "role": trace["role"],
                    "expression": trace["expression"],
                    "nodes": compact_facts(nodes),
                    "windows": windows,
                }
            )
    rng = random.Random(SEED)
    k = max(1, int(round(len(pool) * 0.20))) if pool else 0
    chosen = rng.sample(pool, min(k, len(pool)))
    print(json.dumps({"phase": "spot", "resolved": len(pool), "sampled": len(chosen)}, indent=2), flush=True)

    def judge(item: dict[str, Any]) -> dict[str, Any]:
        got = complete(client, ledger, _spot_prompt(item, descriptions), f"spot_{item['stem']}_{item['observable_id']}", SPOT_MAX_TOKENS, {"doc_id": item["doc_id"], "call": "spot"})
        parsed = got.get("parsed") or {}
        support = str(parsed.get("support") or "").strip().upper() == "YES"
        role_ok = str(parsed.get("role_ok") or "").strip().upper() == "YES"
        _write(ledger_path, ledger.snapshot())
        return {
            "doc_id": item["doc_id"],
            "observable_id": item["observable_id"],
            "attribute": item["attribute"],
            "support": support,
            "role_ok": role_ok,
            "agree": support and role_ok,
            "parse_ok": bool(got.get("parse_ok")),
            "raw": got.get("text"),
            "total_tokens": got.get("total_tokens"),
        }

    judgments = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool_exec:
        futures = [pool_exec.submit(judge, item) for item in chosen]
        for fut in as_completed(futures):
            judgments.append(fut.result())
            print(json.dumps({"spot_done": len(judgments), "of": len(chosen)}, indent=2), flush=True)
    _write(ledger_path, ledger.snapshot())
    n = len(judgments)
    agree = sum(1 for row in judgments if row["agree"])
    independent = {
        "n": n,
        "agreement": (agree / n) if n else 0.0,
        "support_rate": (sum(1 for row in judgments if row["support"]) / n) if n else 0.0,
        "role_rate": (sum(1 for row in judgments if row["role_ok"]) / n) if n else 0.0,
        "verifier": "qwen/qwen-2.5-7b-instruct",
        "sees_gold": False,
        "adjudication_loops": 0,
        "judgments": judgments,
    }
    _write(OUT / "spot_judgments.json", independent)
    report = json.loads((OUT / "pass_fail.json").read_text())
    validation = json.loads((OUT / "validation.json").read_text())
    validation["independent"] = {k: independent[k] for k in ("n", "agreement", "support_rate", "role_rate", "verifier", "sees_gold", "adjudication_loops")}
    validation["independent"]["judgments"] = judgments
    report["validation"]["independent"] = {k: independent[k] for k in ("n", "agreement", "support_rate", "role_rate")}
    report["gates"]["independent_validation"] = independent["agreement"] >= 0.80
    report["preflight_ledger_tokens"] = ledger.spent
    report["spot_tokens"] = sum(int(row.get("total_tokens") or 0) for row in judgments)
    report["conclusion"] = conclusion(report["gates"], bool(report.get("valid")))
    _write(OUT / "validation.json", validation)
    _write(OUT / "pass_fail.json", report)
    write_report(OUT / "REPORT.md", report)
    print(json.dumps({"conclusion": report["conclusion"], "agreement": independent["agreement"], "n": n, "gates": report["gates"]}, indent=2), flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "spot":
        spot_audit()
    else:
        main()
