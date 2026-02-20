-- Query 1: 1 (Finance)
SELECT business_segments_num, dividend_per_share, auditor FROM Finance WHERE auditor = 'PKF Littlejohn LLP';

-- Query 2: 1 (Finance)
SELECT net_assets, board_members, net_profit_or_loss FROM Finance WHERE net_profit_or_loss > '1460000000';

-- Query 3: 1 (Finance)
SELECT bussiness_cost, remuneration_policy, registered_office FROM Finance WHERE bussiness_cost <= '2129327000';

-- Query 4: 1 (Finance)
SELECT net_profit_or_loss, exchange_code, total_Debt FROM Finance WHERE total_Debt = '21325000000';

-- Query 5: 1 (Finance)
SELECT principal_activities, bussiness_profit, major_events FROM Finance WHERE bussiness_profit > '230400000';

-- Query 6: 1 (Finance)
SELECT major_equity_changes, exchange_code, the_highest_ownership_stake FROM Finance WHERE exchange_code = 'RFT';

-- Query 7: 1 (Finance)
SELECT bussiness_profit, auditor, total_assets FROM Finance WHERE auditor != 'PKF Littlejohn LLP';

-- Query 8: 1 (Finance)
SELECT bussiness_sales, net_profit_or_loss, net_assets FROM Finance WHERE net_assets != 249398000;

-- Query 9: 1 (Finance)
SELECT principal_activities, total_Debt, major_equity_changes FROM Finance WHERE major_equity_changes != 'Yes';

-- Query 10: 1 (Finance)
SELECT largest_shareholder, company_name, executive_profiles FROM Finance WHERE company_name != 'NuCana plc';

-- Query 11: 2 (Finance)
SELECT largest_shareholder, auditor, registered_office FROM Finance WHERE largest_shareholder != 'Kelly Investments 1 PTY Ltd' AND business_risks = 'Environmental Risk';

-- Query 12: 2 (Finance)
SELECT cash_reserves, bussiness_profit, auditor FROM Finance WHERE auditor = 'PKF Littlejohn LLP' AND major_equity_changes = 'Yes';

-- Query 13: 2 (Finance)
SELECT dividend_per_share, bussiness_profit, total_Debt FROM Finance WHERE dividend_per_share < 0.40 AND earnings_per_share >= 0.49;

-- Query 14: 2 (Finance)
SELECT net_profit_or_loss, principal_activities, major_equity_changes FROM Finance WHERE net_profit_or_loss >= '2823562' AND total_Debt > '14437351';

-- Query 15: 2 (Finance)
SELECT total_assets, bussiness_profit, principal_activities FROM Finance WHERE principal_activities != 'Finance' AND exchange_code != 'AIM';

-- Query 16: 2 (Finance)
SELECT remuneration_policy, net_assets, principal_activities FROM Finance WHERE remuneration_policy != 'Stock Option' AND total_assets >= 136955488;

-- Query 17: 2 (Finance)
SELECT board_members, revenue, cash_reserves FROM Finance WHERE board_members != 'Keith Bradley' AND business_segments_num < 1;

-- Query 18: 2 (Finance)
SELECT earnings_per_share, the_highest_ownership_stake, net_profit_or_loss FROM Finance WHERE net_profit_or_loss != '165500000' AND bussiness_cost >= '993529';
