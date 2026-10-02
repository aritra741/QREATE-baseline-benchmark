# Invalid outputs: prompt bug, 2026-10-01 23:40 to 2026-10-02 13:20

An edit for E7b (context_probe.FieldSpec.line) moved the line " Answer No unless the document indicates Yes." under
the E7b `elif`, so it was dropped from every never-null yes/no field's prompt even with no experiment variables set.
Every step that started in that window and made new reads used prompts that differ from the recorded runs':
E7b-sr-nullhint, E7-stream-nullable-cspaper, E7c-stream-contradicted-cspaper, the five E2.1b-width runs,
E3.2-fragile on legal / med / cspaper, E3.2-oracle-cspaper, and E3.2-cap-cspaper (interrupted). Their outputs are kept
here for the record and are not used; the steps were reset and re-run with the fixed code. Found when the cspaper
`fragile` control (no queries to skip) differed from the recorded sweep and made 740 reads with new prompts; confirmed
by a replay of a recorded stream that stopped on an unrecorded prompt, and fixed when the same replay ran with zero
model calls and identical scores. A guard step (G0-prompt-guard) now runs that replay first in the GPU lane.
