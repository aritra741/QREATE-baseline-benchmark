"""Legal contrast workloads: realistic legal-research questions on Australian Federal Court cases."""

from .common import q

DATASET = "Legal"
JOIN_NOTES = None
BASELINE = "legal_agg20"

CASE_FAMILY = """
CASE
  WHEN case_type IN ('Administrative Case', 'Civil Case', 'Commercial Case') THEN case_type
  ELSE 'Other'
END
""".strip()

VERDICT_FAMILY = """
CASE
  WHEN verdict IN ('Dismissed', 'Approved', 'Others') THEN verdict
  ELSE 'Other'
END
""".strip()

NATION_FAMILY = """
CASE
  WHEN nationality_for_applicant IN ('Australia', 'China', 'India', 'Bangladesh') THEN nationality_for_applicant
  WHEN nationality_for_applicant != '' THEN 'Other'
END
""".strip()

PLAINTIFF_FAMILY = """
CASE
  WHEN plaintiff_current_status IN ('Company', 'Organization', 'Government') THEN plaintiff_current_status
  WHEN plaintiff_current_status != '' THEN 'Individual_or_other'
END
""".strip()

DEFENDANT_FAMILY = """
CASE
  WHEN defendant_current_status IN ('Government', 'Company', 'Organization') THEN defendant_current_status
  WHEN defendant_current_status != '' THEN 'Other'
END
""".strip()

WORKLOADS = {
    "legal_agg20": {
        "title": "Simple aggregation workload",
        "focus": "Single-table GROUP BY with one aggregate",
        "kind": "baseline",
        "queries": [
            q("q0", f"SELECT {CASE_FAMILY} AS case_family, COUNT(*) AS case_count FROM legal GROUP BY case_family", "How many cases fall into each major case type?"),
            q("q1", f"SELECT {VERDICT_FAMILY} AS verdict_family, COUNT(*) AS case_count FROM legal GROUP BY verdict_family", "How many cases received each major verdict?"),
            q("q2", "SELECT judgment_year, COUNT(*) AS case_count FROM legal WHERE judgment_year BETWEEN 2006 AND 2009 GROUP BY judgment_year", "How many cases were decided in each year from 2006 through 2009?"),
            q("q3", "SELECT hearing_year, COUNT(*) AS case_count FROM legal WHERE hearing_year BETWEEN 2005 AND 2009 GROUP BY hearing_year", "How many cases were heard in each year from 2005 through 2009?"),
            q("q4", "SELECT first_judge, COUNT(*) AS case_count FROM legal WHERE first_judge IS NOT NULL GROUP BY first_judge", "How many cases are recorded as a first judgment versus not?"),
            q("q5", "SELECT evidence, COUNT(*) AS case_count FROM legal WHERE evidence IS NOT NULL GROUP BY evidence", "How many cases have recorded evidence versus none?"),
            q("q6", f"SELECT {NATION_FAMILY} AS applicant_nation, COUNT(*) AS case_count FROM legal WHERE nationality_for_applicant != '' GROUP BY applicant_nation", "Among cases with a known applicant nationality, how many involve Australian, Chinese, Indian, Bangladeshi, or other applicants?"),
            q("q7", f"SELECT {DEFENDANT_FAMILY} AS defendant_family, COUNT(*) AS case_count FROM legal WHERE defendant_current_status != '' GROUP BY defendant_family", "How many cases have a government, company, organization, or other defendant?"),
            q("q8", f"SELECT {CASE_FAMILY} AS case_family, AVG(legal_basis_num) AS avg_statutes FROM legal GROUP BY case_family", "What is the average number of statutes cited in each major case type?"),
            q("q9", f"SELECT {VERDICT_FAMILY} AS verdict_family, AVG(case_number) AS avg_precedents FROM legal WHERE case_number IS NOT NULL GROUP BY verdict_family", "What is the average number of cited precedents for each major verdict?"),
            q("q10", "SELECT judgment_year, AVG(legal_basis_num) AS avg_statutes FROM legal WHERE judgment_year BETWEEN 2006 AND 2009 GROUP BY judgment_year", "What is the average number of statutes cited in each judgment year?"),
            q("q11", f"SELECT {PLAINTIFF_FAMILY} AS plaintiff_family, COUNT(*) AS case_count FROM legal WHERE plaintiff_current_status != '' GROUP BY plaintiff_family", "How many cases have a company, organization, government, or individual plaintiff?"),
            q("q12", "SELECT judge_name, COUNT(*) AS case_count FROM legal WHERE judge_name != '' GROUP BY judge_name HAVING COUNT(*) >= 10", "Which judges decided at least ten cases, and how many cases did each decide?"),
            q("q13", f"SELECT {CASE_FAMILY} AS case_family, MAX(case_number) AS max_precedents FROM legal WHERE case_number IS NOT NULL GROUP BY case_family", "What is the largest number of cited precedents in each major case type?"),
            q("q14", "SELECT first_judge, AVG(legal_basis_num) AS avg_statutes FROM legal WHERE first_judge IS NOT NULL GROUP BY first_judge", "What is the average number of statutes cited in first judgments versus later judgments?"),
            q("q15", f"SELECT {NATION_FAMILY} AS applicant_nation, AVG(case_number) AS avg_precedents FROM legal WHERE nationality_for_applicant != '' AND case_number IS NOT NULL GROUP BY applicant_nation", "Among cases with a known applicant nationality, what is the average number of cited precedents for each nationality group?"),
            q("q16", "SELECT CASE WHEN legal_basis_num = 0 THEN 'none' WHEN legal_basis_num = 1 THEN 'one' WHEN legal_basis_num <= 3 THEN 'two_or_three' ELSE 'four_or_more' END AS statute_band, COUNT(*) AS case_count FROM legal GROUP BY statute_band", "How many cases cite no statutes, one statute, two or three, or four or more?"),
            q("q17", f"SELECT {DEFENDANT_FAMILY} AS defendant_family, AVG(legal_basis_num) AS avg_statutes FROM legal WHERE defendant_current_status != '' GROUP BY defendant_family", "What is the average number of statutes cited when the defendant is a government, company, organization, or other party?"),
            q("q18", "SELECT evidence, AVG(case_number) AS avg_precedents FROM legal WHERE evidence IS NOT NULL AND case_number IS NOT NULL GROUP BY evidence", "What is the average number of cited precedents in cases with recorded evidence versus without?"),
            q("q19", "SELECT judgment_year, MAX(legal_basis_num) AS max_statutes FROM legal WHERE judgment_year BETWEEN 2006 AND 2009 GROUP BY judgment_year", "What is the largest number of statutes cited in a case from each judgment year?"),
        ],
    },
    "legal_filter20": {
        "title": "Selective-filter workload",
        "focus": "Selective WHERE predicates with simple aggregates",
        "kind": "pure",
        "contrast_with": BASELINE,
        "queries": [
            q("q0", "SELECT evidence, COUNT(*) AS case_count FROM legal WHERE case_type = 'Administrative Case' AND verdict = 'Dismissed' AND judgment_year BETWEEN 2007 AND 2008 GROUP BY evidence", "Among administrative cases dismissed in 2007 or 2008, how many have recorded evidence versus none?"),
            q("q1", f"SELECT {VERDICT_FAMILY} AS verdict_family, AVG(legal_basis_num) AS avg_statutes FROM legal WHERE case_type = 'Commercial Case' AND case_number >= 3 GROUP BY verdict_family", "Among commercial cases that cite at least three precedents, what is the average number of statutes for each major verdict?"),
            q("q2", f"SELECT {CASE_FAMILY} AS case_family, COUNT(*) AS case_count FROM legal WHERE nationality_for_applicant IN ('Australia', 'China', 'India') GROUP BY case_family", "Among cases whose applicant is from Australia, China, or India, how many fall into each major case type?"),
            q("q3", "SELECT first_judge, COUNT(*) AS case_count FROM legal WHERE case_type = 'Civil Case' AND judgment_year BETWEEN 2006 AND 2008 GROUP BY first_judge", "Among civil cases decided from 2006 through 2008, how many are recorded as a first judgment versus not?"),
            q("q4", f"SELECT {NATION_FAMILY} AS applicant_nation, COUNT(*) AS case_count FROM legal WHERE case_type = 'Administrative Case' AND verdict = 'Dismissed' AND nationality_for_applicant != '' GROUP BY applicant_nation", "Among dismissed administrative cases with a known applicant nationality, how many involve each nationality group?"),
            q("q5", f"SELECT {DEFENDANT_FAMILY} AS defendant_family, COUNT(*) AS case_count FROM legal WHERE legal_basis_num >= 3 AND defendant_current_status != '' GROUP BY defendant_family", "Among cases that cite at least three statutes, how many have each kind of defendant?"),
            q("q6", "SELECT judgment_year, COUNT(*) AS case_count FROM legal WHERE first_judge = 1 AND evidence = 1 AND judgment_year BETWEEN 2006 AND 2009 GROUP BY judgment_year", "Among first judgments with recorded evidence, how many were decided in each year from 2006 through 2009?"),
            q("q7", f"SELECT {VERDICT_FAMILY} AS verdict_family, AVG(case_number) AS avg_precedents FROM legal WHERE hearing_year BETWEEN 2006 AND 2008 AND case_number IS NOT NULL GROUP BY verdict_family", "Among cases heard from 2006 through 2008, what is the average number of cited precedents for each major verdict?"),
            q("q8", "SELECT CASE WHEN case_number >= 10 THEN 'many_precedents' ELSE 'fewer_precedents' END AS precedent_band, COUNT(*) AS case_count FROM legal WHERE case_type = 'Civil Case' AND case_number IS NOT NULL GROUP BY precedent_band", "Among civil cases, how many cite ten or more precedents versus fewer?"),
            q("q9", f"SELECT {PLAINTIFF_FAMILY} AS plaintiff_family, COUNT(*) AS case_count FROM legal WHERE verdict = 'Approved' AND plaintiff_current_status != '' GROUP BY plaintiff_family", "Among approved cases, how many have each kind of plaintiff?"),
            q("q10", "SELECT judge_name, COUNT(*) AS case_count FROM legal WHERE case_type = 'Administrative Case' AND verdict = 'Dismissed' GROUP BY judge_name HAVING COUNT(*) >= 5", "Which judges dismissed at least five administrative cases, and how many did each dismiss?"),
            q("q11", f"SELECT {CASE_FAMILY} AS case_family, AVG(legal_basis_num) AS avg_statutes FROM legal WHERE defendant_current_status = 'Government' GROUP BY case_family", "Among cases against a government defendant, what is the average number of statutes cited for each major case type?"),
            q("q12", "SELECT evidence, COUNT(*) AS case_count FROM legal WHERE legal_basis_num BETWEEN 2 AND 5 AND case_number >= 4 GROUP BY evidence", "Among cases that cite two to five statutes and at least four precedents, how many have recorded evidence?"),
            q("q13", f"SELECT {NATION_FAMILY} AS applicant_nation, AVG(legal_basis_num) AS avg_statutes FROM legal WHERE case_type = 'Administrative Case' AND nationality_for_applicant != '' GROUP BY applicant_nation", "Among administrative cases with a known applicant nationality, what is the average number of statutes cited for each nationality group?"),
            q("q14", "SELECT judgment_year, COUNT(*) AS case_count FROM legal WHERE case_type = 'Commercial Case' AND legal_basis_num >= 2 AND judgment_year BETWEEN 2006 AND 2009 GROUP BY judgment_year", "Among commercial cases that cite at least two statutes, how many were decided in each year from 2006 through 2009?"),
            q("q15", f"SELECT {VERDICT_FAMILY} AS verdict_family, COUNT(*) AS case_count FROM legal WHERE plaintiff_current_status = 'Company' AND defendant_current_status IN ('Company', 'Organization', 'Government') GROUP BY verdict_family", "Among cases brought by a company against a company, organization, or government, how many received each major verdict?"),
            q("q16", "SELECT first_judge, AVG(case_number) AS avg_precedents FROM legal WHERE hearing_year >= 2007 AND hearing_year <= 2009 AND case_number IS NOT NULL GROUP BY first_judge", "Among cases heard from 2007 through 2009, what is the average number of cited precedents in first judgments versus later judgments?"),
            q("q17", f"SELECT {DEFENDANT_FAMILY} AS defendant_family, COUNT(*) AS case_count FROM legal WHERE verdict IN ('Approved', 'Others') AND defendant_current_status != '' GROUP BY defendant_family", "Among cases that were approved or received another non-dismissal verdict, how many have each kind of defendant?"),
            q("q18", "SELECT CASE WHEN legal_basis_num >= 4 THEN 'statute_heavy' ELSE 'statute_light' END AS statute_band, COUNT(*) AS case_count FROM legal WHERE case_type IN ('Civil Case', 'Commercial Case') GROUP BY statute_band", "Among civil and commercial cases, how many cite four or more statutes versus fewer?"),
            q("q19", f"SELECT {CASE_FAMILY} AS case_family, COUNT(*) AS case_count FROM legal WHERE evidence = 0 AND first_judge = 1 GROUP BY case_family", "Among first judgments with no recorded evidence, how many fall into each major case type?"),
        ],
    },
    "legal_groupby20": {
        "title": "Group-by variety workload",
        "focus": "Diverse GROUP BY keys, including multi-column and banded groupings",
        "kind": "pure",
        "contrast_with": BASELINE,
        "queries": [
            q("q0", f"SELECT {CASE_FAMILY} AS case_family, {VERDICT_FAMILY} AS verdict_family, COUNT(*) AS case_count FROM legal GROUP BY case_family, verdict_family", "For each major case type, how many cases received each major verdict?"),
            q("q1", "SELECT judgment_year, first_judge, COUNT(*) AS case_count FROM legal WHERE judgment_year BETWEEN 2006 AND 2009 AND first_judge IS NOT NULL GROUP BY judgment_year, first_judge", "For each judgment year, how many cases are recorded as a first judgment versus not?"),
            q("q2", f"SELECT {CASE_FAMILY} AS case_family, evidence, COUNT(*) AS case_count FROM legal WHERE evidence IS NOT NULL GROUP BY case_family, evidence", "For each major case type, how many cases have recorded evidence versus none?"),
            q("q3", f"SELECT {NATION_FAMILY} AS applicant_nation, {CASE_FAMILY} AS case_family, COUNT(*) AS case_count FROM legal WHERE nationality_for_applicant != '' GROUP BY applicant_nation, case_family", "For each applicant-nationality group, how many cases fall into each major case type?"),
            q("q4", "SELECT CASE WHEN case_number = 0 THEN 'none' WHEN case_number <= 4 THEN '1_to_4' ELSE '5_or_more' END AS precedent_band, case_type, COUNT(*) AS case_count FROM legal WHERE case_type IN ('Administrative Case', 'Civil Case', 'Commercial Case') AND case_number IS NOT NULL GROUP BY precedent_band, case_type", "For cases with no, 1–4, or 5 or more precedents, how many are administrative, civil, or commercial?"),
            q("q5", f"SELECT {DEFENDANT_FAMILY} AS defendant_family, {VERDICT_FAMILY} AS verdict_family, COUNT(*) AS case_count FROM legal WHERE defendant_current_status != '' GROUP BY defendant_family, verdict_family", "For each kind of defendant, how many cases received each major verdict?"),
            q("q6", "SELECT hearing_year, CASE WHEN legal_basis_num <= 1 THEN '0_or_1' WHEN legal_basis_num <= 3 THEN '2_or_3' ELSE '4_or_more' END AS statute_band, COUNT(*) AS case_count FROM legal WHERE hearing_year BETWEEN 2006 AND 2009 GROUP BY hearing_year, statute_band", "For each hearing year from 2006 through 2009, how many cases cite 0–1, 2–3, or 4 or more statutes?"),
            q("q7", f"SELECT {PLAINTIFF_FAMILY} AS plaintiff_family, {DEFENDANT_FAMILY} AS defendant_family, COUNT(*) AS case_count FROM legal WHERE plaintiff_current_status != '' AND defendant_current_status != '' GROUP BY plaintiff_family, defendant_family", "For each plaintiff and defendant pairing, how many cases are there?"),
            q("q8", "SELECT judgment_year, CASE WHEN verdict = 'Dismissed' THEN 'Dismissed' ELSE 'not_dismissed' END AS dismissal_status, COUNT(*) AS case_count FROM legal WHERE judgment_year BETWEEN 2006 AND 2009 GROUP BY judgment_year, dismissal_status", "For each judgment year, how many cases were dismissed versus not dismissed?"),
            q("q9", f"SELECT {CASE_FAMILY} AS case_family, first_judge, COUNT(*) AS case_count FROM legal WHERE first_judge IS NOT NULL GROUP BY case_family, first_judge", "For each major case type, how many cases are recorded as a first judgment versus not?"),
            q("q10", f"SELECT {NATION_FAMILY} AS applicant_nation, {VERDICT_FAMILY} AS verdict_family, COUNT(*) AS case_count FROM legal WHERE nationality_for_applicant != '' GROUP BY applicant_nation, verdict_family", "For each applicant-nationality group, how many cases received each major verdict?"),
            q("q11", "SELECT evidence, first_judge, COUNT(*) AS case_count FROM legal WHERE evidence IS NOT NULL AND first_judge IS NOT NULL GROUP BY evidence, first_judge", "For cases with and without recorded evidence, how many are recorded as a first judgment versus not?"),
            q("q12", f"SELECT {DEFENDANT_FAMILY} AS defendant_family, CASE WHEN legal_basis_num >= 3 THEN 'statute_heavy' ELSE 'statute_light' END AS statute_band, COUNT(*) AS case_count FROM legal WHERE defendant_current_status != '' GROUP BY defendant_family, statute_band", "For each kind of defendant, how many cases cite three or more statutes versus fewer?"),
            q("q13", "SELECT judge_name, CASE WHEN verdict = 'Dismissed' THEN 'Dismissed' ELSE 'not_dismissed' END AS dismissal_status, COUNT(*) AS case_count FROM legal WHERE judge_name IN ('Flick', 'Tracey', 'Greenwood', 'Marshall', 'Moore', 'Heerey') GROUP BY judge_name, dismissal_status", "For the most frequent judges, how many of their cases were dismissed versus not dismissed?"),
            q("q14", f"SELECT {CASE_FAMILY} AS case_family, CASE WHEN case_number >= 8 THEN 'precedent_heavy' ELSE 'precedent_light' END AS precedent_band, COUNT(*) AS case_count FROM legal WHERE case_number IS NOT NULL GROUP BY case_family, precedent_band", "For each major case type, how many cases cite eight or more precedents versus fewer?"),
            q("q15", "SELECT hearing_year, judgment_year, COUNT(*) AS case_count FROM legal WHERE hearing_year BETWEEN 2006 AND 2009 AND judgment_year BETWEEN 2006 AND 2009 GROUP BY hearing_year, judgment_year", "For each hearing year and judgment year from 2006 through 2009, how many cases are there?"),
            q("q16", f"SELECT {PLAINTIFF_FAMILY} AS plaintiff_family, {VERDICT_FAMILY} AS verdict_family, COUNT(*) AS case_count FROM legal WHERE plaintiff_current_status != '' GROUP BY plaintiff_family, verdict_family", "For each kind of plaintiff, how many cases received each major verdict?"),
            q("q17", "SELECT CASE WHEN legal_basis_num = 0 THEN 'none' WHEN legal_basis_num <= 2 THEN '1_or_2' ELSE '3_or_more' END AS statute_band, CASE WHEN case_number = 0 THEN 'no_precedents' ELSE 'has_precedents' END AS precedent_status, COUNT(*) AS case_count FROM legal WHERE case_number IS NOT NULL GROUP BY statute_band, precedent_status", "For cases citing no, 1–2, or 3 or more statutes, how many also cite precedents versus none?"),
            q("q18", f"SELECT {NATION_FAMILY} AS applicant_nation, evidence, COUNT(*) AS case_count FROM legal WHERE nationality_for_applicant != '' AND evidence IS NOT NULL GROUP BY applicant_nation, evidence", "For each applicant-nationality group, how many cases have recorded evidence versus none?"),
            q("q19", "SELECT judgment_year, CASE WHEN case_type = 'Administrative Case' THEN 'Administrative' ELSE 'non_administrative' END AS case_group, COUNT(*) AS case_count FROM legal WHERE judgment_year BETWEEN 2006 AND 2009 GROUP BY judgment_year, case_group", "For each judgment year, how many cases are administrative versus not?"),
        ],
    },
    "legal_multiagg20": {
        "title": "Multi-aggregation workload",
        "focus": "Several aggregates, often with HAVING, in the same query",
        "kind": "pure",
        "contrast_with": BASELINE,
        "queries": [
            q("q0", f"SELECT {CASE_FAMILY} AS case_family, COUNT(*) AS case_count, AVG(legal_basis_num) AS avg_statutes, AVG(case_number) AS avg_precedents FROM legal WHERE case_number IS NOT NULL GROUP BY case_family", "For each major case type, what are the case count and the average number of statutes and precedents?"),
            q("q1", f"SELECT {VERDICT_FAMILY} AS verdict_family, COUNT(*) AS case_count, AVG(legal_basis_num) AS avg_statutes, MAX(case_number) AS max_precedents FROM legal WHERE case_number IS NOT NULL GROUP BY verdict_family", "For each major verdict, what are the case count, average statutes, and highest precedent count?"),
            q("q2", "SELECT judgment_year, COUNT(*) AS case_count, AVG(legal_basis_num) AS avg_statutes, AVG(case_number) AS avg_precedents, SUM(CASE WHEN evidence = 1 THEN 1 ELSE 0 END) AS evidence_count FROM legal WHERE judgment_year BETWEEN 2006 AND 2009 AND case_number IS NOT NULL GROUP BY judgment_year", "For each judgment year, what are the case count, average statutes and precedents, and number of cases with recorded evidence?"),
            q("q3", f"SELECT {NATION_FAMILY} AS applicant_nation, COUNT(*) AS case_count, AVG(legal_basis_num) AS avg_statutes, AVG(case_number) AS avg_precedents FROM legal WHERE nationality_for_applicant != '' AND case_number IS NOT NULL GROUP BY applicant_nation", "For each applicant-nationality group, what are the case count and the average number of statutes and precedents?"),
            q("q4", "SELECT first_judge, COUNT(*) AS case_count, AVG(legal_basis_num) AS avg_statutes, AVG(case_number) AS avg_precedents, SUM(CASE WHEN verdict = 'Dismissed' THEN 1 ELSE 0 END) AS dismissed_count FROM legal WHERE first_judge IS NOT NULL AND case_number IS NOT NULL GROUP BY first_judge", "For first judgments versus later judgments, what are the count, average statutes and precedents, and number of dismissals?"),
            q("q5", f"SELECT {DEFENDANT_FAMILY} AS defendant_family, COUNT(*) AS case_count, AVG(legal_basis_num) AS avg_statutes, MAX(legal_basis_num) AS max_statutes FROM legal WHERE defendant_current_status != '' GROUP BY defendant_family", "For each kind of defendant, what are the case count and the average and maximum number of statutes cited?"),
            q("q6", "SELECT judge_name, COUNT(*) AS case_count, AVG(legal_basis_num) AS avg_statutes, AVG(case_number) AS avg_precedents FROM legal WHERE judge_name != '' AND case_number IS NOT NULL GROUP BY judge_name HAVING COUNT(*) >= 10", "Among judges with at least ten cases, what are the case count and the average number of statutes and precedents?"),
            q("q7", f"SELECT {PLAINTIFF_FAMILY} AS plaintiff_family, COUNT(*) AS case_count, AVG(case_number) AS avg_precedents, SUM(CASE WHEN verdict = 'Approved' THEN 1 ELSE 0 END) AS approved_count FROM legal WHERE plaintiff_current_status != '' AND case_number IS NOT NULL GROUP BY plaintiff_family", "For each kind of plaintiff, what are the case count, average precedents, and number of approved cases?"),
            q("q8", "SELECT evidence, COUNT(*) AS case_count, AVG(legal_basis_num) AS avg_statutes, AVG(case_number) AS avg_precedents, MAX(case_number) AS max_precedents FROM legal WHERE evidence IS NOT NULL AND case_number IS NOT NULL GROUP BY evidence", "For cases with and without recorded evidence, what are the count, average statutes, and average and maximum precedents?"),
            q("q9", f"SELECT {CASE_FAMILY} AS case_family, {VERDICT_FAMILY} AS verdict_family, COUNT(*) AS case_count, AVG(legal_basis_num) AS avg_statutes, AVG(case_number) AS avg_precedents FROM legal WHERE case_number IS NOT NULL GROUP BY case_family, verdict_family HAVING COUNT(*) >= 5", "For case-type and verdict combinations with at least five cases, what are the count and the average statutes and precedents?"),
            q("q10", "SELECT hearing_year, COUNT(*) AS case_count, MIN(legal_basis_num) AS min_statutes, MAX(legal_basis_num) AS max_statutes, AVG(case_number) AS avg_precedents FROM legal WHERE hearing_year BETWEEN 2006 AND 2009 AND case_number IS NOT NULL GROUP BY hearing_year", "For each hearing year from 2006 through 2009, what are the case count, lowest and highest statute counts, and average precedents?"),
            q("q11", "SELECT CASE WHEN legal_basis_num <= 1 THEN '0_or_1' WHEN legal_basis_num <= 3 THEN '2_or_3' ELSE '4_or_more' END AS statute_band, COUNT(*) AS case_count, AVG(case_number) AS avg_precedents, SUM(CASE WHEN verdict = 'Dismissed' THEN 1 ELSE 0 END) AS dismissed_count FROM legal WHERE case_number IS NOT NULL GROUP BY statute_band", "For each statute-count band, what are the case count, average precedents, and number of dismissals?"),
            q("q12", f"SELECT {NATION_FAMILY} AS applicant_nation, COUNT(*) AS case_count, SUM(CASE WHEN verdict = 'Dismissed' THEN 1 ELSE 0 END) AS dismissed_count, AVG(legal_basis_num) AS avg_statutes FROM legal WHERE nationality_for_applicant != '' GROUP BY applicant_nation", "For each applicant-nationality group, what are the case count, number of dismissals, and average statutes cited?"),
            q("q13", f"SELECT {DEFENDANT_FAMILY} AS defendant_family, COUNT(*) AS case_count, AVG(case_number) AS avg_precedents, SUM(CASE WHEN evidence = 1 THEN 1 ELSE 0 END) AS evidence_count FROM legal WHERE defendant_current_status != '' AND case_number IS NOT NULL GROUP BY defendant_family", "For each kind of defendant, what are the case count, average precedents, and number of cases with recorded evidence?"),
            q("q14", "SELECT judgment_year, first_judge, COUNT(*) AS case_count, AVG(legal_basis_num) AS avg_statutes, AVG(case_number) AS avg_precedents FROM legal WHERE judgment_year BETWEEN 2006 AND 2009 AND first_judge IS NOT NULL AND case_number IS NOT NULL GROUP BY judgment_year, first_judge", "For each judgment year, what are the case count and the average statutes and precedents for first judgments versus later judgments?"),
            q("q15", "SELECT CASE WHEN case_number = 0 THEN 'none' WHEN case_number <= 4 THEN '1_to_4' ELSE '5_or_more' END AS precedent_band, COUNT(*) AS case_count, AVG(legal_basis_num) AS avg_statutes, SUM(CASE WHEN first_judge = 1 THEN 1 ELSE 0 END) AS first_judge_count FROM legal WHERE case_number IS NOT NULL GROUP BY precedent_band", "For each precedent-count band, what are the case count, average statutes, and number of first judgments?"),
            q("q16", f"SELECT {CASE_FAMILY} AS case_family, COUNT(*) AS case_count, SUM(CASE WHEN verdict = 'Dismissed' THEN 1 ELSE 0 END) AS dismissed_count, SUM(CASE WHEN evidence = 1 THEN 1 ELSE 0 END) AS evidence_count, AVG(legal_basis_num) AS avg_statutes FROM legal GROUP BY case_family", "For each major case type, how many cases are there, how many were dismissed, how many have evidence, and what is the average statute count?"),
            q("q17", "SELECT judge_name, COUNT(*) AS case_count, SUM(CASE WHEN verdict = 'Dismissed' THEN 1 ELSE 0 END) AS dismissed_count, AVG(case_number) AS avg_precedents FROM legal WHERE judge_name IN ('Flick', 'Tracey', 'Greenwood', 'Marshall', 'Moore', 'Heerey', 'Spender', 'Rares') AND case_number IS NOT NULL GROUP BY judge_name", "For frequent judges, what are the case count, number of dismissals, and average precedents?"),
            q("q18", f"SELECT {PLAINTIFF_FAMILY} AS plaintiff_family, {DEFENDANT_FAMILY} AS defendant_family, COUNT(*) AS case_count, AVG(legal_basis_num) AS avg_statutes, AVG(case_number) AS avg_precedents FROM legal WHERE plaintiff_current_status != '' AND defendant_current_status != '' AND case_number IS NOT NULL GROUP BY plaintiff_family, defendant_family HAVING COUNT(*) >= 3", "For plaintiff–defendant pairings with at least three cases, what are the count and the average statutes and precedents?"),
            q("q19", "SELECT hearing_year, COUNT(*) AS case_count, AVG(legal_basis_num) AS avg_statutes, MAX(case_number) AS max_precedents, SUM(CASE WHEN verdict = 'Approved' THEN 1 ELSE 0 END) AS approved_count FROM legal WHERE hearing_year BETWEEN 2006 AND 2009 AND case_number IS NOT NULL GROUP BY hearing_year", "For each hearing year from 2006 through 2009, what are the case count, average statutes, highest precedent count, and number of approved cases?"),
        ],
    },
}
