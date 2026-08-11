-- Query 29 (player)
SELECT olympic_gold_medals, age, team FROM player WHERE age >= 47 OR team != 'San Antonio Spurs' OR nba_championships <= 0 OR nba_championships < 0;

-- Query 2 (manager)
SELECT age, nba_team, name FROM manager WHERE nba_team != 'Golden State Warriors' AND age >= 66;

-- Query 2 (city)
SELECT state_name, area, city_name FROM city WHERE area != 1314.80 AND population = '887642';

-- Query 36 (player)
SELECT nationality, birth_date, age FROM player WHERE (birth_date != '1994/6/6' AND nationality = 'Dutch  ') OR (nba_championships <= 2 AND age > 91);

-- Query 6 (player)
SELECT college, birth_date, draft_year FROM player WHERE birth_date = '1973/11/25';

-- Query 4 (player)
SELECT age, birth_date, team FROM player WHERE team = 'Phoenix Suns';

-- Query 3 (player)
SELECT mvp_awards, draft_pick, name FROM player WHERE mvp_awards >= 1;

-- Query 3 (manager)
SELECT age, name, nationality FROM manager WHERE age < 63 OR nationality != 'Israeli-American';

-- Query 9 (team)
SELECT championships, founded_year, location FROM team WHERE founded_year <= 1978 OR team_name = 'Dallas Mavericks' OR location != 'Minneapolis' OR team_name != 'Miami Heat';

-- Query 1 (manager)
SELECT age, nba_team, name FROM manager WHERE nba_team != 'Cleveland Cavaliers';

-- Query 32 (player)
SELECT nationality, olympic_gold_medals, fiba_world_cup FROM player WHERE (fiba_world_cup != 0 AND name = 'Erick Strickland  ') OR (birth_date != '1973/11/25' AND nba_championships >= 0);

-- Query 4 (team)
SELECT championships, founded_year, location FROM team WHERE location = 'Brooklyn' AND location = 'Memphis';

-- Query 23 (player)
SELECT fiba_world_cup, birth_date, draft_pick FROM player WHERE birth_date != '1950/1/29' AND college = 'University of Florida' AND age != 47 AND name = 'Walter Berry ';

-- Query 6 (city)
SELECT population, state_name, city_name FROM city WHERE (state_name = 'Minnesota' AND population = '887642') OR (area != 976.15 AND area != 976.15);

-- Query 26 (player)
SELECT olympic_gold_medals, college, age FROM player WHERE age > 47 OR name != 'Fran Curran Francis Hugh Curran Sr.' OR name = 'Dewayne "D. J." White, Jr.' OR fiba_world_cup = 1;

-- Query 16 (player)
SELECT olympic_gold_medals, fiba_world_cup, birth_date FROM player WHERE birth_date = '1994/4/25' OR position != 'Frontcourt';

-- Query 3 (city)
SELECT state_name, city_name, population FROM city WHERE state_name != 'Indiana' OR population != '372,624';

-- Query 10 (team)
SELECT team_name, founded_year, ownership FROM team WHERE founded_year > 1967 OR team_name != 'Charlotte Hornets' OR team_name = 'Detroit Pistons' OR founded_year >= 1989;

-- Query 35 (player)
SELECT birth_date, olympic_gold_medals, mvp_awards FROM player WHERE (birth_date = '1973/11/25' AND olympic_gold_medals != 0) OR (team = 'Miami Heat' AND nationality = 'Canadian');

-- Query 2 (player)
SELECT position, nationality, age FROM player WHERE age < 91;

-- Query 6 (team)
SELECT ownership, founded_year, championships FROM team WHERE ownership != 'Professional Basketball Club LLC, a group of Oklahoma City investors led by Clay Bennett  ' OR ownership != 'Jerry Buss (from 1979)';

-- Query 21 (player)
SELECT age, olympic_gold_medals, mvp_awards FROM player WHERE olympic_gold_medals >= 1 AND college = 'UCLA  ' AND draft_year > 2012 AND fiba_world_cup >= 0;

-- Query 31 (player)
SELECT team, nationality, fiba_world_cup FROM player WHERE (nationality = 'American-Venezuelan  ' AND position = 'Frontcourt') OR (draft_pick >= 17 AND draft_pick >= 17);

-- Query 24 (player)
SELECT nationality, draft_pick, team FROM player WHERE nationality != 'Croatian  ' AND olympic_gold_medals < 0 AND olympic_gold_medals != 0 AND mvp_awards = 0;

-- Query 1 (player)
SELECT mvp_awards, draft_pick, fiba_world_cup FROM player WHERE fiba_world_cup <= 0;

-- Query 1 (team)
SELECT founded_year, ownership, team_name FROM team WHERE ownership != '  ';

-- Query 15 (player)
SELECT fiba_world_cup, nationality, college FROM player WHERE college = 'UCLA  ' OR birth_date != '1971/12/3';

-- Query 28 (player)
SELECT draft_year, age, nationality FROM player WHERE age <= 91 OR team = 'Guaros de Lara' OR mvp_awards = 0 OR olympic_gold_medals > 1;

-- Query 17 (player)
SELECT college, draft_pick, fiba_world_cup FROM player WHERE draft_pick <= 5 OR college = 'Wake Forest University';

-- Query 7 (player)
SELECT fiba_world_cup, draft_year, name FROM player WHERE draft_year <= 2017 AND fiba_world_cup > 0;

-- Query 5 (team)
SELECT founded_year, team_name, location FROM team WHERE founded_year < 1949 OR location != 'Oklahoma City';

-- Query 14 (player)
SELECT draft_year, age, fiba_world_cup FROM player WHERE draft_year <= 2017 OR olympic_gold_medals >= 0;

-- Query 33 (player)
SELECT college, age, position FROM player WHERE (age < 47 AND olympic_gold_medals <= 1) OR (team = 'Milwaukee Hawks  ' AND college = 'University of Florida  ');

-- Query 1 (city)
SELECT state_name, area, city_name FROM city WHERE area = 375.78;

-- Query 13 (player)
SELECT team, nationality, mvp_awards FROM player WHERE mvp_awards < 1 OR birth_date = '1995/10/2';

-- Query 30 (player)
SELECT position, nationality, olympic_gold_medals FROM player WHERE position != 'Frontcourt' OR draft_pick > 5 OR olympic_gold_medals < 0 OR mvp_awards = 0;

-- Query 11 (player)
SELECT fiba_world_cup, birth_date, nba_championships FROM player WHERE birth_date != '1959/6/10' AND birth_date != '1964/2/15';

-- Query 12 (team)
SELECT location, founded_year, team_name FROM team WHERE (founded_year > 1989 AND ownership != 'Gabe Plotkin and Rick Schnall') OR (ownership = ' ' AND founded_year = 1967);

-- Query 5 (manager)
SELECT own_year, age, nationality FROM manager WHERE age <= 76 OR name = 'Joseph Chung-Hsin Tsai' OR own_year != 2012 OR own_year = 2017;

-- Query 18 (player)
SELECT olympic_gold_medals, nba_championships, age FROM player WHERE olympic_gold_medals > 1 OR position != 'Frontcourt';

-- Query 5 (city)
SELECT gdp, state_name, population FROM city WHERE state_name != 'Ontario' OR city_name = 'Minneapolis' OR gdp != '102,000,000,000' OR gdp != ' ';

-- Query 3 (team)
SELECT founded_year, ownership, team_name FROM team WHERE ownership != 'Harris Blitzer Sports & Entertainment (HBSE)  ' AND founded_year >= 1967;

-- Query 10 (player)
SELECT age, birth_date, college FROM player WHERE age > 91 AND mvp_awards > 0;

-- Query 4 (city)
SELECT gdp, area, state_name FROM city WHERE area = 976.15 AND gdp != '473,000' AND area = 375.78 AND population = '808988';

-- Query 2 (team)
SELECT ownership, championships, founded_year FROM team WHERE founded_year < 1989;

-- Query 19 (player)
SELECT fiba_world_cup, draft_pick, draft_year FROM player WHERE draft_pick >= 17 AND age >= 47 AND mvp_awards <= 0 AND mvp_awards < 1;

-- Query 34 (player)
SELECT nationality, name, draft_year FROM player WHERE (draft_year != 2017 AND nationality != 'Croatian  ') OR (name = 'Donta Hall  ' AND nba_championships != 0);

-- Query 20 (player)
SELECT name, nba_championships, college FROM player WHERE nba_championships > 2 AND olympic_gold_medals >= 0 AND olympic_gold_medals != 1 AND name != 'Toby Kimball  ';

