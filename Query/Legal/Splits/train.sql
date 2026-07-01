-- Query 1: train (agg_only) id=agg_only_legal_gen_12
SELECT case_type, MAX(hearing_year) AS max_hearing_year FROM legal GROUP BY case_type;

-- Query 2: train (agg_only) id=agg_only_legal_gen_62
SELECT hearing_year, MIN(judgment_year) AS min_judgment_year FROM legal GROUP BY hearing_year;

-- Query 3: train (agg_only) id=agg_only_legal_gen_64
SELECT judgment_year, COUNT(ID) AS count_cases FROM legal GROUP BY judgment_year;

-- Query 4: train (agg_only) id=agg_only_legal_gen_94
SELECT first_judge, COUNT(ID) AS count_cases FROM legal GROUP BY first_judge;

-- Query 5: train (agg_only) id=agg_only_legal_gen_76
SELECT judgment_year, MAX(hearing_year) AS max_hearing_year FROM legal GROUP BY judgment_year;

-- Query 6: train (agg_only) id=agg_queries_Legal_9
SELECT case_type, COUNT(evidence) AS count_evidence FROM legal GROUP BY case_type;

-- Query 7: train (agg_only) id=agg_only_legal_gen_60
SELECT hearing_year, SUM(judgment_year) AS sum_judgment_year FROM legal GROUP BY hearing_year;

-- Query 8: train (agg_only) id=agg_only_legal_gen_39
SELECT judge_name, SUM(legal_basis_num) AS sum_legal_basis_num FROM legal GROUP BY judge_name;

-- Query 9: train (agg_only) id=agg_only_legal_gen_104
SELECT first_judge, AVG(hearing_year) AS avg_hearing_year FROM legal GROUP BY first_judge;

-- Query 10: train (agg_only) id=agg_only_legal_gen_88
SELECT evidence, MIN(hearing_year) AS min_hearing_year FROM legal GROUP BY evidence;

-- Query 11: train (agg_only) id=agg_only_legal_gen_105
SELECT first_judge, MIN(hearing_year) AS min_hearing_year FROM legal GROUP BY first_judge;

-- Query 12: train (agg_only) id=agg_only_legal_gen_106
SELECT first_judge, MAX(hearing_year) AS max_hearing_year FROM legal GROUP BY first_judge;

-- Query 13: train (agg_only) id=agg_only_legal_gen_45
SELECT judge_name, MIN(hearing_year) AS min_hearing_year FROM legal GROUP BY judge_name;

-- Query 14: train (agg_only) id=agg_only_legal_gen_51
SELECT hearing_year, COUNT(ID) AS count_cases FROM legal GROUP BY hearing_year;

-- Query 15: train (agg_only) id=agg_only_legal_gen_34
SELECT judge_name, COUNT(ID) AS count_cases FROM legal GROUP BY judge_name;

-- Query 16: train (agg_only) id=agg_only_legal_gen_83
SELECT evidence, AVG(legal_basis_num) AS avg_legal_basis_num FROM legal GROUP BY evidence;

-- Query 17: train (agg_only) id=agg_only_legal_gen_6
SELECT case_type, AVG(legal_basis_num) AS avg_legal_basis_num FROM legal GROUP BY case_type;

-- Query 18: train (agg_only) id=agg_only_legal_gen_66
SELECT judgment_year, AVG(fine_amount) AS avg_fine_amount FROM legal GROUP BY judgment_year;

-- Query 19: train (agg_only) id=agg_only_legal_gen_67
SELECT judgment_year, MIN(fine_amount) AS min_fine_amount FROM legal GROUP BY judgment_year;

-- Query 20: train (agg_only) id=agg_only_legal_gen_77
SELECT evidence, COUNT(ID) AS count_cases FROM legal GROUP BY evidence;

-- Query 21: train (agg_filter) id=agg_filter_legal_gen_1208
SELECT judgment_year, AVG(hearing_year) AS avg_hearing_year FROM legal WHERE verdict = 'Dismissed' GROUP BY judgment_year;

-- Query 22: train (agg_filter) id=agg_filter_legal_gen_627
SELECT judge_name, MAX(fine_amount) AS max_fine_amount FROM legal WHERE legal_basis_num > 1 GROUP BY judge_name;

-- Query 23: train (agg_filter) id=agg_filter_legal_gen_1235
SELECT judgment_year, MIN(hearing_year) AS min_hearing_year FROM legal WHERE legal_basis_num > 1 GROUP BY judgment_year;

-- Query 24: train (agg_filter) id=mixed_queries_2
SELECT nationality_for_applicant, MAX(case_number) AS max_case_number FROM legal WHERE defendant_current_status != 'Company' AND legal_basis_num >= 1 GROUP BY nationality_for_applicant;

-- Query 25: train (agg_filter) id=agg_filter_legal_gen_623
SELECT judge_name, MAX(fine_amount) AS max_fine_amount FROM legal WHERE first_judge = 1 GROUP BY judge_name;

-- Query 26: train (agg_filter) id=agg_filter_legal_gen_1621
SELECT first_judge, MIN(legal_basis_num) AS min_legal_basis_num FROM legal WHERE hearing_year >= 2005 GROUP BY first_judge;

-- Query 27: train (agg_filter) id=agg_filter_legal_gen_1519
SELECT first_judge, SUM(fine_amount) AS sum_fine_amount FROM legal WHERE evidence = 1 GROUP BY first_judge;

-- Query 28: train (agg_filter) id=agg_filter_legal_gen_1303
SELECT evidence, MAX(fine_amount) AS max_fine_amount FROM legal WHERE case_type = 'Commercial Case' GROUP BY evidence;

-- Query 29: train (agg_filter) id=mixed_queries_6
SELECT case_type, SUM(legal_basis_num) AS sum_legal_basis_num FROM legal WHERE (judgment_year = 2009 AND plaintiff != 'Telstra Corporation Limited') OR (verdict != 'Others' AND counsel_for_applicant = 'Dr J G Azzi') GROUP BY case_type;

-- Query 30: train (agg_filter) id=mixed_queries_3
SELECT nationality_for_applicant, MAX(legal_basis_num) AS max_legal_basis_num FROM legal WHERE verdict != 'Dismissed' OR first_judge != 0 GROUP BY nationality_for_applicant;

-- Query 31: train (agg_filter) id=agg_filter_legal_gen_363
SELECT verdict, MIN(fine_amount) AS min_fine_amount FROM legal WHERE case_type = 'Commercial Case' GROUP BY verdict;

-- Query 32: train (agg_filter) id=agg_filter_legal_gen_953
SELECT hearing_year, MIN(legal_basis_num) AS min_legal_basis_num FROM legal WHERE verdict = 'Dismissed' GROUP BY hearing_year;

-- Query 33: train (agg_filter) id=agg_filter_legal_gen_1387
SELECT evidence, SUM(hearing_year) AS sum_hearing_year FROM legal WHERE verdict = 'Dismissed' GROUP BY evidence;

-- Query 34: train (agg_filter) id=agg_filter_legal_gen_1225
SELECT judgment_year, MIN(hearing_year) AS min_hearing_year FROM legal WHERE verdict = 'Dismissed' GROUP BY judgment_year;

-- Query 35: train (agg_filter) id=agg_filter_legal_gen_1220
SELECT judgment_year, AVG(hearing_year) AS avg_hearing_year FROM legal WHERE hearing_year >= 2005 GROUP BY judgment_year;

-- Query 36: train (agg_filter) id=mixed_queries_4
SELECT verdict, MIN(legal_basis_num) AS min_legal_basis_num FROM legal WHERE legal_fees = '3265' AND defendant != 'Construction, Forestry, Mining and Energy Union' AND legal_fees != '2000' GROUP BY verdict;

-- Query 37: train (agg_filter) id=agg_filter_legal_gen_657
SELECT judge_name, AVG(legal_basis_num) AS avg_legal_basis_num FROM legal WHERE evidence = 1 GROUP BY judge_name;

-- Query 38: train (agg_filter) id=agg_filter_legal_gen_872
SELECT hearing_year, AVG(fine_amount) AS avg_fine_amount FROM legal WHERE evidence = 1 GROUP BY hearing_year;

-- Query 39: train (agg_filter) id=agg_filter_legal_gen_369
SELECT verdict, MIN(fine_amount) AS min_fine_amount FROM legal WHERE first_judge = 1 GROUP BY verdict;

-- Query 40: train (agg_filter) id=agg_filter_legal_gen_213
SELECT case_type, MAX(legal_basis_num) AS max_legal_basis_num FROM legal WHERE evidence = 1 GROUP BY case_type;
