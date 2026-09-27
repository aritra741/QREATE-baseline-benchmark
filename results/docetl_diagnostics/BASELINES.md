# Recorded DocETL case80 baselines: zero-token audit (2026-09-27)

Source: `quwarts/eval/docetl_baselines.py` produced `baselines_audit.json`. The rescore reads gold (audit only).

For every corpus, the recorded query set is exactly the seed-42 held-out split that QuWARTS is scored on:

| Corpus | Held-out queries | Workload queries |
|---|---:|---:|
| Med | 20 | 99 |
| Finan | 16 | 80 |
| Legal | 16 | 80 |
| Art | 16 | 80 |
| CSPaper | 16 | 80 |
| Player | 20 | 100 |

| Corpus | Recorded product | Reproduced by QuWARTS scorer | Tokens (summary / session) | Docs missing from output | Sentinel cells | Usable as baseline? |
|---|---:|---|---|---:|---:|---|
| Med | 0.1656 | partly (8 of 20 queries multi-table; single-table subset only) | 31.4M / **11.8M** | 5.4% (max 10%) | 31% | Yes (recorded evaluator); token figure ambiguous |
| Finan | 0.0841 | exact | 1.38M | **93%** | 10% | **No**: 93 of 100 filings dropped (tokenizer mismatch + `skip_on_error`); needs a fair rerun |
| Legal | 0.1235 | exact (fair rerun 0.1250) | 50.4M | 3.5% | 28% | Yes |
| Art | 0.0694 | exact | 20.4M | 0% | 45% | Yes |
| CSPaper | 0.0891 | exact | 4.56M / **2.61M** | 0% | 81% | Yes, but see corpus note; token figure ambiguous |
| Player | 0.2017 | partly (10 of 20 queries multi-table) | 12.8M | 10% (max 24%) | 20% | Yes (recorded evaluator) |

Notes:

- **CSPaper corpus.**
  - `source_data/CSPaper/txt` holds only the first ~4,000 characters of each paper (min 3,974, max 4,105). The full papers are PDFs in the same folder.
  - Both DocETL and QuWARTS read these files, so the comparison is fair, but both are handicapped. That is why 81% of DocETL's CSPaper cells are "not found" sentinels.
  - Whether to regenerate the text from the PDFs is a benchmark-preparation decision.
- **Token ambiguity.** For Med and CSPaper, `summary.json` and `session_token_cost.json` disagree. The handoff used the session figure: Med 11.8M. That sets the 25% budget.
- **Descriptions.** DocETL's prompts list field names only. Under the SQL-only rule QuWARTS also receives no attribute descriptions (only what it derives from the SQL), so this deviation is now symmetric. On Legal, giving DocETL the generated descriptions did not help it (0.1250 vs 0.1235).
- **Sentinels.** Treating `-1` and `""` as NULL changes the rescored products only slightly: Legal 0.1244, Art 0.0701, CSPaper 0.0805.
