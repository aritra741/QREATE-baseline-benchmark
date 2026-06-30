-- Query 1: agg_only (agg_only) id=agg_only_sec_1
SELECT company_name, COUNT(*) AS count_filings FROM filing_metrics GROUP BY company_name;

-- Query 2: agg_only (agg_only) id=agg_only_sec_2
SELECT company_name, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics GROUP BY company_name;

-- Query 3: agg_only (agg_only) id=agg_only_sec_3
SELECT company_name, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics GROUP BY company_name;

-- Query 4: agg_only (agg_only) id=agg_only_sec_4
SELECT company_name, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics GROUP BY company_name;

-- Query 5: agg_only (agg_only) id=agg_only_sec_5
SELECT company_name, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics GROUP BY company_name;

-- Query 6: agg_only (agg_only) id=agg_only_sec_6
SELECT company_name, COUNT(*) AS count_all FROM filing_metrics GROUP BY company_name;

-- Query 7: agg_only (agg_only) id=agg_only_sec_7
SELECT company_name, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics GROUP BY company_name;

-- Query 8: agg_only (agg_only) id=agg_only_sec_8
SELECT company_name, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics GROUP BY company_name;

-- Query 9: agg_only (agg_only) id=agg_only_sec_9
SELECT company_name, MIN(assets_usd) AS min_assets_usd FROM filing_metrics GROUP BY company_name;

-- Query 10: agg_only (agg_only) id=agg_only_sec_10
SELECT company_name, MAX(assets_usd) AS max_assets_usd FROM filing_metrics GROUP BY company_name;

-- Query 11: agg_only (agg_only) id=agg_only_sec_11
SELECT company_name, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics GROUP BY company_name;

-- Query 12: agg_only (agg_only) id=agg_only_sec_12
SELECT company_name, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics GROUP BY company_name;

-- Query 13: agg_only (agg_only) id=agg_only_sec_13
SELECT company_name, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics GROUP BY company_name;

-- Query 14: agg_only (agg_only) id=agg_only_sec_14
SELECT company_name, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics GROUP BY company_name;

-- Query 15: agg_only (agg_only) id=agg_only_sec_15
SELECT company_name, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics GROUP BY company_name;

-- Query 16: agg_only (agg_only) id=agg_only_sec_16
SELECT company_name, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics GROUP BY company_name;

-- Query 17: agg_only (agg_only) id=agg_only_sec_17
SELECT company_name, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics GROUP BY company_name;

-- Query 18: agg_only (agg_only) id=agg_only_sec_18
SELECT company_name, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics GROUP BY company_name;

-- Query 19: agg_only (agg_only) id=agg_only_sec_19
SELECT company_name, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics GROUP BY company_name;

-- Query 20: agg_only (agg_only) id=agg_only_sec_20
SELECT company_name, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics GROUP BY company_name;

-- Query 21: agg_only (agg_only) id=agg_only_sec_21
SELECT company_name, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics GROUP BY company_name;

-- Query 22: agg_only (agg_only) id=agg_only_sec_22
SELECT company_name, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics GROUP BY company_name;

-- Query 23: agg_only (agg_only) id=agg_only_sec_23
SELECT company_name, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics GROUP BY company_name;

-- Query 24: agg_only (agg_only) id=agg_only_sec_24
SELECT company_name, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics GROUP BY company_name;

-- Query 25: agg_only (agg_only) id=agg_only_sec_25
SELECT company_name, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics GROUP BY company_name;

-- Query 26: agg_only (agg_only) id=agg_only_sec_26
SELECT company_name, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics GROUP BY company_name;

-- Query 27: agg_only (agg_only) id=agg_only_sec_27
SELECT company_name, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics GROUP BY company_name;

-- Query 28: agg_only (agg_only) id=agg_only_sec_28
SELECT company_name, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics GROUP BY company_name;

-- Query 29: agg_only (agg_only) id=agg_only_sec_29
SELECT company_name, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics GROUP BY company_name;

-- Query 30: agg_only (agg_only) id=agg_only_sec_30
SELECT company_name, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics GROUP BY company_name;

-- Query 31: agg_only (agg_only) id=agg_only_sec_31
SELECT company_name, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics GROUP BY company_name;

-- Query 32: agg_only (agg_only) id=agg_only_sec_32
SELECT company_name, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics GROUP BY company_name;

-- Query 33: agg_only (agg_only) id=agg_only_sec_33
SELECT company_name, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics GROUP BY company_name;

-- Query 34: agg_only (agg_only) id=agg_only_sec_34
SELECT company_name, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics GROUP BY company_name;

-- Query 35: agg_only (agg_only) id=agg_only_sec_35
SELECT ticker, COUNT(*) AS count_filings FROM filing_metrics GROUP BY ticker;

-- Query 36: agg_only (agg_only) id=agg_only_sec_36
SELECT ticker, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics GROUP BY ticker;

-- Query 37: agg_only (agg_only) id=agg_only_sec_37
SELECT ticker, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics GROUP BY ticker;

-- Query 38: agg_only (agg_only) id=agg_only_sec_38
SELECT ticker, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics GROUP BY ticker;

-- Query 39: agg_only (agg_only) id=agg_only_sec_39
SELECT ticker, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics GROUP BY ticker;

-- Query 40: agg_only (agg_only) id=agg_only_sec_40
SELECT ticker, COUNT(*) AS count_all FROM filing_metrics GROUP BY ticker;

-- Query 41: agg_only (agg_only) id=agg_only_sec_41
SELECT ticker, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics GROUP BY ticker;

-- Query 42: agg_only (agg_only) id=agg_only_sec_42
SELECT ticker, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics GROUP BY ticker;

-- Query 43: agg_only (agg_only) id=agg_only_sec_43
SELECT ticker, MIN(assets_usd) AS min_assets_usd FROM filing_metrics GROUP BY ticker;

-- Query 44: agg_only (agg_only) id=agg_only_sec_44
SELECT ticker, MAX(assets_usd) AS max_assets_usd FROM filing_metrics GROUP BY ticker;

-- Query 45: agg_only (agg_only) id=agg_only_sec_45
SELECT ticker, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics GROUP BY ticker;

-- Query 46: agg_only (agg_only) id=agg_only_sec_46
SELECT ticker, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics GROUP BY ticker;

-- Query 47: agg_only (agg_only) id=agg_only_sec_47
SELECT ticker, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics GROUP BY ticker;

-- Query 48: agg_only (agg_only) id=agg_only_sec_48
SELECT ticker, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics GROUP BY ticker;

-- Query 49: agg_only (agg_only) id=agg_only_sec_49
SELECT ticker, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics GROUP BY ticker;

-- Query 50: agg_only (agg_only) id=agg_only_sec_50
SELECT ticker, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics GROUP BY ticker;

-- Query 51: agg_only (agg_only) id=agg_only_sec_51
SELECT ticker, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics GROUP BY ticker;

-- Query 52: agg_only (agg_only) id=agg_only_sec_52
SELECT ticker, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics GROUP BY ticker;

-- Query 53: agg_only (agg_only) id=agg_only_sec_53
SELECT ticker, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics GROUP BY ticker;

-- Query 54: agg_only (agg_only) id=agg_only_sec_54
SELECT ticker, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics GROUP BY ticker;

-- Query 55: agg_only (agg_only) id=agg_only_sec_55
SELECT ticker, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics GROUP BY ticker;

-- Query 56: agg_only (agg_only) id=agg_only_sec_56
SELECT ticker, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics GROUP BY ticker;

-- Query 57: agg_only (agg_only) id=agg_only_sec_57
SELECT ticker, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics GROUP BY ticker;

-- Query 58: agg_only (agg_only) id=agg_only_sec_58
SELECT ticker, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics GROUP BY ticker;

-- Query 59: agg_only (agg_only) id=agg_only_sec_59
SELECT ticker, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics GROUP BY ticker;

-- Query 60: agg_only (agg_only) id=agg_only_sec_60
SELECT ticker, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics GROUP BY ticker;

-- Query 61: agg_only (agg_only) id=agg_only_sec_61
SELECT ticker, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics GROUP BY ticker;

-- Query 62: agg_only (agg_only) id=agg_only_sec_62
SELECT ticker, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics GROUP BY ticker;

-- Query 63: agg_only (agg_only) id=agg_only_sec_63
SELECT ticker, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics GROUP BY ticker;

-- Query 64: agg_only (agg_only) id=agg_only_sec_64
SELECT ticker, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics GROUP BY ticker;

-- Query 65: agg_only (agg_only) id=agg_only_sec_65
SELECT ticker, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics GROUP BY ticker;

-- Query 66: agg_only (agg_only) id=agg_only_sec_66
SELECT ticker, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics GROUP BY ticker;

-- Query 67: agg_only (agg_only) id=agg_only_sec_67
SELECT ticker, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics GROUP BY ticker;

-- Query 68: agg_only (agg_only) id=agg_only_sec_68
SELECT ticker, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics GROUP BY ticker;

-- Query 69: agg_only (agg_only) id=agg_only_sec_69
SELECT form_type, COUNT(*) AS count_filings FROM filing_metrics GROUP BY form_type;

-- Query 70: agg_only (agg_only) id=agg_only_sec_70
SELECT form_type, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics GROUP BY form_type;

-- Query 71: agg_only (agg_only) id=agg_only_sec_71
SELECT form_type, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics GROUP BY form_type;

-- Query 72: agg_only (agg_only) id=agg_only_sec_72
SELECT form_type, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics GROUP BY form_type;

-- Query 73: agg_only (agg_only) id=agg_only_sec_73
SELECT form_type, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics GROUP BY form_type;

-- Query 74: agg_only (agg_only) id=agg_only_sec_74
SELECT form_type, COUNT(*) AS count_all FROM filing_metrics GROUP BY form_type;

-- Query 75: agg_only (agg_only) id=agg_only_sec_75
SELECT form_type, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics GROUP BY form_type;

-- Query 76: agg_only (agg_only) id=agg_only_sec_76
SELECT form_type, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics GROUP BY form_type;

-- Query 77: agg_only (agg_only) id=agg_only_sec_77
SELECT form_type, MIN(assets_usd) AS min_assets_usd FROM filing_metrics GROUP BY form_type;

-- Query 78: agg_only (agg_only) id=agg_only_sec_78
SELECT form_type, MAX(assets_usd) AS max_assets_usd FROM filing_metrics GROUP BY form_type;

-- Query 79: agg_only (agg_only) id=agg_only_sec_79
SELECT form_type, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics GROUP BY form_type;

-- Query 80: agg_only (agg_only) id=agg_only_sec_80
SELECT form_type, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics GROUP BY form_type;

-- Query 81: agg_only (agg_only) id=agg_only_sec_81
SELECT form_type, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics GROUP BY form_type;

-- Query 82: agg_only (agg_only) id=agg_only_sec_82
SELECT form_type, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics GROUP BY form_type;

-- Query 83: agg_only (agg_only) id=agg_only_sec_83
SELECT form_type, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics GROUP BY form_type;

-- Query 84: agg_only (agg_only) id=agg_only_sec_84
SELECT form_type, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics GROUP BY form_type;

-- Query 85: agg_only (agg_only) id=agg_only_sec_85
SELECT form_type, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics GROUP BY form_type;

-- Query 86: agg_only (agg_only) id=agg_only_sec_86
SELECT form_type, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics GROUP BY form_type;

-- Query 87: agg_only (agg_only) id=agg_only_sec_87
SELECT form_type, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics GROUP BY form_type;

-- Query 88: agg_only (agg_only) id=agg_only_sec_88
SELECT form_type, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics GROUP BY form_type;

-- Query 89: agg_only (agg_only) id=agg_only_sec_89
SELECT form_type, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics GROUP BY form_type;

-- Query 90: agg_only (agg_only) id=agg_only_sec_90
SELECT form_type, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics GROUP BY form_type;

-- Query 91: agg_only (agg_only) id=agg_only_sec_91
SELECT form_type, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics GROUP BY form_type;

-- Query 92: agg_only (agg_only) id=agg_only_sec_92
SELECT form_type, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics GROUP BY form_type;

-- Query 93: agg_only (agg_only) id=agg_only_sec_93
SELECT form_type, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics GROUP BY form_type;

-- Query 94: agg_only (agg_only) id=agg_only_sec_94
SELECT form_type, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics GROUP BY form_type;

-- Query 95: agg_only (agg_only) id=agg_only_sec_95
SELECT form_type, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics GROUP BY form_type;

-- Query 96: agg_only (agg_only) id=agg_only_sec_96
SELECT form_type, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics GROUP BY form_type;

-- Query 97: agg_only (agg_only) id=agg_only_sec_97
SELECT form_type, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics GROUP BY form_type;

-- Query 98: agg_only (agg_only) id=agg_only_sec_98
SELECT form_type, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics GROUP BY form_type;

-- Query 99: agg_only (agg_only) id=agg_only_sec_99
SELECT form_type, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics GROUP BY form_type;

-- Query 100: agg_only (agg_only) id=agg_only_sec_100
SELECT form_type, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics GROUP BY form_type;

-- Query 101: agg_only (agg_only) id=agg_only_sec_101
SELECT form_type, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics GROUP BY form_type;

-- Query 102: agg_only (agg_only) id=agg_only_sec_102
SELECT form_type, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics GROUP BY form_type;

-- Query 103: agg_only (agg_only) id=agg_only_sec_103
SELECT fiscal_period, COUNT(*) AS count_filings FROM filing_metrics GROUP BY fiscal_period;

-- Query 104: agg_only (agg_only) id=agg_only_sec_104
SELECT fiscal_period, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 105: agg_only (agg_only) id=agg_only_sec_105
SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 106: agg_only (agg_only) id=agg_only_sec_106
SELECT fiscal_period, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 107: agg_only (agg_only) id=agg_only_sec_107
SELECT fiscal_period, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 108: agg_only (agg_only) id=agg_only_sec_108
SELECT fiscal_period, COUNT(*) AS count_all FROM filing_metrics GROUP BY fiscal_period;

-- Query 109: agg_only (agg_only) id=agg_only_sec_109
SELECT fiscal_period, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 110: agg_only (agg_only) id=agg_only_sec_110
SELECT fiscal_period, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 111: agg_only (agg_only) id=agg_only_sec_111
SELECT fiscal_period, MIN(assets_usd) AS min_assets_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 112: agg_only (agg_only) id=agg_only_sec_112
SELECT fiscal_period, MAX(assets_usd) AS max_assets_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 113: agg_only (agg_only) id=agg_only_sec_113
SELECT fiscal_period, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 114: agg_only (agg_only) id=agg_only_sec_114
SELECT fiscal_period, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 115: agg_only (agg_only) id=agg_only_sec_115
SELECT fiscal_period, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 116: agg_only (agg_only) id=agg_only_sec_116
SELECT fiscal_period, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 117: agg_only (agg_only) id=agg_only_sec_117
SELECT fiscal_period, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 118: agg_only (agg_only) id=agg_only_sec_118
SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 119: agg_only (agg_only) id=agg_only_sec_119
SELECT fiscal_period, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 120: agg_only (agg_only) id=agg_only_sec_120
SELECT fiscal_period, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 121: agg_only (agg_only) id=agg_only_sec_121
SELECT fiscal_period, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 122: agg_only (agg_only) id=agg_only_sec_122
SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 123: agg_only (agg_only) id=agg_only_sec_123
SELECT fiscal_period, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 124: agg_only (agg_only) id=agg_only_sec_124
SELECT fiscal_period, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 125: agg_only (agg_only) id=agg_only_sec_125
SELECT fiscal_period, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 126: agg_only (agg_only) id=agg_only_sec_126
SELECT fiscal_period, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 127: agg_only (agg_only) id=agg_only_sec_127
SELECT fiscal_period, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 128: agg_only (agg_only) id=agg_only_sec_128
SELECT fiscal_period, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 129: agg_only (agg_only) id=agg_only_sec_129
SELECT fiscal_period, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 130: agg_only (agg_only) id=agg_only_sec_130
SELECT fiscal_period, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 131: agg_only (agg_only) id=agg_only_sec_131
SELECT fiscal_period, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 132: agg_only (agg_only) id=agg_only_sec_132
SELECT fiscal_period, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics GROUP BY fiscal_period;

-- Query 133: agg_only (agg_only) id=agg_only_sec_133
SELECT fiscal_period, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics GROUP BY fiscal_period;

-- Query 134: agg_only (agg_only) id=agg_only_sec_134
SELECT fiscal_period, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics GROUP BY fiscal_period;

-- Query 135: agg_only (agg_only) id=agg_only_sec_135
SELECT fiscal_period, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics GROUP BY fiscal_period;

-- Query 136: agg_only (agg_only) id=agg_only_sec_136
SELECT fiscal_period, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics GROUP BY fiscal_period;

-- Query 137: agg_only (agg_only) id=agg_only_sec_137
SELECT sic_description, COUNT(*) AS count_filings FROM filing_metrics GROUP BY sic_description;

-- Query 138: agg_only (agg_only) id=agg_only_sec_138
SELECT sic_description, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics GROUP BY sic_description;

-- Query 139: agg_only (agg_only) id=agg_only_sec_139
SELECT sic_description, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics GROUP BY sic_description;

-- Query 140: agg_only (agg_only) id=agg_only_sec_140
SELECT sic_description, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics GROUP BY sic_description;

-- Query 141: agg_only (agg_only) id=agg_only_sec_141
SELECT sic_description, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics GROUP BY sic_description;

-- Query 142: agg_only (agg_only) id=agg_only_sec_142
SELECT sic_description, COUNT(*) AS count_all FROM filing_metrics GROUP BY sic_description;

-- Query 143: agg_only (agg_only) id=agg_only_sec_143
SELECT sic_description, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics GROUP BY sic_description;

-- Query 144: agg_only (agg_only) id=agg_only_sec_144
SELECT sic_description, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics GROUP BY sic_description;

-- Query 145: agg_only (agg_only) id=agg_only_sec_145
SELECT sic_description, MIN(assets_usd) AS min_assets_usd FROM filing_metrics GROUP BY sic_description;

-- Query 146: agg_only (agg_only) id=agg_only_sec_146
SELECT sic_description, MAX(assets_usd) AS max_assets_usd FROM filing_metrics GROUP BY sic_description;

-- Query 147: agg_only (agg_only) id=agg_only_sec_147
SELECT sic_description, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics GROUP BY sic_description;

-- Query 148: agg_only (agg_only) id=agg_only_sec_148
SELECT sic_description, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics GROUP BY sic_description;

-- Query 149: agg_only (agg_only) id=agg_only_sec_149
SELECT sic_description, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics GROUP BY sic_description;

-- Query 150: agg_only (agg_only) id=agg_only_sec_150
SELECT sic_description, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics GROUP BY sic_description;

-- Query 151: agg_only (agg_only) id=agg_only_sec_151
SELECT sic_description, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics GROUP BY sic_description;

-- Query 152: agg_only (agg_only) id=agg_only_sec_152
SELECT sic_description, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics GROUP BY sic_description;

-- Query 153: agg_only (agg_only) id=agg_only_sec_153
SELECT sic_description, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics GROUP BY sic_description;

-- Query 154: agg_only (agg_only) id=agg_only_sec_154
SELECT sic_description, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics GROUP BY sic_description;

-- Query 155: agg_only (agg_only) id=agg_only_sec_155
SELECT sic_description, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics GROUP BY sic_description;

-- Query 156: agg_only (agg_only) id=agg_only_sec_156
SELECT sic_description, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics GROUP BY sic_description;

-- Query 157: agg_only (agg_only) id=agg_only_sec_157
SELECT sic_description, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics GROUP BY sic_description;

-- Query 158: agg_only (agg_only) id=agg_only_sec_158
SELECT sic_description, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics GROUP BY sic_description;

-- Query 159: agg_only (agg_only) id=agg_only_sec_159
SELECT sic_description, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics GROUP BY sic_description;

-- Query 160: agg_only (agg_only) id=agg_only_sec_160
SELECT sic_description, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics GROUP BY sic_description;

-- Query 161: agg_only (agg_only) id=agg_only_sec_161
SELECT sic_description, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics GROUP BY sic_description;

-- Query 162: agg_only (agg_only) id=agg_only_sec_162
SELECT sic_description, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics GROUP BY sic_description;

-- Query 163: agg_only (agg_only) id=agg_only_sec_163
SELECT sic_description, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics GROUP BY sic_description;

-- Query 164: agg_only (agg_only) id=agg_only_sec_164
SELECT sic_description, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics GROUP BY sic_description;

-- Query 165: agg_only (agg_only) id=agg_only_sec_165
SELECT sic_description, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics GROUP BY sic_description;

-- Query 166: agg_only (agg_only) id=agg_only_sec_166
SELECT sic_description, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics GROUP BY sic_description;

-- Query 167: agg_only (agg_only) id=agg_only_sec_167
SELECT sic_description, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics GROUP BY sic_description;

-- Query 168: agg_only (agg_only) id=agg_only_sec_168
SELECT sic_description, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics GROUP BY sic_description;

-- Query 169: agg_only (agg_only) id=agg_only_sec_169
SELECT sic_description, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics GROUP BY sic_description;

-- Query 170: agg_only (agg_only) id=agg_only_sec_170
SELECT sic_description, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics GROUP BY sic_description;

-- Query 171: agg_only (agg_only) id=agg_only_sec_171
SELECT state_of_incorporation, COUNT(*) AS count_filings FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 172: agg_only (agg_only) id=agg_only_sec_172
SELECT state_of_incorporation, SUM(revenue_usd) AS sum_revenue_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 173: agg_only (agg_only) id=agg_only_sec_173
SELECT state_of_incorporation, AVG(revenue_usd) AS avg_revenue_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 174: agg_only (agg_only) id=agg_only_sec_174
SELECT state_of_incorporation, MIN(revenue_usd) AS min_revenue_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 175: agg_only (agg_only) id=agg_only_sec_175
SELECT state_of_incorporation, MAX(revenue_usd) AS max_revenue_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 176: agg_only (agg_only) id=agg_only_sec_176
SELECT state_of_incorporation, COUNT(*) AS count_all FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 177: agg_only (agg_only) id=agg_only_sec_177
SELECT state_of_incorporation, SUM(assets_usd) AS sum_assets_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 178: agg_only (agg_only) id=agg_only_sec_178
SELECT state_of_incorporation, AVG(assets_usd) AS avg_assets_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 179: agg_only (agg_only) id=agg_only_sec_179
SELECT state_of_incorporation, MIN(assets_usd) AS min_assets_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 180: agg_only (agg_only) id=agg_only_sec_180
SELECT state_of_incorporation, MAX(assets_usd) AS max_assets_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 181: agg_only (agg_only) id=agg_only_sec_181
SELECT state_of_incorporation, SUM(liabilities_usd) AS sum_liabilities_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 182: agg_only (agg_only) id=agg_only_sec_182
SELECT state_of_incorporation, AVG(liabilities_usd) AS avg_liabilities_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 183: agg_only (agg_only) id=agg_only_sec_183
SELECT state_of_incorporation, MIN(liabilities_usd) AS min_liabilities_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 184: agg_only (agg_only) id=agg_only_sec_184
SELECT state_of_incorporation, MAX(liabilities_usd) AS max_liabilities_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 185: agg_only (agg_only) id=agg_only_sec_185
SELECT state_of_incorporation, SUM(net_income_usd) AS sum_net_income_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 186: agg_only (agg_only) id=agg_only_sec_186
SELECT state_of_incorporation, AVG(net_income_usd) AS avg_net_income_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 187: agg_only (agg_only) id=agg_only_sec_187
SELECT state_of_incorporation, MIN(net_income_usd) AS min_net_income_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 188: agg_only (agg_only) id=agg_only_sec_188
SELECT state_of_incorporation, MAX(net_income_usd) AS max_net_income_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 189: agg_only (agg_only) id=agg_only_sec_189
SELECT state_of_incorporation, SUM(operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 190: agg_only (agg_only) id=agg_only_sec_190
SELECT state_of_incorporation, AVG(operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 191: agg_only (agg_only) id=agg_only_sec_191
SELECT state_of_incorporation, MIN(operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 192: agg_only (agg_only) id=agg_only_sec_192
SELECT state_of_incorporation, MAX(operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 193: agg_only (agg_only) id=agg_only_sec_193
SELECT state_of_incorporation, SUM(investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 194: agg_only (agg_only) id=agg_only_sec_194
SELECT state_of_incorporation, AVG(investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 195: agg_only (agg_only) id=agg_only_sec_195
SELECT state_of_incorporation, MIN(investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 196: agg_only (agg_only) id=agg_only_sec_196
SELECT state_of_incorporation, MAX(investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 197: agg_only (agg_only) id=agg_only_sec_197
SELECT state_of_incorporation, SUM(financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 198: agg_only (agg_only) id=agg_only_sec_198
SELECT state_of_incorporation, AVG(financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 199: agg_only (agg_only) id=agg_only_sec_199
SELECT state_of_incorporation, MIN(financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 200: agg_only (agg_only) id=agg_only_sec_200
SELECT state_of_incorporation, MAX(financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 201: agg_only (agg_only) id=agg_only_sec_201
SELECT state_of_incorporation, SUM(shares_outstanding) AS sum_shares_outstanding FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 202: agg_only (agg_only) id=agg_only_sec_202
SELECT state_of_incorporation, AVG(shares_outstanding) AS avg_shares_outstanding FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 203: agg_only (agg_only) id=agg_only_sec_203
SELECT state_of_incorporation, MIN(shares_outstanding) AS min_shares_outstanding FROM filing_metrics GROUP BY state_of_incorporation;

-- Query 204: agg_only (agg_only) id=agg_only_sec_204
SELECT state_of_incorporation, MAX(shares_outstanding) AS max_shares_outstanding FROM filing_metrics GROUP BY state_of_incorporation;
