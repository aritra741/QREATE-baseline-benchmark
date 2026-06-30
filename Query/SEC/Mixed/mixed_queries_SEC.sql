-- Query 1: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 2: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_2
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 3: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_3
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 4: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_4
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 5: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_5
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 6: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_6
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 7: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_7
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 8: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_8
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 9: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_9
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 10: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_10
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 11: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_11
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 12: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_12
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 13: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_13
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 14: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_14
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 15: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_15
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 16: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_16
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 17: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_17
SELECT company.sic_description, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 18: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_18
SELECT company.sic_description, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 19: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_19
SELECT company.sic_description, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 20: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_20
SELECT company.sic_description, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 21: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_21
SELECT company.sic_description, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 22: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_22
SELECT company.sic_description, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 23: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_23
SELECT company.sic_description, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 24: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_24
SELECT company.sic_description, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 25: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_25
SELECT company.sic_description, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 26: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_26
SELECT company.sic_description, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 27: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_27
SELECT company.sic_description, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 28: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_28
SELECT company.sic_description, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 29: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_29
SELECT company.sic_description, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 30: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_30
SELECT company.sic_description, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 31: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_31
SELECT company.sic_description, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 32: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_32
SELECT company.sic_description, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 33: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_33
SELECT company.sic_description, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 34: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_34
SELECT company.sic_description, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 35: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_35
SELECT company.sic_description, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 36: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_36
SELECT company.sic_description, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 37: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_37
SELECT company.sic_description, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 38: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_38
SELECT company.sic_description, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 39: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_39
SELECT company.sic_description, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 40: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_40
SELECT company.sic_description, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 41: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_41
SELECT company.sic_description, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 42: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_42
SELECT company.sic_description, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 43: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_43
SELECT company.sic_description, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 44: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_44
SELECT company.sic_description, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 45: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_45
SELECT company.sic_description, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 46: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_46
SELECT company.sic_description, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 47: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_47
SELECT company.sic_description, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 48: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_48
SELECT company.sic_description, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 49: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_49
SELECT company.sic_description, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 50: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_50
SELECT company.sic_description, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 51: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_51
SELECT company.sic_description, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 52: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_52
SELECT company.sic_description, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 53: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_53
SELECT company.sic_description, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 54: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_54
SELECT company.sic_description, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 55: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_55
SELECT company.sic_description, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 56: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_56
SELECT company.sic_description, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 57: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_57
SELECT company.sic_description, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 58: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_58
SELECT company.sic_description, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 59: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_59
SELECT company.sic_description, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 60: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_60
SELECT company.sic_description, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 61: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_61
SELECT company.sic_description, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 62: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_62
SELECT company.sic_description, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 63: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_63
SELECT company.sic_description, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 64: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_64
SELECT company.sic_description, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 65: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_65
SELECT company.sic_description, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 66: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_66
SELECT company.sic_description, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 67: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_67
SELECT company.sic_description, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 68: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_68
SELECT company.sic_description, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 69: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_69
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 70: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_70
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 71: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_71
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 72: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_72
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 73: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_73
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 74: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_74
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 75: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_75
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 76: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_76
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 77: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_77
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 78: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_78
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 79: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_79
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 80: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_80
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 81: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_81
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 82: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_82
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 83: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_83
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 84: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_84
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 85: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_85
SELECT company.sic_description, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 86: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_86
SELECT company.sic_description, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 87: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_87
SELECT company.sic_description, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 88: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_88
SELECT company.sic_description, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 89: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_89
SELECT company.sic_description, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 90: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_90
SELECT company.sic_description, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 91: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_91
SELECT company.sic_description, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 92: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_92
SELECT company.sic_description, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 93: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_93
SELECT company.sic_description, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 94: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_94
SELECT company.sic_description, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 95: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_95
SELECT company.sic_description, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 96: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_96
SELECT company.sic_description, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 97: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_97
SELECT company.sic_description, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 98: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_98
SELECT company.sic_description, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 99: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_99
SELECT company.sic_description, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 100: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_100
SELECT company.sic_description, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 101: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_101
SELECT company.sic_description, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 102: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_102
SELECT company.sic_description, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 103: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_103
SELECT company.sic_description, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 104: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_104
SELECT company.sic_description, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 105: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_105
SELECT company.sic_description, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 106: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_106
SELECT company.sic_description, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 107: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_107
SELECT company.sic_description, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 108: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_108
SELECT company.sic_description, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 109: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_109
SELECT company.sic_description, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 110: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_110
SELECT company.sic_description, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 111: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_111
SELECT company.sic_description, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 112: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_112
SELECT company.sic_description, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 113: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_113
SELECT company.sic_description, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 114: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_114
SELECT company.sic_description, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 115: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_115
SELECT company.sic_description, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 116: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_116
SELECT company.sic_description, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 117: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_117
SELECT company.sic_description, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 118: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_118
SELECT company.sic_description, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 119: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_119
SELECT company.sic_description, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 120: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_120
SELECT company.sic_description, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 121: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_121
SELECT company.sic_description, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 122: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_122
SELECT company.sic_description, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 123: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_123
SELECT company.sic_description, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 124: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_124
SELECT company.sic_description, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 125: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_125
SELECT company.sic_description, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 126: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_126
SELECT company.sic_description, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 127: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_127
SELECT company.sic_description, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 128: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_128
SELECT company.sic_description, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 129: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_129
SELECT company.sic_description, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 130: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_130
SELECT company.sic_description, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 131: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_131
SELECT company.sic_description, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 132: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_132
SELECT company.sic_description, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 133: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_133
SELECT company.sic_description, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 134: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_134
SELECT company.sic_description, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 135: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_135
SELECT company.sic_description, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 136: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_136
SELECT company.sic_description, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 137: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_137
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 138: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_138
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 139: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_139
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 140: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_140
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 141: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_141
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 142: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_142
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 143: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_143
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 144: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_144
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 145: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_145
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 146: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_146
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 147: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_147
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 148: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_148
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 149: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_149
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 150: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_150
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 151: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_151
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 152: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_152
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 153: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_153
SELECT company.sic_description, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 154: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_154
SELECT company.sic_description, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 155: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_155
SELECT company.sic_description, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 156: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_156
SELECT company.sic_description, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 157: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_157
SELECT company.sic_description, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 158: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_158
SELECT company.sic_description, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 159: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_159
SELECT company.sic_description, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 160: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_160
SELECT company.sic_description, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 161: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_161
SELECT company.sic_description, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 162: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_162
SELECT company.sic_description, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 163: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_163
SELECT company.sic_description, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 164: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_164
SELECT company.sic_description, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 165: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_165
SELECT company.sic_description, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 166: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_166
SELECT company.sic_description, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 167: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_167
SELECT company.sic_description, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 168: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_168
SELECT company.sic_description, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 169: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_169
SELECT company.sic_description, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 170: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_170
SELECT company.sic_description, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 171: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_171
SELECT company.sic_description, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 172: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_172
SELECT company.sic_description, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 173: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_173
SELECT company.sic_description, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 174: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_174
SELECT company.sic_description, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 175: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_175
SELECT company.sic_description, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 176: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_176
SELECT company.sic_description, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 177: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_177
SELECT company.sic_description, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 178: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_178
SELECT company.sic_description, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 179: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_179
SELECT company.sic_description, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 180: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_180
SELECT company.sic_description, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 181: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_181
SELECT company.sic_description, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 182: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_182
SELECT company.sic_description, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 183: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_183
SELECT company.sic_description, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 184: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_184
SELECT company.sic_description, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 185: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_185
SELECT company.sic_description, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 186: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_186
SELECT company.sic_description, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 187: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_187
SELECT company.sic_description, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 188: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_188
SELECT company.sic_description, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 189: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_189
SELECT company.sic_description, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 190: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_190
SELECT company.sic_description, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 191: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_191
SELECT company.sic_description, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 192: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_192
SELECT company.sic_description, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 193: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_193
SELECT company.sic_description, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 194: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_194
SELECT company.sic_description, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 195: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_195
SELECT company.sic_description, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 196: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_196
SELECT company.sic_description, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 197: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_197
SELECT company.sic_description, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 198: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_198
SELECT company.sic_description, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 199: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_199
SELECT company.sic_description, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 200: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_200
SELECT company.sic_description, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 201: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_201
SELECT company.sic_description, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 202: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_202
SELECT company.sic_description, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 203: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_203
SELECT company.sic_description, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 204: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_204
SELECT company.sic_description, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 205: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_205
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 206: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_206
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 207: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_207
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 208: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_208
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 209: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_209
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 210: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_210
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 211: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_211
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 212: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_212
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 213: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_213
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 214: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_214
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 215: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_215
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 216: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_216
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 217: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_217
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 218: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_218
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 219: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_219
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 220: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_220
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 221: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_221
SELECT company.sic_description, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 222: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_222
SELECT company.sic_description, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 223: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_223
SELECT company.sic_description, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 224: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_224
SELECT company.sic_description, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 225: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_225
SELECT company.sic_description, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 226: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_226
SELECT company.sic_description, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 227: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_227
SELECT company.sic_description, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 228: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_228
SELECT company.sic_description, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 229: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_229
SELECT company.sic_description, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 230: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_230
SELECT company.sic_description, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 231: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_231
SELECT company.sic_description, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 232: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_232
SELECT company.sic_description, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 233: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_233
SELECT company.sic_description, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 234: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_234
SELECT company.sic_description, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 235: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_235
SELECT company.sic_description, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 236: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_236
SELECT company.sic_description, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 237: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_237
SELECT company.sic_description, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 238: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_238
SELECT company.sic_description, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 239: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_239
SELECT company.sic_description, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 240: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_240
SELECT company.sic_description, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 241: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_241
SELECT company.sic_description, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 242: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_242
SELECT company.sic_description, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 243: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_243
SELECT company.sic_description, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 244: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_244
SELECT company.sic_description, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 245: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_245
SELECT company.sic_description, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 246: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_246
SELECT company.sic_description, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 247: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_247
SELECT company.sic_description, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 248: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_248
SELECT company.sic_description, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 249: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_249
SELECT company.sic_description, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 250: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_250
SELECT company.sic_description, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 251: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_251
SELECT company.sic_description, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 252: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_252
SELECT company.sic_description, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 253: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_253
SELECT company.sic_description, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 254: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_254
SELECT company.sic_description, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 255: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_255
SELECT company.sic_description, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 256: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_256
SELECT company.sic_description, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 257: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_257
SELECT company.sic_description, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 258: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_258
SELECT company.sic_description, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 259: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_259
SELECT company.sic_description, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 260: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_260
SELECT company.sic_description, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 261: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_261
SELECT company.sic_description, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 262: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_262
SELECT company.sic_description, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 263: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_263
SELECT company.sic_description, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 264: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_264
SELECT company.sic_description, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 265: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_265
SELECT company.sic_description, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 266: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_266
SELECT company.sic_description, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 267: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_267
SELECT company.sic_description, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 268: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_268
SELECT company.sic_description, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 269: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_269
SELECT company.sic_description, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 270: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_270
SELECT company.sic_description, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 271: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_271
SELECT company.sic_description, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 272: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_272
SELECT company.sic_description, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 273: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_273
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 274: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_274
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 275: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_275
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 276: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_276
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 277: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_277
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 278: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_278
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 279: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_279
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 280: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_280
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 281: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_281
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 282: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_282
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 283: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_283
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 284: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_284
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 285: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_285
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 286: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_286
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 287: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_287
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 288: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_288
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 289: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_289
SELECT company.sic_description, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 290: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_290
SELECT company.sic_description, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 291: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_291
SELECT company.sic_description, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 292: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_292
SELECT company.sic_description, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 293: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_293
SELECT company.sic_description, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 294: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_294
SELECT company.sic_description, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 295: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_295
SELECT company.sic_description, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 296: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_296
SELECT company.sic_description, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 297: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_297
SELECT company.sic_description, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 298: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_298
SELECT company.sic_description, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 299: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_299
SELECT company.sic_description, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 300: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_300
SELECT company.sic_description, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 301: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_301
SELECT company.sic_description, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 302: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_302
SELECT company.sic_description, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 303: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_303
SELECT company.sic_description, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 304: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_304
SELECT company.sic_description, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 305: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_305
SELECT company.sic_description, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 306: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_306
SELECT company.sic_description, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 307: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_307
SELECT company.sic_description, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 308: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_308
SELECT company.sic_description, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 309: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_309
SELECT company.sic_description, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 310: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_310
SELECT company.sic_description, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 311: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_311
SELECT company.sic_description, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 312: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_312
SELECT company.sic_description, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 313: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_313
SELECT company.sic_description, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 314: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_314
SELECT company.sic_description, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 315: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_315
SELECT company.sic_description, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 316: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_316
SELECT company.sic_description, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 317: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_317
SELECT company.sic_description, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 318: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_318
SELECT company.sic_description, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 319: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_319
SELECT company.sic_description, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 320: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_320
SELECT company.sic_description, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 321: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_321
SELECT company.sic_description, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 322: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_322
SELECT company.sic_description, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 323: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_323
SELECT company.sic_description, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 324: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_324
SELECT company.sic_description, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 325: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_325
SELECT company.sic_description, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 326: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_326
SELECT company.sic_description, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 327: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_327
SELECT company.sic_description, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 328: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_328
SELECT company.sic_description, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 329: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_329
SELECT company.sic_description, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 330: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_330
SELECT company.sic_description, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 331: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_331
SELECT company.sic_description, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 332: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_332
SELECT company.sic_description, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 333: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_333
SELECT company.sic_description, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 334: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_334
SELECT company.sic_description, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 335: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_335
SELECT company.sic_description, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 336: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_336
SELECT company.sic_description, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 337: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_337
SELECT company.sic_description, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 338: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_338
SELECT company.sic_description, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 339: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_339
SELECT company.sic_description, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 340: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_340
SELECT company.sic_description, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 341: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_341
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 342: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_342
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 343: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_343
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 344: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_344
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 345: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_345
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 346: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_346
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 347: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_347
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 348: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_348
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 349: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_349
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 350: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_350
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 351: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_351
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 352: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_352
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 353: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_353
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 354: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_354
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 355: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_355
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 356: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_356
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 357: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_357
SELECT company.sic_description, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 358: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_358
SELECT company.sic_description, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 359: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_359
SELECT company.sic_description, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 360: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_360
SELECT company.sic_description, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 361: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_361
SELECT company.sic_description, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 362: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_362
SELECT company.sic_description, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 363: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_363
SELECT company.sic_description, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 364: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_364
SELECT company.sic_description, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 365: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_365
SELECT company.sic_description, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 366: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_366
SELECT company.sic_description, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 367: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_367
SELECT company.sic_description, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 368: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_368
SELECT company.sic_description, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 369: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_369
SELECT company.sic_description, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 370: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_370
SELECT company.sic_description, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 371: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_371
SELECT company.sic_description, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 372: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_372
SELECT company.sic_description, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 373: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_373
SELECT company.sic_description, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 374: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_374
SELECT company.sic_description, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 375: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_375
SELECT company.sic_description, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 376: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_376
SELECT company.sic_description, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 377: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_377
SELECT company.sic_description, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 378: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_378
SELECT company.sic_description, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 379: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_379
SELECT company.sic_description, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 380: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_380
SELECT company.sic_description, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 381: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_381
SELECT company.sic_description, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 382: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_382
SELECT company.sic_description, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 383: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_383
SELECT company.sic_description, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 384: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_384
SELECT company.sic_description, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 385: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_385
SELECT company.sic_description, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 386: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_386
SELECT company.sic_description, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 387: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_387
SELECT company.sic_description, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 388: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_388
SELECT company.sic_description, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 389: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_389
SELECT company.sic_description, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 390: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_390
SELECT company.sic_description, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 391: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_391
SELECT company.sic_description, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 392: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_392
SELECT company.sic_description, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 393: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_393
SELECT company.sic_description, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 394: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_394
SELECT company.sic_description, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 395: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_395
SELECT company.sic_description, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 396: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_396
SELECT company.sic_description, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 397: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_397
SELECT company.sic_description, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 398: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_398
SELECT company.sic_description, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 399: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_399
SELECT company.sic_description, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 400: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_400
SELECT company.sic_description, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 401: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_401
SELECT company.sic_description, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 402: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_402
SELECT company.sic_description, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 403: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_403
SELECT company.sic_description, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 404: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_404
SELECT company.sic_description, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 405: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_405
SELECT company.sic_description, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 406: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_406
SELECT company.sic_description, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 407: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_407
SELECT company.sic_description, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 408: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_408
SELECT company.sic_description, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 409: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_409
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 410: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_410
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 411: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_411
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 412: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_412
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 413: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_413
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 414: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_414
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 415: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_415
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 416: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_416
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 417: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_417
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 418: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_418
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 419: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_419
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 420: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_420
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 421: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_421
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 422: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_422
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 423: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_423
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 424: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_424
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 425: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_425
SELECT company.sic_description, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 426: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_426
SELECT company.sic_description, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 427: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_427
SELECT company.sic_description, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 428: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_428
SELECT company.sic_description, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 429: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_429
SELECT company.sic_description, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 430: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_430
SELECT company.sic_description, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 431: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_431
SELECT company.sic_description, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 432: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_432
SELECT company.sic_description, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 433: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_433
SELECT company.sic_description, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 434: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_434
SELECT company.sic_description, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 435: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_435
SELECT company.sic_description, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 436: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_436
SELECT company.sic_description, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 437: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_437
SELECT company.sic_description, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 438: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_438
SELECT company.sic_description, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 439: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_439
SELECT company.sic_description, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 440: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_440
SELECT company.sic_description, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 441: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_441
SELECT company.sic_description, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 442: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_442
SELECT company.sic_description, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 443: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_443
SELECT company.sic_description, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 444: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_444
SELECT company.sic_description, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 445: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_445
SELECT company.sic_description, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 446: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_446
SELECT company.sic_description, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 447: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_447
SELECT company.sic_description, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 448: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_448
SELECT company.sic_description, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 449: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_449
SELECT company.sic_description, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 450: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_450
SELECT company.sic_description, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 451: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_451
SELECT company.sic_description, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 452: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_452
SELECT company.sic_description, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 453: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_453
SELECT company.sic_description, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 454: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_454
SELECT company.sic_description, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 455: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_455
SELECT company.sic_description, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 456: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_456
SELECT company.sic_description, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 457: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_457
SELECT company.sic_description, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 458: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_458
SELECT company.sic_description, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 459: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_459
SELECT company.sic_description, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 460: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_460
SELECT company.sic_description, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 461: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_461
SELECT company.sic_description, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 462: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_462
SELECT company.sic_description, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 463: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_463
SELECT company.sic_description, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 464: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_464
SELECT company.sic_description, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 465: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_465
SELECT company.sic_description, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 466: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_466
SELECT company.sic_description, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 467: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_467
SELECT company.sic_description, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 468: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_468
SELECT company.sic_description, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 469: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_469
SELECT company.sic_description, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 470: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_470
SELECT company.sic_description, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 471: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_471
SELECT company.sic_description, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 472: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_472
SELECT company.sic_description, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 473: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_473
SELECT company.sic_description, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 474: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_474
SELECT company.sic_description, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 475: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_475
SELECT company.sic_description, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 476: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_476
SELECT company.sic_description, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 477: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_477
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 478: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_478
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 479: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_479
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 480: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_480
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 481: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_481
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 482: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_482
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 483: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_483
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 484: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_484
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 485: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_485
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 486: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_486
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 487: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_487
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 488: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_488
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 489: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_489
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 490: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_490
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 491: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_491
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 492: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_492
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 493: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_493
SELECT company.sic_description, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 494: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_494
SELECT company.sic_description, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 495: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_495
SELECT company.sic_description, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 496: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_496
SELECT company.sic_description, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 497: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_497
SELECT company.sic_description, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 498: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_498
SELECT company.sic_description, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 499: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_499
SELECT company.sic_description, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 500: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_500
SELECT company.sic_description, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 501: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_501
SELECT company.sic_description, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 502: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_502
SELECT company.sic_description, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 503: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_503
SELECT company.sic_description, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 504: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_504
SELECT company.sic_description, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 505: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_505
SELECT company.sic_description, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 506: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_506
SELECT company.sic_description, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 507: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_507
SELECT company.sic_description, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 508: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_508
SELECT company.sic_description, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 509: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_509
SELECT company.sic_description, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 510: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_510
SELECT company.sic_description, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 511: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_511
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 512: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_512
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 513: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_513
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 514: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_514
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 515: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_515
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 516: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_516
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 517: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_517
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 518: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_518
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 519: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_519
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 520: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_520
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 521: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_521
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 522: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_522
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 523: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_523
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 524: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_524
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 525: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_525
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 526: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_526
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 527: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_527
SELECT company.sic_description, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 528: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_528
SELECT company.sic_description, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.sic_description;

-- Query 529: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_529
SELECT company.sic_description, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.sic_description;

-- Query 530: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_530
SELECT company.sic_description, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.sic_description;

-- Query 531: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_531
SELECT company.sic_description, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.sic_description;

-- Query 532: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_532
SELECT company.sic_description, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.sic_description;

-- Query 533: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_533
SELECT company.sic_description, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.sic_description;

-- Query 534: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_534
SELECT company.sic_description, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.sic_description;

-- Query 535: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_535
SELECT company.sic_description, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.sic_description;

-- Query 536: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_536
SELECT company.sic_description, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.sic_description;

-- Query 537: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_537
SELECT company.sic_description, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.sic_description;

-- Query 538: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_538
SELECT company.sic_description, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.sic_description;

-- Query 539: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_539
SELECT company.sic_description, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.sic_description;

-- Query 540: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_540
SELECT company.sic_description, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.sic_description;

-- Query 541: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_541
SELECT company.sic_description, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.sic_description;

-- Query 542: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_542
SELECT company.sic_description, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.sic_description;

-- Query 543: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_543
SELECT company.sic_description, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.sic_description;

-- Query 544: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_544
SELECT company.sic_description, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.sic_description;

-- Query 545: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_545
SELECT company.ticker, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 546: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_546
SELECT company.ticker, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 547: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_547
SELECT company.ticker, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 548: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_548
SELECT company.ticker, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 549: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_549
SELECT company.ticker, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 550: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_550
SELECT company.ticker, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 551: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_551
SELECT company.ticker, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 552: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_552
SELECT company.ticker, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 553: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_553
SELECT company.ticker, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 554: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_554
SELECT company.ticker, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 555: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_555
SELECT company.ticker, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 556: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_556
SELECT company.ticker, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 557: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_557
SELECT company.ticker, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 558: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_558
SELECT company.ticker, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 559: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_559
SELECT company.ticker, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 560: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_560
SELECT company.ticker, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 561: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_561
SELECT company.ticker, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 562: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_562
SELECT company.ticker, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 563: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_563
SELECT company.ticker, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 564: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_564
SELECT company.ticker, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 565: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_565
SELECT company.ticker, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 566: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_566
SELECT company.ticker, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 567: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_567
SELECT company.ticker, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 568: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_568
SELECT company.ticker, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 569: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_569
SELECT company.ticker, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 570: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_570
SELECT company.ticker, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 571: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_571
SELECT company.ticker, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 572: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_572
SELECT company.ticker, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 573: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_573
SELECT company.ticker, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 574: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_574
SELECT company.ticker, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 575: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_575
SELECT company.ticker, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 576: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_576
SELECT company.ticker, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 577: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_577
SELECT company.ticker, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 578: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_578
SELECT company.ticker, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 579: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_579
SELECT company.ticker, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 580: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_580
SELECT company.ticker, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 581: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_581
SELECT company.ticker, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 582: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_582
SELECT company.ticker, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 583: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_583
SELECT company.ticker, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 584: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_584
SELECT company.ticker, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 585: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_585
SELECT company.ticker, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 586: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_586
SELECT company.ticker, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 587: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_587
SELECT company.ticker, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 588: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_588
SELECT company.ticker, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 589: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_589
SELECT company.ticker, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 590: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_590
SELECT company.ticker, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 591: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_591
SELECT company.ticker, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 592: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_592
SELECT company.ticker, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 593: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_593
SELECT company.ticker, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 594: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_594
SELECT company.ticker, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 595: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_595
SELECT company.ticker, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 596: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_596
SELECT company.ticker, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 597: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_597
SELECT company.ticker, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 598: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_598
SELECT company.ticker, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 599: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_599
SELECT company.ticker, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 600: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_600
SELECT company.ticker, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 601: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_601
SELECT company.ticker, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 602: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_602
SELECT company.ticker, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 603: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_603
SELECT company.ticker, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 604: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_604
SELECT company.ticker, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 605: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_605
SELECT company.ticker, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 606: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_606
SELECT company.ticker, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 607: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_607
SELECT company.ticker, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 608: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_608
SELECT company.ticker, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 609: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_609
SELECT company.ticker, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 610: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_610
SELECT company.ticker, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 611: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_611
SELECT company.ticker, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 612: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_612
SELECT company.ticker, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 613: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_613
SELECT company.ticker, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 614: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_614
SELECT company.ticker, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 615: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_615
SELECT company.ticker, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 616: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_616
SELECT company.ticker, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 617: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_617
SELECT company.ticker, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 618: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_618
SELECT company.ticker, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 619: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_619
SELECT company.ticker, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 620: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_620
SELECT company.ticker, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 621: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_621
SELECT company.ticker, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 622: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_622
SELECT company.ticker, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 623: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_623
SELECT company.ticker, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 624: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_624
SELECT company.ticker, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 625: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_625
SELECT company.ticker, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 626: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_626
SELECT company.ticker, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 627: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_627
SELECT company.ticker, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 628: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_628
SELECT company.ticker, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 629: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_629
SELECT company.ticker, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 630: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_630
SELECT company.ticker, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 631: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_631
SELECT company.ticker, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 632: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_632
SELECT company.ticker, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 633: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_633
SELECT company.ticker, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 634: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_634
SELECT company.ticker, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 635: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_635
SELECT company.ticker, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 636: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_636
SELECT company.ticker, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 637: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_637
SELECT company.ticker, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 638: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_638
SELECT company.ticker, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 639: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_639
SELECT company.ticker, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 640: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_640
SELECT company.ticker, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 641: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_641
SELECT company.ticker, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 642: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_642
SELECT company.ticker, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 643: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_643
SELECT company.ticker, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 644: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_644
SELECT company.ticker, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 645: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_645
SELECT company.ticker, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 646: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_646
SELECT company.ticker, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 647: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_647
SELECT company.ticker, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 648: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_648
SELECT company.ticker, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 649: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_649
SELECT company.ticker, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 650: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_650
SELECT company.ticker, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 651: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_651
SELECT company.ticker, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 652: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_652
SELECT company.ticker, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 653: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_653
SELECT company.ticker, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 654: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_654
SELECT company.ticker, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 655: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_655
SELECT company.ticker, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 656: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_656
SELECT company.ticker, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 657: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_657
SELECT company.ticker, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 658: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_658
SELECT company.ticker, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 659: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_659
SELECT company.ticker, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 660: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_660
SELECT company.ticker, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 661: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_661
SELECT company.ticker, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 662: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_662
SELECT company.ticker, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 663: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_663
SELECT company.ticker, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 664: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_664
SELECT company.ticker, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 665: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_665
SELECT company.ticker, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 666: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_666
SELECT company.ticker, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 667: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_667
SELECT company.ticker, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 668: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_668
SELECT company.ticker, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 669: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_669
SELECT company.ticker, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 670: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_670
SELECT company.ticker, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 671: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_671
SELECT company.ticker, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 672: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_672
SELECT company.ticker, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 673: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_673
SELECT company.ticker, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 674: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_674
SELECT company.ticker, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 675: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_675
SELECT company.ticker, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 676: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_676
SELECT company.ticker, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 677: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_677
SELECT company.ticker, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 678: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_678
SELECT company.ticker, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 679: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_679
SELECT company.ticker, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 680: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_680
SELECT company.ticker, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 681: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_681
SELECT company.ticker, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 682: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_682
SELECT company.ticker, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 683: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_683
SELECT company.ticker, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 684: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_684
SELECT company.ticker, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 685: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_685
SELECT company.ticker, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 686: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_686
SELECT company.ticker, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 687: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_687
SELECT company.ticker, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 688: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_688
SELECT company.ticker, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 689: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_689
SELECT company.ticker, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 690: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_690
SELECT company.ticker, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 691: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_691
SELECT company.ticker, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 692: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_692
SELECT company.ticker, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 693: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_693
SELECT company.ticker, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 694: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_694
SELECT company.ticker, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 695: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_695
SELECT company.ticker, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 696: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_696
SELECT company.ticker, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 697: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_697
SELECT company.ticker, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 698: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_698
SELECT company.ticker, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 699: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_699
SELECT company.ticker, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 700: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_700
SELECT company.ticker, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 701: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_701
SELECT company.ticker, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 702: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_702
SELECT company.ticker, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 703: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_703
SELECT company.ticker, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 704: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_704
SELECT company.ticker, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 705: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_705
SELECT company.ticker, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 706: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_706
SELECT company.ticker, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 707: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_707
SELECT company.ticker, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 708: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_708
SELECT company.ticker, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 709: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_709
SELECT company.ticker, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 710: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_710
SELECT company.ticker, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 711: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_711
SELECT company.ticker, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 712: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_712
SELECT company.ticker, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 713: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_713
SELECT company.ticker, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 714: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_714
SELECT company.ticker, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 715: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_715
SELECT company.ticker, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 716: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_716
SELECT company.ticker, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 717: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_717
SELECT company.ticker, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 718: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_718
SELECT company.ticker, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 719: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_719
SELECT company.ticker, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 720: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_720
SELECT company.ticker, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 721: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_721
SELECT company.ticker, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 722: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_722
SELECT company.ticker, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 723: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_723
SELECT company.ticker, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 724: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_724
SELECT company.ticker, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 725: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_725
SELECT company.ticker, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 726: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_726
SELECT company.ticker, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 727: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_727
SELECT company.ticker, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 728: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_728
SELECT company.ticker, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 729: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_729
SELECT company.ticker, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 730: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_730
SELECT company.ticker, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 731: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_731
SELECT company.ticker, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 732: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_732
SELECT company.ticker, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 733: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_733
SELECT company.ticker, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 734: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_734
SELECT company.ticker, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 735: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_735
SELECT company.ticker, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 736: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_736
SELECT company.ticker, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 737: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_737
SELECT company.ticker, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 738: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_738
SELECT company.ticker, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 739: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_739
SELECT company.ticker, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 740: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_740
SELECT company.ticker, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 741: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_741
SELECT company.ticker, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 742: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_742
SELECT company.ticker, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 743: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_743
SELECT company.ticker, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 744: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_744
SELECT company.ticker, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 745: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_745
SELECT company.ticker, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 746: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_746
SELECT company.ticker, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 747: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_747
SELECT company.ticker, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 748: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_748
SELECT company.ticker, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 749: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_749
SELECT company.ticker, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 750: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_750
SELECT company.ticker, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 751: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_751
SELECT company.ticker, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 752: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_752
SELECT company.ticker, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 753: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_753
SELECT company.ticker, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 754: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_754
SELECT company.ticker, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 755: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_755
SELECT company.ticker, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 756: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_756
SELECT company.ticker, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 757: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_757
SELECT company.ticker, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 758: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_758
SELECT company.ticker, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 759: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_759
SELECT company.ticker, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 760: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_760
SELECT company.ticker, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 761: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_761
SELECT company.ticker, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 762: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_762
SELECT company.ticker, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 763: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_763
SELECT company.ticker, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 764: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_764
SELECT company.ticker, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 765: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_765
SELECT company.ticker, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 766: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_766
SELECT company.ticker, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 767: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_767
SELECT company.ticker, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 768: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_768
SELECT company.ticker, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 769: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_769
SELECT company.ticker, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 770: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_770
SELECT company.ticker, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 771: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_771
SELECT company.ticker, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 772: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_772
SELECT company.ticker, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 773: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_773
SELECT company.ticker, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 774: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_774
SELECT company.ticker, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 775: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_775
SELECT company.ticker, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 776: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_776
SELECT company.ticker, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 777: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_777
SELECT company.ticker, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 778: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_778
SELECT company.ticker, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 779: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_779
SELECT company.ticker, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 780: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_780
SELECT company.ticker, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 781: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_781
SELECT company.ticker, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 782: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_782
SELECT company.ticker, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 783: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_783
SELECT company.ticker, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 784: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_784
SELECT company.ticker, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 785: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_785
SELECT company.ticker, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 786: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_786
SELECT company.ticker, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 787: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_787
SELECT company.ticker, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 788: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_788
SELECT company.ticker, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 789: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_789
SELECT company.ticker, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 790: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_790
SELECT company.ticker, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 791: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_791
SELECT company.ticker, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 792: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_792
SELECT company.ticker, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 793: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_793
SELECT company.ticker, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 794: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_794
SELECT company.ticker, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 795: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_795
SELECT company.ticker, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 796: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_796
SELECT company.ticker, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 797: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_797
SELECT company.ticker, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 798: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_798
SELECT company.ticker, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 799: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_799
SELECT company.ticker, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 800: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_800
SELECT company.ticker, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 801: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_801
SELECT company.ticker, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 802: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_802
SELECT company.ticker, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 803: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_803
SELECT company.ticker, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 804: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_804
SELECT company.ticker, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 805: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_805
SELECT company.ticker, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 806: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_806
SELECT company.ticker, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 807: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_807
SELECT company.ticker, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 808: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_808
SELECT company.ticker, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 809: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_809
SELECT company.ticker, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 810: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_810
SELECT company.ticker, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 811: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_811
SELECT company.ticker, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 812: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_812
SELECT company.ticker, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 813: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_813
SELECT company.ticker, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 814: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_814
SELECT company.ticker, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 815: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_815
SELECT company.ticker, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 816: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_816
SELECT company.ticker, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 817: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_817
SELECT company.ticker, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 818: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_818
SELECT company.ticker, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 819: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_819
SELECT company.ticker, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 820: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_820
SELECT company.ticker, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 821: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_821
SELECT company.ticker, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 822: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_822
SELECT company.ticker, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 823: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_823
SELECT company.ticker, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 824: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_824
SELECT company.ticker, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 825: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_825
SELECT company.ticker, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 826: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_826
SELECT company.ticker, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 827: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_827
SELECT company.ticker, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 828: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_828
SELECT company.ticker, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 829: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_829
SELECT company.ticker, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 830: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_830
SELECT company.ticker, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 831: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_831
SELECT company.ticker, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 832: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_832
SELECT company.ticker, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 833: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_833
SELECT company.ticker, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 834: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_834
SELECT company.ticker, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 835: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_835
SELECT company.ticker, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 836: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_836
SELECT company.ticker, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 837: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_837
SELECT company.ticker, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 838: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_838
SELECT company.ticker, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 839: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_839
SELECT company.ticker, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 840: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_840
SELECT company.ticker, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 841: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_841
SELECT company.ticker, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 842: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_842
SELECT company.ticker, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 843: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_843
SELECT company.ticker, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 844: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_844
SELECT company.ticker, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 845: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_845
SELECT company.ticker, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 846: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_846
SELECT company.ticker, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 847: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_847
SELECT company.ticker, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 848: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_848
SELECT company.ticker, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 849: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_849
SELECT company.ticker, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 850: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_850
SELECT company.ticker, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 851: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_851
SELECT company.ticker, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 852: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_852
SELECT company.ticker, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 853: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_853
SELECT company.ticker, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 854: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_854
SELECT company.ticker, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 855: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_855
SELECT company.ticker, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 856: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_856
SELECT company.ticker, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 857: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_857
SELECT company.ticker, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 858: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_858
SELECT company.ticker, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 859: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_859
SELECT company.ticker, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 860: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_860
SELECT company.ticker, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 861: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_861
SELECT company.ticker, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 862: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_862
SELECT company.ticker, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 863: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_863
SELECT company.ticker, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 864: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_864
SELECT company.ticker, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 865: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_865
SELECT company.ticker, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 866: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_866
SELECT company.ticker, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 867: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_867
SELECT company.ticker, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 868: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_868
SELECT company.ticker, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 869: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_869
SELECT company.ticker, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 870: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_870
SELECT company.ticker, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 871: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_871
SELECT company.ticker, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 872: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_872
SELECT company.ticker, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 873: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_873
SELECT company.ticker, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 874: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_874
SELECT company.ticker, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 875: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_875
SELECT company.ticker, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 876: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_876
SELECT company.ticker, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 877: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_877
SELECT company.ticker, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 878: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_878
SELECT company.ticker, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 879: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_879
SELECT company.ticker, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 880: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_880
SELECT company.ticker, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 881: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_881
SELECT company.ticker, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 882: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_882
SELECT company.ticker, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 883: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_883
SELECT company.ticker, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 884: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_884
SELECT company.ticker, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 885: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_885
SELECT company.ticker, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 886: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_886
SELECT company.ticker, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 887: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_887
SELECT company.ticker, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 888: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_888
SELECT company.ticker, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 889: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_889
SELECT company.ticker, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 890: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_890
SELECT company.ticker, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 891: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_891
SELECT company.ticker, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 892: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_892
SELECT company.ticker, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 893: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_893
SELECT company.ticker, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 894: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_894
SELECT company.ticker, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 895: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_895
SELECT company.ticker, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 896: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_896
SELECT company.ticker, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 897: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_897
SELECT company.ticker, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 898: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_898
SELECT company.ticker, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 899: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_899
SELECT company.ticker, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 900: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_900
SELECT company.ticker, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 901: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_901
SELECT company.ticker, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 902: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_902
SELECT company.ticker, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 903: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_903
SELECT company.ticker, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 904: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_904
SELECT company.ticker, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 905: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_905
SELECT company.ticker, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 906: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_906
SELECT company.ticker, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 907: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_907
SELECT company.ticker, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 908: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_908
SELECT company.ticker, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 909: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_909
SELECT company.ticker, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 910: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_910
SELECT company.ticker, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 911: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_911
SELECT company.ticker, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 912: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_912
SELECT company.ticker, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 913: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_913
SELECT company.ticker, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 914: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_914
SELECT company.ticker, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 915: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_915
SELECT company.ticker, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 916: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_916
SELECT company.ticker, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 917: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_917
SELECT company.ticker, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 918: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_918
SELECT company.ticker, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 919: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_919
SELECT company.ticker, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 920: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_920
SELECT company.ticker, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 921: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_921
SELECT company.ticker, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 922: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_922
SELECT company.ticker, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 923: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_923
SELECT company.ticker, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 924: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_924
SELECT company.ticker, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 925: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_925
SELECT company.ticker, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 926: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_926
SELECT company.ticker, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 927: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_927
SELECT company.ticker, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 928: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_928
SELECT company.ticker, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 929: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_929
SELECT company.ticker, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 930: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_930
SELECT company.ticker, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 931: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_931
SELECT company.ticker, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 932: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_932
SELECT company.ticker, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 933: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_933
SELECT company.ticker, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 934: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_934
SELECT company.ticker, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 935: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_935
SELECT company.ticker, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 936: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_936
SELECT company.ticker, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 937: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_937
SELECT company.ticker, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 938: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_938
SELECT company.ticker, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 939: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_939
SELECT company.ticker, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 940: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_940
SELECT company.ticker, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 941: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_941
SELECT company.ticker, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 942: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_942
SELECT company.ticker, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 943: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_943
SELECT company.ticker, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 944: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_944
SELECT company.ticker, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 945: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_945
SELECT company.ticker, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 946: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_946
SELECT company.ticker, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 947: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_947
SELECT company.ticker, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 948: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_948
SELECT company.ticker, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 949: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_949
SELECT company.ticker, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 950: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_950
SELECT company.ticker, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 951: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_951
SELECT company.ticker, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 952: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_952
SELECT company.ticker, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 953: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_953
SELECT company.ticker, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 954: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_954
SELECT company.ticker, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 955: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_955
SELECT company.ticker, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 956: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_956
SELECT company.ticker, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 957: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_957
SELECT company.ticker, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 958: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_958
SELECT company.ticker, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 959: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_959
SELECT company.ticker, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 960: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_960
SELECT company.ticker, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 961: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_961
SELECT company.ticker, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 962: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_962
SELECT company.ticker, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 963: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_963
SELECT company.ticker, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 964: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_964
SELECT company.ticker, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 965: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_965
SELECT company.ticker, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 966: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_966
SELECT company.ticker, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 967: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_967
SELECT company.ticker, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 968: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_968
SELECT company.ticker, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 969: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_969
SELECT company.ticker, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 970: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_970
SELECT company.ticker, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 971: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_971
SELECT company.ticker, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 972: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_972
SELECT company.ticker, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 973: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_973
SELECT company.ticker, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 974: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_974
SELECT company.ticker, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 975: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_975
SELECT company.ticker, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 976: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_976
SELECT company.ticker, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 977: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_977
SELECT company.ticker, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 978: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_978
SELECT company.ticker, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 979: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_979
SELECT company.ticker, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 980: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_980
SELECT company.ticker, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 981: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_981
SELECT company.ticker, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 982: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_982
SELECT company.ticker, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 983: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_983
SELECT company.ticker, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 984: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_984
SELECT company.ticker, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 985: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_985
SELECT company.ticker, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 986: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_986
SELECT company.ticker, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 987: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_987
SELECT company.ticker, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 988: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_988
SELECT company.ticker, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 989: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_989
SELECT company.ticker, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 990: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_990
SELECT company.ticker, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 991: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_991
SELECT company.ticker, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 992: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_992
SELECT company.ticker, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 993: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_993
SELECT company.ticker, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 994: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_994
SELECT company.ticker, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 995: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_995
SELECT company.ticker, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 996: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_996
SELECT company.ticker, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 997: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_997
SELECT company.ticker, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 998: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_998
SELECT company.ticker, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 999: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_999
SELECT company.ticker, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 1000: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1000
SELECT company.ticker, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 1001: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1001
SELECT company.ticker, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 1002: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1002
SELECT company.ticker, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 1003: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1003
SELECT company.ticker, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 1004: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1004
SELECT company.ticker, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 1005: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1005
SELECT company.ticker, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 1006: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1006
SELECT company.ticker, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 1007: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1007
SELECT company.ticker, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 1008: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1008
SELECT company.ticker, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 1009: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1009
SELECT company.ticker, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 1010: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1010
SELECT company.ticker, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 1011: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1011
SELECT company.ticker, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 1012: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1012
SELECT company.ticker, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 1013: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1013
SELECT company.ticker, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 1014: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1014
SELECT company.ticker, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 1015: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1015
SELECT company.ticker, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 1016: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1016
SELECT company.ticker, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 1017: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1017
SELECT company.ticker, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 1018: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1018
SELECT company.ticker, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 1019: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1019
SELECT company.ticker, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 1020: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1020
SELECT company.ticker, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 1021: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1021
SELECT company.ticker, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 1022: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1022
SELECT company.ticker, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 1023: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1023
SELECT company.ticker, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 1024: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1024
SELECT company.ticker, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 1025: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1025
SELECT company.ticker, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 1026: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1026
SELECT company.ticker, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 1027: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1027
SELECT company.ticker, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 1028: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1028
SELECT company.ticker, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 1029: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1029
SELECT company.ticker, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 1030: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1030
SELECT company.ticker, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 1031: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1031
SELECT company.ticker, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 1032: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1032
SELECT company.ticker, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 1033: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1033
SELECT company.ticker, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 1034: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1034
SELECT company.ticker, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 1035: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1035
SELECT company.ticker, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 1036: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1036
SELECT company.ticker, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 1037: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1037
SELECT company.ticker, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 1038: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1038
SELECT company.ticker, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 1039: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1039
SELECT company.ticker, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 1040: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1040
SELECT company.ticker, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 1041: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1041
SELECT company.ticker, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 1042: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1042
SELECT company.ticker, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 1043: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1043
SELECT company.ticker, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 1044: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1044
SELECT company.ticker, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 1045: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1045
SELECT company.ticker, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 1046: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1046
SELECT company.ticker, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 1047: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1047
SELECT company.ticker, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 1048: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1048
SELECT company.ticker, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 1049: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1049
SELECT company.ticker, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 1050: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1050
SELECT company.ticker, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 1051: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1051
SELECT company.ticker, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 1052: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1052
SELECT company.ticker, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 1053: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1053
SELECT company.ticker, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 1054: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1054
SELECT company.ticker, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 1055: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1055
SELECT company.ticker, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 1056: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1056
SELECT company.ticker, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 1057: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1057
SELECT company.ticker, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 1058: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1058
SELECT company.ticker, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 1059: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1059
SELECT company.ticker, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 1060: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1060
SELECT company.ticker, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 1061: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1061
SELECT company.ticker, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 1062: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1062
SELECT company.ticker, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 1063: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1063
SELECT company.ticker, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 1064: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1064
SELECT company.ticker, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 1065: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1065
SELECT company.ticker, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 1066: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1066
SELECT company.ticker, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 1067: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1067
SELECT company.ticker, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 1068: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1068
SELECT company.ticker, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 1069: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1069
SELECT company.ticker, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 1070: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1070
SELECT company.ticker, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 1071: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1071
SELECT company.ticker, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 1072: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1072
SELECT company.ticker, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY company.ticker;

-- Query 1073: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1073
SELECT company.ticker, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY company.ticker;

-- Query 1074: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1074
SELECT company.ticker, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY company.ticker;

-- Query 1075: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1075
SELECT company.ticker, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY company.ticker;

-- Query 1076: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1076
SELECT company.ticker, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY company.ticker;

-- Query 1077: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1077
SELECT company.ticker, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY company.ticker;

-- Query 1078: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1078
SELECT company.ticker, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY company.ticker;

-- Query 1079: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1079
SELECT company.ticker, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY company.ticker;

-- Query 1080: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1080
SELECT company.ticker, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY company.ticker;

-- Query 1081: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1081
SELECT company.ticker, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY company.ticker;

-- Query 1082: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1082
SELECT company.ticker, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY company.ticker;

-- Query 1083: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1083
SELECT company.ticker, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY company.ticker;

-- Query 1084: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1084
SELECT company.ticker, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY company.ticker;

-- Query 1085: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1085
SELECT company.ticker, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY company.ticker;

-- Query 1086: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1086
SELECT company.ticker, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY company.ticker;

-- Query 1087: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1087
SELECT company.ticker, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY company.ticker;

-- Query 1088: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1088
SELECT company.ticker, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY company.ticker;

-- Query 1089: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1089
SELECT filing.form_type, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1090: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1090
SELECT filing.form_type, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1091: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1091
SELECT filing.form_type, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1092: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1092
SELECT filing.form_type, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1093: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1093
SELECT filing.form_type, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1094: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1094
SELECT filing.form_type, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1095: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1095
SELECT filing.form_type, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1096: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1096
SELECT filing.form_type, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1097: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1097
SELECT filing.form_type, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1098: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1098
SELECT filing.form_type, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1099: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1099
SELECT filing.form_type, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1100: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1100
SELECT filing.form_type, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1101: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1101
SELECT filing.form_type, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1102: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1102
SELECT filing.form_type, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1103: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1103
SELECT filing.form_type, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1104: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1104
SELECT filing.form_type, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1105: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1105
SELECT filing.form_type, SUM(filing_metrics.revenue_usd) AS sum_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1106: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1106
SELECT filing.form_type, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1107: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1107
SELECT filing.form_type, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1108: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1108
SELECT filing.form_type, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1109: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1109
SELECT filing.form_type, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1110: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1110
SELECT filing.form_type, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1111: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1111
SELECT filing.form_type, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1112: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1112
SELECT filing.form_type, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1113: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1113
SELECT filing.form_type, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1114: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1114
SELECT filing.form_type, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1115: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1115
SELECT filing.form_type, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1116: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1116
SELECT filing.form_type, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1117: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1117
SELECT filing.form_type, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1118: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1118
SELECT filing.form_type, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1119: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1119
SELECT filing.form_type, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1120: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1120
SELECT filing.form_type, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1121: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1121
SELECT filing.form_type, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1122: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1122
SELECT filing.form_type, AVG(filing_metrics.revenue_usd) AS avg_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1123: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1123
SELECT filing.form_type, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1124: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1124
SELECT filing.form_type, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1125: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1125
SELECT filing.form_type, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1126: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1126
SELECT filing.form_type, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1127: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1127
SELECT filing.form_type, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1128: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1128
SELECT filing.form_type, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1129: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1129
SELECT filing.form_type, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1130: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1130
SELECT filing.form_type, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1131: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1131
SELECT filing.form_type, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1132: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1132
SELECT filing.form_type, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1133: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1133
SELECT filing.form_type, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1134: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1134
SELECT filing.form_type, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1135: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1135
SELECT filing.form_type, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1136: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1136
SELECT filing.form_type, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1137: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1137
SELECT filing.form_type, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1138: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1138
SELECT filing.form_type, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1139: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1139
SELECT filing.form_type, MIN(filing_metrics.revenue_usd) AS min_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1140: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1140
SELECT filing.form_type, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1141: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1141
SELECT filing.form_type, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1142: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1142
SELECT filing.form_type, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1143: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1143
SELECT filing.form_type, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1144: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1144
SELECT filing.form_type, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1145: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1145
SELECT filing.form_type, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1146: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1146
SELECT filing.form_type, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1147: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1147
SELECT filing.form_type, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1148: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1148
SELECT filing.form_type, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1149: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1149
SELECT filing.form_type, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1150: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1150
SELECT filing.form_type, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1151: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1151
SELECT filing.form_type, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1152: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1152
SELECT filing.form_type, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1153: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1153
SELECT filing.form_type, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1154: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1154
SELECT filing.form_type, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1155: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1155
SELECT filing.form_type, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1156: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1156
SELECT filing.form_type, MAX(filing_metrics.revenue_usd) AS max_revenue_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1157: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1157
SELECT filing.form_type, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1158: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1158
SELECT filing.form_type, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1159: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1159
SELECT filing.form_type, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1160: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1160
SELECT filing.form_type, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1161: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1161
SELECT filing.form_type, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1162: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1162
SELECT filing.form_type, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1163: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1163
SELECT filing.form_type, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1164: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1164
SELECT filing.form_type, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1165: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1165
SELECT filing.form_type, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1166: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1166
SELECT filing.form_type, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1167: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1167
SELECT filing.form_type, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1168: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1168
SELECT filing.form_type, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1169: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1169
SELECT filing.form_type, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1170: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1170
SELECT filing.form_type, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1171: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1171
SELECT filing.form_type, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1172: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1172
SELECT filing.form_type, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1173: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1173
SELECT filing.form_type, SUM(filing_metrics.assets_usd) AS sum_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1174: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1174
SELECT filing.form_type, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1175: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1175
SELECT filing.form_type, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1176: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1176
SELECT filing.form_type, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1177: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1177
SELECT filing.form_type, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1178: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1178
SELECT filing.form_type, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1179: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1179
SELECT filing.form_type, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1180: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1180
SELECT filing.form_type, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1181: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1181
SELECT filing.form_type, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1182: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1182
SELECT filing.form_type, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1183: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1183
SELECT filing.form_type, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1184: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1184
SELECT filing.form_type, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1185: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1185
SELECT filing.form_type, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1186: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1186
SELECT filing.form_type, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1187: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1187
SELECT filing.form_type, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1188: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1188
SELECT filing.form_type, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1189: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1189
SELECT filing.form_type, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1190: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1190
SELECT filing.form_type, AVG(filing_metrics.assets_usd) AS avg_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1191: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1191
SELECT filing.form_type, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1192: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1192
SELECT filing.form_type, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1193: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1193
SELECT filing.form_type, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1194: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1194
SELECT filing.form_type, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1195: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1195
SELECT filing.form_type, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1196: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1196
SELECT filing.form_type, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1197: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1197
SELECT filing.form_type, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1198: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1198
SELECT filing.form_type, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1199: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1199
SELECT filing.form_type, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1200: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1200
SELECT filing.form_type, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1201: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1201
SELECT filing.form_type, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1202: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1202
SELECT filing.form_type, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1203: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1203
SELECT filing.form_type, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1204: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1204
SELECT filing.form_type, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1205: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1205
SELECT filing.form_type, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1206: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1206
SELECT filing.form_type, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1207: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1207
SELECT filing.form_type, MIN(filing_metrics.assets_usd) AS min_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1208: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1208
SELECT filing.form_type, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1209: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1209
SELECT filing.form_type, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1210: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1210
SELECT filing.form_type, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1211: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1211
SELECT filing.form_type, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1212: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1212
SELECT filing.form_type, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1213: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1213
SELECT filing.form_type, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1214: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1214
SELECT filing.form_type, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1215: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1215
SELECT filing.form_type, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1216: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1216
SELECT filing.form_type, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1217: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1217
SELECT filing.form_type, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1218: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1218
SELECT filing.form_type, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1219: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1219
SELECT filing.form_type, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1220: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1220
SELECT filing.form_type, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1221: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1221
SELECT filing.form_type, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1222: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1222
SELECT filing.form_type, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1223: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1223
SELECT filing.form_type, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1224: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1224
SELECT filing.form_type, MAX(filing_metrics.assets_usd) AS max_assets_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1225: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1225
SELECT filing.form_type, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1226: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1226
SELECT filing.form_type, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1227: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1227
SELECT filing.form_type, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1228: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1228
SELECT filing.form_type, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1229: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1229
SELECT filing.form_type, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1230: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1230
SELECT filing.form_type, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1231: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1231
SELECT filing.form_type, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1232: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1232
SELECT filing.form_type, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1233: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1233
SELECT filing.form_type, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1234: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1234
SELECT filing.form_type, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1235: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1235
SELECT filing.form_type, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1236: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1236
SELECT filing.form_type, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1237: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1237
SELECT filing.form_type, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1238: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1238
SELECT filing.form_type, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1239: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1239
SELECT filing.form_type, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1240: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1240
SELECT filing.form_type, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1241: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1241
SELECT filing.form_type, SUM(filing_metrics.liabilities_usd) AS sum_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1242: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1242
SELECT filing.form_type, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1243: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1243
SELECT filing.form_type, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1244: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1244
SELECT filing.form_type, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1245: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1245
SELECT filing.form_type, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1246: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1246
SELECT filing.form_type, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1247: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1247
SELECT filing.form_type, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1248: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1248
SELECT filing.form_type, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1249: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1249
SELECT filing.form_type, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1250: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1250
SELECT filing.form_type, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1251: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1251
SELECT filing.form_type, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1252: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1252
SELECT filing.form_type, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1253: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1253
SELECT filing.form_type, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1254: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1254
SELECT filing.form_type, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1255: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1255
SELECT filing.form_type, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1256: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1256
SELECT filing.form_type, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1257: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1257
SELECT filing.form_type, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1258: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1258
SELECT filing.form_type, AVG(filing_metrics.liabilities_usd) AS avg_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1259: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1259
SELECT filing.form_type, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1260: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1260
SELECT filing.form_type, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1261: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1261
SELECT filing.form_type, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1262: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1262
SELECT filing.form_type, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1263: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1263
SELECT filing.form_type, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1264: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1264
SELECT filing.form_type, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1265: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1265
SELECT filing.form_type, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1266: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1266
SELECT filing.form_type, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1267: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1267
SELECT filing.form_type, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1268: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1268
SELECT filing.form_type, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1269: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1269
SELECT filing.form_type, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1270: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1270
SELECT filing.form_type, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1271: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1271
SELECT filing.form_type, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1272: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1272
SELECT filing.form_type, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1273: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1273
SELECT filing.form_type, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1274: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1274
SELECT filing.form_type, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1275: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1275
SELECT filing.form_type, MIN(filing_metrics.liabilities_usd) AS min_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1276: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1276
SELECT filing.form_type, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1277: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1277
SELECT filing.form_type, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1278: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1278
SELECT filing.form_type, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1279: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1279
SELECT filing.form_type, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1280: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1280
SELECT filing.form_type, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1281: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1281
SELECT filing.form_type, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1282: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1282
SELECT filing.form_type, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1283: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1283
SELECT filing.form_type, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1284: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1284
SELECT filing.form_type, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1285: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1285
SELECT filing.form_type, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1286: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1286
SELECT filing.form_type, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1287: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1287
SELECT filing.form_type, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1288: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1288
SELECT filing.form_type, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1289: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1289
SELECT filing.form_type, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1290: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1290
SELECT filing.form_type, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1291: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1291
SELECT filing.form_type, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1292: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1292
SELECT filing.form_type, MAX(filing_metrics.liabilities_usd) AS max_liabilities_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1293: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1293
SELECT filing.form_type, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1294: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1294
SELECT filing.form_type, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1295: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1295
SELECT filing.form_type, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1296: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1296
SELECT filing.form_type, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1297: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1297
SELECT filing.form_type, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1298: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1298
SELECT filing.form_type, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1299: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1299
SELECT filing.form_type, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1300: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1300
SELECT filing.form_type, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1301: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1301
SELECT filing.form_type, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1302: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1302
SELECT filing.form_type, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1303: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1303
SELECT filing.form_type, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1304: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1304
SELECT filing.form_type, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1305: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1305
SELECT filing.form_type, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1306: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1306
SELECT filing.form_type, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1307: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1307
SELECT filing.form_type, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1308: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1308
SELECT filing.form_type, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1309: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1309
SELECT filing.form_type, SUM(filing_metrics.net_income_usd) AS sum_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1310: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1310
SELECT filing.form_type, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1311: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1311
SELECT filing.form_type, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1312: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1312
SELECT filing.form_type, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1313: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1313
SELECT filing.form_type, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1314: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1314
SELECT filing.form_type, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1315: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1315
SELECT filing.form_type, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1316: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1316
SELECT filing.form_type, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1317: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1317
SELECT filing.form_type, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1318: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1318
SELECT filing.form_type, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1319: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1319
SELECT filing.form_type, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1320: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1320
SELECT filing.form_type, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1321: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1321
SELECT filing.form_type, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1322: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1322
SELECT filing.form_type, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1323: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1323
SELECT filing.form_type, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1324: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1324
SELECT filing.form_type, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1325: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1325
SELECT filing.form_type, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1326: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1326
SELECT filing.form_type, AVG(filing_metrics.net_income_usd) AS avg_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1327: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1327
SELECT filing.form_type, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1328: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1328
SELECT filing.form_type, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1329: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1329
SELECT filing.form_type, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1330: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1330
SELECT filing.form_type, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1331: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1331
SELECT filing.form_type, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1332: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1332
SELECT filing.form_type, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1333: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1333
SELECT filing.form_type, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1334: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1334
SELECT filing.form_type, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1335: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1335
SELECT filing.form_type, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1336: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1336
SELECT filing.form_type, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1337: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1337
SELECT filing.form_type, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1338: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1338
SELECT filing.form_type, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1339: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1339
SELECT filing.form_type, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1340: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1340
SELECT filing.form_type, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1341: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1341
SELECT filing.form_type, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1342: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1342
SELECT filing.form_type, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1343: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1343
SELECT filing.form_type, MIN(filing_metrics.net_income_usd) AS min_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1344: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1344
SELECT filing.form_type, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1345: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1345
SELECT filing.form_type, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1346: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1346
SELECT filing.form_type, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1347: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1347
SELECT filing.form_type, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1348: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1348
SELECT filing.form_type, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1349: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1349
SELECT filing.form_type, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1350: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1350
SELECT filing.form_type, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1351: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1351
SELECT filing.form_type, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1352: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1352
SELECT filing.form_type, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1353: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1353
SELECT filing.form_type, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1354: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1354
SELECT filing.form_type, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1355: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1355
SELECT filing.form_type, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1356: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1356
SELECT filing.form_type, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1357: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1357
SELECT filing.form_type, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1358: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1358
SELECT filing.form_type, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1359: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1359
SELECT filing.form_type, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1360: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1360
SELECT filing.form_type, MAX(filing_metrics.net_income_usd) AS max_net_income_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1361: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1361
SELECT filing.form_type, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1362: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1362
SELECT filing.form_type, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1363: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1363
SELECT filing.form_type, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1364: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1364
SELECT filing.form_type, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1365: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1365
SELECT filing.form_type, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1366: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1366
SELECT filing.form_type, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1367: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1367
SELECT filing.form_type, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1368: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1368
SELECT filing.form_type, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1369: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1369
SELECT filing.form_type, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1370: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1370
SELECT filing.form_type, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1371: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1371
SELECT filing.form_type, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1372: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1372
SELECT filing.form_type, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1373: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1373
SELECT filing.form_type, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1374: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1374
SELECT filing.form_type, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1375: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1375
SELECT filing.form_type, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1376: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1376
SELECT filing.form_type, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1377: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1377
SELECT filing.form_type, SUM(filing_metrics.operating_cash_flow_usd) AS sum_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1378: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1378
SELECT filing.form_type, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1379: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1379
SELECT filing.form_type, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1380: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1380
SELECT filing.form_type, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1381: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1381
SELECT filing.form_type, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1382: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1382
SELECT filing.form_type, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1383: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1383
SELECT filing.form_type, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1384: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1384
SELECT filing.form_type, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1385: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1385
SELECT filing.form_type, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1386: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1386
SELECT filing.form_type, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1387: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1387
SELECT filing.form_type, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1388: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1388
SELECT filing.form_type, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1389: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1389
SELECT filing.form_type, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1390: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1390
SELECT filing.form_type, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1391: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1391
SELECT filing.form_type, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1392: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1392
SELECT filing.form_type, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1393: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1393
SELECT filing.form_type, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1394: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1394
SELECT filing.form_type, AVG(filing_metrics.operating_cash_flow_usd) AS avg_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1395: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1395
SELECT filing.form_type, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1396: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1396
SELECT filing.form_type, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1397: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1397
SELECT filing.form_type, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1398: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1398
SELECT filing.form_type, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1399: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1399
SELECT filing.form_type, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1400: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1400
SELECT filing.form_type, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1401: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1401
SELECT filing.form_type, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1402: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1402
SELECT filing.form_type, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1403: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1403
SELECT filing.form_type, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1404: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1404
SELECT filing.form_type, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1405: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1405
SELECT filing.form_type, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1406: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1406
SELECT filing.form_type, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1407: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1407
SELECT filing.form_type, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1408: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1408
SELECT filing.form_type, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1409: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1409
SELECT filing.form_type, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1410: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1410
SELECT filing.form_type, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1411: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1411
SELECT filing.form_type, MIN(filing_metrics.operating_cash_flow_usd) AS min_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1412: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1412
SELECT filing.form_type, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1413: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1413
SELECT filing.form_type, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1414: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1414
SELECT filing.form_type, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1415: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1415
SELECT filing.form_type, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1416: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1416
SELECT filing.form_type, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1417: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1417
SELECT filing.form_type, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1418: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1418
SELECT filing.form_type, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1419: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1419
SELECT filing.form_type, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1420: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1420
SELECT filing.form_type, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1421: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1421
SELECT filing.form_type, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1422: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1422
SELECT filing.form_type, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1423: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1423
SELECT filing.form_type, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1424: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1424
SELECT filing.form_type, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1425: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1425
SELECT filing.form_type, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1426: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1426
SELECT filing.form_type, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1427: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1427
SELECT filing.form_type, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1428: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1428
SELECT filing.form_type, MAX(filing_metrics.operating_cash_flow_usd) AS max_operating_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1429: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1429
SELECT filing.form_type, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1430: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1430
SELECT filing.form_type, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1431: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1431
SELECT filing.form_type, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1432: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1432
SELECT filing.form_type, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1433: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1433
SELECT filing.form_type, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1434: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1434
SELECT filing.form_type, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1435: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1435
SELECT filing.form_type, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1436: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1436
SELECT filing.form_type, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1437: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1437
SELECT filing.form_type, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1438: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1438
SELECT filing.form_type, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1439: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1439
SELECT filing.form_type, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1440: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1440
SELECT filing.form_type, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1441: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1441
SELECT filing.form_type, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1442: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1442
SELECT filing.form_type, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1443: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1443
SELECT filing.form_type, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1444: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1444
SELECT filing.form_type, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1445: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1445
SELECT filing.form_type, SUM(filing_metrics.investing_cash_flow_usd) AS sum_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1446: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1446
SELECT filing.form_type, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1447: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1447
SELECT filing.form_type, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1448: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1448
SELECT filing.form_type, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1449: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1449
SELECT filing.form_type, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1450: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1450
SELECT filing.form_type, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1451: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1451
SELECT filing.form_type, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1452: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1452
SELECT filing.form_type, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1453: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1453
SELECT filing.form_type, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1454: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1454
SELECT filing.form_type, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1455: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1455
SELECT filing.form_type, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1456: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1456
SELECT filing.form_type, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1457: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1457
SELECT filing.form_type, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1458: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1458
SELECT filing.form_type, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1459: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1459
SELECT filing.form_type, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1460: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1460
SELECT filing.form_type, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1461: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1461
SELECT filing.form_type, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1462: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1462
SELECT filing.form_type, AVG(filing_metrics.investing_cash_flow_usd) AS avg_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1463: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1463
SELECT filing.form_type, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1464: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1464
SELECT filing.form_type, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1465: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1465
SELECT filing.form_type, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1466: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1466
SELECT filing.form_type, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1467: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1467
SELECT filing.form_type, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1468: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1468
SELECT filing.form_type, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1469: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1469
SELECT filing.form_type, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1470: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1470
SELECT filing.form_type, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1471: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1471
SELECT filing.form_type, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1472: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1472
SELECT filing.form_type, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1473: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1473
SELECT filing.form_type, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1474: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1474
SELECT filing.form_type, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1475: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1475
SELECT filing.form_type, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1476: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1476
SELECT filing.form_type, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1477: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1477
SELECT filing.form_type, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1478: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1478
SELECT filing.form_type, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1479: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1479
SELECT filing.form_type, MIN(filing_metrics.investing_cash_flow_usd) AS min_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1480: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1480
SELECT filing.form_type, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1481: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1481
SELECT filing.form_type, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1482: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1482
SELECT filing.form_type, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1483: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1483
SELECT filing.form_type, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1484: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1484
SELECT filing.form_type, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1485: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1485
SELECT filing.form_type, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1486: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1486
SELECT filing.form_type, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1487: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1487
SELECT filing.form_type, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1488: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1488
SELECT filing.form_type, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1489: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1489
SELECT filing.form_type, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1490: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1490
SELECT filing.form_type, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1491: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1491
SELECT filing.form_type, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1492: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1492
SELECT filing.form_type, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1493: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1493
SELECT filing.form_type, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1494: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1494
SELECT filing.form_type, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1495: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1495
SELECT filing.form_type, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1496: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1496
SELECT filing.form_type, MAX(filing_metrics.investing_cash_flow_usd) AS max_investing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1497: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1497
SELECT filing.form_type, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1498: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1498
SELECT filing.form_type, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1499: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1499
SELECT filing.form_type, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1500: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1500
SELECT filing.form_type, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1501: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1501
SELECT filing.form_type, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1502: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1502
SELECT filing.form_type, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1503: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1503
SELECT filing.form_type, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1504: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1504
SELECT filing.form_type, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1505: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1505
SELECT filing.form_type, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1506: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1506
SELECT filing.form_type, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1507: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1507
SELECT filing.form_type, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1508: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1508
SELECT filing.form_type, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1509: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1509
SELECT filing.form_type, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1510: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1510
SELECT filing.form_type, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1511: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1511
SELECT filing.form_type, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1512: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1512
SELECT filing.form_type, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1513: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1513
SELECT filing.form_type, SUM(filing_metrics.financing_cash_flow_usd) AS sum_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1514: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1514
SELECT filing.form_type, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1515: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1515
SELECT filing.form_type, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1516: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1516
SELECT filing.form_type, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1517: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1517
SELECT filing.form_type, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1518: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1518
SELECT filing.form_type, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1519: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1519
SELECT filing.form_type, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1520: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1520
SELECT filing.form_type, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1521: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1521
SELECT filing.form_type, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1522: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1522
SELECT filing.form_type, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1523: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1523
SELECT filing.form_type, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1524: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1524
SELECT filing.form_type, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1525: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1525
SELECT filing.form_type, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1526: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1526
SELECT filing.form_type, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1527: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1527
SELECT filing.form_type, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1528: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1528
SELECT filing.form_type, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1529: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1529
SELECT filing.form_type, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1530: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1530
SELECT filing.form_type, AVG(filing_metrics.financing_cash_flow_usd) AS avg_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1531: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1531
SELECT filing.form_type, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1532: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1532
SELECT filing.form_type, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1533: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1533
SELECT filing.form_type, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1534: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1534
SELECT filing.form_type, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1535: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1535
SELECT filing.form_type, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1536: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1536
SELECT filing.form_type, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1537: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1537
SELECT filing.form_type, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1538: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1538
SELECT filing.form_type, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1539: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1539
SELECT filing.form_type, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1540: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1540
SELECT filing.form_type, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1541: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1541
SELECT filing.form_type, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1542: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1542
SELECT filing.form_type, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1543: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1543
SELECT filing.form_type, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1544: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1544
SELECT filing.form_type, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1545: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1545
SELECT filing.form_type, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1546: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1546
SELECT filing.form_type, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1547: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1547
SELECT filing.form_type, MIN(filing_metrics.financing_cash_flow_usd) AS min_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1548: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1548
SELECT filing.form_type, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1549: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1549
SELECT filing.form_type, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1550: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1550
SELECT filing.form_type, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1551: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1551
SELECT filing.form_type, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1552: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1552
SELECT filing.form_type, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1553: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1553
SELECT filing.form_type, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1554: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1554
SELECT filing.form_type, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1555: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1555
SELECT filing.form_type, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1556: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1556
SELECT filing.form_type, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1557: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1557
SELECT filing.form_type, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1558: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1558
SELECT filing.form_type, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1559: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1559
SELECT filing.form_type, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1560: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1560
SELECT filing.form_type, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1561: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1561
SELECT filing.form_type, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1562: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1562
SELECT filing.form_type, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1563: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1563
SELECT filing.form_type, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1564: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1564
SELECT filing.form_type, MAX(filing_metrics.financing_cash_flow_usd) AS max_financing_cash_flow_usd FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1565: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1565
SELECT filing.form_type, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1566: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1566
SELECT filing.form_type, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1567: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1567
SELECT filing.form_type, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1568: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1568
SELECT filing.form_type, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1569: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1569
SELECT filing.form_type, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1570: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1570
SELECT filing.form_type, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1571: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1571
SELECT filing.form_type, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1572: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1572
SELECT filing.form_type, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1573: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1573
SELECT filing.form_type, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1574: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1574
SELECT filing.form_type, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1575: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1575
SELECT filing.form_type, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1576: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1576
SELECT filing.form_type, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1577: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1577
SELECT filing.form_type, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1578: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1578
SELECT filing.form_type, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1579: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1579
SELECT filing.form_type, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1580: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1580
SELECT filing.form_type, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1581: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1581
SELECT filing.form_type, SUM(filing_metrics.shares_outstanding) AS sum_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1582: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1582
SELECT filing.form_type, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1583: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1583
SELECT filing.form_type, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1584: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1584
SELECT filing.form_type, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1585: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1585
SELECT filing.form_type, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1586: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1586
SELECT filing.form_type, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1587: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1587
SELECT filing.form_type, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1588: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1588
SELECT filing.form_type, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1589: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1589
SELECT filing.form_type, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1590: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1590
SELECT filing.form_type, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1591: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1591
SELECT filing.form_type, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1592: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1592
SELECT filing.form_type, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1593: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1593
SELECT filing.form_type, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1594: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1594
SELECT filing.form_type, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1595: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1595
SELECT filing.form_type, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1596: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1596
SELECT filing.form_type, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1597: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1597
SELECT filing.form_type, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1598: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1598
SELECT filing.form_type, AVG(filing_metrics.shares_outstanding) AS avg_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1599: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1599
SELECT filing.form_type, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1600: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1600
SELECT filing.form_type, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1601: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1601
SELECT filing.form_type, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1602: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1602
SELECT filing.form_type, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1603: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1603
SELECT filing.form_type, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1604: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1604
SELECT filing.form_type, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1605: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1605
SELECT filing.form_type, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1606: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1606
SELECT filing.form_type, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1607: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1607
SELECT filing.form_type, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1608: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1608
SELECT filing.form_type, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1609: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1609
SELECT filing.form_type, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1610: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1610
SELECT filing.form_type, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1611: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1611
SELECT filing.form_type, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1612: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1612
SELECT filing.form_type, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1613: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1613
SELECT filing.form_type, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1614: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1614
SELECT filing.form_type, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1615: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1615
SELECT filing.form_type, MIN(filing_metrics.shares_outstanding) AS min_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;

-- Query 1616: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1616
SELECT filing.form_type, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Electronic Computers' GROUP BY filing.form_type;

-- Query 1617: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1617
SELECT filing.form_type, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Motor Vehicles & Passenger Car Bodies' GROUP BY filing.form_type;

-- Query 1618: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1618
SELECT filing.form_type, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'National Commercial Banks' GROUP BY filing.form_type;

-- Query 1619: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1619
SELECT filing.form_type, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Petroleum Refining' GROUP BY filing.form_type;

-- Query 1620: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1620
SELECT filing.form_type, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Pharmaceutical Preparations' GROUP BY filing.form_type;

-- Query 1621: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1621
SELECT filing.form_type, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.sic_description = 'Retail-Catalog & Mail-Order Houses' GROUP BY filing.form_type;

-- Query 1622: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1622
SELECT filing.form_type, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'CA' GROUP BY filing.form_type;

-- Query 1623: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1623
SELECT filing.form_type, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'DE' GROUP BY filing.form_type;

-- Query 1624: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1624
SELECT filing.form_type, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'NJ' GROUP BY filing.form_type;

-- Query 1625: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1625
SELECT filing.form_type, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'TX' GROUP BY filing.form_type;

-- Query 1626: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1626
SELECT filing.form_type, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE company.state_of_incorporation = 'WA' GROUP BY filing.form_type;

-- Query 1627: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1627
SELECT filing.form_type, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-K' GROUP BY filing.form_type;

-- Query 1628: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1628
SELECT filing.form_type, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing.form_type = '10-Q' GROUP BY filing.form_type;

-- Query 1629: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1629
SELECT filing.form_type, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.revenue_usd > 0 GROUP BY filing.form_type;

-- Query 1630: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1630
SELECT filing.form_type, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd > 0 GROUP BY filing.form_type;

-- Query 1631: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1631
SELECT filing.form_type, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.net_income_usd < 0 GROUP BY filing.form_type;

-- Query 1632: agg_filter_join (agg_filter_join) id=agg_filter_join_sec_1632
SELECT filing.form_type, MAX(filing_metrics.shares_outstanding) AS max_shares_outstanding FROM filing_metrics JOIN company ON filing_metrics.company_id = company.company_id JOIN filing ON filing_metrics.filing_id = filing.filing_id WHERE filing_metrics.assets_usd > filing_metrics.liabilities_usd GROUP BY filing.form_type;
