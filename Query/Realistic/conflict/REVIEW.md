# Representation-conflict questions: review

Each group is a set of realistic questions that use one column in different forms. The correct database stores the value as the documents state it, and each question does its own post-processing in SQL, so the raw value answers all of them. **ALT** is the form one question would want stored in place of the raw value (as a system that normalizes at extraction time would store it). The checker requires: the question the ALT is for still scores 1.0, and at least one other question of the group drops below 1.0.

All 34 groups (83 questions) pass the checker (re-run independently after the agents finished) and the standard query checker (runs on the correct data, non-empty, no empty group keys, realism rules, scores 1.0 against itself). No question has a one-row answer.

In each group: **rows changed** = rows whose stored value the ALT actually changes; **breaks** = the other questions' scores on the ALT data, exact / at 20% tolerance; **Flags** = my concerns for you to judge.

| Collection | Groups | Questions | one value vs list | fine vs coarse | join spelling | number vs text |
|---|---|---|---|---|---|---|
| Artists | 9 | 23 | 5 | 3 | 0 | 1 |
| Legal | 7 | 15 | 2 | 5 | 0 | 0 |
| Med | 8 | 17 | 3 | 3 | 1 | 1 |
| Players | 4 | 11 | 2 | 1 | 1 | 0 |
| Papers | 6 | 17 | 4 | 2 | 0 | 0 |

What to check: would a real analyst ask each question this way; is the ALT a form a system would plausibly store for that question; is the conflict large enough to matter (Flags).

## Artists (`Query/Realistic/conflict/art.sql`)

### G1 · `art.field` · list-vs-one

art.field lists every field an artist works in; G1a needs only the field the biography names first, G1b counts an artist under every field, G1c counts how many of five named media each artist works in

> Writer's note: the ALT is what a reader asked for "the artist's field" writes: one field. G1a also tests whether the extraction keeps the biography's order (82 rows list Painting but not first).

| Question | Asks |
|---|---|
| G1a | By each artist's main field (the field the biography names first: painting, sculpture, photography, or other), how many artists are there, how many of them taught, and how many won at least one award? |
| G1b | Per century of activity, how many artists work in painting, in sculpture, in printmaking (including etching, engraving, lithography and woodcut) and in photography, counting an artist under every field they work in? |
| G1c | Among artists who work in at least one of painting, sculpture, printmaking (including etching, engraving, lithography and woodcut), drawing and photography, how many work in exactly one of these five, in two, and in three or more, and how many of each group taught and how many won at least one award? |

**ALT for G1a**: rows changed 599; G1a keeps 1.0; breaks G1b 0.25 / 0.55, G1c 0.00 / 0.00

```sql
UPDATE art SET field = CASE WHEN instr(field, '||') > 0 THEN substr(field, 1, instr(field, '||') - 1) ELSE field END;
```

<details><summary>SQL</summary>

```sql
-- G1a
SELECT CASE WHEN field LIKE 'Painting%' THEN 'Painting' WHEN field LIKE 'Sculpture%' THEN 'Sculpture' WHEN field LIKE 'Photography%' THEN 'Photography' ELSE 'Other' END AS main_field, COUNT(*) AS artists, SUM(teaching) AS teachers, SUM(CASE WHEN awards >= 1 THEN 1 ELSE 0 END) AS award_winners FROM art WHERE field IS NOT NULL AND field <> '' AND awards <> '' GROUP BY main_field;
```
```sql
-- G1b
SELECT century, COUNT(*) AS artists, SUM(CASE WHEN field LIKE '%Painting%' THEN 1 ELSE 0 END) AS painting, SUM(CASE WHEN field LIKE '%Sculpture%' THEN 1 ELSE 0 END) AS sculpture, SUM(CASE WHEN field LIKE '%Print%' OR field LIKE '%Etch%' OR field LIKE '%Engrav%' OR field LIKE '%Lithograph%' OR field LIKE '%Woodcut%' THEN 1 ELSE 0 END) AS printmaking, SUM(CASE WHEN field LIKE '%Photograph%' THEN 1 ELSE 0 END) AS photography FROM art WHERE century IS NOT NULL AND century <> '' AND field IS NOT NULL AND field <> '' GROUP BY century;
```
```sql
-- G1c
SELECT CASE WHEN ((field LIKE '%Painting%') + (field LIKE '%Sculpture%') + (field LIKE '%Print%' OR field LIKE '%Etch%' OR field LIKE '%Engrav%' OR field LIKE '%Lithograph%' OR field LIKE '%Woodcut%') + (field LIKE '%Drawing%' OR field LIKE '%Draught%') + (field LIKE '%Photograph%')) = 1 THEN 'one of the five' WHEN ((field LIKE '%Painting%') + (field LIKE '%Sculpture%') + (field LIKE '%Print%' OR field LIKE '%Etch%' OR field LIKE '%Engrav%' OR field LIKE '%Lithograph%' OR field LIKE '%Woodcut%') + (field LIKE '%Drawing%' OR field LIKE '%Draught%') + (field LIKE '%Photograph%')) = 2 THEN 'two of the five' ELSE 'three or more of the five' END AS media_count, COUNT(*) AS artists, SUM(teaching) AS teachers, SUM(CASE WHEN awards >= 1 THEN 1 ELSE 0 END) AS award_winners FROM art WHERE (field LIKE '%Painting%' OR field LIKE '%Sculpture%' OR field LIKE '%Print%' OR field LIKE '%Etch%' OR field LIKE '%Engrav%' OR field LIKE '%Lithograph%' OR field LIKE '%Woodcut%' OR field LIKE '%Drawing%' OR field LIKE '%Draught%' OR field LIKE '%Photograph%') AND awards <> '' GROUP BY media_count;
```

</details>

### G2 · `art.genre` · list-vs-one

art.genre lists every genre an artist works in; G2a needs only the genre the biography names first, G2b and G2c need every genre to see which combinations an artist works in

> Writer's note: the ALT is what a reader asked for "the artist's primary genre" writes: one genre. G2a also tests whether the extraction keeps the biography's order (158 multi-genre rows hold portrait, landscape or abstract but not first).

| Question | Asks |
|---|---|
| G2a | By each artist's primary genre (the genre the biography names first: portrait, landscape, abstract, or other), how many artists are there, what share of them taught, and what share won at least one award? |
| G2b | Looking at all the genres an artist works in, how many artists do both portraits and landscapes, portraits only, landscapes only, or neither, and what share of each group won at least one award? |
| G2c | For artists active in the 20th century (alone or as part of a span), per century of activity: how many include abstract work among their genres, and how many of those also do figurative or portrait work? |

**ALT for G2a**: rows changed 384; G2a keeps 1.0; breaks G2b 0.00 / 0.34, G2c 0.00 / 0.00

```sql
UPDATE art SET genre = CASE WHEN instr(genre, '||') > 0 THEN substr(genre, 1, instr(genre, '||') - 1) ELSE genre END;
```

<details><summary>SQL</summary>

```sql
-- G2a
SELECT CASE WHEN genre LIKE 'Portrait%' THEN 'Portrait' WHEN genre LIKE 'Landscape%' THEN 'Landscape' WHEN genre LIKE 'Abstract%' THEN 'Abstract' ELSE 'Other' END AS primary_genre, COUNT(*) AS artists, AVG(teaching) AS share_who_taught, AVG(CASE WHEN awards >= 1 THEN 1.0 ELSE 0.0 END) AS share_award_winners FROM art WHERE genre IS NOT NULL AND genre <> '' AND awards <> '' GROUP BY primary_genre;
```
```sql
-- G2b
SELECT CASE WHEN genre LIKE '%Portrait%' AND genre LIKE '%Landscape%' THEN 'portraits and landscapes' WHEN genre LIKE '%Portrait%' THEN 'portraits only' WHEN genre LIKE '%Landscape%' THEN 'landscapes only' ELSE 'neither' END AS portrait_landscape, COUNT(*) AS artists, AVG(CASE WHEN awards >= 1 THEN 1.0 ELSE 0.0 END) AS share_award_winners FROM art WHERE genre IS NOT NULL AND genre <> '' AND awards <> '' GROUP BY portrait_landscape;
```
```sql
-- G2c
SELECT century, SUM(CASE WHEN genre LIKE '%Abstract%' THEN 1 ELSE 0 END) AS abstract_artists, SUM(CASE WHEN genre LIKE '%Abstract%' AND (genre LIKE '%Figur%' OR genre LIKE '%Portrait%') THEN 1 ELSE 0 END) AS also_figurative_or_portrait FROM art WHERE century IN ('19th-20th', '20th', '20th-21st') AND genre IS NOT NULL AND genre <> '' GROUP BY century;
```

</details>

### G3 · `art.style` · fine-vs-coarse

art.style holds the specific style of the featured image (Abstract Expressionism, Neo-Expressionism, Post-Impressionism); G3a wants the broad family by name, G3b needs the specific style within the Expressionism family

> Writer's note: the ALT merges 68 rows (49 Abstract Expressionism, 19 Neo-Expressionism) into Expressionism, among others.

| Question | Asks |
|---|---|
| G3a | Grouping styles into broad families by name (any style whose name contains Expressionism, such as Abstract and Neo-Expressionism; contains Impressionism, such as Post-Impressionism; contains Realism but not Surrealism, such as Social, Magic and Photorealism; contains Minimalism; Surrealism; everything else as other), among artists with a plausible recorded age (15 to 110): how many artists are in each family, how old did they get on average, and how many won at least one award? |
| G3b | How do Expressionists, Abstract Expressionists and Neo-Expressionists compare: how many of each, what share won at least one award, and (among those with a plausible recorded age, 15 to 110) how old did they get on average? |

**ALT for G3a**: rows changed 159; G3a keeps 1.0; breaks G3b 0.00 / 0.00 · **Flags:** long question: G3a

```sql
UPDATE art SET style = CASE WHEN style LIKE '%Surrealism%' THEN 'Surrealism' WHEN style LIKE '%Expressionism%' THEN 'Expressionism' WHEN style LIKE '%Impressionism%' THEN 'Impressionism' WHEN style LIKE '%Realism%' THEN 'Realism' WHEN style LIKE '%Minimalism%' THEN 'Minimalism' ELSE style END;
```

<details><summary>SQL</summary>

```sql
-- G3a
SELECT CASE WHEN style LIKE '%Surrealism%' THEN 'Surrealism' WHEN style LIKE '%Expressionism%' THEN 'Expressionism' WHEN style LIKE '%Impressionism%' THEN 'Impressionism' WHEN style LIKE '%Realism%' THEN 'Realism' WHEN style LIKE '%Minimalism%' THEN 'Minimalism' ELSE 'Other' END AS style_family, COUNT(*) AS artists, AVG(age) AS average_age, SUM(CASE WHEN awards >= 1 THEN 1 ELSE 0 END) AS award_winners FROM art WHERE style IS NOT NULL AND style <> '' AND age IS NOT NULL AND age <> '' AND CAST(age AS INTEGER) BETWEEN 15 AND 110 AND awards <> '' GROUP BY style_family;
```
```sql
-- G3b
SELECT style, COUNT(*) AS artists, AVG(CASE WHEN awards >= 1 THEN 1.0 ELSE 0.0 END) AS share_award_winners, AVG(CASE WHEN age <> '' AND CAST(age AS INTEGER) BETWEEN 15 AND 110 THEN age END) AS average_age FROM art WHERE style IN ('Expressionism', 'Abstract Expressionism', 'Neo-Expressionism') AND awards <> '' GROUP BY style;
```

</details>

### G4 · `art.marriage` · fine-vs-coarse

art.marriage holds the final marital status (married, remarried, divorced, widowed, separated, unmarried); G4a wants only whether the artist ever married, G4b and G4c need the specific final status

> Writer's note: the field's closed list has no "ever married" label, so a reader asked whether the artist ever married can only write Married; that is the ALT (57 values change). marriage is empty on 708 of 1003 rows, so this group is small.

| Question | Asks |
|---|---|
| G4a | Among artists whose final marital status is married, remarried, divorced, widowed, separated or unmarried (the two cohabiting artists left out), how many ever married (counting remarried, divorced, widowed and separated artists as having married) and how many never married, and for each group what share taught and what share won at least one award? |
| G4b | By final marital status (married, remarried, divorced or separated counted together, widowed, unmarried), among artists with a plausible recorded age (15 to 110): how many artists, how old did they get on average, and what share won at least one award? |
| G4c | For artists born in Europe and in North America whose final marital status is known: how many were still married at the end of their lives, how many had remarried, how many were divorced or separated, and how many were widowed? |

**ALT for G4a**: rows changed 57; G4a keeps 1.0; breaks G4b 0.13 / 0.22, G4c 0.20 / 0.20

```sql
UPDATE art SET marriage = 'Married' WHERE marriage IN ('Remarried', 'Divorced', 'Widowed', 'Separated');
```

<details><summary>SQL</summary>

```sql
-- G4a
SELECT CASE WHEN marriage = 'Unmarried' THEN 'never married' ELSE 'married at some point' END AS ever_married, COUNT(*) AS artists, AVG(teaching) AS share_who_taught, AVG(CASE WHEN awards >= 1 THEN 1.0 ELSE 0.0 END) AS share_award_winners FROM art WHERE marriage IN ('Married', 'Remarried', 'Divorced', 'Widowed', 'Separated', 'Unmarried') AND awards <> '' GROUP BY ever_married;
```
```sql
-- G4b
SELECT CASE WHEN marriage IN ('Divorced', 'Separated') THEN 'Divorced or separated' ELSE marriage END AS final_status, COUNT(*) AS artists, AVG(age) AS average_age, AVG(CASE WHEN awards >= 1 THEN 1.0 ELSE 0.0 END) AS share_award_winners FROM art WHERE marriage IN ('Married', 'Remarried', 'Divorced', 'Widowed', 'Separated', 'Unmarried') AND age IS NOT NULL AND age <> '' AND CAST(age AS INTEGER) BETWEEN 15 AND 110 GROUP BY final_status;
```
```sql
-- G4c
SELECT birth_continent, COUNT(*) AS artists, SUM(CASE WHEN marriage = 'Married' THEN 1 ELSE 0 END) AS married, SUM(CASE WHEN marriage = 'Remarried' THEN 1 ELSE 0 END) AS remarried, SUM(CASE WHEN marriage IN ('Divorced', 'Separated') THEN 1 ELSE 0 END) AS divorced_or_separated, SUM(CASE WHEN marriage = 'Widowed' THEN 1 ELSE 0 END) AS widowed FROM art WHERE birth_continent IN ('Europe', 'North America') AND marriage IN ('Married', 'Remarried', 'Divorced', 'Widowed', 'Separated', 'Unmarried') GROUP BY birth_continent;
```

</details>

### G5 · `art.image_genre` · fine-vs-coarse

art.image_genre holds the specific genre of the featured image (portrait, genre painting, figurative, landscape, seascape); G5a wants a broad subject group, G5b needs the specific genre within the figurative group

| Question | Asks |
|---|---|
| G5a | Grouping featured images into figurative work (portraits, figures, genre scenes and nudes), landscapes (including seascapes and cityscapes), still lifes, abstract work (including geometric and non-representational images) and other: per century of activity, how many artists' featured images fall into each group? |
| G5b | Among featured images that show people, per century of activity: how many are portraits, how many are genre scenes (everyday life), and how many are other figure pictures (figurative work and nudes)? |

**ALT for G5a**: rows changed 508; G5a keeps 1.0; breaks G5b 0.00 / 0.17

```sql
UPDATE art SET image_genre = CASE WHEN image_genre LIKE '%Portrait%' OR image_genre LIKE '%Figur%' OR image_genre LIKE '%Genre%' OR image_genre LIKE '%Nude%' THEN 'Figurative' WHEN image_genre LIKE '%Landscape%' OR image_genre LIKE '%Seascape%' OR image_genre LIKE '%Cityscape%' THEN 'Landscape' WHEN image_genre LIKE '%Still Life%' THEN 'Still Life' WHEN image_genre LIKE '%Abstract%' OR image_genre LIKE '%Geometric%' OR image_genre LIKE '%Non-Representational%' THEN 'Abstract' ELSE 'Other' END WHERE image_genre IS NOT NULL AND image_genre <> '';
```

<details><summary>SQL</summary>

```sql
-- G5a
SELECT century, CASE WHEN image_genre LIKE '%Portrait%' OR image_genre LIKE '%Figur%' OR image_genre LIKE '%Genre%' OR image_genre LIKE '%Nude%' THEN 'Figurative' WHEN image_genre LIKE '%Landscape%' OR image_genre LIKE '%Seascape%' OR image_genre LIKE '%Cityscape%' THEN 'Landscape' WHEN image_genre LIKE '%Still Life%' THEN 'Still Life' WHEN image_genre LIKE '%Abstract%' OR image_genre LIKE '%Geometric%' OR image_genre LIKE '%Non-Representational%' THEN 'Abstract' ELSE 'Other' END AS subject_group, COUNT(*) AS artists FROM art WHERE century IS NOT NULL AND century <> '' AND image_genre IS NOT NULL AND image_genre <> '' GROUP BY century, subject_group;
```
```sql
-- G5b
SELECT century, SUM(CASE WHEN image_genre LIKE '%Portrait%' THEN 1 ELSE 0 END) AS portraits, SUM(CASE WHEN image_genre LIKE '%Genre%' THEN 1 ELSE 0 END) AS genre_scenes, SUM(CASE WHEN image_genre LIKE '%Figur%' OR image_genre LIKE '%Nude%' THEN 1 ELSE 0 END) AS other_figure_pictures FROM art WHERE century IS NOT NULL AND century <> '' AND (image_genre LIKE '%Portrait%' OR image_genre LIKE '%Figur%' OR image_genre LIKE '%Genre%' OR image_genre LIKE '%Nude%') GROUP BY century;
```

</details>

### G6 · `art.century` · list-vs-one

art.century holds the stated period of activity, often a span of two centuries ('19th-20th'); G6a wants only the century in which the artist became active, G6b and G6c need the whole span

> Writer's note: the ALT is what a reader asked for "the century the artist became active" writes: one century, the first of a span (498 spans lose their second century: 332 '19th-20th', 166 '20th-21st'). The ALT keeps the stated text ('19th'), so G6c's break comes from the lost span, not from relabeling.

| Question | Asks |
|---|---|
| G6a | By the century in which artists became active (the earlier one when a span such as 19th-20th is given), how many artists are there, how many of them taught, and how many won at least one award? |
| G6b | How many artists were active within a single century and how many across two centuries (a span such as 19th-20th), and, among artists with a plausible recorded age (15 to 110), how old did each group get on average and what share taught? |
| G6c | Per birth continent, how many artists were active in the 19th, in the 20th and in the 21st century, counting an artist active across two centuries in both? |

**ALT for G6a**: rows changed 498; G6a keeps 1.0; breaks G6b 0.00 / 0.00, G6c 0.33 / 0.67

```sql
UPDATE art SET century = CASE WHEN instr(century, '-') > 0 THEN substr(century, 1, instr(century, '-') - 1) ELSE century END WHERE century IS NOT NULL AND century <> '';
```

<details><summary>SQL</summary>

```sql
-- G6a
SELECT CASE WHEN instr(century, '-') > 0 THEN substr(century, 1, instr(century, '-') - 1) ELSE century END AS first_century, COUNT(*) AS artists, SUM(teaching) AS teachers, SUM(CASE WHEN awards >= 1 THEN 1 ELSE 0 END) AS award_winners FROM art WHERE century IS NOT NULL AND century <> '' AND awards <> '' GROUP BY first_century;
```
```sql
-- G6b
SELECT CASE WHEN century LIKE '%-%' THEN 'two centuries' ELSE 'one century' END AS span, COUNT(*) AS artists, AVG(age) AS average_age, AVG(teaching) AS share_who_taught FROM art WHERE century IS NOT NULL AND century <> '' AND age IS NOT NULL AND age <> '' AND CAST(age AS INTEGER) BETWEEN 15 AND 110 GROUP BY span;
```
```sql
-- G6c
SELECT birth_continent, SUM(CASE WHEN century LIKE '%19th%' THEN 1 ELSE 0 END) AS active_19th, SUM(CASE WHEN century LIKE '%20th%' THEN 1 ELSE 0 END) AS active_20th, SUM(CASE WHEN century LIKE '%21st%' THEN 1 ELSE 0 END) AS active_21st FROM art WHERE century IS NOT NULL AND century <> '' AND birth_continent IN ('Europe', 'North America', 'Asia', 'South America') GROUP BY birth_continent;
```

</details>

### G7 · `art.birth_date` · number-vs-text

art.birth_date holds the stated date ('1839/1/9'); G7a wants the birth year as a number, G7b needs the month from the stated date

> Writer's note: the ALT is what a reader or normalizer writes when a date is wanted as a year: the parsed integer. This is the file's only number-vs-text group.

| Question | Asks |
|---|---|
| G7a | Among artists with a known birth year, by birth period (before 1850, 1850-1899, 1900-1949, 1950 or later): how many artists are there, what share of them taught, and what share won at least one award? |
| G7b | Among artists whose full birth date (year, month and day) is known, by birth quarter (January-March, April-June, July-September, October-December): how many artists, and among those with a plausible recorded age (15 to 110), how old did they get on average? |

**ALT for G7a**: rows changed 978; G7a keeps 1.0; breaks G7b 0.00 / 0.00

```sql
UPDATE art SET birth_date = CAST(substr(birth_date, 1, 4) AS INTEGER) WHERE birth_date IS NOT NULL AND birth_date <> '';
```

<details><summary>SQL</summary>

```sql
-- G7a
SELECT CASE WHEN CAST(substr(birth_date, 1, 4) AS INTEGER) < 1850 THEN 'before 1850' WHEN CAST(substr(birth_date, 1, 4) AS INTEGER) < 1900 THEN '1850-1899' WHEN CAST(substr(birth_date, 1, 4) AS INTEGER) < 1950 THEN '1900-1949' ELSE '1950 or later' END AS birth_period, COUNT(*) AS artists, AVG(teaching) AS share_who_taught, AVG(CASE WHEN awards >= 1 THEN 1.0 ELSE 0.0 END) AS share_award_winners FROM art WHERE CAST(substr(birth_date, 1, 4) AS INTEGER) >= 1400 AND awards <> '' GROUP BY birth_period;
```
```sql
-- G7b
SELECT CASE WHEN CAST(substr(birth_date, 6, instr(substr(birth_date, 6), '/') - 1) AS INTEGER) <= 3 THEN 'Jan-Mar' WHEN CAST(substr(birth_date, 6, instr(substr(birth_date, 6), '/') - 1) AS INTEGER) <= 6 THEN 'Apr-Jun' WHEN CAST(substr(birth_date, 6, instr(substr(birth_date, 6), '/') - 1) AS INTEGER) <= 9 THEN 'Jul-Sep' ELSE 'Oct-Dec' END AS birth_quarter, COUNT(*) AS artists, AVG(CASE WHEN age <> '' AND CAST(age AS INTEGER) BETWEEN 15 AND 110 THEN age END) AS average_age FROM art WHERE birth_date GLOB '[0-9][0-9][0-9][0-9]/[0-9]*/[0-9]*' GROUP BY birth_quarter;
```

</details>

### G8 · `art.art_movement` · list-vs-one

art.art_movement lists every movement an artist contributed to (264 of 778 filled values are lists); G8a needs only the movement the biography names first, G8b counts an artist under every movement

> Writer's note: the ALT is what a reader asked for "the artist's movement" writes: one movement. Membership falls under it, e.g. Expressionism (any kind) 86 -> 61, Cubism 34 -> 20, Minimalism 38 -> 24.

| Question | Asks |
|---|---|
| G8a | By each artist's main movement (the movement the biography names first: Abstract Expressionism, Surrealism, Impressionism including Post- and Neo-Impressionism, Pop Art, any kind of Realism, or other), how many artists are there, what share of them taught, and what share won at least one award? |
| G8b | For artists born in Europe and in North America with a known movement, counting an artist under every movement they contributed to: how many contributed to Impressionism (including Post- and Neo-Impressionism), to Expressionism (including Abstract and Neo-Expressionism), to Cubism, to Surrealism, to Pop Art and to Minimalism? |

**ALT for G8a**: rows changed 264; G8a keeps 1.0; breaks G8b 0.14 / 0.36

```sql
UPDATE art SET art_movement = CASE WHEN instr(art_movement, '||') > 0 THEN substr(art_movement, 1, instr(art_movement, '||') - 1) ELSE art_movement END;
```

<details><summary>SQL</summary>

```sql
-- G8a
SELECT CASE WHEN (CASE WHEN instr(art_movement, '||') > 0 THEN substr(art_movement, 1, instr(art_movement, '||') - 1) ELSE art_movement END) LIKE '%Abstract Expressionism%' THEN 'Abstract Expressionism' WHEN (CASE WHEN instr(art_movement, '||') > 0 THEN substr(art_movement, 1, instr(art_movement, '||') - 1) ELSE art_movement END) LIKE '%Surrealism%' THEN 'Surrealism' WHEN (CASE WHEN instr(art_movement, '||') > 0 THEN substr(art_movement, 1, instr(art_movement, '||') - 1) ELSE art_movement END) LIKE '%Impressionism%' THEN 'Impressionism' WHEN (CASE WHEN instr(art_movement, '||') > 0 THEN substr(art_movement, 1, instr(art_movement, '||') - 1) ELSE art_movement END) LIKE '%Pop Art%' THEN 'Pop Art' WHEN (CASE WHEN instr(art_movement, '||') > 0 THEN substr(art_movement, 1, instr(art_movement, '||') - 1) ELSE art_movement END) LIKE '%Realism%' THEN 'Realism' ELSE 'Other' END AS main_movement, COUNT(*) AS artists, AVG(teaching) AS share_who_taught, AVG(CASE WHEN awards >= 1 THEN 1.0 ELSE 0.0 END) AS share_award_winners FROM art WHERE art_movement IS NOT NULL AND art_movement <> '' AND awards <> '' GROUP BY main_movement;
```
```sql
-- G8b
SELECT birth_continent, COUNT(*) AS artists, SUM(CASE WHEN art_movement LIKE '%Impressionism%' THEN 1 ELSE 0 END) AS impressionism, SUM(CASE WHEN art_movement LIKE '%Expressionism%' THEN 1 ELSE 0 END) AS expressionism, SUM(CASE WHEN art_movement LIKE '%Cubism%' THEN 1 ELSE 0 END) AS cubism, SUM(CASE WHEN art_movement LIKE '%Surrealism%' THEN 1 ELSE 0 END) AS surrealism, SUM(CASE WHEN art_movement LIKE '%Pop Art%' THEN 1 ELSE 0 END) AS pop_art, SUM(CASE WHEN art_movement LIKE '%Minimalism%' THEN 1 ELSE 0 END) AS minimalism FROM art WHERE birth_continent IN ('Europe', 'North America') AND art_movement IS NOT NULL AND art_movement <> '' GROUP BY birth_continent;
```

</details>

### G9 · `art.art_institution` · list-vs-one

art.art_institution lists every institution an artist was affiliated with (322 of 709 filled values are lists, 132 with three or more); G9a needs only the institution the biography names first, G9b and G9c need every institution

> Writer's note: the ALT is what a reader asked for "where the artist trained" writes: one institution. Academy affiliation (Acad/Akad in the name) falls from 273 to 196 artists under it, university affiliation from 156 to 96.

| Question | Asks |
|---|---|
| G9a | By the institution the biography names first for each artist (an academy, a university, another school or college, or other), how many artists are there, what share of them taught, and what share won at least one award? |
| G9b | Among artists with at least one recorded institution, do those affiliated with an academy at any point (any institution whose name contains Academy, Academie or Akademie) teach more often than the others: how many artists are in each group, what share taught, and what share won at least one award? |
| G9c | For artists active in the 20th century (alone or as part of a span), per century of activity, among artists with at least one recorded institution: how many were affiliated at some point with an academy, how many with a university, and how many with both? |

**ALT for G9a**: rows changed 322; G9a keeps 1.0; breaks G9b 0.00 / 0.00, G9c 0.25 / 0.50

```sql
UPDATE art SET art_institution = CASE WHEN instr(art_institution, '||') > 0 THEN substr(art_institution, 1, instr(art_institution, '||') - 1) ELSE art_institution END;
```

<details><summary>SQL</summary>

```sql
-- G9a
SELECT CASE WHEN (CASE WHEN instr(art_institution, '||') > 0 THEN substr(art_institution, 1, instr(art_institution, '||') - 1) ELSE art_institution END) LIKE '%Acad%' OR (CASE WHEN instr(art_institution, '||') > 0 THEN substr(art_institution, 1, instr(art_institution, '||') - 1) ELSE art_institution END) LIKE '%Akad%' THEN 'Academy' WHEN (CASE WHEN instr(art_institution, '||') > 0 THEN substr(art_institution, 1, instr(art_institution, '||') - 1) ELSE art_institution END) LIKE '%Universit%' OR (CASE WHEN instr(art_institution, '||') > 0 THEN substr(art_institution, 1, instr(art_institution, '||') - 1) ELSE art_institution END) LIKE '%Universidad%' THEN 'University' WHEN (CASE WHEN instr(art_institution, '||') > 0 THEN substr(art_institution, 1, instr(art_institution, '||') - 1) ELSE art_institution END) LIKE '%School%' OR (CASE WHEN instr(art_institution, '||') > 0 THEN substr(art_institution, 1, instr(art_institution, '||') - 1) ELSE art_institution END) LIKE '%College%' OR (CASE WHEN instr(art_institution, '||') > 0 THEN substr(art_institution, 1, instr(art_institution, '||') - 1) ELSE art_institution END) LIKE '%Schule%' THEN 'School or college' ELSE 'Other' END AS first_institution, COUNT(*) AS artists, AVG(teaching) AS share_who_taught, AVG(CASE WHEN awards >= 1 THEN 1.0 ELSE 0.0 END) AS share_award_winners FROM art WHERE art_institution IS NOT NULL AND art_institution <> '' AND awards <> '' GROUP BY first_institution;
```
```sql
-- G9b
SELECT CASE WHEN art_institution LIKE '%Acad%' OR art_institution LIKE '%Akad%' THEN 'academy at some point' ELSE 'never an academy' END AS academy_affiliation, COUNT(*) AS artists, AVG(teaching) AS share_who_taught, AVG(CASE WHEN awards >= 1 THEN 1.0 ELSE 0.0 END) AS share_award_winners FROM art WHERE art_institution IS NOT NULL AND art_institution <> '' AND awards <> '' GROUP BY academy_affiliation;
```
```sql
-- G9c
SELECT century, COUNT(*) AS artists, SUM(CASE WHEN art_institution LIKE '%Acad%' OR art_institution LIKE '%Akad%' THEN 1 ELSE 0 END) AS academy, SUM(CASE WHEN art_institution LIKE '%Universit%' OR art_institution LIKE '%Universidad%' THEN 1 ELSE 0 END) AS university, SUM(CASE WHEN (art_institution LIKE '%Acad%' OR art_institution LIKE '%Akad%') AND (art_institution LIKE '%Universit%' OR art_institution LIKE '%Universidad%') THEN 1 ELSE 0 END) AS academy_and_university FROM art WHERE century IN ('19th-20th', '20th', '20th-21st') AND art_institution IS NOT NULL AND art_institution <> '' GROUP BY century;
```

</details>


## Legal (`Query/Realistic/conflict/legal.sql`)

### G1 · `legal.counsel_for_applicant` · list-vs-one

legal.counsel_for_applicant lists every counsel named for the applicant; one question needs all of them (does the applicant brief a team), the other only the lead (first-named) counsel. G1 and G2 test the same list-vs-one mechanism, once per side.

| Question | Asks |
|---|---|
| G1a | Per case type, do applicants who brief a team of counsel (two or more counsel named) win more often than applicants with a single named counsel? How many cases, and what share were approved (applicants appearing in person, representing themselves or not represented by counsel left out)? |
| G1b | Per case type, do applicants led by senior counsel (the first-named counsel is SC or QC, also written S.C. or Q.C.) win more often than applicants led by other counsel? How many cases, how many approved, and what share approved (applicants appearing in person, representing themselves or not represented by counsel left out)? |

**ALT for G1b**: rows changed 108; G1b keeps 1.0; breaks G1a 0.05 / 0.23

```sql
UPDATE legal SET counsel_for_applicant = trim(CASE WHEN instr(replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), '||') > 0 THEN substr(replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), 1, instr(replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), '||') - 1) ELSE replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC') END) WHERE counsel_for_applicant IS NOT NULL AND counsel_for_applicant <> '';
```

<details><summary>SQL</summary>

```sql
-- G1a
SELECT case_type, CASE WHEN replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC') GLOB '*||*[A-Z]*' THEN 'team of counsel' ELSE 'single counsel' END AS applicant_counsel, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Approved' THEN 1.0 ELSE 0.0 END) AS approval_rate FROM legal WHERE counsel_for_applicant IS NOT NULL AND counsel_for_applicant <> '' AND counsel_for_applicant NOT LIKE '%in person%' AND counsel_for_applicant NOT LIKE '%self%represent%' AND counsel_for_applicant NOT LIKE '%not represented%' GROUP BY case_type, applicant_counsel;
```
```sql
-- G1b
SELECT case_type, CASE WHEN (trim(CASE WHEN instr(replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), '||') > 0 THEN substr(replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), 1, instr(replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), '||') - 1) ELSE replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC') END) GLOB '* SC*' OR trim(CASE WHEN instr(replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), '||') > 0 THEN substr(replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), 1, instr(replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), '||') - 1) ELSE replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC') END) GLOB '* QC*' OR trim(CASE WHEN instr(replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), '||') > 0 THEN substr(replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), 1, instr(replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), '||') - 1) ELSE replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC') END) GLOB '* S.C*' OR trim(CASE WHEN instr(replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), '||') > 0 THEN substr(replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), 1, instr(replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), '||') - 1) ELSE replace(replace(replace(replace(replace(replace(counsel_for_applicant, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC') END) GLOB '* Q.C*') THEN 'senior counsel' ELSE 'other counsel' END AS lead_counsel, COUNT(*) AS cases, SUM(CASE WHEN verdict = 'Approved' THEN 1 ELSE 0 END) AS approved, AVG(CASE WHEN verdict = 'Approved' THEN 1.0 ELSE 0.0 END) AS approval_rate FROM legal WHERE counsel_for_applicant IS NOT NULL AND counsel_for_applicant <> '' AND counsel_for_applicant NOT LIKE '%in person%' AND counsel_for_applicant NOT LIKE '%self%represent%' AND counsel_for_applicant NOT LIKE '%not represented%' GROUP BY case_type, lead_counsel;
```

</details>

### G2 · `legal.counsel_for_respondent` · list-vs-one

legal.counsel_for_respondent lists every counsel named for the respondent; one question needs all of them (the size of the respondent's team), the other only the lead (first-named) counsel. Same mechanism as G1, on the respondent side.

| Question | Asks |
|---|---|
| G2a | Do respondents brief bigger legal teams in more complex cases? By the number of individual counsel named for the respondent (one, two, three or more; respondents appearing in person or represented only by a solicitor's office left out): how many cases, how many statutes and precedents are cited on average, and what share were dismissed? |
| G2b | For government, company and organization respondents with named counsel: how many cases were led by senior counsel for the respondent (the first-named counsel is SC or QC, also written S.C. or Q.C.) and how many by other counsel, and what share of each were dismissed? |

**ALT for G2b**: rows changed 95; G2b keeps 1.0; breaks G2a 0.00 / 0.14

```sql
UPDATE legal SET counsel_for_respondent = trim(CASE WHEN instr(replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), '||') > 0 THEN substr(replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), 1, instr(replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), '||') - 1) ELSE replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC') END) WHERE counsel_for_respondent IS NOT NULL AND counsel_for_respondent <> '';
```

<details><summary>SQL</summary>

```sql
-- G2a
SELECT CASE WHEN replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC') GLOB '*||*[A-Z]*||*[A-Z]*' THEN 'three or more' WHEN replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC') GLOB '*||*[A-Z]*' THEN 'two' ELSE 'one' END AS respondent_counsel, COUNT(*) AS cases, AVG(legal_basis_num) AS average_statutes, AVG(NULLIF(case_number, '')) AS average_precedents, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate FROM legal WHERE counsel_for_respondent IS NOT NULL AND counsel_for_respondent <> '' AND counsel_for_respondent NOT LIKE '%in person%' AND counsel_for_respondent NOT LIKE '%Solicitor%' GROUP BY respondent_counsel;
```
```sql
-- G2b
SELECT defendant_current_status, CASE WHEN (trim(CASE WHEN instr(replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), '||') > 0 THEN substr(replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), 1, instr(replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), '||') - 1) ELSE replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC') END) GLOB '* SC*' OR trim(CASE WHEN instr(replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), '||') > 0 THEN substr(replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), 1, instr(replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), '||') - 1) ELSE replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC') END) GLOB '* QC*' OR trim(CASE WHEN instr(replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), '||') > 0 THEN substr(replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), 1, instr(replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), '||') - 1) ELSE replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC') END) GLOB '* S.C*' OR trim(CASE WHEN instr(replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), '||') > 0 THEN substr(replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), 1, instr(replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC'), '||') - 1) ELSE replace(replace(replace(replace(replace(replace(counsel_for_respondent, ' & ', '||'), ', ', '||'), 'SCMr', 'SC||Mr'), 'QCDr', 'QC||Dr'), 'QCMr', 'QC||Mr'), '|| QC', ' QC') END) GLOB '* Q.C*') THEN 'senior counsel' ELSE 'other counsel' END AS lead_counsel, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate FROM legal WHERE defendant_current_status IN ('Government', 'Company', 'Organization') AND counsel_for_respondent IS NOT NULL AND counsel_for_respondent <> '' AND counsel_for_respondent NOT LIKE '%in person%' AND counsel_for_respondent NOT LIKE '%Solicitor%' GROUP BY defendant_current_status, lead_counsel;
```

</details>

### G3 · `legal.defendant` · fine-vs-coarse

legal.defendant names the immigration minister under the portfolio title of the time; one question counts the minister as one party, the other needs each title as written

| Question | Asks |
|---|---|
| G3a | Per judgment year: how many cases were brought against the immigration minister (under any title the portfolio had), how many were dismissed, and how many approved? |
| G3b | The immigration portfolio was renamed twice in this period (Immigration and Multicultural and Indigenous Affairs, then Immigration and Multicultural Affairs, then Immigration and Citizenship). For each title the minister is sued under: how many cases, what share were dismissed, and in which judgment years does the title first and last appear? |

**ALT for G3a**: rows changed 84; G3a keeps 1.0; breaks G3b 0.05 / 0.05

```sql
UPDATE legal SET defendant = 'Minister for Immigration and Citizenship' WHERE defendant LIKE 'Minister for Immigration%';
```

<details><summary>SQL</summary>

```sql
-- G3a
SELECT judgment_year, COUNT(*) AS cases, SUM(CASE WHEN verdict = 'Dismissed' THEN 1 ELSE 0 END) AS dismissed, SUM(CASE WHEN verdict = 'Approved' THEN 1 ELSE 0 END) AS approved FROM legal WHERE defendant LIKE 'Minister for Immigration%' AND judgment_year IS NOT NULL AND judgment_year <> '' GROUP BY judgment_year;
```
```sql
-- G3b
SELECT CASE WHEN defendant LIKE '%Indigenous%' THEN 'Immigration and Multicultural and Indigenous Affairs' WHEN defendant LIKE '%Multicultural%' THEN 'Immigration and Multicultural Affairs' WHEN defendant LIKE '%Citizenship%' THEN 'Immigration and Citizenship' ELSE 'other title' END AS portfolio_title, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate, MIN(judgment_year) AS first_year, MAX(judgment_year) AS last_year FROM legal WHERE defendant LIKE 'Minister for Immigration%' AND judgment_year IS NOT NULL AND judgment_year <> '' GROUP BY portfolio_title;
```

</details>

### G4 · `legal.charges` · fine-vs-coarse

legal.charges states the charges or grounds as the judgment words them; one question needs only the area of law they fall in, the others the specific grounds or the Act invoked

| Question | Asks |
|---|---|
| G4a | For areas of law with at least 20 cases, grouping cases by the area their charges mention (refugee, visa or migration; misleading or deceptive conduct; tax; patent, copyright, trade mark or other intellectual property; bankruptcy or insolvency; anything else): how many cases, what share were approved, what share dismissed, and how many statutes are cited on average? |
| G4b | Per judgment year, among cases against the immigration minister: how many cases, and in how many do the charges allege a denial of procedural fairness (including procedural unfairness), a breach of section 424A of the Migration Act, or bias (actual or apprehended)? |
| G4c | For civil and commercial cases, by which Act the charges invoke (the Trade Practices Act; otherwise the Corporations Act or Corporations Law; otherwise neither): how many cases, what share were approved, and what share dismissed? |

**ALT for G4a**: rows changed 539; G4a keeps 1.0; breaks G4b 0.31 / 0.38, G4c 0.00 / 0.06 · **Flags:** long question: G4a

```sql
UPDATE legal SET charges = CASE WHEN charges LIKE '%refugee%' OR charges LIKE '%visa%' OR charges LIKE '%migration%' THEN 'immigration' WHEN charges LIKE '%misleading%' OR charges LIKE '%deceptive%' THEN 'misleading or deceptive conduct' WHEN charges LIKE '%tax%' THEN 'taxation' WHEN charges LIKE '%patent%' OR charges LIKE '%copyright%' OR charges LIKE '%trade mark%' OR charges LIKE '%trademark%' OR charges LIKE '%intellectual property%' THEN 'intellectual property' WHEN charges LIKE '%bankrupt%' OR charges LIKE '%insolven%' THEN 'insolvency' ELSE 'other' END WHERE charges IS NOT NULL AND charges <> '';
```

<details><summary>SQL</summary>

```sql
-- G4a
SELECT CASE WHEN charges LIKE '%refugee%' OR charges LIKE '%visa%' OR charges LIKE '%migration%' THEN 'migration' WHEN charges LIKE '%misleading%' OR charges LIKE '%deceptive%' THEN 'misleading conduct' WHEN charges LIKE '%tax%' THEN 'tax' WHEN charges LIKE '%patent%' OR charges LIKE '%copyright%' OR charges LIKE '%trade mark%' OR charges LIKE '%trademark%' OR charges LIKE '%intellectual property%' THEN 'intellectual property' WHEN charges LIKE '%bankrupt%' OR charges LIKE '%insolven%' THEN 'insolvency' ELSE 'other' END AS area, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Approved' THEN 1.0 ELSE 0.0 END) AS approval_rate, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate, AVG(legal_basis_num) AS average_statutes FROM legal WHERE charges IS NOT NULL AND charges <> '' GROUP BY area HAVING COUNT(*) >= 20;
```
```sql
-- G4b
SELECT judgment_year, COUNT(*) AS cases, SUM(CASE WHEN charges LIKE '%procedural fairness%' OR charges LIKE '%procedural unfairness%' OR charges LIKE '%procedurally unfair%' THEN 1 ELSE 0 END) AS procedural_fairness, SUM(CASE WHEN charges LIKE '%424A%' THEN 1 ELSE 0 END) AS section_424a, SUM(CASE WHEN charges LIKE '%bias%' THEN 1 ELSE 0 END) AS bias FROM legal WHERE defendant LIKE 'Minister for Immigration%' AND judgment_year IS NOT NULL AND judgment_year <> '' GROUP BY judgment_year;
```
```sql
-- G4c
SELECT CASE WHEN charges LIKE '%Trade Practices%' THEN 'Trade Practices Act' WHEN charges LIKE '%Corporations Act%' OR charges LIKE '%Corporations Law%' THEN 'Corporations Act or Law' ELSE 'neither' END AS act_invoked, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Approved' THEN 1.0 ELSE 0.0 END) AS approval_rate, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate FROM legal WHERE case_type IN ('Civil Case', 'Commercial Case') AND charges IS NOT NULL AND charges <> '' GROUP BY act_invoked;
```

</details>

### G5 · `legal.nationality_for_applicant` · fine-vs-coarse

legal.nationality_for_applicant holds the applicant's country as stated; one question needs only the world region, the other the country

| Question | Asks |
|---|---|
| G5a | By where the applicant comes from (Australia, or for foreign applicants their region: South Asia, East Asia, South-East Asia, the Pacific including New Zealand and Papua New Guinea, Europe including Armenia, the Middle East and North Africa including Turkey, Lebanon, Egypt and Libya, and the rest of Africa together with the Americas): how many cases, what share were dismissed, and how many were against the immigration minister? |
| G5b | Among South Asian applicants (from India, Bangladesh, Sri Lanka, Pakistan or Nepal): how many cases does each nationality bring, how many were dismissed, and how many were approved? |

**ALT for G5a**: rows changed 220; G5a keeps 1.0; breaks G5b 0.00 / 0.00 · **Flags:** long question: G5a

```sql
UPDATE legal SET nationality_for_applicant = CASE WHEN nationality_for_applicant IN ('India', 'Bangladesh', 'Sri Lanka', 'Pakistan', 'Nepal') THEN 'South Asia' WHEN nationality_for_applicant IN ('China', 'Korea', 'South Korea', 'Mongolia') THEN 'East Asia' WHEN nationality_for_applicant IN ('Indonesia', 'Republic of Indonesia', 'Vietnam', 'Malaysia', 'Philippines', 'Thai') THEN 'South-East Asia' WHEN nationality_for_applicant IN ('Fiji', 'Tonga', 'Papua New Guinea', 'New Zealand') THEN 'Pacific' WHEN nationality_for_applicant IN ('United Kingdom', 'British', 'Bulgaria', 'Greece', 'Latvia', 'Romania', 'Russian Federation', 'Ukraine', 'France', 'Switzerland', 'Former Yugoslav Republic of Macedonia', 'Armenia') THEN 'Europe' WHEN nationality_for_applicant IN ('Lebanon', 'Turkey', 'Egypt', 'Libya') THEN 'Middle East and North Africa' WHEN nationality_for_applicant IN ('Ethiopia', 'Nigeria', 'South Africa', 'United States', 'Chile') THEN 'Africa and the Americas' ELSE nationality_for_applicant END WHERE nationality_for_applicant IS NOT NULL AND nationality_for_applicant <> '';
```

<details><summary>SQL</summary>

```sql
-- G5a
SELECT CASE WHEN nationality_for_applicant IN ('India', 'Bangladesh', 'Sri Lanka', 'Pakistan', 'Nepal') THEN 'South Asia' WHEN nationality_for_applicant IN ('China', 'Korea', 'South Korea', 'Mongolia') THEN 'East Asia' WHEN nationality_for_applicant IN ('Indonesia', 'Republic of Indonesia', 'Vietnam', 'Malaysia', 'Philippines', 'Thai') THEN 'South-East Asia' WHEN nationality_for_applicant IN ('Fiji', 'Tonga', 'Papua New Guinea', 'New Zealand') THEN 'Pacific' WHEN nationality_for_applicant IN ('United Kingdom', 'British', 'Bulgaria', 'Greece', 'Latvia', 'Romania', 'Russian Federation', 'Ukraine', 'France', 'Switzerland', 'Former Yugoslav Republic of Macedonia', 'Armenia') THEN 'Europe' WHEN nationality_for_applicant IN ('Lebanon', 'Turkey', 'Egypt', 'Libya') THEN 'Middle East and North Africa' WHEN nationality_for_applicant IN ('Ethiopia', 'Nigeria', 'South Africa', 'United States', 'Chile') THEN 'Africa and the Americas' ELSE nationality_for_applicant END AS origin, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate, SUM(CASE WHEN defendant LIKE 'Minister for Immigration%' THEN 1 ELSE 0 END) AS against_immigration_minister FROM legal WHERE nationality_for_applicant IS NOT NULL AND nationality_for_applicant <> '' GROUP BY origin;
```
```sql
-- G5b
SELECT nationality_for_applicant, COUNT(*) AS cases, SUM(CASE WHEN verdict = 'Dismissed' THEN 1 ELSE 0 END) AS dismissed, SUM(CASE WHEN verdict = 'Approved' THEN 1 ELSE 0 END) AS approved FROM legal WHERE nationality_for_applicant IN ('India', 'Bangladesh', 'Sri Lanka', 'Pakistan', 'Nepal') GROUP BY nationality_for_applicant;
```

</details>

### G6 · `legal.case_type` · fine-vs-coarse

legal.case_type distinguishes commercial from other civil cases; one question treats commercial cases as civil, the other compares the two

| Question | Asks |
|---|---|
| G6a | Splitting cases into civil disputes (counting commercial cases as civil), administrative cases and criminal cases: how many cases, what share were approved, and what share dismissed? |
| G6b | How do commercial cases differ from other civil cases: how many cases, how many statutes and precedents are cited on average, and in how many is the defendant a company? |

**ALT for G6a**: rows changed 59; G6a keeps 1.0; breaks G6b 0.00 / 0.00

```sql
UPDATE legal SET case_type = 'Civil Case' WHERE case_type = 'Commercial Case';
```

<details><summary>SQL</summary>

```sql
-- G6a
SELECT CASE WHEN case_type IN ('Civil Case', 'Commercial Case') THEN 'civil' WHEN case_type = 'Administrative Case' THEN 'administrative' ELSE 'criminal' END AS kind_of_case, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Approved' THEN 1.0 ELSE 0.0 END) AS approval_rate, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate FROM legal WHERE case_type IN ('Civil Case', 'Commercial Case', 'Administrative Case', 'Criminal Case') GROUP BY kind_of_case;
```
```sql
-- G6b
SELECT case_type, COUNT(*) AS cases, AVG(legal_basis_num) AS average_statutes, AVG(NULLIF(case_number, '')) AS average_precedents, SUM(CASE WHEN defendant_current_status = 'Company' THEN 1 ELSE 0 END) AS company_defendants FROM legal WHERE case_type IN ('Civil Case', 'Commercial Case') GROUP BY case_type;
```

</details>

### G7 · `legal.plaintiff_current_status` · fine-vs-coarse

legal.plaintiff_current_status holds the plaintiff's kind or, for a person, their stated occupation or situation; one question needs only the kind of party, the other the stated description of individual applicants

| Question | Asks |
|---|---|
| G7a | By kind of plaintiff (company; organization; government, counting regulators, commissioners, inspectors, departments, ministers, customs, the army and registrars as government; or an individual): how many cases, what share were approved, what share dismissed, and in what share was a fine imposed? |
| G7b | For individual applicants described as visa applicants, refugees, students (including international students) or employees (including former employees): how many cases, what share were dismissed, and how many were against the immigration minister? |

**ALT for G7a**: rows changed 147; G7a keeps 1.0; breaks G7b 0.00 / 0.00

```sql
UPDATE legal SET plaintiff_current_status = CASE WHEN plaintiff_current_status = 'Government' OR plaintiff_current_status LIKE '%Commission%' OR plaintiff_current_status LIKE '%Department%' OR plaintiff_current_status LIKE '%Minister%' OR plaintiff_current_status LIKE '%Customs%' OR plaintiff_current_status LIKE '%Army%' OR plaintiff_current_status LIKE '%Registrar%' OR plaintiff_current_status LIKE '%Inspector%' THEN 'Government' WHEN plaintiff_current_status IN ('Company', 'Campany') THEN 'Company' WHEN plaintiff_current_status = 'Organization' THEN 'Organization' ELSE 'Individual' END WHERE plaintiff_current_status IS NOT NULL AND plaintiff_current_status <> '';
```

<details><summary>SQL</summary>

```sql
-- G7a
SELECT CASE WHEN plaintiff_current_status = 'Government' OR plaintiff_current_status LIKE '%Commission%' OR plaintiff_current_status LIKE '%Department%' OR plaintiff_current_status LIKE '%Minister%' OR plaintiff_current_status LIKE '%Customs%' OR plaintiff_current_status LIKE '%Army%' OR plaintiff_current_status LIKE '%Registrar%' OR plaintiff_current_status LIKE '%Inspector%' THEN 'government' WHEN plaintiff_current_status IN ('Company', 'Campany') THEN 'company' WHEN plaintiff_current_status = 'Organization' THEN 'organization' ELSE 'individual' END AS plaintiff_kind, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Approved' THEN 1.0 ELSE 0.0 END) AS approval_rate, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate, AVG(CASE WHEN CAST(fine_amount AS REAL) > 0 THEN 1.0 ELSE 0.0 END) AS fined_share FROM legal WHERE plaintiff_current_status IS NOT NULL AND plaintiff_current_status <> '' GROUP BY plaintiff_kind;
```
```sql
-- G7b
SELECT CASE WHEN plaintiff_current_status LIKE 'Visa Applica%' THEN 'visa applicant' WHEN plaintiff_current_status LIKE '%Refugee%' THEN 'refugee' WHEN plaintiff_current_status LIKE '%Student%' THEN 'student' ELSE 'employee' END AS applicant_description, COUNT(*) AS cases, AVG(CASE WHEN verdict = 'Dismissed' THEN 1.0 ELSE 0.0 END) AS dismissal_rate, SUM(CASE WHEN defendant LIKE 'Minister for Immigration%' THEN 1 ELSE 0 END) AS against_immigration_minister FROM legal WHERE plaintiff_current_status LIKE 'Visa Applica%' OR plaintiff_current_status LIKE '%Refugee%' OR plaintiff_current_status LIKE '%Student%' OR plaintiff_current_status LIKE '%Employee%' GROUP BY applicant_description;
```

</details>


## Med (`Query/Realistic/conflict/med.sql`)

### G1 · `disease.disease_type` · list-vs-one

disease.disease_type lists every classification of a disease; G1a counts a disease under each classification it has, G1b files each disease under one class by a stated precedence (the single label a one-type categoriser would store)

| Question | Asks |
|---|---|
| G1a | Per expected outcome (high mortality; otherwise chronic; otherwise other or not stated): how many diseases have an inflammatory, an infectious, a vascular and a degenerative component, counting a disease under every classification it has? |
| G1b | Counting each disease once, under the first of these classes it has (infectious; cancer; psychiatric; genetic; vascular; inflammatory or autoimmune; other): how many diseases are in each class, and how many of them are chronic and how many have high mortality? |

**ALT for G1b**: rows changed 58; G1b keeps 1.0; breaks G1a 0.40 / 0.67

```sql
UPDATE disease SET disease_type = CASE WHEN disease_type LIKE '%infectious%' THEN 'infectious' WHEN disease_type LIKE '%neoplastic%' THEN 'neoplastic' WHEN disease_type LIKE '%psychiatric%' THEN 'psychiatric' WHEN disease_type LIKE '%genetic%' THEN 'genetic' WHEN disease_type LIKE '%vascular%' THEN 'vascular' WHEN disease_type LIKE '%inflammatory%' THEN 'inflammatory' WHEN disease_type LIKE '%autoimmune%' THEN 'autoimmune' ELSE 'others' END WHERE disease_type <> '';
```

<details><summary>SQL</summary>

```sql
-- G1a
SELECT CASE WHEN prognosis LIKE '%high_mortality%' THEN 'high mortality' WHEN prognosis LIKE '%chronic%' THEN 'chronic' ELSE 'other or not stated' END AS outlook, COUNT(*) AS diseases, SUM(CASE WHEN disease_type LIKE '%inflammatory%' THEN 1 ELSE 0 END) AS inflammatory, SUM(CASE WHEN disease_type LIKE '%infectious%' THEN 1 ELSE 0 END) AS infectious, SUM(CASE WHEN disease_type LIKE '%vascular%' THEN 1 ELSE 0 END) AS vascular, SUM(CASE WHEN disease_type LIKE '%degenerative%' THEN 1 ELSE 0 END) AS degenerative FROM disease WHERE disease_type <> '' GROUP BY outlook;
```
```sql
-- G1b
SELECT CASE WHEN disease_type LIKE '%infectious%' THEN 'infectious' WHEN disease_type LIKE '%neoplastic%' THEN 'cancer' WHEN disease_type LIKE '%psychiatric%' THEN 'psychiatric' WHEN disease_type LIKE '%genetic%' THEN 'genetic' WHEN disease_type LIKE '%vascular%' THEN 'vascular' WHEN disease_type LIKE '%inflammatory%' OR disease_type LIKE '%autoimmune%' THEN 'inflammatory or autoimmune' ELSE 'other' END AS disease_class, COUNT(*) AS diseases, SUM(CASE WHEN prognosis LIKE '%chronic%' THEN 1 ELSE 0 END) AS chronic, SUM(CASE WHEN prognosis LIKE '%high_mortality%' THEN 1 ELSE 0 END) AS high_mortality FROM disease WHERE disease_type <> '' GROUP BY disease_class;
```

</details>

### G2 · `disease.treatments` · list-vs-one

disease.treatments lists every treatment modality; G2a counts the modalities and asks whether surgery is among them, G2b files each disease under its most invasive common treatment (the single label a 'main treatment' reader would store)

| Question | Asks |
|---|---|
| G2a | Per kind of disease (infectious; cancer; psychiatric; inflammatory or autoimmune; other, taking the first that applies): how many diseases, how many different kinds of treatment such a disease receives on average, and how many of them are treated with surgery? |
| G2b | By the most invasive of the three common treatments a disease receives (surgery if it is treated with surgery; else injection; else oral medication; else none of these three): how many diseases, and how many of them are chronic? |

**ALT for G2b**: rows changed 60; G2b keeps 1.0; breaks G2a 0.67 / 0.67

```sql
UPDATE disease SET treatments = CASE WHEN treatments LIKE '%surgery%' THEN 'surgery' WHEN treatments LIKE '%injection%' THEN 'injection' WHEN treatments LIKE '%oral_medication%' THEN 'oral_medication' ELSE 'others' END WHERE treatments <> '';
```

<details><summary>SQL</summary>

```sql
-- G2a
SELECT CASE WHEN disease_type LIKE '%infectious%' THEN 'infectious' WHEN disease_type LIKE '%neoplastic%' THEN 'cancer' WHEN disease_type LIKE '%psychiatric%' THEN 'psychiatric' WHEN disease_type LIKE '%inflammatory%' OR disease_type LIKE '%autoimmune%' THEN 'inflammatory or autoimmune' ELSE 'other' END AS kind, COUNT(*) AS diseases, ROUND(AVG(CAST((LENGTH(treatments) - LENGTH(REPLACE(treatments, '||', ''))) / 2 + 1 AS REAL)), 2) AS avg_treatment_kinds, SUM(CASE WHEN treatments LIKE '%surgery%' THEN 1 ELSE 0 END) AS surgery FROM disease WHERE disease_type <> '' AND treatments <> '' GROUP BY kind;
```
```sql
-- G2b
SELECT CASE WHEN treatments LIKE '%surgery%' THEN 'surgery' WHEN treatments LIKE '%injection%' THEN 'injection' WHEN treatments LIKE '%oral_medication%' THEN 'oral medication' ELSE 'none of these three' END AS most_invasive_treatment, COUNT(*) AS diseases, SUM(CASE WHEN prognosis LIKE '%chronic%' THEN 1 ELSE 0 END) AS chronic FROM disease WHERE treatments <> '' GROUP BY most_invasive_treatment;
```

</details>

### G3 · `disease.pathogenesis` · fine-vs-coarse

disease.pathogenesis states the fine mechanism (infectious_bacterial, infectious_viral, genetic_mutation, ...); G3a needs the germ type, G3b only the broad mechanism (infectious, genetic, ...) that a merged form keeps

| Question | Asks |
|---|---|
| G3a | Among diseases whose stated mechanisms include an infection: how many are bacterial, how many viral (and not also bacterial), and how many parasitic (neither bacterial nor viral), and how many of each are treated with oral medication and how many with injections? |
| G3b | Per disease mechanism (infectious, genetic, cancer, inflammatory or autoimmune, vascular or degenerative, other; a disease with several mechanisms is counted under the first of these): how many diseases, how many are chronic, and how many are treated with surgery? |

**ALT for G3b**: rows changed 44; G3b keeps 1.0; breaks G3a 0.00 / 0.00

```sql
UPDATE disease SET pathogenesis = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(pathogenesis, 'infectious_bacterial', 'infectious'), 'infectious_viral', 'infectious'), 'infectious_parasitic', 'infectious'), 'infectious_fungal', 'infectious'), 'genetic_mutation', 'genetic'), 'metabolic_disorder', 'metabolic'), 'endocrine_disorder', 'endocrine'), 'nutritional_deficiency', 'nutritional');
```

<details><summary>SQL</summary>

```sql
-- G3a
SELECT CASE WHEN pathogenesis LIKE '%infectious_bacterial%' THEN 'bacterial' WHEN pathogenesis LIKE '%infectious_viral%' THEN 'viral' WHEN pathogenesis LIKE '%infectious_parasitic%' THEN 'parasitic' ELSE 'fungal' END AS germ, COUNT(*) AS diseases, SUM(CASE WHEN treatments LIKE '%oral_medication%' THEN 1 ELSE 0 END) AS oral_medication, SUM(CASE WHEN treatments LIKE '%injection%' THEN 1 ELSE 0 END) AS injection FROM disease WHERE pathogenesis LIKE '%infectious_bacterial%' OR pathogenesis LIKE '%infectious_viral%' OR pathogenesis LIKE '%infectious_parasitic%' OR pathogenesis LIKE '%infectious_fungal%' GROUP BY germ;
```
```sql
-- G3b
SELECT CASE WHEN pathogenesis LIKE '%infectious%' THEN 'infectious' WHEN pathogenesis LIKE '%genetic%' THEN 'genetic' WHEN pathogenesis LIKE '%neoplastic%' THEN 'cancer' WHEN pathogenesis LIKE '%inflammatory%' OR pathogenesis LIKE '%autoimmune%' THEN 'inflammatory or autoimmune' WHEN pathogenesis LIKE '%vascular%' OR pathogenesis LIKE '%degenerative%' THEN 'vascular or degenerative' ELSE 'other' END AS mechanism, COUNT(*) AS diseases, SUM(CASE WHEN prognosis LIKE '%chronic%' THEN 1 ELSE 0 END) AS chronic, SUM(CASE WHEN treatments LIKE '%surgery%' THEN 1 ELSE 0 END) AS surgery FROM disease WHERE pathogenesis <> '' GROUP BY mechanism;
```

</details>

### G4 · `drug.unsuitable_population` · fine-vs-coarse

drug.unsuitable_population states each group that should avoid the drug as the label words it (children under 6, nursing mothers, geriatric patients, ...); G4a needs only four broad groups, G4b the youngest stated age limit for children, G4c the breastfeeding warning. ALT G4a is the broad-group normalisation; ALT G4b is a children-only extraction (a per-question prompt that asks only about children). Each breaks the others.

| Question | Asks |
|---|---|
| G4a | Among drugs for people (veterinary labels for dogs and puppies left out), per prescription status (prescription only, over the counter, other or not stated): how many drugs name groups that should avoid them, and how many should be avoided in pregnancy, by children (including infants and pediatric patients), by the elderly (including geriatric patients, older adults and people of old age), and by patients with liver or kidney problems (including hepatic or renal impairment, nephropathy, and a low creatinine clearance or glomerular filtration rate)? |
| G4b | Among drugs whose label names children, infants or pediatric patients among those who should not take it (a warning about nursing infants counts as breastfeeding, not as children): how many labels set the age limit at under 2 years (including infants, younger than 1 year and younger than two months), under 6 years, under 12 to 18 years, or state no age (the youngest limit stated counts), and how many of each are prescription-only? |
| G4c | Among drugs for people whose route is stated, taken by mouth or by another route: how many should be avoided in pregnancy, and how many of those also when breastfeeding (breastfeeding or nursing women, mothers or infants)? |

**ALT for G4a**: rows changed 55; G4a keeps 1.0; breaks G4b 0.00 / 0.00, G4c 0.50 / 0.75 · **Flags:** long question: G4a, G4b

```sql
UPDATE drug SET unsuitable_population = COALESCE(NULLIF(RTRIM(CASE WHEN unsuitable_population LIKE '%pregnan%' THEN 'pregnant women||' ELSE '' END || CASE WHEN (unsuitable_population LIKE '%child%' OR unsuitable_population LIKE '%pediatric%' OR REPLACE(unsuitable_population, 'nursing infants', '') LIKE '%infant%') THEN 'children||' ELSE '' END || CASE WHEN (unsuitable_population LIKE '%elderly%' OR unsuitable_population LIKE '%older adult%' OR unsuitable_population LIKE '%geriatric%' OR unsuitable_population LIKE '%old age%') THEN 'elderly||' ELSE '' END || CASE WHEN (unsuitable_population LIKE '%liver%' OR unsuitable_population LIKE '%hepatic%' OR unsuitable_population LIKE '%kidney%' OR unsuitable_population LIKE '%renal%' OR unsuitable_population LIKE '%nephro%' OR unsuitable_population LIKE '%creatinine%' OR unsuitable_population LIKE '%glomerular%') THEN 'patients with liver or kidney problems' ELSE '' END, '|'), ''), 'other groups') WHERE unsuitable_population <> '' AND unsuitable_population NOT LIKE '%dog%' AND unsuitable_population NOT LIKE '%pupp%';
```

**ALT for G4b**: rows changed 58; G4b keeps 1.0; breaks G4a 0.33 / 0.53, G4c 0.00 / 0.00 · **Flags:** long question: G4a, G4b

```sql
UPDATE drug SET unsuitable_population = CASE WHEN NOT (unsuitable_population LIKE '%child%' OR unsuitable_population LIKE '%pediatric%' OR REPLACE(unsuitable_population, 'nursing infants', '') LIKE '%infant%') THEN '' WHEN (unsuitable_population LIKE '%under 2 %' OR unsuitable_population LIKE '%younger than 1||%' OR unsuitable_population LIKE '%younger than 1' OR unsuitable_population LIKE '%two months%' OR unsuitable_population LIKE '%under one year%' OR REPLACE(unsuitable_population, 'nursing infants', '') LIKE '%infant%') THEN 'children under 2 years' WHEN unsuitable_population LIKE '%under 6%' THEN 'children under 6 years' WHEN unsuitable_population LIKE '%under 12%' THEN 'children under 12 years' WHEN unsuitable_population LIKE '%under 18%' OR unsuitable_population LIKE '%age of 18%' THEN 'children under 18 years' ELSE 'children' END;
```

<details><summary>SQL</summary>

```sql
-- G4a
SELECT CASE WHEN prescription_status LIKE '%prescription_only%' THEN 'prescription only' WHEN prescription_status LIKE '%over_the_counter%' THEN 'over the counter' ELSE 'other or not stated' END AS status, COUNT(*) AS drugs, SUM(CASE WHEN unsuitable_population LIKE '%pregnan%' THEN 1 ELSE 0 END) AS pregnancy, SUM(CASE WHEN (unsuitable_population LIKE '%child%' OR unsuitable_population LIKE '%pediatric%' OR REPLACE(unsuitable_population, 'nursing infants', '') LIKE '%infant%') THEN 1 ELSE 0 END) AS children, SUM(CASE WHEN (unsuitable_population LIKE '%elderly%' OR unsuitable_population LIKE '%older adult%' OR unsuitable_population LIKE '%geriatric%' OR unsuitable_population LIKE '%old age%') THEN 1 ELSE 0 END) AS elderly, SUM(CASE WHEN (unsuitable_population LIKE '%liver%' OR unsuitable_population LIKE '%hepatic%' OR unsuitable_population LIKE '%kidney%' OR unsuitable_population LIKE '%renal%' OR unsuitable_population LIKE '%nephro%' OR unsuitable_population LIKE '%creatinine%' OR unsuitable_population LIKE '%glomerular%') THEN 1 ELSE 0 END) AS liver_or_kidney FROM drug WHERE unsuitable_population <> '' AND unsuitable_population NOT LIKE '%dog%' AND unsuitable_population NOT LIKE '%pupp%' GROUP BY status;
```
```sql
-- G4b
SELECT CASE WHEN (unsuitable_population LIKE '%under 2 %' OR unsuitable_population LIKE '%younger than 1||%' OR unsuitable_population LIKE '%younger than 1' OR unsuitable_population LIKE '%two months%' OR unsuitable_population LIKE '%under one year%' OR REPLACE(unsuitable_population, 'nursing infants', '') LIKE '%infant%') THEN 'under 2' WHEN unsuitable_population LIKE '%under 6%' THEN 'under 6' WHEN (unsuitable_population LIKE '%under 12%' OR unsuitable_population LIKE '%under 18%' OR unsuitable_population LIKE '%age of 18%') THEN 'under 12 to 18' ELSE 'no age stated' END AS age_limit, COUNT(*) AS drugs, SUM(CASE WHEN prescription_status LIKE '%prescription_only%' THEN 1 ELSE 0 END) AS prescription_only FROM drug WHERE (unsuitable_population LIKE '%child%' OR unsuitable_population LIKE '%pediatric%' OR REPLACE(unsuitable_population, 'nursing infants', '') LIKE '%infant%') GROUP BY age_limit;
```
```sql
-- G4c
SELECT CASE WHEN administration_route LIKE '%oral%' THEN 'by mouth' ELSE 'another route' END AS route, COUNT(*) AS avoid_in_pregnancy, SUM(CASE WHEN (unsuitable_population LIKE '%breast%feeding%' OR unsuitable_population LIKE '%nursing%') THEN 1 ELSE 0 END) AS also_when_breastfeeding FROM drug WHERE unsuitable_population LIKE '%pregnan%' AND administration_route <> '' AND unsuitable_population NOT LIKE '%dog%' AND unsuitable_population NOT LIKE '%pupp%' GROUP BY route;
```

</details>

### G5 · `drug.dosage_frequency` · number-vs-text

drug.dosage_frequency states the schedule in words ('twice a day', 'every 4 to 6 hours as needed', several schedules joined by ||); G5a reads it as the most doses a day it allows, G5b needs the stated intervals in hours, ranges and choices, 'as needed' and the number of schedules. ALT G5a is the doses-a-day parse, written back as 'N times a day' (schedules that are not per day are kept as stated).

| Question | Asks |
|---|---|
| G5a | Reading each drug's dosing schedule as the most doses a day it allows (every 4 hours or 6 times = 6; every 6 hours or 4 times = 4; every 8 hours or 3 times = 3; every 12 hours or twice = 2; once a day or every 24 hours = 1; a range or choice such as 'every 4 to 6 hours' or 'once or twice a day' counts at its higher end, 'up to three times a day' as 3, an 'as needed' schedule by its interval, and with several schedules the highest counts; weekly, single-dose, session and treatment-cycle schedules and continuous infusions are left out): per prescription status (prescription only, other or not stated), how many drugs, the average of that number, and how many allow three or more doses a day? |
| G5b | Among drugs whose route is stated, taken by mouth or by another route: how many state a dosing schedule, how many state at least one schedule as an interval in hours (e.g. 'every 8 hours'), how many give a range or a choice of frequencies (e.g. 'every 4-6 hours', '3 to 4 times a day', 'once or twice a day'), how many are taken as needed, and how many state more than one schedule? |

**ALT for G5a**: rows changed 51; G5a keeps 1.0; breaks G5b 0.50 / 0.60 · **Flags:** long question: G5a, G5b

```sql
UPDATE drug SET dosage_frequency = CASE CASE WHEN dosage_frequency LIKE '%continuous%' THEN NULL WHEN dosage_frequency LIKE '%every 4 %hour%' OR dosage_frequency LIKE '%every 4-%hour%' OR dosage_frequency LIKE '%every four hour%' OR dosage_frequency LIKE '%6 times%' THEN 6 WHEN dosage_frequency LIKE '%every 6%hour%' OR dosage_frequency LIKE '%4 times%' OR dosage_frequency LIKE '%four times%' OR dosage_frequency LIKE '%4 doses%' THEN 4 WHEN dosage_frequency LIKE '%every 8%hour%' OR dosage_frequency LIKE '%3 times%' OR dosage_frequency LIKE '%three times%' OR dosage_frequency LIKE '%thrice%' THEN 3 WHEN dosage_frequency LIKE '%every 12%hour%' OR dosage_frequency LIKE '%twice%' OR dosage_frequency LIKE '%2 times%' THEN 2 WHEN dosage_frequency LIKE '%once daily%' OR dosage_frequency LIKE '%once a day%' OR dosage_frequency LIKE '%once per day%' OR dosage_frequency LIKE '%every 24 hour%' THEN 1 END WHEN 6 THEN '6 times a day' WHEN 4 THEN '4 times a day' WHEN 3 THEN '3 times a day' WHEN 2 THEN '2 times a day' WHEN 1 THEN 'once a day' ELSE dosage_frequency END WHERE dosage_frequency <> '';
```

<details><summary>SQL</summary>

```sql
-- G5a
SELECT CASE WHEN prescription_status LIKE '%prescription_only%' THEN 'prescription only' ELSE 'other or not stated' END AS status, COUNT(*) AS drugs, ROUND(AVG(CASE WHEN dosage_frequency LIKE '%continuous%' THEN NULL WHEN dosage_frequency LIKE '%every 4 %hour%' OR dosage_frequency LIKE '%every 4-%hour%' OR dosage_frequency LIKE '%every four hour%' OR dosage_frequency LIKE '%6 times%' THEN 6 WHEN dosage_frequency LIKE '%every 6%hour%' OR dosage_frequency LIKE '%4 times%' OR dosage_frequency LIKE '%four times%' OR dosage_frequency LIKE '%4 doses%' THEN 4 WHEN dosage_frequency LIKE '%every 8%hour%' OR dosage_frequency LIKE '%3 times%' OR dosage_frequency LIKE '%three times%' OR dosage_frequency LIKE '%thrice%' THEN 3 WHEN dosage_frequency LIKE '%every 12%hour%' OR dosage_frequency LIKE '%twice%' OR dosage_frequency LIKE '%2 times%' THEN 2 WHEN dosage_frequency LIKE '%once daily%' OR dosage_frequency LIKE '%once a day%' OR dosage_frequency LIKE '%once per day%' OR dosage_frequency LIKE '%every 24 hour%' THEN 1 END), 2) AS avg_most_doses_per_day, SUM(CASE WHEN CASE WHEN dosage_frequency LIKE '%continuous%' THEN NULL WHEN dosage_frequency LIKE '%every 4 %hour%' OR dosage_frequency LIKE '%every 4-%hour%' OR dosage_frequency LIKE '%every four hour%' OR dosage_frequency LIKE '%6 times%' THEN 6 WHEN dosage_frequency LIKE '%every 6%hour%' OR dosage_frequency LIKE '%4 times%' OR dosage_frequency LIKE '%four times%' OR dosage_frequency LIKE '%4 doses%' THEN 4 WHEN dosage_frequency LIKE '%every 8%hour%' OR dosage_frequency LIKE '%3 times%' OR dosage_frequency LIKE '%three times%' OR dosage_frequency LIKE '%thrice%' THEN 3 WHEN dosage_frequency LIKE '%every 12%hour%' OR dosage_frequency LIKE '%twice%' OR dosage_frequency LIKE '%2 times%' THEN 2 WHEN dosage_frequency LIKE '%once daily%' OR dosage_frequency LIKE '%once a day%' OR dosage_frequency LIKE '%once per day%' OR dosage_frequency LIKE '%every 24 hour%' THEN 1 END >= 3 THEN 1 ELSE 0 END) AS three_or_more_a_day FROM drug WHERE CASE WHEN dosage_frequency LIKE '%continuous%' THEN NULL WHEN dosage_frequency LIKE '%every 4 %hour%' OR dosage_frequency LIKE '%every 4-%hour%' OR dosage_frequency LIKE '%every four hour%' OR dosage_frequency LIKE '%6 times%' THEN 6 WHEN dosage_frequency LIKE '%every 6%hour%' OR dosage_frequency LIKE '%4 times%' OR dosage_frequency LIKE '%four times%' OR dosage_frequency LIKE '%4 doses%' THEN 4 WHEN dosage_frequency LIKE '%every 8%hour%' OR dosage_frequency LIKE '%3 times%' OR dosage_frequency LIKE '%three times%' OR dosage_frequency LIKE '%thrice%' THEN 3 WHEN dosage_frequency LIKE '%every 12%hour%' OR dosage_frequency LIKE '%twice%' OR dosage_frequency LIKE '%2 times%' THEN 2 WHEN dosage_frequency LIKE '%once daily%' OR dosage_frequency LIKE '%once a day%' OR dosage_frequency LIKE '%once per day%' OR dosage_frequency LIKE '%every 24 hour%' THEN 1 END IS NOT NULL GROUP BY status;
```
```sql
-- G5b
SELECT CASE WHEN administration_route LIKE '%oral%' THEN 'by mouth' ELSE 'another route' END AS route, COUNT(*) AS drugs, SUM(CASE WHEN dosage_frequency LIKE '%every%hour%' THEN 1 ELSE 0 END) AS interval_in_hours, SUM(CASE WHEN dosage_frequency LIKE '% or %' OR dosage_frequency GLOB '*[0-9]-[0-9]*' OR dosage_frequency GLOB '*[0-9] to *' THEN 1 ELSE 0 END) AS range_or_choice, SUM(CASE WHEN dosage_frequency LIKE '%as needed%' THEN 1 ELSE 0 END) AS as_needed, SUM(CASE WHEN dosage_frequency LIKE '%||%' THEN 1 ELSE 0 END) AS several_schedules FROM drug WHERE dosage_frequency <> '' AND administration_route <> '' GROUP BY route;
```

</details>

### G6 · `drug.disease_name` · join-spelling

drug.disease_name lists the conditions on a label as the label words them and is the join key to disease.disease_name; G6a joins label conditions to diseases and accepts both the label's wording (through a stated list of other names) and the disease table's names, G6b counts the conditions as the label lists them. ALT G6a is entity resolution: each label condition rewritten to the disease table's name, one entry per resolved disease (so 'Herpes simplex||Genital herpes||...||Cold sores' keeps one 'Herpes Simplex Virus Infection'); it keeps G6a and changes the label's own count of conditions.

| Question | Asks |
|---|---|
| G6a | Per kind of disease (infectious; psychiatric; metabolic or endocrine; other, taking the first that applies): how many drug-disease treatment pairs are there, and in how many is the drug prescription-only? A drug treats a disease when its label names the disease by the disease's (first) name, ignoring case, or by one of these other names: Attention Deficit Hyperactivity Disorder, ADHD or attention deficit disorder for Attention-Deficit Hyperactivity Disorder; Urinary Tract Infections for Urinary Tract Infection; HIV infection or human immunodeficiency virus infection for HIV-1 Infection; acute graft-vs-host disease for Acute Graft-Versus-Host Disease; herpes simplex, herpes labialis, cold sores or genital herpes for Herpes Simplex Virus Infection; type 2 diabetes for Type 2 Diabetes Mellitus; diabetes for Diabetes Mellitus; flu for Influenza; high blood pressure for Hypertension; sinusitis for Sinus Infection; otitis media for Ear Infections; bronchial asthma for Asthma. |
| G6b | Among drugs whose route is stated, taken by mouth or by another route: how many drugs name the conditions they treat, how many conditions a label names on average (each condition as the label lists it, so 'cold sores' and 'genital herpes' count as two), and how many labels name two or more conditions? |

**ALT for G6a**: rows changed 18; G6a keeps 1.0; breaks G6b 0.50 / 0.67 · **Flags:** only 18 rows change; long question: G6a

```sql
UPDATE drug SET disease_name = (WITH RECURSIVE split(item, rest, pos) AS (SELECT '', REPLACE(drug.disease_name, ' || ', '||') || '||', 0 UNION ALL SELECT substr(rest, 1, instr(rest, '||') - 1), substr(rest, instr(rest, '||') + 2), pos + 1 FROM split WHERE rest <> ''), resolved AS (SELECT CASE item WHEN 'Attention Deficit Hyperactivity Disorder' THEN 'Attention-Deficit Hyperactivity Disorder' WHEN 'ADHD' THEN 'Attention-Deficit Hyperactivity Disorder' WHEN 'attention deficit disorder' THEN 'Attention-Deficit Hyperactivity Disorder' WHEN 'Urinary Tract Infections' THEN 'Urinary Tract Infection' WHEN 'HIV infection' THEN 'HIV-1 Infection' WHEN 'Human immunodeficiency virus infection' THEN 'HIV-1 Infection' WHEN 'acute graft-vs-host disease' THEN 'Acute Graft-Versus-Host Disease' WHEN 'Herpes simplex' THEN 'Herpes Simplex Virus Infection' WHEN 'Herpes labialis' THEN 'Herpes Simplex Virus Infection' WHEN 'Cold sores' THEN 'Herpes Simplex Virus Infection' WHEN 'Genital herpes' THEN 'Herpes Simplex Virus Infection' WHEN 'Type 2 Diabetes' THEN 'Type 2 Diabetes Mellitus' WHEN 'Diabetes' THEN 'Diabetes Mellitus' WHEN 'Flu' THEN 'Influenza' WHEN 'High Blood Pressure' THEN 'Hypertension' WHEN 'Sinusitis' THEN 'Sinus Infection' WHEN 'otitis media' THEN 'Ear Infections' WHEN 'Bronchial asthma' THEN 'Asthma' ELSE item END AS name, MIN(pos) AS first_pos FROM split WHERE pos > 0 GROUP BY name) SELECT group_concat(name, '||') FROM (SELECT name FROM resolved ORDER BY first_pos)) WHERE disease_name <> '';
```

<details><summary>SQL</summary>

```sql
-- G6a
SELECT CASE WHEN disease.disease_type LIKE '%infectious%' THEN 'infectious' WHEN disease.disease_type LIKE '%psychiatric%' THEN 'psychiatric' WHEN disease.disease_type LIKE '%metabolic%' OR disease.disease_type LIKE '%endocrine%' THEN 'metabolic or endocrine' ELSE 'other' END AS kind, COUNT(*) AS pairs, SUM(CASE WHEN drug.prescription_status LIKE '%prescription_only%' THEN 1 ELSE 0 END) AS prescription_only FROM drug JOIN disease ON REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE('||' || LOWER(REPLACE(drug.disease_name, ' || ', '||')) || '||', '||attention deficit hyperactivity disorder||', '||attention-deficit hyperactivity disorder||'), '||adhd||', '||attention-deficit hyperactivity disorder||'), '||attention deficit disorder||', '||attention-deficit hyperactivity disorder||'), '||urinary tract infections||', '||urinary tract infection||'), '||hiv infection||', '||hiv-1 infection||'), '||human immunodeficiency virus infection||', '||hiv-1 infection||'), '||acute graft-vs-host disease||', '||acute graft-versus-host disease||'), '||herpes simplex||', '||herpes simplex virus infection||'), '||herpes labialis||', '||herpes simplex virus infection||'), '||cold sores||', '||herpes simplex virus infection||'), '||genital herpes||', '||herpes simplex virus infection||'), '||type 2 diabetes||', '||type 2 diabetes mellitus||'), '||diabetes||', '||diabetes mellitus||'), '||flu||', '||influenza||'), '||high blood pressure||', '||hypertension||'), '||sinusitis||', '||sinus infection||'), '||otitis media||', '||ear infections||'), '||bronchial asthma||', '||asthma||') LIKE '%||' || LOWER(CASE WHEN instr(disease.disease_name, '||') > 0 THEN substr(disease.disease_name, 1, instr(disease.disease_name, '||') - 1) ELSE disease.disease_name END) || '||%' GROUP BY kind;
```
```sql
-- G6b
SELECT CASE WHEN administration_route LIKE '%oral%' THEN 'by mouth' ELSE 'another route' END AS route, COUNT(*) AS drugs, ROUND(AVG(CAST((LENGTH(disease_name) - LENGTH(REPLACE(disease_name, '||', ''))) / 2 + 1 AS REAL)), 2) AS avg_conditions_named, SUM(CASE WHEN disease_name LIKE '%||%' THEN 1 ELSE 0 END) AS two_or_more_conditions FROM drug WHERE disease_name <> '' AND administration_route <> '' GROUP BY route;
```

</details>

### G7 · `disease.affected_organs` · fine-vs-coarse

disease.affected_organs lists the organs a disease affects; G7a needs the body systems (a disease counts under each system it affects), G7b specific organs (liver, kidneys, eyes, brain) that a body-system form merges into a system or drops

| Question | Asks |
|---|---|
| G7a | Per kind of disease (infectious; cancer; other, taking the first that applies), among diseases whose affected organs are stated: how many diseases, and how many affect the lungs and airways (including the pleura and sinuses), the heart and blood vessels (arteries, veins), the nervous system (brain, nerves), the digestive system (gut, stomach, intestines, bowel, colon, esophagus, liver, abdomen), the skin, the bones, joints and muscles (including the spine, ligaments and tendons, but not bone marrow), and the kidneys and urinary tract (bladder, urethra)? A disease counts under every system it affects. |
| G7b | For infectious and other diseases whose affected organs are stated: how many diseases, and how many affect the liver, the kidneys, the eyes (including the retina, macula and optic nerve), and the brain? |

**ALT for G7a**: rows changed 78; G7a keeps 1.0; breaks G7b 0.30 / 0.30 · **Flags:** long question: G7a

```sql
UPDATE disease SET affected_organs = COALESCE(NULLIF(RTRIM(CASE WHEN (affected_organs LIKE '%lung%' OR affected_organs LIKE '%respirat%' OR affected_organs LIKE '%pleura%' OR affected_organs LIKE '%sinus%') THEN 'lungs and airways||' ELSE '' END || CASE WHEN (affected_organs LIKE '%heart%' OR affected_organs LIKE '%arter%' OR affected_organs LIKE '%vessel%' OR affected_organs LIKE '%vein%' OR affected_organs LIKE '%vascular%') THEN 'heart and blood vessels||' ELSE '' END || CASE WHEN (affected_organs LIKE '%brain%' OR affected_organs LIKE '%nerv%') THEN 'nervous system||' ELSE '' END || CASE WHEN (affected_organs LIKE '%gut%' OR affected_organs LIKE '%gastro%' OR affected_organs LIKE '%digest%' OR affected_organs LIKE '%intestin%' OR affected_organs LIKE '%bowel%' OR affected_organs LIKE '%colon%' OR affected_organs LIKE '%esophag%' OR affected_organs LIKE '%stomach%' OR affected_organs LIKE '%liver%' OR affected_organs LIKE '%abdom%') THEN 'digestive system||' ELSE '' END || CASE WHEN (affected_organs LIKE '%skin%' OR affected_organs LIKE '%derm%') THEN 'skin||' ELSE '' END || CASE WHEN (REPLACE(affected_organs, 'bone marrow', '') LIKE '%bone%' OR affected_organs LIKE '%joint%' OR affected_organs LIKE '%muscle%' OR affected_organs LIKE '%spine%' OR affected_organs LIKE '%ligament%' OR affected_organs LIKE '%tendon%') THEN 'bones, joints and muscles||' ELSE '' END || CASE WHEN (affected_organs LIKE '%kidney%' OR affected_organs LIKE '%urinary%' OR affected_organs LIKE '%bladder%' OR affected_organs LIKE '%urethra%') THEN 'kidneys and urinary tract||' ELSE '' END, '|'), ''), 'other') WHERE affected_organs <> '';
```

<details><summary>SQL</summary>

```sql
-- G7a
SELECT CASE WHEN disease_type LIKE '%infectious%' THEN 'infectious' WHEN disease_type LIKE '%neoplastic%' THEN 'cancer' ELSE 'other' END AS kind, COUNT(*) AS diseases, SUM(CASE WHEN (affected_organs LIKE '%lung%' OR affected_organs LIKE '%respirat%' OR affected_organs LIKE '%pleura%' OR affected_organs LIKE '%sinus%') THEN 1 ELSE 0 END) AS lungs_and_airways, SUM(CASE WHEN (affected_organs LIKE '%heart%' OR affected_organs LIKE '%arter%' OR affected_organs LIKE '%vessel%' OR affected_organs LIKE '%vein%' OR affected_organs LIKE '%vascular%') THEN 1 ELSE 0 END) AS heart_and_blood_vessels, SUM(CASE WHEN (affected_organs LIKE '%brain%' OR affected_organs LIKE '%nerv%') THEN 1 ELSE 0 END) AS nervous_system, SUM(CASE WHEN (affected_organs LIKE '%gut%' OR affected_organs LIKE '%gastro%' OR affected_organs LIKE '%digest%' OR affected_organs LIKE '%intestin%' OR affected_organs LIKE '%bowel%' OR affected_organs LIKE '%colon%' OR affected_organs LIKE '%esophag%' OR affected_organs LIKE '%stomach%' OR affected_organs LIKE '%liver%' OR affected_organs LIKE '%abdom%') THEN 1 ELSE 0 END) AS digestive_system, SUM(CASE WHEN (affected_organs LIKE '%skin%' OR affected_organs LIKE '%derm%') THEN 1 ELSE 0 END) AS skin, SUM(CASE WHEN (REPLACE(affected_organs, 'bone marrow', '') LIKE '%bone%' OR affected_organs LIKE '%joint%' OR affected_organs LIKE '%muscle%' OR affected_organs LIKE '%spine%' OR affected_organs LIKE '%ligament%' OR affected_organs LIKE '%tendon%') THEN 1 ELSE 0 END) AS bones_joints_and_muscles, SUM(CASE WHEN (affected_organs LIKE '%kidney%' OR affected_organs LIKE '%urinary%' OR affected_organs LIKE '%bladder%' OR affected_organs LIKE '%urethra%') THEN 1 ELSE 0 END) AS kidneys_and_urinary_tract FROM disease WHERE affected_organs <> '' GROUP BY kind;
```
```sql
-- G7b
SELECT CASE WHEN disease_type LIKE '%infectious%' THEN 'infectious' ELSE 'other' END AS kind, COUNT(*) AS diseases, SUM(CASE WHEN affected_organs LIKE '%liver%' THEN 1 ELSE 0 END) AS liver, SUM(CASE WHEN affected_organs LIKE '%kidney%' THEN 1 ELSE 0 END) AS kidneys, SUM(CASE WHEN affected_organs LIKE '%eye%' OR affected_organs LIKE '%retina%' OR affected_organs LIKE '%macula%' OR affected_organs LIKE '%optic%' THEN 1 ELSE 0 END) AS eyes, SUM(CASE WHEN affected_organs LIKE '%brain%' THEN 1 ELSE 0 END) AS brain FROM disease WHERE affected_organs <> '' GROUP BY kind;
```

</details>

### G8 · `drug.pharmaceutical_form` · list-vs-one

drug.pharmaceutical_form lists every form a drug comes in ('capsule||tablet||injection'); G8a needs all forms (any injectable or liquid form, number of forms), G8b one main form by a stated precedence (the single label a 'dosage form' reader would store)

| Question | Asks |
|---|---|
| G8a | Among drugs whose route and forms are stated, taken by mouth or by another route: how many drugs, how many come in more than one form, how many come in an injectable form, and how many in a liquid form (solution, suspension, syrup, drops or liquid)? |
| G8b | By each drug's main dosage form, taking the first of these it comes in (tablet; capsule; injection; liquid, meaning solution, suspension, syrup or drops; other): how many drugs, and how many of them are prescription-only? |

**ALT for G8b**: rows changed 31; G8b keeps 1.0; breaks G8a 0.38 / 0.38

```sql
UPDATE drug SET pharmaceutical_form = CASE WHEN pharmaceutical_form LIKE '%tablet%' THEN 'tablet' WHEN pharmaceutical_form LIKE '%capsule%' THEN 'capsule' WHEN pharmaceutical_form LIKE '%injection%' THEN 'injection' WHEN (pharmaceutical_form LIKE '%solution%' OR pharmaceutical_form LIKE '%suspension%' OR pharmaceutical_form LIKE '%syrup%' OR pharmaceutical_form LIKE '%drop%' OR pharmaceutical_form LIKE '%liquid%') THEN 'liquid' ELSE 'other' END WHERE pharmaceutical_form <> '';
```

<details><summary>SQL</summary>

```sql
-- G8a
SELECT CASE WHEN administration_route LIKE '%oral%' THEN 'by mouth' ELSE 'another route' END AS route, COUNT(*) AS drugs, SUM(CASE WHEN pharmaceutical_form LIKE '%||%' THEN 1 ELSE 0 END) AS several_forms, SUM(CASE WHEN pharmaceutical_form LIKE '%injection%' THEN 1 ELSE 0 END) AS injectable_form, SUM(CASE WHEN (pharmaceutical_form LIKE '%solution%' OR pharmaceutical_form LIKE '%suspension%' OR pharmaceutical_form LIKE '%syrup%' OR pharmaceutical_form LIKE '%drop%' OR pharmaceutical_form LIKE '%liquid%') THEN 1 ELSE 0 END) AS liquid_form FROM drug WHERE pharmaceutical_form <> '' AND administration_route <> '' GROUP BY route;
```
```sql
-- G8b
SELECT CASE WHEN pharmaceutical_form LIKE '%tablet%' THEN 'tablet' WHEN pharmaceutical_form LIKE '%capsule%' THEN 'capsule' WHEN pharmaceutical_form LIKE '%injection%' THEN 'injection' WHEN (pharmaceutical_form LIKE '%solution%' OR pharmaceutical_form LIKE '%suspension%' OR pharmaceutical_form LIKE '%syrup%' OR pharmaceutical_form LIKE '%drop%' OR pharmaceutical_form LIKE '%liquid%') THEN 'liquid' ELSE 'other' END AS main_form, COUNT(*) AS drugs, SUM(CASE WHEN prescription_status LIKE '%prescription_only%' THEN 1 ELSE 0 END) AS prescription_only FROM drug WHERE pharmaceutical_form <> '' GROUP BY main_form;
```

</details>


## Players (`Query/Realistic/conflict/player.sql`)

### G1 · `player.team` · join-spelling

player.team names a player's last team as the documents do; franchise questions need former names (Milwaukee Hawks) resolved to the team table's current name (Atlanta Hawks), while where-and-under-which-name questions need the name as stated

> Writer's note: G1a and G1b use the same ten-name mapping. The 1940s Baltimore Bullets and the Chicago Stags were separate franchises that folded, so they are not mapped.

| Question | Asks |
|---|---|
| G1a | Per NBA franchise, counting a player whose last team was a former name of the franchise under its current name (Milwaukee Hawks as Atlanta Hawks, New Orleans Jazz as Utah Jazz, Philadelphia Warriors as Golden State Warriors, Seattle SuperSonics as Oklahoma City Thunder, Syracuse Nationals as Philadelphia 76ers, Fort Wayne Pistons as Detroit Pistons, Rochester Royals and Cincinnati Royals as Sacramento Kings, Washington Bullets as Washington Wizards, Charlotte Bobcats as Charlotte Hornets; the 1940s Baltimore Bullets and the Chicago Stags were separate franchises that folded, so their players are left out): how many players, how many MVP winners, how many NBA titles have the players won, and how many has the franchise won? |
| G1b | For each franchise that has moved or been renamed (Atlanta Hawks, formerly Milwaukee Hawks; Utah Jazz, formerly New Orleans Jazz; Golden State Warriors, formerly Philadelphia Warriors; Oklahoma City Thunder, formerly Seattle SuperSonics; Philadelphia 76ers, formerly Syracuse Nationals; Detroit Pistons, formerly Fort Wayne Pistons; Sacramento Kings, formerly Rochester Royals and Cincinnati Royals; Washington Wizards, formerly Washington Bullets; Charlotte Hornets, formerly Charlotte Bobcats): how many of its players last played for it under its current name, how many under an earlier name, and how many NBA titles did each of the two groups win? |
| G1c | Per state (or Canadian province) where players' last NBA teams played at the time, counting a player of a team that has since moved in the state it played in then (Milwaukee Hawks in Wisconsin, New Orleans Jazz in Louisiana, Philadelphia Warriors in Pennsylvania, Seattle SuperSonics in Washington, Syracuse Nationals and Rochester Royals in New York, Fort Wayne Pistons in Indiana, Cincinnati Royals in Ohio, Baltimore Bullets in Maryland, Chicago Stags in Illinois, Charlotte Bobcats in North Carolina; teams in Washington, D.C., which is not a state, are left out): how many players, MVP winners and NBA titles? |

**ALT for G1a**: rows changed 17; G1a keeps 1.0; breaks G1b 0.44 / 0.67, G1c 0.70 / 0.82 · **Flags:** only 17 rows change; long question: G1a, G1b, G1c

```sql
UPDATE player SET team = CASE team WHEN 'Milwaukee Hawks' THEN 'Atlanta Hawks' WHEN 'New Orleans Jazz' THEN 'Utah Jazz' WHEN 'Philadelphia Warriors' THEN 'Golden State Warriors' WHEN 'Seattle SuperSonics' THEN 'Oklahoma City Thunder' WHEN 'Syracuse Nationals' THEN 'Philadelphia 76ers' WHEN 'Fort Wayne Pistons' THEN 'Detroit Pistons' WHEN 'Rochester Royals' THEN 'Sacramento Kings' WHEN 'Cincinnati Royals' THEN 'Sacramento Kings' WHEN 'Washington Bullets' THEN 'Washington Wizards' WHEN 'Charlotte Bobcats' THEN 'Charlotte Hornets' ELSE team END WHERE team IN ('Milwaukee Hawks', 'New Orleans Jazz', 'Philadelphia Warriors', 'Seattle SuperSonics', 'Syracuse Nationals', 'Fort Wayne Pistons', 'Rochester Royals', 'Cincinnati Royals', 'Washington Bullets', 'Charlotte Bobcats');
```

<details><summary>SQL</summary>

```sql
-- G1a
SELECT team.team_name, COUNT(*) AS players, SUM(CASE WHEN player.mvp_awards >= 1 THEN 1 ELSE 0 END) AS mvp_winners, SUM(CAST(player.nba_championships AS INTEGER)) AS titles_won_by_players, MAX(CAST(team.championship AS INTEGER)) AS franchise_titles FROM player JOIN team ON team.team_name = CASE player.team WHEN 'Milwaukee Hawks' THEN 'Atlanta Hawks' WHEN 'New Orleans Jazz' THEN 'Utah Jazz' WHEN 'Philadelphia Warriors' THEN 'Golden State Warriors' WHEN 'Seattle SuperSonics' THEN 'Oklahoma City Thunder' WHEN 'Syracuse Nationals' THEN 'Philadelphia 76ers' WHEN 'Fort Wayne Pistons' THEN 'Detroit Pistons' WHEN 'Rochester Royals' THEN 'Sacramento Kings' WHEN 'Cincinnati Royals' THEN 'Sacramento Kings' WHEN 'Washington Bullets' THEN 'Washington Wizards' WHEN 'Charlotte Bobcats' THEN 'Charlotte Hornets' ELSE player.team END GROUP BY team.team_name;
```
```sql
-- G1b
SELECT team.team_name, SUM(CASE WHEN player.team = team.team_name THEN 1 ELSE 0 END) AS players_under_current_name, SUM(CASE WHEN player.team <> team.team_name THEN 1 ELSE 0 END) AS players_under_earlier_name, SUM(CASE WHEN player.team = team.team_name THEN CAST(player.nba_championships AS INTEGER) ELSE 0 END) AS titles_under_current_name, SUM(CASE WHEN player.team <> team.team_name THEN CAST(player.nba_championships AS INTEGER) ELSE 0 END) AS titles_under_earlier_name FROM player JOIN team ON team.team_name = CASE player.team WHEN 'Milwaukee Hawks' THEN 'Atlanta Hawks' WHEN 'New Orleans Jazz' THEN 'Utah Jazz' WHEN 'Philadelphia Warriors' THEN 'Golden State Warriors' WHEN 'Seattle SuperSonics' THEN 'Oklahoma City Thunder' WHEN 'Syracuse Nationals' THEN 'Philadelphia 76ers' WHEN 'Fort Wayne Pistons' THEN 'Detroit Pistons' WHEN 'Rochester Royals' THEN 'Sacramento Kings' WHEN 'Cincinnati Royals' THEN 'Sacramento Kings' WHEN 'Washington Bullets' THEN 'Washington Wizards' WHEN 'Charlotte Bobcats' THEN 'Charlotte Hornets' ELSE player.team END WHERE team.team_name IN ('Atlanta Hawks', 'Utah Jazz', 'Golden State Warriors', 'Oklahoma City Thunder', 'Philadelphia 76ers', 'Detroit Pistons', 'Sacramento Kings', 'Washington Wizards', 'Charlotte Hornets') GROUP BY team.team_name;
```
```sql
-- G1c
SELECT state, COUNT(*) AS players, SUM(CASE WHEN mvp_awards >= 1 THEN 1 ELSE 0 END) AS mvp_winners, SUM(CAST(nba_championships AS INTEGER)) AS nba_titles FROM (SELECT CASE player.team WHEN 'Milwaukee Hawks' THEN 'Wisconsin' WHEN 'New Orleans Jazz' THEN 'Louisiana' WHEN 'Philadelphia Warriors' THEN 'Pennsylvania' WHEN 'Seattle SuperSonics' THEN 'Washington' WHEN 'Syracuse Nationals' THEN 'New York' WHEN 'Rochester Royals' THEN 'New York' WHEN 'Fort Wayne Pistons' THEN 'Indiana' WHEN 'Cincinnati Royals' THEN 'Ohio' WHEN 'Baltimore Bullets' THEN 'Maryland' WHEN 'Chicago Stags' THEN 'Illinois' WHEN 'Charlotte Bobcats' THEN 'North Carolina' ELSE city.state_name END AS state, player.mvp_awards AS mvp_awards, player.nba_championships AS nba_championships FROM player LEFT JOIN team ON player.team = team.team_name LEFT JOIN city ON team.location = city.city_name) AS p WHERE state IS NOT NULL AND state <> '' GROUP BY state;
```

</details>

### G2 · `player.birth_date` · fine-vs-coarse

player.birth_date holds the full stated date; age-at-draft questions need only the birth year, while birth-month questions need the month that a year-only form drops

> Writer's note: the stored format YYYY/M/D (no leading zeros) is prescribed by the field description; G2b also accepts ISO dates (YYYY-MM-DD), so it tests only whether the month is kept.

| Question | Asks |
|---|---|
| G2a | Among players with a stated draft year and pick number, by age in the draft year (draft year minus birth year: 19 or younger, 20 to 21, 22 or older): how many players, their average pick, and how many went on to win an NBA title? |
| G2b | By birth quarter (January to March, April to June, July to September, October to December): how many players, how many were top-10 draft picks, and how many won an NBA title? |

**ALT for G2a**: rows changed 141; G2a keeps 1.0; breaks G2b 0.00 / 0.00

```sql
UPDATE player SET birth_date = CAST(substr(birth_date, 1, 4) AS INTEGER) WHERE birth_date IS NOT NULL AND birth_date <> '';
```

<details><summary>SQL</summary>

```sql
-- G2a
SELECT CASE WHEN CAST(draft_year AS INTEGER) - CAST(birth_date AS INTEGER) <= 19 THEN '19 or younger' WHEN CAST(draft_year AS INTEGER) - CAST(birth_date AS INTEGER) <= 21 THEN '20 to 21' ELSE '22 or older' END AS age_in_draft_year, COUNT(*) AS drafted_players, AVG(CAST(draft_pick AS INTEGER)) AS average_pick, SUM(CASE WHEN CAST(nba_championships AS INTEGER) >= 1 THEN 1 ELSE 0 END) AS nba_champions FROM player WHERE CAST(draft_pick AS INTEGER) > 0 AND CAST(draft_year AS INTEGER) > 0 AND birth_date IS NOT NULL AND birth_date <> '' GROUP BY age_in_draft_year;
```
```sql
-- G2b
SELECT CASE WHEN birth_date LIKE '%/1/%' OR birth_date LIKE '%-01-%' OR birth_date LIKE '%/2/%' OR birth_date LIKE '%-02-%' OR birth_date LIKE '%/3/%' OR birth_date LIKE '%-03-%' THEN 'January to March' WHEN birth_date LIKE '%/4/%' OR birth_date LIKE '%-04-%' OR birth_date LIKE '%/5/%' OR birth_date LIKE '%-05-%' OR birth_date LIKE '%/6/%' OR birth_date LIKE '%-06-%' THEN 'April to June' WHEN birth_date LIKE '%/7/%' OR birth_date LIKE '%-07-%' OR birth_date LIKE '%/8/%' OR birth_date LIKE '%-08-%' OR birth_date LIKE '%/9/%' OR birth_date LIKE '%-09-%' THEN 'July to September' WHEN birth_date LIKE '%/10/%' OR birth_date LIKE '%-10-%' OR birth_date LIKE '%/11/%' OR birth_date LIKE '%-11-%' OR birth_date LIKE '%/12/%' OR birth_date LIKE '%-12-%' THEN 'October to December' ELSE 'month not given' END AS birth_quarter, COUNT(*) AS players, SUM(CASE WHEN CAST(draft_pick AS INTEGER) BETWEEN 1 AND 10 THEN 1 ELSE 0 END) AS top_10_picks, SUM(CASE WHEN CAST(nba_championships AS INTEGER) >= 1 THEN 1 ELSE 0 END) AS nba_champions FROM player WHERE birth_date IS NOT NULL AND birth_date <> '' GROUP BY birth_quarter;
```

</details>

### G3 · `player.nationality` · list-vs-one

player.nationality can name two nationalities (Greek-American, American-Chinese, Greek and Nigerian, American-born naturalized Azerbaijani); a US-nationality question wants the American one, an origin question wants the other one, and a dual-national question needs both

> Writer's note: small: 8-9 of 139 players carry the conflict. ALT G3b's effect on G3a disappears at 10% tolerance and above (it moves 8 of 124 US players); G3c is ALT G3b's main victim. Kyle Anderson (American-Chinese) is the only Asian-origin player, so G3b's Asia row has one player. Known quirk of the correct data: one Canadian (Larry Robinson) is a hockey figure whose 'team' is a hockey operations job.

| Question | Asks |
|---|---|
| G3a | Players who hold US nationality, alone or with another (e.g. Greek-American, American-Chinese, and counting a US-born player who took another nationality as holding US nationality), versus players who do not: how many, how many have won an NBA title, how many have won an MVP award, and how many FIBA World Cup titles have they won? |
| G3b | Players with a nationality other than American, counting a dual national under his non-US nationality (Greek-American as Greek, a US-born player naturalized elsewhere under his new nationality) and a player with two non-US nationalities under the first one listed: per continent of that nationality (Europe, with Azerbaijan counted in Europe as FIBA does; Africa; the Americas outside the US; Asia), how many players and how many NBA titles? |
| G3c | Players with US nationality only, with US and another nationality (counting a US-born player who took another nationality here), or with another nationality only: how many, how many NBA champions, how many MVP winners, and how many Olympic gold medals? |

**ALT for G3a**: rows changed 8; G3a keeps 1.0; breaks G3b 0.23 / 0.45, G3c 0.29 / 0.57 · **Flags:** only 8 rows change; long question: G3b

```sql
UPDATE player SET nationality = 'American' WHERE nationality LIKE '%American%' AND nationality <> 'American';
```

**ALT for G3b**: rows changed 9; G3b keeps 1.0; breaks G3a 0.00 / 1.00, G3c 0.29 / 0.57 · **Flags:** only 9 rows change; long question: G3b

```sql
UPDATE player SET nationality = CASE WHEN nationality LIKE '%naturalized %' THEN substr(nationality, instr(nationality, 'naturalized ') + 12) WHEN nationality LIKE '%-American' THEN substr(nationality, 1, instr(nationality, '-') - 1) WHEN nationality LIKE 'American-%' THEN substr(nationality, 10) WHEN nationality LIKE '% and %' THEN substr(nationality, 1, instr(nationality, ' and ') - 1) ELSE nationality END WHERE nationality LIKE '%-%' OR nationality LIKE '% and %';
```

<details><summary>SQL</summary>

```sql
-- G3a
SELECT CASE WHEN nationality LIKE '%American%' THEN 'holds US nationality' ELSE 'no US nationality' END AS us_nationality, COUNT(*) AS players, SUM(CASE WHEN CAST(nba_championships AS INTEGER) >= 1 THEN 1 ELSE 0 END) AS nba_champions, SUM(CASE WHEN mvp_awards >= 1 THEN 1 ELSE 0 END) AS mvp_winners, SUM(fiba_world_cup) AS fiba_world_cup_titles FROM player WHERE nationality IS NOT NULL AND nationality <> '' GROUP BY us_nationality;
```
```sql
-- G3b
SELECT CASE WHEN nationality LIKE '%Greek%' OR nationality LIKE '%French%' OR nationality LIKE '%Serbian%' OR nationality LIKE '%Croatian%' OR nationality LIKE '%Slovenian%' OR nationality LIKE '%German%' OR nationality LIKE '%Dutch%' OR nationality LIKE '%British%' OR nationality LIKE '%Spanish%' OR nationality LIKE '%Azerbaijani%' THEN 'Europe' WHEN nationality LIKE '%Nigerian%' OR nationality LIKE '%Cameroonian%' OR nationality LIKE '%Congolese%' THEN 'Africa' WHEN nationality LIKE '%Canadian%' OR nationality LIKE '%Bahamian%' OR nationality LIKE '%Dominican%' OR nationality LIKE '%Mexican%' OR nationality LIKE '%Venezuelan%' THEN 'the Americas outside the US' WHEN nationality LIKE '%Chinese%' THEN 'Asia' ELSE 'other' END AS continent, COUNT(*) AS players, SUM(CAST(nba_championships AS INTEGER)) AS nba_titles FROM player WHERE nationality <> 'American' AND nationality <> '' GROUP BY continent;
```
```sql
-- G3c
SELECT CASE WHEN nationality = 'American' THEN 'US only' WHEN nationality LIKE '%American%' THEN 'US and another' ELSE 'another only' END AS nationality_group, COUNT(*) AS players, SUM(CASE WHEN CAST(nba_championships AS INTEGER) >= 1 THEN 1 ELSE 0 END) AS nba_champions, SUM(CASE WHEN mvp_awards >= 1 THEN 1 ELSE 0 END) AS mvp_winners, SUM(olympic_gold_medals) AS olympic_gold_medals FROM player WHERE nationality IS NOT NULL AND nationality <> '' GROUP BY nationality_group;
```

</details>

### G4 · `player.college` · list-vs-one

player.college lists every college a transfer attended, in order ("Indiana University, Xavier University"); a school question that counts a transfer under his last college wants one name, while every-college and transfer questions need the list (a comma also appears inside one name, e.g. University of California, Berkeley)

> Writer's note: small: 6 transfers carry the conflict; within G4a/G4c's school list only the Indiana-to-Xavier transfer matters, so ALT G4a moves G4c only at strict tolerance (0.90 at 0%, 1.0 at 20%); G4b (0.12 / 0.37) is the main victim. School list is the reviewed QX3's. The ALT is plausible because the field description asks for 'the college' in the singular.

| Question | Asks |
|---|---|
| G4a | For UCLA, Kentucky, Michigan State, Indiana, Florida and Duke against all other colleges, counting a player who transferred under the last college he played for: how many players, NBA champions and MVP winners? |
| G4b | Players who transferred between colleges versus players who attended one college: how many, how many were first-round picks (pick 1 to 30), and how many won an NBA title? |
| G4c | For UCLA, Kentucky, Michigan State, Indiana, Florida and Duke against all other colleges, counting a player who transferred under every college he played for: how many players, how many were top-10 picks, and how many NBA titles have they won? |

**ALT for G4a**: rows changed 6; G4a keeps 1.0; breaks G4b 0.12 / 0.37, G4c 0.90 / 1.00 · **Flags:** only 6 rows change

```sql
UPDATE player SET college = substr(college, instr(college, ', ') + 2) WHERE college LIKE '%, %' AND college NOT LIKE 'University of California, %';
```

<details><summary>SQL</summary>

```sql
-- G4a
SELECT CASE WHEN college LIKE '%UCLA' OR college LIKE '%University of California, Los Angeles' THEN 'UCLA' WHEN college LIKE '%Kentucky' OR college LIKE '%Kentucky Wildcats' THEN 'Kentucky' WHEN college LIKE '%Michigan State' OR college LIKE '%Michigan State University' OR college LIKE '%Michigan State Spartans' THEN 'Michigan State' WHEN college LIKE '%Indiana Hoosiers' OR college LIKE '%Indiana University' THEN 'Indiana' WHEN college LIKE '%University of Florida' THEN 'Florida' WHEN college LIKE '%Duke' OR college LIKE '%Duke University' THEN 'Duke' ELSE 'any other school' END AS college_group, COUNT(*) AS players, SUM(CASE WHEN CAST(nba_championships AS INTEGER) >= 1 THEN 1 ELSE 0 END) AS nba_champions, SUM(CASE WHEN mvp_awards >= 1 THEN 1 ELSE 0 END) AS mvp_winners FROM player WHERE college IS NOT NULL AND college <> '' GROUP BY college_group;
```
```sql
-- G4b
SELECT CASE WHEN college LIKE '%, %' AND college NOT LIKE 'University of California, %' THEN 'transferred' ELSE 'one college' END AS college_path, COUNT(*) AS players, SUM(CASE WHEN CAST(draft_pick AS INTEGER) BETWEEN 1 AND 30 THEN 1 ELSE 0 END) AS first_round_picks, SUM(CASE WHEN CAST(nba_championships AS INTEGER) >= 1 THEN 1 ELSE 0 END) AS nba_champions FROM player WHERE college IS NOT NULL AND college <> '' GROUP BY college_path;
```
```sql
-- G4c
SELECT CASE WHEN college LIKE '%UCLA%' OR college LIKE '%California, Los Angeles%' THEN 'UCLA' WHEN college LIKE '%Kentucky%' THEN 'Kentucky' WHEN college LIKE '%Michigan State%' THEN 'Michigan State' WHEN college LIKE '%Indiana%' THEN 'Indiana' WHEN college LIKE '%University of Florida%' THEN 'Florida' WHEN college LIKE '%Duke%' THEN 'Duke' ELSE 'any other school' END AS college_group, COUNT(*) AS players, SUM(CASE WHEN CAST(draft_pick AS INTEGER) BETWEEN 1 AND 10 THEN 1 ELSE 0 END) AS top_10_picks, SUM(CAST(nba_championships AS INTEGER)) AS nba_titles FROM player WHERE college IS NOT NULL AND college <> '' GROUP BY college_group;
```

</details>


## Papers (`Query/Realistic/conflict/cspaper.sql`)

### G1 · `cspaper.retrieval_method` · list-vs-one

cspaper.retrieval_method lists every retrieval method a paper combines (35 of 199 papers list two or more; 23 more state 'Hybrid Retrieval' alone); G1a counts a paper under every method it lists, G1b wants one method per paper with any combination counted as hybrid retrieval, G1c needs to see which dense-retrieval papers list another method too

> Writer's note: the field spec in fields_of('cspaper') declares retrieval_method single-choice ('choose one from [...]'); for this benchmark the spec shown to systems must say 'choose one or more', otherwise a spec-following system stores the G1b form and G1a/G1c fail for every system, shared extraction or not

| Question | Asks |
|---|---|
| G1a | For single-hop and multi-hop papers, how many use dense retrieval, sparse retrieval, graph-based retrieval, hybrid retrieval and web search, counting a paper that lists several methods under every method it lists? |
| G1b | For each retrieval method, counting a paper that lists two or more methods as hybrid retrieval, how many papers are there, how many use a reranker, and how many baselines do they compare against on average? |
| G1c | Among papers that use dense retrieval, how many use it as their only retrieval method and how many list it together with another method (sparse, graph-based, hybrid, web search or other), and how many of each use a reranker and support multi-turn retrieval? |

**ALT for G1b**: rows changed 35; G1b keeps 1.0; breaks G1a 0.25 / 0.25, G1c 0.37 / 0.37

```sql
UPDATE cspaper SET retrieval_method = CASE WHEN instr(retrieval_method, '||') > 0 THEN 'Hybrid Retrieval' ELSE retrieval_method END;
```

<details><summary>SQL</summary>

```sql
-- G1a
SELECT reasoning_depth, COUNT(*) AS papers, SUM(CASE WHEN retrieval_method LIKE '%Dense%' THEN 1 ELSE 0 END) AS dense, SUM(CASE WHEN retrieval_method LIKE '%Sparse%' THEN 1 ELSE 0 END) AS sparse, SUM(CASE WHEN retrieval_method LIKE '%Graph%' THEN 1 ELSE 0 END) AS graph_based, SUM(CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 1 ELSE 0 END) AS hybrid, SUM(CASE WHEN retrieval_method LIKE '%Web%' THEN 1 ELSE 0 END) AS web_search FROM cspaper WHERE reasoning_depth IN ('multi-hop', 'single-hop') GROUP BY reasoning_depth;
```
```sql
-- G1b
SELECT CASE WHEN instr(retrieval_method, '||') > 0 THEN 'Hybrid Retrieval' ELSE retrieval_method END AS method, COUNT(*) AS papers, SUM(CASE WHEN uses_reranker = 'Yes' THEN 1 ELSE 0 END) AS with_reranker, AVG(baseline_amount) AS average_baselines FROM cspaper WHERE retrieval_method IS NOT NULL AND retrieval_method <> '' GROUP BY method;
```
```sql
-- G1c
SELECT CASE WHEN instr(retrieval_method, '||') > 0 THEN 'dense with another method' ELSE 'dense only' END AS dense_use, COUNT(*) AS papers, SUM(CASE WHEN uses_reranker = 'Yes' THEN 1 ELSE 0 END) AS with_reranker, SUM(CASE WHEN multi_turn_retrieval = 'Yes' THEN 1 ELSE 0 END) AS multi_turn FROM cspaper WHERE retrieval_method LIKE '%Dense%' GROUP BY dense_use;
```

</details>

### G2 · `cspaper.application_domain` · list-vs-one

cspaper.application_domain lists every domain a paper targets (39 of 199 papers list two or more, often General together with a specific domain); G2a counts a paper under every specific domain it lists, G2b needs General, Academic and Other separately, G2c wants one domain per paper (medical, finance, education, legal, or general and other)

| Question | Asks |
|---|---|
| G2a | For papers with and without an agent, how many target medical, finance, education, legal and academic applications, counting a paper under every domain it lists? |
| G2b | For single-hop and multi-hop papers, how many are general-purpose (list the General domain), how many target academic use, and how many target some other application, counting a paper under every domain it lists? |
| G2c | For each application domain (medical, finance, education, legal, or general and other; a paper naming several of the first four goes to the first in that order), how many papers are there, how many use a reranker, and how many support multi-turn retrieval? |

**ALT for G2c**: rows changed 39; G2c keeps 1.0; breaks G2a 0.33 / 0.58, G2b 0.25 / 0.25

```sql
UPDATE cspaper SET application_domain = CASE WHEN application_domain LIKE '%Medical%' THEN 'Medical' WHEN application_domain LIKE '%Finance%' THEN 'Finance' WHEN application_domain LIKE '%Education%' THEN 'Education' WHEN application_domain LIKE '%Legal%' THEN 'Legal' WHEN application_domain LIKE '%Academic%' THEN 'Academic' WHEN application_domain LIKE '%Government%' THEN 'Government' WHEN application_domain LIKE '%Sports%' THEN 'Sports' WHEN application_domain LIKE '%Art%' THEN 'Art' WHEN application_domain LIKE '%General%' THEN 'General' ELSE application_domain END WHERE application_domain IS NOT NULL AND application_domain <> '';
```

<details><summary>SQL</summary>

```sql
-- G2a
SELECT use_agent, COUNT(*) AS papers, SUM(CASE WHEN application_domain LIKE '%Medical%' THEN 1 ELSE 0 END) AS medical, SUM(CASE WHEN application_domain LIKE '%Finance%' THEN 1 ELSE 0 END) AS finance, SUM(CASE WHEN application_domain LIKE '%Education%' THEN 1 ELSE 0 END) AS education, SUM(CASE WHEN application_domain LIKE '%Legal%' THEN 1 ELSE 0 END) AS legal, SUM(CASE WHEN application_domain LIKE '%Academic%' THEN 1 ELSE 0 END) AS academic FROM cspaper WHERE application_domain IS NOT NULL AND application_domain <> '' GROUP BY use_agent;
```
```sql
-- G2b
SELECT reasoning_depth, COUNT(*) AS papers, SUM(CASE WHEN application_domain LIKE '%General%' THEN 1 ELSE 0 END) AS general_purpose, SUM(CASE WHEN application_domain LIKE '%Academic%' THEN 1 ELSE 0 END) AS academic, SUM(CASE WHEN application_domain LIKE '%Other%' THEN 1 ELSE 0 END) AS other_application FROM cspaper WHERE reasoning_depth IN ('multi-hop', 'single-hop') AND application_domain IS NOT NULL AND application_domain <> '' GROUP BY reasoning_depth;
```
```sql
-- G2c
SELECT CASE WHEN application_domain LIKE '%Medical%' THEN 'Medical' WHEN application_domain LIKE '%Finance%' THEN 'Finance' WHEN application_domain LIKE '%Education%' THEN 'Education' WHEN application_domain LIKE '%Legal%' THEN 'Legal' ELSE 'General or other' END AS domain, COUNT(*) AS papers, SUM(CASE WHEN uses_reranker = 'Yes' THEN 1 ELSE 0 END) AS with_reranker, SUM(CASE WHEN multi_turn_retrieval = 'Yes' THEN 1 ELSE 0 END) AS multi_turn FROM cspaper WHERE application_domain IS NOT NULL AND application_domain <> '' GROUP BY domain;
```

</details>

### G3 · `cspaper.data_modality` · list-vs-one

cspaper.data_modality lists every kind of input a paper handles (50 of 192 papers list two or more); G3a wants one input class per paper (images or audio / tables or code / text only), G3b counts the kinds listed, G3c needs each kind separately

| Question | Asks |
|---|---|
| G3a | For each kind of input data (papers that handle images or audio; papers that handle tables or code but no images or audio; text-only papers), how many papers are there, how many use a knowledge graph, and how many baselines do they compare against on average? |
| G3b | How many papers handle one kind of input, two kinds, and three or more kinds (counting text, images, audio, tables and code separately), and how many of them study multi-hop reasoning? |
| G3c | For single-hop and multi-hop papers, how many handle tables, code, images and audio, counting a paper under every kind of input it handles? |

**ALT for G3a**: rows changed 50; G3a keeps 1.0; breaks G3b 0.00 / 0.00, G3c 0.50 / 0.50

```sql
UPDATE cspaper SET data_modality = CASE WHEN data_modality LIKE '%Image%' THEN 'Image' WHEN data_modality LIKE '%Audio%' THEN 'Audio' WHEN data_modality LIKE '%Table%' THEN 'Table' WHEN data_modality LIKE '%Code%' THEN 'Code' WHEN data_modality LIKE '%Text%' THEN 'Text' ELSE data_modality END;
```

<details><summary>SQL</summary>

```sql
-- G3a
SELECT CASE WHEN data_modality LIKE '%Image%' OR data_modality LIKE '%Audio%' THEN 'images or audio' WHEN data_modality LIKE '%Table%' OR data_modality LIKE '%Code%' THEN 'tables or code' ELSE 'text only' END AS input_kind, COUNT(*) AS papers, SUM(CASE WHEN uses_knowledge_graph = 'Yes' THEN 1 ELSE 0 END) AS with_knowledge_graph, AVG(baseline_amount) AS average_baselines FROM cspaper WHERE (data_modality LIKE '%Text%' OR data_modality LIKE '%Image%' OR data_modality LIKE '%Audio%' OR data_modality LIKE '%Table%' OR data_modality LIKE '%Code%') GROUP BY input_kind;
```
```sql
-- G3b
SELECT CASE WHEN length(data_modality) - length(replace(data_modality, '||', '')) = 0 THEN 'one kind' WHEN length(data_modality) - length(replace(data_modality, '||', '')) = 2 THEN 'two kinds' ELSE 'three or more kinds' END AS kinds_of_input, COUNT(*) AS papers, SUM(CASE WHEN reasoning_depth LIKE '%multi-hop%' THEN 1 ELSE 0 END) AS multi_hop FROM cspaper WHERE (data_modality LIKE '%Text%' OR data_modality LIKE '%Image%' OR data_modality LIKE '%Audio%' OR data_modality LIKE '%Table%' OR data_modality LIKE '%Code%') GROUP BY kinds_of_input;
```
```sql
-- G3c
SELECT reasoning_depth, COUNT(*) AS papers, SUM(CASE WHEN data_modality LIKE '%Table%' THEN 1 ELSE 0 END) AS tables, SUM(CASE WHEN data_modality LIKE '%Code%' THEN 1 ELSE 0 END) AS code, SUM(CASE WHEN data_modality LIKE '%Image%' THEN 1 ELSE 0 END) AS images, SUM(CASE WHEN data_modality LIKE '%Audio%' THEN 1 ELSE 0 END) AS audio FROM cspaper WHERE reasoning_depth IN ('multi-hop', 'single-hop') GROUP BY reasoning_depth;
```

</details>

### G4 · `cspaper.generator_model` · fine-vs-coarse

cspaper.generator_model names the specific generator models of 185 papers (GPT-4o, gpt-3.5-turbo, Llama-3.1-8B-Instruct, ...); G4a wants the model family (GPT, Llama, Qwen, Mistral), G4b needs the specific GPT version

| Question | Asks |
|---|---|
| G4a | For papers with and without an agent, how many use as a generator a model whose name contains GPT (OpenAI's GPT and ChatGPT models, but also GPT-2 and GPT-Neo), a Llama model, a Qwen model, and a Mistral or Mixtral model, counting a paper under every model family it uses? |
| G4b | For single-hop and multi-hop papers, how many use GPT-4o (including GPT-4o-mini and ChatGPT-4o), another GPT-4 model (such as GPT-4, GPT-4 Turbo, GPT-4V, GPT-4.1 or ChatGPT-4), and GPT-3.5 as a generator? A ChatGPT entry without a version number is not counted as GPT-3.5. |

**ALT for G4a**: rows changed 184; G4a keeps 1.0; breaks G4b 0.25 / 0.25

```sql
UPDATE cspaper SET generator_model = COALESCE(NULLIF(rtrim(CASE WHEN generator_model LIKE '%GPT%' THEN 'GPT|| ' ELSE '' END || CASE WHEN generator_model LIKE '%Llama%' THEN 'Llama|| ' ELSE '' END || CASE WHEN generator_model LIKE '%Qwen%' THEN 'Qwen|| ' ELSE '' END || CASE WHEN generator_model LIKE '%Mistral%' OR generator_model LIKE '%Mixtral%' THEN 'Mistral|| ' ELSE '' END || CASE WHEN generator_model LIKE '%Gemini%' THEN 'Gemini|| ' ELSE '' END || CASE WHEN generator_model LIKE '%Claude%' THEN 'Claude|| ' ELSE '' END, '| '), ''), 'Other') WHERE generator_model IS NOT NULL AND generator_model <> '' AND generator_model <> 'null';
```

<details><summary>SQL</summary>

```sql
-- G4a
SELECT use_agent, COUNT(*) AS papers, SUM(CASE WHEN generator_model LIKE '%GPT%' THEN 1 ELSE 0 END) AS gpt, SUM(CASE WHEN generator_model LIKE '%Llama%' THEN 1 ELSE 0 END) AS llama, SUM(CASE WHEN generator_model LIKE '%Qwen%' THEN 1 ELSE 0 END) AS qwen, SUM(CASE WHEN generator_model LIKE '%Mistral%' OR generator_model LIKE '%Mixtral%' THEN 1 ELSE 0 END) AS mistral FROM cspaper WHERE generator_model IS NOT NULL AND generator_model <> '' AND generator_model <> 'null' GROUP BY use_agent;
```
```sql
-- G4b
SELECT reasoning_depth, COUNT(*) AS papers, SUM(CASE WHEN generator_model LIKE '%GPT-4o%' OR generator_model LIKE '%GPT4-o%' THEN 1 ELSE 0 END) AS gpt_4o, SUM(CASE WHEN replace(replace(lower(generator_model), 'gpt-4o', ''), 'gpt4-o', '') LIKE '%gpt-4%' THEN 1 ELSE 0 END) AS other_gpt_4, SUM(CASE WHEN generator_model LIKE '%GPT-3.5%' OR generator_model LIKE '%GPT 3.5%' THEN 1 ELSE 0 END) AS gpt_3_5 FROM cspaper WHERE reasoning_depth IN ('multi-hop', 'single-hop') GROUP BY reasoning_depth;
```

</details>

### G5 · `cspaper.evaluation_metric` · fine-vs-coarse

cspaper.evaluation_metric lists every metric a paper reports (169 of 193 papers list two or more); G5a wants only whether a paper reports the standard answer metrics (F1, exact match, accuracy, ROUGE), G5b counts the metrics listed, G5c needs the retrieval ranking metrics, which are none of the four

| Question | Asks |
|---|---|
| G5a | For single-hop and multi-hop papers, how many report F1, exact match, accuracy and ROUGE, counting every metric a paper reports? |
| G5b | Do papers that report more metrics compare against more baselines? Counting each listed metric separately (each cutoff such as Recall@1 and Recall@5 counts as its own metric), for papers reporting one metric, two or three, and four or more: how many papers, and how many baselines on average? |
| G5c | For papers with and without a reranker, how many report a retrieval ranking metric (Recall@k including R@k, MRR, nDCG, or a hit rate such as Hit@k, Hits@k or HR@k), out of how many papers that report any metric? |

**ALT for G5a**: rows changed 179; G5a keeps 1.0; breaks G5b 0.00 / 0.00, G5c 0.50 / 0.50

```sql
UPDATE cspaper SET evaluation_metric = COALESCE(NULLIF(rtrim(CASE WHEN evaluation_metric LIKE '%F1%' THEN 'F1|| ' ELSE '' END || CASE WHEN instr(evaluation_metric, 'EM') > 0 OR evaluation_metric LIKE '%Exact Match%' THEN 'EM|| ' ELSE '' END || CASE WHEN evaluation_metric LIKE '%Accuracy%' THEN 'Accuracy|| ' ELSE '' END || CASE WHEN evaluation_metric LIKE '%ROUGE%' THEN 'ROUGE|| ' ELSE '' END, '| '), ''), 'other') WHERE evaluation_metric IS NOT NULL AND evaluation_metric <> '';
```

<details><summary>SQL</summary>

```sql
-- G5a
SELECT reasoning_depth, COUNT(*) AS papers, SUM(CASE WHEN evaluation_metric LIKE '%F1%' THEN 1 ELSE 0 END) AS report_f1, SUM(CASE WHEN instr(evaluation_metric, 'EM') > 0 OR evaluation_metric LIKE '%Exact Match%' THEN 1 ELSE 0 END) AS report_exact_match, SUM(CASE WHEN evaluation_metric LIKE '%Accuracy%' THEN 1 ELSE 0 END) AS report_accuracy, SUM(CASE WHEN evaluation_metric LIKE '%ROUGE%' THEN 1 ELSE 0 END) AS report_rouge FROM cspaper WHERE reasoning_depth IN ('multi-hop', 'single-hop') AND evaluation_metric IS NOT NULL AND evaluation_metric <> '' GROUP BY reasoning_depth;
```
```sql
-- G5b
SELECT CASE WHEN length(evaluation_metric) - length(replace(evaluation_metric, '||', '')) = 0 THEN 'one metric' WHEN length(evaluation_metric) - length(replace(evaluation_metric, '||', '')) <= 4 THEN 'two or three metrics' ELSE 'four or more metrics' END AS metrics_reported, COUNT(*) AS papers, AVG(baseline_amount) AS average_baselines FROM cspaper WHERE evaluation_metric IS NOT NULL AND evaluation_metric <> '' GROUP BY metrics_reported;
```
```sql
-- G5c
SELECT uses_reranker, COUNT(*) AS papers, SUM(CASE WHEN evaluation_metric LIKE '%Recall@%' OR evaluation_metric LIKE '%Recall @%' OR evaluation_metric LIKE '%R@%' OR evaluation_metric LIKE '%MRR%' OR evaluation_metric LIKE '%nDCG%' OR evaluation_metric LIKE '%Hit%' THEN 1 ELSE 0 END) AS report_ranking_metric FROM cspaper WHERE uses_reranker IN ('Yes', 'No') AND evaluation_metric IS NOT NULL AND evaluation_metric <> '' GROUP BY uses_reranker;
```

</details>

### G6 · `cspaper.evaluation_dataset` · list-vs-one

cspaper.evaluation_dataset names every benchmark a paper evaluates on (119 of 193 papers list two or more); G6a wants one benchmark category per paper (multi-hop QA / open-domain QA / other), G6b needs the individual multi-hop benchmarks, G6c counts the benchmarks listed

| Question | Asks |
|---|---|
| G6a | Grouping papers by the benchmarks they evaluate on (a multi-hop QA benchmark: HotpotQA, 2WikiMultihopQA or MuSiQue; otherwise an open-domain QA benchmark: Natural Questions, TriviaQA or PopQA; otherwise other datasets), how many papers are in each group, how many use an agent, and how many baselines do they compare against on average? |
| G6b | For multi-hop papers with and without an agent, how many evaluate on HotpotQA, on 2WikiMultihopQA and on MuSiQue? |
| G6c | Do papers that evaluate on more benchmarks compare against more baselines? Counting each listed dataset separately, for papers evaluating on one benchmark, two or three, and four or more: how many papers, how many study multi-hop reasoning, and how many baselines on average? |

**ALT for G6a**: rows changed 56; G6a keeps 1.0; breaks G6b 0.50 / 0.50, G6c 0.00 / 0.22

```sql
UPDATE cspaper SET evaluation_dataset = CASE WHEN evaluation_dataset LIKE '%HotpotQA%' THEN 'HotpotQA' WHEN evaluation_dataset LIKE '%2Wiki%' THEN '2WikiMultihopQA' WHEN evaluation_dataset LIKE '%MuSiQue%' THEN 'MuSiQue' WHEN evaluation_dataset LIKE '%Natural%Q%' OR ('||' || REPLACE(evaluation_dataset, ' ', '') || '||') LIKE '%||NQ||%' OR ('||' || REPLACE(evaluation_dataset, ' ', '') || '||') LIKE '%||NQ-Open||%' OR evaluation_dataset LIKE '%KILT NQ%' THEN 'Natural Questions' WHEN evaluation_dataset LIKE '%Trivia%QA%' THEN 'TriviaQA' WHEN evaluation_dataset LIKE '%PopQA%' THEN 'PopQA' ELSE evaluation_dataset END WHERE evaluation_dataset IS NOT NULL AND evaluation_dataset <> '';
```

<details><summary>SQL</summary>

```sql
-- G6a
SELECT CASE WHEN evaluation_dataset LIKE '%HotpotQA%' OR evaluation_dataset LIKE '%2Wiki%' OR evaluation_dataset LIKE '%MuSiQue%' THEN 'multi-hop QA' WHEN evaluation_dataset LIKE '%Natural%Q%' OR ('||' || REPLACE(evaluation_dataset, ' ', '') || '||') LIKE '%||NQ||%' OR ('||' || REPLACE(evaluation_dataset, ' ', '') || '||') LIKE '%||NQ-Open||%' OR evaluation_dataset LIKE '%KILT NQ%' OR evaluation_dataset LIKE '%Trivia%QA%' OR evaluation_dataset LIKE '%PopQA%' THEN 'open-domain QA' ELSE 'other datasets' END AS benchmark_group, COUNT(*) AS papers, SUM(CASE WHEN use_agent = 'Yes' THEN 1 ELSE 0 END) AS with_agent, AVG(baseline_amount) AS average_baselines FROM cspaper WHERE evaluation_dataset IS NOT NULL AND evaluation_dataset <> '' GROUP BY benchmark_group;
```
```sql
-- G6b
SELECT use_agent, COUNT(*) AS papers, SUM(CASE WHEN evaluation_dataset LIKE '%HotpotQA%' THEN 1 ELSE 0 END) AS on_hotpotqa, SUM(CASE WHEN evaluation_dataset LIKE '%2Wiki%' THEN 1 ELSE 0 END) AS on_2wikimultihopqa, SUM(CASE WHEN evaluation_dataset LIKE '%MuSiQue%' THEN 1 ELSE 0 END) AS on_musique FROM cspaper WHERE reasoning_depth = 'multi-hop' GROUP BY use_agent;
```
```sql
-- G6c
SELECT CASE WHEN length(evaluation_dataset) - length(replace(evaluation_dataset, '||', '')) = 0 THEN 'one benchmark' WHEN length(evaluation_dataset) - length(replace(evaluation_dataset, '||', '')) <= 4 THEN 'two or three benchmarks' ELSE 'four or more benchmarks' END AS benchmarks_used, COUNT(*) AS papers, SUM(CASE WHEN reasoning_depth LIKE '%multi-hop%' THEN 1 ELSE 0 END) AS multi_hop, AVG(baseline_amount) AS average_baselines FROM cspaper WHERE evaluation_dataset IS NOT NULL AND evaluation_dataset <> '' GROUP BY benchmarks_used;
```

</details>

