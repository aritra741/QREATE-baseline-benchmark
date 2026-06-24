-- Query 1: train (agg_only) id=agg_only_art_gen_37
SELECT art_movement, MAX(age) AS max_age FROM art GROUP BY art_movement;

-- Query 2: train (agg_only) id=agg_queries_Art_10
SELECT color, MIN(age) AS min_age FROM art GROUP BY color;

-- Query 3: train (agg_only) id=agg_only_art_gen_53
SELECT marriage, AVG(age) AS avg_age FROM art GROUP BY marriage;

-- Query 4: train (agg_only) id=agg_only_art_gen_10
SELECT century, COUNT(name) AS count_artists FROM art GROUP BY century;

-- Query 5: train (agg_only) id=agg_only_art_gen_50
SELECT marriage, COUNT(name) AS count_artists FROM art GROUP BY marriage;

-- Query 6: train (agg_only) id=agg_only_art_gen_35
SELECT art_movement, COUNT(name) AS count_artists FROM art GROUP BY art_movement;

-- Query 7: train (agg_only) id=agg_only_art_gen_49
SELECT color, SUM(age) AS sum_age FROM art GROUP BY color;

-- Query 8: train (agg_only) id=agg_only_art_gen_44
SELECT field, SUM(age) AS sum_age FROM art GROUP BY field;

-- Query 9: train (agg_only) id=agg_only_art_gen_13
SELECT century, AVG(age) AS avg_age FROM art GROUP BY century;

-- Query 10: train (agg_only) id=agg_queries_Art_9
SELECT birth_continent, MIN(age) AS min_age FROM art GROUP BY birth_continent;

-- Query 11: train (agg_only) id=agg_only_art_gen_11
SELECT century, MIN(age) AS min_age FROM art GROUP BY century;

-- Query 12: train (agg_only) id=agg_only_art_gen_12
SELECT century, MAX(age) AS max_age FROM art GROUP BY century;

-- Query 13: train (agg_only) id=agg_only_art_gen_41
SELECT field, MIN(age) AS min_age FROM art GROUP BY field;

-- Query 14: train (agg_only) id=agg_only_art_gen_45
SELECT color, COUNT(name) AS count_artists FROM art GROUP BY color;

-- Query 15: train (agg_only) id=agg_only_art_gen_40
SELECT field, COUNT(name) AS count_artists FROM art GROUP BY field;

-- Query 16: train (agg_only) id=agg_only_art_gen_3
SELECT birth_continent, AVG(age) AS avg_age FROM art GROUP BY birth_continent;

-- Query 17: train (agg_only) id=agg_only_art_gen_38
SELECT art_movement, AVG(age) AS avg_age FROM art GROUP BY art_movement;

-- Query 18: train (agg_only) id=agg_queries_Art_3
SELECT image_genre, AVG(age) AS avg_age FROM art GROUP BY image_genre;

-- Query 19: train (agg_only) id=agg_only_art_gen_52
SELECT marriage, MAX(age) AS max_age FROM art GROUP BY marriage;

-- Query 20: train (agg_only) id=agg_only_art_gen_0
SELECT birth_continent, COUNT(name) AS count_artists FROM art GROUP BY birth_continent;

-- Query 21: train (agg_filter) id=agg_filter_art_gen_1152
SELECT color, SUM(age) AS sum_age FROM art WHERE tone = 'Warm' GROUP BY color;

-- Query 22: train (agg_filter) id=agg_filter_art_gen_179
SELECT zodiac, MAX(age) AS max_age FROM art WHERE birth_continent = 'Europe' GROUP BY zodiac;

-- Query 23: train (agg_filter) id=agg_filter_art_gen_426
SELECT tone, AVG(age) AS avg_age FROM art WHERE age > 0 GROUP BY tone;

-- Query 24: train (agg_filter) id=mixed_queries_2
SELECT nationality, COUNT(birth_continent) AS count_birth_continent FROM art WHERE nationality = 'Japanese' AND birth_continent != 'Australia' GROUP BY nationality;

-- Query 25: train (agg_filter) id=agg_filter_art_gen_479
SELECT teaching, MIN(age) AS min_age FROM art WHERE age > 0 GROUP BY teaching;

-- Query 26: train (agg_filter) id=agg_filter_art_gen_217
SELECT zodiac, AVG(age) AS avg_age FROM art WHERE teaching = 1 GROUP BY zodiac;

-- Query 27: train (agg_filter) id=agg_filter_art_gen_1092
SELECT color, MAX(age) AS max_age FROM art WHERE tone = 'Warm' GROUP BY color;

-- Query 28: train (agg_filter) id=agg_filter_art_gen_1187
SELECT marriage, MIN(age) AS min_age FROM art WHERE teaching = 1 GROUP BY marriage;

-- Query 29: train (agg_filter) id=mixed_queries_5
SELECT color, MAX(awards) AS max_awards FROM art WHERE awards > 0 OR birth_country = 'Kingdom of Hungary' OR birth_country = 'Italy' GROUP BY color;

-- Query 30: train (agg_filter) id=mixed_queries_3
SELECT genre, AVG(age) AS avg_age FROM art WHERE birth_country = 'British India' OR teaching != 0 GROUP BY genre;

-- Query 31: train (agg_filter) id=agg_filter_art_gen_510
SELECT teaching, MAX(age) AS max_age FROM art WHERE age < 50 GROUP BY teaching;

-- Query 32: train (agg_filter) id=agg_filter_art_gen_538
SELECT teaching, AVG(age) AS avg_age FROM art WHERE age < 50 GROUP BY teaching;

-- Query 33: train (agg_filter) id=agg_filter_art_gen_1037
SELECT field, SUM(age) AS sum_age FROM art WHERE teaching = 1 GROUP BY field;

-- Query 34: train (agg_filter) id=agg_filter_art_gen_799
SELECT nationality, SUM(age) AS sum_age FROM art WHERE marriage = 'Married' GROUP BY nationality;

-- Query 35: train (agg_filter) id=agg_filter_art_gen_420
SELECT tone, AVG(age) AS avg_age FROM art WHERE teaching = 1 GROUP BY tone;

-- Query 36: train (agg_filter) id=agg_filter_art_gen_482
SELECT teaching, MIN(age) AS min_age FROM art WHERE age < 50 GROUP BY teaching;

-- Query 37: train (agg_filter) id=agg_filter_art_gen_247
SELECT zodiac, SUM(age) AS sum_age FROM art WHERE age > 0 GROUP BY zodiac;

-- Query 38: train (agg_filter) id=agg_filter_art_gen_475
SELECT teaching, MIN(age) AS min_age FROM art WHERE marriage = 'Married' GROUP BY teaching;

-- Query 39: train (agg_filter) id=agg_filter_art_gen_219
SELECT zodiac, AVG(age) AS avg_age FROM art WHERE marriage = 'Married' GROUP BY zodiac;

-- Query 40: train (agg_filter) id=agg_filter_art_gen_942
SELECT field, MIN(age) AS min_age FROM art WHERE tone = 'Warm' GROUP BY field;
