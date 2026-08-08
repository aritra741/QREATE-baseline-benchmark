#!/usr/bin/env python3
"""Author and validate four Player case-study workloads (20 queries each).

Contrasts with the existing agg20 set (mostly single-table GROUP BY, few joins):
  - player_join20:      join depth is the main axis (1 / 2 / 3 joins)
  - player_groupby20:   GROUP BY variety (single, multi-column, joined keys)
  - player_multiagg20:  multiple aggregates + HAVING in one SELECT
  - player_filterjoin20: selective filters with light joins / light aggs
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAYER_DIR = ROOT / "Query" / "Player"
OUT_ROOT = Path(__file__).resolve().parent / "workloads"


def load_sqlite() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")

    def num(value: str):
        text = (value or "").strip().replace(",", "").replace(" ", "")
        if text == "":
            return None
        try:
            return float(text)
        except ValueError:
            return None

    player_rows = list(csv.DictReader(open(PLAYER_DIR / "player.csv", encoding="utf-8")))
    team_rows = list(csv.DictReader(open(PLAYER_DIR / "team.csv", encoding="utf-8")))
    owner_rows = list(csv.DictReader(open(PLAYER_DIR / "owner.csv", encoding="utf-8")))
    city_rows = list(csv.DictReader(open(PLAYER_DIR / "city.csv", encoding="utf-8")))

    conn.execute(
        """
        CREATE TABLE player (
          name TEXT, birth_date TEXT, nationality TEXT, age REAL, team TEXT, position TEXT,
          draft_pick REAL, draft_year REAL, college TEXT, nba_championships REAL,
          mvp_awards REAL, olympic_gold_medals REAL, fiba_world_cup REAL, id TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO player VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                r["name"].strip(),
                r["birth_date"].strip(),
                r["nationality"].strip(),
                num(r["age"]),
                r["team"].strip(),
                r["position"].strip(),
                num(r["draft_pick"]),
                num(r["draft_year"]),
                r["college"].strip(),
                num(r["nba_championships"]),
                num(r["mvp_awards"]),
                num(r["olympic_gold_medals"]),
                num(r["fiba_world_cup"]),
                r["id"].strip(),
            )
            for r in player_rows
        ],
    )

    conn.execute(
        """
        CREATE TABLE team (
          team_name TEXT, founded_year REAL, location TEXT, ownership TEXT, championship REAL, id TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO team VALUES (?,?,?,?,?,?)",
        [
            (
                r["team_name"].strip(),
                num(r["founded_year"]),
                r["location"].strip(),
                r["ownership"].strip(),
                num(r["championship"]),
                r["id"].strip(),
            )
            for r in team_rows
        ],
    )

    conn.execute(
        """
        CREATE TABLE owner (
          name TEXT, age REAL, nationality TEXT, nba_team TEXT, own_year REAL, id TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO owner VALUES (?,?,?,?,?,?)",
        [
            (
                r["name"].strip(),
                num(r["age"]),
                r["nationality"].strip(),
                r["nba_team"].strip(),
                num(r["own_year"]),
                r["id"].strip(),
            )
            for r in owner_rows
        ],
    )

    conn.execute(
        """
        CREATE TABLE city (
          city_name TEXT, state_name TEXT, population REAL, area REAL, gdp REAL, id TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO city VALUES (?,?,?,?,?,?)",
        [
            (
                r["city_name"].strip(),
                r["state_name"].strip(),
                num(r["population"]),
                num(r["area"]),
                num(r["gdp"]),
                r["id"].strip(),
            )
            for r in city_rows
        ],
    )
    return conn


def finalize_sql(sql: str) -> str:
    """Apply the benchmark's explicit key-normalization policy.

    The source CSV contains padded names plus two team/city aliases. Keeping
    this policy in one place makes every generated workload use the same join
    semantics instead of silently losing rows for formatting differences.
    """
    return (
        sql.replace("p.team = t.team_name", "TRIM(p.team) = TRIM(t.team_name)")
        .replace("t.team_name = o.nba_team", "TRIM(t.team_name) = TRIM(o.nba_team)")
        .replace("t.location = c.city_name", "c.city_name = CASE t.location WHEN 'Brooklyn' THEN 'New York City' WHEN 'Washington' THEN 'Washington, D.C.' ELSE t.location END")
    )


def validate(conn: sqlite3.Connection) -> list[str]:
    errors: list[str] = []
    for name, spec in WORKLOADS.items():
        assert len(spec["queries"]) == 20, name
        seen_ids: set[str] = set()
        seen_sql: set[str] = set()
        for qid, sql, text in spec["queries"]:
            sql = finalize_sql(sql)
            if qid in seen_ids:
                errors.append(f"{name}/{qid}: duplicate query id")
            seen_ids.add(qid)
            fingerprint = re.sub(r"\s+", " ", sql.lower()).strip()
            if fingerprint in seen_sql:
                errors.append(f"{name}/{qid}: duplicate SQL")
            seen_sql.add(fingerprint)
            if not text.strip():
                errors.append(f"{name}/{qid}: empty natural-language question")
            if re.search(
                r"(championship|mvp_awards|olympic_gold_medals|fiba_world_cup)\s*>=\s*0\b",
                sql,
                re.IGNORECASE,
            ):
                errors.append(f"{name}/{qid}: tautological nonnegative filter")
            if re.search(r"HAVING\s+COUNT\([^)]*\)\s*>=\s*1\b", sql, re.IGNORECASE):
                errors.append(f"{name}/{qid}: tautological HAVING COUNT >= 1")
            if re.search(r"\bgdp\b", sql, re.IGNORECASE):
                errors.append(f"{name}/{qid}: GDP is not unit-normalized in the source data")
            try:
                cursor = conn.execute(sql)
                rows = cursor.fetchall()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{name}/{qid}: {exc}\n  SQL: {sql}")
                continue
            if len(rows) == 0:
                errors.append(f"{name}/{qid}: empty result")
            if len(rows) == 1 and "GROUP BY" in sql.upper():
                errors.append(f"{name}/{qid}: GROUP BY produces only one group")
            group_match = re.search(
                r"\bGROUP BY\s+(.+?)(?:\bHAVING\b|$)", sql, re.IGNORECASE
            )
            column_names = [item[0].lower() for item in cursor.description or []]
            count_indexes = [
                index for index, column in enumerate(column_names) if "count" in column
            ]
            if (
                group_match
                and "," in group_match.group(1)
                and len(rows) >= 3
                and count_indexes
                and any(all(row[index] == 1 for row in rows) for index in count_indexes)
            ):
                errors.append(
                    f"{name}/{qid}: multi-column GROUP BY only reproduces singleton rows"
                )
    return errors



# Join convention for owner: owner.nba_team = team.team_name
# (team.ownership names do not align with owner.name in this CSV.)


WORKLOADS: dict[str, dict] = {
    "player_join20": {
        "title": "Join-depth workload",
        "focus": "1–3 table joins; aggregation is light and secondary",
        "queries": [
            # --- 1 join (player–team) ---
            (
                "q0",
                "SELECT t.team_name, COUNT(p.id) AS player_count FROM team t LEFT JOIN player p ON TRIM(p.team) = TRIM(t.team_name) GROUP BY t.team_name",
                "How many players are on each NBA team?",
            ),
            (
                "q1",
                "SELECT t.location, AVG(p.age) AS avg_player_age FROM player p JOIN team t ON p.team = t.team_name GROUP BY t.location",
                "What is the average player age for NBA teams in each city?",
            ),
            (
                "q2",
                "SELECT t.founded_year, COUNT(*) AS player_count FROM player p JOIN team t ON p.team = t.team_name GROUP BY t.founded_year",
                "How many players are on NBA teams founded in each year?",
            ),
            (
                "q3",
                "SELECT t.championship, AVG(p.mvp_awards) AS avg_mvp FROM player p JOIN team t ON p.team = t.team_name GROUP BY t.championship",
                "For each team championship total, what is the average career MVP-award count among players on those teams?",
            ),
            (
                "q4",
                "SELECT p.position, COUNT(DISTINCT t.team_name) AS titled_team_count FROM player p JOIN team t ON TRIM(p.team) = TRIM(t.team_name) WHERE p.position IN ('Frontcourt', 'Backcourt') AND t.championship >= 1 GROUP BY p.position",
                "For Frontcourt and Backcourt players separately, how many championship-winning NBA teams are represented?",
            ),
            # --- 1 join (team–city) ---
            (
                "q5",
                "SELECT c.state_name, COUNT(*) AS team_count FROM team t JOIN city c ON t.location = c.city_name WHERE c.state_name != '' GROUP BY c.state_name",
                "How many NBA teams are based in each state?",
            ),
            (
                "q6",
                "SELECT c.state_name, AVG(t.championship) AS avg_titles FROM team t JOIN city c ON t.location = c.city_name WHERE c.state_name != '' GROUP BY c.state_name",
                "What is the average number of championships for NBA teams in each state?",
            ),
            (
                "q7",
                "SELECT c.state_name, MAX(c.population) AS max_city_population FROM team t JOIN city c ON t.location = c.city_name WHERE c.state_name != '' GROUP BY c.state_name",
                "Among cities that host an NBA team, what is the largest city population in each state?",
            ),
            # --- 1 join (team–owner via nba_team) ---
            (
                "q8",
                "SELECT o.nationality, COUNT(*) AS team_count FROM team t JOIN owner o ON t.team_name = o.nba_team WHERE o.nationality != '' GROUP BY o.nationality",
                "How many NBA teams are owned by owners of each nationality?",
            ),
            (
                "q9",
                "SELECT o.nationality, AVG(t.championship) AS avg_titles FROM team t JOIN owner o ON t.team_name = o.nba_team WHERE o.nationality != '' GROUP BY o.nationality",
                "For each owner nationality, what is the average number of championships among their NBA teams?",
            ),
            # --- 2 joins (player–team–city) ---
            (
                "q10",
                "SELECT c.state_name, COUNT(*) AS player_count FROM player p JOIN team t ON p.team = t.team_name JOIN city c ON t.location = c.city_name WHERE c.state_name != '' GROUP BY c.state_name",
                "How many players are on NBA teams based in each state?",
            ),
            (
                "q11",
                "SELECT c.state_name, AVG(p.nba_championships) AS avg_player_titles FROM player p JOIN team t ON TRIM(p.team) = TRIM(t.team_name) JOIN city c ON c.city_name = CASE t.location WHEN 'Brooklyn' THEN 'New York City' WHEN 'Washington' THEN 'Washington, D.C.' ELSE t.location END WHERE p.nba_championships IS NOT NULL AND c.state_name != '' GROUP BY c.state_name",
                "Among players with a known career championship total, what is the average for NBA teams in each state?",
            ),
            (
                "q12",
                "SELECT c.city_name, SUM(p.mvp_awards) AS total_mvp FROM player p JOIN team t ON p.team = t.team_name JOIN city c ON t.location = c.city_name WHERE p.mvp_awards >= 1 GROUP BY c.city_name",
                "Among players with at least one MVP award, what is the total MVP count for players whose teams are based in each city?",
            ),
            (
                "q13",
                "SELECT c.state_name, MIN(p.draft_pick) AS earliest_pick FROM player p JOIN team t ON p.team = t.team_name JOIN city c ON t.location = c.city_name WHERE p.draft_pick > 0 AND c.state_name != '' GROUP BY c.state_name",
                "For each state, what is the lowest draft pick among drafted players on NBA teams based there?",
            ),
            # --- 2 joins (player–team–owner) ---
            (
                "q14",
                "SELECT o.name, COUNT(p.id) AS player_count FROM owner o LEFT JOIN team t ON TRIM(t.team_name) = TRIM(o.nba_team) LEFT JOIN player p ON TRIM(p.team) = TRIM(t.team_name) GROUP BY o.name",
                "How many players are on each owner's NBA team?",
            ),
            (
                "q15",
                "SELECT o.nationality, AVG(p.age) AS avg_player_age FROM player p JOIN team t ON p.team = t.team_name JOIN owner o ON t.team_name = o.nba_team WHERE o.nationality != '' GROUP BY o.nationality",
                "What is the average player age on teams owned by owners of each nationality?",
            ),
            (
                "q16",
                "SELECT o.name, MAX(p.nba_championships) AS max_player_titles FROM owner o LEFT JOIN team t ON TRIM(t.team_name) = TRIM(o.nba_team) LEFT JOIN player p ON TRIM(p.team) = TRIM(t.team_name) GROUP BY o.name",
                "For each owner, what is the highest career NBA-championship total among players on their team?",
            ),
            # --- 3 joins (player–team–owner–city) ---
            (
                "q17",
                "SELECT c.state_name, COUNT(*) AS player_count FROM player p JOIN team t ON p.team = t.team_name JOIN owner o ON t.team_name = o.nba_team JOIN city c ON t.location = c.city_name WHERE c.state_name != '' GROUP BY c.state_name",
                "Among players on NBA teams with known ownership, how many play for teams based in each state?",
            ),
            (
                "q18",
                "SELECT o.nationality, c.state_name, COUNT(*) AS player_count FROM player p JOIN team t ON p.team = t.team_name JOIN owner o ON t.team_name = o.nba_team JOIN city c ON t.location = c.city_name WHERE o.nationality != '' AND c.state_name != '' GROUP BY o.nationality, c.state_name",
                "For each owner nationality and team state, how many players are on those teams?",
            ),
            (
                "q19",
                "SELECT c.state_name, AVG(p.olympic_gold_medals) AS avg_olympic_golds FROM player p JOIN team t ON p.team = t.team_name JOIN owner o ON t.team_name = o.nba_team JOIN city c ON t.location = c.city_name WHERE p.olympic_gold_medals >= 1 AND c.state_name != '' GROUP BY c.state_name",
                "Among players with at least one Olympic gold medal on teams that have a known owner, what is the average gold-medal count for players whose teams are based in each state?",
            ),
        ],
    },
    "player_groupby20": {
        "title": "Group-by variety workload",
        "focus": "Diverse GROUP BY keys, including multi-column groupings",
        "queries": [
            (
                "q0",
                "SELECT position, CASE WHEN age < 30 THEN 'under_30' WHEN age < 40 THEN '30s' ELSE '40_or_older' END AS age_band, COUNT(*) AS player_count FROM player WHERE position IN ('Frontcourt', 'Backcourt') AND age IS NOT NULL GROUP BY position, age_band",
                "For Frontcourt and Backcourt players separately, how many are under 30, in their 30s, or age 40 and older?",
            ),
            (
                "q1",
                "SELECT college, position, AVG(age) AS avg_age FROM player WHERE college != '' AND position IN ('Frontcourt', 'Backcourt') GROUP BY college, position HAVING COUNT(*) >= 2",
                "For each college-position combination represented by at least two players, what is the average player age?",
            ),
            (
                "q2",
                "SELECT CAST(draft_year / 5 AS INTEGER) * 5 AS draft_cohort, position, COUNT(*) AS player_count FROM player WHERE draft_year > 2000 AND position IN ('Frontcourt', 'Backcourt') GROUP BY draft_cohort, position",
                "For each five-year draft cohort after 2000 and for Frontcourt and Backcourt separately, how many players were drafted?",
            ),
            (
                "q3",
                "SELECT CASE WHEN TRIM(nationality) = 'American' THEN 'American' ELSE 'International' END AS nationality_group, CAST(draft_year / 10 AS INTEGER) * 10 AS draft_decade, COUNT(*) AS player_count FROM player WHERE nationality != '' AND draft_year > 0 GROUP BY nationality_group, draft_decade",
                "For American and international players separately, how many were drafted in each decade?",
            ),
            (
                "q4",
                "SELECT t.team_name, p.position, COUNT(*) AS player_count FROM player p JOIN team t ON TRIM(p.team) = TRIM(t.team_name) WHERE p.position IN ('Frontcourt', 'Backcourt') GROUP BY t.team_name, p.position",
                "For each NBA team, how many players are Frontcourt and how many are Backcourt?",
            ),
            (
                "q5",
                "SELECT position, CASE WHEN draft_pick BETWEEN 1 AND 14 THEN 'lottery' WHEN draft_pick BETWEEN 15 AND 30 THEN 'later_first_round' WHEN draft_pick > 30 THEN 'later_pick' ELSE 'undrafted_or_unknown' END AS draft_band, COUNT(*) AS player_count FROM player WHERE position IN ('Frontcourt', 'Backcourt') GROUP BY position, draft_band",
                "For Frontcourt and Backcourt players separately, how many fall into the lottery, later first-round, later-pick, and undrafted-or-unknown draft bands?",
            ),
            (
                "q6",
                "SELECT position, COUNT(*) AS player_count FROM player WHERE position IN ('Frontcourt', 'Backcourt') GROUP BY position",
                "How many players are at each position?",
            ),
            (
                "q7",
                "SELECT draft_year, COUNT(*) AS player_count FROM player WHERE draft_year BETWEEN 1990 AND 2010 GROUP BY draft_year",
                "How many players were drafted in each year from 1990 through 2010?",
            ),
            (
                "q8",
                "SELECT college, COUNT(*) AS player_count FROM player WHERE college != '' GROUP BY college HAVING COUNT(*) >= 2",
                "Which colleges are represented by at least two players, and how many players came from each?",
            ),
            (
                "q9",
                "SELECT team, COUNT(*) AS player_count FROM player WHERE team != '' GROUP BY team",
                "How many players are on each team?",
            ),
            (
                "q10",
                "SELECT position, CASE WHEN nba_championships >= 1 THEN 'has_championship' WHEN nba_championships = 0 THEN 'no_championship' ELSE 'unknown' END AS championship_status, COUNT(*) AS player_count FROM player WHERE position IN ('Frontcourt', 'Backcourt') GROUP BY position, championship_status",
                "For Frontcourt and Backcourt players separately, how many have at least one NBA championship, none, or an unknown championship count?",
            ),
            (
                "q11",
                "SELECT CAST(founded_year / 10 AS INTEGER) * 10 AS founded_decade, CASE WHEN championship >= 1 THEN 'has_title' ELSE 'no_title' END AS title_status, COUNT(*) AS team_count FROM team WHERE founded_year > 0 GROUP BY founded_decade, title_status",
                "For each founding decade, how many NBA teams have won at least one championship versus none?",
            ),
            (
                "q12",
                "SELECT founded_year, COUNT(*) AS team_count FROM team WHERE founded_year >= 1970 GROUP BY founded_year",
                "How many teams were founded in each year from 1970 onward?",
            ),
            (
                "q13",
                "SELECT position, CASE WHEN mvp_awards >= 1 THEN 'mvp_winner' ELSE 'no_mvp' END AS mvp_status, COUNT(*) AS player_count FROM player WHERE position IN ('Frontcourt', 'Backcourt') GROUP BY position, mvp_status",
                "For Frontcourt and Backcourt players separately, how many have won at least one MVP award versus none?",
            ),
            (
                "q14",
                "SELECT nationality, CAST(own_year / 10 AS INTEGER) * 10 AS acquisition_decade, COUNT(*) AS owner_count FROM owner WHERE nationality != '' AND own_year > 0 GROUP BY nationality, acquisition_decade",
                "For each owner nationality and acquisition decade, how many owners acquired their team then?",
            ),
            (
                "q15",
                "SELECT p.team, p.nationality, COUNT(*) AS player_count FROM player p JOIN team t ON p.team = t.team_name WHERE p.nationality != '' GROUP BY p.team, p.nationality",
                "For each NBA team and player nationality, how many players are there?",
            ),
            (
                "q16",
                "SELECT t.location, p.position, COUNT(*) AS player_count FROM player p JOIN team t ON p.team = t.team_name WHERE p.position IN ('Frontcourt', 'Backcourt') AND t.location != '' GROUP BY t.location, p.position",
                "For each NBA team city and player position, how many players are there?",
            ),
            (
                "q17",
                "SELECT c.state_name, p.position, COUNT(*) AS player_count FROM player p JOIN team t ON p.team = t.team_name JOIN city c ON t.location = c.city_name WHERE p.position IN ('Frontcourt', 'Backcourt') AND c.state_name != '' GROUP BY c.state_name, p.position",
                "For each state and player position, how many players are on NBA teams based there?",
            ),
            (
                "q18",
                "SELECT c.state_name, CASE WHEN p.draft_pick BETWEEN 1 AND 14 THEN 'lottery' WHEN p.draft_pick BETWEEN 15 AND 30 THEN 'later_first_round' WHEN p.draft_pick > 30 THEN 'later_pick' ELSE 'undrafted_or_unknown' END AS draft_band, COUNT(*) AS player_count FROM player p JOIN team t ON TRIM(p.team) = TRIM(t.team_name) JOIN city c ON c.city_name = CASE t.location WHEN 'Brooklyn' THEN 'New York City' WHEN 'Washington' THEN 'Washington, D.C.' ELSE t.location END WHERE c.state_name != '' GROUP BY c.state_name, draft_band",
                "For each state, how many players on NBA teams based there fall into each draft-pick band?",
            ),
            (
                "q19",
                "SELECT o.nationality, p.position, COUNT(*) AS player_count FROM player p JOIN team t ON p.team = t.team_name JOIN owner o ON t.team_name = o.nba_team WHERE p.position IN ('Frontcourt', 'Backcourt') AND o.nationality != '' GROUP BY o.nationality, p.position",
                "For each owner nationality and player position, how many players are on those owners' teams?",
            ),
        ],
    },
    "player_multiagg20": {
        "title": "Multi-aggregation workload",
        "focus": "Several aggregates (and often HAVING) in the same query",
        "queries": [
            (
                "q0",
                "SELECT position, COUNT(*) AS player_count, AVG(age) AS avg_age, MAX(age) AS max_age FROM player WHERE position IN ('Frontcourt', 'Backcourt') GROUP BY position",
                "For each position, how many players are there, and what are their average and maximum ages?",
            ),
            (
                "q1",
                "SELECT nationality, COUNT(*) AS player_count, AVG(nba_championships) AS avg_titles, SUM(nba_championships) AS total_titles FROM player WHERE nationality != '' AND nba_championships IS NOT NULL GROUP BY nationality HAVING COUNT(*) >= 2",
                "Among nationalities with at least two players whose championship totals are known, what are the player count, average championships, and total championships?",
            ),
            (
                "q2",
                "SELECT college, COUNT(*) AS player_count, MAX(mvp_awards) AS max_mvp, SUM(mvp_awards) AS total_mvp FROM player WHERE college != '' AND mvp_awards IS NOT NULL GROUP BY college HAVING COUNT(*) >= 2 AND SUM(mvp_awards) >= 1",
                "Among colleges represented by at least two players whose combined MVP total is at least one, what are the player count, highest individual MVP total, and combined MVP total?",
            ),
            (
                "q3",
                "SELECT draft_year, COUNT(*) AS player_count, AVG(draft_pick) AS avg_pick, MIN(draft_pick) AS best_pick FROM player WHERE draft_year > 2010 AND draft_pick > 0 GROUP BY draft_year",
                "For each draft year after 2010, among players whose draft pick is known, how many are there and what are the average and best (lowest) picks?",
            ),
            (
                "q4",
                "SELECT t.team_name, COUNT(*) AS player_count, AVG(p.age) AS avg_age, SUM(CASE WHEN p.olympic_gold_medals IS NOT NULL THEN p.olympic_gold_medals ELSE 0 END) AS total_recorded_olympic_golds FROM player p JOIN team t ON TRIM(p.team) = TRIM(t.team_name) GROUP BY t.team_name HAVING COUNT(*) >= 2",
                "Among NBA teams with at least two players, what are the player count, average age, and total Olympic gold medals?",
            ),
            (
                "q5",
                "SELECT position, COUNT(*) AS player_count, AVG(mvp_awards) AS avg_mvp, AVG(nba_championships) AS avg_titles FROM player WHERE position IN ('Frontcourt', 'Backcourt') AND mvp_awards IS NOT NULL AND nba_championships IS NOT NULL GROUP BY position",
                "For Frontcourt and Backcourt players whose MVP and championship totals are known, what are the player count and average values for both metrics?",
            ),
            (
                "q6",
                "SELECT nationality, COUNT(*) AS player_count, MIN(age) AS youngest, MAX(age) AS oldest FROM player WHERE nationality != '' AND age BETWEEN 20 AND 45 GROUP BY nationality HAVING COUNT(*) > 1",
                "Among nationalities with more than one player aged 20 to 45, what are the count and the youngest and oldest ages?",
            ),
            (
                "q7",
                "SELECT college, COUNT(*) AS champion_count, AVG(age) AS avg_age, MAX(nba_championships) AS max_titles FROM player WHERE nba_championships >= 1 AND college != '' GROUP BY college HAVING COUNT(*) >= 2",
                "For colleges represented by at least two championship-winning players, what are their count, average age, and highest individual championship total?",
            ),
            (
                "q8",
                "SELECT c.state_name, COUNT(*) AS team_count, AVG(t.championship) AS avg_titles, MAX(t.championship) AS max_titles, MIN(t.founded_year) AS earliest_founded FROM team t JOIN city c ON c.city_name = CASE t.location WHEN 'Brooklyn' THEN 'New York City' WHEN 'Washington' THEN 'Washington, D.C.' ELSE t.location END WHERE c.state_name != '' GROUP BY c.state_name",
                "For each state, how many NBA teams are based there, and what are their average and maximum championship totals and earliest founding year?",
            ),
            (
                "q9",
                "SELECT CAST(founded_year / 10 AS INTEGER) * 10 AS founded_decade, COUNT(*) AS team_count, SUM(championship) AS total_titles, AVG(championship) AS avg_titles, MIN(founded_year) AS earliest_founded FROM team WHERE founded_year > 0 GROUP BY founded_decade",
                "For each team-founding decade, what are the team count, total and average championships, and earliest founding year?",
            ),
            (
                "q10",
                "SELECT state_name, COUNT(*) AS city_count, AVG(population) AS avg_population, MAX(population) AS max_population, SUM(area) AS total_area FROM city WHERE state_name != '' AND population IS NOT NULL AND area IS NOT NULL GROUP BY state_name HAVING COUNT(*) >= 2",
                "For states represented by at least two cities with known population and area, what are the city count, average and maximum population, and total city area?",
            ),
            (
                "q11",
                "SELECT CAST(o.own_year / 10 AS INTEGER) * 10 AS acquisition_decade, COUNT(*) AS owner_count, AVG(t.championship) AS avg_team_titles, MIN(o.own_year) AS earliest_acquisition, MAX(o.own_year) AS latest_acquisition FROM owner o JOIN team t ON TRIM(t.team_name) = TRIM(o.nba_team) WHERE o.own_year > 0 GROUP BY acquisition_decade",
                "For each team-acquisition decade, what are the owner count, average team championship total, and earliest and latest acquisition years?",
            ),
            (
                "q12",
                "SELECT t.team_name, COUNT(*) AS player_count, AVG(p.age) AS avg_age, SUM(CASE WHEN p.mvp_awards >= 1 THEN 1 ELSE 0 END) AS mvp_winner_count, MAX(t.championship) AS team_titles FROM player p JOIN team t ON TRIM(p.team) = TRIM(t.team_name) GROUP BY t.team_name HAVING COUNT(*) >= 2",
                "Among NBA teams with at least two players, what are the player count, average age, number of career MVP winners, and team championship total?",
            ),
            (
                "q13",
                "SELECT t.location, COUNT(*) AS player_count, AVG(p.nba_championships) AS avg_player_titles, SUM(CASE WHEN p.fiba_world_cup >= 1 THEN 1 ELSE 0 END) AS fiba_winner_count FROM player p JOIN team t ON TRIM(p.team) = TRIM(t.team_name) WHERE t.location != '' AND p.nba_championships IS NOT NULL AND p.fiba_world_cup IS NOT NULL GROUP BY t.location HAVING SUM(CASE WHEN p.fiba_world_cup >= 1 THEN 1 ELSE 0 END) >= 1",
                "For NBA team cities with at least one FIBA World Cup winner, what are the player count, average career NBA championships, and number of FIBA winners among players with both statistics known?",
            ),
            (
                "q14",
                "SELECT c.state_name, COUNT(*) AS player_count, AVG(p.age) AS avg_age, MAX(p.mvp_awards) AS max_mvp FROM player p JOIN team t ON p.team = t.team_name JOIN city c ON t.location = c.city_name WHERE c.state_name != '' GROUP BY c.state_name HAVING COUNT(*) >= 3",
                "Among states with at least three players on local NBA teams, what are the player count, average age, and highest MVP total?",
            ),
            (
                "q15",
                "SELECT o.name, COUNT(*) AS player_count, AVG(p.age) AS avg_age, SUM(CASE WHEN p.nba_championships >= 1 THEN 1 ELSE 0 END) AS champion_player_count, MAX(t.championship) AS team_titles FROM player p JOIN team t ON TRIM(p.team) = TRIM(t.team_name) JOIN owner o ON TRIM(t.team_name) = TRIM(o.nba_team) GROUP BY o.name HAVING COUNT(*) >= 2",
                "Among owners whose NBA team has at least two players, what are the player count, average age, number of career NBA champions, and team championship total?",
            ),
            (
                "q16",
                "SELECT p.position, c.state_name, COUNT(*) AS player_count, AVG(p.draft_pick) AS avg_pick, MIN(p.draft_year) AS earliest_draft FROM player p JOIN team t ON p.team = t.team_name JOIN city c ON t.location = c.city_name WHERE p.position IN ('Frontcourt', 'Backcourt') AND p.draft_pick > 0 AND c.state_name != '' GROUP BY p.position, c.state_name HAVING COUNT(*) >= 2",
                "For each position and state with at least two drafted players on local teams, what are the count, average draft pick, and earliest draft year?",
            ),
            (
                "q17",
                "SELECT nationality, COUNT(*) AS player_count, AVG(olympic_gold_medals) AS avg_golds, SUM(olympic_gold_medals) AS total_golds, MAX(olympic_gold_medals) AS max_golds FROM player WHERE olympic_gold_medals >= 1 AND nationality != '' GROUP BY nationality",
                "Among players with at least one Olympic gold, what are the count and the average, total, and maximum gold-medal counts for each nationality?",
            ),
            (
                "q18",
                "SELECT CAST(draft_year / 10 AS INTEGER) * 10 AS draft_decade, COUNT(*) AS player_count, AVG(draft_pick) AS avg_pick, MIN(draft_pick) AS best_pick, MAX(draft_pick) AS latest_pick FROM player WHERE draft_year > 0 AND draft_pick > 0 GROUP BY draft_decade HAVING COUNT(*) >= 2",
                "For draft decades represented by at least two drafted players, what are the player count, average pick, best pick, and latest pick?",
            ),
            (
                "q19",
                "SELECT c.state_name, COUNT(DISTINCT t.team_name) AS team_count, COUNT(*) AS player_count, AVG(p.age) AS avg_age, SUM(CASE WHEN p.mvp_awards >= 1 THEN 1 ELSE 0 END) AS mvp_winner_count FROM player p JOIN team t ON TRIM(p.team) = TRIM(t.team_name) JOIN city c ON c.city_name = CASE t.location WHEN 'Brooklyn' THEN 'New York City' WHEN 'Washington' THEN 'Washington, D.C.' ELSE t.location END WHERE c.state_name != '' GROUP BY c.state_name HAVING COUNT(*) >= 2",
                "Among states with at least two players on NBA teams, how many teams and players are represented, what is the average age, and how many players are career MVP winners?",
            ),
        ],
    },
    "player_filterjoin20": {
        "title": "Filter-and-join workload",
        "focus": "Selective WHERE predicates with light joins; aggregation stays simple",
        "queries": [
            (
                "q0",
                "SELECT position, COUNT(*) AS player_count FROM player WHERE age >= 30 AND nba_championships >= 1 AND position IN ('Frontcourt', 'Backcourt') GROUP BY position",
                "Among players aged 30 or older with at least one NBA championship, how many are Frontcourt and how many are Backcourt?",
            ),
            (
                "q1",
                "SELECT position, COUNT(*) AS player_count FROM player WHERE draft_pick BETWEEN 1 AND 10 AND draft_year >= 2010 AND position IN ('Frontcourt', 'Backcourt') GROUP BY position",
                "Among top-10 picks drafted since 2010, how many are Frontcourt and how many are Backcourt?",
            ),
            (
                "q2",
                "SELECT position, COUNT(*) AS player_count FROM player WHERE mvp_awards >= 1 AND olympic_gold_medals >= 1 AND position IN ('Frontcourt', 'Backcourt') GROUP BY position",
                "Among players with both an MVP award and an Olympic gold medal, how many are there at each position?",
            ),
            (
                "q3",
                "SELECT position, COUNT(*) AS player_count FROM player WHERE fiba_world_cup >= 1 AND age BETWEEN 25 AND 40 AND position IN ('Frontcourt', 'Backcourt') GROUP BY position",
                "Among players aged 25 to 40 with at least one FIBA World Cup title, how many are Frontcourt and how many are Backcourt?",
            ),
            (
                "q4",
                "SELECT CAST(draft_year / 10 AS INTEGER) * 10 AS draft_decade, COUNT(*) AS player_count FROM player WHERE olympic_gold_medals >= 1 AND draft_pick BETWEEN 1 AND 5 AND draft_year > 0 GROUP BY draft_decade",
                "How many Olympic gold medalists selected in the top five picks were drafted in each decade?",
            ),
            (
                "q5",
                "SELECT position, AVG(age) AS avg_age FROM player WHERE college != '' AND nba_championships = 0 AND position IN ('Frontcourt', 'Backcourt') GROUP BY position",
                "Among players with a known college and no NBA championships, what is the average age for Frontcourt and Backcourt players?",
            ),
            (
                "q6",
                "SELECT c.state_name, COUNT(*) AS team_count FROM team t JOIN city c ON c.city_name = CASE t.location WHEN 'Brooklyn' THEN 'New York City' WHEN 'Washington' THEN 'Washington, D.C.' ELSE t.location END WHERE t.founded_year < 1970 AND t.championship >= 1 AND c.state_name != '' GROUP BY c.state_name",
                "How many NBA teams founded before 1970 with at least one championship are based in each state?",
            ),
            (
                "q7",
                "SELECT CAST(founded_year / 10 AS INTEGER) * 10 AS founded_decade, AVG(championship) AS avg_titles FROM team WHERE founded_year BETWEEN 1960 AND 1990 AND championship >= 1 GROUP BY founded_decade",
                "Among title-winning teams founded from 1960 through 1990, what is the average championship count in each founding decade?",
            ),
            (
                "q8",
                "SELECT state_name, COUNT(*) AS city_count FROM city WHERE population > 500000 AND state_name != '' GROUP BY state_name",
                "How many cities with more than 500,000 people are there in each state?",
            ),
            (
                "q9",
                "SELECT CAST(own_year / 10 AS INTEGER) * 10 AS acquisition_decade, COUNT(*) AS owner_count FROM owner WHERE own_year >= 2000 GROUP BY acquisition_decade",
                "Among owners who acquired their team in 2000 or later, how many acquisitions occurred in each decade?",
            ),
            (
                "q10",
                "SELECT p.team, COUNT(*) AS player_count FROM player p JOIN team t ON p.team = t.team_name WHERE t.championship >= 3 AND p.age < 30 GROUP BY p.team",
                "Among players under 30 on teams with at least three championships, how many are on each team?",
            ),
            (
                "q11",
                "SELECT p.position, AVG(p.mvp_awards) AS avg_mvp FROM player p JOIN team t ON TRIM(p.team) = TRIM(t.team_name) WHERE p.mvp_awards >= 1 AND t.founded_year < 1980 AND p.position IN ('Frontcourt', 'Backcourt') GROUP BY p.position",
                "Among career MVP winners on NBA teams founded before 1980, what is the average MVP total for Frontcourt and Backcourt players?",
            ),
            (
                "q12",
                "SELECT p.position, COUNT(*) AS player_count FROM player p JOIN team t ON TRIM(p.team) = TRIM(t.team_name) WHERE t.championship = 0 AND p.draft_year > 2000 AND p.position IN ('Frontcourt', 'Backcourt') GROUP BY p.position",
                "Among players drafted after 2000 on NBA teams with zero championships, how many are Frontcourt and how many are Backcourt?",
            ),
            (
                "q13",
                "SELECT c.state_name, COUNT(*) AS player_count FROM player p JOIN team t ON p.team = t.team_name JOIN city c ON t.location = c.city_name WHERE c.population > 1000000 AND p.nba_championships >= 1 AND c.state_name != '' GROUP BY c.state_name",
                "Among championship-winning players on teams in cities with more than one million people, how many are there for each state?",
            ),
            (
                "q14",
                "SELECT c.state_name, AVG(p.age) AS avg_age FROM player p JOIN team t ON TRIM(p.team) = TRIM(t.team_name) JOIN city c ON c.city_name = CASE t.location WHEN 'Brooklyn' THEN 'New York City' WHEN 'Washington' THEN 'Washington, D.C.' ELSE t.location END WHERE p.draft_pick BETWEEN 1 AND 14 AND p.age BETWEEN 20 AND 45 AND c.state_name != '' GROUP BY c.state_name",
                "Among lottery picks aged 20 to 45, what is the average age for players on NBA teams in each state?",
            ),
            (
                "q15",
                "SELECT o.nationality, COUNT(*) AS player_count FROM player p JOIN team t ON p.team = t.team_name JOIN owner o ON t.team_name = o.nba_team WHERE p.olympic_gold_medals >= 1 AND o.own_year >= 1990 AND o.nationality != '' GROUP BY o.nationality",
                "Among Olympic gold medalists on NBA teams acquired in 1990 or later, how many are there for each owner nationality?",
            ),
            (
                "q16",
                "SELECT t.team_name, COUNT(*) AS player_count FROM player p JOIN team t ON TRIM(p.team) = TRIM(t.team_name) JOIN owner o ON TRIM(t.team_name) = TRIM(o.nba_team) WHERE p.college != '' AND p.mvp_awards = 0 AND p.nba_championships >= 1 GROUP BY t.team_name",
                "For each NBA team with known ownership, how many players with a known college have at least one career championship but no MVP awards?",
            ),
            (
                "q17",
                "SELECT c.state_name, SUM(p.fiba_world_cup) AS total_fiba FROM player p JOIN team t ON p.team = t.team_name JOIN owner o ON t.team_name = o.nba_team JOIN city c ON t.location = c.city_name WHERE p.fiba_world_cup >= 1 AND c.population > 500000 AND c.state_name != '' GROUP BY c.state_name",
                "Among FIBA title holders on owned NBA teams in cities with more than 500,000 people, what is the total career FIBA title count for each state?",
            ),
            (
                "q18",
                "SELECT p.position, COUNT(*) AS player_count FROM player p JOIN team t ON TRIM(p.team) = TRIM(t.team_name) JOIN city c ON c.city_name = CASE t.location WHEN 'Brooklyn' THEN 'New York City' WHEN 'Washington' THEN 'Washington, D.C.' ELSE t.location END WHERE c.state_name IN ('California', 'Texas', 'New York', 'Florida') AND p.age BETWEEN 22 AND 34 AND p.position IN ('Frontcourt', 'Backcourt') GROUP BY p.position",
                "Among players aged 22 to 34 on NBA teams in California, Texas, New York, or Florida, how many are Frontcourt and how many are Backcourt?",
            ),
            (
                "q19",
                "SELECT t.team_name, COUNT(*) AS player_count FROM player p JOIN team t ON p.team = t.team_name JOIN owner o ON t.team_name = o.nba_team WHERE o.own_year >= 2000 AND p.draft_year >= 2000 AND p.draft_pick > 0 AND p.draft_pick <= 30 GROUP BY t.team_name",
                "Among top-30 picks drafted in 2000 or later on NBA teams acquired in 2000 or later, how many players are on each team?",
            ),
        ],
    },
}


def write_workloads() -> None:
    for name, spec in WORKLOADS.items():
        out_dir = OUT_ROOT / name
        out_dir.mkdir(parents=True, exist_ok=True)
        sql_manifest = [
            {"query_id": qid, "sql": finalize_sql(sql)}
            for qid, sql, _ in spec["queries"]
        ]
        nl_manifest = [{"query_id": qid, "text": text} for qid, _, text in spec["queries"]]
        meta = {
            "workload_id": name,
            "title": spec["title"],
            "focus": spec["focus"],
            "dataset": "Player",
            "n_queries": 20,
            "contrast_with": "player_agg20 (case study/docetl_Player_v7)",
            "join_notes": {
                "player_team": "player.team = team.team_name",
                "team_city": "team.location = city.city_name",
                "team_owner": "owner.nba_team = team.team_name",
            },
        }
        (out_dir / "query_manifest.json").write_text(
            json.dumps(sql_manifest, indent=2) + "\n", encoding="utf-8"
        )
        (out_dir / "query_manifest_nl.json").write_text(
            json.dumps(nl_manifest, indent=2) + "\n", encoding="utf-8"
        )
        (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out_dir}")


def write_readme() -> None:
    lines = [
        "# Player case-study workloads",
        "",
        "Five curated 20-query Player workloads for QuWARTS / DocETL-style evaluation.",
        "",
        "## Existing baseline",
        "",
        "| Workload | Path | Focus |",
        "|---|---|---|",
        "| **player_agg20** | `case study/docetl_Player_v7/` | Classic single-table (and a few 1-join) `GROUP BY` aggregations |",
        "",
        "## Four new contrasting workloads",
        "",
        "| Workload | Path | Focus | How it differs |",
        "|---|---|---|---|",
        "| **player_join20** | `workloads/player_join20/` | Join depth | Mix of 1-join, 2-join, and 3-join queries; aggregation is secondary |",
        "| **player_groupby20** | `workloads/player_groupby20/` | `GROUP BY` shape | Many multi-column groupings (`position, nationality`, joined keys, etc.) |",
        "| **player_multiagg20** | `workloads/player_multiagg20/` | Aggregations | Several aggregates in one `SELECT`, often with `HAVING` |",
        "| **player_filterjoin20** | `workloads/player_filterjoin20/` | Filters + light joins | Selective `WHERE` predicates (`BETWEEN`, thresholds, `IN`) with simple aggregates |",
        "",
        "Each folder contains:",
        "",
        "- `query_manifest.json` — `{query_id, sql}`",
        "- `query_manifest_nl.json` — `{query_id, text}`",
        "- `meta.json` — short description",
        "",
        "## Join keys used",
        "",
        "- Player/team and team/owner names are compared after `TRIM`.",
        "- Team/city joins normalize `Brooklyn → New York City` and `Washington → Washington, D.C.`.",
        "- `owner.nba_team = team.team_name` is preferred; `team.ownership` names do not align with `owner.name` in the CSV.",
        "",
        "## Regenerate / validate",
        "",
        "```bash",
        "python3 \"case study/build_player_contrast_workloads.py\"",
        "```",
        "",
    ]
    readme = OUT_ROOT / "README.md"
    marker = "## Mixture subsets"
    suffix = ""
    if readme.exists():
        previous = readme.read_text(encoding="utf-8")
        if marker in previous:
            suffix = "\n\n" + marker + previous.split(marker, 1)[1]
    readme.write_text("\n".join(lines).rstrip() + suffix + "\n", encoding="utf-8")


def main() -> None:
    conn = load_sqlite()
    errors = validate(conn)
    if errors:
        print("VALIDATION FAILED")
        for err in errors:
            print(err)
        raise SystemExit(1)
    write_workloads()
    write_readme()
    print("all workloads validated and written")


if __name__ == "__main__":
    main()
