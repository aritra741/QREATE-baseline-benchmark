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
]

TOOL_NAMES = [
    "get_dataset_summary",
    "get_probe_diagnostics",
    "get_btl_rankings",
    "get_surrogate_ranking",
    "compare_surrogates",
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
    _surrogate_cache: dict[str, list[tuple[str, float]]] = field(default_factory=dict, init=False)
    _cached_tier0: dict[str, Any] = field(default_factory=dict, init=False)

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
