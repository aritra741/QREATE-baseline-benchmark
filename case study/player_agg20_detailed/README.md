# Player aggregation case studies: QuWARTS vs DocETL
This index links the 20 query-level reports. Each report contains the exact query contract, scores, gold output, both system outputs, row/cell discrepancy ledgers, and artifact-backed causal diagnoses.

| query | QuWARTS main score at 20% | DocETL main score at 20% | QuWARTS component | DocETL component |
| --- | --- | --- | --- | --- |
| [q0](q0.md) | 0.0000 | 0.0000 | Normalization | Extraction |
| [q1](q1.md) | 0.5280 | 0.5732 | Normalization | Output validation |
| [q2](q2.md) | 0.2606 | 0.2202 | Extraction | Extraction and query execution |
| [q3](q3.md) | 0.0000 | 0.0356 | Extraction and normalization | Extraction |
| [q4](q4.md) | 0.0000 | 0.0000 | Normalization | Extraction |
| [q5](q5.md) | 0.3333 | 0.4054 | Cell validation | Extraction and evaluation |
| [q6](q6.md) | 0.6633 | 0.0602 | Cell validation | Extraction |
| [q7](q7.md) | 0.4744 | 0.4701 | Extraction | Extraction and query execution |
| [q8](q8.md) | 0.0000 | 0.0000 | Normalization | Extraction |
| [q9](q9.md) | 0.2188 | 0.1836 | Extraction and normalization | Extraction |
| [q10](q10.md) | 0.1598 | 0.1190 | Cell validation | Extraction and query execution |
| [q11](q11.md) | 0.5195 | 0.5398 | Extraction | Extraction |
| [q12](q12.md) | 0.2948 | 0.6761 | Extraction | Extraction |
| [q13](q13.md) | 0.3074 | 0.3735 | Extraction | Extraction |
| [q14](q14.md) | 0.0435 | 0.1094 | Evaluation | Evaluation |
| [q15](q15.md) | 0.4714 | 0.4307 | Extraction | Extraction |
| [q16](q16.md) | 0.0000 | 0.0000 | Extraction | Extraction |
| [q17](q17.md) | 0.0000 | 0.2500 | Cell validation | Extraction |
| [q18](q18.md) | 1.0000 | 0.6478 | Cell validation | Extraction and query execution |
| [q19](q19.md) | 0.0000 | 0.1010 | Extraction and normalization | Extraction |

## Cross-query findings
- **Shared hard failure:** q0, q4, and q8 return no rows in both systems because fine-grained positions are never mapped to the contract literals Frontcourt and Backcourt.
- **QuWARTS:** its largest recurring failures are sparse player attributes, unresolved college/nationality/team aliases, team documents expanding into historical or non-team records, and inconsistent numeric/unit extraction.
- **DocETL:** its largest recurring failures are treating -1 as data inside aggregates and predicates, extracting join keys independently without resolution, and retaining malformed structured payloads as scalar values.
- **Evaluator-specific effects:** q5/q6 expose mixed-type SQLite behavior for empty numeric strings, while q14 gold keys are rewritten through the separate owner table before scoring. The q14 reports distinguish this hidden canonicalization from extraction mistakes.

## Interpretation boundary
The reports treat the supplied run artifacts as immutable observations. Each root cause is tied to the pipeline code and to an error that is visible in an intermediate extraction or materialized table.
