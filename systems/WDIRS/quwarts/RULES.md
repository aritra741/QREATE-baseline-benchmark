# Frozen compiler rules

Derived from `T`, `Q`, and `theta` only. No gold tables, gold row counts, or dataset names enter a rule. This set is frozen for held-out corpora. Player train is development history.

## Rules

1. **IN-list domain.** An `IN` list is a declared domain iff it is disjoint from extracted surfaces. Overlap is a slice, not a domain. Map surfaces onto the domain in `O(distinct)`.
2. **Type unification.** Equijoin sides share one type. String evidence or non-numeric literals force string. `TypeUnificationError` does not abort a corpus; the join stays infeasible and those queries score zero.
3. **Shared canonical ID.** Entity resolution runs once over distinct values and stores surface, canonical ID, match confidence, and provenance. The same ID is used in every database. Joins and identity operations use that ID. No per-join bridge tables and no per-database ER matches.
4. **Declared relationships only.** Keys and join sides come from SQL join structure, declared logical-schema relationships, extracted evidence, and the shared canonical IDs. Column names such as `*_name` or `*_id` do not choose an authority side.
5. **First-feasible routing.** Routing is compile-order, first-feasible. The repair agent may rematerialize databases. It does not choose among multiple feasible databases.
6. **No name-based identity extract.** Do not constrain extraction from `*_name` / `*_id`. Surface forms may be kept for display or provenance.
7. **Join-yield gating.** Rewrite feasibility uses filtered-left join yield, not set Jaccard. Zero-yield empties score zero. Failed rewrite scores zero.
8. **Slice-safety.** Unsafe templates do not admit on a predicate slice. Anti-join / `EXCEPT` / `NOT EXISTS` shapes are slice-unsafe.
9. **Unit standardization.** Numeric commit parses currency marks and scale suffixes (`k`/`m`/`b`, million, billion) into ones. SQL comparison literals already live in that family. Unparseable surfaces stay null. Added after the Finan smoke, before held-out.
10. **SQL-then-evidence type.** Precedence: SQL literals, casts, comparisons, and aggregate operators; then evidence values and observed parse results; then unset / unknown. Attribute names do not set type. An unresolved type keeps the surface value. Literal-derived correction and coercion re-extract are bug fixes, not a research claim.
11. **Coercion retain-and-retry.** `dtype_coercion` keeps the surface and `null_reason`. After the type is corrected, those cells are re-extracted.
12. **Empty-result reject.** `empty_result_rate` above `EMPTY_RESULT_REJECT` (0.25) is a hard reject. The reason is written on the run manifest. The configuration may still be scored; it is not an accepted freeze.
13. **Rho-guided routes.** A second dissimilar route on a document sample estimates per-attribute `rho` (within-format disagreement / total). `rho > 0.5` gets a different strategy (focused prompt, chunked segmentation). `rho ≤ 0.5` may receive more routes of the same family.
14. **Route count from amp.** Use `amp(a)` directly. Do not rank `key/join > projection`. Attributes used in `SUM`, `AVG`, `COUNT DISTINCT`, `GROUP BY`, `MAX`, and `MIN` are high-impact. Agreement accepts; disagreement escalates one route and takes majority.
15. **Span-grounded vote.** A disagreed cell is kept only if its surface appears in the document. Otherwise write null with `ungrounded`.
16. **Repair exit.** The extract loop exits on budget exhaustion or when a pass changes fewer than `CELL_CHANGE_STOP` (0.02) of cells. Nominal requirement satisfaction does not stop the loop while budget remains.

Operator split: joins and grouping use the shared canonical ID. Databases may retain surface forms.

## Pre-registered predictions

The zero-equijoin parity prediction **failed on Art**. Emptiness was predicate failure from mis-typing, not join yield. The Player analysis identified join linkage as the binding constraint; that did not generalize. Both reduce to the same principle: every correspondence SQL declares must be compiled.

Player train is not a claim. Report Player test, new datasets, and pooled per-shape breakdown. Art after the typing fix is development. Med and Legal remain held-out.

## Run protocol

1. Gold-schema ceiling on the corpus before the compiler run.
2. `theta` = 25% of that corpus's DocETL token total.
3. One compiler run. No threshold changes, no per-dataset cases.
4. First structurally unlike corpus is a smoke / engineering run. The remainder are held-out.
