"""
Entity Anchor — identity-column detection for WDIRS.

Two strategies depending on whether the workload provides an identity hint:

  1. detect_identity_column(table_name, schema_columns, llm_client)
     Asks the LLM to pick the best identity column from the known schema.
     Used when at least one workload query filters/selects on an entity name.

  2. discover_entity_attribute(table_name, sample_chunks, llm_client)
     Evaporate-inspired fallback: samples raw text chunks, asks the LLM to
     enumerate attribute:value pairs, counts field frequencies, then picks the
     most entity-like attribute.  Used when the workload has no column that
     could serve as an identity (e.g. pure aggregation queries).
"""

import logging
from collections import Counter
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Strategy 1 — identity column from workload schema
# ---------------------------------------------------------------------------

def detect_identity_column(
    table_name: str,
    schema_columns: List[str],
    llm_client,
) -> Optional[str]:
    """
    Identify the primary identity column for *table_name* using a single LLM
    call that shows all candidates at once.

    Design rationale
    ────────────────
    Binary YES/NO per candidate fails for small (7B) models because:
      - Each question is answered in isolation with no comparative context.
      - The model cannot see that 'company_name' is obviously better than
        'auditor' when they are evaluated separately.
      - The model defaults to NO when uncertain, so zero candidates pass.

    Showing all candidates simultaneously and asking "which is each row
    *about*?" gives the model the comparative context it needs.  The prompt:
      - Uses plain natural language, not database jargon ("PRIMARY IDENTITY").
      - Frames the question as "what is this row about?" — intuitively clear.
      - Gives NO escape hatch to say null/none: the caller guarantees at
        least one of the candidates is the identity column (Tier-1 pre-filter
        already confirmed they are PERSON/ORG/GPE type columns).
      - Retries with a rephrased prompt if the response is not in the list.

    Returns the exact column name (case-preserving) or None if both attempts
    fail (falls through to Tier-3 NER discovery in the caller).
    """
    if not schema_columns:
        return None

    col_lower = {c.lower(): c for c in schema_columns}
    bullet_list = "\n".join(f"  - {c}" for c in schema_columns)

    def _call(prompt: str) -> Optional[str]:
        resp = llm_client.generate(prompt, max_tokens=30, temperature=0.0)
        resp = resp.strip().strip('"').strip("'").rstrip(".")
        # Accept if the response matches a candidate (case-insensitive)
        if resp.lower() in col_lower:
            return col_lower[resp.lower()]
        # Also accept if the response is contained in a candidate name
        # (model sometimes adds/drops underscores)
        for c_lower, c_orig in col_lower.items():
            if resp.lower().replace(" ", "_") == c_lower:
                return c_orig
        return None

    # ── Attempt 1 ─────────────────────────────────────────────────────────────
    # Pure structural description — no domain hints, no examples, no mention
    # of what kinds of entities the table might contain.  The distinction
    # between "the column that names each row's subject" and "columns that
    # describe attributes of that subject" is a universal structural property
    # that holds regardless of domain.
    prompt1 = (
        f"A relational table called '{table_name}' contains these candidate "
        f"columns:\n{bullet_list}\n\n"
        f"In any well-structured table, exactly one column serves as the "
        f"subject identifier: its value tells you WHICH entity the row is "
        f"about, while every other column describes a property of that entity.\n\n"
        f"Which column from the list above is the subject identifier?\n"
        f"Respond with ONLY the exact column name. You must pick one."
    )

    logger.info(
        f"[EntityAnchor] Single-call identity selection for '{table_name}' "
        f"over {len(schema_columns)} candidates"
    )
    result = _call(prompt1)
    if result:
        logger.info(f"[EntityAnchor] Identity column for '{table_name}': '{result}'")
        return result

    # ── Attempt 2 ─────────────────────────────────────────────────────────────
    # Rephrased without any vocabulary that echoes schema column names.
    prompt2 = (
        f"Table: '{table_name}'\n"
        f"Columns: {schema_columns}\n\n"
        f"One column is the anchor of every row — removing it would make "
        f"the row unidentifiable. All other columns are attributes that only "
        f"make sense once you know which row you are looking at.\n\n"
        f"Which column is the anchor?\n"
        f"Respond with ONLY the exact column name. You must pick one."
    )

    result = _call(prompt2)
    if result:
        logger.info(
            f"[EntityAnchor] Identity column for '{table_name}' "
            f"(attempt 2): '{result}'"
        )
        return result

    logger.warning(
        f"[EntityAnchor] Both prompts failed to return a valid column for "
        f"'{table_name}' — returning None (Tier 3 will handle)"
    )
    return None


# ---------------------------------------------------------------------------
# Strategy 2 — Evaporate-inspired discovery from raw text
# ---------------------------------------------------------------------------

def discover_entity_attribute(
    table_name: str,
    sample_chunks: List[str],
    llm_client,
    n_sample: int = 50,
) -> Optional[str]:
    """
    When the workload schema has no obvious identity column, sample raw text
    chunks and discover the primary entity attribute using an Evaporate-style
    two-phase approach:

      Phase A — extraction: for each chunk, ask the LLM to list all
        attribute:value pairs it can find.  Count field frequency across chunks.

      Phase B — selection: present the top-20 most frequent fields to the LLM
        and ask which one is the primary entity identifier.

    Returns a normalized attribute name string, or None if discovery fails.
    """
    chunks = sample_chunks[:n_sample]
    if not chunks:
        return None

    field_counts: Counter = Counter()

    # Phase A — enumerate fields from each chunk
    for chunk in chunks:
        prompt = (
            f"Read the following text and list every distinct attribute you can "
            f"find, as \"attribute: value\" pairs.\n"
            f"Focus on identifying the main subject and its properties.\n\n"
            f"Text:\n{chunk}\n\n"
            f"List attributes (one per line, format: attribute: value):"
        )
        try:
            response = llm_client.generate(prompt, max_tokens=400, temperature=0.0)
            for line in response.strip().split("\n"):
                line = line.strip().lstrip("-").lstrip("*").strip()
                if ": " not in line:
                    continue
                field = line.split(":")[0].strip().lower()
                # Skip obviously non-entity fields
                if field and len(field) <= 60:
                    field_counts[field] += 1
        except Exception as e:
            logger.warning(f"[EntityAnchor] Chunk sampling failed: {e}")
            continue

    if not field_counts:
        logger.warning(
            f"[EntityAnchor] Phase A found no fields for '{table_name}'."
        )
        return None

    top_fields = [f for f, _ in field_counts.most_common(20)]
    logger.info(
        f"[EntityAnchor] Top fields discovered for '{table_name}': {top_fields[:10]}"
    )

    # Phase B — ask LLM to pick the entity identifier from the candidate list
    prompt = (
        f"These attributes were found in text files about \"{table_name}\":\n"
        f"{top_fields}\n\n"
        f"Which SINGLE attribute is the PRIMARY IDENTIFIER that uniquely names "
        f"the main entity/subject of each record?\n"
        f"Examples of what a primary identifier looks like: "
        f"\"name\", \"player name\", \"company\", \"patient id\", \"title\".\n\n"
        f"Rules:\n"
        f"- Respond with ONLY one attribute from the list above.\n"
        f"- No explanation, no punctuation.\n"
        f"- If none qualify, respond with NULL."
    )

    try:
        response = llm_client.generate(prompt, max_tokens=20, temperature=0.0)
        chosen = response.strip().strip('"').strip("'").lower()

        if chosen == "null":
            logger.warning(
                f"[EntityAnchor] LLM could not pick entity attribute for '{table_name}'."
            )
            return None

        if chosen in field_counts:
            logger.info(
                f"[EntityAnchor] Discovered entity attribute for '{table_name}': '{chosen}'"
            )
            return chosen

        # LLM picked something not in the list — fall back to most common
        fallback = field_counts.most_common(1)[0][0]
        logger.warning(
            f"[EntityAnchor] LLM returned '{chosen}' not in candidate list. "
            f"Falling back to most common field: '{fallback}'"
        )
        return fallback

    except Exception as e:
        raise RuntimeError(
            f"[EntityAnchor] Phase B LLM call failed for '{table_name}': {e}"
        ) from e
