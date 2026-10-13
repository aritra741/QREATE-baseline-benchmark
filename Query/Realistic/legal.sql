-- Realistic aggregate questions over Australian federal court judgments (2026-10-12).
-- Q1: How many cases of each type are there?
SELECT case_type, COUNT(*) AS cases FROM legal GROUP BY case_type;
-- Q2: How are the cases of each type decided?
SELECT case_type, verdict, COUNT(*) AS cases FROM legal GROUP BY case_type, verdict;
-- Q3: How many cases did each judge decide?
SELECT judge_name, COUNT(*) AS cases FROM legal GROUP BY judge_name;
-- Q4: How many cases did each judge dismiss?
SELECT judge_name, COUNT(*) AS dismissed FROM legal WHERE verdict = 'Dismissed' GROUP BY judge_name;
-- Q5: How many judgments were given each year?
SELECT judgment_year, COUNT(*) AS cases FROM legal GROUP BY judgment_year;
-- Q6: How many statutes are cited on average, per case type?
SELECT case_type, AVG(legal_basis_num) AS average_statutes FROM legal GROUP BY case_type;
-- Q7: How many cases imposed a fine?
SELECT COUNT(*) AS cases_with_fine FROM legal WHERE fine_amount IS NOT NULL AND fine_amount <> '0';
-- Q8: How are cases against the immigration minister decided?
SELECT verdict, COUNT(*) AS cases FROM legal WHERE defendant LIKE '%Minister for Immigration%' GROUP BY verdict;
-- Q9: How many cases are brought against governments, companies and organizations?
SELECT defendant_current_status, COUNT(*) AS cases FROM legal GROUP BY defendant_current_status;
-- Q10: How many cases did applicants of each nationality bring?
SELECT nationality_for_applicant, COUNT(*) AS cases FROM legal WHERE nationality_for_applicant IS NOT NULL GROUP BY nationality_for_applicant;
-- Q11: How many precedent cases are cited on average, per verdict?
SELECT verdict, AVG(case_number) AS average_precedents FROM legal GROUP BY verdict;
-- Q12: When a company is the plaintiff, how are cases decided?
SELECT verdict, COUNT(*) AS cases FROM legal WHERE plaintiff_current_status = 'Company' GROUP BY verdict;
-- Q13: How many cases concern patent infringement?
SELECT COUNT(*) AS cases FROM legal WHERE charges LIKE '%patent%';
-- Q14: How many cases of each type had evidence provided?
SELECT case_type, SUM(evidence) AS cases_with_evidence FROM legal GROUP BY case_type;
-- Q15: How many cases were heard each year?
SELECT hearing_year, COUNT(*) AS cases FROM legal GROUP BY hearing_year;
