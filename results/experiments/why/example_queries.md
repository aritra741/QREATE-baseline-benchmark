# Appendix: example test queries

Each test query is a benchmark query with one column replaced by a column the build did not read. A few per corpus, chosen to cover the aggregates and, where the corpus has them, joins and several filter conditions.

## Research papers (59 test queries)

```sql
SELECT performance_on_NQ, COUNT(paper_name) AS count_papers FROM cspaper WHERE uses_reranker = 'Yes' GROUP BY performance_on_NQ
```

```sql
SELECT retrieval_method, SUM(baseline_amount) AS sum_baseline_amount FROM cspaper WHERE uses_reranker = 'No' OR performance_on_hotpotqa = 'F1: 62.2' OR baseline = 'Traditional RAG' GROUP BY retrieval_method
```

```sql
SELECT agent_framework, MAX(baseline_amount) AS max_baselines FROM cspaper WHERE agent_framework IN ('Other', 'Multi-Agent Collaboration') AND NOT baseline_amount IS NULL GROUP BY agent_framework
```

```sql
SELECT CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 'Hybrid' WHEN retrieval_method LIKE '%Graph-based%' THEN 'Graph-based' WHEN retrieval_method LIKE '%Dense%' THEN 'Dense' WHEN retrieval_method LIKE '%Sparse%' THEN 'Sparse' WHEN retrieval_method LIKE '%Web Search%' THEN 'Web Search' WHEN retrieval_method <> '' THEN 'Other' END AS retrieval_family, agent_framework, COUNT(*) AS paper_count FROM cspaper WHERE retrieval_method <> '' AND agent_framework IN ('Other', 'Multi-Agent Collaboration') GROUP BY retrieval_family, agent_framework
```

## Basketball players (118 test queries)

```sql
SELECT t.team_name, COUNT(*) AS player_count, AVG(p.draft_pick) AS avg_age, SUM(CASE WHEN NOT p.olympic_gold_medals IS NULL THEN p.olympic_gold_medals ELSE 0 END) AS total_recorded_olympic_golds FROM player AS p JOIN team AS t ON TRIM(p.team) = TRIM(t.team_name) GROUP BY t.team_name HAVING COUNT(*) >= 2
```

```sql
SELECT player.team, SUM(player.nba_championships) AS sum_player_mvp_awards FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE player.age > 28 GROUP BY player.team
```

```sql
SELECT player.position, MAX(player.draft_year) AS max_player_mvp_awards FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name GROUP BY player.position
```

```sql
SELECT player.team, AVG(player.draft_year) AS avg_player_age FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE (city.city_name = 'Los Angeles') OR (player.mvp_awards >= 1) GROUP BY player.team
```

## Artists (43 test queries)

```sql
SELECT zodiac, COUNT(birth_date) AS count_art_institution FROM art GROUP BY zodiac
```

```sql
SELECT genre, AVG(awards) AS avg_age FROM art WHERE birth_country = 'British India' OR teaching <> 0 GROUP BY genre
```

```sql
SELECT nationality, MAX(age) AS max_age FROM art WHERE tone = 'Warm' GROUP BY nationality
```

```sql
SELECT nationality, COUNT(*) AS artist_count FROM art WHERE tone IN ('Bright', 'Dark') AND nationality <> '' GROUP BY nationality HAVING COUNT(*) >= 5
```

## Medical (43 test queries)

```sql
SELECT prescription_status, COUNT(recommended_usage) AS count_side_effects FROM drug WHERE administration_route <> 'inhalation' GROUP BY prescription_status
```

```sql
SELECT disease.complications, COUNT(disease.treatments) AS count_disease_treatments FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY disease.complications
```

```sql
SELECT prescription_status, COUNT(mechanism_of_action) AS count_generic_name FROM drug WHERE (administration_route = 'injection') AND (administration_route <> 'subcutaneous') GROUP BY prescription_status
```

## Court judgments (27 test queries)

```sql
SELECT CASE WHEN case_type IN ('Administrative Case', 'Civil Case', 'Commercial Case') THEN case_type ELSE 'Other' END AS case_family, COUNT(*) AS case_count FROM legal WHERE fine_amount IN ('0', '5000', '20000') GROUP BY case_family
```

```sql
SELECT CASE WHEN verdict IN ('Dismissed', 'Approved', 'Others') THEN verdict ELSE 'Other' END AS verdict_family, AVG(legal_basis_num) AS avg_statutes FROM legal WHERE judgment_year = '2009' AND case_number >= 3 GROUP BY verdict_family
```

```sql
SELECT evidence, MIN(judgment_year) AS min_hearing_year FROM legal GROUP BY evidence
```

```sql
SELECT verdict, MIN(legal_basis_num) AS min_legal_basis_num FROM legal WHERE fine_amount = '20000' AND defendant <> 'Construction, Forestry, Mining and Energy Union' AND fine_amount <> '70000' GROUP BY verdict
```

