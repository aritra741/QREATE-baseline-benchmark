"""Label-free candidate generation and validation. No gold, no corpus names."""

from __future__ import annotations

import json
import random
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from quwarts.core.extract import find_surface_span
from quwarts.core.ledger import BudgetExhausted, BudgetedCaller
from quwarts.core.models import SourceDocument, Workload
from quwarts.core.signature import AtomicPredicate, rewrite_sql
from quwarts.core.signature_cache import CachedCaller, ResponseCache
from quwarts.core.signature_classify import (
    _object,
    membership_prompt,
    nonempty_prompt,
    parse_nonempty,
    parse_v2,
    predicate_lines,
    value_is_missing,
)
from quwarts.core.signature_controller import _documents, _empty_rate, _load_attr_rows, observe
from quwarts.core.signature_populate import (
    _close_labels,
    _quote,
    _write_row,
    clip_document,
    ensure_signature_columns,
    populate_membership,
    populate_nonempty,
    resolve_table,
)
from quwarts.core.signature_realize import is_membership, is_presence
from quwarts.core.truth import PredicateLabel, is_label_resolved, merge_atoms

STRATEGIES = ("direct", "decompose", "gleaning")
SAMPLE_SIZE = 6
TOKENS_PER_ATOM = 200
PLANNER_PROMPT = """Generate exactly three candidate acquisition plans for one unresolved cohort.
Use only these generic strategies: direct, decompose, gleaning.
direct = one-pass extraction or classification.
decompose = extract a note, then decide.
gleaning = extract, validate, then refine.
Each plan must name operator (grounded_existence|semantic_membership|abstain),
context (value|entity_label|document), n_passes, estimated_cost, and a prompt.
Do not use dataset names, gold, scorers, or baseline outputs.
You may choose abstain for a strategy if remaining budget is too small.
Return JSON: {"plans": [{"strategy": "direct|decompose|gleaning", "operator": "...",
"context": "...", "n_passes": 1, "estimated_cost": 0, "prompt": "..."}, ...]}
COHORT:
"""
DECOMPOSE_PROMPT = (
    "Write a short note of any evidence for ATTRIBUTE from the context. "
    "Return JSON {\"note\": \"...\"}. Do not answer queries.\n"
)
VALIDATE_PROMPT = (
    "Does the document support this answer for the attribute? "
    "Return JSON {\"ok\": true|false, \"issue\": \"...\"}.\n"
)
PAIR_PROMPT = (
    "Two anonymous answers for the same predicate and document. "
    "Pick which is better supported. Names are arbitrary. "
    "Return JSON {\"winner\": \"A\"|\"B\"|\"tie\"}.\n"
)


@dataclass
class CandidatePlan:
    strategy: str
    operator: str
    context: str
    n_passes: int
    estimated_cost: int
    prompt: str
    attribute: str = ""
    predicate_ids: tuple[str, ...] = ()

    def as_json(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "operator": self.operator,
            "context": self.context,
            "n_passes": self.n_passes,
            "estimated_cost": self.estimated_cost,
            "prompt": self.prompt,
            "attribute": self.attribute,
            "predicate_ids": list(self.predicate_ids),
        }


@dataclass
class CandidateReport:
    n_cohorts_attempted: int = 0
    n_cohorts_accepted: int = 0
    tokens_spent: int = 0
    tokens_planner: int = 0
    tokens_executor: int = 0
    tokens_refiner: int = 0
    tokens_validator: int = 0
    validator_agree: int = 0
    validator_tie: int = 0
    validator_calls: int = 0
    grounded_ok: int = 0
    grounded_n: int = 0
    n_true: int = 0
    n_false: int = 0
    n_null: int = 0
    n_conflicts: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    accepted: list[dict[str, Any]] = field(default_factory=list)
    query_deltas: list[dict[str, Any]] = field(default_factory=list)
    prior_feedback: list[dict[str, Any]] = field(default_factory=list)


def default_plans(attribute: str, operator: str, pred_ids: tuple[str, ...]) -> list[CandidatePlan]:
    return [
        CandidatePlan("direct", operator, "document", 1, 200, "one-pass typed operator", attribute, pred_ids),
        CandidatePlan("decompose", operator, "document", 2, 400, "note then decide", attribute, pred_ids),
        CandidatePlan("gleaning", operator, "document", 3, 600, "extract validate refine", attribute, pred_ids),
    ]


def parse_plans(text: str, attribute: str, pred_ids: tuple[str, ...], default_op: str) -> list[CandidatePlan]:
    payload = _object(text)
    raw = payload.get("plans") or []
    found: list[CandidatePlan] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        strategy = str(item.get("strategy") or "").strip()
        if strategy not in STRATEGIES:
            continue
        operator = str(item.get("operator") or default_op).strip()
        if operator not in {"grounded_existence", "semantic_membership", "abstain"}:
            operator = default_op
        context = str(item.get("context") or "document").strip()
        if context not in {"value", "entity_label", "document"}:
            context = "document"
        try:
            n_passes = max(1, int(item.get("n_passes") or 1))
        except (TypeError, ValueError):
            n_passes = 1
        try:
            cost = max(1, int(item.get("estimated_cost") or n_passes * TOKENS_PER_ATOM))
        except (TypeError, ValueError):
            cost = n_passes * TOKENS_PER_ATOM
        found.append(
            CandidatePlan(
                strategy=strategy,
                operator=operator,
                context=context,
                n_passes=n_passes,
                estimated_cost=cost,
                prompt=str(item.get("prompt") or strategy),
                attribute=attribute,
                predicate_ids=pred_ids,
            )
        )
    by_strategy = {item.strategy: item for item in found}
    if len(by_strategy) < 3:
        return default_plans(attribute, default_op, pred_ids)
    return [by_strategy[name] for name in STRATEGIES]


def estimated_cohort_cost(unresolved_mass: int) -> float:
    sample = 3 * SAMPLE_SIZE * TOKENS_PER_ATOM
    validate = 3 * SAMPLE_SIZE * 120
    full = max(int(unresolved_mass), 1) * TOKENS_PER_ATOM
    return float(sample + validate + full)


def rank_cohorts(observation: dict[str, Any]) -> list[dict[str, Any]]:
    ranked = []
    for item in observation.get("attributes") or []:
        mass = int(item.get("unresolved_atoms") or 0)
        if mass <= 0:
            continue
        freq = float(item.get("query_frequency") or 1)
        amp = float(item.get("amplification") or 1)
        cost = estimated_cohort_cost(mass)
        row = dict(item)
        row["estimated_cost"] = cost
        row["_priority"] = (freq * amp * mass) / cost
        ranked.append(row)
    ranked.sort(key=lambda item: item["_priority"], reverse=True)
    return ranked


def plan_candidates(
    caller: BudgetedCaller | None,
    cache: ResponseCache,
    cohort: dict[str, Any],
    default_op: str,
    prior: list[dict[str, Any]] | None = None,
) -> list[CandidatePlan]:
    pred_ids = tuple(cohort.get("predicate_ids") or ())
    attribute = str(cohort.get("attribute") or "")
    if caller is None:
        return default_plans(attribute, default_op, pred_ids)
    state = {
        "attribute": attribute,
        "unresolved_presence": cohort.get("unresolved_presence"),
        "unresolved_membership": cohort.get("unresolved_membership"),
        "query_frequency": cohort.get("query_frequency"),
        "amplification": cohort.get("amplification"),
        "n_rows": cohort.get("n_rows"),
        "surface_rate": cohort.get("surface_rate"),
        "entity_label_rate": cohort.get("entity_label_rate"),
        "kinds": cohort.get("kinds"),
        "estimated_cost": cohort.get("estimated_cost"),
        "remaining": cohort.get("remaining"),
        "prior": prior or [],
    }
    try:
        text = cache.complete(
            caller,
            PLANNER_PROMPT + json.dumps(state, default=str),
            "sig_planner",
            system="Propose three generic acquisition plans. JSON only.",
            max_tokens=280,
            plan="planner",
        )
    except (BudgetExhausted, Exception):
        return default_plans(attribute, default_op, pred_ids)
    return parse_plans(text, attribute, pred_ids, default_op)


def stratify_sample(rows: list[dict[str, Any]], k: int = SAMPLE_SIZE, seed: int = 42) -> list[dict[str, Any]]:
    if not rows:
        return []
    lengths = sorted(len(str(row.get("document") or "")) for row in rows)
    median = lengths[len(lengths) // 2] if lengths else 0
    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        surface = "present" if not value_is_missing(row.get("cell")) else "absent"
        length = "long" if len(str(row.get("document") or "")) >= median else "short"
        status = "partial" if any(is_label_resolved(lab) for lab in (row.get("labels") or {}).values()) else "open"
        buckets[(surface, length, status)].append(row)
    rng = random.Random(seed)
    picked: list[dict[str, Any]] = []
    used: set[int] = set()
    for key in sorted(buckets):
        group = list(buckets[key])
        rng.shuffle(group)
        for row in group[:1]:
            if id(row) not in used:
                picked.append(row)
                used.add(id(row))
            if len(picked) >= k:
                return picked
    leftover = [row for row in rows if id(row) not in used]
    rng.shuffle(leftover)
    for row in leftover:
        picked.append(row)
        if len(picked) >= k:
            break
    return picked


def _bundle(row: dict[str, Any], context: str) -> tuple[str, str, list[str]]:
    document = row.get("document") or "" if context == "document" else ""
    entity = row.get("entity_name") or "" if context in {"entity_label", "document"} else ""
    surfaces = list(row.get("surfaces") or []) if context in {"value", "document"} else []
    return document, entity, surfaces


def _note(caller: BudgetedCaller, attribute: str, context_text: str) -> str:
    text = caller.complete(
        DECOMPOSE_PROMPT + f"ATTRIBUTE: {attribute}\nCONTEXT:\n{clip_document(context_text)}\n",
        "sig_executor",
        system="Extract a short evidence note. JSON only.",
        max_tokens=120,
    )
    return str(_object(text).get("note") or "").strip()


def _validate_issue(caller: BudgetedCaller, attribute: str, document: str, answer: str) -> str | None:
    text = caller.complete(
        VALIDATE_PROMPT + f"ATTRIBUTE: {attribute}\nANSWER: {answer}\nDOCUMENT:\n{clip_document(document)}\n",
        "sig_validator",
        system="Check document support. JSON only.",
        max_tokens=80,
    )
    payload = _object(text)
    if payload.get("ok") in {True, "true", "True", 1}:
        return None
    issue = str(payload.get("issue") or "").strip()
    return issue or "unsupported"


def grounded_ok(label: PredicateLabel | None) -> bool:
    if label is None or not is_label_resolved(label) or label.sql_truth != "TRUE":
        return False
    return any(item in {"cell", "nonempty_span"} for item in label.provenance)


def verify_span(label: PredicateLabel, document: str) -> bool:
    """TRUE existence needs an exact supporting span or a stored cell."""

    if not is_label_resolved(label) or label.sql_truth != "TRUE":
        return True
    if "cell" in label.provenance:
        return True
    if "nonempty_span" in label.provenance:
        return True
    for item in label.provenance:
        if item in {"cell", "nonempty_span", "closure", "nonempty_no_span", "nonempty_ungrounded", "budget", "error"}:
            continue
        if find_surface_span(document or "", item) is not None:
            return True
    return False


def drop_ungrounded(labels: dict[str, PredicateLabel], document: str) -> dict[str, PredicateLabel]:
    cleaned = {}
    for key, label in labels.items():
        if label.sql_truth == "TRUE" and not verify_span(label, document):
            cleaned[key] = PredicateLabel("NULL", "uncertain", provenance=("nonempty_ungrounded",))
        else:
            cleaned[key] = label
    return cleaned


def execute_plan_row(
    plan: CandidatePlan,
    row: dict[str, Any],
    predicates: list[AtomicPredicate],
    caller: BudgetedCaller | None,
    cache: ResponseCache | None = None,
) -> dict[str, PredicateLabel]:
    scoped = [
        pred for pred in predicates
        if pred.pred_id in set(plan.predicate_ids) or pred.attribute == plan.attribute
    ]
    presence = [pred for pred in scoped if is_presence(pred)]
    members = [pred for pred in scoped if is_membership(pred)]
    document, entity, surfaces = _bundle(row, plan.context)
    if plan.operator == "abstain" or caller is None:
        return {}
    bound: BudgetedCaller = caller
    if cache is not None and not isinstance(caller, CachedCaller):
        bound = CachedCaller(caller, cache, plan=plan.strategy)
    elif isinstance(caller, CachedCaller):
        bound = caller.bind(plan.strategy)
    extra = " ".join(filter(None, [entity, *surfaces, document]))
    if plan.strategy == "decompose":
        try:
            note = _note(bound, plan.attribute, extra)
        except (BudgetExhausted, Exception):
            note = ""
        if note:
            surfaces = list(surfaces) + [note]
            if plan.operator == "grounded_existence" and not document:
                document = note
    if plan.operator == "grounded_existence":
        label = populate_nonempty(plan.attribute, row.get("cell"), document, bound)
        if plan.strategy == "gleaning" and document and not grounded_ok(label):
            issue = None
            try:
                issue = _validate_issue(bound, plan.attribute, document, label.sql_truth)
            except (BudgetExhausted, Exception):
                issue = None
            if issue:
                try:
                    text = bound.complete(
                        nonempty_prompt(plan.attribute, clip_document(document)) + f"\nISSUE: {issue}\n",
                        "sig_refiner",
                        system="Revise the grounded span. JSON only.",
                        max_tokens=120,
                    )
                    label = parse_nonempty(text, document)
                except (BudgetExhausted, Exception):
                    pass
        labels = drop_ungrounded({pred.pred_id: label for pred in presence}, document)
        return labels
    labels = populate_membership(
        plan.attribute, members, entity_name=entity, surfaces=surfaces, document=document, caller=bound,
    )
    if plan.strategy == "gleaning" and document:
        summary = json.dumps({key: lab.sql_truth for key, lab in labels.items()})
        try:
            issue = _validate_issue(bound, plan.attribute, document, summary)
        except (BudgetExhausted, Exception):
            issue = None
        if issue:
            try:
                text = bound.complete(
                    membership_prompt(
                        plan.attribute, members, entity_name=entity, surfaces=surfaces,
                        document=clip_document(document),
                    ) + f"\nISSUE: {issue}\n",
                    "sig_refiner",
                    system="Revise membership labels. JSON only.",
                    max_tokens=280,
                )
                labels = parse_v2(text, members)
            except (BudgetExhausted, Exception):
                pass
    return labels


def _truth_map(predicates: list[AtomicPredicate], labels: dict[str, PredicateLabel]) -> dict[str, str]:
    return {
        pred.pred_id: labels.get(pred.pred_id, PredicateLabel("NULL", "uncertain")).sql_truth
        for pred in predicates
    }


def _ask_pair(
    caller: BudgetedCaller,
    predicates: list[AtomicPredicate],
    document: str,
    answer_a: dict[str, str],
    answer_b: dict[str, str],
) -> str:
    prompt = (
        PAIR_PROMPT
        + f"PREDICATES:\n{predicate_lines(predicates)}\n"
        + f"DOCUMENT:\n{clip_document(document, 1200)}\n"
        + f"ANSWER A: {json.dumps(answer_a)}\nANSWER B: {json.dumps(answer_b)}\n"
    )
    text = caller.complete(
        prompt,
        "sig_validator",
        system="Compare two anonymous answers. JSON only.",
        max_tokens=60,
    )
    winner = str(_object(text).get("winner") or "tie").strip().upper()
    if winner in {"A", "B"}:
        return winner
    return ""


def prefer_pair(
    caller: BudgetedCaller,
    predicates: list[AtomicPredicate],
    document: str,
    left: dict[str, PredicateLabel],
    right: dict[str, PredicateLabel],
    rng: random.Random,
) -> str:
    """Return 'left', 'right', or '' when orders disagree / still inconsistent."""

    left_map = _truth_map(predicates, left)
    right_map = _truth_map(predicates, right)
    swapped = rng.random() < 0.5

    def run(first: dict[str, str], second: dict[str, str]) -> str:
        return _ask_pair(caller, predicates, document, first, second)

    a, b = (right_map, left_map) if swapped else (left_map, right_map)
    first = run(a, b)
    second = run(b, a)

    def decode(winner: str, first_is_left: bool) -> str:
        if winner == "A":
            return "left" if first_is_left else "right"
        if winner == "B":
            return "right" if first_is_left else "left"
        return ""

    first_is_left = not swapped
    pick1 = decode(first, first_is_left)
    pick2 = decode(second, not first_is_left)
    if pick1 and pick1 == pick2:
        return pick1
    try:
        third = run(a, b)
    except (BudgetExhausted, Exception):
        return ""
    pick3 = decode(third, first_is_left)
    if pick3 and pick3 in {pick1, pick2}:
        return pick3
    if pick3 and not pick1 and not pick2:
        return pick3
    return ""


def select_plan(
    plans: list[CandidatePlan],
    sample: list[dict[str, Any]],
    results: list[list[dict[str, PredicateLabel]]],
    predicates: list[AtomicPredicate],
    caller: BudgetedCaller,
    cache: ResponseCache,
    stats: CandidateReport,
) -> CandidatePlan | None:
    if not plans or not sample:
        return None
    members = [pred for pred in predicates if is_membership(pred)]
    existence = [pred for pred in predicates if is_presence(pred)]
    rng = random.Random(42)
    bound = caller if isinstance(caller, CachedCaller) else CachedCaller(caller, cache, plan="validator")
    wins = [0] * len(plans)
    if existence:
        for index, _plan in enumerate(plans):
            for row, labels in zip(sample, results[index]):
                for pred in existence:
                    lab = labels.get(pred.pred_id)
                    if lab is None:
                        continue
                    stats.grounded_n += 1
                    if grounded_ok(lab) and verify_span(lab, row.get("document") or ""):
                        stats.grounded_ok += 1
    if not members:
        rates = []
        for index, _plan in enumerate(plans):
            ok = 0
            n = 0
            for row, labels in zip(sample, results[index]):
                for pred in existence:
                    lab = labels.get(pred.pred_id)
                    if lab is None:
                        continue
                    n += 1
                    if grounded_ok(lab) and verify_span(lab, row.get("document") or ""):
                        ok += 1
            rates.append((ok, n))
        best = max(range(len(plans)), key=lambda i: (rates[i][0], rates[i][0] / rates[i][1] if rates[i][1] else 0))
        if rates[best][0] < 2:
            return None
        return plans[best]
    compare_preds = members
    for i in range(len(plans)):
        for j in range(i + 1, len(plans)):
            for row, left, right in zip(sample, results[i], results[j]):
                stats.validator_calls += 1
                try:
                    pref = prefer_pair(bound, compare_preds, row.get("document") or "", left, right, rng)
                except (BudgetExhausted, Exception):
                    stats.validator_tie += 1
                    continue
                if pref == "left":
                    wins[i] += 1
                    stats.validator_agree += 1
                elif pref == "right":
                    wins[j] += 1
                    stats.validator_agree += 1
                else:
                    stats.validator_tie += 1
    best = max(range(len(plans)), key=lambda i: wins[i])
    fb_wins = 0
    fb_loss = 0
    for row, labels in zip(sample, results[best]):
        stats.validator_calls += 1
        fallback = row.get("labels") or {}
        try:
            pref = prefer_pair(bound, compare_preds, row.get("document") or "", labels, fallback, rng)
        except (BudgetExhausted, Exception):
            stats.validator_tie += 1
            continue
        if pref == "left":
            fb_wins += 1
            stats.validator_agree += 1
        elif pref == "right":
            fb_loss += 1
            stats.validator_agree += 1
        else:
            stats.validator_tie += 1
    if fb_wins < fb_loss + 2 or wins[best] <= 0:
        return None
    return plans[best]


def _query_cards(
    sqlite_path: str | Path,
    statements: dict[str, str],
    predicates: list[AtomicPredicate],
) -> dict[str, dict[str, Any]]:
    conn = sqlite3.connect(str(sqlite_path))
    cards: dict[str, dict[str, Any]] = {}
    try:
        for qid, sql in statements.items():
            rewritten = rewrite_sql(sql, predicates)
            try:
                n = len(conn.execute(rewritten).fetchall())
            except sqlite3.Error:
                n = None
            cards[qid] = {
                "n": n,
                "empty": n == 0 if n is not None else None,
                "join": "join" in sql.lower(),
                "join_yield": n if n is not None and "join" in sql.lower() else None,
            }
    finally:
        conn.close()
    return cards


def _allowed(plan: CandidatePlan, scoped: list[AtomicPredicate]) -> set[str]:
    wanted = set(plan.predicate_ids)
    if plan.operator == "grounded_existence":
        return {pred.pred_id for pred in scoped if is_presence(pred) and (not wanted or pred.pred_id in wanted)}
    if plan.operator == "semantic_membership":
        return {pred.pred_id for pred in scoped if is_membership(pred) and (not wanted or pred.pred_id in wanted)}
    return set()


def _write_plan(
    sqlite_path: str | Path,
    plan: CandidatePlan,
    predicates: list[AtomicPredicate],
    documents: dict[str, str],
    caller: BudgetedCaller,
    cache: ResponseCache,
) -> tuple[int, int, int, int]:
    scoped = [pred for pred in predicates if pred.attribute == plan.attribute]
    allowed = _allowed(plan, scoped)
    n_true = n_false = n_null = n_conflict = 0
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        existing = ensure_signature_columns(conn, predicates)
        rows = _load_attr_rows(conn, scoped, documents)
        bound = CachedCaller(caller, cache, plan=plan.strategy)
        for row in rows:
            incoming = execute_plan_row(plan, row, scoped, bound, cache)
            merged = merge_atoms(row["labels"], incoming, allowed)
            merged, _ = _close_labels(merged, scoped)
            _write_row(conn, row["table"], row["rowid"], scoped, merged, existing.get(row["table"], set()))
            for pred in scoped:
                lab = merged.get(pred.pred_id)
                if lab is None or not is_label_resolved(lab) or lab.sql_truth == "NULL":
                    if pred.pred_id in incoming:
                        n_null += 1
                elif lab.sql_truth == "TRUE":
                    n_true += 1
                elif lab.sql_truth == "FALSE":
                    n_false += 1
                if lab is not None and lab.conflict:
                    n_conflict += 1
        conn.commit()
    finally:
        conn.close()
    return n_true, n_false, n_null, n_conflict


def count_resolved(sqlite_path: str | Path, predicates: list[AtomicPredicate]) -> dict[str, int]:
    conn = sqlite3.connect(str(sqlite_path))
    counts = {"true": 0, "false": 0, "null": 0, "unresolved": 0}
    try:
        ensure_signature_columns(conn, predicates)
        for pred in predicates:
            table = resolve_table(conn, pred)
            if table is None:
                continue
            try:
                rows = conn.execute(
                    f"SELECT {_quote(pred.sig_name)}, {_quote(pred.resolved_name)} FROM {_quote(table)}"
                ).fetchall()
            except sqlite3.Error:
                continue
            for truth, resolved in rows:
                if int(resolved or 0) != 1:
                    counts["unresolved"] += 1
                elif truth == 1:
                    counts["true"] += 1
                elif truth == 0:
                    counts["false"] += 1
                else:
                    counts["null"] += 1
    finally:
        conn.close()
    return counts


def run_candidate_arm(
    sqlite_path: str | Path,
    predicates: Iterable[AtomicPredicate],
    *,
    documents: list[SourceDocument] | dict[str, str] | None = None,
    caller: BudgetedCaller | None = None,
    workload: Workload | None = None,
    statements: dict[str, str] | None = None,
    max_cohorts: int = 20,
) -> CandidateReport:
    live = list(predicates)
    texts = _documents(documents)
    cache = ResponseCache()
    report = CandidateReport()
    if caller is None:
        return report
    statements = statements or {}
    seen: set[str] = set()
    for _ in range(max_cohorts):
        if caller.ledger.remaining() <= 0:
            break
        observation = observe(
            sqlite_path, live, workload, documents, None, statements, caller.ledger,
        )
        ranked = [item for item in rank_cohorts(observation) if item["attribute"] not in seen]
        if not ranked:
            break
        cohort = ranked[0]
        cohort["remaining"] = caller.ledger.remaining()
        seen.add(cohort["attribute"])
        report.n_cohorts_attempted += 1
        default_op = (
            "grounded_existence"
            if int(cohort.get("unresolved_presence") or 0) >= int(cohort.get("unresolved_membership") or 0)
            else "semantic_membership"
        )
        print(
            f"candidate cohort {cohort['attribute']} priority={cohort['_priority']:.2f} remaining={caller.ledger.remaining()}",
            flush=True,
        )
        try:
            plans = plan_candidates(caller, cache, cohort, default_op, report.prior_feedback)
        except BudgetExhausted:
            break
        if all(plan.operator == "abstain" for plan in plans):
            continue
        conn = sqlite3.connect(str(sqlite_path))
        conn.row_factory = sqlite3.Row
        try:
            ensure_signature_columns(conn, live)
            scoped = [pred for pred in live if pred.attribute == cohort["attribute"]]
            rows = _load_attr_rows(conn, scoped, texts)
            conn.commit()
        finally:
            conn.close()
        sample = stratify_sample(rows)
        results: list[list[dict[str, PredicateLabel]]] = []
        try:
            for plan in plans:
                if plan.operator == "abstain":
                    results.append([{} for _ in sample])
                    continue
                results.append([execute_plan_row(plan, row, scoped, caller, cache) for row in sample])
            winner = select_plan(plans, sample, results, scoped, caller, cache, report)
        except BudgetExhausted:
            break
        if winner is None or winner.operator == "abstain":
            report.prior_feedback.append(
                {
                    "attribute": cohort["attribute"],
                    "accepted": False,
                    "reason": "inconclusive_or_abstain",
                    "remaining": caller.ledger.remaining(),
                }
            )
            continue
        before = _query_cards(sqlite_path, statements, live) if statements else {}
        spent0 = caller.ledger.spent
        try:
            n_true, n_false, n_null, n_conflict = _write_plan(
                sqlite_path, winner, live, texts, caller, cache,
            )
        except BudgetExhausted:
            break
        after = _query_cards(sqlite_path, statements, live) if statements else {}
        empty_conn = sqlite3.connect(str(sqlite_path))
        try:
            empty_rate = _empty_rate(empty_conn, statements, live) if statements else None
        finally:
            empty_conn.close()
        report.n_cohorts_accepted += 1
        report.n_true += n_true
        report.n_false += n_false
        report.n_null += n_null
        report.n_conflicts += n_conflict
        deltas = []
        join_changes = []
        for qid, card in after.items():
            prev = before.get(qid) or {}
            if prev.get("n") != card.get("n"):
                item = {
                    "query_id": qid,
                    "before": prev.get("n"),
                    "after": card.get("n"),
                    "empty_before": prev.get("empty"),
                    "empty_after": card.get("empty"),
                    "join_yield_before": prev.get("join_yield"),
                    "join_yield_after": card.get("join_yield"),
                }
                deltas.append(item)
                if card.get("join") or prev.get("join"):
                    join_changes.append(item)
        feedback = {
            "accepted": True,
            "plan": winner.as_json(),
            "resolution": {"true": n_true, "false": n_false, "null": n_null},
            "conflicts": n_conflict,
            "empty_rate": empty_rate,
            "cardinality_changes": len(deltas),
            "join_yield_changes": len(join_changes),
            "tokens": caller.ledger.spent - spent0,
            "remaining": caller.ledger.remaining(),
        }
        report.accepted.append({"plan": winner.as_json(), "query_deltas": deltas, **feedback})
        report.query_deltas.extend(
            {"plan": winner.strategy, "attribute": winner.attribute, **item} for item in deltas
        )
        report.prior_feedback.append(feedback)
        print(
            f"accepted {winner.strategy} {winner.operator} {winner.attribute} "
            f"true={n_true} false={n_false} null={n_null} deltas={len(deltas)}",
            flush=True,
        )
    report.tokens_spent = caller.ledger.spent
    report.tokens_planner = sum(rec.tokens for rec in caller.ledger.records if rec.purpose == "sig_planner")
    report.tokens_executor = sum(
        rec.tokens
        for rec in caller.ledger.records
        if rec.purpose in {"sig_executor", "sig_nonempty", "sig_membership"}
    )
    report.tokens_refiner = sum(rec.tokens for rec in caller.ledger.records if rec.purpose == "sig_refiner")
    report.tokens_validator = sum(rec.tokens for rec in caller.ledger.records if rec.purpose == "sig_validator")
    report.cache_hits = cache.hits
    report.cache_misses = cache.misses
    return report
