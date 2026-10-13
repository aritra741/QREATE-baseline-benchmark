-- Realistic relational questions over artist biographies, v2 (2026-10-13).
-- Q1: Per birth continent: how many artists, their average age, their total awards, and how many taught?
SELECT birth_continent, COUNT(*) AS artists, AVG(age) AS average_age, SUM(awards) AS total_awards, SUM(teaching) AS teachers FROM art WHERE birth_continent IS NOT NULL GROUP BY birth_continent;
-- Q2: How many artists are there for each continent and century?
SELECT birth_continent, century, COUNT(*) AS artists FROM art WHERE birth_continent IS NOT NULL GROUP BY birth_continent, century;
-- Q3: Which ten birth countries have the most award-winning artists?
SELECT birth_country, COUNT(*) AS award_winners FROM art WHERE awards >= 1 GROUP BY birth_country ORDER BY award_winners DESC, birth_country LIMIT 10;
-- Q4: For nationalities with at least 20 artists, how many awards does an artist win on average?
SELECT nationality, COUNT(*) AS artists, AVG(awards) AS average_awards FROM art WHERE nationality IS NOT NULL AND nationality <> '' GROUP BY nationality HAVING COUNT(*) >= 20;
-- Q5: Painters, sculptors, photographers and others: how many, how many awards on average, and how old on average?
SELECT CASE WHEN field LIKE '%Painting%' THEN 'Painting' WHEN field LIKE '%Sculpture%' THEN 'Sculpture' WHEN field LIKE '%Photography%' THEN 'Photography' ELSE 'Other' END AS main_field, COUNT(*) AS artists, AVG(awards) AS average_awards, AVG(age) AS average_age FROM art GROUP BY main_field;
-- Q6: Per century: what share of artists taught, and how old did they get on average?
SELECT century, AVG(teaching) AS share_who_taught, AVG(age) AS average_age FROM art WHERE century IS NOT NULL GROUP BY century;
-- Q7: From which birth countries did more than ten artists die abroad?
SELECT birth_country, COUNT(*) AS died_abroad FROM art WHERE death_country IS NOT NULL AND death_country <> birth_country GROUP BY birth_country HAVING COUNT(*) > 10;
-- Q8: For Impressionists, Expressionists, Surrealists and Abstract Expressionists: how many, how old, and how many awards on average?
SELECT CASE WHEN style LIKE '%Abstract Expressionism%' THEN 'Abstract Expressionism' WHEN style LIKE '%Impressionism%' THEN 'Impressionism' WHEN style LIKE '%Expressionism%' THEN 'Expressionism' WHEN style LIKE '%Surrealism%' THEN 'Surrealism' ELSE 'Other' END AS movement, COUNT(*) AS artists, AVG(age) AS average_age, AVG(awards) AS average_awards FROM art GROUP BY movement;
-- Q9: By marital status: how old did artists get, and how many awards did they win on average?
SELECT marriage, COUNT(*) AS artists, AVG(age) AS average_age, AVG(awards) AS average_awards FROM art WHERE marriage IS NOT NULL GROUP BY marriage;
-- Q10: Which five cities were the most artists born in?
SELECT birth_city, COUNT(*) AS artists FROM art WHERE birth_city IS NOT NULL GROUP BY birth_city ORDER BY artists DESC LIMIT 5;
-- Q11: Per continent: how many artists were born in the 1800s and how many in the 1900s?
SELECT birth_continent, SUM(CASE WHEN birth_date LIKE '18%' THEN 1 ELSE 0 END) AS born_1800s, SUM(CASE WHEN birth_date LIKE '19%' THEN 1 ELSE 0 END) AS born_1900s FROM art WHERE birth_continent IS NOT NULL GROUP BY birth_continent;
-- Q12: For each century and main field, how many awards does an artist win on average?
SELECT century, CASE WHEN field LIKE '%Painting%' THEN 'Painting' WHEN field LIKE '%Sculpture%' THEN 'Sculpture' ELSE 'Other' END AS main_field, AVG(awards) AS average_awards FROM art WHERE century IS NOT NULL GROUP BY century, main_field;
-- Q13: Where did European-born artists most often die?
SELECT death_city, COUNT(*) AS artists FROM art WHERE birth_continent = 'Europe' AND death_city IS NOT NULL GROUP BY death_city ORDER BY artists DESC LIMIT 10;
-- Q14: For color tones used by at least 20 artists, how many awards do those artists win on average?
SELECT tone, COUNT(*) AS artists, AVG(awards) AS average_awards FROM art WHERE tone IS NOT NULL GROUP BY tone HAVING COUNT(*) >= 20;
-- Q15: How many portrait, landscape and still-life artists come from each continent?
SELECT birth_continent, CASE WHEN image_genre LIKE '%Portrait%' THEN 'Portrait' WHEN image_genre LIKE '%Landscape%' THEN 'Landscape' WHEN image_genre LIKE '%Still Life%' THEN 'Still life' ELSE 'Other' END AS genre_group, COUNT(*) AS artists FROM art WHERE birth_continent IS NOT NULL GROUP BY birth_continent, genre_group;
-- Q16: Per continent, how many artists won more awards than the average artist?
SELECT birth_continent, COUNT(*) AS artists FROM art WHERE awards > (SELECT AVG(awards) FROM art) GROUP BY birth_continent;
-- Q17: For the ten nationalities with the most artists: how many artists, and the most awards won by one of them?
SELECT nationality, COUNT(*) AS artists, MAX(awards) AS most_awards FROM art WHERE nationality IS NOT NULL AND nationality <> '' GROUP BY nationality ORDER BY artists DESC, nationality LIMIT 10;
-- Q18: How many works have a balanced, asymmetrical, centralized or other composition, per century?
SELECT century, CASE WHEN composition LIKE '%Balanced%' THEN 'Balanced' WHEN composition LIKE '%Asymmetrical%' THEN 'Asymmetrical' WHEN composition LIKE '%Central%' THEN 'Centralized' ELSE 'Other' END AS composition_group, COUNT(*) AS artists FROM art WHERE century IS NOT NULL GROUP BY century, composition_group;
-- Q19: How many artists were born in Paris?
SELECT COUNT(*) AS artists FROM art WHERE birth_city LIKE '%Paris%';
-- Q20: How old did artists of each zodiac sign get on average?
SELECT zodiac, COUNT(*) AS artists, AVG(age) AS average_age FROM art WHERE zodiac IS NOT NULL GROUP BY zodiac;
