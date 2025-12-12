-- Query 1: filter1_agg1 (manager)
SELECT nationality, MIN(age) AS min_age FROM manager WHERE nba_team != 'Cleveland Cavaliers' GROUP BY nationality;

-- Query 2: filter2_agg1 (manager)
SELECT nationality, SUM(age) AS sum_age FROM manager WHERE age != 76 AND nba_team != 'Houston Rockets' GROUP BY nationality;

-- Query 3: filter3_agg1 (manager)
SELECT nationality, COUNT(age) AS count_age FROM manager WHERE name = 'Tom Gores  ' OR own_year >= 1994 GROUP BY nationality;

-- Query 4: filter4_agg1 (manager)
SELECT nationality, MAX(age) AS max_age FROM manager WHERE own_year = 2012 AND nba_team = 'New York Knicks' AND age <= 88 GROUP BY nationality;

-- Query 5: filter5_agg1 (manager)
SELECT nationality, AVG(age) AS avg_age FROM manager WHERE nationality = 'Taiwanese-Canadian' OR own_year <= 2012 OR nba_team != 'Dallas Mavericks' GROUP BY nationality;

-- Query 6: filter6_agg1 (manager)
SELECT nationality, MIN(age) AS min_age FROM manager WHERE (nba_team != 'Chicago Bulls' AND nationality = 'Israeli-American') OR (name = 'Steven Anthony Ballmer' AND age <= 63) GROUP BY nationality;

