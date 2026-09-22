"""Zero-token Finan throughput audit of the frozen deterministic-router arm."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import statistics
import sys
import tempfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from sqlglot import exp

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.materialize import file_sha256
from quwarts.core.pipeline import official_sql
from quwarts.core.provenance import document_stem, source_document_hash
from quwarts.core.query_residual import is_count_query
from quwarts.core.query_support import query_shape
from quwarts.core.retrieve_extract.config import FROZEN
from quwarts.core.retrieve_extract.index import index_document
from quwarts.core.retrieve_extract.parse import normalize_value
from quwarts.core.retrieve_extract.priority import gated_query_counts, missing_mass, rank_attributes
from quwarts.core.retrieve_extract.retrieve import (
    Hit,
    adjacent_chunks,
    build_specs,
    pack_chunks,
    retrieve,
    section_map_from_hits,
)
from quwarts.core.retrieve_extract.route import decide_coverage_route, measure, prompt_and_schema_tokens
from quwarts.core.retrieve_extract.salvage import salvage_completion, validate_salvaged
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.retrieve_extract.typed_candidates import candidates_for_document
from quwarts.core.signature import audit_workload, enumerate_predicates
from quwarts.core.signature_realize import live_predicates
from quwarts.core.workload import analyze_workload, parse_sql
from quwarts.eval.finan_additive_arm import PLUMBING_DB, TABLE, load_catalog, load_plumbing_rows
from quwarts.eval.retrieve_extract_postmortem import role_buckets
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.synthesize_case80 import documents_for, gold_name, queries_for

ARM = ROOT / "results" / "quwarts_finan_additive"
OUT = ROOT / "results" / "quwarts_finan_throughput_audit"
FROZEN_DB = ARM / "databases" / "finan_additive.db"
THETA = 345457
CAP = int(FROZEN["retrieve_context_cap"])
MAX_BUNDLE = int(FROZEN["max_bundle_size"])


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _null(value: Any) -> bool:
    return value in (None, "")


def _fetch(conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    cur = conn.execute(sql)
    cols = [item[0] for item in cur.description] if cur.description else []
    return [dict(zip(cols, rec)) for rec in cur.fetchall()]


def _norm_bag(rows: list[dict[str, Any]]) -> tuple:
    frozen = []
    for row in rows:
        frozen.append(tuple(sorted((str(key), json.dumps(row.get(key), default=str)) for key in row)))
    return tuple(sorted(frozen))


def _match_gold(gold: Any, pred: Any, dtype: str) -> bool:
    if gold in (None, "") or pred in (None, ""):
        return False
    if dtype == "numeric":
        try:
            gnum = float(str(gold).replace(",", ""))
            pnum = float(str(pred).replace(",", ""))
            return abs(gnum - pnum) <= max(0.20 * max(abs(gnum), 1.0), 1e-6)
        except ValueError:
            pass
    gold_set = {part.strip().lower() for part in str(gold).replace("||", ";").split(";") if part.strip()}
    pred_set = {part.strip().lower() for part in str(pred).replace("||", ";").split(";") if part.strip()}
    if gold_set and pred_set and (gold_set & pred_set):
        return True
    return str(gold).strip().lower() == str(pred).strip().lower() or (
        str(pred).strip().lower() in str(gold).strip().lower()
    )


def query_attrs(sql: str) -> set[str]:
    try:
        _, work = analyze_workload({"q": sql})
    except Exception:
        return set()
    return set(work.requirements)


def query_roles(sql: str, attr: str) -> list[str]:
    try:
        _, work = analyze_workload({"q": sql})
    except Exception:
        return []
    req = work.requirements.get(attr)
    return role_buckets(req.roles) if req else []


def empty_ids(path: Path, statements: dict[str, str], predicates) -> list[str]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    empty = []
    try:
        for qid, sql in statements.items():
            try:
                rows = _fetch(conn, official_sql(sql, path, predicates))
            except sqlite3.Error:
                empty.append(qid)
                continue
            if not rows:
                empty.append(qid)
    finally:
        conn.close()
    return empty


def salvage_arm(extract_log, repair_log, docs, plumbing_rows, dtypes) -> dict[str, Any]:
    by_eid = {str(row["__entity_id"]): row for row in plumbing_rows}
    texts = {doc.doc_id: (doc.text, source_document_hash(doc.doc_id, doc.text)) for doc in docs}
    completions = []
    for row in extract_log:
        completions.append({**row, "source": "extractor"})
    for row in repair_log:
        if row.get("response"):
            completions.append(
                {
                    "doc_id": row.get("doc_id"),
                    "entity_id": row.get("entity_id") or row.get("doc_id"),
                    "attributes": row.get("attributes") or [],
                    "raw": row.get("response"),
                    "source": "repair",
                    "phase": row.get("phase"),
                    "counts": {},
                    "errors": [],
                }
            )
    class_counts = Counter()
    malformed_completions = 0
    malformed_entries = 0
    parseable = 0
    repaired = 0
    partial_entries = 0
    recovered_grounded = []
    surviving_norm = []
    sql_est = []
    records = []
    for row in completions:
        requested = list(row.get("attributes") or [])
        raw = row.get("raw") or ""
        counts = row.get("counts") or {}
        was_malformed = bool(row.get("errors")) and (
            int(counts.get("malformed") or 0) > 0
            or any("invalid_json" in str(err) for err in (row.get("errors") or []))
        )
        if was_malformed:
            malformed_completions += 1
            malformed_entries += int(counts.get("malformed") or len(requested))
        salvaged = salvage_completion(raw, requested)
        if salvaged["parseable_unmodified"]:
            parseable += 1
        if salvaged["repaired"]:
            repaired += 1
        for klass in salvaged["classes"]:
            class_counts[klass] += 1
        doc = next((item for item in docs if item.doc_id == row.get("doc_id")), None)
        text, digest = texts.get(row.get("doc_id"), ("", ""))
        plow = by_eid.get(str(row.get("entity_id") or "")) or {}
        nulls = {name: _null(plow.get(name.split(".")[-1])) for name in requested}
        validated = validate_salvaged(
            salvaged["by_name"],
            text=text,
            digest=digest,
            dtypes=dtypes,
            plumbing_null=nulls,
        )
        for item in validated:
            if salvaged["partial"] and item["attribute"] in salvaged["by_name"]:
                partial_entries += 1
            if item["status"] == "found" and item["grounded"]:
                recovered_grounded.append(item)
            if item["status"] == "found" and item["grounded"] and not item.get("norm_error"):
                surviving_norm.append(item)
            if item["sql_eligible"]:
                sql_est.append(
                    {
                        **item,
                        "entity_id": row.get("entity_id"),
                        "doc_id": row.get("doc_id"),
                        "source": row.get("source"),
                    }
                )
        records.append(
            {
                "doc_id": row.get("doc_id"),
                "entity_id": row.get("entity_id"),
                "source": row.get("source"),
                "phase": row.get("phase"),
                "requested": requested,
                "was_malformed": was_malformed,
                "classes": salvaged["classes"],
                "transformations": salvaged["transformations"],
                "parseable_unmodified": salvaged["parseable_unmodified"],
                "repaired": salvaged["repaired"],
                "partial": salvaged["partial"],
                "recovered_attributes": list(salvaged["by_name"]),
                "missing": salvaged.get("missing") or [],
                "rejected": salvaged["rejected"],
            }
        )
    unique_sql = {}
    for item in sql_est:
        key = (item.get("entity_id"), item["attribute"], str(item.get("commit")))
        unique_sql[key] = item
    return {
        "completions": len(completions),
        "malformed_completions": malformed_completions,
        "malformed_attribute_entries": malformed_entries,
        "parseable_without_modification": parseable,
        "completions_repaired": repaired,
        "valid_partial_entries_recovered": partial_entries,
        "recovered_grounded_candidates": len(recovered_grounded),
        "candidates_surviving_normalization": len(surviving_norm),
        "estimated_sql_visible_if_null_only": len(unique_sql),
        "failure_classes": dict(class_counts),
        "sql_eligible": list(unique_sql.values()),
        "records": records,
    }


def _union_tokens(index, hits: list[Hit], mode: str) -> int:
    extra = adjacent_chunks(index, hits)
    if mode == "section_map":
        packed, _, _ = section_map_from_hits(index, hits, cap=CAP)
    elif mode == "whole_document":
        return index.document_tokens
    else:
        packed, _, _ = pack_chunks(hits, cap=CAP, extra=extra)
    return count_tokens(packed) if packed else 0


def _fits(index, hits_a: list[Hit], hits_b: list[Hit], mode: str) -> bool:
    merged: list[Hit] = []
    seen: set[str] = set()
    for hit in list(hits_a) + list(hits_b):
        if hit.chunk.source_id in seen:
            continue
        seen.add(hit.chunk.source_id)
        merged.append(hit)
    return _union_tokens(index, merged, mode) <= CAP


def simulate_bundles(
    documents,
    indexes,
    specs,
    ranked,
    missing_by_entity,
    entity_by_doc,
    descriptions,
    extract_log,
    ledger_records,
) -> dict[str, Any]:
    priority = {row["attribute"]: float(row["priority"]) for row in ranked}
    attrs = [row["attribute"] for row in ranked]
    roles = {row["attribute"]: row.get("roles") or [] for row in ranked}
    hits: dict[tuple[str, str], list[Hit]] = {}
    modes: dict[tuple[str, str], str] = {}
    for doc in documents:
        index = indexes[doc.doc_id]
        eid = entity_by_doc[doc.doc_id]
        missing = missing_by_entity.get(eid, set())
        for name in attrs:
            if name not in missing:
                continue
            got = retrieve(index, specs[name])
            hits[(eid, name)] = got
            prompt = prompt_and_schema_tokens([name], descriptions)
            packed, _, _ = pack_chunks(got, extra=adjacent_chunks(index, got))
            meas = measure(index.document_tokens, prompt, count_tokens(packed) if packed else CAP)
            mode, _ = decide_coverage_route(meas, {"diffuse": False, "n_hits": len(got), "top2_share": 1.0} if got else {"diffuse": True, "n_hits": 0, "top2_share": 0.0})
            # reuse recorded concentration if we only need mode from same rule
            from quwarts.core.retrieve_extract.retrieve import concentration as _concentration

            mode, _ = decide_coverage_route(meas, _concentration(got))
            modes[(eid, name)] = mode
    unresolved = [(eid, name) for (eid, name) in hits]
    outputs = [count_tokens(row.get("raw") or "") for row in extract_log if row.get("raw")]
    out_p50 = int(statistics.median(outputs)) if outputs else int(FROZEN["reserved_completion_tokens"])
    first = [int(rec["tokens"]) for rec in ledger_records if rec.get("purpose") == "first_pass"]
    mean_first = sum(first) / len(first) if first else 1700.0

    def estimate(bundle_attrs: list[str], context_tokens: int) -> int:
        prompt = prompt_and_schema_tokens(bundle_attrs, descriptions)
        return prompt + context_tokens + out_p50

    def pack(policy: str) -> list[dict[str, Any]]:
        remaining = list(unresolved)
        if policy == "priority":
            remaining.sort(key=lambda item: (-priority.get(item[1], 0.0), item[0], item[1]))
        elif policy == "greedy":
            remaining.sort(key=lambda item: (item[0], -priority.get(item[1], 0.0), item[1]))
        else:
            remaining.sort(key=lambda item: (item[0], -priority.get(item[1], 0.0), item[1]))
        jobs = []
        used: set[tuple[str, str]] = set()
        for eid, name in remaining:
            if (eid, name) in used:
                continue
            doc_id = next(did for did, ent in entity_by_doc.items() if ent == eid)
            index = indexes[doc_id]
            mode = modes[(eid, name)]
            group = [name]
            group_hits = list(hits[(eid, name)])
            mates = [
                other
                for other_eid, other in remaining
                if other_eid == eid and other != name and (eid, other) not in used and modes.get((eid, other)) == mode
            ]
            if policy == "original":
                seed_src = {hit.chunk.source_id for hit in group_hits}
                for other in mates:
                    other_src = {hit.chunk.source_id for hit in hits[(eid, other)]}
                    if seed_src and other_src and len(seed_src & other_src) / len(seed_src | other_src) >= float(FROZEN["bundle_jaccard"]):
                        group.append(other)
                        group_hits.extend(hits[(eid, other)])
                        seed_src |= other_src
                    if len(group) >= MAX_BUNDLE:
                        break
            else:
                for other in mates:
                    if not _fits(index, group_hits, hits[(eid, other)], mode):
                        continue
                    group.append(other)
                    group_hits.extend(hits[(eid, other)])
                    if len(group) >= MAX_BUNDLE:
                        break
            seen: set[str] = set()
            uniq = []
            for hit in group_hits:
                if hit.chunk.source_id in seen:
                    continue
                seen.add(hit.chunk.source_id)
                uniq.append(hit)
            context_tokens = _union_tokens(index, uniq, mode)
            if context_tokens > CAP and len(group) > 1:
                group = [name]
                uniq = hits[(eid, name)]
                context_tokens = _union_tokens(index, uniq, mode)
            jobs.append(
                {
                    "entity_id": eid,
                    "doc_id": doc_id,
                    "attributes": group,
                    "mode": mode,
                    "context_tokens": context_tokens,
                    "est_tokens": estimate(group, min(context_tokens, CAP)),
                }
            )
            for attr in group:
                used.add((eid, attr))
        return jobs

    original_executed = []
    for row in extract_log:
        if row.get("phase") != "first_pass":
            continue
        original_executed.append(
            {
                "entity_id": row.get("entity_id"),
                "doc_id": row.get("doc_id"),
                "attributes": list(row.get("attributes") or []),
                "mode": row.get("mode"),
            }
        )

    def summarize(name: str, jobs: list[dict[str, Any]], executed: bool = False) -> dict[str, Any]:
        sizes = Counter(len(job["attributes"]) for job in jobs)
        tokens = [int(job.get("est_tokens") or mean_first) for job in jobs]
        covered = {(job["entity_id"], attr) for job in jobs for attr in job["attributes"]}
        entities = {job["entity_id"] for job in jobs}
        by_attr = Counter(attr for job in jobs for attr in job["attributes"])
        by_role = Counter()
        for attr, count in by_attr.items():
            for role in roles.get(attr) or []:
                by_role[role] += count
        spend = sum(tokens)
        return {
            "policy": name,
            "jobs_covered": len(covered),
            "calls_required": len(jobs),
            "bundle_size_distribution": {str(k): int(v) for k, v in sorted(sizes.items())},
            "prompt_input_output_token_estimate": {
                "sum": spend,
                "mean": spend / len(jobs) if jobs else 0,
                "p50_output_tokens": out_p50,
                "mean_recorded_first_pass": mean_first,
            },
            "entities_first_pass": len(entities),
            "coverage_by_attribute": dict(by_attr),
            "coverage_by_ast_role": dict(by_role),
            "estimated_remaining_repair_budget": max(0, THETA - spend),
            "fits_theta_first_pass": spend <= THETA,
        }

    return {
        "unresolved_jobs": len(unresolved),
        "recorded_first_pass_jobs": summarize("recorded_executed", [
            {**job, "est_tokens": mean_first} for job in original_executed
        ]),
        "original_jaccard": summarize("original_jaccard", pack("original")),
        "greedy_context_fit": summarize("greedy_context_fit", pack("greedy")),
        "priority_context_fit": summarize("priority_context_fit", pack("priority")),
    }


def classify_sql_effect(before: dict[str, tuple], after: dict[str, tuple], qid: str, sql: str, attr: str) -> list[str]:
    labels = []
    b, a = before.get(qid), after.get(qid)
    if b == a:
        return ["no SQL-visible effect"]
    if (not b) and a:
        labels.append("newly nonempty bag")
    roles = query_roles(sql, attr)
    if "WHERE" in roles:
        labels.append("predicate support change")
    if "GROUP BY / CASE" in roles:
        labels.append("group-key change")
    if "COUNT or aggregate input" in roles:
        labels.append("aggregate-input change")
    if b and a and len(b) != len(a):
        labels.append("count/value change without score movement")
    elif b and a and b != a:
        labels.append("count/value change without score movement")
    return labels or ["count/value change without score movement"]


QUERY_ATTRS: dict[str, set[str]] = {}


def replay_fill(plumbing: Path, fill: dict[str, Any], statements, predicates, bags_before) -> dict[str, Any]:
    dest = Path(tempfile.mkstemp(suffix=".db")[1])
    shutil.copy2(plumbing, dest)
    conn = sqlite3.connect(str(dest))
    bare = fill["attribute"].split(".")[-1]
    eid = fill["entity_id"]
    value = fill.get("commit") if "commit" in fill else fill.get("value")
    changed = False
    for table, in [(TABLE,)]:
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({_q(table)})")}
        if bare not in cols:
            continue
        conn.execute(
            f"UPDATE {_q(table)} SET {_q(bare)} = ? WHERE {_q('__entity_id')} = ? AND "
            f"({_q(bare)} IS NULL OR CAST({_q(bare)} AS TEXT) = '')",
            [value, eid],
        )
        if conn.execute("SELECT changes()").fetchone()[0]:
            changed = True
    conn.commit()
    after = {}
    affected = []
    for qid, sql in statements.items():
        attrs = QUERY_ATTRS.get(qid)
        if attrs is None:
            attrs = query_attrs(sql)
            QUERY_ATTRS[qid] = attrs
        if fill["attribute"] not in attrs and bare not in sql.lower():
            continue
        rewritten = official_sql(sql, dest, predicates)
        try:
            after[qid] = _norm_bag(_fetch(conn, rewritten))
        except sqlite3.Error:
            after[qid] = tuple()
        affected.append(qid)
    conn.close()
    dest.unlink(missing_ok=True)
    labels = Counter()
    per_query = []
    for qid in affected:
        tags = classify_sql_effect(bags_before, after, qid, statements[qid], fill["attribute"])
        for tag in tags:
            labels[tag] += 1
        per_query.append({"query_id": qid, "classes": tags, "changed": bags_before.get(qid) != after.get(qid)})
    visible = any(tag != "no SQL-visible effect" for tags in (row["classes"] for row in per_query) for tag in ([tags] if isinstance(tags, str) else tags))
    return {
        "entity_id": eid,
        "attribute": fill["attribute"],
        "changed_row": changed,
        "sql_visible": visible,
        "classes": dict(labels),
        "affected_queries": per_query,
        "value": value,
    }


def main() -> int:
    assert not any(
        "openrouter" in str(item).lower() or "qwen" in str(item).lower()
        for item in sys.argv
    )
    OUT.mkdir(parents=True, exist_ok=True)
    extract_log = json.loads((ARM / "extract_log.json").read_text())
    repair_log = json.loads((ARM / "repair_log.json").read_text())
    fills = json.loads((ARM / "fills.json").read_text())
    ledger = json.loads((ARM / "ledger.json").read_text())
    arm = json.loads((ARM / "finan_additive_arm.json").read_text())
    documents = documents_for("Finan")
    queries = queries_for("Finan")
    statements = {row["query_id"]: row["sql"] for row in queries}
    _, workload = analyze_workload(statements)
    catalog = load_catalog()
    descriptions = {
        name: str((catalog.get(name.split(".")[-1].lower()) or {}).get("description") or "")
        for name in workload.requirements
    }
    dtypes = {name: req.dtype or "string" for name, req in workload.requirements.items()}
    plumbing_rows = load_plumbing_rows(PLUMBING_DB)
    print("salvage start", flush=True)
    salvage = salvage_arm(extract_log, repair_log, documents, plumbing_rows, dtypes)
    (OUT / "salvage_records.json").write_text(json.dumps(salvage["records"], indent=2, default=str))

    entity_by_doc: dict[str, str] = {}
    missing_by_entity: dict[str, set[str]] = {}
    docs_by_stem = {document_stem(doc.doc_id) or doc.doc_id: doc for doc in documents}
    for row in plumbing_rows:
        stem = str(row.get("__provenance_label") or document_stem(str(row.get("doc_id") or "")))
        doc = docs_by_stem.get(stem)
        if doc is None:
            continue
        eid = str(row["__entity_id"])
        entity_by_doc[doc.doc_id] = eid
        missing_by_entity[eid] = {
            name for name in workload.requirements if _null(row.get(name.split(".")[-1]))
        }
    documents = [doc for doc in documents if doc.doc_id in entity_by_doc]
    gated = gated_query_counts(PLUMBING_DB, statements, live_predicates(enumerate_predicates(audit_workload(queries).occurrences, audit_workload(queries).signature_eligible)), workload)
    missing = missing_mass(PLUMBING_DB, TABLE, workload.requirements)
    ranked = rank_attributes(workload, gated, missing, descriptions)
    specs = build_specs(workload.requirements, workload, catalog, {})

    print("index start", flush=True)
    indexes = {}
    with ThreadPoolExecutor(max_workers=min(6, len(documents))) as pool:
        futs = {pool.submit(index_document, doc.doc_id, doc.text): doc for doc in documents}
        for fut in as_completed(futs):
            index = fut.result()
            indexes[index.doc_id] = index
    print(f"indexed {len(indexes)}", flush=True)

    print("bundle simulation start", flush=True)
    bundles = simulate_bundles(
        documents, indexes, specs, ranked, missing_by_entity, entity_by_doc, descriptions, extract_log, ledger.get("records") or []
    )
    (OUT / "bundle_simulation.json").write_text(json.dumps(bundles, indent=2, default=str))

    print("typed candidates start", flush=True)
    candidates = []
    for doc in documents:
        eid = entity_by_doc[doc.doc_id]
        candidates.extend(candidates_for_document(indexes[doc.doc_id], specs, dtypes, eid))
    candidate_payload = {
        "n": len(candidates),
        "model": None,
        "qwen_calls": 0,
        "candidates": candidates,
    }
    cand_hash = _hash(candidate_payload)
    (OUT / "typed_candidates.json").write_text(json.dumps(candidate_payload, indent=2, default=str))
    frozen_candidates = {
        "candidate_sha256": cand_hash,
        "n": len(candidates),
        "qwen_calls": 0,
        "wrote_frozen_db": False,
    }
    (OUT / "typed_candidates.frozen.json").write_text(json.dumps(frozen_candidates, indent=2))
    print(f"froze candidates {cand_hash} n={len(candidates)}", flush=True)

    null_cells = []
    by_eid = {str(row["__entity_id"]): row for row in plumbing_rows}
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in candidates:
        groups[(item["entity_id"], item["attribute"])].append(item)
    for eid, missing_set in missing_by_entity.items():
        for attr in missing_set:
            pool = groups.get((eid, attr), [])
            norms = {str(row.get("normalized_value")) for row in pool}
            if not pool:
                kind = "none"
            elif len(pool) == 1:
                kind = "one_unambiguous"
            elif len(norms) == 1:
                kind = "multiple_agreeing"
            else:
                kind = "conflicting"
            null_cells.append({"entity_id": eid, "attribute": attr, "kind": kind, "n": len(pool)})
    null_kinds = Counter(row["kind"] for row in null_cells)

    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    bags_before = {}
    conn = sqlite3.connect(f"file:{PLUMBING_DB}?mode=ro", uri=True)
    for qid, sql in statements.items():
        bags_before[qid] = _norm_bag(_fetch(conn, official_sql(sql, PLUMBING_DB, predicates)))
    conn.close()

    print("sql visibility start", flush=True)
    accepted = fills.get("accepted_fills") or []
    accepted_replays = [replay_fill(PLUMBING_DB, row, statements, predicates, bags_before) for row in accepted]
    salvage_replays = [
        replay_fill(
            PLUMBING_DB,
            {**row, "value": row.get("commit")},
            statements,
            predicates,
            bags_before,
        )
        for row in salvage["sql_eligible"]
    ]
    unambiguous = []
    for row in null_cells:
        if row["kind"] not in {"one_unambiguous", "multiple_agreeing"}:
            continue
        pool = groups[(row["entity_id"], row["attribute"])]
        best = sorted(pool, key=lambda item: -float(item["match_score"]))[0]
        if best.get("norm_error"):
            continue
        if str(best.get("source_span") or "").lower().find(str(best.get("raw_value") or "").lower()) < 0:
            continue
        unambiguous.append(
            {
                "entity_id": row["entity_id"],
                "attribute": row["attribute"],
                "value": best.get("normalized_value"),
                "commit": best.get("normalized_value"),
                "raw": best.get("raw_value"),
                "span": best.get("source_span"),
                "rule": best.get("extraction_rule"),
                "score": best.get("match_score"),
            }
        )
    # replay a bounded unambiguous set: all WHERE-critical plus cap
    critical = {row["attribute"] for row in ranked if row.get("empty_or_zero_support_queries_gated", 0) > 0}
    replay_unamb = [row for row in unambiguous if row["attribute"] in critical][:80]
    if len(replay_unamb) < 40:
        replay_unamb = unambiguous[:80]
    det_replays = [replay_fill(PLUMBING_DB, row, statements, predicates, bags_before) for row in replay_unamb]
    replay_payload = {
        "accepted_fills": accepted_replays,
        "salvaged": salvage_replays,
        "deterministic_unambiguous_sample": det_replays,
    }
    replay_hash = _hash(replay_payload)
    (OUT / "sql_visibility.json").write_text(json.dumps(replay_payload, indent=2, default=str))
    (OUT / "sql_visibility.frozen.json").write_text(json.dumps({"sha256": replay_hash, "qwen_calls": 0}, indent=2))
    print(f"froze sql visibility {replay_hash}", flush=True)

    from diagnostics.run_config_grid import load_ground_truth

    gold = load_ground_truth(gold_name("Finan"))
    gold_rows = {str(row.get("id") or ""): row for row in gold.get(TABLE) or []}
    gold_cells = {}
    for plow in plumbing_rows:
        stem = str(plow.get("__provenance_label") or "")
        grow = gold_rows.get(stem)
        if not grow:
            continue
        for name in workload.requirements:
            bare = name.split(".")[-1]
            if grow.get(bare) not in (None, ""):
                gold_cells[(str(plow["__entity_id"]), name)] = grow.get(bare)

    def pr(items: list[dict[str, Any]], key_attr="attribute", key_val="normalized_value") -> dict[str, Any]:
        tp = fp = 0
        by_rule = defaultdict(lambda: {"tp": 0, "fp": 0})
        by_attr = defaultdict(lambda: {"tp": 0, "fp": 0})
        by_role = defaultdict(lambda: {"tp": 0, "fp": 0})
        by_band = defaultdict(lambda: {"tp": 0, "fp": 0})
        by_src = defaultdict(lambda: {"tp": 0, "fp": 0})
        seen_gold: set[tuple[str, str]] = set()
        for item in items:
            eid = item.get("entity_id")
            attr = item.get(key_attr)
            pred = item.get(key_val)
            gold_v = gold_cells.get((eid, attr))
            hit = gold_v is not None and _match_gold(gold_v, pred, dtypes.get(attr, "string"))
            if hit:
                tp += 1
                seen_gold.add((eid, attr))
            else:
                fp += 1
            rule = item.get("extraction_rule") or item.get("rule") or "salvage"
            band = "high" if float(item.get("match_score") or item.get("score") or 0) >= 0.75 else (
                "mid" if float(item.get("match_score") or item.get("score") or 0) >= 0.5 else "low"
            )
            src = "table" if item.get("scalar") is False or rule == "table_header_row" else "scalar"
            for bucket, key in (
                (by_rule, rule),
                (by_attr, attr),
                (by_band, band),
                (by_src, src),
            ):
                bucket[key]["tp" if hit else "fp"] += 1
            for role in role_buckets(workload.requirements[attr].roles) if attr in workload.requirements else []:
                by_role[role]["tp" if hit else "fp"] += 1
        gold_n = len(gold_cells)
        def _pack(d):
            return {
                k: {
                    **v,
                    "precision": v["tp"] / (v["tp"] + v["fp"]) if (v["tp"] + v["fp"]) else 0.0,
                    "recall": None,
                }
                for k, v in d.items()
            }
        return {
            "precision": tp / (tp + fp) if (tp + fp) else 0.0,
            "recall": len(seen_gold) / gold_n if gold_n else 0.0,
            "tp": tp,
            "fp": fp,
            "gold_cells": gold_n,
            "by_rule": _pack(by_rule),
            "by_attribute": _pack(by_attr),
            "by_ast_role": _pack(by_role),
            "by_score_band": _pack(by_band),
            "by_scalar_vs_table": _pack(by_src),
        }

    cand_pr = pr(candidates)
    for attr, cell in cand_pr["by_attribute"].items():
        gold_n = sum(1 for (eid, name) in gold_cells if name == attr)
        cell["recall"] = cell["tp"] / gold_n if gold_n else 0.0

    def replay_correctness(replays: list[dict[str, Any]]) -> dict[str, Any]:
        by_class = defaultdict(lambda: {"n": 0, "correct": 0})
        for row in replays:
            pred = row.get("value")
            gold_v = gold_cells.get((row["entity_id"], row["attribute"]))
            hit = gold_v is not None and _match_gold(gold_v, pred, dtypes.get(row["attribute"], "string"))
            classes = [k for k, n in (row.get("classes") or {}).items() if n]
            if row.get("sql_visible"):
                classes = [k for k in classes if k != "no SQL-visible effect"] or classes
            else:
                classes = ["no SQL-visible effect"]
            for klass in classes:
                by_class[klass]["n"] += 1
                by_class[klass]["correct"] += int(hit)
        return {
            klass: {**vals, "precision": vals["correct"] / vals["n"] if vals["n"] else 0.0}
            for klass, vals in by_class.items()
        }

    _, test = split_80_20(queries, 42)
    test_count = [row for row in test if is_count_query(query_shape(row["query_id"], row["sql"]))]
    frozen = json.loads((ARM / "frozen.json").read_text())
    empty_official = set(frozen["empty_bag_ids_after"])
    empty_test = [row["query_id"] for row in test_count if row["query_id"] in empty_official]
    leftover = []
    for qid in empty_test:
        sql = statements[qid]
        attrs = sorted(query_attrs(sql))
        leftover.append(
            {
                "query_id": qid,
                "attributes": attrs,
                "roles": sorted({role for attr in attrs if attr in workload.requirements for role in role_buckets(workload.requirements[attr].roles)}),
            }
        )

    accepted_n = len(accepted)
    calls = int((arm.get("qwen_calls") or {}).get("extractor") or 0) + int((arm.get("qwen_calls") or {}).get("repair") or 0)
    spent = int(arm.get("spent") or ledger.get("spent") or 0)
    jobs_attempted = len([row for row in extract_log if not row.get("from_cache")])
    sql_visible_accepted = sum(1 for row in accepted_replays if row["sql_visible"])
    salvage_visible = sum(1 for row in salvage_replays if row["sql_visible"])
    det_visible = sum(1 for row in det_replays if row["sql_visible"])

    # rerun yield estimate: priority context-fit jobs that fit theta
    sim = bundles["priority_context_fit"]
    calls_fit = sim["calls_required"]
    if sim["prompt_input_output_token_estimate"]["sum"] > THETA and calls_fit:
        frac = THETA / sim["prompt_input_output_token_estimate"]["sum"]
        calls_fit = int(calls_fit * frac)
        jobs_fit = int(sim["jobs_covered"] * frac)
    else:
        jobs_fit = sim["jobs_covered"]
    salvage_rate = salvage["estimated_sql_visible_if_null_only"] / max(1, salvage["malformed_attribute_entries"])
    accept_rate = accepted_n / max(1, jobs_attempted)
    visible_rate = sql_visible_accepted / max(1, accepted_n)
    useful_from_extract = jobs_fit * accept_rate * visible_rate
    useful_from_salvage = jobs_fit * (salvage["malformed_attribute_entries"] / max(1, salvage["completions"])) * salvage_rate * 0.25
    unamb_correct = 0
    for row in unambiguous:
        gold_v = gold_cells.get((row["entity_id"], row["attribute"]))
        if gold_v is not None and _match_gold(gold_v, row.get("commit"), dtypes.get(row["attribute"], "string")):
            unamb_correct += 1
    det_precision = unamb_correct / len(unambiguous) if unambiguous else 0.0
    useful_from_det = int(null_kinds.get("one_unambiguous", 0) * det_precision)

    if useful_from_det >= 40 and det_precision >= 0.35:
        recommendation = 2
        reason = "Unambiguous deterministic candidates cover more NULL cells than the frozen arm accepted, with usable post-freeze precision; spend Qwen only to validate/disambiguate."
    elif jobs_fit >= 400 and useful_from_extract + useful_from_salvage >= 40:
        recommendation = 1
        reason = "Denser context-fit bundles plus salvage raise first-pass coverage enough that a theta-capped rerun can produce more useful cells than 19."
    else:
        recommendation = 3
        reason = "Attained and simulated useful-cell counts stay far below the WHERE-critical mass that empty test bags require."

    report = {
        "qwen_calls": 0,
        "wrote_frozen_databases": False,
        "salvage": {k: v for k, v in salvage.items() if k not in {"records", "sql_eligible"}},
        "bundle_simulation": bundles,
        "typed_candidates": {
            "n": len(candidates),
            "sha256": cand_hash,
            "null_cell_kinds": dict(null_kinds),
            "unambiguous": int(null_kinds.get("one_unambiguous", 0)),
            "agreeing": int(null_kinds.get("multiple_agreeing", 0)),
            "conflicting": int(null_kinds.get("conflicting", 0)),
            "none": int(null_kinds.get("none", 0)),
            "post_freeze": cand_pr,
        },
        "sql_visibility": {
            "sha256": replay_hash,
            "accepted": {
                "n": len(accepted_replays),
                "sql_visible": sql_visible_accepted,
                "class_counts": dict(sum((Counter(row["classes"]) for row in accepted_replays), Counter())),
                "post_freeze_correctness": replay_correctness(accepted_replays),
            },
            "salvaged": {
                "n": len(salvage_replays),
                "sql_visible": salvage_visible,
                "class_counts": dict(sum((Counter(row["classes"]) for row in salvage_replays), Counter())),
                "post_freeze_correctness": replay_correctness(salvage_replays),
            },
            "deterministic_unambiguous_sample": {
                "n": len(det_replays),
                "sql_visible": det_visible,
                "class_counts": dict(sum((Counter(row["classes"]) for row in det_replays), Counter())),
                "post_freeze_correctness": replay_correctness(det_replays),
            },
        },
        "throughput": {
            "tokens_spent": spent,
            "extractor_jobs_attempted": jobs_attempted,
            "accepted_fills": accepted_n,
            "sql_visible_accepted": sql_visible_accepted,
            "tokens_per_attempted_job": spent / jobs_attempted if jobs_attempted else None,
            "tokens_per_accepted_cell": spent / accepted_n if accepted_n else None,
            "tokens_per_sql_visible_cell": spent / sql_visible_accepted if sql_visible_accepted else None,
        },
        "empty_test_bags": leftover,
        "rerun_estimate": {
            "theta": THETA,
            "priority_context_fit_jobs_if_uncapped": sim["jobs_covered"],
            "calls_if_uncapped": sim["calls_required"],
            "jobs_fitting_theta": jobs_fit,
            "calls_fitting_theta": calls_fit,
            "useful_cells_from_extract_rate": useful_from_extract,
            "useful_cells_from_salvage": useful_from_salvage,
            "useful_unambiguous_deterministic": useful_from_det,
            "deterministic_unambiguous_precision": det_precision,
        },
        "recommendation": {
            "choice": recommendation,
            "label": {
                1: "rerun with deterministic salvage plus denser bundles",
                2: "use deterministic candidates and Qwen only for validation/disambiguation",
                3: "abandon schema extraction for Finan because the attainable coverage remains insufficient",
            }[recommendation],
            "reason": reason,
        },
        "hashes": {
            "additive_db": arm.get("db_sha256"),
            "candidates": cand_hash,
            "sql_visibility": replay_hash,
            "report": None,
        },
    }
    report["hashes"]["report"] = _hash({k: v for k, v in report.items() if k != "hashes"})
    (OUT / "finan_throughput_audit.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({"wrote": str(OUT / "finan_throughput_audit.json"), "recommendation": report["recommendation"], "salvage_sql": salvage["estimated_sql_visible_if_null_only"], "candidates": len(candidates)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
