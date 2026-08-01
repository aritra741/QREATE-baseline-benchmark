# SPP vs DocETL Case Study — Player Workload (60 queries)

Paired comparison on the DocETL Player v7 query set.

- **SPP run:** `output/evaluation.json` (NL workload `case study/docetl_Player_v7/query_manifest_nl.json`), mean accuracy **0.285**
- **DocETL run:** `case study/docetl_Player_v7/`, mean accuracy **0.258**
- **Ground truth:** `Data/Player/*.csv` executed with the reference SQL (owner ages as of **2026-12-31**)

Overall: SPP wins 18 / DocETL wins 14 / ties 28 (threshold ±0.05).

**Aggregation metrics** (`spp/aggregation_metrics.py`) are reported for GROUP BY queries only (`q54`, `q49`, `q12`). Projection/filter cases (`q20`, `q47`, `q16`, `q34`, `q3`) are structure/coverage comparisons under the original macro-F1 accuracy, not Cell-F1@τ.
Full JSON: `case study/SPP_vs_DocETL_aggregation_metrics.json`.

---

## q54 — SPP strength: clean shared aggregate

| Metric | SPP | DocETL |
| --- | --- | --- |
| Accuracy | **0.7453** | **0.2047** |
| Predicted rows | 3 | 3 |
| Gold rows | 3 | 3 |

**Natural language**

> What is the average owner age for each nationality?

**Reference SQL**

```sql
SELECT nationality, AVG(age) AS avg_age FROM owner GROUP BY nationality
```

**SPP compiled SQL**

```sql
SELECT "t2"."nationality", AVG("t2"."age") AS "avg_age"
FROM "owner" AS "t2"
GROUP BY "t2"."nationality"
```

_Owner ages in ground truth were corrected in `Data/Player/owner.csv` to max age in 2026 (as of 2026-12-31). Micky Arison previously had birth year `1949` stored as age._

### Ground truth (3 rows)

| nationality | avg_age |
| --- | --- |
| American | 72.1429 |
| Israeli-American | 77 |
| Taiwanese-Canadian | 62 |

### SPP output (3 rows)

| nationality | avg_age |
| --- | --- |
| American | 72.4 |
| Israeli-American | 75 |
| Taiwanese-Canadian |  |

### DocETL output (3 rows)

| nationality | avg_age |
| --- | --- |
| American | 305.5 |
| Canadian | -1 |
| U.S. | 59 |

---

## q20 — SPP strength: conservative missing values (empty gold)

| Metric | SPP | DocETL |
| --- | --- | --- |
| Accuracy | **1.0000** | **0.0000** |
| Predicted rows | 0 | 6 |
| Gold rows | 0 | 0 |

**Natural language**

> For matched player and team records where the player has fewer than zero NBA championships, show the team's location, the player's NBA championships, the team's name, and the team recorded for the player.

**Reference SQL**

```sql
SELECT team.location, player.nba_championships, team.team_name, player.team FROM player JOIN team ON player.team = team.team_name WHERE player.nba_championships < 0
```

**SPP compiled SQL**

```sql
SELECT "t0"."nba_championships", "t3"."location", "t3"."team_name"
FROM "player" AS "t0"
JOIN "team" AS "t3" ON "t3"."team_name" = "t0"."team"
WHERE "t0"."nba_championships" < 0
```

### Ground truth (0 rows)

_(empty)_

### SPP output (0 rows)

_(empty)_

### DocETL output (6 rows)

| location | nba_championships | team_name | team |
| --- | --- | --- | --- |
| Milwaukee | -1 | Bucks | Bucks |
| Phoenix, Arizona | -1 | Phoenix Suns | Phoenix Suns |
| Los Angeles | -1 | Los Angeles Lakers | Los Angeles Lakers |
| Los Angeles | -1 | Los Angeles Lakers | Los Angeles Lakers |
| Los Angeles | -1 | Los Angeles Lakers | Los Angeles Lakers |
| Phoenix, Arizona | -1 | Phoenix Suns | Phoenix Suns |

---

## q49 — SPP strength: group coverage on COUNT

| Metric | SPP | DocETL |
| --- | --- | --- |
| Accuracy | **0.8606** | **0.1810** |
| Predicted rows | 21 | 3 |
| Gold rows | 23 | 23 |

**Natural language**

> For each nationality, count the players who are named Antonius Cleveland or have at least zero NBA championships.

**Reference SQL**

```sql
SELECT nationality, COUNT(*) AS count_all FROM player WHERE name = 'Antonius Cleveland' OR nba_championships >= 0 GROUP BY nationality
```

**SPP compiled SQL**

```sql
SELECT "t0"."nationality", COUNT(*) AS "count_all"
FROM "player" AS "t0"
WHERE ("t0"."name" >= 'Antonius Cleveland' OR "t0"."nba_championships" >= 0)
GROUP BY "t0"."nationality"
```

### Ground truth (23 rows)

| nationality | count_all |
| --- | --- |
|  | 2 |
| American | 116 |
| American-Chinese | 1 |
| American-Spanish | 1 |
| American-Venezuelan | 1 |
| American-born naturalized Azerbaijani | 1 |
| Bahamian | 1 |
| British | 1 |
| Cameroonian-American | 1 |
| Canadian | 2 |
| Congolese | 1 |
| Croatian | 1 |
| Dominican | 1 |
| Dutch | 1 |
| French | 2 |

_… 8 more rows (total 23)_

### SPP output (21 rows)

| nationality | count_all |
| --- | --- |
|  | 40 |
| American | 53 |
| American-Chinese | 1 |
| American-Venezuelan | 1 |
| American-born naturalized Azerbaijani | 1 |
| Bahamian | 1 |
| British | 1 |
| Cameroonian-American | 1 |
| Canadian | 1 |
| Congolese | 1 |
| Croatian | 1 |
| Dominican | 1 |
| Dutch | 1 |
| French | 2 |
| German | 1 |

_… 6 more rows (total 21)_

### DocETL output (3 rows)

| nationality | count_all |
| --- | --- |
|  | 11 |
| American | 11 |
| Nigerian-American | 1 |

---

## q12 — DocETL strength: SPP groups the wrong entity

| Metric | SPP | DocETL |
| --- | --- | --- |
| Accuracy | **0.0385** | **0.6505** |
| Predicted rows | 3 | 18 |
| Gold rows | 23 | 23 |

**Natural language**

> What is the maximum player age for each nationality?

**Reference SQL**

```sql
SELECT nationality, MAX(age) AS max_age FROM player GROUP BY nationality
```

**SPP compiled SQL**

```sql
SELECT "t2"."nationality", MAX("t0"."age") AS "max_player_age"
FROM "owner" AS "t2"
JOIN "team" AS "t3" ON "t2"."nba_team" = "t3"."team_name"
JOIN "player" AS "t0" ON "t3"."team_name" = "t0"."team"
GROUP BY "t2"."nationality"
```

### Ground truth (23 rows)

| nationality | max_age |
| --- | --- |
|  | 105 |
| American | 106 |
| American-Chinese | 33 |
| American-Spanish | 59 |
| American-Venezuelan | 53 |
| American-born naturalized Azerbaijani | 28 |
| Bahamian | 33 |
| British | 28 |
| Cameroonian-American | 31 |
| Canadian | 74 |
| Congolese | 23 |
| Croatian | 58 |
| Dominican | 39 |
| Dutch | 59 |
| French | 31 |

_… 8 more rows (total 23)_

### SPP output (3 rows)

| nationality | max_player_age |
| --- | --- |
| American | 73 |
| Israeli-American | 36 |
| Taiwanese-Canadian | 32 |

### DocETL output (18 rows)

| nationality | max_age |
| --- | --- |
|  | 1974 |
| American | 1993 |
| Azerbaijan | -1 |
| Bahamian | 31 |
| British | 26 |
| Canadian | -1 |
| Congolese | -1 |
| Croatian | -1 |
| Dominican | -1 |
| Dutch | -1 |
| French | 29 |
| German | 31 |
| Greek | 35 |
| Mexican-American | 22 |
| Nigerian-American | -1 |

_… 3 more rows (total 18)_

---

## q47 — DocETL strength: SPP changes query shape

| Metric | SPP | DocETL |
| --- | --- | --- |
| Accuracy | **0.0000** | **0.4746** |
| Predicted rows | 1 | 29 |
| Gold rows | 30 | 30 |

**Natural language**

> List the team name, founding year, and owner for teams that were founded after 1967, are not the Charlotte Hornets, are the Detroit Pistons, or were founded in 1989 or later.

**Reference SQL**

```sql
SELECT team_name, founded_year, ownership FROM team WHERE founded_year > 1967 OR team_name != 'Charlotte Hornets' OR team_name = 'Detroit Pistons' OR founded_year >= 1989
```

**SPP compiled SQL**

```sql
SELECT "t3"."location", COUNT(*) AS "count_all"
FROM "team" AS "t3"
WHERE (("t3"."founded_year" > 1967 OR "t3"."location" != 'Charlotte Hornets' OR "t3"."location" = 'Detroit Pistons' OR "t3"."founded_year" = 1989) AND "t3"."founded_year" = 1989)
GROUP BY "t3"."location"
```

### Ground truth (30 rows)

| team_name | founded_year | ownership |
| --- | --- | --- |
| Atlanta Hawks | 1946 | Atlanta Spirit LLC |
| Boston Celtics | 1946 |  |
| Brooklyn Nets | 1967 | Joseph Chung-Hsin Tsai |
| Charlotte Hornets | 1988 | Gabe Plotkin and Rick Schnall |
| Chicago Bulls | 1966 | Jerry Michael Reinsdorf |
| Cleveland Cavaliers | 1970 | Daniel Gilbert |
| Dallas Mavericks | 1980 | Mark Cuban |
| Denver Nuggets | 1967 | Enos Stanley Kroenke |
| Detroit Pistons | 1937 | Tom Gores |
| Golden State Warriors | 1946 | Joseph Steven Lacob |
| Houston Rockets | 1967 | Tilman Joseph Fertitta |
| Indiana Pacers | 1967 | Herbert Simon |
| Los Angeles Clippers | 1970 | Steven Anthony Ballmer |
| Los Angeles Lakers | 1946 | Jerry Buss (from 1979) |
| Memphis Grizzlies | 1995 | Robert J. Pera |

_… 15 more rows (total 30)_

### SPP output (1 rows)

| location | count_all |
| --- | --- |
| Minneapolis | 1 |

### DocETL output (29 rows)

| team_name | founded_year | ownership |
| --- | --- | --- |
| Atlanta Hawks | 1946 |  |
| Boston Celtics | 1946 |  |
| Brooklyn Nets | 1967 | Joseph Tsai |
| Charlotte Hornets | 1988 | Michael Jordan |
| Chicago Bulls | 1966 |  |
| Cleveland Cavaliers | 1970 |  |
| Dallas Mavericks | 1980 | Mark Cuban |
| Denver Nuggets | 1967 |  |
| Detroit Pistons | 1937 |  |
| Golden State Warriors | 1946 |  |
| Houston Rockets | 1967 |  |
| Indiana Pacers | 1967 |  |
| Los Angeles Clippers | 1970 |  |
| Los Angeles Lakers | 1947 |  |
| Memphis Grizzlies | 2001 |  |

_… 14 more rows (total 29)_

---

## q16 — DocETL strength: date normalization self-contradiction

| Metric | SPP | DocETL |
| --- | --- | --- |
| Accuracy | **0.0000** | **0.2275** |
| Predicted rows | 0 | 131 |
| Gold rows | 124 | 124 |

**Natural language**

> Show the team, nationality, and MVP awards for players who have fewer than one MVP award or were born on October 2, 1995.

**Reference SQL**

```sql
SELECT team, nationality, mvp_awards FROM player WHERE mvp_awards < 1 OR birth_date = '1995/10/2'
```

**SPP compiled SQL**

```sql
SELECT "t3"."team_name", "t0"."nationality", "t0"."mvp_awards"
FROM "team" AS "t3"
JOIN "player" AS "t0" ON "t3"."team_name" = "t0"."team"
WHERE (("t0"."mvp_awards" < 1 OR "t0"."birth_date" = '1995-10-02') AND "t0"."birth_date" = '1995/10/2')
```

### Ground truth (124 rows)

| team | nationality | mvp_awards |
| --- | --- | --- |
| Lokomotiv Kuban | American | 0 |
| Los Angeles Lakers | American | 0 |
| Cedevita Olimpija | Serbian | 0 |
| Rochester Royals | American | 0 |
| Orlando Magic | American | 0 |
| Bursaspor Basketbol | French | 0 |
| Saski Baskonia | American-born naturalized Azerbaijani | 0 |
| Milwaukee Bucks | American | 0 |
| New Orleans Jazz | American | 0 |
| New Orleans Jazz | American | 0 |
| Sacramento Kings | American | 0 |
| Houston Rockets | American | 0 |
| Guaros de Lara | American-Venezuelan | 0 |
| Melbourne United | American | 0 |
| Santa Cruz Warriors | American | 0 |

_… 109 more rows (total 124)_

### SPP output (0 rows)

_(empty)_

### DocETL output (131 rows)

| team | nationality | mvp_awards |
| --- | --- | --- |
| Lokomotiv Kuban | American | -1 |
|  |  | -1 |
| Cedevita Olimpija | Serbian | -1 |
|  | American | -1 |
|  | American | -1 |
| Bursaspor Basketbol | French | -1 |
|  |  | -1 |
|  | American | -1 |
| Texas Western Miners | American | -1 |
| Boston Celtics | American | -1 |
| Sacramento Kings | American | -1 |
|  | American | -1 |
|  | American-Venezuelan | -1 |
| Cleveland Cavaliers | American | -1 |
|  | American | -1 |

_… 116 more rows (total 131)_

---

## q34 — DocETL strength: unnecessary JOIN/GROUP BY on projection

| Metric | SPP | DocETL |
| --- | --- | --- |
| Accuracy | **0.0460** | **0.5833** |
| Predicted rows | 13 | 16 |
| Gold rows | 16 | 16 |

**Natural language**

> List every owner's NBA team, name, and team acquisition year.

**Reference SQL**

```sql
SELECT nba_team, name, own_year FROM owner
```

**SPP compiled SQL**

```sql
SELECT "t2"."nba_team", "t3"."team_name", "t2"."name", "t2"."own_year"
FROM "owner" AS "t2"
JOIN "team" AS "t3" ON "t2"."nba_team" = "t3"."team_name"
GROUP BY "t2"."nba_team", "t3"."team_name"
```

### Ground truth (16 rows)

| nba_team | name | own_year |
| --- | --- | --- |
| Detroit Pistons | Tom Gores | 2011 |
| Cleveland Cavaliers | Daniel Gilbert |  |
| Los Angeles Clippers | Steven Anthony Ballmer |  |
| Orlando Magic | Daniel G. DeVos | 1991 |
| Dallas Mavericks | Mark Cuban | 2000 |
| Houston Rockets | Tilman Joseph Fertitta | 2017 |
| Brooklyn Nets | Joseph Chung-Hsin Tsai | 2019 |
| Oklahoma City Thunder | Clay Bennett | 2006 |
| Indiana Pacers | Herbert Simon | 1983 |
| Chicago Bulls | Jerry Michael Reinsdorf | 1985 |
| New Orleans Pelicans | Gayle Marie LaJaunie Bird Benson | 2018 |
| Denver Nuggets | Enos Stanley Kroenke |  |
| Philadelphia 76ers | Joshua Jordan Harris | 2011 |
| New York Knicks | James Lawrence Dolan |  |
| Miami Heat | Micky Arison | 1995 |
| Golden State Warriors | Joseph Steven Lacob | 2010 |

### SPP output (13 rows)

| nba_team | team_name | name | own_year |
| --- | --- | --- | --- |
| Brooklyn Nets | Brooklyn Nets | Joe Lacob Joseph Steven Lacob | 2017 |
| Chicago Bulls | Chicago Bulls | Jerry Michael Reinsdorf | 2009 |
| Cleveland Cavaliers | Cleveland Cavaliers | Cleveland Clinic | 2005 |
| Dallas Mavericks | Dallas Mavericks | Mark Cuban | 2023 |
| Denver Nuggets | Denver Nuggets | Stan Kroenke | 2008 |
| Golden State Warriors | Golden State Warriors | Joe Lacob Joseph Steven Lacob | 2010 |
| Houston Rockets | Houston Rockets | Atlanta Spirit LLC | 2017 |
| Indiana Pacers | Indiana Pacers | Herb Simon via Pacers Sports & Entertainment (PS&E) | 1983 |
| Los Angeles Clippers | Los Angeles Clippers | Atlanta Spirit LLC | 2024 |
| Miami Heat | Miami Heat | Micky Arison | 1995 |
| New Orleans Pelicans | New Orleans Pelicans | Clayton Ike Bennett | 2018 |
| New York Knicks | New York Knicks |  | 1994 |
| Orlando Magic | Orlando Magic | Cleveland Clinic | 1991 |

### DocETL output (16 rows)

| nba_team | name | own_year |
| --- | --- | --- |
| Detroit Pistons |  | 2011 |
| Cleveland Cavaliers |  | 2005 |
| Los Angeles Clippers |  | 2014 |
| Orlando Magic |  | 1991 |
| Dallas Mavericks | Mark Cuban | 2011 |
| Houston Rockets |  | 2017 |
| Brooklyn Nets |  | 2019 |
| Oklahoma City Thunder |  | 2006 |
| Indiana Pacers |  | 1983 |
| Chicago Bulls |  | 1985 |
| New Orleans Pelicans |  | 2018 |
| Denver Nuggets |  | -1 |
| Philadelphia 76ers |  | 2011 |
| New York Knicks |  | -1 |
| Miami Heat |  | 1995 |
| Golden State Warriors |  | 2010 |

---

## q3 — Shared weakness: wide OR filter

| Metric | SPP | DocETL |
| --- | --- | --- |
| Accuracy | **0.0969** | **0.3210** |
| Predicted rows | 35 | 133 |
| Gold rows | 137 | 137 |

**Natural language**

> List the position, nationality, and Olympic gold medals of every player who is not a frontcourt player, was drafted after pick 5, has fewer than zero Olympic gold medals, or has no MVP awards.

**Reference SQL**

```sql
SELECT position, nationality, olympic_gold_medals FROM player WHERE position != 'Frontcourt' OR draft_pick > 5 OR olympic_gold_medals < 0 OR mvp_awards = 0
```

**SPP compiled SQL**

```sql
SELECT "t0"."name", "t0"."position", "t0"."nationality", "t0"."olympic_gold_medals"
FROM "player" AS "t0"
WHERE ("t0"."draft_pick" > 5 OR "t0"."olympic_gold_medals" < 0)
GROUP BY "t0"."name"
```

### Ground truth (137 rows)

| position | nationality | olympic_gold_medals |
| --- | --- | --- |
|  | American | 0 |
| Frontcourt | American | 0 |
| Backcourt | Serbian | 0 |
|  | American | 0 |
| Backcourt | American | 0 |
| Backcourt | French | 0 |
|  | American-born naturalized Azerbaijani | 0 |
|  | American | 0 |
| Frontcourt | American | 0 |
| Frontcourt | American | 0 |
| Frontcourt | American | 0 |
|  | American | 0 |
| Backcourt | American-Venezuelan | 0 |
| Backcourt | American | 0 |
| Backcourt | American | 0 |

_… 122 more rows (total 137)_

### SPP output (35 rows)

| name | position | nationality | olympic_gold_medals |
| --- | --- | --- | --- |
|  | Point Guard | American | 6 |
| Al Horford |  | American | 2 |
| Andre Drummond |  | American | 1 |
| Anthony Avent |  | American |  |
| Bam Edrice Femi Adebayo |  | American | 2 |
| Brandan Keith Wright |  |  |  |
| Buddy Hield |  | Bahamian |  |
| Carrick Felix Carrick Felix |  | American |  |
| Darnell Hillman | Forward | American |  |
| Dennis Schröder |  | Greek | 0 |
| Dino Rađa |  | Croatian |  |
| Draymond Jamal Green | Forward | American | 2 |
| Erazem Lorbek | Power forward | Slovenian |  |
| Garfield Smith |  | American |  |
| Jabari Dominic Walker |  | American |  |

_… 20 more rows (total 35)_

### DocETL output (133 rows)

| position | nationality | olympic_gold_medals |
| --- | --- | --- |
|  | American | -1 |
| forward | American | -1 |
| point guard | Serbian | -1 |
|  | American | -1 |
| point guard | American | 2 |
|  | French | -1 |
|  |  | -1 |
|  | American | -1 |
| center | American | -1 |
| power forward/center | American | -1 |
| forward | American | -1 |
| power forward | American | -1 |
| shooting guard | American-Venezuelan | -1 |
| shooting guard | American | -1 |
|  | American | -1 |

### Aggregation metrics (new evaluator)

| | SPP | DocETL |
| --- | --- | --- |
| Cell-F1@τ (0.01 / 0.05 / 0.20) | 0.333 / 0.667 / 0.667 | 0.000 / 0.000 / 0.000 |
| Row exact P / R / F1 | 1.000 / 1.000 / 1.000 | 0.333 / 0.333 / 0.333 |
| Row normalized P / R / F1 | 1.000 / 1.000 / 1.000 | 0.333 / 0.333 / 0.333 |
| Row semantic P / R / F1 | 1.000 / 1.000 / 1.000 | 0.333 / 0.333 / 0.333 |
| Pass@τ (with Row_Recall) | 0.500 / 1.000 / 1.000 (R=1.000) | 0.000 / 0.000 / 0.000 (R=0.333) |
| Rel-err histogram | ≤1% 50%, 1–5% 50%, 5–20% 0%, 20–100% 0%, >100% 0% | ≤1% 0%, 1–5% 0%, 5–20% 0%, 20–100% 0%, >100% 100% |
| Frac catastrophic (rel_err>1) | 0.000 | 1.000 |
| Merge / Split rate | 0.000 / 0.000 | 0.000 / 0.000 |

### Aggregation metrics (new evaluator)

| | SPP | DocETL |
| --- | --- | --- |
| Cell-F1@τ (0.01 / 0.05 / 0.20) | 0.773 / 0.773 / 0.773 | 0.077 / 0.077 / 0.077 |
| Row exact P / R / F1 | 0.905 / 0.826 / 0.864 | 1.000 / 0.130 / 0.231 |
| Row normalized P / R / F1 | 0.905 / 0.826 / 0.864 | 1.000 / 0.130 / 0.231 |
| Row semantic P / R / F1 | 0.952 / 0.870 / 0.909 | 1.000 / 0.130 / 0.231 |
| Pass@τ (with Row_Recall) | 0.895 / 0.895 / 0.895 (R=0.870) | 0.333 / 0.333 / 0.333 (R=0.130) |
| Rel-err histogram | ≤1% 89%, 1–5% 0%, 5–20% 0%, 20–100% 11%, >100% 0% | ≤1% 33%, 1–5% 0%, 5–20% 0%, 20–100% 33%, >100% 33% |
| Frac catastrophic (rel_err>1) | 0.000 | 0.333 |
| Merge / Split rate | 0.048 / 0.000 | 0.000 / 0.000 |

### Aggregation metrics (new evaluator)

| | SPP | DocETL |
| --- | --- | --- |
| Cell-F1@τ (0.01 / 0.05 / 0.20) | 0.000 / 0.000 / 0.000 | 0.049 / 0.146 / 0.390 |
| Row exact P / R / F1 | 0.333 / 0.043 / 0.077 | 0.889 / 0.696 / 0.780 |
| Row normalized P / R / F1 | 0.333 / 0.043 / 0.077 | 0.889 / 0.696 / 0.780 |
| Row semantic P / R / F1 | 0.333 / 0.043 / 0.077 | 0.889 / 0.696 / 0.780 |
| Pass@τ (with Row_Recall) | 0.000 / 0.000 / 0.000 (R=0.043) | 0.062 / 0.188 / 0.500 (R=0.696) |
| Rel-err histogram | ≤1% 0%, 1–5% 0%, 5–20% 0%, 20–100% 100%, >100% 0% | ≤1% 6%, 1–5% 12%, 5–20% 31%, 20–100% 0%, >100% 50% |
| Frac catastrophic (rel_err>1) | 0.000 | 0.500 |
| Merge / Split rate | 0.000 / 0.000 | 0.000 / 0.000 |

_… 118 more rows (total 133)_

---
