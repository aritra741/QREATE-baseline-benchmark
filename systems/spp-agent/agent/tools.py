from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from diagnostics.tier0 import compute_tier0
from optimizer.config_space import PopulationConfig, generate_config_space
from optimizer.probing import ProbeData
from surrogates.registry import build_surrogate
from utils.config import load_config

AGENT_SURROGATE_CHOICES = [
    "direct_probe_ranking",
    "glass_box_proxy",
    "llm_judge_btl",
    "linear_proxy_glass",
    "rf_proxy_glass",
    "gbdt_proxy_glass",
    "gp_proxy_glass",
    "tpe_proxy",
]

TOOL_NAMES = [
    # Inspection tools (cheap, no ground truth)
    "get_dataset_summary",
    "get_probe_diagnostics",
    "get_btl_rankings",
    "get_surrogate_ranking",
    "compare_surrogates",
    # Pipeline orchestration tools
    "run_stage1_characterization",
    "run_surrogate_bakeoff",
    "probe_additional_configs",
    "run_pipeline_and_select",
    # Terminal action
    "commit",
]

_PROBE_DIAG_FIELDS = (
    "required_table_row_count",
    "numeric_type_success_rate",
    "query_column_type_validity",
    "missing_value_rate",
    "json_parse_error_rate",
    "extraction_refusal_or_empty_rate",
    "schema_column_coverage",
    "glass_box_composite",
    "tuple_count",
    "unit_parse_success_rate",
    "duplicate_candidate_rate",
    "entity_ambiguity_score",
)


def _score_spread(scores: dict[str, float]) -> float:
    if not scores:
        return 0.0
    values = list(scores.values())
    return float(max(values) - min(values))


def _top_config(scores: dict[str, float]) -> str | None:
    if not scores:
        return None
    return max(scores, key=scores.get)


def _parse_config_id(config_id: str) -> PopulationConfig:
    parts = dict(p.split("=", 1) for p in config_id.split("|") if "=" in p)
    return PopulationConfig(
        config_id=config_id,
        er_strategy=parts.get("er", "embedding_0.7"),
        norm_strategy=parts.get("norm", "dictionary"),
        unit_strategy=parts.get("unit", "none"),
        miss_strategy=parts.get("miss", "drop"),
    )


def _required_table_populated(tier1: dict[str, Any]) -> bool:
    rows = tier1.get("required_table_row_count")
    if isinstance(rows, dict):
        return any(int(v) > 0 for v in rows.values())
    if rows is None:
        return False
    return int(rows) > 0


def build_decision_context(
    probe_data: ProbeData,
    *,
    corpus: list[dict],
    queries: list[dict],
    schema,
    slice_name: str,
    budget: float = 0.0,
) -> dict[str, Any]:
    """Deployment-visible diagnostics only — no ground-truth error."""
    tier0 = compute_tier0(
        corpus=corpus,
        queries=queries,
        schema=schema,
        config_space_size=len(generate_config_space()),
        budget=budget,
    )
    glass = dict(probe_data.glass_box_composites)
    btl = dict(probe_data.btl_scores)
    glass_top = _top_config(glass)
    btl_top = _top_config(btl)

    return {
        "slice": slice_name,
        "tier0": tier0,
        "probe_summary": {
            "num_probe_configs": len(probe_data.config_ids),
            "config_ids": list(probe_data.config_ids),
            "glass_box_scores": glass,
            "btl_scores": btl,
            "glass_box_spread": _score_spread(glass),
            "btl_spread": _score_spread(btl),
            "glass_box_top_config": glass_top,
            "btl_top_config": btl_top,
            "top1_agreement": glass_top == btl_top if glass_top and btl_top else None,
            "num_judge_pairs": len(probe_data.pairwise_comparisons),
            "btl_win_counts": (probe_data.btl_report or {}).get("win_counts", {}),
        },
    }


@dataclass
class AgentToolkit:
    """ReAct tool surface over deployment-visible probe diagnostics."""

    probe_data: ProbeData
    corpus: list[dict]
    queries: list[dict]
    schema: Any
    slice_name: str
    committed_surrogate: str | None = field(default=None, init=False)
    committed_configs: list[str] = field(default_factory=list, init=False)
    _surrogate_cache: dict[str, list[tuple[str, float]]] = field(default_factory=dict, init=False)
    _cached_tier0: dict[str, Any] = field(default_factory=dict, init=False)
    _stage1_report: Any = field(default=None, init=False)
    _loo_rhos: dict[str, float] = field(default_factory=dict, init=False)
    # Optional reference to Instance for adaptive probing
    instance: Any = field(default=None, init=False)

    @classmethod
    def from_probe_run(
        cls,
        probe_data: ProbeData,
        *,
        corpus: list[dict],
        queries: list[dict],
        schema,
        slice_name: str,
    ) -> AgentToolkit:
        return cls(
            probe_data=probe_data,
            corpus=corpus,
            queries=queries,
            schema=schema,
            slice_name=slice_name,
        )

    @classmethod
    def from_cache(cls, payload: dict[str, Any]) -> AgentToolkit:
        probe_view = ProbeData(
            config_ids=list(payload["config_ids"]),
            configs={cid: _parse_config_id(cid) for cid in payload["config_ids"]},
            tier1_signals=dict(payload.get("tier1_by_config", {})),
            glass_box_composites=dict(payload.get("glass_box_scores", {})),
            pairwise_comparisons=list(payload.get("pairwise_comparisons", [])),
            btl_scores=dict(payload.get("btl_scores", {})),
            databases={},
            total_cost=0.0,
            btl_report=dict(payload.get("btl_report", {})),
        )
        toolkit = cls(
            probe_data=probe_view,
            corpus=[],
            queries=[],
            schema=_SchemaStub(payload.get("schema_tables", {})),
            slice_name=str(payload.get("slice", "agg_only")),
        )
        toolkit._cached_tier0 = dict(payload.get("tier0", {}))
        return toolkit

    def to_cache(self) -> dict[str, Any]:
        return {
            "version": 1,
            "slice": self.slice_name,
            "config_ids": list(self.probe_data.config_ids),
            "glass_box_scores": dict(self.probe_data.glass_box_composites),
            "btl_scores": dict(self.probe_data.btl_scores),
            "tier1_by_config": {
                cid: dict(self.probe_data.tier1_signals.get(cid, {}))
                for cid in self.probe_data.config_ids
            },
            "btl_report": dict(self.probe_data.btl_report or {}),
            "pairwise_comparisons": list(self.probe_data.pairwise_comparisons),
            "schema_tables": dict(getattr(self.schema, "tables", {})),
            "tier0": compute_tier0(
                corpus=self.corpus,
                queries=self.queries,
                schema=self.schema,
                config_space_size=len(generate_config_space()),
                budget=0.0,
            )
            if self.corpus and self.queries
            else {},
        }

    def decision_context(self) -> dict[str, Any]:
        if self.corpus and self.queries:
            return build_decision_context(
                self.probe_data,
                corpus=self.corpus,
                queries=self.queries,
                schema=self.schema,
                slice_name=self.slice_name,
            )
        summary = {
            "num_probe_configs": len(self.probe_data.config_ids),
            "config_ids": list(self.probe_data.config_ids),
            "glass_box_scores": dict(self.probe_data.glass_box_composites),
            "btl_scores": dict(self.probe_data.btl_scores),
            "glass_box_spread": _score_spread(self.probe_data.glass_box_composites),
            "btl_spread": _score_spread(self.probe_data.btl_scores),
        }
        return {"slice": self.slice_name, "probe_summary": summary}

    def get_dataset_summary(self) -> dict[str, Any]:
        if self.corpus and self.queries:
            tier0 = compute_tier0(
                corpus=self.corpus,
                queries=self.queries,
                schema=self.schema,
                config_space_size=len(generate_config_space()),
                budget=0.0,
            )
        else:
            tier0 = dict(self._cached_tier0)
        return {
            "slice": self.slice_name,
            "dataset": getattr(self.schema, "dataset_name", None),
            "schema_mode": "denormalized_single_table"
            if len(getattr(self.schema, "tables", {})) <= 1
            else "multi_table",
            "tables": list(getattr(self.schema, "tables", {}).keys()),
            "num_probe_configs": len(self.probe_data.config_ids),
            "tier0": tier0,
        }

    def get_probe_diagnostics(self, config_id: str) -> dict[str, Any]:
        if config_id not in self.probe_data.config_ids:
            return {"error": f"Unknown config_id {config_id!r}. Probed configs: {self.probe_data.config_ids}"}
        tier1 = dict(self.probe_data.tier1_signals.get(config_id, {}))
        visible = {k: tier1[k] for k in _PROBE_DIAG_FIELDS if k in tier1}
        return {
            "config_id": config_id,
            "required_table_populated": _required_table_populated(tier1),
            "valid_json_returned": float(tier1.get("json_parse_error_rate", 0.0)) == 0.0,
            "numeric_columns_usable": float(tier1.get("numeric_type_success_rate", 0.0)),
            "signals": visible,
        }

    def get_btl_rankings(self) -> dict[str, Any]:
        scores = dict(self.probe_data.btl_scores)
        ranking = [
            {"rank": i + 1, "config_id": cid, "btl_score": float(scores[cid])}
            for i, cid in enumerate(sorted(scores, key=scores.get, reverse=True))
        ]
        report = self.probe_data.btl_report or {}
        return {
            "num_pairwise_comparisons": len(self.probe_data.pairwise_comparisons),
            "btl_spread": _score_spread(scores),
            "win_counts": report.get("win_counts", {}),
            "loss_counts": report.get("loss_counts", {}),
            "ranking": ranking,
        }

    def _surrogate_ranking(self, surrogate_name: str) -> list[tuple[str, float]]:
        if surrogate_name in self._surrogate_cache:
            return self._surrogate_cache[surrogate_name]
        if surrogate_name not in AGENT_SURROGATE_CHOICES:
            raise ValueError(f"Surrogate {surrogate_name!r} not in agent candidate set.")
        surrogate = build_surrogate(surrogate_name, seed=int(load_config()["experiment"]["seed"]))
        surrogate.fit(self.probe_data)
        ranked = surrogate.rank(list(self.probe_data.config_ids))
        scores = [(cid, float(surrogate.score(cid))) for cid in ranked]
        self._surrogate_cache[surrogate_name] = scores
        return scores

    def get_surrogate_ranking(self, surrogate_name: str) -> dict[str, Any]:
        try:
            scores = self._surrogate_ranking(surrogate_name)
        except ValueError as exc:
            return {"error": str(exc)}
        return {
            "surrogate": surrogate_name,
            "ranking": [
                {"rank": i + 1, "config_id": cid, "proxy_score": score}
                for i, (cid, score) in enumerate(scores)
            ],
        }

    def compare_surrogates(self, surrogate_a: str, surrogate_b: str) -> dict[str, Any]:
        try:
            rank_a = self._surrogate_ranking(surrogate_a)
            rank_b = self._surrogate_ranking(surrogate_b)
        except ValueError as exc:
            return {"error": str(exc)}

        pos_a = {cid: i for i, (cid, _) in enumerate(rank_a)}
        pos_b = {cid: i for i, (cid, _) in enumerate(rank_b)}
        common = set(pos_a) & set(pos_b)
        disagreements = [
            {
                "config_id": cid,
                f"{surrogate_a}_rank": pos_a[cid] + 1,
                f"{surrogate_b}_rank": pos_b[cid] + 1,
                "rank_delta": abs(pos_a[cid] - pos_b[cid]),
            }
            for cid in common
            if pos_a[cid] != pos_b[cid]
        ]
        disagreements.sort(key=lambda row: row["rank_delta"], reverse=True)
        top_a = [cid for cid, _ in rank_a[:3]]
        top_b = [cid for cid, _ in rank_b[:3]]
        return {
            "surrogate_a": surrogate_a,
            "surrogate_b": surrogate_b,
            "top3_overlap": sorted(set(top_a) & set(top_b)),
            "top1_agreement": rank_a[0][0] == rank_b[0][0] if rank_a and rank_b else None,
            "num_disagreements": len(disagreements),
            "largest_disagreements": disagreements[:5],
        }

    # ------------------------------------------------------------------
    # Pipeline orchestration tools
    # ------------------------------------------------------------------

    def run_stage1_characterization(self) -> dict[str, Any]:
        """Run Stage 1 search-space characterization on current probe data.
        Returns recommendations that gate Stage 2 and Stage 3.
        No ground-truth access.
        """
        from stage1.characterizer import characterize
        from thresholds.schema import load_thresholds
        tc = load_thresholds()
        report = characterize(
            self.probe_data,
            queries=self.queries,
            schema=self.schema,
            thresholds=tc,
            true_errors=None,
            reward_rows=None,
        )
        self._stage1_report = report
        return {
            "recommendations": report.recommendations,
            "probe_fidelity": report.probe_fidelity,
            "error_surface": report.error_surface,
            "interactions": report.interactions,
            "clustering": report.clustering,
            "note": "Use these recommendations to guide Stage 2 surrogate selection.",
        }

    def run_surrogate_bakeoff(self) -> dict[str, Any]:
        """Compute LOO Spearman ρ for all surrogates using probe signals only.
        Returns surrogate ranking and which thresholds they cross.
        No ground-truth access.
        """
        from thresholds.optimizer import _compute_loo_rhos
        from thresholds.schema import load_thresholds
        tc = load_thresholds()
        rhos = _compute_loo_rhos(self.probe_data)
        self._loo_rhos = rhos
        sorted_surrogates = sorted(rhos.items(), key=lambda x: -x[1])
        return {
            "surrogate_loo_rhos": dict(sorted_surrogates),
            "viable": [k for k, v in sorted_surrogates if v >= tc.rho_viable],
            "bakeoff_only": [k for k, v in sorted_surrogates
                             if tc.rho_bakeoff <= v < tc.rho_viable],
            "below_bakeoff": [k for k, v in sorted_surrogates if v < tc.rho_bakeoff],
            "thresholds": {"rho_viable": tc.rho_viable, "rho_bakeoff": tc.rho_bakeoff},
            "note": "Pick a surrogate from 'viable' if possible. Use run_pipeline_and_select to apply.",
        }

    def probe_additional_configs(self, n_additional: int = 4) -> dict[str, Any]:
        """Probe n_additional more configs from the config space.
        Call this when Stage 1 probe fidelity is too low (rho < rho_bakeoff).
        Uses cheap LLM extraction + BTL judge — no query evaluation.
        """
        if self.instance is None:
            return {
                "error": "No instance available for adaptive probing. "
                         "Run from an experiment that provides the corpus and schema.",
                "probed": 0,
            }
        from pipeline.full_pipeline import _expand_probes
        from utils.config import load_config
        cfg = load_config()
        seed = int(cfg["experiment"]["seed"])
        n = max(1, min(int(n_additional), 8))
        old_n = len(self.probe_data.config_ids)
        self.probe_data = _expand_probes(
            self.probe_data, self.instance, self.schema,
            self.queries, n_additional=n, seed=seed,
        )
        new_n = len(self.probe_data.config_ids)
        # Invalidate caches
        self._surrogate_cache.clear()
        self._stage1_report = None
        self._loo_rhos = {}
        return {
            "probed_before": old_n,
            "probed_after": new_n,
            "added": new_n - old_n,
            "config_ids": list(self.probe_data.config_ids),
            "note": "Re-run run_stage1_characterization and run_surrogate_bakeoff with expanded probe data.",
        }

    def run_pipeline_and_select(
        self,
        budget: int = 1,
        allow_adaptive_probing: bool = False,
    ) -> dict[str, Any]:
        """Run the full connected Stage 1→2→3→4 pipeline and return selected configs.
        This is the primary action when you have gathered enough evidence.
        No ground-truth access — all decisions from probe signals.
        """
        from pipeline.full_pipeline import run_spp_pipeline
        from thresholds.schema import load_thresholds
        tc = load_thresholds()
        result = run_spp_pipeline(
            self.probe_data,
            queries=self.queries,
            schema=self.schema,
            thresholds=tc,
            budget=int(budget),
            allow_adaptive_probing=allow_adaptive_probing,
            instance=self.instance,
        )
        self.committed_configs = result.selected_configs
        self.committed_surrogate = result.best_surrogate
        return {
            "selected_configs": result.selected_configs,
            "best_surrogate": result.best_surrogate,
            "best_algorithm": result.best_algorithm,
            "stage1_recommendations": result.stage1_recommendations,
            "stage1_probe_fidelity_rho": result.stage1_probe_fidelity_rho,
            "stage4_active_components": result.stage4_retained_components,
            "n_probe_configs_used": result.n_probe_configs_used,
            "probing_expanded": result.probing_expanded,
            "committed": True,
            "message": f"Pipeline complete. Selected {result.selected_configs} via "
                       f"{result.best_surrogate} + {result.best_algorithm}.",
        }

    def commit(self, surrogate_name: str) -> dict[str, Any]:
        if surrogate_name not in AGENT_SURROGATE_CHOICES:
            return {
                "error": f"Invalid surrogate {surrogate_name!r}. Allowed: {AGENT_SURROGATE_CHOICES}",
                "committed": False,
            }
        self.committed_surrogate = surrogate_name
        return {
            "committed": True,
            "surrogate": surrogate_name,
            "message": f"Decision finalized: use {surrogate_name} for config ranking.",
        }

    def dispatch(self, action: str, action_input: dict[str, Any] | None) -> dict[str, Any]:
        action = action.strip().removesuffix("()")
        action_input = action_input or {}

        if action == "get_dataset_summary":
            return self.get_dataset_summary()
        if action == "get_probe_diagnostics":
            config_id = action_input.get("config_id")
            if not config_id:
                return {"error": "action_input.config_id is required"}
            return self.get_probe_diagnostics(str(config_id))
        if action == "get_btl_rankings":
            return self.get_btl_rankings()
        if action == "get_surrogate_ranking":
            name = action_input.get("surrogate_name")
            if not name:
                return {"error": "action_input.surrogate_name is required"}
            return self.get_surrogate_ranking(str(name))
        if action == "compare_surrogates":
            a = action_input.get("surrogate_a")
            b = action_input.get("surrogate_b")
            if not a or not b:
                return {"error": "action_input.surrogate_a and surrogate_b are required"}
            return self.compare_surrogates(str(a), str(b))
        if action == "run_stage1_characterization":
            return self.run_stage1_characterization()
        if action == "run_surrogate_bakeoff":
            return self.run_surrogate_bakeoff()
        if action == "probe_additional_configs":
            n = int(action_input.get("n_additional", 4))
            return self.probe_additional_configs(n)
        if action == "run_pipeline_and_select":
            budget = int(action_input.get("budget", 1))
            adaptive = bool(action_input.get("allow_adaptive_probing", False))
            return self.run_pipeline_and_select(budget, adaptive)
        if action == "commit":
            name = action_input.get("surrogate_name")
            if not name:
                return {"error": "action_input.surrogate_name is required"}
            return self.commit(str(name))

        return {"error": f"Unknown action {action!r}. Available tools: {TOOL_NAMES}"}


@dataclass
class _SchemaStub:
    tables: dict[str, list[str]]
    dataset_name: str = "cached"

    @property
    def column_types(self) -> dict:
        return {}


def save_agent_cache(toolkit: AgentToolkit, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(toolkit.to_cache(), indent=2), encoding="utf-8")


def _legacy_cache_to_payload(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("probe_summary", {})
    return {
        "slice": payload.get("slice", "agg_only"),
        "config_ids": list(summary.get("config_ids", [])),
        "glass_box_scores": dict(summary.get("glass_box_scores", {})),
        "btl_scores": dict(summary.get("btl_scores", {})),
        "tier1_by_config": {},
        "btl_report": {"win_counts": dict(summary.get("btl_win_counts", {}))},
        "pairwise_comparisons": [],
        "tier0": dict(payload.get("tier0", {})),
    }


def load_agent_cache(path) -> AgentToolkit:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "config_ids" in payload:
        return AgentToolkit.from_cache(payload)
    if "probe_summary" in payload:
        return AgentToolkit.from_cache(_legacy_cache_to_payload(payload))
    raise ValueError(f"Cache at {path} is missing agent reload fields; re-run probes with --force-probe.")


def rule_based_select(
    context: dict[str, Any] | None,
    *,
    glass_box_spread_threshold: float = 0.01,
    logger=None,
) -> tuple[str, str]:
    if not context:
        reason = "placeholder_no_diagnostics"
        if logger:
            logger.info("rule_based: no diagnostics available; defaulting to llm_judge_btl (%s)", reason)
        return "llm_judge_btl", reason

    summary = context.get("probe_summary", {})
    btl_scores = summary.get("btl_scores") or {}
    btl_spread = float(summary.get("btl_spread", _score_spread(btl_scores)))
    glass_spread = float(summary.get("glass_box_spread", 0.0))

    if btl_scores and btl_spread > 0:
        return "llm_judge_btl", f"btl_spread={btl_spread:.4f}>0"
    if glass_spread > glass_box_spread_threshold:
        return "rf_proxy_glass", f"glass_box_spread={glass_spread:.4f}>{glass_box_spread_threshold}"
    return "direct_probe_ranking", f"low_signal btl_spread={btl_spread:.4f} glass_spread={glass_spread:.4f}"
