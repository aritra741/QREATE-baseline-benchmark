"""Zero-token replay: hybrid signatures, realizability, presence audit."""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WDIRS = ROOT / "systems" / "WDIRS"
if str(WDIRS) not in sys.path:
    sys.path.insert(0, str(WDIRS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwarts.core.signature import audit_workload, enumerate_predicates, rewrite_sql
from quwarts.core.signature_realize import (
    close_attribute,
    is_membership,
    is_presence,
)
from quwarts.eval.signature_diagnostics import copy_swap, score_db


def overlay_columns(dest: Path, donor: Path, preds) -> None:
    src = sqlite3.connect(donor)
    dst = sqlite3.connect(dest)
    try:
        for pred in preds:
            src_cols = {row[1] for row in src.execute(f"PRAGMA table_info({_q(pred.table)})")}
            dst_cols = {row[1] for row in dst.execute(f"PRAGMA table_info({_q(pred.table)})")}
            if pred.sig_name not in src_cols or pred.sig_name not in dst_cols:
                continue
            for doc_id, value in src.execute(
                f"SELECT doc_id, {_q(pred.sig_name)} FROM {_q(pred.table)}"
            ):
                dst.execute(
                    f"UPDATE {_q(pred.table)} SET {_q(pred.sig_name)} = ? WHERE doc_id = ?",
                    (value, doc_id),
                )
        dst.commit()
    finally:
        src.close()
        dst.close()
from quwarts.experiments.player_case80 import split_80_20
from quwarts.experiments.synthesize_case80 import documents_for, gold_name, queries_for

APRIME = next((ROOT / "results" / "quwarts_med_aprime" / "artifacts" / "databases").glob("*.db"))
GOLD_SIG = ROOT / "results" / "quwarts_med_signatures" / "artifacts" / "aprime_gold_sig.db"
STEP5 = ROOT / "results" / "quwarts_med_signatures" / "artifacts" / "aprime_model_sig.db"
V2 = ROOT / "results" / "quwarts_med_signatures" / "artifacts" / "aprime_model_sig_v2_subset.db"
OUT = ROOT / "results" / "quwarts_med_signatures"
NAME_COLS = {
    "disease": "disease_name",
    "drug": "generic_name",
    "institution": "institution_name",
}


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _fold(value) -> str:
    return " ".join(str(value or "").replace("_", " ").casefold().split())


def _cell(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def load_rows(path: Path, table: str) -> list[dict]:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in con.execute(f"SELECT * FROM {_q(table)}")]
    finally:
        con.close()


def realizability_report(path: Path, predicates) -> dict:
    by_attr = defaultdict(list)
    for pred in predicates:
        by_attr[pred.attribute].append(pred)
    kinds: Counter[str] = Counter()
    n_rows = 0
    n_illegal = 0
    for attr, group in by_attr.items():
        table = group[0].table
        try:
            rows = load_rows(path, table)
        except sqlite3.Error:
            continue
        seen = set()
        for row in rows:
            n_rows += 1
            if row.get("doc_id") in seen:
                continue
            seen.add(row.get("doc_id"))
            truths = {p.pred_id: _cell(row.get(p.sig_name)) for p in group}
            _, violations = close_attribute(truths, group)
            if violations:
                n_illegal += 1
                kinds.update(violations)
    return {"n_row_attributes": n_rows, "n_illegal": n_illegal, "kinds": dict(kinds)}


def apply_closure(path: Path, predicates) -> int:
    by_attr = defaultdict(list)
    for pred in predicates:
        by_attr[pred.attribute].append(pred)
    n = 0
    con = sqlite3.connect(path)
    try:
        for attr, group in by_attr.items():
            table = group[0].table
            cols = {row[1] for row in con.execute(f"PRAGMA table_info({_q(table)})")}
            if "doc_id" not in cols:
                continue
            for row in con.execute(f"SELECT doc_id, {', '.join(_q(p.sig_name) for p in group)} FROM {_q(table)}"):
                doc_id = row[0]
                truths = {group[i].pred_id: _cell(row[i + 1]) for i in range(len(group))}
                closed, violations = close_attribute(truths, group)
                if not violations:
                    continue
                n += 1
                assignments = ", ".join(f"{_q(p.sig_name)} = ?" for p in group)
                con.execute(
                    f"UPDATE {_q(table)} SET {assignments} WHERE doc_id = ?",
                    [closed.get(p.pred_id) for p in group] + [doc_id],
                )
        con.commit()
    finally:
        con.close()
    return n


def set_constant(path: Path, pred, value: int) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute(f"UPDATE {_q(pred.table)} SET {_q(pred.sig_name)} = ?", (value,))
        con.commit()
    finally:
        con.close()


def in_text(value: str | None, text: str | None) -> bool:
    if not value or not text:
        return False
    hay = _fold(text)
    needle = _fold(value)
    if needle and needle in hay:
        return True
    for part in re.split(r"[|;,/]+", str(value)):
        piece = _fold(part)
        if len(piece) >= 4 and piece in hay:
            return True
    return False


def gold_by_stem(tables: dict) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for table, rows in tables.items():
        mapping = {}
        for row in rows:
            stem = str(row.get("id") or "").strip()
            if stem and stem not in mapping:
                mapping[stem] = row
        out[table] = mapping
    return out


def main() -> int:
    from diagnostics.run_config_grid import load_ground_truth

    queries = queries_for("Med")
    train, test = split_80_20(queries, 42)
    report = audit_workload(queries)
    predicates = enumerate_predicates(report.occurrences, report.signature_eligible)
    members = [p for p in predicates if is_membership(p)]
    presence = [p for p in predicates if is_presence(p)]
    v2_attrs = {"drug.manufacturer", "drug.pharmaceutical_form"}
    v2_members = [p for p in members if p.attribute in v2_attrs]
    v2_presence = [p for p in presence if p.attribute in v2_attrs]
    gold = load_ground_truth(gold_name("Med"))
    dest_dir = OUT / "artifacts" / "replay"
    dest_dir.mkdir(parents=True, exist_ok=True)

    pre = {
        "step5": realizability_report(STEP5, predicates),
        "v2_subset": realizability_report(V2, predicates),
        "gold": realizability_report(GOLD_SIG, predicates),
    }

    variants = {}
    # 1 hybrid: step5 base, v2 membership
    hybrid = dest_dir / "hybrid.db"
    copy_swap(hybrid, STEP5, V2, v2_members)
    variants["hybrid"] = score_db(hybrid, test, predicates, gold)

    # 2 hybrid + closure
    hybrid_closed = dest_dir / "hybrid_closed.db"
    shutil.copy2(hybrid, hybrid_closed)
    n_closed = apply_closure(hybrid_closed, predicates)
    variants["hybrid_plus_closure"] = score_db(hybrid_closed, test, predicates, gold)
    variants["hybrid_plus_closure"]["n_rows_closed"] = n_closed

    # 3 v2 membership + gold presence
    v2_gold_pres = dest_dir / "v2_member_gold_presence.db"
    copy_swap(v2_gold_pres, STEP5, V2, v2_members)
    overlay_columns(v2_gold_pres, GOLD_SIG, v2_presence)
    variants["v2_membership_gold_presence"] = score_db(v2_gold_pres, test, predicates, gold)
    apply_closure(v2_gold_pres, predicates)
    variants["v2_membership_gold_presence_closed"] = score_db(v2_gold_pres, test, predicates, gold)

    # 4 gold membership + model presence
    gold_mem_model_pres = dest_dir / "gold_member_model_presence.db"
    copy_swap(gold_mem_model_pres, STEP5, GOLD_SIG, v2_members)
    variants["gold_membership_model_presence"] = score_db(gold_mem_model_pres, test, predicates, gold)

    variants["step5"] = score_db(STEP5, test, predicates, gold)
    variants["v2_raw"] = score_db(V2, test, predicates, gold)

    print("variants", {k: v.get("mean_per_query_product") for k, v in variants.items()}, flush=True)

    docs = {doc.doc_id: doc.text for doc in documents_for("Med")}
    gold_stem = gold_by_stem(gold)
    aprime = {
        table: {row["doc_id"]: row for row in load_rows(APRIME, table) if row.get("doc_id")}
        for table in ("disease", "drug", "institution")
    }
    gold_sig_rows = {
        table: {row["doc_id"]: row for row in load_rows(GOLD_SIG, table) if row.get("doc_id")}
        for table in ("disease", "drug", "institution")
    }
    step5_rows = {
        table: {row["doc_id"]: row for row in load_rows(STEP5, table) if row.get("doc_id")}
        for table in ("disease", "drug", "institution")
    }

    presence_audit = {}
    prior_dir = dest_dir / "priors"
    prior_dir.mkdir(exist_ok=True)
    for pred in presence:
        n = {"TRUE": 0, "FALSE": 0, "NULL": 0}
        span = 0
        name_overlap = 0
        unavailable = 0
        gold_true = 0
        for doc_id, grow in gold_sig_rows.get(pred.table, {}).items():
            g = _cell(grow.get(pred.sig_name))
            label = "TRUE" if g == 1 else "FALSE" if g == 0 else "NULL"
            n[label] += 1
            if g != 1:
                continue
            gold_true += 1
            stem = Path(str(doc_id)).stem
            gold_row = gold_stem.get(pred.table, {}).get(stem) or {}
            gold_val = gold_row.get(pred.column)
            text = docs.get(doc_id, "")
            arow = aprime.get(pred.table, {}).get(doc_id) or {}
            entity = (
                arow.get(f"{pred.table}_name")
                or arow.get("generic_name")
                or gold_row.get(NAME_COLS.get(pred.table, ""))
                or ""
            )
            has_span = in_text(str(gold_val) if gold_val is not None else None, text)
            has_name = in_text(str(gold_val) if gold_val is not None else None, str(entity)) or in_text(str(entity), str(gold_val) if gold_val else "")
            if has_span:
                span += 1
            if has_name:
                name_overlap += 1
            if not has_span and not has_name:
                unavailable += 1
        always_t = prior_dir / f"{pred.pred_id}_true.db"
        always_f = prior_dir / f"{pred.pred_id}_false.db"
        shutil.copy2(STEP5, always_t)
        shutil.copy2(STEP5, always_f)
        set_constant(always_t, pred, 1)
        set_constant(always_f, pred, 0)
        t_score = score_db(always_t, test, predicates, gold)
        f_score = score_db(always_f, test, predicates, gold)
        presence_audit[pred.pred_id] = {
            "attribute": pred.attribute,
            "gold_prevalence": n,
            "gold_true_rate": n["TRUE"] / max(1, sum(n.values())),
            "gold_true": gold_true,
            "span_supported": span,
            "span_rate": span / gold_true if gold_true else None,
            "name_overlap": name_overlap,
            "name_overlap_rate": name_overlap / gold_true if gold_true else None,
            "apparently_unavailable": unavailable,
            "unavailable_rate": unavailable / gold_true if gold_true else None,
            "always_true_product": t_score["mean_per_query_product"],
            "always_false_product": f_score["mean_per_query_product"],
            "step5_product": variants["step5"]["mean_per_query_product"],
            "always_true_delta": t_score["mean_per_query_product"] - variants["step5"]["mean_per_query_product"],
            "always_false_delta": f_score["mean_per_query_product"] - variants["step5"]["mean_per_query_product"],
        }
        print(
            f"presence {pred.attribute} true_rate={presence_audit[pred.pred_id]['gold_true_rate']:.2f} "
            f"span={presence_audit[pred.pred_id]['span_rate']} "
            f"alwaysT {presence_audit[pred.pred_id]['always_true_delta']:+.4f}",
            flush=True,
        )

    # Cache reuse on gold names and on A' available keys.
    def reuse_stats(keys: list[str]) -> dict:
        counts = Counter(keys)
        n = len(keys)
        n_distinct = len(counts)
        reuse = [c for c in counts.values() if c > 1]
        return {
            "n_entities": n,
            "n_distinct_keys": n_distinct,
            "keys_over_entities": n_distinct / n if n else None,
            "n_keys_reused": len(reuse),
            "max_reuse": max(counts.values()) if counts else 0,
            "mean_reuse": (sum(counts.values()) / n_distinct) if n_distinct else None,
            "reuse_histogram": dict(Counter(counts.values())),
        }

    cache = {"gold_entity_name": {}, "aprime_native_key": {}}
    for table in ("disease", "drug", "institution"):
        gold_keys = []
        aprime_keys = []
        for doc_id, grow in gold_sig_rows.get(table, {}).items():
            stem = Path(str(doc_id)).stem
            grow_gold = gold_stem.get(table, {}).get(stem) or {}
            name = _fold(grow_gold.get(NAME_COLS.get(table, "")))
            gold_keys.append(name or stem)
            arow = aprime.get(table, {}).get(doc_id) or {}
            native = arow.get(f"{table}_name") or arow.get("generic_name") or arow.get("name")
            aprime_keys.append(_fold(native) if native else stem)
        cache["gold_entity_name"][table] = reuse_stats(gold_keys)
        cache["aprime_native_key"][table] = reuse_stats(aprime_keys)

    payload = {
        "label": "zero_token_replay",
        "realizability_before_repair": pre,
        "variants": {
            name: {k: row[k] for k in row if k != "per_query_product"}
            for name, row in variants.items()
        },
        "presence_audit": presence_audit,
        "cache_reuse": cache,
        "entity_label": {
            "added_to_evidence": True,
            "query_visible": False,
            "note": "Internal subject label for cache/ER/diagnostics. Not a user-visible column.",
        },
        "v2_scope": sorted(v2_attrs),
        "n_membership": len(members),
        "n_presence": len(presence),
    }
    path = OUT / "replay_hybrids.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    summary = {
        "wrote": str(path),
        "products": {k: v.get("mean_per_query_product") for k, v in variants.items()},
        "realizability": pre,
        "cache": cache,
        "presence_top_always_true": sorted(
            ((v["attribute"], v["always_true_delta"], v["gold_true_rate"], v["span_rate"])
             for v in presence_audit.values()),
            key=lambda item: -item[1],
        )[:8],
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
