"""Offline Query Workload-Aware Relational Table Synthesis.

The deployable system selects explicit ``<schema, population, preprocessing>``
configurations using corpus evidence and workload-derived quality estimates
under one global token ledger. It emits immutable SQLite databases, compiled
SQL, and fixed routing; serving performs no extraction or LLM calls.

Ground-truth-dependent grid/oracle modules remain evaluation-only and are not
imported by :mod:`spp.system`.
"""

from spp.spec import (
    FrozenPortfolio,
    PreprocessingPolicy,
    QualityEstimate,
    QueryRequirement,
    RelationSpec,
    SchemaDesign,
    SynthesisConfig,
)

__all__ = [
    "FrozenPortfolio",
    "PreprocessingPolicy",
    "QualityEstimate",
    "QueryRequirement",
    "RelationSpec",
    "SchemaDesign",
    "SynthesisConfig",
]
