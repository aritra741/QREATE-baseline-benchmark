-- Query 1: test (agg_only) id=agg_only_art_gen_14
SELECT century, SUM(age) AS sum_age FROM art GROUP BY century;

-- Query 2: test (agg_only) id=agg_only_art_gen_51
SELECT marriage, MIN(age) AS min_age FROM art GROUP BY marriage;

-- Query 3: test (agg_only) id=agg_queries_Art_8
SELECT birth_continent, SUM(age) AS sum_age FROM art GROUP BY birth_continent;

-- Query 4: test (agg_only) id=agg_queries_Art_7
SELECT color, MAX(age) AS max_age FROM art GROUP BY color;

-- Query 5: test (agg_only) id=agg_only_art_gen_43
SELECT field, AVG(age) AS avg_age FROM art GROUP BY field;

-- Query 6: test (agg_filter) id=agg_filter_art_gen_199
SELECT zodiac, MAX(age) AS max_age FROM art WHERE age > 0 GROUP BY zodiac;

-- Query 7: test (agg_filter) id=agg_filter_art_gen_70
SELECT birth_continent, MIN(age) AS min_age FROM art WHERE teaching = 1 GROUP BY birth_continent;

-- Query 8: test (agg_filter) id=agg_filter_art_gen_95
SELECT birth_continent, MAX(age) AS max_age FROM art WHERE teaching = 1 GROUP BY birth_continent;

-- Query 9: test (agg_filter) id=agg_filter_art_gen_947
SELECT field, MIN(age) AS min_age FROM art WHERE teaching = 1 GROUP BY field;

-- Query 10: test (agg_filter) id=agg_filter_art_gen_919
SELECT art_movement, SUM(age) AS sum_age FROM art WHERE marriage = 'Married' GROUP BY art_movement;
