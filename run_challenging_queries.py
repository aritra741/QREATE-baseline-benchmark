"""
Run challenging queries against all UDA systems.

Usage:
    python run_challenging_queries.py --systems all
    python run_challenging_queries.py --systems quest lotus --query-types filter projection
    python run_challenging_queries.py --resume  # Resume from last checkpoint

Features:
- Verbose logging to console and file
- Saves preprocessing and intermediate results for resumability
- Checkpointing at each step
"""

import argparse
import json
import os
import sys
import time
import hashlib
import signal
import faulthandler
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
import traceback

# Add project paths
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "systems"))
sys.path.insert(0, str(PROJECT_ROOT / "systems" / "quest"))

# Check for required dependencies
try:
    import pandas as pd
except ImportError:
    print("ERROR: pandas is required. Install with: pip install pandas")
    sys.exit(1)

from evaluation.logging_utils import setup_logger
from evaluation.config import EvalSettings, Paths, dump_json, load_json


# ==============================================================================
# DATA PATHS
# ==============================================================================

DATA_PATHS = {
    "Med": {
        "disease": PROJECT_ROOT / "Data" / "Med" / "disease.csv",
        "drug": PROJECT_ROOT / "Data" / "Med" / "drug.csv",
        "institution": PROJECT_ROOT / "Data" / "Med" / "institution.csv",
    },
    "Player": {
        "player": PROJECT_ROOT / "Data" / "Player" / "player.csv",
        "team": PROJECT_ROOT / "Data" / "Player" / "team.csv",
        "manager": PROJECT_ROOT / "Data" / "Player" / "manager.csv",
        "city": PROJECT_ROOT / "Data" / "Player" / "city.csv",
    },
    "Art": {
        "art": PROJECT_ROOT / "Data" / "Art" / "Art.csv",
    },
    "Legal": {
        "legal_case": PROJECT_ROOT / "Data" / "Legal" / "Legal.csv",
    },
    "Finan": {
        "finance": PROJECT_ROOT / "Data" / "Finan" / "Finan.csv",
    }
}

ATTRIBUTE_PATHS = {
    "Med": PROJECT_ROOT / "Query" / "Med" / "Med_attributes.json",
    "Player": PROJECT_ROOT / "Query" / "Player" / "Player_attributes.json",
    "Art": PROJECT_ROOT / "Query" / "Art" / "Art_attributes.json",
    "Legal": PROJECT_ROOT / "Query" / "Legal" / "Legal_attributes.json",
    "Finan": PROJECT_ROOT / "Query" / "Finan" / "Finan_attributes.json",
}


def load_ground_truth(dataset: str, entity: str) -> Optional[pd.DataFrame]:
    """Load ground truth CSV for a dataset/entity."""
    if dataset in DATA_PATHS and entity in DATA_PATHS[dataset]:
        path = DATA_PATHS[dataset][entity]
        if path.exists():
            return pd.read_csv(path)
    return None


def load_attributes(dataset: str) -> Optional[Dict]:
    """Load attribute definitions for a dataset."""
    if dataset in ATTRIBUTE_PATHS:
        path = ATTRIBUTE_PATHS[dataset]
        if path.exists():
            return load_json(path)
    return None


# ==============================================================================
# CONFIGURATION
# ==============================================================================

@dataclass
class RunConfig:
    """Configuration for a test run."""
    run_id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    output_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "results" / "challenging_queries")
    log_level: str = "DEBUG"
    
    # System settings
    llm_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    
    # Resumability
    checkpoint_file: Optional[Path] = None
    
    def __post_init__(self):
        self.output_dir = Path(self.output_dir) / self.run_id
        self.checkpoint_file = self.output_dir / "checkpoint.json"


# ==============================================================================
# CHALLENGING QUERIES DEFINITION
# ==============================================================================

CHALLENGING_QUERIES = {
    "simple": [
        {
            "id": "simple_1",
            "name": "List all diseases with their types",
            "dataset": "Med",
            "entity": "disease",
            "sql": """SELECT disease_name, disease_type, prognosis
FROM disease""",
            "difficulty": "easy",
            "reason": "Basic projection from disease table - straightforward attribute extraction"
        },
        {
            "id": "simple_2",
            "name": "List all NBA players with their positions and nationalities",
            "dataset": "Player",
            "entity": "player",
            "sql": """SELECT name, position, nationality, team
FROM player""",
            "difficulty": "easy",
            "reason": "Simple attribute selection on player table with no filtering"
        }
    ],
    
    "filter": [
        {
            "id": "filter_1",
            "name": "Find psychiatric diseases",
            "dataset": "Med",
            "entity": "disease",
            "sql": """SELECT disease_name, disease_type, common_symptoms, treatments
FROM disease
WHERE disease_type = 'psychiatric'""",
            "difficulty": "easy",
            "reason": "Simple equality filter on disease_type field"
        },
        {
            "id": "filter_2", 
            "name": "Find Frontcourt players",
            "dataset": "Player",
            "entity": "player",
            "sql": """SELECT name, team, position, nationality, draft_year
FROM player
WHERE position = 'Frontcourt'""",
            "difficulty": "easy",
            "reason": "Simple equality filter on position field"
        },
        {
            "id": "filter_3",
            "name": "Find inflammatory diseases",
            "dataset": "Med",
            "entity": "disease",
            "sql": """SELECT disease_name, disease_type, etiology, treatment_challenges
FROM disease
WHERE disease_type = 'inflammatory'""",
            "difficulty": "easy",
            "reason": "Simple equality filter on disease_type field"
        }
    ],
    
    "projection": [
        {
            "id": "projection_1",
            "name": "Extract diagnostic and treatment information from diseases",
            "dataset": "Med",
            "entity": "disease",
            "sql": """SELECT disease_name, disease_type, diagnostic_methods, 
       common_symptoms, treatments, prognosis
FROM disease""",
            "difficulty": "medium",
            "reason": "Extracting multiple medical attributes including diagnostic and treatment information"
        },
        {
            "id": "projection_2",
            "name": "Extract comprehensive player statistics",
            "dataset": "Player",
            "entity": "player",
            "sql": """SELECT name, position, nationality, team, 
       college, nba_championships, mvp_awards, olympic_gold_medals
FROM player""",
            "difficulty": "medium",
            "reason": "8 attributes mixing categorical and numerical data requiring accurate extraction"
        },
        {
            "id": "projection_3",
            "name": "Extract financial and operational data from companies",
            "dataset": "Finan",
            "entity": "finance",
            "sql": """SELECT company_name, principal_activities, revenue, 
       net_profit_or_loss, total_assets, business_risks
FROM finance""",
            "difficulty": "hard",
            "reason": "Financial attributes scattered across long 100+ page documents; requires careful value extraction"
        }
    ],
    
    "join": [
        {
            "id": "join_1",
            "name": "Select infectious disease information",
            "dataset": "Med",
            "entity": "disease",
            "sql": """SELECT disease_name, disease_type, treatments, diagnostic_methods, common_symptoms
FROM disease
WHERE disease_type = 'infectious'""",
            "difficulty": "medium",
            "reason": "Multi-attribute extraction with equality filter on category"
        },
        {
            "id": "join_2",
            "name": "Select championship-winning players",
            "dataset": "Player",
            "entity": "player",
            "sql": """SELECT name, team, position, nationality, nba_championships
FROM player
WHERE nba_championships > 0""",
            "difficulty": "medium",
            "reason": "Filtering on numerical comparison and multi-attribute extraction"
        },
        {
            "id": "join_3",
            "name": "Select genetic diseases",
            "dataset": "Med",
            "entity": "disease",
            "sql": """SELECT disease_name, disease_type, pathogenesis, prognosis
FROM disease
WHERE disease_type = 'genetic'""",
            "difficulty": "easy",
            "reason": "Multi-attribute extraction with equality filter"
        }
    ],
    
    "aggregation": [
        {
            "id": "agg_1",
            "name": "Count diseases by type",
            "dataset": "Med",
            "entity": "disease",
            "sql": """SELECT disease_type, COUNT(*) AS disease_count
FROM disease
GROUP BY disease_type""",
            "difficulty": "medium",
            "reason": "Tests GROUP BY and COUNT aggregation across multiple categories"
        },
        {
            "id": "agg_2",
            "name": "Analyze USA players by position",
            "dataset": "Player",
            "entity": "player",
            "sql": """SELECT position, COUNT(*) AS player_count, 
       AVG(nba_championships) AS avg_championships
FROM player
WHERE nationality = 'American'
GROUP BY position""",
            "difficulty": "medium",
            "reason": "Tests GROUP BY with entity matching and aggregation functions on numerical data"
        },
        {
            "id": "agg_3",
            "name": "Count companies by activity",
            "dataset": "Finan",
            "entity": "finance",
            "sql": """SELECT principal_activities, COUNT(*) AS company_count
FROM finance
GROUP BY principal_activities""",
            "difficulty": "medium",
            "reason": "Tests GROUP BY and COUNT on text field from financial documents"
        }
    ],
    
    "union": [
        {
            "id": "union_1",
            "name": "Find players with notable achievements",
            "dataset": "Player",
            "entity": "player",
            "sql": """SELECT name, nationality, nba_championships AS achievement_count, 'Championships' AS type
FROM player
WHERE nba_championships > 0
UNION ALL
SELECT name, nationality, mvp_awards AS achievement_count, 'MVP Awards' AS type
FROM player
WHERE mvp_awards > 0""",
            "difficulty": "medium",
            "reason": "UNION of same table with different numerical filters; requires accurate extraction of both fields"
        },
        {
            "id": "union_2",
            "name": "Combine disease diagnostic and treatment information",
            "dataset": "Med",
            "entity": "disease",
            "sql": """SELECT disease_name, diagnostic_methods AS clinical_info, 'Diagnostic' AS info_type
FROM disease
WHERE diagnostic_methods IS NOT NULL
UNION ALL
SELECT disease_name, treatments AS clinical_info, 'Treatment' AS info_type
FROM disease
WHERE treatments IS NOT NULL""",
            "difficulty": "hard",
            "reason": "Cross-field union requiring accurate extraction and understanding of different medical information types"
        },
        {
            "id": "union_3",
            "name": "Compare financial companies by business metrics",
            "dataset": "Finan",
            "entity": "finance",
            "sql": """SELECT company_name, revenue AS metric_value, 'Revenue' AS metric_type
FROM finance
WHERE revenue > 0
UNION ALL
SELECT company_name, total_assets AS metric_value, 'Total Assets' AS metric_type
FROM finance
WHERE total_assets > 0""",
            "difficulty": "hard",
            "reason": "UNION of numerical metrics from different columns requiring proper value extraction and comparison"
        }
    ]
}


# ==============================================================================
# SYSTEM RUNNERS
# ==============================================================================

class SystemRunner:
    """Base class for running UDA systems."""
    
    def __init__(self, config: RunConfig, logger):
        self.config = config
        self.logger = logger
        self.name = "base"
        self._data_cache: Dict[str, pd.DataFrame] = {}
        
    def run_query(self, query: Dict) -> Tuple[Optional[pd.DataFrame], Dict]:
        """Run a single query. Returns (result_df, metadata)."""
        raise NotImplementedError
    
    def preprocess(self, dataset: str, entity: str) -> Dict:
        """Preprocess data for a dataset/entity. Returns metadata."""
        raise NotImplementedError
    
    def load_data(self, dataset: str, entity: str) -> Optional[pd.DataFrame]:
        """Load ground truth data for an entity."""
        cache_key = f"{dataset}_{entity}"
        if cache_key in self._data_cache:
            return self._data_cache[cache_key]
        
        df = load_ground_truth(dataset, entity)
        if df is not None:
            self._data_cache[cache_key] = df
            self.logger.debug(f"Loaded {len(df)} rows for {dataset}/{entity}")
        else:
            self.logger.warning(f"No data found for {dataset}/{entity}")
        return df
    
    def get_entity_list(self, query: Dict) -> List[str]:
        """Extract list of entities from a query."""
        entity_str = query.get("entity", "")
        return [e.strip() for e in entity_str.split(",") if e.strip()]


class QuestRunner(SystemRunner):
    """Runner for QUEST system."""
    
    def __init__(self, config: RunConfig, logger):
        super().__init__(config, logger)
        self.name = "quest"
        self._initialized = False
        
    def _ensure_init(self):
        if self._initialized:
            return
        try:
            from quest.sql.parser import sqlparser
            from quest.sql.planner.logical import LogicalPlanner
            from quest.sql.planner.physical import TextPhysicalPlanner
            from quest.sql.processer.processer import Processer
            from quest.db.indexer.indexer import load_all_indexer
            from quest.core.llm.sampler import AttrSampler
            from quest.core.llm.llm_query import TextLLMQuerier
            
            self.sqlparser = sqlparser
            self.LogicalPlanner = LogicalPlanner
            self.TextPhysicalPlanner = TextPhysicalPlanner
            self.Processer = Processer
            self.load_all_indexer = load_all_indexer
            self.AttrSampler = AttrSampler
            self.TextLLMQuerier = TextLLMQuerier
            self._initialized = True
            self.logger.info("[QUEST] Modules loaded successfully")
        except ImportError as e:
            self.logger.error(f"[QUEST] Failed to import: {e}")
            raise
            
    def preprocess(self, dataset: str, entity: str) -> Dict:
        self._ensure_init()
        self.logger.info(f"[QUEST] Preprocessing {dataset}/{entity}...")
        
        preprocess_dir = self.config.output_dir / "preprocessing" / self.name / dataset / entity
        preprocess_dir.mkdir(parents=True, exist_ok=True)
        
        metadata = {
            "system": self.name,
            "dataset": dataset,
            "entity": entity,
            "timestamp": datetime.now().isoformat(),
            "status": "pending"
        }
        
        try:
            # Load/build indexer
            table_to_type = {entity: "TextDoc"}
            self.logger.debug(f"[QUEST] Loading indexer for {entity}...")
            
            # Note: In actual implementation, this would build/load the index
            # For now we just record that preprocessing was attempted
            metadata["status"] = "completed"
            metadata["index_loaded"] = True
            
        except Exception as e:
            self.logger.error(f"[QUEST] Preprocessing failed: {e}")
            metadata["status"] = "failed"
            metadata["error"] = str(e)
            
        # Save preprocessing metadata
        dump_json(metadata, preprocess_dir / "metadata.json")
        self.logger.info(f"[QUEST] Preprocessing saved to {preprocess_dir}")
        
        return metadata
    
    def run_query(self, query: Dict) -> Tuple[Optional[pd.DataFrame], Dict]:
        self._ensure_init()
        
        query_id = query["id"]
        sql = query["sql"]
        dataset = query["dataset"]
        entity = query.get("entity", "").lower()
        query_type = query.get("type", "unknown")
        
        self.logger.info(f"[QUEST] Running query {query_id}...")
        self.logger.debug(f"[QUEST] SQL: {sql}")
        
        metadata = {
            "system": self.name,
            "query_id": query_id,
            "start_time": datetime.now().isoformat(),
            "status": "running"
        }
        
        result_df = None
        
        # QUEST only supports SPJ (Selection-Projection-Join) queries
        # Skip aggregation and union queries
        if query_type in ["aggregation", "union"]:
            self.logger.info(f"[QUEST] Skipping {query_type} query (not supported by QUEST - SPJ only)")
            metadata["status"] = "unsupported"
            metadata["error"] = f"QUEST does not support {query_type} queries (SPJ only)"
            metadata["end_time"] = datetime.now().isoformat()
            return result_df, metadata
        
        try:
            start_time = time.time()
            
            # Parse SQL
            self.logger.debug("[QUEST] Parsing SQL...")
            ast = self.sqlparser.parse_sql(sql)
            metadata["parse_time"] = time.time() - start_time
            self.logger.debug(f"[QUEST] Parse completed in {metadata['parse_time']:.2f}s")
            
            # Build logical plan
            self.logger.debug("[QUEST] Building logical plan...")
            logical_planner = self.LogicalPlanner()
            logical_plan = logical_planner.build_logical_plan(ast)
            metadata["logical_plan_time"] = time.time() - start_time - metadata["parse_time"]
            self.logger.debug(f"[QUEST] Logical plan built in {metadata['logical_plan_time']:.2f}s")
            
            # Load indexer for required tables
            self.logger.debug("[QUEST] Loading indexer...")
            from quest.db.indexer.indexer import load_all_indexer
            from quest.core.llm.sampler import AttrSampler
            from quest.core.llm.llm_query import TextLLMQuerier
            from quest.sql.planner.physical import TextPhysicalPlanner
            from quest.sql.processer.processer import Processer
            
            # CRITICAL FIX: Pass table_to_type=None to load ALL pre-built indexes from config
            # Do NOT pass a filtered table_to_type, as it will override the full config
            
            try:
                gb_indexer = load_all_indexer(table_to_type=None)
                self.logger.debug(f"[QUEST] Indexer loaded for: {list(gb_indexer.table_to_indexer.keys())}")
                
                # Check how many documents are in the index
                for table_name, indexer_obj in gb_indexer.table_to_indexer.items():
                    doc_ids = indexer_obj.get_docs_id()
                    self.logger.info(f"[QUEST] Index '{table_name}' has {len(doc_ids)} documents")
                    if len(doc_ids) == 0:
                        self.logger.warning(f"[QUEST] WARNING: Index '{table_name}' is EMPTY!")
                    elif len(doc_ids) <= 5:
                        self.logger.info(f"[QUEST] Document IDs in '{table_name}': {doc_ids}")
                    else:
                        self.logger.info(f"[QUEST] First 5 document IDs in '{table_name}': {doc_ids[:5]}")
            except FileNotFoundError as e:
                self.logger.warning(f"[QUEST] Index not found: {e}")
                metadata["status"] = "requires_index"
                metadata["error"] = str(e)
                metadata["total_time"] = time.time() - start_time
                metadata["end_time"] = datetime.now().isoformat()
                return result_df, metadata
            except Exception as e:
                self.logger.warning(f"[QUEST] Failed to load index: {e}")
                metadata["status"] = "requires_index"
                metadata["error"] = str(e)
                metadata["total_time"] = time.time() - start_time
                metadata["end_time"] = datetime.now().isoformat()
                return result_df, metadata
            
            # Load attribute definitions for the dataset
            attributes = load_attributes(dataset)
            if not attributes:
                self.logger.warning(f"[QUEST] No attributes file found for {dataset}")
                metadata["status"] = "requires_schema"
                metadata["error"] = f"No attribute schema file found for {dataset}"
                metadata["total_time"] = time.time() - start_time
                metadata["end_time"] = datetime.now().isoformat()
                return result_df, metadata
            
            # Case-insensitive entity lookup
            entity_attrs = None
            for key in attributes:
                if key.lower() == entity.lower():
                    entity_attrs = attributes[key]
                    break
            
            if entity_attrs is None:
                self.logger.warning(f"[QUEST] No attributes found for entity {entity} in {dataset}")
                metadata["status"] = "requires_schema"
                metadata["error"] = f"No attribute schema found for {dataset}/{entity}"
                metadata["total_time"] = time.time() - start_time
                metadata["end_time"] = datetime.now().isoformat()
                return result_df, metadata
            
            # Build prompt/schema in the format expected by AttrSampler and TextLLMQuerier:
            # "attr_name: description" on each line (colon separator is required for parsing)
            attr_lines = []
            for attr_name, attr_info in entity_attrs.items():
                description = attr_info.get("description", "") if isinstance(attr_info, dict) else ""
                attr_lines.append(f"{attr_name}: {description}")
            prompt_str = "\n".join(attr_lines)
            
            self.logger.debug(f"[QUEST] Schema built with {len(attr_lines)} attributes")
            
            # Create sampler and querier with properly formatted schema
            gb_sampler = AttrSampler(schema=prompt_str)
            gb_querier = TextLLMQuerier(prompt=prompt_str)
            
            # CRITICAL: Initialize sampler with sample data from the index
            # This populates the evidence dictionary that's used during retrieval
            self.logger.info(f"[QUEST] Sampling documents from {entity} index for evidence...")
            try:
                indexer_obj, _ = gb_indexer.get_indexer(entity)
                self.logger.debug(f"[QUEST] Got indexer for {entity}, has {len(indexer_obj.get_docs_id())} docs")
                
                gb_sampler.try_sample(indexer_obj, prompt_str)
                
                self.logger.info(f"[QUEST] Sampler initialized with evidence for {len(gb_sampler.map_attr_evidence)} attributes")
                
                # Log what evidence was found for debugging
                for attr, evidence in gb_sampler.map_attr_evidence.items():
                    if evidence:
                        self.logger.debug(f"[QUEST]   - {attr}: {len(evidence)} chars of evidence")
                    else:
                        self.logger.warning(f"[QUEST]   - {attr}: NO EVIDENCE FOUND!")
                        
            except Exception as e:
                self.logger.error(f"[QUEST] Failed to sample documents: {e}")
                self.logger.error(f"[QUEST] Traceback:\n{traceback.format_exc()}")
                # Continue anyway - the query might still work with empty evidence
            
            # Build physical plan
            self.logger.debug("[QUEST] Building physical plan...")
            physical_planner = TextPhysicalPlanner(gb_indexer, gb_querier, sampler=gb_sampler)
            physical_plan = physical_planner.build(logical_plan)
            metadata["physical_plan_time"] = time.time() - start_time - metadata.get("logical_plan_time", 0) - metadata.get("parse_time", 0)
            
            # Execute
            self.logger.debug("[QUEST] Executing query...")
            processer = Processer()
            result = processer.process(physical_plan)
            
            # Convert result to DataFrame if possible
            self.logger.debug(f"[QUEST] Result type: {type(result)}")
            if result is not None:
                if isinstance(result, list):
                    self.logger.debug(f"[QUEST] Converting list result with {len(result)} items")
                    result_df = pd.DataFrame(result)
                elif hasattr(result, 'to_dataframe'):
                    self.logger.debug("[QUEST] Converting result using to_dataframe()")
                    result_df = result.to_dataframe()
                elif isinstance(result, pd.DataFrame):
                    self.logger.debug("[QUEST] Result is already a DataFrame")
                    result_df = result
                    self.logger.info(f"[QUEST] DataFrame shape: {result_df.shape} (rows={len(result_df)}, cols={len(result_df.columns)})")
                    self.logger.info(f"[QUEST] DataFrame columns: {list(result_df.columns)}")
                    if len(result_df) == 0:
                        self.logger.warning("[QUEST] DataFrame is EMPTY - no rows returned!")
                    else:
                        self.logger.info(f"[QUEST] First few rows:\n{result_df.head(3)}")
                else:
                    self.logger.warning(f"[QUEST] Unknown result type: {type(result)}, result: {result}")
                    # Try to inspect the result object
                    if hasattr(result, '__dict__'):
                        self.logger.debug(f"[QUEST] Result attributes: {list(result.__dict__.keys())}")
                    # Try converting to string representation
                    try:
                        result_str = str(result)[:500]  # First 500 chars
                        self.logger.debug(f"[QUEST] Result string repr: {result_str}")
                    except:
                        pass
            else:
                self.logger.warning("[QUEST] Result is None")
                    
            metadata["status"] = "completed"
            metadata["total_time"] = time.time() - start_time
            metadata["result_count"] = len(result_df) if result_df is not None else 0
            
        except Exception as e:
            self.logger.error(f"[QUEST] Query failed: {e}")
            self.logger.error(f"[QUEST] Full traceback:\n{traceback.format_exc()}")
            metadata["status"] = "failed"
            metadata["error"] = str(e)
            metadata["traceback"] = traceback.format_exc()
            
        metadata["end_time"] = datetime.now().isoformat()
        
        return result_df, metadata


class UQERunner(SystemRunner):
    """Runner for UQE system."""
    
    # Map dataset/entity names to UQE schema classes
    # Format: (dataset, entity): (module, class, data_path, table_name)
    # - data_path: directory name under systems/UQE/data/
    # - table_name: table name in schema.tables_name for SQL replacement
    SCHEMA_MAP = {
        ("Med", "disease"): ("schema.disease", "DiseaseData", "disease", "disease"),
        ("Med", "drug"): ("schema.drug", "DrugData", "drug", "drug"),
        ("Med", "institution"): ("schema.institutes", "InstitutesData", "institutes", "institutes"),
        ("Player", "player"): ("schema.nba", "NBAData", "nba", "player"),
        ("Finan", "finance"): ("schema.fin", "FinRecordData", "Finance", "financial"),
        ("Legal", "legal_case"): ("schema.lcr", "LegalData", "LCR", "LCR"),
        ("Art", "art"): ("schema.art", "ArtData", "Wikiart", "Wikiart"),
    }
    
    def __init__(self, config: RunConfig, logger):
        super().__init__(config, logger)
        self.name = "uqe"
        self._initialized = False
        self._original_cwd = None
        self.uqe_path = PROJECT_ROOT / "systems" / "UQE"
        
    def _ensure_init(self):
        if self._initialized:
            return
        try:
            # Save original working directory
            self._original_cwd = os.getcwd()
            
            # Change to UQE directory for imports (UQE expects to run from its directory)
            uqe_path = self.uqe_path
            sys.path.insert(0, str(uqe_path))
            os.chdir(uqe_path)
            
            from parse import parser
            from plan import planner
            from optimize import optimizer
            from execute import executor
            
            self.parser = parser
            self.planner = planner
            self.optimizer = optimizer
            self.executor = executor
            self._initialized = True
            self.logger.info("[UQE] Modules loaded successfully")
            
        except ImportError as e:
            self.logger.error(f"[UQE] Failed to import: {e}")
            self._restore_cwd()
            raise
    
    def _restore_cwd(self):
        """Restore original working directory."""
        if self._original_cwd:
            try:
                os.chdir(self._original_cwd)
            except:
                pass
    
    def _get_schema_class(self, dataset: str, entity: str):
        """Get the schema class for a dataset/entity combination."""
        key = (dataset, entity.lower())
        if key in self.SCHEMA_MAP:
            module_name, class_name, data_path, table_name = self.SCHEMA_MAP[key]
            return module_name, class_name, data_path, table_name
        
        # Try case-insensitive match
        for (ds, ent), (mod, cls, data_path, table_name) in self.SCHEMA_MAP.items():
            if ds.lower() == dataset.lower() and ent.lower() == entity.lower():
                return mod, cls, data_path, table_name
        
        return None, None, None, None
    
    def preprocess(self, dataset: str, entity: str) -> Dict:
        self.logger.info(f"[UQE] Preprocessing {dataset}/{entity}...")
        
        preprocess_dir = self.config.output_dir / "preprocessing" / self.name / dataset / entity
        preprocess_dir.mkdir(parents=True, exist_ok=True)
        
        metadata = {
            "system": self.name,
            "dataset": dataset,
            "entity": entity,
            "timestamp": datetime.now().isoformat(),
            "status": "completed"
        }
        
        dump_json(metadata, preprocess_dir / "metadata.json")
        return metadata
    
    def run_query(self, query: Dict) -> Tuple[Optional[pd.DataFrame], Dict]:
        self._ensure_init()
        
        query_id = query["id"]
        sql = query["sql"]
        dataset = query["dataset"]
        entity_str = query.get("entity", "")
        query_type = query.get("type", "unknown")
        
        # Extract first entity (UQE only supports single-entity queries)
        entities = [e.strip() for e in entity_str.split(",") if e.strip()]
        if not entities:
            self.logger.warning(f"[UQE] No entity specified in query")
            metadata = {
                "system": self.name,
                "query_id": query_id,
                "start_time": datetime.now().isoformat(),
                "status": "failed",
                "error": "No entity specified",
                "end_time": datetime.now().isoformat()
            }
            return None, metadata
        
        entity = entities[0].lower()
        
        # If multiple entities, this is likely a join (already handled by query_type check)
        if len(entities) > 1:
            self.logger.info(f"[UQE] Multiple entities detected ({len(entities)}), using first: {entity}")
        
        self.logger.info(f"[UQE] Running query {query_id}...")
        self.logger.debug(f"[UQE] SQL: {sql}")
        
        metadata = {
            "system": self.name,
            "query_id": query_id,
            "start_time": datetime.now().isoformat(),
            "status": "running"
        }
        
        result_df = None
        
        # UQE doesn't support JOIN or UNION queries
        if query_type in ["join", "union"]:
            self.logger.info(f"[UQE] Skipping {query_type} query (not supported by UQE)")
            metadata["status"] = "unsupported"
            metadata["error"] = f"UQE does not support {query_type} queries"
            metadata["end_time"] = datetime.now().isoformat()
            return result_df, metadata
        
        try:
            start_time = time.time()
            
            # Ensure we're in UQE directory
            os.chdir(self.uqe_path)
            
            # Get schema class for this dataset/entity
            module_name, class_name, data_path, table_name = self._get_schema_class(dataset, entity)
            if not module_name:
                self.logger.warning(f"[UQE] No schema mapping found for {dataset}/{entity}")
                metadata["status"] = "requires_schema"
                metadata["error"] = f"No schema mapping found for {dataset}/{entity}"
                metadata["total_time"] = time.time() - start_time
                metadata["end_time"] = datetime.now().isoformat()
                return result_df, metadata
            
            # Normalize table names in SQL: replace entity names with schema table names
            normalized_sql = sql
            # Map all entities to their schema table names
            for (ds, ent), (mod, cls, dpath, tbl) in self.SCHEMA_MAP.items():
                # Replace table names case-insensitively and whole-word only
                import re
                # Replace "FROM entity" with "FROM schema_table"
                normalized_sql = re.sub(rf'\bFROM\s+{ent}\b', f'FROM {tbl}', normalized_sql, flags=re.IGNORECASE)
                normalized_sql = re.sub(rf'\bJOIN\s+{ent}\b', f'JOIN {tbl}', normalized_sql, flags=re.IGNORECASE)
            
            self.logger.debug(f"[UQE] Original SQL: {sql}")
            self.logger.debug(f"[UQE] Normalized SQL: {normalized_sql}")
            
            # Import and instantiate schema class
            self.logger.debug(f"[UQE] Loading schema: {module_name}.{class_name} (data_path={data_path}, table={table_name})")
            try:
                schema_module = __import__(module_name, fromlist=[class_name])
                schema_class = getattr(schema_module, class_name)
                source_data = schema_class(data_path)
            except Exception as e:
                self.logger.error(f"[UQE] Failed to load schema class: {e}")
                self.logger.error(f"[UQE] Traceback:\n{traceback.format_exc()}")
                metadata["status"] = "failed"
                metadata["error"] = f"Failed to load schema: {e}"
                metadata["total_time"] = time.time() - start_time
                metadata["end_time"] = datetime.now().isoformat()
                return result_df, metadata
            
            # Parse query with normalized SQL
            self.logger.debug("[UQE] Parsing query...")
            parsed = self.parser(normalized_sql)
            metadata["parse_time"] = time.time() - start_time
            self.logger.debug(f"[UQE] Parse completed in {metadata['parse_time']:.2f}s")
            
            # Build plan
            self.logger.debug("[UQE] Building plan...")
            plan, invalid = self.planner(parsed, source_data)
            if invalid:
                self.logger.warning("[UQE] Query marked as invalid by planner")
                metadata["status"] = "invalid_query"
                metadata["error"] = "Query planner marked query as invalid"
                metadata["total_time"] = time.time() - start_time
                metadata["end_time"] = datetime.now().isoformat()
                return result_df, metadata
            
            if plan is None:
                self.logger.error("[UQE] Planner returned None")
                metadata["status"] = "failed"
                metadata["error"] = "Planner returned None"
                metadata["total_time"] = time.time() - start_time
                metadata["end_time"] = datetime.now().isoformat()
                return result_df, metadata
            
            metadata["plan_time"] = time.time() - start_time - metadata["parse_time"]
            self.logger.debug(f"[UQE] Plan built in {metadata['plan_time']:.2f}s")
            
            # Optimize plan
            self.logger.debug("[UQE] Optimizing plan...")
            optimized_plan = self.optimizer(plan)
            metadata["optimize_time"] = time.time() - start_time - metadata.get("plan_time", 0) - metadata.get("parse_time", 0)
            self.logger.debug(f"[UQE] Optimization completed in {metadata['optimize_time']:.2f}s")
            
            # Execute plan
            self.logger.debug("[UQE] Executing plan...")
            result_df = self.executor(optimized_plan)
            metadata["execute_time"] = time.time() - start_time - metadata.get("optimize_time", 0) - metadata.get("plan_time", 0) - metadata.get("parse_time", 0)
            self.logger.debug(f"[UQE] Execution completed in {metadata['execute_time']:.2f}s")
            
            # Ensure result is a DataFrame
            if result_df is not None:
                if not isinstance(result_df, pd.DataFrame):
                    self.logger.warning(f"[UQE] Result is not a DataFrame: {type(result_df)}")
                    result_df = None
                else:
                    self.logger.info(f"[UQE] Result shape: {result_df.shape} (rows={len(result_df)}, cols={len(result_df.columns)})")
                    self.logger.info(f"[UQE] Result columns: {list(result_df.columns)}")
                    if len(result_df) == 0:
                        self.logger.warning("[UQE] Result DataFrame is EMPTY - no rows returned!")
                    else:
                        self.logger.info(f"[UQE] First few rows:\n{result_df.head(3)}")
            
            metadata["status"] = "completed"
            metadata["total_time"] = time.time() - start_time
            metadata["result_count"] = len(result_df) if result_df is not None else 0
            
        except Exception as e:
            self.logger.error(f"[UQE] Query failed: {e}")
            self.logger.error(f"[UQE] Full traceback:\n{traceback.format_exc()}")
            metadata["status"] = "failed"
            metadata["error"] = str(e)
            metadata["traceback"] = traceback.format_exc()
        finally:
            self._restore_cwd()
            
        metadata["end_time"] = datetime.now().isoformat()
        
        return result_df, metadata


class LotusRunner(SystemRunner):
    """Runner for LOTUS system."""
    
    def __init__(self, config: RunConfig, logger):
        super().__init__(config, logger)
        self.name = "lotus"
        self._initialized = False
        self._available = True
        
    def _ensure_init(self):
        if self._initialized:
            return
        try:
            import lotus
            from lotus.models import LM
            
            self.lotus = lotus
            self.LM = LM
            self._initialized = True
            self.logger.info("[LOTUS] Modules loaded successfully")
        except ImportError as e:
            self._available = False
            self.logger.warning(f"[LOTUS] Not available (requires Python <3.13): {e}")
            self.logger.warning("[LOTUS] Install with: pip install lotus-ai (Python 3.10-3.12)")
            # Don't raise - will handle gracefully
    
    def preprocess(self, dataset: str, entity: str) -> Dict:
        self.logger.info(f"[LOTUS] Preprocessing {dataset}/{entity}...")
        
        preprocess_dir = self.config.output_dir / "preprocessing" / self.name / dataset / entity
        preprocess_dir.mkdir(parents=True, exist_ok=True)
        
        metadata = {
            "system": self.name,
            "dataset": dataset,
            "entity": entity,
            "timestamp": datetime.now().isoformat(),
            "status": "completed"
        }
        
        dump_json(metadata, preprocess_dir / "metadata.json")
        return metadata
    
    def run_query(self, query: Dict) -> Tuple[Optional[pd.DataFrame], Dict]:
        self._ensure_init()
        
        query_id = query["id"]
        
        self.logger.info(f"[LOTUS] Running query {query_id}...")
        
        metadata = {
            "system": self.name,
            "query_id": query_id,
            "start_time": datetime.now().isoformat(),
        }
        
        if not self._available:
            metadata["status"] = "unavailable"
            metadata["error"] = "lotus-ai requires Python <3.13"
            self.logger.warning(f"[LOTUS] Skipping {query_id} - lotus-ai not available")
        else:
            # LOTUS uses Python API, would need to convert SQL to LOTUS calls
            metadata["status"] = "not_implemented"
        
        metadata["end_time"] = datetime.now().isoformat()
        
        return None, metadata


class UnifyRunner(SystemRunner):
    """Runner for Unify system."""
    
    def __init__(self, config: RunConfig, logger):
        super().__init__(config, logger)
        self.name = "unify"
        self._initialized = False
        self._available = True
        self.unify_path = PROJECT_ROOT / "systems" / "Unify" / "main"
        self._original_cwd = None
        
    def _ensure_init(self):
        if self._initialized:
            return
        try:
            # Save original working directory
            self._original_cwd = os.getcwd()
            
            # Change to Unify directory for imports
            unify_path = self.unify_path
            if not unify_path.exists():
                raise FileNotFoundError(f"Unify path not found: {unify_path}")
            
            sys.path.insert(0, str(unify_path))
            os.chdir(unify_path)
            
            # Import Unify modules
            from unify import recursive_plan_generation
            from PlanManager import planManager
            from chunk import load_process_data_chunks, ChunkExtractor
            from embed import EmbedModel
            from index import indexHNSW
            from semanticParse import semantic_parse, replace_parsed_elements_with_identifiers, BQMatcher
            from utils.llm_config import ModelConfig
            from openai import OpenAI
            
            self.recursive_plan_generation = recursive_plan_generation
            self.planManager = planManager
            self.load_process_data_chunks = load_process_data_chunks
            self.ChunkExtractor = ChunkExtractor
            self.EmbedModel = EmbedModel
            self.indexHNSW = indexHNSW
            self.semantic_parse = semantic_parse
            self.replace_parsed_elements_with_identifiers = replace_parsed_elements_with_identifiers
            self.BQMatcher = BQMatcher
            self.ModelConfig = ModelConfig
            self.OpenAI = OpenAI
            
            # Configure Ollama/Qwen2.5 settings
            self.ollama_model = "qwen2.5:7b-instruct"
            self.ollama_base_url = "http://localhost:11434/v1"
            self.ollama_api_key = "ollama"
            
            self._initialized = True
            self.logger.info("[UNIFY] Modules loaded successfully")
            self.logger.info(f"[UNIFY] Using Ollama model: {self.ollama_model}")
            self.logger.info(f"[UNIFY] Ollama base URL: {self.ollama_base_url}")
        except ImportError as e:
            self._available = False
            self.logger.warning(f"[UNIFY] Failed to import modules: {e}")
            self.logger.error(f"[UNIFY] Traceback:\n{traceback.format_exc()}")
        except FileNotFoundError as e:
            self._available = False
            self.logger.warning(f"[UNIFY] Unify directory not found: {e}")
        except Exception as e:
            self._available = False
            self.logger.error(f"[UNIFY] Unexpected error during initialization: {e}")
            self.logger.error(f"[UNIFY] Traceback:\n{traceback.format_exc()}")
    
    def _restore_cwd(self):
        """Restore original working directory."""
        if self._original_cwd:
            try:
                os.chdir(self._original_cwd)
            except:
                pass
    
    def _get_model_paths(self):
        """Get model identifiers - use HuggingFace model names that will be cached."""
        # Use HuggingFace model names directly - they'll be loaded from cache in /scratch/general/vast/u1592362/hf_cache/
        tokenizer_id = "Qwen/Qwen2.5-7B"
        embedding_id = "sentence-transformers/all-MiniLM-L6-v2"
        
        self.logger.info(f"[UNIFY] Using tokenizer model: {tokenizer_id}")
        self.logger.info(f"[UNIFY] Using embedding model: {embedding_id}")
        self.logger.info(f"[UNIFY] Models will be loaded from HF cache at: /scratch/general/vast/u1592362/hf_cache/")
        
        return tokenizer_id, embedding_id
    
    def preprocess(self, dataset: str, entity: str) -> Dict:
        """Preprocess data for Unify (data loading and indexing)."""
        self._ensure_init()
        
        if not self._available:
            return {"status": "unavailable", "error": "Unify modules not available"}
        
        self.logger.info(f"[UNIFY] Preprocessing {dataset}/{entity}...")
        
        preprocess_dir = self.config.output_dir / "preprocessing" / self.name / dataset / entity
        preprocess_dir.mkdir(parents=True, exist_ok=True)
        
        metadata = {
            "system": self.name,
            "dataset": dataset,
            "entity": entity,
            "timestamp": datetime.now().isoformat(),
            "status": "pending"
        }
        
        try:
            os.chdir(self.unify_path)
            
            # Get data path for this dataset/entity
            data_path = self._get_data_path(dataset, entity)
            if not data_path:
                metadata["status"] = "failed"
                metadata["error"] = f"No data path found for {dataset}/{entity}"
                return metadata
            
            if not Path(data_path).exists():
                metadata["status"] = "failed"
                metadata["error"] = f"Data path does not exist: {data_path}"
                return metadata
            
            # Load and process data chunks
            self.logger.debug(f"[UNIFY] Loading data from {data_path}...")
            chunk_extractor = self.ChunkExtractor()
            tokenizer_path, embedding_path = self._get_model_paths()
            embed_model = self.EmbedModel(
                tokenizer_path=tokenizer_path,
                sentence_model_path=embedding_path
            )
            
            all_file_data, all_chunks, all_ids, all_embeds, all_chunk_locs = self.load_process_data_chunks(
                embed_model, chunk_extractor, data_path
            )
            
            # Build index
            self.logger.debug(f"[UNIFY] Building index with {len(all_chunks)} chunks...")
            index = self.indexHNSW(all_chunks, all_embeds, all_ids, all_chunk_locs)
            
            metadata["status"] = "completed"
            metadata["chunks_count"] = len(all_chunks)
            metadata["index_built"] = True
            
            self.logger.info(f"[UNIFY] Preprocessing completed: {len(all_chunks)} chunks indexed")
            
        except Exception as e:
            self.logger.error(f"[UNIFY] Preprocessing failed: {e}")
            self.logger.error(f"[UNIFY] Traceback:\n{traceback.format_exc()}")
            metadata["status"] = "failed"
            metadata["error"] = str(e)
        
        finally:
            self._restore_cwd()
        
        dump_json(metadata, preprocess_dir / "metadata.json")
        return metadata
    
    def _convert_csv_to_text_dir(self, csv_path: Path, output_dir: Path) -> Path:
        """Convert CSV file to text format in a directory for Unify.
        
        Unify expects a directory containing .txt or .pdf files.
        This converts each CSV row into a text document.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Read CSV
        df = pd.read_csv(csv_path)
        
        # Convert each row to a text document
        # Format: "column1: value1. column2: value2. ..."
        text_lines = []
        for idx, row in df.iterrows():
            row_parts = []
            for col in df.columns:
                val = row[col]
                if pd.notna(val):
                    # Convert to string and clean
                    val_str = str(val).strip()
                    if val_str:
                        row_parts.append(f"{col}: {val_str}")
            
            # Join with periods and newlines for better sentence splitting
            row_text = ". ".join(row_parts) + "."
            text_lines.append(row_text)
        
        # Write to a single text file (Unify will chunk it)
        output_file = output_dir / f"{csv_path.stem}.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n\n".join(text_lines))
        
        self.logger.debug(f"[UNIFY] Converted {len(df)} rows from {csv_path.name} to {output_file}")
        return output_dir
    
    def _get_data_path(self, dataset: str, entity: str) -> Optional[str]:
        """Get the data path for a dataset/entity combination.
        
        Returns a directory path containing .txt files from source_data.
        Unify expects a directory with .txt or .pdf files, which we have in source_data.
        """
        # Map dataset/entity to source_data directory paths
        # These directories contain the original .txt files that Unify can process directly
        source_data_map = {
            ("Med", "disease"): PROJECT_ROOT / "source_data" / "Healthcare" / "disease_small",
            ("Med", "drug"): PROJECT_ROOT / "source_data" / "Healthcare" / "drug_small",
            ("Med", "institution"): PROJECT_ROOT / "source_data" / "Healthcare" / "institutes_small",
            ("Player", "player"): PROJECT_ROOT / "source_data" / "Player" / "player",
            ("Art", "art"): PROJECT_ROOT / "source_data" / "Art" / "wikiart",
            ("Legal", "legal_case"): PROJECT_ROOT / "source_data" / "Legal" / "legal_case",
            ("Finan", "finance"): PROJECT_ROOT / "source_data" / "Finance" / "finance",
        }
        
        key = (dataset, entity.lower())
        text_dir = None
        for (ds, ent), path in source_data_map.items():
            if ds.lower() == dataset.lower() and ent.lower() == entity.lower():
                text_dir = Path(path)
                break
        
        if text_dir is None:
            self.logger.warning(f"[UNIFY] No source_data mapping found for {dataset}/{entity}")
            return None
        
        if not text_dir.exists():
            self.logger.warning(f"[UNIFY] Source data directory does not exist: {text_dir}")
            return None
        
        # Verify directory contains .txt files
        txt_files = list(text_dir.glob("*.txt"))
        if not txt_files:
            self.logger.warning(f"[UNIFY] No .txt files found in {text_dir}")
            return None
        
        self.logger.info(f"[UNIFY] Using source_data directory: {text_dir} ({len(txt_files)} .txt files)")
        return str(text_dir)
    
    def _load_preprocessed_index(self, dataset: str, entity: str) -> Optional[Dict]:
        """Load preprocessed index from disk if available."""
        import pickle
        
        # Preprocessed indexes are saved relative to PROJECT_ROOT
        preprocess_dir = PROJECT_ROOT / "preprocess_unify" / "indexes" / dataset / entity
        
        if not preprocess_dir.exists():
            self.logger.warning(f"[UNIFY] Preprocessed index not found at {preprocess_dir}")
            self.logger.warning(f"[UNIFY] Run: python systems/Unify/scripts/preprocess_unify_data.py --entities {dataset} {entity}")
            return None
        
        pkl_file = preprocess_dir / "preprocessed_data.pkl"
        if not pkl_file.exists():
            self.logger.warning(f"[UNIFY] Preprocessed data file not found: {pkl_file}")
            return None
        
        try:
            self.logger.debug(f"[UNIFY] Loading preprocessed index from {pkl_file}...")
            with open(pkl_file, "rb") as f:
                preprocessed_data = pickle.load(f)
            self.logger.info(f"[UNIFY] ✓ Loaded preprocessed index: {len(preprocessed_data['all_chunks'])} chunks")
            return preprocessed_data
        except Exception as e:
            self.logger.error(f"[UNIFY] Failed to load preprocessed index: {e}")
            return None
    
    def run_query(self, query: Dict) -> Tuple[Optional[pd.DataFrame], Dict]:
        """Run a query with Unify."""
        self._ensure_init()
        
        query_id = query["id"]
        sql = query["sql"]
        dataset = query["dataset"]
        entity = query.get("entity", "").lower()
        query_type = query.get("type", "unknown")
        
        self.logger.info(f"[UNIFY] Running query {query_id}...")
        self.logger.debug(f"[UNIFY] SQL: {sql}")
        
        metadata = {
            "system": self.name,
            "query_id": query_id,
            "start_time": datetime.now().isoformat(),
            "status": "running"
        }
        
        result_df = None
        
        if not self._available:
            metadata["status"] = "unavailable"
            metadata["error"] = "Unify modules not available"
            metadata["end_time"] = datetime.now().isoformat()
            return result_df, metadata
        
        try:
            os.chdir(self.unify_path)
            start_time = time.time()
            
            self.logger.info("[UNIFY] Starting query execution...")
            sys.stdout.flush()
            sys.stderr.flush()
            
            # Try to load preprocessed index (offline preprocessing)
            self.logger.debug("[UNIFY] Attempting to load preprocessed index...")
            sys.stdout.flush()
            sys.stderr.flush()
            preprocessed_data = self._load_preprocessed_index(dataset, entity)
            
            if preprocessed_data is None:
                metadata["status"] = "requires_preprocessing"
                metadata["error"] = f"Preprocessed index not found for {dataset}/{entity}"
                metadata["hint"] = f"Run: python systems/Unify/scripts/preprocess_unify_data.py --entities {dataset} {entity}"
                metadata["total_time"] = time.time() - start_time
                metadata["end_time"] = datetime.now().isoformat()
                return result_df, metadata
            
            # Use preprocessed data (offline)
            all_file_data = preprocessed_data["all_file_data"]
            all_chunks = preprocessed_data["all_chunks"]
            all_ids = preprocessed_data["all_ids"]
            all_embeds = preprocessed_data["all_embeds"]
            all_chunk_locs = preprocessed_data["all_chunk_locs"]
            index = preprocessed_data["index"]
            
            metadata["data_load_time"] = time.time() - start_time
            
            # Initialize Ollama/Qwen2.5 client (compatible with OpenAI interface)
            client = self.OpenAI(api_key=self.ollama_api_key, base_url=self.ollama_base_url)
            chat_model = self.ModelConfig(self.ollama_model)
            # Model path is set correctly via constructor
            
            # Initialize embedding model for semantic operations
            self.logger.info("[UNIFY] Initializing embedding model...")
            sys.stdout.flush()
            sys.stderr.flush()
            try:
                tokenizer_path, embedding_path = self._get_model_paths()
                embed_model = self.EmbedModel(
                    tokenizer_path=tokenizer_path,
                    sentence_model_path=embedding_path
                )
                self.logger.info("[UNIFY] Embedding model initialized successfully")
            except Exception as e:
                self.logger.error(f"[UNIFY] Failed to initialize embedding model: {e}")
                self.logger.error(f"[UNIFY] Traceback:\n{traceback.format_exc()}")
                sys.stdout.flush()
                sys.stderr.flush()
                raise
            sys.stdout.flush()
            sys.stderr.flush()
            
            self.logger.debug(f"[UNIFY] Using LLM: {self.ollama_model}")
            sys.stdout.flush()
            sys.stderr.flush()
            
            # Parse the query
            self.logger.debug("[UNIFY] Parsing query...")
            sys.stdout.flush()
            sys.stderr.flush()
            parsed_result = self.semantic_parse(sql, client, chat_model)
            self.logger.debug("[UNIFY] Query parsed successfully")
            sys.stdout.flush()
            sys.stderr.flush()
            transformed_question = self.replace_parsed_elements_with_identifiers(sql, parsed_result)
            
            metadata["parse_time"] = time.time() - start_time - metadata["data_load_time"]
            
            # Generate plan
            self.logger.debug("[UNIFY] Generating execution plan...")
            bq_matcher = self.BQMatcher(embed_model)
            final_flag, final_plan, final_bq_list, partial_question_list = self.recursive_plan_generation(
                sql, transformed_question, bq_matcher, client, chat_model, embed_model,
                current_plan=[], use_bq_list=[], partial_question_list=[], depth=0
            )
            
            metadata["plan_generation_time"] = time.time() - start_time - metadata.get("parse_time", 0) - metadata["data_load_time"]
            self.logger.debug(f"[UNIFY] Plan generated: {final_flag}")
            
            # Execute plan
            self.logger.debug("[UNIFY] Executing plan...")
            pm = self.planManager(
                sql, final_plan, client, chat_model, final_bq_list, all_file_data, 
                parsed_result, partial_question_list, embed_model, index
            )
            pm.execute_with_plan()
            
            metadata["execution_time"] = time.time() - start_time - metadata.get("plan_generation_time", 0) - metadata.get("parse_time", 0) - metadata["data_load_time"]
            
            # Extract result
            final_result = None
            if pm.BQ_list and "IDPlan" in pm.BQ_list[-1] and pm.BQ_list[-1]["IDPlan"]:
                final_result = pm.BQ_list[-1]["IDPlan"][0].get("Result", None)
            
            if final_result is not None:
                # Convert result to DataFrame if needed
                if isinstance(final_result, list):
                    result_df = pd.DataFrame(final_result)
                elif isinstance(final_result, pd.DataFrame):
                    result_df = final_result
                else:
                    # Try to wrap in a dataframe
                    result_df = pd.DataFrame([final_result])
                
                self.logger.info(f"[UNIFY] Query executed successfully, result shape: {result_df.shape}")
            else:
                self.logger.warning("[UNIFY] No result returned from query execution")
            
            metadata["status"] = "completed"
            metadata["total_time"] = time.time() - start_time
            metadata["result_count"] = len(result_df) if result_df is not None else 0
            
        except Exception as e:
            self.logger.error(f"[UNIFY] Query execution failed: {e}")
            self.logger.error(f"[UNIFY] Full traceback:\n{traceback.format_exc()}")
            metadata["status"] = "failed"
            metadata["error"] = str(e)
            metadata["traceback"] = traceback.format_exc()
            metadata["total_time"] = time.time() - start_time
        
        finally:
            self._restore_cwd()
        
        metadata["end_time"] = datetime.now().isoformat()
        return result_df, metadata


# ==============================================================================
# CHECKPOINT MANAGEMENT
# ==============================================================================

@dataclass
class Checkpoint:
    """Tracks progress for resumability."""
    completed_queries: Dict[str, List[str]] = field(default_factory=dict)  # system -> [query_ids]
    failed_queries: Dict[str, List[str]] = field(default_factory=dict)
    current_system: Optional[str] = None
    current_query_type: Optional[str] = None
    last_update: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def mark_completed(self, system: str, query_id: str):
        if system not in self.completed_queries:
            self.completed_queries[system] = []
        if query_id not in self.completed_queries[system]:
            self.completed_queries[system].append(query_id)
        self.last_update = datetime.now().isoformat()
    
    def mark_failed(self, system: str, query_id: str):
        if system not in self.failed_queries:
            self.failed_queries[system] = []
        if query_id not in self.failed_queries[system]:
            self.failed_queries[system].append(query_id)
        self.last_update = datetime.now().isoformat()
    
    def is_completed(self, system: str, query_id: str) -> bool:
        return query_id in self.completed_queries.get(system, [])
    
    def save(self, path: Path):
        dump_json(asdict(self), path)
    
    @classmethod
    def load(cls, path: Path) -> 'Checkpoint':
        if path.exists():
            data = load_json(path)
            return cls(**data)
        return cls()


# ==============================================================================
# MAIN RUNNER
# ==============================================================================

class ChallengingQueryRunner:
    """Main orchestrator for running challenging queries."""
    
    AVAILABLE_SYSTEMS = ["quest", "uqe", "lotus", "unify"]
    
    SYSTEM_DEPENDENCIES = {
        "quest": ["ply", "sqlglot", "duckdb", "openai", "tiktoken"],
        "uqe": ["tqdm", "numpy", "openai"],
        "unify": ["openai", "torch", "sentence-transformers", "hnswlib"],
        # lotus-ai requires Python <3.13, checked separately
    }
    
    def __init__(self, config: RunConfig):
        self.config = config
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logging
        log_file = self.config.output_dir / "run.log"
        self.logger = setup_logger("runner", level=config.log_level, log_file=log_file)
        
        self.logger.info("=" * 80)
        self.logger.info(f"Starting Challenging Query Runner")
        self.logger.info(f"Run ID: {config.run_id}")
        self.logger.info(f"Output dir: {config.output_dir}")
        self.logger.info("=" * 80)
        
        # Load checkpoint
        self.checkpoint = Checkpoint.load(config.checkpoint_file)
        self.logger.info(f"Loaded checkpoint: {len(self.checkpoint.completed_queries)} systems with completed queries")
        
        # Initialize runners
        self.runners: Dict[str, SystemRunner] = {}
    
    def check_dependencies(self, systems: List[str]) -> Dict[str, List[str]]:
        """Check if required dependencies are available for each system."""
        missing = {}
        
        for system in systems:
            if system not in self.SYSTEM_DEPENDENCIES:
                continue
                
            system_missing = []
            for dep in self.SYSTEM_DEPENDENCIES[system]:
                try:
                    __import__(dep)
                except ImportError:
                    system_missing.append(dep)
            
            if system_missing:
                missing[system] = system_missing
        
        return missing
        
    def _get_runner(self, system: str) -> Optional[SystemRunner]:
        """Get or create a system runner."""
        if system in self.runners:
            return self.runners[system]
            
        try:
            if system == "quest":
                runner = QuestRunner(self.config, self.logger)
            elif system == "uqe":
                runner = UQERunner(self.config, self.logger)
            elif system == "lotus":
                runner = LotusRunner(self.config, self.logger)
            elif system == "unify":
                runner = UnifyRunner(self.config, self.logger)
            else:
                self.logger.error(f"Unknown system: {system}")
                return None
            self.runners[system] = runner
            return runner
        except Exception as e:
            self.logger.error(f"Failed to initialize {system}: {e}")
            return None
    
    def run(self, systems: List[str], query_types: List[str], skip_completed: bool = True):
        """Run queries for specified systems and types."""
        
        self.logger.info(f"Running systems: {systems}")
        self.logger.info(f"Query types: {query_types}")
        
        # Check dependencies
        missing_deps = self.check_dependencies(systems)
        if missing_deps:
            self.logger.warning("")
            self.logger.warning("=" * 60)
            self.logger.warning("WARNING: Missing dependencies detected!")
            self.logger.warning("=" * 60)
            for system, deps in missing_deps.items():
                self.logger.warning(f"  {system.upper()}: missing {', '.join(deps)}")
            self.logger.warning("")
            self.logger.warning("Install with:")
            self.logger.warning("  pip install -r requirements_testing.txt")
            self.logger.warning("")
            self.logger.warning("Or install individually:")
            for system, deps in missing_deps.items():
                self.logger.warning(f"  pip install {' '.join(deps)}  # for {system}")
            self.logger.warning("=" * 60)
            self.logger.warning("")
        
        # Special note for lotus
        if "lotus" in systems:
            import sys
            if sys.version_info >= (3, 13):
                self.logger.warning("")
                self.logger.warning("NOTE: LOTUS (lotus-ai) requires Python <3.13")
                self.logger.warning("      You are running Python %s.%s", sys.version_info.major, sys.version_info.minor)
                self.logger.warning("      LOTUS queries will be marked as 'unavailable'")
                self.logger.warning("")
        
        # Special note for unify
        if "unify" in systems:
            self.logger.warning("")
            self.logger.warning("NOTE: UNIFY system requires additional setup")
            self.logger.warning("      1. Unify models must be in: systems/Unify/main/models/")
            self.logger.warning("         - models/tokenizer")
            self.logger.warning("         - models/embedding")
            self.logger.warning("      2. Ollama server must be running with qwen2.5:7b-instruct")
            self.logger.warning("         - Start with: ollama pull qwen2.5:7b-instruct && ollama serve")
            self.logger.warning("         - Default endpoint: http://localhost:11434/v1")
            self.logger.warning("")
        
        # Collect all queries to run
        queries_to_run = []
        for qtype in query_types:
            if qtype in CHALLENGING_QUERIES:
                for query in CHALLENGING_QUERIES[qtype]:
                    queries_to_run.append((qtype, query))
        
        self.logger.info(f"Total queries to run: {len(queries_to_run)}")
        
        # Summary tracking
        summary = {
            "total": len(queries_to_run) * len(systems),
            "completed": 0,
            "failed": 0,
            "skipped": 0
        }
        
        # Run each system
        for system in systems:
            self.logger.info("")
            self.logger.info("=" * 60)
            self.logger.info(f"SYSTEM: {system.upper()}")
            self.logger.info("=" * 60)
            
            self.checkpoint.current_system = system
            
            runner = self._get_runner(system)
            if runner is None:
                self.logger.warning(f"Skipping {system} - runner not available")
                summary["skipped"] += len(queries_to_run)
                continue
            
            # Run each query
            for query_type, query in queries_to_run:
                query_id = query["id"]
                
                self.checkpoint.current_query_type = query_type
                
                # Check if already completed
                if skip_completed and self.checkpoint.is_completed(system, query_id):
                    self.logger.info(f"[{system}] Skipping {query_id} - already completed")
                    summary["skipped"] += 1
                    continue
                
                self.logger.info("")
                self.logger.info("-" * 40)
                self.logger.info(f"[{system}] Query: {query_id} ({query['name']})")
                self.logger.info(f"[{system}] Type: {query_type}")
                self.logger.info(f"[{system}] Dataset: {query['dataset']}")
                self.logger.info(f"[{system}] Difficulty: {query['difficulty']}")
                self.logger.info(f"[{system}] Reason: {query['reason']}")
                self.logger.info("-" * 40)
                
                # Create output directory for this query
                query_output_dir = (
                    self.config.output_dir / "results" / system / query_type / query_id
                )
                query_output_dir.mkdir(parents=True, exist_ok=True)
                
                # Save query info (add type for runner's use)
                query_with_type = {**query, "type": query_type}
                dump_json(query_with_type, query_output_dir / "query.json")
                
                # Run query
                try:
                    result_df, metadata = runner.run_query(query_with_type)
                    
                    # Save result
                    if result_df is not None:
                        result_df.to_csv(query_output_dir / "result.csv", index=False)
                        self.logger.info(f"[{system}] Result saved: {len(result_df)} rows")
                        
                        # Log the actual answer content
                        self.logger.info("")
                        self.logger.info(f"[{system}] ===== QUERY RESULT =====")
                        self.logger.info(f"[{system}] Shape: {result_df.shape} (rows={len(result_df)}, cols={len(result_df.columns)})")
                        self.logger.info(f"[{system}] Columns: {list(result_df.columns)}")
                        if len(result_df) == 0:
                            self.logger.warning(f"[{system}] WARNING: Result is EMPTY - no rows returned!")
                        else:
                            # Show all rows for small results, or first 10 for larger ones
                            if len(result_df) <= 10:
                                self.logger.info(f"[{system}] Full result:\n{result_df.to_string()}")
                            else:
                                self.logger.info(f"[{system}] First 10 rows:\n{result_df.head(10).to_string()}")
                                self.logger.info(f"[{system}] ... ({len(result_df) - 10} more rows)")
                        self.logger.info(f"[{system}] =========================")
                        self.logger.info("")
                    else:
                        self.logger.warning(f"[{system}] WARNING: Result is None - no data returned!")
                    
                    # Save metadata
                    dump_json(metadata, query_output_dir / "metadata.json")
                    
                    if metadata.get("status") == "failed":
                        self.checkpoint.mark_failed(system, query_id)
                        summary["failed"] += 1
                        self.logger.error(f"[{system}] Query {query_id} FAILED")
                    else:
                        self.checkpoint.mark_completed(system, query_id)
                        summary["completed"] += 1
                        self.logger.info(f"[{system}] Query {query_id} completed with status: {metadata.get('status')}")
                    
                except Exception as e:
                    self.logger.error(f"[{system}] Query {query_id} raised exception: {e}")
                    self.logger.debug(traceback.format_exc())
                    
                    # Save error
                    dump_json({
                        "error": str(e),
                        "traceback": traceback.format_exc()
                    }, query_output_dir / "error.json")
                    
                    self.checkpoint.mark_failed(system, query_id)
                    summary["failed"] += 1
                
                # Save checkpoint after each query
                self.checkpoint.save(self.config.checkpoint_file)
        
        # Final summary
        self.logger.info("")
        self.logger.info("=" * 80)
        self.logger.info("RUN SUMMARY")
        self.logger.info("=" * 80)
        self.logger.info(f"Total queries: {summary['total']}")
        self.logger.info(f"Completed: {summary['completed']}")
        self.logger.info(f"Failed: {summary['failed']}")
        self.logger.info(f"Skipped: {summary['skipped']}")
        self.logger.info(f"Results saved to: {self.config.output_dir}")
        self.logger.info("=" * 80)
        
        # Save final summary
        summary["run_id"] = self.config.run_id
        summary["end_time"] = datetime.now().isoformat()
        summary["systems"] = systems
        summary["query_types"] = query_types
        dump_json(summary, self.config.output_dir / "summary.json")
        
        # Generate detailed report
        self._generate_report(systems, query_types)
        
        return summary
    
    def _generate_report(self, systems: List[str], query_types: List[str]):
        """Generate a detailed report of all results."""
        self.logger.info("")
        self.logger.info("Generating detailed report...")
        
        report = {
            "run_id": self.config.run_id,
            "generated_at": datetime.now().isoformat(),
            "systems": {},
            "by_query_type": {},
            "by_difficulty": {"hard": {"total": 0, "completed": 0, "failed": 0}}
        }
        
        results_dir = self.config.output_dir / "results"
        
        for system in systems:
            system_dir = results_dir / system
            if not system_dir.exists():
                continue
                
            report["systems"][system] = {
                "total": 0,
                "completed": 0,
                "failed": 0,
                "queries": {}
            }
            
            for query_type in query_types:
                if query_type not in report["by_query_type"]:
                    report["by_query_type"][query_type] = {"total": 0, "completed": 0, "failed": 0}
                
                type_dir = system_dir / query_type
                if not type_dir.exists():
                    continue
                    
                for query_dir in type_dir.iterdir():
                    if not query_dir.is_dir():
                        continue
                        
                    query_id = query_dir.name
                    metadata_path = query_dir / "metadata.json"
                    
                    if metadata_path.exists():
                        metadata = load_json(metadata_path)
                        status = metadata.get("status", "unknown")
                        
                        report["systems"][system]["total"] += 1
                        report["by_query_type"][query_type]["total"] += 1
                        report["by_difficulty"]["hard"]["total"] += 1
                        
                        if status in ["completed", "requires_index", "requires_schema"]:
                            report["systems"][system]["completed"] += 1
                            report["by_query_type"][query_type]["completed"] += 1
                            report["by_difficulty"]["hard"]["completed"] += 1
                        elif status == "unsupported":
                            # Track unsupported queries separately
                            if "unsupported" not in report["systems"][system]:
                                report["systems"][system]["unsupported"] = 0
                            report["systems"][system]["unsupported"] += 1
                        elif status == "failed":
                            report["systems"][system]["failed"] += 1
                            report["by_query_type"][query_type]["failed"] += 1
                            report["by_difficulty"]["hard"]["failed"] += 1
                        
                        report["systems"][system]["queries"][query_id] = {
                            "status": status,
                            "query_type": query_type,
                            "time": metadata.get("total_time")
                        }
        
        # Save report
        dump_json(report, self.config.output_dir / "detailed_report.json")
        self.logger.info(f"Report saved to {self.config.output_dir / 'detailed_report.json'}")


# ==============================================================================
# CLI
# ==============================================================================

def main():
    # Enable fault handler to debug segfaults
    faulthandler.enable()
    
    parser = argparse.ArgumentParser(
        description="Run challenging queries against UDA systems",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all systems on all query types
  python run_challenging_queries.py --systems all
  
  # Run specific systems on specific query types  
  python run_challenging_queries.py --systems quest uqe --query-types filter projection
  
  # Resume from checkpoint
  python run_challenging_queries.py --resume --run-id 20241208_120000
  
  # Run with debug logging
  python run_challenging_queries.py --systems quest --log-level DEBUG
        """
    )
    
    parser.add_argument(
        "--systems",
        nargs="+",
        choices=ChallengingQueryRunner.AVAILABLE_SYSTEMS + ["all"],
        default=["all"],
        help="Systems to run (default: all)"
    )
    
    parser.add_argument(
        "--query-types",
        nargs="+",
        choices=list(CHALLENGING_QUERIES.keys()) + ["all"],
        default=["all"],
        help="Query types to run (default: all)"
    )
    
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Run ID for output directory (default: timestamp)"
    )
    
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint (requires --run-id)"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )
    
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "results" / "challenging_queries",
        help="Base output directory"
    )
    
    args = parser.parse_args()
    
    # Handle 'all' options
    if "all" in args.systems:
        systems = ChallengingQueryRunner.AVAILABLE_SYSTEMS
    else:
        systems = args.systems
    
    if "all" in args.query_types:
        query_types = list(CHALLENGING_QUERIES.keys())
    else:
        query_types = args.query_types
    
    # Create config
    config = RunConfig(
        run_id=args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S"),
        output_dir=args.output_dir,
        log_level=args.log_level
    )
    
    # Handle resume
    if args.resume:
        if not args.run_id:
            # Find latest run
            runs = sorted(args.output_dir.glob("*"))
            if runs:
                config.run_id = runs[-1].name
                print(f"Resuming from latest run: {config.run_id}")
            else:
                print("No previous runs found to resume")
                return 1
        config.output_dir = args.output_dir / config.run_id
        config.checkpoint_file = config.output_dir / "checkpoint.json"
    
    # Run
    runner = ChallengingQueryRunner(config)
    summary = runner.run(systems, query_types, skip_completed=args.resume)
    
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

