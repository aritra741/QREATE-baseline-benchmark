# Audit: does our DocETL baseline receive inputs the way DocETL and UDA-Bench expect? (2026-09-26)

Runner: `systems/DocETL/run_player_grid_test_docetl.py` ->
`systems/DocETL/test_player_query_awareness_trend_docetl.py` (`_run_docetl_map_pipeline_for_table`).
References: DocETL source (`systems/docetl-main`, v0.2.6) and the UDA-Bench paper (`uda-new.md`).
No frozen DocETL artifact was modified; cell counts below read DocETL outputs for auditing only.

## Valid

| Item | Runner | DocETL expectation |
|---|---|---|
| Dataset | in-memory list of `{doc_id, text}` | a JSON array of documents (paper 2.1); `memory` datasets supported |
| Prompt | Jinja with `{{ input.text }}` | operator prompts are Jinja over `input` |
| Output schema types | `number`, `str` | accepted by `convert_val` (`validation.py`) |
| One map per (query, table) | yes | a valid single-operator pipeline |

## Deviations

1. **Truncation and silent skips.** DocETL truncates with a tokenizer that undercounts Qwen's
   tokens; prompts over the endpoint's 32,768 limit get HTTP 400 and `skip_on_error=True`
   drops the document (`finan_skipped_filings.md`): 93 of 100 Finan filings.
2. **No attribute descriptions.** The prompt lists field *names* only (`- revenue`). UDA-Bench
   ships a description per attribute (units, "convert to USD", allowed values such as
   "choose one from ['Yes', 'No']") and describes systems as feeding "the attribute (with
   optional user descriptions)". QuWARTS reads use those descriptions; the DocETL baseline did not.
3. **Sentinels kept as data.** The prompt asks for `-1` for unknown numbers and `""` for
   unknown text, and nothing converts them to NULL before the benchmark SQL runs. `-1` enters
   `AVG/SUM/MIN/MAX` and passes `IS NOT NULL`; `""` passes `IS NOT NULL`. Share of extracted cells:

   | Corpus | cells | `-1` | `""` |
   |---|---:|---:|---:|
   | Art | 37,031 | 28% | 17% |
   | CSPaper | 6,800 | 25% | 56% |
   | Player | 4,213 | 14% | 6% |
   | Legal | 21,486 | 12% | 16% |
   | Finan | 273 | 4% | 5% |
   | Med | 6,310 | 0% | 31% |

4. **No optimizer, no chunking.** The map runs as written. UDA-Bench ran DocETL with its
   optimizer, which on long documents chooses split -> per-chunk extraction -> aggregation
   ("DocETL always selects the plan that splits documents into chunks"). Our baseline relies
   on truncation instead, so on long documents it is a single-map DocETL, not optimized DocETL.
5. **Query context is raw SQL.** The runner passes the benchmark SQL as the "natural-language
   query" because the sampled queries have no NL text. UDA-Bench queries are SQL, so this is
   a reasonable choice, but it is not an NL task description.
6. **Model.** Qwen 2.5 7B via OpenRouter, where UDA-Bench used GPT-4.1-mini. This is the
   project's deliberate constraint, not a format error.

## Consequence

The recorded DocETL numbers are a *single-map DocETL without attribute descriptions, with
sentinel values scored as data, and with long documents silently dropped*. That is weaker
than DocETL as DocETL and UDA-Bench intend it. A fair baseline should: pass attribute
descriptions, map `-1`/`""` to NULL before SQL, count tokens with the Qwen tokenizer (or leave
a margin) and log failures, and either run the optimizer or report that it was not used.
