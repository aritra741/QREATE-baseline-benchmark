from __future__ import annotations

import dataclasses
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


def _score_spread(scores: dict[str, float]) -> float:
    if len(scores) < 2:
        return 0.0
    vals = list(scores.values())
    return float(max(vals) - min(vals))


def _compute_loo_rhos(probe_data) -> dict[str, float]:
    """Compute LOO Spearman ρ for every surrogate using ONLY deployment-visible
    probe signals (glass-box composites and BTL scores).  No ground-truth
    query error is accessed here.

    For each surrogate we hold out one probed config at a time, fit on the
    rest, predict the held-out config's score, then correlate predicted scores
    with BTL scores across all hold-outs (BTL is cheap: produced by the LLM
    judge during probing, not from query evaluation).

    Returns {surrogate_name: spearman_rho}.
    """
    from scipy.stats import spearmanr
    from surrogates.registry import ALL_SURROGATES

    config_ids = list(probe_data.config_ids)
    if len(config_ids) < 3:
        # Not enough probed configs for meaningful LOO
        logger.warning("Too few probed configs (%d) for LOO; returning zeros", len(config_ids))
        return {name: 0.0 for name in ALL_SURROGATES if name != "random_ranking"}

    btl = probe_data.btl_scores

    results: dict[str, float] = {}
    for surrogate_name in ALL_SURROGATES:
        if surrogate_name == "random_ranking":
            continue
        predicted: list[float] = []
        reference: list[float] = []
        for held_out in config_ids:
            remaining = [c for c in config_ids if c != held_out]
            # Build a reduced ProbeData without touching ground-truth fields
            reduced = dataclasses.replace(
                probe_data,
                config_ids=remaining,
                configs={c: probe_data.configs[c] for c in remaining},
                glass_box_composites={c: probe_data.glass_box_composites[c] for c in remaining},
                btl_scores={c: btl[c] for c in remaining if c in btl},
                tier1_signals={c: probe_data.tier1_signals.get(c, {}) for c in remaining},
                pairwise_comparisons=[
                    p for p in probe_data.pairwise_comparisons
                    if p.get("winner") != held_out and p.get("loser") != held_out
                ],
                databases={c: probe_data.databases.get(c, {}) for c in remaining},
                # explicitly zero out any true_errors to ensure no leakage
                true_errors={},
            )
            try:
                from surrogates.registry import build_surrogate
                s = build_surrogate(surrogate_name, seed=42)
                s.fit(reduced)
                predicted.append(s.score(held_out))
                reference.append(btl.get(held_out, 0.0))
            except Exception:
                predicted.append(0.0)
                reference.append(btl.get(held_out, 0.0))

        if len(set(reference)) < 2 or len(set(predicted)) < 2:
            results[surrogate_name] = 0.0
        else:
            rho, _ = spearmanr(predicted, reference)
            results[surrogate_name] = float(rho) if rho == rho else 0.0  # guard NaN

    logger.info("LOO Spearman ρ by surrogate: %s",
                {k: f"{v:.3f}" for k, v in sorted(results.items(), key=lambda x: -x[1])})
    return results


def simulate_routing(surrogate_rhos: dict[str, float], tc: ThresholdConfig) -> float:
    """Given precomputed LOO Spearman ρ values (deployment-visible, no ground
    truth), return ρ-space regret of the surrogate selected by *tc* thresholds.

    Routing logic (mirrors Stage 1E → Stage 2 handoff in full_pipeline):
    - Surrogates with ρ >= rho_viable are "viable"; pick the best among them.
    - Surrogates with rho_bakeoff <= ρ < rho_viable trigger a bakeoff; pick best.
    - Otherwise fall back to direct_probe_ranking.

    Regret = best_ρ − selected_ρ  (both deployment-visible, range [0, 1]).
    """
    if not surrogate_rhos:
        return 1.0

    best_rho = max(surrogate_rhos.values())

    viable = {k: v for k, v in surrogate_rhos.items() if v >= tc.rho_viable}
    bakeoff = {k: v for k, v in surrogate_rhos.items()
               if tc.rho_bakeoff <= v < tc.rho_viable}

    if viable:
        selected_rho = max(viable.values())
    elif bakeoff:
        selected_rho = max(bakeoff.values())
    else:
        selected_rho = surrogate_rhos.get("direct_probe_ranking", 0.0)

    return float(best_rho - selected_rho)  # minimize → maximise selected ρ


def optimize_thresholds(
    probe_data,
    *,
    n_trials: int = 100,
    seed: int = 42,
    save_path: Path | None = None,
) -> ThresholdConfig:
    """Find ThresholdConfig that minimises ρ-space routing regret.

    Inputs are deployment-visible only: probe_data carries glass-box composites
    and BTL scores from the LLM judge — no ground-truth query error is used.
    """
    # Precompute LOO ρ once (expensive); threshold optimisation reuses the cache.
    logger.info("Starting threshold optimisation n_trials=%d seed=%d", n_trials, seed)
    surrogate_rhos = _compute_loo_rhos(probe_data)

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="minimize", sampler=sampler)

    def objective(trial: optuna.Trial) -> float:
        tc = _build_tc_from_trial(trial)
        return simulate_routing(surrogate_rhos, tc)

    study.optimize(objective, n_trials=n_trials)

    best = study.best_params
    logger.info("Best trial rho_regret=%.6f params=%s", study.best_value, best)
    tc = ThresholdConfig(**{k: best[k] for k in THRESHOLD_SEARCH_SPACES})

    if save_path is not None:
        save_thresholds(tc, save_path)

    return tc
