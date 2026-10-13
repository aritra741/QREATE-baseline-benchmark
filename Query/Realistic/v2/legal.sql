-- Realistic relational questions over Australian federal court judgments, v2 (2026-10-13).
-- Q1: How are the cases of each type decided?
SELECT case_type, verdict, COUNT(*) AS cases FROM legal GROUP BY case_type, verdict;
-- Q2: For judges with at least ten cases: how many cases, how many dismissed, and how many statutes cited on average, busiest first?
SELECT judge_name, COUNT(*) AS cases, SUM(CASE WHEN verdict = 'Dismissed' THEN 1 ELSE 0 END) AS dismissed, AVG(legal_basis_num) AS average_statutes FROM legal GROUP BY judge_name HAVING COUNT(*) >= 10 ORDER BY cases DESC;
-- Q3: Per judgment year: how many cases, what share dismissed, and how many precedents cited on average?
SELECT judgment_year, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate, AVG(case_number) AS average_precedents FROM legal GROUP BY judgment_year;
-- Q4: Per case type: average statutes, average precedents, and how many cases had evidence?
SELECT case_type, AVG(legal_basis_num) AS average_statutes, AVG(case_number) AS average_precedents, SUM(evidence) AS with_evidence FROM legal GROUP BY case_type;
-- Q5: For defendant types with at least five cases: how many cases, and how many were approved?
SELECT defendant_current_status, COUNT(*) AS cases, SUM(CASE WHEN verdict = 'Approved' THEN 1 ELSE 0 END) AS approved FROM legal WHERE defendant_current_status <> '' GROUP BY defendant_current_status HAVING COUNT(*) >= 5;
-- Q6: Which ten applicant nationalities bring the most cases, and how many of their cases are dismissed?
SELECT nationality_for_applicant, COUNT(*) AS cases, SUM(CASE WHEN verdict = 'Dismissed' THEN 1 ELSE 0 END) AS dismissed FROM legal WHERE nationality_for_applicant IS NOT NULL GROUP BY nationality_for_applicant ORDER BY cases DESC LIMIT 10;
-- Q7: Per verdict: how many statutes and precedents are cited on average?
SELECT verdict, AVG(legal_basis_num) AS average_statutes, AVG(case_number) AS average_precedents FROM legal GROUP BY verdict;
-- Q8: When a company, an organization or a government is the plaintiff, how are cases decided?
SELECT plaintiff_current_status, verdict, COUNT(*) AS cases FROM legal WHERE plaintiff_current_status IN ('Company', 'Organization', 'Government') GROUP BY plaintiff_current_status, verdict;
-- Q9: How many cases of each type were decided each year?
SELECT judgment_year, case_type, COUNT(*) AS cases FROM legal GROUP BY judgment_year, case_type;
-- Q10: Which judges with at least five cases dismissed more than 70% of them?
SELECT judge_name, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate FROM legal GROUP BY judge_name HAVING COUNT(*) >= 5 AND AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) > 0.7;
-- Q11: Per case type, how many years pass on average between hearing and judgment?
SELECT case_type, AVG(CAST(judgment_year AS INTEGER) - CAST(hearing_year AS INTEGER)) AS average_years_to_judgment FROM legal GROUP BY case_type;
-- Q12: Per case type, how many cases cite more statutes than the average case?
SELECT case_type, COUNT(*) AS cases FROM legal WHERE legal_basis_num > (SELECT AVG(legal_basis_num) FROM legal) GROUP BY case_type;
-- Q13: For defendant types fined at least twice, how large is the average fine?
SELECT defendant_current_status, COUNT(*) AS fined_cases, AVG(CAST(fine_amount AS REAL)) AS average_fine FROM legal WHERE fine_amount IS NOT NULL AND fine_amount <> '0' AND defendant_current_status <> '' GROUP BY defendant_current_status HAVING COUNT(*) >= 2;
-- Q14: How are patent, copyright and trade mark cases decided?
SELECT CASE WHEN charges LIKE '%patent%' THEN 'patent' WHEN charges LIKE '%copyright%' THEN 'copyright' WHEN charges LIKE '%trade mark%' OR charges LIKE '%trademark%' THEN 'trade mark' ELSE 'other' END AS area, verdict, COUNT(*) AS cases FROM legal GROUP BY area, verdict;
-- Q15: How many cases concern patent infringement?
SELECT COUNT(*) AS cases FROM legal WHERE charges LIKE '%patent%';
