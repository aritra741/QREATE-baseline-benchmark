# Deck review from the advisor's point of view (deck v45, 2026-10-12)

Read as the advisor would: she wants robust "why" knowledge (property, effect, mechanism, conditions, where it
breaks) that a VLDB/SIGMOD reviewer cannot knock over, not a list of design tips. Ordered by how much damage each
problem would do in the meeting.

## A. Problems that would undermine trust in the results

1. **Instability includes chance, and H1 to H10 were measured before we knew that.** Every instability number
   compares one sample with one other sample at temperature 0.1. The resend test shows 10 to 13% of answers change
   with the identical prompt (19 to 24% for lists). This touches H2 (the 5/10/20-document test ranks columns partly by
   chance), H3 (see A2), H7 (disagreement between two prompts includes disagreement from chance), H9 and H10 (their
   inputs are instability scores). Only H1 has been re-checked. The deck says "about a third is chance" on one slide
   but the slides before it still present the raw numbers as prompt effects.

2. **H3's threshold is smaller than the noise.** "Columns that gained or lost at least 5 points" on 30 documents: one
   document is 3.3 points, and a resend alone changes 4 to 24% of answers. Most of the "7 better alone, 11 better with
   others" counts can be produced by resending the same prompt. The conclusion (no general rule) may survive, but the
   counts do not support it as shown.

3. **H9's test is one column.** "Most unstable first" spent all 600 re-reads on a single list column. The
   comparison is that column against 39 (uniform) and 29 (random) columns, so it compares a column, not a selection
   rule. The new "lists are rarely fixed" reason is also measured mostly on that one column.

4. **H13 is a test our benchmark decides.** The drifted workload is built so that new queries ask for columns no
   earlier query used. "Forecasting from past queries never wins" is then a property of how we generated the queries,
   not of real workloads. The slide says this in its footer, but the verdict ("Wrong") and the "What it means" read as
   general findings.

5. **Two different meanings of "correct".** Per-answer accuracy (H3, H7, H9, H10, H11, H14) uses a lenient
   comparison (containment, number forms). Query scores use exact values. We saw the gap directly: damaging answers
   the lenient check called "correct" raised query scores. H14's puzzle ("answers more accurate, queries not better")
   is at least partly this mismatch, which the slide does not say.

6. **Absolute scores are low and never explained.** Our system scores 0.10 to 0.37, DocETL 0.06 to 0.17. The
   advisor will ask what 0.15 means, how the score is computed (it is defined nowhere in the deck), and whether "beats
   DocETL by 0.03" on papers is more than noise (the limits slide says differences under 0.03 to 0.05 cannot be told
   apart).

7. **DocETL setup will be questioned.** DocETL ran once, with Qwen 7B, a much weaker model than it is designed for,
   and answered only 21 of 27 queries on court cases. The deck does not say whether DocETL's own optimizer ran. A
   reviewer will call this a weakened baseline unless the deck states the setup and why it is fair.

8. **Our system uses correct answers; DocETL does not.** 20 correct answers per new column choose the re-reads. The
   green "no re-reads" bars answer this, but the headline ("beats DocETL on all five") uses the version with correct
   answers. On papers the label-free version beats DocETL by 0.03, inside the noise band.

9. **Design was tuned on the test queries** (limits slide). This is the single biggest threat to every system
   number, and it sits on slide 54 of 57. The advisor will want it first, or fixed (held-out queries or collection).

10. **The planner lowers accuracy.** Without it, scores are 0.014 to 0.015 higher on three collections. The planner's
    case rests on cost and on the budget slide, where the budget is defined as a fraction of the ablation's own spend
    (circular) and DocETL is absent.

## B. Slides that contradict each other (after today's corrections)

11. **Scoreboard is stale.** H5's tile still says "Confirmed: documents cause the changes"; the H5 slide now says
    "B's pattern, another cause" (the cluster appears on an identical resend, so it comes from the reply, not the
    document). The count "6 confirmed, 9 wrong, 3 partly" is therefore out of date, and the two added checks are not on
    the board.
12. **Conclusion still says "the documents cause it"** and "Guesses cannot be fixed by re-reading". Both rest on the
    withdrawn "the document leaves the answer unstated" mechanism.
13. **H7's "Why" uses the withdrawn mechanism:** "Disagreement means the document leaves room to guess".
14. **H10's "Why" uses it too:** "The checker detects documents that leave the answer open." Untested, and the same
    reason was refuted for instability.
15. **H6 against H5.** H6's "What really happens" is that the model builds on its own earlier answers (explanation
    A). H5 found A adds little (40% against 36%). Both can be true (one column against the average), but the deck
    states them as if they disagree, and H6 rests on one column (agent framework).
16. **H11's aside** ("invented items change between prompts, reworded truths stay") is untested, and lists change 19
    to 24% on a resend regardless of truth.
17. **H2 calls a negative correlation a "similarity" of 0.62.** The ranking compares instability with accuracy (high
    instability, low accuracy), so the true value is -0.62. Calling it similarity hides the direction.

## C. "Why" statements that are stories, not tests

The advisor's standard is property, effect, mechanism. These slides state a mechanism no experiment tested:

| Slide | Stated reason | Status |
|---|---|---|
| H6 | model builds on its earlier answers | one column, 93% example; not tested across columns |
| H7 | disagreement means the document leaves room to guess | withdrawn mechanism |
| H10 | checker finds documents that leave the answer open | withdrawn mechanism, untested |
| H14 | gains were wording, blanks, slightly different numbers | counted, but the metric mismatch (A5) is not separated |
| H16 | dates improved because the full biography made the model return only the year | untested |
| H17 | system already reads only rows a query can select | checked for two collections only |
| H9 | large model rarely fixes lists | mostly one column (A3) |

Tested and holding: H1 (with chance removed), H3 (changed answers are wrong both times), H5 (cluster on resend), H8
(direction toward the condition), H15 (lifetime vs mentioned century), H18 and blank vs wrong (controlled).

## D. Arbitrary numbers presented as standards

18. Pass marks and predicted sizes chosen by us without derivation: 0.6 rank similarity (H1, H2), "at least 5 points"
    (H3), "1.4 to 2 times" (H9), "at least half as often" (H15), "cost halves, score within 0.02" (H16), "20 documents
    suffice" (H2). A result is judged against a number nobody can defend. Replace with measured references: chance
    level (shuffled columns), repeat level (resend), and a range from resampling documents.
19. Experiment settings that look like findings: 20 documents, 20 correct answers per column, re-reads capped at 25%,
    16 questions per prompt, 20% of cells damaged. Say they were chosen, and which were varied.

## E. What the advisor will find missing for a VLDB/SIGMOD story

20. **No single thesis.** 18 hypotheses plus 2 checks, 57 slides, each with its own "What it means". The
    reader cannot tell which three insights the paper stands on. The scoreboard counts verdicts instead of naming
    insights.
21. **"What it means" boxes are design tips** ("Never blank an answer", "Put a question after the one it depends on",
    "Group questions to save cost", "Read partially only for facts stated early"). The advisor asked for conditions and
    mechanisms, not guidelines.
22. **Conditions and breakdowns are thin.** Most results are averages over 5 collections and 1 model family (Qwen).
    Where an effect flips (budget on medical, lists vs single values, row counts vs other queries) the deck reports it
    in footers instead of making it the finding.
23. **No problem statement or related work.** The setting slide shows a scenario; there is no definition of the
    problem (what is optimized, under what constraints), and no slide on how ZenDB, Evaporate, LOTUS, Palimpzest or
    DocETL's own optimizer handle drift or answer stability.
24. **One model family.** Every finding is Qwen 2.5 (7B and 32B); Llama appears only in an open question.

## F. Presentation

25. **Undefined terms:** query score, planner, re-read, "the 20-document test", list column vs single value, "correct
    answers" (gold). The glossary covers eight words, not these.
26. **Corrections scattered across slides** (H3 footer, fulldrift footer, ablations footer, H18a footer, asymmetry).
    Each one is honest, but together they read as unreliable. One errata slide would be better.
27. **Stale time words:** "Tested today", "Settled today", "Corrected today", "Today's tests" (section name). They
    will be wrong at the meeting.
28. **Length:** 57 slides for a weekly meeting. The H-slides could be one table of results with the 4 to 5 that carry
    the thesis expanded.

## Suggested order of fixes (cheapest first)

- B11 to B17, F27: text edits, under an hour.
- A2, A3, D18: recompute from saved data with chance and repeat reference levels (no model calls), about two hours.
- A1: rerun H2/H7 analyses using the resend data as the noise floor, about two hours.
- A5: report per-answer accuracy with the query scorer's exact comparison next to the lenient one, about an hour.
- A6/A7: one slide defining the score and DocETL's setup; needs the DocETL run config.
- A9, E20 to E24: decisions for you and the advisor, not edits.
