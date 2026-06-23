-- Query 1: test (agg_only) id=agg_only_med_gen_8
SELECT prescription_status, MAX(storage_conditions) AS max_storage_conditions FROM drug GROUP BY prescription_status;

-- Query 2: test (agg_only) id=agg_queries_drug_4
SELECT prescription_status, MAX(recommended_usage) AS max_recommended_usage FROM drug GROUP BY prescription_status;

-- Query 3: test (agg_only) id=agg_only_med_gen_19
SELECT pharmaceutical_form, COUNT(manufacturer) AS count_manufacturer FROM drug GROUP BY pharmaceutical_form;

-- Query 4: test (agg_only) id=agg_queries_institution_1
SELECT research_fields, MIN(institution_country) AS min_institution_country FROM institution GROUP BY research_fields;

-- Query 5: test (agg_only) id=agg_only_med_gen_15
SELECT administration_route, MIN(storage_conditions) AS min_storage_conditions FROM drug GROUP BY administration_route;

-- Query 6: test (agg_filter) id=agg_filter_med_gen_77
SELECT prescription_status, COUNT(side_effects) AS count_side_effects FROM drug WHERE pharmaceutical_form != 'tablet' GROUP BY prescription_status;

-- Query 7: test (agg_filter) id=agg_filter_med_gen_65
SELECT prescription_status, COUNT(side_effects) AS count_side_effects FROM drug WHERE administration_route = 'subcutaneous' GROUP BY prescription_status;

-- Query 8: test (agg_filter) id=agg_filter_med_gen_84
SELECT prescription_status, MIN(dosage_frequency) AS min_dosage_frequency FROM drug WHERE (pharmaceutical_form = 'tablet' AND pharmaceutical_form != 'solution') OR (pharmaceutical_form != 'spray') GROUP BY prescription_status;

-- Query 9: test (agg_filter) id=agg_filter_med_gen_120
SELECT administration_route, COUNT(*) AS count_all FROM drug WHERE (pharmaceutical_form != 'spray' AND prescription_status = 'unclassified') OR (pharmaceutical_form = 'injection') GROUP BY administration_route;

-- Query 10: test (agg_filter) id=agg_filter_med_gen_371
SELECT institution_country, MIN(research_fields) AS min_research_fields FROM institution WHERE (institution_type = 'university-affiliated') AND (institution_type != 'public') GROUP BY institution_country;

-- Query 11: test (agg_join) id=agg_join_med_gen_6
SELECT drug.prescription_status, MIN(drug.storage_conditions) AS min_drug_storage_conditions FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY drug.prescription_status;

-- Query 12: test (agg_join) id=agg_join_med_gen_12
SELECT drug.administration_route, MAX(drug.dosage_frequency) AS max_drug_dosage_frequency FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY drug.administration_route;

-- Query 13: test (agg_join) id=agg_join_med_gen_14
SELECT drug.administration_route, COUNT(disease.treatments) AS count_disease_treatments FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY drug.administration_route;

-- Query 14: test (agg_join) id=agg_join_med_gen_17
SELECT drug.pharmaceutical_form, COUNT(disease.disease_name) AS count_disease_disease_name FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY drug.pharmaceutical_form;

-- Query 15: test (agg_join) id=agg_join_med_gen_15
SELECT drug.pharmaceutical_form, COUNT(*) AS count_all FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY drug.pharmaceutical_form;

-- Query 16: test (agg_filter_join) id=agg_filter_join_med_gen_165
SELECT drug.pharmaceutical_form, MIN(drug.dosage_frequency) AS min_drug_dosage_frequency FROM drug JOIN disease ON drug.disease_name = disease.disease_name WHERE (drug.prescription_status = 'unclassified') OR (disease.disease_type = 'infectious') GROUP BY drug.pharmaceutical_form;

-- Query 17: test (agg_filter_join) id=mixed_queries_filter_agg_join_8
SELECT institution.institution_type, AVG(drug.dosage_frequency) AS avg_drug_dosage_frequency FROM disease JOIN drug ON disease.disease_name = drug.disease_name JOIN institution ON disease.disease_name = institution.research_diseases WHERE drug.generic_name != 'Linaclotide' AND disease.common_symptoms != 'headache' GROUP BY institution.institution_type;

-- Query 18: test (agg_filter_join) id=mixed_queries_filter_agg_join_4
SELECT institution.research_fields, MAX(disease.diagnosis_challenges) AS max_disease_diagnosis_challenges FROM disease JOIN drug ON disease.disease_name = drug.disease_name JOIN institution ON disease.disease_name = institution.research_diseases WHERE institution.institution_country = 'United Kingdom' AND institution.research_fields != 'gastroenterology' AND disease.etiology = 'pulmonary embolism' GROUP BY institution.research_fields;

-- Query 19: test (agg_filter_join) id=agg_filter_join_med_gen_109
SELECT drug.administration_route, MAX(drug.dosage_frequency) AS max_drug_dosage_frequency FROM drug JOIN disease ON drug.disease_name = disease.disease_name WHERE disease.disease_type = 'degenerative' GROUP BY drug.administration_route;

-- Query 20: test (agg_filter_join) id=mixed_queries_filter_agg_join_6
SELECT institution.institution_type, AVG(disease.epidemiology) AS avg_disease_epidemiology FROM disease JOIN drug ON disease.disease_name = drug.disease_name JOIN institution ON disease.disease_name = institution.research_diseases WHERE (drug.brand_name != 'Daliresp' AND disease.common_symptoms != 'back pain') OR (institution.key_technologies = 'enzyme-linked immunosorbent assay (ELISA)' AND drug.pharmaceutical_form != 'ointment') GROUP BY institution.institution_type;
