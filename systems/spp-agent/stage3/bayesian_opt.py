from __future__ import annotations

import optuna
from surrogates.base import BaseSurrogate
from utils.logging import setup_logger

logger = setup_logger("spp.stage3.bayesian_opt")


def bayesian_opt_select(
    surrogate: BaseSurrogate,
    candidate_ids: list[str],
    budget: int,
    *,
    n_startup_trials: int = 5,
    n_trials: int = 30,
    seed: int = 42,
) -> list[str]:
    """Select *budget* configs from *candidate_ids* via Optuna TPE maximisation."""
    if len(candidate_ids) <= budget:
        return surrogate.rank(candidate_ids)[:budget]

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    n_candidates = len(candidate_ids)

    def objective(trial: optuna.Trial) -> float:
        indices: list[int] = []
        seen: set[int] = set()
        for slot in range(budget):
            idx = trial.suggest_int(f"idx_{slot}", 0, n_candidates - 1)
            if idx not in seen:
                seen.add(idx)
                indices.append(idx)
        # Fill remaining slots with first unseen indices when duplicates occur
        if len(indices) < budget:
            for i in range(n_candidates):
                if i not in seen:
                    indices.append(i)
                    seen.add(i)
                    if len(indices) >= budget:
                        break
        return sum(surrogate.score(candidate_ids[i]) for i in indices[:budget])

    sampler = optuna.samplers.TPESampler(seed=seed, n_startup_trials=n_startup_trials)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best = study.best_trial
    seen: set[int] = set()
    indices: list[int] = []
    for slot in range(budget):
        idx = best.params[f"idx_{slot}"]
        if idx not in seen:
            seen.add(idx)
            indices.append(idx)
    if len(indices) < budget:
        for i in range(n_candidates):
            if i not in seen:
                indices.append(i)
                seen.add(i)
                if len(indices) >= budget:
                    break

    selected = [candidate_ids[i] for i in indices[:budget]]
    logger.info(
        "Bayesian opt selected %d configs (trials=%d best_value=%.4f)",
        len(selected),
        n_trials,
        study.best_value,
    )
    return selected
