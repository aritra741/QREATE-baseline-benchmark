"""
UQE Optimization Integration
Connects sampling, active learning, and query optimization
to the existing operator execution model.
"""

import numpy as np
import logging
from active_learning import ActiveLearner, StratifiedSampler
from query_optimizer import QueryOptimizer

logger = logging.getLogger('UQE.optimization')
if not logger.handlers:
    import sys
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('[UQE-OPTIMIZATION] %(levelname)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)


class OptimizedFilterOperator:
    """
    Enhanced filter operator that uses stratified sampling and active learning
    to reduce LLM calls while maintaining accuracy.
    """
    
    def __init__(self, embeddings, cluster_dict, n_rows, budget=128, 
                 is_aggregation=False):
        """
        Args:
            embeddings: pre-computed embeddings for all rows
            cluster_dict: clustering result for stratified sampling
            n_rows: total number of rows
            budget: LLM call budget
            is_aggregation: True for aggregation queries, False for retrieval
        """
        self.embeddings = embeddings
        self.cluster_dict = cluster_dict
        self.n_rows = n_rows
        self.budget = budget
        self.is_aggregation = is_aggregation
        
        if is_aggregation:
            self.sampler = StratifiedSampler(embeddings, cluster_dict, n_rows)
        else:
            self.sampler = ActiveLearner(embeddings, budget=budget)
        
        logger.info(f"Created OptimizedFilterOperator (aggregation={is_aggregation}, "
                   f"budget={budget})")
    
    def apply_filter_aggregation(self, llm_filter_fn, sample_size_ratio=0.1):
        """
        Apply filter for aggregation queries using stratified sampling.
        
        Returns unbiased estimate with reduced variance.
        """
        logger.info("Applying filter with stratified sampling for aggregation")
        
        # Get stratified sample
        sample_size = max(1, int(self.n_rows * sample_size_ratio))
        sampled_indices = self._get_stratified_sample(sample_size)
        
        logger.info(f"Querying {len(sampled_indices)} rows (from {self.n_rows} total)")
        
        # Query LLM for sampled rows
        responses = np.zeros(len(sampled_indices))
        for i, row_idx in enumerate(sampled_indices):
            try:
                responses[i] = llm_filter_fn(row_idx)
            except Exception as e:
                logger.error(f"Error querying row {row_idx}: {e}")
                responses[i] = 0
        
        # Estimate total count using stratified sampling
        estimated_count = self.sampler.estimate_count(sampled_indices, responses)
        
        return estimated_count, sampled_indices, responses
    
    def apply_filter_retrieval(self, llm_filter_fn):
        """
        Apply filter for retrieval queries using active learning.
        
        Returns all rows that satisfy condition within budget.
        """
        logger.info("Applying filter with active learning for retrieval")
        
        # Run active learning to find positive rows
        positive_rows = self.sampler.run_active_learning(llm_filter_fn)
        
        logger.info(f"Retrieved {len(positive_rows)} rows satisfying condition")
        
        return positive_rows
    
    def _get_stratified_sample(self, sample_size):
        """
        Get a stratified random sample from clusters.
        """
        sampled_indices = []
        
        for cluster_id, cluster_rows in self.cluster_dict.items():
            cluster_sample_size = max(1, int(sample_size / len(self.cluster_dict)))
            if len(cluster_rows) < cluster_sample_size:
                sample = cluster_rows
            else:
                sample = np.random.choice(cluster_rows, cluster_sample_size, replace=False)
            sampled_indices.extend(sample)
        
        return np.array(sampled_indices)


class OptimizedQueryExecutor:
    """
    Enhanced query executor that uses optimizer to select best execution plan.
    """
    
    def __init__(self, data_schema, budget=128):
        """
        Args:
            data_schema: schema object with data and metadata
            budget: LLM call budget
        """
        self.data_schema = data_schema
        self.budget = budget
        self.optimizer = QueryOptimizer(budget=budget)
        
        logger.info(f"Created OptimizedQueryExecutor with budget={budget}")
    
    def build_operators(self, parsed_query):
        """
        Convert parsed query to operator representations for optimization.
        
        Args:
            parsed_query: tuple of (select, from, where, group_by, order_by, limit)
            
        Returns:
            operators: list of operator dicts for optimization
        """
        select, from_, where, group_by, order_by, limit = parsed_query
        
        operators = []
        
        if from_:
            operators.append({
                'type': 'SCAN',
                'table': from_,
            })
        
        if where:
            # Determine if WHERE clause is structured or unstructured
            is_structured = self._is_structured_where(where)
            operators.append({
                'type': 'WHERE',
                'condition': where,
                'is_structured': is_structured,
            })
        
        if select:
            operators.append({
                'type': 'SELECT',
                'columns': select,
            })
        
        if group_by:
            operators.append({
                'type': 'GROUP_BY',
                'keys': group_by,
            })
        
        if order_by:
            operators.append({
                'type': 'ORDER_BY',
                'columns': order_by,
            })
        
        if limit:
            operators.append({
                'type': 'LIMIT',
                'limit': limit,
            })
        
        return operators
    
    def _is_structured_where(self, where_clause):
        """
        Check if WHERE clause involves only structured columns.
        """
        # TODO: Implement based on data schema
        # For now, assume all are unstructured
        return False
    
    def optimize_query(self, parsed_query, input_size):
        """
        Optimize query execution plan.
        
        Args:
            parsed_query: tuple of (select, from, where, group_by, order_by, limit)
            input_size: size of input table
            
        Returns:
            optimized_plan: best execution plan
        """
        operators = self.build_operators(parsed_query)
        optimized_plan = self.optimizer.optimize(operators, input_size)
        
        return optimized_plan
    
    def is_aggregation_query(self, parsed_query):
        """
        Determine if query is aggregation or non-aggregation.
        
        Aggregation queries have GROUP BY or aggregate functions in SELECT.
        """
        select, _, _, group_by, _, _ = parsed_query
        
        has_group_by = group_by is not None
        has_aggregate = any(agg in str(select).upper() 
                           for agg in ['COUNT', 'SUM', 'AVG', 'MIN', 'MAX'])
        
        return has_group_by or has_aggregate


class OptimizationManager:
    """
    High-level manager for query optimizations.
    Orchestrates sampling, active learning, and plan optimization.
    """
    
    def __init__(self, data_schema, embeddings, cluster_dict, budget=128):
        """
        Args:
            data_schema: schema object
            embeddings: pre-computed embeddings for all rows
            cluster_dict: clustering result
            budget: LLM call budget
        """
        self.data_schema = data_schema
        self.embeddings = embeddings
        self.cluster_dict = cluster_dict
        self.budget = budget
        self.n_rows = len(embeddings)
        
        self.query_executor = OptimizedQueryExecutor(data_schema, budget)
        
        logger.info(f"Created OptimizationManager with {self.n_rows} rows, budget={budget}")
    
    def optimize_and_execute(self, parsed_query, base_executor, llm_filter_fn):
        """
        Full optimization and execution pipeline.
        
        Args:
            parsed_query: parsed SQL query
            base_executor: base executor for non-optimized operations
            llm_filter_fn: function to query LLM for rows
            
        Returns:
            result: query execution result
        """
        logger.info(f"\n{'='*60}")
        logger.info("Starting optimized query execution")
        logger.info(f"{'='*60}")
        
        # Step 1: Optimize query plan
        optimized_plan = self.query_executor.optimize_query(parsed_query, self.n_rows)
        
        # Step 2: Determine query type
        is_aggregation = self.query_executor.is_aggregation_query(parsed_query)
        logger.info(f"Query type: {'aggregation' if is_aggregation else 'retrieval'}")
        
        # Step 3: Create optimized filter operator
        filter_op = OptimizedFilterOperator(
            self.embeddings,
            self.cluster_dict,
            self.n_rows,
            budget=self.budget,
            is_aggregation=is_aggregation
        )
        
        # Step 4: Apply optimized filtering
        if is_aggregation:
            result, sampled_indices, responses = filter_op.apply_filter_aggregation(
                llm_filter_fn,
                sample_size_ratio=0.2
            )
            logger.info(f"Aggregation result: {result}")
        else:
            result = filter_op.apply_filter_retrieval(llm_filter_fn)
            logger.info(f"Retrieval result: {len(result)} rows found")
        
        return result
    
    def get_statistics(self):
        """Return optimization statistics."""
        return {
            'n_rows': self.n_rows,
            'n_clusters': len(self.cluster_dict),
            'budget': self.budget,
            'embeddings_shape': self.embeddings.shape,
        }
