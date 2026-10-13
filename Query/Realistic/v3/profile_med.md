# Data profile: med

Tables (rows = documents): disease (100), drug (98), institution (99)

Columns marked INITIAL are read by the initial build; build questions may use ONLY those. Test questions may use any column.

Value statistics are from the correct data (what a perfect extraction would hold). Values containing '||' are lists.

## disease.affected_organs  [new; list; filled 80/100; distinct 75]
description: primary organs, tissues, or body systems impacted by the disease (e.g., lungs, liver, joints, nervous system).
most common values: 'lungs' x3; 'respiratory system' x2; 'skin' x2; 'gut' x2; 'gastrointestinal tract||intestine' x1; 'joints||gums' x1; 'central nervous system' x1; 'red blood cells||bone marrow||critical organs' x1; 'large_blood_vessels||kidneys||eyes||nerves||pancreas' x1; 'heart||arteries||legs||lungs' x1

## disease.common_symptoms  [new; list; filled 82/100; distinct 82]
description: typical clinical manifestations or symptoms experienced by patients with this disease (e.g., fever, cough, joint pain).
most common values: 'loose bowel motion||diarrhea' x1; 'chronic pain||acute pain||bleeding||joint bleeds||mobility p' x1; 'behavioral issues||developmental delay||learning disabilitie' x1; 'pale skin||pale color inside the eyelids||pale color under t' x1; 'thirst||polyuria||weight_loss||healthy_appetite||weakness||m' x1; 'chest pain||chest pressure||chest squeezing||arm pain||jaw p' x1; 'shortness of breath||chest pain' x1; 'chronic fatigue||joint stiffness||insomnia||overall weakness' x1; 'inability to urinate||straining while trying to urinate||clo' x1; 'urinary_obstruction||enlarged_prostate' x1

## disease.complications  [new; list; filled 50/100; distinct 50]
description: significant secondary conditions or health problems that can arise as a result of the disease (e.g., heart failure, kidney injury).
most common values: 'dehydration' x1; 'arthritis||anxiety||depression||high blood pressure||gingivi' x1; 'adverse educational outcomes||repeating a grade||special edu' x1; 'organ damage||death' x1; 'blindness||cardiovascular_disorders||large_blood_vessel_dama' x1; 'stroke||life-threatening clots in legs||life-threatening clo' x1; 'kidney_failure||acute_kidney_injury||urinary_obstruction||me' x1; 'encephalitis' x1; 'metastatic lung cancer||superior vena cava syndrome||paraneo' x1; "erosive esophagitis||Barrett's esophagus||peptic esophageal " x1

## disease.diagnosis_challenges  [new; list; filled 31/100; distinct 26]
description: typical difficulties or obstacles encountered in the diagnosis of the disease (e.g., nonspecific symptoms, lack of early biomarkers, disease mimics).
most common values: 'nonspecific symptoms||disease mimics' x3; 'asymptomatic||nonspecific symptoms' x2; 'nonspecific_symptoms' x2; 'disease mimics||nonspecific symptoms' x2; 'misdiagnosis||misunderstood' x1; 'low sensitivity in early illness||delays in recognizing rash' x1; 'lack of simple diagnostic test||brain pathology starts decad' x1; 'nonspecific symptoms||asymptomatic' x1; 'denial of need for care||dismissal of diagnosis||ridicule of' x1; 'lack of accurate diagnostic test' x1

## disease.diagnostic_methods  [INITIAL; list; filled 56/100; distinct 24]
description: primary diagnostic approaches used for this disease; choose one or more from ['clinical_evaluation', 'laboratory_test', 'imaging', 'biopsy', 'genetic_testing', 'endoscopy', 'functional_test', 'pathology', 'screening', 'other'], seperated by `||` (e.g. clinical_evaluation || laboratory_test).
most common values: 'clinical_evaluation' x18; 'clinical_evaluation||imaging' x6; 'laboratory_test' x5; 'clinical_evaluation||laboratory_test' x4; 'clinical_evaluation||laboratory_test||imaging' x2; 'laboratory_test||imaging' x2; 'laboratory_test||clinical_evaluation' x2; 'laboratory_test||screening||clinical_evaluation||imaging' x1; 'clinical_evaluation||endoscopy||functional_test' x1; 'laboratory_test||screening' x1

## disease.disease_name  [INITIAL; list; filled 100/100; distinct 100]
description: the official name of the disease (e.g., Rheumatoid Arthritis).
most common values: 'Antibiotic-associated diarrhea' x1; 'Hemophilia B' x1; 'Attention-Deficit Hyperactivity Disorder' x1; 'Microcytic Anemia' x1; 'Diabetes type 1' x1; 'Birth Control Heart Attack' x1; 'Pleural Effusion' x1; 'Fibromyalgia' x1; 'Urinary Tract Infection' x1; 'Prostate Cancer' x1

## disease.disease_type  [INITIAL; list; filled 90/100; distinct 50]
description: comprehensive classification of the disease; choose one or more from ['autoimmune', 'infectious', 'genetic', 'metabolic', 'neoplastic', 'degenerative', 'congenital', 'traumatic', 'nutritional', 'vascular', 'inflammatory', 'endocrine', 'psychiatric', 'toxic', 'allergic', 'iatrogenic', 'idiopathic', 'parasitic', 'others'], seperated by `||` (e.g. neoplastic || degenerative)
most common values: 'infectious||inflammatory' x9; 'psychiatric' x7; 'neoplastic' x7; 'inflammatory' x7; 'infectious' x7; 'genetic' x3; 'infectious||parasitic' x3; 'vascular||iatrogenic' x2; 'vascular||degenerative' x2; 'metabolic||endocrine' x2

## disease.drugs  [new; list; filled 86/100; distinct 80]
description: list the specific names of drugs or pharmaceuticals used to treat or control the disease (e.g., metformin, aspirin, infliximab, penicillin).
most common values: 'antibiotics' x7; 'probiotics' x1; 'recombinant factor IX||Alprolix' x1; 'Ritalin||Adderall||Prozac||Strattera||antipsychotic drugs||a' x1; 'iron supplements||antibiotics||hormones' x1; 'insulin' x1; 'insulin||glucose||calcium' x1; 'antibiotics||diuretics||Combiflam' x1; 'medical marijuana||Nabilone||Lyrica||Cymbalta||Savella' x1; 'finasteride' x1

## disease.epidemiology  [new; list; filled 61/100; distinct 61]
description: population-level data about the disease, including prevalence, incidence, age/gender distribution, or notable epidemiological patterns (e.g., 1 in 1000 adults, more common in males).
most common values: 'more common in males||median age 47' x1; '8–10% of children in southeastern Virginia medicated for ADH' x1; '8-44 percent in older men' x1; '100000_in_Netherlands||12000_children_under_20_in_Netherland' x1; 'women taking drospirenone/ethinyl estradiol birth control pi' x1; 'over five million Americans||most are women' x1; 'more_common_in_males||elderly_men||second_leading_cause_of_c' x1; 'most common rickettsial disease in United States||age-relate' x1; 'number one cause of cancer death in the United States in bot' x1; 'most common upper gastrointestinal disorder in the Western H' x1

## disease.etiology  [new; list; filled 64/100; distinct 64]
description: the underlying cause(s) of the disease, including genetic, environmental, infectious, or lifestyle factors (e.g., gene mutation, viral infection, smoking).
most common values: 'antibiotic use' x1; 'lack of functional factor IX (FIX)' x1; 'thalassemia||iron deficiency||chronic disease||lead poisonin' x1; 'genetic_susceptibility||environmental_factors||diet||infecti' x1; 'use of drospirenone/ethinyl estradiol birth control pills' x1; 'pneumonia||pulmonary embolism||kidney disease||congestive he' x1; 'Clinical Endocannabinoid Deficiency (CECD) (under study)||un' x1; 'bacterial exposure||injury' x1; 'Rickettsia rickettsii infection||tick-borne' x1; 'smoking||secondhand smoke||environmental exposures||asbestos' x1

## disease.pathogenesis  [INITIAL; list; filled 80/100; distinct 53]
description: the biological and physiological process by which the disease develops and progresses, choose one or more from: ['autoimmune', 'infectious_bacterial', 'infectious_viral', 'infectious_fungal', 'infectious_parasitic', 'genetic_mutation', 'metabolic_disorder', 'inflammatory', 'degenerative', 'neoplastic', 'vascular', 'traumatic', 'toxic', 'allergic', 'endocrine_disorder', 'nutritional_deficiency', 'iatrogenic', 'idiopathic', 'other'], seperated by `||` (e.g. inflammatory || degenerative).
most common values: 'infectious_bacterial||inflammatory' x6; 'inflammatory' x5; 'infectious_bacterial' x5; 'neoplastic' x4; 'iatrogenic' x3; 'genetic_mutation' x3; 'infectious_parasitic' x3; 'other' x2; 'vascular' x2; 'genetic_mutation||degenerative' x2

## disease.preventive_measures  [INITIAL; list; filled 32/100; distinct 25]
description: known methods or actions to reduce the risk of disease occurrence, choose one or more from ['vaccination', 'lifestyle_modification', 'screening', 'prophylactic_medication', 'personal_hygiene', 'health_education', 'protective_equipment', 'environmental_control', 'vector_control', 'safe_sex_practices', 'regular_exercise', 'dietary_management', 'early_detection', 'other'], , seperated by `||` (e.g. vaccination || regular_exercise).
most common values: 'lifestyle_modification||dietary_management' x3; 'dietary_intervention' x2; 'dietary_management' x2; 'lifestyle_modification' x2; 'vaccination' x2; 'lifestyle_modification||regular_exercise||dietary_management' x2; 'stop taking potentially harmful drugs' x1; 'screening' x1; 'screening||safe_sex_practices' x1; 'prophylactic_medication' x1

## disease.prognosis  [INITIAL; list; filled 56/100; distinct 42]
description: typical course and expected outcome of the disease; choose one or more from ['full_recovery', 'partial_recovery', 'chronic_condition', 'remission_possible', 'high_recurrence_risk', 'low_recurrence_risk', 'high_mortality', 'moderate_mortality', 'low_mortality', 'disability', 'variable', 'stable', 'progressive', 'quality_of_life_impairment', 'asymptomatic', 'unknown'], seperated by `||` (e.g.artial_recovery || chronic_condition)
most common values: 'chronic_condition||quality_of_life_impairment' x4; 'high_mortality' x4; 'chronic_condition||quality_of_life_impairment||variable' x3; 'variable' x3; 'high_mortality||progressive||quality_of_life_impairment' x2; 'chronic_condition' x2; 'full_recovery||chronic_condition' x2; 'high_recurrence_risk' x2; 'full_recovery||partial_recovery||chronic_condition||variable' x1; 'high_mortality||quality_of_life_impairment||variable' x1

## disease.quality_of_life_impact  [INITIAL; list; filled 53/100; distinct 42]
description: how the disease affects the patient's daily living, social interactions, work, and psychological well-being choose one or more from: ['mobility_impairment', 'chronic_pain', 'fatigue', 'sleep_disorders', 'anxiety', 'depression', 'social_isolation', 'work_disability', 'cognitive_impairment', 'sexual_dysfunction', 'self_care_difficulty', 'dietary_restriction', 'dependence_on_others', 'body_image_issues', 'financial_burden', 'emotional_distress', 'stigma', 'quality_of_life_decline', 'other'], , seperated by `||` (e.g. chronic_pain || work_disability).
most common values: 'quality_of_life_decline' x10; 'quality_of_life_decline||social_isolation' x2; 'dietary_restriction' x2; 'mobility_impairment||chronic_pain||anxiety||depression||self' x1; 'quality_of_life_decline||educational impairment||emotional_d' x1; 'fatigue' x1; 'chronic_pain||fatigue||sleep_disorders||anxiety||cognitive_i' x1; 'urinary_dysfunction||sexual_dysfunction||quality_of_life_dec' x1; 'chronic_pain||work_disability' x1; 'self_care_difficulty||dependence_on_others||anxiety||quality' x1

## disease.risk_factors  [new; list; filled 58/100; distinct 53]
description: factors that increase the likelihood of developing the disease, choose one or more from ['family_history', 'genetic_predisposition', 'age', 'gender', 'smoking', 'alcohol_consumption', 'obesity', 'overweight', 'sedentary_lifestyle', 'unhealthy_diet', 'hypertension', 'hyperlipidemia', 'diabetes', 'chronic_disease', 'immunosuppression', 'environmental_exposure', 'occupational_exposure', 'exposure_to_toxins', 'infection', 'stress', 'low_socioeconomic_status', 'radiation_exposure', 'other'], seperated by `||` (e.g. family_history || age).
most common values: 'genetic_predisposition' x3; 'infection' x2; 'age' x2; 'stress' x2; 'gender||age||other' x1; 'genetic_predisposition||age||gender||chronic_disease||enviro' x1; 'genetic_predisposition||infection||diet||age' x1; 'age||drug_use' x1; 'gender' x1; 'age||gender' x1

## disease.sequelae  [new; list; filled 15/100; distinct 15]
description: long-term or permanent health problems, symptoms, or functional impairments that persist after the acute phase of a disease or injury has resolved.(e.g., paralysis after stroke, chronic pain, hearing loss or cognitive impairment)
most common values: 'chronic pain||mobility impairment' x1; 'blindness||cardiovascular_disorders||large_blood_vessel_dama' x1; 'chronic_kidney_disease' x1; 'permanent nerve damage' x1; 'infertility||blindness in children' x1; 'visual field defects' x1; 'chronic_pain||disability' x1; 'disability||nerve damage' x1; 'loss of fingers||loss of toes' x1; 'deformity||amputation||mobility impairment' x1

## disease.treatment_challenges  [INITIAL; list; filled 46/100; distinct 44]
description: major issues in the treatment or management of the disease (e.g., drug resistance, frequent relapse, side effects, poor adherence).
most common values: 'side effects' x3; 'high rates of chronic pain||high analgesia use||need for mul' x1; 'overdiagnosis||overtreatment||polypharmacy||side effects||dr' x1; 'current medical treatments fall far short||side effects of p' x1; 'drug resistance' x1; 'side_effects||renal_failure_risk' x1; 'higher risk of death with antibiotics other than doxycycline' x1; 'drug resistance||side effects' x1; 'drug resistance||frequent relapse||side effects||poor adhere' x1; 'no cure' x1

## disease.treatments  [INITIAL; list; filled 89/100; distinct 50]
description: list of treatment modalities, choose one or more from ['oral_medication', 'injection', 'surgery', 'radiotherapy', 'chemotherapy', 'physical_therapy', 'psychotherapy', 'lifestyle_modification', 'device_implantation', 'dietary_intervention', 'others'], seperated by `||` (e.g. oral_medication).
most common values: 'oral_medication' x23; 'oral_medication||injection' x5; 'injection' x4; 'oral_medication||surgery' x4; 'dietary_intervention' x2; 'oral_medication||lifestyle_modification||others' x2; 'oral_medication||lifestyle_modification' x2; 'oral_medication||others' x2; 'surgery' x2; 'oral_medication||injection||lifestyle_modification||dietary_' x2

## drug.activation_conditions  [new; list; filled 29/98; distinct 7]
description: specific conditions or requirements for the drug to take effect; choose one or more from ['requires stimulation', 'requires food', 'requires fasting', 'requires physical activity', 'no special condition', 'requires specific timing', 'requires co-administration with other drugs', 'other'], seperated by `||` (e.g. requires stimulation || requires food)
most common values: 'no special condition' x18; 'requires specific timing' x3; 'other' x2; 'requires co-administration with other drugs' x2; 'take with food' x2; 'before meals' x1; 'requires stimulation' x1

## drug.active_ingredients  [new; list; filled 90/98; distinct 90]
description: active pharmaceutical ingredients in the drug (e.g., Sildenafil||Dapoxetine).
most common values: 'Promethazine' x1; 'Gabapentin' x1; 'Letrozole' x1; 'Insulin Lispro' x1; '6-mercaptopurine' x1; 'Penicillin V Potassium' x1; 'Amoxicillin||Clavulanic Acid' x1; 'Bupivacaine' x1; 'Isoniazid' x1; 'Psilocybin' x1

## drug.administration_route  [INITIAL; list; filled 77/98; distinct 16]
description: the route through which the drug is administered; choose one or more from ['oral', 'intravenous', 'intramuscular', 'subcutaneous', 'topical', 'transdermal', 'rectal', 'nasal', 'inhalation', 'other'], seperated by `||` (e.g. other).
most common values: 'oral' x50; 'subcutaneous' x4; 'intravenous' x4; 'inhalation' x3; 'topical' x3; 'other' x3; 'injection' x1; 'oral||other' x1; 'intravenous||subcutaneous' x1; 'oral||intravenous||topical' x1

## drug.brand_name  [INITIAL; list; filled 68/98; distinct 68]
description: the commercial or brand name of the drug (e.g., Super Kamagra).
most common values: 'Phenadoz' x1; 'Neurontin®||Lyrica®' x1; 'Fempro' x1; 'Humalog' x1; 'Penicillin V Potassium Tablets, USP' x1; 'Augmentin' x1; 'Isokin' x1; 'LINZESS®||CONSTELLA®' x1; 'Savella' x1; 'Androxal' x1

## drug.disease_name  [INITIAL; list; filled 94/98; distinct 94]
description: the main disease(s) the drug is intended to treat; use standard disease names (e.g., Hypertension, Diabetes Mellitus, Asthma).
most common values: 'Motion Sickness||Nausea||Vomiting||Allergic Rhinitis||Urtica' x1; 'Partial onset seizures' x1; 'Pulmonary thromboembolism' x1; 'breast cancer' x1; 'Diabetes Mellitus' x1; 'rheumatoid arthritis||renal transplant rejection||inflammato' x1; 'upper respiratory tract infection||scarlet fever||erysipelas' x1; 'common cold || bronchitis || tonsillitis' x1; 'pain||soft tissue anesthesia||pulpal anesthesia' x1; 'Human immunodeficiency virus infection||diabetes mellitus||g' x1

## drug.dosage_frequency  [INITIAL; list; filled 55/98; distinct 34]
description: the recommended frequency of administration (e.g., once daily, twice a day, every 8 hours).
most common values: 'once daily' x15; 'twice a day' x8; 'once every 4 to eight hours' x1; 'every 6 to 8 hours || every 6 hours' x1; 'three times a day' x1; 'single dose' x1; 'twice daily' x1; '3-4 times per day||once daily' x1; '12 sessions' x1; 'continuous infusion||three times a day||once or twice a day|' x1

## drug.generic_name  [INITIAL; list; filled 91/98; distinct 91]
description: the standard generic name(s) of the drug (e.g., Sildenafil with Dapoxetine).
most common values: 'Promethazine' x1; 'Gabapentin' x1; 'Warfarin' x1; 'Letrozole' x1; 'Insulin Lispro' x1; '6-mercaptopurine' x1; 'Penicillin V' x1; 'Clavulanic Acid' x1; 'Bupivacaine' x1; 'Isoniazid' x1

## drug.indication  [new; list; filled 89/98; distinct 89]
description: the main symptoms, clinical manifestations, or related conditions for which the drug may be used (e.g., fever, pain, edema, high cholesterol, wheezing).
most common values: 'nasal congestion||itching nose||runny nose||sneezing||itchy ' x1; 'partial onset seizures' x1; 'pulmonary thromboembolism' x1; 'breast tumors that require estrogen for growth' x1; 'high blood glucose' x1; 'rheumatoid arthritis||prevention of graft rejection||inflamm' x1; 'infection||recurrence prevention||prophylaxis' x1; 'infections' x1; 'surgical anesthesia||lengthy restorative procedures||postope' x1; 'preventive treatment of bacterial infections' x1

## drug.manufacturer  [new; list; filled 28/98; distinct 27]
description: the name of the company or manufacturer producing the drug (e.g., Ajanta Pharma).
most common values: 'Bayer' x2; 'Cipla' x1; 'GlaxoSmithKline' x1; 'Pfizer Laboratories Limited' x1; 'Ironwood Pharmaceuticals, Inc.||AbbVie||Astellas||Astra Zene' x1; 'Forest Pharmaceuticals, Inc.' x1; 'Lupin Limited' x1; 'Beijing Chemeebio Pharma-tech Co., Ltd.' x1; 'Shanghai Chemicals' x1; 'Preferred Pharmaceuticals, Inc.' x1

## drug.mechanism_of_action  [new; list; filled 70/98; distinct 70]
description: how the drug works in the body to achieve its intended effect (e.g., improves blood circulation in penile vessels, supporting erection).
most common values: 'preventing the aromatase enzyme from converting androstenedi' x1; 'preserves glucose in cells||prevents liver glucose release||' x1; 'Metabolized by TPMT into 6-methylmercaptopurine, by xanthine' x1; 'inactivates beta-lactamase enzymes' x1; 'Binds to sodium channels in neurons, blocking nerve impulse ' x1; 'blocking the cell wall synthesis' x1; 'damages oligodendrocytes and dividing precursor cells in the' x1; 'guanylate cyclase-C agonist; increases intestinal fluid secr' x1; 'serotonin and norepinephrine reuptake inhibition' x1; 'helps your body respond better to insulin produced by your p' x1

## drug.pharmaceutical_form  [INITIAL; list; filled 74/98; distinct 30]
description: the physical form in which the drug is administered; choose one or more from ['tablet', 'capsule', 'injection', 'solution', 'cream', 'ointment', 'powder', 'granule', 'suspension', 'patch', 'spray', 'suppository', 'other'], seperated by `||` (e.g. tablet || injection).
most common values: 'tablet' x28; 'injection' x9; 'capsule' x5; 'powder' x3; 'other' x2; 'solution' x2; 'tablet||solution' x2; 'tablet || suspension' x1; 'tablet||injection||syrup' x1; 'capsule||other' x1

## drug.prescription_status  [INITIAL; category; filled 45/98; distinct 4]
description: whether the drug requires a prescription or can be bought over-the-counter; choose one from ['prescription_only', 'over_the_counter', 'restricted', 'unclassified'].
most common values: 'prescription_only' x39; 'over_the_counter' x4; 'prescription_only||restricted' x1; 'unclassified' x1

## drug.recommended_usage  [new; list; filled 59/98; distinct 22]
description: recommended instructions for use, choose one or more from ['swallowed with water', 'chewable', 'dissolve in water', 'take with food', 'take without food', 'take with or without food', 'at fixed time', 'before meals', 'after meals', 'other'], seperated by `||` (e.g. chewable || other).
most common values: 'other' x19; 'take with or without food' x8; 'at fixed time' x6; 'take with food' x4; 'take with or without food||at fixed time' x3; 'take with or without food||swallowed with water' x2; 'swallowed with water||take with or without food||at fixed ti' x2; 'before meals||after meals' x1; 'take as prescribed' x1; 'take with food||swallowed with water' x1

## drug.side_effects  [INITIAL; list; filled 72/98; distinct 72]
description: known or common side effects associated with the drug (e.g., photosensitivity, nausea, dizziness, drowsiness, tenderness).
most common values: 'blurred vision||confusion||fatigue||dizziness||drowsiness||d' x1; 'major bleeding||minor bleeding' x1; 'blood clots||flu-like symptoms||angina||heart attack||stroke' x1; 'tender swollen glands on neck||itching at injection site||sw' x1; 'myelosuppression||hepatotoxicity||megaloblastosis' x1; 'Clostridium difficile associated diarrhea' x1; 'self-inflicted injury from biting anesthetized tissue' x1; 'severe complications' x1; 'hallucinatory side effects||headache||slight increase in blo' x1; 'long-term brain damage||healthy brain cells die off' x1

## drug.single_dose  [new; list; filled 59/98; distinct 56]
description: the amount of the drug to be taken at one time per administration,extract all 'population + dose' pairs (e.g., adults 10 mg || children 5 mg || patients with EGPA 3x100 mg).
most common values: 'adults 10 mg || adults 25 mg' x2; 'adults 20 mg' x2; 'adults 2 mg' x2; 'adults and children 1 year and older [dose not specified]' x1; '125 to 250 mg || 250 to 500 mg' x1; 'adults and children 12 years old and older weighing 40 kg or' x1; 'adults 300 mg' x1; 'adults 25 mg (oral capsule)||adults 1 mg (intravenous)||adul' x1; 'children 2-5 years 9 mcg||children 2-5 years 18 mcg||childre' x1; 'adults 12.5 mg (Day 1)||adults 12.5 mg twice daily (for 2 da' x1

## drug.storage_conditions  [new; list; filled 18/98; distinct 15]
description: recommended conditions for storing the drug; choose one or more from ['store at room temperature', 'store in a cool place', 'refrigerate', 'freeze', 'protect from light', 'keep in a dry place', 'keep tightly closed', 'avoid freezing', 'other'], seperated by `||` (e.g. avoid freezing || other).
most common values: 'store at room temperature' x3; 'refrigerate' x2; 'keep tightly closed||store in a tight, light-resistant conta' x1; 'freeze' x1; 'protect from light||store in a cool place' x1; 'store at room temperature||avoid freezing||store below 25C o' x1; 'protect from light||use within 60 days of opening' x1; 'store at room temperature||keep tightly closed||keep in a dr' x1; 'store at room temperature||refrigerate||keep tightly closed|' x1; 'store at room temperature||store in a secure place out of th' x1

## drug.unsuitable_population  [new; list; filled 57/98; distinct 57]
description: main populations for which the drug is not suitable or should be avoided; specify as described in the document (e.g., children, elderly, pregnant women, patients with renal impairment, children under 12).
most common values: 'children under 2 years old||pregnant women' x1; 'individuals with histories of significant allergies and/or a' x1; 'pediatric patients||patients with cognitive impairment or me' x1; 'pregnant women||elderly people||patients with nephropathy||p' x1; 'patients using antidepressants' x1; 'patients with severe psychiatric illness' x1; 'patients with cyst on the ovary||patients with fibroid tumor' x1; 'allergy to Pamelor or similar medicines||currently taking or' x1; 'patients hypersensitive to glimepiride||patients hypersensit' x1; 'pediatric patients||pregnant women||breastfeeding women||pat' x1
