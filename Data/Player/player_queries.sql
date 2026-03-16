SELECT t.team_name, t.founded_year, t.championship, SUM(p.nba_championships)
FROM team t
LEFT JOIN player p ON t.team_name = p.team
WHERE t.location = 'Los Angeles' OR t.location = 'Boston'
   OR t.championship > 15
   OR p.nba_championships < 12
GROUP BY t.team_name;

SELECT position, college, COUNT(*)
FROM player
WHERE position = 'Frontcourt' 
  OR college = 'University of Minnesota'
GROUP BY position, college;

SELECT draft_year, MIN(birth_date), AVG(draft_pick)
FROM player
WHERE birth_date > '1990/01/01'
  AND draft_pick < 30
GROUP BY draft_year;

SELECT nationality, AVG(age), SUM(mvp_awards), SUM(olympic_gold_medals), SUM(fiba_world_cup)
FROM player
WHERE nationality = 'Serbian'
   OR nationality = 'Greek and Nigerian'
   OR mvp_awards < 7
   OR olympic_gold_medals <= 3
   OR fiba_world_cup <= 2
GROUP BY nationality;

SELECT t.location, c.state_name, MAX(c.population), SUM(c.area), AVG(c.gdp)
FROM team t
JOIN city c ON t.location = c.city_name
WHERE c.area < 340 
   OR c.population > 1000000
   OR c.gdp > 200000
GROUP BY t.location;

SELECT o.nba_team, o.name, o.age, MIN(o.own_year), t.ownership
FROM owner o
JOIN team t ON o.nba_team = t.team_name
WHERE o.own_year > 2010.0 
   OR o.age > 80
GROUP BY o.nba_team;

SELECT nationality, AVG(age), COUNT(*)
FROM owner
WHERE nationality = 'American'
GROUP BY nationality;

SELECT p.name, t.team_name, c.city_name
FROM player p
JOIN team t ON p.team = t.team_name
JOIN city c ON t.location = c.city_name
WHERE p.name = 'Anthony Marshon Davis Jr.' 
   OR p.name = 'LeBron Raymone James Sr.';

SELECT t.team_name, t.championship, t.founded_year, o.name, o.nationality, AVG(o.age)
FROM team t
JOIN owner o ON t.ownership = o.name
WHERE t.championship > 5
   OR o.own_year > 2000
GROUP BY t.team_name;

SELECT p.name, p.nationality, t.team_name, o.name, MAX(p.mvp_awards)
FROM player p
JOIN team t ON p.team = t.team_name
JOIN owner o ON t.ownership = o.name
WHERE p.age > 25
   OR o.nationality = 'American'
GROUP BY p.nationality;

SELECT t.team_name, t.location, c.city_name, c.state_name, o.name, SUM(t.championship)
FROM team t
JOIN city c ON t.location = c.city_name
JOIN owner o ON t.ownership = o.name
WHERE c.population > 500000
   OR o.own_year > 2005
GROUP BY t.team_name;

SELECT p.name, p.nationality, t.team_name, o.name, c.city_name, c.state_name, COUNT(*)
FROM player p
JOIN team t ON p.team = t.team_name
JOIN owner o ON t.ownership = o.name
JOIN city c ON t.location = c.city_name
WHERE p.draft_year > 2000
   OR c.population > 1000000
GROUP BY t.team_name;
