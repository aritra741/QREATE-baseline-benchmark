from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from diagnostics.tier0 import compute_tier0
from optimizer.config_space import PopulationConfig, generate_config_space, parse_config_id
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
    "get_dataset_summary",
    "get_probe_diagnostics",
    "get_btl_rankings",
    "get_surrogate_ranking",
    "compare_surrogates",
    "choose_cluster_granularity",
    "run_stage1_characterization",
    "run_surrogate_bakeoff",
    "probe_additional_configs",
    "stop_probing",
    "choose_risk_level",
    "run_pipeline_and_select",
    "emit_routing_table",
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
    return parse_config_id(config_id)


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
    instance: Any = field(default=None, init=False)
    risk_level: str = field(default="risk_neutral", init=False)
    routing_table: dict[int, str] = field(default_factory=dict, init=False)
    probing_stopped: bool = field(default=False, init=False)
    n_clusters_chosen: int = field(default=0, init=False)
    query_clusters: Any = field(default=None, init=False)

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
        from pipeline.extraction import ExtractionResult

        extraction = None
        raw_extraction = payload.get("extraction")
        if isinstance(raw_extraction, dict):
            extraction = ExtractionResult(
                tuples_by_table=raw_extraction.get("tuples_by_table", {}),
                token_cost=float(raw_extraction.get("token_cost", 0.0)),
                per_doc_signals=list(raw_extraction.get("per_doc_signals", [])),
            )

        probe_view = ProbeData(
            config_ids=list(payload["config_ids"]),
            configs={cid: _parse_config_id(cid) for cid in payload["config_ids"]},
            tier1_signals=dict(payload.get("tier1_by_config", {})),
            glass_box_composites=dict(payload.get("glass_box_scores", {})),
            pairwise_comparisons=list(payload.get("pairwise_comparisons", [])),
            btl_scores=dict(payload.get("btl_scores", {})),
            databases={},
            total_cost=float(payload.get("probe_total_cost", 0.0)),
            btl_report=dict(payload.get("btl_report", {})),
            extraction=extraction,
        )
        toolkit = cls(
            probe_data=probe_view,
            corpus=list(payload.get("corpus", [])),
            queries=list(payload.get("queries", [])),
            schema=_SchemaStub(payload.get("schema_tables", {})),
            slice_name=str(payload.get("slice", "agg_only")),
        )
        toolkit._cached_tier0 = dict(payload.get("tier0", {}))
        return toolkit

    def to_cache(self) -> dict[str, Any]:
        extraction_payload = None
        if self.probe_data.extraction is not None:
            ex = self.probe_data.extraction
            extraction_payload = {
                "tuples_by_table": ex.tuples_by_table,
                "token_cost": ex.token_cost,
                "per_doc_signals": ex.per_doc_signals,
            }
        return {
            "version": 2,
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
            "probe_total_cost": float(self.probe_data.total_cost),
            "corpus": list(self.corpus),
            "queries": list(self.queries),
            "extraction": extraction_payload,
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
        from thresholds.optimizer import _compute_loo_rhos, _compute_loo_rhos_per_cluster
        from thresholds.schema import load_thresholds
        tc = load_thresholds()
        rhos = _compute_loo_rhos(self.probe_data)
        self._loo_rhos = rhos
        per_cluster = {}
        if self.query_clusters is not None:
            per_cluster = _compute_loo_rhos_per_cluster(self.probe_data, self.query_clusters)
        sorted_surrogates = sorted(rhos.items(), key=lambda x: -x[1])
        return {
            "surrogate_loo_rhos": dict(sorted_surrogates),
            "per_cluster_loo_rhos": per_cluster,
            "viable": [k for k, v in sorted_surrogates if v >= tc.rho_viable],
            "bakeoff_only": [k for k, v in sorted_surrogates
                             if tc.rho_bakeoff <= v < tc.rho_viable],
            "below_bakeoff": [k for k, v in sorted_surrogates if v < tc.rho_bakeoff],
            "thresholds": {"rho_viable": tc.rho_viable, "rho_bakeoff": tc.rho_bakeoff},
            "note": "Per-cluster bakeoff available. Use emit_routing_table to finalize.",
        }

    def choose_cluster_granularity(self, n_clusters: int) -> dict[str, Any]:
        from stage4.query_clustering import cluster_workload
        from utils.config import load_config

        n = int(n_clusters)
        if n < 1 or n > 4:
            return {"error": "n_clusters must be between 1 and 4", "updated": False}

        seed = int(load_config()["experiment"]["seed"])
        self.query_clusters = cluster_workload(self.queries, seed=seed, n_clusters=n)
        self.n_clusters_chosen = n
        return {
            "updated": True,
            "n_clusters": self.query_clusters.n_clusters,
            "cluster_types": self.query_clusters.cluster_types,
            "cluster_sizes": {
                k: len(v) for k, v in self.query_clusters.cluster_to_queries.items()
            },
        }

    def stop_probing(self) -> dict[str, Any]:
        self.probing_stopped = True
        return {
            "probing_stopped": True,
            "num_probe_configs": len(self.probe_data.config_ids),
            "config_ids": list(self.probe_data.config_ids),
        }

    def choose_risk_level(self, level: str) -> dict[str, Any]:
        if level not in {"risk_neutral", "risk_averse"}:
            return {"error": "level must be 'risk_neutral' or 'risk_averse'", "updated": False}
        self.risk_level = level
        return {"updated": True, "risk_level": level}

    def probe_additional_configs(self, n_additional: int = 4, reasoning: str = "") -> dict[str, Any]:
        """Probe more configs when cost-benefit analysis supports it."""
        if self.probing_stopped:
            return {"error": "Probing was stopped explicitly.", "probed": 0}
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
            query_clusters=self.query_clusters,
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
            "reasoning": reasoning,
            "note": "Re-run run_stage1_characterization and run_surrogate_bakeoff with expanded probe data.",
        }

    def emit_routing_table(self, surrogate_name: str = "") -> dict[str, Any]:
        if surrogate_name and surrogate_name not in AGENT_SURROGATE_CHOICES:
            return {
                "error": f"Invalid surrogate {surrogate_name!r}. Allowed: {AGENT_SURROGATE_CHOICES}",
                "committed": False,
            }
        result = self.run_pipeline_and_select(
            token_budget=int(load_config().get("token_budget", 500_000)),
            allow_adaptive_probing=not self.probing_stopped,
        )
        if surrogate_name:
            self.committed_surrogate = surrogate_name
        return result

    def run_pipeline_and_select(
        self,
        token_budget: int = 50_000,
        allow_adaptive_probing: bool = False,
    ) -> dict[str, Any]:
        """Run the full connected Stage 1→2→3→4 pipeline and return selected configs.
        token_budget is the number of tokens available; the pipeline selects as
        many configs as the remaining budget (after probing) allows.
        No ground-truth access — all decisions from probe signals.
        """
        from pipeline.full_pipeline import run_spp_pipeline
        from stage4.query_clustering import cluster_workload
        from thresholds.schema import load_thresholds
        from utils.config import load_config

        tc = load_thresholds()
        cfg = load_config()
        seed = int(cfg["experiment"]["seed"])
        if self.instance is None and self.corpus and self.queries:
            from data.instance_builder import Instance

            self.instance = Instance(
                dataset_name=getattr(self.schema, "dataset_name", "Player"),
                corpus=list(self.corpus),
                queries=list(self.queries),
                schema=self.schema,
            )

        result = run_spp_pipeline(
            self.probe_data,
            queries=self.queries,
            schema=self.schema,
            thresholds=tc,
            token_budget=int(token_budget),
            allow_adaptive_probing=allow_adaptive_probing and not self.probing_stopped,
            instance=self.instance,
            agent_risk_level=self.risk_level,
        )
        self.committed_configs = result.selected_configs
        self.committed_surrogate = result.best_surrogate
        if result.routing_table is not None:
            rt = result.routing_table
            if getattr(rt, "query_to_config", None):
                self.routing_table = dict(rt.query_to_config)
            else:
                self.routing_table = dict(getattr(rt, "cluster_to_config", {}))
        payload = {
            "selected_configs": result.selected_configs,
            "n_configs_selected": result.n_configs_selected,
            "best_surrogate": result.best_surrogate,
            "best_algorithm": result.best_algorithm,
            "stage1_recommendations": result.stage1_recommendations,
            "stage1_probe_fidelity_rho": result.stage1_probe_fidelity_rho,
            "stage4_active_components": result.stage4_retained_components,
            "n_probe_configs_used": result.n_probe_configs_used,
            "probing_expanded": result.probing_expanded,
            "token_budget_total": result.token_budget_total,
            "token_budget_spent": result.token_budget_spent,
            "token_budget_remaining": result.token_budget_remaining,
            "routing_table": {
                str(k): v for k, v in (result.routing_table.cluster_to_config.items()
                                      if result.routing_table else {})
            },
            "cluster_surrogates": {str(k): v for k, v in result.cluster_surrogates.items()},
            "query_cluster_info": result.query_cluster_info,
            "risk_level": result.risk_level,
            "committed": True,
            "audit_log": result.audit_log,
            "message": (
                f"Pipeline complete. Routing table with {result.n_configs_selected} materializations "
                f"via {result.best_algorithm}."
            ),
        }
        return payload

    def commit(self, surrogate_name: str) -> dict[str, Any]:
        """Backward-compatible alias for emit_routing_table."""
        return self.emit_routing_table(surrogate_name)

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
            reasoning = str(action_input.get("reasoning", ""))
            return self.probe_additional_configs(n, reasoning)
        if action == "choose_cluster_granularity":
            n = int(action_input.get("n_clusters", 3))
            return self.choose_cluster_granularity(n)
        if action == "stop_probing":
            return self.stop_probing()
        if action == "choose_risk_level":
            level = str(action_input.get("level", "risk_neutral"))
            return self.choose_risk_level(level)
        if action == "emit_routing_table":
            name = str(action_input.get("surrogate_name", ""))
            return self.emit_routing_table(name)
        if action == "run_pipeline_and_select":
            token_budget = int(action_input.get("token_budget", 50_000))
            adaptive = bool(action_input.get("allow_adaptive_probing", False))
            return self.run_pipeline_and_select(token_budget, adaptive)
        if action == "commit":
            name = str(action_input.get("surrogate_name", ""))
            return self.emit_routing_table(name)

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
    glass = dict(summary.get("glass_box_scores", {}))
    tier1_by_config = {
        cid: {"glass_box_composite": score}
        for cid, score in glass.items()
    }
    return {
        "slice": payload.get("slice", "agg_only"),
        "config_ids": list(summary.get("config_ids", [])),
        "glass_box_scores": glass,
        "btl_scores": dict(summary.get("btl_scores", {})),
        "tier1_by_config": tier1_by_config,
        "btl_report": {"win_counts": dict(summary.get("btl_win_counts", {}))},
        "pairwise_comparisons": [],
        "tier0": dict(payload.get("tier0", {})),
    }


def lock_toolkit_corpus_to_probe(toolkit: AgentToolkit, *, full_corpus: list[dict] | None = None) -> list[dict]:
    """Align toolkit.corpus with probe_data.extraction doc IDs (no re-extraction)."""
    from data.query_alignment import corpus_for_probe_extraction

    extraction = toolkit.probe_data.extraction if toolkit.probe_data else None
    if extraction is None or not extraction.per_doc_signals:
        return list(toolkit.corpus)

    corpus = corpus_for_probe_extraction(
        extraction,
        cached_corpus=toolkit.corpus,
        full_corpus=full_corpus,
    )
    toolkit.corpus = corpus
    return corpus


def load_agent_cache(path, *, lock_corpus_to_probe: bool = True) -> AgentToolkit:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "config_ids" in payload:
        toolkit = AgentToolkit.from_cache(payload)
    elif "probe_summary" in payload:
        toolkit = AgentToolkit.from_cache(_legacy_cache_to_payload(payload))
    else:
        raise ValueError(f"Cache at {path} is missing agent reload fields; re-run probes with --force-probe.")

    if lock_corpus_to_probe and toolkit.probe_data.extraction is not None:
        lock_toolkit_corpus_to_probe(toolkit)
    return toolkit


def _apply_routing_fallback(toolkit: AgentToolkit, surrogate: str) -> None:
    """Populate routing table from deployment-visible glass-box scores."""
    if not toolkit.queries:
        return
    from stage3.routing_assignment import deterministic_routing_fallback
    from stage4.query_clustering import cluster_workload

    seed = int(load_config()["experiment"]["seed"])
    if toolkit.query_clusters is None:
        toolkit.query_clusters = cluster_workload(toolkit.queries, seed=seed)
    rt = deterministic_routing_fallback(toolkit.query_clusters, toolkit.probe_data)
    toolkit.routing_table = dict(rt.cluster_to_config)
    toolkit.committed_configs = list(rt.selected_configs)
    toolkit.committed_surrogate = surrogate


def rule_based_select(
    context: dict[str, Any] | None,
    *,
    glass_box_spread_threshold: float = 0.01,
    logger=None,
    toolkit: AgentToolkit | None = None,
) -> tuple[str, str]:
    if not context:
        reason = "placeholder_no_diagnostics"
        surrogate = "llm_judge_btl"
        if logger:
            logger.info("rule_based: no diagnostics available; defaulting to llm_judge_btl (%s)", reason)
        if toolkit is not None:
            _apply_routing_fallback(toolkit, surrogate)
        return surrogate, reason

    summary = context.get("probe_summary", {})
    btl_scores = summary.get("btl_scores") or {}
    btl_spread = float(summary.get("btl_spread", _score_spread(btl_scores)))
    glass_spread = float(summary.get("glass_box_spread", 0.0))

    if btl_scores and btl_spread > 0:
        surrogate, reason = "llm_judge_btl", f"btl_spread={btl_spread:.4f}>0"
    elif glass_spread > glass_box_spread_threshold:
        surrogate, reason = (
            "rf_proxy_glass",
            f"glass_box_spread={glass_spread:.4f}>{glass_box_spread_threshold}",
        )
    else:
        surrogate, reason = (
            "direct_probe_ranking",
            f"low_signal btl_spread={btl_spread:.4f} glass_spread={glass_spread:.4f}",
        )

    if toolkit is not None:
        _apply_routing_fallback(toolkit, surrogate)
    return surrogate, reason
