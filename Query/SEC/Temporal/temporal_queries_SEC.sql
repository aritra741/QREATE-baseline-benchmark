-- Query 1: agg_temporal (agg_temporal) id=agg_temporal_sec_1
SELECT fiscal_year, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 2: agg_temporal (agg_temporal) id=agg_temporal_sec_2
SELECT fiscal_year, fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 3: agg_temporal (agg_temporal) id=agg_temporal_sec_3
SELECT company.ticker, fiscal_year, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 4: agg_temporal (agg_temporal) id=agg_temporal_sec_4
SELECT fiscal_year, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 5: agg_temporal (agg_temporal) id=agg_temporal_sec_5
SELECT fiscal_year, fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 6: agg_temporal (agg_temporal) id=agg_temporal_sec_6
SELECT company.ticker, fiscal_year, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 7: agg_temporal (agg_temporal) id=agg_temporal_sec_7
SELECT fiscal_year, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 8: agg_temporal (agg_temporal) id=agg_temporal_sec_8
SELECT fiscal_year, fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 9: agg_temporal (agg_temporal) id=agg_temporal_sec_9
SELECT company.ticker, fiscal_year, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 10: agg_temporal (agg_temporal) id=agg_temporal_sec_10
SELECT fiscal_year, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 11: agg_temporal (agg_temporal) id=agg_temporal_sec_11
SELECT fiscal_year, fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 12: agg_temporal (agg_temporal) id=agg_temporal_sec_12
SELECT company.ticker, fiscal_year, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 13: agg_temporal (agg_temporal) id=agg_temporal_sec_13
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_year = 2021 GROUP BY fiscal_period;

-- Query 14: agg_temporal (agg_temporal) id=agg_temporal_sec_14
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2021 GROUP BY company.sic_description;

-- Query 15: agg_temporal (agg_temporal) id=agg_temporal_sec_15
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_year = 2022 GROUP BY fiscal_period;

-- Query 16: agg_temporal (agg_temporal) id=agg_temporal_sec_16
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2022 GROUP BY company.sic_description;

-- Query 17: agg_temporal (agg_temporal) id=agg_temporal_sec_17
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_year = 2023 GROUP BY fiscal_period;

-- Query 18: agg_temporal (agg_temporal) id=agg_temporal_sec_18
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2023 GROUP BY company.sic_description;

-- Query 19: agg_temporal (agg_temporal) id=agg_temporal_sec_19
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_year = 2024 GROUP BY fiscal_period;

-- Query 20: agg_temporal (agg_temporal) id=agg_temporal_sec_20
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2024 GROUP BY company.sic_description;

-- Query 21: agg_temporal (agg_temporal) id=agg_temporal_sec_21
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_year = 2025 GROUP BY fiscal_period;

-- Query 22: agg_temporal (agg_temporal) id=agg_temporal_sec_22
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2025 GROUP BY company.sic_description;

-- Query 23: agg_temporal (agg_temporal) id=agg_temporal_sec_23
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_year = 2026 GROUP BY fiscal_period;

-- Query 24: agg_temporal (agg_temporal) id=agg_temporal_sec_24
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2026 GROUP BY company.sic_description;

-- Query 25: agg_temporal (agg_temporal) id=agg_temporal_sec_25
SELECT fiscal_year, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 26: agg_temporal (agg_temporal) id=agg_temporal_sec_26
SELECT fiscal_year, fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 27: agg_temporal (agg_temporal) id=agg_temporal_sec_27
SELECT company.ticker, fiscal_year, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 28: agg_temporal (agg_temporal) id=agg_temporal_sec_28
SELECT fiscal_year, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 29: agg_temporal (agg_temporal) id=agg_temporal_sec_29
SELECT fiscal_year, fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 30: agg_temporal (agg_temporal) id=agg_temporal_sec_30
SELECT company.ticker, fiscal_year, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 31: agg_temporal (agg_temporal) id=agg_temporal_sec_31
SELECT fiscal_year, MIN(assets_usd) AS min_assets_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 32: agg_temporal (agg_temporal) id=agg_temporal_sec_32
SELECT fiscal_year, fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 33: agg_temporal (agg_temporal) id=agg_temporal_sec_33
SELECT company.ticker, fiscal_year, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 34: agg_temporal (agg_temporal) id=agg_temporal_sec_34
SELECT fiscal_year, MAX(assets_usd) AS max_assets_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 35: agg_temporal (agg_temporal) id=agg_temporal_sec_35
SELECT fiscal_year, fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 36: agg_temporal (agg_temporal) id=agg_temporal_sec_36
SELECT company.ticker, fiscal_year, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 37: agg_temporal (agg_temporal) id=agg_temporal_sec_37
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_year = 2021 GROUP BY fiscal_period;

-- Query 38: agg_temporal (agg_temporal) id=agg_temporal_sec_38
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2021 GROUP BY company.sic_description;

-- Query 39: agg_temporal (agg_temporal) id=agg_temporal_sec_39
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_year = 2022 GROUP BY fiscal_period;

-- Query 40: agg_temporal (agg_temporal) id=agg_temporal_sec_40
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2022 GROUP BY company.sic_description;

-- Query 41: agg_temporal (agg_temporal) id=agg_temporal_sec_41
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_year = 2023 GROUP BY fiscal_period;

-- Query 42: agg_temporal (agg_temporal) id=agg_temporal_sec_42
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2023 GROUP BY company.sic_description;

-- Query 43: agg_temporal (agg_temporal) id=agg_temporal_sec_43
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_year = 2024 GROUP BY fiscal_period;

-- Query 44: agg_temporal (agg_temporal) id=agg_temporal_sec_44
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2024 GROUP BY company.sic_description;

-- Query 45: agg_temporal (agg_temporal) id=agg_temporal_sec_45
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_year = 2025 GROUP BY fiscal_period;

-- Query 46: agg_temporal (agg_temporal) id=agg_temporal_sec_46
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2025 GROUP BY company.sic_description;

-- Query 47: agg_temporal (agg_temporal) id=agg_temporal_sec_47
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_year = 2026 GROUP BY fiscal_period;

-- Query 48: agg_temporal (agg_temporal) id=agg_temporal_sec_48
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2026 GROUP BY company.sic_description;

-- Query 49: agg_temporal (agg_temporal) id=agg_temporal_sec_49
SELECT fiscal_year, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 50: agg_temporal (agg_temporal) id=agg_temporal_sec_50
SELECT fiscal_year, fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 51: agg_temporal (agg_temporal) id=agg_temporal_sec_51
SELECT company.ticker, fiscal_year, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 52: agg_temporal (agg_temporal) id=agg_temporal_sec_52
SELECT fiscal_year, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 53: agg_temporal (agg_temporal) id=agg_temporal_sec_53
SELECT fiscal_year, fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 54: agg_temporal (agg_temporal) id=agg_temporal_sec_54
SELECT company.ticker, fiscal_year, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 55: agg_temporal (agg_temporal) id=agg_temporal_sec_55
SELECT fiscal_year, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 56: agg_temporal (agg_temporal) id=agg_temporal_sec_56
SELECT fiscal_year, fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 57: agg_temporal (agg_temporal) id=agg_temporal_sec_57
SELECT company.ticker, fiscal_year, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 58: agg_temporal (agg_temporal) id=agg_temporal_sec_58
SELECT fiscal_year, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 59: agg_temporal (agg_temporal) id=agg_temporal_sec_59
SELECT fiscal_year, fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 60: agg_temporal (agg_temporal) id=agg_temporal_sec_60
SELECT company.ticker, fiscal_year, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 61: agg_temporal (agg_temporal) id=agg_temporal_sec_61
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_year = 2021 GROUP BY fiscal_period;

-- Query 62: agg_temporal (agg_temporal) id=agg_temporal_sec_62
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2021 GROUP BY company.sic_description;

-- Query 63: agg_temporal (agg_temporal) id=agg_temporal_sec_63
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_year = 2022 GROUP BY fiscal_period;

-- Query 64: agg_temporal (agg_temporal) id=agg_temporal_sec_64
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2022 GROUP BY company.sic_description;

-- Query 65: agg_temporal (agg_temporal) id=agg_temporal_sec_65
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_year = 2023 GROUP BY fiscal_period;

-- Query 66: agg_temporal (agg_temporal) id=agg_temporal_sec_66
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2023 GROUP BY company.sic_description;

-- Query 67: agg_temporal (agg_temporal) id=agg_temporal_sec_67
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_year = 2024 GROUP BY fiscal_period;

-- Query 68: agg_temporal (agg_temporal) id=agg_temporal_sec_68
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2024 GROUP BY company.sic_description;

-- Query 69: agg_temporal (agg_temporal) id=agg_temporal_sec_69
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_year = 2025 GROUP BY fiscal_period;

-- Query 70: agg_temporal (agg_temporal) id=agg_temporal_sec_70
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2025 GROUP BY company.sic_description;

-- Query 71: agg_temporal (agg_temporal) id=agg_temporal_sec_71
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_year = 2026 GROUP BY fiscal_period;

-- Query 72: agg_temporal (agg_temporal) id=agg_temporal_sec_72
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2026 GROUP BY company.sic_description;

-- Query 73: agg_temporal (agg_temporal) id=agg_temporal_sec_73
SELECT fiscal_year, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 74: agg_temporal (agg_temporal) id=agg_temporal_sec_74
SELECT fiscal_year, fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 75: agg_temporal (agg_temporal) id=agg_temporal_sec_75
SELECT company.ticker, fiscal_year, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 76: agg_temporal (agg_temporal) id=agg_temporal_sec_76
SELECT fiscal_year, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 77: agg_temporal (agg_temporal) id=agg_temporal_sec_77
SELECT fiscal_year, fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 78: agg_temporal (agg_temporal) id=agg_temporal_sec_78
SELECT company.ticker, fiscal_year, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 79: agg_temporal (agg_temporal) id=agg_temporal_sec_79
SELECT fiscal_year, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 80: agg_temporal (agg_temporal) id=agg_temporal_sec_80
SELECT fiscal_year, fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 81: agg_temporal (agg_temporal) id=agg_temporal_sec_81
SELECT company.ticker, fiscal_year, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 82: agg_temporal (agg_temporal) id=agg_temporal_sec_82
SELECT fiscal_year, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 83: agg_temporal (agg_temporal) id=agg_temporal_sec_83
SELECT fiscal_year, fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 84: agg_temporal (agg_temporal) id=agg_temporal_sec_84
SELECT company.ticker, fiscal_year, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 85: agg_temporal (agg_temporal) id=agg_temporal_sec_85
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_year = 2021 GROUP BY fiscal_period;

-- Query 86: agg_temporal (agg_temporal) id=agg_temporal_sec_86
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2021 GROUP BY company.sic_description;

-- Query 87: agg_temporal (agg_temporal) id=agg_temporal_sec_87
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_year = 2022 GROUP BY fiscal_period;

-- Query 88: agg_temporal (agg_temporal) id=agg_temporal_sec_88
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2022 GROUP BY company.sic_description;

-- Query 89: agg_temporal (agg_temporal) id=agg_temporal_sec_89
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_year = 2023 GROUP BY fiscal_period;

-- Query 90: agg_temporal (agg_temporal) id=agg_temporal_sec_90
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2023 GROUP BY company.sic_description;

-- Query 91: agg_temporal (agg_temporal) id=agg_temporal_sec_91
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_year = 2024 GROUP BY fiscal_period;

-- Query 92: agg_temporal (agg_temporal) id=agg_temporal_sec_92
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2024 GROUP BY company.sic_description;

-- Query 93: agg_temporal (agg_temporal) id=agg_temporal_sec_93
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_year = 2025 GROUP BY fiscal_period;

-- Query 94: agg_temporal (agg_temporal) id=agg_temporal_sec_94
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2025 GROUP BY company.sic_description;

-- Query 95: agg_temporal (agg_temporal) id=agg_temporal_sec_95
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_year = 2026 GROUP BY fiscal_period;

-- Query 96: agg_temporal (agg_temporal) id=agg_temporal_sec_96
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2026 GROUP BY company.sic_description;

-- Query 97: agg_temporal (agg_temporal) id=agg_temporal_sec_97
SELECT fiscal_year, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 98: agg_temporal (agg_temporal) id=agg_temporal_sec_98
SELECT fiscal_year, fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 99: agg_temporal (agg_temporal) id=agg_temporal_sec_99
SELECT company.ticker, fiscal_year, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 100: agg_temporal (agg_temporal) id=agg_temporal_sec_100
SELECT fiscal_year, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 101: agg_temporal (agg_temporal) id=agg_temporal_sec_101
SELECT fiscal_year, fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 102: agg_temporal (agg_temporal) id=agg_temporal_sec_102
SELECT company.ticker, fiscal_year, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 103: agg_temporal (agg_temporal) id=agg_temporal_sec_103
SELECT fiscal_year, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 104: agg_temporal (agg_temporal) id=agg_temporal_sec_104
SELECT fiscal_year, fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 105: agg_temporal (agg_temporal) id=agg_temporal_sec_105
SELECT company.ticker, fiscal_year, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 106: agg_temporal (agg_temporal) id=agg_temporal_sec_106
SELECT fiscal_year, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 107: agg_temporal (agg_temporal) id=agg_temporal_sec_107
SELECT fiscal_year, fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 108: agg_temporal (agg_temporal) id=agg_temporal_sec_108
SELECT company.ticker, fiscal_year, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 109: agg_temporal (agg_temporal) id=agg_temporal_sec_109
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2021 GROUP BY fiscal_period;

-- Query 110: agg_temporal (agg_temporal) id=agg_temporal_sec_110
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2021 GROUP BY company.sic_description;

-- Query 111: agg_temporal (agg_temporal) id=agg_temporal_sec_111
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2022 GROUP BY fiscal_period;

-- Query 112: agg_temporal (agg_temporal) id=agg_temporal_sec_112
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2022 GROUP BY company.sic_description;

-- Query 113: agg_temporal (agg_temporal) id=agg_temporal_sec_113
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2023 GROUP BY fiscal_period;

-- Query 114: agg_temporal (agg_temporal) id=agg_temporal_sec_114
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2023 GROUP BY company.sic_description;

-- Query 115: agg_temporal (agg_temporal) id=agg_temporal_sec_115
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2024 GROUP BY fiscal_period;

-- Query 116: agg_temporal (agg_temporal) id=agg_temporal_sec_116
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2024 GROUP BY company.sic_description;

-- Query 117: agg_temporal (agg_temporal) id=agg_temporal_sec_117
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2025 GROUP BY fiscal_period;

-- Query 118: agg_temporal (agg_temporal) id=agg_temporal_sec_118
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2025 GROUP BY company.sic_description;

-- Query 119: agg_temporal (agg_temporal) id=agg_temporal_sec_119
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2026 GROUP BY fiscal_period;

-- Query 120: agg_temporal (agg_temporal) id=agg_temporal_sec_120
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2026 GROUP BY company.sic_description;

-- Query 121: agg_temporal (agg_temporal) id=agg_temporal_sec_121
SELECT fiscal_year, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 122: agg_temporal (agg_temporal) id=agg_temporal_sec_122
SELECT fiscal_year, fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 123: agg_temporal (agg_temporal) id=agg_temporal_sec_123
SELECT company.ticker, fiscal_year, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 124: agg_temporal (agg_temporal) id=agg_temporal_sec_124
SELECT fiscal_year, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 125: agg_temporal (agg_temporal) id=agg_temporal_sec_125
SELECT fiscal_year, fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 126: agg_temporal (agg_temporal) id=agg_temporal_sec_126
SELECT company.ticker, fiscal_year, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 127: agg_temporal (agg_temporal) id=agg_temporal_sec_127
SELECT fiscal_year, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 128: agg_temporal (agg_temporal) id=agg_temporal_sec_128
SELECT fiscal_year, fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 129: agg_temporal (agg_temporal) id=agg_temporal_sec_129
SELECT company.ticker, fiscal_year, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 130: agg_temporal (agg_temporal) id=agg_temporal_sec_130
SELECT fiscal_year, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 131: agg_temporal (agg_temporal) id=agg_temporal_sec_131
SELECT fiscal_year, fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 132: agg_temporal (agg_temporal) id=agg_temporal_sec_132
SELECT company.ticker, fiscal_year, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 133: agg_temporal (agg_temporal) id=agg_temporal_sec_133
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2021 GROUP BY fiscal_period;

-- Query 134: agg_temporal (agg_temporal) id=agg_temporal_sec_134
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2021 GROUP BY company.sic_description;

-- Query 135: agg_temporal (agg_temporal) id=agg_temporal_sec_135
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2022 GROUP BY fiscal_period;

-- Query 136: agg_temporal (agg_temporal) id=agg_temporal_sec_136
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2022 GROUP BY company.sic_description;

-- Query 137: agg_temporal (agg_temporal) id=agg_temporal_sec_137
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2023 GROUP BY fiscal_period;

-- Query 138: agg_temporal (agg_temporal) id=agg_temporal_sec_138
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2023 GROUP BY company.sic_description;

-- Query 139: agg_temporal (agg_temporal) id=agg_temporal_sec_139
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2024 GROUP BY fiscal_period;

-- Query 140: agg_temporal (agg_temporal) id=agg_temporal_sec_140
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2024 GROUP BY company.sic_description;

-- Query 141: agg_temporal (agg_temporal) id=agg_temporal_sec_141
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2025 GROUP BY fiscal_period;

-- Query 142: agg_temporal (agg_temporal) id=agg_temporal_sec_142
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2025 GROUP BY company.sic_description;

-- Query 143: agg_temporal (agg_temporal) id=agg_temporal_sec_143
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2026 GROUP BY fiscal_period;

-- Query 144: agg_temporal (agg_temporal) id=agg_temporal_sec_144
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2026 GROUP BY company.sic_description;

-- Query 145: agg_temporal (agg_temporal) id=agg_temporal_sec_145
SELECT fiscal_year, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 146: agg_temporal (agg_temporal) id=agg_temporal_sec_146
SELECT fiscal_year, fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 147: agg_temporal (agg_temporal) id=agg_temporal_sec_147
SELECT company.ticker, fiscal_year, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 148: agg_temporal (agg_temporal) id=agg_temporal_sec_148
SELECT fiscal_year, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 149: agg_temporal (agg_temporal) id=agg_temporal_sec_149
SELECT fiscal_year, fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 150: agg_temporal (agg_temporal) id=agg_temporal_sec_150
SELECT company.ticker, fiscal_year, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 151: agg_temporal (agg_temporal) id=agg_temporal_sec_151
SELECT fiscal_year, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 152: agg_temporal (agg_temporal) id=agg_temporal_sec_152
SELECT fiscal_year, fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 153: agg_temporal (agg_temporal) id=agg_temporal_sec_153
SELECT company.ticker, fiscal_year, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 154: agg_temporal (agg_temporal) id=agg_temporal_sec_154
SELECT fiscal_year, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year;

-- Query 155: agg_temporal (agg_temporal) id=agg_temporal_sec_155
SELECT fiscal_year, fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 156: agg_temporal (agg_temporal) id=agg_temporal_sec_156
SELECT company.ticker, fiscal_year, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 157: agg_temporal (agg_temporal) id=agg_temporal_sec_157
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2021 GROUP BY fiscal_period;

-- Query 158: agg_temporal (agg_temporal) id=agg_temporal_sec_158
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2021 GROUP BY company.sic_description;

-- Query 159: agg_temporal (agg_temporal) id=agg_temporal_sec_159
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2022 GROUP BY fiscal_period;

-- Query 160: agg_temporal (agg_temporal) id=agg_temporal_sec_160
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2022 GROUP BY company.sic_description;

-- Query 161: agg_temporal (agg_temporal) id=agg_temporal_sec_161
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2023 GROUP BY fiscal_period;

-- Query 162: agg_temporal (agg_temporal) id=agg_temporal_sec_162
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2023 GROUP BY company.sic_description;

-- Query 163: agg_temporal (agg_temporal) id=agg_temporal_sec_163
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2024 GROUP BY fiscal_period;

-- Query 164: agg_temporal (agg_temporal) id=agg_temporal_sec_164
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2024 GROUP BY company.sic_description;

-- Query 165: agg_temporal (agg_temporal) id=agg_temporal_sec_165
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2025 GROUP BY fiscal_period;

-- Query 166: agg_temporal (agg_temporal) id=agg_temporal_sec_166
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2025 GROUP BY company.sic_description;

-- Query 167: agg_temporal (agg_temporal) id=agg_temporal_sec_167
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_year = 2026 GROUP BY fiscal_period;

-- Query 168: agg_temporal (agg_temporal) id=agg_temporal_sec_168
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2026 GROUP BY company.sic_description;

-- Query 169: agg_temporal (agg_temporal) id=agg_temporal_sec_169
SELECT fiscal_year, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics GROUP BY fiscal_year;

-- Query 170: agg_temporal (agg_temporal) id=agg_temporal_sec_170
SELECT fiscal_year, fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 171: agg_temporal (agg_temporal) id=agg_temporal_sec_171
SELECT company.ticker, fiscal_year, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 172: agg_temporal (agg_temporal) id=agg_temporal_sec_172
SELECT fiscal_year, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics GROUP BY fiscal_year;

-- Query 173: agg_temporal (agg_temporal) id=agg_temporal_sec_173
SELECT fiscal_year, fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 174: agg_temporal (agg_temporal) id=agg_temporal_sec_174
SELECT company.ticker, fiscal_year, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 175: agg_temporal (agg_temporal) id=agg_temporal_sec_175
SELECT fiscal_year, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics GROUP BY fiscal_year;

-- Query 176: agg_temporal (agg_temporal) id=agg_temporal_sec_176
SELECT fiscal_year, fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 177: agg_temporal (agg_temporal) id=agg_temporal_sec_177
SELECT company.ticker, fiscal_year, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 178: agg_temporal (agg_temporal) id=agg_temporal_sec_178
SELECT fiscal_year, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics GROUP BY fiscal_year;

-- Query 179: agg_temporal (agg_temporal) id=agg_temporal_sec_179
SELECT fiscal_year, fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics GROUP BY fiscal_year, fiscal_period;

-- Query 180: agg_temporal (agg_temporal) id=agg_temporal_sec_180
SELECT company.ticker, fiscal_year, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id GROUP BY company.ticker, fiscal_year;

-- Query 181: agg_temporal (agg_temporal) id=agg_temporal_sec_181
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_year = 2021 GROUP BY fiscal_period;

-- Query 182: agg_temporal (agg_temporal) id=agg_temporal_sec_182
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2021 GROUP BY company.sic_description;

-- Query 183: agg_temporal (agg_temporal) id=agg_temporal_sec_183
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_year = 2022 GROUP BY fiscal_period;

-- Query 184: agg_temporal (agg_temporal) id=agg_temporal_sec_184
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2022 GROUP BY company.sic_description;

-- Query 185: agg_temporal (agg_temporal) id=agg_temporal_sec_185
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_year = 2023 GROUP BY fiscal_period;

-- Query 186: agg_temporal (agg_temporal) id=agg_temporal_sec_186
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2023 GROUP BY company.sic_description;

-- Query 187: agg_temporal (agg_temporal) id=agg_temporal_sec_187
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_year = 2024 GROUP BY fiscal_period;

-- Query 188: agg_temporal (agg_temporal) id=agg_temporal_sec_188
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2024 GROUP BY company.sic_description;

-- Query 189: agg_temporal (agg_temporal) id=agg_temporal_sec_189
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_year = 2025 GROUP BY fiscal_period;

-- Query 190: agg_temporal (agg_temporal) id=agg_temporal_sec_190
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2025 GROUP BY company.sic_description;

-- Query 191: agg_temporal (agg_temporal) id=agg_temporal_sec_191
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_year = 2026 GROUP BY fiscal_period;

-- Query 192: agg_temporal (agg_temporal) id=agg_temporal_sec_192
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id WHERE filing_metrics.fiscal_year = 2026 GROUP BY company.sic_description;
