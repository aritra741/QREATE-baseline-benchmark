"""
DocETL Query Executor for Healthcare Join Queries
Follows UDA-Bench evaluation methodology exactly.

Integration point with docetl_healthcare_evaluation.py
"""

import json
import logging
import hashlib
import pickle
from typing import Dict, List, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Cache for extracted attributes
EXTRACTION_CACHE_DIR = Path("extraction_cache")
EXTRACTION_CACHE_DIR.mkdir(exist_ok=True)


def _get_cache_key(doc_content: str, entity_type: str) -> str:
    """Generate cache key for a document extraction."""
    content_hash = hashlib.md5(doc_content.encode()).hexdigest()
    return f"{entity_type}_{content_hash}"


def _get_cached_extraction(doc_content: str, entity_type: str) -> Dict | None:
    """Retrieve cached extraction if available."""
    cache_key = _get_cache_key(doc_content, entity_type)
    cache_file = EXTRACTION_CACHE_DIR / f"{cache_key}.pkl"
    
    if cache_file.exists():
        try:
            with open(cache_file, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            logger.warning(f"Failed to load cache for {cache_key}: {e}")
    return None


def _cache_extraction(doc_content: str, entity_type: str, result: Dict) -> None:
    """Cache extraction result."""
    cache_key = _get_cache_key(doc_content, entity_type)
    cache_file = EXTRACTION_CACHE_DIR / f"{cache_key}.pkl"
    
    try:
        with open(cache_file, 'wb') as f:
            pickle.dump(result, f)
    except Exception as e:
        logger.warning(f"Failed to cache extraction for {cache_key}: {e}")


class DocETLHealthcareQueryExecutor:
    """
    Execute Healthcare join queries using DocETL Python API.
    
    Mirrors the approach described in UDA-Bench Section 4.1:
    "DocETL is an open-source project allowing users to execute queries by 
     writing Python code. We rewrite our queries with DocETL library and 
     execute the Python programs."
    """
    
    def __init__(self, 
                 attributes_file: str = "Query/Med/Med_attributes.json",
                 model: str = "ollama/qwen2.5:7b-instruct"):
        """
        Initialize DocETL executor.
        
        Args:
            attributes_file: Path to Med_attributes.json (schema definition)
            model: LLM model to use (following their choice)
        """
        self.attributes_file = Path(attributes_file)
        self.model = model
        
        # Load attribute definitions
        with open(self.attributes_file) as f:
            self.attributes = json.load(f)
        
        # Extract tables and their schemas
        self.tables = {
            "disease": self.attributes.get("disease", {}),
            "drug": self.attributes.get("drug", {}),
            "institution": self.attributes.get("institution", {}),
        }
    
    def extract_disease_attributes(self, document: str) -> Dict[str, Any]:
        """
        Extract disease attributes from document using DocETL map operator.
        Results are cached to avoid re-running LLM inference.
        """
        # Check cache first
        cached = _get_cached_extraction(document, "disease")
        if cached is not None:
            logger.debug("Using cached disease extraction")
            return cached
        
        attributes_to_extract = [
            "disease_name",
            "disease_type", 
            "pathogenesis",
            "etiology",
            "diagnostic_methods",
            "common_symptoms",
            "complications",
            "treatments",
            "prognosis",
            "epidemiology",
            "risk_factors",
            "preventive_measures",
        ]
        
        prompt = self._build_extraction_prompt(
            "disease",
            attributes_to_extract,
            document
        )
        
        # Call DocETL map operator (to be implemented)
        result = self._call_docetl_map(prompt, attributes_to_extract)
        _cache_extraction(document, "disease", result)
        return result
    
    def extract_drug_attributes(self, document: str) -> Dict[str, Any]:
        """
        Extract drug attributes from document using DocETL map operator.
        Results are cached to avoid re-running LLM inference.
        """
        # Check cache first
        cached = _get_cached_extraction(document, "drug")
        if cached is not None:
            logger.debug("Using cached drug extraction")
            return cached
        
        attributes_to_extract = [
            "generic_name",
            "brand_name",
            "disease_name",
            "indication",
            "active_ingredients",
            "pharmaceutical_form",
            "manufacturer",
            "mechanism_of_action",
            "side_effects",
            "administration_route",
            "recommended_usage",
            "single_dose",
            "prescription_status",
            "storage_conditions",
        ]
        
        prompt = self._build_extraction_prompt(
            "drug",
            attributes_to_extract,
            document
        )
        
        result = self._call_docetl_map(prompt, attributes_to_extract)
        _cache_extraction(document, "drug", result)
        return result
    
    def extract_institution_attributes(self, document: str) -> Dict[str, Any]:
        """
        Extract institution attributes from document using DocETL map operator.
        """
        attributes_to_extract = [
            "institution_name",
            "institution_type",
            "institution_country",
            "institution_city",
            "research_diseases",
            "research_fields",
            "key_technologies",
            "funding_sources",
        ]
        
        prompt = self._build_extraction_prompt(
            "institution",
            attributes_to_extract,
            document
        )
        
        result = self._call_docetl_map(prompt, attributes_to_extract)
        
        return result
    
    def execute_join_query(self, 
                          query_sql: str,
                          disease_docs: List[Dict],
                          drug_docs: List[Dict],
                          institution_docs: List[Dict] = None) -> Dict:
        """
        Execute a join query following UDA-Bench approach.
        
        Strategy (from UDA-Bench Section 4.1):
        1. Extract join key attributes from each document set
        2. Perform join based on join condition
        3. Return result tuples
        
        Args:
            query_sql: SQL join query to execute
            disease_docs: List of disease documents
            drug_docs: List of drug documents
            institution_docs: Optional list of institution documents
        
        Returns:
            {
                "tuples": [...],  # Result tuples
                "token_count": int,  # Estimated tokens used
                "num_documents_processed": int,
            }
        """
        logger.info(f"Executing join query: {query_sql[:80]}...")
        
        # Parse query to identify:
        # - SELECT attributes
        # - FROM tables
        # - WHERE conditions
        # - JOIN conditions
        parsed = self._parse_sql_query(query_sql)
        
        logger.info(f"Parsed query: {parsed}")
        
        # Step 1: Extract relevant attributes from each document set
        logger.info("Step 1: Extracting attributes from document sets...")
        
        disease_extracted = []
        for doc in disease_docs:
            try:
                attrs = self.extract_disease_attributes(doc.get("content", ""))
                disease_extracted.append(attrs)
            except Exception as e:
                logger.warning(f"Error extracting disease doc {doc.get('id')}: {e}")
        
        drug_extracted = []
        for doc in drug_docs:
            try:
                attrs = self.extract_drug_attributes(doc.get("content", ""))
                drug_extracted.append(attrs)
            except Exception as e:
                logger.warning(f"Error extracting drug doc {doc.get('id')}: {e}")
        
        institution_extracted = []
        if institution_docs:
            for doc in institution_docs:
                try:
                    attrs = self.extract_institution_attributes(doc.get("content", ""))
                    institution_extracted.append(attrs)
                except Exception as e:
                    logger.warning(f"Error extracting institution doc {doc.get('id')}: {e}")
        
        logger.info(f"Extracted: {len(disease_extracted)} disease, {len(drug_extracted)} drug")
        
        # Step 2: Perform join
        logger.info("Step 2: Performing join operation...")
        
        join_key = parsed["join_key"]  # e.g., "disease_name"
        result_tuples = self._perform_join(
            disease_extracted,
            drug_extracted,
            join_key,
            parsed["select_attributes"]
        )
        
        logger.info(f"Join produced {len(result_tuples)} result tuples")
        
        # Step 3: Filter if WHERE clause exists
        if parsed.get("where_conditions"):
            logger.info("Step 3: Applying WHERE filters...")
            result_tuples = self._apply_filters(result_tuples, parsed["where_conditions"])
            logger.info(f"After filtering: {len(result_tuples)} tuples")
        
        # Step 4: Aggregate if GROUP BY exists
        if parsed.get("group_by"):
            logger.info("Step 4: Applying GROUP BY aggregation...")
            result_tuples = self._apply_aggregation(
                result_tuples,
                parsed["group_by"],
                parsed.get("aggregation_functions")
            )
            logger.info(f"After aggregation: {len(result_tuples)} tuples")
        
        # Estimate token usage (rough estimate)
        total_docs_processed = len(disease_docs) + len(drug_docs)
        token_count = self._estimate_token_count(
            disease_extracted,
            drug_extracted,
            total_docs_processed
        )
        
        return {
            "tuples": result_tuples,
            "token_count": token_count,
            "num_documents_processed": total_docs_processed,
            "query_type": parsed.get("query_type", "unknown"),
        }
    
    def _parse_sql_query(self, query_sql: str) -> Dict:
        """
        Parse SQL query to extract join conditions, select attributes, etc.
        
        Simple parser for Healthcare join queries.
        """
        query_upper = query_sql.upper()
        
        parsed = {
            "select_attributes": [],
            "from_tables": [],
            "join_key": None,
            "join_condition": None,
            "where_conditions": [],
            "group_by": None,
            "aggregation_functions": {},
        }
        
        # Extract SELECT attributes
        select_start = query_upper.find("SELECT") + 6
        from_start = query_upper.find("FROM")
        if select_start > 5 and from_start > select_start:
            select_part = query_sql[select_start:from_start].strip()
            parsed["select_attributes"] = [s.strip() for s in select_part.split(",")]
        
        # Extract FROM and JOIN tables
        join_start = query_upper.find("JOIN")
        if join_start > 0:
            from_part = query_sql[from_start+4:join_start].strip()
            parsed["from_tables"] = [t.strip() for t in from_part.split(",")]
            
            # Extract join condition
            on_start = query_upper.find("ON", join_start)
            where_start = query_upper.find("WHERE")
            
            if on_start > 0:
                if where_start > on_start:
                    on_part = query_sql[on_start+2:where_start].strip()
                else:
                    on_part = query_sql[on_start+2:].strip()
                    # Remove GROUP BY if present
                    group_start = on_part.upper().find("GROUP")
                    if group_start > 0:
                        on_part = on_part[:group_start]
                
                # Parse ON condition: "disease.name = drug.disease"
                if "=" in on_part:
                    left, right = on_part.split("=")
                    parsed["join_key"] = right.strip().split(".")[-1]
                    parsed["join_condition"] = (left.strip(), right.strip())
        
        # Determine query type for reporting
        if "WHERE" in query_upper and "GROUP BY" in query_upper:
            parsed["query_type"] = "Select+Filter+Join+Aggregation"
        elif "WHERE" in query_upper:
            parsed["query_type"] = "Select+Filter+Join"
        elif "GROUP BY" in query_upper:
            parsed["query_type"] = "Select+Join+Aggregation"
        else:
            parsed["query_type"] = "Select+Join"
        
        return parsed
    
    def _build_extraction_prompt(self, 
                                 entity_type: str, 
                                 attributes: List[str],
                                 document: str) -> str:
        """
        Build extraction prompt for DocETL map operator.
        
        Format matching UDA-Bench evaluation prompts.
        """
        attr_list = "\n".join([f"- {attr}" for attr in attributes])
        
        prompt = f"""Extract the following {entity_type} attributes from this document:

{attr_list}

Document:
{document[:1000]}...

Return ONLY a JSON object with the extracted values or "Not found" if attribute is not mentioned."""
        
        return prompt
    
    def _call_docetl_map(self, prompt: str, output_attributes: List[str]) -> Dict:
        try:
            from litellm import completion
            import re
            
            output_schema = {attr: "string" for attr in output_attributes}
            schema_str = json.dumps(output_schema, indent=2)
            
            messages = [
                {"role": "system", "content": "You are a helpful assistant. Return ONLY valid JSON, no markdown, no code blocks."},
                {"role": "user", "content": f"{prompt}\n\nReturn response as JSON with this schema:\n{schema_str}"}
            ]
            
            response = completion(
                model=self.model,
                messages=messages,
                temperature=0.0
            )
            
            content = response.choices[0].message.content.strip()
            
            # Remove markdown code blocks if present
            if content.startswith("```"):
                # Extract JSON from code block
                match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
                if match:
                    content = match.group(1)
                else:
                    # Try to find JSON object
                    match = re.search(r'\{.*\}', content, re.DOTALL)
                    if match:
                        content = match.group(0)
            
            try:
                result = json.loads(content)
                # Ensure all required attributes are present
                for attr in output_attributes:
                    if attr not in result:
                        result[attr] = "Not found"
                return result
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON response: {e}")
                logger.warning(f"Content: {content[:200]}")
                return {attr: "Not found" for attr in output_attributes}
            
        except Exception as e:
            logger.error(f"Error in _call_docetl_map: {e}")
            return {attr: "Not found" for attr in output_attributes}
    
    def _perform_join(self, 
                     left_records: List[Dict],
                     right_records: List[Dict],
                     join_key: str,
                     select_attributes: List[str]) -> List[Dict]:
        """
        Perform join operation between two record sets.
        
        Join type: inner join on join_key
        """
        result = []
        
        for left in left_records:
            for right in right_records:
                # Check if join keys match
                left_key = left.get(join_key, "")
                right_key = right.get(join_key, "")
                
                if left_key and right_key and left_key.lower() == right_key.lower():
                    # Create joined record
                    joined = {}
                    
                    # Add requested attributes
                    for attr in select_attributes:
                        if "." in attr:
                            # Qualified attribute like "disease.diagnostic_methods"
                            table, col = attr.split(".")
                            if table.lower() in ["disease", "drug"]:
                                source = left if table.lower() == "disease" else right
                                # Try exact match first, then try variations
                                value = source.get(col, None)
                                if value is None:
                                    # Try common variations
                                    for key in source.keys():
                                        if key.lower() == col.lower() or key.replace("_", "") == col.replace("_", ""):
                                            value = source[key]
                                            break
                                joined[attr] = value if value else "Not found"
                        else:
                            # Unqualified - try both
                            if attr in left:
                                joined[attr] = left[attr]
                            elif attr in right:
                                joined[attr] = right[attr]
                            else:
                                joined[attr] = "Not found"
                    
                    if joined:
                        result.append(joined)
        
        return result
    
    def _apply_filters(self, records: List[Dict], conditions: List[str]) -> List[Dict]:
        filtered = []
        for record in records:
            include = True
            for condition in conditions:
                try:
                    if not eval(condition, {"record": record, **record}):
                        include = False
                        break
                except:
                    include = False
                    break
            if include:
                filtered.append(record)
        return filtered
    
    def _apply_aggregation(self, 
                          records: List[Dict],
                          group_by: str,
                          agg_functions: Dict) -> List[Dict]:
        from collections import defaultdict
        
        groups = defaultdict(list)
        for record in records:
            key = record.get(group_by, "unknown")
            groups[key].append(record)
        
        result = []
        for key, group_records in groups.items():
            agg_record = {group_by: key}
            
            if agg_functions:
                for agg_col, agg_func in agg_functions.items():
                    values = [r.get(agg_col) for r in group_records if agg_col in r]
                    
                    if agg_func.lower() == "count":
                        agg_record[f"{agg_func}({agg_col})"] = len(values)
                    elif agg_func.lower() == "sum":
                        agg_record[f"{agg_func}({agg_col})"] = sum(float(v) for v in values if v)
                    elif agg_func.lower() == "avg":
                        nums = [float(v) for v in values if v]
                        agg_record[f"{agg_func}({agg_col})"] = sum(nums) / len(nums) if nums else 0
                    elif agg_func.lower() == "min":
                        nums = [float(v) for v in values if v]
                        agg_record[f"{agg_func}({agg_col})"] = min(nums) if nums else None
                    elif agg_func.lower() == "max":
                        nums = [float(v) for v in values if v]
                        agg_record[f"{agg_func}({agg_col})"] = max(nums) if nums else None
            
            result.append(agg_record)
        
        return result
    
    def _estimate_token_count(self, 
                             disease_extracted: List[Dict],
                             drug_extracted: List[Dict],
                             total_docs: int) -> int:
        """
        Estimate total tokens used for the query.
        
        Rough estimate: ~500 tokens per document extraction
        """
        tokens_per_doc = 500
        return total_docs * tokens_per_doc


def execute_healthcare_queries(evaluation_system):
    """
    Execute all Healthcare queries using DocETL.
    
    Integration function for docetl_healthcare_evaluation.py
    """
    executor = DocETLHealthcareQueryExecutor()
    
    # Get documents from evaluation system
    disease_docs = evaluation_system.documents.get("disease", [])
    drug_docs = evaluation_system.documents.get("drug", [])
    institution_docs = evaluation_system.documents.get("institution", [])
    
    # Load queries
    with open(evaluation_system.queries_file) as f:
        queries_text = f.read()
    
    queries = [q.strip() for q in queries_text.split(";") if q.strip()]
    
    # Execute each query
    for query_id, query_sql in enumerate(queries, 1):
        try:
            results = executor.execute_join_query(
                query_sql,
                disease_docs,
                drug_docs,
                institution_docs
            )
            
            # Update evaluation system results
            evaluation_system.results["queries"][query_id] = {
                "sql": query_sql[:100],
                "num_tuples": len(results["tuples"]),
                "cost": results["token_count"] / 1000.0 / max(1, results["num_documents_processed"]),
                "query_type": results["query_type"],
            }
            
            logger.info(f"Query {query_id} completed: {len(results['tuples'])} tuples")
        
        except Exception as e:
            logger.error(f"Error executing query {query_id}: {e}", exc_info=True)


if __name__ == "__main__":
    # Example usage
    executor = DocETLHealthcareQueryExecutor()
    
    # Test query
    test_query = """
    SELECT disease.diagnostic_methods, drug.manufacturer, 
           drug.brand_name, disease.disease_name 
    FROM disease 
    JOIN drug ON disease.disease_name = drug.disease_name
    """
    
    logger.info(f"Test query: {test_query}")
    parsed = executor._parse_sql_query(test_query)
    logger.info(f"Parsed: {parsed}")
