-- Query 1: test (agg_only) id=agg_only_sec_48
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics GROUP BY ticker;

-- Query 2: test (agg_only) id=agg_only_sec_79
SELECT form_type, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics GROUP BY form_type;

-- Query 3: test (agg_only) id=agg_only_sec_6
SELECT company_name, COUNT(*) AS count_all FROM filing_metrics GROUP BY company_name;

-- Query 4: test (agg_only) id=agg_only_sec_14
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics GROUP BY company_name;

-- Query 5: test (agg_only) id=agg_only_sec_38
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics GROUP BY ticker;

-- Query 6: test (agg_filter) id=agg_filter_sec_2347
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 7: test (agg_filter) id=agg_filter_sec_1867
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 8: test (agg_filter) id=agg_filter_sec_1856
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 9: test (agg_filter) id=agg_filter_sec_1191
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 10: test (agg_filter) id=agg_filter_sec_397
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 11: test (agg_join) id=agg_join_sec_10
SELECT company.ticker, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 12: test (agg_join) id=agg_join_sec_24
SELECT company.ticker, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 13: test (agg_join) id=agg_join_sec_84
SELECT company.state_of_incorporation, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 14: test (agg_join) id=agg_join_sec_110
SELECT filing.form_type, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 15: test (agg_join) id=agg_join_sec_88
SELECT company.state_of_incorporation, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 16: test (agg_filter_join) id=agg_filter_join_sec_38
SELECT company.sic_description, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 17: test (agg_filter_join) id=agg_filter_join_sec_1363
SELECT filing.form_type, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 18: test (agg_filter_join) id=agg_filter_join_sec_1212
SELECT filing.form_type, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 19: test (agg_filter_join) id=agg_filter_join_sec_143
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 20: test (agg_filter_join) id=agg_filter_join_sec_202
SELECT company.sic_description, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 21: test (agg_temporal) id=agg_temporal_sec_181
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_year = 2021 GROUP BY fiscal_period;

-- Query 22: test (agg_temporal) id=agg_temporal_sec_67
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_year = 2024 GROUP BY fiscal_period;

-- Query 23: test (agg_temporal) id=agg_temporal_sec_174
SELECT company.ticker, fiscal_year, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 24: test (agg_temporal) id=agg_temporal_sec_153
SELECT company.ticker, fiscal_year, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 25: test (agg_temporal) id=agg_temporal_sec_94
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2025 GROUP BY company.sic_description;
