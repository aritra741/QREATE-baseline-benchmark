"""
Optimized Disease Dataset Query Execution with UQE Optimizations.

This version integrates:
- Stratified Sampling for aggregation queries
- Active Learning for retrieval queries
- Query Plan Optimization for all queries
"""

from parse import parser
from plan import planner
from optimize import optimizer 
from optimized_executor import optimized_executor
from utils import read_query_list, print_config_to_file

from schema.disease import DiseaseData

import os
from datetime import datetime
from tqdm import tqdm
import logging

# Setup logger
logger = logging.getLogger('UQE.main_disease')
if not logger.handlers:
    import sys
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('[UQE-DISEASE] %(levelname)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Import optimization configuration
try:
    import config_uqe
    ENABLE_OPTIMIZATIONS = config_uqe.ENABLE_OPTIMIZATIONS
    logger.info(f"Optimizations enabled: {ENABLE_OPTIMIZATIONS}")
except Exception as e:
    logger.warning(f"Could not load optimization config: {e}")
    ENABLE_OPTIMIZATIONS = False


def main(query_type="SF", use_optimizations: bool = None):
    """
    Execute disease queries with optional UQE optimizations.
    
    Args:
        query_type: Type of queries to run (SF, SFW, etc.)
        use_optimizations: Override optimization setting (None = use config)
    """
    
    # Determine if optimizations should be enabled
    enable_opts = ENABLE_OPTIMIZATIONS if use_optimizations is None else use_optimizations
    
    # location of query - use absolute path relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    query_dir = os.path.join(script_dir, "query/disease")
    
    # read query
    query_dict = read_query_list(query_dir, query_type)
    
    # result save location, add timestamp
    result_dir = "result/disease"
    
    # Add optimization marker to result path
    opt_marker = "_optimized" if enable_opts else "_baseline"
    result_dir = os.path.join(script_dir, result_dir, query_type + opt_marker, 
                              datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(result_dir, exist_ok=True)
    
    logger.info("=" * 70)
    logger.info(f"DISEASE DATASET EXECUTION (Optimizations: {enable_opts})")
    logger.info("=" * 70)
    
    # Initialize source data
    source_data = DiseaseData("disease")
    
    # Load embeddings if optimizations are enabled
    embeddings = None
    if enable_opts:
        try:
            import numpy as np
            embedding_path = os.path.join(script_dir, "data/disease/embeddings.npy")
            if os.path.exists(embedding_path):
                embeddings = np.load(embedding_path)
                logger.info(f"Loaded embeddings: {embeddings.shape}")
            else:
                logger.warning(f"Embeddings not found at {embedding_path}")
        except Exception as e:
            logger.warning(f"Could not load embeddings: {e}")
    
    # Prepare optimization config
    opt_config = {}
    if enable_opts:
        try:
            opt_config = {
                'enable_stratified_sampling': config_uqe.ENABLE_STRATIFIED_SAMPLING,
                'enable_active_learning': config_uqe.ENABLE_ACTIVE_LEARNING,
                'enable_query_optimization': config_uqe.ENABLE_QUERY_OPTIMIZATION,
                'optimizer_budget': config_uqe.OPTIMIZER_BUDGET,
            }
            logger.info(f"Optimization config: {opt_config}")
        except Exception as e:
            logger.warning(f"Could not load full optimization config: {e}")
    
    # Execute queries
    successful_queries = 0
    failed_queries = 0
    
    for query_name, query in tqdm(query_dict.items(), desc="Executing queries"):
        try:
            logger.info(f"\n{'='*70}")
            logger.info(f"Query: {query_name}")
            logger.info(f"{'='*70}")
            
            # Parse query
            parsed_query = parser(query)
            
            # Create plan
            plan, invalid = planner(parsed_query, source_data)
            if invalid:
                logger.warning(f"Invalid query: {query_name}")
                failed_queries += 1
                continue
            
            assert plan is not None
            logger.info(f"Plan created with operators")
            
            # Apply basic optimizer
            optimized_plan = optimizer(plan)
            
            # Execute with optimizations
            if enable_opts and embeddings is not None:
                logger.info("Executing with UQE OPTIMIZATIONS")
                result = optimized_executor(
                    optimized_plan,
                    embeddings=embeddings,
                    source_data=source_data,
                    enable_optimizations=True,
                    **opt_config
                )
            else:
                logger.info("Executing without optimizations (BASELINE)")
                result = optimized_executor(
                    optimized_plan,
                    enable_optimizations=False
                )
            
            # Save results
            os.makedirs(os.path.join(result_dir, query_name), exist_ok=True)
            output_file = os.path.join(result_dir, query_name, f"{query_name}.csv")
            
            if result is not None:
                result.to_csv(output_file, index=False, encoding='utf-8')
                logger.info(f"✓ Results saved: {query_name}.csv ({len(result)} rows)")
                successful_queries += 1
            else:
                logger.warning(f"✗ Query returned empty result: {query_name}")
                failed_queries += 1
        
        except Exception as e:
            logger.error(f"✗ Error executing query {query_name}: {e}", exc_info=True)
            failed_queries += 1
    
    # Print summary
    logger.info("\n" + "=" * 70)
    logger.info("EXECUTION SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Dataset: disease")
    logger.info(f"Query type: {query_type}")
    logger.info(f"Optimizations: {'ENABLED' if enable_opts else 'DISABLED'}")
    logger.info(f"Results saved to: {result_dir}")
    logger.info(f"Successful queries: {successful_queries}")
    logger.info(f"Failed queries: {failed_queries}")
    logger.info(f"Total queries: {successful_queries + failed_queries}")
    logger.info("=" * 70)
    
    return successful_queries, failed_queries


if __name__ == '__main__':
    import sys
    
    query_type = "SF"  # Default query type
    if len(sys.argv) > 1:
        query_type = sys.argv[1]
    
    # Run with config setting
    main(query_type)
