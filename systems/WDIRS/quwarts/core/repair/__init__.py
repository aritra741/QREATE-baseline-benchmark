"""Post-compiler repair agent. Detectors and leftover theta only."""

from quwarts.core.repair.agent import MIN_REPAIR_TOKENS, run_repair_agent
from quwarts.core.repair.diagnose import (
    EmptyQueryDiagnosis,
    FilterFailureDiagnosis,
    diagnose_empty_query,
    diagnose_empty_queries,
    diagnose_filter_failure,
    diagnose_filter_failures,
)
from quwarts.core.repair.er import resolve_shared_ids, stamp_shared_ids
from quwarts.core.repair.models import RepairReport
from quwarts.core.repair.rank import priority, rank_repairs

__all__ = [
    "EmptyQueryDiagnosis",
    "FilterFailureDiagnosis",
    "MIN_REPAIR_TOKENS",
    "RepairReport",
    "diagnose_empty_query",
    "diagnose_empty_queries",
    "diagnose_filter_failure",
    "diagnose_filter_failures",
    "priority",
    "rank_repairs",
    "resolve_shared_ids",
    "run_repair_agent",
    "stamp_shared_ids",
]
