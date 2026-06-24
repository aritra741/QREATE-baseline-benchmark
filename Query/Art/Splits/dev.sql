-- Query 1: dev (agg_only) id=agg_only_art_gen_2
SELECT birth_continent, MAX(age) AS max_age FROM art GROUP BY birth_continent;

-- Query 2: dev (agg_only) id=agg_only_art_gen_42
SELECT field, MAX(age) AS max_age FROM art GROUP BY field;

-- Query 3: dev (agg_only) id=agg_queries_Art_4
SELECT color, AVG(age) AS avg_age FROM art GROUP BY color;

-- Query 4: dev (agg_only) id=agg_only_art_gen_39
SELECT art_movement, SUM(age) AS sum_age FROM art GROUP BY art_movement;

-- Query 5: dev (agg_only) id=agg_only_art_gen_36
SELECT art_movement, MIN(age) AS min_age FROM art GROUP BY art_movement;

-- Query 6: dev (agg_filter) id=agg_filter_art_gen_698
SELECT nationality, MIN(age) AS min_age FROM art WHERE century = '20th' GROUP BY nationality;

-- Query 7: dev (agg_filter) id=agg_filter_art_gen_1067
SELECT color, MIN(age) AS min_age FROM art WHERE teaching = 1 GROUP BY color;

-- Query 8: dev (agg_filter) id=agg_filter_art_gen_1043
SELECT field, SUM(age) AS sum_age FROM art WHERE age > 0 GROUP BY field;

-- Query 9: dev (agg_filter) id=agg_filter_art_gen_623
SELECT style, MAX(age) AS max_age FROM art WHERE age > 0 GROUP BY style;

-- Query 10: dev (agg_filter) id=agg_filter_art_gen_193
SELECT zodiac, MAX(age) AS max_age FROM art WHERE teaching = 1 GROUP BY zodiac;
