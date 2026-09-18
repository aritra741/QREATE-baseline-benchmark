# Signature population handoff

Med development corpus only. No Legal/Finan gold. No new model calls.

The compiler result that does not depend on the classifier:

> 551 eligible occurrences collapse to 55 shared predicates; rewritten queries preserve all 99 bags on gold.

---

## 1. Current path

```
Q (SQL)
  → parse_sql / classify_column / audit_workload     # AST usages
  → enumerate_predicates                             # atomic (attr, op, literal, transforms)
  → [A' row set held fixed]
  → population:
        emptiness_labels          # AST != '' / IS NULL from A' cell
        value_prompt | v2_prompt  # model, row-local
        document_prompt           # Step 5 escalate; v2 only if uncertain
  → PredicateLabel(sql_truth, classifier_status)
  → labels_to_cells / rewrite_cell                   # only sql_truth → INTEGER 1/0/NULL
  → close_attribute                                  # realizability (replay; not on the live compile path)
  → rewrite_sql                                      # LIKE / != ''  →  sig_* = 1
  → SQLite
```

`source_present` is parsed as provenance. After the gate fix it must not write `sql_truth`. Step 5’s **stored arm** still wiped labels when the document result was tagged `absent` (see §3).

Oracle gold materialization (`gold_signature_sql` + `materialize_signatures`) is eval-only.

---

## 2. Code map

| Stage | File | Functions |
|---|---|---|
| Parse / usages | `systems/WDIRS/quwarts/core/signature.py` | `parse_sql` (via workload), `classify_column`, `audit_sql`, `audit_workload` |
| Atomic predicates | same | `enumerate_predicates`, `AtomicPredicate` |
| Class split | `systems/WDIRS/quwarts/core/signature_realize.py` | `is_presence`, `is_absence`, `is_membership` |
| Two-column truth | `systems/WDIRS/quwarts/core/truth.py` | `PredicateLabel`, `rewrite_cell`, `label_from_classifier` |
| Step 5 prompts / parse | `systems/WDIRS/quwarts/core/signature_classify.py` | `value_prompt`, `document_prompt`, `parse_labels`, `emptiness_labels`, `needs_model` |
| v2 prompts / parse | same | `v2_prompt`, `parse_v2`, `needs_document` |
| Step 5 driver | `systems/WDIRS/quwarts/eval/step5_model_signatures.py` | `classify_one`, `main` (cache, escalate, `UPDATE`) |
| v2 driver | `systems/WDIRS/quwarts/eval/step5_v2_subset.py` | `entity_key`, `run`, `main` |
| Closure | `signature_realize.py` | `close_attribute`, `audit_rows`; applied in `eval/replay_hybrids.py` `apply_closure` |
| Rewrite | `signature.py` | `rewrite_sql` |
| Gold oracle (eval) | `signature.py` | `gold_signature_sql`, `materialize_signatures` |
| Hybrid recombine | `eval/replay_hybrids.py` | `copy_swap` / `overlay_columns` |
| Entity label slot | `systems/WDIRS/quwarts/core/models.py` | `EvidenceRecord.entity_label` (unused, not query-visible) |
| Observability CLI | `eval/observability_audit.py` | `main` |

Live `compile_workload` / `rematerialize_databases` still populate `__like` / `__vocab` surfaces. Signature columns are written by the eval drivers, not yet by the compiler population loop.

---

## 3. Prompts, schemas, mapping rules

### 3.1 Step 5 — value

`signature_classify.value_prompt`:

```
Classify each workload predicate for one extracted attribute value.
A predicate holds if the extracted value satisfies that operator and literal.
If the value is not enough to decide, mark that predicate UNKNOWN / uncertain.
Do not answer queries, aggregates, or CASE branches.
Return JSON: {"source_present": true|false, "labels":
[{"i": 1, "sql_truth": "TRUE|FALSE|NULL",
"classifier_status": "known|uncertain|failed"}, ...]}
ATTRIBUTE: {attribute}
VALUE:
{value}
PREDICATES:
{n}. op={operator} literal={json} transforms={lower,trim|none}
```

### 3.2 Step 5 — document

`signature_classify.document_prompt` (the stored arm used this text; it still *instructs* a gate):

```
Classify each workload predicate for one attribute of one document.
Use the document. The extracted value may be incomplete.
If the document does not determine the attribute, set source_present false
and every sql_truth to NULL.
...
ATTRIBUTE: {attribute}
EXTRACTED_VALUE: {value or <empty>}
PREDICATES: ...
DOCUMENT: {clip}
```

### 3.3 Step 5 — response → `sql_truth`

`parse_labels`:

| Model field | Maps to |
|---|---|
| `labels[i].sql_truth` `TRUE`/`T` | `TRUE` |
| `FALSE`/`F` | `FALSE` |
| `NULL`/`UNKNOWN`/missing | `NULL` |
| `classifier_status` `known`/`uncertain`/`failed` | stored as-is; `known`+`NULL` coerced to `uncertain` |
| missing label object | `NULL` + `failed` |
| `source_present` | returned separately; **must not** change `sql_truth` |

```python
# parse_labels (current)
sql_truth = _TRUTH.get(truth, "NULL")          # UNKNOWN → NULL
if sql_truth == "NULL" and classifier_status == "known":
    classifier_status = "uncertain"
# source_present is provenance. It must not gate sql_truth.
return present, labels
```

`rewrite_cell` / `labels_to_cells`: only `sql_truth` becomes `1` / `0` / SQL `NULL`. Status is dropped.

`label_from_classifier` (not the parse path, but the stated invariant) still maps `uncertain` / `failed` / `grounding-abstained` → `sql_truth=NULL`.

### 3.4 Step 5 — `source_present` in the stored arm

Parse no longer gates. The **driver still did**, on the stored Step 5 DB:

```python
# eval/step5_model_signatures.py after document call
labels.update(result.labels)
if result.source.endswith("absent"):
    labels = {
        pred.pred_id: PredicateLabel("NULL", ...)
        for pred in by_attr[attr]
    }
```

`classify_one` sets `source = source + "+absent"` when `present is False`. That wipe applies to **every** predicate on the attribute, including a prior `!= ''` from `emptiness_labels`.

`document_prompt` also tells the model to set every `sql_truth` to NULL when `source_present` is false. Many stored raw bodies did that themselves (`grounding-abstained`).

### 3.5 Step 5 — presence without the model

`needs_model` is false for `IS NULL` / `IS NOT NULL` / `=` `''` / `!=` `''`.

`emptiness_labels`: if the A' cell is non-missing, `!= ''` → `TRUE` known. If the cell is missing, `!= ''` is **left unset** (not FALSE). Document update / absent wipe then fills or clears it.

### 3.6 v2 — prompt and schema

`v2_prompt` (one call per entity–attribute; all predicates for that attribute):

```
Classify whether each concept applies to this entity.
Multiple concepts may be true at once.
Absence of a literal string is not evidence of falsehood and is not SQL NULL.
Infer from the entity name or context when the literal is not written.
applies is the semantic result. basis and status are metadata only.
Do not answer queries, aggregates, or CASE branches.
Return JSON: {"concepts": [{"i": 1, "applies": "true|false|unknown",
"basis": "explicitly_stated|inferred_from_entity|inferred_from_context",
"status": "known|uncertain"}, ...]}
ATTRIBUTE: {attribute}
ENTITY: {entity_key}
SURFACES: {extracted cell + *_name columns}
CONCEPTS:
{n}. op=... literal=... transforms=...
DOCUMENT: {optional}
```

`parse_v2`: `applies` true/yes → `TRUE`; false/no → `FALSE`; unknown → `NULL`. Empty `status` → `uncertain` if NULL else `known`. Missing concept → `NULL`/`failed`. `basis` is not stored on `PredicateLabel`.

v2 still sends **presence and membership in the same CONCEPTS list**. There is no separate existence operator.

### 3.7 Realizability closure

Not on the compile path. Used in `replay_hybrids.apply_closure`.

```python
# close_attribute
LIKE=TRUE  ⇒  nonempty=TRUE      # even if classifier left nonempty NULL
nonempty=FALSE and no LIKE=TRUE  ⇒  every LIKE NULL/TRUE becomes FALSE
nonempty=FALSE and LIKE=TRUE     ⇒  nonempty forced TRUE (membership wins)
```

Gold signatures: 0 illegal rows. Stored Step 5: 1. Stored v2 subset: 10, all `membership_true_nonempty_not_true`.

### 3.8 Preservation vs replacement of earlier evidence

| Path | What is kept |
|---|---|
| Step 5 value cache | Distinct A' **cell string** → all `needs_model` labels for that attribute |
| Step 5 document | `labels.update` overwrites cache; `absent` replaces the **whole** attribute vector with NULL |
| v2 | `UPDATE` all `sig_*` for that attribute from the last call (entity or document) |
| Hybrid replay | Column overlay: v2 membership `sig_*` + Step 5 presence `sig_*` on a copy of Step 5. A' base columns untouched |
| Closure | Only repairs illegal `(membership, nonempty)` pairs; does not call the model |
| A' row set / keys / non-`sig_` columns | Held byte-identical in Steps 4–5 and hybrids |

---

## 4. Predicate summary (this Q)

Classes are AST-generic (`signature_realize`). Counts are this workload.

| Class | Rule | Predicates | Occurrences | Queries |
|---|---|---:|---:|---:|
| Presence | `!=` and literal `''` | 20 | 236 | 99 |
| Membership | `LIKE`, or `=`/`IN` with a nonempty literal | 35 | 315 | 95 |
| Comparison / null | `IS NULL`, `IS NOT NULL`, `=` `''`, numeric cmp | **0** | 0 | 0 |
| Full-value-required | Equijoin, var-compare, `COUNT(DISTINCT)`, raw group/project — **not** signature predicates | 6 attrs | 354 | 52 |

Full-value attributes (out of this mechanism): `disease.disease_name`, `drug.disease_name`, `institution.research_diseases`, `*.id`.

Presence and membership **share attributes**. A typical CASE column has one `!= ''` plus several `LIKE`s. They must stay independent atoms: `nonempty` is not `OR` of visible LIKEs.

---

## 5. Ten traces (from stored arms)

Gold here is the eval oracle signature, not a method input.

### Presence: gold TRUE → model NULL

**T1.** `institution/450993.txt` · `institution.institution_type != ''`  
A' cell empty. Step 5 left presence unset, then document `source_present: false`. Model NULL. Same row: gold `LIKE '%university%'` is TRUE (T3).

**T2.** `drug/391379.txt` · `drug.pharmaceutical_form != ''` (v2)  
Gold nonempty TRUE (form is tablet). A' `pharmaceutical_form` is NULL. v2 `applies: unknown` on `!= ''` → SQL NULL. Membership on the same row is TRUE (T5). Illegal pair, T7.

### Membership: gold TRUE → model NULL

**T3.** `institution/450993.txt` · `institution_type LIKE '%university%'`  
Gold TRUE. A' type NULL. Step 5 document `source_present: false` → NULL / grounding-abstained.

**T4.** `drug/125390.txt` · `administration_route LIKE '%subcutaneous%'`  
Gold TRUE. A' surface `"injections"`. Step 5 NULL, `source_present: false`. The cell is a related word, not the LIKE token; the model treated that as “not present.”

### Inferred membership without a form-column span

**T5.** `drug/391379.txt` · `pharmaceutical_form LIKE '%tablet%'`  
A' form NULL (no literal in the extracted cell). Step 5 sig NULL. v2 `tablet=TRUE`. Gold TRUE. This is the intended membership task. Presence on the same row was left NULL (T2).

**T6.** `drug/1110.txt` · same LIKE  
A' form `"tablets"`. Step 5 still NULL. v2 `tablet=TRUE`. Gold TRUE. Shows Step 5 failed even when the surface contained the token; v2 recovered.

### Realizability violation

**T7.** `drug/1110.txt` (v2): `tablet=1`, `!= ''` NULL. `close_attribute` → `membership_true_nonempty_not_true`, force nonempty=1.

**T8.** `drug/245092.txt` (v2): `capsule=1`, `!= ''` = 0. Same repair: nonempty forced TRUE.

### Grounded presence extraction

**T9.** `drug/88704.txt` · `manufacturer != ''`  
A' `"Ascend Laboratories, LLC"`. `emptiness_labels` → TRUE known. Gold TRUE. No model call. Span-supported in the presence audit (27/28 gold-TRUE manufacturers appear in the document).

**T10.** `drug/203427.txt` · same predicate  
A' `"Lupin Limited"`. Step 5 TRUE, gold TRUE. Same path as T9.

---

## 6. Implementation answers

**Can presence and membership be populated independently and recombined?**  
Yes. `is_presence` / `is_membership` already split the 55 atoms. Hybrid replay overlaid v2 LIKE columns onto Step 5 `!= ''` columns and scored 0.137 vs Step 5 0.125 vs raw v2 0.094. Closure is a third, deterministic pass. Do not derive nonempty as OR of LIKEs.

**Does abstention overwrite earlier evidence?**  
On the stored Step 5 document path, yes: `absent` replaces the whole attribute vector, including a known `!= ''` from `emptiness_labels`. v2 `UPDATE`s every `sig_*` for the attribute from the last call. Hybrid overlay is the pattern that does **not** overwrite presence with membership abstention.

**Can all predicates for one entity–attribute pair be classified in one call?**  
v2 already does that (`CONCEPTS` is the full attribute list). That is necessary for multilabel consistency and cost. It is **not** sufficient: presence and membership must not share one decision rule inside that call. Either two operators in one JSON (`exists`, `applies[]`) or two calls with recombination.

**Which current decisions depend on Med-specific column names?**  
In **core**, only the Step 0 gate checklist in `audit_workload`:

```python
vocab = (
    "disease_type", "research_fields", "prescription_status",
    "institution_type", "administration_route", "pharmaceutical_form",
)
```

Classification, rewrite, closure, and `is_presence` / `is_membership` are AST-typed. Eval-only Med strings: `queries_for("Med")`, `gold_name("Med")`, `TARGET = ("drug.manufacturer", "drug.pharmaceutical_form")`, `NAME_COLS` in diagnostics/replay. `entity_key` uses generic `{table}_name` / `generic_name` / `name`, then doc stem — no ontology tokens.

**Smallest generic change for the two operators**

1. **Grounded value-existence** — select with `is_presence` (already: `!=` + `''`). Populate from (a) non-missing extracted cell, else (b) a span-grounded extract of *any* value for that attribute, else NULL. Do not ask “is the LIKE token in the text.” Do not set FALSE from an empty latent column.

2. **Semantic concept-membership** — select with `is_membership` (already: `LIKE` / nonempty `=` / `IN`). Populate with the v2 `applies` head only. `basis` stays metadata. Never write `sql_truth` from `source_present`.

Wire both in `signature_classify` (two heads or two functions) and in the driver (`overlay` like `replay_hybrids`). Run `close_attribute` before `rewrite_sql`. Remove the `absent` wipe and the document prompt sentence that sets every `sql_truth` to NULL.

**Can both operators be selected entirely from AST predicate type?**  
Yes. `is_presence` / `is_membership` / `is_absence` do not use dataset or attribute names. This Q has zero comparison/null signature predicates; if `IS NULL` or `id >= k` appears later, add a third AST class the same way. Do not special-case `manufacturer` vs `tablet` by name. Defer manufacturer as a *spend* choice (extraction-recall of a 29% nonempty class), not as a different operator.

---

## Appendix — excerpts

Rewrite (membership and presence become the same physical form: `sig = 1`):

```python
# signature.py rewrite_sql
sig = exp.Column(this=exp.to_identifier(pred.sig_name), table=...)
node.replace(exp.EQ(this=sig, expression=exp.Literal.number(1)))
```

Gold CASE (eval only):

```python
f"CASE WHEN {col} IS NULL THEN NULL WHEN {pred.bare_condition_sql} THEN 1 ELSE 0 END"
```

Presence vs membership:

```python
def is_presence(pred):
    return pred.operator == "!=" and pred.literal == ""

def is_membership(pred):
    if pred.operator == "LIKE":
        return True
    if pred.operator in {"=", "IN"} and pred.literal not in (None, ""):
        return True
    return False
```
