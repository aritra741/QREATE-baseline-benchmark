-- Query 1: agg_filter (agg_filter) id=agg_filter_sec_1
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 2: agg_filter (agg_filter) id=agg_filter_sec_2
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 3: agg_filter (agg_filter) id=agg_filter_sec_3
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 4: agg_filter (agg_filter) id=agg_filter_sec_4
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 5: agg_filter (agg_filter) id=agg_filter_sec_5
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 6: agg_filter (agg_filter) id=agg_filter_sec_6
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 7: agg_filter (agg_filter) id=agg_filter_sec_7
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 8: agg_filter (agg_filter) id=agg_filter_sec_8
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 9: agg_filter (agg_filter) id=agg_filter_sec_9
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 10: agg_filter (agg_filter) id=agg_filter_sec_10
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 11: agg_filter (agg_filter) id=agg_filter_sec_11
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 12: agg_filter (agg_filter) id=agg_filter_sec_12
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 13: agg_filter (agg_filter) id=agg_filter_sec_13
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 14: agg_filter (agg_filter) id=agg_filter_sec_14
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 15: agg_filter (agg_filter) id=agg_filter_sec_15
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 16: agg_filter (agg_filter) id=agg_filter_sec_16
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 17: agg_filter (agg_filter) id=agg_filter_sec_17
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 18: agg_filter (agg_filter) id=agg_filter_sec_18
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 19: agg_filter (agg_filter) id=agg_filter_sec_19
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 20: agg_filter (agg_filter) id=agg_filter_sec_20
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 21: agg_filter (agg_filter) id=agg_filter_sec_21
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 22: agg_filter (agg_filter) id=agg_filter_sec_22
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 23: agg_filter (agg_filter) id=agg_filter_sec_23
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 24: agg_filter (agg_filter) id=agg_filter_sec_24
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 25: agg_filter (agg_filter) id=agg_filter_sec_25
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 26: agg_filter (agg_filter) id=agg_filter_sec_26
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 27: agg_filter (agg_filter) id=agg_filter_sec_27
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 28: agg_filter (agg_filter) id=agg_filter_sec_28
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 29: agg_filter (agg_filter) id=agg_filter_sec_29
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 30: agg_filter (agg_filter) id=agg_filter_sec_30
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 31: agg_filter (agg_filter) id=agg_filter_sec_31
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 32: agg_filter (agg_filter) id=agg_filter_sec_32
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 33: agg_filter (agg_filter) id=agg_filter_sec_33
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 34: agg_filter (agg_filter) id=agg_filter_sec_34
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 35: agg_filter (agg_filter) id=agg_filter_sec_35
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 36: agg_filter (agg_filter) id=agg_filter_sec_36
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 37: agg_filter (agg_filter) id=agg_filter_sec_37
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 38: agg_filter (agg_filter) id=agg_filter_sec_38
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 39: agg_filter (agg_filter) id=agg_filter_sec_39
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 40: agg_filter (agg_filter) id=agg_filter_sec_40
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 41: agg_filter (agg_filter) id=agg_filter_sec_41
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 42: agg_filter (agg_filter) id=agg_filter_sec_42
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 43: agg_filter (agg_filter) id=agg_filter_sec_43
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 44: agg_filter (agg_filter) id=agg_filter_sec_44
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 45: agg_filter (agg_filter) id=agg_filter_sec_45
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 46: agg_filter (agg_filter) id=agg_filter_sec_46
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 47: agg_filter (agg_filter) id=agg_filter_sec_47
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 48: agg_filter (agg_filter) id=agg_filter_sec_48
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 49: agg_filter (agg_filter) id=agg_filter_sec_49
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 50: agg_filter (agg_filter) id=agg_filter_sec_50
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 51: agg_filter (agg_filter) id=agg_filter_sec_51
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 52: agg_filter (agg_filter) id=agg_filter_sec_52
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 53: agg_filter (agg_filter) id=agg_filter_sec_53
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 54: agg_filter (agg_filter) id=agg_filter_sec_54
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 55: agg_filter (agg_filter) id=agg_filter_sec_55
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 56: agg_filter (agg_filter) id=agg_filter_sec_56
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 57: agg_filter (agg_filter) id=agg_filter_sec_57
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 58: agg_filter (agg_filter) id=agg_filter_sec_58
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 59: agg_filter (agg_filter) id=agg_filter_sec_59
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 60: agg_filter (agg_filter) id=agg_filter_sec_60
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 61: agg_filter (agg_filter) id=agg_filter_sec_61
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 62: agg_filter (agg_filter) id=agg_filter_sec_62
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 63: agg_filter (agg_filter) id=agg_filter_sec_63
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 64: agg_filter (agg_filter) id=agg_filter_sec_64
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 65: agg_filter (agg_filter) id=agg_filter_sec_65
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 66: agg_filter (agg_filter) id=agg_filter_sec_66
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 67: agg_filter (agg_filter) id=agg_filter_sec_67
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 68: agg_filter (agg_filter) id=agg_filter_sec_68
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 69: agg_filter (agg_filter) id=agg_filter_sec_69
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 70: agg_filter (agg_filter) id=agg_filter_sec_70
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 71: agg_filter (agg_filter) id=agg_filter_sec_71
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 72: agg_filter (agg_filter) id=agg_filter_sec_72
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 73: agg_filter (agg_filter) id=agg_filter_sec_73
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 74: agg_filter (agg_filter) id=agg_filter_sec_74
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 75: agg_filter (agg_filter) id=agg_filter_sec_75
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 76: agg_filter (agg_filter) id=agg_filter_sec_76
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 77: agg_filter (agg_filter) id=agg_filter_sec_77
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 78: agg_filter (agg_filter) id=agg_filter_sec_78
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 79: agg_filter (agg_filter) id=agg_filter_sec_79
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 80: agg_filter (agg_filter) id=agg_filter_sec_80
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 81: agg_filter (agg_filter) id=agg_filter_sec_81
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 82: agg_filter (agg_filter) id=agg_filter_sec_82
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 83: agg_filter (agg_filter) id=agg_filter_sec_83
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 84: agg_filter (agg_filter) id=agg_filter_sec_84
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 85: agg_filter (agg_filter) id=agg_filter_sec_85
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 86: agg_filter (agg_filter) id=agg_filter_sec_86
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 87: agg_filter (agg_filter) id=agg_filter_sec_87
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 88: agg_filter (agg_filter) id=agg_filter_sec_88
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 89: agg_filter (agg_filter) id=agg_filter_sec_89
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 90: agg_filter (agg_filter) id=agg_filter_sec_90
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 91: agg_filter (agg_filter) id=agg_filter_sec_91
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 92: agg_filter (agg_filter) id=agg_filter_sec_92
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 93: agg_filter (agg_filter) id=agg_filter_sec_93
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 94: agg_filter (agg_filter) id=agg_filter_sec_94
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 95: agg_filter (agg_filter) id=agg_filter_sec_95
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 96: agg_filter (agg_filter) id=agg_filter_sec_96
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 97: agg_filter (agg_filter) id=agg_filter_sec_97
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 98: agg_filter (agg_filter) id=agg_filter_sec_98
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 99: agg_filter (agg_filter) id=agg_filter_sec_99
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 100: agg_filter (agg_filter) id=agg_filter_sec_100
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 101: agg_filter (agg_filter) id=agg_filter_sec_101
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 102: agg_filter (agg_filter) id=agg_filter_sec_102
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 103: agg_filter (agg_filter) id=agg_filter_sec_103
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 104: agg_filter (agg_filter) id=agg_filter_sec_104
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 105: agg_filter (agg_filter) id=agg_filter_sec_105
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 106: agg_filter (agg_filter) id=agg_filter_sec_106
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 107: agg_filter (agg_filter) id=agg_filter_sec_107
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 108: agg_filter (agg_filter) id=agg_filter_sec_108
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 109: agg_filter (agg_filter) id=agg_filter_sec_109
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 110: agg_filter (agg_filter) id=agg_filter_sec_110
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 111: agg_filter (agg_filter) id=agg_filter_sec_111
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 112: agg_filter (agg_filter) id=agg_filter_sec_112
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 113: agg_filter (agg_filter) id=agg_filter_sec_113
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 114: agg_filter (agg_filter) id=agg_filter_sec_114
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 115: agg_filter (agg_filter) id=agg_filter_sec_115
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 116: agg_filter (agg_filter) id=agg_filter_sec_116
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 117: agg_filter (agg_filter) id=agg_filter_sec_117
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 118: agg_filter (agg_filter) id=agg_filter_sec_118
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 119: agg_filter (agg_filter) id=agg_filter_sec_119
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 120: agg_filter (agg_filter) id=agg_filter_sec_120
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 121: agg_filter (agg_filter) id=agg_filter_sec_121
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 122: agg_filter (agg_filter) id=agg_filter_sec_122
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 123: agg_filter (agg_filter) id=agg_filter_sec_123
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 124: agg_filter (agg_filter) id=agg_filter_sec_124
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 125: agg_filter (agg_filter) id=agg_filter_sec_125
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 126: agg_filter (agg_filter) id=agg_filter_sec_126
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 127: agg_filter (agg_filter) id=agg_filter_sec_127
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 128: agg_filter (agg_filter) id=agg_filter_sec_128
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 129: agg_filter (agg_filter) id=agg_filter_sec_129
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 130: agg_filter (agg_filter) id=agg_filter_sec_130
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 131: agg_filter (agg_filter) id=agg_filter_sec_131
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 132: agg_filter (agg_filter) id=agg_filter_sec_132
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 133: agg_filter (agg_filter) id=agg_filter_sec_133
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 134: agg_filter (agg_filter) id=agg_filter_sec_134
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 135: agg_filter (agg_filter) id=agg_filter_sec_135
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 136: agg_filter (agg_filter) id=agg_filter_sec_136
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 137: agg_filter (agg_filter) id=agg_filter_sec_137
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 138: agg_filter (agg_filter) id=agg_filter_sec_138
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 139: agg_filter (agg_filter) id=agg_filter_sec_139
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 140: agg_filter (agg_filter) id=agg_filter_sec_140
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 141: agg_filter (agg_filter) id=agg_filter_sec_141
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 142: agg_filter (agg_filter) id=agg_filter_sec_142
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 143: agg_filter (agg_filter) id=agg_filter_sec_143
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 144: agg_filter (agg_filter) id=agg_filter_sec_144
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 145: agg_filter (agg_filter) id=agg_filter_sec_145
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 146: agg_filter (agg_filter) id=agg_filter_sec_146
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 147: agg_filter (agg_filter) id=agg_filter_sec_147
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 148: agg_filter (agg_filter) id=agg_filter_sec_148
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 149: agg_filter (agg_filter) id=agg_filter_sec_149
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 150: agg_filter (agg_filter) id=agg_filter_sec_150
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 151: agg_filter (agg_filter) id=agg_filter_sec_151
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 152: agg_filter (agg_filter) id=agg_filter_sec_152
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 153: agg_filter (agg_filter) id=agg_filter_sec_153
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 154: agg_filter (agg_filter) id=agg_filter_sec_154
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 155: agg_filter (agg_filter) id=agg_filter_sec_155
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 156: agg_filter (agg_filter) id=agg_filter_sec_156
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 157: agg_filter (agg_filter) id=agg_filter_sec_157
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 158: agg_filter (agg_filter) id=agg_filter_sec_158
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 159: agg_filter (agg_filter) id=agg_filter_sec_159
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 160: agg_filter (agg_filter) id=agg_filter_sec_160
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 161: agg_filter (agg_filter) id=agg_filter_sec_161
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 162: agg_filter (agg_filter) id=agg_filter_sec_162
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 163: agg_filter (agg_filter) id=agg_filter_sec_163
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 164: agg_filter (agg_filter) id=agg_filter_sec_164
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 165: agg_filter (agg_filter) id=agg_filter_sec_165
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 166: agg_filter (agg_filter) id=agg_filter_sec_166
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 167: agg_filter (agg_filter) id=agg_filter_sec_167
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 168: agg_filter (agg_filter) id=agg_filter_sec_168
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 169: agg_filter (agg_filter) id=agg_filter_sec_169
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 170: agg_filter (agg_filter) id=agg_filter_sec_170
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 171: agg_filter (agg_filter) id=agg_filter_sec_171
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 172: agg_filter (agg_filter) id=agg_filter_sec_172
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 173: agg_filter (agg_filter) id=agg_filter_sec_173
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 174: agg_filter (agg_filter) id=agg_filter_sec_174
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 175: agg_filter (agg_filter) id=agg_filter_sec_175
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 176: agg_filter (agg_filter) id=agg_filter_sec_176
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 177: agg_filter (agg_filter) id=agg_filter_sec_177
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 178: agg_filter (agg_filter) id=agg_filter_sec_178
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 179: agg_filter (agg_filter) id=agg_filter_sec_179
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 180: agg_filter (agg_filter) id=agg_filter_sec_180
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 181: agg_filter (agg_filter) id=agg_filter_sec_181
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 182: agg_filter (agg_filter) id=agg_filter_sec_182
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 183: agg_filter (agg_filter) id=agg_filter_sec_183
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 184: agg_filter (agg_filter) id=agg_filter_sec_184
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 185: agg_filter (agg_filter) id=agg_filter_sec_185
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 186: agg_filter (agg_filter) id=agg_filter_sec_186
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 187: agg_filter (agg_filter) id=agg_filter_sec_187
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 188: agg_filter (agg_filter) id=agg_filter_sec_188
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 189: agg_filter (agg_filter) id=agg_filter_sec_189
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 190: agg_filter (agg_filter) id=agg_filter_sec_190
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 191: agg_filter (agg_filter) id=agg_filter_sec_191
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 192: agg_filter (agg_filter) id=agg_filter_sec_192
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 193: agg_filter (agg_filter) id=agg_filter_sec_193
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 194: agg_filter (agg_filter) id=agg_filter_sec_194
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 195: agg_filter (agg_filter) id=agg_filter_sec_195
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 196: agg_filter (agg_filter) id=agg_filter_sec_196
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 197: agg_filter (agg_filter) id=agg_filter_sec_197
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 198: agg_filter (agg_filter) id=agg_filter_sec_198
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 199: agg_filter (agg_filter) id=agg_filter_sec_199
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 200: agg_filter (agg_filter) id=agg_filter_sec_200
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 201: agg_filter (agg_filter) id=agg_filter_sec_201
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 202: agg_filter (agg_filter) id=agg_filter_sec_202
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 203: agg_filter (agg_filter) id=agg_filter_sec_203
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 204: agg_filter (agg_filter) id=agg_filter_sec_204
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 205: agg_filter (agg_filter) id=agg_filter_sec_205
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 206: agg_filter (agg_filter) id=agg_filter_sec_206
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 207: agg_filter (agg_filter) id=agg_filter_sec_207
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 208: agg_filter (agg_filter) id=agg_filter_sec_208
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 209: agg_filter (agg_filter) id=agg_filter_sec_209
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 210: agg_filter (agg_filter) id=agg_filter_sec_210
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 211: agg_filter (agg_filter) id=agg_filter_sec_211
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 212: agg_filter (agg_filter) id=agg_filter_sec_212
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 213: agg_filter (agg_filter) id=agg_filter_sec_213
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 214: agg_filter (agg_filter) id=agg_filter_sec_214
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 215: agg_filter (agg_filter) id=agg_filter_sec_215
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 216: agg_filter (agg_filter) id=agg_filter_sec_216
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 217: agg_filter (agg_filter) id=agg_filter_sec_217
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 218: agg_filter (agg_filter) id=agg_filter_sec_218
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 219: agg_filter (agg_filter) id=agg_filter_sec_219
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 220: agg_filter (agg_filter) id=agg_filter_sec_220
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 221: agg_filter (agg_filter) id=agg_filter_sec_221
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 222: agg_filter (agg_filter) id=agg_filter_sec_222
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 223: agg_filter (agg_filter) id=agg_filter_sec_223
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 224: agg_filter (agg_filter) id=agg_filter_sec_224
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 225: agg_filter (agg_filter) id=agg_filter_sec_225
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 226: agg_filter (agg_filter) id=agg_filter_sec_226
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 227: agg_filter (agg_filter) id=agg_filter_sec_227
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 228: agg_filter (agg_filter) id=agg_filter_sec_228
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 229: agg_filter (agg_filter) id=agg_filter_sec_229
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 230: agg_filter (agg_filter) id=agg_filter_sec_230
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 231: agg_filter (agg_filter) id=agg_filter_sec_231
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 232: agg_filter (agg_filter) id=agg_filter_sec_232
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 233: agg_filter (agg_filter) id=agg_filter_sec_233
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 234: agg_filter (agg_filter) id=agg_filter_sec_234
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 235: agg_filter (agg_filter) id=agg_filter_sec_235
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 236: agg_filter (agg_filter) id=agg_filter_sec_236
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 237: agg_filter (agg_filter) id=agg_filter_sec_237
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 238: agg_filter (agg_filter) id=agg_filter_sec_238
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 239: agg_filter (agg_filter) id=agg_filter_sec_239
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 240: agg_filter (agg_filter) id=agg_filter_sec_240
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 241: agg_filter (agg_filter) id=agg_filter_sec_241
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 242: agg_filter (agg_filter) id=agg_filter_sec_242
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 243: agg_filter (agg_filter) id=agg_filter_sec_243
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 244: agg_filter (agg_filter) id=agg_filter_sec_244
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 245: agg_filter (agg_filter) id=agg_filter_sec_245
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 246: agg_filter (agg_filter) id=agg_filter_sec_246
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 247: agg_filter (agg_filter) id=agg_filter_sec_247
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 248: agg_filter (agg_filter) id=agg_filter_sec_248
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 249: agg_filter (agg_filter) id=agg_filter_sec_249
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 250: agg_filter (agg_filter) id=agg_filter_sec_250
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 251: agg_filter (agg_filter) id=agg_filter_sec_251
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 252: agg_filter (agg_filter) id=agg_filter_sec_252
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 253: agg_filter (agg_filter) id=agg_filter_sec_253
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 254: agg_filter (agg_filter) id=agg_filter_sec_254
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 255: agg_filter (agg_filter) id=agg_filter_sec_255
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 256: agg_filter (agg_filter) id=agg_filter_sec_256
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 257: agg_filter (agg_filter) id=agg_filter_sec_257
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 258: agg_filter (agg_filter) id=agg_filter_sec_258
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 259: agg_filter (agg_filter) id=agg_filter_sec_259
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 260: agg_filter (agg_filter) id=agg_filter_sec_260
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 261: agg_filter (agg_filter) id=agg_filter_sec_261
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 262: agg_filter (agg_filter) id=agg_filter_sec_262
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 263: agg_filter (agg_filter) id=agg_filter_sec_263
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 264: agg_filter (agg_filter) id=agg_filter_sec_264
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 265: agg_filter (agg_filter) id=agg_filter_sec_265
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 266: agg_filter (agg_filter) id=agg_filter_sec_266
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 267: agg_filter (agg_filter) id=agg_filter_sec_267
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 268: agg_filter (agg_filter) id=agg_filter_sec_268
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 269: agg_filter (agg_filter) id=agg_filter_sec_269
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 270: agg_filter (agg_filter) id=agg_filter_sec_270
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 271: agg_filter (agg_filter) id=agg_filter_sec_271
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 272: agg_filter (agg_filter) id=agg_filter_sec_272
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 273: agg_filter (agg_filter) id=agg_filter_sec_273
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 274: agg_filter (agg_filter) id=agg_filter_sec_274
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 275: agg_filter (agg_filter) id=agg_filter_sec_275
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 276: agg_filter (agg_filter) id=agg_filter_sec_276
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 277: agg_filter (agg_filter) id=agg_filter_sec_277
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 278: agg_filter (agg_filter) id=agg_filter_sec_278
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 279: agg_filter (agg_filter) id=agg_filter_sec_279
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 280: agg_filter (agg_filter) id=agg_filter_sec_280
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 281: agg_filter (agg_filter) id=agg_filter_sec_281
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 282: agg_filter (agg_filter) id=agg_filter_sec_282
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 283: agg_filter (agg_filter) id=agg_filter_sec_283
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 284: agg_filter (agg_filter) id=agg_filter_sec_284
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 285: agg_filter (agg_filter) id=agg_filter_sec_285
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 286: agg_filter (agg_filter) id=agg_filter_sec_286
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 287: agg_filter (agg_filter) id=agg_filter_sec_287
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 288: agg_filter (agg_filter) id=agg_filter_sec_288
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 289: agg_filter (agg_filter) id=agg_filter_sec_289
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 290: agg_filter (agg_filter) id=agg_filter_sec_290
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 291: agg_filter (agg_filter) id=agg_filter_sec_291
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 292: agg_filter (agg_filter) id=agg_filter_sec_292
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 293: agg_filter (agg_filter) id=agg_filter_sec_293
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 294: agg_filter (agg_filter) id=agg_filter_sec_294
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 295: agg_filter (agg_filter) id=agg_filter_sec_295
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 296: agg_filter (agg_filter) id=agg_filter_sec_296
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 297: agg_filter (agg_filter) id=agg_filter_sec_297
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 298: agg_filter (agg_filter) id=agg_filter_sec_298
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 299: agg_filter (agg_filter) id=agg_filter_sec_299
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 300: agg_filter (agg_filter) id=agg_filter_sec_300
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 301: agg_filter (agg_filter) id=agg_filter_sec_301
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 302: agg_filter (agg_filter) id=agg_filter_sec_302
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 303: agg_filter (agg_filter) id=agg_filter_sec_303
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 304: agg_filter (agg_filter) id=agg_filter_sec_304
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 305: agg_filter (agg_filter) id=agg_filter_sec_305
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 306: agg_filter (agg_filter) id=agg_filter_sec_306
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 307: agg_filter (agg_filter) id=agg_filter_sec_307
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 308: agg_filter (agg_filter) id=agg_filter_sec_308
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 309: agg_filter (agg_filter) id=agg_filter_sec_309
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 310: agg_filter (agg_filter) id=agg_filter_sec_310
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 311: agg_filter (agg_filter) id=agg_filter_sec_311
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 312: agg_filter (agg_filter) id=agg_filter_sec_312
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 313: agg_filter (agg_filter) id=agg_filter_sec_313
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 314: agg_filter (agg_filter) id=agg_filter_sec_314
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 315: agg_filter (agg_filter) id=agg_filter_sec_315
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 316: agg_filter (agg_filter) id=agg_filter_sec_316
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 317: agg_filter (agg_filter) id=agg_filter_sec_317
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 318: agg_filter (agg_filter) id=agg_filter_sec_318
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 319: agg_filter (agg_filter) id=agg_filter_sec_319
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 320: agg_filter (agg_filter) id=agg_filter_sec_320
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 321: agg_filter (agg_filter) id=agg_filter_sec_321
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 322: agg_filter (agg_filter) id=agg_filter_sec_322
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 323: agg_filter (agg_filter) id=agg_filter_sec_323
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 324: agg_filter (agg_filter) id=agg_filter_sec_324
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 325: agg_filter (agg_filter) id=agg_filter_sec_325
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 326: agg_filter (agg_filter) id=agg_filter_sec_326
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 327: agg_filter (agg_filter) id=agg_filter_sec_327
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 328: agg_filter (agg_filter) id=agg_filter_sec_328
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 329: agg_filter (agg_filter) id=agg_filter_sec_329
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 330: agg_filter (agg_filter) id=agg_filter_sec_330
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 331: agg_filter (agg_filter) id=agg_filter_sec_331
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 332: agg_filter (agg_filter) id=agg_filter_sec_332
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 333: agg_filter (agg_filter) id=agg_filter_sec_333
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 334: agg_filter (agg_filter) id=agg_filter_sec_334
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 335: agg_filter (agg_filter) id=agg_filter_sec_335
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 336: agg_filter (agg_filter) id=agg_filter_sec_336
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 337: agg_filter (agg_filter) id=agg_filter_sec_337
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 338: agg_filter (agg_filter) id=agg_filter_sec_338
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 339: agg_filter (agg_filter) id=agg_filter_sec_339
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 340: agg_filter (agg_filter) id=agg_filter_sec_340
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 341: agg_filter (agg_filter) id=agg_filter_sec_341
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 342: agg_filter (agg_filter) id=agg_filter_sec_342
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 343: agg_filter (agg_filter) id=agg_filter_sec_343
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 344: agg_filter (agg_filter) id=agg_filter_sec_344
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 345: agg_filter (agg_filter) id=agg_filter_sec_345
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 346: agg_filter (agg_filter) id=agg_filter_sec_346
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 347: agg_filter (agg_filter) id=agg_filter_sec_347
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 348: agg_filter (agg_filter) id=agg_filter_sec_348
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 349: agg_filter (agg_filter) id=agg_filter_sec_349
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 350: agg_filter (agg_filter) id=agg_filter_sec_350
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 351: agg_filter (agg_filter) id=agg_filter_sec_351
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 352: agg_filter (agg_filter) id=agg_filter_sec_352
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 353: agg_filter (agg_filter) id=agg_filter_sec_353
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 354: agg_filter (agg_filter) id=agg_filter_sec_354
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 355: agg_filter (agg_filter) id=agg_filter_sec_355
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 356: agg_filter (agg_filter) id=agg_filter_sec_356
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 357: agg_filter (agg_filter) id=agg_filter_sec_357
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 358: agg_filter (agg_filter) id=agg_filter_sec_358
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 359: agg_filter (agg_filter) id=agg_filter_sec_359
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 360: agg_filter (agg_filter) id=agg_filter_sec_360
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 361: agg_filter (agg_filter) id=agg_filter_sec_361
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 362: agg_filter (agg_filter) id=agg_filter_sec_362
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 363: agg_filter (agg_filter) id=agg_filter_sec_363
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 364: agg_filter (agg_filter) id=agg_filter_sec_364
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 365: agg_filter (agg_filter) id=agg_filter_sec_365
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 366: agg_filter (agg_filter) id=agg_filter_sec_366
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 367: agg_filter (agg_filter) id=agg_filter_sec_367
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 368: agg_filter (agg_filter) id=agg_filter_sec_368
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 369: agg_filter (agg_filter) id=agg_filter_sec_369
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 370: agg_filter (agg_filter) id=agg_filter_sec_370
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 371: agg_filter (agg_filter) id=agg_filter_sec_371
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 372: agg_filter (agg_filter) id=agg_filter_sec_372
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 373: agg_filter (agg_filter) id=agg_filter_sec_373
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 374: agg_filter (agg_filter) id=agg_filter_sec_374
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 375: agg_filter (agg_filter) id=agg_filter_sec_375
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 376: agg_filter (agg_filter) id=agg_filter_sec_376
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 377: agg_filter (agg_filter) id=agg_filter_sec_377
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 378: agg_filter (agg_filter) id=agg_filter_sec_378
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 379: agg_filter (agg_filter) id=agg_filter_sec_379
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 380: agg_filter (agg_filter) id=agg_filter_sec_380
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 381: agg_filter (agg_filter) id=agg_filter_sec_381
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 382: agg_filter (agg_filter) id=agg_filter_sec_382
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 383: agg_filter (agg_filter) id=agg_filter_sec_383
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 384: agg_filter (agg_filter) id=agg_filter_sec_384
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 385: agg_filter (agg_filter) id=agg_filter_sec_385
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 386: agg_filter (agg_filter) id=agg_filter_sec_386
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 387: agg_filter (agg_filter) id=agg_filter_sec_387
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 388: agg_filter (agg_filter) id=agg_filter_sec_388
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 389: agg_filter (agg_filter) id=agg_filter_sec_389
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 390: agg_filter (agg_filter) id=agg_filter_sec_390
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 391: agg_filter (agg_filter) id=agg_filter_sec_391
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 392: agg_filter (agg_filter) id=agg_filter_sec_392
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 393: agg_filter (agg_filter) id=agg_filter_sec_393
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 394: agg_filter (agg_filter) id=agg_filter_sec_394
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 395: agg_filter (agg_filter) id=agg_filter_sec_395
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 396: agg_filter (agg_filter) id=agg_filter_sec_396
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 397: agg_filter (agg_filter) id=agg_filter_sec_397
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 398: agg_filter (agg_filter) id=agg_filter_sec_398
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 399: agg_filter (agg_filter) id=agg_filter_sec_399
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 400: agg_filter (agg_filter) id=agg_filter_sec_400
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 401: agg_filter (agg_filter) id=agg_filter_sec_401
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 402: agg_filter (agg_filter) id=agg_filter_sec_402
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 403: agg_filter (agg_filter) id=agg_filter_sec_403
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 404: agg_filter (agg_filter) id=agg_filter_sec_404
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 405: agg_filter (agg_filter) id=agg_filter_sec_405
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 406: agg_filter (agg_filter) id=agg_filter_sec_406
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 407: agg_filter (agg_filter) id=agg_filter_sec_407
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 408: agg_filter (agg_filter) id=agg_filter_sec_408
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 409: agg_filter (agg_filter) id=agg_filter_sec_409
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 410: agg_filter (agg_filter) id=agg_filter_sec_410
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 411: agg_filter (agg_filter) id=agg_filter_sec_411
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 412: agg_filter (agg_filter) id=agg_filter_sec_412
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 413: agg_filter (agg_filter) id=agg_filter_sec_413
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 414: agg_filter (agg_filter) id=agg_filter_sec_414
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 415: agg_filter (agg_filter) id=agg_filter_sec_415
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 416: agg_filter (agg_filter) id=agg_filter_sec_416
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 417: agg_filter (agg_filter) id=agg_filter_sec_417
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 418: agg_filter (agg_filter) id=agg_filter_sec_418
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 419: agg_filter (agg_filter) id=agg_filter_sec_419
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 420: agg_filter (agg_filter) id=agg_filter_sec_420
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 421: agg_filter (agg_filter) id=agg_filter_sec_421
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 422: agg_filter (agg_filter) id=agg_filter_sec_422
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 423: agg_filter (agg_filter) id=agg_filter_sec_423
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 424: agg_filter (agg_filter) id=agg_filter_sec_424
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 425: agg_filter (agg_filter) id=agg_filter_sec_425
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 426: agg_filter (agg_filter) id=agg_filter_sec_426
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 427: agg_filter (agg_filter) id=agg_filter_sec_427
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 428: agg_filter (agg_filter) id=agg_filter_sec_428
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 429: agg_filter (agg_filter) id=agg_filter_sec_429
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 430: agg_filter (agg_filter) id=agg_filter_sec_430
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 431: agg_filter (agg_filter) id=agg_filter_sec_431
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 432: agg_filter (agg_filter) id=agg_filter_sec_432
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 433: agg_filter (agg_filter) id=agg_filter_sec_433
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 434: agg_filter (agg_filter) id=agg_filter_sec_434
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 435: agg_filter (agg_filter) id=agg_filter_sec_435
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 436: agg_filter (agg_filter) id=agg_filter_sec_436
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 437: agg_filter (agg_filter) id=agg_filter_sec_437
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 438: agg_filter (agg_filter) id=agg_filter_sec_438
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 439: agg_filter (agg_filter) id=agg_filter_sec_439
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 440: agg_filter (agg_filter) id=agg_filter_sec_440
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 441: agg_filter (agg_filter) id=agg_filter_sec_441
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 442: agg_filter (agg_filter) id=agg_filter_sec_442
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 443: agg_filter (agg_filter) id=agg_filter_sec_443
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 444: agg_filter (agg_filter) id=agg_filter_sec_444
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 445: agg_filter (agg_filter) id=agg_filter_sec_445
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 446: agg_filter (agg_filter) id=agg_filter_sec_446
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 447: agg_filter (agg_filter) id=agg_filter_sec_447
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 448: agg_filter (agg_filter) id=agg_filter_sec_448
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 449: agg_filter (agg_filter) id=agg_filter_sec_449
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 450: agg_filter (agg_filter) id=agg_filter_sec_450
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 451: agg_filter (agg_filter) id=agg_filter_sec_451
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 452: agg_filter (agg_filter) id=agg_filter_sec_452
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 453: agg_filter (agg_filter) id=agg_filter_sec_453
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 454: agg_filter (agg_filter) id=agg_filter_sec_454
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 455: agg_filter (agg_filter) id=agg_filter_sec_455
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 456: agg_filter (agg_filter) id=agg_filter_sec_456
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 457: agg_filter (agg_filter) id=agg_filter_sec_457
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 458: agg_filter (agg_filter) id=agg_filter_sec_458
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 459: agg_filter (agg_filter) id=agg_filter_sec_459
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 460: agg_filter (agg_filter) id=agg_filter_sec_460
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 461: agg_filter (agg_filter) id=agg_filter_sec_461
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 462: agg_filter (agg_filter) id=agg_filter_sec_462
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 463: agg_filter (agg_filter) id=agg_filter_sec_463
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 464: agg_filter (agg_filter) id=agg_filter_sec_464
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 465: agg_filter (agg_filter) id=agg_filter_sec_465
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 466: agg_filter (agg_filter) id=agg_filter_sec_466
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 467: agg_filter (agg_filter) id=agg_filter_sec_467
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 468: agg_filter (agg_filter) id=agg_filter_sec_468
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 469: agg_filter (agg_filter) id=agg_filter_sec_469
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 470: agg_filter (agg_filter) id=agg_filter_sec_470
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 471: agg_filter (agg_filter) id=agg_filter_sec_471
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 472: agg_filter (agg_filter) id=agg_filter_sec_472
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 473: agg_filter (agg_filter) id=agg_filter_sec_473
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 474: agg_filter (agg_filter) id=agg_filter_sec_474
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 475: agg_filter (agg_filter) id=agg_filter_sec_475
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 476: agg_filter (agg_filter) id=agg_filter_sec_476
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 477: agg_filter (agg_filter) id=agg_filter_sec_477
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 478: agg_filter (agg_filter) id=agg_filter_sec_478
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 479: agg_filter (agg_filter) id=agg_filter_sec_479
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 480: agg_filter (agg_filter) id=agg_filter_sec_480
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 481: agg_filter (agg_filter) id=agg_filter_sec_481
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 482: agg_filter (agg_filter) id=agg_filter_sec_482
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 483: agg_filter (agg_filter) id=agg_filter_sec_483
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 484: agg_filter (agg_filter) id=agg_filter_sec_484
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 485: agg_filter (agg_filter) id=agg_filter_sec_485
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 486: agg_filter (agg_filter) id=agg_filter_sec_486
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 487: agg_filter (agg_filter) id=agg_filter_sec_487
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 488: agg_filter (agg_filter) id=agg_filter_sec_488
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 489: agg_filter (agg_filter) id=agg_filter_sec_489
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 490: agg_filter (agg_filter) id=agg_filter_sec_490
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 491: agg_filter (agg_filter) id=agg_filter_sec_491
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 492: agg_filter (agg_filter) id=agg_filter_sec_492
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 493: agg_filter (agg_filter) id=agg_filter_sec_493
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 494: agg_filter (agg_filter) id=agg_filter_sec_494
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 495: agg_filter (agg_filter) id=agg_filter_sec_495
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 496: agg_filter (agg_filter) id=agg_filter_sec_496
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 497: agg_filter (agg_filter) id=agg_filter_sec_497
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 498: agg_filter (agg_filter) id=agg_filter_sec_498
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 499: agg_filter (agg_filter) id=agg_filter_sec_499
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 500: agg_filter (agg_filter) id=agg_filter_sec_500
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 501: agg_filter (agg_filter) id=agg_filter_sec_501
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 502: agg_filter (agg_filter) id=agg_filter_sec_502
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 503: agg_filter (agg_filter) id=agg_filter_sec_503
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 504: agg_filter (agg_filter) id=agg_filter_sec_504
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 505: agg_filter (agg_filter) id=agg_filter_sec_505
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 506: agg_filter (agg_filter) id=agg_filter_sec_506
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 507: agg_filter (agg_filter) id=agg_filter_sec_507
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 508: agg_filter (agg_filter) id=agg_filter_sec_508
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 509: agg_filter (agg_filter) id=agg_filter_sec_509
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 510: agg_filter (agg_filter) id=agg_filter_sec_510
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 511: agg_filter (agg_filter) id=agg_filter_sec_511
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 512: agg_filter (agg_filter) id=agg_filter_sec_512
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 513: agg_filter (agg_filter) id=agg_filter_sec_513
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 514: agg_filter (agg_filter) id=agg_filter_sec_514
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 515: agg_filter (agg_filter) id=agg_filter_sec_515
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 516: agg_filter (agg_filter) id=agg_filter_sec_516
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 517: agg_filter (agg_filter) id=agg_filter_sec_517
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 518: agg_filter (agg_filter) id=agg_filter_sec_518
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 519: agg_filter (agg_filter) id=agg_filter_sec_519
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 520: agg_filter (agg_filter) id=agg_filter_sec_520
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 521: agg_filter (agg_filter) id=agg_filter_sec_521
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 522: agg_filter (agg_filter) id=agg_filter_sec_522
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 523: agg_filter (agg_filter) id=agg_filter_sec_523
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 524: agg_filter (agg_filter) id=agg_filter_sec_524
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 525: agg_filter (agg_filter) id=agg_filter_sec_525
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 526: agg_filter (agg_filter) id=agg_filter_sec_526
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 527: agg_filter (agg_filter) id=agg_filter_sec_527
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 528: agg_filter (agg_filter) id=agg_filter_sec_528
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 529: agg_filter (agg_filter) id=agg_filter_sec_529
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 530: agg_filter (agg_filter) id=agg_filter_sec_530
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 531: agg_filter (agg_filter) id=agg_filter_sec_531
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 532: agg_filter (agg_filter) id=agg_filter_sec_532
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 533: agg_filter (agg_filter) id=agg_filter_sec_533
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 534: agg_filter (agg_filter) id=agg_filter_sec_534
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 535: agg_filter (agg_filter) id=agg_filter_sec_535
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 536: agg_filter (agg_filter) id=agg_filter_sec_536
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 537: agg_filter (agg_filter) id=agg_filter_sec_537
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 538: agg_filter (agg_filter) id=agg_filter_sec_538
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 539: agg_filter (agg_filter) id=agg_filter_sec_539
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 540: agg_filter (agg_filter) id=agg_filter_sec_540
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 541: agg_filter (agg_filter) id=agg_filter_sec_541
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 542: agg_filter (agg_filter) id=agg_filter_sec_542
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 543: agg_filter (agg_filter) id=agg_filter_sec_543
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 544: agg_filter (agg_filter) id=agg_filter_sec_544
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 545: agg_filter (agg_filter) id=agg_filter_sec_545
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 546: agg_filter (agg_filter) id=agg_filter_sec_546
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 547: agg_filter (agg_filter) id=agg_filter_sec_547
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 548: agg_filter (agg_filter) id=agg_filter_sec_548
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 549: agg_filter (agg_filter) id=agg_filter_sec_549
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 550: agg_filter (agg_filter) id=agg_filter_sec_550
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 551: agg_filter (agg_filter) id=agg_filter_sec_551
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 552: agg_filter (agg_filter) id=agg_filter_sec_552
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 553: agg_filter (agg_filter) id=agg_filter_sec_553
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 554: agg_filter (agg_filter) id=agg_filter_sec_554
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 555: agg_filter (agg_filter) id=agg_filter_sec_555
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 556: agg_filter (agg_filter) id=agg_filter_sec_556
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 557: agg_filter (agg_filter) id=agg_filter_sec_557
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 558: agg_filter (agg_filter) id=agg_filter_sec_558
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 559: agg_filter (agg_filter) id=agg_filter_sec_559
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 560: agg_filter (agg_filter) id=agg_filter_sec_560
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 561: agg_filter (agg_filter) id=agg_filter_sec_561
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 562: agg_filter (agg_filter) id=agg_filter_sec_562
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 563: agg_filter (agg_filter) id=agg_filter_sec_563
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 564: agg_filter (agg_filter) id=agg_filter_sec_564
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 565: agg_filter (agg_filter) id=agg_filter_sec_565
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 566: agg_filter (agg_filter) id=agg_filter_sec_566
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 567: agg_filter (agg_filter) id=agg_filter_sec_567
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 568: agg_filter (agg_filter) id=agg_filter_sec_568
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 569: agg_filter (agg_filter) id=agg_filter_sec_569
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 570: agg_filter (agg_filter) id=agg_filter_sec_570
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 571: agg_filter (agg_filter) id=agg_filter_sec_571
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 572: agg_filter (agg_filter) id=agg_filter_sec_572
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 573: agg_filter (agg_filter) id=agg_filter_sec_573
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 574: agg_filter (agg_filter) id=agg_filter_sec_574
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 575: agg_filter (agg_filter) id=agg_filter_sec_575
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 576: agg_filter (agg_filter) id=agg_filter_sec_576
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 577: agg_filter (agg_filter) id=agg_filter_sec_577
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 578: agg_filter (agg_filter) id=agg_filter_sec_578
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 579: agg_filter (agg_filter) id=agg_filter_sec_579
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 580: agg_filter (agg_filter) id=agg_filter_sec_580
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 581: agg_filter (agg_filter) id=agg_filter_sec_581
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 582: agg_filter (agg_filter) id=agg_filter_sec_582
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 583: agg_filter (agg_filter) id=agg_filter_sec_583
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 584: agg_filter (agg_filter) id=agg_filter_sec_584
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 585: agg_filter (agg_filter) id=agg_filter_sec_585
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 586: agg_filter (agg_filter) id=agg_filter_sec_586
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 587: agg_filter (agg_filter) id=agg_filter_sec_587
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 588: agg_filter (agg_filter) id=agg_filter_sec_588
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 589: agg_filter (agg_filter) id=agg_filter_sec_589
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 590: agg_filter (agg_filter) id=agg_filter_sec_590
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 591: agg_filter (agg_filter) id=agg_filter_sec_591
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 592: agg_filter (agg_filter) id=agg_filter_sec_592
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 593: agg_filter (agg_filter) id=agg_filter_sec_593
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 594: agg_filter (agg_filter) id=agg_filter_sec_594
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 595: agg_filter (agg_filter) id=agg_filter_sec_595
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 596: agg_filter (agg_filter) id=agg_filter_sec_596
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 597: agg_filter (agg_filter) id=agg_filter_sec_597
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 598: agg_filter (agg_filter) id=agg_filter_sec_598
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 599: agg_filter (agg_filter) id=agg_filter_sec_599
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 600: agg_filter (agg_filter) id=agg_filter_sec_600
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 601: agg_filter (agg_filter) id=agg_filter_sec_601
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 602: agg_filter (agg_filter) id=agg_filter_sec_602
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 603: agg_filter (agg_filter) id=agg_filter_sec_603
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 604: agg_filter (agg_filter) id=agg_filter_sec_604
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 605: agg_filter (agg_filter) id=agg_filter_sec_605
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 606: agg_filter (agg_filter) id=agg_filter_sec_606
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 607: agg_filter (agg_filter) id=agg_filter_sec_607
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 608: agg_filter (agg_filter) id=agg_filter_sec_608
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 609: agg_filter (agg_filter) id=agg_filter_sec_609
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 610: agg_filter (agg_filter) id=agg_filter_sec_610
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 611: agg_filter (agg_filter) id=agg_filter_sec_611
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 612: agg_filter (agg_filter) id=agg_filter_sec_612
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 613: agg_filter (agg_filter) id=agg_filter_sec_613
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 614: agg_filter (agg_filter) id=agg_filter_sec_614
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 615: agg_filter (agg_filter) id=agg_filter_sec_615
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 616: agg_filter (agg_filter) id=agg_filter_sec_616
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 617: agg_filter (agg_filter) id=agg_filter_sec_617
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 618: agg_filter (agg_filter) id=agg_filter_sec_618
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 619: agg_filter (agg_filter) id=agg_filter_sec_619
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 620: agg_filter (agg_filter) id=agg_filter_sec_620
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 621: agg_filter (agg_filter) id=agg_filter_sec_621
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 622: agg_filter (agg_filter) id=agg_filter_sec_622
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 623: agg_filter (agg_filter) id=agg_filter_sec_623
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 624: agg_filter (agg_filter) id=agg_filter_sec_624
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 625: agg_filter (agg_filter) id=agg_filter_sec_625
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 626: agg_filter (agg_filter) id=agg_filter_sec_626
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 627: agg_filter (agg_filter) id=agg_filter_sec_627
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 628: agg_filter (agg_filter) id=agg_filter_sec_628
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 629: agg_filter (agg_filter) id=agg_filter_sec_629
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 630: agg_filter (agg_filter) id=agg_filter_sec_630
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 631: agg_filter (agg_filter) id=agg_filter_sec_631
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 632: agg_filter (agg_filter) id=agg_filter_sec_632
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 633: agg_filter (agg_filter) id=agg_filter_sec_633
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 634: agg_filter (agg_filter) id=agg_filter_sec_634
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 635: agg_filter (agg_filter) id=agg_filter_sec_635
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 636: agg_filter (agg_filter) id=agg_filter_sec_636
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 637: agg_filter (agg_filter) id=agg_filter_sec_637
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 638: agg_filter (agg_filter) id=agg_filter_sec_638
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 639: agg_filter (agg_filter) id=agg_filter_sec_639
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 640: agg_filter (agg_filter) id=agg_filter_sec_640
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 641: agg_filter (agg_filter) id=agg_filter_sec_641
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 642: agg_filter (agg_filter) id=agg_filter_sec_642
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 643: agg_filter (agg_filter) id=agg_filter_sec_643
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 644: agg_filter (agg_filter) id=agg_filter_sec_644
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 645: agg_filter (agg_filter) id=agg_filter_sec_645
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 646: agg_filter (agg_filter) id=agg_filter_sec_646
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 647: agg_filter (agg_filter) id=agg_filter_sec_647
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 648: agg_filter (agg_filter) id=agg_filter_sec_648
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 649: agg_filter (agg_filter) id=agg_filter_sec_649
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 650: agg_filter (agg_filter) id=agg_filter_sec_650
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 651: agg_filter (agg_filter) id=agg_filter_sec_651
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 652: agg_filter (agg_filter) id=agg_filter_sec_652
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 653: agg_filter (agg_filter) id=agg_filter_sec_653
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 654: agg_filter (agg_filter) id=agg_filter_sec_654
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 655: agg_filter (agg_filter) id=agg_filter_sec_655
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 656: agg_filter (agg_filter) id=agg_filter_sec_656
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 657: agg_filter (agg_filter) id=agg_filter_sec_657
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 658: agg_filter (agg_filter) id=agg_filter_sec_658
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 659: agg_filter (agg_filter) id=agg_filter_sec_659
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 660: agg_filter (agg_filter) id=agg_filter_sec_660
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 661: agg_filter (agg_filter) id=agg_filter_sec_661
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 662: agg_filter (agg_filter) id=agg_filter_sec_662
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 663: agg_filter (agg_filter) id=agg_filter_sec_663
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 664: agg_filter (agg_filter) id=agg_filter_sec_664
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 665: agg_filter (agg_filter) id=agg_filter_sec_665
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 666: agg_filter (agg_filter) id=agg_filter_sec_666
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 667: agg_filter (agg_filter) id=agg_filter_sec_667
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 668: agg_filter (agg_filter) id=agg_filter_sec_668
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 669: agg_filter (agg_filter) id=agg_filter_sec_669
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 670: agg_filter (agg_filter) id=agg_filter_sec_670
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 671: agg_filter (agg_filter) id=agg_filter_sec_671
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 672: agg_filter (agg_filter) id=agg_filter_sec_672
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 673: agg_filter (agg_filter) id=agg_filter_sec_673
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 674: agg_filter (agg_filter) id=agg_filter_sec_674
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 675: agg_filter (agg_filter) id=agg_filter_sec_675
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 676: agg_filter (agg_filter) id=agg_filter_sec_676
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 677: agg_filter (agg_filter) id=agg_filter_sec_677
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 678: agg_filter (agg_filter) id=agg_filter_sec_678
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 679: agg_filter (agg_filter) id=agg_filter_sec_679
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 680: agg_filter (agg_filter) id=agg_filter_sec_680
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 681: agg_filter (agg_filter) id=agg_filter_sec_681
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 682: agg_filter (agg_filter) id=agg_filter_sec_682
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 683: agg_filter (agg_filter) id=agg_filter_sec_683
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 684: agg_filter (agg_filter) id=agg_filter_sec_684
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 685: agg_filter (agg_filter) id=agg_filter_sec_685
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 686: agg_filter (agg_filter) id=agg_filter_sec_686
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 687: agg_filter (agg_filter) id=agg_filter_sec_687
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 688: agg_filter (agg_filter) id=agg_filter_sec_688
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 689: agg_filter (agg_filter) id=agg_filter_sec_689
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 690: agg_filter (agg_filter) id=agg_filter_sec_690
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 691: agg_filter (agg_filter) id=agg_filter_sec_691
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 692: agg_filter (agg_filter) id=agg_filter_sec_692
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 693: agg_filter (agg_filter) id=agg_filter_sec_693
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 694: agg_filter (agg_filter) id=agg_filter_sec_694
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 695: agg_filter (agg_filter) id=agg_filter_sec_695
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 696: agg_filter (agg_filter) id=agg_filter_sec_696
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 697: agg_filter (agg_filter) id=agg_filter_sec_697
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 698: agg_filter (agg_filter) id=agg_filter_sec_698
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 699: agg_filter (agg_filter) id=agg_filter_sec_699
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 700: agg_filter (agg_filter) id=agg_filter_sec_700
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 701: agg_filter (agg_filter) id=agg_filter_sec_701
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 702: agg_filter (agg_filter) id=agg_filter_sec_702
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 703: agg_filter (agg_filter) id=agg_filter_sec_703
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 704: agg_filter (agg_filter) id=agg_filter_sec_704
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 705: agg_filter (agg_filter) id=agg_filter_sec_705
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 706: agg_filter (agg_filter) id=agg_filter_sec_706
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 707: agg_filter (agg_filter) id=agg_filter_sec_707
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 708: agg_filter (agg_filter) id=agg_filter_sec_708
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 709: agg_filter (agg_filter) id=agg_filter_sec_709
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 710: agg_filter (agg_filter) id=agg_filter_sec_710
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 711: agg_filter (agg_filter) id=agg_filter_sec_711
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 712: agg_filter (agg_filter) id=agg_filter_sec_712
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 713: agg_filter (agg_filter) id=agg_filter_sec_713
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 714: agg_filter (agg_filter) id=agg_filter_sec_714
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE form_type = '10-K' GROUP BY company_name;

-- Query 715: agg_filter (agg_filter) id=agg_filter_sec_715
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE form_type = '10-Q' GROUP BY company_name;

-- Query 716: agg_filter (agg_filter) id=agg_filter_sec_716
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY company_name;

-- Query 717: agg_filter (agg_filter) id=agg_filter_sec_717
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY company_name;

-- Query 718: agg_filter (agg_filter) id=agg_filter_sec_718
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY company_name;

-- Query 719: agg_filter (agg_filter) id=agg_filter_sec_719
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY company_name;

-- Query 720: agg_filter (agg_filter) id=agg_filter_sec_720
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY company_name;

-- Query 721: agg_filter (agg_filter) id=agg_filter_sec_721
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company_name;

-- Query 722: agg_filter (agg_filter) id=agg_filter_sec_722
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY company_name;

-- Query 723: agg_filter (agg_filter) id=agg_filter_sec_723
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY company_name;

-- Query 724: agg_filter (agg_filter) id=agg_filter_sec_724
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY company_name;

-- Query 725: agg_filter (agg_filter) id=agg_filter_sec_725
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company_name;

-- Query 726: agg_filter (agg_filter) id=agg_filter_sec_726
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY company_name;

-- Query 727: agg_filter (agg_filter) id=agg_filter_sec_727
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY company_name;

-- Query 728: agg_filter (agg_filter) id=agg_filter_sec_728
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY company_name;

-- Query 729: agg_filter (agg_filter) id=agg_filter_sec_729
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY company_name;

-- Query 730: agg_filter (agg_filter) id=agg_filter_sec_730
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY company_name;

-- Query 731: agg_filter (agg_filter) id=agg_filter_sec_731
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY company_name;

-- Query 732: agg_filter (agg_filter) id=agg_filter_sec_732
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE revenue_usd > 0 GROUP BY company_name;

-- Query 733: agg_filter (agg_filter) id=agg_filter_sec_733
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE net_income_usd > 0 GROUP BY company_name;

-- Query 734: agg_filter (agg_filter) id=agg_filter_sec_734
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE net_income_usd < 0 GROUP BY company_name;

-- Query 735: agg_filter (agg_filter) id=agg_filter_sec_735
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY company_name;

-- Query 736: agg_filter (agg_filter) id=agg_filter_sec_736
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY company_name;

-- Query 737: agg_filter (agg_filter) id=agg_filter_sec_737
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 738: agg_filter (agg_filter) id=agg_filter_sec_738
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 739: agg_filter (agg_filter) id=agg_filter_sec_739
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 740: agg_filter (agg_filter) id=agg_filter_sec_740
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 741: agg_filter (agg_filter) id=agg_filter_sec_741
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 742: agg_filter (agg_filter) id=agg_filter_sec_742
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 743: agg_filter (agg_filter) id=agg_filter_sec_743
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 744: agg_filter (agg_filter) id=agg_filter_sec_744
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 745: agg_filter (agg_filter) id=agg_filter_sec_745
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 746: agg_filter (agg_filter) id=agg_filter_sec_746
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 747: agg_filter (agg_filter) id=agg_filter_sec_747
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 748: agg_filter (agg_filter) id=agg_filter_sec_748
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 749: agg_filter (agg_filter) id=agg_filter_sec_749
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 750: agg_filter (agg_filter) id=agg_filter_sec_750
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 751: agg_filter (agg_filter) id=agg_filter_sec_751
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 752: agg_filter (agg_filter) id=agg_filter_sec_752
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 753: agg_filter (agg_filter) id=agg_filter_sec_753
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 754: agg_filter (agg_filter) id=agg_filter_sec_754
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 755: agg_filter (agg_filter) id=agg_filter_sec_755
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 756: agg_filter (agg_filter) id=agg_filter_sec_756
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 757: agg_filter (agg_filter) id=agg_filter_sec_757
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 758: agg_filter (agg_filter) id=agg_filter_sec_758
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 759: agg_filter (agg_filter) id=agg_filter_sec_759
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 760: agg_filter (agg_filter) id=agg_filter_sec_760
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 761: agg_filter (agg_filter) id=agg_filter_sec_761
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 762: agg_filter (agg_filter) id=agg_filter_sec_762
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 763: agg_filter (agg_filter) id=agg_filter_sec_763
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 764: agg_filter (agg_filter) id=agg_filter_sec_764
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 765: agg_filter (agg_filter) id=agg_filter_sec_765
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 766: agg_filter (agg_filter) id=agg_filter_sec_766
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 767: agg_filter (agg_filter) id=agg_filter_sec_767
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 768: agg_filter (agg_filter) id=agg_filter_sec_768
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 769: agg_filter (agg_filter) id=agg_filter_sec_769
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 770: agg_filter (agg_filter) id=agg_filter_sec_770
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 771: agg_filter (agg_filter) id=agg_filter_sec_771
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 772: agg_filter (agg_filter) id=agg_filter_sec_772
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 773: agg_filter (agg_filter) id=agg_filter_sec_773
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 774: agg_filter (agg_filter) id=agg_filter_sec_774
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 775: agg_filter (agg_filter) id=agg_filter_sec_775
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 776: agg_filter (agg_filter) id=agg_filter_sec_776
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 777: agg_filter (agg_filter) id=agg_filter_sec_777
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 778: agg_filter (agg_filter) id=agg_filter_sec_778
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 779: agg_filter (agg_filter) id=agg_filter_sec_779
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 780: agg_filter (agg_filter) id=agg_filter_sec_780
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 781: agg_filter (agg_filter) id=agg_filter_sec_781
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 782: agg_filter (agg_filter) id=agg_filter_sec_782
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 783: agg_filter (agg_filter) id=agg_filter_sec_783
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 784: agg_filter (agg_filter) id=agg_filter_sec_784
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 785: agg_filter (agg_filter) id=agg_filter_sec_785
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 786: agg_filter (agg_filter) id=agg_filter_sec_786
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 787: agg_filter (agg_filter) id=agg_filter_sec_787
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 788: agg_filter (agg_filter) id=agg_filter_sec_788
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 789: agg_filter (agg_filter) id=agg_filter_sec_789
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 790: agg_filter (agg_filter) id=agg_filter_sec_790
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 791: agg_filter (agg_filter) id=agg_filter_sec_791
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 792: agg_filter (agg_filter) id=agg_filter_sec_792
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 793: agg_filter (agg_filter) id=agg_filter_sec_793
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 794: agg_filter (agg_filter) id=agg_filter_sec_794
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 795: agg_filter (agg_filter) id=agg_filter_sec_795
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 796: agg_filter (agg_filter) id=agg_filter_sec_796
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 797: agg_filter (agg_filter) id=agg_filter_sec_797
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 798: agg_filter (agg_filter) id=agg_filter_sec_798
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 799: agg_filter (agg_filter) id=agg_filter_sec_799
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 800: agg_filter (agg_filter) id=agg_filter_sec_800
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 801: agg_filter (agg_filter) id=agg_filter_sec_801
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 802: agg_filter (agg_filter) id=agg_filter_sec_802
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 803: agg_filter (agg_filter) id=agg_filter_sec_803
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 804: agg_filter (agg_filter) id=agg_filter_sec_804
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 805: agg_filter (agg_filter) id=agg_filter_sec_805
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 806: agg_filter (agg_filter) id=agg_filter_sec_806
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 807: agg_filter (agg_filter) id=agg_filter_sec_807
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 808: agg_filter (agg_filter) id=agg_filter_sec_808
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 809: agg_filter (agg_filter) id=agg_filter_sec_809
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 810: agg_filter (agg_filter) id=agg_filter_sec_810
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 811: agg_filter (agg_filter) id=agg_filter_sec_811
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 812: agg_filter (agg_filter) id=agg_filter_sec_812
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 813: agg_filter (agg_filter) id=agg_filter_sec_813
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 814: agg_filter (agg_filter) id=agg_filter_sec_814
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 815: agg_filter (agg_filter) id=agg_filter_sec_815
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 816: agg_filter (agg_filter) id=agg_filter_sec_816
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 817: agg_filter (agg_filter) id=agg_filter_sec_817
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 818: agg_filter (agg_filter) id=agg_filter_sec_818
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 819: agg_filter (agg_filter) id=agg_filter_sec_819
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 820: agg_filter (agg_filter) id=agg_filter_sec_820
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 821: agg_filter (agg_filter) id=agg_filter_sec_821
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 822: agg_filter (agg_filter) id=agg_filter_sec_822
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 823: agg_filter (agg_filter) id=agg_filter_sec_823
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 824: agg_filter (agg_filter) id=agg_filter_sec_824
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 825: agg_filter (agg_filter) id=agg_filter_sec_825
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 826: agg_filter (agg_filter) id=agg_filter_sec_826
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 827: agg_filter (agg_filter) id=agg_filter_sec_827
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 828: agg_filter (agg_filter) id=agg_filter_sec_828
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 829: agg_filter (agg_filter) id=agg_filter_sec_829
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 830: agg_filter (agg_filter) id=agg_filter_sec_830
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 831: agg_filter (agg_filter) id=agg_filter_sec_831
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 832: agg_filter (agg_filter) id=agg_filter_sec_832
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 833: agg_filter (agg_filter) id=agg_filter_sec_833
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 834: agg_filter (agg_filter) id=agg_filter_sec_834
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 835: agg_filter (agg_filter) id=agg_filter_sec_835
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 836: agg_filter (agg_filter) id=agg_filter_sec_836
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 837: agg_filter (agg_filter) id=agg_filter_sec_837
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 838: agg_filter (agg_filter) id=agg_filter_sec_838
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 839: agg_filter (agg_filter) id=agg_filter_sec_839
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 840: agg_filter (agg_filter) id=agg_filter_sec_840
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 841: agg_filter (agg_filter) id=agg_filter_sec_841
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 842: agg_filter (agg_filter) id=agg_filter_sec_842
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 843: agg_filter (agg_filter) id=agg_filter_sec_843
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 844: agg_filter (agg_filter) id=agg_filter_sec_844
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 845: agg_filter (agg_filter) id=agg_filter_sec_845
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 846: agg_filter (agg_filter) id=agg_filter_sec_846
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 847: agg_filter (agg_filter) id=agg_filter_sec_847
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 848: agg_filter (agg_filter) id=agg_filter_sec_848
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 849: agg_filter (agg_filter) id=agg_filter_sec_849
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 850: agg_filter (agg_filter) id=agg_filter_sec_850
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 851: agg_filter (agg_filter) id=agg_filter_sec_851
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 852: agg_filter (agg_filter) id=agg_filter_sec_852
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 853: agg_filter (agg_filter) id=agg_filter_sec_853
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 854: agg_filter (agg_filter) id=agg_filter_sec_854
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 855: agg_filter (agg_filter) id=agg_filter_sec_855
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 856: agg_filter (agg_filter) id=agg_filter_sec_856
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 857: agg_filter (agg_filter) id=agg_filter_sec_857
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 858: agg_filter (agg_filter) id=agg_filter_sec_858
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 859: agg_filter (agg_filter) id=agg_filter_sec_859
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 860: agg_filter (agg_filter) id=agg_filter_sec_860
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 861: agg_filter (agg_filter) id=agg_filter_sec_861
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 862: agg_filter (agg_filter) id=agg_filter_sec_862
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 863: agg_filter (agg_filter) id=agg_filter_sec_863
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 864: agg_filter (agg_filter) id=agg_filter_sec_864
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 865: agg_filter (agg_filter) id=agg_filter_sec_865
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 866: agg_filter (agg_filter) id=agg_filter_sec_866
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 867: agg_filter (agg_filter) id=agg_filter_sec_867
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 868: agg_filter (agg_filter) id=agg_filter_sec_868
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 869: agg_filter (agg_filter) id=agg_filter_sec_869
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 870: agg_filter (agg_filter) id=agg_filter_sec_870
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 871: agg_filter (agg_filter) id=agg_filter_sec_871
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 872: agg_filter (agg_filter) id=agg_filter_sec_872
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 873: agg_filter (agg_filter) id=agg_filter_sec_873
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 874: agg_filter (agg_filter) id=agg_filter_sec_874
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 875: agg_filter (agg_filter) id=agg_filter_sec_875
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 876: agg_filter (agg_filter) id=agg_filter_sec_876
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 877: agg_filter (agg_filter) id=agg_filter_sec_877
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 878: agg_filter (agg_filter) id=agg_filter_sec_878
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 879: agg_filter (agg_filter) id=agg_filter_sec_879
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 880: agg_filter (agg_filter) id=agg_filter_sec_880
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 881: agg_filter (agg_filter) id=agg_filter_sec_881
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 882: agg_filter (agg_filter) id=agg_filter_sec_882
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 883: agg_filter (agg_filter) id=agg_filter_sec_883
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 884: agg_filter (agg_filter) id=agg_filter_sec_884
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 885: agg_filter (agg_filter) id=agg_filter_sec_885
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 886: agg_filter (agg_filter) id=agg_filter_sec_886
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 887: agg_filter (agg_filter) id=agg_filter_sec_887
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 888: agg_filter (agg_filter) id=agg_filter_sec_888
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 889: agg_filter (agg_filter) id=agg_filter_sec_889
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 890: agg_filter (agg_filter) id=agg_filter_sec_890
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 891: agg_filter (agg_filter) id=agg_filter_sec_891
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 892: agg_filter (agg_filter) id=agg_filter_sec_892
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 893: agg_filter (agg_filter) id=agg_filter_sec_893
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 894: agg_filter (agg_filter) id=agg_filter_sec_894
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 895: agg_filter (agg_filter) id=agg_filter_sec_895
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 896: agg_filter (agg_filter) id=agg_filter_sec_896
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 897: agg_filter (agg_filter) id=agg_filter_sec_897
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 898: agg_filter (agg_filter) id=agg_filter_sec_898
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 899: agg_filter (agg_filter) id=agg_filter_sec_899
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 900: agg_filter (agg_filter) id=agg_filter_sec_900
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 901: agg_filter (agg_filter) id=agg_filter_sec_901
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 902: agg_filter (agg_filter) id=agg_filter_sec_902
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 903: agg_filter (agg_filter) id=agg_filter_sec_903
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 904: agg_filter (agg_filter) id=agg_filter_sec_904
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 905: agg_filter (agg_filter) id=agg_filter_sec_905
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 906: agg_filter (agg_filter) id=agg_filter_sec_906
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 907: agg_filter (agg_filter) id=agg_filter_sec_907
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 908: agg_filter (agg_filter) id=agg_filter_sec_908
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 909: agg_filter (agg_filter) id=agg_filter_sec_909
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 910: agg_filter (agg_filter) id=agg_filter_sec_910
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 911: agg_filter (agg_filter) id=agg_filter_sec_911
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 912: agg_filter (agg_filter) id=agg_filter_sec_912
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 913: agg_filter (agg_filter) id=agg_filter_sec_913
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 914: agg_filter (agg_filter) id=agg_filter_sec_914
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 915: agg_filter (agg_filter) id=agg_filter_sec_915
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 916: agg_filter (agg_filter) id=agg_filter_sec_916
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 917: agg_filter (agg_filter) id=agg_filter_sec_917
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 918: agg_filter (agg_filter) id=agg_filter_sec_918
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 919: agg_filter (agg_filter) id=agg_filter_sec_919
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 920: agg_filter (agg_filter) id=agg_filter_sec_920
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 921: agg_filter (agg_filter) id=agg_filter_sec_921
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 922: agg_filter (agg_filter) id=agg_filter_sec_922
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 923: agg_filter (agg_filter) id=agg_filter_sec_923
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 924: agg_filter (agg_filter) id=agg_filter_sec_924
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 925: agg_filter (agg_filter) id=agg_filter_sec_925
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 926: agg_filter (agg_filter) id=agg_filter_sec_926
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 927: agg_filter (agg_filter) id=agg_filter_sec_927
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 928: agg_filter (agg_filter) id=agg_filter_sec_928
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 929: agg_filter (agg_filter) id=agg_filter_sec_929
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 930: agg_filter (agg_filter) id=agg_filter_sec_930
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 931: agg_filter (agg_filter) id=agg_filter_sec_931
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 932: agg_filter (agg_filter) id=agg_filter_sec_932
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 933: agg_filter (agg_filter) id=agg_filter_sec_933
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 934: agg_filter (agg_filter) id=agg_filter_sec_934
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 935: agg_filter (agg_filter) id=agg_filter_sec_935
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 936: agg_filter (agg_filter) id=agg_filter_sec_936
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 937: agg_filter (agg_filter) id=agg_filter_sec_937
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 938: agg_filter (agg_filter) id=agg_filter_sec_938
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 939: agg_filter (agg_filter) id=agg_filter_sec_939
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 940: agg_filter (agg_filter) id=agg_filter_sec_940
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 941: agg_filter (agg_filter) id=agg_filter_sec_941
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 942: agg_filter (agg_filter) id=agg_filter_sec_942
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 943: agg_filter (agg_filter) id=agg_filter_sec_943
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 944: agg_filter (agg_filter) id=agg_filter_sec_944
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 945: agg_filter (agg_filter) id=agg_filter_sec_945
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 946: agg_filter (agg_filter) id=agg_filter_sec_946
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 947: agg_filter (agg_filter) id=agg_filter_sec_947
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 948: agg_filter (agg_filter) id=agg_filter_sec_948
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 949: agg_filter (agg_filter) id=agg_filter_sec_949
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 950: agg_filter (agg_filter) id=agg_filter_sec_950
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 951: agg_filter (agg_filter) id=agg_filter_sec_951
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 952: agg_filter (agg_filter) id=agg_filter_sec_952
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 953: agg_filter (agg_filter) id=agg_filter_sec_953
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 954: agg_filter (agg_filter) id=agg_filter_sec_954
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 955: agg_filter (agg_filter) id=agg_filter_sec_955
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 956: agg_filter (agg_filter) id=agg_filter_sec_956
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 957: agg_filter (agg_filter) id=agg_filter_sec_957
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 958: agg_filter (agg_filter) id=agg_filter_sec_958
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 959: agg_filter (agg_filter) id=agg_filter_sec_959
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 960: agg_filter (agg_filter) id=agg_filter_sec_960
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 961: agg_filter (agg_filter) id=agg_filter_sec_961
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 962: agg_filter (agg_filter) id=agg_filter_sec_962
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 963: agg_filter (agg_filter) id=agg_filter_sec_963
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 964: agg_filter (agg_filter) id=agg_filter_sec_964
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 965: agg_filter (agg_filter) id=agg_filter_sec_965
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 966: agg_filter (agg_filter) id=agg_filter_sec_966
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 967: agg_filter (agg_filter) id=agg_filter_sec_967
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 968: agg_filter (agg_filter) id=agg_filter_sec_968
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 969: agg_filter (agg_filter) id=agg_filter_sec_969
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 970: agg_filter (agg_filter) id=agg_filter_sec_970
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 971: agg_filter (agg_filter) id=agg_filter_sec_971
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 972: agg_filter (agg_filter) id=agg_filter_sec_972
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 973: agg_filter (agg_filter) id=agg_filter_sec_973
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 974: agg_filter (agg_filter) id=agg_filter_sec_974
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 975: agg_filter (agg_filter) id=agg_filter_sec_975
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 976: agg_filter (agg_filter) id=agg_filter_sec_976
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 977: agg_filter (agg_filter) id=agg_filter_sec_977
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 978: agg_filter (agg_filter) id=agg_filter_sec_978
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 979: agg_filter (agg_filter) id=agg_filter_sec_979
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 980: agg_filter (agg_filter) id=agg_filter_sec_980
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 981: agg_filter (agg_filter) id=agg_filter_sec_981
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 982: agg_filter (agg_filter) id=agg_filter_sec_982
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 983: agg_filter (agg_filter) id=agg_filter_sec_983
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 984: agg_filter (agg_filter) id=agg_filter_sec_984
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 985: agg_filter (agg_filter) id=agg_filter_sec_985
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 986: agg_filter (agg_filter) id=agg_filter_sec_986
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 987: agg_filter (agg_filter) id=agg_filter_sec_987
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 988: agg_filter (agg_filter) id=agg_filter_sec_988
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 989: agg_filter (agg_filter) id=agg_filter_sec_989
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 990: agg_filter (agg_filter) id=agg_filter_sec_990
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 991: agg_filter (agg_filter) id=agg_filter_sec_991
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 992: agg_filter (agg_filter) id=agg_filter_sec_992
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 993: agg_filter (agg_filter) id=agg_filter_sec_993
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 994: agg_filter (agg_filter) id=agg_filter_sec_994
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 995: agg_filter (agg_filter) id=agg_filter_sec_995
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 996: agg_filter (agg_filter) id=agg_filter_sec_996
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 997: agg_filter (agg_filter) id=agg_filter_sec_997
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 998: agg_filter (agg_filter) id=agg_filter_sec_998
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 999: agg_filter (agg_filter) id=agg_filter_sec_999
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1000: agg_filter (agg_filter) id=agg_filter_sec_1000
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1001: agg_filter (agg_filter) id=agg_filter_sec_1001
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1002: agg_filter (agg_filter) id=agg_filter_sec_1002
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1003: agg_filter (agg_filter) id=agg_filter_sec_1003
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1004: agg_filter (agg_filter) id=agg_filter_sec_1004
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1005: agg_filter (agg_filter) id=agg_filter_sec_1005
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1006: agg_filter (agg_filter) id=agg_filter_sec_1006
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1007: agg_filter (agg_filter) id=agg_filter_sec_1007
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1008: agg_filter (agg_filter) id=agg_filter_sec_1008
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1009: agg_filter (agg_filter) id=agg_filter_sec_1009
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1010: agg_filter (agg_filter) id=agg_filter_sec_1010
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1011: agg_filter (agg_filter) id=agg_filter_sec_1011
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1012: agg_filter (agg_filter) id=agg_filter_sec_1012
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1013: agg_filter (agg_filter) id=agg_filter_sec_1013
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 1014: agg_filter (agg_filter) id=agg_filter_sec_1014
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 1015: agg_filter (agg_filter) id=agg_filter_sec_1015
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 1016: agg_filter (agg_filter) id=agg_filter_sec_1016
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 1017: agg_filter (agg_filter) id=agg_filter_sec_1017
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 1018: agg_filter (agg_filter) id=agg_filter_sec_1018
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 1019: agg_filter (agg_filter) id=agg_filter_sec_1019
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 1020: agg_filter (agg_filter) id=agg_filter_sec_1020
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 1021: agg_filter (agg_filter) id=agg_filter_sec_1021
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 1022: agg_filter (agg_filter) id=agg_filter_sec_1022
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1023: agg_filter (agg_filter) id=agg_filter_sec_1023
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1024: agg_filter (agg_filter) id=agg_filter_sec_1024
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1025: agg_filter (agg_filter) id=agg_filter_sec_1025
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1026: agg_filter (agg_filter) id=agg_filter_sec_1026
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1027: agg_filter (agg_filter) id=agg_filter_sec_1027
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1028: agg_filter (agg_filter) id=agg_filter_sec_1028
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1029: agg_filter (agg_filter) id=agg_filter_sec_1029
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1030: agg_filter (agg_filter) id=agg_filter_sec_1030
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1031: agg_filter (agg_filter) id=agg_filter_sec_1031
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1032: agg_filter (agg_filter) id=agg_filter_sec_1032
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1033: agg_filter (agg_filter) id=agg_filter_sec_1033
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1034: agg_filter (agg_filter) id=agg_filter_sec_1034
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1035: agg_filter (agg_filter) id=agg_filter_sec_1035
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1036: agg_filter (agg_filter) id=agg_filter_sec_1036
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 1037: agg_filter (agg_filter) id=agg_filter_sec_1037
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 1038: agg_filter (agg_filter) id=agg_filter_sec_1038
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 1039: agg_filter (agg_filter) id=agg_filter_sec_1039
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 1040: agg_filter (agg_filter) id=agg_filter_sec_1040
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 1041: agg_filter (agg_filter) id=agg_filter_sec_1041
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 1042: agg_filter (agg_filter) id=agg_filter_sec_1042
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 1043: agg_filter (agg_filter) id=agg_filter_sec_1043
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 1044: agg_filter (agg_filter) id=agg_filter_sec_1044
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 1045: agg_filter (agg_filter) id=agg_filter_sec_1045
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1046: agg_filter (agg_filter) id=agg_filter_sec_1046
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1047: agg_filter (agg_filter) id=agg_filter_sec_1047
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1048: agg_filter (agg_filter) id=agg_filter_sec_1048
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1049: agg_filter (agg_filter) id=agg_filter_sec_1049
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1050: agg_filter (agg_filter) id=agg_filter_sec_1050
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1051: agg_filter (agg_filter) id=agg_filter_sec_1051
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1052: agg_filter (agg_filter) id=agg_filter_sec_1052
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1053: agg_filter (agg_filter) id=agg_filter_sec_1053
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1054: agg_filter (agg_filter) id=agg_filter_sec_1054
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1055: agg_filter (agg_filter) id=agg_filter_sec_1055
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1056: agg_filter (agg_filter) id=agg_filter_sec_1056
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1057: agg_filter (agg_filter) id=agg_filter_sec_1057
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1058: agg_filter (agg_filter) id=agg_filter_sec_1058
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1059: agg_filter (agg_filter) id=agg_filter_sec_1059
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 1060: agg_filter (agg_filter) id=agg_filter_sec_1060
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 1061: agg_filter (agg_filter) id=agg_filter_sec_1061
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 1062: agg_filter (agg_filter) id=agg_filter_sec_1062
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 1063: agg_filter (agg_filter) id=agg_filter_sec_1063
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 1064: agg_filter (agg_filter) id=agg_filter_sec_1064
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 1065: agg_filter (agg_filter) id=agg_filter_sec_1065
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 1066: agg_filter (agg_filter) id=agg_filter_sec_1066
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 1067: agg_filter (agg_filter) id=agg_filter_sec_1067
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 1068: agg_filter (agg_filter) id=agg_filter_sec_1068
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1069: agg_filter (agg_filter) id=agg_filter_sec_1069
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1070: agg_filter (agg_filter) id=agg_filter_sec_1070
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1071: agg_filter (agg_filter) id=agg_filter_sec_1071
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1072: agg_filter (agg_filter) id=agg_filter_sec_1072
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1073: agg_filter (agg_filter) id=agg_filter_sec_1073
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1074: agg_filter (agg_filter) id=agg_filter_sec_1074
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1075: agg_filter (agg_filter) id=agg_filter_sec_1075
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1076: agg_filter (agg_filter) id=agg_filter_sec_1076
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1077: agg_filter (agg_filter) id=agg_filter_sec_1077
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1078: agg_filter (agg_filter) id=agg_filter_sec_1078
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1079: agg_filter (agg_filter) id=agg_filter_sec_1079
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1080: agg_filter (agg_filter) id=agg_filter_sec_1080
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1081: agg_filter (agg_filter) id=agg_filter_sec_1081
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1082: agg_filter (agg_filter) id=agg_filter_sec_1082
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 1083: agg_filter (agg_filter) id=agg_filter_sec_1083
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 1084: agg_filter (agg_filter) id=agg_filter_sec_1084
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 1085: agg_filter (agg_filter) id=agg_filter_sec_1085
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 1086: agg_filter (agg_filter) id=agg_filter_sec_1086
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 1087: agg_filter (agg_filter) id=agg_filter_sec_1087
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 1088: agg_filter (agg_filter) id=agg_filter_sec_1088
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 1089: agg_filter (agg_filter) id=agg_filter_sec_1089
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 1090: agg_filter (agg_filter) id=agg_filter_sec_1090
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 1091: agg_filter (agg_filter) id=agg_filter_sec_1091
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1092: agg_filter (agg_filter) id=agg_filter_sec_1092
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1093: agg_filter (agg_filter) id=agg_filter_sec_1093
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1094: agg_filter (agg_filter) id=agg_filter_sec_1094
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1095: agg_filter (agg_filter) id=agg_filter_sec_1095
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1096: agg_filter (agg_filter) id=agg_filter_sec_1096
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1097: agg_filter (agg_filter) id=agg_filter_sec_1097
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1098: agg_filter (agg_filter) id=agg_filter_sec_1098
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1099: agg_filter (agg_filter) id=agg_filter_sec_1099
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1100: agg_filter (agg_filter) id=agg_filter_sec_1100
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1101: agg_filter (agg_filter) id=agg_filter_sec_1101
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1102: agg_filter (agg_filter) id=agg_filter_sec_1102
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1103: agg_filter (agg_filter) id=agg_filter_sec_1103
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1104: agg_filter (agg_filter) id=agg_filter_sec_1104
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1105: agg_filter (agg_filter) id=agg_filter_sec_1105
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 1106: agg_filter (agg_filter) id=agg_filter_sec_1106
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 1107: agg_filter (agg_filter) id=agg_filter_sec_1107
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 1108: agg_filter (agg_filter) id=agg_filter_sec_1108
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 1109: agg_filter (agg_filter) id=agg_filter_sec_1109
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 1110: agg_filter (agg_filter) id=agg_filter_sec_1110
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 1111: agg_filter (agg_filter) id=agg_filter_sec_1111
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 1112: agg_filter (agg_filter) id=agg_filter_sec_1112
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 1113: agg_filter (agg_filter) id=agg_filter_sec_1113
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 1114: agg_filter (agg_filter) id=agg_filter_sec_1114
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1115: agg_filter (agg_filter) id=agg_filter_sec_1115
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1116: agg_filter (agg_filter) id=agg_filter_sec_1116
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1117: agg_filter (agg_filter) id=agg_filter_sec_1117
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1118: agg_filter (agg_filter) id=agg_filter_sec_1118
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1119: agg_filter (agg_filter) id=agg_filter_sec_1119
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1120: agg_filter (agg_filter) id=agg_filter_sec_1120
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1121: agg_filter (agg_filter) id=agg_filter_sec_1121
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1122: agg_filter (agg_filter) id=agg_filter_sec_1122
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1123: agg_filter (agg_filter) id=agg_filter_sec_1123
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1124: agg_filter (agg_filter) id=agg_filter_sec_1124
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1125: agg_filter (agg_filter) id=agg_filter_sec_1125
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1126: agg_filter (agg_filter) id=agg_filter_sec_1126
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1127: agg_filter (agg_filter) id=agg_filter_sec_1127
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1128: agg_filter (agg_filter) id=agg_filter_sec_1128
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 1129: agg_filter (agg_filter) id=agg_filter_sec_1129
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 1130: agg_filter (agg_filter) id=agg_filter_sec_1130
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 1131: agg_filter (agg_filter) id=agg_filter_sec_1131
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 1132: agg_filter (agg_filter) id=agg_filter_sec_1132
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 1133: agg_filter (agg_filter) id=agg_filter_sec_1133
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 1134: agg_filter (agg_filter) id=agg_filter_sec_1134
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 1135: agg_filter (agg_filter) id=agg_filter_sec_1135
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 1136: agg_filter (agg_filter) id=agg_filter_sec_1136
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 1137: agg_filter (agg_filter) id=agg_filter_sec_1137
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1138: agg_filter (agg_filter) id=agg_filter_sec_1138
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1139: agg_filter (agg_filter) id=agg_filter_sec_1139
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1140: agg_filter (agg_filter) id=agg_filter_sec_1140
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1141: agg_filter (agg_filter) id=agg_filter_sec_1141
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1142: agg_filter (agg_filter) id=agg_filter_sec_1142
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1143: agg_filter (agg_filter) id=agg_filter_sec_1143
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1144: agg_filter (agg_filter) id=agg_filter_sec_1144
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1145: agg_filter (agg_filter) id=agg_filter_sec_1145
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1146: agg_filter (agg_filter) id=agg_filter_sec_1146
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1147: agg_filter (agg_filter) id=agg_filter_sec_1147
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1148: agg_filter (agg_filter) id=agg_filter_sec_1148
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1149: agg_filter (agg_filter) id=agg_filter_sec_1149
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1150: agg_filter (agg_filter) id=agg_filter_sec_1150
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1151: agg_filter (agg_filter) id=agg_filter_sec_1151
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 1152: agg_filter (agg_filter) id=agg_filter_sec_1152
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 1153: agg_filter (agg_filter) id=agg_filter_sec_1153
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 1154: agg_filter (agg_filter) id=agg_filter_sec_1154
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 1155: agg_filter (agg_filter) id=agg_filter_sec_1155
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 1156: agg_filter (agg_filter) id=agg_filter_sec_1156
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 1157: agg_filter (agg_filter) id=agg_filter_sec_1157
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 1158: agg_filter (agg_filter) id=agg_filter_sec_1158
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 1159: agg_filter (agg_filter) id=agg_filter_sec_1159
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 1160: agg_filter (agg_filter) id=agg_filter_sec_1160
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1161: agg_filter (agg_filter) id=agg_filter_sec_1161
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1162: agg_filter (agg_filter) id=agg_filter_sec_1162
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1163: agg_filter (agg_filter) id=agg_filter_sec_1163
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1164: agg_filter (agg_filter) id=agg_filter_sec_1164
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1165: agg_filter (agg_filter) id=agg_filter_sec_1165
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1166: agg_filter (agg_filter) id=agg_filter_sec_1166
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1167: agg_filter (agg_filter) id=agg_filter_sec_1167
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1168: agg_filter (agg_filter) id=agg_filter_sec_1168
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1169: agg_filter (agg_filter) id=agg_filter_sec_1169
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1170: agg_filter (agg_filter) id=agg_filter_sec_1170
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1171: agg_filter (agg_filter) id=agg_filter_sec_1171
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1172: agg_filter (agg_filter) id=agg_filter_sec_1172
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1173: agg_filter (agg_filter) id=agg_filter_sec_1173
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1174: agg_filter (agg_filter) id=agg_filter_sec_1174
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 1175: agg_filter (agg_filter) id=agg_filter_sec_1175
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 1176: agg_filter (agg_filter) id=agg_filter_sec_1176
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 1177: agg_filter (agg_filter) id=agg_filter_sec_1177
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 1178: agg_filter (agg_filter) id=agg_filter_sec_1178
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 1179: agg_filter (agg_filter) id=agg_filter_sec_1179
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 1180: agg_filter (agg_filter) id=agg_filter_sec_1180
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 1181: agg_filter (agg_filter) id=agg_filter_sec_1181
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 1182: agg_filter (agg_filter) id=agg_filter_sec_1182
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 1183: agg_filter (agg_filter) id=agg_filter_sec_1183
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1184: agg_filter (agg_filter) id=agg_filter_sec_1184
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1185: agg_filter (agg_filter) id=agg_filter_sec_1185
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1186: agg_filter (agg_filter) id=agg_filter_sec_1186
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1187: agg_filter (agg_filter) id=agg_filter_sec_1187
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1188: agg_filter (agg_filter) id=agg_filter_sec_1188
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1189: agg_filter (agg_filter) id=agg_filter_sec_1189
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1190: agg_filter (agg_filter) id=agg_filter_sec_1190
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1191: agg_filter (agg_filter) id=agg_filter_sec_1191
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1192: agg_filter (agg_filter) id=agg_filter_sec_1192
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1193: agg_filter (agg_filter) id=agg_filter_sec_1193
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1194: agg_filter (agg_filter) id=agg_filter_sec_1194
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1195: agg_filter (agg_filter) id=agg_filter_sec_1195
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1196: agg_filter (agg_filter) id=agg_filter_sec_1196
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1197: agg_filter (agg_filter) id=agg_filter_sec_1197
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 1198: agg_filter (agg_filter) id=agg_filter_sec_1198
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 1199: agg_filter (agg_filter) id=agg_filter_sec_1199
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 1200: agg_filter (agg_filter) id=agg_filter_sec_1200
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 1201: agg_filter (agg_filter) id=agg_filter_sec_1201
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 1202: agg_filter (agg_filter) id=agg_filter_sec_1202
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 1203: agg_filter (agg_filter) id=agg_filter_sec_1203
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 1204: agg_filter (agg_filter) id=agg_filter_sec_1204
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 1205: agg_filter (agg_filter) id=agg_filter_sec_1205
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 1206: agg_filter (agg_filter) id=agg_filter_sec_1206
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1207: agg_filter (agg_filter) id=agg_filter_sec_1207
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1208: agg_filter (agg_filter) id=agg_filter_sec_1208
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1209: agg_filter (agg_filter) id=agg_filter_sec_1209
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1210: agg_filter (agg_filter) id=agg_filter_sec_1210
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1211: agg_filter (agg_filter) id=agg_filter_sec_1211
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1212: agg_filter (agg_filter) id=agg_filter_sec_1212
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1213: agg_filter (agg_filter) id=agg_filter_sec_1213
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1214: agg_filter (agg_filter) id=agg_filter_sec_1214
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1215: agg_filter (agg_filter) id=agg_filter_sec_1215
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1216: agg_filter (agg_filter) id=agg_filter_sec_1216
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1217: agg_filter (agg_filter) id=agg_filter_sec_1217
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1218: agg_filter (agg_filter) id=agg_filter_sec_1218
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1219: agg_filter (agg_filter) id=agg_filter_sec_1219
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1220: agg_filter (agg_filter) id=agg_filter_sec_1220
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 1221: agg_filter (agg_filter) id=agg_filter_sec_1221
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 1222: agg_filter (agg_filter) id=agg_filter_sec_1222
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 1223: agg_filter (agg_filter) id=agg_filter_sec_1223
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 1224: agg_filter (agg_filter) id=agg_filter_sec_1224
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 1225: agg_filter (agg_filter) id=agg_filter_sec_1225
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 1226: agg_filter (agg_filter) id=agg_filter_sec_1226
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 1227: agg_filter (agg_filter) id=agg_filter_sec_1227
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 1228: agg_filter (agg_filter) id=agg_filter_sec_1228
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 1229: agg_filter (agg_filter) id=agg_filter_sec_1229
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1230: agg_filter (agg_filter) id=agg_filter_sec_1230
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1231: agg_filter (agg_filter) id=agg_filter_sec_1231
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1232: agg_filter (agg_filter) id=agg_filter_sec_1232
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1233: agg_filter (agg_filter) id=agg_filter_sec_1233
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1234: agg_filter (agg_filter) id=agg_filter_sec_1234
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1235: agg_filter (agg_filter) id=agg_filter_sec_1235
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1236: agg_filter (agg_filter) id=agg_filter_sec_1236
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1237: agg_filter (agg_filter) id=agg_filter_sec_1237
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1238: agg_filter (agg_filter) id=agg_filter_sec_1238
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1239: agg_filter (agg_filter) id=agg_filter_sec_1239
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1240: agg_filter (agg_filter) id=agg_filter_sec_1240
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1241: agg_filter (agg_filter) id=agg_filter_sec_1241
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1242: agg_filter (agg_filter) id=agg_filter_sec_1242
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1243: agg_filter (agg_filter) id=agg_filter_sec_1243
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 1244: agg_filter (agg_filter) id=agg_filter_sec_1244
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 1245: agg_filter (agg_filter) id=agg_filter_sec_1245
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 1246: agg_filter (agg_filter) id=agg_filter_sec_1246
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 1247: agg_filter (agg_filter) id=agg_filter_sec_1247
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 1248: agg_filter (agg_filter) id=agg_filter_sec_1248
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 1249: agg_filter (agg_filter) id=agg_filter_sec_1249
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 1250: agg_filter (agg_filter) id=agg_filter_sec_1250
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 1251: agg_filter (agg_filter) id=agg_filter_sec_1251
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 1252: agg_filter (agg_filter) id=agg_filter_sec_1252
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1253: agg_filter (agg_filter) id=agg_filter_sec_1253
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1254: agg_filter (agg_filter) id=agg_filter_sec_1254
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1255: agg_filter (agg_filter) id=agg_filter_sec_1255
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1256: agg_filter (agg_filter) id=agg_filter_sec_1256
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1257: agg_filter (agg_filter) id=agg_filter_sec_1257
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1258: agg_filter (agg_filter) id=agg_filter_sec_1258
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1259: agg_filter (agg_filter) id=agg_filter_sec_1259
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1260: agg_filter (agg_filter) id=agg_filter_sec_1260
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1261: agg_filter (agg_filter) id=agg_filter_sec_1261
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1262: agg_filter (agg_filter) id=agg_filter_sec_1262
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1263: agg_filter (agg_filter) id=agg_filter_sec_1263
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1264: agg_filter (agg_filter) id=agg_filter_sec_1264
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1265: agg_filter (agg_filter) id=agg_filter_sec_1265
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1266: agg_filter (agg_filter) id=agg_filter_sec_1266
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 1267: agg_filter (agg_filter) id=agg_filter_sec_1267
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 1268: agg_filter (agg_filter) id=agg_filter_sec_1268
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 1269: agg_filter (agg_filter) id=agg_filter_sec_1269
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 1270: agg_filter (agg_filter) id=agg_filter_sec_1270
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 1271: agg_filter (agg_filter) id=agg_filter_sec_1271
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 1272: agg_filter (agg_filter) id=agg_filter_sec_1272
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 1273: agg_filter (agg_filter) id=agg_filter_sec_1273
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 1274: agg_filter (agg_filter) id=agg_filter_sec_1274
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 1275: agg_filter (agg_filter) id=agg_filter_sec_1275
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1276: agg_filter (agg_filter) id=agg_filter_sec_1276
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1277: agg_filter (agg_filter) id=agg_filter_sec_1277
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1278: agg_filter (agg_filter) id=agg_filter_sec_1278
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1279: agg_filter (agg_filter) id=agg_filter_sec_1279
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1280: agg_filter (agg_filter) id=agg_filter_sec_1280
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1281: agg_filter (agg_filter) id=agg_filter_sec_1281
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1282: agg_filter (agg_filter) id=agg_filter_sec_1282
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1283: agg_filter (agg_filter) id=agg_filter_sec_1283
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1284: agg_filter (agg_filter) id=agg_filter_sec_1284
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1285: agg_filter (agg_filter) id=agg_filter_sec_1285
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1286: agg_filter (agg_filter) id=agg_filter_sec_1286
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1287: agg_filter (agg_filter) id=agg_filter_sec_1287
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1288: agg_filter (agg_filter) id=agg_filter_sec_1288
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1289: agg_filter (agg_filter) id=agg_filter_sec_1289
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 1290: agg_filter (agg_filter) id=agg_filter_sec_1290
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 1291: agg_filter (agg_filter) id=agg_filter_sec_1291
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 1292: agg_filter (agg_filter) id=agg_filter_sec_1292
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 1293: agg_filter (agg_filter) id=agg_filter_sec_1293
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 1294: agg_filter (agg_filter) id=agg_filter_sec_1294
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 1295: agg_filter (agg_filter) id=agg_filter_sec_1295
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 1296: agg_filter (agg_filter) id=agg_filter_sec_1296
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 1297: agg_filter (agg_filter) id=agg_filter_sec_1297
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 1298: agg_filter (agg_filter) id=agg_filter_sec_1298
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1299: agg_filter (agg_filter) id=agg_filter_sec_1299
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1300: agg_filter (agg_filter) id=agg_filter_sec_1300
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1301: agg_filter (agg_filter) id=agg_filter_sec_1301
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1302: agg_filter (agg_filter) id=agg_filter_sec_1302
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1303: agg_filter (agg_filter) id=agg_filter_sec_1303
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1304: agg_filter (agg_filter) id=agg_filter_sec_1304
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1305: agg_filter (agg_filter) id=agg_filter_sec_1305
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1306: agg_filter (agg_filter) id=agg_filter_sec_1306
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1307: agg_filter (agg_filter) id=agg_filter_sec_1307
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1308: agg_filter (agg_filter) id=agg_filter_sec_1308
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1309: agg_filter (agg_filter) id=agg_filter_sec_1309
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1310: agg_filter (agg_filter) id=agg_filter_sec_1310
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1311: agg_filter (agg_filter) id=agg_filter_sec_1311
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1312: agg_filter (agg_filter) id=agg_filter_sec_1312
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 1313: agg_filter (agg_filter) id=agg_filter_sec_1313
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 1314: agg_filter (agg_filter) id=agg_filter_sec_1314
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 1315: agg_filter (agg_filter) id=agg_filter_sec_1315
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 1316: agg_filter (agg_filter) id=agg_filter_sec_1316
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 1317: agg_filter (agg_filter) id=agg_filter_sec_1317
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 1318: agg_filter (agg_filter) id=agg_filter_sec_1318
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 1319: agg_filter (agg_filter) id=agg_filter_sec_1319
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 1320: agg_filter (agg_filter) id=agg_filter_sec_1320
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 1321: agg_filter (agg_filter) id=agg_filter_sec_1321
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1322: agg_filter (agg_filter) id=agg_filter_sec_1322
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1323: agg_filter (agg_filter) id=agg_filter_sec_1323
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1324: agg_filter (agg_filter) id=agg_filter_sec_1324
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1325: agg_filter (agg_filter) id=agg_filter_sec_1325
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1326: agg_filter (agg_filter) id=agg_filter_sec_1326
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1327: agg_filter (agg_filter) id=agg_filter_sec_1327
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1328: agg_filter (agg_filter) id=agg_filter_sec_1328
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1329: agg_filter (agg_filter) id=agg_filter_sec_1329
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1330: agg_filter (agg_filter) id=agg_filter_sec_1330
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1331: agg_filter (agg_filter) id=agg_filter_sec_1331
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1332: agg_filter (agg_filter) id=agg_filter_sec_1332
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1333: agg_filter (agg_filter) id=agg_filter_sec_1333
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1334: agg_filter (agg_filter) id=agg_filter_sec_1334
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1335: agg_filter (agg_filter) id=agg_filter_sec_1335
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 1336: agg_filter (agg_filter) id=agg_filter_sec_1336
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 1337: agg_filter (agg_filter) id=agg_filter_sec_1337
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 1338: agg_filter (agg_filter) id=agg_filter_sec_1338
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 1339: agg_filter (agg_filter) id=agg_filter_sec_1339
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 1340: agg_filter (agg_filter) id=agg_filter_sec_1340
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 1341: agg_filter (agg_filter) id=agg_filter_sec_1341
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 1342: agg_filter (agg_filter) id=agg_filter_sec_1342
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 1343: agg_filter (agg_filter) id=agg_filter_sec_1343
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 1344: agg_filter (agg_filter) id=agg_filter_sec_1344
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1345: agg_filter (agg_filter) id=agg_filter_sec_1345
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1346: agg_filter (agg_filter) id=agg_filter_sec_1346
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1347: agg_filter (agg_filter) id=agg_filter_sec_1347
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1348: agg_filter (agg_filter) id=agg_filter_sec_1348
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1349: agg_filter (agg_filter) id=agg_filter_sec_1349
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1350: agg_filter (agg_filter) id=agg_filter_sec_1350
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1351: agg_filter (agg_filter) id=agg_filter_sec_1351
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1352: agg_filter (agg_filter) id=agg_filter_sec_1352
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1353: agg_filter (agg_filter) id=agg_filter_sec_1353
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1354: agg_filter (agg_filter) id=agg_filter_sec_1354
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1355: agg_filter (agg_filter) id=agg_filter_sec_1355
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1356: agg_filter (agg_filter) id=agg_filter_sec_1356
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1357: agg_filter (agg_filter) id=agg_filter_sec_1357
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1358: agg_filter (agg_filter) id=agg_filter_sec_1358
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 1359: agg_filter (agg_filter) id=agg_filter_sec_1359
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 1360: agg_filter (agg_filter) id=agg_filter_sec_1360
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 1361: agg_filter (agg_filter) id=agg_filter_sec_1361
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 1362: agg_filter (agg_filter) id=agg_filter_sec_1362
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 1363: agg_filter (agg_filter) id=agg_filter_sec_1363
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 1364: agg_filter (agg_filter) id=agg_filter_sec_1364
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 1365: agg_filter (agg_filter) id=agg_filter_sec_1365
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 1366: agg_filter (agg_filter) id=agg_filter_sec_1366
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 1367: agg_filter (agg_filter) id=agg_filter_sec_1367
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1368: agg_filter (agg_filter) id=agg_filter_sec_1368
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1369: agg_filter (agg_filter) id=agg_filter_sec_1369
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1370: agg_filter (agg_filter) id=agg_filter_sec_1370
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1371: agg_filter (agg_filter) id=agg_filter_sec_1371
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1372: agg_filter (agg_filter) id=agg_filter_sec_1372
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1373: agg_filter (agg_filter) id=agg_filter_sec_1373
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1374: agg_filter (agg_filter) id=agg_filter_sec_1374
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1375: agg_filter (agg_filter) id=agg_filter_sec_1375
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1376: agg_filter (agg_filter) id=agg_filter_sec_1376
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1377: agg_filter (agg_filter) id=agg_filter_sec_1377
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1378: agg_filter (agg_filter) id=agg_filter_sec_1378
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1379: agg_filter (agg_filter) id=agg_filter_sec_1379
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1380: agg_filter (agg_filter) id=agg_filter_sec_1380
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1381: agg_filter (agg_filter) id=agg_filter_sec_1381
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 1382: agg_filter (agg_filter) id=agg_filter_sec_1382
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 1383: agg_filter (agg_filter) id=agg_filter_sec_1383
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 1384: agg_filter (agg_filter) id=agg_filter_sec_1384
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 1385: agg_filter (agg_filter) id=agg_filter_sec_1385
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 1386: agg_filter (agg_filter) id=agg_filter_sec_1386
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 1387: agg_filter (agg_filter) id=agg_filter_sec_1387
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 1388: agg_filter (agg_filter) id=agg_filter_sec_1388
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 1389: agg_filter (agg_filter) id=agg_filter_sec_1389
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 1390: agg_filter (agg_filter) id=agg_filter_sec_1390
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1391: agg_filter (agg_filter) id=agg_filter_sec_1391
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1392: agg_filter (agg_filter) id=agg_filter_sec_1392
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1393: agg_filter (agg_filter) id=agg_filter_sec_1393
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1394: agg_filter (agg_filter) id=agg_filter_sec_1394
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1395: agg_filter (agg_filter) id=agg_filter_sec_1395
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1396: agg_filter (agg_filter) id=agg_filter_sec_1396
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1397: agg_filter (agg_filter) id=agg_filter_sec_1397
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1398: agg_filter (agg_filter) id=agg_filter_sec_1398
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1399: agg_filter (agg_filter) id=agg_filter_sec_1399
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1400: agg_filter (agg_filter) id=agg_filter_sec_1400
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1401: agg_filter (agg_filter) id=agg_filter_sec_1401
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1402: agg_filter (agg_filter) id=agg_filter_sec_1402
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1403: agg_filter (agg_filter) id=agg_filter_sec_1403
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1404: agg_filter (agg_filter) id=agg_filter_sec_1404
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 1405: agg_filter (agg_filter) id=agg_filter_sec_1405
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 1406: agg_filter (agg_filter) id=agg_filter_sec_1406
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 1407: agg_filter (agg_filter) id=agg_filter_sec_1407
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 1408: agg_filter (agg_filter) id=agg_filter_sec_1408
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 1409: agg_filter (agg_filter) id=agg_filter_sec_1409
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 1410: agg_filter (agg_filter) id=agg_filter_sec_1410
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 1411: agg_filter (agg_filter) id=agg_filter_sec_1411
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 1412: agg_filter (agg_filter) id=agg_filter_sec_1412
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 1413: agg_filter (agg_filter) id=agg_filter_sec_1413
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1414: agg_filter (agg_filter) id=agg_filter_sec_1414
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1415: agg_filter (agg_filter) id=agg_filter_sec_1415
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1416: agg_filter (agg_filter) id=agg_filter_sec_1416
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1417: agg_filter (agg_filter) id=agg_filter_sec_1417
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1418: agg_filter (agg_filter) id=agg_filter_sec_1418
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1419: agg_filter (agg_filter) id=agg_filter_sec_1419
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1420: agg_filter (agg_filter) id=agg_filter_sec_1420
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1421: agg_filter (agg_filter) id=agg_filter_sec_1421
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1422: agg_filter (agg_filter) id=agg_filter_sec_1422
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1423: agg_filter (agg_filter) id=agg_filter_sec_1423
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1424: agg_filter (agg_filter) id=agg_filter_sec_1424
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1425: agg_filter (agg_filter) id=agg_filter_sec_1425
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1426: agg_filter (agg_filter) id=agg_filter_sec_1426
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1427: agg_filter (agg_filter) id=agg_filter_sec_1427
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 1428: agg_filter (agg_filter) id=agg_filter_sec_1428
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 1429: agg_filter (agg_filter) id=agg_filter_sec_1429
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 1430: agg_filter (agg_filter) id=agg_filter_sec_1430
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 1431: agg_filter (agg_filter) id=agg_filter_sec_1431
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 1432: agg_filter (agg_filter) id=agg_filter_sec_1432
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 1433: agg_filter (agg_filter) id=agg_filter_sec_1433
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 1434: agg_filter (agg_filter) id=agg_filter_sec_1434
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 1435: agg_filter (agg_filter) id=agg_filter_sec_1435
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 1436: agg_filter (agg_filter) id=agg_filter_sec_1436
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1437: agg_filter (agg_filter) id=agg_filter_sec_1437
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1438: agg_filter (agg_filter) id=agg_filter_sec_1438
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1439: agg_filter (agg_filter) id=agg_filter_sec_1439
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1440: agg_filter (agg_filter) id=agg_filter_sec_1440
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1441: agg_filter (agg_filter) id=agg_filter_sec_1441
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1442: agg_filter (agg_filter) id=agg_filter_sec_1442
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1443: agg_filter (agg_filter) id=agg_filter_sec_1443
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1444: agg_filter (agg_filter) id=agg_filter_sec_1444
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1445: agg_filter (agg_filter) id=agg_filter_sec_1445
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1446: agg_filter (agg_filter) id=agg_filter_sec_1446
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1447: agg_filter (agg_filter) id=agg_filter_sec_1447
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1448: agg_filter (agg_filter) id=agg_filter_sec_1448
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1449: agg_filter (agg_filter) id=agg_filter_sec_1449
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1450: agg_filter (agg_filter) id=agg_filter_sec_1450
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE form_type = '10-K' GROUP BY ticker;

-- Query 1451: agg_filter (agg_filter) id=agg_filter_sec_1451
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE form_type = '10-Q' GROUP BY ticker;

-- Query 1452: agg_filter (agg_filter) id=agg_filter_sec_1452
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY ticker;

-- Query 1453: agg_filter (agg_filter) id=agg_filter_sec_1453
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY ticker;

-- Query 1454: agg_filter (agg_filter) id=agg_filter_sec_1454
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY ticker;

-- Query 1455: agg_filter (agg_filter) id=agg_filter_sec_1455
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY ticker;

-- Query 1456: agg_filter (agg_filter) id=agg_filter_sec_1456
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY ticker;

-- Query 1457: agg_filter (agg_filter) id=agg_filter_sec_1457
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY ticker;

-- Query 1458: agg_filter (agg_filter) id=agg_filter_sec_1458
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY ticker;

-- Query 1459: agg_filter (agg_filter) id=agg_filter_sec_1459
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY ticker;

-- Query 1460: agg_filter (agg_filter) id=agg_filter_sec_1460
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY ticker;

-- Query 1461: agg_filter (agg_filter) id=agg_filter_sec_1461
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY ticker;

-- Query 1462: agg_filter (agg_filter) id=agg_filter_sec_1462
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY ticker;

-- Query 1463: agg_filter (agg_filter) id=agg_filter_sec_1463
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY ticker;

-- Query 1464: agg_filter (agg_filter) id=agg_filter_sec_1464
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY ticker;

-- Query 1465: agg_filter (agg_filter) id=agg_filter_sec_1465
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY ticker;

-- Query 1466: agg_filter (agg_filter) id=agg_filter_sec_1466
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY ticker;

-- Query 1467: agg_filter (agg_filter) id=agg_filter_sec_1467
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker;

-- Query 1468: agg_filter (agg_filter) id=agg_filter_sec_1468
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE revenue_usd > 0 GROUP BY ticker;

-- Query 1469: agg_filter (agg_filter) id=agg_filter_sec_1469
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE net_income_usd > 0 GROUP BY ticker;

-- Query 1470: agg_filter (agg_filter) id=agg_filter_sec_1470
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE net_income_usd < 0 GROUP BY ticker;

-- Query 1471: agg_filter (agg_filter) id=agg_filter_sec_1471
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY ticker;

-- Query 1472: agg_filter (agg_filter) id=agg_filter_sec_1472
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY ticker;

-- Query 1473: agg_filter (agg_filter) id=agg_filter_sec_1473
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1474: agg_filter (agg_filter) id=agg_filter_sec_1474
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1475: agg_filter (agg_filter) id=agg_filter_sec_1475
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1476: agg_filter (agg_filter) id=agg_filter_sec_1476
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1477: agg_filter (agg_filter) id=agg_filter_sec_1477
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1478: agg_filter (agg_filter) id=agg_filter_sec_1478
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1479: agg_filter (agg_filter) id=agg_filter_sec_1479
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1480: agg_filter (agg_filter) id=agg_filter_sec_1480
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1481: agg_filter (agg_filter) id=agg_filter_sec_1481
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1482: agg_filter (agg_filter) id=agg_filter_sec_1482
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1483: agg_filter (agg_filter) id=agg_filter_sec_1483
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1484: agg_filter (agg_filter) id=agg_filter_sec_1484
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1485: agg_filter (agg_filter) id=agg_filter_sec_1485
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1486: agg_filter (agg_filter) id=agg_filter_sec_1486
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1487: agg_filter (agg_filter) id=agg_filter_sec_1487
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1488: agg_filter (agg_filter) id=agg_filter_sec_1488
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1489: agg_filter (agg_filter) id=agg_filter_sec_1489
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1490: agg_filter (agg_filter) id=agg_filter_sec_1490
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1491: agg_filter (agg_filter) id=agg_filter_sec_1491
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1492: agg_filter (agg_filter) id=agg_filter_sec_1492
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1493: agg_filter (agg_filter) id=agg_filter_sec_1493
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1494: agg_filter (agg_filter) id=agg_filter_sec_1494
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1495: agg_filter (agg_filter) id=agg_filter_sec_1495
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1496: agg_filter (agg_filter) id=agg_filter_sec_1496
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1497: agg_filter (agg_filter) id=agg_filter_sec_1497
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1498: agg_filter (agg_filter) id=agg_filter_sec_1498
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1499: agg_filter (agg_filter) id=agg_filter_sec_1499
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1500: agg_filter (agg_filter) id=agg_filter_sec_1500
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1501: agg_filter (agg_filter) id=agg_filter_sec_1501
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1502: agg_filter (agg_filter) id=agg_filter_sec_1502
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1503: agg_filter (agg_filter) id=agg_filter_sec_1503
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1504: agg_filter (agg_filter) id=agg_filter_sec_1504
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1505: agg_filter (agg_filter) id=agg_filter_sec_1505
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1506: agg_filter (agg_filter) id=agg_filter_sec_1506
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1507: agg_filter (agg_filter) id=agg_filter_sec_1507
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1508: agg_filter (agg_filter) id=agg_filter_sec_1508
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1509: agg_filter (agg_filter) id=agg_filter_sec_1509
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1510: agg_filter (agg_filter) id=agg_filter_sec_1510
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1511: agg_filter (agg_filter) id=agg_filter_sec_1511
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1512: agg_filter (agg_filter) id=agg_filter_sec_1512
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1513: agg_filter (agg_filter) id=agg_filter_sec_1513
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1514: agg_filter (agg_filter) id=agg_filter_sec_1514
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1515: agg_filter (agg_filter) id=agg_filter_sec_1515
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1516: agg_filter (agg_filter) id=agg_filter_sec_1516
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1517: agg_filter (agg_filter) id=agg_filter_sec_1517
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1518: agg_filter (agg_filter) id=agg_filter_sec_1518
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1519: agg_filter (agg_filter) id=agg_filter_sec_1519
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1520: agg_filter (agg_filter) id=agg_filter_sec_1520
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1521: agg_filter (agg_filter) id=agg_filter_sec_1521
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1522: agg_filter (agg_filter) id=agg_filter_sec_1522
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1523: agg_filter (agg_filter) id=agg_filter_sec_1523
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1524: agg_filter (agg_filter) id=agg_filter_sec_1524
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1525: agg_filter (agg_filter) id=agg_filter_sec_1525
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1526: agg_filter (agg_filter) id=agg_filter_sec_1526
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1527: agg_filter (agg_filter) id=agg_filter_sec_1527
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1528: agg_filter (agg_filter) id=agg_filter_sec_1528
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1529: agg_filter (agg_filter) id=agg_filter_sec_1529
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1530: agg_filter (agg_filter) id=agg_filter_sec_1530
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1531: agg_filter (agg_filter) id=agg_filter_sec_1531
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1532: agg_filter (agg_filter) id=agg_filter_sec_1532
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1533: agg_filter (agg_filter) id=agg_filter_sec_1533
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1534: agg_filter (agg_filter) id=agg_filter_sec_1534
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1535: agg_filter (agg_filter) id=agg_filter_sec_1535
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1536: agg_filter (agg_filter) id=agg_filter_sec_1536
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1537: agg_filter (agg_filter) id=agg_filter_sec_1537
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1538: agg_filter (agg_filter) id=agg_filter_sec_1538
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1539: agg_filter (agg_filter) id=agg_filter_sec_1539
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1540: agg_filter (agg_filter) id=agg_filter_sec_1540
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1541: agg_filter (agg_filter) id=agg_filter_sec_1541
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1542: agg_filter (agg_filter) id=agg_filter_sec_1542
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1543: agg_filter (agg_filter) id=agg_filter_sec_1543
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1544: agg_filter (agg_filter) id=agg_filter_sec_1544
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1545: agg_filter (agg_filter) id=agg_filter_sec_1545
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1546: agg_filter (agg_filter) id=agg_filter_sec_1546
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1547: agg_filter (agg_filter) id=agg_filter_sec_1547
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1548: agg_filter (agg_filter) id=agg_filter_sec_1548
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1549: agg_filter (agg_filter) id=agg_filter_sec_1549
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1550: agg_filter (agg_filter) id=agg_filter_sec_1550
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1551: agg_filter (agg_filter) id=agg_filter_sec_1551
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1552: agg_filter (agg_filter) id=agg_filter_sec_1552
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1553: agg_filter (agg_filter) id=agg_filter_sec_1553
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1554: agg_filter (agg_filter) id=agg_filter_sec_1554
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1555: agg_filter (agg_filter) id=agg_filter_sec_1555
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1556: agg_filter (agg_filter) id=agg_filter_sec_1556
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1557: agg_filter (agg_filter) id=agg_filter_sec_1557
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1558: agg_filter (agg_filter) id=agg_filter_sec_1558
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1559: agg_filter (agg_filter) id=agg_filter_sec_1559
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1560: agg_filter (agg_filter) id=agg_filter_sec_1560
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1561: agg_filter (agg_filter) id=agg_filter_sec_1561
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1562: agg_filter (agg_filter) id=agg_filter_sec_1562
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1563: agg_filter (agg_filter) id=agg_filter_sec_1563
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1564: agg_filter (agg_filter) id=agg_filter_sec_1564
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1565: agg_filter (agg_filter) id=agg_filter_sec_1565
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1566: agg_filter (agg_filter) id=agg_filter_sec_1566
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1567: agg_filter (agg_filter) id=agg_filter_sec_1567
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1568: agg_filter (agg_filter) id=agg_filter_sec_1568
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1569: agg_filter (agg_filter) id=agg_filter_sec_1569
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1570: agg_filter (agg_filter) id=agg_filter_sec_1570
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1571: agg_filter (agg_filter) id=agg_filter_sec_1571
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1572: agg_filter (agg_filter) id=agg_filter_sec_1572
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1573: agg_filter (agg_filter) id=agg_filter_sec_1573
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1574: agg_filter (agg_filter) id=agg_filter_sec_1574
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1575: agg_filter (agg_filter) id=agg_filter_sec_1575
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1576: agg_filter (agg_filter) id=agg_filter_sec_1576
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1577: agg_filter (agg_filter) id=agg_filter_sec_1577
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1578: agg_filter (agg_filter) id=agg_filter_sec_1578
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1579: agg_filter (agg_filter) id=agg_filter_sec_1579
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1580: agg_filter (agg_filter) id=agg_filter_sec_1580
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1581: agg_filter (agg_filter) id=agg_filter_sec_1581
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1582: agg_filter (agg_filter) id=agg_filter_sec_1582
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1583: agg_filter (agg_filter) id=agg_filter_sec_1583
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1584: agg_filter (agg_filter) id=agg_filter_sec_1584
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1585: agg_filter (agg_filter) id=agg_filter_sec_1585
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1586: agg_filter (agg_filter) id=agg_filter_sec_1586
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1587: agg_filter (agg_filter) id=agg_filter_sec_1587
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1588: agg_filter (agg_filter) id=agg_filter_sec_1588
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1589: agg_filter (agg_filter) id=agg_filter_sec_1589
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1590: agg_filter (agg_filter) id=agg_filter_sec_1590
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1591: agg_filter (agg_filter) id=agg_filter_sec_1591
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1592: agg_filter (agg_filter) id=agg_filter_sec_1592
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1593: agg_filter (agg_filter) id=agg_filter_sec_1593
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1594: agg_filter (agg_filter) id=agg_filter_sec_1594
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1595: agg_filter (agg_filter) id=agg_filter_sec_1595
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1596: agg_filter (agg_filter) id=agg_filter_sec_1596
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1597: agg_filter (agg_filter) id=agg_filter_sec_1597
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1598: agg_filter (agg_filter) id=agg_filter_sec_1598
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1599: agg_filter (agg_filter) id=agg_filter_sec_1599
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1600: agg_filter (agg_filter) id=agg_filter_sec_1600
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1601: agg_filter (agg_filter) id=agg_filter_sec_1601
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1602: agg_filter (agg_filter) id=agg_filter_sec_1602
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1603: agg_filter (agg_filter) id=agg_filter_sec_1603
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1604: agg_filter (agg_filter) id=agg_filter_sec_1604
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1605: agg_filter (agg_filter) id=agg_filter_sec_1605
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1606: agg_filter (agg_filter) id=agg_filter_sec_1606
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1607: agg_filter (agg_filter) id=agg_filter_sec_1607
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1608: agg_filter (agg_filter) id=agg_filter_sec_1608
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1609: agg_filter (agg_filter) id=agg_filter_sec_1609
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1610: agg_filter (agg_filter) id=agg_filter_sec_1610
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1611: agg_filter (agg_filter) id=agg_filter_sec_1611
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1612: agg_filter (agg_filter) id=agg_filter_sec_1612
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1613: agg_filter (agg_filter) id=agg_filter_sec_1613
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1614: agg_filter (agg_filter) id=agg_filter_sec_1614
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1615: agg_filter (agg_filter) id=agg_filter_sec_1615
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1616: agg_filter (agg_filter) id=agg_filter_sec_1616
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1617: agg_filter (agg_filter) id=agg_filter_sec_1617
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1618: agg_filter (agg_filter) id=agg_filter_sec_1618
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1619: agg_filter (agg_filter) id=agg_filter_sec_1619
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1620: agg_filter (agg_filter) id=agg_filter_sec_1620
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1621: agg_filter (agg_filter) id=agg_filter_sec_1621
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1622: agg_filter (agg_filter) id=agg_filter_sec_1622
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1623: agg_filter (agg_filter) id=agg_filter_sec_1623
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1624: agg_filter (agg_filter) id=agg_filter_sec_1624
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1625: agg_filter (agg_filter) id=agg_filter_sec_1625
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1626: agg_filter (agg_filter) id=agg_filter_sec_1626
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1627: agg_filter (agg_filter) id=agg_filter_sec_1627
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1628: agg_filter (agg_filter) id=agg_filter_sec_1628
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1629: agg_filter (agg_filter) id=agg_filter_sec_1629
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1630: agg_filter (agg_filter) id=agg_filter_sec_1630
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1631: agg_filter (agg_filter) id=agg_filter_sec_1631
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1632: agg_filter (agg_filter) id=agg_filter_sec_1632
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1633: agg_filter (agg_filter) id=agg_filter_sec_1633
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1634: agg_filter (agg_filter) id=agg_filter_sec_1634
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1635: agg_filter (agg_filter) id=agg_filter_sec_1635
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1636: agg_filter (agg_filter) id=agg_filter_sec_1636
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1637: agg_filter (agg_filter) id=agg_filter_sec_1637
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1638: agg_filter (agg_filter) id=agg_filter_sec_1638
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1639: agg_filter (agg_filter) id=agg_filter_sec_1639
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1640: agg_filter (agg_filter) id=agg_filter_sec_1640
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1641: agg_filter (agg_filter) id=agg_filter_sec_1641
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1642: agg_filter (agg_filter) id=agg_filter_sec_1642
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1643: agg_filter (agg_filter) id=agg_filter_sec_1643
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1644: agg_filter (agg_filter) id=agg_filter_sec_1644
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1645: agg_filter (agg_filter) id=agg_filter_sec_1645
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1646: agg_filter (agg_filter) id=agg_filter_sec_1646
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1647: agg_filter (agg_filter) id=agg_filter_sec_1647
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1648: agg_filter (agg_filter) id=agg_filter_sec_1648
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1649: agg_filter (agg_filter) id=agg_filter_sec_1649
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1650: agg_filter (agg_filter) id=agg_filter_sec_1650
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1651: agg_filter (agg_filter) id=agg_filter_sec_1651
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1652: agg_filter (agg_filter) id=agg_filter_sec_1652
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1653: agg_filter (agg_filter) id=agg_filter_sec_1653
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1654: agg_filter (agg_filter) id=agg_filter_sec_1654
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1655: agg_filter (agg_filter) id=agg_filter_sec_1655
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1656: agg_filter (agg_filter) id=agg_filter_sec_1656
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1657: agg_filter (agg_filter) id=agg_filter_sec_1657
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1658: agg_filter (agg_filter) id=agg_filter_sec_1658
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1659: agg_filter (agg_filter) id=agg_filter_sec_1659
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1660: agg_filter (agg_filter) id=agg_filter_sec_1660
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1661: agg_filter (agg_filter) id=agg_filter_sec_1661
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1662: agg_filter (agg_filter) id=agg_filter_sec_1662
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1663: agg_filter (agg_filter) id=agg_filter_sec_1663
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1664: agg_filter (agg_filter) id=agg_filter_sec_1664
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1665: agg_filter (agg_filter) id=agg_filter_sec_1665
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1666: agg_filter (agg_filter) id=agg_filter_sec_1666
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1667: agg_filter (agg_filter) id=agg_filter_sec_1667
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1668: agg_filter (agg_filter) id=agg_filter_sec_1668
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1669: agg_filter (agg_filter) id=agg_filter_sec_1669
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1670: agg_filter (agg_filter) id=agg_filter_sec_1670
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1671: agg_filter (agg_filter) id=agg_filter_sec_1671
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1672: agg_filter (agg_filter) id=agg_filter_sec_1672
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1673: agg_filter (agg_filter) id=agg_filter_sec_1673
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1674: agg_filter (agg_filter) id=agg_filter_sec_1674
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1675: agg_filter (agg_filter) id=agg_filter_sec_1675
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1676: agg_filter (agg_filter) id=agg_filter_sec_1676
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1677: agg_filter (agg_filter) id=agg_filter_sec_1677
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1678: agg_filter (agg_filter) id=agg_filter_sec_1678
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1679: agg_filter (agg_filter) id=agg_filter_sec_1679
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1680: agg_filter (agg_filter) id=agg_filter_sec_1680
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1681: agg_filter (agg_filter) id=agg_filter_sec_1681
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1682: agg_filter (agg_filter) id=agg_filter_sec_1682
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1683: agg_filter (agg_filter) id=agg_filter_sec_1683
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1684: agg_filter (agg_filter) id=agg_filter_sec_1684
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1685: agg_filter (agg_filter) id=agg_filter_sec_1685
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1686: agg_filter (agg_filter) id=agg_filter_sec_1686
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1687: agg_filter (agg_filter) id=agg_filter_sec_1687
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1688: agg_filter (agg_filter) id=agg_filter_sec_1688
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1689: agg_filter (agg_filter) id=agg_filter_sec_1689
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1690: agg_filter (agg_filter) id=agg_filter_sec_1690
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1691: agg_filter (agg_filter) id=agg_filter_sec_1691
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1692: agg_filter (agg_filter) id=agg_filter_sec_1692
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1693: agg_filter (agg_filter) id=agg_filter_sec_1693
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1694: agg_filter (agg_filter) id=agg_filter_sec_1694
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1695: agg_filter (agg_filter) id=agg_filter_sec_1695
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1696: agg_filter (agg_filter) id=agg_filter_sec_1696
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1697: agg_filter (agg_filter) id=agg_filter_sec_1697
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1698: agg_filter (agg_filter) id=agg_filter_sec_1698
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1699: agg_filter (agg_filter) id=agg_filter_sec_1699
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1700: agg_filter (agg_filter) id=agg_filter_sec_1700
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1701: agg_filter (agg_filter) id=agg_filter_sec_1701
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1702: agg_filter (agg_filter) id=agg_filter_sec_1702
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1703: agg_filter (agg_filter) id=agg_filter_sec_1703
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1704: agg_filter (agg_filter) id=agg_filter_sec_1704
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1705: agg_filter (agg_filter) id=agg_filter_sec_1705
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1706: agg_filter (agg_filter) id=agg_filter_sec_1706
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1707: agg_filter (agg_filter) id=agg_filter_sec_1707
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1708: agg_filter (agg_filter) id=agg_filter_sec_1708
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1709: agg_filter (agg_filter) id=agg_filter_sec_1709
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1710: agg_filter (agg_filter) id=agg_filter_sec_1710
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1711: agg_filter (agg_filter) id=agg_filter_sec_1711
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1712: agg_filter (agg_filter) id=agg_filter_sec_1712
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1713: agg_filter (agg_filter) id=agg_filter_sec_1713
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1714: agg_filter (agg_filter) id=agg_filter_sec_1714
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1715: agg_filter (agg_filter) id=agg_filter_sec_1715
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1716: agg_filter (agg_filter) id=agg_filter_sec_1716
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1717: agg_filter (agg_filter) id=agg_filter_sec_1717
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1718: agg_filter (agg_filter) id=agg_filter_sec_1718
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1719: agg_filter (agg_filter) id=agg_filter_sec_1719
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1720: agg_filter (agg_filter) id=agg_filter_sec_1720
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1721: agg_filter (agg_filter) id=agg_filter_sec_1721
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1722: agg_filter (agg_filter) id=agg_filter_sec_1722
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1723: agg_filter (agg_filter) id=agg_filter_sec_1723
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1724: agg_filter (agg_filter) id=agg_filter_sec_1724
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1725: agg_filter (agg_filter) id=agg_filter_sec_1725
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1726: agg_filter (agg_filter) id=agg_filter_sec_1726
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1727: agg_filter (agg_filter) id=agg_filter_sec_1727
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1728: agg_filter (agg_filter) id=agg_filter_sec_1728
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1729: agg_filter (agg_filter) id=agg_filter_sec_1729
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1730: agg_filter (agg_filter) id=agg_filter_sec_1730
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1731: agg_filter (agg_filter) id=agg_filter_sec_1731
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1732: agg_filter (agg_filter) id=agg_filter_sec_1732
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1733: agg_filter (agg_filter) id=agg_filter_sec_1733
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1734: agg_filter (agg_filter) id=agg_filter_sec_1734
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1735: agg_filter (agg_filter) id=agg_filter_sec_1735
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1736: agg_filter (agg_filter) id=agg_filter_sec_1736
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1737: agg_filter (agg_filter) id=agg_filter_sec_1737
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1738: agg_filter (agg_filter) id=agg_filter_sec_1738
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1739: agg_filter (agg_filter) id=agg_filter_sec_1739
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1740: agg_filter (agg_filter) id=agg_filter_sec_1740
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1741: agg_filter (agg_filter) id=agg_filter_sec_1741
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1742: agg_filter (agg_filter) id=agg_filter_sec_1742
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1743: agg_filter (agg_filter) id=agg_filter_sec_1743
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1744: agg_filter (agg_filter) id=agg_filter_sec_1744
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1745: agg_filter (agg_filter) id=agg_filter_sec_1745
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1746: agg_filter (agg_filter) id=agg_filter_sec_1746
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1747: agg_filter (agg_filter) id=agg_filter_sec_1747
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1748: agg_filter (agg_filter) id=agg_filter_sec_1748
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1749: agg_filter (agg_filter) id=agg_filter_sec_1749
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1750: agg_filter (agg_filter) id=agg_filter_sec_1750
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1751: agg_filter (agg_filter) id=agg_filter_sec_1751
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1752: agg_filter (agg_filter) id=agg_filter_sec_1752
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1753: agg_filter (agg_filter) id=agg_filter_sec_1753
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1754: agg_filter (agg_filter) id=agg_filter_sec_1754
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1755: agg_filter (agg_filter) id=agg_filter_sec_1755
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1756: agg_filter (agg_filter) id=agg_filter_sec_1756
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1757: agg_filter (agg_filter) id=agg_filter_sec_1757
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1758: agg_filter (agg_filter) id=agg_filter_sec_1758
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1759: agg_filter (agg_filter) id=agg_filter_sec_1759
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1760: agg_filter (agg_filter) id=agg_filter_sec_1760
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1761: agg_filter (agg_filter) id=agg_filter_sec_1761
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1762: agg_filter (agg_filter) id=agg_filter_sec_1762
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1763: agg_filter (agg_filter) id=agg_filter_sec_1763
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1764: agg_filter (agg_filter) id=agg_filter_sec_1764
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1765: agg_filter (agg_filter) id=agg_filter_sec_1765
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1766: agg_filter (agg_filter) id=agg_filter_sec_1766
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1767: agg_filter (agg_filter) id=agg_filter_sec_1767
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1768: agg_filter (agg_filter) id=agg_filter_sec_1768
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1769: agg_filter (agg_filter) id=agg_filter_sec_1769
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1770: agg_filter (agg_filter) id=agg_filter_sec_1770
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1771: agg_filter (agg_filter) id=agg_filter_sec_1771
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1772: agg_filter (agg_filter) id=agg_filter_sec_1772
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1773: agg_filter (agg_filter) id=agg_filter_sec_1773
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1774: agg_filter (agg_filter) id=agg_filter_sec_1774
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1775: agg_filter (agg_filter) id=agg_filter_sec_1775
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1776: agg_filter (agg_filter) id=agg_filter_sec_1776
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1777: agg_filter (agg_filter) id=agg_filter_sec_1777
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1778: agg_filter (agg_filter) id=agg_filter_sec_1778
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1779: agg_filter (agg_filter) id=agg_filter_sec_1779
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1780: agg_filter (agg_filter) id=agg_filter_sec_1780
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1781: agg_filter (agg_filter) id=agg_filter_sec_1781
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1782: agg_filter (agg_filter) id=agg_filter_sec_1782
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1783: agg_filter (agg_filter) id=agg_filter_sec_1783
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1784: agg_filter (agg_filter) id=agg_filter_sec_1784
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1785: agg_filter (agg_filter) id=agg_filter_sec_1785
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1786: agg_filter (agg_filter) id=agg_filter_sec_1786
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1787: agg_filter (agg_filter) id=agg_filter_sec_1787
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1788: agg_filter (agg_filter) id=agg_filter_sec_1788
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1789: agg_filter (agg_filter) id=agg_filter_sec_1789
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1790: agg_filter (agg_filter) id=agg_filter_sec_1790
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1791: agg_filter (agg_filter) id=agg_filter_sec_1791
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1792: agg_filter (agg_filter) id=agg_filter_sec_1792
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1793: agg_filter (agg_filter) id=agg_filter_sec_1793
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1794: agg_filter (agg_filter) id=agg_filter_sec_1794
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1795: agg_filter (agg_filter) id=agg_filter_sec_1795
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1796: agg_filter (agg_filter) id=agg_filter_sec_1796
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1797: agg_filter (agg_filter) id=agg_filter_sec_1797
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1798: agg_filter (agg_filter) id=agg_filter_sec_1798
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1799: agg_filter (agg_filter) id=agg_filter_sec_1799
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1800: agg_filter (agg_filter) id=agg_filter_sec_1800
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1801: agg_filter (agg_filter) id=agg_filter_sec_1801
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1802: agg_filter (agg_filter) id=agg_filter_sec_1802
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1803: agg_filter (agg_filter) id=agg_filter_sec_1803
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1804: agg_filter (agg_filter) id=agg_filter_sec_1804
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1805: agg_filter (agg_filter) id=agg_filter_sec_1805
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1806: agg_filter (agg_filter) id=agg_filter_sec_1806
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1807: agg_filter (agg_filter) id=agg_filter_sec_1807
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1808: agg_filter (agg_filter) id=agg_filter_sec_1808
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1809: agg_filter (agg_filter) id=agg_filter_sec_1809
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1810: agg_filter (agg_filter) id=agg_filter_sec_1810
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1811: agg_filter (agg_filter) id=agg_filter_sec_1811
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1812: agg_filter (agg_filter) id=agg_filter_sec_1812
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1813: agg_filter (agg_filter) id=agg_filter_sec_1813
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1814: agg_filter (agg_filter) id=agg_filter_sec_1814
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1815: agg_filter (agg_filter) id=agg_filter_sec_1815
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1816: agg_filter (agg_filter) id=agg_filter_sec_1816
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1817: agg_filter (agg_filter) id=agg_filter_sec_1817
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1818: agg_filter (agg_filter) id=agg_filter_sec_1818
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1819: agg_filter (agg_filter) id=agg_filter_sec_1819
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1820: agg_filter (agg_filter) id=agg_filter_sec_1820
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1821: agg_filter (agg_filter) id=agg_filter_sec_1821
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1822: agg_filter (agg_filter) id=agg_filter_sec_1822
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1823: agg_filter (agg_filter) id=agg_filter_sec_1823
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1824: agg_filter (agg_filter) id=agg_filter_sec_1824
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1825: agg_filter (agg_filter) id=agg_filter_sec_1825
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1826: agg_filter (agg_filter) id=agg_filter_sec_1826
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1827: agg_filter (agg_filter) id=agg_filter_sec_1827
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1828: agg_filter (agg_filter) id=agg_filter_sec_1828
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1829: agg_filter (agg_filter) id=agg_filter_sec_1829
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1830: agg_filter (agg_filter) id=agg_filter_sec_1830
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1831: agg_filter (agg_filter) id=agg_filter_sec_1831
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1832: agg_filter (agg_filter) id=agg_filter_sec_1832
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1833: agg_filter (agg_filter) id=agg_filter_sec_1833
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1834: agg_filter (agg_filter) id=agg_filter_sec_1834
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1835: agg_filter (agg_filter) id=agg_filter_sec_1835
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1836: agg_filter (agg_filter) id=agg_filter_sec_1836
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1837: agg_filter (agg_filter) id=agg_filter_sec_1837
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1838: agg_filter (agg_filter) id=agg_filter_sec_1838
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1839: agg_filter (agg_filter) id=agg_filter_sec_1839
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1840: agg_filter (agg_filter) id=agg_filter_sec_1840
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1841: agg_filter (agg_filter) id=agg_filter_sec_1841
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1842: agg_filter (agg_filter) id=agg_filter_sec_1842
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1843: agg_filter (agg_filter) id=agg_filter_sec_1843
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1844: agg_filter (agg_filter) id=agg_filter_sec_1844
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1845: agg_filter (agg_filter) id=agg_filter_sec_1845
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1846: agg_filter (agg_filter) id=agg_filter_sec_1846
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1847: agg_filter (agg_filter) id=agg_filter_sec_1847
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1848: agg_filter (agg_filter) id=agg_filter_sec_1848
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1849: agg_filter (agg_filter) id=agg_filter_sec_1849
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1850: agg_filter (agg_filter) id=agg_filter_sec_1850
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1851: agg_filter (agg_filter) id=agg_filter_sec_1851
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1852: agg_filter (agg_filter) id=agg_filter_sec_1852
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1853: agg_filter (agg_filter) id=agg_filter_sec_1853
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1854: agg_filter (agg_filter) id=agg_filter_sec_1854
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1855: agg_filter (agg_filter) id=agg_filter_sec_1855
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1856: agg_filter (agg_filter) id=agg_filter_sec_1856
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1857: agg_filter (agg_filter) id=agg_filter_sec_1857
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1858: agg_filter (agg_filter) id=agg_filter_sec_1858
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1859: agg_filter (agg_filter) id=agg_filter_sec_1859
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1860: agg_filter (agg_filter) id=agg_filter_sec_1860
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1861: agg_filter (agg_filter) id=agg_filter_sec_1861
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1862: agg_filter (agg_filter) id=agg_filter_sec_1862
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1863: agg_filter (agg_filter) id=agg_filter_sec_1863
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1864: agg_filter (agg_filter) id=agg_filter_sec_1864
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1865: agg_filter (agg_filter) id=agg_filter_sec_1865
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1866: agg_filter (agg_filter) id=agg_filter_sec_1866
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1867: agg_filter (agg_filter) id=agg_filter_sec_1867
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1868: agg_filter (agg_filter) id=agg_filter_sec_1868
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1869: agg_filter (agg_filter) id=agg_filter_sec_1869
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1870: agg_filter (agg_filter) id=agg_filter_sec_1870
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1871: agg_filter (agg_filter) id=agg_filter_sec_1871
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1872: agg_filter (agg_filter) id=agg_filter_sec_1872
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1873: agg_filter (agg_filter) id=agg_filter_sec_1873
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1874: agg_filter (agg_filter) id=agg_filter_sec_1874
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1875: agg_filter (agg_filter) id=agg_filter_sec_1875
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1876: agg_filter (agg_filter) id=agg_filter_sec_1876
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1877: agg_filter (agg_filter) id=agg_filter_sec_1877
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1878: agg_filter (agg_filter) id=agg_filter_sec_1878
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1879: agg_filter (agg_filter) id=agg_filter_sec_1879
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1880: agg_filter (agg_filter) id=agg_filter_sec_1880
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1881: agg_filter (agg_filter) id=agg_filter_sec_1881
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1882: agg_filter (agg_filter) id=agg_filter_sec_1882
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1883: agg_filter (agg_filter) id=agg_filter_sec_1883
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1884: agg_filter (agg_filter) id=agg_filter_sec_1884
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1885: agg_filter (agg_filter) id=agg_filter_sec_1885
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1886: agg_filter (agg_filter) id=agg_filter_sec_1886
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1887: agg_filter (agg_filter) id=agg_filter_sec_1887
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1888: agg_filter (agg_filter) id=agg_filter_sec_1888
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1889: agg_filter (agg_filter) id=agg_filter_sec_1889
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1890: agg_filter (agg_filter) id=agg_filter_sec_1890
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1891: agg_filter (agg_filter) id=agg_filter_sec_1891
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1892: agg_filter (agg_filter) id=agg_filter_sec_1892
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1893: agg_filter (agg_filter) id=agg_filter_sec_1893
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1894: agg_filter (agg_filter) id=agg_filter_sec_1894
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1895: agg_filter (agg_filter) id=agg_filter_sec_1895
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1896: agg_filter (agg_filter) id=agg_filter_sec_1896
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1897: agg_filter (agg_filter) id=agg_filter_sec_1897
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1898: agg_filter (agg_filter) id=agg_filter_sec_1898
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1899: agg_filter (agg_filter) id=agg_filter_sec_1899
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1900: agg_filter (agg_filter) id=agg_filter_sec_1900
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1901: agg_filter (agg_filter) id=agg_filter_sec_1901
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1902: agg_filter (agg_filter) id=agg_filter_sec_1902
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1903: agg_filter (agg_filter) id=agg_filter_sec_1903
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1904: agg_filter (agg_filter) id=agg_filter_sec_1904
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1905: agg_filter (agg_filter) id=agg_filter_sec_1905
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1906: agg_filter (agg_filter) id=agg_filter_sec_1906
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1907: agg_filter (agg_filter) id=agg_filter_sec_1907
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1908: agg_filter (agg_filter) id=agg_filter_sec_1908
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1909: agg_filter (agg_filter) id=agg_filter_sec_1909
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1910: agg_filter (agg_filter) id=agg_filter_sec_1910
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1911: agg_filter (agg_filter) id=agg_filter_sec_1911
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1912: agg_filter (agg_filter) id=agg_filter_sec_1912
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1913: agg_filter (agg_filter) id=agg_filter_sec_1913
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1914: agg_filter (agg_filter) id=agg_filter_sec_1914
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1915: agg_filter (agg_filter) id=agg_filter_sec_1915
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1916: agg_filter (agg_filter) id=agg_filter_sec_1916
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1917: agg_filter (agg_filter) id=agg_filter_sec_1917
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1918: agg_filter (agg_filter) id=agg_filter_sec_1918
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1919: agg_filter (agg_filter) id=agg_filter_sec_1919
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1920: agg_filter (agg_filter) id=agg_filter_sec_1920
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1921: agg_filter (agg_filter) id=agg_filter_sec_1921
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1922: agg_filter (agg_filter) id=agg_filter_sec_1922
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1923: agg_filter (agg_filter) id=agg_filter_sec_1923
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1924: agg_filter (agg_filter) id=agg_filter_sec_1924
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1925: agg_filter (agg_filter) id=agg_filter_sec_1925
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1926: agg_filter (agg_filter) id=agg_filter_sec_1926
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1927: agg_filter (agg_filter) id=agg_filter_sec_1927
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1928: agg_filter (agg_filter) id=agg_filter_sec_1928
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1929: agg_filter (agg_filter) id=agg_filter_sec_1929
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1930: agg_filter (agg_filter) id=agg_filter_sec_1930
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1931: agg_filter (agg_filter) id=agg_filter_sec_1931
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1932: agg_filter (agg_filter) id=agg_filter_sec_1932
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1933: agg_filter (agg_filter) id=agg_filter_sec_1933
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1934: agg_filter (agg_filter) id=agg_filter_sec_1934
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1935: agg_filter (agg_filter) id=agg_filter_sec_1935
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1936: agg_filter (agg_filter) id=agg_filter_sec_1936
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1937: agg_filter (agg_filter) id=agg_filter_sec_1937
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1938: agg_filter (agg_filter) id=agg_filter_sec_1938
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1939: agg_filter (agg_filter) id=agg_filter_sec_1939
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1940: agg_filter (agg_filter) id=agg_filter_sec_1940
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1941: agg_filter (agg_filter) id=agg_filter_sec_1941
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1942: agg_filter (agg_filter) id=agg_filter_sec_1942
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1943: agg_filter (agg_filter) id=agg_filter_sec_1943
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1944: agg_filter (agg_filter) id=agg_filter_sec_1944
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1945: agg_filter (agg_filter) id=agg_filter_sec_1945
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1946: agg_filter (agg_filter) id=agg_filter_sec_1946
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1947: agg_filter (agg_filter) id=agg_filter_sec_1947
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1948: agg_filter (agg_filter) id=agg_filter_sec_1948
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1949: agg_filter (agg_filter) id=agg_filter_sec_1949
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1950: agg_filter (agg_filter) id=agg_filter_sec_1950
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1951: agg_filter (agg_filter) id=agg_filter_sec_1951
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1952: agg_filter (agg_filter) id=agg_filter_sec_1952
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1953: agg_filter (agg_filter) id=agg_filter_sec_1953
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1954: agg_filter (agg_filter) id=agg_filter_sec_1954
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1955: agg_filter (agg_filter) id=agg_filter_sec_1955
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1956: agg_filter (agg_filter) id=agg_filter_sec_1956
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1957: agg_filter (agg_filter) id=agg_filter_sec_1957
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1958: agg_filter (agg_filter) id=agg_filter_sec_1958
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1959: agg_filter (agg_filter) id=agg_filter_sec_1959
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1960: agg_filter (agg_filter) id=agg_filter_sec_1960
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1961: agg_filter (agg_filter) id=agg_filter_sec_1961
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1962: agg_filter (agg_filter) id=agg_filter_sec_1962
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1963: agg_filter (agg_filter) id=agg_filter_sec_1963
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1964: agg_filter (agg_filter) id=agg_filter_sec_1964
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1965: agg_filter (agg_filter) id=agg_filter_sec_1965
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1966: agg_filter (agg_filter) id=agg_filter_sec_1966
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1967: agg_filter (agg_filter) id=agg_filter_sec_1967
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1968: agg_filter (agg_filter) id=agg_filter_sec_1968
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1969: agg_filter (agg_filter) id=agg_filter_sec_1969
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1970: agg_filter (agg_filter) id=agg_filter_sec_1970
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1971: agg_filter (agg_filter) id=agg_filter_sec_1971
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1972: agg_filter (agg_filter) id=agg_filter_sec_1972
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1973: agg_filter (agg_filter) id=agg_filter_sec_1973
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1974: agg_filter (agg_filter) id=agg_filter_sec_1974
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1975: agg_filter (agg_filter) id=agg_filter_sec_1975
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1976: agg_filter (agg_filter) id=agg_filter_sec_1976
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 1977: agg_filter (agg_filter) id=agg_filter_sec_1977
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 1978: agg_filter (agg_filter) id=agg_filter_sec_1978
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 1979: agg_filter (agg_filter) id=agg_filter_sec_1979
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 1980: agg_filter (agg_filter) id=agg_filter_sec_1980
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 1981: agg_filter (agg_filter) id=agg_filter_sec_1981
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 1982: agg_filter (agg_filter) id=agg_filter_sec_1982
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 1983: agg_filter (agg_filter) id=agg_filter_sec_1983
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 1984: agg_filter (agg_filter) id=agg_filter_sec_1984
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 1985: agg_filter (agg_filter) id=agg_filter_sec_1985
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 1986: agg_filter (agg_filter) id=agg_filter_sec_1986
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 1987: agg_filter (agg_filter) id=agg_filter_sec_1987
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 1988: agg_filter (agg_filter) id=agg_filter_sec_1988
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 1989: agg_filter (agg_filter) id=agg_filter_sec_1989
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 1990: agg_filter (agg_filter) id=agg_filter_sec_1990
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 1991: agg_filter (agg_filter) id=agg_filter_sec_1991
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 1992: agg_filter (agg_filter) id=agg_filter_sec_1992
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 1993: agg_filter (agg_filter) id=agg_filter_sec_1993
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 1994: agg_filter (agg_filter) id=agg_filter_sec_1994
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 1995: agg_filter (agg_filter) id=agg_filter_sec_1995
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 1996: agg_filter (agg_filter) id=agg_filter_sec_1996
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 1997: agg_filter (agg_filter) id=agg_filter_sec_1997
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 1998: agg_filter (agg_filter) id=agg_filter_sec_1998
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 1999: agg_filter (agg_filter) id=agg_filter_sec_1999
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 2000: agg_filter (agg_filter) id=agg_filter_sec_2000
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 2001: agg_filter (agg_filter) id=agg_filter_sec_2001
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 2002: agg_filter (agg_filter) id=agg_filter_sec_2002
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 2003: agg_filter (agg_filter) id=agg_filter_sec_2003
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 2004: agg_filter (agg_filter) id=agg_filter_sec_2004
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 2005: agg_filter (agg_filter) id=agg_filter_sec_2005
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 2006: agg_filter (agg_filter) id=agg_filter_sec_2006
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 2007: agg_filter (agg_filter) id=agg_filter_sec_2007
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 2008: agg_filter (agg_filter) id=agg_filter_sec_2008
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 2009: agg_filter (agg_filter) id=agg_filter_sec_2009
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 2010: agg_filter (agg_filter) id=agg_filter_sec_2010
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 2011: agg_filter (agg_filter) id=agg_filter_sec_2011
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 2012: agg_filter (agg_filter) id=agg_filter_sec_2012
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 2013: agg_filter (agg_filter) id=agg_filter_sec_2013
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 2014: agg_filter (agg_filter) id=agg_filter_sec_2014
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 2015: agg_filter (agg_filter) id=agg_filter_sec_2015
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 2016: agg_filter (agg_filter) id=agg_filter_sec_2016
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 2017: agg_filter (agg_filter) id=agg_filter_sec_2017
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 2018: agg_filter (agg_filter) id=agg_filter_sec_2018
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 2019: agg_filter (agg_filter) id=agg_filter_sec_2019
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 2020: agg_filter (agg_filter) id=agg_filter_sec_2020
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 2021: agg_filter (agg_filter) id=agg_filter_sec_2021
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 2022: agg_filter (agg_filter) id=agg_filter_sec_2022
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 2023: agg_filter (agg_filter) id=agg_filter_sec_2023
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 2024: agg_filter (agg_filter) id=agg_filter_sec_2024
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 2025: agg_filter (agg_filter) id=agg_filter_sec_2025
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 2026: agg_filter (agg_filter) id=agg_filter_sec_2026
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 2027: agg_filter (agg_filter) id=agg_filter_sec_2027
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 2028: agg_filter (agg_filter) id=agg_filter_sec_2028
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 2029: agg_filter (agg_filter) id=agg_filter_sec_2029
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 2030: agg_filter (agg_filter) id=agg_filter_sec_2030
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 2031: agg_filter (agg_filter) id=agg_filter_sec_2031
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 2032: agg_filter (agg_filter) id=agg_filter_sec_2032
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 2033: agg_filter (agg_filter) id=agg_filter_sec_2033
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 2034: agg_filter (agg_filter) id=agg_filter_sec_2034
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 2035: agg_filter (agg_filter) id=agg_filter_sec_2035
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 2036: agg_filter (agg_filter) id=agg_filter_sec_2036
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 2037: agg_filter (agg_filter) id=agg_filter_sec_2037
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 2038: agg_filter (agg_filter) id=agg_filter_sec_2038
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 2039: agg_filter (agg_filter) id=agg_filter_sec_2039
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 2040: agg_filter (agg_filter) id=agg_filter_sec_2040
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 2041: agg_filter (agg_filter) id=agg_filter_sec_2041
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 2042: agg_filter (agg_filter) id=agg_filter_sec_2042
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 2043: agg_filter (agg_filter) id=agg_filter_sec_2043
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 2044: agg_filter (agg_filter) id=agg_filter_sec_2044
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 2045: agg_filter (agg_filter) id=agg_filter_sec_2045
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 2046: agg_filter (agg_filter) id=agg_filter_sec_2046
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 2047: agg_filter (agg_filter) id=agg_filter_sec_2047
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 2048: agg_filter (agg_filter) id=agg_filter_sec_2048
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 2049: agg_filter (agg_filter) id=agg_filter_sec_2049
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 2050: agg_filter (agg_filter) id=agg_filter_sec_2050
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 2051: agg_filter (agg_filter) id=agg_filter_sec_2051
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 2052: agg_filter (agg_filter) id=agg_filter_sec_2052
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 2053: agg_filter (agg_filter) id=agg_filter_sec_2053
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 2054: agg_filter (agg_filter) id=agg_filter_sec_2054
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 2055: agg_filter (agg_filter) id=agg_filter_sec_2055
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 2056: agg_filter (agg_filter) id=agg_filter_sec_2056
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 2057: agg_filter (agg_filter) id=agg_filter_sec_2057
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 2058: agg_filter (agg_filter) id=agg_filter_sec_2058
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 2059: agg_filter (agg_filter) id=agg_filter_sec_2059
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 2060: agg_filter (agg_filter) id=agg_filter_sec_2060
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 2061: agg_filter (agg_filter) id=agg_filter_sec_2061
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 2062: agg_filter (agg_filter) id=agg_filter_sec_2062
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 2063: agg_filter (agg_filter) id=agg_filter_sec_2063
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 2064: agg_filter (agg_filter) id=agg_filter_sec_2064
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 2065: agg_filter (agg_filter) id=agg_filter_sec_2065
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 2066: agg_filter (agg_filter) id=agg_filter_sec_2066
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 2067: agg_filter (agg_filter) id=agg_filter_sec_2067
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 2068: agg_filter (agg_filter) id=agg_filter_sec_2068
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 2069: agg_filter (agg_filter) id=agg_filter_sec_2069
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 2070: agg_filter (agg_filter) id=agg_filter_sec_2070
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 2071: agg_filter (agg_filter) id=agg_filter_sec_2071
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 2072: agg_filter (agg_filter) id=agg_filter_sec_2072
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 2073: agg_filter (agg_filter) id=agg_filter_sec_2073
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 2074: agg_filter (agg_filter) id=agg_filter_sec_2074
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 2075: agg_filter (agg_filter) id=agg_filter_sec_2075
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 2076: agg_filter (agg_filter) id=agg_filter_sec_2076
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 2077: agg_filter (agg_filter) id=agg_filter_sec_2077
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 2078: agg_filter (agg_filter) id=agg_filter_sec_2078
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 2079: agg_filter (agg_filter) id=agg_filter_sec_2079
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 2080: agg_filter (agg_filter) id=agg_filter_sec_2080
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 2081: agg_filter (agg_filter) id=agg_filter_sec_2081
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 2082: agg_filter (agg_filter) id=agg_filter_sec_2082
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 2083: agg_filter (agg_filter) id=agg_filter_sec_2083
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 2084: agg_filter (agg_filter) id=agg_filter_sec_2084
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 2085: agg_filter (agg_filter) id=agg_filter_sec_2085
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 2086: agg_filter (agg_filter) id=agg_filter_sec_2086
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 2087: agg_filter (agg_filter) id=agg_filter_sec_2087
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 2088: agg_filter (agg_filter) id=agg_filter_sec_2088
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 2089: agg_filter (agg_filter) id=agg_filter_sec_2089
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 2090: agg_filter (agg_filter) id=agg_filter_sec_2090
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 2091: agg_filter (agg_filter) id=agg_filter_sec_2091
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 2092: agg_filter (agg_filter) id=agg_filter_sec_2092
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 2093: agg_filter (agg_filter) id=agg_filter_sec_2093
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 2094: agg_filter (agg_filter) id=agg_filter_sec_2094
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 2095: agg_filter (agg_filter) id=agg_filter_sec_2095
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 2096: agg_filter (agg_filter) id=agg_filter_sec_2096
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 2097: agg_filter (agg_filter) id=agg_filter_sec_2097
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 2098: agg_filter (agg_filter) id=agg_filter_sec_2098
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 2099: agg_filter (agg_filter) id=agg_filter_sec_2099
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 2100: agg_filter (agg_filter) id=agg_filter_sec_2100
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 2101: agg_filter (agg_filter) id=agg_filter_sec_2101
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 2102: agg_filter (agg_filter) id=agg_filter_sec_2102
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 2103: agg_filter (agg_filter) id=agg_filter_sec_2103
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 2104: agg_filter (agg_filter) id=agg_filter_sec_2104
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 2105: agg_filter (agg_filter) id=agg_filter_sec_2105
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 2106: agg_filter (agg_filter) id=agg_filter_sec_2106
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 2107: agg_filter (agg_filter) id=agg_filter_sec_2107
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 2108: agg_filter (agg_filter) id=agg_filter_sec_2108
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 2109: agg_filter (agg_filter) id=agg_filter_sec_2109
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 2110: agg_filter (agg_filter) id=agg_filter_sec_2110
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 2111: agg_filter (agg_filter) id=agg_filter_sec_2111
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 2112: agg_filter (agg_filter) id=agg_filter_sec_2112
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 2113: agg_filter (agg_filter) id=agg_filter_sec_2113
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 2114: agg_filter (agg_filter) id=agg_filter_sec_2114
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 2115: agg_filter (agg_filter) id=agg_filter_sec_2115
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 2116: agg_filter (agg_filter) id=agg_filter_sec_2116
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 2117: agg_filter (agg_filter) id=agg_filter_sec_2117
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 2118: agg_filter (agg_filter) id=agg_filter_sec_2118
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 2119: agg_filter (agg_filter) id=agg_filter_sec_2119
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 2120: agg_filter (agg_filter) id=agg_filter_sec_2120
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 2121: agg_filter (agg_filter) id=agg_filter_sec_2121
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 2122: agg_filter (agg_filter) id=agg_filter_sec_2122
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 2123: agg_filter (agg_filter) id=agg_filter_sec_2123
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 2124: agg_filter (agg_filter) id=agg_filter_sec_2124
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 2125: agg_filter (agg_filter) id=agg_filter_sec_2125
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 2126: agg_filter (agg_filter) id=agg_filter_sec_2126
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 2127: agg_filter (agg_filter) id=agg_filter_sec_2127
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 2128: agg_filter (agg_filter) id=agg_filter_sec_2128
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 2129: agg_filter (agg_filter) id=agg_filter_sec_2129
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 2130: agg_filter (agg_filter) id=agg_filter_sec_2130
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 2131: agg_filter (agg_filter) id=agg_filter_sec_2131
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 2132: agg_filter (agg_filter) id=agg_filter_sec_2132
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 2133: agg_filter (agg_filter) id=agg_filter_sec_2133
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 2134: agg_filter (agg_filter) id=agg_filter_sec_2134
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 2135: agg_filter (agg_filter) id=agg_filter_sec_2135
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 2136: agg_filter (agg_filter) id=agg_filter_sec_2136
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 2137: agg_filter (agg_filter) id=agg_filter_sec_2137
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 2138: agg_filter (agg_filter) id=agg_filter_sec_2138
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 2139: agg_filter (agg_filter) id=agg_filter_sec_2139
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 2140: agg_filter (agg_filter) id=agg_filter_sec_2140
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 2141: agg_filter (agg_filter) id=agg_filter_sec_2141
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 2142: agg_filter (agg_filter) id=agg_filter_sec_2142
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 2143: agg_filter (agg_filter) id=agg_filter_sec_2143
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 2144: agg_filter (agg_filter) id=agg_filter_sec_2144
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 2145: agg_filter (agg_filter) id=agg_filter_sec_2145
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 2146: agg_filter (agg_filter) id=agg_filter_sec_2146
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 2147: agg_filter (agg_filter) id=agg_filter_sec_2147
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 2148: agg_filter (agg_filter) id=agg_filter_sec_2148
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 2149: agg_filter (agg_filter) id=agg_filter_sec_2149
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 2150: agg_filter (agg_filter) id=agg_filter_sec_2150
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 2151: agg_filter (agg_filter) id=agg_filter_sec_2151
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 2152: agg_filter (agg_filter) id=agg_filter_sec_2152
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 2153: agg_filter (agg_filter) id=agg_filter_sec_2153
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 2154: agg_filter (agg_filter) id=agg_filter_sec_2154
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 2155: agg_filter (agg_filter) id=agg_filter_sec_2155
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 2156: agg_filter (agg_filter) id=agg_filter_sec_2156
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 2157: agg_filter (agg_filter) id=agg_filter_sec_2157
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 2158: agg_filter (agg_filter) id=agg_filter_sec_2158
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 2159: agg_filter (agg_filter) id=agg_filter_sec_2159
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 2160: agg_filter (agg_filter) id=agg_filter_sec_2160
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 2161: agg_filter (agg_filter) id=agg_filter_sec_2161
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 2162: agg_filter (agg_filter) id=agg_filter_sec_2162
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 2163: agg_filter (agg_filter) id=agg_filter_sec_2163
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 2164: agg_filter (agg_filter) id=agg_filter_sec_2164
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 2165: agg_filter (agg_filter) id=agg_filter_sec_2165
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 2166: agg_filter (agg_filter) id=agg_filter_sec_2166
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 2167: agg_filter (agg_filter) id=agg_filter_sec_2167
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 2168: agg_filter (agg_filter) id=agg_filter_sec_2168
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 2169: agg_filter (agg_filter) id=agg_filter_sec_2169
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 2170: agg_filter (agg_filter) id=agg_filter_sec_2170
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 2171: agg_filter (agg_filter) id=agg_filter_sec_2171
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 2172: agg_filter (agg_filter) id=agg_filter_sec_2172
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 2173: agg_filter (agg_filter) id=agg_filter_sec_2173
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 2174: agg_filter (agg_filter) id=agg_filter_sec_2174
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 2175: agg_filter (agg_filter) id=agg_filter_sec_2175
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 2176: agg_filter (agg_filter) id=agg_filter_sec_2176
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 2177: agg_filter (agg_filter) id=agg_filter_sec_2177
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 2178: agg_filter (agg_filter) id=agg_filter_sec_2178
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 2179: agg_filter (agg_filter) id=agg_filter_sec_2179
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 2180: agg_filter (agg_filter) id=agg_filter_sec_2180
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 2181: agg_filter (agg_filter) id=agg_filter_sec_2181
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 2182: agg_filter (agg_filter) id=agg_filter_sec_2182
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 2183: agg_filter (agg_filter) id=agg_filter_sec_2183
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 2184: agg_filter (agg_filter) id=agg_filter_sec_2184
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 2185: agg_filter (agg_filter) id=agg_filter_sec_2185
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 2186: agg_filter (agg_filter) id=agg_filter_sec_2186
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE form_type = '10-K' GROUP BY sic_description;

-- Query 2187: agg_filter (agg_filter) id=agg_filter_sec_2187
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE form_type = '10-Q' GROUP BY sic_description;

-- Query 2188: agg_filter (agg_filter) id=agg_filter_sec_2188
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY sic_description;

-- Query 2189: agg_filter (agg_filter) id=agg_filter_sec_2189
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY sic_description;

-- Query 2190: agg_filter (agg_filter) id=agg_filter_sec_2190
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY sic_description;

-- Query 2191: agg_filter (agg_filter) id=agg_filter_sec_2191
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY sic_description;

-- Query 2192: agg_filter (agg_filter) id=agg_filter_sec_2192
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY sic_description;

-- Query 2193: agg_filter (agg_filter) id=agg_filter_sec_2193
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY sic_description;

-- Query 2194: agg_filter (agg_filter) id=agg_filter_sec_2194
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY sic_description;

-- Query 2195: agg_filter (agg_filter) id=agg_filter_sec_2195
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY sic_description;

-- Query 2196: agg_filter (agg_filter) id=agg_filter_sec_2196
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY sic_description;

-- Query 2197: agg_filter (agg_filter) id=agg_filter_sec_2197
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY sic_description;

-- Query 2198: agg_filter (agg_filter) id=agg_filter_sec_2198
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY sic_description;

-- Query 2199: agg_filter (agg_filter) id=agg_filter_sec_2199
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY sic_description;

-- Query 2200: agg_filter (agg_filter) id=agg_filter_sec_2200
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY sic_description;

-- Query 2201: agg_filter (agg_filter) id=agg_filter_sec_2201
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY sic_description;

-- Query 2202: agg_filter (agg_filter) id=agg_filter_sec_2202
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY sic_description;

-- Query 2203: agg_filter (agg_filter) id=agg_filter_sec_2203
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY sic_description;

-- Query 2204: agg_filter (agg_filter) id=agg_filter_sec_2204
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE revenue_usd > 0 GROUP BY sic_description;

-- Query 2205: agg_filter (agg_filter) id=agg_filter_sec_2205
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE net_income_usd > 0 GROUP BY sic_description;

-- Query 2206: agg_filter (agg_filter) id=agg_filter_sec_2206
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE net_income_usd < 0 GROUP BY sic_description;

-- Query 2207: agg_filter (agg_filter) id=agg_filter_sec_2207
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY sic_description;

-- Query 2208: agg_filter (agg_filter) id=agg_filter_sec_2208
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY sic_description;

-- Query 2209: agg_filter (agg_filter) id=agg_filter_sec_2209
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2210: agg_filter (agg_filter) id=agg_filter_sec_2210
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2211: agg_filter (agg_filter) id=agg_filter_sec_2211
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2212: agg_filter (agg_filter) id=agg_filter_sec_2212
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2213: agg_filter (agg_filter) id=agg_filter_sec_2213
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2214: agg_filter (agg_filter) id=agg_filter_sec_2214
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2215: agg_filter (agg_filter) id=agg_filter_sec_2215
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2216: agg_filter (agg_filter) id=agg_filter_sec_2216
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2217: agg_filter (agg_filter) id=agg_filter_sec_2217
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2218: agg_filter (agg_filter) id=agg_filter_sec_2218
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2219: agg_filter (agg_filter) id=agg_filter_sec_2219
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2220: agg_filter (agg_filter) id=agg_filter_sec_2220
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2221: agg_filter (agg_filter) id=agg_filter_sec_2221
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2222: agg_filter (agg_filter) id=agg_filter_sec_2222
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2223: agg_filter (agg_filter) id=agg_filter_sec_2223
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2224: agg_filter (agg_filter) id=agg_filter_sec_2224
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2225: agg_filter (agg_filter) id=agg_filter_sec_2225
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2226: agg_filter (agg_filter) id=agg_filter_sec_2226
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2227: agg_filter (agg_filter) id=agg_filter_sec_2227
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2228: agg_filter (agg_filter) id=agg_filter_sec_2228
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2229: agg_filter (agg_filter) id=agg_filter_sec_2229
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2230: agg_filter (agg_filter) id=agg_filter_sec_2230
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2231: agg_filter (agg_filter) id=agg_filter_sec_2231
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2232: agg_filter (agg_filter) id=agg_filter_sec_2232
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2233: agg_filter (agg_filter) id=agg_filter_sec_2233
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2234: agg_filter (agg_filter) id=agg_filter_sec_2234
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2235: agg_filter (agg_filter) id=agg_filter_sec_2235
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2236: agg_filter (agg_filter) id=agg_filter_sec_2236
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2237: agg_filter (agg_filter) id=agg_filter_sec_2237
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2238: agg_filter (agg_filter) id=agg_filter_sec_2238
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2239: agg_filter (agg_filter) id=agg_filter_sec_2239
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2240: agg_filter (agg_filter) id=agg_filter_sec_2240
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2241: agg_filter (agg_filter) id=agg_filter_sec_2241
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2242: agg_filter (agg_filter) id=agg_filter_sec_2242
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2243: agg_filter (agg_filter) id=agg_filter_sec_2243
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2244: agg_filter (agg_filter) id=agg_filter_sec_2244
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2245: agg_filter (agg_filter) id=agg_filter_sec_2245
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2246: agg_filter (agg_filter) id=agg_filter_sec_2246
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2247: agg_filter (agg_filter) id=agg_filter_sec_2247
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2248: agg_filter (agg_filter) id=agg_filter_sec_2248
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2249: agg_filter (agg_filter) id=agg_filter_sec_2249
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2250: agg_filter (agg_filter) id=agg_filter_sec_2250
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2251: agg_filter (agg_filter) id=agg_filter_sec_2251
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2252: agg_filter (agg_filter) id=agg_filter_sec_2252
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2253: agg_filter (agg_filter) id=agg_filter_sec_2253
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2254: agg_filter (agg_filter) id=agg_filter_sec_2254
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2255: agg_filter (agg_filter) id=agg_filter_sec_2255
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2256: agg_filter (agg_filter) id=agg_filter_sec_2256
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2257: agg_filter (agg_filter) id=agg_filter_sec_2257
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2258: agg_filter (agg_filter) id=agg_filter_sec_2258
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2259: agg_filter (agg_filter) id=agg_filter_sec_2259
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2260: agg_filter (agg_filter) id=agg_filter_sec_2260
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2261: agg_filter (agg_filter) id=agg_filter_sec_2261
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2262: agg_filter (agg_filter) id=agg_filter_sec_2262
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2263: agg_filter (agg_filter) id=agg_filter_sec_2263
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2264: agg_filter (agg_filter) id=agg_filter_sec_2264
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2265: agg_filter (agg_filter) id=agg_filter_sec_2265
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2266: agg_filter (agg_filter) id=agg_filter_sec_2266
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2267: agg_filter (agg_filter) id=agg_filter_sec_2267
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2268: agg_filter (agg_filter) id=agg_filter_sec_2268
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2269: agg_filter (agg_filter) id=agg_filter_sec_2269
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2270: agg_filter (agg_filter) id=agg_filter_sec_2270
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2271: agg_filter (agg_filter) id=agg_filter_sec_2271
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2272: agg_filter (agg_filter) id=agg_filter_sec_2272
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2273: agg_filter (agg_filter) id=agg_filter_sec_2273
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2274: agg_filter (agg_filter) id=agg_filter_sec_2274
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2275: agg_filter (agg_filter) id=agg_filter_sec_2275
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2276: agg_filter (agg_filter) id=agg_filter_sec_2276
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2277: agg_filter (agg_filter) id=agg_filter_sec_2277
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2278: agg_filter (agg_filter) id=agg_filter_sec_2278
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2279: agg_filter (agg_filter) id=agg_filter_sec_2279
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2280: agg_filter (agg_filter) id=agg_filter_sec_2280
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2281: agg_filter (agg_filter) id=agg_filter_sec_2281
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2282: agg_filter (agg_filter) id=agg_filter_sec_2282
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2283: agg_filter (agg_filter) id=agg_filter_sec_2283
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2284: agg_filter (agg_filter) id=agg_filter_sec_2284
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2285: agg_filter (agg_filter) id=agg_filter_sec_2285
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2286: agg_filter (agg_filter) id=agg_filter_sec_2286
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2287: agg_filter (agg_filter) id=agg_filter_sec_2287
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2288: agg_filter (agg_filter) id=agg_filter_sec_2288
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2289: agg_filter (agg_filter) id=agg_filter_sec_2289
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2290: agg_filter (agg_filter) id=agg_filter_sec_2290
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2291: agg_filter (agg_filter) id=agg_filter_sec_2291
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2292: agg_filter (agg_filter) id=agg_filter_sec_2292
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2293: agg_filter (agg_filter) id=agg_filter_sec_2293
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2294: agg_filter (agg_filter) id=agg_filter_sec_2294
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2295: agg_filter (agg_filter) id=agg_filter_sec_2295
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2296: agg_filter (agg_filter) id=agg_filter_sec_2296
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2297: agg_filter (agg_filter) id=agg_filter_sec_2297
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2298: agg_filter (agg_filter) id=agg_filter_sec_2298
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2299: agg_filter (agg_filter) id=agg_filter_sec_2299
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2300: agg_filter (agg_filter) id=agg_filter_sec_2300
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2301: agg_filter (agg_filter) id=agg_filter_sec_2301
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2302: agg_filter (agg_filter) id=agg_filter_sec_2302
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2303: agg_filter (agg_filter) id=agg_filter_sec_2303
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2304: agg_filter (agg_filter) id=agg_filter_sec_2304
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2305: agg_filter (agg_filter) id=agg_filter_sec_2305
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2306: agg_filter (agg_filter) id=agg_filter_sec_2306
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2307: agg_filter (agg_filter) id=agg_filter_sec_2307
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2308: agg_filter (agg_filter) id=agg_filter_sec_2308
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2309: agg_filter (agg_filter) id=agg_filter_sec_2309
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2310: agg_filter (agg_filter) id=agg_filter_sec_2310
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2311: agg_filter (agg_filter) id=agg_filter_sec_2311
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2312: agg_filter (agg_filter) id=agg_filter_sec_2312
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2313: agg_filter (agg_filter) id=agg_filter_sec_2313
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2314: agg_filter (agg_filter) id=agg_filter_sec_2314
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2315: agg_filter (agg_filter) id=agg_filter_sec_2315
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2316: agg_filter (agg_filter) id=agg_filter_sec_2316
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2317: agg_filter (agg_filter) id=agg_filter_sec_2317
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2318: agg_filter (agg_filter) id=agg_filter_sec_2318
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2319: agg_filter (agg_filter) id=agg_filter_sec_2319
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2320: agg_filter (agg_filter) id=agg_filter_sec_2320
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2321: agg_filter (agg_filter) id=agg_filter_sec_2321
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2322: agg_filter (agg_filter) id=agg_filter_sec_2322
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2323: agg_filter (agg_filter) id=agg_filter_sec_2323
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2324: agg_filter (agg_filter) id=agg_filter_sec_2324
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2325: agg_filter (agg_filter) id=agg_filter_sec_2325
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2326: agg_filter (agg_filter) id=agg_filter_sec_2326
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2327: agg_filter (agg_filter) id=agg_filter_sec_2327
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2328: agg_filter (agg_filter) id=agg_filter_sec_2328
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2329: agg_filter (agg_filter) id=agg_filter_sec_2329
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2330: agg_filter (agg_filter) id=agg_filter_sec_2330
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2331: agg_filter (agg_filter) id=agg_filter_sec_2331
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2332: agg_filter (agg_filter) id=agg_filter_sec_2332
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2333: agg_filter (agg_filter) id=agg_filter_sec_2333
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2334: agg_filter (agg_filter) id=agg_filter_sec_2334
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2335: agg_filter (agg_filter) id=agg_filter_sec_2335
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2336: agg_filter (agg_filter) id=agg_filter_sec_2336
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2337: agg_filter (agg_filter) id=agg_filter_sec_2337
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2338: agg_filter (agg_filter) id=agg_filter_sec_2338
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2339: agg_filter (agg_filter) id=agg_filter_sec_2339
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2340: agg_filter (agg_filter) id=agg_filter_sec_2340
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2341: agg_filter (agg_filter) id=agg_filter_sec_2341
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2342: agg_filter (agg_filter) id=agg_filter_sec_2342
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2343: agg_filter (agg_filter) id=agg_filter_sec_2343
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2344: agg_filter (agg_filter) id=agg_filter_sec_2344
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2345: agg_filter (agg_filter) id=agg_filter_sec_2345
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2346: agg_filter (agg_filter) id=agg_filter_sec_2346
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2347: agg_filter (agg_filter) id=agg_filter_sec_2347
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2348: agg_filter (agg_filter) id=agg_filter_sec_2348
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2349: agg_filter (agg_filter) id=agg_filter_sec_2349
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2350: agg_filter (agg_filter) id=agg_filter_sec_2350
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2351: agg_filter (agg_filter) id=agg_filter_sec_2351
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2352: agg_filter (agg_filter) id=agg_filter_sec_2352
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2353: agg_filter (agg_filter) id=agg_filter_sec_2353
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2354: agg_filter (agg_filter) id=agg_filter_sec_2354
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2355: agg_filter (agg_filter) id=agg_filter_sec_2355
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2356: agg_filter (agg_filter) id=agg_filter_sec_2356
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2357: agg_filter (agg_filter) id=agg_filter_sec_2357
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2358: agg_filter (agg_filter) id=agg_filter_sec_2358
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2359: agg_filter (agg_filter) id=agg_filter_sec_2359
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2360: agg_filter (agg_filter) id=agg_filter_sec_2360
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2361: agg_filter (agg_filter) id=agg_filter_sec_2361
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2362: agg_filter (agg_filter) id=agg_filter_sec_2362
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2363: agg_filter (agg_filter) id=agg_filter_sec_2363
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2364: agg_filter (agg_filter) id=agg_filter_sec_2364
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2365: agg_filter (agg_filter) id=agg_filter_sec_2365
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2366: agg_filter (agg_filter) id=agg_filter_sec_2366
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2367: agg_filter (agg_filter) id=agg_filter_sec_2367
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2368: agg_filter (agg_filter) id=agg_filter_sec_2368
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2369: agg_filter (agg_filter) id=agg_filter_sec_2369
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2370: agg_filter (agg_filter) id=agg_filter_sec_2370
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2371: agg_filter (agg_filter) id=agg_filter_sec_2371
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2372: agg_filter (agg_filter) id=agg_filter_sec_2372
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2373: agg_filter (agg_filter) id=agg_filter_sec_2373
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2374: agg_filter (agg_filter) id=agg_filter_sec_2374
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2375: agg_filter (agg_filter) id=agg_filter_sec_2375
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2376: agg_filter (agg_filter) id=agg_filter_sec_2376
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2377: agg_filter (agg_filter) id=agg_filter_sec_2377
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2378: agg_filter (agg_filter) id=agg_filter_sec_2378
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2379: agg_filter (agg_filter) id=agg_filter_sec_2379
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2380: agg_filter (agg_filter) id=agg_filter_sec_2380
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2381: agg_filter (agg_filter) id=agg_filter_sec_2381
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2382: agg_filter (agg_filter) id=agg_filter_sec_2382
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2383: agg_filter (agg_filter) id=agg_filter_sec_2383
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2384: agg_filter (agg_filter) id=agg_filter_sec_2384
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2385: agg_filter (agg_filter) id=agg_filter_sec_2385
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2386: agg_filter (agg_filter) id=agg_filter_sec_2386
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2387: agg_filter (agg_filter) id=agg_filter_sec_2387
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2388: agg_filter (agg_filter) id=agg_filter_sec_2388
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2389: agg_filter (agg_filter) id=agg_filter_sec_2389
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2390: agg_filter (agg_filter) id=agg_filter_sec_2390
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2391: agg_filter (agg_filter) id=agg_filter_sec_2391
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2392: agg_filter (agg_filter) id=agg_filter_sec_2392
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2393: agg_filter (agg_filter) id=agg_filter_sec_2393
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2394: agg_filter (agg_filter) id=agg_filter_sec_2394
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2395: agg_filter (agg_filter) id=agg_filter_sec_2395
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2396: agg_filter (agg_filter) id=agg_filter_sec_2396
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2397: agg_filter (agg_filter) id=agg_filter_sec_2397
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2398: agg_filter (agg_filter) id=agg_filter_sec_2398
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2399: agg_filter (agg_filter) id=agg_filter_sec_2399
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2400: agg_filter (agg_filter) id=agg_filter_sec_2400
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2401: agg_filter (agg_filter) id=agg_filter_sec_2401
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2402: agg_filter (agg_filter) id=agg_filter_sec_2402
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2403: agg_filter (agg_filter) id=agg_filter_sec_2403
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2404: agg_filter (agg_filter) id=agg_filter_sec_2404
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2405: agg_filter (agg_filter) id=agg_filter_sec_2405
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2406: agg_filter (agg_filter) id=agg_filter_sec_2406
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2407: agg_filter (agg_filter) id=agg_filter_sec_2407
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2408: agg_filter (agg_filter) id=agg_filter_sec_2408
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2409: agg_filter (agg_filter) id=agg_filter_sec_2409
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2410: agg_filter (agg_filter) id=agg_filter_sec_2410
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2411: agg_filter (agg_filter) id=agg_filter_sec_2411
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2412: agg_filter (agg_filter) id=agg_filter_sec_2412
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2413: agg_filter (agg_filter) id=agg_filter_sec_2413
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2414: agg_filter (agg_filter) id=agg_filter_sec_2414
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2415: agg_filter (agg_filter) id=agg_filter_sec_2415
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2416: agg_filter (agg_filter) id=agg_filter_sec_2416
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2417: agg_filter (agg_filter) id=agg_filter_sec_2417
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2418: agg_filter (agg_filter) id=agg_filter_sec_2418
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2419: agg_filter (agg_filter) id=agg_filter_sec_2419
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2420: agg_filter (agg_filter) id=agg_filter_sec_2420
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2421: agg_filter (agg_filter) id=agg_filter_sec_2421
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2422: agg_filter (agg_filter) id=agg_filter_sec_2422
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2423: agg_filter (agg_filter) id=agg_filter_sec_2423
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2424: agg_filter (agg_filter) id=agg_filter_sec_2424
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2425: agg_filter (agg_filter) id=agg_filter_sec_2425
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2426: agg_filter (agg_filter) id=agg_filter_sec_2426
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2427: agg_filter (agg_filter) id=agg_filter_sec_2427
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2428: agg_filter (agg_filter) id=agg_filter_sec_2428
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2429: agg_filter (agg_filter) id=agg_filter_sec_2429
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2430: agg_filter (agg_filter) id=agg_filter_sec_2430
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2431: agg_filter (agg_filter) id=agg_filter_sec_2431
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2432: agg_filter (agg_filter) id=agg_filter_sec_2432
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2433: agg_filter (agg_filter) id=agg_filter_sec_2433
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2434: agg_filter (agg_filter) id=agg_filter_sec_2434
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2435: agg_filter (agg_filter) id=agg_filter_sec_2435
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2436: agg_filter (agg_filter) id=agg_filter_sec_2436
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2437: agg_filter (agg_filter) id=agg_filter_sec_2437
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2438: agg_filter (agg_filter) id=agg_filter_sec_2438
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2439: agg_filter (agg_filter) id=agg_filter_sec_2439
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2440: agg_filter (agg_filter) id=agg_filter_sec_2440
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2441: agg_filter (agg_filter) id=agg_filter_sec_2441
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2442: agg_filter (agg_filter) id=agg_filter_sec_2442
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2443: agg_filter (agg_filter) id=agg_filter_sec_2443
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2444: agg_filter (agg_filter) id=agg_filter_sec_2444
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2445: agg_filter (agg_filter) id=agg_filter_sec_2445
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2446: agg_filter (agg_filter) id=agg_filter_sec_2446
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2447: agg_filter (agg_filter) id=agg_filter_sec_2447
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2448: agg_filter (agg_filter) id=agg_filter_sec_2448
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2449: agg_filter (agg_filter) id=agg_filter_sec_2449
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2450: agg_filter (agg_filter) id=agg_filter_sec_2450
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2451: agg_filter (agg_filter) id=agg_filter_sec_2451
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2452: agg_filter (agg_filter) id=agg_filter_sec_2452
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2453: agg_filter (agg_filter) id=agg_filter_sec_2453
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2454: agg_filter (agg_filter) id=agg_filter_sec_2454
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2455: agg_filter (agg_filter) id=agg_filter_sec_2455
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2456: agg_filter (agg_filter) id=agg_filter_sec_2456
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2457: agg_filter (agg_filter) id=agg_filter_sec_2457
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2458: agg_filter (agg_filter) id=agg_filter_sec_2458
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2459: agg_filter (agg_filter) id=agg_filter_sec_2459
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2460: agg_filter (agg_filter) id=agg_filter_sec_2460
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2461: agg_filter (agg_filter) id=agg_filter_sec_2461
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2462: agg_filter (agg_filter) id=agg_filter_sec_2462
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2463: agg_filter (agg_filter) id=agg_filter_sec_2463
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2464: agg_filter (agg_filter) id=agg_filter_sec_2464
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2465: agg_filter (agg_filter) id=agg_filter_sec_2465
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2466: agg_filter (agg_filter) id=agg_filter_sec_2466
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2467: agg_filter (agg_filter) id=agg_filter_sec_2467
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2468: agg_filter (agg_filter) id=agg_filter_sec_2468
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2469: agg_filter (agg_filter) id=agg_filter_sec_2469
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2470: agg_filter (agg_filter) id=agg_filter_sec_2470
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2471: agg_filter (agg_filter) id=agg_filter_sec_2471
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2472: agg_filter (agg_filter) id=agg_filter_sec_2472
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2473: agg_filter (agg_filter) id=agg_filter_sec_2473
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2474: agg_filter (agg_filter) id=agg_filter_sec_2474
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2475: agg_filter (agg_filter) id=agg_filter_sec_2475
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2476: agg_filter (agg_filter) id=agg_filter_sec_2476
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2477: agg_filter (agg_filter) id=agg_filter_sec_2477
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2478: agg_filter (agg_filter) id=agg_filter_sec_2478
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2479: agg_filter (agg_filter) id=agg_filter_sec_2479
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2480: agg_filter (agg_filter) id=agg_filter_sec_2480
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2481: agg_filter (agg_filter) id=agg_filter_sec_2481
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2482: agg_filter (agg_filter) id=agg_filter_sec_2482
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2483: agg_filter (agg_filter) id=agg_filter_sec_2483
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2484: agg_filter (agg_filter) id=agg_filter_sec_2484
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2485: agg_filter (agg_filter) id=agg_filter_sec_2485
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2486: agg_filter (agg_filter) id=agg_filter_sec_2486
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2487: agg_filter (agg_filter) id=agg_filter_sec_2487
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2488: agg_filter (agg_filter) id=agg_filter_sec_2488
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2489: agg_filter (agg_filter) id=agg_filter_sec_2489
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2490: agg_filter (agg_filter) id=agg_filter_sec_2490
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2491: agg_filter (agg_filter) id=agg_filter_sec_2491
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2492: agg_filter (agg_filter) id=agg_filter_sec_2492
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2493: agg_filter (agg_filter) id=agg_filter_sec_2493
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2494: agg_filter (agg_filter) id=agg_filter_sec_2494
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2495: agg_filter (agg_filter) id=agg_filter_sec_2495
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2496: agg_filter (agg_filter) id=agg_filter_sec_2496
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2497: agg_filter (agg_filter) id=agg_filter_sec_2497
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2498: agg_filter (agg_filter) id=agg_filter_sec_2498
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2499: agg_filter (agg_filter) id=agg_filter_sec_2499
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2500: agg_filter (agg_filter) id=agg_filter_sec_2500
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2501: agg_filter (agg_filter) id=agg_filter_sec_2501
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2502: agg_filter (agg_filter) id=agg_filter_sec_2502
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2503: agg_filter (agg_filter) id=agg_filter_sec_2503
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2504: agg_filter (agg_filter) id=agg_filter_sec_2504
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2505: agg_filter (agg_filter) id=agg_filter_sec_2505
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2506: agg_filter (agg_filter) id=agg_filter_sec_2506
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2507: agg_filter (agg_filter) id=agg_filter_sec_2507
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2508: agg_filter (agg_filter) id=agg_filter_sec_2508
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2509: agg_filter (agg_filter) id=agg_filter_sec_2509
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2510: agg_filter (agg_filter) id=agg_filter_sec_2510
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2511: agg_filter (agg_filter) id=agg_filter_sec_2511
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2512: agg_filter (agg_filter) id=agg_filter_sec_2512
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2513: agg_filter (agg_filter) id=agg_filter_sec_2513
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2514: agg_filter (agg_filter) id=agg_filter_sec_2514
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2515: agg_filter (agg_filter) id=agg_filter_sec_2515
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2516: agg_filter (agg_filter) id=agg_filter_sec_2516
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2517: agg_filter (agg_filter) id=agg_filter_sec_2517
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2518: agg_filter (agg_filter) id=agg_filter_sec_2518
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2519: agg_filter (agg_filter) id=agg_filter_sec_2519
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2520: agg_filter (agg_filter) id=agg_filter_sec_2520
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2521: agg_filter (agg_filter) id=agg_filter_sec_2521
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2522: agg_filter (agg_filter) id=agg_filter_sec_2522
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2523: agg_filter (agg_filter) id=agg_filter_sec_2523
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2524: agg_filter (agg_filter) id=agg_filter_sec_2524
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2525: agg_filter (agg_filter) id=agg_filter_sec_2525
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2526: agg_filter (agg_filter) id=agg_filter_sec_2526
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2527: agg_filter (agg_filter) id=agg_filter_sec_2527
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2528: agg_filter (agg_filter) id=agg_filter_sec_2528
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2529: agg_filter (agg_filter) id=agg_filter_sec_2529
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2530: agg_filter (agg_filter) id=agg_filter_sec_2530
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2531: agg_filter (agg_filter) id=agg_filter_sec_2531
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2532: agg_filter (agg_filter) id=agg_filter_sec_2532
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2533: agg_filter (agg_filter) id=agg_filter_sec_2533
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2534: agg_filter (agg_filter) id=agg_filter_sec_2534
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2535: agg_filter (agg_filter) id=agg_filter_sec_2535
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2536: agg_filter (agg_filter) id=agg_filter_sec_2536
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2537: agg_filter (agg_filter) id=agg_filter_sec_2537
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2538: agg_filter (agg_filter) id=agg_filter_sec_2538
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2539: agg_filter (agg_filter) id=agg_filter_sec_2539
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2540: agg_filter (agg_filter) id=agg_filter_sec_2540
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2541: agg_filter (agg_filter) id=agg_filter_sec_2541
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2542: agg_filter (agg_filter) id=agg_filter_sec_2542
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2543: agg_filter (agg_filter) id=agg_filter_sec_2543
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2544: agg_filter (agg_filter) id=agg_filter_sec_2544
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2545: agg_filter (agg_filter) id=agg_filter_sec_2545
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2546: agg_filter (agg_filter) id=agg_filter_sec_2546
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2547: agg_filter (agg_filter) id=agg_filter_sec_2547
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2548: agg_filter (agg_filter) id=agg_filter_sec_2548
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2549: agg_filter (agg_filter) id=agg_filter_sec_2549
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2550: agg_filter (agg_filter) id=agg_filter_sec_2550
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2551: agg_filter (agg_filter) id=agg_filter_sec_2551
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2552: agg_filter (agg_filter) id=agg_filter_sec_2552
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2553: agg_filter (agg_filter) id=agg_filter_sec_2553
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2554: agg_filter (agg_filter) id=agg_filter_sec_2554
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2555: agg_filter (agg_filter) id=agg_filter_sec_2555
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2556: agg_filter (agg_filter) id=agg_filter_sec_2556
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2557: agg_filter (agg_filter) id=agg_filter_sec_2557
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2558: agg_filter (agg_filter) id=agg_filter_sec_2558
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2559: agg_filter (agg_filter) id=agg_filter_sec_2559
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2560: agg_filter (agg_filter) id=agg_filter_sec_2560
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2561: agg_filter (agg_filter) id=agg_filter_sec_2561
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2562: agg_filter (agg_filter) id=agg_filter_sec_2562
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2563: agg_filter (agg_filter) id=agg_filter_sec_2563
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2564: agg_filter (agg_filter) id=agg_filter_sec_2564
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2565: agg_filter (agg_filter) id=agg_filter_sec_2565
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2566: agg_filter (agg_filter) id=agg_filter_sec_2566
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2567: agg_filter (agg_filter) id=agg_filter_sec_2567
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2568: agg_filter (agg_filter) id=agg_filter_sec_2568
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2569: agg_filter (agg_filter) id=agg_filter_sec_2569
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2570: agg_filter (agg_filter) id=agg_filter_sec_2570
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2571: agg_filter (agg_filter) id=agg_filter_sec_2571
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2572: agg_filter (agg_filter) id=agg_filter_sec_2572
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2573: agg_filter (agg_filter) id=agg_filter_sec_2573
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2574: agg_filter (agg_filter) id=agg_filter_sec_2574
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2575: agg_filter (agg_filter) id=agg_filter_sec_2575
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2576: agg_filter (agg_filter) id=agg_filter_sec_2576
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2577: agg_filter (agg_filter) id=agg_filter_sec_2577
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2578: agg_filter (agg_filter) id=agg_filter_sec_2578
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2579: agg_filter (agg_filter) id=agg_filter_sec_2579
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2580: agg_filter (agg_filter) id=agg_filter_sec_2580
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2581: agg_filter (agg_filter) id=agg_filter_sec_2581
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2582: agg_filter (agg_filter) id=agg_filter_sec_2582
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2583: agg_filter (agg_filter) id=agg_filter_sec_2583
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2584: agg_filter (agg_filter) id=agg_filter_sec_2584
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2585: agg_filter (agg_filter) id=agg_filter_sec_2585
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2586: agg_filter (agg_filter) id=agg_filter_sec_2586
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2587: agg_filter (agg_filter) id=agg_filter_sec_2587
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2588: agg_filter (agg_filter) id=agg_filter_sec_2588
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2589: agg_filter (agg_filter) id=agg_filter_sec_2589
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2590: agg_filter (agg_filter) id=agg_filter_sec_2590
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2591: agg_filter (agg_filter) id=agg_filter_sec_2591
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2592: agg_filter (agg_filter) id=agg_filter_sec_2592
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2593: agg_filter (agg_filter) id=agg_filter_sec_2593
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2594: agg_filter (agg_filter) id=agg_filter_sec_2594
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2595: agg_filter (agg_filter) id=agg_filter_sec_2595
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2596: agg_filter (agg_filter) id=agg_filter_sec_2596
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2597: agg_filter (agg_filter) id=agg_filter_sec_2597
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2598: agg_filter (agg_filter) id=agg_filter_sec_2598
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2599: agg_filter (agg_filter) id=agg_filter_sec_2599
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2600: agg_filter (agg_filter) id=agg_filter_sec_2600
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2601: agg_filter (agg_filter) id=agg_filter_sec_2601
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2602: agg_filter (agg_filter) id=agg_filter_sec_2602
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2603: agg_filter (agg_filter) id=agg_filter_sec_2603
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2604: agg_filter (agg_filter) id=agg_filter_sec_2604
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2605: agg_filter (agg_filter) id=agg_filter_sec_2605
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2606: agg_filter (agg_filter) id=agg_filter_sec_2606
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2607: agg_filter (agg_filter) id=agg_filter_sec_2607
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2608: agg_filter (agg_filter) id=agg_filter_sec_2608
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2609: agg_filter (agg_filter) id=agg_filter_sec_2609
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2610: agg_filter (agg_filter) id=agg_filter_sec_2610
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2611: agg_filter (agg_filter) id=agg_filter_sec_2611
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2612: agg_filter (agg_filter) id=agg_filter_sec_2612
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2613: agg_filter (agg_filter) id=agg_filter_sec_2613
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2614: agg_filter (agg_filter) id=agg_filter_sec_2614
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2615: agg_filter (agg_filter) id=agg_filter_sec_2615
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2616: agg_filter (agg_filter) id=agg_filter_sec_2616
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2617: agg_filter (agg_filter) id=agg_filter_sec_2617
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2618: agg_filter (agg_filter) id=agg_filter_sec_2618
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2619: agg_filter (agg_filter) id=agg_filter_sec_2619
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2620: agg_filter (agg_filter) id=agg_filter_sec_2620
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2621: agg_filter (agg_filter) id=agg_filter_sec_2621
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2622: agg_filter (agg_filter) id=agg_filter_sec_2622
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2623: agg_filter (agg_filter) id=agg_filter_sec_2623
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2624: agg_filter (agg_filter) id=agg_filter_sec_2624
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2625: agg_filter (agg_filter) id=agg_filter_sec_2625
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2626: agg_filter (agg_filter) id=agg_filter_sec_2626
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2627: agg_filter (agg_filter) id=agg_filter_sec_2627
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2628: agg_filter (agg_filter) id=agg_filter_sec_2628
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2629: agg_filter (agg_filter) id=agg_filter_sec_2629
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2630: agg_filter (agg_filter) id=agg_filter_sec_2630
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2631: agg_filter (agg_filter) id=agg_filter_sec_2631
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2632: agg_filter (agg_filter) id=agg_filter_sec_2632
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2633: agg_filter (agg_filter) id=agg_filter_sec_2633
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2634: agg_filter (agg_filter) id=agg_filter_sec_2634
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2635: agg_filter (agg_filter) id=agg_filter_sec_2635
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2636: agg_filter (agg_filter) id=agg_filter_sec_2636
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2637: agg_filter (agg_filter) id=agg_filter_sec_2637
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2638: agg_filter (agg_filter) id=agg_filter_sec_2638
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2639: agg_filter (agg_filter) id=agg_filter_sec_2639
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2640: agg_filter (agg_filter) id=agg_filter_sec_2640
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2641: agg_filter (agg_filter) id=agg_filter_sec_2641
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2642: agg_filter (agg_filter) id=agg_filter_sec_2642
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2643: agg_filter (agg_filter) id=agg_filter_sec_2643
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2644: agg_filter (agg_filter) id=agg_filter_sec_2644
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2645: agg_filter (agg_filter) id=agg_filter_sec_2645
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2646: agg_filter (agg_filter) id=agg_filter_sec_2646
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2647: agg_filter (agg_filter) id=agg_filter_sec_2647
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2648: agg_filter (agg_filter) id=agg_filter_sec_2648
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2649: agg_filter (agg_filter) id=agg_filter_sec_2649
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2650: agg_filter (agg_filter) id=agg_filter_sec_2650
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2651: agg_filter (agg_filter) id=agg_filter_sec_2651
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2652: agg_filter (agg_filter) id=agg_filter_sec_2652
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2653: agg_filter (agg_filter) id=agg_filter_sec_2653
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2654: agg_filter (agg_filter) id=agg_filter_sec_2654
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2655: agg_filter (agg_filter) id=agg_filter_sec_2655
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2656: agg_filter (agg_filter) id=agg_filter_sec_2656
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2657: agg_filter (agg_filter) id=agg_filter_sec_2657
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2658: agg_filter (agg_filter) id=agg_filter_sec_2658
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2659: agg_filter (agg_filter) id=agg_filter_sec_2659
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2660: agg_filter (agg_filter) id=agg_filter_sec_2660
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2661: agg_filter (agg_filter) id=agg_filter_sec_2661
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2662: agg_filter (agg_filter) id=agg_filter_sec_2662
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2663: agg_filter (agg_filter) id=agg_filter_sec_2663
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2664: agg_filter (agg_filter) id=agg_filter_sec_2664
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2665: agg_filter (agg_filter) id=agg_filter_sec_2665
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2666: agg_filter (agg_filter) id=agg_filter_sec_2666
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2667: agg_filter (agg_filter) id=agg_filter_sec_2667
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2668: agg_filter (agg_filter) id=agg_filter_sec_2668
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2669: agg_filter (agg_filter) id=agg_filter_sec_2669
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2670: agg_filter (agg_filter) id=agg_filter_sec_2670
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2671: agg_filter (agg_filter) id=agg_filter_sec_2671
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2672: agg_filter (agg_filter) id=agg_filter_sec_2672
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2673: agg_filter (agg_filter) id=agg_filter_sec_2673
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2674: agg_filter (agg_filter) id=agg_filter_sec_2674
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2675: agg_filter (agg_filter) id=agg_filter_sec_2675
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2676: agg_filter (agg_filter) id=agg_filter_sec_2676
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2677: agg_filter (agg_filter) id=agg_filter_sec_2677
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2678: agg_filter (agg_filter) id=agg_filter_sec_2678
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2679: agg_filter (agg_filter) id=agg_filter_sec_2679
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2680: agg_filter (agg_filter) id=agg_filter_sec_2680
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2681: agg_filter (agg_filter) id=agg_filter_sec_2681
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2682: agg_filter (agg_filter) id=agg_filter_sec_2682
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2683: agg_filter (agg_filter) id=agg_filter_sec_2683
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2684: agg_filter (agg_filter) id=agg_filter_sec_2684
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2685: agg_filter (agg_filter) id=agg_filter_sec_2685
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2686: agg_filter (agg_filter) id=agg_filter_sec_2686
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2687: agg_filter (agg_filter) id=agg_filter_sec_2687
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2688: agg_filter (agg_filter) id=agg_filter_sec_2688
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2689: agg_filter (agg_filter) id=agg_filter_sec_2689
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2690: agg_filter (agg_filter) id=agg_filter_sec_2690
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2691: agg_filter (agg_filter) id=agg_filter_sec_2691
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2692: agg_filter (agg_filter) id=agg_filter_sec_2692
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2693: agg_filter (agg_filter) id=agg_filter_sec_2693
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2694: agg_filter (agg_filter) id=agg_filter_sec_2694
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2695: agg_filter (agg_filter) id=agg_filter_sec_2695
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2696: agg_filter (agg_filter) id=agg_filter_sec_2696
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2697: agg_filter (agg_filter) id=agg_filter_sec_2697
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2698: agg_filter (agg_filter) id=agg_filter_sec_2698
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2699: agg_filter (agg_filter) id=agg_filter_sec_2699
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2700: agg_filter (agg_filter) id=agg_filter_sec_2700
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2701: agg_filter (agg_filter) id=agg_filter_sec_2701
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2702: agg_filter (agg_filter) id=agg_filter_sec_2702
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2703: agg_filter (agg_filter) id=agg_filter_sec_2703
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2704: agg_filter (agg_filter) id=agg_filter_sec_2704
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2705: agg_filter (agg_filter) id=agg_filter_sec_2705
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2706: agg_filter (agg_filter) id=agg_filter_sec_2706
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2707: agg_filter (agg_filter) id=agg_filter_sec_2707
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2708: agg_filter (agg_filter) id=agg_filter_sec_2708
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2709: agg_filter (agg_filter) id=agg_filter_sec_2709
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2710: agg_filter (agg_filter) id=agg_filter_sec_2710
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2711: agg_filter (agg_filter) id=agg_filter_sec_2711
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2712: agg_filter (agg_filter) id=agg_filter_sec_2712
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2713: agg_filter (agg_filter) id=agg_filter_sec_2713
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2714: agg_filter (agg_filter) id=agg_filter_sec_2714
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2715: agg_filter (agg_filter) id=agg_filter_sec_2715
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2716: agg_filter (agg_filter) id=agg_filter_sec_2716
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2717: agg_filter (agg_filter) id=agg_filter_sec_2717
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2718: agg_filter (agg_filter) id=agg_filter_sec_2718
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2719: agg_filter (agg_filter) id=agg_filter_sec_2719
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2720: agg_filter (agg_filter) id=agg_filter_sec_2720
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2721: agg_filter (agg_filter) id=agg_filter_sec_2721
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2722: agg_filter (agg_filter) id=agg_filter_sec_2722
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2723: agg_filter (agg_filter) id=agg_filter_sec_2723
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2724: agg_filter (agg_filter) id=agg_filter_sec_2724
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2725: agg_filter (agg_filter) id=agg_filter_sec_2725
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2726: agg_filter (agg_filter) id=agg_filter_sec_2726
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2727: agg_filter (agg_filter) id=agg_filter_sec_2727
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2728: agg_filter (agg_filter) id=agg_filter_sec_2728
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2729: agg_filter (agg_filter) id=agg_filter_sec_2729
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2730: agg_filter (agg_filter) id=agg_filter_sec_2730
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2731: agg_filter (agg_filter) id=agg_filter_sec_2731
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2732: agg_filter (agg_filter) id=agg_filter_sec_2732
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2733: agg_filter (agg_filter) id=agg_filter_sec_2733
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2734: agg_filter (agg_filter) id=agg_filter_sec_2734
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2735: agg_filter (agg_filter) id=agg_filter_sec_2735
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2736: agg_filter (agg_filter) id=agg_filter_sec_2736
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2737: agg_filter (agg_filter) id=agg_filter_sec_2737
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2738: agg_filter (agg_filter) id=agg_filter_sec_2738
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2739: agg_filter (agg_filter) id=agg_filter_sec_2739
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2740: agg_filter (agg_filter) id=agg_filter_sec_2740
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2741: agg_filter (agg_filter) id=agg_filter_sec_2741
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2742: agg_filter (agg_filter) id=agg_filter_sec_2742
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2743: agg_filter (agg_filter) id=agg_filter_sec_2743
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2744: agg_filter (agg_filter) id=agg_filter_sec_2744
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2745: agg_filter (agg_filter) id=agg_filter_sec_2745
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2746: agg_filter (agg_filter) id=agg_filter_sec_2746
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2747: agg_filter (agg_filter) id=agg_filter_sec_2747
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2748: agg_filter (agg_filter) id=agg_filter_sec_2748
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2749: agg_filter (agg_filter) id=agg_filter_sec_2749
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2750: agg_filter (agg_filter) id=agg_filter_sec_2750
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2751: agg_filter (agg_filter) id=agg_filter_sec_2751
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2752: agg_filter (agg_filter) id=agg_filter_sec_2752
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2753: agg_filter (agg_filter) id=agg_filter_sec_2753
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2754: agg_filter (agg_filter) id=agg_filter_sec_2754
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2755: agg_filter (agg_filter) id=agg_filter_sec_2755
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2756: agg_filter (agg_filter) id=agg_filter_sec_2756
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2757: agg_filter (agg_filter) id=agg_filter_sec_2757
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2758: agg_filter (agg_filter) id=agg_filter_sec_2758
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2759: agg_filter (agg_filter) id=agg_filter_sec_2759
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2760: agg_filter (agg_filter) id=agg_filter_sec_2760
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2761: agg_filter (agg_filter) id=agg_filter_sec_2761
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2762: agg_filter (agg_filter) id=agg_filter_sec_2762
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2763: agg_filter (agg_filter) id=agg_filter_sec_2763
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2764: agg_filter (agg_filter) id=agg_filter_sec_2764
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2765: agg_filter (agg_filter) id=agg_filter_sec_2765
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2766: agg_filter (agg_filter) id=agg_filter_sec_2766
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2767: agg_filter (agg_filter) id=agg_filter_sec_2767
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2768: agg_filter (agg_filter) id=agg_filter_sec_2768
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2769: agg_filter (agg_filter) id=agg_filter_sec_2769
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2770: agg_filter (agg_filter) id=agg_filter_sec_2770
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2771: agg_filter (agg_filter) id=agg_filter_sec_2771
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2772: agg_filter (agg_filter) id=agg_filter_sec_2772
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2773: agg_filter (agg_filter) id=agg_filter_sec_2773
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2774: agg_filter (agg_filter) id=agg_filter_sec_2774
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2775: agg_filter (agg_filter) id=agg_filter_sec_2775
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2776: agg_filter (agg_filter) id=agg_filter_sec_2776
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2777: agg_filter (agg_filter) id=agg_filter_sec_2777
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2778: agg_filter (agg_filter) id=agg_filter_sec_2778
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2779: agg_filter (agg_filter) id=agg_filter_sec_2779
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2780: agg_filter (agg_filter) id=agg_filter_sec_2780
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2781: agg_filter (agg_filter) id=agg_filter_sec_2781
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2782: agg_filter (agg_filter) id=agg_filter_sec_2782
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2783: agg_filter (agg_filter) id=agg_filter_sec_2783
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2784: agg_filter (agg_filter) id=agg_filter_sec_2784
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2785: agg_filter (agg_filter) id=agg_filter_sec_2785
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2786: agg_filter (agg_filter) id=agg_filter_sec_2786
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2787: agg_filter (agg_filter) id=agg_filter_sec_2787
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2788: agg_filter (agg_filter) id=agg_filter_sec_2788
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2789: agg_filter (agg_filter) id=agg_filter_sec_2789
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2790: agg_filter (agg_filter) id=agg_filter_sec_2790
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2791: agg_filter (agg_filter) id=agg_filter_sec_2791
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2792: agg_filter (agg_filter) id=agg_filter_sec_2792
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2793: agg_filter (agg_filter) id=agg_filter_sec_2793
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2794: agg_filter (agg_filter) id=agg_filter_sec_2794
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2795: agg_filter (agg_filter) id=agg_filter_sec_2795
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2796: agg_filter (agg_filter) id=agg_filter_sec_2796
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2797: agg_filter (agg_filter) id=agg_filter_sec_2797
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2798: agg_filter (agg_filter) id=agg_filter_sec_2798
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2799: agg_filter (agg_filter) id=agg_filter_sec_2799
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2800: agg_filter (agg_filter) id=agg_filter_sec_2800
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2801: agg_filter (agg_filter) id=agg_filter_sec_2801
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2802: agg_filter (agg_filter) id=agg_filter_sec_2802
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2803: agg_filter (agg_filter) id=agg_filter_sec_2803
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2804: agg_filter (agg_filter) id=agg_filter_sec_2804
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2805: agg_filter (agg_filter) id=agg_filter_sec_2805
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2806: agg_filter (agg_filter) id=agg_filter_sec_2806
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2807: agg_filter (agg_filter) id=agg_filter_sec_2807
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2808: agg_filter (agg_filter) id=agg_filter_sec_2808
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2809: agg_filter (agg_filter) id=agg_filter_sec_2809
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2810: agg_filter (agg_filter) id=agg_filter_sec_2810
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2811: agg_filter (agg_filter) id=agg_filter_sec_2811
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2812: agg_filter (agg_filter) id=agg_filter_sec_2812
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2813: agg_filter (agg_filter) id=agg_filter_sec_2813
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2814: agg_filter (agg_filter) id=agg_filter_sec_2814
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2815: agg_filter (agg_filter) id=agg_filter_sec_2815
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2816: agg_filter (agg_filter) id=agg_filter_sec_2816
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2817: agg_filter (agg_filter) id=agg_filter_sec_2817
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2818: agg_filter (agg_filter) id=agg_filter_sec_2818
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2819: agg_filter (agg_filter) id=agg_filter_sec_2819
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2820: agg_filter (agg_filter) id=agg_filter_sec_2820
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2821: agg_filter (agg_filter) id=agg_filter_sec_2821
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2822: agg_filter (agg_filter) id=agg_filter_sec_2822
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2823: agg_filter (agg_filter) id=agg_filter_sec_2823
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2824: agg_filter (agg_filter) id=agg_filter_sec_2824
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2825: agg_filter (agg_filter) id=agg_filter_sec_2825
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2826: agg_filter (agg_filter) id=agg_filter_sec_2826
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2827: agg_filter (agg_filter) id=agg_filter_sec_2827
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2828: agg_filter (agg_filter) id=agg_filter_sec_2828
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2829: agg_filter (agg_filter) id=agg_filter_sec_2829
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2830: agg_filter (agg_filter) id=agg_filter_sec_2830
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2831: agg_filter (agg_filter) id=agg_filter_sec_2831
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2832: agg_filter (agg_filter) id=agg_filter_sec_2832
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2833: agg_filter (agg_filter) id=agg_filter_sec_2833
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2834: agg_filter (agg_filter) id=agg_filter_sec_2834
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2835: agg_filter (agg_filter) id=agg_filter_sec_2835
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2836: agg_filter (agg_filter) id=agg_filter_sec_2836
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2837: agg_filter (agg_filter) id=agg_filter_sec_2837
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2838: agg_filter (agg_filter) id=agg_filter_sec_2838
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2839: agg_filter (agg_filter) id=agg_filter_sec_2839
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2840: agg_filter (agg_filter) id=agg_filter_sec_2840
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2841: agg_filter (agg_filter) id=agg_filter_sec_2841
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2842: agg_filter (agg_filter) id=agg_filter_sec_2842
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2843: agg_filter (agg_filter) id=agg_filter_sec_2843
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2844: agg_filter (agg_filter) id=agg_filter_sec_2844
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2845: agg_filter (agg_filter) id=agg_filter_sec_2845
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2846: agg_filter (agg_filter) id=agg_filter_sec_2846
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2847: agg_filter (agg_filter) id=agg_filter_sec_2847
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2848: agg_filter (agg_filter) id=agg_filter_sec_2848
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2849: agg_filter (agg_filter) id=agg_filter_sec_2849
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2850: agg_filter (agg_filter) id=agg_filter_sec_2850
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2851: agg_filter (agg_filter) id=agg_filter_sec_2851
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2852: agg_filter (agg_filter) id=agg_filter_sec_2852
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2853: agg_filter (agg_filter) id=agg_filter_sec_2853
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2854: agg_filter (agg_filter) id=agg_filter_sec_2854
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2855: agg_filter (agg_filter) id=agg_filter_sec_2855
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2856: agg_filter (agg_filter) id=agg_filter_sec_2856
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2857: agg_filter (agg_filter) id=agg_filter_sec_2857
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2858: agg_filter (agg_filter) id=agg_filter_sec_2858
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2859: agg_filter (agg_filter) id=agg_filter_sec_2859
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2860: agg_filter (agg_filter) id=agg_filter_sec_2860
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2861: agg_filter (agg_filter) id=agg_filter_sec_2861
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2862: agg_filter (agg_filter) id=agg_filter_sec_2862
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2863: agg_filter (agg_filter) id=agg_filter_sec_2863
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2864: agg_filter (agg_filter) id=agg_filter_sec_2864
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2865: agg_filter (agg_filter) id=agg_filter_sec_2865
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2866: agg_filter (agg_filter) id=agg_filter_sec_2866
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2867: agg_filter (agg_filter) id=agg_filter_sec_2867
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2868: agg_filter (agg_filter) id=agg_filter_sec_2868
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2869: agg_filter (agg_filter) id=agg_filter_sec_2869
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2870: agg_filter (agg_filter) id=agg_filter_sec_2870
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2871: agg_filter (agg_filter) id=agg_filter_sec_2871
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2872: agg_filter (agg_filter) id=agg_filter_sec_2872
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2873: agg_filter (agg_filter) id=agg_filter_sec_2873
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2874: agg_filter (agg_filter) id=agg_filter_sec_2874
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2875: agg_filter (agg_filter) id=agg_filter_sec_2875
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2876: agg_filter (agg_filter) id=agg_filter_sec_2876
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2877: agg_filter (agg_filter) id=agg_filter_sec_2877
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2878: agg_filter (agg_filter) id=agg_filter_sec_2878
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2879: agg_filter (agg_filter) id=agg_filter_sec_2879
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2880: agg_filter (agg_filter) id=agg_filter_sec_2880
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2881: agg_filter (agg_filter) id=agg_filter_sec_2881
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2882: agg_filter (agg_filter) id=agg_filter_sec_2882
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2883: agg_filter (agg_filter) id=agg_filter_sec_2883
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2884: agg_filter (agg_filter) id=agg_filter_sec_2884
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2885: agg_filter (agg_filter) id=agg_filter_sec_2885
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2886: agg_filter (agg_filter) id=agg_filter_sec_2886
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2887: agg_filter (agg_filter) id=agg_filter_sec_2887
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2888: agg_filter (agg_filter) id=agg_filter_sec_2888
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2889: agg_filter (agg_filter) id=agg_filter_sec_2889
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2890: agg_filter (agg_filter) id=agg_filter_sec_2890
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2891: agg_filter (agg_filter) id=agg_filter_sec_2891
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2892: agg_filter (agg_filter) id=agg_filter_sec_2892
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2893: agg_filter (agg_filter) id=agg_filter_sec_2893
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2894: agg_filter (agg_filter) id=agg_filter_sec_2894
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2895: agg_filter (agg_filter) id=agg_filter_sec_2895
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2896: agg_filter (agg_filter) id=agg_filter_sec_2896
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2897: agg_filter (agg_filter) id=agg_filter_sec_2897
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2898: agg_filter (agg_filter) id=agg_filter_sec_2898
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2899: agg_filter (agg_filter) id=agg_filter_sec_2899
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2900: agg_filter (agg_filter) id=agg_filter_sec_2900
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2901: agg_filter (agg_filter) id=agg_filter_sec_2901
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2902: agg_filter (agg_filter) id=agg_filter_sec_2902
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2903: agg_filter (agg_filter) id=agg_filter_sec_2903
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2904: agg_filter (agg_filter) id=agg_filter_sec_2904
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2905: agg_filter (agg_filter) id=agg_filter_sec_2905
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2906: agg_filter (agg_filter) id=agg_filter_sec_2906
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2907: agg_filter (agg_filter) id=agg_filter_sec_2907
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2908: agg_filter (agg_filter) id=agg_filter_sec_2908
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2909: agg_filter (agg_filter) id=agg_filter_sec_2909
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2910: agg_filter (agg_filter) id=agg_filter_sec_2910
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2911: agg_filter (agg_filter) id=agg_filter_sec_2911
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2912: agg_filter (agg_filter) id=agg_filter_sec_2912
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2913: agg_filter (agg_filter) id=agg_filter_sec_2913
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2914: agg_filter (agg_filter) id=agg_filter_sec_2914
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2915: agg_filter (agg_filter) id=agg_filter_sec_2915
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2916: agg_filter (agg_filter) id=agg_filter_sec_2916
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2917: agg_filter (agg_filter) id=agg_filter_sec_2917
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2918: agg_filter (agg_filter) id=agg_filter_sec_2918
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2919: agg_filter (agg_filter) id=agg_filter_sec_2919
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2920: agg_filter (agg_filter) id=agg_filter_sec_2920
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2921: agg_filter (agg_filter) id=agg_filter_sec_2921
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;

-- Query 2922: agg_filter (agg_filter) id=agg_filter_sec_2922
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE form_type = '10-K' GROUP BY fiscal_period;

-- Query 2923: agg_filter (agg_filter) id=agg_filter_sec_2923
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE form_type = '10-Q' GROUP BY fiscal_period;

-- Query 2924: agg_filter (agg_filter) id=agg_filter_sec_2924
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'FY' GROUP BY fiscal_period;

-- Query 2925: agg_filter (agg_filter) id=agg_filter_sec_2925
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q1' GROUP BY fiscal_period;

-- Query 2926: agg_filter (agg_filter) id=agg_filter_sec_2926
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q2' GROUP BY fiscal_period;

-- Query 2927: agg_filter (agg_filter) id=agg_filter_sec_2927
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE fiscal_period = 'Q3' GROUP BY fiscal_period;

-- Query 2928: agg_filter (agg_filter) id=agg_filter_sec_2928
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'Electronic Computers' GROUP BY fiscal_period;

-- Query 2929: agg_filter (agg_filter) id=agg_filter_sec_2929
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY fiscal_period;

-- Query 2930: agg_filter (agg_filter) id=agg_filter_sec_2930
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'National Commercial Banks' GROUP BY fiscal_period;

-- Query 2931: agg_filter (agg_filter) id=agg_filter_sec_2931
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'Petroleum Refining' GROUP BY fiscal_period;

-- Query 2932: agg_filter (agg_filter) id=agg_filter_sec_2932
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'Pharmaceutical Preparations' GROUP BY fiscal_period;

-- Query 2933: agg_filter (agg_filter) id=agg_filter_sec_2933
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY fiscal_period;

-- Query 2934: agg_filter (agg_filter) id=agg_filter_sec_2934
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'CA' GROUP BY fiscal_period;

-- Query 2935: agg_filter (agg_filter) id=agg_filter_sec_2935
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'DE' GROUP BY fiscal_period;

-- Query 2936: agg_filter (agg_filter) id=agg_filter_sec_2936
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'NJ' GROUP BY fiscal_period;

-- Query 2937: agg_filter (agg_filter) id=agg_filter_sec_2937
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'TX' GROUP BY fiscal_period;

-- Query 2938: agg_filter (agg_filter) id=agg_filter_sec_2938
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE state_of_incorporation = 'WA' GROUP BY fiscal_period;

-- Query 2939: agg_filter (agg_filter) id=agg_filter_sec_2939
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period;

-- Query 2940: agg_filter (agg_filter) id=agg_filter_sec_2940
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE revenue_usd > 0 GROUP BY fiscal_period;

-- Query 2941: agg_filter (agg_filter) id=agg_filter_sec_2941
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE net_income_usd > 0 GROUP BY fiscal_period;

-- Query 2942: agg_filter (agg_filter) id=agg_filter_sec_2942
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE net_income_usd < 0 GROUP BY fiscal_period;

-- Query 2943: agg_filter (agg_filter) id=agg_filter_sec_2943
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE assets_usd > liabilities_usd GROUP BY fiscal_period;

-- Query 2944: agg_filter (agg_filter) id=agg_filter_sec_2944
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics WHERE shares_outstanding IS NOT NULL GROUP BY fiscal_period;
