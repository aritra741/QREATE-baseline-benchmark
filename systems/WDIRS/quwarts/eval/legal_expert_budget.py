"""Legal query-expert budget scaling.

Stage A freezes a gold-free expert order, then replays stored DocETL map rows.
Stage B is not started unless the conservative diagnostic beats DocETL at θ50 or θ75.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import shutil
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path("/Users/aritramazumder/Documents/UDA-Bench-main")
sys.path[:0] = [str(ROOT / "systems" / "WDIRS"), str(ROOT / "systems" / "docetl-main"), str(ROOT)]

_OPEN = builtins.open
_BLOCK = (
    "ground_truth",
    "/gold/",
    "gold.json",
    "official_bags",
    "query_tables",
    "pipeline_output.json",
    "extract_fields.json",
    "evaluation.json",
    "query_results.json",
    "shared_reachability",
    "cost_aware_reachability",
    "evidence_card_aggregation_audit",
)
_ALLOW = ("query_manifest.json", "legal_attributes.json", "observables.json")


def _blocked(path: object) -> bool:
    text = str(path).replace("\\", "/").lower()
    if any(text.endswith(suffix) for suffix in _ALLOW):
        return False
    return any(fragment in text for fragment in _BLOCK)


def _guard(path, *args, **kwargs):
    if _blocked(path):
        raise PermissionError(f"gold_or_answer_blocked:{path}")
    return _OPEN(path, *args, **kwargs)


builtins.open = _guard

from quwarts.core.observable_sidecar import (  # noqa: E402
    TABLE,
    bag_hash,
    compile_observables,
    execute_bags,
    write_specs,
)
from quwarts.core.pipeline import official_sql  # noqa: E402
from quwarts.core.signature import audit_workload, enumerate_predicates  # noqa: E402
from quwarts.core.signature_realize import live_predicates  # noqa: E402

GATE = ROOT / "results" / "quwarts_legal_expert_set_cover"
MANIFEST = ROOT / "results" / "docetl_legal_case80" / "query_manifest.json"
PLUMBING = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
EXTRACT_ROOT = ROOT / "results" / "docetl_legal_case80" / "docetl_pipelines"
OUT = ROOT / "results" / "quwarts_legal_expert_budget"
DOCETL_PRODUCT = 0.12350932750098194
BUDGETS = {
    "theta25": 12_610_011,
    "theta50": 25_220_022,
    "theta75": 37_830_032,
}
THETA100 = 50_440_043


def sha(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with _OPEN(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def marginal_score(
    expert: str,
    selected: list[str],
    compatible: dict[str, list[dict[str, Any]]],
    covered: dict[str, int],
    served: set[str],
    tokens: dict[str, int],
) -> dict[str, float]:
    weights: dict[str, float] = {}
    queries_hit = {expert}
    reuse = 0.0
    workload = 0.0
    for cell in compatible[expert]:
        oid = cell["observable_id"]
        seen = covered.get(oid, 0)
        weight = 1.0 if seen == 0 else 1.0 / (1.0 + seen)
        weights[oid] = weight
        others = [qid for qid in cell["query_ids"] if qid != expert]
        reuse += weight * len(others)
        workload += weight * int(cell["raw_occurrences"])
        if weight > 0:
            queries_hit.update(cell["query_ids"])
    marginal_obs = sum(weights.values())
    marginal_query = float(len(queries_hit - served))
    cost = tokens[expert]
    numerator = marginal_query * marginal_obs * reuse * workload
    score = (numerator / cost) if cost else 0.0
    return {
        "score": score,
        "marginal_query_coverage": marginal_query,
        "marginal_observable_coverage": marginal_obs,
        "cross_query_field_reuse": reuse,
        "workload_occurrence_count": workload,
        "token_cost": cost,
    }


def freeze_schedule() -> dict[str, Any]:
    experts = json.loads((GATE / "experts.json").read_text())
    compatibility = json.loads((GATE / "compatibility.json").read_text())
    projection = json.loads((GATE / "projection.json").read_text())
    queries = json.loads(MANIFEST.read_text())
    inventory = compile_observables(queries)
    by_id = {item.observable_id: item for item in inventory.observables}
    compatible: dict[str, list[dict[str, Any]]] = {}
    for row in compatibility["matrix"]:
        cells = []
        for cell in row["cells"]:
            if not cell["compatible"]:
                continue
            obs = by_id[cell["observable_id"]]
            cells.append(
                {
                    "observable_id": obs.observable_id,
                    "kind": obs.kind,
                    "role": obs.role,
                    "attribute": obs.attribute,
                    "query_ids": list(obs.query_ids),
                    "raw_occurrences": obs.raw_occurrences,
                    "expression": obs.expression,
                }
            )
        compatible[row["query_id"]] = cells
    tokens = {row["query_id"]: int(row["total_tokens"]) for row in projection["per_expert"]}
    if set(tokens) != {expert["query_id"] for expert in experts}:
        raise SystemExit("expert token table does not match the reconstructed experts")
    render_rows = [
        {
            "query_id": row["query_id"],
            "doc_id": row["doc_id"],
            "prompt_tokens": row["prompt_tokens"],
            "completion_reservation": row["completion_reservation"],
            "total_tokens": row["total_tokens"],
            "truncated": row["truncated"],
            "fields": row["fields"],
        }
        for row in projection["per_document"]
    ]
    if len(render_rows) != 16 * 570:
        raise SystemExit(f"expected 9120 rendered requests, found {len(render_rows)}")

    remaining = [expert["query_id"] for expert in experts]
    order: list[str] = []
    trace: list[dict[str, Any]] = []
    covered: dict[str, int] = defaultdict(int)
    served: set[str] = set()
    while remaining:
        scored = {
            expert: marginal_score(expert, order, compatible, covered, served, tokens)
            for expert in remaining
        }
        pick = min(remaining, key=lambda expert: (-scored[expert]["score"], expert))
        detail = scored[pick]
        order.append(pick)
        remaining.remove(pick)
        served.add(pick)
        for cell in compatible[pick]:
            covered[cell["observable_id"]] += 1
            served.update(cell["query_ids"])
        trace.append({"query_id": pick, **detail, "rank": len(order)})

    cumulative = 0
    prefixes: dict[str, dict[str, Any]] = {}
    running: list[str] = []
    named = [("theta25", BUDGETS["theta25"]), ("theta50", BUDGETS["theta50"]), ("theta75", BUDGETS["theta75"])]
    cuts = {name: budget for name, budget in named}
    assigned = {name: False for name, _ in named}
    for expert in order:
        cumulative += tokens[expert]
        running.append(expert)
        for name, budget in named:
            if not assigned[name] and cumulative > budget:
                chosen = running[:-1]
                spent = sum(tokens[item] for item in chosen)
                assigned[name] = True
                prefixes[name] = _prefix_record(name, budget, chosen, tokens, compatible, queries)
        if all(assigned.values()):
            break
    for name, budget in named:
        if name not in prefixes:
            prefixes[name] = _prefix_record(name, budget, list(order), tokens, compatible, queries)
    if prefixes["theta25"]["experts"] != prefixes["theta50"]["experts"][: len(prefixes["theta25"]["experts"])]:
        raise SystemExit("theta25 is not a prefix of theta50")
    if prefixes["theta50"]["experts"] != prefixes["theta75"]["experts"][: len(prefixes["theta50"]["experts"])]:
        raise SystemExit("theta50 is not a prefix of theta75")

    conservative = {}
    optimistic = {}
    specs = {expert["query_id"]: expert for expert in experts}
    for expert in experts:
        qid = expert["query_id"]
        conservative[qid] = {
            "own_query": qid,
            "compatible_observables": compatible[qid],
            "rule": "own query fully; other observables only when Gate 2A marked the field and role compatible",
        }
        optimistic[qid] = {
            "own_query": qid,
            "shared_attributes": [
                {"attribute": name, "type": kind}
                for name, kind in expert["output_schema"].items()
            ],
            "rule": "optimistic diagnostic: same base attribute and output type may serve another query even when role compatibility is uncertain",
            "label": "optimistic",
        }
    schedule = {
        "stage": "A",
        "model_calls": 0,
        "theta100_not_run": THETA100,
        "budgets": BUDGETS,
        "order": order,
        "score_trace": trace,
        "prefixes": prefixes,
        "ranking": {
            "formula": "marginal query coverage × marginal AST-observable coverage × cross-query field reuse × workload occurrence count ÷ exact rendered token cost",
            "duplicate_credit": "1/(1+experts_already_covering)",
            "incompatible_column_share": 0,
            "tie_break": "query_id ascending",
            "partial_experts": "forbidden",
        },
        "routing": {"conservative": conservative, "optimistic": optimistic},
        "expert_hashes": {expert["query_id"]: expert["expert_hash"] for expert in experts},
        "expert_spec_sha256": file_sha(GATE / "experts.json"),
        "compatibility_sha256": file_sha(GATE / "compatibility.json"),
        "rendered_request_sha256": sha(render_rows),
        "rendered_request_count": len(render_rows),
        "estimated_cost_by_expert": tokens,
        "gold_loaded": False,
        "docetl_outputs_loaded": False,
    }
    schedule["schedule_sha256"] = sha({key: value for key, value in schedule.items() if key != "schedule_sha256"})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "schedule_frozen.json").write_text(json.dumps(schedule, indent=2))
    (OUT / "schedule_frozen.sha256").write_text(schedule["schedule_sha256"] + "\n")
    return schedule


def _prefix_record(name, budget, chosen, tokens, compatible, queries) -> dict[str, Any]:
    spent = sum(tokens[item] for item in chosen)
    served_obs = {}
    for expert in chosen:
        for cell in compatible[expert]:
            served_obs.setdefault(cell["observable_id"], expert)
    all_obs = {cell["observable_id"] for cells in compatible.values() for cell in cells}
    # Observables with no compatible expert stay uncovered even if every expert runs.
    inventory_ids = set()
    for cells in compatible.values():
        inventory_ids.update(cell["observable_id"] for cell in cells)
    query_ids = [row["query_id"] for row in queries]
    return {
        "checkpoint": name,
        "budget": budget,
        "experts": list(chosen),
        "queries_directly_served": list(chosen),
        "observables_served": sorted(served_obs),
        "observable_primary": served_obs,
        "projected_tokens": spent,
        "unused_budget": budget - spent,
        "uncovered_queries": [qid for qid in query_ids if qid not in chosen],
        "calls_per_document": len(chosen),
        "complete_experts_only": True,
    }


def _lift_guard() -> None:
    builtins.open = _OPEN


def _load_extracts(order: list[str]) -> dict[str, dict[str, dict[str, Any]]]:
    """Per expert, last row per doc stem. Document text is discarded."""
    loaded: dict[str, dict[str, dict[str, Any]]] = {}
    for qid in order:
        path = EXTRACT_ROOT / qid / "table_legal" / "docetl_intermediate" / "extract_step" / "extract_fields.json"
        rows = json.loads(path.read_text())
        by_doc: dict[str, dict[str, Any]] = {}
        duplicates = 0
        for row in rows:
            stem = str(row.get("doc_id"))
            if stem in by_doc:
                duplicates += 1
            kept = {key: value for key, value in row.items() if key != "text"}
            by_doc[stem] = kept
        loaded[qid] = {"rows": by_doc, "n_rows": len(rows), "n_docs": len(by_doc), "duplicate_rows": duplicates}
    return loaded


def _entities(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    return list(conn.execute('SELECT doc_id, "__entity_id" FROM legal').fetchall())


def _overlay(conn: sqlite3.Connection, fields: list[str], rows: dict[str, dict[str, Any]], numeric: set[str]) -> int:
    written = 0
    for stem, row in rows.items():
        doc_id = stem if stem.endswith(".txt") else f"{stem}.txt"
        assignments = []
        values: list[Any] = []
        for field in fields:
            if field not in row:
                continue
            value = _coerce(row[field], field in numeric)
            if value is None:
                continue
            assignments.append(f'"{field}" = ?')
            values.append(value)
        if not assignments:
            continue
        values.append(doc_id)
        cur = conn.execute(f'UPDATE legal SET {", ".join(assignments)} WHERE doc_id = ?', values)
        written += cur.rowcount
    return written


def _coerce(value: Any, numeric: bool) -> Any:
    if value is None:
        return None
    if numeric:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return value
        text = str(value).replace(",", "").replace(" ", "")
        if text == "":
            return None
        try:
            return float(text) if "." in text else int(float(text)) if text.replace(".", "", 1).lstrip("-").isdigit() else float(text)
        except ValueError:
            return None
    return str(value)


def _truth(expression: str, attribute: str, value: Any) -> str | None:
    conn = sqlite3.connect(":memory:")
    conn.execute(f'CREATE TABLE t ("{attribute}")')
    conn.execute("INSERT INTO t VALUES (?)", (value,))
    try:
        row = conn.execute(f"SELECT ({expression}) FROM t").fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if row is None or row[0] is None:
        return None
    return "TRUE" if int(row[0]) != 0 else "FALSE"


def _copy(dest: Path) -> sqlite3.Connection:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.copy(PLUMBING, dest)
    return sqlite3.connect(dest)


def _statements_and_predicates():
    queries = json.loads(MANIFEST.read_text())
    statements = {row["query_id"]: row["sql"] for row in queries}
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    inventory = compile_observables(queries)
    return statements, predicates, inventory


def _run_bags(paths: dict[str, Path], statements, predicates) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, str]]]:
    bags: dict[str, list[dict[str, Any]]] = {}
    failures = []
    for qid, sql in statements.items():
        path = paths[qid]
        rewritten = official_sql(sql, path, predicates, query_id=qid)
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            cur = conn.execute(rewritten)
            cols = [item[0] for item in cur.description] if cur.description else []
            bags[qid] = [dict(zip(cols, rec)) for rec in cur.fetchall()]
        except sqlite3.Error as exc:
            failures.append({"query_id": qid, "error": str(exc)})
            bags[qid] = []
        finally:
            conn.close()
    return bags, failures


def replay(schedule: dict[str, Any]) -> dict[str, Any]:
    frozen_hash = (OUT / "schedule_frozen.sha256").read_text().strip()
    body = {key: value for key, value in schedule.items() if key != "schedule_sha256"}
    if sha(body) != frozen_hash or schedule["schedule_sha256"] != frozen_hash:
        raise SystemExit("schedule hash changed before replay")
    if schedule.get("docetl_outputs_loaded") or schedule.get("gold_loaded"):
        raise SystemExit("schedule was not frozen before outputs")
    _lift_guard()
    extracts = _load_extracts(schedule["order"])
    statements, predicates, inventory = _statements_and_predicates()
    experts = {row["query_id"]: row for row in json.loads((GATE / "experts.json").read_text())}
    obs_by_id = {item.observable_id: item for item in inventory.observables}
    plumbing_bags, plumbing_failures = _run_bags({qid: PLUMBING for qid in statements}, statements, predicates)
    if plumbing_failures:
        raise SystemExit(f"plumbing execution failed: {plumbing_failures}")

    coverage = {
        qid: {"documents": payload["n_docs"], "rows": payload["n_rows"], "duplicate_rows": payload["duplicate_rows"]}
        for qid, payload in extracts.items()
    }
    results = {"plumbing_bag_sha256": bag_hash(plumbing_bags), "extract_coverage": coverage, "checkpoints": {}}
    for name in ("theta25", "theta50", "theta75"):
        prefix = schedule["prefixes"][name]["experts"]
        results["checkpoints"][name] = {}
        for policy in ("conservative", "optimistic"):
            checkpoint_dir = OUT / "databases" / policy / name
            if checkpoint_dir.exists():
                shutil.rmtree(checkpoint_dir)
            paths, direct_writes, reuse_writes = _materialize(
                checkpoint_dir, prefix, policy, extracts, experts, inventory, obs_by_id, schedule
            )
            bags, failures = _run_bags(paths, statements, predicates)
            direct = []
            reused = []
            unchanged = []
            for qid, bag in bags.items():
                changed = bag != plumbing_bags[qid]
                if qid in prefix and changed:
                    direct.append(qid)
                elif qid not in prefix and changed:
                    reused.append(qid)
                elif qid in prefix:
                    direct.append(qid)
                else:
                    unchanged.append(qid)
            payload = {
                "policy": policy,
                "label": "optimistic" if policy == "optimistic" else "conservative",
                "experts": prefix,
                "projected_tokens": schedule["prefixes"][name]["projected_tokens"],
                "unused_budget": schedule["prefixes"][name]["unused_budget"],
                "paths": {qid: str(path) for qid, path in paths.items()},
                "db_sha256": {qid: file_sha(path) for qid, path in paths.items()},
                "bag_sha256": bag_hash(bags),
                "bags": bags,
                "failures": failures,
                "empty_bags": [qid for qid, bag in bags.items() if not bag],
                "direct_queries": direct,
                "reused_queries": reused,
                "unchanged_queries": unchanged,
                "direct_writes": direct_writes,
                "reuse_writes": reuse_writes,
                "gold_loaded": False,
            }
            (checkpoint_dir / "bags_frozen.json").write_text(json.dumps({k: v for k, v in payload.items() if k != "bags"} , indent=2))
            (checkpoint_dir / "bags.json").write_text(json.dumps(bags, default=str))
            results["checkpoints"][name][policy] = payload
            print(
                f"frozen {policy} {name} experts={len(prefix)} direct={len(direct)} reused={len(reused)} empty={len(payload['empty_bags'])} failures={len(failures)}",
                flush=True,
            )
    (OUT / "replay_frozen.json").write_text(
        json.dumps(
            {
                "schedule_sha256": frozen_hash,
                "extract_coverage": coverage,
                "plumbing_bag_sha256": results["plumbing_bag_sha256"],
                "checkpoints": {
                    name: {
                        policy: {key: value for key, value in row.items() if key != "bags"}
                        for policy, row in policies.items()
                    }
                    for name, policies in results["checkpoints"].items()
                },
                "gold_loaded": False,
            },
            indent=2,
            default=str,
        )
    )
    return results


def _materialize(checkpoint_dir, prefix, policy, extracts, experts, inventory, obs_by_id, schedule):
    shared = checkpoint_dir / "shared.db"
    conn = _copy(shared)
    entities = dict(_entities(conn))
    direct_writes = {}
    reuse_writes = 0
    if policy == "conservative":
        write_specs(conn, inventory)
        filled: set[str] = set()
        for qid in prefix:
            for cell in schedule["routing"]["conservative"][qid]["compatible_observables"]:
                oid = cell["observable_id"]
                if oid in filled:
                    continue
                obs = obs_by_id[oid]
                reuse_writes += _insert_sidecar(conn, obs, extracts[qid]["rows"], entities, qid)
                filled.add(oid)
        conn.commit()
    else:
        written_attr: set[str] = set()
        for qid in prefix:
            schema = experts[qid]["output_schema"]
            fields = [name for name in experts[qid]["fields"] if name not in written_attr]
            if not fields:
                continue
            numeric = {name for name, kind in schema.items() if kind == "number"}
            reuse_writes += _overlay(conn, fields, extracts[qid]["rows"], numeric)
            written_attr.update(fields)
        conn.commit()
    conn.close()

    paths: dict[str, Path] = {}
    statements = {row["query_id"]: row["sql"] for row in json.loads(MANIFEST.read_text())}
    for qid in statements:
        if qid in prefix:
            dest = checkpoint_dir / f"direct_{qid.replace(':', '_')}.db"
            direct = _copy(dest)
            schema = experts[qid]["output_schema"]
            numeric = {name for name, kind in schema.items() if kind == "number"}
            direct_writes[qid] = _overlay(direct, experts[qid]["fields"], extracts[qid]["rows"], numeric)
            direct.commit()
            direct.close()
            paths[qid] = dest
        else:
            paths[qid] = shared
    return paths, direct_writes, reuse_writes


def _insert_sidecar(conn, obs, rows, entities, source) -> int:
    inserted = 0
    for stem, row in rows.items():
        if obs.attribute not in row:
            continue
        doc_id = stem if stem.endswith(".txt") else f"{stem}.txt"
        entity = entities.get(doc_id)
        if entity is None:
            continue
        raw = row[obs.attribute]
        if raw is None:
            continue
        if obs.kind in {"presence", "predicate"}:
            truth = _truth(obs.expression, obs.attribute, raw)
            if truth is None:
                continue
            conn.execute(
                f"INSERT OR REPLACE INTO {TABLE} (observable_id, entity_id, resolved, sql_truth, value_text, provenance) VALUES (?, ?, 1, ?, NULL, ?)",
                [obs.observable_id, entity, truth, f"replay:{source}"],
            )
        else:
            value = _coerce(raw, obs.kind == "numeric")
            if value is None:
                continue
            conn.execute(
                f"INSERT OR REPLACE INTO {TABLE} (observable_id, entity_id, resolved, sql_truth, value_text, provenance) VALUES (?, ?, 1, NULL, ?, ?)",
                [obs.observable_id, entity, str(value), f"replay:{source}"],
            )
        inserted += 1
    return inserted


def score(results: dict[str, Any]) -> dict[str, Any]:
    freeze_path = OUT / "replay_frozen.json"
    if not freeze_path.exists():
        raise SystemExit("replay is not frozen")
    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.eval.legal_coverage_transfer import score_db
    from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
    from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites

    statements, predicates, _inventory = _statements_and_predicates()
    query_ids = list(statements)
    gold = load_ground_truth(gold_name("Legal"))
    full = {row["query_id"]: row for row in queries_for("Legal")}
    scored = {}
    for name, policies in results["checkpoints"].items():
        scored[name] = {}
        for policy, payload in policies.items():
            rewrites = {}
            for qid in query_ids:
                path = payload["paths"][qid]
                rewrites[qid] = {
                    "sql": official_sql(statements[qid], path, predicates, query_id=qid),
                    "sqlite_path": path,
                }
            rows = [
                {"query_id": qid, "sql": statements[qid], "pack": (full.get(qid) or {}).get("pack")}
                for qid in query_ids
            ]
            report = score_with_rewrites(rows, rewrites, PLUMBING, gold, "Legal")
            product = mean_per_query_product(report)
            scored[name][policy] = {
                "f2": float(report.get("mean_structure_f2") or 0.0),
                "f1": mean_cell_f1_20(report),
                "product": product,
                "per_query": [
                    {
                        "query_id": row["query_id"],
                        "structure_f2": row.get("structure_f2"),
                        "cell_f1_20": row.get("cell_f1_20"),
                        "product": float(row.get("structure_f2") or 0.0) * float(row.get("cell_f1_20") or 0.0),
                        "pred_rows": row.get("pred_rows"),
                        "direct": row["query_id"] in payload["experts"],
                    }
                    for row in report.get("per_query") or []
                ],
                "beats_docetl": product > DOCETL_PRODUCT,
                "experts": payload["experts"],
                "tokens": payload["projected_tokens"],
                "direct_queries": payload["direct_queries"],
                "reused_queries": payload["reused_queries"],
                "empty_bags": payload["empty_bags"],
                "failures": payload["failures"],
            }
            print(f"scored {policy} {name} product={product}", flush=True)
    plumbing_score = score_db(PLUMBING, statements, predicates, query_ids, gold)
    return {"checkpoints": scored, "plumbing": {
        "f2": plumbing_score["mean_structure_f2"],
        "f1": plumbing_score["mean_cell_f1_at_0.20"],
        "product": plumbing_score["mean_per_query_product"],
    }}


def decide(scored: dict[str, Any]) -> str:
    cons = [scored["checkpoints"][name]["conservative"]["beats_docetl"] for name in ("theta50", "theta75")]
    opt = [scored["checkpoints"][name]["optimistic"]["beats_docetl"] for name in ("theta50", "theta75")]
    if any(cons):
        return "conservative-gate-open"
    if any(opt):
        return "QuWARTS only beats under optimistic semantic sharing"
    return "diagnostic gate prevents live execution"


def main() -> None:
    schedule = freeze_schedule()
    print(json.dumps({
        "schedule_sha256": schedule["schedule_sha256"],
        "order": schedule["order"],
        "prefixes": {name: row["experts"] for name, row in schedule["prefixes"].items()},
        "tokens": {name: row["projected_tokens"] for name, row in schedule["prefixes"].items()},
    }, indent=2), flush=True)
    results = replay(schedule)
    scored = score(results)
    decision = decide(scored)
    (OUT / "diagnostic_scores.json").write_text(json.dumps({"decision": decision, "docetl_product": DOCETL_PRODUCT, **scored}, indent=2))
    print(json.dumps({"decision": decision, "products": {
        name: {policy: row["product"] for policy, row in policies.items()}
        for name, policies in scored["checkpoints"].items()
    }}, indent=2), flush=True)


if __name__ == "__main__":
    main()
