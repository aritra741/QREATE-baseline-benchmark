"""Attribute micro-bundles: one to three attributes that share context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from quwarts.core.retrieve_extract.config import FROZEN
from quwarts.core.retrieve_extract.retrieve import Hit


@dataclass
class Bundle:
    attributes: list[str]
    mode: str
    hits: list[Hit]
    priority: float


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _sources(hits: list[Hit]) -> set[str]:
    return {hit.chunk.source_id for hit in hits}


def pack_bundles(
    attributes: list[str],
    mode_by_attr: dict[str, str],
    hits_by_attr: dict[str, list[Hit]],
    priority_by_attr: dict[str, float],
) -> list[Bundle]:
    max_size = int(FROZEN["max_bundle_size"])
    threshold = float(FROZEN["bundle_jaccard"])
    remaining = [name for name in attributes if name in mode_by_attr]
    remaining.sort(key=lambda name: (-priority_by_attr.get(name, 0.0), name))
    bundles: list[Bundle] = []
    while remaining:
        seed = remaining.pop(0)
        mode = mode_by_attr[seed]
        group = [seed]
        seed_src = _sources(hits_by_attr.get(seed, []))
        if mode == "whole_document":
            for name in list(remaining):
                if mode_by_attr.get(name) != mode:
                    continue
                group.append(name)
                remaining.remove(name)
                if len(group) >= max_size:
                    break
        else:
            for name in list(remaining):
                if mode_by_attr.get(name) != mode:
                    continue
                other = _sources(hits_by_attr.get(name, []))
                if _jaccard(seed_src, other) < threshold:
                    continue
                group.append(name)
                remaining.remove(name)
                seed_src |= other
                if len(group) >= max_size:
                    break
        hits: list[Hit] = []
        seen: set[str] = set()
        for name in group:
            for hit in hits_by_attr.get(name, []):
                if hit.chunk.source_id in seen:
                    continue
                seen.add(hit.chunk.source_id)
                hits.append(hit)
        hits.sort(key=lambda item: (-item.score, item.chunk.start))
        bundles.append(
            Bundle(
                attributes=group,
                mode=mode,
                hits=hits,
                priority=sum(priority_by_attr.get(name, 0.0) for name in group),
            )
        )
    return bundles


def split_if_over_cap(bundle: Bundle, packed_tokens: int, cap: int) -> list[list[str]]:
    if packed_tokens <= cap or len(bundle.attributes) <= 1:
        return [list(bundle.attributes)]
    return [[name] for name in bundle.attributes]


def singleton_bundles(attributes: Iterable[str], mode: str, hits_by_attr: dict[str, list[Hit]]) -> list[Bundle]:
    return [
        Bundle(attributes=[name], mode=mode, hits=list(hits_by_attr.get(name, [])), priority=0.0)
        for name in attributes
    ]
