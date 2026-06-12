"""Low-level corpus profilers for supply_profile (no LLM, no extraction)."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from pipeline.schema import Schema

WINDOW_TOKENS = 30
_CLUSTER_THRESHOLD = 0.3
_SOFT_JOIN_THRESHOLD = 0.2

_NUMERIC_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_DATE_RE = re.compile(
    r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b|\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b"
)
_PROPER_NOUN_RE = re.compile(r"\b([A-Z][a-z]+(?:[ -][A-Z][a-z]+)*)\b")
_NATIONALITY_VALUE_RE = re.compile(
    r"\b([A-Z][a-z]+(?:-[A-Z][a-z]+)?)\s+national(?:ity)?\b", re.IGNORECASE
)
_BORN_IN_RE = re.compile(r"\bborn\s+in\s+(?:the\s+)?([^,.\n;]+)", re.IGNORECASE)
_CITIZEN_RE = re.compile(r"\bcitizen\s+of\s+([^,.\n;]+)", re.IGNORECASE)
_AGE_DIRECT_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s+years?\s+old\b", re.IGNORECASE)
_BORN_YEAR_RE = re.compile(r"\bborn\s+(?:in\s+)?(\d{4})\b", re.IGNORECASE)


@dataclass
class MentionRecord:
    doc_id: str
    window_text: str
    value_span: str
    normalized: str


@dataclass
class ColumnMentionIndex:
    mentions: list[MentionRecord] = field(default_factory=list)
    doc_ids_with_mentions: set[str] = field(default_factory=set)


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def edit_distance_ratio(a: str, b: str) -> float:
    if not a and not b:
        return 0.0
    dist = _levenshtein(a, b)
    return dist / max(len(a), len(b), 1)


def normalize_span(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> list[str]:
    return re.findall(r"\S+", text)


def _norm_token(tok: str) -> str:
    return re.sub(r"^[^\w]+|[^\w]+$", "", tok.lower())


def column_bare_name(column: str) -> str:
    return column.split(".")[-1].lower()


def column_table_name(column: str, schema: Schema) -> str | None:
    if "." in column:
        return column.split(".", 1)[0].lower()
    bare = column_bare_name(column)
    matches = [
        table.lower()
        for table, cols in schema.tables.items()
        if bare in [c.lower() for c in cols]
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def column_synonyms(column: str, schema: Schema) -> list[str]:
    bare = column_bare_name(column)
    names = {bare, column.lower()}
    for table, cols in schema.tables.items():
        for col in cols:
            if col.lower() == bare:
                names.add(f"{table}.{col}".lower())
                names.add(col.lower())
    if bare == "nationality":
        names.update({"national", "citizen", "born in", "demonym"})
    if bare in {"team", "team_name"}:
        names.update({"team", "franchise", "club"})
    if bare == "position":
        names.update({"play as", "plays as", "position"})
    if bare == "team":
        names.update({"for the", "plays for"})
    if bare == "age":
        names.update({"age", "years old", "born"})
    if bare in {"birth_date", "birth"}:
        names.update({"born", "birth", "birthday"})
    return sorted(names)


def is_string_column(column: str, schema: Schema) -> bool:
    return column_kind(column, schema) not in {"numeric", "date"}


def column_kind(column: str, schema: Schema) -> str:
    bare = column_bare_name(column)
    table = column_table_name(column, schema)
    if table and schema.column_types.get(table, {}).get(
        next((c for c in schema.tables.get(table, []) if c.lower() == bare), bare), "str"
    ) in {"int", "float", "numeric"}:
        return "numeric"
    if bare in {"nationality"} or "nationality" in bare:
        return "nationality"
    if bare in {"name", "team_name", "team", "position", "location", "ownership"}:
        return "name"
    if any(k in bare for k in ("date", "birth", "year")):
        return "date"
    return "text"


def find_mention_windows(text: str, synonyms: list[str]) -> list[str]:
    tokens = tokenize(text)
    if not tokens:
        return []
    norm_tokens = [_norm_token(t) for t in tokens]
    windows: list[str] = []
    seen_spans: set[tuple[int, int]] = set()
    for i, _tok in enumerate(norm_tokens):
        for syn in synonyms:
            syn_tokens = [_norm_token(t) for t in tokenize(syn)]
            syn_tokens = [t for t in syn_tokens if t]
            if not syn_tokens:
                continue
            n = len(syn_tokens)
            if norm_tokens[i : i + n] == syn_tokens:
                start = max(0, i - WINDOW_TOKENS)
                end = min(len(tokens), i + n + WINDOW_TOKENS)
                span = (start, end)
                if span in seen_spans:
                    break
                seen_spans.add(span)
                windows.append(" ".join(tokens[start:end]))
                break
    return windows


def extract_value_span(window: str, column: str, schema: Schema) -> str:
    kind = column_kind(column, schema)
    if kind == "nationality":
        phrase = re.search(
            r"\bA\s+(.+?)\s+national\b",
            window,
            re.IGNORECASE,
        )
        if phrase:
            return phrase.group(1).strip()
        for pat in (_NATIONALITY_VALUE_RE, _BORN_IN_RE, _CITIZEN_RE):
            m = pat.search(window)
            if m:
                return m.group(1).strip()
        nouns = _PROPER_NOUN_RE.findall(window)
        return nouns[0] if nouns else ""
    if kind == "numeric":
        m = _NUMERIC_RE.search(window)
        return m.group(0) if m else ""
    if kind == "date":
        m = _DATE_RE.search(window)
        return m.group(0) if m else ""
    if kind == "name":
        bare = column_bare_name(column)
        if bare in {"team", "team_name"}:
            m = re.search(
                r"\b(?:for|with)\s+the\s+([A-Z][^\n,.;]+?)(?:\s*\.|\s+They|\s+and\b)",
                window,
            )
            if m:
                return m.group(1).strip()
            m = re.search(
                r"\bThe\s+([A-Z][^\n]+?)\s+basketball\s+team\b",
                window,
            )
            if m:
                return m.group(1).strip()
        if bare == "position":
            m = re.search(
                r"\bplay(?:s)?\s+as\s+a\s+(Frontcourt|Backcourt)\s+for\b",
                window,
                re.IGNORECASE,
            )
            if m:
                return m.group(1).strip()
            return ""
        nouns = _PROPER_NOUN_RE.findall(window)
        return nouns[0] if nouns else ""
    bare = column_bare_name(column)
    m = re.search(rf"{re.escape(bare)}\s*[:=]?\s*([^\n,.;]+)", window, re.IGNORECASE)
    return m.group(1).strip()[:80] if m else ""


def index_column_mentions(
    corpus: list[dict],
    column: str,
    schema: Schema,
    *,
    table_filter: str | None = None,
) -> ColumnMentionIndex:
    synonyms = column_synonyms(column, schema)
    table = table_filter or column_table_name(column, schema)
    index = ColumnMentionIndex()
    for doc in corpus:
        doc_id = doc.get("doc_id", "")
        if table:
            prefix = doc_id.split("/")[0].lower() if "/" in doc_id else doc_id.split("_")[0].lower()
            hint = str(doc.get("metadata", {}).get("table_hint", "")).lower()
            if prefix != table and hint != table:
                continue
        text = doc.get("text", "")
        windows = find_mention_windows(text, synonyms)
        if not windows:
            continue
        index.doc_ids_with_mentions.add(doc_id)
        for window in windows:
            span = extract_value_span(window, column, schema)
            if not _valid_span(span):
                continue
            index.mentions.append(
                MentionRecord(
                    doc_id=doc_id,
                    window_text=window,
                    value_span=span,
                    normalized=normalize_span(span),
                )
            )
    return index


def cluster_spans(spans: list[str], threshold: float = _CLUSTER_THRESHOLD) -> list[list[str]]:
    clusters: list[list[str]] = []
    norms = [normalize_span(s) for s in spans]
    for span, norm in zip(spans, norms):
        if not norm:
            continue
        placed = False
        for cluster in clusters:
            rep_norm = normalize_span(cluster[0])
            if edit_distance_ratio(norm, rep_norm) < threshold:
                cluster.append(span)
                placed = True
                break
        if not placed:
            clusters.append([span])
    return clusters


def _valid_span(span: str) -> bool:
    norm = normalize_span(span)
    return bool(norm) and norm not in {"for", "the", "a", "an"}


def semantic_collision_rate(clusters: list[list[str]]) -> float:
    """Fraction of clusters where a rep form is a substring of another cluster's rep."""
    if len(clusters) < 2:
        return 0.0
    reps = [normalize_span(c[0]) for c in clusters if c]
    if len(reps) < 2:
        return 0.0
    colliding: set[int] = set()
    for i in range(len(reps)):
        for j in range(i + 1, len(reps)):
            a, b = reps[i], reps[j]
            if not a or not b or a == b:
                continue
            shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
            if shorter in longer:
                colliding.add(i)
                colliding.add(j)
    return round(len(colliding) / len(reps), 4)


def profile_expression_diversity(
    mentions: list[MentionRecord],
    *,
    column: str | None = None,
    schema: Schema | None = None,
) -> dict[str, Any]:
    spans = [m.value_span for m in mentions if _valid_span(m.value_span)]
    n_mentions = len(spans)
    string_typed = (
        column is not None
        and schema is not None
        and is_string_column(column, schema)
    )
    if n_mentions == 0:
        out: dict[str, Any] = {
            "n_distinct_clusters": 0,
            "n_mentions": 0,
            "diversity_ratio": 0.0,
            "example_forms": [],
        }
        if string_typed:
            out["semantic_collision_rate"] = 0.0
        return out
    clusters = cluster_spans(spans)
    examples = [c[0] for c in sorted(clusters, key=len, reverse=True)[:5]]
    n_clusters = len(clusters)
    out = {
        "n_distinct_clusters": n_clusters,
        "n_mentions": n_mentions,
        "diversity_ratio": round(n_clusters / n_mentions, 4),
        "example_forms": examples,
    }
    if string_typed:
        out["semantic_collision_rate"] = semantic_collision_rate(clusters)
    return out


def classify_derivability(
    mention: MentionRecord,
    column: str,
    schema: Schema,
) -> str:
    kind = column_kind(column, schema)
    window = mention.window_text
    norm = mention.normalized
    candidates: list[str] = []

    if kind == "nationality":
        if _NATIONALITY_VALUE_RE.search(window):
            return "direct"
        if _BORN_IN_RE.search(window) or _CITIZEN_RE.search(window):
            return "derivable"
        candidates = [normalize_span(m.group(0)) for m in _PROPER_NOUN_RE.finditer(window)]
    elif kind == "numeric" and column_bare_name(column) == "age":
        if _AGE_DIRECT_RE.search(window):
            return "direct"
        if _BORN_YEAR_RE.search(window):
            return "derivable"
        candidates = [normalize_span(m.group(0)) for m in _NUMERIC_RE.finditer(window)]
    elif kind == "name":
        candidates = [normalize_span(m.group(0)) for m in _PROPER_NOUN_RE.finditer(window)]
        if norm and any(edit_distance_ratio(norm, c) < 0.15 for c in candidates if c):
            return "direct"
    elif kind == "date":
        if _DATE_RE.search(window) and norm in normalize_span(_DATE_RE.search(window).group(0)):
            return "direct"
        if _BORN_YEAR_RE.search(window):
            return "derivable"
    else:
        bare = column_bare_name(column)
        if bare in window.lower() and norm:
            return "direct"

    candidates = [c for c in candidates if c]
    distinct = {c for c in candidates if c}
    if len(distinct) > 1 and norm in distinct:
        return "ambiguous"
    if len(distinct) > 1:
        return "ambiguous"
    if norm:
        return "direct"
    return "derivable"


def profile_derivability(mentions: list[MentionRecord], column: str, schema: Schema) -> dict[str, Any]:
    valid = [m for m in mentions if _valid_span(m.value_span)]
    if not valid:
        return {"direct_rate": 0.0, "derivable_rate": 0.0, "ambiguous_rate": 0.0}
    counts = {"direct": 0, "derivable": 0, "ambiguous": 0}
    for m in valid:
        counts[classify_derivability(m, column, schema)] += 1
    total = len(valid)
    return {
        "direct_rate": round(counts["direct"] / total, 4),
        "derivable_rate": round(counts["derivable"] / total, 4),
        "ambiguous_rate": round(counts["ambiguous"] / total, 4),
    }


def value_set_from_corpus(
    corpus: list[dict],
    column: str,
    schema: Schema,
) -> set[str]:
    idx = index_column_mentions(corpus, column, schema)
    return {m.normalized for m in idx.mentions if m.normalized}


def soft_overlap(left: set[str], right: set[str], threshold: float = _SOFT_JOIN_THRESHOLD) -> float:
    if not left and not right:
        return 0.0
    soft_matched: set[str] = set()
    for a in left:
        for b in right:
            if edit_distance_ratio(a, b) < threshold:
                soft_matched.add(a)
                soft_matched.add(b)
    union = left | right
    return len(soft_matched) / len(union) if union else 0.0


def profile_join_key_ambiguity(
    corpus: list[dict],
    column: str,
    schema: Schema,
    *,
    join_partner: str | None = None,
) -> dict[str, Any] | None:
    table = column_table_name(column, schema)
    if not table:
        return None
    idx = index_column_mentions(corpus, column, schema, table_filter=table)
    if not idx.mentions:
        return None

    by_doc: dict[str, list[str]] = defaultdict(list)
    for m in idx.mentions:
        by_doc[m.doc_id].append(m.normalized)

    variant_counts = [len(set(v for v in vals if v)) for vals in by_doc.values() if vals]
    mean_variants = sum(variant_counts) / len(variant_counts) if variant_counts else 0.0
    max_variants = max(variant_counts) if variant_counts else 0

    left_values = {m.normalized for m in idx.mentions if m.normalized}
    exact_overlap = 0.0
    soft = 0.0
    if join_partner:
        right_values = value_set_from_corpus(corpus, join_partner, schema)
        union = left_values | right_values
        exact_overlap = len(left_values & right_values) / len(union) if union else 0.0
        soft = soft_overlap(left_values, right_values)

    if soft > 0.7 and mean_variants < 2:
        feasibility = "high"
    elif soft < 0.4 or mean_variants > 4:
        feasibility = "low"
    else:
        feasibility = "moderate"

    return {
        "exact_overlap_rate": round(exact_overlap, 4),
        "soft_overlap_rate": round(soft, 4),
        "mean_variants_per_entity": round(mean_variants, 4),
        "max_variants_per_entity": int(max_variants),
        "join_feasibility": feasibility,
        "join_partner": join_partner,
    }


def infer_join_partner(column: str, demand_columns: list[dict], schema: Schema) -> str | None:
    """Find the other join_key column on the opposite table, if any."""
    if "." not in column and column_table_name(column, schema) is None:
        return None
    this_table = column_table_name(column, schema)
    join_cols = [
        c.get("column", "")
        for c in demand_columns
        if "join_key" in c.get("roles", [])
    ]
    for other in join_cols:
        if other == column:
            continue
        other_table = column_table_name(other, schema)
        if this_table and other_table and other_table != this_table:
            return other
    return None


def build_recommendations(
    *,
    expression_diversity: dict[str, Any],
    derivability: dict[str, Any],
    join_key_ambiguity: dict[str, Any] | None,
) -> dict[str, Any]:
    diversity_ratio = float(expression_diversity.get("diversity_ratio", 0.0))
    collision_rate = expression_diversity.get("semantic_collision_rate")
    derivable_rate = float(derivability.get("derivable_rate", 0.0))
    ambiguous_rate = float(derivability.get("ambiguous_rate", 0.0))

    # diversity_ratio > 0.3 or semantic_collision_rate > 0.2 → norm=llm
    norm_rec = "dictionary"
    if diversity_ratio > 0.3:
        norm_rec = "llm"
    if collision_rate is not None and float(collision_rate) > 0.2:
        norm_rec = "llm"
    # derivable_rate > 0.2 → coerce=llm (spec)
    coerce_rec = "llm" if derivable_rate > 0.2 else "strict"
    # ambiguous_rate > 0.1 → er=llm (spec)
    er_rec = "llm" if ambiguous_rate > 0.1 else "embedding"

    rec: dict[str, Any] = {
        "norm_recommendation": norm_rec,
        "coerce_recommendation": coerce_rec,
        "er_recommendation": er_rec,
    }
    if join_key_ambiguity:
        if float(join_key_ambiguity.get("mean_variants_per_entity", 0)) > 2:
            rec["er_recommendation"] = "llm"
        if join_key_ambiguity.get("join_feasibility") == "low":
            rec["feasibility_flag"] = True
    return rec
