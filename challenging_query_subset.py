"""
UDA-Bench Challenging Query Subset - Python API Format
Designed to test failure cases of LLM-powered UDA systems
Compatible with systems like Palimpzest, LOTUS, and DocETL
"""

# ============================================================================
# 1. FILTER QUERIES (3 challenging queries)
# ============================================================================

# FILTER-1: Multi-attribute semantic reasoning on disease (Healthcare domain)
# Challenge: Requires understanding implicit relationships between pathogenesis, 
# prognosis, and quality of life impact across long documents
filter_query_1 = """
disease_doc = disease.filter(
    (disease["pathogenesis"] == "autoimmune") &
    (disease["prognosis"] == "chronic_condition") &
    (disease["quality_of_life_impact"] == "work_disability") &
    (disease["treatment_challenges"] != "drug resistance")
)
result = disease_doc.select([
    "disease_name", "pathogenesis", "prognosis", 
    "quality_of_life_impact", "treatment_challenges"
])
"""
# Why it's hard: Requires accurate extraction of 4 attributes with semantic overlap,
# autoimmune diseases often have complex descriptions scattered across documents


# FILTER-2: Inference-heavy legal case filtering (Legal domain)
# Challenge: "first_judge" requires inferring if this was a first-instance trial
filter_query_2 = """
legal_doc = Legal_Case.filter(
    (Legal_Case["first_judge"] == "1") &
    (Legal_Case["case_type"] == "Commercial Case") &
    (Legal_Case["case_number"] >= 10) &
    (Legal_Case["fine_amount"] != "20000.00")
)
result = legal_doc.select([
    "judge_name", "plaintiff", "defendant", "charges", 
    "first_judge", "case_number", "verdict"
])
"""
# Why it's hard: first_judge requires complex reasoning across entire document,
# case_number requires counting all cited precedent cases


# FILTER-3: Multi-modal filtering with semantic image understanding (Art domain)
# Challenge: Combines text and image attributes requiring style recognition
filter_query_3 = """
art_doc = art.filter(
    (art["style"] == "abstract expressionism") &
    (art["tone"] == "dark and dramatic") &
    (art["marriage"] == "Divorced") &
    (art["century"] == "20th")
)
result = art_doc.select([
    "name", "art_movement", "style", "composition", 
    "tone", "image_genre", "birth_country"
])
"""
# Why it's hard: style and tone require sophisticated image analysis,
# marriage status is often implicit in biographical text


# ============================================================================
# 2. PROJECTION QUERIES (3 challenging queries)
# ============================================================================

# PROJECTION-1: Complex numerical extraction from finance (Finance domain)
projection_query_1 = """
result = finance.select([
    "company_name", "bussiness_cost", "bussiness_profit", 
    "bussiness_sales", "business_segments_num", "business_risks"
])
"""
# Why it's hard: Financial values scattered across 100+ page documents,
# requires identifying relevant sections, summing multiple segments,
# and handling currency conversions


# PROJECTION-2: Inference-heavy medical attributes (Healthcare domain)
projection_query_2 = """
result = disease.select([
    "disease_name", "diagnosis_challenges", "treatment_challenges",
    "sequelae", "complications", "quality_of_life_impact"
])
"""
# Why it's hard: diagnosis_challenges and treatment_challenges require
# inferring implicit difficulties from descriptions;
# sequelae vs complications distinction requires medical knowledge


# PROJECTION-3: Multi-modal image attributes (Art domain)
projection_query_3 = """
result = art.select([
    "style", "theme", "object", "color", 
    "tone", "composition", "image_genre"
])
"""
# Why it's hard: Requires sophisticated vision-language understanding,
# theme requires high-level semantic interpretation,
# style classification needs art history knowledge


# ============================================================================
# 3. JOIN QUERIES (3 challenging queries)
# ============================================================================

# JOIN-1: Three-way join with semantic matching (Healthcare domain)
join_query_1 = """
disease_doc = disease.filter(disease["disease_type"] == "autoimmune")
drug_doc = drug.filter(drug["prescription_status"] == "prescription_only")
institution_doc = institution.filter(institution["research_fields"] == "immunology")

disease_drug = disease_doc.join(
    drug_doc,
    on_left="disease_name",
    on_right="disease_name"
)

result = disease_drug.join(
    institution_doc,
    on_left="disease_name",
    on_right="research_diseases"
)

result = result.select([
    "disease.disease_name", "disease.pathogenesis", "disease.prognosis",
    "drug.generic_name", "drug.mechanism_of_action", "drug.side_effects",
    "institution.institution_name", "institution.key_technologies", 
    "institution.research_fields"
])
"""
# Why it's hard: disease_name matching with variations,
# research_diseases is multi-valued requiring semantic matching


# JOIN-2: Four-way join across NBA entities (Sports domain)
join_query_2 = """
player_doc = player.filter(player["nba_championships"] >= 2)
manager_doc = manager.filter(manager["age"] > 50)
city_doc = city.filter(city["population"] > 2000000)

player_team = player_doc.join(team, on_left="team", on_right="team_name")
player_team_manager = player_team.join(
    manager_doc, 
    on_left="team.ownership", 
    on_right="name"
)
result = player_team_manager.join(
    city_doc,
    on_left="team.location",
    on_right="city_name"
)

result = result.select([
    "player.name", "player.mvp_awards", "player.college",
    "team.team_name", "team.championships", "team.founded_year",
    "manager.name", "manager.nationality",
    "city.population", "city.gdp", "city.state_name"
])
"""
# Why it's hard: Team names must match exactly,
# ownership field matches manager name with potential variations


# JOIN-3: Join with complex filtering (Healthcare domain)
join_query_3 = """
disease_doc = disease.filter(
    (disease["diagnostic_methods"] == "laboratory_test") &
    (disease["risk_factors"] == "genetic_predisposition")
)

drug_doc = drug.filter(
    (drug["pharmaceutical_form"] == "injection") &
    (drug["activation_conditions"] == "no special condition")
)

result = disease_doc.join(
    drug_doc,
    on_left="disease_name",
    on_right="disease_name"
)

result = result.select([
    "disease.disease_name", "disease.common_symptoms", "disease.affected_organs",
    "drug.brand_name", "drug.dosage_frequency", 
    "drug.unsuitable_population", "drug.storage_conditions"
])
"""
# Why it's hard: Multi-valued attribute matching,
# requires accurate extraction from both document types


# ============================================================================
# 4. AGGREGATION QUERIES (3 challenging queries)
# ============================================================================

# AGGREGATION-1: Grouping by multi-valued categorical attribute (Healthcare)
aggregation_query_1 = """
disease_filtered = disease.filter(
    # Implicit: count per group >= 5
)
result = disease_filtered.groupby("disease_type").agg({
    "disease_name": "count",
    "epidemiology": "avg"
})
result = result.filter(result["disease_name_count"] >= 5)
"""
# Why it's hard: disease_type is multi-valued with "||" separator,
# epidemiology contains text requiring numerical extraction


# AGGREGATION-2: Complex financial aggregation (Finance domain)
aggregation_query_2 = """
result = finance.groupby("principal_activities").agg({
    "revenue": ["avg", "sum"],
    "net_profit_or_loss": "sum",
    "total_assets": "max",
    "company_name": "count"
})
result = result.filter(result["revenue_avg"] > 1000000)
"""
# Why it's hard: principal_activities is multi-valued,
# financial values require extraction + currency conversion,
# negative numbers must be handled


# AGGREGATION-3: Multi-dimensional grouping (Sports domain)
aggregation_query_3 = """
result = player.groupby(["position", "nationality"]).agg({
    "name": "count",
    "mvp_awards": "avg",
    "nba_championships": "sum",
    "olympic_gold_medals": "max"
})
result = result.filter(
    (result["name_count"] >= 3) &
    (result["mvp_awards_avg"] > 0)
)
"""
# Why it's hard: Two-level grouping increases complexity,
# requires accurate extraction of all numerical award fields


# ============================================================================
# 5. UNION QUERIES (3 challenging queries)
# ============================================================================

# UNION-1: Union across different medical entity types (Healthcare)
union_query_1 = """
disease_results = disease.filter(
    disease["pathogenesis"] == "infectious_bacterial"
).select([
    "disease_name as entity_name",
    "'disease' as entity_type",
    "common_symptoms as symptoms_or_indication"
])

drug_results = drug.filter(
    drug["pharmaceutical_form"] == "injection"
).select([
    "brand_name as entity_name",
    "'drug' as entity_type",
    "indication as symptoms_or_indication"
])

result = disease_results.union(drug_results)
"""
# Why it's hard: Extracting comparable attributes from two different
# document types with different structures


# UNION-2: Union of players by different achievement criteria (Sports)
union_query_2 = """
mvp_winners = player.filter(player["mvp_awards"] >= 2).select([
    "name", "nationality", "team",
    "'MVP Winner' as achievement_type",
    "mvp_awards as count"
])

championship_winners = player.filter(player["nba_championships"] >= 3).select([
    "name", "nationality", "team",
    "'Championship Winner' as achievement_type",
    "nba_championships as count"
])

olympic_medalists = player.filter(player["olympic_gold_medals"] >= 2).select([
    "name", "nationality", "team",
    "'Olympic Gold Medalist' as achievement_type",
    "olympic_gold_medals as count"
])

result = mvp_winners.union(championship_winners).union(olympic_medalists)
"""
# Why it's hard: Three-way union requiring consistent numerical extraction,
# multiple threshold comparisons


# UNION-3: Union of legal cases by verdict types (Legal domain)
union_query_3 = """
guilty_cases = Legal_Case.filter(
    (Legal_Case["verdict"] == "Guilty") &
    (Legal_Case["case_type"] == "Commercial Case") &
    (Legal_Case["fine_amount"] != "")
).select([
    "judge_name", "plaintiff", "defendant",
    "'Guilty' as outcome",
    "fine_amount"
])

dismissed_cases = Legal_Case.filter(
    (Legal_Case["verdict"] == "Dismissed") &
    (Legal_Case["case_type"] == "Commercial Case") &
    (Legal_Case["legal_fees"] != "")
).select([
    "judge_name", "plaintiff", "defendant",
    "'Dismissed' as outcome",
    "legal_fees as fine_amount"
])

result = guilty_cases.union(dismissed_cases)
"""
# Why it's hard: Requires understanding verdict semantics,
# handling nullable fields


# ============================================================================
# LOTUS-specific semantic operator format examples
# ============================================================================

# LOTUS Filter with semantic operator
lotus_filter_example = """
# Using LOTUS semantic filter
result = disease.sem_filter(
    "the {document} has pathogenesis of autoimmune type AND "
    "prognosis indicates chronic condition AND "
    "significantly impacts work ability"
)
result = lotus.extract(result, [
    "disease_name", "pathogenesis", "prognosis",
    "quality_of_life_impact", "treatment_challenges"
])
"""

# LOTUS Join with semantic search
lotus_join_example = """
# Using LOTUS semantic join
disease_docs = disease.filter(disease["disease_type"] == "autoimmune")
drug_docs = drug.filter(drug["prescription_status"] == "prescription_only")

# Semantic join using embeddings
result = disease_docs.sem_join(
    drug_docs,
    join_key_left="disease_name",
    join_key_right="disease_name"
)
"""

# ============================================================================
# DocETL-specific multi-agent format example
# ============================================================================

docetl_complex_extraction = """
# DocETL with decomposition for complex extraction
from docetl import Pipeline

pipeline = Pipeline()

# Define extraction with decomposition strategy
extraction_op = pipeline.add_operation(
    op_type="extract",
    name="complex_disease_extraction",
    config={
        "attributes": [
            {
                "name": "diagnosis_challenges",
                "description": "Difficulties in diagnosing this disease, "
                               "inferred from diagnostic procedure descriptions"
            },
            {
                "name": "treatment_challenges", 
                "description": "Major issues in treatment, inferred from "
                               "treatment outcome descriptions and limitations"
            }
        ],
        "decomposition": "split_and_reduce",
        "chunk_size": 512
    }
)
"""

# ============================================================================
# NOTES ON ADAPTATION FOR DIFFERENT SYSTEMS:
# ============================================================================
"""
1. Palimpzest: Use the Python API format directly with filter(), select(), join()
2. LOTUS: Replace filter() with sem_filter() for semantic filtering
3. DocETL: Wrap queries in Pipeline operations with decomposition strategies
4. ZenDB/QUEST: Convert to SQL format (see challenging_query_subset.sql)
5. UQE: Use SQL format with clustering for aggregation queries

System-specific considerations:
- LOTUS: Benefits from semantic operators for complex filters
- DocETL: Use split-reduce for long documents (Finance, Legal)
- Palimpzest: Add model selection hints for complex extractions
- QUEST: Enable per-document filter ordering for multi-filter queries
- ZenDB: Ensure documents have hierarchical structure for SHT chunking
"""


