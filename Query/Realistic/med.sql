-- Realistic aggregate questions over drug labels and disease descriptions (2026-10-12).
-- Q1: How many drugs need a prescription, and how many are over the counter?
SELECT prescription_status, COUNT(*) AS drugs FROM drug GROUP BY prescription_status;
-- Q2: How many drugs are taken orally?
SELECT COUNT(*) AS drugs FROM drug WHERE administration_route LIKE '%oral%';
-- Q3: How many drugs come as tablets, capsules or injections?
SELECT CASE WHEN pharmaceutical_form LIKE '%tablet%' THEN 'tablet' WHEN pharmaceutical_form LIKE '%capsule%' THEN 'capsule' WHEN pharmaceutical_form LIKE '%injection%' THEN 'injection' ELSE 'other' END AS form, COUNT(*) AS drugs FROM drug GROUP BY form;
-- Q4: How many drugs should be taken with food?
SELECT COUNT(*) AS drugs FROM drug WHERE recommended_usage LIKE '%with food%';
-- Q5: How many drugs must be refrigerated?
SELECT COUNT(*) AS drugs FROM drug WHERE storage_conditions LIKE '%refrigerat%';
-- Q6: How many drugs are unsuitable for pregnant women?
SELECT COUNT(*) AS drugs FROM drug WHERE unsuitable_population LIKE '%pregnan%';
-- Q7: How many prescription drugs list dizziness as a side effect?
SELECT prescription_status, COUNT(*) AS drugs FROM drug WHERE side_effects LIKE '%dizziness%' GROUP BY prescription_status;
-- Q8: How many drugs are made by Pfizer?
SELECT COUNT(*) AS drugs FROM drug WHERE manufacturer LIKE '%Pfizer%';
-- Q9: How many diseases are infectious, autoimmune, genetic or psychiatric?
SELECT CASE WHEN disease_type LIKE '%infectious%' THEN 'infectious' WHEN disease_type LIKE '%autoimmune%' THEN 'autoimmune' WHEN disease_type LIKE '%genetic%' THEN 'genetic' WHEN disease_type LIKE '%psychiatric%' THEN 'psychiatric' ELSE 'other' END AS kind, COUNT(*) AS diseases FROM disease GROUP BY kind;
-- Q10: How many diseases affect the lungs?
SELECT COUNT(*) AS diseases FROM disease WHERE affected_organs LIKE '%lung%';
-- Q11: How many diseases are chronic?
SELECT COUNT(*) AS diseases FROM disease WHERE prognosis LIKE '%chronic%';
-- Q12: How many diseases are treated with surgery?
SELECT COUNT(*) AS diseases FROM disease WHERE treatments LIKE '%surgery%';
-- Q13: How many diseases have a genetic risk factor?
SELECT COUNT(*) AS diseases FROM disease WHERE risk_factors LIKE '%genetic%';
-- Q14: How many diseases list fever as a symptom?
SELECT COUNT(*) AS diseases FROM disease WHERE common_symptoms LIKE '%fever%';
-- Q15: How many diseases can be prevented by vaccination?
SELECT COUNT(*) AS diseases FROM disease WHERE preventive_measures LIKE '%vaccin%';

-- QJ1: How many drugs are available for each disease?
SELECT disease.disease_name, COUNT(*) AS drugs FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' GROUP BY disease.disease_name;

-- QJ2: How many prescription and over-the-counter drugs are there for chronic diseases?
SELECT drug.prescription_status, COUNT(*) AS drugs FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' WHERE disease.prognosis LIKE '%chronic%' GROUP BY drug.prescription_status;

-- QJ3: How many drugs treat autoimmune diseases?
SELECT COUNT(*) AS drugs FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' WHERE disease.disease_type LIKE '%autoimmune%';

-- QJ4: How many oral drugs are available for infectious diseases?
SELECT COUNT(*) AS oral_drugs FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' WHERE disease.disease_type LIKE '%infectious%' AND drug.administration_route LIKE '%oral%';

-- QJ5: For diseases treated by injection, how many drugs need a prescription?
SELECT drug.prescription_status, COUNT(*) AS drugs FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' WHERE disease.treatments LIKE '%injection%' GROUP BY drug.prescription_status;
