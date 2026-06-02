from __future__ import annotations

from collections import defaultdict

import numpy as np


def fit_btl(
    comparisons: list[dict],
    *,
    all_config_ids: list[str] | None = None,
    max_iter: int = 200,
    tol: float = 1e-9,
) -> dict[str, float]:
    """
    Bradley-Terry-Luce via MM updates.

    Input comparisons: [{"winner": config_id_1, "loser": config_id_2}]
    Ties are skipped for the pilot.
    """
    players_set: set[str] = set(all_config_ids or [])
    for comp in comparisons:
        if comp.get("winner"):
            players_set.add(comp["winner"])
        if comp.get("loser"):
            players_set.add(comp["loser"])

    if not players_set:
        return {}

    players = sorted(players_set)
    index = {pid: i for i, pid in enumerate(players)}
    n = len(players)

    wins = np.zeros(n, dtype=float)
    n_ij = np.zeros((n, n), dtype=float)

    for comp in comparisons:
        winner = comp.get("winner")
        loser = comp.get("loser")
        if not winner or not loser or winner == loser:
            continue
        if winner not in index or loser not in index:
            continue
        wi, li = index[winner], index[loser]
        wins[wi] += 1.0
        n_ij[wi, li] += 1.0
        n_ij[li, wi] += 1.0

    scores = np.ones(n, dtype=float)
    for _ in range(max_iter):
        new_scores = np.zeros(n, dtype=float)
        for i in range(n):
            denom = 0.0
            for j in range(n):
                if i == j or n_ij[i, j] == 0:
                    continue
                denom += n_ij[i, j] / (scores[i] + scores[j])
            if wins[i] > 0 and denom > 0:
                new_scores[i] = wins[i] / denom
            elif wins[i] == 0:
                new_scores[i] = max(scores[i] * 0.25, 1e-6)
            else:
                new_scores[i] = scores[i]

        if new_scores.sum() <= 0:
            new_scores = np.ones(n, dtype=float)
        new_scores = new_scores / new_scores.sum() * n

        if np.max(np.abs(new_scores - scores)) < tol:
            scores = new_scores
            break
        scores = new_scores

    return {players[i]: float(scores[i]) for i in range(n)}
