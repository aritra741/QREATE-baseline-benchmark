"""
GEM Runner - System Integration

Implements the SystemRunner interface for integration with run_challenging_queries.py.
Orchestrates the full GEM pipeline: schema -> extraction -> blocking -> resolution -> storage -> query.
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

try:
    import pandas as pd
except ImportError:
    pd = None

from .config import (
    PROJECT_ROOT, CACHE_DIR, SOURCE_DATA_DIR,
    LOG_LEVEL, LOG_DIR
)
from .schema_loader import SchemaLoader, Schema
from .extractor import Extractor
from .blocking import SemanticBlocker
from .resolver import EntityResolver
from .db_engine import DBEngine


# Setup logger for this module
_log_file = LOG_DIR / "gem_runner.log"
_logger = logging.getLogger("GEM")
_logger.setLevel(LOG_LEVEL)

if not _logger.handlers:
    handler = logging.FileHandler(_log_file)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    _logger.addHandler(handler)
    
    # Also add console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    _logger.addHandler(console_handler)


# Map of dataset/entity to source data directory
DATA_PATH_MAP = {
    ("Med", "disease"): SOURCE_DATA_DIR / "Healthcare" / "disease_small",
    ("Med", "drug"): SOURCE_DATA_DIR / "Healthcare" / "drug_small",
    ("Med", "institution"): SOURCE_DATA_DIR / "Healthcare" / "institutes_small",
    ("Player", "player"): SOURCE_DATA_DIR / "Player" / "player",
    ("Player", "team"): SOURCE_DATA_DIR / "Player" / "team",
    ("Player", "manager"): SOURCE_DATA_DIR / "Player" / "owner",  # Note: actual directory is 'owner', not 'manager'
    ("Player", "city"): SOURCE_DATA_DIR / "Player" / "city",
    ("Art", "art"): SOURCE_DATA_DIR / "Art" / "wikiart",
    ("Legal", "legal_case"): SOURCE_DATA_DIR / "Legal" / "legal_case",
    ("Finan", "finance"): SOURCE_DATA_DIR / "Finance" / "finance",
    ("Synthetic", "product"): PROJECT_ROOT / "test_data" / "synthetic",  # Test dataset
}

# Map of dataset to attributes file
ATTRIBUTES_PATH_MAP = {
    "Med": PROJECT_ROOT / "Query" / "Med" / "Med_attributes.json",
    "Player": PROJECT_ROOT / "Query" / "Player" / "Player_attributes.json",
    "Art": PROJECT_ROOT / "Query" / "Art" / "Art_attributes.json",
    "Legal": PROJECT_ROOT / "Query" / "Legal" / "Legal_attributes.json",
    "Finan": PROJECT_ROOT / "Query" / "Finan" / "Finan_attributes.json",
    "Synthetic": PROJECT_ROOT / "Query" / "Synthetic" / "Synthetic_attributes.json",  # Test dataset
}


class GEMRunner:
    """GEM system runner - integrates all modules for UDA."""
    
    def __init__(self, config=None, logger=None):
        """Initialize GEM runner.
        
        Args:
            config: RunConfig object (unused but required by interface)
            logger: Logger instance (uses module logger if not provided)
        """
        self.config = config
        self.logger = logger or _logger
        self.name = "gem"
        self.schema_loader = SchemaLoader()
        self._data_cache: Dict[str, pd.DataFrame] = {}
        self._preprocessing_cache: Dict[str, Dict] = {}
    
    def _get_data_path(self, dataset: str, entity: str) -> Optional[Path]:
        """Get source data directory for dataset/entity.
        
        Args:
            dataset: Dataset name
            entity: Entity name
            
        Returns:
            Path to data directory or None
        """
        key = (dataset, entity.lower())
        if key in DATA_PATH_MAP:
            path = DATA_PATH_MAP[key]
            if path.exists():
                return path
            else:
                self.logger.warning(f"Data path not found: {path}")
        
        return None
    
    def _get_attributes_path(self, dataset: str) -> Optional[Path]:
        """Get schema attributes file for dataset.
        
        Args:
            dataset: Dataset name
            
        Returns:
            Path to attributes JSON file or None
        """
        if dataset in ATTRIBUTES_PATH_MAP:
            path = ATTRIBUTES_PATH_MAP[dataset]
            if path.exists():
                return path
            else:
                self.logger.warning(f"Attributes file not found: {path}")
        
        return None
    
    def _load_schema(self, dataset: str, entity: str) -> Optional[Schema]:
        """Load schema for dataset/entity.
        
        Args:
            dataset: Dataset name
            entity: Entity name
            
        Returns:
            Schema object or None
        """
        attr_path = self._get_attributes_path(dataset)
        if not attr_path:
            return None
        
        try:
            schema_data = json.load(open(attr_path))
            
            # UDA-Bench format: {"entity_name": {"attr": {"value_type": ..., "description": ...}}}
            # or {"entity_name": "name", "attributes": {...}}
            
            if isinstance(schema_data, dict):
                # Check if it's already in correct format
                if "attributes" in schema_data and "entity_name" in schema_data:
                    # Already correct format
                    pass
                elif entity.lower() in schema_data:
                    # UDA-Bench nested by entity
                    entity_attrs = schema_data[entity.lower()]
                    schema_data = {"entity_name": entity, "attributes": entity_attrs}
                elif "entities" in schema_data and entity.lower() in schema_data["entities"]:
                    # Schema nested under "entities"
                    schema_data = {
                        "entity_name": entity,
                        "attributes": schema_data["entities"][entity.lower()]
                    }
                else:
                    # Try to find the entity by looking for the first matching key
                    for key in schema_data.keys():
                        if key.lower() == entity.lower() and isinstance(schema_data[key], dict):
                            entity_attrs = schema_data[key]
                            schema_data = {"entity_name": entity, "attributes": entity_attrs}
                            break
            
            schema_data["entity_name"] = entity
            return self.schema_loader._parse_schema(schema_data)
        except Exception as e:
            self.logger.error(f"Failed to load schema for {dataset}/{entity}: {e}")
            return None
    
    def _get_preprocessing_cache_path(self, dataset: str, entity: str) -> Path:
        """Get preprocessing cache directory.
        
        Args:
            dataset: Dataset name
            entity: Entity name
            
        Returns:
            Cache directory path
        """
        return CACHE_DIR / "preprocessing" / dataset / entity
    
    def _save_preprocessing_results(self, dataset: str, entity: str, data: Dict):
        """Save preprocessing results to cache.
        
        Args:
            dataset: Dataset name
            entity: Entity name
            data: Data to cache
        """
        cache_dir = self._get_preprocessing_cache_path(dataset, entity)
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Save canonical map
        if "canonical_map" in data:
            canon_path = cache_dir / "canonical_map.json"
            with open(canon_path, "w") as f:
                json.dump(data["canonical_map"], f, indent=2)
        
        # Save normalized records
        if "normalized_records" in data:
            records_path = cache_dir / "normalized_records.json"
            with open(records_path, "w") as f:
                json.dump(data["normalized_records"], f, indent=2)
        
        # Save metadata
        metadata_path = cache_dir / "metadata.json"
        metadata = {
            "dataset": dataset,
            "entity": entity,
            "timestamp": datetime.now().isoformat(),
            "records_count": len(data.get("normalized_records", [])),
            "canonical_count": len(data.get("canonical_map", {}))
        }
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
    
    def _load_preprocessing_results(self, dataset: str, entity: str) -> Optional[Dict]:
        """Load preprocessing results from cache.
        
        Args:
            dataset: Dataset name
            entity: Entity name
            
        Returns:
            Preprocessed data or None
        """
        cache_dir = self._get_preprocessing_cache_path(dataset, entity)
        
        canon_path = cache_dir / "canonical_map.json"
        records_path = cache_dir / "normalized_records.json"
        
        if not canon_path.exists() or not records_path.exists():
            return None
        
        try:
            with open(canon_path, "r") as f:
                canonical_map = json.load(f)
            with open(records_path, "r") as f:
                normalized_records = json.load(f)
            
            return {
                "canonical_map": canonical_map,
                "normalized_records": normalized_records
            }
        except Exception as e:
            self.logger.warning(f"Failed to load preprocessing cache: {e}")
            return None
    
    def preprocess(self, dataset: str, entity: str) -> Dict:
        """Preprocess dataset/entity through full GEM pipeline.
        
        Args:
            dataset: Dataset name
            entity: Entity name
            
        Returns:
            Metadata dictionary
        """
        self.logger.info(f"[GEM] Preprocessing {dataset}/{entity}...")
        
        metadata = {
            "system": self.name,
            "dataset": dataset,
            "entity": entity,
            "timestamp": datetime.now().isoformat(),
            "status": "pending"
        }
        
        try:
            # Check for cached results
            cached = self._load_preprocessing_results(dataset, entity)
            if cached is not None:
                self.logger.info(f"[GEM] Using cached preprocessing for {dataset}/{entity}")
                metadata["status"] = "completed"
                metadata["from_cache"] = True
                self._preprocessing_cache[f"{dataset}_{entity}"] = cached
                return metadata
            
            start_time = time.time()
            
            # Load schema
            schema = self._load_schema(dataset, entity)
            if not schema:
                metadata["status"] = "failed"
                metadata["error"] = f"Could not load schema for {dataset}/{entity}"
                return metadata
            
            # Get data path
            data_path = self._get_data_path(dataset, entity)
            if not data_path:
                metadata["status"] = "failed"
                metadata["error"] = f"Could not find data for {dataset}/{entity}"
                return metadata
            
            # Extract
            self.logger.info(f"[GEM] Extracting from {data_path}...")
            extractor = Extractor(schema, self.logger)
            records, extract_stats = extractor.extract_from_directory(data_path)
            
            if not records:
                self.logger.warning(f"[GEM] No records extracted for {dataset}/{entity}")
                metadata["status"] = "completed_empty"
                metadata["extraction_stats"] = extract_stats
                return metadata
            
            self.logger.info(f"[GEM] Extracted {len(records)} records")
            
            # Block
            self.logger.info(f"[GEM] Blocking {len(records)} records...")
            blocker = SemanticBlocker(logger=self.logger)
            key_attrs = schema.get_key_attributes()
            blocks = blocker.block_entities(records, key_attrs)
            
            self.logger.info(f"[GEM] Blocked into {len(blocks)} blocks")
            
            # Resolve
            self.logger.info(f"[GEM] Resolving {len(blocks)} blocks...")
            resolver = EntityResolver(self.logger)
            canonical_map = resolver.resolve_blocks(records, blocks, key_attrs)
            
            # Normalize with type conversion
            normalized_records = resolver.normalize_records(records, key_attrs, schema)
            
            # Cache results
            cache_data = {
                "canonical_map": canonical_map,
                "normalized_records": normalized_records
            }
            self._save_preprocessing_results(dataset, entity, cache_data)
            self._preprocessing_cache[f"{dataset}_{entity}"] = cache_data
            
            metadata["status"] = "completed"
            metadata["total_time"] = time.time() - start_time
            metadata["records_count"] = len(normalized_records)
            metadata["canonical_count"] = len(canonical_map)
            metadata["extraction_stats"] = extract_stats
            
            self.logger.info(f"[GEM] Preprocessing complete: {len(normalized_records)} normalized records, {len(canonical_map)} canonicals")
            
        except Exception as e:
            self.logger.error(f"[GEM] Preprocessing failed: {e}", exc_info=True)
            metadata["status"] = "failed"
            metadata["error"] = str(e)
        
        return metadata
    
    def run_query(self, query: Dict) -> Tuple[Optional[pd.DataFrame], Dict]:
        """Execute a query.
        
        Args:
            query: Query dictionary
            
        Returns:
            Tuple of (result_df, metadata)
        """
        if pd is None:
            return None, {"status": "failed", "error": "pandas not available"}
        
        query_id = query["id"]
        dataset = query["dataset"]
        entity_str = query.get("entity", "").lower()
        entities = [e.strip() for e in entity_str.split(",") if e.strip()]
        sql = query.get("sql", "")
        
        self.logger.info(f"[GEM] Running query {query_id}...")
        self.logger.info(f"[GEM] Query involves entities: {entities}")
        
        metadata = {
            "system": self.name,
            "query_id": query_id,
            "start_time": datetime.now().isoformat(),
            "status": "running"
        }
        
        result_df = None
        
        try:
            start_time = time.time()
            
            # Ensure preprocessing is done for all entities in the query
            for entity in entities:
                cache_key = f"{dataset}_{entity}"
                if cache_key not in self._preprocessing_cache:
                    self.logger.debug(f"[GEM] Preprocessing not in cache for {entity}, running now...")
                    preprocess_meta = self.preprocess(dataset, entity)
                    if preprocess_meta["status"] not in ["completed", "completed_empty"]:
                        metadata["status"] = preprocess_meta["status"]
                        metadata["error"] = f"Preprocessing failed for {entity}: {preprocess_meta.get('error', 'Unknown error')}"
                        metadata["end_time"] = datetime.now().isoformat()
                        return result_df, metadata
            
            # Load preprocessing results for all entities
            engine = DBEngine(logger=self.logger)
            resolver = EntityResolver(self.logger)
            
            # Create and populate tables for all entities
            for entity in entities:
                cache_key = f"{dataset}_{entity}"
                
                if cache_key not in self._preprocessing_cache:
                    cached = self._load_preprocessing_results(dataset, entity)
                    if cached is None:
                        metadata["status"] = "failed"
                        metadata["error"] = f"No preprocessed data available for {entity}"
                        metadata["end_time"] = datetime.now().isoformat()
                        return result_df, metadata
                    self._preprocessing_cache[cache_key] = cached
                
                preprocess_data = self._preprocessing_cache[cache_key]
                canonical_map = preprocess_data["canonical_map"]
                normalized_records = preprocess_data["normalized_records"]
                
                # Get schema for this entity
                schema = self._load_schema(dataset, entity)
                if not schema:
                    metadata["status"] = "failed"
                    metadata["error"] = f"Could not load schema for {entity}"
                    metadata["end_time"] = datetime.now().isoformat()
                    return result_df, metadata
                
                resolver.canonical_map = canonical_map
                engine.set_resolver(resolver)
                engine.set_schema(schema)
                
                # Create and populate table
                table_name = entity
                engine.create_table(table_name, schema)
                engine.insert_records(table_name, normalized_records)
                self.logger.info(f"[GEM] Created table {table_name} with {len(normalized_records)} records")
            
            # Execute query
            result_df = engine.execute_query(sql)
            
            if result_df is not None:
                metadata["status"] = "completed"
                metadata["result_count"] = len(result_df)
                self.logger.info(f"[GEM] Query returned {len(result_df)} rows")
            else:
                metadata["status"] = "failed"
                metadata["error"] = "Query execution returned no results"
            
            engine.close()
            
        except Exception as e:
            self.logger.error(f"[GEM] Query failed: {e}", exc_info=True)
            metadata["status"] = "failed"
            metadata["error"] = str(e)
        
        metadata["total_time"] = time.time() - start_time
        metadata["end_time"] = datetime.now().isoformat()
        
        return result_df, metadata

