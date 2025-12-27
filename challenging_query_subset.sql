-- ============================================================================
-- UDA-Bench Challenging Query Subset
-- Designed to test failure cases of LLM-powered UDA systems
-- ============================================================================

-- ============================================================================
-- 1. FILTER QUERIES (3 challenging queries)
-- These queries test complex semantic reasoning and multi-attribute filtering
-- ============================================================================

-- FILTER-1: Multi-attribute semantic reasoning on disease (Healthcare domain)
-- Challenge: Requires understanding implicit relationships between pathogenesis, 
-- prognosis, and quality of life impact across long documents
SELECT disease_name, pathogenesis, prognosis, quality_of_life_impact, treatment_challenges
FROM disease
WHERE pathogenesis = 'autoimmune' 
  AND prognosis = 'chronic_condition' 
  AND quality_of_life_impact = 'work_disability'
  AND treatment_challenges != 'drug resistance';
-- Why it's hard: Requires accurate extraction of 4 attributes with semantic overlap,
-- autoimmune diseases often have complex descriptions scattered across documents

-- FILTER-2: Inference-heavy legal case filtering (Legal domain)
-- Challenge: "first_judge" requires inferring if this was a first-instance trial
-- by analyzing procedural history and previous case references
SELECT judge_name, plaintiff, defendant, charges, first_judge, case_number, verdict
FROM Legal_Case
WHERE first_judge = '1' 
  AND case_type = 'Commercial Case'
  AND case_number >= 10
  AND fine_amount != '20000.00';
-- Why it's hard: first_judge requires complex reasoning across the entire document,
-- not a direct extraction; case_number requires counting all cited precedent cases

-- FILTER-3: Multi-modal filtering with semantic image understanding (Art domain)
-- Challenge: Combines text and image attributes requiring style recognition
SELECT name, art_movement, style, composition, tone, image_genre, birth_country
FROM art
WHERE style = 'abstract expressionism'
  AND tone = 'dark and dramatic'
  AND marriage = 'Divorced'
  AND century = '20th';
-- Why it's hard: style and tone require sophisticated image analysis,
-- marriage status is often implicit in biographical text


-- ============================================================================
-- 2. PROJECTION QUERIES (3 challenging queries)
-- These test extraction of difficult-to-extract attributes
-- ============================================================================

-- PROJECTION-1: Complex numerical extraction from finance (Finance domain)
-- Challenge: bussiness_cost requires aggregating costs across multiple segments
-- and currency conversion, often scattered in tables and footnotes
SELECT company_name, bussiness_cost, bussiness_profit, bussiness_sales, 
       business_segments_num, business_risks
FROM finance;
-- Why it's hard: Financial values scattered across 100+ page documents,
-- requires identifying relevant sections, summing multiple segments,
-- and handling currency conversions

-- PROJECTION-2: Inference-heavy medical attributes (Healthcare domain)
-- Challenge: Extracting attributes requiring medical domain knowledge
SELECT disease_name, diagnosis_challenges, treatment_challenges, sequelae, 
       complications, quality_of_life_impact
FROM disease;
-- Why it's hard: diagnosis_challenges and treatment_challenges require
-- inferring implicit difficulties from descriptions of diagnostic/treatment procedures;
-- sequelae vs complications distinction requires medical knowledge

-- PROJECTION-3: Multi-modal image attributes (Art domain)
-- Challenge: All attributes require image analysis
SELECT style, theme, object, color, tone, composition, image_genre
FROM art;
-- Why it's hard: Requires sophisticated vision-language understanding,
-- theme requires high-level semantic interpretation,
-- style classification needs art history knowledge


-- ============================================================================
-- 3. JOIN QUERIES (3 challenging queries)
-- These test cross-document reasoning and semantic matching
-- ============================================================================

-- JOIN-1: Three-way join with semantic matching (Healthcare domain)
-- Challenge: Joining disease->drug requires matching disease names that may have
-- variations, then joining to institutions that "research" those diseases
SELECT disease.disease_name, disease.pathogenesis, disease.prognosis,
       drug.generic_name, drug.mechanism_of_action, drug.side_effects,
       institution.institution_name, institution.key_technologies, 
       institution.research_fields
FROM disease 
JOIN drug ON disease.disease_name = drug.disease_name
JOIN institution ON disease.disease_name = institution.research_diseases
WHERE disease.disease_type = 'autoimmune'
  AND drug.prescription_status = 'prescription_only'
  AND institution.research_fields = 'immunology';
-- Why it's hard: disease_name matching across documents with name variations,
-- research_diseases is multi-valued requiring semantic matching,
-- filters on all three tables increase complexity

-- JOIN-2: Four-way join across NBA entities (Sports domain)
-- Challenge: Requires maintaining join semantics across 4 tables with
-- potential naming inconsistencies
SELECT player.name, player.mvp_awards, player.college,
       team.team_name, team.championships, team.founded_year,
       manager.name AS manager_name, manager.nationality AS manager_nationality,
       city.population, city.gdp, city.state_name
FROM player
JOIN team ON player.team = team.team_name
JOIN manager ON team.ownership = manager.name
JOIN city ON team.location = city.city_name
WHERE player.nba_championships >= 2
  AND manager.age > 50
  AND city.population > 2000000;
-- Why it's hard: Team names must match exactly (e.g., "Los Angeles Lakers"),
-- ownership field matches manager name which may have variations,
-- location to city_name matching requires exact string match

-- JOIN-3: Join with complex filtering and aggregation requirement (Healthcare domain)
-- Challenge: Cross-document join with multi-attribute filtering
SELECT disease.disease_name, disease.common_symptoms, disease.affected_organs,
       drug.brand_name, drug.dosage_frequency, drug.unsuitable_population,
       drug.storage_conditions
FROM disease
JOIN drug ON disease.disease_name = drug.disease_name
WHERE disease.diagnostic_methods = 'laboratory_test'
  AND disease.risk_factors = 'genetic_predisposition'
  AND drug.pharmaceutical_form = 'injection'
  AND drug.activation_conditions = 'no special condition';
-- Why it's hard: Multi-valued attribute matching (diagnostic_methods, risk_factors),
-- requires accurate extraction from both document types before join


-- ============================================================================
-- 4. AGGREGATION QUERIES (3 challenging queries)
-- These test grouping on semantic attributes and numerical aggregation
-- ============================================================================

-- AGGREGATION-1: Grouping by multi-valued categorical attribute (Healthcare domain)
-- Challenge: disease_type is multi-valued (e.g., "autoimmune || inflammatory")
-- requiring proper parsing and grouping
SELECT disease_type, 
       COUNT(disease_name) AS disease_count,
       AVG(epidemiology) AS avg_prevalence
FROM disease
GROUP BY disease_type
HAVING COUNT(disease_name) >= 5;
-- Why it's hard: disease_type is multi-valued with "||" separator,
-- epidemiology contains text requiring numerical extraction,
-- HAVING clause requires accurate counting

-- AGGREGATION-2: Complex financial aggregation (Finance domain)
-- Challenge: Aggregating on numerical values that require extraction
-- from tables and currency conversion
SELECT principal_activities,
       AVG(revenue) AS avg_revenue,
       SUM(net_profit_or_loss) AS total_profit,
       MAX(total_assets) AS max_assets,
       COUNT(company_name) AS company_count
FROM finance
GROUP BY principal_activities
HAVING AVG(revenue) > 1000000;
-- Why it's hard: principal_activities is multi-valued,
-- financial values scattered across long documents requiring extraction + conversion,
-- negative numbers for losses must be handled correctly

-- AGGREGATION-3: Multi-dimensional grouping on player statistics (Sports domain)
-- Challenge: Grouping by position and computing aggregates on awards
SELECT position, nationality,
       COUNT(name) AS player_count,
       AVG(mvp_awards) AS avg_mvp,
       SUM(nba_championships) AS total_championships,
       MAX(olympic_gold_medals) AS max_olympic_golds
FROM player
GROUP BY position, nationality
HAVING COUNT(name) >= 3 AND AVG(mvp_awards) > 0;
-- Why it's hard: Two-level grouping increases complexity,
-- requires accurate extraction of all numerical award fields,
-- HAVING with multiple conditions on aggregate results


-- ============================================================================
-- 5. UNION QUERIES (3 challenging queries)
-- These test ability to combine results from different entity types or conditions
-- ============================================================================

-- UNION-1: Union across different medical entity types (Healthcare domain)
-- Challenge: Combining drug and disease information with compatible schemas
SELECT disease_name AS entity_name, 'disease' AS entity_type, 
       common_symptoms AS symptoms_or_indication
FROM disease
WHERE pathogenesis = 'infectious_bacterial'
UNION
SELECT brand_name AS entity_name, 'drug' AS entity_type,
       indication AS symptoms_or_indication
FROM drug
WHERE pharmaceutical_form = 'injection';
-- Why it's hard: Requires extracting comparable attributes from two different
-- document types with different structures, semantic matching of symptom-like fields

-- UNION-2: Union of players by different achievement criteria (Sports domain)
-- Challenge: Multiple selection criteria requiring accurate numerical extraction
SELECT name, nationality, team, 'MVP Winner' AS achievement_type, mvp_awards AS count
FROM player
WHERE mvp_awards >= 2
UNION
SELECT name, nationality, team, 'Championship Winner' AS achievement_type, nba_championships AS count
FROM player
WHERE nba_championships >= 3
UNION
SELECT name, nationality, team, 'Olympic Gold Medalist' AS achievement_type, olympic_gold_medals AS count
FROM player
WHERE olympic_gold_medals >= 2;
-- Why it's hard: Three-way union requiring consistent numerical extraction,
-- multiple threshold comparisons, result set de-duplication

-- UNION-3: Union of legal cases by different verdict types (Legal domain)
-- Challenge: Combining cases with semantic filtering on multiple attributes
SELECT judge_name, plaintiff, defendant, 'Guilty' AS outcome, fine_amount
FROM Legal_Case
WHERE verdict = 'Guilty' 
  AND case_type = 'Commercial Case'
  AND fine_amount != ''
UNION
SELECT judge_name, plaintiff, defendant, 'Dismissed' AS outcome, legal_fees AS fine_amount
FROM Legal_Case
WHERE verdict = 'Dismissed'
  AND case_type = 'Commercial Case'
  AND legal_fees != '';
-- Why it's hard: Requires understanding verdict semantics,
-- handling nullable fields (fine_amount, legal_fees),
-- semantic equivalence between different monetary penalty types


-- ============================================================================
-- NOTES ON DIFFICULTY FACTORS:
-- ============================================================================
-- 1. Long documents (Finance: avg 130K tokens, Legal: avg 5.6K tokens)
-- 2. Multi-valued attributes requiring parsing ("||" separator)
-- 3. Numerical extraction with currency conversion
-- 4. Attributes requiring inference (first_judge, diagnosis_challenges)
-- 5. Multi-modal reasoning (image style, tone, composition)
-- 6. Semantic matching in joins (name variations)
-- 7. Cross-document consistency requirements
-- 8. Aggregation on extracted numerical values
-- 9. Multi-level grouping with HAVING clauses
-- 10. Union requiring schema alignment across entity types
-- ============================================================================



