-- Query 1: train (agg_only) id=agg_only_med_gen_13
SELECT administration_route, MIN(dosage_frequency) AS min_dosage_frequency FROM drug GROUP BY administration_route;

-- Query 2: train (agg_only) id=agg_only_med_gen_11
SELECT administration_route, COUNT(manufacturer) AS count_manufacturer FROM drug GROUP BY administration_route;

-- Query 3: train (agg_only) id=agg_only_med_gen_24
SELECT pharmaceutical_form, MAX(storage_conditions) AS max_storage_conditions FROM drug GROUP BY pharmaceutical_form;

-- Query 4: train (agg_only) id=agg_only_med_gen_21
SELECT pharmaceutical_form, MIN(dosage_frequency) AS min_dosage_frequency FROM drug GROUP BY pharmaceutical_form;

-- Query 5: train (agg_only) id=agg_only_med_gen_23
SELECT pharmaceutical_form, MIN(storage_conditions) AS min_storage_conditions FROM drug GROUP BY pharmaceutical_form;

-- Query 6: train (agg_only) id=agg_only_med_gen_14
SELECT administration_route, MAX(dosage_frequency) AS max_dosage_frequency FROM drug GROUP BY administration_route;

-- Query 7: train (agg_only) id=agg_only_med_gen_16
SELECT administration_route, MAX(storage_conditions) AS max_storage_conditions FROM drug GROUP BY administration_route;

-- Query 8: train (agg_only) id=agg_only_med_gen_27
SELECT institution_type, COUNT(funding_sources) AS count_funding_sources FROM institution GROUP BY institution_type;

-- Query 9: train (agg_only) id=agg_only_med_gen_22
SELECT pharmaceutical_form, MAX(dosage_frequency) AS max_dosage_frequency FROM drug GROUP BY pharmaceutical_form;

-- Query 10: train (agg_only) id=agg_only_med_gen_28
SELECT institution_type, MIN(research_fields) AS min_research_fields FROM institution GROUP BY institution_type;

-- Query 11: train (agg_only) id=agg_queries_drug_5
SELECT prescription_status, COUNT(storage_conditions) AS count_storage_conditions FROM drug GROUP BY prescription_status;

-- Query 12: train (agg_only) id=agg_queries_drug_3
SELECT prescription_status, AVG(recommended_usage) AS avg_recommended_usage FROM drug GROUP BY prescription_status;

-- Query 13: train (agg_only) id=agg_only_med_gen_31
SELECT institution_country, COUNT(institution_name) AS count_institution_name FROM institution GROUP BY institution_country;

-- Query 14: train (agg_only) id=agg_queries_drug_8
SELECT prescription_status, SUM(recommended_usage) AS sum_recommended_usage FROM drug GROUP BY prescription_status;

-- Query 15: train (agg_only) id=agg_only_med_gen_30
SELECT institution_country, COUNT(*) AS count_all FROM institution GROUP BY institution_country;

-- Query 16: train (agg_only) id=agg_only_med_gen_33
SELECT institution_country, MIN(research_fields) AS min_research_fields FROM institution GROUP BY institution_country;

-- Query 17: train (agg_only) id=agg_only_med_gen_10
SELECT administration_route, COUNT(generic_name) AS count_generic_name FROM drug GROUP BY administration_route;

-- Query 18: train (agg_only) id=agg_only_med_gen_20
SELECT pharmaceutical_form, COUNT(side_effects) AS count_side_effects FROM drug GROUP BY pharmaceutical_form;

-- Query 19: train (agg_only) id=agg_queries_drug_2
SELECT prescription_status, COUNT(generic_name) AS count_generic_name FROM drug GROUP BY prescription_status;

-- Query 20: train (agg_only) id=agg_queries_institution_2
SELECT institution_type, COUNT(institution_name) AS count_institution_name FROM institution GROUP BY institution_type;

-- Query 21: train (agg_filter) id=agg_filter_med_gen_188
SELECT administration_route, MIN(dosage_frequency) AS min_dosage_frequency FROM drug WHERE (pharmaceutical_form = 'tablet' AND pharmaceutical_form != 'solution') OR (pharmaceutical_form != 'spray') GROUP BY administration_route;

-- Query 22: train (agg_filter) id=agg_filter_med_gen_320
SELECT institution_type, COUNT(funding_sources) AS count_funding_sources FROM institution WHERE (institution_country = 'France') AND (institution_country != 'China') GROUP BY institution_type;

-- Query 23: train (agg_filter) id=agg_filter_med_gen_248
SELECT pharmaceutical_form, COUNT(manufacturer) AS count_manufacturer FROM drug WHERE (administration_route != 'subcutaneous' AND prescription_status = 'unclassified') OR (administration_route = 'injection') GROUP BY pharmaceutical_form;

-- Query 24: train (agg_filter) id=agg_filter_med_gen_306
SELECT institution_type, COUNT(*) AS count_all FROM institution WHERE (institution_country != 'USA') OR (institution_country = 'Australia') GROUP BY institution_type;

-- Query 25: train (agg_filter) id=agg_filter_med_gen_169
SELECT administration_route, COUNT(side_effects) AS count_side_effects FROM drug WHERE prescription_status = 'unclassified' GROUP BY administration_route;

-- Query 26: train (agg_filter) id=agg_filter_med_gen_48
SELECT prescription_status, COUNT(manufacturer) AS count_manufacturer FROM drug WHERE (administration_route != 'topical' AND pharmaceutical_form = 'capsule') OR (pharmaceutical_form = 'cream') GROUP BY prescription_status;

-- Query 27: train (agg_filter) id=agg_filter_med_gen_83
SELECT prescription_status, MIN(dosage_frequency) AS min_dosage_frequency FROM drug WHERE (pharmaceutical_form = 'tablet') OR (pharmaceutical_form != 'solution') GROUP BY prescription_status;

-- Query 28: train (agg_filter) id=agg_filter_med_gen_76
SELECT prescription_status, COUNT(side_effects) AS count_side_effects FROM drug WHERE (pharmaceutical_form = 'tablet' AND pharmaceutical_form != 'solution') OR (pharmaceutical_form != 'spray') GROUP BY prescription_status;

-- Query 29: train (agg_filter) id=agg_filter_med_gen_346
SELECT institution_country, COUNT(institution_name) AS count_institution_name FROM institution WHERE research_fields = 'immunology' GROUP BY institution_country;

-- Query 30: train (agg_filter) id=mixed_queries_filter_agg_6
SELECT prescription_status, MIN(storage_conditions) AS min_storage_conditions FROM drug WHERE (prescription_status < 'unclassified' AND side_effects != 'hair loss') OR (disease_name != 'Chronic Obstructive Pulmonary Disease' AND administration_route = 'intravenous') GROUP BY prescription_status;

-- Query 31: train (agg_filter) id=agg_filter_med_gen_125
SELECT administration_route, COUNT(generic_name) AS count_generic_name FROM drug WHERE pharmaceutical_form != 'spray' GROUP BY administration_route;

-- Query 32: train (agg_filter) id=agg_filter_med_gen_364
SELECT institution_country, MIN(research_fields) AS min_research_fields FROM institution WHERE research_fields = 'microbiology' GROUP BY institution_country;

-- Query 33: train (agg_filter) id=agg_filter_med_gen_28
SELECT prescription_status, COUNT(generic_name) AS count_generic_name FROM drug WHERE (administration_route = 'injection' AND administration_route != 'subcutaneous') OR (pharmaceutical_form != 'injection') GROUP BY prescription_status;

-- Query 34: train (agg_filter) id=agg_filter_med_gen_310
SELECT institution_type, COUNT(institution_name) AS count_institution_name FROM institution WHERE institution_country = 'Germany' GROUP BY institution_type;

-- Query 35: train (agg_filter) id=agg_filter_med_gen_64
SELECT prescription_status, COUNT(side_effects) AS count_side_effects FROM drug WHERE (administration_route != 'inhalation' AND pharmaceutical_form = 'injection') OR (pharmaceutical_form = 'gel') GROUP BY prescription_status;

-- Query 36: train (agg_filter) id=agg_filter_med_gen_61
SELECT prescription_status, COUNT(side_effects) AS count_side_effects FROM drug WHERE administration_route != 'inhalation' GROUP BY prescription_status;

-- Query 37: train (agg_filter) id=agg_filter_med_gen_367
SELECT institution_country, MIN(research_fields) AS min_research_fields FROM institution WHERE research_fields != 'microbiology' GROUP BY institution_country;

-- Query 38: train (agg_filter) id=agg_filter_med_gen_330
SELECT institution_type, MIN(research_fields) AS min_research_fields FROM institution WHERE (institution_country = 'Australia') OR (institution_country != 'India') GROUP BY institution_type;

-- Query 39: train (agg_filter) id=agg_filter_med_gen_372
SELECT institution_country, MIN(research_fields) AS min_research_fields FROM institution WHERE (institution_type = 'university-affiliated') OR (institution_type != 'public') GROUP BY institution_country;

-- Query 40: train (agg_filter) id=agg_filter_med_gen_294
SELECT pharmaceutical_form, MIN(dosage_frequency) AS min_dosage_frequency FROM drug WHERE (prescription_status != 'unclassified') AND (administration_route = 'topical') GROUP BY pharmaceutical_form;

-- Query 41: train (agg_join) id=agg_join_med_gen_3
SELECT drug.prescription_status, COUNT(disease.disease_name) AS count_disease_disease_name FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY drug.prescription_status;

-- Query 42: train (agg_join) id=agg_join_med_gen_10
SELECT drug.administration_route, COUNT(disease.disease_name) AS count_disease_disease_name FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY drug.administration_route;

-- Query 43: train (agg_join) id=agg_join_med_gen_11
SELECT drug.administration_route, MIN(drug.dosage_frequency) AS min_drug_dosage_frequency FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY drug.administration_route;

-- Query 44: train (agg_join) id=agg_join_med_gen_27
SELECT disease.disease_type, MIN(drug.storage_conditions) AS min_drug_storage_conditions FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY disease.disease_type;

-- Query 45: train (agg_join) id=agg_join_med_gen_19
SELECT drug.pharmaceutical_form, MAX(drug.dosage_frequency) AS max_drug_dosage_frequency FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY drug.pharmaceutical_form;

-- Query 46: train (agg_join) id=agg_join_med_gen_7
SELECT drug.prescription_status, COUNT(disease.treatments) AS count_disease_treatments FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY drug.prescription_status;

-- Query 47: train (agg_join) id=agg_join_med_gen_8
SELECT drug.administration_route, COUNT(*) AS count_all FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY drug.administration_route;

-- Query 48: train (agg_join) id=agg_join_med_gen_18
SELECT drug.pharmaceutical_form, MIN(drug.dosage_frequency) AS min_drug_dosage_frequency FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY drug.pharmaceutical_form;

-- Query 49: train (agg_join) id=agg_join_med_gen_23
SELECT disease.disease_type, COUNT(drug.generic_name) AS count_drug_generic_name FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY disease.disease_type;

-- Query 50: train (agg_join) id=agg_join_med_gen_22
SELECT disease.disease_type, COUNT(*) AS count_all FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY disease.disease_type;

-- Query 51: train (agg_join) id=mixed_queries_agg_join_2
SELECT institution.institution_type, MIN(drug.recommended_usage) AS min_drug_recommended_usage FROM disease JOIN drug ON disease.disease_name = drug.disease_name JOIN institution ON disease.disease_name = institution.research_diseases GROUP BY institution.institution_type;

-- Query 52: train (agg_join) id=agg_join_med_gen_1
SELECT drug.prescription_status, COUNT(*) AS count_all FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY drug.prescription_status;

-- Query 53: train (agg_join) id=agg_join_med_gen_26
SELECT disease.disease_type, MAX(drug.dosage_frequency) AS max_drug_dosage_frequency FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY disease.disease_type;

-- Query 54: train (agg_join) id=agg_join_med_gen_21
SELECT drug.pharmaceutical_form, COUNT(disease.treatments) AS count_disease_treatments FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY drug.pharmaceutical_form;

-- Query 55: train (agg_join) id=agg_join_med_gen_9
SELECT drug.administration_route, COUNT(drug.generic_name) AS count_drug_generic_name FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY drug.administration_route;

-- Query 56: train (agg_join) id=agg_join_med_gen_2
SELECT drug.prescription_status, COUNT(drug.generic_name) AS count_drug_generic_name FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY drug.prescription_status;

-- Query 57: train (agg_join) id=agg_join_med_gen_28
SELECT disease.disease_type, COUNT(disease.treatments) AS count_disease_treatments FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY disease.disease_type;

-- Query 58: train (agg_join) id=agg_join_med_gen_4
SELECT drug.prescription_status, MIN(drug.dosage_frequency) AS min_drug_dosage_frequency FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY drug.prescription_status;

-- Query 59: train (agg_join) id=agg_join_med_gen_20
SELECT drug.pharmaceutical_form, MIN(drug.storage_conditions) AS min_drug_storage_conditions FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY drug.pharmaceutical_form;

-- Query 60: train (agg_join) id=agg_join_med_gen_13
SELECT drug.administration_route, MIN(drug.storage_conditions) AS min_drug_storage_conditions FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY drug.administration_route;

-- Query 61: train (agg_filter_join) id=agg_filter_join_med_gen_175
SELECT drug.pharmaceutical_form, MAX(drug.dosage_frequency) AS max_drug_dosage_frequency FROM drug JOIN disease ON drug.disease_name = disease.disease_name WHERE drug.administration_route = 'oral' GROUP BY drug.pharmaceutical_form;

-- Query 62: train (agg_filter_join) id=agg_filter_join_med_gen_112
SELECT drug.administration_route, MAX(drug.dosage_frequency) AS max_drug_dosage_frequency FROM drug JOIN disease ON drug.disease_name = disease.disease_name WHERE disease.pathogenesis != 'traumatic' GROUP BY drug.administration_route;

-- Query 63: train (agg_filter_join) id=agg_filter_join_med_gen_30
SELECT drug.prescription_status, COUNT(disease.disease_name) AS count_disease_disease_name FROM drug JOIN disease ON drug.disease_name = disease.disease_name WHERE (drug.pharmaceutical_form = 'tablet') OR (disease.disease_type = 'degenerative') GROUP BY drug.prescription_status;

-- Query 64: train (agg_filter_join) id=agg_filter_join_med_gen_60
SELECT drug.prescription_status, MAX(drug.dosage_frequency) AS max_drug_dosage_frequency FROM drug JOIN disease ON drug.disease_name = disease.disease_name WHERE (disease.disease_type = 'metabolic') OR (drug.administration_route = 'oral') GROUP BY drug.prescription_status;

-- Query 65: train (agg_filter_join) id=agg_filter_join_med_gen_1
SELECT drug.prescription_status, COUNT(*) AS count_all FROM drug JOIN disease ON drug.disease_name = disease.disease_name WHERE drug.administration_route = 'oral' GROUP BY drug.prescription_status;

-- Query 66: train (agg_filter_join) id=agg_filter_join_med_gen_173
SELECT drug.pharmaceutical_form, MAX(drug.dosage_frequency) AS max_drug_dosage_frequency FROM drug JOIN disease ON drug.disease_name = disease.disease_name WHERE (drug.prescription_status = 'unclassified') AND (disease.disease_type = 'infectious') GROUP BY drug.pharmaceutical_form;

-- Query 67: train (agg_filter_join) id=agg_filter_join_med_gen_101
SELECT drug.administration_route, MIN(drug.dosage_frequency) AS min_drug_dosage_frequency FROM drug JOIN disease ON drug.disease_name = disease.disease_name WHERE (disease.disease_type = 'degenerative') AND (drug.prescription_status = 'unclassified') GROUP BY drug.administration_route;

-- Query 68: train (agg_filter_join) id=agg_filter_join_med_gen_103
SELECT drug.administration_route, MIN(drug.dosage_frequency) AS min_drug_dosage_frequency FROM drug JOIN disease ON drug.disease_name = disease.disease_name WHERE disease.pathogenesis != 'traumatic' GROUP BY drug.administration_route;

-- Query 69: train (agg_filter_join) id=mixed_queries_filter_agg_join_2
SELECT institution.research_fields, MAX(disease.quality_of_life_impact) AS max_disease_quality_of_life_impact FROM disease JOIN drug ON disease.disease_name = drug.disease_name JOIN institution ON disease.disease_name = institution.research_diseases WHERE institution.leadership = 'Pierre-Yves Marcy' AND drug.activation_conditions != 'take with food' GROUP BY institution.research_fields;

-- Query 70: train (agg_filter_join) id=mixed_queries_filter_agg_join_7
SELECT drug.prescription_status, AVG(disease.epidemiology) AS avg_disease_epidemiology FROM disease JOIN drug ON disease.disease_name = drug.disease_name WHERE drug.pharmaceutical_form = 'tablet' GROUP BY drug.prescription_status;

-- Query 71: train (agg_filter_join) id=agg_filter_join_med_gen_138
SELECT drug.pharmaceutical_form, COUNT(drug.generic_name) AS count_drug_generic_name FROM drug JOIN disease ON drug.disease_name = disease.disease_name WHERE (disease.disease_type = 'autoimmune') OR (drug.administration_route = 'injection') GROUP BY drug.pharmaceutical_form;

-- Query 72: train (agg_filter_join) id=agg_filter_join_med_gen_127
SELECT drug.pharmaceutical_form, COUNT(*) AS count_all FROM drug JOIN disease ON drug.disease_name = disease.disease_name WHERE disease.disease_type = 'autoimmune' GROUP BY drug.pharmaceutical_form;

-- Query 73: train (agg_filter_join) id=agg_filter_join_med_gen_58
SELECT drug.prescription_status, MAX(drug.dosage_frequency) AS max_drug_dosage_frequency FROM drug JOIN disease ON drug.disease_name = disease.disease_name WHERE disease.disease_type = 'metabolic' GROUP BY drug.prescription_status;

-- Query 74: train (agg_filter_join) id=agg_filter_join_med_gen_137
SELECT drug.pharmaceutical_form, COUNT(drug.generic_name) AS count_drug_generic_name FROM drug JOIN disease ON drug.disease_name = disease.disease_name WHERE (disease.disease_type = 'autoimmune') AND (drug.administration_route = 'injection') GROUP BY drug.pharmaceutical_form;

-- Query 75: train (agg_filter_join) id=agg_filter_join_med_gen_96
SELECT drug.administration_route, COUNT(disease.disease_name) AS count_disease_disease_name FROM drug JOIN disease ON drug.disease_name = disease.disease_name WHERE (disease.pathogenesis != 'traumatic') OR (drug.pharmaceutical_form = 'tablet') GROUP BY drug.administration_route;

-- Query 76: train (agg_filter_join) id=agg_filter_join_med_gen_172
SELECT drug.pharmaceutical_form, MAX(drug.dosage_frequency) AS max_drug_dosage_frequency FROM drug JOIN disease ON drug.disease_name = disease.disease_name WHERE drug.prescription_status = 'unclassified' GROUP BY drug.pharmaceutical_form;

-- Query 77: train (agg_filter_join) id=agg_filter_join_med_gen_23
SELECT drug.prescription_status, COUNT(drug.generic_name) AS count_drug_generic_name FROM drug JOIN disease ON drug.disease_name = disease.disease_name WHERE (drug.pharmaceutical_form = 'capsule') AND (disease.pathogenesis != 'traumatic') GROUP BY drug.prescription_status;

-- Query 78: train (agg_filter_join) id=agg_filter_join_med_gen_42
SELECT drug.prescription_status, MIN(drug.dosage_frequency) AS min_drug_dosage_frequency FROM drug JOIN disease ON drug.disease_name = disease.disease_name WHERE (drug.pharmaceutical_form = 'capsule') OR (disease.pathogenesis != 'traumatic') GROUP BY drug.prescription_status;

-- Query 79: train (agg_filter_join) id=agg_filter_join_med_gen_102
SELECT drug.administration_route, MIN(drug.dosage_frequency) AS min_drug_dosage_frequency FROM drug JOIN disease ON drug.disease_name = disease.disease_name WHERE (disease.disease_type = 'degenerative') OR (drug.prescription_status = 'unclassified') GROUP BY drug.administration_route;

-- Query 80: train (agg_filter_join) id=mixed_queries_filter_agg_join_11
SELECT drug.prescription_status, SUM(disease.treatment_challenges) AS sum_disease_treatment_challenges FROM disease JOIN drug ON disease.disease_name = drug.disease_name WHERE disease.treatments != 'radiotherapy' OR drug.brand_name != 'Lo Loestrin FE' OR drug.brand_name = 'Nucala' GROUP BY drug.prescription_status;
