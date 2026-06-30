-- Query 1: agg_join (agg_join) id=agg_join_sec_1
SELECT company.ticker, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 2: agg_join (agg_join) id=agg_join_sec_2
SELECT company.ticker, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 3: agg_join (agg_join) id=agg_join_sec_3
SELECT company.ticker, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 4: agg_join (agg_join) id=agg_join_sec_4
SELECT company.ticker, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 5: agg_join (agg_join) id=agg_join_sec_5
SELECT company.ticker, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 6: agg_join (agg_join) id=agg_join_sec_6
SELECT company.ticker, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 7: agg_join (agg_join) id=agg_join_sec_7
SELECT company.ticker, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 8: agg_join (agg_join) id=agg_join_sec_8
SELECT company.ticker, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 9: agg_join (agg_join) id=agg_join_sec_9
SELECT company.ticker, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 10: agg_join (agg_join) id=agg_join_sec_10
SELECT company.ticker, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 11: agg_join (agg_join) id=agg_join_sec_11
SELECT company.ticker, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 12: agg_join (agg_join) id=agg_join_sec_12
SELECT company.ticker, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 13: agg_join (agg_join) id=agg_join_sec_13
SELECT company.ticker, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 14: agg_join (agg_join) id=agg_join_sec_14
SELECT company.ticker, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 15: agg_join (agg_join) id=agg_join_sec_15
SELECT company.ticker, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 16: agg_join (agg_join) id=agg_join_sec_16
SELECT company.ticker, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 17: agg_join (agg_join) id=agg_join_sec_17
SELECT company.ticker, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 18: agg_join (agg_join) id=agg_join_sec_18
SELECT company.ticker, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 19: agg_join (agg_join) id=agg_join_sec_19
SELECT company.ticker, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 20: agg_join (agg_join) id=agg_join_sec_20
SELECT company.ticker, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 21: agg_join (agg_join) id=agg_join_sec_21
SELECT company.ticker, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 22: agg_join (agg_join) id=agg_join_sec_22
SELECT company.ticker, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 23: agg_join (agg_join) id=agg_join_sec_23
SELECT company.ticker, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 24: agg_join (agg_join) id=agg_join_sec_24
SELECT company.ticker, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 25: agg_join (agg_join) id=agg_join_sec_25
SELECT company.ticker, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 26: agg_join (agg_join) id=agg_join_sec_26
SELECT company.ticker, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 27: agg_join (agg_join) id=agg_join_sec_27
SELECT company.ticker, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 28: agg_join (agg_join) id=agg_join_sec_28
SELECT company.ticker, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 29: agg_join (agg_join) id=agg_join_sec_29
SELECT company.ticker, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 30: agg_join (agg_join) id=agg_join_sec_30
SELECT company.ticker, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 31: agg_join (agg_join) id=agg_join_sec_31
SELECT company.ticker, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 32: agg_join (agg_join) id=agg_join_sec_32
SELECT company.ticker, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.ticker;

-- Query 33: agg_join (agg_join) id=agg_join_sec_33
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 34: agg_join (agg_join) id=agg_join_sec_34
SELECT company.sic_description, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 35: agg_join (agg_join) id=agg_join_sec_35
SELECT company.sic_description, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 36: agg_join (agg_join) id=agg_join_sec_36
SELECT company.sic_description, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 37: agg_join (agg_join) id=agg_join_sec_37
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 38: agg_join (agg_join) id=agg_join_sec_38
SELECT company.sic_description, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 39: agg_join (agg_join) id=agg_join_sec_39
SELECT company.sic_description, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 40: agg_join (agg_join) id=agg_join_sec_40
SELECT company.sic_description, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 41: agg_join (agg_join) id=agg_join_sec_41
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 42: agg_join (agg_join) id=agg_join_sec_42
SELECT company.sic_description, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 43: agg_join (agg_join) id=agg_join_sec_43
SELECT company.sic_description, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 44: agg_join (agg_join) id=agg_join_sec_44
SELECT company.sic_description, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 45: agg_join (agg_join) id=agg_join_sec_45
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 46: agg_join (agg_join) id=agg_join_sec_46
SELECT company.sic_description, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 47: agg_join (agg_join) id=agg_join_sec_47
SELECT company.sic_description, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 48: agg_join (agg_join) id=agg_join_sec_48
SELECT company.sic_description, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 49: agg_join (agg_join) id=agg_join_sec_49
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 50: agg_join (agg_join) id=agg_join_sec_50
SELECT company.sic_description, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 51: agg_join (agg_join) id=agg_join_sec_51
SELECT company.sic_description, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 52: agg_join (agg_join) id=agg_join_sec_52
SELECT company.sic_description, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 53: agg_join (agg_join) id=agg_join_sec_53
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 54: agg_join (agg_join) id=agg_join_sec_54
SELECT company.sic_description, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 55: agg_join (agg_join) id=agg_join_sec_55
SELECT company.sic_description, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 56: agg_join (agg_join) id=agg_join_sec_56
SELECT company.sic_description, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 57: agg_join (agg_join) id=agg_join_sec_57
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 58: agg_join (agg_join) id=agg_join_sec_58
SELECT company.sic_description, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 59: agg_join (agg_join) id=agg_join_sec_59
SELECT company.sic_description, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 60: agg_join (agg_join) id=agg_join_sec_60
SELECT company.sic_description, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 61: agg_join (agg_join) id=agg_join_sec_61
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 62: agg_join (agg_join) id=agg_join_sec_62
SELECT company.sic_description, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 63: agg_join (agg_join) id=agg_join_sec_63
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 64: agg_join (agg_join) id=agg_join_sec_64
SELECT company.sic_description, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.sic_description;

-- Query 65: agg_join (agg_join) id=agg_join_sec_65
SELECT company.state_of_incorporation, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 66: agg_join (agg_join) id=agg_join_sec_66
SELECT company.state_of_incorporation, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 67: agg_join (agg_join) id=agg_join_sec_67
SELECT company.state_of_incorporation, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 68: agg_join (agg_join) id=agg_join_sec_68
SELECT company.state_of_incorporation, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 69: agg_join (agg_join) id=agg_join_sec_69
SELECT company.state_of_incorporation, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 70: agg_join (agg_join) id=agg_join_sec_70
SELECT company.state_of_incorporation, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 71: agg_join (agg_join) id=agg_join_sec_71
SELECT company.state_of_incorporation, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 72: agg_join (agg_join) id=agg_join_sec_72
SELECT company.state_of_incorporation, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 73: agg_join (agg_join) id=agg_join_sec_73
SELECT company.state_of_incorporation, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 74: agg_join (agg_join) id=agg_join_sec_74
SELECT company.state_of_incorporation, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 75: agg_join (agg_join) id=agg_join_sec_75
SELECT company.state_of_incorporation, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 76: agg_join (agg_join) id=agg_join_sec_76
SELECT company.state_of_incorporation, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 77: agg_join (agg_join) id=agg_join_sec_77
SELECT company.state_of_incorporation, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 78: agg_join (agg_join) id=agg_join_sec_78
SELECT company.state_of_incorporation, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 79: agg_join (agg_join) id=agg_join_sec_79
SELECT company.state_of_incorporation, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 80: agg_join (agg_join) id=agg_join_sec_80
SELECT company.state_of_incorporation, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 81: agg_join (agg_join) id=agg_join_sec_81
SELECT company.state_of_incorporation, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 82: agg_join (agg_join) id=agg_join_sec_82
SELECT company.state_of_incorporation, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 83: agg_join (agg_join) id=agg_join_sec_83
SELECT company.state_of_incorporation, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 84: agg_join (agg_join) id=agg_join_sec_84
SELECT company.state_of_incorporation, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 85: agg_join (agg_join) id=agg_join_sec_85
SELECT company.state_of_incorporation, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 86: agg_join (agg_join) id=agg_join_sec_86
SELECT company.state_of_incorporation, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 87: agg_join (agg_join) id=agg_join_sec_87
SELECT company.state_of_incorporation, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 88: agg_join (agg_join) id=agg_join_sec_88
SELECT company.state_of_incorporation, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 89: agg_join (agg_join) id=agg_join_sec_89
SELECT company.state_of_incorporation, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 90: agg_join (agg_join) id=agg_join_sec_90
SELECT company.state_of_incorporation, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 91: agg_join (agg_join) id=agg_join_sec_91
SELECT company.state_of_incorporation, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 92: agg_join (agg_join) id=agg_join_sec_92
SELECT company.state_of_incorporation, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 93: agg_join (agg_join) id=agg_join_sec_93
SELECT company.state_of_incorporation, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 94: agg_join (agg_join) id=agg_join_sec_94
SELECT company.state_of_incorporation, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 95: agg_join (agg_join) id=agg_join_sec_95
SELECT company.state_of_incorporation, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 96: agg_join (agg_join) id=agg_join_sec_96
SELECT company.state_of_incorporation, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY company.state_of_incorporation;

-- Query 97: agg_join (agg_join) id=agg_join_sec_97
SELECT filing.form_type, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 98: agg_join (agg_join) id=agg_join_sec_98
SELECT filing.form_type, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 99: agg_join (agg_join) id=agg_join_sec_99
SELECT filing.form_type, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 100: agg_join (agg_join) id=agg_join_sec_100
SELECT filing.form_type, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 101: agg_join (agg_join) id=agg_join_sec_101
SELECT filing.form_type, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 102: agg_join (agg_join) id=agg_join_sec_102
SELECT filing.form_type, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 103: agg_join (agg_join) id=agg_join_sec_103
SELECT filing.form_type, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 104: agg_join (agg_join) id=agg_join_sec_104
SELECT filing.form_type, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 105: agg_join (agg_join) id=agg_join_sec_105
SELECT filing.form_type, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 106: agg_join (agg_join) id=agg_join_sec_106
SELECT filing.form_type, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 107: agg_join (agg_join) id=agg_join_sec_107
SELECT filing.form_type, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 108: agg_join (agg_join) id=agg_join_sec_108
SELECT filing.form_type, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 109: agg_join (agg_join) id=agg_join_sec_109
SELECT filing.form_type, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 110: agg_join (agg_join) id=agg_join_sec_110
SELECT filing.form_type, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 111: agg_join (agg_join) id=agg_join_sec_111
SELECT filing.form_type, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 112: agg_join (agg_join) id=agg_join_sec_112
SELECT filing.form_type, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 113: agg_join (agg_join) id=agg_join_sec_113
SELECT filing.form_type, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 114: agg_join (agg_join) id=agg_join_sec_114
SELECT filing.form_type, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 115: agg_join (agg_join) id=agg_join_sec_115
SELECT filing.form_type, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 116: agg_join (agg_join) id=agg_join_sec_116
SELECT filing.form_type, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 117: agg_join (agg_join) id=agg_join_sec_117
SELECT filing.form_type, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 118: agg_join (agg_join) id=agg_join_sec_118
SELECT filing.form_type, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 119: agg_join (agg_join) id=agg_join_sec_119
SELECT filing.form_type, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 120: agg_join (agg_join) id=agg_join_sec_120
SELECT filing.form_type, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 121: agg_join (agg_join) id=agg_join_sec_121
SELECT filing.form_type, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 122: agg_join (agg_join) id=agg_join_sec_122
SELECT filing.form_type, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 123: agg_join (agg_join) id=agg_join_sec_123
SELECT filing.form_type, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 124: agg_join (agg_join) id=agg_join_sec_124
SELECT filing.form_type, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 125: agg_join (agg_join) id=agg_join_sec_125
SELECT filing.form_type, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 126: agg_join (agg_join) id=agg_join_sec_126
SELECT filing.form_type, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 127: agg_join (agg_join) id=agg_join_sec_127
SELECT filing.form_type, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;

-- Query 128: agg_join (agg_join) id=agg_join_sec_128
SELECT filing.form_type, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id GROUP BY filing.form_type;
