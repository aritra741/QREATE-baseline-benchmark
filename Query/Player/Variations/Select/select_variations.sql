-- Inspiration: Query 1 (select_queries_player.sql)
-- Variation: Added name and team for context.
SELECT name, team, draft_pick FROM player;

-- Inspiration: Query 2 (select_queries_player.sql)
-- Variation: Focused on career achievements and demographics.
SELECT name, nba_championships, olympic_gold_medals, mvp_awards, birth_date FROM player;

-- Inspiration: Query 1 (select_queries_team.sql)
-- Variation: Added location for full team profile.
SELECT team_name, ownership, championships, founded_year, location FROM team;

-- Inspiration: Query 1 (select_queries_city.sql)
-- Variation: Included population for city context.
SELECT city_name, area, gdp, population, state_name FROM city;

-- Inspiration: Query 1 (select_queries_manager.sql)
-- Variation: Added age and nationality for manager profile.
SELECT name, nba_team, own_year, age, nationality FROM manager;

-- Inspiration: Query 4 (select_queries_player.sql)
-- Variation: Selection focused on international and team success.
SELECT name, fiba_world_cup, nba_championships, team FROM player;
