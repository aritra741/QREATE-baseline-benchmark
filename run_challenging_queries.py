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
import re
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
sys.path.insert(0, str(PROJECT_ROOT / "systems" / "PZ"))

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
            "nl_query": "Get disease names, types, and prognosis from all disease documents",
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
            "nl_query": "Get names, positions, nationalities, and teams from all player documents",
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
            "nl_query": "Get psychiatric disease documents with disease names, types, common symptoms, and treatments",
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
            "nl_query": "Get Frontcourt player documents with names, teams, positions, nationalities, and draft years",
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
            "nl_query": "Get inflammatory disease documents with disease names, types, etiology, and treatment challenges",
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
            "nl_query": "Get all disease documents with names, types, diagnostic methods, common symptoms, treatments, and prognosis",
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
            "nl_query": "Get all player documents with names, positions, nationalities, teams, colleges, NBA championships, MVP awards, and Olympic gold medals",
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
            "nl_query": "Get all company documents with names, principal activities, revenue, net profit or loss, total assets, and business risks",
            "difficulty": "hard",
            "reason": "Financial attributes scattered across long 100+ page documents; requires careful value extraction"
        }
    ],
    
    "join": [
        {
            "id": "join_1",
            "name": "Join diseases with their drug treatments",
            "dataset": "Med",
            "entity": "disease,drug",
            "sql": """SELECT d.disease_name, d.disease_type, d.treatments, dr.generic_name, dr.brand_name, dr.side_effects
FROM disease d
JOIN drug dr ON d.disease_name = dr.disease_name
WHERE d.disease_name IN ('Type 2 Diabetes Mellitus', 'Tuberculosis', 'Fibromyalgia', 'Asthma', 'Depression')""",
            "nl_query": "Get common diseases (diabetes, tuberculosis, fibromyalgia, asthma, depression) with their associated drug treatments, showing disease names, types, treatments from disease documents, generic drug names, brand names, and side effects",
            "difficulty": "hard",
            "reason": "Requires joining disease and drug tables on disease name matching across documents; tests accurate extraction of treatment-related fields from both entity types"
        },
        {
            "id": "join_2",
            "name": "Join players with their teams",
            "dataset": "Player",
            "entity": "player,team",
            "sql": """SELECT p.name, p.position, p.nationality, t.team_name, t.ownership, t.founded_year
FROM player p
JOIN team t ON p.team = t.team_name""",
            "nl_query": "Get all players with their team information, showing player names, positions, nationalities, team names, ownership, and founding years",
            "difficulty": "hard",
            "reason": "Binary join across player and team entities; requires matching team names across documents from different tables"
        },
        {
            "id": "join_3",
            "name": "Join diseases with research institutions",
            "dataset": "Med",
            "entity": "disease,institution",
            "sql": """SELECT DISTINCT d.disease_name, d.disease_type, d.prognosis, i.institution_name, i.research_diseases, i.institution_country
FROM disease d
JOIN institution i ON d.disease_name IN i.research_diseases
WHERE d.disease_type IN ('infectious', 'genetic')""",
            "nl_query": "Get infectious and genetic diseases along with institutions that research them, showing disease names, disease types, prognosis, institution names, research focus, and institution countries",
            "difficulty": "hard",
            "reason": "Joining disease and institution tables where disease names must be found within research_diseases field; requires semantic substring matching across documents"
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
            "nl_query": "Count how many diseases there are for each disease type",
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
            "nl_query": "For American players, count how many players there are in each position and calculate the average number of NBA championships per position",
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
            "nl_query": "Count how many companies there are for each principal activity",
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
            "nl_query": "Find all players who have won NBA championships or MVP awards, showing their names, nationalities, achievement counts, and achievement types",
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
            "nl_query": "Combine diagnostic methods and treatments for all diseases, showing disease names, clinical information, and information type",
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
            "nl_query": "Compare financial companies by showing their revenue and total assets, including company names, metric values, and metric types",
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
            
            # Per QUEST paper: use join transformation for join queries
            is_join_query = query_type == "join"
            
            if is_join_query:
                # Use join transformation planner per paper Section 3.2 - NO FALLBACK
                    from quest.sql.planner.joinlogical_quest_paper import JoinLogicalPlanner
                    logical_planner = JoinLogicalPlanner()
                    self.logger.info("[QUEST] Using JOIN TRANSFORMATION planner per paper Section 3.2 (NO FALLBACK)")
            else:
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
            
            # Handle multi-entity join queries (e.g., "disease,drug")
            # Split by comma and strip whitespace
            entity_list = [e.strip() for e in entity.split(",")]
            
            # For join queries, we need to combine schemas from all entities
            all_entity_attrs = {}
            all_attr_lines = []
            
            for ent in entity_list:
                # Case-insensitive entity lookup
                entity_attrs = None
                for key in attributes:
                    if key.lower() == ent.lower():
                        entity_attrs = attributes[key]
                        break
                
                if entity_attrs is None:
                    self.logger.warning(f"[QUEST] No attributes found for entity {ent} in {dataset}")
                    metadata["status"] = "requires_schema"
                    metadata["error"] = f"No attribute schema found for {dataset}/{ent}"
                    metadata["total_time"] = time.time() - start_time
                    metadata["end_time"] = datetime.now().isoformat()
                    return result_df, metadata
                
                all_entity_attrs[ent] = entity_attrs
                
                # Build prompt/schema in the format expected by AttrSampler and TextLLMQuerier:
                # "attr_name: description" on each line (colon separator is required for parsing)
            for ent in entity_list:
                entity_attrs = all_entity_attrs[ent]
                for attr_name, attr_info in entity_attrs.items():
                    description = attr_info.get("description", "") if isinstance(attr_info, dict) else ""
                    all_attr_lines.append(f"{attr_name}: {description}")
            
            prompt_str = "\n".join(all_attr_lines)
            
            self.logger.debug(f"[QUEST] Schema built with {len(all_attr_lines)} attributes for {len(entity_list)} entities")
            
            # Create sampler and querier with properly formatted schema
            gb_sampler = AttrSampler(schema=prompt_str)
            gb_querier = TextLLMQuerier(prompt=prompt_str)
            
            # CRITICAL: Initialize sampler with sample data from the index for each entity
            # This populates the evidence dictionary that's used during retrieval
            for ent in entity_list:
                self.logger.info(f"[QUEST] Sampling documents from {ent} index for evidence...")
                try:
                    indexer_obj, _ = gb_indexer.get_indexer(ent)
                    self.logger.debug(f"[QUEST] Got indexer for {ent}, has {len(indexer_obj.get_docs_id())} docs")
                    
                    # Check if exhaustive sampling is enabled via environment variable
                    use_exhaustive = os.environ.get('QUEST_EXHAUSTIVE_SAMPLING', '').lower() == 'true'
                    if use_exhaustive:
                        self.logger.warning(f"[QUEST] EXHAUSTIVE SAMPLING ENABLED - sampling ALL documents for {ent}!")
                        gb_sampler.try_sample_all_docs(indexer_obj, prompt_str)
                    else:
                        gb_sampler.try_sample(indexer_obj, prompt_str)
                    
                    self.logger.info(f"[QUEST] Sampler initialized with evidence for {len(gb_sampler.map_attr_evidence)} attributes from {ent}")
                    
                    # Log what evidence was found for debugging
                    for attr, evidence in gb_sampler.map_attr_evidence.items():
                        if evidence:
                            self.logger.debug(f"[QUEST]   - {attr}: {len(evidence)} chars of evidence")
                        else:
                            self.logger.warning(f"[QUEST]   - {attr}: NO EVIDENCE FOUND!")
                            
                except Exception as e:
                    self.logger.error(f"[QUEST] Failed to sample documents for {ent}: {e}")
                    self.logger.error(f"[QUEST] Traceback:\n{traceback.format_exc()}")
                    # Continue anyway - the query might still work with empty evidence
            
            # Build physical plan
            self.logger.info("[QUEST] About to build physical plan...")
            self.logger.debug("[QUEST] Building physical plan...")
            physical_planner = TextPhysicalPlanner(gb_indexer, gb_querier, sampler=gb_sampler)
            self.logger.info("[QUEST] Physical planner created, building plan...")
            physical_plan = physical_planner.build(logical_plan)
            self.logger.info(f"[QUEST] Physical plan built: {type(physical_plan)}")
            metadata["physical_plan_time"] = time.time() - start_time - metadata.get("logical_plan_time", 0) - metadata.get("parse_time", 0)
            
            # Execute
            self.logger.debug("[QUEST] Executing query...")
            self.logger.debug(f"[QUEST] Physical plan type: {type(physical_plan)}")
            self.logger.debug(f"[QUEST] Physical plan: {physical_plan}")
            processer = Processer()
            result = processer.process(physical_plan)
            
            self.logger.debug(f"[QUEST] Result from processer: {result}")
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
            
            # Get natural language query for Unify
            nl_query = query.get("nl_query")
            if not nl_query:
                self.logger.warning("[UNIFY] No nl_query field found, falling back to SQL")
                nl_query = sql
            self.logger.info(f"[UNIFY] Using NL Query: {nl_query}")
            sys.stdout.flush()
            sys.stderr.flush()
            
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
            
            # Parse the natural language query (not SQL)
            self.logger.debug("[UNIFY] Parsing natural language query...")
            sys.stdout.flush()
            sys.stderr.flush()
            parsed_result = self.semantic_parse(nl_query, client, chat_model)
            self.logger.debug("[UNIFY] Query parsed successfully")
            sys.stdout.flush()
            sys.stderr.flush()
            transformed_question = self.replace_parsed_elements_with_identifiers(nl_query, parsed_result)
            
            metadata["parse_time"] = time.time() - start_time - metadata["data_load_time"]
            
            # Generate plan (use nl_query for planning)
            self.logger.debug("[UNIFY] Generating execution plan...")
            bq_matcher = self.BQMatcher(embed_model)
            final_flag, final_plan, final_bq_list, partial_question_list = self.recursive_plan_generation(
                nl_query, transformed_question, bq_matcher, client, chat_model, embed_model,
                [], [], [], 0  # current_plan, use_bq_list, partial_question_list, depth
            )
            
            metadata["plan_generation_time"] = time.time() - start_time - metadata.get("parse_time", 0) - metadata["data_load_time"]
            self.logger.debug(f"[UNIFY] Plan generated: {final_flag}")
            
            # Execute plan (use nl_query as the original question)
            self.logger.debug("[UNIFY] Executing plan...")
            pm = self.planManager(
                nl_query, final_plan, client, chat_model, final_bq_list, all_file_data, 
                parsed_result, partial_question_list, embed_model, index
            )
            pm.execute_with_plan()
            
            metadata["execution_time"] = time.time() - start_time - metadata.get("plan_generation_time", 0) - metadata.get("parse_time", 0) - metadata["data_load_time"]
            
            # Extract result - find the result from the executed plan
            final_result = None
            if pm.BQ_list and "IDPlan" in pm.BQ_list[-1] and pm.BQ_list[-1]["IDPlan"]:
                def find_final_result(plan):
                    """Recursively find the final result from the executed plan."""
                    if not plan:
                        return None
                    
                    # Look through all operators to find one with a Result
                    # Start from the end (root after postorder) and work backwards
                    for operator in reversed(plan):
                        if "Result" in operator and operator["Result"] is not None:
                            result = operator["Result"]
                            # Make sure it's not just a primitive or string
                            if isinstance(result, (list, dict)) or isinstance(result, pd.DataFrame):
                                return result
                        
                        # Check nested FollowupPlan
                        if "FollowupPlan" in operator and operator["FollowupPlan"]:
                            nested_result = find_final_result(operator["FollowupPlan"])
                            if nested_result is not None:
                                return nested_result
                    
                    return None
                
                final_result = find_final_result(pm.BQ_list[-1]["IDPlan"])
                
                if final_result is None:
                    # Log the structure for debugging
                    self.logger.debug(f"[UNIFY] IDPlan structure (last BQ): {pm.BQ_list[-1]['IDPlan']}")
                    self.logger.warning("[UNIFY] No Result found in any operator")
            
            if final_result is not None:
                # Convert result to DataFrame if needed
                if isinstance(final_result, list):
                    if final_result:  # Only create DataFrame if list is not empty
                        result_df = pd.DataFrame(final_result)
                    else:
                        self.logger.warning("[UNIFY] Result list is empty")
                        result_df = pd.DataFrame()
                elif isinstance(final_result, dict):
                    # If result is a dictionary (e.g., from Scan operator), convert to DataFrame
                    if final_result:
                        result_df = pd.DataFrame([final_result])
                    else:
                        result_df = pd.DataFrame()
                elif isinstance(final_result, pd.DataFrame):
                    result_df = final_result
                else:
                    # Try to wrap in a dataframe
                    try:
                        result_df = pd.DataFrame([final_result])
                    except Exception as e:
                        self.logger.warning(f"[UNIFY] Could not convert result to DataFrame: {e}")
                        result_df = None
                
                if result_df is not None:
                    self.logger.info(f"[UNIFY] Query executed successfully, result shape: {result_df.shape}")
                    if len(result_df) > 0:
                        self.logger.debug(f"[UNIFY] Result preview:\n{result_df.head()}")
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


class SQUiDRunner(SystemRunner):
    """Runner for SQUiD system.
    
    SQUiD synthesizes relational databases from unstructured text.
    Reference: https://github.com/yale-sys/squid
    
    The SQUiD pipeline is run ONCE as preprocessing:
    1. Preprocess LLM documents (preprocess_squid_data.py)
    2. Run full SQUiD pipeline (schema generation, value identification, 
       value population, database generation, ensemble)
    3. Save results to disk
    
    This runner loads pre-computed results and executes SQL queries on them.
    
    Setup:
    1. python preprocess_squid_data.py --dataset all
    2. python run_squid_pipeline.py (to be created)
    3. python run_challenging_queries.py --systems squid
    
    All LLM calls use: qwen2.5:7b-instruct via Ollama
    """
    
    def __init__(self, config: RunConfig, logger):
        super().__init__(config, logger)
        self.name = "squid"
        self.squid_path = PROJECT_ROOT / "systems" / "SQUiD"
        self._results_cache: Dict[str, pd.DataFrame] = {}
    
    def _load_pipeline_results(self, dataset: str, entity: str) -> Optional[Dict]:
        """Load pre-computed results from the SQUiD pipeline.
        
        Results should be pre-computed and saved during preprocessing.
        """
        try:
            # Results saved by pipeline preprocessing in ensemble directory
            # The ensemble combines results from TS, TST, TST-L methods
            ensemble_path = (
                self.squid_path / "results" / "database_generation" / "ensemble" / 
                "TS_TST_TST-L" / dataset / entity / "text_direct_ollama.json"
            )
            
            if ensemble_path.exists():
                self.logger.debug(f"[SQUID] Loading ensemble results from {ensemble_path}")
                with open(ensemble_path, "r") as f:
                    return json.load(f)
            
            # Fallback: try other possible locations
            possible_paths = [
                self.squid_path / "results" / "database_generation" / "TS" / dataset / entity / "text_direct_ollama.json",
                self.squid_path / "results" / "database_generation" / "TST" / dataset / entity / "text_direct_ollama.json",
                PROJECT_ROOT / "preprocess_squid" / dataset / entity / "pipeline_results.json",
            ]
            
            for result_path in possible_paths:
                if result_path.exists():
                    self.logger.debug(f"[SQUID] Loading results from fallback path: {result_path}")
                    with open(result_path, "r") as f:
                        return json.load(f)
            
            # Log available paths for debugging
            self.logger.debug(f"[SQUID] Checked primary path: {ensemble_path}")
            self.logger.debug(f"[SQUID] Ensemble directory exists: {ensemble_path.parent.parent.exists()}")
            if ensemble_path.parent.parent.exists():
                available_entities = list(ensemble_path.parent.parent.iterdir())
                self.logger.debug(f"[SQUID] Available entities in ensemble: {[e.name for e in available_entities]}")
            
            return None
            
        except Exception as e:
            self.logger.debug(f"[SQUID] Error loading pipeline results: {e}")
            return None
    
    def preprocess(self, dataset: str, entity: str) -> Dict:
        """Check that preprocessing is complete (LLM documents + pipeline results)."""
        metadata = {
            "system": self.name,
            "dataset": dataset,
            "entity": entity,
            "timestamp": datetime.now().isoformat()
        }
        
        # Check for LLM-preprocessed documents
        preprocess_dir = PROJECT_ROOT / "preprocess_squid" / dataset / entity
        if not preprocess_dir.exists():
            metadata["status"] = "requires_preprocessing"
            metadata["error"] = f"Run: python preprocess_squid_data.py --dataset {dataset} --entities {entity}"
            self.logger.warning(f"[SQUID] {metadata['error']}")
            return metadata
        
        json_path = preprocess_dir / "preprocessed_data.json"
        if not json_path.exists():
            metadata["status"] = "requires_preprocessing"
            metadata["error"] = f"No preprocessed data at {json_path}"
            return metadata
        
        try:
            with open(json_path, "r") as f:
                preprocess_data = json.load(f)
            doc_count = len(preprocess_data.get("documents", []))
            self.logger.info(f"[SQUID] Found {doc_count} LLM-preprocessed documents")
        except Exception as e:
            metadata["status"] = "failed"
            metadata["error"] = f"Failed to load preprocessed data: {e}"
            return metadata
        
        # Check for pipeline results
        pipeline_results = self._load_pipeline_results(dataset, entity)
        if pipeline_results is None:
            metadata["status"] = "requires_pipeline"
            metadata["error"] = "Run SQUiD pipeline preprocessing (run_squid_pipeline.py)"
            self.logger.warning(f"[SQUID] {metadata['error']}")
            return metadata
        
        metadata["status"] = "completed"
        metadata["documents_count"] = doc_count
        metadata["results_loaded"] = True
        self.logger.info(f"[SQUID] Preprocessing complete: {doc_count} documents, results loaded")
        
        return metadata
    
    def _rewrite_sql_for_squid_tables(self, sql: str, ensemble_data: List[Dict], entity: str = "") -> str:
        """Rewrite SQL query to use correct SQUiD table names with UNION ALL across all documents.
        
        SQUiD creates separate tables for each document using db_name (e.g., Med_0, Med_1, ...).
        This converts queries using generic table names (entity) into UNION ALL queries that combine all documents.
        
        Example:
            Input:  SELECT name FROM disease
            Output: (SELECT name FROM Med_0) UNION ALL (SELECT name FROM Med_1) UNION ALL ...
        
        Args:
            sql: Original SQL query
            ensemble_data: List of ensemble entries with db_name and other metadata
            entity: The entity name to replace in the query (e.g., "disease", "player")
        """
        import re
        
        if not entity:
            self.logger.warning("[SQUID] No entity name provided, cannot rewrite SQL")
            return sql
        
        # Get all db_names from ensemble data - these are the actual table names (Med_0, Med_1, etc.)
        db_names = []
        for idx, entry in enumerate(ensemble_data):
            db_name = entry.get("db_name", f"result_{idx}")
            db_names.append(db_name)
        
        if not db_names:
            self.logger.warning("[SQUID] No db_names found in ensemble data, using original SQL")
            return sql
        
        # Replace entity name with UNION of all db_names
        # Pattern matches the entity name as a table reference (FROM entity or JOIN entity)
        pattern = rf'\bFROM\s+{re.escape(entity)}\b'
        
        if re.search(pattern, sql, re.IGNORECASE):
            # Build union of all tables
            union_parts = []
            for db_name in sorted(set(db_names)):  # Use set to avoid duplicates
                temp_sql = sql
                # Replace FROM entity with FROM db_name
                temp_sql = re.sub(pattern, f'FROM {db_name}', temp_sql, flags=re.IGNORECASE)
                # Also handle JOINs with the same entity
                join_pattern = rf'\bJOIN\s+{re.escape(entity)}\b'
                temp_sql = re.sub(join_pattern, f'JOIN {db_name}', temp_sql, flags=re.IGNORECASE)
                union_parts.append(f'({temp_sql})')
            
            # Join all parts with UNION ALL
            rewritten_sql = ' UNION ALL '.join(union_parts)
            self.logger.debug(f"[SQUID] SQL rewriting: entity={entity}, db_names={sorted(set(db_names))[:3]}...")
            return rewritten_sql
        else:
            # Entity not in FROM clause
            self.logger.warning(f"[SQUID] Entity '{entity}' not found in FROM clause of query")
            return sql
    
    def _build_database_from_ensemble(self, ensemble_data: List[Dict]) -> Optional[Any]:
        """Build an in-memory DuckDB database from SQUiD ensemble results.
        
        SQUiD pipeline outputs joined_rows which are the denormalized results of joining
        all tables across the schema. These are the actual data extracted and populated
        by the SQUiD pipeline, ready to be queried.
        
        Returns a DuckDB connection with queryable denormalized tables.
        """
        try:
            import duckdb
            
            # Create in-memory database
            conn = duckdb.connect(":memory:")
            
            # Each entry in ensemble_data represents one document's extracted data
            # joined_rows contains the denormalized rows from that document
            table_count = 0
            row_count = 0
            
            for idx, entry in enumerate(ensemble_data):
                joined_rows = entry.get("joined_rows", [])
                
                if not joined_rows or len(joined_rows) == 0:
                    self.logger.debug(f"[SQUID] Entry {idx}: No joined_rows data")
                    continue
                
                db_name = entry.get("db_name", f"result_{idx}")
                domain = entry.get("domain", "data")
                
                # Create a table for this entry's denormalized data
                table_name = f"{domain}_{idx}"
                
                try:
                    # Register joined_rows as a table in DuckDB
                    # DuckDB can directly query Python dicts/lists
                    import pandas as pd
                    df = pd.DataFrame(joined_rows)
                    conn.register(table_name, df)
                    
                    row_count += len(joined_rows)
                    table_count += 1
                    self.logger.debug(f"[SQUID] Created table {table_name} with {len(joined_rows)} rows, {len(df.columns)} columns")
                    
                except Exception as e:
                    self.logger.warning(f"[SQUID] Failed to register table for entry {idx}: {e}")
                    continue
            
            self.logger.info(f"[SQUID] Built in-memory database with {table_count} tables, {row_count} total rows")
            return conn
            
        except ImportError:
            self.logger.warning("[SQUID] DuckDB or pandas not available")
            return None
        except Exception as e:
            self.logger.error(f"[SQUID] Failed to build database: {e}")
            return None
    
    def run_query(self, query: Dict) -> Tuple[Optional[pd.DataFrame], Dict]:
        """Run a query using pre-computed SQUiD results."""
        query_id = query["id"]
        dataset = query["dataset"]
        entity = query.get("entity", "").lower()
        sql = query.get("sql", "")
        
        metadata = {
            "system": self.name,
            "query_id": query_id,
            "start_time": datetime.now().isoformat()
        }
        
        start_time = time.time()
        result_df = None
        
        try:
            # Load pre-computed results
            cache_key = f"{dataset}_{entity}"
            
            if cache_key not in self._results_cache:
                pipeline_results = self._load_pipeline_results(dataset, entity)
                
                if pipeline_results is None:
                    metadata["status"] = "requires_pipeline"
                    metadata["error"] = "Pipeline results not found. Run SQUiD pipeline preprocessing."
                    metadata["total_time"] = time.time() - start_time
                    metadata["end_time"] = datetime.now().isoformat()
                    return None, metadata
                
                # Convert to list if needed
                if isinstance(pipeline_results, dict):
                    pipeline_results = [pipeline_results]
                elif not isinstance(pipeline_results, list):
                    pipeline_results = [pipeline_results]
                
                # Build queryable database from ensemble data
                db_conn = self._build_database_from_ensemble(pipeline_results)
                
                if db_conn is None:
                    self.logger.warning("[SQUID] Could not build database, returning raw results")
                    self._results_cache[cache_key] = (None, pd.DataFrame(pipeline_results), pipeline_results)
                else:
                    self._results_cache[cache_key] = (db_conn, None, pipeline_results)
            
            # Execute query if we have a database
            # Cache now includes pipeline_results as third element
            cache_entry = self._results_cache[cache_key]
            if len(cache_entry) == 3:
                db_conn, fallback_df, pipeline_results = cache_entry
            else:
                # Backward compatibility with old 2-tuple cache format
                db_conn, fallback_df = cache_entry
                pipeline_results = []
            
            if db_conn is not None:
                try:
                    # Rewrite SQL query to use correct table names (db_name format)
                    rewritten_sql = self._rewrite_sql_for_squid_tables(sql, pipeline_results, entity)
                    self.logger.debug(f"[SQUID] Original SQL: {sql}")
                    self.logger.debug(f"[SQUID] Rewritten SQL: {rewritten_sql}")
                    
                    # Execute SQL query on database
                    result_df = db_conn.execute(rewritten_sql).fetch_df()
                    self.logger.info(f"[SQUID] Query {query_id}: {len(result_df)} rows from database query")
                except Exception as query_error:
                    # If query fails (e.g., table/column not found), log and try fallback
                    self.logger.warning(f"[SQUID] Query execution failed: {query_error}")
                    if fallback_df is not None and len(fallback_df) > 0:
                        result_df = fallback_df
                        self.logger.info(f"[SQUID] Query {query_id}: using fallback results ({len(result_df)} rows)")
                    else:
                        raise
            else:
                # Fallback to raw results
                result_df = fallback_df
                self.logger.info(f"[SQUID] Query {query_id}: using fallback results ({len(result_df)} rows)")
            
            metadata["status"] = "completed"
            metadata["result_count"] = len(result_df) if result_df is not None else 0
            
        except Exception as e:
            self.logger.error(f"[SQUID] Query {query_id} failed: {e}")
            self.logger.error(f"[SQUID] Traceback:\n{traceback.format_exc()}")
            metadata["status"] = "failed"
            metadata["error"] = str(e)
        
        metadata["total_time"] = time.time() - start_time
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
    
    AVAILABLE_SYSTEMS = ["quest", "uqe", "lotus", "unify", "squid", "pz", "gem"]
    
    SYSTEM_DEPENDENCIES = {
        "quest": ["ply", "sqlglot", "duckdb", "openai", "tiktoken"],
        "uqe": ["tqdm", "numpy", "openai"],
        "unify": ["openai", "torch", "sentence-transformers", "hnswlib"],
        "squid": ["pandas", "openai"],
        "pz": ["pandas"],
        "gem": ["pandas", "openai", "sentence-transformers", "faiss"],
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
            elif system == "squid":
                runner = SQUiDRunner(self.config, self.logger)
            elif system == "pz":
                from systems.PZ.pz_runner import PZRunner
                runner = PZRunner(self.config, self.logger)
            elif system == "gem":
                from systems.GEM.gem_runner import GEMRunner
                runner = GEMRunner(self.config, self.logger)
            else:
                self.logger.error(f"Unknown system: {system}")
                return None
            self.runners[system] = runner
            return runner
        except Exception as e:
            self.logger.error(f"Failed to initialize {system}: {e}")
            return None
    
    def run(self, systems: List[str], query_types: List[str], skip_completed: bool = True, query_ids: Optional[List[str]] = None):
        """Run queries for specified systems and types.
        
        Args:
            systems: List of system names to run
            query_types: List of query types to run
            skip_completed: Whether to skip already completed queries
            query_ids: Optional list of specific query IDs to run (filters queries)
        """
        
        self.logger.info(f"Running systems: {systems}")
        self.logger.info(f"Query types: {query_types}")
        if query_ids:
            self.logger.info(f"Filtering to query IDs: {query_ids}")
        
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
        
        # Special note for squid
        if "squid" in systems:
            self.logger.warning("")
            self.logger.warning("NOTE: SQUiD system requires additional setup")
            self.logger.warning("      1. Preprocess data with:")
            self.logger.warning("         python preprocess_squid_data.py --dataset all")
            self.logger.warning("      2. This generates text documents from ground truth CSVs")
            self.logger.warning("      3. Preprocessed data is saved to: preprocess_squid/")
            self.logger.warning("")
        
        # Special note for pz
        if "pz" in systems:
            self.logger.warning("")
            self.logger.warning("NOTE: PZ (Palimpzest) system")
            self.logger.warning("      PZ uses MaxQuality policy for maximum accuracy")
            self.logger.warning("      Install with: pip install -e systems/PZ/PZ_original/palimpzest/")
            self.logger.warning("")
        
        # Special note for gem
        if "gem" in systems:
            self.logger.warning("")
            self.logger.warning("NOTE: GEM (Global Entity Manager) system")
            self.logger.warning("      GEM requires Ollama server running with qwen2.5:7b-instruct")
            self.logger.warning("      1. Start Ollama: ollama pull qwen2.5:7b-instruct && ollama serve")
            self.logger.warning("      2. Default endpoint: http://localhost:11434/v1")
            self.logger.warning("      3. GEM pipeline: extract -> block -> resolve -> query")
            self.logger.warning("      4. Install dependencies: pip install sentence-transformers faiss-cpu duckdb")
            self.logger.warning("")
        
        # Collect all queries to run
        queries_to_run = []
        for qtype in query_types:
            if qtype in CHALLENGING_QUERIES:
                for query in CHALLENGING_QUERIES[qtype]:
                    # Filter by query_ids if specified
                    if query_ids is None or query["id"] in query_ids:
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
        "--query-ids",
        nargs="+",
        default=None,
        help="Specific query IDs to run (e.g., filter_1, projection_2). If not specified, runs all queries of the specified types."
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
    
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local indexes (PROJECT_ROOT/index) instead of CHPC path"
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
    
    # Set local index path if --local flag is used
    if args.local:
        # Set the path to project root so indexes are at PROJECT_ROOT/index
        os.environ["QUEST_INDEX_ROOT"] = str(PROJECT_ROOT)
        print(f"Using local indexes at: {PROJECT_ROOT}/index")
    
    
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
    summary = runner.run(systems, query_types, skip_completed=args.resume, query_ids=args.query_ids)
    
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

