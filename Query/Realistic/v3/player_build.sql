-- Realistic build questions over NBA players, teams and cities, v3 (2026-10-13): asked before the table was built, initial-build columns only.
-- QB1: Per position: how many players, how old are they on average, and how old are the youngest and the oldest?
SELECT position, COUNT(*) AS players, AVG(age) AS average_age, MIN(age) AS youngest_age, MAX(age) AS oldest_age FROM player WHERE position IN ('Frontcourt', 'Backcourt') GROUP BY position;
-- QB2: Per position: how many MVP awards and Olympic gold medals have the players won in total?
SELECT position, SUM(mvp_awards) AS total_mvp_awards, SUM(olympic_gold_medals) AS total_olympic_gold_medals FROM player WHERE position IN ('Frontcourt', 'Backcourt') GROUP BY position;
-- QB3: Per age bracket: how many players, how many MVP winners and how many Olympic gold medalists?
SELECT CASE WHEN age < 25 THEN 'under 25' WHEN age < 30 THEN '25 to 29' WHEN age < 35 THEN '30 to 34' WHEN age < 50 THEN '35 to 49' ELSE '50 or older' END AS age_bracket, COUNT(*) AS players, SUM(CASE WHEN mvp_awards >= 1 THEN 1 ELSE 0 END) AS mvp_winners, SUM(CASE WHEN CAST(olympic_gold_medals AS INTEGER) >= 1 THEN 1 ELSE 0 END) AS olympic_gold_medalists FROM player GROUP BY age_bracket;
-- QB4: American versus international players: how many players, how many have an Olympic gold medal, and how many gold medals in total?
SELECT CASE WHEN nationality = 'American' THEN 'American' ELSE 'international' END AS origin, COUNT(*) AS players, SUM(CASE WHEN CAST(olympic_gold_medals AS INTEGER) >= 1 THEN 1 ELSE 0 END) AS gold_medalists, SUM(olympic_gold_medals) AS total_olympic_gold_medals FROM player WHERE nationality IS NOT NULL AND nationality <> '' GROUP BY origin;
-- QB5: By number of Olympic gold medals (none, one, two or more): how many players, how old on average, and how many MVP awards?
SELECT CASE WHEN CAST(olympic_gold_medals AS INTEGER) = 0 THEN 'none' WHEN CAST(olympic_gold_medals AS INTEGER) = 1 THEN 'one' ELSE 'two or more' END AS olympic_golds, COUNT(*) AS players, AVG(age) AS average_age, SUM(mvp_awards) AS total_mvp_awards FROM player WHERE olympic_gold_medals IS NOT NULL AND olympic_gold_medals <> '' GROUP BY olympic_golds;
-- QB6: By number of MVP awards (none, one, several): how many players, how old on average, and how many Olympic gold medals?
SELECT CASE WHEN mvp_awards = 0 THEN 'none' WHEN mvp_awards = 1 THEN 'one' ELSE 'several' END AS mvp_count, COUNT(*) AS players, AVG(age) AS average_age, SUM(olympic_gold_medals) AS total_olympic_gold_medals FROM player GROUP BY mvp_count;
-- QB7: Per origin (American or international) and age group (under 30, 30 or older): how many players?
SELECT CASE WHEN nationality = 'American' THEN 'American' ELSE 'international' END AS origin, CASE WHEN age < 30 THEN 'under 30' ELSE '30 or older' END AS age_group, COUNT(*) AS players FROM player WHERE nationality IS NOT NULL AND nationality <> '' GROUP BY origin, age_group;
-- QB8: Per position and MVP status: how many players, and how old are they on average?
SELECT position, CASE WHEN mvp_awards >= 1 THEN 'MVP winner' ELSE 'no MVP' END AS mvp_status, COUNT(*) AS players, AVG(age) AS average_age FROM player WHERE position IN ('Frontcourt', 'Backcourt') GROUP BY position, mvp_status;
-- QB9: Per nationality group (only American, dual nationality including American, European, rest of the world): how many players, how old on average, and how many Olympic gold medals?
SELECT CASE WHEN nationality = 'American' THEN 'USA only' WHEN nationality LIKE '%American%' THEN 'dual nationality' WHEN nationality LIKE '%French%' OR nationality LIKE '%Greek%' OR nationality LIKE '%Serbian%' OR nationality LIKE '%Slovenian%' OR nationality LIKE '%Croatian%' OR nationality LIKE '%German%' OR nationality LIKE '%Dutch%' OR nationality LIKE '%British%' THEN 'Europe' ELSE 'rest of world' END AS region, COUNT(*) AS players, AVG(age) AS average_age, SUM(olympic_gold_medals) AS total_olympic_gold_medals FROM player WHERE nationality IS NOT NULL AND nationality <> '' GROUP BY region;
-- QB10: Per position: how many players are older than the average player?
SELECT position, COUNT(*) AS older_than_average FROM player WHERE position IN ('Frontcourt', 'Backcourt') AND age > (SELECT AVG(age) FROM player) GROUP BY position;
-- QB11: Which three states' teams have players with the most MVP awards, and how many players do those teams have?
SELECT city.state_name, COUNT(*) AS players, SUM(player.mvp_awards) AS total_mvp_awards FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE city.state_name IS NOT NULL AND city.state_name <> '' GROUP BY city.state_name ORDER BY mvp_awards DESC, city.state_name LIMIT 3;
-- QB12: Per position: how many players have won both an MVP award and an Olympic gold medal?
SELECT position, COUNT(*) AS players, SUM(CASE WHEN mvp_awards >= 1 AND CAST(olympic_gold_medals AS INTEGER) >= 1 THEN 1 ELSE 0 END) AS mvp_and_olympic_gold FROM player WHERE position IN ('Frontcourt', 'Backcourt') GROUP BY position;
-- QB13: What is the average age of players who have won an MVP award?
SELECT AVG(age) AS average_age_of_mvp_winners FROM player WHERE mvp_awards >= 1;
-- QB14: Per position and Olympic status (gold medalist or not): how many players, and how old on average?
SELECT position, CASE WHEN CAST(olympic_gold_medals AS INTEGER) >= 1 THEN 'gold medalist' ELSE 'no gold' END AS olympic_status, COUNT(*) AS players, AVG(age) AS average_age FROM player WHERE position IN ('Frontcourt', 'Backcourt') AND olympic_gold_medals IS NOT NULL AND olympic_gold_medals <> '' GROUP BY position, olympic_status;
-- QB15: For the Lakers, Celtics, Warriors and Knicks: how many players, MVP awards and Olympic gold medals?
SELECT team, COUNT(*) AS players, SUM(mvp_awards) AS total_mvp_awards, SUM(olympic_gold_medals) AS total_olympic_gold_medals FROM player WHERE team IN ('Los Angeles Lakers', 'Boston Celtics', 'Golden State Warriors', 'New York Knicks') GROUP BY team;
-- QB16: Which teams have at least five players, and how old are their players on average?
SELECT team, COUNT(*) AS players, AVG(age) AS average_age FROM player WHERE team IS NOT NULL AND team <> '' GROUP BY team HAVING COUNT(*) >= 5;
-- QB17: Which five NBA teams have players with the most MVP awards, and how many players and Olympic gold medals do they have?
SELECT team.team_name, COUNT(*) AS players, SUM(player.mvp_awards) AS total_mvp_awards, SUM(player.olympic_gold_medals) AS total_olympic_gold_medals FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name ORDER BY mvp_awards DESC, team.team_name LIMIT 5;
-- QB18: For NBA teams with at least four players: how many players, and how many championships has the team won?
SELECT team.team_name, COUNT(*) AS players, MAX(CAST(team.championship AS INTEGER)) AS team_championships FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name HAVING COUNT(*) >= 4;
-- QB19: By the team's championship record (none, one to three, four or more): how many players, how old on average, and how many MVP awards?
SELECT CASE WHEN CAST(team.championship AS INTEGER) = 0 THEN 'no titles' WHEN CAST(team.championship AS INTEGER) <= 3 THEN '1 to 3 titles' ELSE '4 or more titles' END AS team_record, COUNT(*) AS players, AVG(player.age) AS average_age, SUM(player.mvp_awards) AS total_mvp_awards FROM player JOIN team ON player.team = team.team_name GROUP BY team_record;
-- QB20: Which NBA teams have players who are older on average than the average player, and how many players do they have?
SELECT team.team_name, COUNT(*) AS players, AVG(player.age) AS average_age FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name HAVING AVG(player.age) > (SELECT AVG(age) FROM player);
-- QB21: For NBA teams with at least three players: how old are their youngest and oldest players?
SELECT team.team_name, COUNT(*) AS players, MIN(player.age) AS youngest_age, MAX(player.age) AS oldest_age FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name HAVING COUNT(*) >= 3;
-- QB22: Which NBA teams have at least one player with both an MVP award and an Olympic gold medal, and how many such players?
SELECT team.team_name, SUM(CASE WHEN player.mvp_awards >= 1 AND CAST(player.olympic_gold_medals AS INTEGER) >= 1 THEN 1 ELSE 0 END) AS mvp_and_olympic_gold FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name HAVING SUM(CASE WHEN player.mvp_awards >= 1 AND CAST(player.olympic_gold_medals AS INTEGER) >= 1 THEN 1 ELSE 0 END) >= 1;
-- QB23: For NBA teams with at least three players: how many frontcourt and how many backcourt players?
SELECT team.team_name, COUNT(*) AS players, SUM(CASE WHEN player.position = 'Frontcourt' THEN 1 ELSE 0 END) AS frontcourt, SUM(CASE WHEN player.position = 'Backcourt' THEN 1 ELSE 0 END) AS backcourt FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name HAVING COUNT(*) >= 3;
-- QB24: Per team city: how many players play there, and how many Olympic gold medals do they hold?
SELECT team.location, COUNT(*) AS players, SUM(player.olympic_gold_medals) AS total_olympic_gold_medals FROM player JOIN team ON player.team = team.team_name GROUP BY team.location;
-- QB25: Which three NBA teams have players with the most Olympic gold medals?
SELECT team.team_name, SUM(player.olympic_gold_medals) AS total_olympic_gold_medals, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name ORDER BY olympic_gold_medals DESC, team.team_name LIMIT 3;
-- QB26: By the team's championship record (no titles or at least one) and position: how many players?
SELECT CASE WHEN CAST(team.championship AS INTEGER) = 0 THEN 'no titles' ELSE 'at least one title' END AS team_record, player.position, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name WHERE player.position IN ('Frontcourt', 'Backcourt') GROUP BY team_record, player.position;
-- QB27: Per NBA team with at least three players: how many players are under 30 and how many are 30 or older?
SELECT team.team_name, SUM(CASE WHEN player.age < 30 THEN 1 ELSE 0 END) AS under_30, SUM(CASE WHEN player.age >= 30 THEN 1 ELSE 0 END) AS age_30_or_older FROM player JOIN team ON player.team = team.team_name GROUP BY team.team_name HAVING COUNT(*) >= 3;
-- QB28: By championship record (none, one to three, four or more): how many teams, and how many championships in total?
SELECT CASE WHEN CAST(championship AS INTEGER) = 0 THEN 'no titles' WHEN CAST(championship AS INTEGER) <= 3 THEN '1 to 3 titles' ELSE '4 or more titles' END AS team_record, COUNT(*) AS teams, SUM(CAST(championship AS INTEGER)) AS total_championships FROM team GROUP BY team_record;
-- QB29: Per state: how many teams, and how large is the biggest team city?
SELECT city.state_name, COUNT(*) AS teams, MAX(city.population) AS largest_city_population FROM team JOIN city ON team.location = city.city_name WHERE city.state_name IS NOT NULL AND city.state_name <> '' GROUP BY city.state_name;
-- QB30: Per state: how many teams, and how many of them have won more championships than the average team?
SELECT city.state_name, COUNT(*) AS teams, SUM(CASE WHEN CAST(team.championship AS INTEGER) > (SELECT AVG(CAST(championship AS INTEGER)) FROM team) THEN 1 ELSE 0 END) AS teams_above_average FROM team JOIN city ON team.location = city.city_name WHERE city.state_name IS NOT NULL AND city.state_name <> '' GROUP BY city.state_name;
-- QB31: By city size (under 500,000, 500,000 to 1 million, over 1 million people): how many teams, and how many championships in total and per team?
SELECT CASE WHEN city.population < 500000 THEN 'under 500k' WHEN city.population <= 1000000 THEN '500k to 1M' ELSE 'over 1M' END AS city_size, COUNT(*) AS teams, SUM(CAST(team.championship AS INTEGER)) AS total_championships, AVG(CAST(team.championship AS INTEGER)) AS championships_per_team FROM team JOIN city ON team.location = city.city_name GROUP BY city_size;
-- QB32: For states with at least two teams: how many championships in total, and the most won by one team?
SELECT city.state_name, COUNT(*) AS teams, SUM(CAST(team.championship AS INTEGER)) AS total_championships, MAX(CAST(team.championship AS INTEGER)) AS most_by_one_team FROM team JOIN city ON team.location = city.city_name WHERE city.state_name IS NOT NULL AND city.state_name <> '' GROUP BY city.state_name HAVING COUNT(*) >= 2;
-- QB33: By city size (under 500,000, 500,000 to 1 million, over 1 million people): how many players, how old on average, and how many MVP awards?
SELECT CASE WHEN city.population < 500000 THEN 'under 500k' WHEN city.population <= 1000000 THEN '500k to 1M' ELSE 'over 1M' END AS city_size, COUNT(*) AS players, AVG(player.age) AS average_age, SUM(player.mvp_awards) AS total_mvp_awards FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name GROUP BY city_size;
-- QB34: Which five team cities have the most players, and how many people live there?
SELECT city.city_name, COUNT(*) AS players, MAX(city.population) AS total_population FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name GROUP BY city.city_name ORDER BY players DESC, city.city_name LIMIT 5;
-- QB35: Per state: how many frontcourt and how many backcourt players play for its teams?
SELECT city.state_name, SUM(CASE WHEN player.position = 'Frontcourt' THEN 1 ELSE 0 END) AS frontcourt, SUM(CASE WHEN player.position = 'Backcourt' THEN 1 ELSE 0 END) AS backcourt FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE city.state_name IS NOT NULL AND city.state_name <> '' GROUP BY city.state_name;
-- QB36: For states whose teams have at least three players: how old are the players on average, and how old is the oldest?
SELECT city.state_name, COUNT(*) AS players, AVG(player.age) AS average_age, MAX(player.age) AS oldest_age FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE city.state_name IS NOT NULL AND city.state_name <> '' GROUP BY city.state_name HAVING COUNT(*) >= 3;
-- QB37: By city size (over or under 1 million people) and position: how many players?
SELECT CASE WHEN city.population > 1000000 THEN 'over 1M' ELSE '1M or less' END AS city_size, player.position, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE player.position IN ('Frontcourt', 'Backcourt') GROUP BY city_size, player.position;
-- QB38: Per position: how many players play in a city larger than the average team city?
SELECT player.position, COUNT(*) AS players FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE player.position IN ('Frontcourt', 'Backcourt') AND city.population > (SELECT AVG(population) FROM city WHERE city_name IN (SELECT location FROM team)) GROUP BY player.position;
-- QB39: Per state: how many international players play for its teams, and how many players in total?
SELECT city.state_name, COUNT(*) AS players, SUM(CASE WHEN player.nationality = 'American' THEN 0 ELSE 1 END) AS international_players FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE city.state_name IS NOT NULL AND city.state_name <> '' AND player.nationality IS NOT NULL AND player.nationality <> '' GROUP BY city.state_name;
-- QB40: For the three states whose most successful team has won the most championships: how many players do the state's teams have, how many Olympic gold medals do those players hold, and how many titles has that top team won?
SELECT city.state_name, COUNT(*) AS players, SUM(player.olympic_gold_medals) AS total_olympic_gold_medals, MAX(CAST(team.championship AS INTEGER)) AS most_titles_of_one_team FROM player JOIN team ON player.team = team.team_name JOIN city ON team.location = city.city_name WHERE city.state_name IS NOT NULL AND city.state_name <> '' GROUP BY city.state_name ORDER BY most_titles_of_one_team DESC, city.state_name LIMIT 3;
