"""Join repair from a profile. Shared canonical IDs only."""

from __future__ import annotations

from typing import Any

from quwarts.core.repair.er import align_unmatched, resolve_shared_ids, stamp_shared_ids


def referencing_side(edge: dict[str, Any]) -> tuple[str, str] | None:
    """Higher-cardinality, low-yield side is the free-form reference."""

    left, right = edge["left"], edge["right"]
    n_left = int(edge.get("n_left") or 0)
    n_right = int(edge.get("n_right") or 0)
    exact = float(edge.get("exact_yield") or 0.0)
    if exact >= 0.25:
        return None
    if n_left <= 1 or n_right <= 1:
        return None
    if n_left >= n_right:
        return left, right
    return right, left


def repair_join_edges(
    records: list,
    workload,
    caller,
    profile: list[dict[str, Any]],
    *,
    extractor=None,
    documents=None,
    logical=None,
) -> dict[str, Any]:
    shared = resolve_shared_ids(records, workload, caller)
    aligned = 0
    reextracted = 0
    for edge in profile:
        if int(edge.get("n_empty") or 0) <= 0:
            continue
        pair = referencing_side(edge)
        unmatched_left = [row["left"] for row in edge.get("unmatched_sample") or []]
        right_vals = []
        if pair is not None:
            ref, auth = pair
            if extractor is not None and documents is not None:
                extractor.constraints = {ref: auth}
                extractor.extract_attributes(
                    documents,
                    [ref],
                    {ref: "expensive"},
                    stage=3,
                    workload=workload,
                    logical=logical,
                )
                reextracted += 1
        if unmatched_left:
            right_cands = []
            for row in edge.get("unmatched_sample") or []:
                right_cands.extend(item["value"] for item in row.get("nearest") or [])
            mapping = align_unmatched(unmatched_left, right_cands or unmatched_left, caller, label="join")
            if mapping:
                maps = shared.setdefault("maps", {})
                for attr in (edge["left"], edge["right"]):
                    current = dict(maps.get(attr) or {})
                    current.update(mapping)
                    maps[attr] = current
                    maps[attr.split(".")[-1]] = current
                aligned += len(mapping)
    report = stamp_shared_ids({}, shared)
    report["n_aligned"] = aligned
    report["n_reextracted"] = reextracted
    return report
