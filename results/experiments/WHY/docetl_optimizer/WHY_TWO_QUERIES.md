# Why DocETL misses medical Q12 and players QJ17 on Haiku (2026-10-14)

On the 8 queries of the optimizer comparison, our full system's lead on Haiku (0.626 against DocETL's 0.394) is two queries
that return one number scored exactly: medical Q12 (diseases treated with surgery, correct 21) and players QJ17 (teams in
cities over 1 million, correct 10). All runs below are on Haiku at its default sampling. DocETL "our wording" keeps DocETL's
design (one map per query and table, whole document, typed tool call) but uses our reader's per-query prompt text
(`exp_docetl_arms.py --arm ourwords`).

## QJ17: one team's city name

The city table comes out the same in every run ("New York City", "Phoenix", ...). The count is exact only if every one of the
10 big-city teams names its city exactly as the city table does. Neither system sees the city table's spellings.

| Setup | Runs with count 10 | What goes wrong |
|---|---|---|
| DocETL, harness wording | 0 of 1 | Knicks "New York" ("Keep names concise and normalized"; removing that sentence gives 10) |
| DocETL, our wording | 1 of 4 | Suns "Phoenix, Arizona" in 3 runs (the page opens "based in Phoenix, Arizona", then says "Phoenix" 70 times) |
| DocETL, our wording, build's columns | 0 of 1 | Suns "Phoenix, Arizona" |
| Our reader, per query, document in pieces | 2 of 4 | Knicks "New York City (Manhattan)", "Manhattan, New York City" |
| Our reader, per query, whole document | 3 of 3 | none |
| Our full system | 1 of 1 | none (Knicks pieces said "New York City" and "New York"; the tie goes to the first piece) |
| DocETL, our wording, structured output instead of tool call | 2 of 4 | Suns now "Phoenix" in 4 of 4, but the city page names itself "Phoenix, Arizona" in 2 of 4 |

Switching DocETL's answer form from tool call to structured output moves the long name from the team side to the city side:
each table is read on its own, both "Phoenix" and "Phoenix, Arizona" are faithful to their page, and the join holds only when
both sides pick the same one. An exact count over 10 joined teams needs all 10 to agree.

## Q12: over-reads and misses must cancel

83 of the 100 disease pages mention surgery, mostly in unrelated text (hospital ads, staff biographies, other diseases); 21 are
labelled as treated with surgery, and a few labels are themselves debatable. A count is exact only when wrong matches equal
missed ones.

| Setup | Count | Right | Wrong | Missed |
|---|---|---|---|---|
| DocETL, harness wording | 43 | 15 | 28 (4 on pages never mentioning surgery) | 6 |
| DocETL, our wording (4 runs) | 27-30 | 16-18 | 10-14 | 3-5 |
| DocETL, our wording, no "high recall" | 24 | 17 | 7 | 4 |
| DocETL, our wording, build's 9 columns (3 runs) | 13-14 | 8-10 | 4-6 | 11-13 |
| Our reader, per query, pieces (4 runs) | 29-34 | 15-17 | 13-17 | 4-6 |
| Our reader, per query, whole document (3 runs) | 32-34 | 16-17 | 15-17 | 4-5 |
| Our full system (3 runs) | 21, 17, 20 | 15, 13, 16 | 6, 4, 4 | 6, 8, 5 |

- DocETL's harness wording plus its "exhaustively (i.e., high recall)" system prompt lists all 11 treatment types on 18 pages.
- With the same wording per query, DocETL reads Q12 at least as well as our own per-query reader.
- Reading the build's 9 columns together cuts wrong matches to our full system's level (4-6) but also cuts recall sharply in
  DocETL; our full system kept 13 to 16 right. Over 3 runs it is exact once (21; then 17 and 20): what holds is few wrong
  matches (4-6 in every run, against 10-17 when the column is read for one query), not the exact count.

## Conclusion

With a strong model and the same wording, neither query separates the designs: QJ17 hangs on whether one team's free-text
city matches the other table's spelling, Q12 on whether over-reads and misses cancel. One property does hold: reading a list
column together with the table's other columns, without the query, gives fewer over-reads (4-6 wrong in all 3 full-system runs
and all 3 DocETL runs with the build's columns) at the cost of more misses. Replicate 2 of the full system crashed in the final
scoring step (both replicates finished in the same second; "unable to open database file"); its per-query views were saved and
are scored here like the others.
