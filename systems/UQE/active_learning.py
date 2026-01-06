"""
Online Active Learning for Non-Aggregation Queries
Implements Algorithm 2 from UQE paper: online learning to find relevant rows
while minimizing LLM calls within a token budget.
"""

import numpy as np
import logging
from sklearn.linear_model import LogisticRegression
from collections import defaultdict

logger = logging.getLogger('UQE.active_learning')
if not logger.handlers:
    import sys
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('[UQE-ACTIVE-LEARNING] %(levelname)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)


class ActiveLearner:
    """
    Online active learning for semantic retrieval queries.
    Maintains a surrogate model that predicts which rows satisfy a condition,
    and iteratively selects the most informative rows to query via LLM.
    
    Based on Algorithm 2 from the UQE paper.
    """
    
    def __init__(self, embeddings, budget=128, n_batches=4, exploration_decay=0.95):
        """
        Args:
            embeddings: numpy array of shape (n_rows, embedding_dim)
            budget: total number of LLM calls allowed
            n_batches: number of batches for iterative sampling
            exploration_decay: decay rate for exploration noise
        """
        self.embeddings = embeddings
        self.n_rows = embeddings.shape[0]
        self.budget = budget
        self.n_batches = n_batches
        self.budget_per_batch = budget // n_batches
        self.exploration_decay = exploration_decay
        
        # Initialize surrogate model prediction scores uniformly
        self.surrogate_scores = np.random.uniform(0, 1, self.n_rows)
        self.surrogate_model = None
        
        # Track which rows have been queried
        self.queried_mask = np.zeros(self.n_rows, dtype=bool)
        self.labels = {}  # row_idx -> {0, 1} (does not satisfy, satisfies)
        
        logger.info(f"Initialized ActiveLearner with {self.n_rows} rows, budget={budget}")
    
    def select_batch(self, batch_num, noise_scale=0.1):
        """
        Select a batch of rows to query next.
        Uses UCB-like strategy: argmax(surrogate_score + exploration_noise)
        """
        logger.info(f"Selecting batch {batch_num + 1}/{self.n_batches}")
        
        # Exploration noise decays over batches
        exploration_factor = noise_scale * (self.exploration_decay ** batch_num)
        
        # Compute selection scores: surrogate + exploration
        unqueried_mask = ~self.queried_mask
        scores = np.full(self.n_rows, -np.inf)
        scores[unqueried_mask] = (
            self.surrogate_scores[unqueried_mask] + 
            exploration_factor * np.random.randn(np.sum(unqueried_mask))
        )
        
        # Select top budget_per_batch rows
        selected_indices = np.argsort(-scores)[:self.budget_per_batch]
        selected_indices = selected_indices[unqueried_mask[selected_indices]]
        
        logger.debug(f"Selected {len(selected_indices)} rows in batch {batch_num + 1}")
        logger.debug(f"Top scores: min={scores[selected_indices].min():.4f}, max={scores[selected_indices].max():.4f}")
        
        return selected_indices
    
    def update_surrogate_model(self):
        """
        Refit the surrogate model using queried samples.
        Uses logistic regression to predict satisfaction likelihood.
        """
        logger.info("Updating surrogate model")
        
        if len(self.labels) < 2:
            logger.warning(f"Not enough labeled data ({len(self.labels)}) to update model, skipping")
            return
        
        # Prepare training data
        queried_indices = np.array(list(self.labels.keys()))
        X_train = self.embeddings[queried_indices]
        y_train = np.array([self.labels[idx] for idx in queried_indices])
        
        logger.debug(f"Training on {len(queried_indices)} samples: {np.sum(y_train)} positive, {np.sum(y_train == 0)} negative")
        
        try:
            # Train logistic regression as surrogate
            self.surrogate_model = LogisticRegression(max_iter=1000)
            self.surrogate_model.fit(X_train, y_train)
            
            # Update scores for all rows based on posterior probability
            self.surrogate_scores = self.surrogate_model.predict_proba(self.embeddings)[:, 1]
            
            logger.debug(f"Surrogate scores updated: min={self.surrogate_scores.min():.4f}, max={self.surrogate_scores.max():.4f}")
        except Exception as e:
            logger.error(f"Error updating surrogate model: {e}")
    
    def record_label(self, row_idx, label):
        """
        Record the LLM response for a queried row.
        
        Args:
            row_idx: index of the row
            label: 1 if satisfies condition, 0 otherwise
        """
        if self.queried_mask[row_idx]:
            logger.warning(f"Row {row_idx} already queried, skipping duplicate")
            return
        
        self.queried_mask[row_idx] = True
        self.labels[row_idx] = label
        logger.debug(f"Recorded label for row {row_idx}: {label}")
    
    def get_positive_rows(self):
        """Return indices of rows that were labeled as positive (satisfy condition)."""
        return sorted([idx for idx, label in self.labels.items() if label == 1])
    
    def get_remaining_rows(self):
        """Return indices of rows that haven't been queried yet."""
        return np.where(~self.queried_mask)[0]
    
    def run_active_learning(self, llm_filter_fn):
        """
        Execute the full active learning loop.
        
        Args:
            llm_filter_fn: function(row_idx) -> bool that queries LLM for a row
            
        Returns:
            List of row indices that satisfy the condition
        """
        logger.info("Starting active learning loop")
        
        for batch_num in range(self.n_batches):
            logger.info(f"\n{'='*60}")
            logger.info(f"Batch {batch_num + 1}/{self.n_batches}")
            logger.info(f"{'='*60}")
            
            # Select rows to query in this batch
            batch_indices = self.select_batch(batch_num)
            
            if len(batch_indices) == 0:
                logger.warning("No more rows to query")
                break
            
            # Query LLM for each selected row
            logger.info(f"Querying {len(batch_indices)} rows")
            for row_idx in batch_indices:
                try:
                    label = llm_filter_fn(row_idx)
                    self.record_label(row_idx, label)
                except Exception as e:
                    logger.error(f"Error querying row {row_idx}: {e}")
                    self.queried_mask[row_idx] = True  # Mark as queried to avoid retry
            
            # Update surrogate model for next batch
            if batch_num < self.n_batches - 1:
                self.update_surrogate_model()
            
            # Summary
            num_positive = len(self.get_positive_rows())
            num_queried = np.sum(self.queried_mask)
            logger.info(f"Batch summary: {num_positive} positive out of {num_queried} queried")
        
        positive_rows = self.get_positive_rows()
        logger.info(f"\nActive learning complete. Found {len(positive_rows)} rows satisfying condition")
        
        return positive_rows


class StratifiedSampler:
    """
    Stratified sampling for aggregation queries.
    Implements Algorithm 1 from UQE paper: uses embeddings and clustering
    to reduce variance of aggregation estimates.
    """
    
    def __init__(self, embeddings, cluster_dict, n_rows):
        """
        Args:
            embeddings: numpy array of shape (n_rows, embedding_dim)
            cluster_dict: dict mapping cluster_id -> array of row indices
            n_rows: total number of rows in dataset
        """
        self.embeddings = embeddings
        self.cluster_dict = cluster_dict
        self.n_rows = n_rows
        self.n_clusters = len(cluster_dict)
        
        logger.info(f"Initialized StratifiedSampler with {self.n_rows} rows, {self.n_clusters} clusters")
    
    def get_importance_weights(self, sampled_indices):
        """
        Compute importance weights for sampled rows.
        
        weight_i = |C_cluster(i)| / |S_cluster(i)|
        
        where C_cluster(i) is total size of cluster i, S_cluster(i) is sampled size.
        
        Args:
            sampled_indices: array of sampled row indices
            
        Returns:
            weights: array of importance weights for sampled rows
        """
        weights = np.ones(len(sampled_indices))
        
        # Count samples per cluster
        sampled_per_cluster = defaultdict(int)
        row_to_cluster = {}
        
        for cluster_id, cluster_rows in self.cluster_dict.items():
            for row_idx in cluster_rows:
                # Convert to int to ensure consistent types
                row_to_cluster[int(row_idx)] = cluster_id
        
        # Track rows not in any cluster
        unmapped_count = 0
        
        for i, row_idx in enumerate(sampled_indices):
            # Convert numpy int to Python int for dict lookup
            row_idx_int = int(row_idx)
            if row_idx_int not in row_to_cluster:
                # Row not in any cluster, assign it to a default cluster
                # Use uniform weight for unmapped rows
                unmapped_count += 1
                continue
            cluster_id = row_to_cluster[row_idx_int]
            sampled_per_cluster[cluster_id] += 1
        
        # Compute weights
        for i, row_idx in enumerate(sampled_indices):
            # Convert numpy int to Python int for dict lookup
            row_idx_int = int(row_idx)
            if row_idx_int not in row_to_cluster:
                # Unmapped rows get uniform weight
                weights[i] = 1.0
            else:
                cluster_id = row_to_cluster[row_idx_int]
                cluster_size = len(self.cluster_dict[cluster_id])
                sampled_size = sampled_per_cluster[cluster_id]
                
                if sampled_size > 0:
                    weights[i] = cluster_size / sampled_size
        
        # Normalize weights to sum to number of samples
        weights = weights / weights.sum() * len(sampled_indices)
        
        if unmapped_count > 0:
            logger.debug(f"Warning: {unmapped_count}/{len(sampled_indices)} sampled rows not in any cluster")
        
        logger.debug(f"Computed weights for {len(sampled_indices)} samples: "
                    f"min={weights.min():.4f}, max={weights.max():.4f}, mean={weights.mean():.4f}")
        
        return weights
    
    def estimate_count(self, sampled_indices, llm_responses):
        """
        Estimate count of rows satisfying condition using stratified sampling.
        
        Implements unbiased estimator from Equation 3:
        E[count] ≈ (1/|S|) * sum_i (w_i * f(row_i))
        
        Args:
            sampled_indices: array of sampled row indices
            llm_responses: array of binary LLM responses (0 or 1)
            
        Returns:
            estimated_count: unbiased estimate of total count (as Python float)
        """
        if len(sampled_indices) == 0:
            logger.warning("No samples provided for estimation")
            return 0.0
        
        weights = self.get_importance_weights(sampled_indices)
        
        # Compute weighted average
        weighted_sum = np.sum(weights * llm_responses)
        sample_size = len(sampled_indices)
        
        # Estimate total count
        estimated_count = float((weighted_sum / sample_size) * self.n_rows)
        
        logger.info(f"Estimated count: {estimated_count:.2f} "
                   f"(from {len(sampled_indices)} samples, {np.sum(llm_responses)} positive)")
        
        return estimated_count
    
    def estimate_sum(self, sampled_indices, llm_responses, values):
        """
        Estimate sum of values for rows satisfying condition.
        
        Args:
            sampled_indices: array of sampled row indices
            llm_responses: array of binary LLM responses
            values: array of values to sum
            
        Returns:
            estimated_sum: unbiased estimate of total sum
        """
        if len(sampled_indices) == 0:
            logger.warning("No samples provided for estimation")
            return 0
        
        weights = self.get_importance_weights(sampled_indices)
        
        # Compute weighted average of values
        weighted_sum = np.sum(weights * llm_responses * values)
        sample_size = len(sampled_indices)
        
        # Estimate total sum
        estimated_sum = (weighted_sum / sample_size) * self.n_rows
        
        logger.info(f"Estimated sum: {estimated_sum:.2f} "
                   f"(from {len(sampled_indices)} samples)")
        
        return estimated_sum
