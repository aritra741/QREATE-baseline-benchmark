# SEC Benchmark Data Dictionary

Official sources:
- https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- https://www.sec.gov/files/company_tickers.json

The benchmark keeps raw filings on disk, preserves normalized SEC fact tables, and adds one derived `filing_metrics` table for workload construction.

## company

One row per issuer. Stable key is company_id = zero-padded CIK.

- `company_id`
- `cik`
- `ticker`
- `name`
- `sic`
- `sic_description`
- `state_of_incorporation`
- `fiscal_year_end`
- `entity_type`

## filing

One row per selected 10-K or 10-Q filing.

- `filing_id`
- `company_id`
- `ticker`
- `company_name`
- `accession_number`
- `accession_nodash`
- `form_type`
- `filing_date`
- `report_date`
- `acceptance_datetime`
- `fiscal_year`
- `fiscal_period`
- `fiscal_quarter`
- `sic`
- `sic_description`
- `state_of_incorporation`
- `fiscal_year_end`
- `primary_document`
- `primary_doc_description`
- `source_url`
- `raw_html_path`
- `raw_text_path`
- `is_xbrl`
- `is_inline_xbrl`

## concept

One row per SEC taxonomy concept observed in the retained facts.

- `concept_id`
- `taxonomy`
- `concept_name`
- `label`
- `description`

## period

One row per unique fact period context.

- `period_id`
- `period_start`
- `period_end`
- `fiscal_year`
- `fiscal_period`
- `fiscal_quarter`
- `frame`
- `period_type`

## unit

One row per explicit SEC unit string.

- `unit_id`
- `unit_name`

## financial_fact

Atomic numeric XBRL fact rows filtered to the selected companies and filings only.

- `fact_id`
- `company_id`
- `filing_id`
- `accession_number`
- `concept_id`
- `concept_name`
- `taxonomy`
- `value`
- `unit_id`
- `period_id`
- `period_start`
- `period_end`
- `period_type`
- `fiscal_year`
- `fiscal_period`
- `fiscal_quarter`
- `form_type`
- `filed_date`
- `frame`
- `source_api_url`

## filing_metrics

Derived filing-level metric table built strictly from the retained SEC facts for aggregation-heavy evaluation.

- `filing_id`
- `company_id`
- `ticker`
- `company_name`
- `form_type`
- `filing_date`
- `report_date`
- `fiscal_year`
- `fiscal_period`
- `fiscal_quarter`
- `sic`
- `sic_description`
- `state_of_incorporation`
- `revenue_usd`
- `revenue_usd_concept_id`
- `revenue_usd_unit_id`
- `revenue_usd_period_start`
- `revenue_usd_period_end`
- `assets_usd`
- `assets_usd_concept_id`
- `assets_usd_unit_id`
- `assets_usd_period_start`
- `assets_usd_period_end`
- `liabilities_usd`
- `liabilities_usd_concept_id`
- `liabilities_usd_unit_id`
- `liabilities_usd_period_start`
- `liabilities_usd_period_end`
- `net_income_usd`
- `net_income_usd_concept_id`
- `net_income_usd_unit_id`
- `net_income_usd_period_start`
- `net_income_usd_period_end`
- `operating_cash_flow_usd`
- `operating_cash_flow_usd_concept_id`
- `operating_cash_flow_usd_unit_id`
- `operating_cash_flow_usd_period_start`
- `operating_cash_flow_usd_period_end`
- `investing_cash_flow_usd`
- `investing_cash_flow_usd_concept_id`
- `investing_cash_flow_usd_unit_id`
- `investing_cash_flow_usd_period_start`
- `investing_cash_flow_usd_period_end`
- `financing_cash_flow_usd`
- `financing_cash_flow_usd_concept_id`
- `financing_cash_flow_usd_unit_id`
- `financing_cash_flow_usd_period_start`
- `financing_cash_flow_usd_period_end`
- `shares_outstanding`
- `shares_outstanding_concept_id`
- `shares_outstanding_unit_id`
- `shares_outstanding_period_start`
- `shares_outstanding_period_end`
- `market_cap_usd`
- `market_cap_usd_concept_id`
- `market_cap_usd_unit_id`
- `market_cap_usd_period_start`
- `market_cap_usd_period_end`
