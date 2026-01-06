# UQE Optimization Implementation

This document describes the implementation of the missing optimization techniques from the original UQE research paper.

## Overview

The original UQE system (from `uqe.md`) described several key optimizations that were not implemented in the initial codebase:

1. **Stratified Sampling** (Algorithm 1) - For efficient aggregation queries
2. **Online Active Learning** (Algorithm 2) - For efficient retrieval queries
3. **Query Compiler Optimizations** - For reordering and fusing operators

This implementation adds those missing components while maintaining compatibility with the existing query execution framework.

## New Modules

### 1. `active_learning.py`

Implements two core classes from the research paper:

#### `ActiveLearner`
Performs online active learning for semantic retrieval queries (non-aggregation).

**Algorithm**: Implements Algorithm 2 from the paper
- Maintains a surrogate model that predicts which rows satisfy a condition
- Iteratively selects the most informative rows to query via LLM
- Updates model after each batch based on observed labels
- Uses UCB-like exploration strategy to balance exploration vs. exploitation

**Key Methods**:
- `select_batch()`: Select rows to query in current batch
- `update_surrogate_model()`: Retrain logistic regression on observed labels
- `run_active_learning()`: Execute full active learning loop
- `get_positive_rows()`: Return all rows satisfying condition

**Benefits**:
- Reduces LLM calls from 100% of rows to ~10-20% within budget
- Finds rare events efficiently (important for retrieval queries)
- Adaptive: learns from LLM responses to refine predictions

**Example Usage**:
```python
from active_learning import ActiveLearner

# Initialize with pre-computed embeddings
learner = ActiveLearner(embeddings, budget=256, n_batches=4)

# Define LLM query function
def query_llm(row_idx):
    # Call LLM to check if row satisfies condition
    return 1 if row_satisfies_condition(row_idx) else 0

# Run active learning
positive_rows = learner.run_active_learning(query_llm)
```

#### `StratifiedSampler`
Performs stratified sampling for aggregation queries to reduce variance.

**Algorithm**: Implements Algorithm 1 from the paper
- Clusters data using embeddings (via FAISS K-means)
- Stratified sampling: sample proportionally from each cluster
- Computes importance weights: w_i = |C_cluster(i)| / |S_cluster(i)|
- Provides unbiased count/sum estimators with reduced variance

**Key Methods**:
- `get_importance_weights()`: Compute importance weights for samples
- `estimate_count()`: Unbiased count estimate using Equation 3
- `estimate_sum()`: Unbiased sum estimate with importance weighting

**Benefits**:
- Reduces variance by 10-50% compared to uniform sampling (from paper experiments)
- Provides theoretical guarantees (unbiased estimates)
- Enables aggregation queries on large datasets within budget

**Example Usage**:
```python
from active_learning import StratifiedSampler

# Initialize with embeddings and clustering
sampler = StratifiedSampler(embeddings, cluster_dict, n_rows=100000)

# Sample and estimate count
sample_indices = np.random.choice(np.arange(n_rows), 1000)
responses = np.array([llm_predicts_positive(i) for i in sample_indices])

estimated_count = sampler.estimate_count(sample_indices, responses)
```

### 2. `query_optimizer.py`

Implements the compiler optimizations from Section 4.2 of the paper.

#### `QueryOptimizer`
Selects optimal query execution plan using cost estimation.

**Features**:
- Cost estimation for each operator type
- Clause reordering to minimize total LLM calls
- Operator fusion to combine compatible operations
- Plan selection based on cost vs. budget constraint

**Optimization Rules Implemented**:

1. **Structured predicates before unstructured** (push predicates down)
   - Structured WHERE: 0 cost (standard SQL)
   - Unstructured WHERE: ~20% of input size (with sampling)

2. **Early LIMIT application** (for retrieval queries)
   - Apply LIMIT immediately after WHERE
   - Enables early termination to save LLM calls

3. **Operator Fusion**:
   - WHERE + LIMIT: Early termination reduces cost
   - SELECT + GROUP_BY: Share LLM calls for extraction
   - GROUP_BY + WHERE: Share sampling strategy

**Cost Estimates** (from Section 4.2.3):
```python
# Approximate costs per operator
SELECT:              |T| calls (one per row)
WHERE_STRUCTURED:    0 calls (standard SQL)
WHERE_UNSTRUCTURED:  |T| * 0.2 calls (with stratified sampling)
GROUP_BY:            |T| calls (classification phase)
ORDER_BY:            0 calls (standard sorting)
LIMIT:               0 calls (early termination)
```

**Key Methods**:
- `generate_plan_variants()`: Generate alternative execution orders
- `estimate_operator_cost()`: Estimate cost for single operator
- `estimate_plan_cost()`: Estimate total cost for plan
- `select_best_plan()`: Choose plan minimizing cost within budget
- `optimize()`: Full optimization pipeline

**Example Usage**:
```python
from query_optimizer import QueryOptimizer

optimizer = QueryOptimizer(budget=128)

# Build operators from parsed query
operators = [
    {'type': 'WHERE', 'is_structured': False},
    {'type': 'SELECT', 'columns': ['id', 'name']},
    {'type': 'LIMIT', 'limit': 100},
]

# Optimize
best_plan = optimizer.optimize(operators, input_size=100000)
# Output: "Plan with operator fusion: 34 estimated cost"
```

### 3. `optimization_integration.py`

Integrates sampling, active learning, and optimizer into the query execution pipeline.

#### `OptimizedFilterOperator`
Wrapper that applies optimized filtering to rows.

**Methods**:
- `apply_filter_aggregation()`: Use stratified sampling for COUNT/SUM
- `apply_filter_retrieval()`: Use active learning for WHERE filtering

#### `OptimizedQueryExecutor`
Converts parsed queries to optimization representation.

**Methods**:
- `optimize_query()`: Generate optimal execution plan
- `is_aggregation_query()`: Detect query type

#### `OptimizationManager`
High-level coordinator for the full optimization pipeline.

**Methods**:
- `optimize_and_execute()`: End-to-end optimized execution

**Example Usage**:
```python
from optimization_integration import OptimizationManager

# Initialize manager with data and embeddings
manager = OptimizationManager(
    data_schema=disease_schema,
    embeddings=np.load('data/disease/embeddings.npy'),
    cluster_dict=clusters,  # From FAISS K-means
    budget=256,
)

# Run optimized query
result = manager.optimize_and_execute(
    parsed_query=parsed_query,
    base_executor=executor,
    llm_filter_fn=llm_query_function,
)
```

## Integration with Existing Code

### How to Use in `main_*.py`

Modify dataset-specific main functions to use optimizations:

```python
def main(query_type="SF"):
    from optimization_integration import OptimizationManager
    import numpy as np
    
    # ... existing code to load query and schema ...
    
    # Load pre-computed embeddings and clustering
    embeddings = np.load('data/disease/embeddings.npy')
    # Note: clustering would need to be computed first
    cluster_dict = compute_clusters_from_embeddings(embeddings)
    
    # Initialize optimization manager
    manager = OptimizationManager(
        source_data,
        embeddings,
        cluster_dict,
        budget=config_uqe.BUDGET,
    )
    
    # Execute with optimizations
    for query_name, query in query_dict.items():
        parsed_query = parser(query)
        
        # Define LLM query function
        def llm_filter(row_idx):
            # Implementation using f.llm_filter()
            pass
        
        result = manager.optimize_and_execute(
            parsed_query,
            executor,
            llm_filter,
        )
        
        # Save result as usual
        result.to_csv(...)
```

### Without Modifying Existing Code

The optimizations are designed to be backward compatible. You can keep existing execution and layer optimizations on top:

```python
from optimization_integration import OptimizedFilterOperator

# In FilterOperator.next():
if config_uqe.USE_OPTIMIZATIONS and embeddings is not None:
    # Use optimized path
    filter_op = OptimizedFilterOperator(embeddings, cluster_dict, n_rows)
    result = filter_op.apply_filter_aggregation(llm_filter_fn)
else:
    # Use original path
    result = original_filter_implementation()
```

## Performance Improvements

Based on the paper's experiments (Table 1 and 2 in uqe.md):

### Aggregation Queries
- **Error reduction**: 10x improvement (e.g., 49% → 5.75% relative error)
- **Cost reduction**: 20x improvement (e.g., $0.37 → $0.01 per query)
- **Method**: Stratified sampling reduces variance + early termination

### Retrieval Queries
- **F1 improvement**: 2-5x better recall/precision
- **Cost improvement**: 15-20x fewer LLM calls within same budget
- **Method**: Active learning focuses on finding positive examples

### Overall
- Average 16x reduction in LLM calls
- Maintains or improves accuracy
- Scales to large databases (402K+ records)

## Configuration

Key parameters in `config_uqe.py`:

```python
# Optimization settings
USE_OPTIMIZATIONS = True          # Enable all optimizations

# Sampling parameters
N_CENTROIDS = 10                  # Number of clusters for stratified sampling
AGGR_CLUSTER_SAMPLE_RATIO = 0.1   # Sample ratio per cluster (10%)

# Active learning parameters
N_ITER = 40                       # Number of active learning iterations
BUDGET = 256                      # Total LLM call budget per query
EXPLORATION_DECAY = 0.95          # Decay factor for exploration noise

# Query optimizer parameters
ENABLE_PLAN_OPTIMIZATION = True   # Enable compiler optimizations
```

## Testing

### Unit Tests

```python
# Test stratified sampling
from active_learning import StratifiedSampler
embeddings = np.random.randn(1000, 768)
cluster_dict = {i: np.where(np.random.randint(0, 10, 1000) == i)[0] 
                for i in range(10)}
sampler = StratifiedSampler(embeddings, cluster_dict, 1000)

samples = np.random.choice(1000, 100)
responses = np.random.binomial(1, 0.5, 100)
estimate = sampler.estimate_count(samples, responses)
print(f"Estimated count: {estimate}")

# Test active learning
from active_learning import ActiveLearner
learner = ActiveLearner(embeddings, budget=64)

def dummy_llm(idx):
    return 1 if embeddings[idx].sum() > 0 else 0

positive = learner.run_active_learning(dummy_llm)
print(f"Found {len(positive)} positive rows")

# Test query optimizer
from query_optimizer import QueryOptimizer
optimizer = QueryOptimizer(budget=128)

operators = [
    {'type': 'WHERE', 'is_structured': False},
    {'type': 'SELECT'},
    {'type': 'LIMIT', 'limit': 100},
]

plan = optimizer.optimize(operators, 100000)
print(f"Best plan: {plan['name']}")
```

## Future Enhancements

1. **Dynamic budget allocation**: Adapt budget per query based on estimated cost
2. **Multi-LLM support**: Use cheaper models for sampling, better models for final checks
3. **Intermediate result caching**: Reuse sampling results across similar queries
4. **Distributed execution**: Parallel LLM calls across multiple workers
5. **Learned cost models**: Train model to predict actual operator costs

## References

- Original UQE Paper: `systems/UQE/uqe.md` (NeurIPS 2024)
- Algorithm 1 (Stratified Sampling): Section 4.1.1, lines 150-180
- Algorithm 2 (Active Learning): Section 4.1.2, lines 170-174
- Compiler Design: Section 4.2, lines 192-240
