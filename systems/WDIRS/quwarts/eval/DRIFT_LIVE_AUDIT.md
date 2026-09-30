# Audit of the fixed-question drift levels (design v3, `fixed3-<axis>/<p>`), 2026-09-30

This checks everything that can differ between drift levels, without a GPU, before the long run.

## The method: an extractor that cannot add noise

`tests/oracle_ollama.py` stands in for Ollama. For each document and field, it returns the value an earlier read stored (the replay's `robust_raw.db`), no matter which other fields are in the prompt, what the usage phrases say, or how the document is chunked. With it, every level's extraction is identical by construction. So any difference between levels comes from the pipeline itself: builds, patches, scopes, views, scoring or bookkeeping.

To rerun the audit on any machine:

```bash
bash systems/WDIRS/quwarts/scripts/chpc/audit_oracle.sh cspaper,player
```

It takes a few minutes per corpus. If `robust_raw.db` isn't on the machine, the script rebuilds it from `results/drift_design/<corpus>/reads.jsonl`. The same script also runs `python -m quwarts.eval.drift_live_audit --design` and `--levels`, which can be used on a real run too.

## Results (attribute axis, all six corpora)

| Corpus | Accuracy at 0 / 25 / 50 / 75 / 100% | Queries whose score differs | Why the served data differs where it does |
|---|---|---|---|
| cspaper | 0.215 at every level | 1 (0.002 → 0.000) | 1 query represented differently; 1 query with rows outside a patch's scope |
| player | 0.396 at every level | 0 | 2 queries with rows outside a patch's scope |
| med | 0.082 at every level | 0 | 2 scope; 2 represented differently |
| art | 0.283 at every level | 0 | 1 scope; 2 represented differently |
| legal | 0.202 at every level | 0 | 1 scope |
| finan | 0.093 at 0% and 100% | 0 | 3 scope |

Levels 25–75 for finan weren't finished (long documents make the stand-in slow). Its 0% and 100% levels match.

- **Every level scores the same**, and matches the replay's full-read reference (cspaper 0.215, player 0.396, med 0.082, art 0.283, legal 0.202). With extraction held fixed, the pipeline adds no level-to-level differences.
- **Rows outside a patch's scope:** a patch reads only the documents that can affect the answer, so other rows stay empty. Their score is identical at every level, which confirms the scope logic is right.
- **Represented differently:** the representation layer (the query-time views) knows the anticipated queries' constants at build time. At low drift levels it can therefore normalize a value differently, for example `F1 || EM` → `F1` instead of `EM || F1`. This is a real, small effect of anticipating queries. It changed one score, by 0.002.
- **The cost side behaves as designed.** Patches and documents re-read rise with the level. For example, cspaper had 0 / 0 / 1 / 4 / 6 patches and 0 / 0 / 200 / 600 / 1003 documents re-read at 0 / 25 / 50 / 75 / 100%.

## Other checks

- **Design** (`--design`, all six corpora × three axes): the withheld sets are nested, and the kept columns shrink as the level rises. Level 100 keeps no extra columns. No usage phrase uses a constant from a query that is withheld at a level that keeps the column. 0 problems.
- **Resuming:** a cspaper run stopped five times mid-stream gave the same data, scores, actions, documents read and token counts as an uninterrupted run.
- **Score cache:** scores are memoized by query and a digest of the columns the query reads. Twenty (query, view) pairs rescored from scratch matched the cache exactly.
- **Everything already verified by construction:**
  - W0's columns are identical at every level;
  - the kept extra columns are identical to level 0 at every level where they're kept;
  - columns a level doesn't keep are empty;
  - levels 25–75 make no new build calls.

## Bugs found and fixed in this audit

1. **Input tokens were undercounted with Ollama.** Ollama reports only the prompt tokens it evaluated, so a prefix reused from its cache wasn't counted. The prompt is now counted with the exact Qwen 2.5 tokenizer plus the chat template's markers, and the larger of the two counts is kept. Ollama's own count is stored as `ollama_prompt_eval_count`.
2. **Truncation was checked against Ollama's count,** which undercounts. It now uses the tokenizer count. A new `cut_off` flag marks answers that hit `num_predict`, whose JSON may be cut short.
3. **The build cost of anticipated levels was overstated.** The separate supplement read, which exists only to hold values fixed across levels, was charged in full on top of W0's read. A level is now charged what one shared read of W0's and its kept columns would cost: W0's read as measured, plus the kept fields' prompt lines and answers per call. The measured cost is kept as `measured_tokens`. Build metadata written without this is recomputed from the journal automatically.
4. **With a deadline under 20 seconds, the build read never progressed** (OpenRouter mode only). The build now always gets at least 5 seconds.

## What the real run can still show between levels, and why it isn't a bug

With the stand-in, every level scores the same. With Qwen, the only remaining difference is how a drifted column is read:

- **ahead:** in the shared build read, alongside all the extra columns, with usage phrases from the anticipated queries;
- **on arrival:** in a patch with the columns the query lacks, with a usage phrase from the queries seen so far.

The two prompts differ, and a 7B model's answers depend on the prompt. That is the drift effect on accuracy, and it can go either way.

Queries withheld at two different levels can also be patched with different prompts, because different earlier queries were seen. That spreads their scores somewhat. It's still genuine drift behavior.

Identical prompts get identical answers, since every call is journaled. Extraction runs at temperature 0.1 with no seed. Setting temperature to 0 would reduce the variance of new prompts, but it would invalidate the cached reads.
