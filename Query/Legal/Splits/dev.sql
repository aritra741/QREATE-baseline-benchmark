-- Query 1: dev (agg_only) id=agg_only_legal_gen_93
SELECT evidence, MAX(judgment_year) AS max_judgment_year FROM legal GROUP BY evidence;

-- Query 2: dev (agg_only) id=agg_only_legal_gen_38
SELECT judge_name, MAX(fine_amount) AS max_fine_amount FROM legal GROUP BY judge_name;

-- Query 3: dev (agg_only) id=agg_only_legal_gen_53
SELECT hearing_year, AVG(fine_amount) AS avg_fine_amount FROM legal GROUP BY hearing_year;

-- Query 4: dev (agg_only) id=agg_only_legal_gen_9
SELECT case_type, SUM(hearing_year) AS sum_hearing_year FROM legal GROUP BY case_type;

-- Query 5: dev (agg_only) id=agg_only_legal_gen_3
SELECT case_type, MIN(fine_amount) AS min_fine_amount FROM legal GROUP BY case_type;

-- Query 6: dev (agg_filter) id=agg_filter_legal_gen_1263
SELECT evidence, SUM(fine_amount) AS sum_fine_amount FROM legal WHERE first_judge = 1 GROUP BY evidence;

-- Query 7: dev (agg_filter) id=agg_filter_legal_gen_1750
SELECT first_judge, MIN(judgment_year) AS min_judgment_year FROM legal WHERE judgment_year >= 2005 GROUP BY first_judge;

-- Query 8: dev (agg_filter) id=agg_filter_legal_gen_377
SELECT verdict, MAX(fine_amount) AS max_fine_amount FROM legal WHERE case_type = 'Commercial Case' GROUP BY verdict;

-- Query 9: dev (agg_filter) id=agg_filter_legal_gen_1493
SELECT evidence, MIN(judgment_year) AS min_judgment_year FROM legal WHERE hearing_year >= 2005 GROUP BY evidence;

-- Query 10: dev (agg_filter) id=agg_filter_legal_gen_1599
SELECT first_judge, AVG(legal_basis_num) AS avg_legal_basis_num FROM legal WHERE evidence = 1 GROUP BY first_judge;
