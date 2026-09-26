# INVALID: used benchmark attribute descriptions (2026-09-26)

The reads behind these results were prompted with text from the benchmark's attribute
files (`Query/<Corpus>/*_attributes.json`: descriptions, allowed values, nullability,
"use 0 if none", "convert to USD"). The system's inputs are the documents, the SQL
workload and theta only (`systems/WDIRS/quwarts/RULES.md`), so these numbers are not
QuWARTS results and must not be reported as such. Kept for the record. Since commit
518b596571 the system cannot read those files (`CorpusSpec.descriptions()` raises), and
`tests/test_router_sql_only.py` fails if any read prompt contains attribute-file text.
