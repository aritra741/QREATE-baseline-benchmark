"""Art contrast workloads: realistic curator / art-historian questions."""

from .common import q

DATASET = "Art"
JOIN_NOTES = None
BASELINE = "art_agg20"

FIELD_FAMILY = """
CASE
  WHEN field LIKE '%Painting%' THEN 'Painting'
  WHEN field LIKE '%Sculpture%' THEN 'Sculpture'
  WHEN field LIKE '%Photography%' THEN 'Photography'
  ELSE 'Other'
END
""".strip()

COLOR_FAMILY = """
CASE
  WHEN color IN ('Earth Tones', 'Blue', 'Green', 'Red', 'Black And White', 'Brown', 'Yellow') THEN color
  WHEN color != '' THEN 'Other'
END
""".strip()

TONE_FAMILY = """
CASE
  WHEN tone IN ('Neutral', 'Bright', 'Dark', 'Warm') THEN tone
  WHEN tone != '' THEN 'Other'
END
""".strip()

WORKLOADS = {
    "art_agg20": {
        "title": "Simple aggregation workload",
        "focus": "Single-table GROUP BY with one aggregate",
        "kind": "baseline",
        "queries": [
            q("q0", "SELECT birth_continent, COUNT(*) AS artist_count FROM art WHERE birth_continent != '' GROUP BY birth_continent", "How many artists were born on each continent?"),
            q("q1", "SELECT century, COUNT(*) AS artist_count FROM art WHERE century != '' GROUP BY century", "How many artists are associated with each century?"),
            q("q2", "SELECT CASE WHEN art_institution != '' THEN 'known_institution' ELSE 'institution_unknown' END AS institution_status, COUNT(*) AS artist_count FROM art GROUP BY institution_status", "How many artists have a known art institution versus none recorded?"),
            q("q3", "SELECT teaching, COUNT(*) AS artist_count FROM art WHERE teaching IS NOT NULL GROUP BY teaching", "How many artists have a teaching record versus none?"),
            q("q4", "SELECT century, AVG(age) AS avg_age FROM art WHERE century != '' AND age BETWEEN 25 AND 105 GROUP BY century", "What is the average age of artists associated with each century?"),
            q("q5", "SELECT birth_continent, AVG(age) AS avg_age FROM art WHERE birth_continent != '' AND age BETWEEN 25 AND 105 GROUP BY birth_continent", "What is the average age of artists born on each continent?"),
            q("q6", f"SELECT {FIELD_FAMILY} AS field_family, COUNT(*) AS artist_count FROM art WHERE field != '' GROUP BY field_family", "How many artists are primarily painters, sculptors, photographers, or something else?"),
            q("q7", "SELECT image_genre, COUNT(*) AS artist_count FROM art WHERE image_genre != '' GROUP BY image_genre HAVING COUNT(*) >= 10", "Which image genres are represented by at least ten artists, and how many artists fall into each?"),
            q("q8", "SELECT style, COUNT(*) AS artist_count FROM art WHERE style != '' GROUP BY style HAVING COUNT(*) >= 15", "Which visual styles are represented by at least fifteen artists, and how many artists use each?"),
            q("q9", f"SELECT {COLOR_FAMILY} AS color_family, COUNT(*) AS artist_count FROM art WHERE color != '' GROUP BY color_family", "How many artists have a work using each major dominant color family?"),
            q("q10", f"SELECT {TONE_FAMILY} AS tone_family, COUNT(*) AS artist_count FROM art WHERE tone != '' GROUP BY tone_family", "How many artists have a work in each major tone family?"),
            q("q11", "SELECT CASE WHEN awards >= 1 THEN 'awarded' ELSE 'unawarded' END AS award_status, COUNT(*) AS artist_count FROM art WHERE awards IS NOT NULL GROUP BY award_status", "How many artists have at least one recorded award versus none?"),
            q("q12", "SELECT birth_continent, MAX(awards) AS max_awards FROM art WHERE birth_continent != '' GROUP BY birth_continent", "What is the highest recorded award count among artists born on each continent?"),
            q("q13", "SELECT century, SUM(awards) AS total_awards FROM art WHERE century != '' GROUP BY century", "How many recorded awards are there among artists associated with each century?"),
            q("q14", "SELECT teaching, AVG(awards) AS avg_awards FROM art WHERE teaching IS NOT NULL GROUP BY teaching", "What is the average award count for artists who taught versus those who did not?"),
            q("q15", "SELECT nationality, COUNT(*) AS artist_count FROM art WHERE nationality != '' GROUP BY nationality HAVING COUNT(*) >= 10", "Which nationalities are represented by at least ten artists, and how many artists are there for each?"),
            q("q16", "SELECT birth_country, COUNT(*) AS artist_count FROM art WHERE birth_country != '' GROUP BY birth_country HAVING COUNT(*) >= 10", "Which birth countries are represented by at least ten artists, and how many artists were born in each?"),
            q("q17", "SELECT image_genre, AVG(age) AS avg_age FROM art WHERE image_genre != '' AND age BETWEEN 25 AND 105 GROUP BY image_genre HAVING COUNT(*) >= 10", "For image genres with at least ten artists of known age, what is the average age?"),
            q("q18", "SELECT style, AVG(awards) AS avg_awards FROM art WHERE style != '' GROUP BY style HAVING COUNT(*) >= 15", "For visual styles with at least fifteen artists, what is the average award count?"),
            q("q19", "SELECT century, MIN(age) AS youngest FROM art WHERE century != '' AND age BETWEEN 25 AND 105 GROUP BY century", "What is the youngest recorded age among artists associated with each century?"),
        ],
    },
    "art_filter20": {
        "title": "Selective-filter workload",
        "focus": "Selective WHERE predicates with simple aggregates",
        "kind": "pure",
        "contrast_with": BASELINE,
        "queries": [
            q("q0", f"SELECT {FIELD_FAMILY} AS field_family, COUNT(*) AS artist_count FROM art WHERE century IN ('20th', '20th-21st') AND field != '' GROUP BY field_family", "Among 20th-century and living-generation artists, how many are painters, sculptors, photographers, or something else?"),
            q("q1", "SELECT birth_continent, COUNT(*) AS artist_count FROM art WHERE awards >= 1 AND birth_continent != '' GROUP BY birth_continent", "Among artists with at least one recorded award, how many were born on each continent?"),
            q("q2", "SELECT century, COUNT(*) AS artist_count FROM art WHERE teaching = 1 AND century != '' GROUP BY century", "Among artists who taught, how many are associated with each century?"),
            q("q3", "SELECT birth_continent, AVG(age) AS avg_age FROM art WHERE awards >= 1 AND age BETWEEN 25 AND 105 AND birth_continent != '' GROUP BY birth_continent", "Among awarded artists with a recorded age, what is the average age by birth continent?"),
            q("q4", "SELECT century, COUNT(*) AS artist_count FROM art WHERE nationality IN ('American', 'French', 'British', 'German') AND age BETWEEN 40 AND 90 AND century != '' GROUP BY century", "Among American, French, British, or German artists aged 40 to 90, how many fall into each century?"),
            q("q5", f"SELECT {TONE_FAMILY} AS tone_family, COUNT(*) AS artist_count FROM art WHERE image_genre = 'Portrait' AND color IN ('Earth Tones', 'Blue', 'Red', 'Black And White') GROUP BY tone_family", "Among artists with a portrait dominated by earth tones, blue, red, or black-and-white, how many fall into each tone family?"),
            q("q6", "SELECT image_genre, COUNT(*) AS artist_count FROM art WHERE teaching = 1 AND awards = 0 AND image_genre != '' GROUP BY image_genre HAVING COUNT(*) >= 3", "Among teachers with no recorded awards, which image genres appear at least three times?"),
            q("q7", f"SELECT {COLOR_FAMILY} AS color_family, COUNT(*) AS artist_count FROM art WHERE style IN ('Expressionism', 'Impressionism', 'Surrealism', 'Realism') AND color != '' GROUP BY color_family", "Among Expressionist, Impressionist, Surrealist, or Realist artists, how many use each major color family?"),
            q("q8", "SELECT century, COUNT(*) AS artist_count FROM art WHERE awards >= 1 AND teaching = 1 AND century != '' GROUP BY century", "Among awarded artists who taught, how many are associated with each century?"),
            q("q9", "SELECT birth_continent, COUNT(*) AS artist_count FROM art WHERE field LIKE '%Painting%' AND age BETWEEN 50 AND 90 AND birth_continent != '' GROUP BY birth_continent", "Among painters aged 50 to 90, how many were born on each continent?"),
            q("q10", "SELECT century, AVG(awards) AS avg_awards FROM art WHERE art_institution != '' AND century != '' GROUP BY century", "Among artists with a known art institution, what is the average award count by century?"),
            q("q11", "SELECT century, COUNT(*) AS artist_count FROM art WHERE birth_continent = 'Europe' AND awards >= 1 AND century != '' GROUP BY century", "Among awarded European-born artists, how many are associated with each century?"),
            q("q12", f"SELECT {FIELD_FAMILY} AS field_family, COUNT(*) AS artist_count FROM art WHERE birth_country IN ('United States', 'France', 'United Kingdom', 'Germany', 'Italy') AND field != '' GROUP BY field_family", "Among artists born in the United States, France, the United Kingdom, Germany, or Italy, how many are painters, sculptors, photographers, or something else?"),
            q("q13", "SELECT style, COUNT(*) AS artist_count FROM art WHERE tone IN ('Bright', 'Dark') AND style != '' GROUP BY style HAVING COUNT(*) >= 5", "Among artists with bright- or dark-toned works, which styles appear at least five times?"),
            q("q14", "SELECT birth_continent, COUNT(*) AS artist_count FROM art WHERE death_country != '' AND death_country != birth_country AND birth_continent != '' GROUP BY birth_continent", "Among artists who died in a different country from where they were born, how many were born on each continent?"),
            q("q15", "SELECT century, COUNT(*) AS artist_count FROM art WHERE genre IN ('Abstract', 'Landscape', 'Portrait') AND century != '' GROUP BY century", "Among artists working in abstract, landscape, or portrait genres, how many are associated with each century?"),
            q("q16", "SELECT teaching, COUNT(*) AS artist_count FROM art WHERE age >= 80 AND age <= 105 AND teaching IS NOT NULL GROUP BY teaching", "Among artists aged 80 to 105, how many taught versus did not teach?"),
            q("q17", f"SELECT {TONE_FAMILY} AS tone_family, AVG(age) AS avg_age FROM art WHERE image_genre IN ('Portrait', 'Landscape', 'Still Life', 'Abstract') AND age BETWEEN 25 AND 105 GROUP BY tone_family", "Among artists of known age with a portrait, landscape, still-life, or abstract work, what is the average age for each tone family?"),
            q("q18", "SELECT nationality, COUNT(*) AS artist_count FROM art WHERE awards >= 2 AND nationality != '' GROUP BY nationality HAVING COUNT(*) >= 2", "Among artists with at least two awards, which nationalities appear at least twice?"),
            q("q19", "SELECT century, COUNT(*) AS artist_count FROM art WHERE composition LIKE '%Asymmetrical%' AND century != '' GROUP BY century", "Among artists whose work has an asymmetrical composition, how many are associated with each century?"),
        ],
    },
    "art_groupby20": {
        "title": "Group-by variety workload",
        "focus": "Diverse GROUP BY keys, including multi-column and banded groupings",
        "kind": "pure",
        "contrast_with": BASELINE,
        "queries": [
            q("q0", f"SELECT {FIELD_FAMILY} AS field_family, century, COUNT(*) AS artist_count FROM art WHERE field != '' AND century != '' GROUP BY field_family, century", "For painters, sculptors, photographers, and other artists separately, how many are associated with each century?"),
            q("q1", "SELECT birth_continent, CASE WHEN teaching = 1 THEN 'taught' ELSE 'did_not_teach' END AS teaching_status, COUNT(*) AS artist_count FROM art WHERE birth_continent != '' AND teaching IS NOT NULL GROUP BY birth_continent, teaching_status", "For each birth continent, how many artists taught versus did not teach?"),
            q("q2", "SELECT century, CASE WHEN age < 50 THEN 'under_50' WHEN age < 75 THEN '50_to_74' ELSE '75_or_older' END AS age_band, COUNT(*) AS artist_count FROM art WHERE century != '' AND age BETWEEN 25 AND 105 GROUP BY century, age_band", "For each century, how many artists are under 50, 50 to 74, or 75 and older?"),
            q("q3", f"SELECT birth_continent, {TONE_FAMILY} AS tone_family, COUNT(*) AS artist_count FROM art WHERE birth_continent != '' AND tone != '' GROUP BY birth_continent, tone_family", "For each birth continent and tone family, how many artists are there?"),
            q("q4", "SELECT CASE WHEN awards = 0 THEN 'no_awards' WHEN awards = 1 THEN 'one_award' ELSE 'multiple_awards' END AS award_band, teaching, COUNT(*) AS artist_count FROM art WHERE teaching IS NOT NULL AND awards IS NOT NULL GROUP BY award_band, teaching", "For artists with no awards, one award, or multiple awards, how many taught versus did not teach?"),
            q("q5", "SELECT image_genre, CASE WHEN awards >= 1 THEN 'awarded' ELSE 'unawarded' END AS award_status, COUNT(*) AS artist_count FROM art WHERE image_genre IN ('Portrait', 'Landscape', 'Still Life', 'Abstract', 'Sculpture', 'Figurative') GROUP BY image_genre, award_status", "For major image genres, how many artists have at least one award versus none?"),
            q("q6", f"SELECT {FIELD_FAMILY} AS field_family, {COLOR_FAMILY} AS color_family, COUNT(*) AS artist_count FROM art WHERE field != '' AND color != '' GROUP BY field_family, color_family", "For painters, sculptors, photographers, and other artists, how many use each major color family?"),
            q("q7", "SELECT century, CASE WHEN nationality = 'American' THEN 'American' WHEN nationality != '' THEN 'non_American' END AS nationality_group, COUNT(*) AS artist_count FROM art WHERE century != '' AND nationality != '' GROUP BY century, nationality_group", "For each century, how many artists are American versus not American?"),
            q("q8", "SELECT birth_continent, CASE WHEN death_country != '' AND death_country != birth_country THEN 'died_abroad' WHEN death_country != '' THEN 'died_in_birth_country' ELSE 'death_country_unknown' END AS death_place, COUNT(*) AS artist_count FROM art WHERE birth_continent != '' GROUP BY birth_continent, death_place", "For each birth continent, how many artists died in their birth country, died abroad, or have no recorded death country?"),
            q("q9", "SELECT style, century, COUNT(*) AS artist_count FROM art WHERE style IN ('Expressionism', 'Romanticism', 'Impressionism', 'Realism', 'Surrealism', 'Abstract Expressionism') AND century != '' GROUP BY style, century", "For major styles, how many artists are associated with each century?"),
            q("q10", f"SELECT {TONE_FAMILY} AS tone_family, image_genre, COUNT(*) AS artist_count FROM art WHERE tone != '' AND image_genre IN ('Portrait', 'Landscape', 'Still Life', 'Abstract') GROUP BY tone_family, image_genre", "For each tone family, how many artists have a portrait, landscape, still-life, or abstract work?"),
            q("q11", "SELECT style, CASE WHEN teaching = 1 THEN 'taught' ELSE 'did_not_teach' END AS teaching_status, COUNT(*) AS artist_count FROM art WHERE style IN ('Expressionism', 'Romanticism', 'Impressionism', 'Realism', 'Surrealism', 'Abstract Expressionism') AND teaching IS NOT NULL GROUP BY style, teaching_status", "For major styles, how many artists taught versus did not teach?"),
            q("q12", "SELECT birth_country, century, COUNT(*) AS artist_count FROM art WHERE birth_country IN ('United States', 'France', 'United Kingdom', 'Germany', 'Italy') AND century != '' GROUP BY birth_country, century", "For artists born in the United States, France, the United Kingdom, Germany, or Italy, how many are associated with each century?"),
            q("q13", f"SELECT {FIELD_FAMILY} AS field_family, CASE WHEN age < 60 THEN 'under_60' ELSE '60_or_older' END AS age_band, COUNT(*) AS artist_count FROM art WHERE field != '' AND age BETWEEN 25 AND 105 GROUP BY field_family, age_band", "For painters, sculptors, photographers, and other artists, how many are under 60 versus 60 or older?"),
            q("q14", "SELECT birth_country, CASE WHEN teaching = 1 THEN 'taught' ELSE 'did_not_teach' END AS teaching_status, COUNT(*) AS artist_count FROM art WHERE birth_country IN ('United States', 'France', 'United Kingdom', 'Germany', 'Italy') AND teaching IS NOT NULL GROUP BY birth_country, teaching_status", "For artists born in the United States, France, the United Kingdom, Germany, or Italy, how many taught versus did not teach?"),
            q("q15", "SELECT CASE WHEN birth_continent IN ('Europe', 'North America') THEN birth_continent ELSE 'Other' END AS continent_group, CASE WHEN awards >= 1 THEN 'awarded' ELSE 'unawarded' END AS award_status, COUNT(*) AS artist_count FROM art WHERE birth_continent != '' GROUP BY continent_group, award_status", "For European-born, North American-born, and other artists, how many have at least one award versus none?"),
            q("q16", "SELECT image_genre, CASE WHEN color IN ('Earth Tones', 'Blue', 'Green', 'Red') THEN color ELSE 'Other' END AS color_group, COUNT(*) AS artist_count FROM art WHERE image_genre IN ('Portrait', 'Landscape', 'Still Life', 'Abstract') AND color != '' GROUP BY image_genre, color_group", "For major image genres, how many artists use earth tones, blue, green, red, or another color?"),
            q("q17", "SELECT century, CASE WHEN art_institution != '' THEN 'known_institution' ELSE 'institution_unknown' END AS institution_status, COUNT(*) AS artist_count FROM art WHERE century != '' GROUP BY century, institution_status", "For each century, how many artists have a known art institution versus none recorded?"),
            q("q18", f"SELECT {FIELD_FAMILY} AS field_family, CASE WHEN awards >= 1 THEN 'awarded' ELSE 'unawarded' END AS award_status, COUNT(*) AS artist_count FROM art WHERE field != '' GROUP BY field_family, award_status", "For painters, sculptors, photographers, and other artists, how many have at least one award versus none?"),
            q("q19", "SELECT style, CASE WHEN tone IN ('Neutral', 'Bright', 'Dark') THEN tone ELSE 'Other' END AS tone_group, COUNT(*) AS artist_count FROM art WHERE style IN ('Expressionism', 'Romanticism', 'Impressionism', 'Realism', 'Surrealism') AND tone != '' GROUP BY style, tone_group", "For major styles, how many artists have a work that is neutral, bright, dark, or another tone?"),
        ],
    },
    "art_multiagg20": {
        "title": "Multi-aggregation workload",
        "focus": "Several aggregates, often with HAVING, in the same query",
        "kind": "pure",
        "contrast_with": BASELINE,
        "queries": [
            q("q0", "SELECT century, COUNT(*) AS artist_count, AVG(age) AS avg_age, MAX(awards) AS max_awards FROM art WHERE century != '' AND age BETWEEN 25 AND 105 GROUP BY century", "For each century, how many artists of known age are there, and what are their average age and highest award count?"),
            q("q1", "SELECT birth_continent, COUNT(*) AS artist_count, AVG(age) AS avg_age, SUM(awards) AS total_awards FROM art WHERE birth_continent != '' AND age BETWEEN 25 AND 105 GROUP BY birth_continent HAVING COUNT(*) >= 5", "Among birth continents with at least five artists of known age, what are the artist count, average age, and total awards?"),
            q("q2", "SELECT nationality, COUNT(*) AS artist_count, AVG(awards) AS avg_awards, MAX(awards) AS max_awards FROM art WHERE nationality != '' GROUP BY nationality HAVING COUNT(*) >= 8", "Among nationalities with at least eight artists, what are the artist count and the average and highest award totals?"),
            q("q3", f"SELECT {FIELD_FAMILY} AS field_family, COUNT(*) AS artist_count, AVG(age) AS avg_age, SUM(CASE WHEN teaching = 1 THEN 1 ELSE 0 END) AS teacher_count FROM art WHERE field != '' AND age BETWEEN 25 AND 105 GROUP BY field_family", "For painters, sculptors, photographers, and other artists of known age, what are the count, average age, and number who taught?"),
            q("q4", "SELECT image_genre, COUNT(*) AS artist_count, AVG(awards) AS avg_awards, MAX(age) AS oldest FROM art WHERE image_genre != '' AND age BETWEEN 25 AND 105 GROUP BY image_genre HAVING COUNT(*) >= 10", "For image genres with at least ten artists of known age, what are the count, average awards, and oldest age?"),
            q("q5", "SELECT style, COUNT(*) AS artist_count, AVG(age) AS avg_age, SUM(CASE WHEN awards >= 1 THEN 1 ELSE 0 END) AS awarded_count FROM art WHERE style != '' AND age BETWEEN 25 AND 105 GROUP BY style HAVING COUNT(*) >= 12", "For styles with at least twelve artists of known age, what are the count, average age, and number of awarded artists?"),
            q("q6", f"SELECT {TONE_FAMILY} AS tone_family, COUNT(*) AS artist_count, AVG(age) AS avg_age, AVG(awards) AS avg_awards FROM art WHERE tone != '' AND age BETWEEN 25 AND 105 GROUP BY tone_family", "For each tone family, what are the artist count, average age, and average award count?"),
            q("q7", "SELECT teaching, COUNT(*) AS artist_count, AVG(age) AS avg_age, AVG(awards) AS avg_awards, MAX(awards) AS max_awards FROM art WHERE teaching IS NOT NULL AND age BETWEEN 25 AND 105 GROUP BY teaching", "For teachers versus non-teachers, what are the count, average age, and average and maximum award totals?"),
            q("q8", "SELECT century, COUNT(*) AS artist_count, MIN(age) AS youngest, MAX(age) AS oldest, AVG(awards) AS avg_awards FROM art WHERE century != '' AND age BETWEEN 25 AND 105 GROUP BY century", "For each century, what are the artist count, youngest and oldest ages, and average award count?"),
            q("q9", "SELECT birth_country, COUNT(*) AS artist_count, AVG(age) AS avg_age, SUM(awards) AS total_awards FROM art WHERE birth_country != '' AND age BETWEEN 25 AND 105 GROUP BY birth_country HAVING COUNT(*) >= 8", "Among birth countries with at least eight artists of known age, what are the count, average age, and total awards?"),
            q("q10", f"SELECT {COLOR_FAMILY} AS color_family, COUNT(*) AS artist_count, AVG(age) AS avg_age, MAX(awards) AS max_awards FROM art WHERE color != '' AND age BETWEEN 25 AND 105 GROUP BY color_family HAVING COUNT(*) >= 10", "For major color families with at least ten artists of known age, what are the count, average age, and highest award total?"),
            q("q11", "SELECT CASE WHEN art_institution != '' THEN 'known_institution' ELSE 'institution_unknown' END AS institution_status, COUNT(*) AS artist_count, AVG(age) AS avg_age, AVG(awards) AS avg_awards FROM art WHERE age BETWEEN 25 AND 105 GROUP BY institution_status", "For artists with a known art institution versus none recorded, what are the count, average age, and average awards?"),
            q("q12", "SELECT CASE WHEN death_country != '' AND death_country != birth_country THEN 'died_abroad' WHEN death_country != '' THEN 'died_in_birth_country' ELSE 'death_country_unknown' END AS death_place, COUNT(*) AS artist_count, AVG(age) AS avg_age, SUM(CASE WHEN teaching = 1 THEN 1 ELSE 0 END) AS teacher_count FROM art WHERE age BETWEEN 25 AND 105 GROUP BY death_place", "For artists who died abroad, died in their birth country, or have no recorded death country, what are the count, average age, and number who taught?"),
            q("q13", "SELECT CASE WHEN birth_continent IN ('Europe', 'North America', 'Asia') THEN birth_continent ELSE 'Other' END AS continent_group, COUNT(*) AS artist_count, AVG(awards) AS avg_awards, MAX(awards) AS max_awards, SUM(CASE WHEN teaching = 1 THEN 1 ELSE 0 END) AS teacher_count FROM art WHERE birth_continent != '' GROUP BY continent_group", "For European, North American, Asian, and other artists, what are the count, average and maximum awards, and number of teachers?"),
            q("q14", "SELECT century, COUNT(*) AS artist_count, SUM(CASE WHEN awards >= 1 THEN 1 ELSE 0 END) AS awarded_count, SUM(CASE WHEN teaching = 1 THEN 1 ELSE 0 END) AS teacher_count, AVG(age) AS avg_age FROM art WHERE century != '' AND age BETWEEN 25 AND 105 GROUP BY century", "For each century, how many artists of known age are there, how many were awarded, how many taught, and what is the average age?"),
            q("q15", f"SELECT {FIELD_FAMILY} AS field_family, century, COUNT(*) AS artist_count, AVG(age) AS avg_age, AVG(awards) AS avg_awards FROM art WHERE field != '' AND century != '' AND age BETWEEN 25 AND 105 GROUP BY field_family, century HAVING COUNT(*) >= 5", "For painters, sculptors, photographers, and other artists in each century with at least five artists of known age, what are the count, average age, and average awards?"),
            q("q16", "SELECT image_genre, COUNT(*) AS artist_count, MIN(age) AS youngest, MAX(age) AS oldest, SUM(awards) AS total_awards FROM art WHERE image_genre IN ('Portrait', 'Landscape', 'Still Life', 'Abstract', 'Sculpture') AND age BETWEEN 25 AND 105 GROUP BY image_genre", "For major image genres, what are the artist count, youngest and oldest ages, and total awards?"),
            q("q17", "SELECT style, COUNT(*) AS artist_count, AVG(age) AS avg_age, MAX(awards) AS max_awards FROM art WHERE style IN ('Expressionism', 'Romanticism', 'Impressionism', 'Realism', 'Surrealism', 'Abstract Expressionism', 'Pop Art', 'Minimalism') AND age BETWEEN 25 AND 105 GROUP BY style", "For major styles, what are the artist count, average age, and highest award total?"),
            q("q18", "SELECT CASE WHEN awards = 0 THEN 'no_awards' WHEN awards = 1 THEN 'one_award' ELSE 'multiple_awards' END AS award_band, COUNT(*) AS artist_count, AVG(age) AS avg_age, SUM(CASE WHEN teaching = 1 THEN 1 ELSE 0 END) AS teacher_count FROM art WHERE awards IS NOT NULL AND age BETWEEN 25 AND 105 GROUP BY award_band", "For artists with no awards, one award, or multiple awards, what are the count, average age, and number of teachers?"),
            q("q19", "SELECT birth_continent, COUNT(*) AS artist_count, AVG(age) AS avg_age, SUM(CASE WHEN death_country != '' AND death_country != birth_country THEN 1 ELSE 0 END) AS died_abroad_count, MAX(awards) AS max_awards FROM art WHERE birth_continent != '' AND age BETWEEN 25 AND 105 GROUP BY birth_continent HAVING COUNT(*) >= 5", "Among birth continents with at least five artists of known age, what are the count, average age, number who died abroad, and highest award total?"),
        ],
    },
}
