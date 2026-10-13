-- Realistic relational questions over NBA players, teams, cities and owners, v2 (2026-10-13).
-- Q1: Per nationality group and position: how many players, and how old on average?
SELECT CASE WHEN nationality = 'American' THEN 'American' ELSE 'international' END AS origin, position, COUNT(*) AS players, AVG(age) AS average_age FROM player WHERE position IN ('Frontcourt', 'Backcourt') GROUP BY origin, position;
-- Q2: Per position: how many players, MVP winners and NBA champions?
SELECT position, COUNT(*) AS players, SUM(CASE WHEN mvp_awards >= 1 THEN 1 ELSE 0 END) AS mvp_winners, SUM(CASE WHEN nba_championships >= 1 THEN 1 ELSE 0 END) AS champions FROM player WHERE position IN ('Frontcourt', 'Backcourt') GROUP BY position;
-- Q3: Which five colleges produced the most NBA champions?
SELECT college, COUNT(*) AS champions FROM player WHERE nba_championships >= 1 AND college IS NOT NULL GROUP BY college ORDER BY champions DESC LIMIT 5;
-- Q4: Per draft decade: how many players, and how many were top-10 picks?
SELECT CASE WHEN draft_year >= 2010 THEN '2010s or later' WHEN draft_year >= 2000 THEN '2000s' WHEN draft_year >= 1990 THEN '1990s' WHEN draft_year > 0 THEN 'before 1990' ELSE 'undrafted' END AS draft_decade, COUNT(*) AS players, SUM(CASE WHEN draft_pick BETWEEN 1 AND 10 THEN 1 ELSE 0 END) AS top_10_picks FROM player GROUP BY draft_decade;
-- Q5: For nationalities with at least two players: how many players have won a FIBA World Cup and an Olympic gold medal?
SELECT nationality, SUM(CASE WHEN fiba_world_cup >= 1 THEN 1 ELSE 0 END) AS world_cup_winners, SUM(CASE WHEN olympic_gold_medals >= 1 THEN 1 ELSE 0 END) AS olympic_champions FROM player WHERE nationality IS NOT NULL AND nationality <> '' GROUP BY nationality HAVING COUNT(*) >= 2;
-- Q6: Per team: how many players, their average age, and how many NBA titles they have won?
SELECT team.team_name, COUNT(*) AS players, AVG(player.age) AS average_age, SUM(player.nba_championships) AS titles_won_by_players FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name;
-- Q7: Which teams have at least three players, ordered by their players' average age?
SELECT team.team_name, COUNT(*) AS players, AVG(player.age) AS average_age FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name HAVING COUNT(*) >= 3 ORDER BY average_age DESC;
-- Q8: Per team: how many MVP winners and international players?
SELECT team.team_name, SUM(CASE WHEN player.mvp_awards >= 1 THEN 1 ELSE 0 END) AS mvp_winners, SUM(CASE WHEN player.nationality <> 'American' THEN 1 ELSE 0 END) AS international FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name;
-- Q9: Per team: what is the best draft pick among its drafted players, and how many were drafted?
SELECT team.team_name, MIN(player.draft_pick) AS best_pick, COUNT(*) AS drafted FROM player JOIN team ON player.team = team.team_name WHERE player.draft_pick > 0 GROUP BY team.team_name;
-- Q10: Per state: how many players, MVP winners and Olympic gold medals?
SELECT city.state_name, COUNT(*) AS players, SUM(CASE WHEN player.mvp_awards >= 1 THEN 1 ELSE 0 END) AS mvp_winners, SUM(player.olympic_gold_medals) AS olympic_golds FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name GROUP BY city.state_name;
-- Q11: Which five states' teams have won the most NBA titles through their players?
SELECT city.state_name, SUM(player.nba_championships) AS titles FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name GROUP BY city.state_name ORDER BY titles DESC LIMIT 5;
-- Q12: For California and Texas teams: how many frontcourt and backcourt players are there?
SELECT city.state_name, player.position, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE city.state_name IN ('California', 'Texas') AND player.position IN ('Frontcourt', 'Backcourt') GROUP BY city.state_name, player.position;
-- Q13: Do players on franchises founded before 1970 differ in age and titles?
SELECT CASE WHEN team.founded_year < 1970 THEN 'founded before 1970' ELSE 'founded 1970 or later' END AS franchise_age, COUNT(*) AS players, AVG(player.age) AS average_age, SUM(player.nba_championships) AS titles FROM player JOIN team ON player.team = team.team_name GROUP BY franchise_age;
-- Q14: Per owner: how many players, and how many NBA titles have they won?
SELECT team.ownership, COUNT(*) AS players, SUM(player.nba_championships) AS titles FROM player JOIN team ON player.team = team.team_name WHERE team.ownership IS NOT NULL GROUP BY team.ownership;
-- Q15: Which teams' players have won more NBA titles than the team itself?
SELECT team.team_name, SUM(player.nba_championships) AS titles_won_by_players, MAX(CAST(team.championship AS INTEGER)) AS team_titles FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name HAVING SUM(player.nba_championships) > MAX(CAST(team.championship AS INTEGER));
-- Q16: Per team: how many players are older than the league's average age?
SELECT team.team_name, COUNT(*) AS older_players FROM player JOIN team ON player.team = team.team_name WHERE player.age > (SELECT AVG(age) FROM player) GROUP BY team.team_name;
-- Q17: Per state: how many teams, their total championships, and their oldest founding year?
SELECT city.state_name, COUNT(*) AS teams, SUM(CAST(team.championship AS INTEGER)) AS championships, MIN(team.founded_year) AS oldest_founding FROM team JOIN city ON team.location = city.city_name GROUP BY city.state_name;
-- Q18: Which states host teams in cities of more than a million people, and how many such teams?
SELECT city.state_name, COUNT(*) AS teams, AVG(city.population) AS average_population FROM team JOIN city ON team.location = city.city_name WHERE city.population > 1000000 GROUP BY city.state_name;
-- Q19: Per owner nationality: how many teams, and how many championships have they won?
SELECT owner.nationality, COUNT(*) AS teams, SUM(CAST(team.championship AS INTEGER)) AS championships FROM team JOIN owner ON team.ownership = owner.name GROUP BY owner.nationality;
-- Q20: Per owner nationality: how many players do their teams have, and how old are they on average?
SELECT owner.nationality, COUNT(*) AS players, AVG(player.age) AS average_age FROM player JOIN team ON player.team = team.team_name JOIN owner ON team.ownership = owner.name GROUP BY owner.nationality;
-- Q21: How many players were first overall picks?
SELECT COUNT(*) AS first_picks FROM player WHERE draft_pick = 1;
