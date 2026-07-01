-- Query 1: test (agg_only) id=agg_only_legal_gen_107
SELECT first_judge, SUM(judgment_year) AS sum_judgment_year FROM legal GROUP BY first_judge;

-- Query 2: test (agg_only) id=agg_only_legal_gen_69
SELECT judgment_year, SUM(legal_basis_num) AS sum_legal_basis_num FROM legal GROUP BY judgment_year;

-- Query 3: test (agg_only) id=agg_only_legal_gen_86
SELECT evidence, SUM(hearing_year) AS sum_hearing_year FROM legal GROUP BY evidence;

-- Query 4: test (agg_only) id=agg_only_legal_gen_55
SELECT hearing_year, MAX(fine_amount) AS max_fine_amount FROM legal GROUP BY hearing_year;

-- Query 5: test (agg_only) id=agg_only_legal_gen_44
SELECT judge_name, AVG(hearing_year) AS avg_hearing_year FROM legal GROUP BY judge_name;

-- Query 6: test (agg_filter) id=agg_filter_legal_gen_1339
SELECT evidence, AVG(legal_basis_num) AS avg_legal_basis_num FROM legal WHERE verdict = 'Dismissed' GROUP BY evidence;

-- Query 7: test (agg_filter) id=agg_filter_legal_gen_1727
SELECT first_judge, AVG(judgment_year) AS avg_judgment_year FROM legal WHERE evidence = 1 GROUP BY first_judge;

-- Query 8: test (agg_filter) id=mixed_queries_5
SELECT nationality_for_applicant, MAX(case_number) AS max_case_number FROM legal WHERE first_judge != 0 OR evidence < 1 OR defendant = 'Secretary, Department of Employment and Workplace Relations' GROUP BY nationality_for_applicant;

-- Query 9: test (agg_filter) id=agg_filter_legal_gen_1135
SELECT judgment_year, SUM(legal_basis_num) AS sum_legal_basis_num FROM legal WHERE hearing_year >= 2005 GROUP BY judgment_year;

-- Query 10: test (agg_filter) id=agg_filter_legal_gen_1014
SELECT hearing_year, AVG(judgment_year) AS avg_judgment_year FROM legal WHERE legal_basis_num > 1 GROUP BY hearing_year;
