"""Uncertainty-triggered cell adjudication. Compiler prompts and executor stay unchanged."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from quwarts.core.amortized_select.features import annotate_candidate, scope_role
from quwarts.core.amortized_select.prompt import assemble_tools
from quwarts.core.candidate_select.candidates import _header_scale

ADJUDICATE_SCHEMA = {"candidate_id": "str"}
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
ROLE_WEIGHT = {
    "WHERE": 3,
    "JOIN": 3,
    "HAVING": 3,
    "CASE": 2,
    "GROUP BY": 2,
    "aggregate input": 2,
}
QUERY_ID_RE = re.compile(r"finan_[a-z0-9]+:q\d+", re.I)


def _clip(text: Any, limit: int = 120) -> str:
    body = " ".join(str(text or "").split())
    return body if len(body) <= limit else body[: limit - 1].rstrip() + "…"


def _id_key(cid: str) -> tuple[int, str]:
    digits = "".join(ch for ch in str(cid) if ch.isdigit())
    return (int(digits) if digits else 10**9, str(cid))


def local_context(text: str, start: int, end: int, window: int = 160) -> str:
    lo = max(0, int(start) - window)
    hi = min(len(text or ""), max(int(start), int(end)) + window)
    return _clip((text or "")[lo:hi], 280)


def detect_scale(*parts: str) -> str:
    blob = " ".join(part for part in parts if part)
    name, factor = _header_scale(blob)
    if name:
        return name
    return "ones" if factor == 1 else str(factor)


def document_period(text: str, candidates: list[dict[str, Any]]) -> str:
    header_years = YEAR.findall((text or "")[:2000])
    if header_years:
        return max(header_years)
    found = [str(item.get("period") or "") for item in candidates if item.get("period")]
    return max(found) if found else ""


def classify_votes(replica_rows: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for rows in replica_rows:
        for row in rows:
            by_key.setdefault((row["entity_id"], row["attribute"]), []).append(row)
    out = []
    for key, votes in sorted(by_key.items()):
        chosen: list[str | None] = []
        for row in votes:
            ids = [item for item in (row.get("used_ids") or row.get("candidate_ids") or []) if item]
            if row.get("status") == "selected" and ids and row.get("accepted") not in (None, "", -1, "-1"):
                chosen.append(str(ids[0]))
            else:
                chosen.append(None)
        counts = Counter(item for item in chosen if item)
        winner = None
        cohort = "all_abstain"
        if not counts:
            cohort = "all_abstain"
        else:
            top, n = counts.most_common(1)[0]
            selected_n = sum(item is not None for item in chosen)
            if n >= 2:
                winner = top
                cohort = "unanimous_3" if n == 3 else "majority_2"
            elif selected_n == 1:
                cohort = "singleton"
            else:
                cohort = "conflict"
        out.append(
            {
                "entity_id": key[0],
                "attribute": key[1],
                "document_id": votes[0]["document_id"],
                "votes": chosen,
                "winner_id": winner,
                "cohort": cohort,
                "status": "selected" if winner else "abstain",
            }
        )
    return out


def proposed_ids(row: dict[str, Any]) -> list[str]:
    return sorted({item for item in row.get("votes") or [] if item}, key=_id_key)


def unproposed_ids(inventory_row: dict[str, Any], taken: set[str], limit: int = 2) -> list[str]:
    ranked = sorted(
        [item for item in inventory_row.get("candidates") or [] if item.get("id") and item.get("id") not in taken],
        key=lambda item: (-float(item.get("score") or 0.0), int(item.get("start") or 0), str(item.get("id"))),
    )
    return [str(item["id"]) for item in ranked[:limit]]


def candidate_card_line(item: dict[str, Any], feat: dict[str, Any], source_text: str) -> str:
    scale = detect_scale(str(item.get("unit") or ""), str(item.get("column_header") or ""), str(item.get("table_title") or ""), str(item.get("row_label") or ""))
    context = local_context(source_text, int(item.get("start") or 0), int(item.get("end") or 0))
    return (
        f"{item.get('id')}: surface={_clip(item.get('raw_span'), 80)}; "
        f"normalized={item.get('normalized')}; period={item.get('period') or 'unknown'}; "
        f"unit={item.get('unit') or 'unknown'}; scale={scale}; "
        f"scope={feat.get('scope_role') or scope_role(str(item.get('row_label') or ''), str(item.get('column_header') or ''), str(item.get('table_title') or ''), str(item.get('heading') or ''))}; "
        f"row={_clip(item.get('row_label'), 80)}; col={_clip(item.get('column_header'), 80)}; "
        f"title={_clip(item.get('table_title'), 80)}; section={_clip(item.get('heading'), 80)}; "
        f"source={feat.get('source_type') or item.get('kind')}; "
        f"offsets={item.get('start')}-{item.get('end')}; context={context}"
    )


def build_card(
    row: dict[str, Any],
    spec: Any,
    inventory_row: dict[str, Any],
    feats: list[dict[str, Any]],
    source_text: str,
) -> dict[str, Any]:
    by_id = {str(item.get("id")): item for item in inventory_row.get("candidates") or []}
    feat_by = {str(item.get("id")): item for item in feats}
    taken = set(proposed_ids(row))
    extras = unproposed_ids(inventory_row, taken, 2)
    listed = [cid for cid in proposed_ids(row) + extras if cid in by_id]
    period = document_period(source_text, inventory_row.get("candidates") or [])
    lines = []
    if listed:
        lines.append("Candidates:")
        for cid in listed:
            item = by_id[cid]
            feat = feat_by.get(cid) or annotate_candidate(item, set(), len(source_text or ""), 1)
            lines.append(candidate_card_line(item, feat, source_text))
    else:
        lines.append("Candidates: (none)")
    lines.append("NONE")
    body = (
        f"Attribute: {spec.name}\n"
        f"Official description: {spec.official_description}\n"
        f"Expected type: {spec.dtype} ({spec.sql_type})\n"
        f"Entity: {row['entity_id']}\n"
        f"Document: {row['document_id']}\n"
        f"Document period: {period or 'unknown'}\n"
        + "\n".join(lines)
    )
    return {
        "entity_id": row["entity_id"],
        "attribute": row["attribute"],
        "document_id": row["document_id"],
        "cohort": row["cohort"],
        "listed_ids": listed,
        "proposed_ids": proposed_ids(row),
        "alternative_ids": extras,
        "document_period": period,
        "body": body,
        "allowed": listed + ["NONE"],
    }


PRIMARY_INSTRUCTION = (
    "Select the single listed candidate ID that is the requested attribute value, or NONE.\n"
    "Output only one listed ID or NONE. Do not emit a numeric or text value.\n"
    "Distinguish a consolidated total from a component; the current reporting period from a "
    "comparative or historical period; a reported value from a threshold, example, page number, "
    "or narrative reference; a company-wide value from a segment-level value; and a normalized "
    "value from its displayed unit and scale.\n"
    "Choose NONE when the evidence does not determine the requested attribute.\n"
    "The listed order is arbitrary. Do not infer votes or compiler identities.\n"
)


VERIFY_INSTRUCTION = (
    "Re-evaluate this cell independently. Return exactly one listed identifier, or NONE if the "
    "document does not establish the attribute.\n"
    "The options are listed in reverse order; ignore position. Do not copy a previous answer.\n"
    "Prefer a period-end consolidated figure over a prior-year, segment, or component figure. "
    "Reject page numbers, examples, covenants, and narrative mentions that are not the attribute.\n"
    "Treat unit and scale as metadata, not as a reason to invent a new number.\n"
    "If two options remain equally plausible, return NONE.\n"
)


def primary_user(card: dict[str, Any]) -> str:
    return PRIMARY_INSTRUCTION + "\n" + card["body"]


def verify_user(card: dict[str, Any], inventory_row: dict[str, Any], feats: list[dict[str, Any]], source_text: str) -> str:
    by_id = {str(item.get("id")): item for item in inventory_row.get("candidates") or []}
    feat_by = {str(item.get("id")): item for item in feats}
    header = card["body"].split("Candidates:")[0].rstrip()
    lines = [header, "Candidates (reversed):"]
    for cid in reversed(card["listed_ids"]):
        item = by_id.get(cid)
        if item is None:
            continue
        feat = feat_by.get(cid) or annotate_candidate(item, set(), len(source_text or ""), 1)
        lines.append(candidate_card_line(item, feat, source_text))
    lines.append("NONE")
    return VERIFY_INSTRUCTION + "\n" + "\n".join(lines)


def repair_user(raw: str, allowed: list[str]) -> str:
    return (
        "Repair the response so it is exactly one allowed identifier.\n"
        f"Allowed: {', '.join(allowed)}\n"
        "Output only the identifier. No explanation.\n"
        f"Malformed output:\n{(raw or '')[:500]}"
    )


def assemble_adjudicate(user: str) -> dict[str, Any]:
    return assemble_tools(ADJUDICATE_SCHEMA, user)


def parse_choice(parsed: dict[str, Any], allowed: list[str]) -> str:
    raw = parsed.get("candidate_id")
    if raw is None:
        raw = parsed.get("id") or parsed.get("choice")
    token = str(raw or "").strip()
    if token.upper() == "NONE":
        return "NONE"
    allowed_set = {str(item) for item in allowed}
    if token in allowed_set and token != "NONE":
        return token
    return "NONE"


def sql_amplification(record: Any) -> int:
    roles = getattr(record, "roles", {}) or {}
    weighted = sum(ROLE_WEIGHT.get(str(role), 1) * int(count) for role, count in roles.items())
    return max(1, weighted or int(getattr(record, "n_expressions", 0) or getattr(record, "n_queries", 1) or 1))


def annotate_schedule(card: dict[str, Any], record: Any, primary_reserved: int, verify_reserved: int) -> dict[str, Any]:
    estimated = primary_reserved + verify_reserved
    occurrence = int(getattr(record, "occurrence_count", 0) or record.n_queries)
    amp = sql_amplification(record)
    return {
        **card,
        "primary_reserved": primary_reserved,
        "verify_reserved": verify_reserved,
        "estimated_cost": estimated,
        "occurrence": occurrence,
        "amplification": amp,
        "priority": (occurrence * amp) / max(estimated, 1),
    }


def sort_disputes(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(cards, key=lambda item: (-float(item["priority"]), item["entity_id"], item["attribute"]))


def card_has_query_literals(card: dict[str, Any], records: dict[str, Any]) -> bool:
    blob = card["body"]
    if QUERY_ID_RE.search(blob):
        return True
    if re.search(r"\b(SELECT|GROUP BY|CASE WHEN|LEFT JOIN)\b", blob):
        return True
    rec = records.get(card["attribute"])
    if rec is None:
        return False
    header = card["body"].split("Candidates:")[0]
    official = f"{card['attribute']} {header}"
    for token in list(getattr(rec, "predicate_literals", []) or []):
        text = str(token or "").strip()
        if text and text in header and text not in official:
            return True
    return False
