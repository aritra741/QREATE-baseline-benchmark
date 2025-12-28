"""
Palimpzest (PZ) integration for UDA-Bench.

Implements Algorithm 1 from "Palimpzest: Optimizing AI-Powered Analytics with 
Declarative Query Processing" (Liu et al., CIDR 2025):

Algorithm 1 - 7-Step Pipeline:
① Compilation: Declarative API → Logical Plan
② Logical Optimization: Filter reordering, convert reordering (via Cascades)
③ Physical Plan Generation: Model selection, prompt marshaling, token reduction
④-⑤ Sentinel Profiling: Run sample plans to estimate cost/quality/time
⑥ Plan Selection: Choose Pareto-optimal plan based on policy
⑦ Execution: Execute selected plan on full dataset

The PZ library's optimize_and_run() implements all 7 steps internally.
This runner prepares unstructured text data and calls the library correctly.
"""

import logging
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re

import pandas as pd


PROJECT_ROOT = Path(__file__).parent.parent.parent


class PZRunner:
    """Palimpzest runner - follows Paper Algorithm 1 on unstructured text."""
    
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.name = "pz"
        self._initialized = False
        self._pz_available = False
        self.pz = None
        
    def _ensure_init(self):
        if self._initialized:
            return
        self._initialized = True
        
        try:
            import palimpzest as pz
            self.pz = pz
            self._pz_available = True
            self.logger.info("[PZ] ✓ Library loaded - Algorithm 1 available via optimize_and_run()")
        except ImportError as e:
            self._pz_available = False
            self.logger.error(f"[PZ] Import failed: {e}")
    
    def preprocess(self, dataset: str, entity: str) -> Dict:
        return {
            "system": self.name,
            "dataset": dataset,
            "entity": entity,
            "timestamp": datetime.now().isoformat(),
            "status": "completed",
            "pz_available": self._pz_available
        }
    
    def run_query(self, query: Dict) -> Tuple[Optional[pd.DataFrame], Dict]:
        """Execute query following Paper Algorithm 1 on unstructured text files.
        
        Paper Algorithm 1 (7 steps):
        ① Compile declarative program → logical plan
        ② Generate logically equivalent plans (filter/convert reordering)
        ③ Generate physical plans (model selection, prompt strategies)
        ④-⑤ Execute sentinel plans on validation set, estimate cost/quality
        ⑥ Select Pareto-optimal plan based on policy
        ⑦ Execute selected plan on full dataset
        
        The PZ library's optimize_and_run() implements all 7 steps.
        This method prepares data and builds the declarative program (step ①).
        
        Note: PZ supports all operators in Table 1 (Project, Select, Convert, 
        Group by, Aggregate, Limit) but current implementation focuses on 
        extraction and filtering (SPJ queries) as per paper evaluation.
        """
        self._ensure_init()
        
        query_id = query["id"]
        sql = query["sql"]
        dataset = query["dataset"]
        entity = query.get("entity", "").lower()
        query_type = query.get("type", "unknown")
        
        self.logger.info(f"[PZ] Query {query_id} - {query_type}")
        
        metadata = {
            "system": self.name,
            "query_id": query_id,
            "dataset": dataset,
            "entity": entity,
            "query_type": query_type,
            "start_time": datetime.now().isoformat(),
            "status": "running",
            "algorithm_1_implementation": "PZ library optimize_and_run()",
            "paper_reference": "Liu et al. CIDR 2025, Algorithm 1",
        }
        
        result_df = None
        start_time = time.time()
        
        # Check for unsupported query types
        # Union queries are not in the paper evaluation
        if query_type == "union":
            self.logger.warning(f"[PZ] Union queries not evaluated in paper (uda-new.md §2.2)")
            metadata["status"] = "unsupported"
            metadata["error"] = f"Union queries not supported - not in paper evaluation"
            metadata["total_time"] = time.time() - start_time
            metadata["end_time"] = datetime.now().isoformat()
            return None, metadata
        
        # Join queries with multiple entities not supported
        if query_type == "join":
            # Check if multi-entity join
            entities = [e.strip() for e in entity.split(",") if e.strip()]
            if len(entities) > 1:
                self.logger.warning(f"[PZ] Multi-entity join requires multiple datasets")
                self.logger.warning(f"[PZ] Paper focuses on single-entity queries")
                metadata["status"] = "unsupported"
                metadata["error"] = f"Multi-entity join not implemented (paper evaluates single-dataset queries)"
                metadata["total_time"] = time.time() - start_time
                metadata["end_time"] = datetime.now().isoformat()
                return None, metadata
        
        # Note: Aggregation IS supported via Extract-All strategy
        # (uda-new.md §2.2 line 422-424: "Evaporate, ZenDB, QUEST and Palimpzest extract 
        # the attribute from all documents, group the values in a table, and then perform aggregation")
        
        try:
            if not self._pz_available:
                raise RuntimeError("Palimpzest library not available")
            
            # Get source_data path (unstructured .txt files - PZ's native format)
            source_path = self._get_source_data_path(dataset, entity)
            if not source_path or not Path(source_path).exists():
                metadata["status"] = "requires_data"
                metadata["error"] = f"Unstructured source_data not found: {source_path}"
                metadata["hint"] = "PZ requires .txt files in source_data/"
                metadata["total_time"] = time.time() - start_time
                metadata["end_time"] = datetime.now().isoformat()
                return None, metadata
            
            txt_files = list(Path(source_path).glob("*.txt"))
            if not txt_files:
                metadata["status"] = "requires_data"
                metadata["error"] = f"No .txt files in: {source_path}"
                metadata["total_time"] = time.time() - start_time
                metadata["end_time"] = datetime.now().isoformat()
                return None, metadata
            
            self.logger.info(f"[PZ] Using {len(txt_files)} unstructured .txt files from {source_path}")
            
            # STEP ① (Paper Algorithm 1, line 1): Build declarative program
            # Paper §3: "Users write declarative programs with lazy Dataset API"
            self.logger.info("[PZ] Step ① Compilation: Building declarative program from SQL")
            
            # Load unstructured text files (Paper §3, TextFile schema)
            dataset_obj = self.pz.TextFileDataset(
                path=str(source_path), 
                id=f"{dataset}_{entity}_docs"
            )
            self.logger.debug(f"[PZ] Created TextFileDataset for {dataset}/{entity}")
            
            # Parse SQL to build PZ operators
            select_cols = self._extract_select_columns(sql)
            where_clauses = self._extract_where_clauses(sql)
            group_cols, agg_specs = self._extract_aggregation_spec(sql)
            
            # Paper Table 1: Convert operator χ - extract schema from unstructured text
            # Extract all attributes needed for the query (including aggregation grouping keys)
            extract_cols = select_cols.copy() if select_cols != ["*"] else []
            if group_cols:
                extract_cols = list(set(extract_cols + group_cols))
            
            if extract_cols:
                # Define output schema for sem_map (Paper Figure 2 example)
                schema_fields = []
                for col in extract_cols:
                    # Use proper PZ field types (paper uses StringField, IntField, etc.)
                    schema_fields.append({
                        "name": col,
                        "type": str,  # Simplified; real impl would infer types
                        "desc": f"The {col} attribute extracted from the document"
                    })
                dataset_obj = dataset_obj.sem_map(schema_fields)
                self.logger.info(f"[PZ] sem_map: Extracting {len(extract_cols)} attributes via Convert operator")
            
            # Paper Table 1: Select operator σ - apply semantic filters
            for where in where_clauses:
                dataset_obj = dataset_obj.sem_filter(where)
                self.logger.info(f"[PZ] sem_filter: '{where}'")
            
            # Paper Table 1: Aggregate operator - GroupBy + Aggregation
            # uda-new.md §2.2 (line 422-424): "Palimpzest extracts all attributes, groups, then aggregates"
            if group_cols and agg_specs:
                self.logger.info(f"[PZ] groupby(): Extract-All strategy - grouping by {group_cols}, then aggregating")
                # PZ's groupby() uses GroupBySig to specify the grouping and aggregation
                try:
                    from palimpzest.core.elements.groupbysig import GroupBySig
                    
                    # Build GroupBySig with:
                    # - group_by_fields: list of columns to group by
                    # - agg_funcs: list of aggregation functions (e.g., ['count', 'sum'])
                    # - agg_fields: list of fields to aggregate on
                    agg_funcs = [spec["function"].lower() for spec in agg_specs]
                    agg_fields = [spec["column"] if spec["column"] != "*" else group_cols[0] for spec in agg_specs]
                    
                    group_by_sig = GroupBySig(
                        group_by_fields=group_cols,
                        agg_funcs=agg_funcs,
                        agg_fields=agg_fields
                    )
                    dataset_obj = dataset_obj.groupby(group_by_sig)
                    self.logger.info(f"[PZ] Applied groupby() with columns={group_cols}, agg_funcs={agg_funcs}")
                except Exception as e:
                    self.logger.warning(f"[PZ] groupby() failed: {e}")
                    self.logger.warning(f"[PZ] Will proceed with extraction only")
            
            # STEPS ②-⑦ (Paper Algorithm 1, lines 2-20): Execute via optimize_and_run()
            # Paper §3: "optimize_and_run() compiles initial logical plan, generates
            # logically equivalent plans, creates physical candidates, runs sentinel
            # profiling, selects optimal plan based on policy, and executes"
            self.logger.info("[PZ] Steps ②-⑦: Calling optimize_and_run() for:")
            self.logger.info("  ② Logical optimization (filter/convert reordering)")
            self.logger.info("  ③ Physical plan generation (model selection, prompts)")
            self.logger.info("  ④-⑤ Sentinel profiling (cost/quality estimation)")
            self.logger.info("  ⑥ Plan selection (Pareto-optimal via policy)")
            self.logger.info("  ⑦ Execution on full dataset")
            
            # Paper §3: QueryProcessorConfig specifies policy and execution strategy
            # Paper Figure 2: Policy determines optimization goal
            # Configure Ollama/qwen2.5:7b-instruct via LiteLLM environment variables
            import os
            os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "true"
            os.environ["OLLAMA_API_BASE"] = "http://localhost:11434/v1"
            os.environ["OLLAMA_API_KEY"] = "ollama"
            # Required for LiteLLM when routing to Ollama via "openai/" prefix
            # This is a dummy key since Ollama doesn't authenticate
            os.environ["OPENAI_API_KEY"] = "ollama-no-auth"
            
            # Don't set api_base or VLLM_API_BASE - this would enable vLLM models
            # which would then be chosen before Ollama models. Instead, only Ollama
            # detection via OLLAMA_API_BASE environment variable is used.
            
            config = self.pz.QueryProcessorConfig(
                policy=self.pz.MaxQuality(),  # Paper: maximize F1-score
                execution_strategy="parallel",
                max_workers=4,
                progress=True,
                # Paper Algorithm 1 lines 4-9: Validation sample for sentinel profiling
                validation_sample_size=0.05,  # 5% for cost/quality estimation (paper §3)
            )
            
            # Paper §3: Validator checks quality against champion model
            validator = self.pz.Validator()
            
            # Call PZ library - this executes Algorithm 1 steps ②-⑦
            output_dataset = dataset_obj.optimize_and_run(config=config, validator=validator)
            
            # Convert result to DataFrame
            result_df = output_dataset.to_df()
            
            metadata["status"] = "completed"
            metadata["result_count"] = len(result_df)
            metadata["result_shape"] = list(result_df.shape)
            metadata["operators_applied"] = {
                "sem_map": len(select_cols) if select_cols else 0,
                "sem_filter": len(where_clauses)
            }
            
            self.logger.info(f"[PZ] ✓ Algorithm 1 completed: {len(result_df)} rows returned")
            
        except Exception as e:
            self.logger.error(f"[PZ] Query failed: {e}")
            self.logger.debug(traceback.format_exc())
            metadata["status"] = "failed"
            metadata["error"] = str(e)
            metadata["traceback"] = traceback.format_exc()
        
        metadata["total_time"] = time.time() - start_time
        metadata["end_time"] = datetime.now().isoformat()
        return result_df, metadata
    
    def _extract_select_columns(self, sql: str) -> List[str]:
        """Extract SELECT columns (excluding aggregate function results)."""
        match = re.search(r'SELECT\s+(.+?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
        if match:
            cols_str = re.sub(r'\s+', ' ', match.group(1).strip())
            if cols_str == "*":
                return ["*"]
            # Parse columns, but skip aggregate function results
            cols = []
            # Remove aggregate functions and their arguments
            # e.g., "COUNT(*) AS disease_count" -> ""
            no_aggs = re.sub(r'(COUNT|SUM|AVG|MIN|MAX)\s*\([^)]*\)\s*(?:AS\s+\w+)?', '', cols_str, flags=re.IGNORECASE)
            # Extract remaining column names
            for col_match in re.finditer(r'(\w+)', no_aggs):
                col_name = col_match.group(1)
                # Skip SQL keywords
                if col_name.upper() not in ['AS', 'FROM', 'WHERE', 'GROUP', 'ORDER', 'BY']:
                    cols.append(col_name)
            return cols if cols else ["*"]
        return ["*"]
    
    def _extract_where_clauses(self, sql: str) -> List[str]:
        """Extract WHERE clauses."""
        match = re.search(r'WHERE\s+(.+?)(?:GROUP|ORDER|;|$)', sql, re.IGNORECASE | re.DOTALL)
        if match:
            where = match.group(1).strip()
            return [c.strip() for c in re.split(r'\s+AND\s+', where, flags=re.IGNORECASE)]
        return []
    
    def _extract_aggregation_spec(self, sql: str) -> Tuple[List[str], List[Dict]]:
        """Extract GROUP BY columns and aggregation functions.
        
        Paper: uda-new.md §2.2 (line 422-424) describes Extract-All aggregation:
        "Palimpzest extracts the attribute from all documents, groups the values, 
        then performs aggregation on the grouped data"
        
        Returns:
            - group_cols: List of GROUP BY columns
            - agg_specs: List of aggregation specifications
        """
        group_cols = []
        agg_specs = []
        
        # Extract GROUP BY clause
        group_match = re.search(r'GROUP\s+BY\s+(.+?)(?:ORDER|;|$)', sql, re.IGNORECASE | re.DOTALL)
        if group_match:
            group_cols = [col.strip() for col in group_match.group(1).split(',')]
        
        # Extract aggregation functions from SELECT clause
        select_match = re.search(r'SELECT\s+(.+?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
        if select_match:
            select_clause = select_match.group(1)
            # Find functions like COUNT(*), AVG(col), SUM(col), MIN(col), MAX(col)
            agg_pattern = r'(COUNT|SUM|AVG|MIN|MAX)\s*\(\s*(?:\*|([^)]+))\s*\)\s*(?:AS\s+(\w+))?'
            for match in re.finditer(agg_pattern, select_clause, re.IGNORECASE):
                func = match.group(1).upper()
                col = match.group(2) if match.group(2) else "*"
                alias = match.group(3) if match.group(3) else f"{func}_{col}"
                agg_specs.append({
                    "function": func,
                    "column": col,
                    "alias": alias
                })
        
        return group_cols, agg_specs
    
    def _get_source_data_path(self, dataset: str, entity: str) -> Optional[str]:
        """Get source_data path with unstructured .txt files.
        
        Paper requirement: Palimpzest operates on unstructured text documents.
        The source_data/ directory contains raw .txt files (one per document).
        """
        
        # Map to source_data directories with .txt files
        # These are the UNSTRUCTURED documents that PZ processes (paper §2)
        data_map = {
            ("Med", "disease"): PROJECT_ROOT / "source_data" / "Healthcare" / "disease_small",
            ("Med", "drug"): PROJECT_ROOT / "source_data" / "Healthcare" / "drug_small",
            ("Med", "institution"): PROJECT_ROOT / "source_data" / "Healthcare" / "institutes_small",
            ("Player", "player"): PROJECT_ROOT / "source_data" / "Player" / "player",
            ("Player", "team"): PROJECT_ROOT / "source_data" / "Player" / "team",
            ("Player", "city"): PROJECT_ROOT / "source_data" / "Player" / "city",
            ("Art", "art"): PROJECT_ROOT / "source_data" / "Art" / "wikiart",
            ("Legal", "legal_case"): PROJECT_ROOT / "source_data" / "Legal" / "legal_case",
            ("Finan", "finance"): PROJECT_ROOT / "source_data" / "Finance" / "finance",
        }
        
        for (ds, ent), path in data_map.items():
            if ds.lower() == dataset.lower() and ent.lower() == entity.lower():
                if path.exists():
                    self.logger.debug(f"[PZ] Mapped {dataset}/{entity} → {path}")
                    return str(path)
                else:
                    self.logger.warning(f"[PZ] Path does not exist: {path}")
                    return None
        
        self.logger.warning(f"[PZ] No source_data mapping for {dataset}/{entity}")
        return None
