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

def _ask_is_identity(col: str, table_name: str, all_candidates: List[str],
                     llm_client) -> bool:
    """
    Ask the LLM a single binary question: is *col* the primary identity column
    of *table_name*?  Binary YES/NO questions are far more reliable for small
    models than open-ended selection from a list.
    """
    others = [c for c in all_candidates if c != col]
    prompt = (
        f"Database table: '{table_name}'\n"
        f"Column under review: '{col}'\n"
        f"Other columns in the table: {others}\n\n"
        f"The PRIMARY IDENTITY column is the single column that:\n"
        f"  - Stores the unique name or identifier of the main real-world entity "
        f"    (e.g. the company, person, patient, product, city).\n"
        f"  - Has one value per row — NOT a list of multiple people or items.\n"
        f"  - Each row in the table represents exactly ONE of these entities.\n\n"
        f"Is '{col}' the PRIMARY IDENTITY column of this table?\n"
        f"Answer with ONLY 'YES' or 'NO'."
    )
    response = llm_client.generate(prompt, max_tokens=5, temperature=0.0)
    answer = response.strip().upper()
    return answer.startswith("Y")


def detect_identity_column(
    table_name: str,
    schema_columns: List[str],
    llm_client,
) -> Optional[str]:
    """
    Identify the primary identity column for *table_name*.

    Uses pairwise binary YES/NO questioning instead of asking the model to
    pick from a list.  Binary questions are far more reliable for small (7B)
    models because each question has only two valid answers and a clear
    definition.

    Strategy:
      1. Ask the LLM YES/NO for each candidate: "Is X the primary identity column?"
      2. Collect all YES answers.
         - Exactly one YES  → return it directly.
         - Multiple YES     → ask pairwise comparisons to break the tie.
         - Zero YES         → return None (falls through to Tier-3 NER discovery).

    Returns the exact column name (case-preserving) or None.
    """
    if not schema_columns:
        return None

    logger.info(
        f"[EntityAnchor] Running binary YES/NO identity check for "
        f"'{table_name}' over {len(schema_columns)} candidates"
    )

    yes_cols: List[str] = []
    for col in schema_columns:
        try:
            if _ask_is_identity(col, table_name, schema_columns, llm_client):
                yes_cols.append(col)
                logger.info(f"[EntityAnchor] '{col}' → YES")
            else:
                logger.info(f"[EntityAnchor] '{col}' → NO")
        except Exception as exc:
            logger.warning(f"[EntityAnchor] Binary check failed for '{col}': {exc}")

    if len(yes_cols) == 1:
        logger.info(
            f"[EntityAnchor] Identity column for '{table_name}': '{yes_cols[0]}'"
        )
        return yes_cols[0]

    if len(yes_cols) == 0:
        logger.warning(
            f"[EntityAnchor] No candidate confirmed as identity column for "
            f"'{table_name}' — returning None"
        )
        return None

    # Multiple YES answers — break tie with direct comparison pairs
    logger.info(
        f"[EntityAnchor] Multiple YES answers for '{table_name}': {yes_cols} — "
        f"running pairwise tiebreak"
    )
    winner = yes_cols[0]
    for challenger in yes_cols[1:]:
        prompt = (
            f"Table: '{table_name}'\n"
            f"Two columns are both candidates for PRIMARY IDENTITY column.\n"
            f"The PRIMARY IDENTITY column uniquely names the main entity of each "
            f"row (e.g. company name, player name, patient id).\n\n"
            f"Column A: '{winner}'\n"
            f"Column B: '{challenger}'\n\n"
            f"Which is more likely to be the PRIMARY IDENTITY column?\n"
            f"Answer with ONLY 'A' or 'B'."
        )
        resp = llm_client.generate(prompt, max_tokens=5, temperature=0.0).strip().upper()
        if resp.startswith("B"):
            winner = challenger
        logger.info(
            f"[EntityAnchor] Tiebreak '{winner}' vs '{challenger}' → '{winner}'"
        )

    logger.info(
        f"[EntityAnchor] Identity column for '{table_name}' after tiebreak: '{winner}'"
    )
    return winner


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
