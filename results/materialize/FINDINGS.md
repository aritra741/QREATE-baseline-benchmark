# Triggered materialization: answer, patch or rebuild (2026-09-29)

Code: `core/adapt/drift.py` (workload drift) and `core/adapt/controller.py` (decisions). The streams and experiments are in `eval/materialize_stream.py`.

## Method
- **Per query: answer, patch or rebuild.**
  - **Answer** when every needed column is materialized for every document that can affect the result.
  - Otherwise **patch** (targeted extraction):
    - read only the documents that can affect the answer; a top-level `AND` conjunct over fully materialized columns is pushed down to the master database;
    - use the build's reader, so the fidelity is the same;
    - memoize the cells.
  - **Rebuild** means one shared read with the design of the build workload plus every query seen since.
- **What a read extracts (robust reads).** A read costs about the document's length, so a read fills every schema column of that table the document still lacks. A rebuild uses the same robust design, in the spirit of CliffGuard's robust designs (Mozafari et al., SIGMOD 2015). The ablation `_observed` extracts only the columns the queries use.
- **When to rebuild: ski rental.**
  - Following OnlinePT (Bruno & Chaudhuri, ICDE 2007), the rent is the extraction the rebuilt design would have saved (patch tokens since the last build) and the buy is the rebuild's tokens.
  - Following ski rental with predictions (Purohit, Svitkina & Kumar, NeurIPS 2018), buy at λ·R when a shift is predicted and at R/λ otherwise, with λ = 0.5. This is 1.5-competitive when the prediction is right and 3-competitive whatever it says.
  - **Remaining-rent cap:** with robust reads, all future rent together is at most the cost of patching every cell still missing. When that is below R, no rebuild can pay off.
- **Drift.**
  - The magnitude uses CliffGuard's δ_separate: a query is its set of (column, clause) pairs, and δ = |ΔV| S |ΔV|ᵀ with S the Hamming distance / 2n.
  - The prediction is a novelty test. The share of window queries using a (column, clause) pair unseen in the build workload is tested against the build workload's own leave-one-out novelty rate, the Good–Turing unseen mass (as in distinct-value estimation), with a binomial tail.
  - A permutation test on δ was tried first and rejected. Stream queries that repeat build queries look closer than exchangeable splits, so it never fired (p ≈ 1 in trends). A resampling null gives novel queries zero mass, so it fires on any single novel query.
- **Streams** (seeded, from the 80% input split):
  - hide columns until 30% of the queries use one; the build workload is the rest;
  - **stable** phase: 30 build queries plus one in eight of the hidden-column queries;
  - **trend** phase: the other hidden-column queries alternating with build queries;
  - **recur** phase: 20 queries mixing both.
  - The master database at the start is the protocol run's database with the hidden columns removed.
- **Offline optimum** (clairvoyant): the cheaper of never rebuilding and rebuilding before the first query with the whole stream's design.

## Cost (token estimates of every read decided; zero-token dry runs)

| Corpus | OPT | patch | eager | OnlinePT | **drift** | patch_obs | eager_obs | OnlinePT_obs | drift_obs |
|---|---:|---|---|---|---|---|---|---|---|
| Med | 3.75M | ×1.23 | ×2.15 | ×1.93 | **×1.23** | ×1.97 | ×6.90 | ×2.71 | ×2.67 |
| Finan | 16.0M | ×1.00 | ×1.09 | ×1.00 | **×1.00** | ×2.70 | ×3.04 | ×2.80 | ×2.80 |
| Legal | 4.30M | ×1.00 | ×1.15 | ×1.00 | **×1.00** | ×1.86 | ×2.18 | ×2.03 | ×2.03 |
| Art | 2.09M | ×1.00 | ×1.53 | ×1.00 | **×1.00** | ×1.95 | ×3.31 | ×2.57 | ×2.57 |
| CSPaper | 0.33M | ×1.00 | ×1.55 | ×1.00 | **×1.00** | ×2.05 | ×3.89 | ×2.66 | ×2.66 |
| Player | 2.18M | ×1.34 | ×2.01 | ×1.93 | **×1.34** | ×1.84 | ×5.93 | ×2.08 | ×2.51 |

The cost model matched the money actually spent within 0.2% (CSPaper observed patching: 676,476 estimated, 675,442 spent).

## Accuracy (CSPaper, real reads; mean query score at the database version each query was answered on; AUDIT: reads gold)

| Policy | Tokens | All 77 positions | Hidden-column queries | Build queries |
|---|---:|---:|---:|---:|
| robust patching (patch = drift) | 0.33M | 0.229 | 0.265 | 0.212 |
| observed patching | 0.68M | 0.226 | 0.254 | 0.212 |
| rebuild at the first miss (eager) | 0.51M | 0.240 | 0.290 | 0.216 |

## Findings
1. **In extraction cost, new columns never justify a rebuild once reads are robust.**
   - Each document is read at most once more (it gets every missing column), whereas a rebuild reads every document.
   - The remaining-rent cap turns this into the rule: the proposed policy never rebuilt, and matched the clairvoyant optimum on four corpora.
   - **Med and Player** (multi-table, ×1.23 and ×1.34):
     - joins disable pushdown;
     - the full schema's field list adds prompt overhead;
     - some queried attributes are not in the schema file;
     - a clairvoyant rebuild with only the needed columns is cheaper there.
   - OnlinePT without the cap rebuilt needlessly on those two (×1.93).
2. **Without robust reads, patches recur for every new column.**
   - Every policy lands at 1.9–2.8× the optimum.
   - Rebuilding at every miss is the worst, up to 6.9×.
   - Here the drift prediction and OnlinePT cost the same on four corpora; drift is slightly better on Med (×2.67 against ×2.71) and worse on Player (×2.51 against ×2.08).
3. **The novelty test separates the phases once a trend is under way.** On CSPaper (observed run), p was 0.19 at the stable-phase miss, 0.32 at the first trend miss (one trend query in the window) and 0.000 at the two later trend misses.
4. **A rebuild's value is quality, not cost.**
   - Rebuilding once improved CSPaper's mean score from 0.229 to 0.240 (hidden-column queries 0.265 → 0.290). It cost 0.51M tokens instead of 0.33M.
   - This is one corpus and one stream, whose positions repeat queries; the difference is not tested.
   - A trend that only adds columns is handled by patching. A rebuild would pay when a trend changes how *existing* columns are used (their usage phrases), which the cost rule cannot see.

## Next (not built)
A quality trigger for rebuilds:
- detect usage drift on materialized columns (their field lines change under the current workload);
- re-extract a small probe sample with the new design and with the old one;
- rebuild (or refresh those columns) only if the new design changes values beyond the old design's own re-read noise, using a paired test.
