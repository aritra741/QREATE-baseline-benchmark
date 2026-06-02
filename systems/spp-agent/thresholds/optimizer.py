from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import optuna

from thresholds.schema import THRESHOLD_SEARCH_SPACES, ThresholdConfig, save_thresholds
from utils.logging import setup_logger

logger = setup_logger("spp.thresholds.optimizer")


def _build_tc_from_trial(trial: optuna.Trial) -> ThresholdConfig:
    kwargs: dict = {}
    for name, (kind, lo, hi) in THRESHOLD_SEARCH_SPACES.items():
        if kind == "float":
            kwargs[name] = trial.suggest_float(name, lo, hi)
        elif kind == "int":
            kwargs[name] = trial.suggest_int(name, lo, hi)
    return ThresholdConfig(**kwargs)


def simulate_routing(rows: list[dict], tc: ThresholdConfig) -> float:
    """Return mean regret when routing surrogates via *tc* thresholds.

    For each budget level the oracle picks the surrogate with minimum
    ``true_spp_error``.  The simulated router picks the *first* surrogate
    whose ``rho_signal`` (= ``1 - true_spp_error``) exceeds ``rho_viable``;
    if none qualifies but at least one exceeds ``rho_bakeoff``, it picks the
    best among those.  Otherwise it falls back to the surrogate with the
    highest rho_signal.

    Regret = selected_error − oracle_error.
    """
    by_budget: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_budget[str(row["budget"])].append(row)

    total_regret = 0.0
    n_budgets = 0
    for _budget, group in by_budget.items():
        oracle_error = min(r["true_spp_error"] for r in group)

        viable: list[dict] = []
        bakeoff: list[dict] = []
        for r in group:
            rho_signal = 1.0 - r["true_spp_error"]
            if rho_signal >= tc.rho_viable:
                viable.append(r)
            elif rho_signal >= tc.rho_bakeoff:
                bakeoff.append(r)

        if viable:
            selected = min(viable, key=lambda r: r["true_spp_error"])
        elif bakeoff:
            selected = min(bakeoff, key=lambda r: r["true_spp_error"])
        else:
            selected = max(group, key=lambda r: 1.0 - r["true_spp_error"])

        total_regret += selected["true_spp_error"] - oracle_error
        n_budgets += 1

    return total_regret / max(n_budgets, 1)


def optimize_thresholds(
    reward_rows: list[dict],
    *,
    n_trials: int = 100,
    seed: int = 42,
    save_path: Path | None = None,
) -> ThresholdConfig:
    """Find ThresholdConfig that minimises routing regret on *reward_rows*."""
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="minimize", sampler=sampler)

    def objective(trial: optuna.Trial) -> float:
        tc = _build_tc_from_trial(trial)
        return simulate_routing(reward_rows, tc)

    logger.info("Starting threshold optimisation n_trials=%d seed=%d", n_trials, seed)
    study.optimize(objective, n_trials=n_trials)

    best = study.best_params
    logger.info("Best trial regret=%.6f params=%s", study.best_value, best)
    tc = ThresholdConfig(**{k: best[k] for k in THRESHOLD_SEARCH_SPACES})

    if save_path is not None:
        save_thresholds(tc, save_path)

    return tc
