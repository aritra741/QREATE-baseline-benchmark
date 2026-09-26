"""Gold-free, insight-based operator router.

The router decides, per (table, attribute), which QuWARTS operator family
should own that attribute:

* ``repair``        additive repair of a small, SQL-sensitive residue on an incumbent database
* ``program``       reusable candidate-selection program; values shared across queries
* ``canonical_map`` query-independent bundled extraction; values shared across queries
* ``fused_map``     query-conditioned whole-document maps, fused across compatible queries
* ``retrieval_map`` query-conditioned maps over retrieved windows (documents do not fit)
* ``keep``          keep the incumbent/plumbing value (budget-infeasible or no signal)

Each rule follows from a redundancy argument (see ``policy.py``). Inputs are
the workload SQL, the raw corpus, an optional incumbent database, and a small
budgeted probe. Benchmark gold and stored baseline predictions are never read.
"""
