from __future__ import annotations

import itertools
import random

import numpy as np

from optimizer.config_space import PopulationConfig, encode_config_features


def _connectivity_backbone(config_ids: list[str], configs: dict[str, PopulationConfig]) -> list[tuple[str, str]]:
    """Build a spanning tree so every config appears in at least one comparison."""
    if len(config_ids) <= 1:
        return []

    features = {cid: encode_config_features(configs[cid]) for cid in config_ids}
    remaining = list(config_ids[1:])
    connected = [config_ids[0]]
    backbone: list[tuple[str, str]] = []

    while remaining:
        best_pair: tuple[str, str] | None = None
        best_dist = -1.0
        for a in connected:
            for b in remaining:
                dist = float(np.linalg.norm(features[a] - features[b]))
                if dist > best_dist:
                    best_dist = dist
                    best_pair = (a, b)
        if best_pair is None:
            break
        backbone.append(best_pair)
        connected.append(best_pair[1])
        remaining.remove(best_pair[1])

    return backbone


def select_diverse_pairs(
    config_ids: list[str],
    configs: dict[str, PopulationConfig],
    budget: int,
    *,
    seed: int = 42,
) -> list[tuple[str, str]]:
    if len(config_ids) < 2:
        return []

    rng = random.Random(seed)
    all_pairs = list(itertools.combinations(sorted(config_ids), 2))
    pair_set: set[tuple[str, str]] = set()

    for pair in _connectivity_backbone(config_ids, configs):
        ordered = tuple(sorted(pair))
        pair_set.add(ordered)

    features = {cid: encode_config_features(configs[cid]) for cid in config_ids}
    covered = set()
    for a, b in pair_set:
        covered.add(a)
        covered.add(b)

    scored_pairs: list[tuple[float, tuple[str, str]]] = []
    for a, b in all_pairs:
        dist = float(np.linalg.norm(features[a] - features[b]))
        novelty = (0 if a in covered else 1) + (0 if b in covered else 1)
        scored_pairs.append((novelty * 10 + dist, (a, b)))

    scored_pairs.sort(reverse=True)
    for _, pair in scored_pairs:
        if len(pair_set) >= budget:
            break
        pair_set.add(pair)
        covered.add(pair[0])
        covered.add(pair[1])

    if len(pair_set) < budget:
        remaining = [p for p in all_pairs if p not in pair_set]
        rng.shuffle(remaining)
        for pair in remaining:
            if len(pair_set) >= budget:
                break
            pair_set.add(pair)

    selected = list(pair_set)
    rng.shuffle(selected)
    return selected[:budget]
