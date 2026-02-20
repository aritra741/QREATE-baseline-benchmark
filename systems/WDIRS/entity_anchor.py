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
    Ask the LLM which column in schema_columns is the primary identity key.

    Returns the exact column name (case-preserving) or None if the LLM
    cannot find a clear candidate.

    Raises RuntimeError if the LLM returns a value that is not in the list,
    which indicates a prompt-compliance failure that must not be silently
    swallowed.
    """
    if not schema_columns:
        return None

    prompt = (
        f"You are a database schema expert.\n"
        f"Table name: '{table_name}'\n"
        f"Columns: {schema_columns}\n\n"
        f"Which SINGLE column is the PRIMARY IDENTITY column — the one that "
        f"uniquely identifies a real-world entity in this table "
        f"(e.g. person name, company name, player name, team name)?\n\n"
        f"Rules:\n"
        f"- Respond with ONLY the exact column name from the list above.\n"
        f"- Do NOT include any explanation, punctuation, or extra words.\n"
        f"- If no single column clearly identifies the entity, respond with NULL."
    )

    response = llm_client.generate(prompt, max_tokens=20, temperature=0.0)
    response = response.strip().strip('"').strip("'")

    if response.upper() == "NULL":
        logger.info(
            f"[EntityAnchor] LLM says no identity column in '{table_name}' schema."
        )
        return None

    col_lower = {c.lower(): c for c in schema_columns}
    if response.lower() in col_lower:
        chosen = col_lower[response.lower()]
        logger.info(
            f"[EntityAnchor] Identity column for '{table_name}': '{chosen}'"
        )
        return chosen

    raise RuntimeError(
        f"[EntityAnchor] LLM returned '{response}' which is not in the column "
        f"list {schema_columns} for table '{table_name}'. "
        f"This is a prompt-compliance failure."
    )


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
