# Frozen compiler rules

Derived from `T`, `Q`, and `theta` only. No gold tables, gold row counts, or dataset names enter a rule. This set is frozen for held-out corpora. Player train is development history.

## Rules

1. **IN-list domain.** An `IN` list is a declared domain iff it is disjoint from extracted surfaces. Overlap is a slice, not a domain. Map surfaces onto the domain in `O(distinct)`.
2. **Type unification.** Equijoin sides share one type. String evidence or non-numeric literals force string. `TypeUnificationError` does not abort a corpus; the join stays infeasible and those queries score zero.
3. **Bridges.** Equijoin linkage is a relation `bridge(left, right, evidence, confidence)`. Keep `rename`, `alias`, `abbreviation`, `historical_name`. Drop affiliation and location. The bridge is a function on the left: reject a left value with more than one right.
4. **Co-mention.** `rename` and `historical_name` rows require both surface forms in one document. `alias` and `abbreviation` are unfiltered.
5. **Authority membership.** The identity side of an equijoin is one compile-time set, stamped onto every cluster database. Routing does not change membership. Unmatched atomic references become authority rows so a right-hand value exists.
6. **Constrained referencing extract.** Extract the authority identity first, from documents that assert that entity. Extract the referencing column as a closed choice over that set plus `other`. A constrained assignment must appear in the extract span; otherwise emit `other`. Free-form leftovers are not populated.
7. **Join-yield gating.** Rewrite feasibility uses filtered-left join yield, not set Jaccard. Zero-yield empties score zero. Failed rewrite scores zero.
8. **Slice-safety.** Unsafe templates do not admit on a predicate slice. Anti-join / `EXCEPT` / `NOT EXISTS` shapes are slice-unsafe.
9. **Unit standardization.** Numeric commit parses currency marks and scale suffixes (`k`/`m`/`b`, million, billion) into ones. SQL comparison literals already live in that family. Unparseable surfaces stay null. Added after the Finan smoke, before held-out.
10. **Literal-derived type.** A comparison predicate declares the column type. String literals force string; numeric literals force numeric. Precedence: literal, then corpus evidence, then name heuristics only for attributes no predicate touches. Added after Art, against a typing defect, not an Art vocabulary.
11. **Coercion retain-and-retry.** `dtype_coercion` keeps the surface and `null_reason`. After the type is corrected, those cells are re-extracted.
12. **Empty-result reject.** `empty_result_rate` above `EMPTY_RESULT_REJECT` (0.25) is a hard reject. The reason is written on the run manifest. The configuration may still be scored; it is not an accepted freeze.

Operator split: `GROUP BY` may use a canonical form; joins use surface values and consult the bridge per left value.

## Pre-registered predictions

The zero-equijoin parity prediction **failed on Art**. Emptiness was predicate failure from mis-typing, not join yield. The Player analysis identified join linkage as the binding constraint; that did not generalize. Both reduce to the same principle: every correspondence SQL declares must be compiled.

Player train is not a claim. Report Player test, new datasets, and pooled per-shape breakdown. Art after the typing fix is development. Med and Legal remain held-out.

## Run protocol

1. Gold-schema ceiling on the corpus before the compiler run.
2. `theta` = 25% of that corpus's DocETL token total.
3. One compiler run. No threshold changes, no per-dataset cases.
4. First structurally unlike corpus is a smoke / engineering run. The remainder are held-out.
