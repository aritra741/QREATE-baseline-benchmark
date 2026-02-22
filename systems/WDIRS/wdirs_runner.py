"""
WDIRS Runner - Main orchestration module.
Integrates all components and provides the main interface.
"""

import json
import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict
import sys

from data_layer import DataLayer, TextChunk
from lattice_planner import LatticePlanner, load_workload_from_directory
from sieve_synthesizer import SieveSynthesizer
from extractor import ConstrainedExtractor, OllamaClient
from entity_resolver import EntityResolver, extract_mentions_from_records, apply_canonical_map
from delta_engine import DeltaEngine, DeltaType
from entity_anchor import detect_identity_column

from config import (
    SOURCE_DATA_DIR,
    QUERY_DIR,
    get_dataset_path,
    get_schema_path,
    get_workload_path,
    CACHE_DIR,
    LOG_LEVEL,
    LOG_FORMAT,
    LOG_FILE
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class PreprocessingResult:
    """Result of preprocessing phase."""
    success: bool
    tables_processed: List[str]
    total_chunks: int
    total_records: int
    preprocessing_time: float
    error: Optional[str] = None

@dataclass
class QueryResult:
    """Result of query execution."""
    success: bool
    results: List[Dict[str, Any]]
    delta_type: str
    rows_extracted: int
    rows_enriched: int
    execution_time: float
    error: Optional[str] = None


# ============================================================================
# Helper Functions
# ============================================================================

def semantic_to_sql_type(semantic_type: str) -> str:
    """Convert semantic type to SQL type."""
    type_map = {
        "PERSON": "TEXT",
        "ORG": "TEXT",
        "DATE": "TEXT",
        "GPE": "TEXT",
        "CODE": "TEXT",
        "MONEY": "REAL",
        "QUANTITY": "REAL",
        "PRODUCT": "TEXT",
        "EVENT": "TEXT",
        "OTHER": "TEXT"
    }
    return type_map.get(semantic_type, "TEXT")


# ============================================================================
# WDIRS Runner
# ============================================================================

class WDIRSRunner:
    """
    Main orchestrator for WDIRS system.
    Coordinates all phases of the pipeline.
    """
    
    def __init__(
        self,
        dataset: str,
        postgres_uri: Optional[str] = None
    ):
        """
        Initialize WDIRS runner.
        
        Args:
            dataset: Name of the dataset
            postgres_uri: Optional PostgreSQL connection URI
        """
        self.dataset = dataset
        
        logger.info(f"Initializing WDIRS for dataset: {dataset}")
        
        # Initialize components
        self.data_layer = DataLayer(postgres_uri) if postgres_uri else DataLayer()
        self.llm_client = OllamaClient()
        self.lattice_planner = LatticePlanner(self.llm_client)
        self.sieve_synthesizer = SieveSynthesizer(self.llm_client)
        self.extractor = ConstrainedExtractor(self.llm_client)
        self.entity_resolver = EntityResolver(self.llm_client)
        self.delta_engine = DeltaEngine(
            self.data_layer,
            self.lattice_planner,
            self.extractor,
            self.entity_resolver
        )
        
        # Identity columns detected/discovered per table.
        # Populated by _build_identity_map before extraction.
        # None value means the table has no reliable identity column (rare).
        self.identity_columns: Dict[str, Optional[str]] = {}

        # spaCy NER label for each table's identity column.
        # Used by entity-first extraction to group chunks by entity without LLM.
        self.identity_ner_labels: Dict[str, Optional[str]] = {}

        # Load spaCy model once; reused for all NER passes.
        import spacy as _spacy
        try:
            self._nlp = _spacy.load("en_core_web_sm")
            logger.info("spaCy en_core_web_sm loaded for entity-first extraction")
        except OSError:
            raise RuntimeError(
                "spaCy model 'en_core_web_sm' not found. "
                "Run: python -m spacy download en_core_web_sm"
            )
        
        # Cache
        self.cache_dir = CACHE_DIR / dataset
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("WDIRS initialization complete")
    
    # ========================================================================
    # Phase 1: Offline Relational Synthesis (Preprocessing)
    # ========================================================================
    
    def preprocess(
        self,
        workload_queries: Optional[List[str]] = None
    ) -> PreprocessingResult:
        """
        Run complete preprocessing pipeline.
        
        Args:
            workload_queries: Optional list of SQL queries. If not provided, loads from Query directory.
            
        Returns:
            PreprocessingResult
        """
        logger.info("=" * 80)
        logger.info("PHASE 1: OFFLINE RELATIONAL SYNTHESIS")
        logger.info("=" * 80)
        
        start_time = time.time()
        
        try:
            # Step 1: Load and parse workload
            logger.info("\n[Step 1/6] Loading workload...")
            if workload_queries is None:
                workload_path = str(QUERY_DIR / self.dataset)
                from lattice_planner import load_workload_from_directory
                workload_queries = load_workload_from_directory(workload_path)
            
            lattice = self.lattice_planner.parse_workload(workload_queries)
            
            total_columns = sum(len(t.columns) for t in lattice.tables.values())
            logger.info(f"Workload parsed: {len(lattice.tables)} tables, {total_columns} columns")
            
            # Check if we have columns
            if total_columns == 0:
                logger.warning("No columns extracted from workload! This will result in no data extraction.")
                logger.warning("Sample queries:")
                for i, q in enumerate(workload_queries[:3]):
                    logger.warning(f"  Query {i+1}: {q[:100]}...")
            
            # Log table details
            for table_name, table_info in lattice.tables.items():
                logger.info(f"  Table '{table_name}': {len(table_info.columns)} columns - {list(table_info.columns.keys())}")
            
            # Step 2: Ingest text data
            logger.info("\n[Step 2/6] Ingesting text data...")
            total_chunks = self._ingest_text_data()
            logger.info(f"Ingested {total_chunks} chunks")
            
            # Step 3: Synthesize sieves
            logger.info("\n[Step 3/7] Synthesizing programmatic sieves...")
            self._synthesize_sieves(lattice)

            # Step 3.5: Detect identity columns — must happen after sieves so
            # we have candidate chunks available for Evaporate-style fallback.
            logger.info("\n[Step 4/7] Detecting entity identity columns...")
            self._build_identity_map(lattice)

            # Step 4: Global extraction
            logger.info("\n[Step 5/7] Performing constrained global extraction...")
            total_records = self._global_extraction(lattice)
            logger.info(f"Extracted {total_records} records")

            # Step 5.5: Record consolidation — merge any remaining duplicates
            logger.info("\n[Step 6/7] Consolidating extracted records (deduplication + merging)...")
            self._consolidate_records(lattice)

            # Step 6: Entity resolution on join keys
            logger.info("\n[Step 7/7] Performing proactive entity resolution...")
            self._proactive_entity_resolution(lattice)

            # Step 7: Save preprocessing results
            logger.info("\n[Step 8/8] Saving preprocessing results...")
            self._save_preprocessing_results(lattice)
            
            preprocessing_time = time.time() - start_time
            
            result = PreprocessingResult(
                success=True,
                tables_processed=list(lattice.tables.keys()),
                total_chunks=total_chunks,
                total_records=total_records,
                preprocessing_time=preprocessing_time
            )
            
            logger.info("=" * 80)
            logger.info("PREPROCESSING COMPLETE")
            logger.info(f"Time: {preprocessing_time:.2f}s")
            logger.info(f"Tables: {len(lattice.tables)}")
            logger.info(f"Chunks: {total_chunks}")
            logger.info(f"Records: {total_records}")
            logger.info("=" * 80)
            
            return result
        
        except Exception as e:
            logger.error(f"Preprocessing failed: {e}", exc_info=True)
            preprocessing_time = time.time() - start_time
            
            return PreprocessingResult(
                success=False,
                tables_processed=[],
                total_chunks=0,
                total_records=0,
                preprocessing_time=preprocessing_time,
                error=str(e)
            )
    
    def _ingest_text_data(self) -> int:
        """Ingest text data and create chunks."""
        dataset_path = get_dataset_path(self.dataset)
        
        if not dataset_path.exists():
            logger.warning(f"Dataset path not found: {dataset_path}")
            return 0
        
        total_chunks = 0
        
        # Process all text files
        for text_file in dataset_path.glob("**/*.txt"):
            try:
                with open(text_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Create chunks
                doc_id = str(text_file.relative_to(dataset_path))
                chunks = self.data_layer.create_chunks(
                    content,
                    doc_id,
                    metadata={"source_file": str(text_file)}
                )
                
                # Insert into database
                self.data_layer.insert_chunks(chunks)
                total_chunks += len(chunks)
                
                logger.debug(f"Ingested {len(chunks)} chunks from {doc_id}")
            
            except Exception as e:
                logger.error(f"Error ingesting {text_file}: {e}")
        
        return total_chunks
    
    def _synthesize_sieves(self, lattice) -> None:
        """Synthesize sieves for all tables."""
        for table_name, table_info in lattice.tables.items():
            try:
                # Get sample chunks
                sample_chunks_objs = self.data_layer.get_all_chunks(
                    limit=10
                )
                sample_chunks = [c.content for c in sample_chunks_objs]
                
                # Get schema
                schema = self.lattice_planner.get_table_schema(table_name)
                
                # Synthesize sieve
                sieve_result = self.sieve_synthesizer.synthesize_sieve(
                    table_name,
                    schema,
                    sample_chunks
                )
                
                logger.info(f"Synthesized sieve for {table_name} "
                           f"(accuracy: {sieve_result.accuracy:.2%})")
                
                # Apply sieve to all chunks
                all_chunks = self.data_layer.get_all_chunks()
                chunk_texts = [c.content for c in all_chunks]
                
                relevant_indices = self.sieve_synthesizer.apply_sieve(
                    table_name,
                    chunk_texts
                )
                
                # Store candidate indices
                relevant_chunk_ids = [all_chunks[i].chunk_id for i in relevant_indices]
                self.data_layer.insert_candidates(table_name, relevant_chunk_ids)
                
                logger.info(f"Indexed {len(relevant_chunk_ids)} candidate chunks for {table_name}")
            
            except Exception as e:
                logger.error(f"Error synthesizing sieve for {table_name}: {e}")
                raise RuntimeError(f"Sieve synthesis failed for table '{table_name}': {e}") from e
    
    def _build_identity_map(self, lattice) -> None:
        """
        Detect the primary identity column for every table in the lattice.

        Three-tier strategy, each tier falling through to the next only if it
        produces no result:

        Tier 1 — Semantic-type pre-filter (zero LLM cost):
          The lattice planner already ran _identify_semantic_types and tagged
          every column as PERSON, ORG, GPE, DATE, etc.  The identity column is
          almost always the one with a PERSON, ORG, or GPE tag.  Collect those
          candidates and, if exactly one exists, use it directly.  If several
          exist, pass only those to the LLM (Tier 2) — much easier than 25+.

        Tier 2 — LLM on pre-filtered candidates:
          Ask the LLM to pick from the short candidate list (typically 1-3
          columns).  This is reliable even for 7B models because the list is
          small and all candidates are plausible identity types.

        Tier 3 — Evaporate-style text discovery (last resort):
          Used only when the workload has NO PERSON/ORG/GPE column at all
          (e.g. pure aggregation queries with no entity reference).  Samples
          raw text chunks and discovers the entity attribute by field frequency.

        Results are stored in self.identity_columns[table_name].
        """
        ENTITY_SEMANTIC_TYPES = {"PERSON", "ORG", "GPE"}

        for table_name, table_info in lattice.tables.items():
            schema = self.lattice_planner.get_table_schema(table_name)
            schema_columns = list(schema.keys())

            logger.info(
                f"[IdentityMap] Detecting identity column for '{table_name}' "
                f"({len(schema_columns)} columns): {schema_columns}"
            )

            # --- Tier 1: semantic-type pre-filter ---
            entity_candidates = [
                col for col, col_info in table_info.columns.items()
                if getattr(col_info, "semantic_type", "OTHER") in ENTITY_SEMANTIC_TYPES
                and col in schema_columns
            ]

            logger.info(
                f"[IdentityMap] Tier-1 entity candidates for '{table_name}': "
                f"{entity_candidates}"
            )

            identity_col: Optional[str] = None

            if len(entity_candidates) == 1:
                # Unambiguous — no LLM call needed.
                identity_col = entity_candidates[0]
                logger.info(
                    f"[IdentityMap] Single entity candidate → '{identity_col}' "
                    f"(no LLM call needed)"
                )
            elif len(entity_candidates) > 1:
                # --- Tier 2a: binary YES/NO LLM check on pre-filtered list ---
                identity_col = detect_identity_column(
                    table_name,
                    entity_candidates,
                    self.extractor.llm_client,
                )
                # If None, fall through to Tier 3 (NER-based discovery).
            else:
                # No PERSON/ORG/GPE columns — try full schema with LLM
                # --- Tier 2b: LLM on full schema ---
                identity_col = detect_identity_column(
                    table_name,
                    schema_columns,
                    self.extractor.llm_client,
                )

            if identity_col is None:
                # --- Tier 3: NER-based entity type detection ---
                # Reached only when the workload has no PERSON/ORG/GPE column
                # (e.g. pure aggregation queries).  We do NOT try to discover
                # a column name from raw text — that always picks up document
                # structure words ('attribute', 'value', 'subject') instead of
                # real entity identifiers.  Instead, we let spaCy NER tell us
                # which named-entity type dominates the candidate chunks, then
                # inject a virtual '_entity' routing column.  During extraction
                # the LLM is instructed to populate '_entity' with whatever name
                # it finds for that entity type, and upsert_by_entity uses that
                # as the key.
                logger.info(
                    f"[IdentityMap] No entity column in schema for '{table_name}'. "
                    f"Running NER-based entity type detection (Tier 3)..."
                )
                candidate_chunk_ids = self.data_layer.get_candidates(table_name)
                if not candidate_chunk_ids:
                    logger.warning(
                        f"[IdentityMap] No candidate chunks for '{table_name}'. "
                        f"Skipping entity detection."
                    )
                    self.identity_columns[table_name] = None
                    continue

                sample_chunks = self.data_layer.get_chunks_by_ids(
                    candidate_chunk_ids[:50]
                )
                sample_texts = [c.content for c in sample_chunks]

                # Count named-entity types across the sample
                from collections import Counter as _Counter
                ner_type_counts: _Counter = _Counter()
                for doc in self._nlp.pipe(
                    sample_texts, batch_size=32,
                    disable=["parser", "lemmatizer"]
                ):
                    for ent in doc.ents:
                        if ent.label_ in {"PERSON", "ORG", "GPE"}:
                            ner_type_counts[ent.label_] += 1

                if ner_type_counts:
                    dominant_type = ner_type_counts.most_common(1)[0][0]
                    # Virtual identity column: tells the extractor what to put
                    # in _entity, and tells _group_chunks_by_entity which NER
                    # label to look for.
                    virtual_col = "_entity_discovered"
                    table_info.columns[virtual_col] = type("ColInfo", (), {
                        "semantic_type": dominant_type,
                        "predicate_literals": set(),
                    })()
                    identity_col = virtual_col
                    logger.info(
                        f"[IdentityMap] Tier-3 NER: dominant entity type for "
                        f"'{table_name}' is {dominant_type} "
                        f"(counts: {dict(ner_type_counts.most_common(3))}). "
                        f"Using virtual column '{virtual_col}'."
                    )
                else:
                    logger.warning(
                        f"[IdentityMap] Tier-3 NER found no named entities in "
                        f"sample chunks for '{table_name}'. "
                        f"Upsert will fall back to plain insert."
                    )

            # Derive the spaCy NER label from the LLM-assigned semantic type of
            # the identity column.  The semantic type was determined by
            # _identify_semantic_types during parse_workload.
            # We then cross-check against workload normalization hint values to
            # catch the common case where the LLM mistakenly labels an ORG
            # column (e.g. company_name) as PERSON.  Value-based detection is
            # dataset-agnostic and requires no extra LLM call.
            ner_label: Optional[str] = None
            if identity_col and identity_col in table_info.columns:
                sem_type = getattr(
                    table_info.columns[identity_col], "semantic_type", None
                )
                ner_label = self._semantic_type_to_ner_label(sem_type)

                # ── Validate / correct PERSON → ORG mislabel ─────────────
                # If the LLM assigned PERSON but the workload hint values for
                # this column contain org-suffix tokens ("Inc.", "Ltd.", etc.)
                # the column is almost certainly an ORG column.
                if ner_label == "PERSON":
                    _ORG_SUFFIXES = {
                        " inc", " ltd", " llc", " corp", " co.", " limited",
                        " company", " plc", " gmbh", " s.a.", " ag", " lp",
                        " llp", " group", " holdings", " bank", " fund",
                        " trust", " association", " authority", " council",
                    }
                    _norm_hints = self.lattice_planner.get_normalization_hints(table_name)
                    _hint_vals  = " ".join(_norm_hints.get(identity_col, [])).lower()
                    if any(suf in _hint_vals for suf in _ORG_SUFFIXES):
                        logger.info(
                            f"[IdentityMap] Correcting NER label PERSON→ORG for "
                            f"'{identity_col}': hint values contain org indicators"
                        )
                        ner_label = "ORG"

            self.identity_columns[table_name] = identity_col
            self.identity_ner_labels[table_name] = ner_label
            logger.info(
                f"[IdentityMap] '{table_name}' → identity_col='{identity_col}', "
                f"ner_label='{ner_label}'"
            )

    @staticmethod
    def _semantic_type_to_ner_label(semantic_type: Optional[str]) -> Optional[str]:
        """
        Map a lattice-planner semantic type to its spaCy NER label.

        Semantic types are assigned by the LLM during parse_workload and are
        fully dataset-agnostic (PERSON, ORG, GPE, etc.).  This mapping is the
        single source of truth for how we translate those types into spaCy's
        entity label vocabulary.

        Returns None for types that have no direct NER analogue (CODE, DATE,
        QUANTITY, OTHER) — in that case _group_chunks_by_entity sweeps all
        named-entity types.
        """
        _MAP = {
            "PERSON":   "PERSON",
            "ORG":      "ORG",
            "GPE":      "GPE",
            "PRODUCT":  "PRODUCT",
            "EVENT":    "EVENT",
            "MONEY":    "MONEY",
            "QUANTITY": "QUANTITY",
            # DATE, CODE, OTHER have no reliable spaCy analogue; use all types.
        }
        return _MAP.get(semantic_type) if semantic_type else None

    def _group_chunks_by_entity(
        self,
        candidate_chunks: list,
        ner_label: Optional[str],
        top_k_per_entity: int,
    ) -> tuple:
        """
        Two-phase entity grouping designed to avoid running spaCy NER on every chunk.

        Phase 1 — Discovery (NER on a sample):
            Run spaCy NER on up to ENTITY_DISCOVERY_SAMPLE chunks to collect all
            entity names. This is fast (seconds, not minutes).

        Phase 2 — Assignment (FlashText on all chunks):
            Build a FlashText KeywordProcessor from the discovered names and run it
            over every chunk. FlashText processes millions of strings/sec — far faster
            than NER.

        Chunks that FlashText cannot assign fall into `unassigned`.

        Returns:
            entity_to_chunks: Dict[str, List[TextChunk]] — top_k chunks per entity
            unassigned: List[TextChunk] — chunks with no discovered entity string
        """
        import random
        from collections import defaultdict, Counter as _Counter
        from flashtext import KeywordProcessor
        from config import NER_BATCH_SIZE

        ENTITY_DISCOVERY_SAMPLE = 5000   # NER only on this many chunks
        ACCEPTABLE_LABELS = {"PERSON", "ORG", "GPE", "PRODUCT"}
        label_filter = {ner_label} if ner_label else ACCEPTABLE_LABELS

        # ── Phase 1: Entity discovery via NER on a sample ────────────────────
        total = len(candidate_chunks)
        sample_size = min(ENTITY_DISCOVERY_SAMPLE, total)
        sample_indices = random.sample(range(total), sample_size)
        sample_chunks = [candidate_chunks[i] for i in sample_indices]

        logger.info(
            f"[EntityFirst] Phase-1 NER discovery on {sample_size}/{total} chunks "
            f"(label filter: {ner_label or 'ALL'})"
        )

        entity_counter: "_Counter[str]" = _Counter()
        sample_texts = [c.content for c in sample_chunks]
        for doc in self._nlp.pipe(
            sample_texts,
            batch_size=NER_BATCH_SIZE,
            disable=["tok2vec", "tagger", "parser", "attribute_ruler", "lemmatizer"],
        ):
            for ent in doc.ents:
                if ent.label_ in label_filter:
                    name = ent.text.strip()
                    if len(name) > 1:
                        entity_counter[name] += 1

        if not entity_counter:
            logger.warning(
                "[EntityFirst] NER discovered no entities in sample — "
                "all chunks will be unassigned"
            )
            return {}, candidate_chunks

        discovered_entities = list(entity_counter.keys())
        logger.info(
            f"[EntityFirst] Phase-1 discovered {len(discovered_entities)} unique entities "
            f"(top-5 by freq: {[e for e, _ in entity_counter.most_common(5)]})"
        )

        # ── Phase 2: FlashText assignment over all chunks ────────────────────
        kp = KeywordProcessor(case_sensitive=False)
        for ent_name in discovered_entities:
            kp.add_keyword(ent_name)

        logger.info(
            f"[EntityFirst] Phase-2 FlashText assignment over {total} chunks"
        )

        entity_to_all_chunks: Dict[str, list] = defaultdict(list)
        unassigned: list = []

        for chunk in candidate_chunks:
            hits = kp.extract_keywords(chunk.content)
            # hits is a list of matched entity names; use the most frequent
            if hits:
                primary = _Counter(hits).most_common(1)[0][0]
                entity_to_all_chunks[primary].append(chunk)
            else:
                unassigned.append(chunk)

        # Keep only top_k chunks per entity
        entity_to_chunks: Dict[str, list] = {
            entity: chunks[:top_k_per_entity]
            for entity, chunks in entity_to_all_chunks.items()
        }

        logger.info(
            f"[EntityFirst] {len(entity_to_chunks)} entities assigned, "
            f"{len(unassigned)} unassigned chunks"
        )
        return entity_to_chunks, unassigned

    def _entity_first_extraction(
        self,
        table_name: str,
        schema: Dict[str, Any],
        sql_schema: Dict[str, Any],
        identity_col: str,
        ner_label: Optional[str],
        candidate_chunks: list,
        normalization_hints: Dict[str, Any],
    ) -> int:
        """
        Entity-first extraction pipeline.

        1. Group candidate chunks by entity using spaCy NER (no LLM cost).
        2. For each entity, run the LLM on only its top-K chunks.
        3. Upsert results directly into the DB.
        4. Process a small set of unassigned chunks with the standard path.

        This reduces LLM calls from O(all_candidates) to O(entities × top_k).
        """
        from collections import defaultdict as _dd

        from config import TOP_K_CHUNKS_PER_ENTITY, UNASSIGNED_CHUNK_CAP

        # normalization_hints contain EXPECTED OUTPUT values (e.g. 'USA'),
        # not the text forms as they appear in documents.  Do NOT seed FlashText
        # with them — FlashText must match document text forms, and NER Phase-1
        # discovers those from the corpus sample.  Normalization hints are only
        # used later in the LLM extraction prompt to standardize output values.
        entity_to_chunks, unassigned = self._group_chunks_by_entity(
            candidate_chunks, ner_label,
            top_k_per_entity=TOP_K_CHUNKS_PER_ENTITY,
        )

        # For entity-first extraction the context is tightly focused (all
        # chunks belong to ONE entity), so the 7B model can reliably handle
        # the full schema in a single call.  Pass col_batch_size_override that
        # exceeds schema width to disable column batching entirely.
        _no_batch_size = len(schema) + 1

        self.data_layer.create_dynamic_table(table_name, sql_schema)
        total_records = 0

        # --- Per-entity targeted LLM extraction (parallel) ---
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from config import EXTRACTION_MAX_WORKERS

        entity_items = list(entity_to_chunks.items())
        logger.info(
            f"[EntityFirst] Extracting {len(entity_items)} entities × "
            f"≤{TOP_K_CHUNKS_PER_ENTITY} chunks each for '{table_name}' "
            f"using {EXTRACTION_MAX_WORKERS} workers"
        )

        def _extract_entity(entity_name: str, entity_chunks: list):
            chunk_texts   = [c.content  for c in entity_chunks]
            chunk_ids_lst = [c.chunk_id for c in entity_chunks]
            results = self.extractor.extract_batch(
                chunk_texts,
                chunk_ids_lst,
                table_name,
                schema,
                normalization_hints=normalization_hints,
                entity_col=identity_col,
                col_batch_size_override=_no_batch_size,
            )
            pairs = [
                (record, er.chunk_id)
                for er in results
                if not er.error
                for record in er.records
            ]
            # Guarantee the _entity routing field is always populated
            for record, _ in pairs:
                if not record.get("_entity"):
                    record["_entity"] = entity_name
                if identity_col not in record:
                    record[identity_col] = entity_name
            return pairs

        # Collect all results then bulk-upsert once per 1000 entities to
        # amortise the DB round-trips without holding everything in RAM.
        all_pairs: list = []
        batch_size = 1000

        with ThreadPoolExecutor(max_workers=EXTRACTION_MAX_WORKERS) as pool:
            futs = {
                pool.submit(_extract_entity, name, chunks): name
                for name, chunks in entity_items
            }
            done_count = 0
            for fut in as_completed(futs):
                pairs = fut.result()
                all_pairs.extend(pairs)
                done_count += 1
                if done_count % batch_size == 0:
                    if all_pairs:
                        pv = self.data_layer.upsert_by_entity(table_name, identity_col, all_pairs)
                        self.data_layer.bulk_insert_provenance(table_name, pv)
                        total_records += len(pv)
                        all_pairs = []
                    logger.info(f"[EntityFirst] {done_count}/{len(entity_items)} entities done")

        # Flush remainder
        if all_pairs:
            pv = self.data_layer.upsert_by_entity(table_name, identity_col, all_pairs)
            self.data_layer.bulk_insert_provenance(table_name, pv)
            total_records += len(pv)

        # --- Unassigned chunks: hard-capped standard extraction ──────────────
        # With the correct NER label and FlashText, unassigned should be rare
        # (chunks with no detectable entity name).  A hard cap of
        # UNASSIGNED_CHUNK_CAP prevents this from becoming a bottleneck even
        # in pathological cases.
        if unassigned:
            to_process = unassigned[:UNASSIGNED_CHUNK_CAP]
            logger.info(
                f"[EntityFirst] Processing {len(to_process)} unassigned chunks "
                f"(hard cap={UNASSIGNED_CHUNK_CAP}, total unassigned={len(unassigned)})"
            )
            ua_texts = [c.content for c in to_process]
            ua_ids   = [c.chunk_id for c in to_process]
            results  = self.extractor.extract_batch(
                ua_texts, ua_ids, table_name, schema,
                normalization_hints=normalization_hints,
                entity_col=identity_col,
                col_batch_size_override=_no_batch_size,
            )
            record_chunk_pairs = [
                (record, er.chunk_id)
                for er in results if not er.error
                for record in er.records
            ]
            if record_chunk_pairs:
                prov_pairs = self.data_layer.upsert_by_entity(
                    table_name, identity_col, record_chunk_pairs
                )
                self.data_layer.bulk_insert_provenance(table_name, prov_pairs)
                total_records += len(prov_pairs)

        return total_records

    def _global_extraction(self, lattice) -> int:
        """Perform predicate-based extraction (like QAIRS)."""
        total_records = 0
        
        # Check if there are joins in the workload
        has_joins = len(lattice.join_pairs) > 0
        if has_joins:
            logger.info(f"Workload has {len(lattice.join_pairs)} join pairs: {lattice.join_pairs}")
        
        for table_name, table_info in lattice.tables.items():
            try:
                # Get schema
                schema = self.lattice_planner.get_table_schema(table_name)
                
                # Convert semantic types to SQL types for table creation
                sql_schema = {col: semantic_to_sql_type(sem_type) 
                             for col, sem_type in schema.items()}
                
                # Get candidate chunks
                candidate_chunk_ids = self.data_layer.get_candidates(table_name)
                
                if not candidate_chunk_ids:
                    logger.warning(f"No candidate chunks for {table_name}")
                    continue
                
                logger.info(f"Table {table_name}: {len(candidate_chunk_ids)} candidates, "
                           f"{len(table_info.predicates)} predicates, "
                           f"in_joins={table_info.referenced_in_joins}")
                
                candidate_chunks = self.data_layer.get_chunks_by_ids(candidate_chunk_ids)
                
                # Schema stabilization
                sample_chunks = [c.content for c in candidate_chunks[:50]]
                stabilized_schema = self.extractor.stabilize_schema(
                    table_name,
                    schema,
                    sample_chunks
                )
                
                logger.info(f"Stabilized schema for {table_name}: "
                           f"{len(stabilized_schema.frozen_keys)} keys")
                
                # Build normalization hints from workload predicate literals so the
                # LLM stores values in the exact form the queries expect
                # (e.g. "USA" not "United States" if queries filter on 'USA').
                normalization_hints = self.lattice_planner.get_normalization_hints(table_name)
                if normalization_hints:
                    logger.info(
                        f"Normalization hints for {table_name}: "
                        + ", ".join(f"{c}={v}" for c, v in normalization_hints.items())
                    )

                # For tables in joins, extract ALL data to ensure referential integrity
                # Phase 2 will handle join alignment
                entity_col = self.identity_columns.get(table_name)

                ner_label = self.identity_ner_labels.get(table_name)

                if entity_col:
                    # ── Entity-first extraction ──────────────────────────────
                    # Use spaCy NER to group candidate chunks by entity, then
                    # run the LLM on only the top-K chunks per entity.
                    # LLM calls: N_entities × ceil(TOP_K / CHUNK_BATCH_SIZE)
                    #            vs N_candidates / CHUNK_BATCH_SIZE (brute-force)
                    suffix = "(join table)" if table_info.referenced_in_joins else ""
                    logger.info(
                        f"[EntityFirst] {table_name} {suffix}: "
                        f"{len(candidate_chunks)} candidates → NER grouping → "
                        f"targeted extraction"
                    )
                    table_records = self._entity_first_extraction(
                        table_name=table_name,
                        schema=schema,
                        sql_schema=sql_schema,
                        identity_col=entity_col,
                        ner_label=ner_label,
                        candidate_chunks=candidate_chunks,
                        normalization_hints=normalization_hints,
                    )
                    total_records += table_records
                else:
                    # ── Brute-force extraction (no identity column) ──────────
                    # Only for tables where no entity anchor was found at all.
                    # This is the old path — every candidate chunk is processed.
                    logger.info(
                        f"[BruteForce] {table_name}: "
                        f"{len(candidate_chunks)} candidates, no identity column"
                    )
                    chunk_texts = [c.content for c in candidate_chunks]
                    chunk_ids_list = [c.chunk_id for c in candidate_chunks]

                    results = self.extractor.extract_batch(
                        chunk_texts,
                        chunk_ids_list,
                        table_name,
                        schema,
                        stabilized_schema.frozen_keys,
                        normalization_hints,
                    )

                    table_records = sum(len(r.records) for r in results)
                    total_records += table_records
                    logger.info(f"Extracted {table_records} records for {table_name}")

                    self.data_layer.create_dynamic_table(table_name, sql_schema)
                    prov_pairs = self.data_layer.bulk_insert_records(table_name, results)
                    self.data_layer.bulk_insert_provenance(table_name, prov_pairs)
                    logger.info(f"Inserted {len(prov_pairs)} records into {table_name}")

                # Mark every column FULL — we extracted everything we could find.
                # Any runtime predicate on these columns is a cache hit.
                for col_name in schema.keys():
                    self.data_layer.update_metadata(
                        table_name, col_name, [], "FULL", table_records
                    )
            
            except Exception as e:
                logger.error(f"Error extracting for {table_name}: {e}")
                raise RuntimeError(f"Extraction failed for table '{table_name}': {e}") from e
        
        return total_records

    # -------------------------------------------------------------------------
    # Step 4.5: Record Consolidation
    # -------------------------------------------------------------------------

    def _get_identity_column_llm(self, table_name: str, columns: List[str]) -> Optional[str]:
        """
        Ask the LLM to identify the single column that is the primary identity
        key for this table (i.e. the column that uniquely names the real-world entity).
        Returns the column name, or None if it cannot be determined.
        """
        prompt = (
            f"You are a database schema expert.\n"
            f"Table name: '{table_name}'\n"
            f"Columns: {columns}\n\n"
            f"Which SINGLE column is the PRIMARY IDENTITY column — the one that uniquely "
            f"identifies a real-world entity in this table "
            f"(e.g. person name, company name, player name, team name)?\n\n"
            f"Rules:\n"
            f"- Respond with ONLY the exact column name from the list above.\n"
            f"- Do NOT include any explanation, punctuation, or extra words.\n"
            f"- If no single column clearly identifies the entity, respond with NULL."
        )
        try:
            response = self.extractor.ollama_client.generate(
                prompt,
                max_tokens=20,
                temperature=0.0
            ).strip().strip('"').strip("'")

            # Validate the response is actually one of the columns
            col_lower = {c.lower(): c for c in columns}
            if response.lower() in col_lower:
                chosen = col_lower[response.lower()]
                logger.info(f"LLM chose identity column for '{table_name}': {chosen}")
                return chosen

            if response.upper() == "NULL":
                logger.warning(f"LLM could not identify an identity column for '{table_name}'")
                return None

            # LLM returned something not in the column list — fail loudly
            raise RuntimeError(
                f"LLM returned invalid identity column '{response}' for table '{table_name}'. "
                f"Valid columns: {columns}"
            )
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(
                f"LLM call failed while identifying identity column for '{table_name}': {e}"
            ) from e

    def _consolidate_records(self, lattice) -> None:
        """
        Post-extraction consolidation pass (Step 4.5).

        For each synthesized table:
          1. Ask the LLM which column is the identity key.
          2. Group all rows by the lowercase canonical value of that column.
          3. For groups with >1 row, merge using frequency-wins per attribute.
          4. Keep one canonical row, delete the duplicates, and merge provenance.
        """
        from collections import defaultdict, Counter

        for table_name in list(lattice.tables.keys()):
            logger.info(f"[Consolidation] Processing table '{table_name}'...")

            try:
                all_rows = self.data_layer.get_all_records(table_name)
            except Exception as e:
                logger.error(f"[Consolidation] Cannot read records from '{table_name}': {e}")
                raise

            if len(all_rows) <= 1:
                logger.info(f"[Consolidation] '{table_name}' has {len(all_rows)} rows — nothing to consolidate.")
                continue

            # Columns available in this table (excluding system columns)
            system_cols = {"row_id", "created_at"}
            data_columns = [c for c in all_rows[0].keys() if c not in system_cols]

            if not data_columns:
                logger.warning(f"[Consolidation] No data columns in '{table_name}', skipping.")
                continue

            # Use pre-detected identity column (avoids redundant LLM call).
            identity_col = self.identity_columns.get(table_name)
            if identity_col is None:
                logger.warning(
                    f"[Consolidation] No identity column for '{table_name}' — skipping consolidation."
                )
                continue

            # Step 2: Group rows by canonical identity value
            groups: Dict[str, List[Dict]] = defaultdict(list)
            no_identity = []
            for row in all_rows:
                key = str(row.get(identity_col) or "").strip().lower()
                if key:
                    groups[key].append(row)
                else:
                    no_identity.append(row)

            if no_identity:
                logger.warning(
                    f"[Consolidation] {len(no_identity)} rows in '{table_name}' "
                    f"have no identity value — left as-is."
                )

            merged_count = 0
            deleted_count = 0

            for key, rows in groups.items():
                if len(rows) == 1:
                    continue  # already unique

                # Step 3: Merge using frequency-wins
                merged_data: Dict[str, Any] = {}
                for col in data_columns:
                    if col == identity_col:
                        # Keep the most frequent spelling (frequency-wins)
                        spellings = [str(r[col]).strip() for r in rows if r.get(col)]
                        merged_data[col] = Counter(spellings).most_common(1)[0][0] if spellings else None
                    else:
                        non_null = [str(r[col]).strip() for r in rows if r.get(col) and str(r[col]).strip()]
                        if not non_null:
                            merged_data[col] = None
                        elif len(set(non_null)) == 1:
                            merged_data[col] = non_null[0]
                        else:
                            # Frequency-wins: most common non-null value
                            merged_data[col] = Counter(non_null).most_common(1)[0][0]

                canonical_row = rows[0]
                duplicate_rows = rows[1:]

                # Step 4a: Update canonical row with merged data
                self.data_layer.update_record(table_name, canonical_row["row_id"], merged_data)

                # Step 4b: Merge provenance — collect all chunk IDs from all duplicate rows
                all_chunk_ids: List[str] = []
                for row in rows:
                    try:
                        provenance_list = self.data_layer.get_provenance(
                            row_ids=[row["row_id"]]
                        )
                        for p in provenance_list:
                            all_chunk_ids.extend(json.loads(p.chunk_ids))
                    except Exception as e:
                        logger.warning(f"[Consolidation] Could not read provenance for {row['row_id']}: {e}")

                # Deduplicate chunk IDs
                all_chunk_ids = list(dict.fromkeys(all_chunk_ids))

                self.data_layer.update_provenance_chunks(canonical_row["row_id"], all_chunk_ids)

                # Step 4c: Delete duplicate rows and their provenance
                for dup_row in duplicate_rows:
                    self.data_layer.delete_provenance(dup_row["row_id"])
                    self.data_layer.delete_record(table_name, dup_row["row_id"])
                    deleted_count += 1

                merged_count += 1

            logger.info(
                f"[Consolidation] '{table_name}': merged {merged_count} groups, "
                f"deleted {deleted_count} duplicate rows."
            )

    def _proactive_entity_resolution(self, lattice) -> None:
        """
        Perform proactive entity resolution on join keys.
        Aligns join columns so Phase 2 can execute joins instantly.
        """
        if not lattice.join_pairs:
            logger.info("No joins in workload, skipping entity resolution")
            return
        
        logger.info(f"Performing entity resolution on {len(lattice.join_pairs)} join pairs")
        
        for left_table, right_table in lattice.join_pairs:
            # Identify join columns
            left_schema = self.lattice_planner.get_table_schema(left_table)
            right_schema = self.lattice_planner.get_table_schema(right_table)
            
            # Find likely join keys
            join_keys = []
            for left_col in left_schema.keys():
                for right_col in right_schema.keys():
                    if (left_col == right_col or 
                        left_table.lower() in right_col.lower() or
                        right_table.lower() in left_col.lower()):
                        join_keys.append((left_col, right_col))
            
            if not join_keys:
                logger.warning(f"Could not identify join columns for {left_table} ↔ {right_table}")
                continue
            
            left_col, right_col = join_keys[0]
            logger.info(f"Resolving join: {left_table}.{left_col} ↔ {right_table}.{right_col}")
            
            # Get all unique values from both join columns
            left_values = self.data_layer.get_distinct_values(left_table, left_col)
            right_values = self.data_layer.get_distinct_values(right_table, right_col)
            
            logger.info(f"Found {len(left_values)} unique values in {left_table}.{left_col}")
            logger.info(f"Found {len(right_values)} unique values in {right_table}.{right_col}")
            
            # Create entity mentions
            from entity_resolver import EntityMention
            mentions = []
            
            for value in left_values:
                if value and str(value).strip():
                    mentions.append(EntityMention(
                        mention_id=f"{left_table}_{left_col}_{value}",
                        value=str(value),
                        table_name=left_table,
                        column_name=left_col,
                        semantic_type="JOIN_KEY"
                    ))
            
            for value in right_values:
                if value and str(value).strip():
                    mentions.append(EntityMention(
                        mention_id=f"{right_table}_{right_col}_{value}",
                        value=str(value),
                        table_name=right_table,
                        column_name=right_col,
                        semantic_type="JOIN_KEY"
                    ))
            
            if len(mentions) < 2:
                logger.warning(f"Not enough values to resolve for {left_table} ↔ {right_table}")
                continue
            
            # Perform entity resolution
            logger.info(f"Running entity resolution on {len(mentions)} mentions")
            result = self.entity_resolver.resolve_entities(mentions)
            
            logger.info(f"Resolved into {result.total_clusters} clusters")
            
            # Update database with canonical forms
            for mention_value, canonical_value in result.canonical_map.items():
                # Update left table
                self.data_layer.update_column_values(
                    left_table,
                    left_col,
                    {mention_value: canonical_value}
                )
                
                # Update right table
                self.data_layer.update_column_values(
                    right_table,
                    right_col,
                    {mention_value: canonical_value}
                )
            
            logger.info(f"Updated {left_table}.{left_col} and {right_table}.{right_col} with canonical values")
        
        logger.info("Entity resolution complete - joins are now aligned")
    
    def _save_preprocessing_results(self, lattice) -> None:
        """Save preprocessing results to cache."""
        results_file = self.cache_dir / "preprocessing_results.json"
        
        extraction_plan = self.lattice_planner.get_extraction_plan()
        
        with open(results_file, 'w') as f:
            json.dump(extraction_plan, f, indent=2)
        
        logger.info(f"Saved preprocessing results to {results_file}")
    
    # ========================================================================
    # Phase 2: Runtime Execution
    # ========================================================================

    def restore_lattice(self, workload_queries: List[str]) -> None:
        """
        Re-parse the training workload to rebuild the in-memory lattice without
        re-running any extraction.  Call this in Phase 2 after loading a
        preprocessed DB so the delta engine knows the table schemas and predicate
        literals.

        Semantic type identification (LLM call) is skipped — the DB tables
        already exist with the correct column types from Phase 1.
        """
        logger.info(f"Restoring lattice from {len(workload_queries)} training queries")
        self.lattice_planner.parse_workload(workload_queries, identify_types=False)
        logger.info(
            f"Lattice restored: {len(self.lattice_planner.lattice.tables)} tables"
        )

    # ========================================================================

    def execute_query(self, query: str) -> QueryResult:
        """
        Execute query with delta engine.
        
        Args:
            query: SQL query string
            
        Returns:
            QueryResult
        """
        logger.info("=" * 80)
        logger.info("PHASE 2: RUNTIME QUERY EXECUTION")
        logger.info("=" * 80)
        logger.info(f"Query: {query}")
        
        start_time = time.time()
        
        try:
            # Analyze query
            plan = self.delta_engine.analyze_query(query)
            
            logger.info(f"Delta plan: {plan.delta_type.value}")
            logger.info(f"Missing columns: {plan.missing_columns}")
            logger.info(f"Missing predicates: {plan.missing_predicates}")
            
            # Execute delta (extracts / enriches / aligns as needed)
            delta_result = self.delta_engine.execute_delta(plan, query)

            if not delta_result.success:
                raise Exception(f"Delta execution failed: {delta_result.error}")

            # Execute the SQL query against the synthesized DB
            results = self.data_layer.execute_sql(query)
            logger.info(f"SQL executed: {len(results)} rows returned")
            
            execution_time = time.time() - start_time
            
            result = QueryResult(
                success=True,
                results=results,
                delta_type=plan.delta_type.value,
                rows_extracted=delta_result.rows_extracted,
                rows_enriched=delta_result.rows_enriched,
                execution_time=execution_time
            )
            
            logger.info("=" * 80)
            logger.info("QUERY EXECUTION COMPLETE")
            logger.info(f"Time: {execution_time:.2f}s")
            logger.info(f"Delta type: {plan.delta_type.value}")
            logger.info(f"Rows extracted: {delta_result.rows_extracted}")
            logger.info(f"Rows enriched: {delta_result.rows_enriched}")
            logger.info("=" * 80)
            
            return result
        
        except Exception as e:
            logger.error(f"Query execution failed: {e}", exc_info=True)
            execution_time = time.time() - start_time
            
            return QueryResult(
                success=False,
                results=[],
                delta_type="error",
                rows_extracted=0,
                rows_enriched=0,
                execution_time=execution_time,
                error=str(e)
            )
    
    # ========================================================================
    # Utility Methods
    # ========================================================================
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get system statistics."""
        stats = {
            "dataset": self.dataset,
            "total_chunks": self.data_layer.count_chunks(),
            "tables": [],
            "metadata_entries": len(self.data_layer.get_metadata())
        }
        
        # Get table statistics
        metadata_entries = self.data_layer.get_metadata()
        tables_set = set(entry.table_name for entry in metadata_entries)
        
        for table_name in tables_set:
            table_metadata = self.data_layer.get_metadata(table_name=table_name)
            
            stats["tables"].append({
                "name": table_name,
                "columns": len(table_metadata),
                "status": "materialized" if table_metadata else "pending"
            })
        
        return stats
    
    def clear_cache(self) -> None:
        """Clear all caches."""
        import shutil
        
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("Cache cleared")
    
    def close(self) -> None:
        """Close all connections."""
        self.data_layer.close()
        logger.info("WDIRS runner closed")


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    """Main CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="WDIRS - Workload-Driven Incremental Relational Synthesis")
    parser.add_argument("dataset", help="Dataset name")
    parser.add_argument("--preprocess", action="store_true", help="Run preprocessing")
    parser.add_argument("--query", help="Execute SQL query")
    parser.add_argument("--workload", help="Path to workload directory")
    parser.add_argument("--stats", action="store_true", help="Show statistics")
    parser.add_argument("--clear-cache", action="store_true", help="Clear cache")
    
    args = parser.parse_args()
    
    # Initialize runner
    runner = WDIRSRunner(args.dataset)
    
    try:
        if args.clear_cache:
            runner.clear_cache()
            print("Cache cleared")
        
        if args.preprocess:
            result = runner.preprocess(args.workload)
            
            if result.success:
                print(f"\nPreprocessing complete!")
                print(f"Tables: {len(result.tables_processed)}")
                print(f"Chunks: {result.total_chunks}")
                print(f"Records: {result.total_records}")
                print(f"Time: {result.preprocessing_time:.2f}s")
            else:
                print(f"\nPreprocessing failed: {result.error}")
                sys.exit(1)
        
        if args.query:
            result = runner.execute_query(args.query)
            
            if result.success:
                print(f"\nQuery executed successfully!")
                print(f"Delta type: {result.delta_type}")
                print(f"Rows extracted: {result.rows_extracted}")
                print(f"Rows enriched: {result.rows_enriched}")
                print(f"Time: {result.execution_time:.2f}s")
                print(f"\nResults: {len(result.results)} rows")
            else:
                print(f"\nQuery failed: {result.error}")
                sys.exit(1)
        
        if args.stats:
            stats = runner.get_statistics()
            print(f"\nSystem Statistics:")
            print(f"Dataset: {stats['dataset']}")
            print(f"Total chunks: {stats['total_chunks']}")
            print(f"Metadata entries: {stats['metadata_entries']}")
            print(f"\nTables:")
            for table in stats['tables']:
                print(f"  - {table['name']}: {table['columns']} columns ({table['status']})")
    
    finally:
        runner.close()


if __name__ == "__main__":
    main()
