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
