"""Install the manually reviewed causal analysis in the case-study artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSES = ROOT / "case study" / "player_agg20_diagnoses.json"
SITE_DATA = ROOT / "player-agg20-case-site" / "src" / "data.json"


def q(
    stage: str,
    root_cause: str,
    design_choice: str,
    why_checks_missed: str,
    failure_path: str,
) -> dict[str, str]:
    return {
        "failure_stage": stage,
        "root_cause": root_cause,
        "summary": root_cause,
        "design_choice": design_choice,
        "why_checks_missed": why_checks_missed,
        "failure_path": failure_path,
    }


ANALYSIS: dict[str, dict[str, dict[str, str]]] = {
    "q0": {
        "quwarts": q(
            "Position names",
            "QuWARTS kept detailed positions but the question needed two broad position groups.",
            "The selected working table kept the position text as extracted. It did not include a step that maps each detailed position to one of the two groups.",
            "The checks accept normal text values. They do not test whether every position matches one of the values used by the question.",
            "The question accepts only Frontcourt or Backcourt. Neither name was present, so no player reached the average calculation.",
        ),
        "docetl": q(
            "Position names",
            "DocETL read detailed position names but did not turn them into the two values used by the filter.",
            "The natural-language instruction asked for known positions and said to keep names concise and normalized. It gave no mapping from detailed positions to Frontcourt and Backcourt.",
            "Center, forward, and point guard are all normal text values, so they passed the checks.",
            "None of those values matched Frontcourt or Backcourt, so the result was empty.",
        ),
    },
    "q1": {
        "quwarts": q(
            "Nationality names and missing values",
            "QuWARTS did not use one clear set of nationality names. It also missed many nationality values.",
            "The table chosen for this question was meant to use name mapping, but its nationality column is identical to the table without mapping. No nationality value changed.",
            "Names such as Azerbaijan and American-born naturalized Azerbaijani are both valid text. A text and type check cannot determine which benchmark label should be used.",
            "The same nationality appears under several names, while missing values make the American group too small. The question counts each name as a separate group.",
        ),
        "docetl": q(
            "Nationality output",
            "DocETL saved some full data objects as nationality names. It also did not join different names for the same nationality.",
            "The output rule only checks that nationality is text. It does not check that the text is a normal nationality name.",
            "A full data object can still be saved as text, so it passed the check.",
            "The broken text became a group name. Shorter nationality names also created missing and extra groups.",
        ),
    },
    "q2": {
        "quwarts": q(
            "Teams and title counts",
            "The QuWARTS working table was missing many team and NBA title values, and some retained values did not match the benchmark rows.",
            "The selected table stores one team name and one title count, but it stores no date or event that could be used to check what each value describes.",
            "The basic checks test text and number types. A real team name or number can pass even when it refers to the wrong part of a player's history.",
            "The average used an incomplete set of player values. The saved query is correct, but it ran on incomplete and incorrect input rows.",
        ),
        "docetl": q(
            "Missing numbers and team names",
            "DocETL used -1 for missing title counts. It also used different forms of the same team name.",
            "Player data and team data were built separately. Missing numbers stayed as -1, and team names were not cleaned together.",
            "-1 is still a number, and names such as Celtics and Boston Celtics are both normal text.",
            "The -1 values lowered the averages. Different team names also stopped valid players from matching their teams.",
        ),
    },
    "q3": {
        "quwarts": q(
            "College names and MVP counts",
            "QuWARTS used several names for the same college and missed most MVP counts.",
            "The selected working table did not run a name-cleaning step that joins short names, full names, and mascot names.",
            "UCLA and UCLA Bruins are both valid text. The basic type check does not test whether two labels refer to the same college.",
            "Players from one college were split into several groups. This changed which colleges had more than one player and changed the highest MVP value.",
        ),
        "docetl": q(
            "College names and missing numbers",
            "DocETL used several names for the same college and used -1 for missing MVP counts.",
            "The instruction said to keep names concise and normalized, but it did not provide a shared college-name mapping.",
            "Short college names and -1 both matched the expected format, so they passed.",
            "College groups were split. A group with no real MVP count could also return -1 as its highest value.",
        ),
    },
    "q4": {
        "quwarts": q(
            "Position names",
            "QuWARTS did not change detailed positions into Frontcourt and Backcourt.",
            "The selected working table contains detailed position labels and no Frontcourt or Backcourt values.",
            "The basic check accepts text values without testing them against the two labels used by the query.",
            "No row matched Frontcourt or Backcourt, so there were no MVP values to add.",
        ),
        "docetl": q(
            "Position names",
            "DocETL returned detailed positions instead of the two groups needed by the question.",
            "The instruction did not provide a fixed list or explain how each position should be grouped.",
            "Detailed positions are normal text, so they passed the output check.",
            "The question found no Frontcourt or Backcourt rows, so the result was empty.",
        ),
    },
    "q5": {
        "quwarts": q(
            "Meaning of title counts",
            "QuWARTS retained wrong NBA title counts, including a value of 6 linked to a hockey player's Stanley Cups.",
            "The selected working table checks that this field contains a number. It does not apply an NBA-specific meaning or range check.",
            "A count of six fits the numeric type even when it counts titles from another sport.",
            "Wrong title counts became the highest value for some nationalities. Different nationality names created more group errors. One error also comes from an unusual empty value in the scoring data.",
        ),
        "docetl": q(
            "Missing rows, names, and a scoring edge case",
            "The DocETL output omitted 25 of the 141 input player documents and split nationality names. Its American value of 9 matches Steve Kerr's source row, but the benchmark result for that group is an empty string because of mixed text and number handling.",
            "The map step is configured to skip a document after an extraction error, and it uses one free-text nationality field with no shared mapping. The saved output does not record the reason for each omitted document.",
            "The output checks cannot recover a skipped player or join two nationality spellings. The score also treats the empty benchmark value as different from the valid number 9.",
            "Omitted or incomplete rows removed groups, name differences added other groups, and the benchmark edge case marks the American value as wrong even though 9 is present in the source table.",
        ),
    },
    "q6": {
        "quwarts": q(
            "Meaning of years",
            "QuWARTS used a year from a draft discussion as the player's draft year, even when the player was not drafted.",
            "The selected working table checks the value type, but it does not require evidence that the year is the player's own draft year.",
            "A saved validation record says Max Fiedler's 2024 value was not supported as his draft year, but the working table still retained it.",
            "Players moved into the wrong year groups and a false 2024 group appeared. Other players had no draft year.",
        ),
        "docetl": q(
            "Wrong and missing draft years",
            "DocETL assigned unrelated years to some players and left many other draft years unknown.",
            "The instruction asked for a draft year but did not require proof that the year described the player's own draft.",
            "The wrong years looked like normal years. Players with an unknown year simply disappeared from the displayed result.",
            "The final table has no -1 row. The after-2010 rule removed those missing-value rows. Wrong years still moved players into the wrong groups, and several real year groups disappeared.",
        ),
    },
    "q7": {
        "quwarts": q(
            "Current teams",
            "The QuWARTS working table missed many team and draft-pick values, and some retained team groups did not match the benchmark.",
            "The player row stores a team name but no date or status. After extraction, the working table has no check that confirms the value is the current team requested by the question.",
            "A team name can be valid text and still be the wrong team for the benchmark row.",
            "Players were placed under missing or wrong teams. The lowest draft pick was then calculated from the wrong players.",
        ),
        "docetl": q(
            "Team name matching",
            "DocETL built player team names and official team names separately. It also kept some old team links.",
            "The prompt asks for the current team, but the output stores only the team name. The two tables are not cleaned together, and there is no later check of team identity or date.",
            "Both sides contained normal text, even when the names differed or the team link was old.",
            "Valid players failed to match their teams, while other players were sent to the wrong team. This changed the lowest draft pick.",
        ),
    },
    "q8": {
        "quwarts": q(
            "Position names",
            "QuWARTS did not change detailed positions into Frontcourt and Backcourt.",
            "The selected working table contains detailed position labels and no Frontcourt or Backcourt values.",
            "The basic checks accept valid text and number types without testing the position labels against the query filter.",
            "The position rule removed every row before the medal average could be calculated.",
        ),
        "docetl": q(
            "Position names and missing values",
            "DocETL missed many positions and medal counts. It also did not create Frontcourt and Backcourt groups.",
            "The instruction gave no fixed position list. Many position and medal values remained unknown.",
            "Detailed positions and missing values passed the basic output checks.",
            "No position matched Frontcourt or Backcourt, so the result was empty.",
        ),
    },
    "q9": {
        "quwarts": q(
            "College names and title counts",
            "QuWARTS used several names for the same college and accepted some wrong NBA title counts.",
            "The selected working table does not clean college names and only checks that the title field is a number.",
            "Two college labels and an incorrect title count can all pass those text and number checks.",
            "College groups were split, and some players wrongly passed the NBA title rule.",
        ),
        "docetl": q(
            "College names and title counts",
            "DocETL produced several forms of each college name and some wrong NBA title counts.",
            "There was no shared college-name list and no check of what each title number meant.",
            "Every college form was normal text, and every false title was still a number.",
            "Wrong title values let some players pass. Short, mascot, and full college names then became separate groups.",
        ),
    },
    "q10": {
        "quwarts": q(
            "Meaning of title counts",
            "QuWARTS accepted years as FIBA title counts and often missed current team links.",
            "The selected working table checked that the title field held a number, but it did not apply a sensible count range.",
            "Saved validation records mark Rik Smits's 1986 value as contradicted and Bam Adebayo's 2024 value as unsupported. The working table still retained both numbers.",
            "These years passed the at-least-one rule and made the totals extremely large. Missing or wrong teams also changed the groups.",
        ),
        "docetl": q(
            "Title counts and team names",
            "DocETL accepted any number as a title count and built team names separately.",
            "It had no sensible range for title counts and no shared cleanup for team names.",
            "A title value of 30 and two different forms of a team name both passed the basic checks.",
            "Wrong counts made totals too high, while different team names removed valid players.",
        ),
    },
    "q11": {
        "quwarts": q(
            "Age calculation",
            "The QuWARTS table contains old age values instead of the players' ages in 2026.",
            "The working table stores age, but it does not store birth date or the date used for the age calculation. It can therefore keep an age stated in an older article.",
            "An old age from an article is still a normal number. A type check cannot tell whether it is the person's age in 2026.",
            "Old ages let some older players pass the 20 to 40 rule. Missing ages removed other players, and nationality names split more groups.",
        ),
        "docetl": q(
            "Age calculation and missing values",
            "The DocETL table contains old age values and leaves many other ages unknown.",
            "The instruction requests one age number but does not require a birth-date calculation or store the date used for that calculation.",
            "The old ages looked like normal numbers. Players with an unknown age did not appear in the displayed result.",
            "The final table has no -1 age. The 20 to 40 rule removed those rows. Wrong ages still changed which players passed, and different nationality names caused more errors.",
        ),
    },
    "q12": {
        "quwarts": q(
            "Team records and current facts",
            "The QuWARTS team table contains historical team names, person names, and a year as separate team rows.",
            "The selected team table has 42 rows, while the benchmark has 30 teams. It has no final rule that limits the result to one current row for each benchmark team.",
            "Person names and years still pass the table's text and number type checks even when the row identity is not a current team.",
            "Old and false rows added locations. Some years were also used as title counts, which changed the highest values.",
        ),
        "docetl": q(
            "Choosing current team facts",
            "DocETL sometimes chose old team facts, and some documents produced no row.",
            "Each team document was handled once. There was no second check to choose current facts over old facts.",
            "An old location or title total has the expected format, so it passed.",
            "Old values replaced current ones, missing titles became -1, and missing rows removed three teams.",
        ),
    },
    "q13": {
        "quwarts": q(
            "Team rows, cities, and years",
            "QuWARTS kept extra historical or non-current team rows, different city names, and wrong founding years.",
            "The selected team table has 42 rows for a 30-team benchmark and no final step that keeps one current row per team.",
            "A historical city or wrong year still passes the text or number type check.",
            "Different city names split the groups. Wrong founding years also removed Houston and Philadelphia.",
        ),
        "docetl": q(
            "Missing years and old locations",
            "DocETL marked some founding years as unknown and sometimes chose old locations.",
            "Inside the team table, DocETL used -1 to mark an unknown year. It also did not clearly require one current team record.",
            "The question treats -1 as a year before 1970. The final table shows only city and count, so the -1 value itself is not displayed.",
            "Teams with unknown years were wrongly counted. Other current teams appeared under old city names or wrong years.",
        ),
    },
    "q14": {
        "quwarts": q(
            "Owner names used for scoring",
            "The scoring data changes team owner names by using a separate owner table, but the question does not ask either system to use that table.",
            "The requested table has a team ownership field but no owner lookup table. QuWARTS therefore uses ownership text from its team rows, including old, legal, and short names.",
            "Those values are valid owner text. The query setup contains no link to the separate owner-name list used while building the gold table.",
            "Related owner names became separate groups. Extra team rows added more owners. Part of this error comes from a gold-table rewrite that is not present in the query.",
        ),
        "docetl": q(
            "Owner names used for scoring",
            "DocETL reads owner names from team documents, while the scoring data changes them by using a separate owner table.",
            "The reference query requests only a team table, so this DocETL run builds only that table. It does not build or join the separate owner lookup used while creating the gold table.",
            "Names such as Dan Gilbert and Joseph Tsai are reasonable answers from team documents.",
            "These names did not exactly match the scorer's longer names. Old owners and missing rows caused more errors.",
        ),
    },
    "q15": {
        "quwarts": q(
            "Current locations and title totals",
            "QuWARTS kept location variants and wrong title totals instead of one benchmark row for each team.",
            "The working table stores a location and title number, but it stores no date that could identify the current version of each fact.",
            "Location variants and wrong totals still have valid text and number types. The checks could not identify the benchmark version from type alone.",
            "The question kept the wrong versions of teams. Different city names split groups, and wrong totals changed the averages.",
        ),
        "docetl": q(
            "Choosing current team facts",
            "DocETL chose historical cities and some wrong title totals.",
            "It made one row from each team document without a second step that checks the time period of each selected fact.",
            "Historical cities and wrong title totals still have the expected text and number formats.",
            "Historical locations created extra groups, and wrong totals changed the averages.",
        ),
    },
    "q16": {
        "quwarts": q(
            "Owner coverage and age calculation",
            "The QuWARTS table has only 11 owner rows, and several saved ages do not match the 2026 benchmark values.",
            "The working table stores age but not birth date or the date used for the calculation, so the saved age cannot be recalculated or checked for 2026.",
            "A wrong age is still a valid number. The basic type check does not compare it with birth information and 2026.",
            "The average used too few owners. Missing ages gave empty results for some groups, and different nationality wording created extra groups.",
        ),
        "docetl": q(
            "Age values and missing numbers",
            "DocETL confused a birth year with an age and used -1 for missing ages.",
            "The age field only had to contain a number. The instruction did not require a sensible age range or a birth-date calculation.",
            "1959 and -1 are both numbers, so the basic check accepted them.",
            "These values were averaged as real ages, making the American result far too large.",
        ),
    },
    "q17": {
        "quwarts": q(
            "Owner coverage and purchase years",
            "The QuWARTS owner table lacks the American purchase year 2000 and contains an unsupported 1996 year for the Taiwanese-Canadian row.",
            "The owner table stores one year but no event text that proves the year is a team purchase. The working table can keep a numeric year without that proof.",
            "A wrong year can still have the correct number format. A saved validation record says Joseph Tsai's 1996 value was not supported as an ownership year.",
            "The missing 2000 purchase changed the American minimum. A wrong 1996 year removed the Taiwanese-Canadian row.",
        ),
        "docetl": q(
            "Purchase years and nationality",
            "DocETL left most nationality values empty and used a company job year as a team purchase year.",
            "The extraction output stores only the year value. It does not store a quote or event label that proves the year describes buying the team.",
            "The job year is still a number, and an empty nationality was allowed.",
            "Empty nationalities joined unrelated owners into one group. The wrong year could also pass the date rule.",
        ),
    },
    "q18": {
        "quwarts": q(
            "Population date and area",
            "QuWARTS used population numbers from different years or different areas.",
            "It saved one population number without also saving the date or whether it covered the city or the larger metro area.",
            "The basic check validates the number type but does not validate the population date or geographic area.",
            "Every state group was present, but the wrong population version changed six averages.",
        ),
        "docetl": q(
            "Missing states and populations",
            "DocETL left many state names empty and marked some populations as unknown.",
            "Inside the city table, DocETL used -1 to mark an unknown population. It did not remove that marker before calculating averages.",
            "The output rule accepts -1 because the prompt defines it as the missing marker. The later average then treats it as a real number.",
            "Empty state names removed groups. In Florida, a hidden -1 marker lowered the displayed average.",
        ),
    },
    "q19": {
        "quwarts": q(
            "GDP units and population area",
            "QuWARTS mixed GDP values written in dollars, millions, and billions.",
            "The working table stores one GDP number but no unit, so values cannot be converted to a common scale after extraction.",
            "The basic check validates the number type but does not compare or convert GDP units.",
            "The maximum was chosen from values that used different units. A metro population also caused Utah to pass a rule meant for city population.",
        ),
        "docetl": q(
            "GDP units and missing states",
            "DocETL saved GDP as a number without saving its unit. It also left some state names empty.",
            "The output has one numeric GDP field and no unit field. It therefore cannot show whether a value is in dollars, millions, or billions.",
            "Values on different scales are still numbers, and empty state names were allowed.",
            "Some cities disappeared because the state was empty. Other GDP values were reported even though they used different units.",
        ),
    },
}


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any, *, compact: bool = False) -> None:
    text = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":") if compact else None,
        indent=None if compact else 2,
    )
    path.write_text(text + ("" if compact else "\n"), encoding="utf-8")


def main() -> int:
    diagnoses = _read(DIAGNOSES)
    for query_id, systems in ANALYSIS.items():
        for system, analysis in systems.items():
            evidence = diagnoses[query_id][system].get("evidence", [])
            diagnoses[query_id][system] = {**analysis, "evidence": evidence}
    _write(DIAGNOSES, diagnoses)

    site = _read(SITE_DATA)
    site.pop("system_design", None)
    by_id = {item["query_id"]: item for item in site["queries"]}
    for query_id, systems in ANALYSIS.items():
        for system, analysis in systems.items():
            evidence = diagnoses[query_id][system].get("evidence", [])
            by_id[query_id]["reasons"][system] = {
                "component": analysis["failure_stage"],
                "root_cause": analysis["root_cause"],
                "design_choice": analysis["design_choice"],
                "why_checks_missed": analysis["why_checks_missed"],
                "failure_path": analysis["failure_path"],
                "evidence": evidence,
            }
    _write(SITE_DATA, site, compact=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
