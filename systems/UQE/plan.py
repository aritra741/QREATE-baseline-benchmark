from expression import Expression
from expression import ComparisonExpr, ConjunctionAndExpr, ConjunctionOrExpr

from oper import Operator
from oper import FilterOperator, ProjectOperator, GroupbyOperator, OrderbyOperator, LimitOperator, ScanOperator
import logging
import sys

# Setup logger
logger = logging.getLogger('UQE.plan')
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('[UQE-PLAN] %(levelname)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

def planner(parsed_query, source_data):
    logger.info("=" * 60)
    logger.info("Building query execution plan")
    logger.info("=" * 60)
    
    invalid_query = False
    project = parsed_query[0]
    from_ = parsed_query[1]
    where = parsed_query[2]
    group_by = parsed_query[3]
    order_by = parsed_query[4]
    limit = parsed_query[5]

    logger.debug(f"Project columns: {project}")
    logger.debug(f"From table: {from_}")
    logger.debug(f"Where clause: {where if where else 'None'}")
    logger.debug(f"Group by: {group_by if group_by else 'None'}")
    logger.debug(f"Order by: {order_by if order_by else 'None'}")
    logger.debug(f"Limit: {limit if limit else 'None'}")

    oper_ = Operator()

    if from_:
        logger.debug(f"Creating ScanOperator for table: {from_}")
        scan_oper = ScanOperator(source_data, from_)
        oper_ = scan_oper

    if where:
        logger.debug(f"Processing WHERE clause: {where}")
        or_list = where.split('OR')
        logger.debug(f"Split into {len(or_list)} OR conditions")
        if len(or_list) > 1:
            and_expr_list = []
            for and_list in or_list:
                and_list = and_list.strip()
                if and_list.startswith('(') and and_list.endswith(')'):
                    and_list = and_list[1:-1]
                and_list = and_list.split('AND')
                comp_expr_list = []
                for and_unit in and_list:
                    and_unit = and_unit.strip()
                    and_unit = and_unit.lstrip('(')
                    and_unit = and_unit.rstrip(')')
                    comp_expr_list.append(ComparisonExpr(and_unit))
                and_expr = ConjunctionAndExpr(comp_expr_list)
                and_expr_list.append(and_expr)
            or_expr = ConjunctionOrExpr(and_expr_list)
            logger.debug(f"Created OR expression with {len(and_expr_list)} AND groups")
            filter_oper_ = FilterOperator(source_data, or_expr)
        else:
            and_list = or_list[0].strip()
            if and_list.startswith('(') and and_list.endswith(')'):
                and_list = and_list[1:-1]
            and_list = and_list.split('AND')
            logger.debug(f"Split into {len(and_list)} AND conditions")
            comp_expr_list = []
            for and_unit in and_list:
                and_unit = and_unit.strip()
                and_unit = and_unit.lstrip('(')
                and_unit = and_unit.rstrip(')')
                comp_expr_list.append(ComparisonExpr(and_unit))
            and_expr = ConjunctionAndExpr(comp_expr_list)
            logger.debug(f"Created AND expression with {len(comp_expr_list)} conditions")
            filter_oper_ = FilterOperator(source_data, and_expr)
        filter_oper_.add_child(oper_)
        oper_ = filter_oper_
        logger.info("Added FILTER operator to plan")
    
    aggr_col_list = []
    has_aggregate = False
    logger.debug("Checking for aggregation functions in SELECT clause")
    col_lower = None
    for col in project:
        col_lower = col.lower()
        if col_lower.find('sum(') != -1 or col_lower.find('avg(') != -1 or col_lower.find('count(') != -1 or col_lower.find('max(') != -1 or col_lower.find('min(') != -1:
            aggr_func = col.split('(')[0].strip().lower()
            aggr_col = col.split('(')[1].split(')')[0].strip()
            logger.debug(f"Found aggregation: {aggr_func}({aggr_col})")

            aggr_col_list.append({aggr_col: aggr_func})
            has_aggregate = True
            if col_lower.find('max(') != -1 or col_lower.find('min(') != -1:
                logger.error(f"Unsupported aggregation function: {aggr_func}")
                invalid_query = True
                return None, invalid_query
    if has_aggregate:
        logger.info(f"Adding GROUP BY operator with {len(aggr_col_list)} aggregations")
        
        # For aggregation queries with virtual columns, we need to extract them first
        # Build list of columns needed: group_by columns + aggregation source columns
        needed_cols = []
        if group_by:
            needed_cols.extend(group_by)
        for agg_col_dict in aggr_col_list:
            agg_col = list(agg_col_dict.keys())[0]
            if agg_col != '*':
                needed_cols.append(agg_col)
        
        # Add id column for non-aggregate queries
        if 'id' not in needed_cols:
            needed_cols.insert(0, 'id')
        
        logger.debug(f"Columns needed for aggregation: {needed_cols}")
        
        # Insert PROJECT operator to extract virtual columns before GROUP BY
        # Always extract the needed columns before aggregation, as they may be virtual
        if needed_cols and needed_cols != ['id']:
            logger.debug(f"Inserting PROJECT operator before GROUP BY to extract: {needed_cols}")
            extract_oper = ProjectOperator(source_data, needed_cols)
            extract_oper.add_child(oper_)
            oper_ = extract_oper
        
        if group_by:
            logger.debug(f"Group by columns: {group_by}")
            group_by_oper = GroupbyOperator(source_data, group_by, aggr_col_list)
        else:
            logger.debug("Global aggregation (no GROUP BY)")
            group_by_oper = GroupbyOperator(source_data, None, aggr_col_list)
        group_by_oper.add_child(oper_)
        oper_ = group_by_oper
    else:
        if group_by:
            logger.error("GROUP BY without aggregate function - invalid query")
            raise ValueError("Group by without aggregate function")
        
    if not has_aggregate and not group_by:
        logger.debug("Adding 'id' to projection for non-aggregate query")
        project.insert(0, 'id')
    
    logger.info(f"Adding PROJECT operator with columns: {project}")
    project_oper = ProjectOperator(source_data, project)
    project_oper.add_child(oper_)
    oper_ = project_oper

    if order_by:
        logger.info(f"Adding ORDER BY operator: {order_by}")
        order_by_oper = OrderbyOperator(source_data, order_by)
        order_by_oper.add_child(oper_)
        oper_ = order_by_oper

    if limit:
        logger.info(f"Adding LIMIT operator: {limit}")
        limit_oper = LimitOperator(source_data, limit)
        limit_oper.add_child(oper_)
        oper_ = limit_oper

    logger.info("Query plan built successfully:")
    oper_.print_plan()
    return oper_, invalid_query
