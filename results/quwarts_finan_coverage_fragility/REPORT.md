# Finan coverage-selected program synthesis: fragility audit

Zero-token diagnostic. Frozen Finan artifacts were not altered.

Exact token ratio: `331,564 / 1,381,827` = 0.239946.
Absolute product lift over DocETL: +0.014748. Relative lift: +17.54%.
Of 16 queries, QuWARTS beats 5, ties 6, loses 5.

## Per-query contribution to the mean product difference

- `finan_multiagg20:q4`: QuWARTS 0.3750 vs DocETL 0.5000 (lose; mean contribution -0.007812)
- `finan_filter20:q9`: QuWARTS 0.3704 vs DocETL 0.0000 (beat; mean contribution +0.023148)
- `finan_filter20:q7`: QuWARTS 0.0000 vs DocETL 0.0000 (tie; mean contribution +0.000000)
- `finan_multiagg20:q11`: QuWARTS 0.0000 vs DocETL 0.1786 (lose; mean contribution -0.011161)
- `finan_multiagg20:q18`: QuWARTS 0.0163 vs DocETL 0.0000 (beat; mean contribution +0.001018)
- `finan_agg20:q4`: QuWARTS 0.3704 vs DocETL 0.0000 (beat; mean contribution +0.023148)
- `finan_groupby20:q14`: QuWARTS 0.1235 vs DocETL 0.0555 (beat; mean contribution +0.004248)
- `finan_agg20:q11`: QuWARTS 0.0000 vs DocETL 0.0000 (tie; mean contribution +0.000000)
- `finan_multiagg20:q9`: QuWARTS 0.0000 vs DocETL 0.1667 (lose; mean contribution -0.010417)
- `finan_agg20:q13`: QuWARTS 0.0000 vs DocETL 0.1852 (lose; mean contribution -0.011574)
- `finan_agg20:q17`: QuWARTS 0.0000 vs DocETL 0.0000 (tie; mean contribution +0.000000)
- `finan_filter20:q8`: QuWARTS 0.0000 vs DocETL 0.1299 (lose; mean contribution -0.008117)
- `finan_filter20:q11`: QuWARTS 0.0000 vs DocETL 0.0000 (tie; mean contribution +0.000000)
- `finan_filter20:q15`: QuWARTS 0.0000 vs DocETL 0.0000 (tie; mean contribution +0.000000)
- `finan_agg20:q3`: QuWARTS 0.0000 vs DocETL 0.0000 (tie; mean contribution +0.000000)
- `finan_agg20:q14`: QuWARTS 0.3261 vs DocETL 0.1299 (beat; mean contribution +0.012264)

With `finan_agg20:q14` removed: QuWARTS 0.083699, DocETL 0.081049.
Fraction of the overall advantage contributed by `q14`: 0.8316.

## Leave-one-query-out product

- remove `finan_multiagg20:q4`: QuWARTS 0.080438 vs DocETL 0.056377 (Δ +0.024060; reverses=False)
- remove `finan_filter20:q9`: QuWARTS 0.080746 vs DocETL 0.089710 (Δ -0.008964; reverses=True)
- remove `finan_filter20:q7`: QuWARTS 0.105438 vs DocETL 0.089710 (Δ +0.015727; reverses=False)
- remove `finan_multiagg20:q11`: QuWARTS 0.105438 vs DocETL 0.077806 (Δ +0.027632; reverses=False)
- remove `finan_multiagg20:q18`: QuWARTS 0.104352 vs DocETL 0.089710 (Δ +0.014642; reverses=False)
- remove `finan_agg20:q4`: QuWARTS 0.080746 vs DocETL 0.089710 (Δ -0.008964; reverses=True)
- remove `finan_groupby20:q14`: QuWARTS 0.097207 vs DocETL 0.086011 (Δ +0.011196; reverses=False)
- remove `finan_agg20:q11`: QuWARTS 0.105438 vs DocETL 0.089710 (Δ +0.015727; reverses=False)
- remove `finan_multiagg20:q9`: QuWARTS 0.105438 vs DocETL 0.078599 (Δ +0.026838; reverses=False)
- remove `finan_agg20:q13`: QuWARTS 0.105438 vs DocETL 0.077365 (Δ +0.028073; reverses=False)
- remove `finan_agg20:q17`: QuWARTS 0.105438 vs DocETL 0.089710 (Δ +0.015727; reverses=False)
- remove `finan_filter20:q8`: QuWARTS 0.105438 vs DocETL 0.081052 (Δ +0.024385; reverses=False)
- remove `finan_filter20:q11`: QuWARTS 0.105438 vs DocETL 0.089710 (Δ +0.015727; reverses=False)
- remove `finan_filter20:q15`: QuWARTS 0.105438 vs DocETL 0.089710 (Δ +0.015727; reverses=False)
- remove `finan_agg20:q3`: QuWARTS 0.105438 vs DocETL 0.089710 (Δ +0.015727; reverses=False)
- remove `finan_agg20:q14`: QuWARTS 0.083699 vs DocETL 0.081052 (Δ +0.002646; reverses=False)

Any single-query removal reverses the system ordering: True.
This audit does not change the frozen transfer policy.

