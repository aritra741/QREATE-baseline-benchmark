-- Query 1: train (agg_only) id=agg_only_sec_111
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 2: train (agg_only) id=agg_only_sec_86
SELECT form_type, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics GROUP BY form_type;

-- Query 3: train (agg_only) id=agg_only_sec_53
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics GROUP BY ticker;

-- Query 4: train (agg_only) id=agg_only_sec_198
SELECT state_of_incorporation, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 5: train (agg_only) id=agg_only_sec_46
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics GROUP BY ticker;

-- Query 6: train (agg_only) id=agg_only_sec_107
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 7: train (agg_only) id=agg_only_sec_194
SELECT state_of_incorporation, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 8: train (agg_only) id=agg_only_sec_31
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics GROUP BY company_name;

-- Query 9: train (agg_only) id=agg_only_sec_166
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics GROUP BY sic_description;

-- Query 10: train (agg_only) id=agg_only_sec_3
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics GROUP BY company_name;

-- Query 11: train (agg_only) id=agg_only_sec_126
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 12: train (agg_only) id=agg_only_sec_197
SELECT state_of_incorporation, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 13: train (agg_only) id=agg_only_sec_148
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics GROUP BY sic_description;

-- Query 14: train (agg_only) id=agg_only_sec_81
SELECT form_type, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics GROUP BY form_type;

-- Query 15: train (agg_only) id=agg_only_sec_37
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics GROUP BY ticker;

-- Query 16: train (agg_only) id=agg_only_sec_139
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics GROUP BY sic_description;

-- Query 17: train (agg_only) id=agg_only_sec_163
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics GROUP BY sic_description;

-- Query 18: train (agg_only) id=agg_only_sec_77
SELECT form_type, MIN(assets_usd) AS min_assets_usd FROM filing_metrics GROUP BY form_type;

-- Query 19: train (agg_only) id=agg_only_sec_4
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics GROUP BY company_name;

-- Query 20: train (agg_only) id=agg_only_sec_39
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics GROUP BY ticker;

-- Query 21: train (agg_filter) id=agg_filter_sec_1507
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 22: train (agg_filter) id=agg_filter_sec_2528
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 23: train (agg_filter) id=agg_filter_sec_1002
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 24: train (agg_filter) id=agg_filter_sec_1501
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 25: train (agg_filter) id=agg_filter_sec_497
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 26: train (agg_filter) id=agg_filter_sec_376
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 27: train (agg_filter) id=agg_filter_sec_2590
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 28: train (agg_filter) id=agg_filter_sec_1843
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 29: train (agg_filter) id=agg_filter_sec_1677
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 30: train (agg_filter) id=agg_filter_sec_630
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 31: train (agg_filter) id=agg_filter_sec_1728
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 32: train (agg_filter) id=agg_filter_sec_73
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 33: train (agg_filter) id=agg_filter_sec_902
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 34: train (agg_filter) id=agg_filter_sec_1128
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 35: train (agg_filter) id=agg_filter_sec_674
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 36: train (agg_filter) id=agg_filter_sec_2889
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 37: train (agg_filter) id=agg_filter_sec_777
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 38: train (agg_filter) id=agg_filter_sec_1379
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 39: train (agg_filter) id=agg_filter_sec_1692
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 40: train (agg_filter) id=agg_filter_sec_1679
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 41: train (agg_join) id=agg_join_sec_104
SELECT filing.form_type, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 42: train (agg_join) id=agg_join_sec_17
SELECT company.ticker, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 43: train (agg_join) id=agg_join_sec_5
SELECT company.ticker, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 44: train (agg_join) id=agg_join_sec_35
SELECT company.sic_description, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 45: train (agg_join) id=agg_join_sec_93
SELECT company.state_of_incorporation, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 46: train (agg_join) id=agg_join_sec_98
SELECT filing.form_type, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 47: train (agg_join) id=agg_join_sec_70
SELECT company.state_of_incorporation, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 48: train (agg_join) id=agg_join_sec_115
SELECT filing.form_type, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 49: train (agg_join) id=agg_join_sec_119
SELECT filing.form_type, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 50: train (agg_join) id=agg_join_sec_18
SELECT company.ticker, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 51: train (agg_join) id=agg_join_sec_124
SELECT filing.form_type, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 52: train (agg_join) id=agg_join_sec_120
SELECT filing.form_type, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 53: train (agg_join) id=agg_join_sec_63
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 54: train (agg_join) id=agg_join_sec_33
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 55: train (agg_join) id=agg_join_sec_25
SELECT company.ticker, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 56: train (agg_join) id=agg_join_sec_90
SELECT company.state_of_incorporation, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 57: train (agg_join) id=agg_join_sec_126
SELECT filing.form_type, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 58: train (agg_join) id=agg_join_sec_118
SELECT filing.form_type, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 59: train (agg_join) id=agg_join_sec_23
SELECT company.ticker, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 60: train (agg_join) id=agg_join_sec_1
SELECT company.ticker, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 61: train (agg_filter_join) id=agg_filter_join_sec_1611
SELECT filing.form_type, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 62: train (agg_filter_join) id=agg_filter_join_sec_1268
SELECT filing.form_type, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 63: train (agg_filter_join) id=agg_filter_join_sec_1100
SELECT filing.form_type, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 64: train (agg_filter_join) id=agg_filter_join_sec_1522
SELECT filing.form_type, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 65: train (agg_filter_join) id=agg_filter_join_sec_527
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 66: train (agg_filter_join) id=agg_filter_join_sec_810
SELECT company.ticker, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 67: train (agg_filter_join) id=agg_filter_join_sec_1042
SELECT company.ticker, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 68: train (agg_filter_join) id=agg_filter_join_sec_1331
SELECT filing.form_type, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 69: train (agg_filter_join) id=agg_filter_join_sec_941
SELECT company.ticker, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 70: train (agg_filter_join) id=agg_filter_join_sec_1613
SELECT filing.form_type, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 71: train (agg_filter_join) id=agg_filter_join_sec_137
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 72: train (agg_filter_join) id=agg_filter_join_sec_377
SELECT company.sic_description, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 73: train (agg_filter_join) id=agg_filter_join_sec_1581
SELECT filing.form_type, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 74: train (agg_filter_join) id=agg_filter_join_sec_1241
SELECT filing.form_type, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 75: train (agg_filter_join) id=agg_filter_join_sec_883
SELECT company.ticker, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 76: train (agg_filter_join) id=agg_filter_join_sec_474
SELECT company.sic_description, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 77: train (agg_filter_join) id=agg_filter_join_sec_266
SELECT company.sic_description, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 78: train (agg_filter_join) id=agg_filter_join_sec_1345
SELECT filing.form_type, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 79: train (agg_filter_join) id=agg_filter_join_sec_983
SELECT company.ticker, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 80: train (agg_filter_join) id=agg_filter_join_sec_525
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 81: train (agg_temporal) id=agg_temporal_sec_148
SELECT fiscal_year, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 82: train (agg_temporal) id=agg_temporal_sec_47
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_year = 2026 GROUP BY fiscal_period;

-- Query 83: train (agg_temporal) id=agg_temporal_sec_121
SELECT fiscal_year, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 84: train (agg_temporal) id=agg_temporal_sec_126
SELECT company.ticker, fiscal_year, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 85: train (agg_temporal) id=agg_temporal_sec_45
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_year = 2025 GROUP BY fiscal_period;

-- Query 86: train (agg_temporal) id=agg_temporal_sec_84
SELECT company.ticker, fiscal_year, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 87: train (agg_temporal) id=agg_temporal_sec_127
SELECT fiscal_year, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 88: train (agg_temporal) id=agg_temporal_sec_18
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2023 GROUP BY company.sic_description;

-- Query 89: train (agg_temporal) id=agg_temporal_sec_135
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2022 GROUP BY fiscal_period;

-- Query 90: train (agg_temporal) id=agg_temporal_sec_40
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2022 GROUP BY company.sic_description;

-- Query 91: train (agg_temporal) id=agg_temporal_sec_152
SELECT fiscal_year, fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 92: train (agg_temporal) id=agg_temporal_sec_13
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_year = 2021 GROUP BY fiscal_period;

-- Query 93: train (agg_temporal) id=agg_temporal_sec_170
SELECT fiscal_year, fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 94: train (agg_temporal) id=agg_temporal_sec_118
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2025 GROUP BY company.sic_description;

-- Query 95: train (agg_temporal) id=agg_temporal_sec_115
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2024 GROUP BY fiscal_period;

-- Query 96: train (agg_temporal) id=agg_temporal_sec_176
SELECT fiscal_year, fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 97: train (agg_temporal) id=agg_temporal_sec_158
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2021 GROUP BY company.sic_description;

-- Query 98: train (agg_temporal) id=agg_temporal_sec_143
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2026 GROUP BY fiscal_period;

-- Query 99: train (agg_temporal) id=agg_temporal_sec_111
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2022 GROUP BY fiscal_period;

-- Query 100: train (agg_temporal) id=agg_temporal_sec_32
SELECT fiscal_year, fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;
