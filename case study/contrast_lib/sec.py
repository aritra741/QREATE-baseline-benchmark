"""SEC contrast workloads: realistic filing-analyst questions on 10-K / 10-Q metrics."""

from .common import q

DATASET = "SEC"
BASELINE = "sec_agg20"
JOIN_NOTES = {
    "metrics_company": "filing_metrics.company_id = company.company_id",
    "metrics_filing": "filing_metrics.filing_id = filing.filing_id",
    "metrics_concept": "filing_metrics.revenue_usd_concept_id = concept.concept_id",
}

INDUSTRY_FAMILY = """
CASE
  WHEN m.sic_description LIKE '%Computer%' OR m.sic_description LIKE '%Software%' OR m.sic_description LIKE '%Semiconductor%' THEN 'Technology'
  WHEN m.sic_description LIKE '%Retail%' THEN 'Retail'
  WHEN m.sic_description LIKE '%Bank%' THEN 'Financial'
  WHEN m.sic_description LIKE '%Petroleum%' THEN 'Energy'
  WHEN m.sic_description LIKE '%Pharmaceutical%' THEN 'Healthcare'
  WHEN m.sic_description LIKE '%Motor%' THEN 'Automotive'
  ELSE 'Other'
END
""".strip()

STATE_FAMILY = """
CASE
  WHEN m.state_of_incorporation = 'DE' THEN 'Delaware'
  WHEN m.state_of_incorporation != '' THEN 'other_state'
END
""".strip()

CONCEPT_FAMILY = """
CASE
  WHEN con.concept_name LIKE '%RevenueFromContract%' THEN 'contract_revenue'
  WHEN con.concept_name LIKE '%Revenue%' THEN 'revenues'
  ELSE 'other_concept'
END
""".strip()

WORKLOADS = {
    "sec_agg20": {
        "title": "Simple aggregation workload",
        "focus": "Single-table GROUP BY with one aggregate",
        "kind": "baseline",
        "queries": [
            q("q0", "SELECT ticker, COUNT(*) AS filing_count FROM filing_metrics GROUP BY ticker", "How many filings are there for each issuer?"),
            q("q1", "SELECT form_type, COUNT(*) AS filing_count FROM filing_metrics GROUP BY form_type", "How many filings are 10-Ks versus 10-Qs?"),
            q("q2", "SELECT fiscal_year, COUNT(*) AS filing_count FROM filing_metrics WHERE fiscal_year BETWEEN 2022 AND 2025 GROUP BY fiscal_year", "How many filings are there for each fiscal year from 2022 through 2025?"),
            q("q3", "SELECT fiscal_period, COUNT(*) AS filing_count FROM filing_metrics GROUP BY fiscal_period", "How many filings are there for each fiscal period?"),
            q("q4", "SELECT state_of_incorporation, COUNT(*) AS filing_count FROM filing_metrics WHERE state_of_incorporation != '' GROUP BY state_of_incorporation", "How many filings come from issuers incorporated in each state?"),
            q("q5", f"SELECT {INDUSTRY_FAMILY} AS industry_family, COUNT(*) AS filing_count FROM filing_metrics m GROUP BY industry_family", "How many filings come from technology, retail, financial, energy, healthcare, or automotive issuers?"),
            q("q6", "SELECT ticker, AVG(revenue_usd) AS avg_revenue FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker", "What is the average reported revenue for each issuer?"),
            q("q7", "SELECT form_type, AVG(net_income_usd) AS avg_net_income FROM filing_metrics WHERE net_income_usd IS NOT NULL GROUP BY form_type", "What is the average net income in 10-K versus 10-Q filings?"),
            q("q8", "SELECT fiscal_year, AVG(assets_usd) AS avg_assets FROM filing_metrics WHERE fiscal_year BETWEEN 2022 AND 2025 AND assets_usd IS NOT NULL GROUP BY fiscal_year", "What is the average reported assets in each fiscal year from 2022 through 2025?"),
            q("q9", "SELECT fiscal_period, AVG(operating_cash_flow_usd) AS avg_ocf FROM filing_metrics WHERE operating_cash_flow_usd IS NOT NULL GROUP BY fiscal_period", "What is the average operating cash flow for each fiscal period?"),
            q("q10", "SELECT ticker, MAX(revenue_usd) AS max_revenue FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY ticker", "What is the highest reported revenue for each issuer?"),
            q("q11", "SELECT state_of_incorporation, AVG(net_income_usd) AS avg_net_income FROM filing_metrics WHERE state_of_incorporation != '' AND net_income_usd IS NOT NULL GROUP BY state_of_incorporation", "What is the average net income for issuers incorporated in each state?"),
            q("q12", f"SELECT {INDUSTRY_FAMILY} AS industry_family, AVG(revenue_usd) AS avg_revenue FROM filing_metrics m WHERE revenue_usd IS NOT NULL GROUP BY industry_family", "What is the average revenue for each industry family?"),
            q("q13", "SELECT form_type, SUM(CASE WHEN net_income_usd > 0 THEN 1 ELSE 0 END) AS profitable_filings FROM filing_metrics WHERE net_income_usd IS NOT NULL GROUP BY form_type", "How many 10-K versus 10-Q filings report positive net income?"),
            q("q14", "SELECT fiscal_year, MAX(assets_usd) AS max_assets FROM filing_metrics WHERE fiscal_year BETWEEN 2022 AND 2025 GROUP BY fiscal_year", "What is the largest asset total reported in each fiscal year from 2022 through 2025?"),
            q("q15", "SELECT ticker, AVG(operating_cash_flow_usd) AS avg_ocf FROM filing_metrics WHERE operating_cash_flow_usd IS NOT NULL GROUP BY ticker", "What is the average operating cash flow for each issuer?"),
            q("q16", "SELECT fiscal_period, AVG(revenue_usd) AS avg_revenue FROM filing_metrics WHERE revenue_usd IS NOT NULL GROUP BY fiscal_period", "What is the average revenue reported for each fiscal period?"),
            q("q17", f"SELECT {STATE_FAMILY} AS state_family, COUNT(*) AS filing_count FROM filing_metrics m GROUP BY state_family", "How many filings come from Delaware-incorporated issuers versus issuers incorporated elsewhere?"),
            q("q18", "SELECT ticker, MIN(net_income_usd) AS min_net_income FROM filing_metrics WHERE net_income_usd IS NOT NULL GROUP BY ticker", "What is the lowest reported net income for each issuer?"),
            q("q19", f"SELECT {INDUSTRY_FAMILY} AS industry_family, AVG(assets_usd) AS avg_assets FROM filing_metrics m WHERE assets_usd IS NOT NULL GROUP BY industry_family", "What is the average asset total for each industry family?"),
        ],
    },
    "sec_join20": {
        "title": "Join-depth workload",
        "focus": "1–3 table joins; aggregation is light and secondary",
        "kind": "pure",
        "contrast_with": BASELINE,
        "queries": [
            q("q0", "SELECT c.ticker, COUNT(*) AS filing_count FROM filing_metrics m JOIN company c ON m.company_id = c.company_id GROUP BY c.ticker", "How many filings are there for each company?"),
            q("q1", "SELECT c.state_of_incorporation, AVG(m.revenue_usd) AS avg_revenue FROM filing_metrics m JOIN company c ON m.company_id = c.company_id WHERE m.revenue_usd IS NOT NULL GROUP BY c.state_of_incorporation", "What is the average filing revenue for companies incorporated in each state?"),
            q("q2", "SELECT c.sic_description, COUNT(*) AS filing_count FROM filing_metrics m JOIN company c ON m.company_id = c.company_id GROUP BY c.sic_description", "How many filings are there for companies in each industry?"),
            q("q3", "SELECT CASE WHEN c.state_of_incorporation = 'DE' THEN 'Delaware' ELSE 'other_state' END AS state_family, AVG(m.net_income_usd) AS avg_net_income FROM filing_metrics m JOIN company c ON m.company_id = c.company_id WHERE m.net_income_usd IS NOT NULL GROUP BY state_family", "What is the average net income for Delaware-incorporated companies versus companies incorporated elsewhere?"),
            q("q4", "SELECT f.form_type, COUNT(*) AS filing_count FROM filing_metrics m JOIN filing f ON m.filing_id = f.filing_id GROUP BY f.form_type", "How many filings are 10-Ks versus 10-Qs?"),
            q("q5", "SELECT f.fiscal_year, AVG(m.assets_usd) AS avg_assets FROM filing_metrics m JOIN filing f ON m.filing_id = f.filing_id WHERE f.fiscal_year BETWEEN 2022 AND 2025 AND m.assets_usd IS NOT NULL GROUP BY f.fiscal_year", "What is the average assets figure for filings from each fiscal year 2022–2025?"),
            q("q6", "SELECT f.fiscal_period, AVG(m.operating_cash_flow_usd) AS avg_ocf FROM filing_metrics m JOIN filing f ON m.filing_id = f.filing_id WHERE m.operating_cash_flow_usd IS NOT NULL GROUP BY f.fiscal_period", "What is the average operating cash flow for each fiscal period?"),
            q("q7", "SELECT f.ticker, MAX(m.revenue_usd) AS max_revenue FROM filing_metrics m JOIN filing f ON m.filing_id = f.filing_id WHERE m.revenue_usd IS NOT NULL GROUP BY f.ticker", "What is the highest revenue attached to a filing for each ticker?"),
            q("q8", "SELECT con.concept_name, COUNT(*) AS filing_count FROM filing_metrics m JOIN concept con ON m.revenue_usd_concept_id = con.concept_id GROUP BY con.concept_name", "How many filings report revenue using each revenue concept?"),
            q("q9", f"SELECT {CONCEPT_FAMILY} AS concept_family, AVG(m.revenue_usd) AS avg_revenue FROM filing_metrics m JOIN concept con ON m.revenue_usd_concept_id = con.concept_id WHERE m.revenue_usd IS NOT NULL GROUP BY concept_family", "What is the average revenue for filings that use a contract-revenue concept versus a generic revenues concept?"),
            q("q10", "SELECT c.ticker, f.form_type, COUNT(*) AS filing_count FROM filing_metrics m JOIN company c ON m.company_id = c.company_id JOIN filing f ON m.filing_id = f.filing_id GROUP BY c.ticker, f.form_type", "For each company, how many filings are 10-Ks versus 10-Qs?"),
            q("q11", "SELECT c.state_of_incorporation, f.fiscal_year, AVG(m.net_income_usd) AS avg_net_income FROM filing_metrics m JOIN company c ON m.company_id = c.company_id JOIN filing f ON m.filing_id = f.filing_id WHERE f.fiscal_year BETWEEN 2022 AND 2025 AND m.net_income_usd IS NOT NULL GROUP BY c.state_of_incorporation, f.fiscal_year", "For each state of incorporation and fiscal year, what is the average net income?"),
            q("q12", "SELECT f.fiscal_period, c.state_of_incorporation, COUNT(*) AS filing_count FROM filing_metrics m JOIN company c ON m.company_id = c.company_id JOIN filing f ON m.filing_id = f.filing_id GROUP BY f.fiscal_period, c.state_of_incorporation", "For each fiscal period, how many filings come from companies incorporated in each state?"),
            q("q13", "SELECT c.ticker, AVG(m.operating_cash_flow_usd) AS avg_ocf FROM filing_metrics m JOIN company c ON m.company_id = c.company_id JOIN filing f ON m.filing_id = f.filing_id WHERE f.form_type = '10-Q' AND m.operating_cash_flow_usd IS NOT NULL GROUP BY c.ticker", "Among quarterly filings, what is the average operating cash flow for each company?"),
            q("q14", "SELECT c.state_of_incorporation, con.concept_name, COUNT(*) AS filing_count FROM filing_metrics m JOIN company c ON m.company_id = c.company_id JOIN concept con ON m.revenue_usd_concept_id = con.concept_id GROUP BY c.state_of_incorporation, con.concept_name", "For companies in each state, how many filings use each revenue concept?"),
            q("q15", "SELECT f.form_type, con.concept_name, AVG(m.revenue_usd) AS avg_revenue FROM filing_metrics m JOIN filing f ON m.filing_id = f.filing_id JOIN concept con ON m.revenue_usd_concept_id = con.concept_id WHERE m.revenue_usd IS NOT NULL GROUP BY f.form_type, con.concept_name", "For 10-K versus 10-Q filings, what is the average revenue under each revenue concept?"),
            q("q16", "SELECT c.ticker, f.fiscal_year, con.concept_name, COUNT(*) AS filing_count FROM filing_metrics m JOIN company c ON m.company_id = c.company_id JOIN filing f ON m.filing_id = f.filing_id JOIN concept con ON m.revenue_usd_concept_id = con.concept_id WHERE f.fiscal_year BETWEEN 2022 AND 2025 GROUP BY c.ticker, f.fiscal_year, con.concept_name", "For each company and fiscal year, how many filings use each revenue concept?"),
            q("q17", "SELECT c.state_of_incorporation, f.form_type, AVG(m.assets_usd) AS avg_assets FROM filing_metrics m JOIN company c ON m.company_id = c.company_id JOIN filing f ON m.filing_id = f.filing_id JOIN concept con ON m.revenue_usd_concept_id = con.concept_id WHERE m.assets_usd IS NOT NULL GROUP BY c.state_of_incorporation, f.form_type", "For each state and form type, among filings with a known revenue concept, what is the average asset total?"),
            q("q18", f"SELECT {CONCEPT_FAMILY} AS concept_family, f.fiscal_period, COUNT(*) AS filing_count FROM filing_metrics m JOIN company c ON m.company_id = c.company_id JOIN filing f ON m.filing_id = f.filing_id JOIN concept con ON m.revenue_usd_concept_id = con.concept_id GROUP BY concept_family, f.fiscal_period", "For contract-revenue versus generic revenues concepts, how many filings are there in each fiscal period?"),
            q("q19", "SELECT c.ticker, AVG(m.net_income_usd) AS avg_net_income FROM filing_metrics m JOIN company c ON m.company_id = c.company_id JOIN filing f ON m.filing_id = f.filing_id JOIN concept con ON m.revenue_usd_concept_id = con.concept_id WHERE f.form_type = '10-K' AND m.net_income_usd IS NOT NULL GROUP BY c.ticker", "Among annual filings with a known revenue concept, what is the average net income for each company?"),
        ],
    },
    "sec_groupby20": {
        "title": "Group-by variety workload",
        "focus": "Diverse GROUP BY keys, including multi-column and joined keys",
        "kind": "pure",
        "contrast_with": BASELINE,
        "queries": [
            q("q0", "SELECT ticker, form_type, COUNT(*) AS filing_count FROM filing_metrics GROUP BY ticker, form_type", "For each issuer, how many filings are 10-Ks versus 10-Qs?"),
            q("q1", "SELECT fiscal_year, fiscal_period, COUNT(*) AS filing_count FROM filing_metrics WHERE fiscal_year BETWEEN 2022 AND 2025 GROUP BY fiscal_year, fiscal_period", "For each fiscal year from 2022 through 2025, how many filings are there in each fiscal period?"),
            q("q2", "SELECT state_of_incorporation, form_type, COUNT(*) AS filing_count FROM filing_metrics GROUP BY state_of_incorporation, form_type", "For issuers incorporated in each state, how many filings are 10-Ks versus 10-Qs?"),
            q("q3", f"SELECT {INDUSTRY_FAMILY} AS industry_family, form_type, COUNT(*) AS filing_count FROM filing_metrics m GROUP BY industry_family, form_type", "For each industry family, how many filings are 10-Ks versus 10-Qs?"),
            q("q4", "SELECT ticker, CASE WHEN net_income_usd > 0 THEN 'profitable' ELSE 'loss_or_zero' END AS profit_status, COUNT(*) AS filing_count FROM filing_metrics WHERE net_income_usd IS NOT NULL GROUP BY ticker, profit_status", "For each issuer, how many filings report a profit versus a loss or zero?"),
            q("q5", "SELECT fiscal_year, CASE WHEN revenue_usd >= 100000000000 THEN 'revenue_100b_plus' ELSE 'revenue_under_100b' END AS revenue_band, COUNT(*) AS filing_count FROM filing_metrics WHERE fiscal_year BETWEEN 2022 AND 2025 AND revenue_usd IS NOT NULL GROUP BY fiscal_year, revenue_band", "For each fiscal year, how many filings report at least $100 billion in revenue versus less?"),
            q("q6", f"SELECT {STATE_FAMILY} AS state_family, fiscal_period, COUNT(*) AS filing_count FROM filing_metrics m GROUP BY state_family, fiscal_period", "For Delaware versus other issuers, how many filings are there in each fiscal period?"),
            q("q7", f"SELECT {INDUSTRY_FAMILY} AS industry_family, CASE WHEN net_income_usd > 0 THEN 'profitable' ELSE 'loss_or_zero' END AS profit_status, COUNT(*) AS filing_count FROM filing_metrics m WHERE net_income_usd IS NOT NULL GROUP BY industry_family, profit_status", "For each industry family, how many filings are profitable versus not?"),
            q("q8", "SELECT form_type, CASE WHEN operating_cash_flow_usd > 0 THEN 'positive_ocf' ELSE 'nonpositive_ocf' END AS ocf_status, COUNT(*) AS filing_count FROM filing_metrics WHERE operating_cash_flow_usd IS NOT NULL GROUP BY form_type, ocf_status", "For 10-K versus 10-Q filings, how many report positive operating cash flow versus not?"),
            q("q9", "SELECT ticker, fiscal_year, COUNT(*) AS filing_count FROM filing_metrics WHERE fiscal_year BETWEEN 2022 AND 2025 GROUP BY ticker, fiscal_year", "For each issuer and fiscal year from 2022 through 2025, how many filings are there?"),
            q("q10", "SELECT state_of_incorporation, CASE WHEN assets_usd >= 500000000000 THEN 'assets_500b_plus' ELSE 'assets_under_500b' END AS asset_band, COUNT(*) AS filing_count FROM filing_metrics WHERE assets_usd IS NOT NULL GROUP BY state_of_incorporation, asset_band", "For issuers in each state, how many filings report at least $500 billion in assets versus less?"),
            q("q11", f"SELECT {INDUSTRY_FAMILY} AS industry_family, fiscal_period, COUNT(*) AS filing_count FROM filing_metrics m GROUP BY industry_family, fiscal_period", "For each industry family, how many filings are there in each fiscal period?"),
            q("q12", "SELECT fiscal_year, form_type, CASE WHEN net_income_usd > 0 THEN 'profitable' ELSE 'loss_or_zero' END AS profit_status, COUNT(*) AS filing_count FROM filing_metrics WHERE fiscal_year BETWEEN 2022 AND 2025 AND net_income_usd IS NOT NULL GROUP BY fiscal_year, form_type, profit_status", "For each fiscal year and form type, how many filings are profitable versus not?"),
            q("q13", "SELECT c.ticker, f.fiscal_period, COUNT(*) AS filing_count FROM filing_metrics m JOIN company c ON m.company_id = c.company_id JOIN filing f ON m.filing_id = f.filing_id GROUP BY c.ticker, f.fiscal_period", "For each company, how many filings are there in each fiscal period?"),
            q("q14", "SELECT c.state_of_incorporation, f.form_type, CASE WHEN m.net_income_usd > 0 THEN 'profitable' ELSE 'loss_or_zero' END AS profit_status, COUNT(*) AS filing_count FROM filing_metrics m JOIN company c ON m.company_id = c.company_id JOIN filing f ON m.filing_id = f.filing_id WHERE m.net_income_usd IS NOT NULL GROUP BY c.state_of_incorporation, f.form_type, profit_status", "For each state and form type, how many filings are profitable versus not?"),
            q("q15", f"SELECT {CONCEPT_FAMILY} AS concept_family, f.form_type, COUNT(*) AS filing_count FROM filing_metrics m JOIN filing f ON m.filing_id = f.filing_id JOIN concept con ON m.revenue_usd_concept_id = con.concept_id GROUP BY concept_family, f.form_type", "For each revenue-concept family, how many filings are 10-Ks versus 10-Qs?"),
            q("q16", "SELECT f.fiscal_year, con.concept_name, COUNT(*) AS filing_count FROM filing_metrics m JOIN filing f ON m.filing_id = f.filing_id JOIN concept con ON m.revenue_usd_concept_id = con.concept_id WHERE f.fiscal_year BETWEEN 2022 AND 2025 GROUP BY f.fiscal_year, con.concept_name", "For each fiscal year, how many filings use each revenue concept?"),
            q("q17", f"SELECT {INDUSTRY_FAMILY} AS industry_family, CASE WHEN m.operating_cash_flow_usd > 0 THEN 'positive_ocf' ELSE 'nonpositive_ocf' END AS ocf_status, COUNT(*) AS filing_count FROM filing_metrics m WHERE m.operating_cash_flow_usd IS NOT NULL GROUP BY industry_family, ocf_status", "For each industry family, how many filings report positive operating cash flow versus not?"),
            q("q18", "SELECT ticker, CASE WHEN liabilities_usd >= assets_usd THEN 'liabilities_ge_assets' ELSE 'assets_exceed_liabilities' END AS leverage_status, COUNT(*) AS filing_count FROM filing_metrics WHERE assets_usd IS NOT NULL AND liabilities_usd IS NOT NULL GROUP BY ticker, leverage_status", "For each issuer, how many filings have liabilities at least as large as assets versus assets exceeding liabilities?"),
            q("q19", "SELECT fiscal_period, CASE WHEN net_income_usd >= 20000000000 THEN 'ni_20b_plus' ELSE 'ni_under_20b' END AS income_band, COUNT(*) AS filing_count FROM filing_metrics WHERE net_income_usd IS NOT NULL GROUP BY fiscal_period, income_band", "For each fiscal period, how many filings report at least $20 billion in net income versus less?"),
        ],
    },
    "sec_multiagg20": {
        "title": "Multi-aggregation workload",
        "focus": "Several aggregates, often with HAVING, in the same query",
        "kind": "pure",
        "contrast_with": BASELINE,
        "queries": [
            q("q0", "SELECT ticker, COUNT(*) AS filing_count, AVG(revenue_usd) AS avg_revenue, AVG(net_income_usd) AS avg_net_income FROM filing_metrics WHERE revenue_usd IS NOT NULL AND net_income_usd IS NOT NULL GROUP BY ticker", "For each issuer, how many filings have both revenue and net income, and what are the averages of each?"),
            q("q1", "SELECT form_type, COUNT(*) AS filing_count, AVG(assets_usd) AS avg_assets, AVG(liabilities_usd) AS avg_liabilities, AVG(net_income_usd) AS avg_net_income FROM filing_metrics WHERE assets_usd IS NOT NULL AND liabilities_usd IS NOT NULL AND net_income_usd IS NOT NULL GROUP BY form_type", "For 10-K versus 10-Q filings, what are the count and the average assets, liabilities, and net income?"),
            q("q2", "SELECT fiscal_year, COUNT(*) AS filing_count, AVG(revenue_usd) AS avg_revenue, MAX(revenue_usd) AS max_revenue, AVG(operating_cash_flow_usd) AS avg_ocf FROM filing_metrics WHERE fiscal_year BETWEEN 2022 AND 2025 AND revenue_usd IS NOT NULL AND operating_cash_flow_usd IS NOT NULL GROUP BY fiscal_year", "For each fiscal year from 2022 through 2025, what are the filing count, average and maximum revenue, and average operating cash flow?"),
            q("q3", "SELECT fiscal_period, COUNT(*) AS filing_count, AVG(net_income_usd) AS avg_net_income, MIN(net_income_usd) AS min_net_income, MAX(net_income_usd) AS max_net_income FROM filing_metrics WHERE net_income_usd IS NOT NULL GROUP BY fiscal_period", "For each fiscal period, what are the filing count and the average, lowest, and highest net income?"),
            q("q4", "SELECT state_of_incorporation, COUNT(*) AS filing_count, AVG(revenue_usd) AS avg_revenue, AVG(assets_usd) AS avg_assets FROM filing_metrics WHERE revenue_usd IS NOT NULL AND assets_usd IS NOT NULL GROUP BY state_of_incorporation", "For issuers in each state, what are the filing count and the average revenue and assets?"),
            q("q5", f"SELECT {INDUSTRY_FAMILY} AS industry_family, COUNT(*) AS filing_count, AVG(revenue_usd) AS avg_revenue, AVG(net_income_usd) AS avg_net_income, SUM(CASE WHEN m.net_income_usd > 0 THEN 1 ELSE 0 END) AS profitable_count FROM filing_metrics m WHERE revenue_usd IS NOT NULL AND net_income_usd IS NOT NULL GROUP BY industry_family", "For each industry family, what are the filing count, average revenue and net income, and number of profitable filings?"),
            q("q6", "SELECT ticker, COUNT(*) AS filing_count, AVG(operating_cash_flow_usd) AS avg_ocf, AVG(investing_cash_flow_usd) AS avg_icf, AVG(financing_cash_flow_usd) AS avg_fcf FROM filing_metrics WHERE operating_cash_flow_usd IS NOT NULL AND investing_cash_flow_usd IS NOT NULL AND financing_cash_flow_usd IS NOT NULL GROUP BY ticker", "For each issuer, what are the filing count and the average operating, investing, and financing cash flows?"),
            q("q7", f"SELECT {STATE_FAMILY} AS state_family, COUNT(*) AS filing_count, AVG(net_income_usd) AS avg_net_income, MAX(assets_usd) AS max_assets FROM filing_metrics m WHERE net_income_usd IS NOT NULL AND assets_usd IS NOT NULL GROUP BY state_family", "For Delaware versus other issuers, what are the filing count, average net income, and largest asset total?"),
            q("q8", "SELECT form_type, fiscal_year, COUNT(*) AS filing_count, AVG(revenue_usd) AS avg_revenue, AVG(net_income_usd) AS avg_net_income FROM filing_metrics WHERE fiscal_year BETWEEN 2022 AND 2025 AND revenue_usd IS NOT NULL AND net_income_usd IS NOT NULL GROUP BY form_type, fiscal_year", "For each form type and fiscal year, what are the filing count and the average revenue and net income?"),
            q("q9", "SELECT ticker, COUNT(*) AS filing_count, SUM(CASE WHEN net_income_usd > 0 THEN 1 ELSE 0 END) AS profitable_count, AVG(revenue_usd) AS avg_revenue, MAX(net_income_usd) AS max_net_income FROM filing_metrics WHERE revenue_usd IS NOT NULL AND net_income_usd IS NOT NULL GROUP BY ticker", "For each issuer, how many filings have revenue and net income, how many are profitable, and what are the average revenue and highest net income?"),
            q("q10", "SELECT fiscal_period, COUNT(*) AS filing_count, AVG(assets_usd) AS avg_assets, AVG(liabilities_usd) AS avg_liabilities, AVG(revenue_usd) AS avg_revenue FROM filing_metrics WHERE assets_usd IS NOT NULL AND liabilities_usd IS NOT NULL AND revenue_usd IS NOT NULL GROUP BY fiscal_period", "For each fiscal period, what are the filing count and the average assets, liabilities, and revenue?"),
            q("q11", f"SELECT {INDUSTRY_FAMILY} AS industry_family, COUNT(*) AS filing_count, MIN(revenue_usd) AS min_revenue, MAX(revenue_usd) AS max_revenue, AVG(operating_cash_flow_usd) AS avg_ocf FROM filing_metrics m WHERE revenue_usd IS NOT NULL AND operating_cash_flow_usd IS NOT NULL GROUP BY industry_family", "For each industry family, what are the filing count, lowest and highest revenue, and average operating cash flow?"),
            q("q12", "SELECT c.ticker, COUNT(*) AS filing_count, AVG(m.revenue_usd) AS avg_revenue, AVG(m.net_income_usd) AS avg_net_income, AVG(m.assets_usd) AS avg_assets FROM filing_metrics m JOIN company c ON m.company_id = c.company_id WHERE m.revenue_usd IS NOT NULL AND m.net_income_usd IS NOT NULL AND m.assets_usd IS NOT NULL GROUP BY c.ticker", "After joining companies, what are each issuer's filing count and average revenue, net income, and assets?"),
            q("q13", "SELECT c.state_of_incorporation, COUNT(*) AS filing_count, AVG(m.net_income_usd) AS avg_net_income, SUM(CASE WHEN m.operating_cash_flow_usd > 0 THEN 1 ELSE 0 END) AS positive_ocf_count FROM filing_metrics m JOIN company c ON m.company_id = c.company_id WHERE m.net_income_usd IS NOT NULL AND m.operating_cash_flow_usd IS NOT NULL GROUP BY c.state_of_incorporation", "For companies in each state, what are the filing count, average net income, and number of filings with positive operating cash flow?"),
            q("q14", "SELECT f.fiscal_year, COUNT(DISTINCT c.ticker) AS issuer_count, COUNT(*) AS filing_count, AVG(m.revenue_usd) AS avg_revenue, AVG(m.net_income_usd) AS avg_net_income FROM filing_metrics m JOIN company c ON m.company_id = c.company_id JOIN filing f ON m.filing_id = f.filing_id WHERE f.fiscal_year BETWEEN 2022 AND 2025 AND m.revenue_usd IS NOT NULL AND m.net_income_usd IS NOT NULL GROUP BY f.fiscal_year", "For each fiscal year, how many issuers and filings are there, and what are the average revenue and net income?"),
            q("q15", f"SELECT {CONCEPT_FAMILY} AS concept_family, COUNT(*) AS filing_count, AVG(m.revenue_usd) AS avg_revenue, AVG(m.net_income_usd) AS avg_net_income FROM filing_metrics m JOIN concept con ON m.revenue_usd_concept_id = con.concept_id WHERE m.revenue_usd IS NOT NULL AND m.net_income_usd IS NOT NULL GROUP BY concept_family", "For each revenue-concept family, what are the filing count and the average revenue and net income?"),
            q("q16", "SELECT f.form_type, con.concept_name, COUNT(*) AS filing_count, AVG(m.revenue_usd) AS avg_revenue, MAX(m.revenue_usd) AS max_revenue FROM filing_metrics m JOIN filing f ON m.filing_id = f.filing_id JOIN concept con ON m.revenue_usd_concept_id = con.concept_id WHERE m.revenue_usd IS NOT NULL GROUP BY f.form_type, con.concept_name", "For each form type and revenue concept, what are the filing count and the average and highest revenue?"),
            q("q17", "SELECT c.ticker, f.form_type, COUNT(*) AS filing_count, AVG(m.assets_usd) AS avg_assets, AVG(m.net_income_usd) AS avg_net_income FROM filing_metrics m JOIN company c ON m.company_id = c.company_id JOIN filing f ON m.filing_id = f.filing_id WHERE m.assets_usd IS NOT NULL AND m.net_income_usd IS NOT NULL GROUP BY c.ticker, f.form_type", "For each company and form type, what are the filing count and the average assets and net income?"),
            q("q18", "SELECT fiscal_year, COUNT(*) AS filing_count, SUM(CASE WHEN net_income_usd > 0 THEN 1 ELSE 0 END) AS profitable_count, SUM(CASE WHEN operating_cash_flow_usd > 0 THEN 1 ELSE 0 END) AS positive_ocf_count, AVG(revenue_usd) AS avg_revenue FROM filing_metrics WHERE fiscal_year BETWEEN 2022 AND 2025 AND revenue_usd IS NOT NULL GROUP BY fiscal_year", "For each fiscal year, how many filings are there, how many are profitable, how many have positive operating cash flow, and what is the average revenue?"),
            q("q19", f"SELECT {INDUSTRY_FAMILY} AS industry_family, form_type, COUNT(*) AS filing_count, AVG(m.revenue_usd) AS avg_revenue, AVG(m.net_income_usd) AS avg_net_income FROM filing_metrics m WHERE revenue_usd IS NOT NULL AND net_income_usd IS NOT NULL GROUP BY industry_family, form_type", "For each industry family and form type, what are the filing count and the average revenue and net income?"),
        ],
    },
    "sec_filterjoin20": {
        "title": "Filter-and-join workload",
        "focus": "Selective WHERE predicates with light joins; aggregation stays simple",
        "kind": "pure",
        "contrast_with": BASELINE,
        "queries": [
            q("q0", "SELECT ticker, COUNT(*) AS filing_count FROM filing_metrics WHERE form_type = '10-Q' AND net_income_usd > 0 GROUP BY ticker", "Among profitable quarterly filings, how many are there for each issuer?"),
            q("q1", "SELECT fiscal_year, AVG(revenue_usd) AS avg_revenue FROM filing_metrics WHERE form_type = '10-K' AND revenue_usd >= 50000000000 AND fiscal_year BETWEEN 2022 AND 2025 GROUP BY fiscal_year", "Among annual filings with at least $50 billion in revenue, what is the average revenue in each fiscal year from 2022 through 2025?"),
            q("q2", "SELECT form_type, COUNT(*) AS filing_count FROM filing_metrics WHERE state_of_incorporation = 'DE' AND operating_cash_flow_usd > 0 GROUP BY form_type", "Among Delaware-incorporated issuers with positive operating cash flow, how many filings are 10-Ks versus 10-Qs?"),
            q("q3", f"SELECT {INDUSTRY_FAMILY} AS industry_family, COUNT(*) AS filing_count FROM filing_metrics m WHERE net_income_usd < 0 AND assets_usd >= 100000000000 GROUP BY industry_family", "Among loss-making filings with at least $100 billion in assets, how many come from each industry family?"),
            q("q4", "SELECT fiscal_period, AVG(net_income_usd) AS avg_net_income FROM filing_metrics WHERE revenue_usd >= 100000000000 AND net_income_usd IS NOT NULL GROUP BY fiscal_period", "Among filings with at least $100 billion in revenue, what is the average net income for each fiscal period?"),
            q("q5", "SELECT ticker, COUNT(*) AS filing_count FROM filing_metrics WHERE fiscal_year >= 2023 AND investing_cash_flow_usd < 0 GROUP BY ticker", "Among filings from 2023 onward with negative investing cash flow, how many are there for each issuer?"),
            q("q6", "SELECT state_of_incorporation, COUNT(*) AS filing_count FROM filing_metrics WHERE form_type = '10-Q' AND liabilities_usd >= 200000000000 GROUP BY state_of_incorporation", "Among quarterly filings with at least $200 billion in liabilities, how many come from issuers in each state?"),
            q("q7", "SELECT fiscal_year, COUNT(*) AS filing_count FROM filing_metrics WHERE operating_cash_flow_usd >= 20000000000 AND net_income_usd > 0 AND fiscal_year BETWEEN 2022 AND 2025 GROUP BY fiscal_year", "Among profitable filings with at least $20 billion of operating cash flow, how many are there in each fiscal year from 2022 through 2025?"),
            q("q8", "SELECT c.ticker, AVG(m.revenue_usd) AS avg_revenue FROM filing_metrics m JOIN company c ON m.company_id = c.company_id WHERE m.form_type = '10-K' AND m.revenue_usd IS NOT NULL GROUP BY c.ticker", "Among annual filings, what is the average revenue for each company?"),
            q("q9", "SELECT c.state_of_incorporation, COUNT(*) AS filing_count FROM filing_metrics m JOIN company c ON m.company_id = c.company_id WHERE m.net_income_usd >= 10000000000 GROUP BY c.state_of_incorporation", "Among filings with at least $10 billion in net income, how many come from companies in each state?"),
            q("q10", "SELECT f.fiscal_period, AVG(m.assets_usd) AS avg_assets FROM filing_metrics m JOIN filing f ON m.filing_id = f.filing_id WHERE f.form_type = '10-Q' AND m.assets_usd >= 200000000000 GROUP BY f.fiscal_period", "Among quarterly filings with at least $200 billion in assets, what is the average asset total for each fiscal period?"),
            q("q11", "SELECT f.fiscal_year, COUNT(*) AS filing_count FROM filing_metrics m JOIN filing f ON m.filing_id = f.filing_id WHERE m.financing_cash_flow_usd < 0 AND f.fiscal_year BETWEEN 2022 AND 2025 GROUP BY f.fiscal_year", "Among filings with negative financing cash flow, how many are there in each fiscal year from 2022 through 2025?"),
            q("q12", "SELECT c.ticker, COUNT(*) AS filing_count FROM filing_metrics m JOIN company c ON m.company_id = c.company_id JOIN filing f ON m.filing_id = f.filing_id WHERE f.form_type = '10-Q' AND m.revenue_usd >= 80000000000 GROUP BY c.ticker", "Among quarterly filings with at least $80 billion in revenue, how many are there for each company?"),
            q("q13", "SELECT c.state_of_incorporation, AVG(m.net_income_usd) AS avg_net_income FROM filing_metrics m JOIN company c ON m.company_id = c.company_id JOIN filing f ON m.filing_id = f.filing_id WHERE f.fiscal_year >= 2023 AND m.net_income_usd IS NOT NULL GROUP BY c.state_of_incorporation", "Among filings from 2023 onward, what is the average net income for companies in each state?"),
            q("q14", f"SELECT {CONCEPT_FAMILY} AS concept_family, COUNT(*) AS filing_count FROM filing_metrics m JOIN concept con ON m.revenue_usd_concept_id = con.concept_id WHERE m.form_type = '10-K' AND m.revenue_usd >= 50000000000 GROUP BY concept_family", "Among annual filings with at least $50 billion in revenue, how many use each revenue-concept family?"),
            q("q15", "SELECT f.form_type, AVG(m.operating_cash_flow_usd) AS avg_ocf FROM filing_metrics m JOIN filing f ON m.filing_id = f.filing_id JOIN concept con ON m.revenue_usd_concept_id = con.concept_id WHERE m.net_income_usd > 0 AND m.operating_cash_flow_usd IS NOT NULL GROUP BY f.form_type", "Among profitable filings with a known revenue concept, what is the average operating cash flow for 10-Ks versus 10-Qs?"),
            q("q16", "SELECT c.ticker, COUNT(*) AS filing_count FROM filing_metrics m JOIN company c ON m.company_id = c.company_id JOIN filing f ON m.filing_id = f.filing_id JOIN concept con ON m.revenue_usd_concept_id = con.concept_id WHERE f.fiscal_year BETWEEN 2023 AND 2025 AND m.assets_usd >= 300000000000 GROUP BY c.ticker", "Among 2023–2025 filings with at least $300 billion in assets and a known revenue concept, how many are there for each company?"),
            q("q17", "SELECT f.fiscal_period, COUNT(*) AS filing_count FROM filing_metrics m JOIN company c ON m.company_id = c.company_id JOIN filing f ON m.filing_id = f.filing_id WHERE c.state_of_incorporation = 'DE' AND m.net_income_usd > 0 GROUP BY f.fiscal_period", "Among profitable filings from Delaware companies, how many are there in each fiscal period?"),
            q("q18", f"SELECT {INDUSTRY_FAMILY} AS industry_family, COUNT(*) AS filing_count FROM filing_metrics m JOIN company c ON m.company_id = c.company_id WHERE m.form_type = '10-Q' AND m.revenue_usd BETWEEN 20000000000 AND 200000000000 GROUP BY industry_family", "Among quarterly filings with revenue between $20 billion and $200 billion, how many come from each industry family?"),
            q("q19", "SELECT c.state_of_incorporation, COUNT(*) AS filing_count FROM filing_metrics m JOIN company c ON m.company_id = c.company_id JOIN filing f ON m.filing_id = f.filing_id JOIN concept con ON m.revenue_usd_concept_id = con.concept_id WHERE f.form_type = '10-K' AND m.operating_cash_flow_usd > 0 AND m.net_income_usd > 0 GROUP BY c.state_of_incorporation", "Among profitable annual filings with positive operating cash flow and a known revenue concept, how many come from companies in each state?"),
        ],
    },
}
