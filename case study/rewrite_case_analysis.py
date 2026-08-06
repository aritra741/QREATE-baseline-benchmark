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
            "QuWARTS kept names such as center and point guard because those names came directly from the documents.",
            "The names are real basketball positions, so the checks did not see them as wrong.",
            "The question accepts only Frontcourt or Backcourt. Neither name was present, so no player reached the average calculation.",
        ),
        "docetl": q(
            "Position names",
            "DocETL was not told how to change detailed positions into Frontcourt and Backcourt.",
            "The instruction only asked DocETL to keep names clean. It did not give a fixed list of allowed positions.",
            "Center, forward, and point guard are all normal text values, so they passed the checks.",
            "None of those values matched Frontcourt or Backcourt, so the result was empty.",
        ),
    },
    "q1": {
        "quwarts": q(
            "Nationality names and missing values",
            "QuWARTS did not use one clear set of nationality names. It also missed many nationality values.",
            "QuWARTS changes a value only when there is clear proof that the change is right. This reduces guessing, but it leaves difficult names unchanged.",
            "Names such as Azerbaijan and Azerbaijani both appear reasonable. The checks cannot tell that they should be placed in the same group.",
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
            "QuWARTS often missed a player's current team or NBA title count.",
            "It kept team and number mentions from the documents so that it would not lose useful facts. It did not always choose the current fact.",
            "A team name or number can appear in the document and still describe the wrong time or event.",
            "The average used only a small and unfair set of players. The calculation was correct, but the input rows were wrong.",
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
            "It kept the college name found in each document. It had no shared list that joined short names, full names, and mascot names.",
            "The checks did not know that UCLA and UCLA Bruins mean the same college.",
            "Players from one college were split into several groups. This changed which colleges had more than one player and changed the highest MVP value.",
        ),
        "docetl": q(
            "College names and missing numbers",
            "DocETL used several names for the same college and used -1 for missing MVP counts.",
            "The instruction asked for short names but did not give one shared list of college names.",
            "Short college names and -1 both matched the expected format, so they passed.",
            "College groups were split. A group with no real MVP count could also return -1 as its highest value.",
        ),
    },
    "q4": {
        "quwarts": q(
            "Position names",
            "QuWARTS did not change detailed positions into Frontcourt and Backcourt.",
            "It kept the position names found in the documents.",
            "The names were real positions and appeared in the source text, so the checks accepted them.",
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
            "QuWARTS treated numbers from other sports and nearby years as NBA title counts.",
            "It checked that the value was a number, but not what the number described.",
            "Six Stanley Cups and several years appear in the documents, so the checks found support for those numbers.",
            "Wrong title counts became the highest value for some nationalities. Different nationality names created more group errors. One error also comes from an unusual empty value in the scoring data.",
        ),
        "docetl": q(
            "Missing rows and wrong title counts",
            "DocETL skipped some rows and accepted a wrong NBA title count.",
            "A failed document can be skipped without stopping the full question. The number check does not test what the number means.",
            "A value such as 9 looks like a valid number even when it describes the wrong fact.",
            "Skipped rows removed nationality groups, while the wrong value made the American maximum too high.",
        ),
    },
    "q6": {
        "quwarts": q(
            "Meaning of years",
            "QuWARTS used a year from a draft discussion as the player's draft year, even when the player was not drafted.",
            "It checked that draft year was a whole number, but it did not prove that the year described the player's own draft.",
            "The year 2024 appeared in the document and had the right number format.",
            "Players moved into the wrong year groups and a false 2024 group appeared. Other players had no draft year.",
        ),
        "docetl": q(
            "Draft years and missing values",
            "DocETL used unrelated years as draft years and used -1 when it was unsure.",
            "The instruction asked for a draft year but did not require proof that the year described the player's own draft.",
            "Unrelated years and -1 are all numbers, so they passed the basic check.",
            "Players moved into wrong groups, many real year groups disappeared, and rows with -1 did not pass the year rule.",
        ),
    },
    "q7": {
        "quwarts": q(
            "Current teams",
            "QuWARTS did not always choose a player's current NBA team and missed many draft picks.",
            "It kept team mentions from different parts of a document instead of choosing one current team.",
            "An old team or related company can appear in the document and therefore look supported.",
            "Players were placed under missing or wrong teams. The lowest draft pick was then calculated from the wrong players.",
        ),
        "docetl": q(
            "Team name matching",
            "DocETL built player team names and official team names separately. It also kept some old team links.",
            "The two sets of names were not cleaned together, and there was no clear rule to choose only the current team.",
            "Both sides contained normal text, even when the names differed or the team link was old.",
            "Valid players failed to match their teams, while other players were sent to the wrong team. This changed the lowest draft pick.",
        ),
    },
    "q8": {
        "quwarts": q(
            "Position names",
            "QuWARTS did not change detailed positions into Frontcourt and Backcourt.",
            "It kept the detailed names found in the documents.",
            "The names and medal counts looked valid on their own. The checks did not know that the empty result came from missing position groups.",
            "The position rule removed every row before the medal average could be calculated.",
        ),
        "docetl": q(
            "Position names and missing values",
            "DocETL missed many positions and medal counts. It also did not create Frontcourt and Backcourt groups.",
            "The instruction gave no fixed position list. Unknown numbers became -1 and unknown text became empty.",
            "Detailed positions, empty text, and -1 all matched the basic output format.",
            "No position matched Frontcourt or Backcourt, so the result was empty.",
        ),
    },
    "q9": {
        "quwarts": q(
            "College names and title counts",
            "QuWARTS used several names for the same college and accepted some wrong NBA title counts.",
            "It kept names and numbers that appeared in the documents so that it would not lose possible facts.",
            "The checks did not know that two college names meant the same place or that a title number described the wrong event.",
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
            "It checked that the title field held a number, but it did not check that the number was a sensible count.",
            "Values such as 1986 and 2024 appeared in the documents and had the right number format.",
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
            "QuWARTS copied ages mentioned in articles instead of calculating age in 2026 from birth information.",
            "The question asked for age, so QuWARTS filled that value directly. It did not require birth information for a checked calculation.",
            "An old age from an article is still a normal number and appears in the source text.",
            "Old ages let some older players pass the 20 to 40 rule. Missing ages removed other players, and nationality names split more groups.",
        ),
        "docetl": q(
            "Age calculation and missing values",
            "DocETL copied ages from articles and used -1 when age was unclear.",
            "The instruction did not require age to be calculated from birth information.",
            "Old ages and -1 are both numbers, so the basic check accepted them.",
            "Wrong ages changed which players passed the 20 to 40 rule. Missing ages and different nationality names caused more errors.",
        ),
    },
    "q12": {
        "quwarts": q(
            "Team records and current facts",
            "QuWARTS created extra team rows from old sections, owner documents, people, and years.",
            "It keeps documents that may be useful and can create several rows from one document. It did not reduce them to one current row for each team.",
            "Each row can contain real words and numbers from the source, even when the row does not describe a current team.",
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
            "QuWARTS kept old and repeated team rows, different city names, and wrong founding years.",
            "It did not reduce several possible team rows to one current team row.",
            "An old city or year can appear in the source and look correct on its own.",
            "Different city names split the groups. Wrong founding years also removed Houston and Philadelphia.",
        ),
        "docetl": q(
            "Missing years and old locations",
            "DocETL used -1 for unknown founding years and sometimes chose old locations.",
            "The instruction allowed -1 for missing numbers and did not clearly require one current team record.",
            "-1 is a number and is less than 1970. Old locations are also normal text.",
            "Teams with unknown years were wrongly included. Other current teams appeared under old city names or wrong years.",
        ),
    },
    "q14": {
        "quwarts": q(
            "Owner names used for scoring",
            "The scoring data changes team owner names by using a separate owner table, but the question does not ask either system to use that table.",
            "QuWARTS follows the question and reads owner names from team documents. It also keeps old, legal, and short owner names.",
            "Those owner names really appear in team documents, so QuWARTS has no clear reason to replace them with the names used by the scorer.",
            "Related owner names became separate groups. Extra team rows added more owners. Part of this error comes from a scoring rule that was hidden from both systems.",
        ),
        "docetl": q(
            "Owner names used for scoring",
            "DocETL reads owner names from team documents, while the scoring data changes them by using a separate owner table.",
            "DocETL builds only the tables named by the question. It does not add a separate owner lookup that the question never requested.",
            "Names such as Dan Gilbert and Joseph Tsai are reasonable answers from team documents.",
            "These names did not exactly match the scorer's longer names. Old owners and missing rows caused more errors.",
        ),
    },
    "q15": {
        "quwarts": q(
            "Current locations and title totals",
            "QuWARTS kept old locations and old title totals instead of one current row for each team.",
            "It kept facts from different times because each fact appeared in a document.",
            "Old cities and totals look valid on their own. The checks could not tell which year the question expected.",
            "The question kept the wrong versions of teams. Different city names split groups, and wrong totals changed the averages.",
        ),
        "docetl": q(
            "Choosing current team facts",
            "DocETL chose old cities and title totals because the instruction did not clearly ask for the current facts.",
            "It made one row from each team document without a second step to choose the best time period.",
            "Old cities and title totals have the expected text and number formats.",
            "Old locations created extra groups, and wrong totals changed the averages.",
        ),
    },
    "q16": {
        "quwarts": q(
            "Owner coverage and age calculation",
            "QuWARTS built rows for only some owners and did not calculate age from birth information.",
            "The document sorting and extraction can miss documents or fields. QuWARTS also accepts ages stated directly in articles.",
            "A stated age is a normal number. There was no required check against birth information and 2026.",
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
            "QuWARTS missed an important owner and confused other years with the year a team was bought.",
            "It searched for a year in the source text but did not always prove that the year described the team purchase.",
            "A wrong year can still appear in the document and have the correct number format.",
            "The missing 2000 purchase changed the American minimum. A wrong 1996 year removed the Taiwanese-Canadian row.",
        ),
        "docetl": q(
            "Purchase years and nationality",
            "DocETL left most nationality values empty and used a company job year as a team purchase year.",
            "The field name was the main guide. The output did not include proof that the year described buying the team.",
            "The job year is still a number, and an empty nationality was allowed.",
            "Empty nationalities joined unrelated owners into one group. The wrong year could also pass the date rule.",
        ),
    },
    "q18": {
        "quwarts": q(
            "Population date and area",
            "QuWARTS used population numbers from different years or different areas.",
            "It saved one population number without also saving the date or whether it covered the city or the larger metro area.",
            "All the values looked like reasonable population numbers and appeared in the source text.",
            "Every state group was present, but the wrong population version changed six averages.",
        ),
        "docetl": q(
            "Missing states and populations",
            "DocETL left many state names empty and used -1 for unknown populations.",
            "The instruction allowed empty text and -1. These missing-value markers were not removed before calculation.",
            "Both markers matched the expected output format.",
            "Empty state names removed groups, while -1 lowered averages such as Florida.",
        ),
    },
    "q19": {
        "quwarts": q(
            "GDP units and population area",
            "QuWARTS mixed GDP values written in dollars, millions, and billions.",
            "It kept the number found in each document without changing all values to one unit.",
            "Each value was a number and appeared in the source text. The checks did not compare the units.",
            "The total added values that used different units. A metro population also caused Utah to pass a rule meant for city population.",
        ),
        "docetl": q(
            "GDP units and missing states",
            "DocETL saved GDP as a number without saving its unit. It also left some state names empty.",
            "It removed commas from numbers but did not change millions and billions to one common unit.",
            "Values on different scales are still numbers, and empty state names were allowed.",
            "Some cities disappeared because the state was empty. Other GDP values were added even though they used different units.",
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
