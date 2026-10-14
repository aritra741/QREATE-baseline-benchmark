# Representation-conflict queries: review

**What the systems see:** only the SQL below each question. The question text is a label for us. The correct answer comes from a hidden **answer key** (folded under each query), computed from the correct data, where values are stored as the documents state them.

**What makes a group a conflict:** its queries use one column, and each needs that column stored in a different form. The **stored forms** table shows each query's score (exact match) when the column is stored as the documents state it, and under each alternative form. Every query scores 1.0 under some form, and no single form gives 1.0 to all of them.

**How it was checked:**
1. Written, reviewed by a devil's advocate (realism of the SQL first) and revised, per collection.
2. The checker, re-run by me: the answer keys pass the standard query checks, the natural queries pass the realism rules, and the stored-form conditions above hold.
3. A blind reading test. Two judges per collection saw only the SQL, the schema and the differing values (no question, no key) and picked the stored form the SQL's author most likely means. 44 of 55 queries were kept, where both judges picked the key's form; the 11 others were dropped, along with 2 groups left without a conflict (listed at the end). Every query below passed.

| Collection | Groups | Queries |
|---|---|---|
| Artists | 3 | 6 |
| Med | 7 | 14 |
| Players | 2 | 4 |
| Papers | 5 | 10 |
| **Total** | **17** | **34** |

Coverage by type: see each heading. Legal has no group left: every legal group had a query the blind judges read differently from its key.


## Artists

### Artists G1: `art.field` (one value vs a list)

art.field lists every field an artist works in, main field first; a per-main-field question needs one field per artist (the main one), a who-works-in-sculpture question needs the whole list

**G1a.** For artists whose main field is sculpture, photography or illustration: how many artists per field, how many taught, and how many won at least one award?

```sql
SELECT field, COUNT(*) AS artists, SUM(teaching) AS teachers, SUM(CASE WHEN awards >= 1 THEN 1 ELSE 0 END) AS award_winners FROM art WHERE field IN ('Sculpture', 'Photography', 'Illustration') GROUP BY field;
```
<sub>Blind judges: Exact IN ('Sculpture','Photography','Illustration') with GROUP BY field expects a single primary field per row. Form 1 lets 'Sculpture||Painting' and similar ro</sub>

<details><summary>answer key</summary>

```sql
SELECT field, COUNT(*) AS artists, SUM(teaching) AS teachers, SUM(CASE WHEN awards >= 1 THEN 1 ELSE 0 END) AS award_winners FROM (SELECT CASE WHEN trim(CASE WHEN instr(field, '||') > 0 THEN substr(field, 1, instr(field, '||') - 1) ELSE field END) = 'Public Sculpture' THEN 'Sculpture' ELSE trim(CASE WHEN instr(field, '||') > 0 THEN substr(field, 1, instr(field, '||') - 1) ELSE field END) END AS field, teaching, awards FROM art) WHERE field IN ('Sculpture', 'Photography', 'Illustration') GROUP BY field;
```
</details>

**G1b.** Per birth continent with at least five such artists, how many artists work in sculpture (alone or alongside other fields), and how many of them taught?

```sql
SELECT birth_continent, COUNT(*) AS sculptors, SUM(teaching) AS teachers FROM art WHERE field LIKE '%Sculpture%' AND birth_continent <> '' GROUP BY birth_continent HAVING COUNT(*) >= 5;
```
<sub>Blind judges: LIKE '%Sculpture%' is a membership test written for a multi-valued field. Form 1 would drop sculptors listed second, as in 'Painting||Sculpture'.</sub>

<details><summary>answer key</summary>

```sql
SELECT birth_continent, COUNT(*) AS sculptors, SUM(teaching) AS teachers FROM art WHERE field LIKE '%Sculpture%' AND birth_continent <> '' GROUP BY birth_continent HAVING COUNT(*) >= 5;
```
</details>

Stored forms (exact match; rows changed):

| Query | as stated (0) | stored as G1a needs (599) |
|---|---|---|
| G1a | 0.00 | 1.00 |
| G1b | 1.00 | 0.00 |

<details><summary>stored forms as SQL</summary>

```sql
-- G1a
UPDATE art SET field = CASE WHEN trim(CASE WHEN instr(field, '||') > 0 THEN substr(field, 1, instr(field, '||') - 1) ELSE field END) = 'Public Sculpture' THEN 'Sculpture' ELSE trim(CASE WHEN instr(field, '||') > 0 THEN substr(field, 1, instr(field, '||') - 1) ELSE field END) END;
```
</details>

### Artists G2: `art.genre` (one value vs a list)

art.genre lists every genre an artist works in, main genre first; a per-main-genre question needs one genre per artist in the description's vocabulary, a who-paints-both-portraits-and-landscapes question needs the whole list

**G2a.** For artists whose main genre is portrait, landscape or abstract: how many artists per genre, how many taught, and what share won at least one award?

```sql
SELECT genre, COUNT(*) AS artists, SUM(teaching) AS teachers, AVG(CASE WHEN awards >= 1 THEN 1.0 ELSE 0.0 END) AS share_award_winners FROM art WHERE genre IN ('Portrait', 'Landscape', 'Abstract') GROUP BY genre;
```
<sub>Blind judges: Exact IN plus GROUP BY genre expects one primary genre per row, which matches the description's 'primary genre'. Form 1 lets 'Portrait||Landscape', 'Portraiture</sub>

<details><summary>answer key</summary>

```sql
SELECT genre, COUNT(*) AS artists, SUM(teaching) AS teachers, AVG(CASE WHEN awards >= 1 THEN 1.0 ELSE 0.0 END) AS share_award_winners FROM (SELECT CASE WHEN lower(trim(CASE WHEN instr(genre, '||') > 0 THEN substr(genre, 1, instr(genre, '||') - 1) ELSE genre END)) LIKE '%portrait%' THEN 'Portrait' WHEN lower(trim(CASE WHEN instr(genre, '||') > 0 THEN substr(genre, 1, instr(genre, '||') - 1) ELSE genre END)) LIKE '%landscape%' THEN 'Landscape' WHEN lower(trim(CASE WHEN instr(genre, '||') > 0 THEN substr(genre, 1, instr(genre, '||') - 1) ELSE genre END)) LIKE 'abstract%' OR lower(trim(CASE WHEN instr(genre, '||') > 0 THEN substr(genre, 1, instr(genre, '||') - 1) ELSE genre END)) = 'geometric abstraction' THEN 'Abstract' ELSE trim(CASE WHEN instr(genre, '||') > 0 THEN substr(genre, 1, instr(genre, '||') - 1) ELSE genre END) END AS genre, teaching, awards FROM art) WHERE genre IN ('Portrait', 'Landscape', 'Abstract') GROUP BY genre;
```
</details>

**G2b.** Per birth continent with at least five such artists, how many artists work in both portraits and landscapes, and how many of them taught?

```sql
SELECT birth_continent, COUNT(*) AS artists, SUM(teaching) AS teachers FROM art WHERE genre LIKE '%Portrait%' AND genre LIKE '%Landscape%' AND birth_continent <> '' GROUP BY birth_continent HAVING COUNT(*) >= 5;
```
<sub>Blind judges: The SQL requires a genre to contain both Portrait and Landscape, which is only possible if the multi-valued lists are kept. Form 1 keeps only one genre per row.</sub>

<details><summary>answer key</summary>

```sql
SELECT birth_continent, COUNT(*) AS artists, SUM(teaching) AS teachers FROM art WHERE genre LIKE '%Portrait%' AND genre LIKE '%Landscape%' AND birth_continent <> '' GROUP BY birth_continent HAVING COUNT(*) >= 5;
```
</details>

Stored forms (exact match; rows changed):

| Query | as stated (0) | stored as G2a needs (399) |
|---|---|---|
| G2a | 0.00 | 1.00 |
| G2b | 1.00 | 0.00 |

<details><summary>stored forms as SQL</summary>

```sql
-- G2a
UPDATE art SET genre = CASE WHEN lower(trim(CASE WHEN instr(genre, '||') > 0 THEN substr(genre, 1, instr(genre, '||') - 1) ELSE genre END)) LIKE '%portrait%' THEN 'Portrait' WHEN lower(trim(CASE WHEN instr(genre, '||') > 0 THEN substr(genre, 1, instr(genre, '||') - 1) ELSE genre END)) LIKE '%landscape%' THEN 'Landscape' WHEN lower(trim(CASE WHEN instr(genre, '||') > 0 THEN substr(genre, 1, instr(genre, '||') - 1) ELSE genre END)) LIKE 'abstract%' OR lower(trim(CASE WHEN instr(genre, '||') > 0 THEN substr(genre, 1, instr(genre, '||') - 1) ELSE genre END)) = 'geometric abstraction' THEN 'Abstract' ELSE trim(CASE WHEN instr(genre, '||') > 0 THEN substr(genre, 1, instr(genre, '||') - 1) ELSE genre END) END;
```
</details>

### Artists G3: `art.art_movement` (one value vs a list)

art.art_movement lists every movement an artist took part in, main movement first; a per-main-movement question needs one movement per artist, a who-took-part-in question needs the whole list

**G3a.** For artists whose main movement is Surrealism, Abstract Expressionism or Pop Art: how many artists per movement, how many taught, and how many won at least one award?

```sql
SELECT art_movement, COUNT(*) AS artists, SUM(teaching) AS teachers, SUM(CASE WHEN awards >= 1 THEN 1 ELSE 0 END) AS award_winners FROM art WHERE art_movement IN ('Surrealism', 'Abstract Expressionism', 'Pop Art') GROUP BY art_movement;
```
<sub>Blind judges: Exact IN match with GROUP BY art_movement expects one canonical movement per row. Form 1 fixes the case of 'Abstract expressionism' and turns 'Abstract Expressi</sub>

<details><summary>answer key</summary>

```sql
SELECT art_movement, COUNT(*) AS artists, SUM(teaching) AS teachers, SUM(CASE WHEN awards >= 1 THEN 1 ELSE 0 END) AS award_winners FROM (SELECT CASE WHEN lower(trim(CASE WHEN instr(art_movement, '||') > 0 THEN substr(art_movement, 1, instr(art_movement, '||') - 1) ELSE art_movement END)) LIKE '%surrealism%' THEN 'Surrealism' WHEN lower(trim(CASE WHEN instr(art_movement, '||') > 0 THEN substr(art_movement, 1, instr(art_movement, '||') - 1) ELSE art_movement END)) LIKE '%abstract expressionism%' THEN 'Abstract Expressionism' WHEN lower(trim(CASE WHEN instr(art_movement, '||') > 0 THEN substr(art_movement, 1, instr(art_movement, '||') - 1) ELSE art_movement END)) LIKE '%pop art%' THEN 'Pop Art' ELSE trim(CASE WHEN instr(art_movement, '||') > 0 THEN substr(art_movement, 1, instr(art_movement, '||') - 1) ELSE art_movement END) END AS art_movement, teaching, awards FROM art) WHERE art_movement IN ('Surrealism', 'Abstract Expressionism', 'Pop Art') GROUP BY art_movement;
```
</details>

**G3b.** For artists born in Europe and in North America, how many took part in Surrealism, in Pop Art and in Abstract Expressionism at any point in their career?

```sql
SELECT birth_continent, SUM(CASE WHEN art_movement LIKE '%Surrealism%' THEN 1 ELSE 0 END) AS surrealism, SUM(CASE WHEN art_movement LIKE '%Pop Art%' THEN 1 ELSE 0 END) AS pop_art, SUM(CASE WHEN art_movement LIKE '%Abstract Expressionism%' THEN 1 ELSE 0 END) AS abstract_expressionism FROM art WHERE birth_continent IN ('Europe', 'North America') GROUP BY birth_continent;
```
<sub>Blind judges: Each count uses LIKE '%X%' membership tests, so a row like 'Abstract Expressionism||Surrealism' should count for both movements. Form 1 keeps only the first mov</sub>

<details><summary>answer key</summary>

```sql
SELECT birth_continent, SUM(CASE WHEN art_movement LIKE '%Surrealism%' THEN 1 ELSE 0 END) AS surrealism, SUM(CASE WHEN art_movement LIKE '%Pop Art%' THEN 1 ELSE 0 END) AS pop_art, SUM(CASE WHEN art_movement LIKE '%Abstract Expressionism%' THEN 1 ELSE 0 END) AS abstract_expressionism FROM art WHERE birth_continent IN ('Europe', 'North America') GROUP BY birth_continent;
```
</details>

Stored forms (exact match; rows changed):

| Query | as stated (0) | stored as G3a needs (269) |
|---|---|---|
| G3a | 0.11 | 1.00 |
| G3b | 1.00 | 0.17 |

<details><summary>stored forms as SQL</summary>

```sql
-- G3a
UPDATE art SET art_movement = CASE WHEN lower(trim(CASE WHEN instr(art_movement, '||') > 0 THEN substr(art_movement, 1, instr(art_movement, '||') - 1) ELSE art_movement END)) LIKE '%surrealism%' THEN 'Surrealism' WHEN lower(trim(CASE WHEN instr(art_movement, '||') > 0 THEN substr(art_movement, 1, instr(art_movement, '||') - 1) ELSE art_movement END)) LIKE '%abstract expressionism%' THEN 'Abstract Expressionism' WHEN lower(trim(CASE WHEN instr(art_movement, '||') > 0 THEN substr(art_movement, 1, instr(art_movement, '||') - 1) ELSE art_movement END)) LIKE '%pop art%' THEN 'Pop Art' ELSE trim(CASE WHEN instr(art_movement, '||') > 0 THEN substr(art_movement, 1, instr(art_movement, '||') - 1) ELSE art_movement END) END;
```
</details>


## Med

### Med G1: `disease.disease_type` (one value vs a list)

disease.disease_type lists every class a disease belongs to; G1a groups by a disease's main type and needs one type per row, G1b counts a disease under every type it has and needs the full list

**G1a.** For each main disease type, how many diseases are there, and how many of them are chronic and how many have a high mortality?

```sql
SELECT disease_type, COUNT(*) AS diseases, SUM(CASE WHEN prognosis LIKE '%chronic%' THEN 1 ELSE 0 END) AS chronic, SUM(CASE WHEN prognosis LIKE '%high_mortality%' THEN 1 ELSE 0 END) AS high_mortality FROM disease WHERE disease_type <> '' GROUP BY disease_type;
```
<sub>Blind judges: GROUP BY disease_type on the exact value only makes sense with one class per row. Form 1 gives clean single-class groups; the stated form makes a separate group</sub>

<details><summary>answer key</summary>

```sql
SELECT disease_type, COUNT(*) AS diseases, SUM(CASE WHEN prognosis LIKE '%chronic%' THEN 1 ELSE 0 END) AS chronic, SUM(CASE WHEN prognosis LIKE '%high_mortality%' THEN 1 ELSE 0 END) AS high_mortality FROM (SELECT CASE disease_name WHEN 'Asthma' THEN 'allergic' WHEN 'Microcytic Anemia' THEN 'nutritional' WHEN 'Celiac Disease' THEN 'autoimmune' WHEN 'Chronic Fatigue Syndrome||myalgic encephalomyelitis' THEN 'idiopathic' WHEN 'Heart Failure' THEN 'vascular' WHEN 'Acne' THEN 'inflammatory' WHEN 'Immune Reconstitution Syndrome (IRS)' THEN 'inflammatory' ELSE TRIM(CASE WHEN instr(disease_type, '||') > 0 THEN substr(disease_type, 1, instr(disease_type, '||') - 1) ELSE disease_type END) END AS disease_type, prognosis FROM disease WHERE disease_type <> '') GROUP BY disease_type;
```
</details>

**G1b.** How many diseases are classified as inflammatory, as infectious, as vascular, as degenerative and as psychiatric?

```sql
SELECT SUM(CASE WHEN disease_type LIKE '%inflammatory%' THEN 1 ELSE 0 END) AS inflammatory, SUM(CASE WHEN disease_type LIKE '%infectious%' THEN 1 ELSE 0 END) AS infectious, SUM(CASE WHEN disease_type LIKE '%vascular%' THEN 1 ELSE 0 END) AS vascular, SUM(CASE WHEN disease_type LIKE '%degenerative%' THEN 1 ELSE 0 END) AS degenerative, SUM(CASE WHEN disease_type LIKE '%psychiatric%' THEN 1 ELSE 0 END) AS psychiatric FROM disease;
```
<sub>Blind judges: The query counts diseases tagged with each type using LIKE substring matching, which assumes a multi-label value. Form 1 keeps only one class and drops co-label</sub>

<details><summary>answer key</summary>

```sql
SELECT SUM(CASE WHEN disease_type LIKE '%inflammatory%' THEN 1 ELSE 0 END) AS inflammatory, SUM(CASE WHEN disease_type LIKE '%infectious%' THEN 1 ELSE 0 END) AS infectious, SUM(CASE WHEN disease_type LIKE '%vascular%' THEN 1 ELSE 0 END) AS vascular, SUM(CASE WHEN disease_type LIKE '%degenerative%' THEN 1 ELSE 0 END) AS degenerative, SUM(CASE WHEN disease_type LIKE '%psychiatric%' THEN 1 ELSE 0 END) AS psychiatric FROM disease;
```
</details>

Stored forms (exact match; rows changed):

| Query | as stated (0) | stored as G1a needs (52) |
|---|---|---|
| G1a | 0.08 | 1.00 |
| G1b | 1.00 | 0.00 |

<details><summary>stored forms as SQL</summary>

```sql
-- G1a
UPDATE disease SET disease_type = CASE disease_name WHEN 'Asthma' THEN 'allergic' WHEN 'Microcytic Anemia' THEN 'nutritional' WHEN 'Celiac Disease' THEN 'autoimmune' WHEN 'Chronic Fatigue Syndrome||myalgic encephalomyelitis' THEN 'idiopathic' WHEN 'Heart Failure' THEN 'vascular' WHEN 'Acne' THEN 'inflammatory' WHEN 'Immune Reconstitution Syndrome (IRS)' THEN 'inflammatory' ELSE TRIM(CASE WHEN instr(disease_type, '||') > 0 THEN substr(disease_type, 1, instr(disease_type, '||') - 1) ELSE disease_type END) END WHERE disease_type <> '';
```
</details>

### Med G2: `disease.treatments` (fine vs coarse)

disease.treatments lists each treatment modality as stated (oral_medication, injection, surgery, dietary_intervention, ...); G2a needs the kinds of treatment (medication, procedure, lifestyle), G2b the stated modalities

**G2a.** For chronic and other diseases, how many are treated with medication of any kind, how many with surgery or another procedure, and how many with lifestyle or diet changes?

```sql
SELECT CASE WHEN prognosis LIKE '%chronic%' THEN 'chronic' ELSE 'other' END AS course, COUNT(*) AS diseases, SUM(CASE WHEN treatments LIKE '%medication%' THEN 1 ELSE 0 END) AS medication, SUM(CASE WHEN treatments LIKE '%procedure%' THEN 1 ELSE 0 END) AS procedure, SUM(CASE WHEN treatments LIKE '%lifestyle%' THEN 1 ELSE 0 END) AS lifestyle FROM disease WHERE treatments <> '' GROUP BY course;
```
<sub>Blind judges: The filters look for 'medication', 'procedure' and 'lifestyle', which are Form 1's coarse categories. In the stated form 'procedure' never occurs, and injection</sub>

<details><summary>answer key</summary>

```sql
SELECT CASE WHEN prognosis LIKE '%chronic%' THEN 'chronic' ELSE 'other' END AS course, COUNT(*) AS diseases, SUM(CASE WHEN treatments LIKE '%medication%' THEN 1 ELSE 0 END) AS medication, SUM(CASE WHEN treatments LIKE '%procedure%' THEN 1 ELSE 0 END) AS procedure, SUM(CASE WHEN treatments LIKE '%lifestyle%' THEN 1 ELSE 0 END) AS lifestyle FROM (SELECT prognosis, CASE treatments WHEN 'oral_medication||injection' THEN 'medication' WHEN 'oral_medication||lifestyle_modification||dietary_intervention||regular_exercise' THEN 'medication||lifestyle' WHEN 'oral_medication||other' THEN 'medication||other' WHEN 'oral_medication||dietary_intervention' THEN 'medication||lifestyle' WHEN 'injection||dietary_intervention||lifestyle_modification' THEN 'medication||lifestyle' WHEN 'oral_medication||surgery' THEN 'medication||procedure' WHEN 'oral_medication||lifestyle_modification||dietary_intervention' THEN 'medication||lifestyle' WHEN 'chemotherapy||radiotherapy||surgery' THEN 'medication||procedure' WHEN 'chemotherapy||stem cell transplantation' THEN 'medication||procedure' WHEN 'physical_therapy||injection||oral_medication||device_implantation' THEN 'medication||procedure||physical or psychological therapy' WHEN 'lifestyle_modification||oral_medication||dietary_intervention' THEN 'medication||lifestyle' WHEN 'oral_medication' THEN 'medication' WHEN 'injection' THEN 'medication' WHEN 'oral_medication||inhaler||dietary_intervention' THEN 'medication||lifestyle' WHEN 'dietary_intervention' THEN 'lifestyle' WHEN 'oral_medication||psychotherapy||lifestyle_modification' THEN 'medication||lifestyle||physical or psychological therapy' WHEN 'oral_medication||injection||surgery||dietary_intervention||others' THEN 'medication||procedure||lifestyle||other' WHEN 'surgery||drug_therapy||lifestyle_modification||others' THEN 'medication||procedure||lifestyle||other' WHEN 'surgery||hormone_therapy||chemotherapy' THEN 'medication||procedure' WHEN 'oral_medication||lifestyle_modification||surgery' THEN 'medication||procedure||lifestyle' WHEN 'physical_therapy||oral_medication||surgery' THEN 'medication||procedure||physical or psychological therapy' WHEN 'oral_medication||lifestyle_modification||others' THEN 'medication||lifestyle||other' WHEN 'oral_medication||others' THEN 'medication||other' WHEN 'injection||oral_medication' THEN 'medication' WHEN 'psychotherapy' THEN 'physical or psychological therapy' WHEN 'surgery' THEN 'procedure' WHEN 'vaccination||oral_medication' THEN 'medication' WHEN 'injection||laboratory_test||dietary_intervention||lifestyle_modification' THEN 'medication||lifestyle||other' WHEN 'oral_medication||lifestyle_modification||dietary_intervention||others' THEN 'medication||lifestyle||other' WHEN 'oral_medication||physical_therapy||lifestyle_modification||surgery||injection||dietary_intervention' THEN 'medication||procedure||lifestyle||physical or psychological therapy' WHEN 'oral_medication||lifestyle_modification' THEN 'medication||lifestyle' WHEN 'surgery||oral_medication' THEN 'medication||procedure' WHEN 'oral_medication||surgery||physical_therapy||psychotherapy||others' THEN 'medication||procedure||physical or psychological therapy||other' WHEN 'psychotherapy||physical_therapy||lifestyle_modification' THEN 'lifestyle||physical or psychological therapy' WHEN 'oral_medication||psychotherapy||lifestyle_modification||dietary_intervention||regular_exercise||relaxation_techniques||meditation' THEN 'medication||lifestyle||physical or psychological therapy' WHEN 'surgery||radiotherapy||chemotherapy||biological_therapy||dietary_intervention' THEN 'medication||procedure||lifestyle' WHEN 'oral_medication||injection||surgery||lifestyle_modification||dietary_intervention||physical_therapy' THEN 'medication||procedure||lifestyle||physical or psychological therapy' WHEN 'oral_medication||chemotherapy||lifestyle_modification' THEN 'medication||lifestyle' WHEN 'physical_therapy||surgery||lifestyle_modification||others' THEN 'procedure||lifestyle||physical or psychological therapy||other' WHEN 'dietary_intervention||oral_medication' THEN 'medication||lifestyle' WHEN 'oral_medication||physical_therapy' THEN 'medication||physical or psychological therapy' WHEN 'chemotherapy' THEN 'medication' WHEN 'psychotherapy||oral_medication' THEN 'medication||physical or psychological therapy' WHEN 'lifestyle_modification||oral_medication||surgery||others' THEN 'medication||procedure||lifestyle||other' WHEN 'oral_medication||injection||surgery' THEN 'medication||procedure' WHEN 'oral_medication||injection||lifestyle_modification||dietary_intervention' THEN 'medication||lifestyle' WHEN 'injection||oral_medication||dietary_intervention||lifestyle_modification||surgery' THEN 'medication||procedure||lifestyle' WHEN 'physical_therapy||lifestyle_modification||dietary_intervention||oral_medication' THEN 'medication||lifestyle||physical or psychological therapy' WHEN 'injection||chemotherapy||immunotherapy' THEN 'medication' WHEN 'lifestyle_modification||dietary_intervention' THEN 'lifestyle' ELSE treatments END AS treatments FROM disease WHERE treatments <> '') GROUP BY course;
```
</details>

**G2b.** How many diseases are treated with surgery, with injections, with lifestyle changes, with a diet, and with physical therapy?

```sql
SELECT SUM(CASE WHEN treatments LIKE '%surgery%' THEN 1 ELSE 0 END) AS surgery, SUM(CASE WHEN treatments LIKE '%injection%' THEN 1 ELSE 0 END) AS injection, SUM(CASE WHEN treatments LIKE '%lifestyle_modification%' THEN 1 ELSE 0 END) AS lifestyle_modification, SUM(CASE WHEN treatments LIKE '%dietary_intervention%' THEN 1 ELSE 0 END) AS dietary_intervention, SUM(CASE WHEN treatments LIKE '%physical_therapy%' THEN 1 ELSE 0 END) AS physical_therapy FROM disease;
```
<sub>Blind judges: The filters use the exact category names from the column description (surgery, injection, lifestyle_modification, dietary_intervention, physical_therapy), which</sub>

<details><summary>answer key</summary>

```sql
SELECT SUM(CASE WHEN treatments LIKE '%surgery%' THEN 1 ELSE 0 END) AS surgery, SUM(CASE WHEN treatments LIKE '%injection%' THEN 1 ELSE 0 END) AS injection, SUM(CASE WHEN treatments LIKE '%lifestyle_modification%' THEN 1 ELSE 0 END) AS lifestyle_modification, SUM(CASE WHEN treatments LIKE '%dietary_intervention%' THEN 1 ELSE 0 END) AS dietary_intervention, SUM(CASE WHEN treatments LIKE '%physical_therapy%' THEN 1 ELSE 0 END) AS physical_therapy FROM disease;
```
</details>

Stored forms (exact match; rows changed):

| Query | as stated (0) | stored as G2a needs (89) |
|---|---|---|
| G2a | 0.25 | 1.00 |
| G2b | 1.00 | 0.00 |

<details><summary>stored forms as SQL</summary>

```sql
-- G2a
UPDATE disease SET treatments = CASE treatments WHEN 'oral_medication||injection' THEN 'medication' WHEN 'oral_medication||lifestyle_modification||dietary_intervention||regular_exercise' THEN 'medication||lifestyle' WHEN 'oral_medication||other' THEN 'medication||other' WHEN 'oral_medication||dietary_intervention' THEN 'medication||lifestyle' WHEN 'injection||dietary_intervention||lifestyle_modification' THEN 'medication||lifestyle' WHEN 'oral_medication||surgery' THEN 'medication||procedure' WHEN 'oral_medication||lifestyle_modification||dietary_intervention' THEN 'medication||lifestyle' WHEN 'chemotherapy||radiotherapy||surgery' THEN 'medication||procedure' WHEN 'chemotherapy||stem cell transplantation' THEN 'medication||procedure' WHEN 'physical_therapy||injection||oral_medication||device_implantation' THEN 'medication||procedure||physical or psychological therapy' WHEN 'lifestyle_modification||oral_medication||dietary_intervention' THEN 'medication||lifestyle' WHEN 'oral_medication' THEN 'medication' WHEN 'injection' THEN 'medication' WHEN 'oral_medication||inhaler||dietary_intervention' THEN 'medication||lifestyle' WHEN 'dietary_intervention' THEN 'lifestyle' WHEN 'oral_medication||psychotherapy||lifestyle_modification' THEN 'medication||lifestyle||physical or psychological therapy' WHEN 'oral_medication||injection||surgery||dietary_intervention||others' THEN 'medication||procedure||lifestyle||other' WHEN 'surgery||drug_therapy||lifestyle_modification||others' THEN 'medication||procedure||lifestyle||other' WHEN 'surgery||hormone_therapy||chemotherapy' THEN 'medication||procedure' WHEN 'oral_medication||lifestyle_modification||surgery' THEN 'medication||procedure||lifestyle' WHEN 'physical_therapy||oral_medication||surgery' THEN 'medication||procedure||physical or psychological therapy' WHEN 'oral_medication||lifestyle_modification||others' THEN 'medication||lifestyle||other' WHEN 'oral_medication||others' THEN 'medication||other' WHEN 'injection||oral_medication' THEN 'medication' WHEN 'psychotherapy' THEN 'physical or psychological therapy' WHEN 'surgery' THEN 'procedure' WHEN 'vaccination||oral_medication' THEN 'medication' WHEN 'injection||laboratory_test||dietary_intervention||lifestyle_modification' THEN 'medication||lifestyle||other' WHEN 'oral_medication||lifestyle_modification||dietary_intervention||others' THEN 'medication||lifestyle||other' WHEN 'oral_medication||physical_therapy||lifestyle_modification||surgery||injection||dietary_intervention' THEN 'medication||procedure||lifestyle||physical or psychological therapy' WHEN 'oral_medication||lifestyle_modification' THEN 'medication||lifestyle' WHEN 'surgery||oral_medication' THEN 'medication||procedure' WHEN 'oral_medication||surgery||physical_therapy||psychotherapy||others' THEN 'medication||procedure||physical or psychological therapy||other' WHEN 'psychotherapy||physical_therapy||lifestyle_modification' THEN 'lifestyle||physical or psychological therapy' WHEN 'oral_medication||psychotherapy||lifestyle_modification||dietary_intervention||regular_exercise||relaxation_techniques||meditation' THEN 'medication||lifestyle||physical or psychological therapy' WHEN 'surgery||radiotherapy||chemotherapy||biological_therapy||dietary_intervention' THEN 'medication||procedure||lifestyle' WHEN 'oral_medication||injection||surgery||lifestyle_modification||dietary_intervention||physical_therapy' THEN 'medication||procedure||lifestyle||physical or psychological therapy' WHEN 'oral_medication||chemotherapy||lifestyle_modification' THEN 'medication||lifestyle' WHEN 'physical_therapy||surgery||lifestyle_modification||others' THEN 'procedure||lifestyle||physical or psychological therapy||other' WHEN 'dietary_intervention||oral_medication' THEN 'medication||lifestyle' WHEN 'oral_medication||physical_therapy' THEN 'medication||physical or psychological therapy' WHEN 'chemotherapy' THEN 'medication' WHEN 'psychotherapy||oral_medication' THEN 'medication||physical or psychological therapy' WHEN 'lifestyle_modification||oral_medication||surgery||others' THEN 'medication||procedure||lifestyle||other' WHEN 'oral_medication||injection||surgery' THEN 'medication||procedure' WHEN 'oral_medication||injection||lifestyle_modification||dietary_intervention' THEN 'medication||lifestyle' WHEN 'injection||oral_medication||dietary_intervention||lifestyle_modification||surgery' THEN 'medication||procedure||lifestyle' WHEN 'physical_therapy||lifestyle_modification||dietary_intervention||oral_medication' THEN 'medication||lifestyle||physical or psychological therapy' WHEN 'injection||chemotherapy||immunotherapy' THEN 'medication' WHEN 'lifestyle_modification||dietary_intervention' THEN 'lifestyle' ELSE treatments END WHERE treatments <> '';
```
</details>

### Med G3: `drug.disease_name` (join partner's spelling)

drug.disease_name lists the conditions a label treats as the label words them; G3a joins the disease table and needs each drug's main condition stored in the disease table's spelling, G3b needs every stated condition

**G3a.** For each disease the collection describes, how many drug labels are mainly for it, and how many of those need a prescription?

```sql
SELECT disease.disease_name, COUNT(*) AS drugs, SUM(CASE WHEN drug.prescription_status = 'prescription_only' THEN 1 ELSE 0 END) AS prescription_only FROM drug JOIN disease ON drug.disease_name = disease.disease_name GROUP BY disease.disease_name;
```
<sub>Blind judges: The equality join drug.disease_name = disease.disease_name needs one standard disease name per drug. Form 1 normalizes to standard names. The stated form holds </sub>

<details><summary>answer key</summary>

```sql
SELECT disease.disease_name, COUNT(*) AS drugs, SUM(CASE WHEN drug.prescription_status = 'prescription_only' THEN 1 ELSE 0 END) AS prescription_only FROM drug JOIN disease ON disease.disease_name = CASE drug.disease_name WHEN 'Major depressive disorder||Cancer-related anxiety||Cancer-related depression||Eating disorders||Headaches||Substance abuse||Alcohol abuse||Opioid abuse||Smoking||Cocaine abuse' THEN 'Major Depressive Disorder' WHEN 'Gastroesophageal reflux disease||Peptic ulcer disease' THEN 'Gastroesophageal Reflux Disease||GERD' WHEN 'Gastroesophageal reflux disease||Gastric acid-related disorders' THEN 'Gastroesophageal Reflux Disease||GERD' WHEN 'Gastroesophageal Reflux Disease||Esophagitis||Zollinger-Ellison Syndrome||Multiple Endocrine Adenomas' THEN 'Gastroesophageal Reflux Disease||GERD' WHEN 'Attention Deficit Hyperactivity Disorder||High Blood Pressure' THEN 'Attention-Deficit Hyperactivity Disorder' WHEN 'Attention Deficit Hyperactivity Disorder' THEN 'Attention-Deficit Hyperactivity Disorder' WHEN 'ADHD||attention deficit disorder||narcolepsy||depression||obesity' THEN 'Attention-Deficit Hyperactivity Disorder' WHEN 'Irritable Bowel Syndrome with Constipation||Chronic Idiopathic Constipation||Functional Constipation' THEN 'Irritable Bowel Syndrome' WHEN 'Post transplantation diabetes mellitus||Impaired glucose tolerance||Diabetes Mellitus' THEN 'Diabetes Mellitus' WHEN 'Diabetes||Heart Disease||Urinary Tract Infections||Gastric Ulcers||Candida Infection||Dengue Fever' THEN 'Diabetes Mellitus' WHEN 'Type 2 Diabetes' THEN 'Type 2 Diabetes Mellitus' WHEN 'Hypertension||Heart Diseases||Kidney Failure||Liver Failure' THEN 'Hypertension' WHEN 'Hypertension||Chronic kidney disease||Severe congestive heart failure||Volume depletion' THEN 'Hypertension' WHEN 'Periodontal disease' THEN 'Periodontal Disease' WHEN 'Depression||Obsessive-Compulsive Disorder||Panic Disorder||Bulimia Nervosa' THEN 'Depression' WHEN 'treatment-resistant depression' THEN 'Major Depressive Disorder' WHEN 'severe eosinophilic asthma||eosinophilic granulomatosis with polyangiitis||chronic obstructive pulmonary disease' THEN 'Asthma' WHEN 'Herpes labialis||Herpes simplex' THEN 'Herpes Simplex Virus Infection||cold sores||genital herpes' WHEN 'Herpes simplex||Genital herpes||Shingles||Chicken pox||Cold sores||Epstein-Barr virus infection' THEN 'Herpes Simplex Virus Infection||cold sores||genital herpes' WHEN 'osteoarthritis||rheumatoid arthritis||gout||ankylosing spondylitis||tendinitis||bursitis' THEN 'Osteoarthritis' WHEN 'Generalized Anxiety Disorder||Panic Disorder' THEN 'Anxiety Disorders' WHEN 'Alcohol withdrawal||Anxiety disorders||Muscle spasms||Stiffness||Seizures||Panic attacks||Vertigo||Insomnia' THEN 'Anxiety Disorders' WHEN 'Human immunodeficiency virus infection||diabetes mellitus||gastrointestinal disorders||peptic ulcers||tuberculosis||Mycobacteria kansasii infection||Mycobacteria xenopi infection' THEN 'Tuberculosis' WHEN 'Metastatic Colorectal Cancer||Gastrointestinal Stromal Tumour' THEN 'Metastatic Colorectal Cancer||mCRC' WHEN 'HIV infection||AIDS' THEN 'HIV-1 Infection' WHEN 'acute graft-vs-host disease' THEN 'Acute Graft-Versus-Host Disease' WHEN 'Cystic fibrosis' THEN 'Cystic Fibrosis' WHEN 'cancer' THEN 'Cancer' ELSE drug.disease_name END GROUP BY disease.disease_name;
```
</details>

**G3b.** How many drug labels list panic, an ulcer, gout, diabetes and heart failure among the conditions they treat?

```sql
SELECT SUM(CASE WHEN disease_name LIKE '%panic%' THEN 1 ELSE 0 END) AS panic, SUM(CASE WHEN disease_name LIKE '%ulcer%' THEN 1 ELSE 0 END) AS ulcer, SUM(CASE WHEN disease_name LIKE '%gout%' THEN 1 ELSE 0 END) AS gout, SUM(CASE WHEN disease_name LIKE '%diabetes%' THEN 1 ELSE 0 END) AS diabetes, SUM(CASE WHEN disease_name LIKE '%heart failure%' THEN 1 ELSE 0 END) AS heart_failure FROM drug;
```
<sub>Blind judges: The query counts drugs whose disease list mentions panic, ulcer, gout, diabetes or heart failure. Form 1 collapses each drug to a single primary disease and los</sub>

<details><summary>answer key</summary>

```sql
SELECT SUM(CASE WHEN disease_name LIKE '%panic%' THEN 1 ELSE 0 END) AS panic, SUM(CASE WHEN disease_name LIKE '%ulcer%' THEN 1 ELSE 0 END) AS ulcer, SUM(CASE WHEN disease_name LIKE '%gout%' THEN 1 ELSE 0 END) AS gout, SUM(CASE WHEN disease_name LIKE '%diabetes%' THEN 1 ELSE 0 END) AS diabetes, SUM(CASE WHEN disease_name LIKE '%heart failure%' THEN 1 ELSE 0 END) AS heart_failure FROM drug;
```
</details>

Stored forms (exact match; rows changed):

| Query | as stated (0) | stored as G3a needs (28) |
|---|---|---|
| G3a | 0.15 | 1.00 |
| G3b | 1.00 | 0.00 |

<details><summary>stored forms as SQL</summary>

```sql
-- G3a
UPDATE drug SET disease_name = CASE disease_name WHEN 'Major depressive disorder||Cancer-related anxiety||Cancer-related depression||Eating disorders||Headaches||Substance abuse||Alcohol abuse||Opioid abuse||Smoking||Cocaine abuse' THEN 'Major Depressive Disorder' WHEN 'Gastroesophageal reflux disease||Peptic ulcer disease' THEN 'Gastroesophageal Reflux Disease||GERD' WHEN 'Gastroesophageal reflux disease||Gastric acid-related disorders' THEN 'Gastroesophageal Reflux Disease||GERD' WHEN 'Gastroesophageal Reflux Disease||Esophagitis||Zollinger-Ellison Syndrome||Multiple Endocrine Adenomas' THEN 'Gastroesophageal Reflux Disease||GERD' WHEN 'Attention Deficit Hyperactivity Disorder||High Blood Pressure' THEN 'Attention-Deficit Hyperactivity Disorder' WHEN 'Attention Deficit Hyperactivity Disorder' THEN 'Attention-Deficit Hyperactivity Disorder' WHEN 'ADHD||attention deficit disorder||narcolepsy||depression||obesity' THEN 'Attention-Deficit Hyperactivity Disorder' WHEN 'Irritable Bowel Syndrome with Constipation||Chronic Idiopathic Constipation||Functional Constipation' THEN 'Irritable Bowel Syndrome' WHEN 'Post transplantation diabetes mellitus||Impaired glucose tolerance||Diabetes Mellitus' THEN 'Diabetes Mellitus' WHEN 'Diabetes||Heart Disease||Urinary Tract Infections||Gastric Ulcers||Candida Infection||Dengue Fever' THEN 'Diabetes Mellitus' WHEN 'Type 2 Diabetes' THEN 'Type 2 Diabetes Mellitus' WHEN 'Hypertension||Heart Diseases||Kidney Failure||Liver Failure' THEN 'Hypertension' WHEN 'Hypertension||Chronic kidney disease||Severe congestive heart failure||Volume depletion' THEN 'Hypertension' WHEN 'Periodontal disease' THEN 'Periodontal Disease' WHEN 'Depression||Obsessive-Compulsive Disorder||Panic Disorder||Bulimia Nervosa' THEN 'Depression' WHEN 'treatment-resistant depression' THEN 'Major Depressive Disorder' WHEN 'severe eosinophilic asthma||eosinophilic granulomatosis with polyangiitis||chronic obstructive pulmonary disease' THEN 'Asthma' WHEN 'Herpes labialis||Herpes simplex' THEN 'Herpes Simplex Virus Infection||cold sores||genital herpes' WHEN 'Herpes simplex||Genital herpes||Shingles||Chicken pox||Cold sores||Epstein-Barr virus infection' THEN 'Herpes Simplex Virus Infection||cold sores||genital herpes' WHEN 'osteoarthritis||rheumatoid arthritis||gout||ankylosing spondylitis||tendinitis||bursitis' THEN 'Osteoarthritis' WHEN 'Generalized Anxiety Disorder||Panic Disorder' THEN 'Anxiety Disorders' WHEN 'Alcohol withdrawal||Anxiety disorders||Muscle spasms||Stiffness||Seizures||Panic attacks||Vertigo||Insomnia' THEN 'Anxiety Disorders' WHEN 'Human immunodeficiency virus infection||diabetes mellitus||gastrointestinal disorders||peptic ulcers||tuberculosis||Mycobacteria kansasii infection||Mycobacteria xenopi infection' THEN 'Tuberculosis' WHEN 'Metastatic Colorectal Cancer||Gastrointestinal Stromal Tumour' THEN 'Metastatic Colorectal Cancer||mCRC' WHEN 'HIV infection||AIDS' THEN 'HIV-1 Infection' WHEN 'acute graft-vs-host disease' THEN 'Acute Graft-Versus-Host Disease' WHEN 'Cystic fibrosis' THEN 'Cystic Fibrosis' WHEN 'cancer' THEN 'Cancer' ELSE disease_name END;
```
</details>

### Med G4: `drug.dosage_frequency` (number vs stated text)

drug.dosage_frequency states the schedule in words ('twice a day', 'every 4-6 hours', several schedules joined); G4a needs the most doses a day as a number, G4c one wording per schedule ('twice a day' = 'twice daily'), G4b the stated wording (hours, 'as needed')

**G4a.** Grouping drugs by the most doses a day their label allows, how many drugs are in each group and how many of them need a prescription?

```sql
SELECT dosage_frequency, COUNT(*) AS drugs, SUM(CASE WHEN prescription_status = 'prescription_only' THEN 1 ELSE 0 END) AS prescription_only FROM drug WHERE dosage_frequency IS NOT NULL GROUP BY dosage_frequency;
```
<sub>Blind judges: The query groups by the raw value and filters IS NOT NULL. Only Form 2 stores missing values as NULL, so the filter removes them; in the text forms an empty-str</sub>

<details><summary>answer key</summary>

```sql
SELECT dosage_frequency, COUNT(*) AS drugs, SUM(CASE WHEN prescription_status = 'prescription_only' THEN 1 ELSE 0 END) AS prescription_only FROM (SELECT CASE dosage_frequency WHEN '2 or 3 times a day' THEN 3 WHEN '2 or 3 times daily' THEN 3 WHEN '3-4 times per day||once daily' THEN 4 WHEN 'continuous infusion||three times a day||once or twice a day||once every 8 hours' THEN 3 WHEN 'every 12 hours||every 24 hours' THEN 2 WHEN 'every 4 to 6 hours as needed' THEN 6 WHEN 'every 4-6 hours' THEN 6 WHEN 'every 4-6 hours||3 to 4 times a day' THEN 6 WHEN 'every 6 to 8 hours || every 6 hours' THEN 4 WHEN 'every 6-8 hours||maximum 4 doses per day' THEN 4 WHEN 'every 8 hours' THEN 3 WHEN 'every 8 hours||every 8-12 hours||every 12 hours' THEN 3 WHEN 'every four hours as needed' THEN 6 WHEN 'once a day' THEN 1 WHEN 'once a day||once daily' THEN 1 WHEN 'once daily' THEN 1 WHEN 'once daily || three times daily' THEN 3 WHEN 'once daily||not more than once per day||not more than once in every 48 hours' THEN 1 WHEN 'once daily||twice a day' THEN 2 WHEN 'once daily||twice daily' THEN 2 WHEN 'once every 4 to eight hours' THEN 6 WHEN 'once or thrice daily' THEN 3 WHEN 'once or twice a day' THEN 2 WHEN 'three times a day' THEN 3 WHEN 'three times daily||twice daily' THEN 3 WHEN 'three times per day' THEN 3 WHEN 'twice a day' THEN 2 WHEN 'twice daily' THEN 2 WHEN 'twice every 24 hours || thrice daily' THEN 3 WHEN 'up to three times a day' THEN 3 ELSE NULL END AS dosage_frequency, prescription_status FROM drug) WHERE dosage_frequency IS NOT NULL GROUP BY dosage_frequency;
```
</details>

**G4c.** For prescription-only drugs and the others, how many labels give a dosing schedule, and how many give it as once, twice, three times or four times a day (not as an hour interval)?

```sql
SELECT CASE WHEN prescription_status = 'prescription_only' THEN 'prescription only' ELSE 'other' END AS status, COUNT(*) AS drugs, SUM(CASE WHEN dosage_frequency LIKE '%once daily%' THEN 1 ELSE 0 END) AS once_daily, SUM(CASE WHEN dosage_frequency LIKE '%twice daily%' THEN 1 ELSE 0 END) AS twice_daily, SUM(CASE WHEN dosage_frequency LIKE '%three times daily%' THEN 1 ELSE 0 END) AS three_times_daily, SUM(CASE WHEN dosage_frequency LIKE '%four times daily%' THEN 1 ELSE 0 END) AS four_times_daily FROM drug WHERE dosage_frequency <> '' GROUP BY status;
```
<sub>Blind judges: The filters look for the phrases 'once daily', 'twice daily', 'three times daily' and 'four times daily'. Form 2 normalizes values like 'twice a day', 'thrice d</sub>

<details><summary>answer key</summary>

```sql
SELECT CASE WHEN prescription_status = 'prescription_only' THEN 'prescription only' ELSE 'other' END AS status, COUNT(*) AS drugs, SUM(CASE WHEN dosage_frequency LIKE '%once daily%' THEN 1 ELSE 0 END) AS once_daily, SUM(CASE WHEN dosage_frequency LIKE '%twice daily%' THEN 1 ELSE 0 END) AS twice_daily, SUM(CASE WHEN dosage_frequency LIKE '%three times daily%' THEN 1 ELSE 0 END) AS three_times_daily, SUM(CASE WHEN dosage_frequency LIKE '%four times daily%' THEN 1 ELSE 0 END) AS four_times_daily FROM (SELECT prescription_status, CASE dosage_frequency WHEN '2 or 3 times a day' THEN 'twice daily||three times daily' WHEN '2 or 3 times daily' THEN 'twice daily||three times daily' WHEN '3-4 times per day||once daily' THEN 'three times daily||four times daily||once daily' WHEN 'continuous infusion||three times a day||once or twice a day||once every 8 hours' THEN 'continuous infusion||three times daily||once daily||twice daily||every 8 hours' WHEN 'every 4 to 6 hours as needed' THEN 'every 4-6 hours as needed' WHEN 'every 4-6 hours||3 to 4 times a day' THEN 'every 4-6 hours||three times daily||four times daily' WHEN 'every 6 to 8 hours || every 6 hours' THEN 'every 6-8 hours||every 6 hours' WHEN 'every 6-8 hours||maximum 4 doses per day' THEN 'every 6-8 hours||up to four times daily' WHEN 'every four hours as needed' THEN 'every 4 hours as needed' WHEN 'once a day' THEN 'once daily' WHEN 'once a day||once daily' THEN 'once daily' WHEN 'once daily || three times daily' THEN 'once daily||three times daily' WHEN 'once daily||not more than once per day||not more than once in every 48 hours' THEN 'once daily||not more than once every 48 hours' WHEN 'once daily||twice a day' THEN 'once daily||twice daily' WHEN 'once every 4 to eight hours' THEN 'every 4-8 hours' WHEN 'once or thrice daily' THEN 'once daily||three times daily' WHEN 'once or twice a day' THEN 'once daily||twice daily' WHEN 'three times a day' THEN 'three times daily' WHEN 'three times per day' THEN 'three times daily' WHEN 'twice a day' THEN 'twice daily' WHEN 'twice every 24 hours || thrice daily' THEN 'twice daily||three times daily' WHEN 'up to three times a day' THEN 'up to three times daily' ELSE dosage_frequency END AS dosage_frequency FROM drug WHERE dosage_frequency <> '') GROUP BY status;
```
</details>

Stored forms (exact match; rows changed):

| Query | as stated (0) | stored as G4a needs (100) | stored as G4c needs (31) |
|---|---|---|---|
| G4a | 0.00 | 1.00 | 0.00 |
| G4c | 0.30 | 0.10 | 1.00 |

<details><summary>stored forms as SQL</summary>

```sql
-- G4a
UPDATE drug SET dosage_frequency = CASE dosage_frequency WHEN '2 or 3 times a day' THEN 3 WHEN '2 or 3 times daily' THEN 3 WHEN '3-4 times per day||once daily' THEN 4 WHEN 'continuous infusion||three times a day||once or twice a day||once every 8 hours' THEN 3 WHEN 'every 12 hours||every 24 hours' THEN 2 WHEN 'every 4 to 6 hours as needed' THEN 6 WHEN 'every 4-6 hours' THEN 6 WHEN 'every 4-6 hours||3 to 4 times a day' THEN 6 WHEN 'every 6 to 8 hours || every 6 hours' THEN 4 WHEN 'every 6-8 hours||maximum 4 doses per day' THEN 4 WHEN 'every 8 hours' THEN 3 WHEN 'every 8 hours||every 8-12 hours||every 12 hours' THEN 3 WHEN 'every four hours as needed' THEN 6 WHEN 'once a day' THEN 1 WHEN 'once a day||once daily' THEN 1 WHEN 'once daily' THEN 1 WHEN 'once daily || three times daily' THEN 3 WHEN 'once daily||not more than once per day||not more than once in every 48 hours' THEN 1 WHEN 'once daily||twice a day' THEN 2 WHEN 'once daily||twice daily' THEN 2 WHEN 'once every 4 to eight hours' THEN 6 WHEN 'once or thrice daily' THEN 3 WHEN 'once or twice a day' THEN 2 WHEN 'three times a day' THEN 3 WHEN 'three times daily||twice daily' THEN 3 WHEN 'three times per day' THEN 3 WHEN 'twice a day' THEN 2 WHEN 'twice daily' THEN 2 WHEN 'twice every 24 hours || thrice daily' THEN 3 WHEN 'up to three times a day' THEN 3 ELSE NULL END;
```
```sql
-- G4c
UPDATE drug SET dosage_frequency = CASE dosage_frequency WHEN '2 or 3 times a day' THEN 'twice daily||three times daily' WHEN '2 or 3 times daily' THEN 'twice daily||three times daily' WHEN '3-4 times per day||once daily' THEN 'three times daily||four times daily||once daily' WHEN 'continuous infusion||three times a day||once or twice a day||once every 8 hours' THEN 'continuous infusion||three times daily||once daily||twice daily||every 8 hours' WHEN 'every 4 to 6 hours as needed' THEN 'every 4-6 hours as needed' WHEN 'every 4-6 hours||3 to 4 times a day' THEN 'every 4-6 hours||three times daily||four times daily' WHEN 'every 6 to 8 hours || every 6 hours' THEN 'every 6-8 hours||every 6 hours' WHEN 'every 6-8 hours||maximum 4 doses per day' THEN 'every 6-8 hours||up to four times daily' WHEN 'every four hours as needed' THEN 'every 4 hours as needed' WHEN 'once a day' THEN 'once daily' WHEN 'once a day||once daily' THEN 'once daily' WHEN 'once daily || three times daily' THEN 'once daily||three times daily' WHEN 'once daily||not more than once per day||not more than once in every 48 hours' THEN 'once daily||not more than once every 48 hours' WHEN 'once daily||twice a day' THEN 'once daily||twice daily' WHEN 'once every 4 to eight hours' THEN 'every 4-8 hours' WHEN 'once or thrice daily' THEN 'once daily||three times daily' WHEN 'once or twice a day' THEN 'once daily||twice daily' WHEN 'three times a day' THEN 'three times daily' WHEN 'three times per day' THEN 'three times daily' WHEN 'twice a day' THEN 'twice daily' WHEN 'twice every 24 hours || thrice daily' THEN 'twice daily||three times daily' WHEN 'up to three times a day' THEN 'up to three times daily' ELSE dosage_frequency END;
```
</details>

### Med G5: `drug.single_dose` (number vs stated text)

drug.single_dose states population + dose pairs as text ('adults 10 mg || children 5 mg'); G5a needs the highest adult dose as a number of mg, G5b needs the stated text (weight-based doses)

**G5a.** How many drugs have a highest adult dose under 10 mg, from 10 to 99 mg, and 100 mg or more, and how many of each need a prescription?

```sql
SELECT CASE WHEN CAST(single_dose AS REAL) < 10 THEN 'under 10 mg' WHEN CAST(single_dose AS REAL) < 100 THEN '10 to 99 mg' ELSE '100 mg or more' END AS dose_range, COUNT(*) AS drugs, SUM(CASE WHEN prescription_status = 'prescription_only' THEN 1 ELSE 0 END) AS prescription_only FROM drug WHERE single_dose IS NOT NULL GROUP BY dose_range;
```
<sub>Blind judges: CAST(single_dose AS REAL) put into mg ranges, with an IS NOT NULL filter, needs one numeric mg value with NULL for missing. Form 1 provides that; the stated tex</sub>

<details><summary>answer key</summary>

```sql
SELECT CASE WHEN CAST(mg AS REAL) < 10 THEN 'under 10 mg' WHEN CAST(mg AS REAL) < 100 THEN '10 to 99 mg' ELSE '100 mg or more' END AS dose_range, COUNT(*) AS drugs, SUM(CASE WHEN prescription_status = 'prescription_only' THEN 1 ELSE 0 END) AS prescription_only FROM (SELECT CASE single_dose WHEN 'adults 25 milligrams' THEN 25 WHEN 'adults 400 mcg' THEN 0.4 WHEN 'adults 4 g piperacillin + 0.5 g tazobactam' THEN 4000 WHEN 'Esophageal-gastric varices bleeding 0.025 mg/hour intravenous infusion || Prevention of pancreatic complications 0.1 mg subcutaneous injection || Gastrointestinal pancreatic endocrine tumors 0.05 mg subcutaneous injection || Acromegaly 0.05~0.1 mg subcutaneous injection' THEN 0.1 WHEN 'adults 10-40 mg once a day||cardiovascular prevention 40 mg per day||post-transplant (immunosuppressive therapy) 20 mg per day (up to 40 mg)||renal or hepatic insufficiency 10 mg per day' THEN 40 WHEN 'adults 2 mg' THEN 2 WHEN 'adults 40 mg' THEN 40 WHEN 'adults 12.5 mg (Day 1)||adults 12.5 mg twice/d (for 2 days)||adults 25 mg twice/d (for 4 days)||adults 50 mg twice/d (for 7 days)||adults 100 mg twice/d (for 7 days)' THEN 100 WHEN 'adults 20 mg' THEN 20 WHEN 'adults 500 mg||children 12 mg per 2' THEN 500 WHEN 'adults 500mcg||adults 250mcg' THEN 0.5 WHEN 'adults 20 mg||pediatric patients 0.5 mg/kg/dose or 1 mg/kg/dose' THEN 20 WHEN 'adults 1 mg norethindrone acetate and 10 mcg ethinyl estradiol per tablet' THEN 1 WHEN 'adults 500 mg' THEN 500 WHEN 'adults 12.5 mg (Day 1)||adults 12.5 mg twice daily (for 2 days)||adults 25 mg twice daily (for 4 days)||adults 50 mg twice daily (for 7 days)||adults 100 mg twice daily (for 7 days)' THEN 100 WHEN 'adults 25 mg || elderly 30-50 mg || adolescents 30-50 mg' THEN 25 WHEN 'children and adolescents up to 54mg daily||adults up to 72mg daily' THEN 72 WHEN 'adults 250 mg || adults 500 mg || adults 750 mg || adults 1000 mg' THEN 1000 WHEN 'adults 600 mg' THEN 600 WHEN 'adults 1-2 tablets 500mg||adults 1 tablet 750mg||children 1 drop/kg (not exceeding 35 drops)||children see weight-based mL dosing' THEN 1000 WHEN 'adults 1 mg || adults 2 mg' THEN 2 WHEN '15 mg' THEN 15 WHEN 'adults 25-50 mg' THEN 50 WHEN 'adults sinusitis 500 mg||adults acute exacerbation of chronic bronchitis 250-500 mg||adults skin and soft tissue infections 250-500 mg||adults creatinine clearance 250 mg/24h||adults creatinine clearance 500 mg/24h||adults creatinine clearance 500 mg/12h||adults 50-20 mL/min 125-500 mg/24h||adults 19-10 mL/min 125-500 mg/24h||adults 10 mL/min 125-250 mg/24-48h' THEN 500 WHEN 'adults 5 mg||adults 10 mg||children over 6 years 2.5 mg||children over 6 years 5 mg' THEN 10 WHEN '125 to 250 mg || 250 to 500 mg' THEN 500 WHEN 'adults 400 mg' THEN 400 WHEN 'adults 10 mg || adults 25 mg' THEN 25 WHEN 'adults 30 mg 1-2 tablets || adults 60 mg 1 tablet' THEN 60 WHEN 'adults 160 mg' THEN 160 WHEN 'adults 300 mg' THEN 300 WHEN 'newborns 0.5 mg/kg/dose || pediatric patients <30 kg 1 mg/kg/dose || pediatric patients ≥30 kg adult dosage || adults ≥60 kg 20 mg || adults <60 kg 15 mg' THEN 20 WHEN 'adults and children 12 years old and older weighing 40 kg or more 1 tablet of 500 mg + 125 mg' THEN 500 WHEN 'adults 1 mg' THEN 1 WHEN 'adults and children over 12 years 200 mg each 8 hours up to 400 mg each 8-12 hours || children 6-12 years 200 mg each 8-12 hours up to 400 mg each 12 hours || adults and children over 12 years (prevention) 400 mg each 12 hours || children 6-12 years (prevention) 200-400 mg each 12 hours || adults and children over 12 years (hyperammonemia) 400 mg each 8 hours || children 6-12 years (hyperammonemia) 200-300 mg each 8 hours' THEN 400 WHEN 'most patients 5 mg || patients with severe renal impairment 2.5 mg || patients with moderate hepatic impairment 2.5 mg' THEN 5 WHEN 'adults 5 mg || adults 10 mg || adults 20 mg' THEN 20 WHEN 'adults 100 mg' THEN 100 WHEN 'adults 250-500mg||children 15mg/kg daily' THEN 500 WHEN '250 mg capsule||500 mg tablet||500 mg intravenous' THEN 500 WHEN 'oral 400mg||oral 800mg' THEN 800 WHEN 'adults 25 mg (oral capsule)||adults 1 mg (intravenous)||adults 10-20 mg (oral, equivalent to 1 mg IV)' THEN 25 WHEN 'patients with severe asthma aged 12 years and older 100 mg || adult patients with EGPA 3x100 mg' THEN 300 WHEN 'adults and adolescents (12 years and older) initial 400 mg (two 200 mg injections) || adults and adolescents (12 years and older) initial 600 mg (two 300 mg injections) || adults initial 600 mg (two 300 mg injections) || pediatric patients 15 to <30 kg 600 mg (two 300 mg injections) || pediatric patients 30 to <60 kg 400 mg (two 200 mg injections) || pediatric patients 60 kg or more 600 mg (two 300 mg injections)' THEN 600 ELSE NULL END AS mg, prescription_status FROM drug) WHERE mg IS NOT NULL GROUP BY dose_range;
```
</details>

**G5b.** For prescription-only drugs and the others, how many drug labels state a single dose, and how many of them give a dose per kilogram of body weight?

```sql
SELECT CASE WHEN prescription_status = 'prescription_only' THEN 'prescription only' ELSE 'other' END AS status, COUNT(*) AS drugs, SUM(CASE WHEN single_dose LIKE '%/kg%' THEN 1 ELSE 0 END) AS per_kg FROM drug WHERE single_dose <> '' GROUP BY status;
```
<sub>Blind judges: LIKE '%/kg%' needs the unit text. Form 1 stores bare numbers or NULL, so no row could ever match, and the per-kg doses are NULL there anyway.</sub>

<details><summary>answer key</summary>

```sql
SELECT CASE WHEN prescription_status = 'prescription_only' THEN 'prescription only' ELSE 'other' END AS status, COUNT(*) AS drugs, SUM(CASE WHEN single_dose LIKE '%/kg%' THEN 1 ELSE 0 END) AS per_kg FROM drug WHERE single_dose <> '' GROUP BY status;
```
</details>

Stored forms (exact match; rows changed):

| Query | as stated (0) | stored as G5a needs (100) |
|---|---|---|
| G5a | 0.00 | 1.00 |
| G5b | 1.00 | 0.00 |

<details><summary>stored forms as SQL</summary>

```sql
-- G5a
UPDATE drug SET single_dose = CASE single_dose WHEN 'adults 25 milligrams' THEN 25 WHEN 'adults 400 mcg' THEN 0.4 WHEN 'adults 4 g piperacillin + 0.5 g tazobactam' THEN 4000 WHEN 'Esophageal-gastric varices bleeding 0.025 mg/hour intravenous infusion || Prevention of pancreatic complications 0.1 mg subcutaneous injection || Gastrointestinal pancreatic endocrine tumors 0.05 mg subcutaneous injection || Acromegaly 0.05~0.1 mg subcutaneous injection' THEN 0.1 WHEN 'adults 10-40 mg once a day||cardiovascular prevention 40 mg per day||post-transplant (immunosuppressive therapy) 20 mg per day (up to 40 mg)||renal or hepatic insufficiency 10 mg per day' THEN 40 WHEN 'adults 2 mg' THEN 2 WHEN 'adults 40 mg' THEN 40 WHEN 'adults 12.5 mg (Day 1)||adults 12.5 mg twice/d (for 2 days)||adults 25 mg twice/d (for 4 days)||adults 50 mg twice/d (for 7 days)||adults 100 mg twice/d (for 7 days)' THEN 100 WHEN 'adults 20 mg' THEN 20 WHEN 'adults 500 mg||children 12 mg per 2' THEN 500 WHEN 'adults 500mcg||adults 250mcg' THEN 0.5 WHEN 'adults 20 mg||pediatric patients 0.5 mg/kg/dose or 1 mg/kg/dose' THEN 20 WHEN 'adults 1 mg norethindrone acetate and 10 mcg ethinyl estradiol per tablet' THEN 1 WHEN 'adults 500 mg' THEN 500 WHEN 'adults 12.5 mg (Day 1)||adults 12.5 mg twice daily (for 2 days)||adults 25 mg twice daily (for 4 days)||adults 50 mg twice daily (for 7 days)||adults 100 mg twice daily (for 7 days)' THEN 100 WHEN 'adults 25 mg || elderly 30-50 mg || adolescents 30-50 mg' THEN 25 WHEN 'children and adolescents up to 54mg daily||adults up to 72mg daily' THEN 72 WHEN 'adults 250 mg || adults 500 mg || adults 750 mg || adults 1000 mg' THEN 1000 WHEN 'adults 600 mg' THEN 600 WHEN 'adults 1-2 tablets 500mg||adults 1 tablet 750mg||children 1 drop/kg (not exceeding 35 drops)||children see weight-based mL dosing' THEN 1000 WHEN 'adults 1 mg || adults 2 mg' THEN 2 WHEN '15 mg' THEN 15 WHEN 'adults 25-50 mg' THEN 50 WHEN 'adults sinusitis 500 mg||adults acute exacerbation of chronic bronchitis 250-500 mg||adults skin and soft tissue infections 250-500 mg||adults creatinine clearance 250 mg/24h||adults creatinine clearance 500 mg/24h||adults creatinine clearance 500 mg/12h||adults 50-20 mL/min 125-500 mg/24h||adults 19-10 mL/min 125-500 mg/24h||adults 10 mL/min 125-250 mg/24-48h' THEN 500 WHEN 'adults 5 mg||adults 10 mg||children over 6 years 2.5 mg||children over 6 years 5 mg' THEN 10 WHEN '125 to 250 mg || 250 to 500 mg' THEN 500 WHEN 'adults 400 mg' THEN 400 WHEN 'adults 10 mg || adults 25 mg' THEN 25 WHEN 'adults 30 mg 1-2 tablets || adults 60 mg 1 tablet' THEN 60 WHEN 'adults 160 mg' THEN 160 WHEN 'adults 300 mg' THEN 300 WHEN 'newborns 0.5 mg/kg/dose || pediatric patients <30 kg 1 mg/kg/dose || pediatric patients ≥30 kg adult dosage || adults ≥60 kg 20 mg || adults <60 kg 15 mg' THEN 20 WHEN 'adults and children 12 years old and older weighing 40 kg or more 1 tablet of 500 mg + 125 mg' THEN 500 WHEN 'adults 1 mg' THEN 1 WHEN 'adults and children over 12 years 200 mg each 8 hours up to 400 mg each 8-12 hours || children 6-12 years 200 mg each 8-12 hours up to 400 mg each 12 hours || adults and children over 12 years (prevention) 400 mg each 12 hours || children 6-12 years (prevention) 200-400 mg each 12 hours || adults and children over 12 years (hyperammonemia) 400 mg each 8 hours || children 6-12 years (hyperammonemia) 200-300 mg each 8 hours' THEN 400 WHEN 'most patients 5 mg || patients with severe renal impairment 2.5 mg || patients with moderate hepatic impairment 2.5 mg' THEN 5 WHEN 'adults 5 mg || adults 10 mg || adults 20 mg' THEN 20 WHEN 'adults 100 mg' THEN 100 WHEN 'adults 250-500mg||children 15mg/kg daily' THEN 500 WHEN '250 mg capsule||500 mg tablet||500 mg intravenous' THEN 500 WHEN 'oral 400mg||oral 800mg' THEN 800 WHEN 'adults 25 mg (oral capsule)||adults 1 mg (intravenous)||adults 10-20 mg (oral, equivalent to 1 mg IV)' THEN 25 WHEN 'patients with severe asthma aged 12 years and older 100 mg || adult patients with EGPA 3x100 mg' THEN 300 WHEN 'adults and adolescents (12 years and older) initial 400 mg (two 200 mg injections) || adults and adolescents (12 years and older) initial 600 mg (two 300 mg injections) || adults initial 600 mg (two 300 mg injections) || pediatric patients 15 to <30 kg 600 mg (two 300 mg injections) || pediatric patients 30 to <60 kg 400 mg (two 200 mg injections) || pediatric patients 60 kg or more 600 mg (two 300 mg injections)' THEN 600 ELSE NULL END;
```
</details>

### Med G6: `drug.unsuitable_population` (fine vs coarse)

drug.unsuitable_population states each group to avoid the drug as the label words it ('nursing mothers', 'geriatric patients', 'renal insufficiency', 'patients with glaucoma'); G6a needs standard population groups, G6b the stated conditions

**G6a.** For prescription-only drugs and the others, how many labels name groups who should avoid the drug, and how many of them warn against use in pregnancy, while breastfeeding, in children, in the elderly, and in patients with kidney or with liver problems?

```sql
SELECT CASE WHEN prescription_status = 'prescription_only' THEN 'prescription only' ELSE 'other' END AS status, COUNT(*) AS drugs, SUM(CASE WHEN unsuitable_population LIKE '%pregnan%' THEN 1 ELSE 0 END) AS pregnancy, SUM(CASE WHEN unsuitable_population LIKE '%breastfeed%' THEN 1 ELSE 0 END) AS breastfeeding, SUM(CASE WHEN unsuitable_population LIKE '%children%' THEN 1 ELSE 0 END) AS children, SUM(CASE WHEN unsuitable_population LIKE '%elderly%' THEN 1 ELSE 0 END) AS elderly, SUM(CASE WHEN unsuitable_population LIKE '%kidney%' THEN 1 ELSE 0 END) AS kidney_problems, SUM(CASE WHEN unsuitable_population LIKE '%liver%' THEN 1 ELSE 0 END) AS liver_problems FROM drug WHERE unsuitable_population <> '' GROUP BY status;
```
<sub>Blind judges: The filters (pregnan, breastfeed, children, elderly, kidney, liver) match Form 1's normalized categories. The stated text misses 'breast feeding', 'nursing wome</sub>

<details><summary>answer key</summary>

```sql
SELECT CASE WHEN prescription_status = 'prescription_only' THEN 'prescription only' ELSE 'other' END AS status, COUNT(*) AS drugs, SUM(CASE WHEN unsuitable_population LIKE '%pregnan%' THEN 1 ELSE 0 END) AS pregnancy, SUM(CASE WHEN unsuitable_population LIKE '%breastfeed%' THEN 1 ELSE 0 END) AS breastfeeding, SUM(CASE WHEN unsuitable_population LIKE '%children%' THEN 1 ELSE 0 END) AS children, SUM(CASE WHEN unsuitable_population LIKE '%elderly%' THEN 1 ELSE 0 END) AS elderly, SUM(CASE WHEN unsuitable_population LIKE '%kidney%' THEN 1 ELSE 0 END) AS kidney_problems, SUM(CASE WHEN unsuitable_population LIKE '%liver%' THEN 1 ELSE 0 END) AS liver_problems FROM (SELECT prescription_status, CASE unsuitable_population WHEN 'children under 18||pregnant women||breastfeeding women||patients with active liver disease||patients with persistent elevated transaminases||patients with hereditary problems of galactose intolerance, Lapp lactase deficiency, or glucose-galactose malabsorption' THEN 'pregnancy||breastfeeding||children||liver problems||other conditions' WHEN 'patients using antidepressants' THEN 'other conditions' WHEN 'pregnant women' THEN 'pregnancy' WHEN 'patients with cyst on the ovary||patients with fibroid tumor of the uterus||patients with inflamed veins due to blood clots||patients with endometriosis||patients with liver disease||patients with depression||patients with unusual vaginal bleeding||pregnant women' THEN 'pregnancy||liver problems||other conditions' WHEN 'patients with severe psychiatric illness' THEN 'other conditions' WHEN 'children under 18 years of age' THEN 'children' WHEN 'children under 6 years||children under 12 years (for some products)||patients with breathing problems||patients with diabetes||patients with glaucoma||patients with heart problems||patients with high blood pressure||patients with kidney problems||patients with liver disease||patients with seizures||patients with stomach/intestinal problems||patients with overactive thyroid||patients with urination problems||elderly' THEN 'children||elderly||kidney problems||liver problems||other conditions' WHEN 'children younger than 1||pediatric patients with pneumonia who are judged to be inappropriate for oral therapy' THEN 'children||other conditions' WHEN 'individuals with cardiovascular diseases' THEN 'other conditions' WHEN 'pregnant women (unless clearly needed)||breastfeeding women' THEN 'pregnancy||breastfeeding' WHEN 'patients with moderate or severe renal insufficiency' THEN 'kidney problems' WHEN 'children' THEN 'children' WHEN 'people with moderate to severe kidney disease||people with AST or ALT values of 2.5 to 10 times the upper limit of normal||people with total bilirubin levels of 1.5 to 3 times the upper limit of normal||pregnant women||people allergic to Bendeka or polyethylene glycol 400, propylene glycol, or monothioglycerol' THEN 'pregnancy||kidney problems||liver problems||other conditions' WHEN 'women with current or past breast cancer||pregnant women||nursing infants' THEN 'pregnancy||breastfeeding||other conditions' WHEN 'diabetes mellitus at the time of transplant||history of antidiabetic therapy||unable to consent||steroid pulse therapy in the 2 weeks prior to OGTT||pregnancy||breast feeding||estimated glomerular filtration rate (eGFR) ≤30 mL/min/1.73 m2||current substance abuse (including alcohol)||any major illness or comorbidity that may result in death within 12 months' THEN 'pregnancy||breastfeeding||kidney problems||other conditions' WHEN 'pediatric patients||patients with cognitive impairment or mental disabilities||patients with neuromuscular diseases such as Parkinson''s disease or multiple sclerosis' THEN 'children||other conditions' WHEN 'children under 6 years||children under 12 years (for some forms)||patients with breathing problems||patients with diabetes||patients with glaucoma||patients with heart problems||patients with high blood pressure||patients with kidney problems||patients with liver disease||patients with seizures||patients with stomach/intestinal problems||patients with overactive thyroid||patients with urination problems||elderly||pregnant women||nursing women' THEN 'pregnancy||breastfeeding||children||elderly||kidney problems||liver problems||other conditions' WHEN 'tetracycline allergy||pregnant women||nursing women' THEN 'pregnancy||breastfeeding||other conditions' WHEN 'allergy to Pamelor or similar medicines||currently taking or recently taken MAO inhibitors||recent heart attack' THEN 'other conditions' WHEN 'children under 6||patients with allergy or hypersensitivity to methylphenidate HCI||patients with anxiety||patients with glaucoma||patients with tics or history of Tourette’s syndrome||patients taking monoamine oxidase inhibitors (MAOIs)||patients with heart or mental problems||patients with seizures||patients with abnormal brain wave tests||patients with circulation problems||patients with esophagus, stomach or intestine problems||pregnant women||nursing mothers' THEN 'pregnancy||breastfeeding||children||other conditions' WHEN 'pregnant or breastfeeding women' THEN 'pregnancy||breastfeeding' WHEN 'patients with kidney disease||patients with liver disease||older adults' THEN 'elderly||kidney problems||liver problems' WHEN 'Allergy to Lopid||Gallbladder disease||Liver disease||Taking Repaglinide||Pregnant women||Nursing women' THEN 'pregnancy||breastfeeding||liver problems||other conditions' WHEN 'people with liver complications||people with kidney problems||pregnant women (except with medical recommendation)||children under 12 (without medical advice)||people allergic to any components' THEN 'pregnancy||children||kidney problems||liver problems||other conditions' WHEN 'allergic to Tolterodine or Fesoterodine fumarate||untreated or uncontrolled narrow-angle glaucoma||blockage of the urinary tract||blockage of the stomach||blockage of the intestines' THEN 'other conditions' WHEN 'pediatric patients||pregnant women||breastfeeding women||patients receiving strong CYP3A inhibitors' THEN 'pregnancy||breastfeeding||children||other conditions' WHEN 'patients who are hypersensitive to animal—specifically avian-based—proteins' THEN 'other conditions' WHEN 'Patients with liver or kidney problem' THEN 'kidney problems||liver problems' WHEN 'children under 6 years||children under 12 years||patients with glaucoma||patients with bronchitis||patients with emphysema||patients with high blood pressure||patients with kidney disease||asthmatics||pregnant women||breastfeeding mothers' THEN 'pregnancy||breastfeeding||children||kidney problems||other conditions' WHEN 'children||adolescents||pregnant women||breast-feeding women||patients with epilepsy||patients with history of tendon problems with quinolones||patients with glucose-6-phosphate dehydrogenase deficiency||patients with kidney disease' THEN 'pregnancy||breastfeeding||children||kidney problems||other conditions' WHEN 'children taking ibuprofen or ASA||children allergic to ibuprofen, ASA, salicylates, NSAIDs, or any inactive ingredients||children right before or after heart surgery' THEN 'other conditions' WHEN 'patients with asthma||patients allergic to aclidinium bromide||patients allergic to formoterol fumarate||patients allergic to any of the other ingredients' THEN 'other conditions' WHEN 'children under 6 years||breastfeeding women' THEN 'breastfeeding||children' WHEN 'individuals with histories of significant allergies and/or asthma' THEN 'other conditions' WHEN 'patients with cataracts||patients with kidney disease||patients with diabetic retinopathy||patients with optic neuritis||pregnant women||nursing women' THEN 'pregnancy||breastfeeding||kidney problems||other conditions' WHEN 'patients with creatinine clearance <50 mL/min||patients with significant or unstable cardiac disease||patients with autoimmune disorders||patients with preexisting ophthalmologic disorders||pregnant women||nursing mothers||pediatric patients below the age of 18 years' THEN 'pregnancy||breastfeeding||children||kidney problems||other conditions' WHEN 'pregnant women||nursing mothers' THEN 'pregnancy||breastfeeding' WHEN 'pregnant dogs||nursing dogs||dogs with diabetes||dogs taking Novocox||dogs taking Metacam||dogs taking Rimadyl||dogs taking NSAIDs' THEN 'pregnancy||breastfeeding||other conditions' WHEN 'pregnant women||elderly people||patients with nephropathy||patients with neuropathy||patients with cardiovascular disorders' THEN 'pregnancy||elderly||kidney problems||other conditions' WHEN 'patients with pancreatitis||patients with hepatic decompensation||patients with severe peripheral neuropathy||pregnant women (with caution)||patients with history of lactic acidosis' THEN 'pregnancy||liver problems||other conditions' WHEN 'children under 2 years old||pregnant women' THEN 'pregnancy||children' WHEN 'hypersensitivity to beta-lactamics||moderate or serious renal alteration||hepatic alteration||granulocytopenia less than 1,000/mm3||thrombocytopenia less than 50,000/mm3' THEN 'kidney problems||liver problems||other conditions' WHEN 'children under 12 years||pregnant women||nursing women||patients with persistent/chronic cough||patients with shortness of breath||patients with chronic lung disease||patients taking MAOI||patients taking SSRI||patients taking medications for depression, psychiatric, or emotional conditions, or Parkinson''s disease' THEN 'pregnancy||breastfeeding||children||other conditions' WHEN 'nursing mothers||infants' THEN 'breastfeeding||children' WHEN 'people allergic to azelaic acid or any other ingredient listed in the gel' THEN 'other conditions' WHEN 'pediatric patients||geriatric patients||pregnant women||nursing mothers||patients with allergy to aminoglycoside antibiotics||patients with breathing problems||patients with kidney problems||patients with myasthenia gravis||patients with Parkinson''s disease||patients with hearing or balance problems' THEN 'pregnancy||breastfeeding||children||elderly||kidney problems||other conditions' WHEN 'patients hypersensitive to glimepiride||patients hypersensitive to other sulfonylureas||patients hypersensitive to other sulfonamides||patients with type I diabetes mellitus||patients with diabetic ketoacidosis||patients with diabetic precoma or coma||pregnant women||nursing women' THEN 'pregnancy||breastfeeding||other conditions' WHEN 'individuals with hypersensitivity to any component of the drug or other rifamycin antibiotics||patients with intestinal obstruction||patients with ulcerative colitis' THEN 'other conditions' WHEN 'Pregnant females||Young puppies||Pets with unspecified conditions' THEN 'pregnancy||other conditions' WHEN 'pregnant women || women planning to become pregnant || breastfeeding women || patients with severe liver disease || patients with severe kidney disease || patients with high triglycerides || patients allergic to retinoids' THEN 'pregnancy||breastfeeding||kidney problems||liver problems||other conditions' WHEN 'patients with severe bradycardia||heart block greater than first degree||patients with cardiogenic shock||decompensated cardiac failure||sick sinus syndrome (unless a permanent pacemaker is in place)||patients with severe hepatic impairment (Child-Pugh greater than B)||hypersensitive to any component of this product||children under 18' THEN 'children||liver problems||other conditions' WHEN 'pregnant women||breastfeeding women||children' THEN 'pregnancy||breastfeeding||children' WHEN 'Women using oral contraceptives' THEN 'other conditions' WHEN 'patients taking nitrate containing medicines for cardiac insufficiency||patients with heart failure II stage||angina||complex forms of arrhythmias||resistant hypertension||states associated with a drop in blood pressure' THEN 'other conditions' WHEN 'men||postmenopausal women||children||patients with hepatic impairment||patients using alcohol||patients using moderate or strong CYP3A4 inhibitors||patients with hypersensitivity to Flibanserin or any inactive ingredient' THEN 'children||liver problems||other conditions' WHEN 'Allergic to Valium or other benzodiazepines||Pregnant women||Nursing mothers||Older adults' THEN 'pregnancy||breastfeeding||elderly||other conditions' WHEN 'people with individual intolerance of the active or additional elements of the drug||children younger than two months (ointment)||children under one year (cream)||people of old age (cautiously)||people with severe kidney dysfunction (cautiously)' THEN 'children||elderly||kidney problems||other conditions' WHEN 'patients allergic to Clarithromycin or other macrolide antibiotics||patients using Ergotamine, Dihydroergotamine, or other ergot alkaloids||patients using Terfenadine or Astemizole||patients using Cisapride||patients using statins (Lovastatin, Atorvastatin, Simvastatin, Rosuvastatin, Fluvastatin)||patients with hypokalaemia||patients with impaired liver function||patients with kidney damage||patients with cardiac problems' THEN 'kidney problems||liver problems||other conditions' ELSE unsuitable_population END AS unsuitable_population FROM drug WHERE unsuitable_population <> '') GROUP BY status;
```
</details>

**G6b.** How many drug labels warn patients with glaucoma, with asthma or with diabetes, and how many warn patients taking MAO inhibitors?

```sql
SELECT SUM(CASE WHEN unsuitable_population LIKE '%glaucoma%' THEN 1 ELSE 0 END) AS glaucoma, SUM(CASE WHEN unsuitable_population LIKE '%asthma%' THEN 1 ELSE 0 END) AS asthma, SUM(CASE WHEN unsuitable_population LIKE '%diabet%' THEN 1 ELSE 0 END) AS diabetes, SUM(CASE WHEN unsuitable_population LIKE '%MAO%' THEN 1 ELSE 0 END) AS mao_inhibitors FROM drug;
```
<sub>Blind judges: The filters look for specific conditions (glaucoma, asthma, diabet, MAO). These appear only in the stated detailed text; Form 1 folds them into 'other condition</sub>

<details><summary>answer key</summary>

```sql
SELECT SUM(CASE WHEN unsuitable_population LIKE '%glaucoma%' THEN 1 ELSE 0 END) AS glaucoma, SUM(CASE WHEN unsuitable_population LIKE '%asthma%' THEN 1 ELSE 0 END) AS asthma, SUM(CASE WHEN unsuitable_population LIKE '%diabet%' THEN 1 ELSE 0 END) AS diabetes, SUM(CASE WHEN unsuitable_population LIKE '%MAO%' THEN 1 ELSE 0 END) AS mao_inhibitors FROM drug;
```
</details>

Stored forms (exact match; rows changed):

| Query | as stated (0) | stored as G6a needs (58) |
|---|---|---|
| G6a | 0.36 | 1.00 |
| G6b | 1.00 | 0.00 |

<details><summary>stored forms as SQL</summary>

```sql
-- G6a
UPDATE drug SET unsuitable_population = CASE unsuitable_population WHEN 'children under 18||pregnant women||breastfeeding women||patients with active liver disease||patients with persistent elevated transaminases||patients with hereditary problems of galactose intolerance, Lapp lactase deficiency, or glucose-galactose malabsorption' THEN 'pregnancy||breastfeeding||children||liver problems||other conditions' WHEN 'patients using antidepressants' THEN 'other conditions' WHEN 'pregnant women' THEN 'pregnancy' WHEN 'patients with cyst on the ovary||patients with fibroid tumor of the uterus||patients with inflamed veins due to blood clots||patients with endometriosis||patients with liver disease||patients with depression||patients with unusual vaginal bleeding||pregnant women' THEN 'pregnancy||liver problems||other conditions' WHEN 'patients with severe psychiatric illness' THEN 'other conditions' WHEN 'children under 18 years of age' THEN 'children' WHEN 'children under 6 years||children under 12 years (for some products)||patients with breathing problems||patients with diabetes||patients with glaucoma||patients with heart problems||patients with high blood pressure||patients with kidney problems||patients with liver disease||patients with seizures||patients with stomach/intestinal problems||patients with overactive thyroid||patients with urination problems||elderly' THEN 'children||elderly||kidney problems||liver problems||other conditions' WHEN 'children younger than 1||pediatric patients with pneumonia who are judged to be inappropriate for oral therapy' THEN 'children||other conditions' WHEN 'individuals with cardiovascular diseases' THEN 'other conditions' WHEN 'pregnant women (unless clearly needed)||breastfeeding women' THEN 'pregnancy||breastfeeding' WHEN 'patients with moderate or severe renal insufficiency' THEN 'kidney problems' WHEN 'children' THEN 'children' WHEN 'people with moderate to severe kidney disease||people with AST or ALT values of 2.5 to 10 times the upper limit of normal||people with total bilirubin levels of 1.5 to 3 times the upper limit of normal||pregnant women||people allergic to Bendeka or polyethylene glycol 400, propylene glycol, or monothioglycerol' THEN 'pregnancy||kidney problems||liver problems||other conditions' WHEN 'women with current or past breast cancer||pregnant women||nursing infants' THEN 'pregnancy||breastfeeding||other conditions' WHEN 'diabetes mellitus at the time of transplant||history of antidiabetic therapy||unable to consent||steroid pulse therapy in the 2 weeks prior to OGTT||pregnancy||breast feeding||estimated glomerular filtration rate (eGFR) ≤30 mL/min/1.73 m2||current substance abuse (including alcohol)||any major illness or comorbidity that may result in death within 12 months' THEN 'pregnancy||breastfeeding||kidney problems||other conditions' WHEN 'pediatric patients||patients with cognitive impairment or mental disabilities||patients with neuromuscular diseases such as Parkinson''s disease or multiple sclerosis' THEN 'children||other conditions' WHEN 'children under 6 years||children under 12 years (for some forms)||patients with breathing problems||patients with diabetes||patients with glaucoma||patients with heart problems||patients with high blood pressure||patients with kidney problems||patients with liver disease||patients with seizures||patients with stomach/intestinal problems||patients with overactive thyroid||patients with urination problems||elderly||pregnant women||nursing women' THEN 'pregnancy||breastfeeding||children||elderly||kidney problems||liver problems||other conditions' WHEN 'tetracycline allergy||pregnant women||nursing women' THEN 'pregnancy||breastfeeding||other conditions' WHEN 'allergy to Pamelor or similar medicines||currently taking or recently taken MAO inhibitors||recent heart attack' THEN 'other conditions' WHEN 'children under 6||patients with allergy or hypersensitivity to methylphenidate HCI||patients with anxiety||patients with glaucoma||patients with tics or history of Tourette’s syndrome||patients taking monoamine oxidase inhibitors (MAOIs)||patients with heart or mental problems||patients with seizures||patients with abnormal brain wave tests||patients with circulation problems||patients with esophagus, stomach or intestine problems||pregnant women||nursing mothers' THEN 'pregnancy||breastfeeding||children||other conditions' WHEN 'pregnant or breastfeeding women' THEN 'pregnancy||breastfeeding' WHEN 'patients with kidney disease||patients with liver disease||older adults' THEN 'elderly||kidney problems||liver problems' WHEN 'Allergy to Lopid||Gallbladder disease||Liver disease||Taking Repaglinide||Pregnant women||Nursing women' THEN 'pregnancy||breastfeeding||liver problems||other conditions' WHEN 'people with liver complications||people with kidney problems||pregnant women (except with medical recommendation)||children under 12 (without medical advice)||people allergic to any components' THEN 'pregnancy||children||kidney problems||liver problems||other conditions' WHEN 'allergic to Tolterodine or Fesoterodine fumarate||untreated or uncontrolled narrow-angle glaucoma||blockage of the urinary tract||blockage of the stomach||blockage of the intestines' THEN 'other conditions' WHEN 'pediatric patients||pregnant women||breastfeeding women||patients receiving strong CYP3A inhibitors' THEN 'pregnancy||breastfeeding||children||other conditions' WHEN 'patients who are hypersensitive to animal—specifically avian-based—proteins' THEN 'other conditions' WHEN 'Patients with liver or kidney problem' THEN 'kidney problems||liver problems' WHEN 'children under 6 years||children under 12 years||patients with glaucoma||patients with bronchitis||patients with emphysema||patients with high blood pressure||patients with kidney disease||asthmatics||pregnant women||breastfeeding mothers' THEN 'pregnancy||breastfeeding||children||kidney problems||other conditions' WHEN 'children||adolescents||pregnant women||breast-feeding women||patients with epilepsy||patients with history of tendon problems with quinolones||patients with glucose-6-phosphate dehydrogenase deficiency||patients with kidney disease' THEN 'pregnancy||breastfeeding||children||kidney problems||other conditions' WHEN 'children taking ibuprofen or ASA||children allergic to ibuprofen, ASA, salicylates, NSAIDs, or any inactive ingredients||children right before or after heart surgery' THEN 'other conditions' WHEN 'patients with asthma||patients allergic to aclidinium bromide||patients allergic to formoterol fumarate||patients allergic to any of the other ingredients' THEN 'other conditions' WHEN 'children under 6 years||breastfeeding women' THEN 'breastfeeding||children' WHEN 'individuals with histories of significant allergies and/or asthma' THEN 'other conditions' WHEN 'patients with cataracts||patients with kidney disease||patients with diabetic retinopathy||patients with optic neuritis||pregnant women||nursing women' THEN 'pregnancy||breastfeeding||kidney problems||other conditions' WHEN 'patients with creatinine clearance <50 mL/min||patients with significant or unstable cardiac disease||patients with autoimmune disorders||patients with preexisting ophthalmologic disorders||pregnant women||nursing mothers||pediatric patients below the age of 18 years' THEN 'pregnancy||breastfeeding||children||kidney problems||other conditions' WHEN 'pregnant women||nursing mothers' THEN 'pregnancy||breastfeeding' WHEN 'pregnant dogs||nursing dogs||dogs with diabetes||dogs taking Novocox||dogs taking Metacam||dogs taking Rimadyl||dogs taking NSAIDs' THEN 'pregnancy||breastfeeding||other conditions' WHEN 'pregnant women||elderly people||patients with nephropathy||patients with neuropathy||patients with cardiovascular disorders' THEN 'pregnancy||elderly||kidney problems||other conditions' WHEN 'patients with pancreatitis||patients with hepatic decompensation||patients with severe peripheral neuropathy||pregnant women (with caution)||patients with history of lactic acidosis' THEN 'pregnancy||liver problems||other conditions' WHEN 'children under 2 years old||pregnant women' THEN 'pregnancy||children' WHEN 'hypersensitivity to beta-lactamics||moderate or serious renal alteration||hepatic alteration||granulocytopenia less than 1,000/mm3||thrombocytopenia less than 50,000/mm3' THEN 'kidney problems||liver problems||other conditions' WHEN 'children under 12 years||pregnant women||nursing women||patients with persistent/chronic cough||patients with shortness of breath||patients with chronic lung disease||patients taking MAOI||patients taking SSRI||patients taking medications for depression, psychiatric, or emotional conditions, or Parkinson''s disease' THEN 'pregnancy||breastfeeding||children||other conditions' WHEN 'nursing mothers||infants' THEN 'breastfeeding||children' WHEN 'people allergic to azelaic acid or any other ingredient listed in the gel' THEN 'other conditions' WHEN 'pediatric patients||geriatric patients||pregnant women||nursing mothers||patients with allergy to aminoglycoside antibiotics||patients with breathing problems||patients with kidney problems||patients with myasthenia gravis||patients with Parkinson''s disease||patients with hearing or balance problems' THEN 'pregnancy||breastfeeding||children||elderly||kidney problems||other conditions' WHEN 'patients hypersensitive to glimepiride||patients hypersensitive to other sulfonylureas||patients hypersensitive to other sulfonamides||patients with type I diabetes mellitus||patients with diabetic ketoacidosis||patients with diabetic precoma or coma||pregnant women||nursing women' THEN 'pregnancy||breastfeeding||other conditions' WHEN 'individuals with hypersensitivity to any component of the drug or other rifamycin antibiotics||patients with intestinal obstruction||patients with ulcerative colitis' THEN 'other conditions' WHEN 'Pregnant females||Young puppies||Pets with unspecified conditions' THEN 'pregnancy||other conditions' WHEN 'pregnant women || women planning to become pregnant || breastfeeding women || patients with severe liver disease || patients with severe kidney disease || patients with high triglycerides || patients allergic to retinoids' THEN 'pregnancy||breastfeeding||kidney problems||liver problems||other conditions' WHEN 'patients with severe bradycardia||heart block greater than first degree||patients with cardiogenic shock||decompensated cardiac failure||sick sinus syndrome (unless a permanent pacemaker is in place)||patients with severe hepatic impairment (Child-Pugh greater than B)||hypersensitive to any component of this product||children under 18' THEN 'children||liver problems||other conditions' WHEN 'pregnant women||breastfeeding women||children' THEN 'pregnancy||breastfeeding||children' WHEN 'Women using oral contraceptives' THEN 'other conditions' WHEN 'patients taking nitrate containing medicines for cardiac insufficiency||patients with heart failure II stage||angina||complex forms of arrhythmias||resistant hypertension||states associated with a drop in blood pressure' THEN 'other conditions' WHEN 'men||postmenopausal women||children||patients with hepatic impairment||patients using alcohol||patients using moderate or strong CYP3A4 inhibitors||patients with hypersensitivity to Flibanserin or any inactive ingredient' THEN 'children||liver problems||other conditions' WHEN 'Allergic to Valium or other benzodiazepines||Pregnant women||Nursing mothers||Older adults' THEN 'pregnancy||breastfeeding||elderly||other conditions' WHEN 'people with individual intolerance of the active or additional elements of the drug||children younger than two months (ointment)||children under one year (cream)||people of old age (cautiously)||people with severe kidney dysfunction (cautiously)' THEN 'children||elderly||kidney problems||other conditions' WHEN 'patients allergic to Clarithromycin or other macrolide antibiotics||patients using Ergotamine, Dihydroergotamine, or other ergot alkaloids||patients using Terfenadine or Astemizole||patients using Cisapride||patients using statins (Lovastatin, Atorvastatin, Simvastatin, Rosuvastatin, Fluvastatin)||patients with hypokalaemia||patients with impaired liver function||patients with kidney damage||patients with cardiac problems' THEN 'kidney problems||liver problems||other conditions' ELSE unsuitable_population END;
```
</details>

### Med G7: `disease.affected_organs` (fine vs coarse)

disease.affected_organs states organs and tissues as the source names them (brain, lungs, kidneys, ...); G7a needs the body systems they belong to, G7b the stated organs

**G7a.** For chronic and other diseases whose affected organs are known, how many affect the nervous system, the respiratory system, the cardiovascular system, the musculoskeletal system and the urinary system?

```sql
SELECT CASE WHEN prognosis LIKE '%chronic%' THEN 'chronic' ELSE 'other' END AS course, COUNT(*) AS diseases, SUM(CASE WHEN affected_organs LIKE '%nervous system%' THEN 1 ELSE 0 END) AS nervous_system, SUM(CASE WHEN affected_organs LIKE '%respiratory system%' THEN 1 ELSE 0 END) AS respiratory_system, SUM(CASE WHEN affected_organs LIKE '%cardiovascular system%' THEN 1 ELSE 0 END) AS cardiovascular_system, SUM(CASE WHEN affected_organs LIKE '%musculoskeletal system%' THEN 1 ELSE 0 END) AS musculoskeletal_system, SUM(CASE WHEN affected_organs LIKE '%urinary system%' THEN 1 ELSE 0 END) AS urinary_system FROM disease WHERE affected_organs <> '' GROUP BY course;
```
<sub>Blind judges: The query looks for body-system labels ('nervous system', 'respiratory system', 'urinary system', ...). Form 1 normalizes organs into exactly these systems; the</sub>

<details><summary>answer key</summary>

```sql
SELECT CASE WHEN prognosis LIKE '%chronic%' THEN 'chronic' ELSE 'other' END AS course, COUNT(*) AS diseases, SUM(CASE WHEN affected_organs LIKE '%nervous system%' THEN 1 ELSE 0 END) AS nervous_system, SUM(CASE WHEN affected_organs LIKE '%respiratory system%' THEN 1 ELSE 0 END) AS respiratory_system, SUM(CASE WHEN affected_organs LIKE '%cardiovascular system%' THEN 1 ELSE 0 END) AS cardiovascular_system, SUM(CASE WHEN affected_organs LIKE '%musculoskeletal system%' THEN 1 ELSE 0 END) AS musculoskeletal_system, SUM(CASE WHEN affected_organs LIKE '%urinary system%' THEN 1 ELSE 0 END) AS urinary_system FROM (SELECT prognosis, CASE affected_organs WHEN 'cervix||womb||fallopian tubes||ovaries||reproductive organs||eyes (in babies)||lungs (in babies)' THEN 'respiratory system||reproductive system||eyes and ears' WHEN 'gastrointestinal system||abdomen' THEN 'digestive system||other body parts' WHEN 'lungs||pleura||chest' THEN 'respiratory system||other body parts' WHEN 'gastrointestinal tract||rectosigmoid colon' THEN 'digestive system' WHEN 'large_blood_vessels||kidneys||eyes||nerves||pancreas' THEN 'nervous system||cardiovascular system||digestive system||urinary system||eyes and ears' WHEN 'fingers||toes||skin||arms||legs||palms||soles' THEN 'skin||other body parts' WHEN 'joints||big toe||elbow||ankle||wrist' THEN 'musculoskeletal system' WHEN 'lungs||blood vessels||nerves||bones||liver||brain' THEN 'nervous system||respiratory system||cardiovascular system||digestive system||musculoskeletal system' WHEN 'plasma cells||bone marrow||bone' THEN 'musculoskeletal system||blood and immune system' WHEN 'limbs||nervous system' THEN 'nervous system||other body parts' WHEN 'bowels||gastrointestinal tract' THEN 'digestive system' WHEN 'skin||blood vessels||brain||cerebral white matter' THEN 'nervous system||cardiovascular system||skin' WHEN 'abdomen||liver||lung||digestive tract||skin' THEN 'respiratory system||digestive system||skin||other body parts' WHEN 'skin' THEN 'skin' WHEN 'facial skin||genital area' THEN 'skin||reproductive system' WHEN 'respiratory system' THEN 'respiratory system' WHEN 'lungs' THEN 'respiratory system' WHEN 'lungs||pancreas' THEN 'respiratory system||digestive system' WHEN 'gastrointestinal tract||intestine' THEN 'digestive system' WHEN 'joints||gums' THEN 'digestive system||musculoskeletal system' WHEN 'central nervous system' THEN 'nervous system' WHEN 'red blood cells||bone marrow||critical organs' THEN 'blood and immune system||other body parts' WHEN 'heart||arteries||legs||lungs' THEN 'respiratory system||cardiovascular system||other body parts' WHEN 'urinary tract' THEN 'urinary system' WHEN 'prostate||kidney||bladder||liver||bone||lung||lymph_nodes' THEN 'respiratory system||digestive system||musculoskeletal system||urinary system||reproductive system||blood and immune system' WHEN 'esophagus' THEN 'digestive system' WHEN 'nerves||veins||shoulders||hands||arms' THEN 'nervous system||cardiovascular system||other body parts' WHEN 'skin||eyes' THEN 'skin||eyes and ears' WHEN 'ears' THEN 'eyes and ears' WHEN 'muscles||heart' THEN 'cardiovascular system||musculoskeletal system' WHEN 'brain' THEN 'nervous system' WHEN 'appendix' THEN 'digestive system' WHEN 'pancreas||kidney||eye||skin||heart' THEN 'cardiovascular system||digestive system||urinary system||skin||eyes and ears' WHEN 'large intestine||small intestine||colon' THEN 'digestive system' WHEN 'lumbar_spine||muscles||ligaments||tendons||discs||bones||nerves' THEN 'nervous system||musculoskeletal system' WHEN 'gums||bone' THEN 'digestive system||musculoskeletal system' WHEN 'trigeminal nerve||face' THEN 'nervous system||other body parts' WHEN 'heart' THEN 'cardiovascular system' WHEN 'nervous system||joints||digestive system' THEN 'nervous system||digestive system||musculoskeletal system' WHEN 'optic nerve||eye||nervous system' THEN 'nervous system||eyes and ears' WHEN 'heart||nervous system||adrenal glands' THEN 'nervous system||cardiovascular system||endocrine system' WHEN 'lymph nodes||lungs||skin||central nervous system' THEN 'nervous system||respiratory system||skin||blood and immune system' WHEN 'heart||lungs||abdomen||chest cavity' THEN 'respiratory system||cardiovascular system||other body parts' WHEN 'stomach||nearby organs||lymph nodes' THEN 'digestive system||blood and immune system||other body parts' WHEN 'skin||dermis' THEN 'skin' WHEN 'intestinal wall' THEN 'digestive system' WHEN 'any organ||joints||small joints in hand||bones' THEN 'musculoskeletal system||other body parts' WHEN 'prostate gland||urinary tract' THEN 'urinary system||reproductive system' WHEN 'abdominal wall||intra-abdominal organs' THEN 'digestive system' WHEN 'heart||brain||arteries||vascular' THEN 'nervous system||cardiovascular system' WHEN 'brain||basal ganglia||cortex||striatum||caudate nuclei||pallidium' THEN 'nervous system' WHEN 'foot||ankle||bone||joints||ligaments||tendons' THEN 'musculoskeletal system||other body parts' WHEN 'gut' THEN 'digestive system' WHEN 'brain||nervous system' THEN 'nervous system' WHEN 'blood||lymph||subcutaneous tissues||central nervous system' THEN 'nervous system||skin||blood and immune system' WHEN 'peripheral nervous system' THEN 'nervous system' WHEN 'intestines||joints||back||mouth||eyes' THEN 'digestive system||musculoskeletal system||eyes and ears||other body parts' WHEN 'joints' THEN 'musculoskeletal system' WHEN 'breast' THEN 'reproductive system' WHEN 'medial temporal lobes||brain' THEN 'nervous system' WHEN 'sinuses||nervous system||trigeminal nerve||autonomic nervous system' THEN 'nervous system||respiratory system' WHEN 'arteries||legs||feet||toes||limbs||muscles||skin' THEN 'cardiovascular system||musculoskeletal system||skin||other body parts' WHEN 'retina||macula||eye' THEN 'eyes and ears' WHEN 'placenta||liver||kidney' THEN 'digestive system||urinary system||reproductive system' WHEN 'liver||nervous system||kidneys' THEN 'nervous system||digestive system||urinary system' WHEN 'joints||skin||cardiovascular system||blood vessels' THEN 'cardiovascular system||musculoskeletal system||skin' WHEN 'facial nerve' THEN 'nervous system' WHEN 'muscles' THEN 'musculoskeletal system' WHEN 'lungs||bone' THEN 'respiratory system||musculoskeletal system' WHEN 'peritoneum||abdomen' THEN 'digestive system||other body parts' WHEN 'heart||brain' THEN 'nervous system||cardiovascular system' WHEN 'liver' THEN 'digestive system' WHEN 'heart||blood vessels' THEN 'cardiovascular system' WHEN 'prostate||urethra' THEN 'urinary system||reproductive system' WHEN 'kidney' THEN 'urinary system' ELSE affected_organs END AS affected_organs FROM disease WHERE affected_organs <> '') GROUP BY course;
```
</details>

**G7b.** For chronic and other diseases whose affected organs are known, how many affect the brain, the heart, the lungs, the liver and the kidneys?

```sql
SELECT CASE WHEN prognosis LIKE '%chronic%' THEN 'chronic' ELSE 'other' END AS course, SUM(CASE WHEN affected_organs LIKE '%brain%' THEN 1 ELSE 0 END) AS brain, SUM(CASE WHEN affected_organs LIKE '%heart%' THEN 1 ELSE 0 END) AS heart, SUM(CASE WHEN affected_organs LIKE '%lung%' THEN 1 ELSE 0 END) AS lungs, SUM(CASE WHEN affected_organs LIKE '%liver%' THEN 1 ELSE 0 END) AS liver, SUM(CASE WHEN affected_organs LIKE '%kidney%' THEN 1 ELSE 0 END) AS kidneys FROM disease WHERE affected_organs <> '' GROUP BY course;
```
<sub>Blind judges: The filters look for organ names (brain, heart, lung, liver, kidney). These appear in the stated organ lists; Form 1 replaces organs with system labels, so thes</sub>

<details><summary>answer key</summary>

```sql
SELECT CASE WHEN prognosis LIKE '%chronic%' THEN 'chronic' ELSE 'other' END AS course, SUM(CASE WHEN affected_organs LIKE '%brain%' THEN 1 ELSE 0 END) AS brain, SUM(CASE WHEN affected_organs LIKE '%heart%' THEN 1 ELSE 0 END) AS heart, SUM(CASE WHEN affected_organs LIKE '%lung%' THEN 1 ELSE 0 END) AS lungs, SUM(CASE WHEN affected_organs LIKE '%liver%' THEN 1 ELSE 0 END) AS liver, SUM(CASE WHEN affected_organs LIKE '%kidney%' THEN 1 ELSE 0 END) AS kidneys FROM disease WHERE affected_organs <> '' GROUP BY course;
```
</details>

Stored forms (exact match; rows changed):

| Query | as stated (0) | stored as G7a needs (76) |
|---|---|---|
| G7a | 0.17 | 1.00 |
| G7b | 1.00 | 0.10 |

<details><summary>stored forms as SQL</summary>

```sql
-- G7a
UPDATE disease SET affected_organs = CASE affected_organs WHEN 'cervix||womb||fallopian tubes||ovaries||reproductive organs||eyes (in babies)||lungs (in babies)' THEN 'respiratory system||reproductive system||eyes and ears' WHEN 'gastrointestinal system||abdomen' THEN 'digestive system||other body parts' WHEN 'lungs||pleura||chest' THEN 'respiratory system||other body parts' WHEN 'gastrointestinal tract||rectosigmoid colon' THEN 'digestive system' WHEN 'large_blood_vessels||kidneys||eyes||nerves||pancreas' THEN 'nervous system||cardiovascular system||digestive system||urinary system||eyes and ears' WHEN 'fingers||toes||skin||arms||legs||palms||soles' THEN 'skin||other body parts' WHEN 'joints||big toe||elbow||ankle||wrist' THEN 'musculoskeletal system' WHEN 'lungs||blood vessels||nerves||bones||liver||brain' THEN 'nervous system||respiratory system||cardiovascular system||digestive system||musculoskeletal system' WHEN 'plasma cells||bone marrow||bone' THEN 'musculoskeletal system||blood and immune system' WHEN 'limbs||nervous system' THEN 'nervous system||other body parts' WHEN 'bowels||gastrointestinal tract' THEN 'digestive system' WHEN 'skin||blood vessels||brain||cerebral white matter' THEN 'nervous system||cardiovascular system||skin' WHEN 'abdomen||liver||lung||digestive tract||skin' THEN 'respiratory system||digestive system||skin||other body parts' WHEN 'skin' THEN 'skin' WHEN 'facial skin||genital area' THEN 'skin||reproductive system' WHEN 'respiratory system' THEN 'respiratory system' WHEN 'lungs' THEN 'respiratory system' WHEN 'lungs||pancreas' THEN 'respiratory system||digestive system' WHEN 'gastrointestinal tract||intestine' THEN 'digestive system' WHEN 'joints||gums' THEN 'digestive system||musculoskeletal system' WHEN 'central nervous system' THEN 'nervous system' WHEN 'red blood cells||bone marrow||critical organs' THEN 'blood and immune system||other body parts' WHEN 'heart||arteries||legs||lungs' THEN 'respiratory system||cardiovascular system||other body parts' WHEN 'urinary tract' THEN 'urinary system' WHEN 'prostate||kidney||bladder||liver||bone||lung||lymph_nodes' THEN 'respiratory system||digestive system||musculoskeletal system||urinary system||reproductive system||blood and immune system' WHEN 'esophagus' THEN 'digestive system' WHEN 'nerves||veins||shoulders||hands||arms' THEN 'nervous system||cardiovascular system||other body parts' WHEN 'skin||eyes' THEN 'skin||eyes and ears' WHEN 'ears' THEN 'eyes and ears' WHEN 'muscles||heart' THEN 'cardiovascular system||musculoskeletal system' WHEN 'brain' THEN 'nervous system' WHEN 'appendix' THEN 'digestive system' WHEN 'pancreas||kidney||eye||skin||heart' THEN 'cardiovascular system||digestive system||urinary system||skin||eyes and ears' WHEN 'large intestine||small intestine||colon' THEN 'digestive system' WHEN 'lumbar_spine||muscles||ligaments||tendons||discs||bones||nerves' THEN 'nervous system||musculoskeletal system' WHEN 'gums||bone' THEN 'digestive system||musculoskeletal system' WHEN 'trigeminal nerve||face' THEN 'nervous system||other body parts' WHEN 'heart' THEN 'cardiovascular system' WHEN 'nervous system||joints||digestive system' THEN 'nervous system||digestive system||musculoskeletal system' WHEN 'optic nerve||eye||nervous system' THEN 'nervous system||eyes and ears' WHEN 'heart||nervous system||adrenal glands' THEN 'nervous system||cardiovascular system||endocrine system' WHEN 'lymph nodes||lungs||skin||central nervous system' THEN 'nervous system||respiratory system||skin||blood and immune system' WHEN 'heart||lungs||abdomen||chest cavity' THEN 'respiratory system||cardiovascular system||other body parts' WHEN 'stomach||nearby organs||lymph nodes' THEN 'digestive system||blood and immune system||other body parts' WHEN 'skin||dermis' THEN 'skin' WHEN 'intestinal wall' THEN 'digestive system' WHEN 'any organ||joints||small joints in hand||bones' THEN 'musculoskeletal system||other body parts' WHEN 'prostate gland||urinary tract' THEN 'urinary system||reproductive system' WHEN 'abdominal wall||intra-abdominal organs' THEN 'digestive system' WHEN 'heart||brain||arteries||vascular' THEN 'nervous system||cardiovascular system' WHEN 'brain||basal ganglia||cortex||striatum||caudate nuclei||pallidium' THEN 'nervous system' WHEN 'foot||ankle||bone||joints||ligaments||tendons' THEN 'musculoskeletal system||other body parts' WHEN 'gut' THEN 'digestive system' WHEN 'brain||nervous system' THEN 'nervous system' WHEN 'blood||lymph||subcutaneous tissues||central nervous system' THEN 'nervous system||skin||blood and immune system' WHEN 'peripheral nervous system' THEN 'nervous system' WHEN 'intestines||joints||back||mouth||eyes' THEN 'digestive system||musculoskeletal system||eyes and ears||other body parts' WHEN 'joints' THEN 'musculoskeletal system' WHEN 'breast' THEN 'reproductive system' WHEN 'medial temporal lobes||brain' THEN 'nervous system' WHEN 'sinuses||nervous system||trigeminal nerve||autonomic nervous system' THEN 'nervous system||respiratory system' WHEN 'arteries||legs||feet||toes||limbs||muscles||skin' THEN 'cardiovascular system||musculoskeletal system||skin||other body parts' WHEN 'retina||macula||eye' THEN 'eyes and ears' WHEN 'placenta||liver||kidney' THEN 'digestive system||urinary system||reproductive system' WHEN 'liver||nervous system||kidneys' THEN 'nervous system||digestive system||urinary system' WHEN 'joints||skin||cardiovascular system||blood vessels' THEN 'cardiovascular system||musculoskeletal system||skin' WHEN 'facial nerve' THEN 'nervous system' WHEN 'muscles' THEN 'musculoskeletal system' WHEN 'lungs||bone' THEN 'respiratory system||musculoskeletal system' WHEN 'peritoneum||abdomen' THEN 'digestive system||other body parts' WHEN 'heart||brain' THEN 'nervous system||cardiovascular system' WHEN 'liver' THEN 'digestive system' WHEN 'heart||blood vessels' THEN 'cardiovascular system' WHEN 'prostate||urethra' THEN 'urinary system||reproductive system' WHEN 'kidney' THEN 'urinary system' ELSE affected_organs END;
```
</details>


## Players

### Players G3: `player.name` (join partner's spelling)

player.name holds the full name the article states (Wardell Stephen Curry II); a lookup of well-known players by the names fans use needs the common name (the article's title, Stephen Curry), a question about generational suffixes needs the full name with its Jr., Sr., II or III

**G3a.** Together, how many NBA titles, MVP awards and Olympic gold medals have LeBron James, Stephen Curry, Kevin Durant, Michael Jordan, Kobe Bryant, Shaquille O'Neal, Tim Duncan and Giannis Antetokounmpo won?

```sql
SELECT COUNT(*) AS players, SUM(nba_championships) AS nba_titles, SUM(mvp_awards) AS mvp_awards, SUM(olympic_gold_medals) AS olympic_golds FROM player WHERE name IN ('LeBron James', 'Stephen Curry', 'Kevin Durant', 'Michael Jordan', 'Kobe Bryant', 'Shaquille O''Neal', 'Tim Duncan', 'Giannis Antetokounmpo');
```
<sub>Blind judges: The query matches names by exact equality on common short forms ('Kevin Durant'), so the stored value must be the common name, not the full legal name ('Kevin W</sub>

<details><summary>answer key</summary>

```sql
SELECT COUNT(*) AS players, SUM(nba_championships) AS nba_titles, SUM(mvp_awards) AS mvp_awards, SUM(olympic_gold_medals) AS olympic_golds FROM player WHERE name IN ('LeBron Raymone James Sr.', 'Wardell Stephen Curry II', 'Kevin Wayne Durant', 'Michael Jeffrey Jordan', 'Kobe Bean Bryant', 'Shaquille Rashaun O''Neal', 'Tim Duncan', 'Giannis Sina Ugo Antetokounmpo');
```
</details>

**G3b.** Players whose full name carries a generational suffix (Jr., Sr., II or III) versus all others: how many players, how many NBA titles have they won, and how many MVP awards?

```sql
SELECT CASE WHEN name LIKE '% Jr.' OR name LIKE '% Sr.' OR name LIKE '% II' OR name LIKE '% III' THEN 'with suffix' ELSE 'without suffix' END AS name_suffix, COUNT(*) AS players, SUM(nba_championships) AS nba_titles, SUM(mvp_awards) AS mvp_awards FROM player GROUP BY name_suffix;
```
<sub>Blind judges: The query classifies names by suffix (LIKE '% Jr.', '% Sr.'), so the suffixes must be kept. Form 1 strips them (e.g., 'Anthony Marshon Davis Jr.' becomes 'Antho</sub>

<details><summary>answer key</summary>

```sql
SELECT CASE WHEN name LIKE '% Jr.' OR name LIKE '% Sr.' OR name LIKE '% II' OR name LIKE '% III' THEN 'with suffix' ELSE 'without suffix' END AS name_suffix, COUNT(*) AS players, SUM(nba_championships) AS nba_titles, SUM(mvp_awards) AS mvp_awards FROM player GROUP BY name_suffix;
```
</details>

Stored forms (exact match; rows changed):

| Query | as stated (0) | stored as G3a needs (81) |
|---|---|---|
| G3a | 0.00 | 1.00 |
| G3b | 1.00 | 0.00 |

<details><summary>stored forms as SQL</summary>

```sql
-- G3a
UPDATE player SET name = CASE name WHEN 'Jay Vincent Jay Fletcher Vincent' THEN 'Jay Vincent' WHEN 'Fran Curran Francis Hugh Curran Sr.' THEN 'Fran Curran' WHEN 'David Lattin' THEN 'Dave Lattin' WHEN 'Anthony Marshon Davis Jr.' THEN 'Anthony Davis' WHEN 'Brandan Keith Wright' THEN 'Brandan Wright' WHEN 'Askia Rahman Jones' THEN 'Askia Jones' WHEN 'Marvin Roberts' THEN 'Marv Roberts' WHEN 'Kenneth "Apple" Green' THEN 'Ken Green' WHEN 'Gerald Madkins Jr.' THEN 'Gerald Madkins' WHEN 'Philip Douglas Jackson' THEN 'Phil Jackson' WHEN 'Drew Edward Gordon' THEN 'Drew Gordon' WHEN 'Ed Dahler Edward Dahler Jr.' THEN 'Ed Dahler' WHEN 'Stanley M. Noszka' THEN 'Stan Noszka' WHEN 'Dwayne Kenneth Schintzius' THEN 'Dwayne Schintzius' WHEN 'Miles Julian Simon' THEN 'Miles Simon' WHEN 'Guy William Rodgers' THEN 'Guy Rodgers' WHEN 'James Patrick Walsh' THEN 'Jim Walsh' WHEN 'Tony Lorenzo Delk' THEN 'Tony Delk' WHEN 'Calvin Ramsey' THEN 'Cal Ramsey' WHEN 'Gene Dyker Eugene Walter Dyker' THEN 'Gene Dyker' WHEN 'Harry Junior "The Horse" Gallatin' THEN 'Harry Gallatin' WHEN 'Nicholas William Calathes' THEN 'Nick Calathes' WHEN 'Kevin Wayne Durant' THEN 'Kevin Durant' WHEN 'Nathaniel Thomas Huffman' THEN 'Nate Huffman' WHEN 'Shawn Christopher Respert' THEN 'Shawn Respert' WHEN 'Rodney Strickland' THEN 'Rod Strickland' WHEN 'Elmer H. Behnke' THEN 'Elmer Behnke' WHEN 'Lamar Brandon Stevens' THEN 'Lamar Stevens' WHEN 'Marvin "Mickey" Rottner' THEN 'Mickey Rottner' WHEN 'Dewayne "D. J." White, Jr.' THEN 'D. J. White' WHEN 'Gregory Clinton Foster' THEN 'Greg Foster' WHEN 'Joseph Xavier Forte' THEN 'Joseph Forte' WHEN 'Mark Jeffrey Radford' THEN 'Mark Radford' WHEN 'Garry Witts Garrett David Witts' THEN 'Garry Witts' WHEN 'Jabari Dominic Walker' THEN 'Jabari Walker' WHEN 'Jordan Lee Crawford' THEN 'Jordan Crawford' WHEN 'Wayne Lavern Robinson' THEN 'Wayne Robinson' WHEN 'Greg Fillmore Gregory Paul Fillmore' THEN 'Greg Fillmore' WHEN 'John Harding Lucas II' THEN 'John Lucas II' WHEN 'Leroy Patrick Chollet' THEN 'Leroy Chollet' WHEN 'Monti Davis DaMon William "Monti" Davis' THEN 'Monti Davis' WHEN 'Eric Johnson Jones' THEN 'Eric Johnson' WHEN 'Sidney Harold Tanenbaum' THEN 'Sid Tanenbaum' WHEN 'Andre Jamal Drummond' THEN 'Andre Drummond' WHEN 'Chavano Rainer "Buddy" Hield' THEN 'Buddy Hield' WHEN 'Joel Hans Embiid' THEN 'Joel Embiid' WHEN 'Paul Clifton Anthony George' THEN 'Paul George' WHEN 'Kyrie Andrew Irving' THEN 'Kyrie Irving' WHEN 'Jayson Christopher Tatum' THEN 'Jayson Tatum' WHEN 'Andrew Christian Wiggins' THEN 'Andrew Wiggins' WHEN 'Max Berning Fiedler' THEN 'Max Fiedler' WHEN 'Ogugua "OG" Anunoby Jr.' THEN 'OG Anunoby' WHEN 'Jaylen Marselles Brown' THEN 'Jaylen Brown' WHEN 'Jrue Randall Holiday' THEN 'Jrue Holiday' WHEN 'Austin Tyler Reaves' THEN 'Austin Reaves' WHEN 'Kevin Wesley Love' THEN 'Kevin Love' WHEN 'Giannis Sina Ugo Antetokounmpo' THEN 'Giannis Antetokounmpo' WHEN 'Wardell Stephen Curry II' THEN 'Stephen Curry' WHEN 'Alfred Joel Horford Reynoso' THEN 'Al Horford' WHEN 'Tyler Christopher Herro' THEN 'Tyler Herro' WHEN 'Duncan McBryde Robinson' THEN 'Duncan Robinson' WHEN 'Kyle Forman Anderson' THEN 'Kyle Anderson' WHEN 'Cade Parker Cunningham' THEN 'Cade Cunningham' WHEN 'LeBron Raymone James Sr.' THEN 'LeBron James' WHEN 'Jimmy Butler III' THEN 'Jimmy Butler' WHEN 'Kevon Grant Looney' THEN 'Kevon Looney' WHEN 'Zachary Thomas LaVine' THEN 'Zach LaVine' WHEN 'Jaden Edward Dhananjay Ivey' THEN 'Jaden Ivey' WHEN 'Kyle Terrell Lowry' THEN 'Kyle Lowry' WHEN 'Michael Jeffrey Jordan' THEN 'Michael Jordan' WHEN 'Devin Armani Booker' THEN 'Devin Booker' WHEN 'Draymond Jamal Green' THEN 'Draymond Green' WHEN 'Jonathan Malangu Kuminga' THEN 'Jonathan Kuminga' WHEN 'Lonzo Anderson Ball' THEN 'Lonzo Ball' WHEN 'Ausar XLNC Thompson' THEN 'Ausar Thompson' WHEN 'Jalen Marquis Brunson' THEN 'Jalen Brunson' WHEN 'Shaquille Rashaun O''Neal' THEN 'Shaquille O''Neal' WHEN 'Kobe Bean Bryant' THEN 'Kobe Bryant' WHEN 'Christopher Emmanuel Paul' THEN 'Chris Paul' WHEN 'Harrison Bryce Jordan Barnes' THEN 'Harrison Barnes' WHEN 'Edrice Femi "Bam" Adebayo' THEN 'Bam Adebayo' ELSE name END;
```
</details>

### Players G4: `player.college` (join partner's spelling)

player.college names a school as each article does (UCLA, University of Kentucky, Kentucky Wildcats, Duke University, Michigan State); a question that names schools the short way (Kentucky, Duke) needs every spelling stored as the short name, one that names them officially (University of Kentucky, Duke University) needs every spelling stored as the official name

**G4a.** For UCLA, Kentucky, Duke, Michigan State and North Carolina: how many players went there, how many became NBA champions, and how many were top-10 draft picks?

```sql
SELECT college, COUNT(*) AS players, SUM(CASE WHEN nba_championships >= 1 THEN 1 ELSE 0 END) AS nba_champions, SUM(CASE WHEN draft_pick BETWEEN 1 AND 10 THEN 1 ELSE 0 END) AS top_10_picks FROM player WHERE college IN ('UCLA', 'Kentucky', 'Duke', 'Michigan State', 'North Carolina') GROUP BY college;
```
<sub>Blind judges: The IN list uses short names ('UCLA', 'Kentucky', 'Duke', 'Michigan State', 'North Carolina'), and only Form 2 maps every variant to those short forms.</sub>

<details><summary>answer key</summary>

```sql
SELECT college, COUNT(*) AS players, SUM(CASE WHEN nba_championships >= 1 THEN 1 ELSE 0 END) AS nba_champions, SUM(CASE WHEN draft_pick BETWEEN 1 AND 10 THEN 1 ELSE 0 END) AS top_10_picks FROM (SELECT CASE WHEN college IN ('UCLA', 'University of California, Los Angeles') THEN 'UCLA' WHEN college IN ('Kentucky', 'Kentucky Wildcats', 'University of Kentucky') THEN 'Kentucky' WHEN college IN ('Duke', 'Duke University') THEN 'Duke' WHEN college IN ('Michigan State', 'Michigan State Spartans', 'Michigan State University') THEN 'Michigan State' WHEN college IN ('North Carolina Tar Heels', 'University of North Carolina', 'University of North Carolina at Chapel Hill') THEN 'North Carolina' END AS college, nba_championships, draft_pick FROM player) AS p WHERE college IS NOT NULL GROUP BY college;
```
</details>

**G4b.** For the University of Kentucky, Duke University, Michigan State University, Indiana University and the University of Florida: how many players went there, and how many NBA titles and Olympic gold medals have they won?

```sql
SELECT college, COUNT(*) AS players, SUM(nba_championships) AS nba_titles, SUM(olympic_gold_medals) AS olympic_golds FROM player WHERE college IN ('University of Kentucky', 'Duke University', 'Michigan State University', 'Indiana University', 'University of Florida') GROUP BY college;
```
<sub>Blind judges: The IN list uses full official names ('University of Kentucky', 'Michigan State University', 'Indiana University', 'Duke University'), and only Form 1 normalize</sub>

<details><summary>answer key</summary>

```sql
SELECT college, COUNT(*) AS players, SUM(nba_championships) AS nba_titles, SUM(olympic_gold_medals) AS olympic_golds FROM (SELECT CASE WHEN college IN ('Kentucky', 'Kentucky Wildcats', 'University of Kentucky') THEN 'University of Kentucky' WHEN college IN ('Duke', 'Duke University') THEN 'Duke University' WHEN college IN ('Michigan State', 'Michigan State Spartans', 'Michigan State University') THEN 'Michigan State University' WHEN college IN ('Indiana Hoosiers', 'Indiana University') THEN 'Indiana University' WHEN college IN ('University of Florida') THEN 'University of Florida' END AS college, nba_championships, olympic_gold_medals FROM player) AS p WHERE college IS NOT NULL GROUP BY college;
```
</details>

Stored forms (exact match; rows changed):

| Query | as stated (0) | stored as G4a needs (33) | stored as G4b needs (27) |
|---|---|---|---|
| G4a | 0.25 | 1.00 | 0.00 |
| G4b | 0.33 | 0.00 | 1.00 |

<details><summary>stored forms as SQL</summary>

```sql
-- G4a
UPDATE player SET college = CASE WHEN college IN ('UCLA', 'University of California, Los Angeles') THEN 'UCLA' WHEN college IN ('Kentucky', 'Kentucky Wildcats', 'University of Kentucky') THEN 'Kentucky' WHEN college IN ('Duke', 'Duke University') THEN 'Duke' WHEN college IN ('Michigan State', 'Michigan State Spartans', 'Michigan State University') THEN 'Michigan State' WHEN college IN ('North Carolina Tar Heels', 'University of North Carolina', 'University of North Carolina at Chapel Hill') THEN 'North Carolina' WHEN college IN ('Indiana Hoosiers', 'Indiana University') THEN 'Indiana' WHEN college IN ('Kansas Jayhawks', 'University of Kansas') THEN 'Kansas' WHEN college IN ('Villanova Wildcats', 'Villanova University') THEN 'Villanova' WHEN college IN ('Marquette', 'Marquette University') THEN 'Marquette' WHEN college IN ('NYU', 'New York University') THEN 'NYU' WHEN college IN ('Notre Dame', 'University of Notre Dame') THEN 'Notre Dame' WHEN college IN ('University of Florida') THEN 'Florida' WHEN college IN ('University of Connecticut') THEN 'Connecticut' ELSE college END;
```
```sql
-- G4b
UPDATE player SET college = CASE WHEN college IN ('UCLA', 'University of California, Los Angeles') THEN 'University of California, Los Angeles' WHEN college IN ('Kentucky', 'Kentucky Wildcats', 'University of Kentucky') THEN 'University of Kentucky' WHEN college IN ('Duke', 'Duke University') THEN 'Duke University' WHEN college IN ('Michigan State', 'Michigan State Spartans', 'Michigan State University') THEN 'Michigan State University' WHEN college IN ('North Carolina Tar Heels', 'University of North Carolina', 'University of North Carolina at Chapel Hill') THEN 'University of North Carolina' WHEN college IN ('Indiana Hoosiers', 'Indiana University') THEN 'Indiana University' WHEN college IN ('Kansas Jayhawks', 'University of Kansas') THEN 'University of Kansas' WHEN college IN ('Villanova Wildcats', 'Villanova University') THEN 'Villanova University' WHEN college IN ('Marquette', 'Marquette University') THEN 'Marquette University' WHEN college IN ('NYU', 'New York University') THEN 'New York University' WHEN college IN ('Notre Dame', 'University of Notre Dame') THEN 'University of Notre Dame' WHEN college IN ('University of Florida') THEN 'University of Florida' WHEN college IN ('University of Connecticut') THEN 'University of Connecticut' ELSE college END;
```
</details>


## Papers

### Papers G1: `cspaper.retrieval_method` (one value vs a list)

cspaper.retrieval_method lists every retrieval method a paper names (35 of 199 papers name two or more); G1a counts a paper under each method it names (needs the list as stated), G1b counts each paper once, a combination of methods as hybrid retrieval (needs one value per paper)

**G1a.** For single-hop and multi-hop papers, how many use dense retrieval, sparse retrieval, graph-based retrieval, hybrid retrieval and web search? A paper counts under every method it names.

```sql
SELECT reasoning_depth, COUNT(*) AS papers, SUM(CASE WHEN retrieval_method LIKE '%Dense%' THEN 1 ELSE 0 END) AS dense, SUM(CASE WHEN retrieval_method LIKE '%Sparse%' THEN 1 ELSE 0 END) AS sparse, SUM(CASE WHEN retrieval_method LIKE '%Graph%' THEN 1 ELSE 0 END) AS graph_based, SUM(CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 1 ELSE 0 END) AS hybrid, SUM(CASE WHEN retrieval_method LIKE '%Web%' THEN 1 ELSE 0 END) AS web_search FROM cspaper WHERE reasoning_depth IN ('multi-hop', 'single-hop') GROUP BY reasoning_depth;
```
<sub>Blind judges: Separate LIKE counts for Dense, Sparse, Graph, Hybrid and Web need the component methods kept in the string. Form 1 collapses them into 'Hybrid Retrieval', so t</sub>

<details><summary>answer key</summary>

```sql
SELECT reasoning_depth, COUNT(*) AS papers, SUM(CASE WHEN retrieval_method LIKE '%Dense%' THEN 1 ELSE 0 END) AS dense, SUM(CASE WHEN retrieval_method LIKE '%Sparse%' THEN 1 ELSE 0 END) AS sparse, SUM(CASE WHEN retrieval_method LIKE '%Graph%' THEN 1 ELSE 0 END) AS graph_based, SUM(CASE WHEN retrieval_method LIKE '%Hybrid%' THEN 1 ELSE 0 END) AS hybrid, SUM(CASE WHEN retrieval_method LIKE '%Web%' THEN 1 ELSE 0 END) AS web_search FROM cspaper WHERE reasoning_depth IN ('multi-hop', 'single-hop') GROUP BY reasoning_depth;
```
</details>

**G1b.** For each retrieval method, how many papers use it, how many of them use a reranker, and how many baselines do they compare against on average? A paper that combines two or more methods counts as hybrid retrieval.

```sql
SELECT retrieval_method, COUNT(*) AS papers, SUM(CASE WHEN uses_reranker = 'Yes' THEN 1 ELSE 0 END) AS with_reranker, AVG(baseline_amount) AS average_baselines FROM cspaper WHERE retrieval_method <> '' GROUP BY retrieval_method;
```
<sub>Blind judges: GROUP BY retrieval_method on a column described as 'choose one' expects one method per paper. Form 1 maps combinations to 'Hybrid Retrieval'; stored as stated, </sub>

<details><summary>answer key</summary>

```sql
SELECT CASE WHEN retrieval_method LIKE '%||%' THEN 'Hybrid Retrieval' ELSE retrieval_method END AS retrieval_method, COUNT(*) AS papers, SUM(CASE WHEN uses_reranker = 'Yes' THEN 1 ELSE 0 END) AS with_reranker, AVG(baseline_amount) AS average_baselines FROM cspaper WHERE retrieval_method <> '' GROUP BY CASE WHEN retrieval_method LIKE '%||%' THEN 'Hybrid Retrieval' ELSE retrieval_method END;
```
</details>

Stored forms (exact match; rows changed):

| Query | as stated (0) | stored as G1b needs (35) |
|---|---|---|
| G1a | 1.00 | 0.25 |
| G1b | 0.01 | 1.00 |

<details><summary>stored forms as SQL</summary>

```sql
-- G1b
UPDATE cspaper SET retrieval_method = 'Hybrid Retrieval' WHERE retrieval_method LIKE '%||%';
```
</details>

### Papers G2: `cspaper.application_domain` (one value vs a list)

cspaper.application_domain lists every domain a paper targets (39 of 199 papers name two or more, often General plus a specific domain); G2a counts a paper under each domain it names (needs the list as stated), G2b counts each paper once under its specific domain (needs one value per paper)

**G2a.** For papers with and without an agent, how many are general-purpose and how many target medicine, education, finance and academic research? A paper counts under every domain it names.

```sql
SELECT use_agent, COUNT(*) AS papers, SUM(CASE WHEN application_domain LIKE '%General%' THEN 1 ELSE 0 END) AS general_purpose, SUM(CASE WHEN application_domain LIKE '%Medical%' THEN 1 ELSE 0 END) AS medical, SUM(CASE WHEN application_domain LIKE '%Education%' THEN 1 ELSE 0 END) AS education, SUM(CASE WHEN application_domain LIKE '%Finance%' THEN 1 ELSE 0 END) AS finance, SUM(CASE WHEN application_domain LIKE '%Academic%' THEN 1 ELSE 0 END) AS academic FROM cspaper WHERE application_domain <> '' GROUP BY use_agent;
```
<sub>Blind judges: Separate LIKE counts for General, Medical, Education, Finance and Academic assume a paper can fall under several domains. Form 1 drops 'General' and folds mixes</sub>

<details><summary>answer key</summary>

```sql
SELECT use_agent, COUNT(*) AS papers, SUM(CASE WHEN application_domain LIKE '%General%' THEN 1 ELSE 0 END) AS general_purpose, SUM(CASE WHEN application_domain LIKE '%Medical%' THEN 1 ELSE 0 END) AS medical, SUM(CASE WHEN application_domain LIKE '%Education%' THEN 1 ELSE 0 END) AS education, SUM(CASE WHEN application_domain LIKE '%Finance%' THEN 1 ELSE 0 END) AS finance, SUM(CASE WHEN application_domain LIKE '%Academic%' THEN 1 ELSE 0 END) AS academic FROM cspaper WHERE application_domain <> '' GROUP BY use_agent;
```
</details>

**G2b.** Counting each paper once under its specific application domain (General only if it names no other domain, Multiple if it names two or more specific ones), how many papers are there per domain, how many study multi-hop reasoning, and how many use a knowledge graph?

```sql
SELECT application_domain, COUNT(*) AS papers, SUM(CASE WHEN reasoning_depth = 'multi-hop' THEN 1 ELSE 0 END) AS multi_hop, SUM(CASE WHEN uses_knowledge_graph = 'Yes' THEN 1 ELSE 0 END) AS with_knowledge_graph FROM cspaper WHERE application_domain <> '' GROUP BY application_domain;
```
<sub>Blind judges: GROUP BY application_domain with exact grouping implies one label per paper. Form 1 gives a single domain, with 'Multiple' for real mixes; stored as stated, eac</sub>

<details><summary>answer key</summary>

```sql
SELECT CASE WHEN application_domain NOT LIKE '%||%' THEN application_domain WHEN length(application_domain) - length(replace(application_domain, '||', '')) = 2 AND application_domain LIKE '%General%' THEN trim(replace(replace(application_domain, 'General||', ''), '|| General', '')) ELSE 'Multiple' END AS application_domain, COUNT(*) AS papers, SUM(CASE WHEN reasoning_depth = 'multi-hop' THEN 1 ELSE 0 END) AS multi_hop, SUM(CASE WHEN uses_knowledge_graph = 'Yes' THEN 1 ELSE 0 END) AS with_knowledge_graph FROM cspaper WHERE application_domain <> '' GROUP BY CASE WHEN application_domain NOT LIKE '%||%' THEN application_domain WHEN length(application_domain) - length(replace(application_domain, '||', '')) = 2 AND application_domain LIKE '%General%' THEN trim(replace(replace(application_domain, 'General||', ''), '|| General', '')) ELSE 'Multiple' END;
```
</details>

Stored forms (exact match; rows changed):

| Query | as stated (0) | stored as G2b needs (39) |
|---|---|---|
| G2a | 1.00 | 0.17 |
| G2b | 0.09 | 1.00 |

<details><summary>stored forms as SQL</summary>

```sql
-- G2b
UPDATE cspaper SET application_domain = CASE WHEN application_domain NOT LIKE '%||%' THEN application_domain WHEN length(application_domain) - length(replace(application_domain, '||', '')) = 2 AND application_domain LIKE '%General%' THEN trim(replace(replace(application_domain, 'General||', ''), '|| General', '')) ELSE 'Multiple' END WHERE application_domain <> '';
```
</details>

### Papers G3: `cspaper.performance_on_hotpotqa` (number vs stated text)

cspaper.performance_on_hotpotqa is the HotpotQA result as the paper states it (31 papers; metric names, model variants, several numbers); G3a needs each paper's best answer F1 as one number on a 0-100 scale (empty when the paper reports no answer F1), G3b needs the stated text to see which metrics are reported

**G3a.** For papers with and without an agent, what are the lowest and the highest answer F1 reported on HotpotQA, taking each paper's best F1 on a 0-100 scale?

```sql
SELECT use_agent, MIN(performance_on_hotpotqa) AS lowest_hotpotqa_f1, MAX(performance_on_hotpotqa) AS best_hotpotqa_f1 FROM cspaper WHERE performance_on_hotpotqa <> '' GROUP BY use_agent;
```
<sub>Blind judges: MIN and MAX aliased lowest_hotpotqa_f1 and best_hotpotqa_f1 call for a single numeric F1 per row, which Form 1 stores. MIN/MAX over the free-text metric strings</sub>

<details><summary>answer key</summary>

```sql
SELECT use_agent, MIN(f1) AS lowest_hotpotqa_f1, MAX(f1) AS best_hotpotqa_f1 FROM (SELECT use_agent, CASE paper_name WHEN 'learning to Refine Query for Retrieval Augmented Generation (RQ-RAG)' THEN 62.6 WHEN 'A Multi-Source Retrieval Question Answering Framework Based on RAG' THEN 30.66 WHEN 'DR-RAG: Applying Dynamic Document Relevance to RetrievalAugmented Generation for Question-Answering' THEN 62.87 WHEN 'Enhancing Retrieval and Managing Retrieval: A Four-Module Synergy for Improved Quality and Efficiency in RAG Systems' THEN 57.59 WHEN 'SMART-RAG: Selection using Determinantal Matrices for Augmented Retrieval' THEN 40.8 WHEN 'OPEN-RAG: Enhanced Retrieval-Augmented Reasoning with Open-Source Large Language Models' THEN 76.9 WHEN 'DMQR-RAG: DIVERSE MULTI-QUERY REWRITING FOR RETRIEVAL-AUGMENTED GENERATION' THEN 53.99 WHEN 'MBA-RAG: a Bandit Approach for Adaptive Retrieval-Augmented Generation through Question Complexity' THEN 53.3 WHEN 'Post-training an LLM for RAG? Train on Self-Generated Demonstrations' THEN 75.9 WHEN 'Vendi-RAG: Adaptively Trading-Off Diversity And Quality Significantly Improves Retrieval Augmented Generation With LLMs' THEN 57.0 WHEN 'Unveiling Knowledge Utilization Mechanisms in LLM-based Retrieval-Augmented Generation' THEN 59.57 WHEN 'KARE-RAG: Knowledge-Aware Refinement and Enhancement for RAG' THEN 46.45 WHEN 'BEE-RAG: Balanced Entropy Engineering for Retrieval-Augmented Generation' THEN 44.81 WHEN 'Transforming Questions and Documents for Semantically Aligned Retrieval-Augmented Generation' THEN 67.5 WHEN 'CORE: LOSSLESS COMPRESSION FOR RETRIEVALAUGMENTED LLMS VIA REINFORCEMENT LEARNING' THEN 46.35 WHEN 'TeaRAG: A Token-Efficient Agentic Retrieval-Augmented Generation Framework' THEN 63.14 WHEN 'Answering-Students-Questions-on-Course-Forums-Using-Multiple-Chain-of-Thought-Reasoning-and-Finetuni' THEN 62.2 END AS f1 FROM cspaper) WHERE f1 IS NOT NULL GROUP BY use_agent;
```
</details>

**G3b.** For papers with and without a reranker that report HotpotQA results, how many report an F1 score and how many report accuracy?

```sql
SELECT uses_reranker, COUNT(*) AS papers, SUM(CASE WHEN performance_on_hotpotqa LIKE '%F1%' THEN 1 ELSE 0 END) AS report_f1, SUM(CASE WHEN performance_on_hotpotqa LIKE '%Acc%' THEN 1 ELSE 0 END) AS report_accuracy FROM cspaper WHERE performance_on_hotpotqa <> '' AND uses_reranker IN ('Yes', 'No') GROUP BY uses_reranker;
```
<sub>Blind judges: LIKE '%F1%' and LIKE '%Acc%' test which metric names a paper reports. Only the text as stated keeps the metric labels; Form 1 keeps just a bare F1 number or 'No</sub>

<details><summary>answer key</summary>

```sql
SELECT uses_reranker, COUNT(*) AS papers, SUM(CASE WHEN performance_on_hotpotqa LIKE '%F1%' THEN 1 ELSE 0 END) AS report_f1, SUM(CASE WHEN performance_on_hotpotqa LIKE '%Acc%' THEN 1 ELSE 0 END) AS report_accuracy FROM cspaper WHERE performance_on_hotpotqa <> '' AND uses_reranker IN ('Yes', 'No') GROUP BY uses_reranker;
```
</details>

Stored forms (exact match; rows changed):

| Query | as stated (0) | stored as G3a needs (31) |
|---|---|---|
| G3a | 0.00 | 1.00 |
| G3b | 1.00 | 0.00 |

<details><summary>stored forms as SQL</summary>

```sql
-- G3a
UPDATE cspaper SET performance_on_hotpotqa = CASE paper_name WHEN 'learning to Refine Query for Retrieval Augmented Generation (RQ-RAG)' THEN 62.6 WHEN 'A Multi-Source Retrieval Question Answering Framework Based on RAG' THEN 30.66 WHEN 'DR-RAG: Applying Dynamic Document Relevance to RetrievalAugmented Generation for Question-Answering' THEN 62.87 WHEN 'Enhancing Retrieval and Managing Retrieval: A Four-Module Synergy for Improved Quality and Efficiency in RAG Systems' THEN 57.59 WHEN 'SMART-RAG: Selection using Determinantal Matrices for Augmented Retrieval' THEN 40.8 WHEN 'OPEN-RAG: Enhanced Retrieval-Augmented Reasoning with Open-Source Large Language Models' THEN 76.9 WHEN 'DMQR-RAG: DIVERSE MULTI-QUERY REWRITING FOR RETRIEVAL-AUGMENTED GENERATION' THEN 53.99 WHEN 'MBA-RAG: a Bandit Approach for Adaptive Retrieval-Augmented Generation through Question Complexity' THEN 53.3 WHEN 'Post-training an LLM for RAG? Train on Self-Generated Demonstrations' THEN 75.9 WHEN 'Vendi-RAG: Adaptively Trading-Off Diversity And Quality Significantly Improves Retrieval Augmented Generation With LLMs' THEN 57.0 WHEN 'Unveiling Knowledge Utilization Mechanisms in LLM-based Retrieval-Augmented Generation' THEN 59.57 WHEN 'KARE-RAG: Knowledge-Aware Refinement and Enhancement for RAG' THEN 46.45 WHEN 'BEE-RAG: Balanced Entropy Engineering for Retrieval-Augmented Generation' THEN 44.81 WHEN 'Transforming Questions and Documents for Semantically Aligned Retrieval-Augmented Generation' THEN 67.5 WHEN 'CORE: LOSSLESS COMPRESSION FOR RETRIEVALAUGMENTED LLMS VIA REINFORCEMENT LEARNING' THEN 46.35 WHEN 'TeaRAG: A Token-Efficient Agentic Retrieval-Augmented Generation Framework' THEN 63.14 WHEN 'Answering-Students-Questions-on-Course-Forums-Using-Multiple-Chain-of-Thought-Reasoning-and-Finetuni' THEN 62.2 END WHERE performance_on_hotpotqa <> '';
```
</details>

### Papers G4: `cspaper.data_modality` (fine vs coarse)

cspaper.data_modality lists the input types a paper handles (Text, Image, Table, Code, Audio; 53 papers name more than text alone); G4a counts papers per stated input type (needs the list as stated), G4b compares text-only with multimodal papers (needs one coarse value per paper)

**G4a.** For single-hop and multi-hop papers, how many handle images, tables, code and audio as input?

```sql
SELECT reasoning_depth, COUNT(*) AS papers, SUM(CASE WHEN data_modality LIKE '%Image%' THEN 1 ELSE 0 END) AS image, SUM(CASE WHEN data_modality LIKE '%Table%' THEN 1 ELSE 0 END) AS tables, SUM(CASE WHEN data_modality LIKE '%Code%' THEN 1 ELSE 0 END) AS code, SUM(CASE WHEN data_modality LIKE '%Audio%' THEN 1 ELSE 0 END) AS audio FROM cspaper WHERE reasoning_depth IN ('multi-hop', 'single-hop') GROUP BY reasoning_depth;
```
<sub>Blind judges: The query counts each modality with LIKE '%Image%', '%Table%', '%Code%' and '%Audio%', so it needs the individual modalities kept in the string. Form 1 collapse</sub>

<details><summary>answer key</summary>

```sql
SELECT reasoning_depth, COUNT(*) AS papers, SUM(CASE WHEN data_modality LIKE '%Image%' THEN 1 ELSE 0 END) AS image, SUM(CASE WHEN data_modality LIKE '%Table%' THEN 1 ELSE 0 END) AS tables, SUM(CASE WHEN data_modality LIKE '%Code%' THEN 1 ELSE 0 END) AS code, SUM(CASE WHEN data_modality LIKE '%Audio%' THEN 1 ELSE 0 END) AS audio FROM cspaper WHERE reasoning_depth IN ('multi-hop', 'single-hop') GROUP BY reasoning_depth;
```
</details>

**G4b.** How do text-only papers compare with multimodal papers (any image, table, code or audio input): how many are there, how many use an agent, and how many use a reranker?

```sql
SELECT data_modality, COUNT(*) AS papers, SUM(CASE WHEN use_agent = 'Yes' THEN 1 ELSE 0 END) AS with_agent, SUM(CASE WHEN uses_reranker = 'Yes' THEN 1 ELSE 0 END) AS with_reranker FROM cspaper WHERE data_modality IN ('Text', 'Multimodal') GROUP BY data_modality;
```
<sub>Blind judges: The filter data_modality IN ('Text','Multimodal') uses 'Multimodal' as a stored value. Only Form 1 stores it; stored as stated, every multi-modality row would d</sub>

<details><summary>answer key</summary>

```sql
SELECT CASE WHEN data_modality = 'Text' THEN 'Text' ELSE 'Multimodal' END AS data_modality, COUNT(*) AS papers, SUM(CASE WHEN use_agent = 'Yes' THEN 1 ELSE 0 END) AS with_agent, SUM(CASE WHEN uses_reranker = 'Yes' THEN 1 ELSE 0 END) AS with_reranker FROM cspaper WHERE data_modality <> '' AND data_modality <> 'proprietary enterprise dataset' GROUP BY CASE WHEN data_modality = 'Text' THEN 'Text' ELSE 'Multimodal' END;
```
</details>

Stored forms (exact match; rows changed):

| Query | as stated (0) | stored as G4b needs (53) |
|---|---|---|
| G4a | 1.00 | 0.30 |
| G4b | 0.37 | 1.00 |

<details><summary>stored forms as SQL</summary>

```sql
-- G4b
UPDATE cspaper SET data_modality = CASE WHEN data_modality = 'Text' THEN 'Text' ELSE 'Multimodal' END WHERE data_modality <> '' AND data_modality <> 'proprietary enterprise dataset';
```
</details>

### Papers G5: `cspaper.generator_model` (fine vs coarse)

cspaper.generator_model lists the generator models as each paper spells them (Llama2-7B, Llama 2 7B, LLaMA-2-7b, Qwen-2.5-7B, GPT-4o, ...); G5a needs model versions under one spelling (Llama 2, Llama 3, Qwen2.5), G5b needs one coarse class per paper (proprietary only, open-weight only, both)

**G5a.** For single-hop and multi-hop papers, how many papers are there, and how many use a Llama 2 model, a Llama 3 model (any 3.x release) and a Qwen2.5 model as a generator?

```sql
SELECT reasoning_depth, COUNT(*) AS papers, SUM(CASE WHEN generator_model LIKE '%Llama 2%' THEN 1 ELSE 0 END) AS llama_2, SUM(CASE WHEN generator_model LIKE '%Llama 3%' THEN 1 ELSE 0 END) AS llama_3, SUM(CASE WHEN generator_model LIKE '%Qwen2.5%' THEN 1 ELSE 0 END) AS qwen_2_5 FROM cspaper WHERE reasoning_depth IN ('multi-hop', 'single-hop') GROUP BY reasoning_depth;
```
<sub>Blind judges: LIKE '%Llama 2%' and '%Llama 3%' (with a space) only match the normalized names in Form 1. Stored as stated, values like 'Llama2-13B' and 'Llama3 8B' are missed</sub>

<details><summary>answer key</summary>

```sql
SELECT reasoning_depth, COUNT(*) AS papers, SUM(CASE WHEN (replace(replace(replace(lower(generator_model), ' ', ''), '-', ''), 'shearedllama2.7b', '') LIKE '%llama2%' OR replace(replace(lower(generator_model), ' ', ''), '-', '') LIKE '%llama7bchat%') THEN 1 ELSE 0 END) AS llama_2, SUM(CASE WHEN (replace(replace(lower(generator_model), ' ', ''), '-', '') LIKE '%llama3%' OR replace(replace(lower(generator_model), ' ', ''), '-', '') LIKE '%llama8binstruct%') THEN 1 ELSE 0 END) AS llama_3, SUM(CASE WHEN replace(replace(lower(generator_model), ' ', ''), '-', '') LIKE '%qwen2.5%' THEN 1 ELSE 0 END) AS qwen_2_5 FROM cspaper WHERE reasoning_depth IN ('multi-hop', 'single-hop') GROUP BY reasoning_depth;
```
</details>

**G5b.** How do papers that use only proprietary generator models (such as GPT, Claude or Gemini), only open-weight models (such as Llama, Qwen or Mistral), or both compare: how many papers are in each group, how many use an agent, and how many baselines do they compare against on average?

```sql
SELECT generator_model, COUNT(*) AS papers, SUM(CASE WHEN use_agent = 'Yes' THEN 1 ELSE 0 END) AS with_agent, AVG(baseline_amount) AS average_baselines FROM cspaper WHERE generator_model IN ('Proprietary', 'Open-weight', 'Both') GROUP BY generator_model;
```
<sub>Blind judges: The filter generator_model IN ('Proprietary','Open-weight','Both') and GROUP BY only match rows if the column holds those licence categories, which only Form 2 </sub>

<details><summary>answer key</summary>

```sql
SELECT CASE WHEN (replace(replace(replace(lower(generator_model), 'gpt-neo', ''), 'gpt-2', ''), 'gpt-based', '') LIKE '%gpt%' OR lower(generator_model) LIKE '%claude%' OR lower(generator_model) LIKE '%gemini%' OR lower(generator_model) LIKE '%palm%' OR lower(generator_model) LIKE '%o3-mini%' OR lower(generator_model) LIKE '%openai o3%' OR lower(generator_model) LIKE '%sabia%' OR lower(generator_model) LIKE '%text-embedding%' OR lower(generator_model) LIKE '%qwen-vl-plus%' OR lower(generator_model) LIKE '%mistral large%' OR lower(generator_model) LIKE '%openrouter%') AND (replace(lower(generator_model), 'ollama', '') LIKE '%llama%' OR replace(lower(generator_model), 'mistral large', '') LIKE '%mistral%' OR replace(lower(generator_model), 'qwen-vl-plus', '') LIKE '%qwen%' OR lower(generator_model) LIKE '%mixtral%' OR lower(generator_model) LIKE '%qwq%' OR lower(generator_model) LIKE '%phi%' OR lower(generator_model) LIKE '%gemma%' OR lower(generator_model) LIKE '%falcon%' OR lower(generator_model) LIKE '%t5%' OR lower(generator_model) LIKE '%bert%' OR lower(generator_model) LIKE '%opt-%' OR lower(generator_model) LIKE '%bloom%' OR lower(generator_model) LIKE '%gpt-neo%' OR lower(generator_model) LIKE '%gpt-2%' OR lower(generator_model) LIKE '%vicuna%' OR lower(generator_model) LIKE '%baichuan%' OR lower(generator_model) LIKE '%glm%' OR lower(generator_model) LIKE '%deepseek%' OR lower(generator_model) LIKE '%minicpm%' OR lower(generator_model) LIKE '%llava%' OR lower(generator_model) LIKE '%unifiedqa%' OR lower(generator_model) LIKE '%aya%' OR lower(generator_model) LIKE '%flan%' OR lower(generator_model) LIKE '%ui-tars%' OR lower(generator_model) LIKE '%oransight%' OR lower(generator_model) LIKE '%smallcap%' OR lower(generator_model) LIKE '%lambada%') THEN 'Both' WHEN (replace(replace(replace(lower(generator_model), 'gpt-neo', ''), 'gpt-2', ''), 'gpt-based', '') LIKE '%gpt%' OR lower(generator_model) LIKE '%claude%' OR lower(generator_model) LIKE '%gemini%' OR lower(generator_model) LIKE '%palm%' OR lower(generator_model) LIKE '%o3-mini%' OR lower(generator_model) LIKE '%openai o3%' OR lower(generator_model) LIKE '%sabia%' OR lower(generator_model) LIKE '%text-embedding%' OR lower(generator_model) LIKE '%qwen-vl-plus%' OR lower(generator_model) LIKE '%mistral large%' OR lower(generator_model) LIKE '%openrouter%') THEN 'Proprietary' WHEN (replace(lower(generator_model), 'ollama', '') LIKE '%llama%' OR replace(lower(generator_model), 'mistral large', '') LIKE '%mistral%' OR replace(lower(generator_model), 'qwen-vl-plus', '') LIKE '%qwen%' OR lower(generator_model) LIKE '%mixtral%' OR lower(generator_model) LIKE '%qwq%' OR lower(generator_model) LIKE '%phi%' OR lower(generator_model) LIKE '%gemma%' OR lower(generator_model) LIKE '%falcon%' OR lower(generator_model) LIKE '%t5%' OR lower(generator_model) LIKE '%bert%' OR lower(generator_model) LIKE '%opt-%' OR lower(generator_model) LIKE '%bloom%' OR lower(generator_model) LIKE '%gpt-neo%' OR lower(generator_model) LIKE '%gpt-2%' OR lower(generator_model) LIKE '%vicuna%' OR lower(generator_model) LIKE '%baichuan%' OR lower(generator_model) LIKE '%glm%' OR lower(generator_model) LIKE '%deepseek%' OR lower(generator_model) LIKE '%minicpm%' OR lower(generator_model) LIKE '%llava%' OR lower(generator_model) LIKE '%unifiedqa%' OR lower(generator_model) LIKE '%aya%' OR lower(generator_model) LIKE '%flan%' OR lower(generator_model) LIKE '%ui-tars%' OR lower(generator_model) LIKE '%oransight%' OR lower(generator_model) LIKE '%smallcap%' OR lower(generator_model) LIKE '%lambada%') THEN 'Open-weight' ELSE 'Unknown' END AS generator_model, COUNT(*) AS papers, SUM(CASE WHEN use_agent = 'Yes' THEN 1 ELSE 0 END) AS with_agent, AVG(baseline_amount) AS average_baselines FROM cspaper WHERE generator_model <> '' AND CASE WHEN (replace(replace(replace(lower(generator_model), 'gpt-neo', ''), 'gpt-2', ''), 'gpt-based', '') LIKE '%gpt%' OR lower(generator_model) LIKE '%claude%' OR lower(generator_model) LIKE '%gemini%' OR lower(generator_model) LIKE '%palm%' OR lower(generator_model) LIKE '%o3-mini%' OR lower(generator_model) LIKE '%openai o3%' OR lower(generator_model) LIKE '%sabia%' OR lower(generator_model) LIKE '%text-embedding%' OR lower(generator_model) LIKE '%qwen-vl-plus%' OR lower(generator_model) LIKE '%mistral large%' OR lower(generator_model) LIKE '%openrouter%') AND (replace(lower(generator_model), 'ollama', '') LIKE '%llama%' OR replace(lower(generator_model), 'mistral large', '') LIKE '%mistral%' OR replace(lower(generator_model), 'qwen-vl-plus', '') LIKE '%qwen%' OR lower(generator_model) LIKE '%mixtral%' OR lower(generator_model) LIKE '%qwq%' OR lower(generator_model) LIKE '%phi%' OR lower(generator_model) LIKE '%gemma%' OR lower(generator_model) LIKE '%falcon%' OR lower(generator_model) LIKE '%t5%' OR lower(generator_model) LIKE '%bert%' OR lower(generator_model) LIKE '%opt-%' OR lower(generator_model) LIKE '%bloom%' OR lower(generator_model) LIKE '%gpt-neo%' OR lower(generator_model) LIKE '%gpt-2%' OR lower(generator_model) LIKE '%vicuna%' OR lower(generator_model) LIKE '%baichuan%' OR lower(generator_model) LIKE '%glm%' OR lower(generator_model) LIKE '%deepseek%' OR lower(generator_model) LIKE '%minicpm%' OR lower(generator_model) LIKE '%llava%' OR lower(generator_model) LIKE '%unifiedqa%' OR lower(generator_model) LIKE '%aya%' OR lower(generator_model) LIKE '%flan%' OR lower(generator_model) LIKE '%ui-tars%' OR lower(generator_model) LIKE '%oransight%' OR lower(generator_model) LIKE '%smallcap%' OR lower(generator_model) LIKE '%lambada%') THEN 'Both' WHEN (replace(replace(replace(lower(generator_model), 'gpt-neo', ''), 'gpt-2', ''), 'gpt-based', '') LIKE '%gpt%' OR lower(generator_model) LIKE '%claude%' OR lower(generator_model) LIKE '%gemini%' OR lower(generator_model) LIKE '%palm%' OR lower(generator_model) LIKE '%o3-mini%' OR lower(generator_model) LIKE '%openai o3%' OR lower(generator_model) LIKE '%sabia%' OR lower(generator_model) LIKE '%text-embedding%' OR lower(generator_model) LIKE '%qwen-vl-plus%' OR lower(generator_model) LIKE '%mistral large%' OR lower(generator_model) LIKE '%openrouter%') THEN 'Proprietary' WHEN (replace(lower(generator_model), 'ollama', '') LIKE '%llama%' OR replace(lower(generator_model), 'mistral large', '') LIKE '%mistral%' OR replace(lower(generator_model), 'qwen-vl-plus', '') LIKE '%qwen%' OR lower(generator_model) LIKE '%mixtral%' OR lower(generator_model) LIKE '%qwq%' OR lower(generator_model) LIKE '%phi%' OR lower(generator_model) LIKE '%gemma%' OR lower(generator_model) LIKE '%falcon%' OR lower(generator_model) LIKE '%t5%' OR lower(generator_model) LIKE '%bert%' OR lower(generator_model) LIKE '%opt-%' OR lower(generator_model) LIKE '%bloom%' OR lower(generator_model) LIKE '%gpt-neo%' OR lower(generator_model) LIKE '%gpt-2%' OR lower(generator_model) LIKE '%vicuna%' OR lower(generator_model) LIKE '%baichuan%' OR lower(generator_model) LIKE '%glm%' OR lower(generator_model) LIKE '%deepseek%' OR lower(generator_model) LIKE '%minicpm%' OR lower(generator_model) LIKE '%llava%' OR lower(generator_model) LIKE '%unifiedqa%' OR lower(generator_model) LIKE '%aya%' OR lower(generator_model) LIKE '%flan%' OR lower(generator_model) LIKE '%ui-tars%' OR lower(generator_model) LIKE '%oransight%' OR lower(generator_model) LIKE '%smallcap%' OR lower(generator_model) LIKE '%lambada%') THEN 'Open-weight' ELSE 'Unknown' END <> 'Unknown' GROUP BY CASE WHEN (replace(replace(replace(lower(generator_model), 'gpt-neo', ''), 'gpt-2', ''), 'gpt-based', '') LIKE '%gpt%' OR lower(generator_model) LIKE '%claude%' OR lower(generator_model) LIKE '%gemini%' OR lower(generator_model) LIKE '%palm%' OR lower(generator_model) LIKE '%o3-mini%' OR lower(generator_model) LIKE '%openai o3%' OR lower(generator_model) LIKE '%sabia%' OR lower(generator_model) LIKE '%text-embedding%' OR lower(generator_model) LIKE '%qwen-vl-plus%' OR lower(generator_model) LIKE '%mistral large%' OR lower(generator_model) LIKE '%openrouter%') AND (replace(lower(generator_model), 'ollama', '') LIKE '%llama%' OR replace(lower(generator_model), 'mistral large', '') LIKE '%mistral%' OR replace(lower(generator_model), 'qwen-vl-plus', '') LIKE '%qwen%' OR lower(generator_model) LIKE '%mixtral%' OR lower(generator_model) LIKE '%qwq%' OR lower(generator_model) LIKE '%phi%' OR lower(generator_model) LIKE '%gemma%' OR lower(generator_model) LIKE '%falcon%' OR lower(generator_model) LIKE '%t5%' OR lower(generator_model) LIKE '%bert%' OR lower(generator_model) LIKE '%opt-%' OR lower(generator_model) LIKE '%bloom%' OR lower(generator_model) LIKE '%gpt-neo%' OR lower(generator_model) LIKE '%gpt-2%' OR lower(generator_model) LIKE '%vicuna%' OR lower(generator_model) LIKE '%baichuan%' OR lower(generator_model) LIKE '%glm%' OR lower(generator_model) LIKE '%deepseek%' OR lower(generator_model) LIKE '%minicpm%' OR lower(generator_model) LIKE '%llava%' OR lower(generator_model) LIKE '%unifiedqa%' OR lower(generator_model) LIKE '%aya%' OR lower(generator_model) LIKE '%flan%' OR lower(generator_model) LIKE '%ui-tars%' OR lower(generator_model) LIKE '%oransight%' OR lower(generator_model) LIKE '%smallcap%' OR lower(generator_model) LIKE '%lambada%') THEN 'Both' WHEN (replace(replace(replace(lower(generator_model), 'gpt-neo', ''), 'gpt-2', ''), 'gpt-based', '') LIKE '%gpt%' OR lower(generator_model) LIKE '%claude%' OR lower(generator_model) LIKE '%gemini%' OR lower(generator_model) LIKE '%palm%' OR lower(generator_model) LIKE '%o3-mini%' OR lower(generator_model) LIKE '%openai o3%' OR lower(generator_model) LIKE '%sabia%' OR lower(generator_model) LIKE '%text-embedding%' OR lower(generator_model) LIKE '%qwen-vl-plus%' OR lower(generator_model) LIKE '%mistral large%' OR lower(generator_model) LIKE '%openrouter%') THEN 'Proprietary' WHEN (replace(lower(generator_model), 'ollama', '') LIKE '%llama%' OR replace(lower(generator_model), 'mistral large', '') LIKE '%mistral%' OR replace(lower(generator_model), 'qwen-vl-plus', '') LIKE '%qwen%' OR lower(generator_model) LIKE '%mixtral%' OR lower(generator_model) LIKE '%qwq%' OR lower(generator_model) LIKE '%phi%' OR lower(generator_model) LIKE '%gemma%' OR lower(generator_model) LIKE '%falcon%' OR lower(generator_model) LIKE '%t5%' OR lower(generator_model) LIKE '%bert%' OR lower(generator_model) LIKE '%opt-%' OR lower(generator_model) LIKE '%bloom%' OR lower(generator_model) LIKE '%gpt-neo%' OR lower(generator_model) LIKE '%gpt-2%' OR lower(generator_model) LIKE '%vicuna%' OR lower(generator_model) LIKE '%baichuan%' OR lower(generator_model) LIKE '%glm%' OR lower(generator_model) LIKE '%deepseek%' OR lower(generator_model) LIKE '%minicpm%' OR lower(generator_model) LIKE '%llava%' OR lower(generator_model) LIKE '%unifiedqa%' OR lower(generator_model) LIKE '%aya%' OR lower(generator_model) LIKE '%flan%' OR lower(generator_model) LIKE '%ui-tars%' OR lower(generator_model) LIKE '%oransight%' OR lower(generator_model) LIKE '%smallcap%' OR lower(generator_model) LIKE '%lambada%') THEN 'Open-weight' ELSE 'Unknown' END;
```
</details>

Stored forms (exact match; rows changed):

| Query | as stated (0) | stored as G5a needs (77) | stored as G5b needs (185) |
|---|---|---|---|
| G5a | 0.38 | 1.00 | 0.25 |
| G5b | 0.00 | 0.00 | 1.00 |

<details><summary>stored forms as SQL</summary>

```sql
-- G5a
UPDATE cspaper SET generator_model = replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(generator_model, 'Sheared LLaMA-2.7B', 'Sheared-LLaMA (2.7B)'), 'Llama27B', 'Llama 2 7B'), 'Llama3gB', 'Llama 3 8B'), 'Llama-7b-chat', 'Llama 2 7b-chat'), 'Llama-13b-chat', 'Llama 2 13b-chat'), 'LLaMA-8B Instruct', 'Llama 3 8B Instruct'), 'LLaMA-2', 'LLaMA 2'), 'LLaMA-3', 'LLaMA 3'), 'LLaMA2', 'LLaMA 2'), 'LLaMA3', 'LLaMA 3'), 'Llama-2', 'Llama 2'), 'Llama-3', 'Llama 3'), 'Llama2', 'Llama 2'), 'Llama3', 'Llama 3'), 'LLaMa2', 'LLaMa 2'), 'LLaMa3', 'LLaMa 3'), 'LLama3', 'LLama 3'), 'LLAMA3', 'LLAMA 3'), 'llama-3', 'llama 3'), 'llama3', 'llama 3'), 'Qwen-2.5', 'Qwen2.5'), 'Qwen 2.5', 'Qwen2.5');
```
```sql
-- G5b
UPDATE cspaper SET generator_model = CASE WHEN (replace(replace(replace(lower(generator_model), 'gpt-neo', ''), 'gpt-2', ''), 'gpt-based', '') LIKE '%gpt%' OR lower(generator_model) LIKE '%claude%' OR lower(generator_model) LIKE '%gemini%' OR lower(generator_model) LIKE '%palm%' OR lower(generator_model) LIKE '%o3-mini%' OR lower(generator_model) LIKE '%openai o3%' OR lower(generator_model) LIKE '%sabia%' OR lower(generator_model) LIKE '%text-embedding%' OR lower(generator_model) LIKE '%qwen-vl-plus%' OR lower(generator_model) LIKE '%mistral large%' OR lower(generator_model) LIKE '%openrouter%') AND (replace(lower(generator_model), 'ollama', '') LIKE '%llama%' OR replace(lower(generator_model), 'mistral large', '') LIKE '%mistral%' OR replace(lower(generator_model), 'qwen-vl-plus', '') LIKE '%qwen%' OR lower(generator_model) LIKE '%mixtral%' OR lower(generator_model) LIKE '%qwq%' OR lower(generator_model) LIKE '%phi%' OR lower(generator_model) LIKE '%gemma%' OR lower(generator_model) LIKE '%falcon%' OR lower(generator_model) LIKE '%t5%' OR lower(generator_model) LIKE '%bert%' OR lower(generator_model) LIKE '%opt-%' OR lower(generator_model) LIKE '%bloom%' OR lower(generator_model) LIKE '%gpt-neo%' OR lower(generator_model) LIKE '%gpt-2%' OR lower(generator_model) LIKE '%vicuna%' OR lower(generator_model) LIKE '%baichuan%' OR lower(generator_model) LIKE '%glm%' OR lower(generator_model) LIKE '%deepseek%' OR lower(generator_model) LIKE '%minicpm%' OR lower(generator_model) LIKE '%llava%' OR lower(generator_model) LIKE '%unifiedqa%' OR lower(generator_model) LIKE '%aya%' OR lower(generator_model) LIKE '%flan%' OR lower(generator_model) LIKE '%ui-tars%' OR lower(generator_model) LIKE '%oransight%' OR lower(generator_model) LIKE '%smallcap%' OR lower(generator_model) LIKE '%lambada%') THEN 'Both' WHEN (replace(replace(replace(lower(generator_model), 'gpt-neo', ''), 'gpt-2', ''), 'gpt-based', '') LIKE '%gpt%' OR lower(generator_model) LIKE '%claude%' OR lower(generator_model) LIKE '%gemini%' OR lower(generator_model) LIKE '%palm%' OR lower(generator_model) LIKE '%o3-mini%' OR lower(generator_model) LIKE '%openai o3%' OR lower(generator_model) LIKE '%sabia%' OR lower(generator_model) LIKE '%text-embedding%' OR lower(generator_model) LIKE '%qwen-vl-plus%' OR lower(generator_model) LIKE '%mistral large%' OR lower(generator_model) LIKE '%openrouter%') THEN 'Proprietary' WHEN (replace(lower(generator_model), 'ollama', '') LIKE '%llama%' OR replace(lower(generator_model), 'mistral large', '') LIKE '%mistral%' OR replace(lower(generator_model), 'qwen-vl-plus', '') LIKE '%qwen%' OR lower(generator_model) LIKE '%mixtral%' OR lower(generator_model) LIKE '%qwq%' OR lower(generator_model) LIKE '%phi%' OR lower(generator_model) LIKE '%gemma%' OR lower(generator_model) LIKE '%falcon%' OR lower(generator_model) LIKE '%t5%' OR lower(generator_model) LIKE '%bert%' OR lower(generator_model) LIKE '%opt-%' OR lower(generator_model) LIKE '%bloom%' OR lower(generator_model) LIKE '%gpt-neo%' OR lower(generator_model) LIKE '%gpt-2%' OR lower(generator_model) LIKE '%vicuna%' OR lower(generator_model) LIKE '%baichuan%' OR lower(generator_model) LIKE '%glm%' OR lower(generator_model) LIKE '%deepseek%' OR lower(generator_model) LIKE '%minicpm%' OR lower(generator_model) LIKE '%llava%' OR lower(generator_model) LIKE '%unifiedqa%' OR lower(generator_model) LIKE '%aya%' OR lower(generator_model) LIKE '%flan%' OR lower(generator_model) LIKE '%ui-tars%' OR lower(generator_model) LIKE '%oransight%' OR lower(generator_model) LIKE '%smallcap%' OR lower(generator_model) LIKE '%lambada%') THEN 'Open-weight' ELSE 'Unknown' END WHERE generator_model <> '';
```
</details>


## Dropped by the blind reading test

| Query | Outcome | Judges' reason (first judge) |
|---|---|---|
| Artists G4a | a judge contradicts the key | GROUP BY century with only a non-empty filter, over a column whose description explicitly allows spans like 19th-20th, groups by the values as given. Nothing in |
| Artists G5a | a judge contradicts the key | Exact IN ('Realism','Expressionism') on a free-text style column picks out those exact styles. Abstract Expressionism, Neo-Expressionism and Photorealism are di |
| Legal G1a | a judge contradicts the key | Grouping by defendant should treat surface variants as one defendant: a leading 'The', truncated names, and a co-respondent appended (the description says keep  |
| Legal G1c | a judge contradicts the key | A per-defendant, per-year breakdown of frequent defendants fits two readings equally well. Form 2 keeps distinct ministerial titles with each title's years. For |
| Legal G2a | a judge contradicts the key | The query groups by case_type with no filter, so the analyst expects one row per category in the description's list, and 'Commercial Case' is one of the four. F |
| Legal G3a | a judge contradicts the key | Grouping by status follows the description's per-occupation rule, which Form 1 keeps (with International Student folded into Student). Form 2 collapses everyone |
| Legal G4a | a judge contradicts the key | This is the same per-lawyer grouping as legal-9890. Form 1 keeps one bare name for the first counsel, so team strings are not used as keys and 'Mr P Gray' and ' |
| Legal G4c | a judge contradicts the key | The query groups by counsel to get per-lawyer counts, so the key should name one lawyer, not a team string like 'C Golvan SC || S Ricketson'. Form 3 keeps the f |
| Med G4b | one judge ambiguous | The filters LIKE '%hours%' and '%as needed%' with <> '' need text. Form 2's numbers break them. Form 1 and the stated form both keep 'hours' and 'as needed' in  |
| Players G1c | one judge ambiguous | The query groups by team with no join, for players drafted before 1980. Grouping by the historical team name as stated (matching 'last team joined') and groupin |
| Players G2a | one judge ambiguous | The query filters nationality <> 'American'. Form 1 maps hyphenated values such as 'Nigerian-American' to 'American', which excludes them. Form 2 and the stored |

Also dropped: Players G1 (after G1c was dropped, one stored form answered both remaining queries) and Legal G3 (its remaining query needed the form of a dropped one).
