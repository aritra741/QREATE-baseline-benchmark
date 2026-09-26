"""Frozen router constants.

These are decision boundaries and cost-model parameters declared before any
router run. They are not tuned on benchmark scores. Changing any value changes
``FROZEN_HASH``, which is written into every plan manifest.
"""

from __future__ import annotations

import hashlib
import json

from quwarts.core.corpus_probe.context import COMPLETION_SPACE, SAFETY_MARGIN, EFFECTIVE_INPUT_LIMIT

FROZEN: dict[str, float | int | str] = {
    "version": "router-v1",
    # --- cost model -------------------------------------------------------
    # Usable document tokens in one call (same limit as corpus_probe.context).
    "context_window_tokens": EFFECTIVE_INPUT_LIMIT - COMPLETION_SPACE - SAFETY_MARGIN,
    # Prompt wrapper + schema + completion charged per call on top of the document.
    "call_overhead_tokens": 600,
    # Queries per fused transmission. Two is the widest fusion with audited
    # evidence of preserved per-query semantics on a 7B model.
    "fusion_width": 2,
    # Attributes per query-independent bundle call.
    "canonical_bundle_size": 6,
    # Retrieved window for long documents, repair lookups, and probes.
    "window_tokens": 3000,
    # Program synthesis: model calls per attribute (examples + synthesis + repair).
    "program_calls_per_attribute": 8,
    # --- probe budget -----------------------------------------------------
    "probe_budget_fraction": 0.10,
    "probe_docs_min": 3,
    "probe_docs_max": 8,
    "probe_query_contexts_per_doc": 2,
    "probe_seed": 20260926,
    # --- decision boundaries ---------------------------------------------
    # Majority rule: an attribute is extractive when most non-null answers are
    # source spans (or normalized spans).
    "extractive_min": 0.5,
    # Query sensitivity net of sampling noise. Above this, one shared value
    # cannot serve every query context.
    "sensitivity_max": 0.2,
    # Anchor regularity: most grounded values share one textual anchor.
    "regularity_min": 0.5,
    # Repair only when the SQL-unknown residue is a small fraction of rows and
    # the incumbent's existing values are grounded in the source.
    "residue_fraction_max": 0.10,
    "incumbent_grounding_min": 0.5,
    # Zero-token priors.
    "label_surface_min": 0.5,
    "corpus_sample_docs": 50,
    # Plan verdict from served (query, attribute) coverage within theta.
    "coverage_serve_min": 0.8,
    "coverage_loss_max": 0.5,
}


def frozen_hash() -> str:
    payload = json.dumps(FROZEN, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


FROZEN_HASH = frozen_hash()
