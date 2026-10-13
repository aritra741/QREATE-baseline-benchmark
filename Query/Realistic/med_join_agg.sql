-- Realistic aggregated joins, medical (draft for review, 2026-10-12). drug.disease_name is a list of diseases, so the
-- realistic join is "the drug treats this disease": the disease's name is one of the drug's listed diseases. Written
-- with LIKE on the '||'-separated list; the '=' form of the benchmark's join split matches only single-disease drugs.

-- Q1: How many drugs are available for each disease?
SELECT disease.disease_name, COUNT(*) AS drugs FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' GROUP BY disease.disease_name;

-- Q2: How many prescription and over-the-counter drugs are there for chronic diseases?
SELECT drug.prescription_status, COUNT(*) AS drugs FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' WHERE disease.prognosis LIKE '%chronic%' GROUP BY drug.prescription_status;

-- Q3: How many drugs treat autoimmune diseases?
SELECT COUNT(*) AS drugs FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' WHERE disease.disease_type LIKE '%autoimmune%';

-- Q4: How many oral drugs are available for infectious diseases?
SELECT COUNT(*) AS oral_drugs FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' WHERE disease.disease_type LIKE '%infectious%' AND drug.administration_route LIKE '%oral%';

-- Q5: For diseases treated by injection, how many drugs need a prescription?
SELECT drug.prescription_status, COUNT(*) AS drugs FROM drug JOIN disease ON '||' || REPLACE(drug.disease_name, ' || ', '||') || '||' LIKE '%||' || disease.disease_name || '||%' WHERE disease.treatments LIKE '%injection%' GROUP BY drug.prescription_status;
