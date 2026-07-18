"""SPP (Schema-Population-Preprocessing) control-plane layer for WDIRS.

Implements the plan in `.cursor/plans/wdirs_to_spp_migration_*.plan.md`:
WDIRS remains the data-plane (single extraction, sieve synthesis, schema
stabilization, grounding checks are untouched). This package adds a thin
control-plane on top: an explicit population config space (Phase 1), a
brute-force config grid diagnostic (Phase 2), structural query clustering
(Phase 3), budget-aware routing (Phase 4), and a ground-truth-firewalled
evaluation harness (Phase 5).
"""
