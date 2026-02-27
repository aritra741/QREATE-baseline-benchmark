-- ============================================================
-- Query-Awareness Trend Queries (Player Dataset)
-- Designed to span a spectrum: Q1 (most workload-similar) → Q10 (most workload-dissimilar)
-- Goal: show that WDIRS performance degrades as queries diverge from the training workload.
-- ============================================================

-- ── TIER 1: Near-identical to training workload ──────────────────────────────
-- Same table(s), same join keys, same attribute types, near-identical predicate structure.
-- The system will have seen the relevant chunks and the identity map for these tables.

-- Q1: Single-table filter (player) — mirrors filter_queries_player.sql
-- [Tables: player] [Ops: SELECT + WHERE(AND)]
SELECT position, nationality, age
FROM player
WHERE age < 91;

-- Q2: Binary join (player ⟕ team) with equality filter — mirrors join_queries.sql Q3 style
-- [Tables: player, team] [Ops: SELECT + JOIN + WHERE(single)]
SELECT player.name, player.mvp_awards, team.team_name, team.championship
FROM player
JOIN team ON player.team = team.team_name
WHERE player.nba_championships > 0;

-- ── TIER 2: Similar — same schema, slightly novel attribute combination ──────
-- Same join path(s) from training. Columns queried were individually seen in training
-- but not always co-selected together.

-- Q3: 4-table join (player ⟕ team ⟕ owner ⟕ city) + single filter
-- All 4 tables and join keys appeared in training; columns co-selected are new.
-- [Tables: player, team, owner, city] [Ops: SELECT + JOIN(4) + WHERE]
SELECT player.name, owner.name AS owner_name, city.state_name, city.population
FROM player
JOIN team ON player.team = team.team_name
JOIN owner ON team.ownership = owner.name
JOIN city ON team.location = city.city_name
WHERE player.age > 0;

-- Q4: Filter + Agg on player with GROUP BY position — mirrors mixed_queries_filter_agg_player.sql
-- [Tables: player] [Ops: SELECT + WHERE(OR) + GROUP BY + COUNT]
SELECT position, COUNT(*) AS player_count, AVG(nba_championships) AS avg_championships
FROM player
WHERE nationality = 'American  ' OR college = 'Duke University'
GROUP BY position;

-- ── TIER 3: Moderately similar — same tables, less-seen attribute combos ─────
-- Join path still exists in the training graph, but predicates reference attributes
-- that appeared less frequently (college, birth_date, draft_pick, city.gdp).

-- Q5: 3-table join (player ⟕ team ⟕ city) with filter on city.gdp
-- city.gdp appeared in training selects but almost never in WHERE.
-- [Tables: player, team, city] [Ops: SELECT + JOIN(3) + WHERE(AND)]
SELECT player.name, player.college, city.city_name, city.gdp
FROM player
JOIN team ON player.team = team.team_name
JOIN city ON team.location = city.city_name
WHERE city.gdp != '518.5' AND player.draft_pick <= 10;

-- Q6: Aggregation anchored at team+city with SUM — binary join (team ⟕ city) was in
-- training but agg over championship grouped by state_name is new.
-- [Tables: team, city] [Ops: SELECT + JOIN(2) + GROUP BY + SUM]
SELECT city.state_name, SUM(team.championship) AS total_championships, COUNT(*) AS team_count
FROM team
JOIN city ON team.location = city.city_name
GROUP BY city.state_name;

-- ── TIER 4: Moderately different — unusual traversal direction or anchor table ─
-- Owner as anchor (not player/team), or multi-hop predicate patterns not seen in training.

-- Q7: Owner-anchored 3-way join with filter on owner.own_year and player.college
-- In training, owner always appeared at the end of the join chain; here it's the anchor.
-- player.college as filter was barely used.
-- [Tables: owner, team, player] [Ops: SELECT + JOIN(3) + WHERE(AND)]
SELECT owner.name, owner.nationality, player.name AS player_name, player.college
FROM owner
JOIN team ON team.ownership = owner.name
JOIN player ON player.team = team.team_name
WHERE owner.own_year < 2000 AND player.college != '';

-- Q8: Complex multi-table filter using attributes rarely co-filtered in training
-- (birth_date, city.area, owner.own_year, player.fiba_world_cup all in same WHERE).
-- [Tables: player, team, city, owner] [Ops: SELECT + JOIN(4) + WHERE(mixed AND/OR)]
SELECT player.name, player.birth_date, city.area, owner.own_year
FROM player
JOIN team ON player.team = team.team_name
JOIN city ON team.location = city.city_name
JOIN owner ON team.ownership = owner.name
WHERE (player.fiba_world_cup > 0 AND city.area > 300.0)
   OR (player.olympic_gold_medals > 0 AND owner.own_year > 2010);

-- ── TIER 5: Very different — structural novelty, unseen predicates, reverse agg ─
-- Queries that require facts and entity-attribute combinations the workload
-- never asked for: city as primary aggregation anchor, subquery-like filtering on
-- rare attributes, multi-column GROUP BY never seen in training.

-- Q9: City-anchored aggregation over players — reverse traversal (city→team→player).
-- The direction city→team→player was never in the training workload (always player→team→city).
-- [Tables: city, team, player] [Ops: SELECT + JOIN(3) + WHERE + GROUP BY(city) + COUNT/AVG]
SELECT city.city_name, COUNT(DISTINCT player.name) AS num_players,
       AVG(player.age) AS avg_player_age, MAX(player.mvp_awards) AS max_mvp
FROM city
JOIN team ON city.city_name = team.location
JOIN player ON player.team = team.team_name
WHERE player.age < 40
GROUP BY city.city_name;

-- Q10: Multi-column GROUP BY (nationality + position) with owner attributes in SELECT
-- via 4-table join — combination of GROUP BY key structure and cross-table attribute
-- selection never appeared anywhere in the training workload.
-- [Tables: player, team, owner, city] [Ops: SELECT + JOIN(4) + GROUP BY(2 cols) + AVG/COUNT]
SELECT player.nationality, player.position,
       COUNT(*) AS player_count,
       AVG(player.draft_pick) AS avg_draft_pick,
       MIN(owner.own_year) AS earliest_ownership
FROM player
JOIN team ON player.team = team.team_name
JOIN owner ON team.ownership = owner.name
JOIN city ON team.location = city.city_name
WHERE city.population > '500000'
GROUP BY player.nationality, player.position;
