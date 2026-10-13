-- Realistic aggregate questions over NBA player biographies, single table (2026-10-12).
-- Q1: How many players are there of each nationality?
SELECT nationality, COUNT(*) AS players FROM player GROUP BY nationality;
-- Q2: How many MVP winners play in the frontcourt and the backcourt?
SELECT position, COUNT(*) AS mvp_winners FROM player WHERE mvp_awards >= 1 GROUP BY position;
-- Q3: What is the average age of frontcourt and backcourt players?
SELECT position, AVG(age) AS average_age FROM player GROUP BY position;
-- Q4: How many players attended each college?
SELECT college, COUNT(*) AS players FROM player WHERE college IS NOT NULL GROUP BY college;
-- Q5: How many players were first overall picks?
SELECT COUNT(*) AS first_picks FROM player WHERE draft_pick = 1;
-- Q6: How many players were drafted in each decade?
SELECT CASE WHEN draft_year >= 2010 THEN '2010s or later' WHEN draft_year >= 2000 THEN '2000s' WHEN draft_year >= 1990 THEN '1990s' WHEN draft_year > 0 THEN 'before 1990' ELSE 'undrafted' END AS draft_decade, COUNT(*) AS players FROM player GROUP BY draft_decade;
-- Q7: How many players of each nationality have won a FIBA World Cup?
SELECT nationality, COUNT(*) AS players FROM player WHERE fiba_world_cup >= 1 GROUP BY nationality;
-- Q8: How many NBA championships have frontcourt and backcourt players won in total?
SELECT position, SUM(nba_championships) AS championships FROM player GROUP BY position;

-- QJ1: How many players does each team have?
SELECT team.team_name, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name;

-- QJ2: How many NBA championships have each team's players won in total?
SELECT team.team_name, SUM(player.nba_championships) AS titles_won_by_players FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name;

-- QJ3: How many MVP winners does each team have?
SELECT team.team_name, COUNT(*) AS mvp_winners FROM player JOIN team ON player.team = team.team_name WHERE player.mvp_awards >= 1 GROUP BY team.team_name;

-- QJ4: What is the average age of each team's players?
SELECT team.team_name, AVG(player.age) AS average_age FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name;

-- QJ5: What is the best (lowest) draft pick on each team?
SELECT team.team_name, MIN(player.draft_pick) AS best_draft_pick FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name;

-- QJ6: How many non-American players does each team have?
SELECT team.team_name, COUNT(*) AS international_players FROM player JOIN team ON player.team = team.team_name WHERE player.nationality <> 'American' GROUP BY team.team_name;

-- QJ7: How many players play for teams in each state?
SELECT city.state_name, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name GROUP BY city.state_name;

-- QJ8: How many Olympic gold medals do the players of each state's teams hold?
SELECT city.state_name, SUM(player.olympic_gold_medals) AS olympic_golds FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name GROUP BY city.state_name;

-- QJ9: How many MVP awards have the players of each state's teams won?
SELECT city.state_name, SUM(player.mvp_awards) AS mvp_awards FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name GROUP BY city.state_name;

-- QJ10: How many frontcourt and backcourt players play in California?
SELECT player.position, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE city.state_name = 'California' GROUP BY player.position;

-- QJ11: Are players on older franchises (founded before 1970) older on average?
SELECT CASE WHEN team.founded_year < 1970 THEN 'founded before 1970' ELSE 'founded 1970 or later' END AS franchise_age, AVG(player.age) AS average_age, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name GROUP BY franchise_age;

-- QJ12: How many players does each owner have under contract?
SELECT team.ownership, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name GROUP BY team.ownership;

-- QJ13: Which home cities' teams have the most players with at least one NBA title?
SELECT team.location, COUNT(*) AS champions FROM player JOIN team ON player.team = team.team_name WHERE player.nba_championships >= 1 GROUP BY team.location;

-- QJ14: How many teams are there in each state?
SELECT city.state_name, COUNT(*) AS teams FROM team JOIN city ON team.location = city.city_name GROUP BY city.state_name;

-- QJ15: How many championships have the teams of each state won?
SELECT city.state_name, SUM(CAST(team.championship AS INTEGER)) AS championships FROM team JOIN city ON team.location = city.city_name GROUP BY city.state_name;

-- QJ16: When was the oldest team in each state founded?
SELECT city.state_name, MIN(team.founded_year) AS oldest_founding FROM team JOIN city ON team.location = city.city_name GROUP BY city.state_name;

-- QJ17: How many teams play in cities of more than one million people?
SELECT COUNT(*) AS teams_in_big_cities FROM team JOIN city ON team.location = city.city_name WHERE city.population > 1000000;

-- QJ18: What is the average population of the cities that host a team, per state?
SELECT city.state_name, AVG(city.population) AS average_population FROM team JOIN city ON team.location = city.city_name GROUP BY city.state_name;

-- QJ19: How many teams does each owner nationality own?
SELECT owner.nationality, COUNT(*) AS teams FROM team JOIN owner ON team.ownership = owner.name GROUP BY owner.nationality;

-- QJ20: How many championships have the teams of owners of each nationality won?
SELECT owner.nationality, SUM(CAST(team.championship AS INTEGER)) AS championships FROM team JOIN owner ON team.ownership = owner.name GROUP BY owner.nationality;
