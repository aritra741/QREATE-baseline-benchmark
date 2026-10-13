-- Realistic aggregated joins, players (draft for review, 2026-10-12). Every join feeds an aggregate; only additive
-- quantities are summed; every joined table contributes a grouped, filtered or aggregated column.

-- Q1: How many players does each team have?
SELECT team.team_name, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name;

-- Q2: How many NBA championships have each team's players won in total?
SELECT team.team_name, SUM(player.nba_championships) AS titles_won_by_players FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name;

-- Q3: How many MVP winners does each team have?
SELECT team.team_name, COUNT(*) AS mvp_winners FROM player JOIN team ON player.team = team.team_name WHERE player.mvp_awards >= 1 GROUP BY team.team_name;

-- Q4: What is the average age of each team's players?
SELECT team.team_name, AVG(player.age) AS average_age FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name;

-- Q5: What is the best (lowest) draft pick on each team?
SELECT team.team_name, MIN(player.draft_pick) AS best_draft_pick FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name;

-- Q6: How many non-American players does each team have?
SELECT team.team_name, COUNT(*) AS international_players FROM player JOIN team ON player.team = team.team_name WHERE player.nationality <> 'American' GROUP BY team.team_name;

-- Q7: How many players play for teams in each state?
SELECT city.state_name, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name GROUP BY city.state_name;

-- Q8: How many Olympic gold medals do the players of each state's teams hold?
SELECT city.state_name, SUM(player.olympic_gold_medals) AS olympic_golds FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name GROUP BY city.state_name;

-- Q9: How many MVP awards have the players of each state's teams won?
SELECT city.state_name, SUM(player.mvp_awards) AS mvp_awards FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name GROUP BY city.state_name;

-- Q10: How many frontcourt and backcourt players play in California?
SELECT player.position, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE city.state_name = 'California' GROUP BY player.position;

-- Q11: Are players on older franchises (founded before 1970) older on average?
SELECT CASE WHEN team.founded_year < 1970 THEN 'founded before 1970' ELSE 'founded 1970 or later' END AS franchise_age, AVG(player.age) AS average_age, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name GROUP BY franchise_age;

-- Q12: How many players does each owner have under contract?
SELECT team.ownership, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name GROUP BY team.ownership;

-- Q13: Which home cities' teams have the most players with at least one NBA title?
SELECT team.location, COUNT(*) AS champions FROM player JOIN team ON player.team = team.team_name WHERE player.nba_championships >= 1 GROUP BY team.location;

-- Q14: How many teams are there in each state?
SELECT city.state_name, COUNT(*) AS teams FROM team JOIN city ON team.location = city.city_name GROUP BY city.state_name;

-- Q15: How many championships have the teams of each state won?
SELECT city.state_name, SUM(CAST(team.championship AS INTEGER)) AS championships FROM team JOIN city ON team.location = city.city_name GROUP BY city.state_name;

-- Q16: When was the oldest team in each state founded?
SELECT city.state_name, MIN(team.founded_year) AS oldest_founding FROM team JOIN city ON team.location = city.city_name GROUP BY city.state_name;

-- Q17: How many teams play in cities of more than one million people?
SELECT COUNT(*) AS teams_in_big_cities FROM team JOIN city ON team.location = city.city_name WHERE city.population > 1000000;

-- Q18: What is the average population of the cities that host a team, per state?
SELECT city.state_name, AVG(city.population) AS average_population FROM team JOIN city ON team.location = city.city_name GROUP BY city.state_name;

-- Q19: How many teams does each owner nationality own?
SELECT owner.nationality, COUNT(*) AS teams FROM team JOIN owner ON team.ownership = owner.name GROUP BY owner.nationality;

-- Q20: How many championships have the teams of owners of each nationality won?
SELECT owner.nationality, SUM(CAST(team.championship AS INTEGER)) AS championships FROM team JOIN owner ON team.ownership = owner.name GROUP BY owner.nationality;
