"""
Query Plan Optimizer
Implements compiler optimizations from UQE paper:
- Clause reordering
- Operator fusion
- Cost estimation and plan selection
"""

import logging
from itertools import permutations

logger = logging.getLogger('UQE.query_optimizer')
if not logger.handlers:
    import sys
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('[UQE-OPTIMIZER] %(levelname)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)


class QueryOptimizer:
    """
    Optimizes query execution plans by:
    1. Reordering clauses to minimize LLM calls
    2. Fusing compatible operators
    3. Selecting cheapest execution plan
    """
    
    def __init__(self, budget=128):
        """
        Args:
            budget: token budget constraint (approximately, LLM calls)
        """
        self.budget = budget
        logger.info(f"Initialized QueryOptimizer with budget={budget}")
    
    def estimate_operator_cost(self, operator, input_size):
        """
        Estimate cost (number of LLM calls) for an operator.
        
        Costs (from UQE paper Section 4.2.3):
        - SELECT: |T| calls (one per row)
        - WHERE (structured): 0 calls (no LLM needed)
        - WHERE (unstructured): depends on sampling strategy
        - GROUP BY: |T| calls for classification (taxonomy already built)
        - ORDER BY: 0 calls (standard sorting)
        - LIMIT: 0 calls if applied after WHERE (early termination)
        """
        costs = {
            'SELECT': input_size,  # One LLM call per row
            'WHERE_UNSTRUCTURED': max(1, int(input_size * 0.2)),  # Sampling reduces cost
            'WHERE_STRUCTURED': 0,  # No LLM needed
            'GROUP_BY': input_size,  # Classification of samples
            'ORDER_BY': 0,  # Standard sorting
            'LIMIT': 0,  # No cost
            'SCAN': 0,  # Just load data
        }
        return costs
    
    def can_fuse_operators(self, op1, op2):
        """
        Check if two operators can be fused to reduce cost.
        
        Valid fusions (from UQE paper Section 4.2.2):
        - WHERE + LIMIT: can terminate early for non-aggregation queries
        - SELECT + GROUP_BY: both use same LLM call for extraction + classification
        - GROUP_BY + WHERE: can share same sampling proposal
        """
        valid_fusions = [
            ('WHERE', 'LIMIT'),
            ('SELECT', 'GROUP_BY'),
            ('GROUP_BY', 'WHERE'),
        ]
        
        fusion_key = (op1['type'], op2['type'])
        return fusion_key in valid_fusions
    
    def estimate_fused_cost(self, op1, op2, input_size):
        """
        Estimate cost of fused operator.
        
        Fusions reduce cost:
        - WHERE + LIMIT: use query budget for early termination
        - SELECT + GROUP_BY: share input tokens, cost = GROUP_BY alone
        - GROUP_BY + WHERE: share sampling, amortize cost
        """
        if (op1['type'], op2['type']) == ('WHERE', 'LIMIT'):
            # Early termination benefit: only process up to LIMIT rows
            limit_val = op2.get('limit', input_size)
            return max(1, int(limit_val * 0.2))  # Rough estimate with sampling
        
        elif (op1['type'], op2['type']) == ('SELECT', 'GROUP_BY'):
            # Shared LLM call: cost = max(SELECT, GROUP_BY)
            return input_size  # GROUP_BY cost dominates
        
        elif (op1['type'], op2['type']) == ('GROUP_BY', 'WHERE'):
            # Shared sampling: amortize cost
            return int(input_size * 0.6)
        
        else:
            # Default: sum of costs
            costs = self.estimate_operator_cost(op1, input_size) + \
                   self.estimate_operator_cost(op2, input_size)
            return costs
    
    def generate_plan_variants(self, operators):
        """
        Generate alternative query execution plans.
        
        For each valid clause ordering:
        1. Try original order
        2. Apply optimizer rules (e.g., push filters down, move LIMIT early)
        3. Try operator fusions
        """
        plans = []
        
        # Plan 1: Original order
        plans.append({
            'operators': operators,
            'name': 'Original order',
        })
        
        # Plan 2: Apply optimization rules
        optimized = self._apply_optimization_rules(operators)
        if optimized != operators:
            plans.append({
                'operators': optimized,
                'name': 'With optimization rules',
            })
        
        # Plan 3: Try operator fusions
        fused = self._apply_operator_fusion(operators)
        if len(fused) < len(operators):  # Fusion happened
            plans.append({
                'operators': fused,
                'name': 'With operator fusion',
            })
        
        logger.info(f"Generated {len(plans)} query execution plans")
        return plans
    
    def _apply_optimization_rules(self, operators):
        """
        Apply classical query optimization rules:
        - Push predicates down (apply structured filters before unstructured)
        - Early LIMIT application
        - Eliminate redundant operations
        """
        optimized = []
        
        # Collect different types of operators
        structured_where = []
        unstructured_where = []
        select_ops = []
        group_by_ops = []
        order_by_ops = []
        limit_ops = []
        others = []
        
        for op in operators:
            if op['type'] == 'WHERE':
                if op.get('is_structured', False):
                    structured_where.append(op)
                else:
                    unstructured_where.append(op)
            elif op['type'] == 'SELECT':
                select_ops.append(op)
            elif op['type'] == 'GROUP_BY':
                group_by_ops.append(op)
            elif op['type'] == 'ORDER_BY':
                order_by_ops.append(op)
            elif op['type'] == 'LIMIT':
                limit_ops.append(op)
            else:
                others.append(op)
        
        # Reorder: structured WHERE first (cheaper), then unstructured WHERE
        optimized.extend(structured_where)
        
        # Apply LIMIT early if present (for non-aggregation queries)
        if limit_ops and not group_by_ops:
            optimized.extend(limit_ops)
        
        optimized.extend(unstructured_where)
        optimized.extend(select_ops)
        optimized.extend(group_by_ops)
        
        if limit_ops and group_by_ops:
            optimized.extend(limit_ops)
        
        optimized.extend(order_by_ops)
        optimized.extend(others)
        
        return optimized
    
    def _apply_operator_fusion(self, operators):
        """
        Apply operator fusion to reduce LLM calls.
        """
        fused = []
        skip_next = False
        
        for i, op in enumerate(operators):
            if skip_next:
                skip_next = False
                continue
            
            if i + 1 < len(operators):
                next_op = operators[i + 1]
                if self.can_fuse_operators(op, next_op):
                    # Create fused operator
                    fused_op = {
                        'type': f'{op["type"]}+{next_op["type"]}',
                        'original_ops': [op, next_op],
                        **{k: v for k, v in op.items() if k not in ['type']},
                        **{k: v for k, v in next_op.items() if k not in ['type']},
                    }
                    logger.debug(f"Fusing {op['type']} + {next_op['type']}")
                    fused.append(fused_op)
                    skip_next = True
                    continue
            
            fused.append(op)
        
        return fused
    
    def estimate_plan_cost(self, plan, input_size):
        """
        Estimate total cost of executing a plan.
        """
        total_cost = 0
        current_size = input_size
        
        logger.debug(f"\nEstimating cost for plan: {plan['name']}")
        
        for op in plan['operators']:
            if '+' in op['type']:
                # Fused operator
                op_types = op['type'].split('+')
                cost = self.estimate_fused_cost(
                    {'type': op_types[0]},
                    {'type': op_types[1]},
                    current_size
                )
                logger.debug(f"  {op['type']}: cost={cost}")
            else:
                cost_dict = self.estimate_operator_cost(op, current_size)
                cost = cost_dict.get(op['type'], 0)
                logger.debug(f"  {op['type']}: cost={cost}")
            
            total_cost += cost
            # Rough estimate of output size reduction
            if op['type'].startswith('WHERE'):
                current_size = max(1, int(current_size * 0.3))
            elif op['type'] == 'LIMIT':
                current_size = min(current_size, op.get('limit', current_size))
        
        logger.debug(f"  Total estimated cost: {total_cost}")
        return total_cost
    
    def select_best_plan(self, plans, input_size, max_cost=None):
        """
        Select the cheapest execution plan.
        
        Args:
            plans: list of plan variants
            input_size: size of input table
            max_cost: optional maximum cost constraint
            
        Returns:
            best_plan: plan with minimum cost
        """
        if not plans:
            logger.warning("No plans provided")
            return None
        
        best_plan = None
        best_cost = float('inf')
        
        for plan in plans:
            cost = self.estimate_plan_cost(plan, input_size)
            
            # Check if plan exceeds budget
            if max_cost and cost > max_cost:
                logger.warning(f"Plan '{plan['name']}' exceeds budget: {cost} > {max_cost}")
                continue
            
            if cost < best_cost:
                best_cost = cost
                best_plan = plan
        
        if best_plan:
            logger.info(f"Selected plan '{best_plan['name']}' with estimated cost {best_cost}")
        else:
            logger.warning("No plan within budget, selecting cheapest anyway")
            best_plan = min(plans, key=lambda p: self.estimate_plan_cost(p, input_size))
        
        return best_plan
    
    def optimize(self, operators, input_size):
        """
        Full optimization pipeline.
        
        Args:
            operators: list of operators in query plan
            input_size: size of input table
            
        Returns:
            optimized_plan: best query execution plan
        """
        logger.info(f"\n{'='*60}")
        logger.info("Starting query optimization")
        logger.info(f"{'='*60}")
        logger.info(f"Input operators: {[op['type'] for op in operators]}")
        logger.info(f"Input size: {input_size} rows")
        
        # Generate alternative plans
        plans = self.generate_plan_variants(operators)
        
        # Select best plan
        best_plan = self.select_best_plan(plans, input_size, max_cost=self.budget)
        
        if best_plan:
            logger.info(f"\nOptimized plan: {best_plan['name']}")
            logger.info(f"Operators: {[op['type'] for op in best_plan['operators']]}")
        
        return best_plan
