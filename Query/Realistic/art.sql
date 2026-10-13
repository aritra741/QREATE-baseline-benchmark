-- Realistic aggregate questions over artist biographies (2026-10-12).
-- Q1: How many artists were born on each continent?
SELECT birth_continent, COUNT(*) AS artists FROM art GROUP BY birth_continent;
-- Q2: What is the average age of artists born on each continent?
SELECT birth_continent, AVG(age) AS average_age FROM art GROUP BY birth_continent;
-- Q3: How many award-winning artists are there of each nationality?
SELECT nationality, COUNT(*) AS award_winners FROM art WHERE awards >= 1 GROUP BY nationality;
-- Q4: How many awards have artists from each continent won in total?
SELECT birth_continent, SUM(awards) AS total_awards FROM art GROUP BY birth_continent;
-- Q5: How many artists were born in Paris?
SELECT COUNT(*) AS artists FROM art WHERE birth_city LIKE '%Paris%';
-- Q6: How many artists died in a different country from the one they were born in?
SELECT COUNT(*) AS artists FROM art WHERE death_country IS NOT NULL AND death_country <> birth_country;
-- Q7: How many artists were active in each century?
SELECT century, COUNT(*) AS artists FROM art GROUP BY century;
-- Q8: How many artists work in painting, sculpture or photography?
SELECT CASE WHEN field LIKE '%Painting%' THEN 'Painting' WHEN field LIKE '%Sculpture%' THEN 'Sculpture' WHEN field LIKE '%Photography%' THEN 'Photography' ELSE 'Other' END AS main_field, COUNT(*) AS artists FROM art GROUP BY main_field;
-- Q9: How many artists from each continent taught at an institution?
SELECT birth_continent, SUM(teaching) AS teachers FROM art GROUP BY birth_continent;
-- Q10: Did artists who taught live longer on average?
SELECT teaching, AVG(age) AS average_age FROM art GROUP BY teaching;
-- Q11: How many Impressionists were born in each country?
SELECT birth_country, COUNT(*) AS artists FROM art WHERE style LIKE '%Impressionism%' GROUP BY birth_country;
-- Q12: How many American artists were active in each century?
SELECT century, COUNT(*) AS artists FROM art WHERE nationality = 'American' GROUP BY century;
-- Q13: How many artists' works have a balanced composition, by continent?
SELECT birth_continent, COUNT(*) AS artists FROM art WHERE composition = 'Balanced' GROUP BY birth_continent;
-- Q14: What is the most awards won by a single artist from each continent?
SELECT birth_continent, MAX(awards) AS most_awards FROM art GROUP BY birth_continent;
-- Q15: How many artists died in Paris?
SELECT COUNT(*) AS artists FROM art WHERE death_city LIKE '%Paris%';
-- Q16: How many awards do painters, sculptors and photographers win on average?
SELECT CASE WHEN field LIKE '%Painting%' THEN 'Painting' WHEN field LIKE '%Sculpture%' THEN 'Sculpture' WHEN field LIKE '%Photography%' THEN 'Photography' ELSE 'Other' END AS main_field, AVG(awards) AS average_awards FROM art GROUP BY main_field;
-- Q17: How many artists on each continent were married?
SELECT birth_continent, COUNT(*) AS married_artists FROM art WHERE marriage = 'Married' GROUP BY birth_continent;
-- Q18: How many portrait artists were born in each country?
SELECT birth_country, COUNT(*) AS artists FROM art WHERE image_genre LIKE '%Portrait%' GROUP BY birth_country;
-- Q19: How many artists were born in the 1800s?
SELECT COUNT(*) AS artists FROM art WHERE birth_date LIKE '18%';
-- Q20: How many artists died before 1950?
SELECT COUNT(*) AS artists FROM art WHERE death_date < '1950';
-- Q21: What was the average age of artists active only in the 20th century?
SELECT AVG(age) AS average_age FROM art WHERE century = '20th';
-- Q22: How many abstract artists are there per color tone?
SELECT tone, COUNT(*) AS artists FROM art WHERE genre LIKE '%Abstract%' GROUP BY tone;
