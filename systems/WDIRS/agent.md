
# QuWARTS Build Specification

Query-workload-aware relational database synthesis from unstructured text under
a token budget. Input is SQL. Search has no access to query answers.

Read this file end to end before writing code. Section 3 invariants and Section
9 soundness rules are enforced by tests. Violating Section 3 invalidates
experimental results; violating Section 9 produces silently wrong answers.

---

## 1. Problem Statement

**Given**
- `T`: a corpus of text documents
- `Q`: a workload of SQL statements
- `theta`: a token budget in LLM tokens

**Produce**
- `L`: a published logical schema, inferred from `T` and `Q`
- `SPP`: a set of configurations, each a triple `<schema, pop, pre>`
- One materialized SQLite database per configuration, hashed and immutable
- A static router assigning each statement in `Q` to exactly one database
- A provably equivalent SQL rewrite of each statement against its assigned
  physical schema

**Objective.** Minimize `sum over q in Q of Error(T, q, D_q, rewrite(q, s_q))`
subject to `Cost(T, SPP) <= theta`, where `Error = 1 - F1` under the column-wise
aligned scoring protocol of Section 20.

**Why a surrogate is required.** `Error` compares `q(T)` against `q'(D)`.
Computing `q(T)` requires a correct corpus-wide answer, which is the task
itself. No sub-corpus sample gives an unbiased estimate, because the quantities
determining configuration quality (entity collision rate, distinct-value
multiplicity `n/d`, join fan-out) scale superlinearly with corpus size. Search
therefore ranks configurations by a surrogate `U_hat` computed from structural
properties of materialized databases.

**What SQL input removes.** Query translation is no longer an unobservable error
source. Rewrites are deterministic and statically verified, so the only
remaining error term is data error from extraction and population. Search
optimizes one thing rather than a composition through an uncontrolled module.

---

## 2. Schema Provenance Assumption

Users write SQL, but the physical schema is a system output. The circularity is
resolved as follows and this resolution is load-bearing.

1. The system infers and publishes a **logical schema** `L` from `T` and `Q`:
   entity types, attributes, types, and relationships. `L` is a contract, not a
   physical design. It specifies no normalization level, no table layout, no
   population policy, no grain commitment.
2. Users write SQL against `L`.
3. Synthesis searches **physical** designs `s` that support provably equivalent
   rewrites of statements written against `L`.

Schema search survives because `L` fixes semantics while leaving physical
representation free. Normalization level, table decomposition, and grain remain
search variables.

If `Q` is supplied before `L` exists, run Section 8.1 canonicalization on the
raw statements to induce `L` from the referenced identifiers, then re-bind the
statements to `L`. Binding failures are reported to the user as schema conflicts
and are not silently repaired.

---

## 3. Invariants

**I1. Evaluation firewall.** `quwarts/eval/` may import `quwarts/core/`.
`quwarts/core/` may never import `quwarts/eval/`. Ground truth lives only under
`data/gold/` and is readable only by `quwarts/eval/`. Enforced by an import
linter test and a filesystem access guard in CI.

**I2. Single token ledger.** Every LLM call passes through
`TokenLedger.spend()`. A call exceeding `theta` raises `BudgetExhausted`. No
module calls a model client directly.

**I3. Deterministic replay.** Given a fixed seed, evidence store, and
configuration, materialization is byte-identical. All randomness is seeded and
recorded.

**I4. Evidence reuse is mandatory.** No extraction is performed for a
`(segment_id, attribute, extractor_cfg, quality_tier)` tuple already present in
the evidence store. Cache hit rate is a reported metric.

**I5. Immutable materialization.** A hashed database is never mutated.
Re-population produces a new file with a new hash.

**I6. No approximate rewrites.** A rewrite is emitted only when equivalence is
proved under the declared constraints of the physical schema. Best-effort
rewrites are rejected, not degraded.

**I7. Commitment is free, extraction is not.** Any operation that costs tokens
lives in the evidence layer. Population modules are deterministic views over
evidence. LLM-backed population strategies are hoisted into the evidence layer
as shared annotations, never executed per configuration.

---

## 4. Naming Conventions

Fixed identifiers. No synonyms, no reuse across modules.

| Name | Meaning | Module |
|---|---|---|
| `L` | published logical schema | `core/logical` |
| `amp(a)` | amplification factor of attribute `a` | `core/amplify` |
| `amp_role(a, role)` | per-role component of `amp(a)` | `core/amplify` |
| `rho(a)` | within-template extraction error correlation | `core/pilot` |
| `R(q, s)` | rewritability predicate, boolean | `core/rewrite` |
| `freq(t)` | statement count for template `t` | `core/workload` |
| `slice(a)` | extraction slice for attribute `a` | `core/workload` |
| `widen_coef`, `widen_exp` | progressive widening parameters | `core/search` |
| `explore_coef` | exploration coefficient in selection | `core/search` |
| `theta` | global token budget | `core/ledger` |
| `U_hat` | surrogate utility | `core/surrogate` |

`amp` and `widen_coef` are distinct quantities and must not share an identifier.

---

## 5. Repository Layout

```
quwarts/
  core/
    logical/         # logical schema inference, statement binding
    workload/        # SQL parsing, canonicalization, templating, requirements
    conflict/        # presupposition extraction, conflict graph, clustering
    rewrite/         # R(q, s), equivalence-preserving rewriter
    schema/          # physical schema candidate generation
    preprocess/      # Pre policies
    extract/         # staged extractor, evidence store, cache
    pilot/           # pilot extraction, statistics, rho
    amplify/         # amplification calculus
    population/      # deterministic views over evidence, per attribute
    materialize/     # SQLite writer, hashing, coverage sets
    surrogate/       # U_hat signals and aggregation
    search/          # budget-aware search
    route/           # static routing from clusters and feasibility
    ledger/          # TokenLedger
  eval/              # Error(), F1 protocol, gold loaders. FIREWALLED.
  cli/
  tests/
data/
  corpora/
  workloads/         # SQL statements
  gold/              # readable only by quwarts/eval
artifacts/
  evidence/
  databases/
  pilots/
  runs/
```

---

## 6. Data Contracts

Pydantic models, JSON-serialized, each carrying `schema_version`.

### 6.1 Logical schema

```python
class LogicalAttribute(BaseModel):
    name: str
    entity_type: str
    dtype: Literal["string", "numeric", "date", "categorical", "multivalued"]
    unit_domain: str | None          # canonical unit family, if any
    nullable: bool

class LogicalSchema(BaseModel):
    id: str
    entity_types: list[str]
    attributes: list[LogicalAttribute]
    relationships: list[LogicalRelationship]
    identity_grain: dict[str, str]   # entity_type -> declared finest grain
```

### 6.2 Template and requirements

```python
class Role(str, Enum):
    KEY = "key"                      # part of alignment composite key
    JOIN = "join"
    GROUP = "group"
    PREDICATE = "predicate"
    AGG_ADDITIVE = "agg_additive"    # SUM, AVG
    AGG_DISTINCT = "agg_distinct"    # COUNT DISTINCT
    AGG_EXTREMAL = "agg_extremal"    # MAX, MIN, TOP-K
    PROJECT = "project"

class ParamSlot(BaseModel):
    slot_id: str
    attribute: str
    op: str                          # =, <, >, BETWEEN, IN, LIKE
    dtype: str
    observed_constants: list[Any]    # retained, not discarded

class Template(BaseModel):
    id: str                          # hash of parameterized canonical AST
    canonical_sql: str
    param_slots: list[ParamSlot]
    statement_ids: list[str]
    freq: int
    roles_by_attribute: dict[str, set[Role]]
    slice_safe: bool                 # Section 9
    shape: TemplateShape             # Section 9 classification

class AttributeStats(BaseModel):
    n_rows: int                      # base relation cardinality estimate
    n_groups: int
    group_size: float                # m, mean fan-in
    n_distinct: int                  # d
    multiplicity: float              # n / d
    rho: float                       # Section 13.3
    n_scored_columns: int            # C_cols

class AttributeRequirement(BaseModel):
    name: str
    entity_type: str
    dtype: str
    roles: set[Role]
    templates: list[str]
    freq_weight: float               # sum of freq over touching templates
    finest_grain: str                # least-commitment grain required
    required_forms: set[str]         # e.g. {"surface", "parsed", "unit:usd"}
    slice: SliceSpec                 # union of demanded predicate ranges
    stats: AttributeStats | None     # null until pilot completes
    amp: float | None                # null until pilot completes
```

### 6.3 Conflict model

```python
class Presupposition(BaseModel):
    entity_type: str
    attribute: str | None
    module: Literal["er", "norm", "unit", "type", "miss", "grain"]
    demand: str                      # e.g. "merge", "no_merge", "unit:usd", "nulls_preserved"
    destructive: bool                # true if it destroys information another demand needs

class ConflictEdge(BaseModel):
    template_a: str
    template_b: str
    cell: tuple[str, str, str]       # entity_type, attribute, module
    demands: tuple[str, str]
    destructive: bool

class ConflictCluster(BaseModel):
    id: str
    template_ids: list[str]
    resolved_demands: dict[str, str] # cell -> demand
```

### 6.4 Configuration and artifacts

```python
class ModuleConfig(BaseModel):
    strategy: str
    params: dict[str, Any]

class PopulationPolicy(BaseModel):
    er: dict[str, ModuleConfig]      # attribute -> config
    norm: dict[str, ModuleConfig]
    unit: dict[str, ModuleConfig]
    type: dict[str, ModuleConfig]
    miss: dict[str, ModuleConfig]
    grain: dict[str, str]            # entity_type -> materialized grain

class PreprocessPolicy(BaseModel):
    mode: Literal["whole_document", "fixed_chunk", "semantic_chunk"]
    chunk_tokens: int | None
    overlap_tokens: int | None
    carry_metadata: list[str]

class PhysicalSchema(BaseModel):
    id: str
    pattern: Literal["denormalized", "star", "snowflake"]
    relations: list[Relation]
    primary_keys: dict[str, list[str]]
    foreign_keys: list[ForeignKey]
    declared_fds: list[FunctionalDependency]
    declared_dcs: list[DenialConstraint]
    covered_attributes: set[str]

class Configuration(BaseModel):
    id: str
    schema: PhysicalSchema
    pop: PopulationPolicy
    pre: PreprocessPolicy
    cluster_id: str

class CoverageSet(BaseModel):
    attribute_ranges: dict[str, SliceSpec]   # where population is complete
    attributes_present: set[str]
    grain: dict[str, str]
    forms: dict[str, set[str]]
    corpus_fingerprint: str

class MaterializedDB(BaseModel):
    config_id: str
    sqlite_path: str
    sha256: str
    row_counts: dict[str, int]
    tokens_spent: int
    coverage: CoverageSet
    surrogate: SurrogateReport
```

`declared_fds` and `declared_dcs` are required. The surrogate uses violation
rates against declared constraints as its only supervision signal, so a schema
declaring nothing scores nothing. Generation always emits primary keys and the
dependencies implied by `L`.

---

## 7. Pipeline

```
Q (SQL) ──> Canonicalize ──> Templates ──> Requirements (roles, slices, grain)
                                 │              │
                                 v              │
                          ConflictGraph         │
                                 │              │
                                 v              │
                          ConflictClusters      │
                                 │              │
T ──> LogicalSchema L <──────────┘              │
       │                                        │
       v                                        v
  PhysicalSchemaGen ──> R(q, s) feasibility ──> admissible SPP candidates
       │                                        │
       └──> PilotExtraction ──> Stats (n, m, d, rho, C_cols)
                                        │
                                        v
                                   amp(a) ──> BudgetAllocator
                                        │
                                        v
                        StagedExtractor (slice-gated, recall-biased Stage 1)
                                        │
                                        v
                          Least-commitment EvidenceStore  [shared]
                                        │
                     ┌──────────────────┼──────────────────┐
                     v                  v                  v
               PopulationPolicy   PopulationPolicy   PopulationPolicy   (free)
                     │                  │                  │
                     v                  v                  v
                 SQLite + hash + CoverageSet  (one per configuration)
                                        │
                                        v
                                     U_hat
                                        │
                                        v
                             Search under theta ──> SPP
                                        │
                                        v
                        Static router ──> rewrite(q, s_q) ──> execute
                                        │
                             [FIREWALL] │
                                        v
                                  eval.Error()   (offline only)
```

---

## 8. Workload Analysis

### 8.1 Canonicalization and templating

1. Parse each statement to an AST. Bind identifiers to `L`; report binding
   failures rather than repairing them.
2. Canonicalize: alias-independent form, sorted conjuncts, canonical join
   order, folded constant arithmetic, normalized subquery form.
3. Abstract literals in comparison predicates to typed `ParamSlot`s. Retain
   observed constants per slot.
4. Hash the parameterized canonical AST. Equal hashes define a template.
5. Record `freq(t)` as the number of statements collapsing into `t`.

Templates are the unit of workload accounting. Conflict detection, `amp(a)`
computation, and slice derivation all operate on templates. Constants are
retained because soundness depends on the literals; the template records only
which slots vary.

### 8.2 Role extraction

Read directly off the AST. No inference.

| Role | Source |
|---|---|
| `JOIN` | equijoin predicate operands |
| `KEY` | primary key of the entity, plus attributes forming the alignment composite key |
| `GROUP` | `GROUP BY` list |
| `PREDICATE` | `WHERE` and `HAVING` comparison operands |
| `AGG_ADDITIVE` | `SUM`, `AVG` arguments |
| `AGG_DISTINCT` | `COUNT(DISTINCT ...)` arguments |
| `AGG_EXTREMAL` | `MAX`, `MIN`, `ORDER BY ... LIMIT k` arguments |
| `PROJECT` | select list, otherwise unused |

`C_cols` for attribute `a` is the number of scored output columns across
templates touching `a`.

### 8.3 Slice derivation

For each attribute, `slice(a)` is the union over all templates of the predicate
ranges demanded on `a`, with constants taken from `observed_constants`. An
attribute referenced by any slice-unsafe template has `slice(a) = FULL`.

### 8.4 Grain and form derivation

`finest_grain(a)` is the finest identity grain demanded by any template
touching `a`. `required_forms(a)` is the union of representational demands, for
example `{"surface", "unit:usd"}` when one template compares raw strings and
another aggregates a converted unit. Both drive the least-commitment extraction
of Section 11.

---

## 9. Slice Safety

Staged extraction is unsound for some template shapes. Misclassification here
produces silently wrong answers that no surrogate detects. This is the highest
soundness risk in the system.

```python
class TemplateShape(str, Enum):
    FILTERED_AGGREGATE = "filtered_aggregate"
    FILTERED_PROJECTION = "filtered_projection"
    UNFILTERED_AGGREGATE = "unfiltered_aggregate"
    BASE_CARDINALITY = "base_cardinality"
    ANTI_JOIN = "anti_join"
    CROSS_ATTRIBUTE_FILTER = "cross_attribute_filter"
```

| Shape | Slice-safe | Reason |
|---|---|---|
| `FILTERED_AGGREGATE` | yes | only qualifying rows contribute |
| `FILTERED_PROJECTION` | yes | same |
| `UNFILTERED_AGGREGATE` | no | needs full population |
| `BASE_CARDINALITY` (`COUNT(*)`) | no | depends on non-qualifying rows |
| `ANTI_JOIN` (`NOT EXISTS`, `NOT IN`, `LEFT JOIN ... IS NULL`, `EXCEPT`) | no | correctness depends on absent rows |
| `CROSS_ATTRIBUTE_FILTER` | partially | slice union across attributes required |

Classification rules:
- Any negated existential or set-difference construct forces `ANTI_JOIN`.
- Any aggregate whose input relation has no restricting predicate on the
  aggregated entity forces `UNFILTERED_AGGREGATE`.
- `COUNT(*)` without a predicate on the counted entity forces
  `BASE_CARDINALITY`.
- A template filtering on attribute `x` while aggregating attribute `y` yields
  `CROSS_ATTRIBUTE_FILTER`; `slice(y)` must include the slice induced by the
  predicate on `x`.
- Default on any unrecognized construct is slice-unsafe. Fail closed.

Testing requirement: property-based tests compare staged extraction against
full materialization on a small corpus for every template shape, asserting
identical query results. This test gates M6.

---

## 10. Rewritability and Feasibility

`R(q, s)` attempts an equivalence-preserving rewrite of template `q` against
physical schema `s`, using the declared keys, foreign keys, and functional
dependencies of `s`.

Permitted rewrite operations:
- join elimination and introduction justified by declared foreign keys
- projection and predicate pushdown
- aggregate rewriting over a declared functional dependency
- grain coarsening by `GROUP BY` when `s` materializes a finer grain
- view substitution for deterministic derived columns

Forbidden:
- any rewrite requiring an undeclared dependency
- any rewrite over a grain coarser than `finest_grain` for a touched attribute
- any rewrite requiring a representational form absent from `forms` in the
  coverage set
- approximate or best-effort rewrites (I6)

Feasibility rules:
- `R(q, s) = 0` makes `s` infeasible **for `q` only**. `s` is retained for other
  templates.
- `SPP` is **admissible** only if every template has at least one configuration
  with `R(q, s) = 1` and whose coverage set contains `q`'s constants.
- Admissibility is checked before any extraction. Inadmissible candidate sets
  are pruned at zero token cost.

---

## 11. Conflict Analysis and Static Routing

### 11.1 Presupposition extraction

For each template, derive its demands per `(entity_type, attribute, module)`
cell: identity grain, value form, unit, null semantics. Two templates conflict
on a cell when their demands are contradictory.

A conflict is **destructive** when satisfying one demand irrecoverably destroys
information the other requires. Coarsening is derivable from a finer form;
merging, canonicalizing, converting, and imputing are not reversible.

| Conflict | Destructive | Separate database required |
|---|---|---|
| ER merge vs. no-merge on one entity type | yes | yes |
| Lossy unit or value canonicalization | yes | yes, unless both forms stored |
| Imputation vs. null preservation on a column | yes | yes, unless nullability preserved and imputation pushed into SQL |
| Physical normalization level | yes | yes, schema is a whole-database property |
| Different extractors for different attributes | no | no, per-attribute policies suffice |
| Different output granularity | no | no, finest grain plus `GROUP BY` suffices |

Non-destructive conflicts are resolved by storing the finer or richer form and
deriving the rest. Only destructive conflicts partition the workload.

Note the interaction with per-attribute population policies: attribute-indexed
policies absorb the two non-destructive rows into a single database, which
reduces how often portfolios are needed. Report the measured mix of conflict
types; it determines how much of the portfolio result is attributable to
conflicts rather than to allocation.

### 11.2 Clustering

Build a conflict graph over templates with destructive edges only. Partition
into conflict-free clusters by greedy coloring, minimizing cluster count. Each
cluster receives a consistent `resolved_demands` map, which fixes `pop.grain`,
`pop.er`, `pop.unit`, and `pop.miss` demands for its configurations.

### 11.3 Static routing and monotonicity

Routing is a static lookup, not a scored choice:

```
route(q) = a configuration c such that
           c.cluster_id == cluster(q)
           and R(q, c.schema) == 1
           and q.constants subset of c.coverage.attribute_ranges
```

Ties are broken by a deterministic rule recorded in the run manifest.

Because assignment is determined by static structure rather than by
`argmax U_hat`, adding a configuration to `SPP` cannot reroute an
already-served template. The objective is therefore monotone in `SPP`, and
cost-weighted greedy selection under the budget constraint recovers its
approximation guarantee. This is a consequence of SQL input plus static
clustering, not an added assumption. Assert monotonicity in a test: for random
`SPP` subsets, adding a configuration never increases realized error in the
offline harness.

---

## 12. Least-Commitment Evidence Layer

Separate the two operations the earlier design conflated:

- **Extraction** reads the corpus and costs tokens.
- **Commitment** transforms extracted values and is deterministic, hence free.

Every conflict-causing operation is a commitment. The evidence layer therefore
stores the least-committed form that any template requires.

| Dimension | Evidence layer stores | Commitment deferred to population |
|---|---|---|
| Entity identity | unmerged mention-level records with candidate keys | ER merge at a chosen grain |
| Value form | surface string plus parsed value | normalization, canonicalization |
| Units | original unit as extracted | conversion to a target unit |
| Missingness | null preserved with a reason code | imputation |
| Granularity | finest grain any template requires | aggregation to coarser grain |

```python
class EvidenceRecord(BaseModel):
    key: str                 # sha256(segment_id | attribute | extractor_cfg_hash | tier)
    segment_id: str
    doc_id: str
    template_cluster_id: str | None   # document format cluster, for rho
    attribute: str
    surface_value: str | None
    parsed_value: Any | None
    original_unit: str | None
    null_reason: str | None
    candidate_keys: dict[str, str]    # uncommitted identity signals
    span: tuple[int, int] | None
    confidence: float | None
    extractor_cfg_hash: str
    quality_tier: Literal["cheap", "expensive"]
    stage: Literal[1, 2, 3]
    tokens_spent: int
```

Consequence: two conflicting templates differing only in commitment cost **zero
additional tokens**. Two SQLite files are materialized from one evidence store.
Population modules are pure deterministic views (I7).

LLM-backed population strategies are not free views. They are hoisted into the
evidence layer as additional shared annotations, extracted once and reused
across configurations.

---

## 13. Staged Extraction and Amplification

### 13.1 Staging

Predicate pushdown cannot precede extraction, because determining a filter
attribute's value *is* extraction. Staging recovers the saving:

**Stage 1.** Extract only filter attributes appearing in template predicates,
ordered by estimated selectivity divided by extraction cost. Configuration is
**recall-biased** and over-admits.

**Stage 2.** Extract remaining attributes only for entities surviving Stage 1,
restricted to `slice(a)`.

**Stage 3.** Refine the admitted set with the expensive tier when the filter
attribute also occupies an output, grouping, or key position.

Savings scale as `(1 - selectivity) * cost(remaining attributes)`.

The Stage 1 recall bias is mandatory and asymmetric. A false negative removes an
entity permanently, and under the alignment protocol a dropped row contributes
zero numerator mass to **every** scored column. Over-admission costs tokens;
under-admission costs recall on all columns at once. Set Stage 1 thresholds well
toward recall and treat the threshold as an ablated parameter, not a default.

Attributes touched by any slice-unsafe template are extracted at `FULL` slice
regardless of staging.

### 13.2 Amplification factors

`amp(a)` is the sensitivity of column F1 to per-cell extraction error in `a`,
normalized so a projection-only column equals 1. It is data-dependent and
computed, never hard-coded.

| Role | `amp_role` | Derivation |
|---|---|---|
| `PROJECT` | `1` | one input cell to one output cell, the unit |
| `KEY`, `JOIN` | `C_cols` | a key error drops the row from the aligned tables, contributing zero numerator to every scored column while `\|T\|` and `\|T_hat\|` remain in the denominators |
| `AGG_ADDITIVE` | `max(1 / sqrt(m), sqrt(rho))` | independent errors over `m` summands cancel at `O(m^-0.5)`; correlated errors do not, tending to `eps * sqrt(rho)` |
| `GROUP` | `2 * m` | a misassigned row corrupts source and target groups against only `n / m` output rows |
| `AGG_EXTREMAL` | `m` | a group extremum is wrong if any of its `m` cells errs in the dominant direction |
| `AGG_DISTINCT` | `n / d` | average multiplicity; each spurious value inflates the count by one against a base of `d` |

```
amp(a) = max(amp_role(a, r) for r in roles(a)) * freq_weight(a)
```

Three of six factors scale with `m`.

### 13.3 Estimating rho

`rho` is the only quantity not read off materialized data, and the additive
discount depends on it entirely.

1. Cluster pilot documents by format into `template_cluster_id` groups using
   structural features: section headers, table presence, length distribution,
   extraction prompt path taken.
2. Per attribute, compute the variance of an extraction-disagreement indicator
   within clusters and across clusters. Disagreement between two independent
   extractor configurations is the error proxy, since true error is unavailable.
3. `rho = within_cluster_variance / total_variance`, clipped to `[0, 1]`.

The two extractor configurations must be maximally dissimilar in model family,
prompt structure, and segmentation. Extractors sharing a failure mode agree
while both being wrong, biasing `rho` downward and the additive discount upward.
Record the configurations used so the bias direction is auditable.

Default before the pilot completes: `rho = 0.5`.

### 13.4 Budget allocation

Allocate tokens proportional to `amp(a) * expected_marginal_quality(a)`.

| Attribute class | Tier | ER strategy |
|---|---|---|
| `KEY`, `JOIN` | expensive | `llm` |
| `GROUP`, `AGG_EXTREMAL` with large `m` | expensive | `llm` |
| `AGG_DISTINCT` with large `n / d` | expensive | `llm` |
| Stage 1 filter attribute also in output position | expensive at Stage 3 | per above |
| `AGG_ADDITIVE` with low measured `rho` | cheap | `embedding` at 0.7 |
| `AGG_ADDITIVE` with high measured `rho` | as `PROJECT` or above | `embedding` at 0.8 |
| `PROJECT` only | cheap | `embedding` at 0.7 |

---

## 14. Cost Model

```
Cost(T, SPP) = pilot_cost
             + sum over distinct `pre` policies of corpus_pass_cost
             + staged extraction over the union of required attributes,
               each at its allocated tier and slice
             + LLM-backed population annotations, shared across configurations
```

Token-costly dimensions: preprocessing policies, per-attribute extractor tiers,
slice width, LLM annotations.

Zero-token dimensions: physical schema choice, non-LLM population modules,
grain coarsening, materialization.

Implement `marginal_cost(config, evidence_store)` and use it everywhere in
search. Additive per-configuration accounting over-counts shared extraction,
biases the optimizer toward `|SPP| = 1`, and works directly against the
portfolio claim.

Over-extraction is paid only when: two templates need different `pre` for the
same attribute; a template needs a grain finer than what was extracted; an LLM
population strategy is required; or a second quality tier is warranted for the
same attribute. Everything else is free.

Search priority follows: schema and non-LLM population dimensions can be
explored near-exhaustively because they cost CPU, not budget.

---

## 15. Surrogate `U_hat`

Signature: `U_hat(db: MaterializedDB, schema, T, Q) -> SurrogateReport`. No
signal reads `data/gold/` (I1).

Translation-side signals from the pre-pivot design are removed. Rewritability is
now a hard predicate in Section 10, not a surrogate component.

| Signal | Definition | Predicts |
|---|---|---|
| `cardinality_plausibility` | deviation of rows-per-document and distinct-key counts from corpus priors estimated on a held-out sample of `T` | deflation of every `P_c` via `\|T_hat\|` |
| `key_provenance_coverage` | fraction of key cells with a resolvable source span | alignment failure, zeroing all columns |
| `key_null_dup_rate` | null and duplicate rate on declared primary keys | alignment failure, key collision |
| `cross_config_agreement` | Jaccard over key-value sets across configurations sharing an evidence store | alignment instability |
| `type_coercion_failure` | fraction of cells failing declared type coercion | cell comparator failure |
| `constraint_violation` | FD and denial-constraint violation rate against `declared_fds`, `declared_dcs` | schema and population mismatch |
| `slice_boundary_mass` | fraction of rows at the edge of `slice(a)`, indicating Stage 1 truncation | recall loss from staging |
| `stage1_admission_rate` | admitted fraction at Stage 1 against pilot-estimated selectivity | Stage 1 threshold miscalibration |
| `empty_result_rate` | fraction of templates returning zero or degenerate results | both sides |

Per-attribute contributions are weighted by `amp(a)`, so a constraint violation
on a key attribute outweighs one on a projection column. The global weight
vector is fit on a development workload and reported on a disjoint workload.

A configuration can raise internal consistency by discarding difficult records.
`cardinality_plausibility` and `slice_boundary_mass` penalize this. A regression
test constructs a deliberately record-dropping configuration and asserts it does
not reach the top quartile of `U_hat`.

---

## 16. Search

### 16.1 Structure

Search operates over admissible `SPP` sets. Cluster structure fixes `|SPP|`'s
lower bound and the demand map per configuration, so search chooses physical
schema, preprocessing, extractor tiers, slice widths, and non-demanded
population modules.

### 16.2 Selection rule

```
score(x) = (U_hat(x) + explore_coef * sqrt(2 * ln(t) / n_visits(x)))
           / (marginal_cost(x, E_t) + eps)
```

Select `argmax score(x)` over the frontier. This is the bandits-with-knapsacks
form specialized to a single resource, appropriate because candidate costs vary
by orders of magnitude.

### 16.3 Progressive widening

Cap children at `ceil(widen_coef * n_visits ** widen_exp)` with `widen_exp`
near 0.5.

### 16.4 Complete-configuration search

Nodes are complete `<schema, pop, pre>` triples within a cluster. Schema,
population, and preprocessing interact through joins, filters, and aggregation,
so a configuration assembled from individually optimal modules can be globally
dominated. Locally optimal composition is not used.

Move set:
- swap physical schema pattern
- promote or demote an attribute to a different relation
- change `pre` mode or chunk size
- raise or lower an attribute's extractor tier
- widen or narrow a slice
- specialize a non-demanded population module for one attribute
- add or remove a configuration within a cluster

Specialization and tier moves are ordered by `amp(a)` descending.

### 16.5 Ordering and pruning

Marginal cost falls as evidence accumulates, so evaluate cheap, evidence-rich
candidates early; tiebreak on `evidence_yield / cost` within tolerance.

Prune before extraction on: admissibility (Section 10), attribute coverage
against requirements, declared-constraint sanity, and pilot statistics. A
majority of candidates will not reach the frontier, so structural pruning is a
feasibility requirement rather than an optimization.

---

## 17. Coverage Sets

Each materialized database records, per attribute, the constant sets and
predicate ranges over which population is complete, plus grain, forms present,
and corpus fingerprint.

This is a soundness artifact. It is what permits the claim that a served answer
is faithful to the user's SQL rather than faithful to a slice. A template whose
constants fall outside the recorded set is infeasible on that database and
routes elsewhere; if the set contains them, the answer is exact with respect to
the extracted evidence.

---

## 18. Router

Static lookup per Section 11.3. Zero tokens, deterministic, recorded in the run
manifest. No LLM router. No score-based selection.

An oracle best-of-routing score is computed in `quwarts/eval/` only and the gap
reported as a diagnostic upper bound on routing loss.

---

## 19. Evaluation Harness (firewalled)

1. **Row alignment.** Composite key `k(r)` from string-normalized key attribute
   values. Phase one: per key, match `min(|T_k|, |T_hat_k|)` pairs in table
   order. Phase two: optionally match remaining rows with an LLM entity matcher.
   Unmatched rows are excluded from the aligned tables.
2. **Cell scoring.** Type-specific comparators returning `(p, r)` in `[0,1]`:
   exact match for strings, overlap for multivalued, soft error for numeric.
3. **Column scores.** `P_c = (1/|T_hat|) * sum_j p_j`,
   `R_c = (1/|T|) * sum_j r_j`.
4. **Error.** `1 - F1`.

Reported metrics:
- realized `sum_q Error` for the selected `SPP`
- Spearman and Kendall correlation between `U_hat` and `1 - Error` across
  materialized configurations
- realized regret against the configuration set an oracle would have chosen
- measured versus predicted amplification: perturb extraction quality per
  attribute, measure realized change in column F1, compare against `amp(a)`
- staged versus full extraction result equality per template shape
- conflict type mix: destructive versus non-destructive, and cluster count
- routing gap against best-of routing
- tokens spent, cache hit rate, fraction of candidates materialized, share of
  budget spent per stage

Correlation, regret, and amplification validity are the headline results.

---

## 20. Milestones

**M0. Skeleton and invariants.** Layout, contracts, `TokenLedger`, import linter
for I1, deterministic replay for I3.

**M1. SQL frontend.** Parser, canonicalization, templating, role extraction,
slice derivation, grain and form derivation. Golden tests over a hand-built
statement set.

**M2. Slice safety and rewritability.** Shape classification, `R(q, s)`,
admissibility check. Property-based tests for every shape. Fail-closed default
asserted.

**M3. Conflict analysis and routing.** Presupposition extraction, destructive
classification, clustering, static router. Monotonicity test over random `SPP`
subsets.

**M4. Evidence store and staged extraction.** Least-commitment records,
content-addressed cache, three-stage extractor, document format clustering.
Assert I4 by asserting zero duplicate extractions across configurations sharing
attributes. Assert I7 by asserting zero tokens spent during population with
non-LLM strategies.

**M5. Pilot and amplification.** Statistics estimation, `rho`, `amp(a)`.
Estimators unit-tested on synthetic data with known statistics.

**M6. Schema generation, population, materialization.** Three patterns,
per-attribute policies, deterministic views, SQLite writer, hashing, coverage
sets. Gate: staged-versus-full equality tests from M2 pass on a small corpus.

**M7. Surrogate.** All nine signals, amplification-weighted aggregation, gaming
regression test.

**M8. Evaluation harness.** Full protocol, gold loaders, firewall enforcement.
First measurement of `U_hat` correlation and amplification validity. Gate:
proceed only when rank correlation on the development workload exceeds the
pre-registered threshold.

**M9. Search.** Benefit-per-token selection, progressive widening, set-level
cost, pruning, portfolio construction, validation-fallback hook.

**M10. Experiments.**

---

## 21. Experiments

1. **Surrogate fidelity.** Rank correlation and realized regret on a workload
   family disjoint from the weight-fitting workload.
2. **Amplification validity.** Predicted `amp(a)` against measured F1
   sensitivity, with a fitted slope.
3. **Sensitivity to rho.** Sweep `rho` in `{0, 0.25, 0.5, 0.75, 1}`, reporting
   allocation shift and final error.
4. **Staged versus full extraction.** Token savings and result equality by
   template shape.
5. **Stage 1 recall threshold.** Sweep the admission threshold, reporting token
   cost against irrecoverable recall loss.
6. **Amplification-weighted versus uniform allocation** at equal `theta`.
7. **Per-attribute versus uniform population policy** at equal `theta`.
8. **Portfolio versus single configuration** at equal `theta`, decomposing the
   gain into destructive conflicts, schema effects, and allocation.
9. **Conflict density.** Measured mix of destructive and non-destructive
   conflicts across benchmark workloads, with resulting cluster counts. This
   either validates the portfolio motivation or redirects the contribution
   toward allocation.
10. **Least-commitment ablation.** Committing early in the evidence layer versus
    deferring, measuring token cost when a later template demands a finer form.
11. **Set-level versus additive cost accounting.**
12. **Search ablation.** Benefit-per-token against uniform-cost UCT; progressive
    widening on and off.
13. **Pilot cost ablation.** Pilot sample size against statistics quality and
    tokens diverted from extraction.
14. **Budgeted validation fallback.** Spend a slice of `theta` labeling a subset
    of `Q`, use `U_hat` to select which configurations to label, compare against
    pure-surrogate selection at equal total budget.

---

## 22. Fallback Path

If surrogate fidelity is weak on a workload family, retain the surrogate rather
than discarding it. Admit a labeled subset `Q_val` with acquisition cost charged
against `theta`, and use `U_hat` to decide which configurations merit a label.
The system becomes an active selection procedure under the same budget, with the
surrogate acting as a cost-reduction mechanism. The hook is built in M9
regardless.

---

## 23. Known Risks

1. **Slice-safety misclassification is the top soundness risk.** Anti-joins and
   unfiltered aggregates are easy to misclassify, and a misclassification
   produces silently wrong answers the surrogate cannot detect. Mitigated by
   fail-closed defaults and property-based equality tests against full
   materialization; these gate M6.
2. **Stage 1 recall couples to every downstream column.** A dropped entity zeroes
   numerator mass across all scored columns, so the recall-biased threshold has
   outsized influence and requires its own ablation.
3. **Surrogate fidelity is load-bearing.** If `U_hat` does not rank
   configurations consistently with `Error`, search is unfounded. M8 is gated on
   this.
4. **The additive aggregate discount depends entirely on `rho`.** Extraction
   errors are often correlated because the same prompt fails identically on the
   same document format. High `rho` removes the discount and shifts allocation.
5. **`rho` is estimated from disagreement, not true error.** Extractors sharing a
   failure mode agree while both wrong, biasing `rho` downward and the discount
   upward. Mitigated by maximally dissimilar extractor configurations; bias
   direction is reported.
6. **Conflict density may be low in real workloads.** If destructive conflicts are
   rare, the portfolio contribution is thin and the result rests on allocation
   instead. Experiment 9 settles this early.
7. **Per-attribute policies and portfolios partially compete.** Attribute-indexed
   policies absorb non-destructive conflicts into one database, reducing the need
   for portfolios. Report the decomposition rather than attributing the full gain
   to either mechanism.
8. **Logical schema inference quality bounds everything.** If `L` misses an entity
   type or attribute the user needs, statements fail to bind and no physical
   search recovers it. Binding failure rate on benchmark workloads is a reported
   metric.
