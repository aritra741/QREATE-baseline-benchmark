-- Query 1: dev (agg_only) id=agg_only_sec_160
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics GROUP BY sic_description;

-- Query 2: dev (agg_only) id=agg_only_sec_191
SELECT state_of_incorporation, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 3: dev (agg_only) id=agg_only_sec_131
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 4: dev (agg_only) id=agg_only_sec_70
SELECT form_type, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics GROUP BY form_type;

-- Query 5: dev (agg_only) id=agg_only_sec_165
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics GROUP BY sic_description;

-- Query 6: dev (agg_filter) id=agg_filter_sec_2809
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 7: dev (agg_filter) id=agg_filter_sec_2481
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 8: dev (agg_filter) id=agg_filter_sec_1703
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 9: dev (agg_filter) id=agg_filter_sec_1726
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 10: dev (agg_filter) id=agg_filter_sec_1486
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 11: dev (agg_join) id=agg_join_sec_21
SELECT company.ticker, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 12: dev (agg_join) id=agg_join_sec_31
SELECT company.ticker, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 13: dev (agg_join) id=agg_join_sec_50
SELECT company.sic_description, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 14: dev (agg_join) id=agg_join_sec_71
SELECT company.state_of_incorporation, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 15: dev (agg_join) id=agg_join_sec_82
SELECT company.state_of_incorporation, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 16: dev (agg_filter_join) id=agg_filter_join_sec_691
SELECT company.ticker, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 17: dev (agg_filter_join) id=agg_filter_join_sec_221
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 18: dev (agg_filter_join) id=agg_filter_join_sec_1055
SELECT company.ticker, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 19: dev (agg_filter_join) id=agg_filter_join_sec_847
SELECT company.ticker, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 20: dev (agg_filter_join) id=agg_filter_join_sec_534
SELECT company.sic_description, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 21: dev (agg_temporal) id=agg_temporal_sec_3
SELECT company.ticker, fiscal_year, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 22: dev (agg_temporal) id=agg_temporal_sec_85
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_year = 2021 GROUP BY fiscal_period;

-- Query 23: dev (agg_temporal) id=agg_temporal_sec_120
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2026 GROUP BY company.sic_description;

-- Query 24: dev (agg_temporal) id=agg_temporal_sec_187
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_year = 2024 GROUP BY fiscal_period;

-- Query 25: dev (agg_temporal) id=agg_temporal_sec_136
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2022 GROUP BY company.sic_description;
