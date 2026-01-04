"""
Join Logical Planner - Implementation of QUEST Paper Section 3.2

According to QUEST paper:
1. Extract join attributes from first table with filters applied
2. Transform join into IN filter on second table  
3. Order all filters (including generated IN filter) using cost model from Section 3.1

This implements the join transformation strategy:
"We propose an approach that transforms a join operation into a filter operation
and progressively orders the operations during query execution."
"""

from quest.sql.nn import *
from quest.core.node import ast_node as astn
from quest.conf import sqlconst
from quest.core.node.logical_node import FilterNode, BinaryNode
from quest.sql.nn.logical_filter import LogicalFilter
from quest.sql.nn.logical_extract import LogicalExtract
from quest.sql.nn.logical_retrieve import LogicalRetrieve
from quest.sql.nn.logical_join import LogicalJoin
from quest.sql.nn.logical_projection import LogicalProjection
import copy
from quest.utils.log import print_log


def remove_duplicates(lst):
    return list(dict.fromkeys(lst))


def remove_duplicates_columns(lst):
    res = []
    for v in lst:
        flag = False
        for x in res:
            if(x.parse_full() == v.parse_full()):
                flag = True
                break
        if not flag:
            res.append(v)
    return res


class JoinLogicalPlanner(object):
    """
    Implements join optimization according to QUEST paper Section 3.2.
    
    Key principles:
    - Transform joins into IN filters (reduces LLM cost)
    - Order operations based on cost model, not just selectivity
    - Execute joins lazily, only when needed
    """
    
    def __init__(self):
        self.root = None

    def extract_function(self, attrList):
        res = []
        for v in attrList:
            if isinstance(v, astn.FunctionExpr):
                res.append(copy.copy(v))
        return res

    def extract_binary(self, node):
        res = []
        if not isinstance(node, astn.BinaryOperationExpr):
            raise Exception('Not a Binary!')
        if node.op in sqlconst.LOGIC_TUPLE:
            res.extend(self.extract_binary(node.lhs))
            res.extend(self.extract_binary(node.rhs))
        else:
            res.append(copy.copy(node.lhs))
            if isinstance(node.rhs, astn.ColumnExpr):
                res.append(copy.copy(node.rhs))
        return res

    def extract_attrs_from_whereClause(self, whereClause):
        if isinstance(whereClause, astn.WhereExpr):
            return self.extract_binary(whereClause.value)
        return []

    def extract_join_conditions(self, whereClause):
        """
        Extract join conditions (table1.col = table2.col) from WHERE clause.
        Per paper Section 3.2: "Transform join into IN filter"
        """
        if not whereClause:
            return []
        
        return self._extract_joins_recursive(
            whereClause.value if isinstance(whereClause, astn.WhereExpr) else whereClause
        )
    
    def _extract_joins_recursive(self, node):
        """Recursively find join conditions"""
        if not isinstance(node, astn.BinaryOperationExpr):
            return []
        
        joins = []
        
        if node.op in sqlconst.LOGIC_TUPLE:
            # AND/OR - recurse both sides
            joins.extend(self._extract_joins_recursive(node.lhs))
            joins.extend(self._extract_joins_recursive(node.rhs))
        else:
            # Check if join condition: column = column from different tables
            if (isinstance(node.lhs, astn.ColumnExpr) and 
                isinstance(node.rhs, astn.ColumnExpr)):
                lhs_table = node.lhs.parse_table()
                rhs_table = node.rhs.parse_table()
                
                # Join if different tables and neither is DEFAULT
                if (lhs_table != rhs_table and 
                    lhs_table != sqlconst.DEFAULT_TABLE_NAME and 
                    rhs_table != sqlconst.DEFAULT_TABLE_NAME):
                    joins.append(BinaryNode(node.lhs, node.op, node.rhs))
        
        return joins

    def extract_filter_conditions_for_table(self, whereClause, table):
        """
        Extract non-join filters for specific table.
        Per paper: These are applied BEFORE the join transformation.
        """
        if not whereClause:
            return None
        
        where_expr = whereClause.value if isinstance(whereClause, astn.WhereExpr) else whereClause
        return self.build_filter_for_table(where_expr, table)

    def build_filter_for_table(self, conditions, table):
        """Build filter node for conditions that apply to specific table"""
        if not isinstance(conditions, astn.BinaryOperationExpr):
            raise Exception('Not a Binary!')
        
        if conditions.op in sqlconst.LOGIC_TUPLE:
            # AND/OR
            ls = self.build_filter_for_table(conditions.lhs, table) if conditions.lhs else None
            rs = self.build_filter_for_table(conditions.rhs, table) if conditions.rhs else None
            
            if ls is None and rs is None:
                return None
            elif ls is None:
                return rs
            elif rs is None:
                return ls
            else:
                x = FilterNode(conditions.op, table, [])
                if ls:
                    x.add_filter(ls)
                if rs:
                    x.add_filter(rs)
                return x
        else:
            # Single condition
            if isinstance(conditions.lhs, astn.ColumnExpr):
                lhs_table = conditions.lhs.parse_table()
                
                # Check if this is a join condition (both sides are columns)
                if isinstance(conditions.rhs, astn.ColumnExpr):
                    rhs_table = conditions.rhs.parse_table()
                    # Skip join conditions
                    if lhs_table != rhs_table:
                        return None
                
                # Apply if it matches this table or has no table specified
                if lhs_table == table or lhs_table == sqlconst.DEFAULT_TABLE_NAME:
                    condi = BinaryNode(conditions.lhs, conditions.op, conditions.rhs)
                    return FilterNode('cmp', table, [condi])
            
            return None

    def build_select(self, selectStmt):
        """
        Build logical plan according to QUEST paper Section 3.2.
        
        Process:
        1. Identify join conditions in WHERE clause
        2. For first table: apply filters, extract join attributes
        3. Transform join into IN filter on second table
        4. Order all operations by cost (per Section 3.1)
        """
        if not isinstance(selectStmt, astn.SelectExpr):
            raise Exception('Not a Select Node!')
        
        # Get table list from FROM clause
        tableList = selectStmt.fromClause.value
        
        # CRITICAL: Extract all tables involved in JOIN clause (not just FROM)
        # The parser puts joined tables in joinClause, not in tableList
        if selectStmt.joinClause and selectStmt.joinClause.value:
            for join_info in selectStmt.joinClause.value:
                # join_info is [JOIN_TYPE, TABLE, CONDITION]
                joined_table = join_info[1]  # The table being joined
                if joined_table not in tableList:
                    tableList.append(joined_table)
        
        if len(tableList) < 2:
            # No join - use regular logical planner
            raise Exception('Use LogicalPlanner for non-join queries')
        
        proj_attrs = copy.copy(selectStmt.selectClause.value)
        
        # Extract all attributes from WHERE clause for retrieve
        where_attrs = self.extract_attrs_from_whereClause(selectStmt.whereClause)
        where_attrs = remove_duplicates_columns(where_attrs)
        
        # Find join conditions
        # Check both WHERE clause (legacy) and JOIN clause (explicit)
        join_conditions = self.extract_join_conditions(selectStmt.whereClause)
        
        # CRITICAL: Also extract join conditions from explicit JOIN clauses
        if selectStmt.joinClause and selectStmt.joinClause.value:
            for join_info in selectStmt.joinClause.value:
                # join_info is [JOIN_TYPE, TABLE, CONDITION]
                condition = join_info[2]  # The condition is a BinaryOperationExpr
                if isinstance(condition, astn.BinaryOperationExpr):
                    join_conditions.append(BinaryNode(condition.lhs, condition.op, condition.rhs))
        
        if not join_conditions:
            raise Exception('No join conditions found')
        
        # Step 1: Build retrieve nodes for all tables
        all_attrs = []
        all_attrs.extend(where_attrs)
        all_attrs.extend(proj_attrs)
        
        # CRITICAL: Add join attributes to retrieval list so they get fetched during retrieve phase
        for join_cond in join_conditions:
            if hasattr(join_cond, 'lhs') and join_cond.lhs not in all_attrs:
                all_attrs.append(join_cond.lhs)
            if hasattr(join_cond, 'rhs') and join_cond.rhs not in all_attrs:
                all_attrs.append(join_cond.rhs)
        
        all_attrs = remove_duplicates_columns(all_attrs)
        
        # CRITICAL FIX: Resolve table aliases to actual table names
        # Import the parser's origin_tables which maps aliases to table names
        from quest.sql.parser import sqlparser
        alias_to_table = getattr(sqlparser, 'origin_tables', {})
        print(f"[DEBUG JoinLogicalPlanner] alias_to_table from parser: {alias_to_table}")
        
        # Resolve aliases in all_attrs
        resolved_attrs = []
        for attr in all_attrs:
            if isinstance(attr, astn.ColumnExpr):
                table_prefix = attr.parse_table()
                # If table_prefix is an alias, resolve it to actual table name
                if table_prefix in alias_to_table:
                    actual_table = alias_to_table[table_prefix]
                    # ColumnExpr.column is a list: [table_name, column_name, alias_name]
                    column_name = attr.parse_column()
                    alias_name = attr.column[2] if len(attr.column) > 2 else None
                    # Create new ColumnExpr with resolved table name
                    resolved_attr = astn.ColumnExpr([actual_table, column_name, alias_name])
                    resolved_attrs.append(resolved_attr)
                    print(f"[DEBUG JoinLogicalPlanner] Resolved {table_prefix}.{column_name} -> {actual_table}.{column_name}")
                else:
                    resolved_attrs.append(attr)
            else:
                resolved_attrs.append(attr)
        
        all_attrs = resolved_attrs
        print(f"[DEBUG JoinLogicalPlanner] all_attrs after resolution: {[a.parse_full() for a in all_attrs]}")
        print(f"[DEBUG JoinLogicalPlanner] tableList: {tableList}")
        
        # CRITICAL: Also resolve aliases in proj_attrs and where_attrs for extraction
        def resolve_attr_list(attr_list):
            """Resolve aliases in a list of attributes."""
            resolved = []
            for attr in attr_list:
                if isinstance(attr, astn.ColumnExpr):
                    table_prefix = attr.parse_table()
                    if table_prefix in alias_to_table:
                        actual_table = alias_to_table[table_prefix]
                        column_name = attr.parse_column()
                        alias_name = attr.column[2] if len(attr.column) > 2 else None
                        resolved_attr = astn.ColumnExpr([actual_table, column_name, alias_name])
                        resolved.append(resolved_attr)
                        print(f"[DEBUG JoinLogicalPlanner] Resolved projection/where {table_prefix}.{column_name} -> {actual_table}.{column_name}")
                    else:
                        resolved.append(attr)
                else:
                    resolved.append(attr)
            return resolved
        
        proj_attrs = resolve_attr_list(proj_attrs)
        where_attrs = resolve_attr_list(where_attrs)
        
        retrieveDict = {}
        for table in tableList:
            columns = []
            for attr in all_attrs:
                tbl = attr.parse_table()
                if table == tbl or tbl == sqlconst.DEFAULT_TABLE_NAME:
                    columns.append(attr)
            print(f"[DEBUG JoinLogicalPlanner] Table '{table}': columns={[c.parse_full() for c in columns]}")
            retrieveDict[table] = LogicalRetrieve(columns=columns, table=table, type='Text')
        
        # Step 2: Per QUEST paper - Process joins progressively
        # For now, implement 2-table join. Multi-way joins use left-deep approach.
        
        extractDict = {}
        
        # Process FIRST table: apply filters, extract join attributes
        first_table = tableList[0]
        join_cond = join_conditions[0]  # First join condition
        
        # Get the join attribute for first table
        # CRITICAL: Resolve aliases in join attributes too
        join_lhs_table = join_cond.lhs.parse_table()
        join_rhs_table = join_cond.rhs.parse_table()
        
        # Resolve aliases in join condition tables
        if join_lhs_table in alias_to_table:
            join_lhs_table = alias_to_table[join_lhs_table]
        if join_rhs_table in alias_to_table:
            join_rhs_table = alias_to_table[join_rhs_table]
        
        if join_lhs_table == first_table:
            join_attr_first = join_cond.lhs
            join_attr_second = join_cond.rhs
            second_table = join_rhs_table
        else:
            join_attr_first = join_cond.rhs
            join_attr_second = join_cond.lhs
            second_table = join_lhs_table
        
        # Resolve join attributes themselves if they have aliases
        if isinstance(join_attr_first, astn.ColumnExpr):
            join_attr_first_table = join_attr_first.parse_table()
            if join_attr_first_table in alias_to_table:
                actual_table = alias_to_table[join_attr_first_table]
                column_name = join_attr_first.parse_column()
                alias_name = join_attr_first.column[2] if len(join_attr_first.column) > 2 else None
                join_attr_first = astn.ColumnExpr([actual_table, column_name, alias_name])
        
        if isinstance(join_attr_second, astn.ColumnExpr):
            join_attr_second_table = join_attr_second.parse_table()
            if join_attr_second_table in alias_to_table:
                actual_table = alias_to_table[join_attr_second_table]
                column_name = join_attr_second.parse_column()
                alias_name = join_attr_second.column[2] if len(join_attr_second.column) > 2 else None
                join_attr_second = astn.ColumnExpr([actual_table, column_name, alias_name])
        
        # For first table: get filters that apply to it
        # CRITICAL: We MUST apply WHERE clause filters to filter the first table
        # before extracting join values. This is essential for correctness.
        filter_first = self.extract_filter_conditions_for_table(selectStmt.whereClause, first_table)
        
        # Build projection for first table (need join attribute + projection attributes + filter attributes)
        first_table_cols = []
        for attr in proj_attrs:
            tbl = attr.parse_table()
            if tbl == first_table or tbl == sqlconst.DEFAULT_TABLE_NAME:
                first_table_cols.append(attr)
        for attr in where_attrs:
            tbl = attr.parse_table()
            if tbl == first_table or tbl == sqlconst.DEFAULT_TABLE_NAME:
                if attr not in first_table_cols:
                    first_table_cols.append(attr)
        # Add join attribute
        if join_attr_first not in first_table_cols:
            first_table_cols.append(join_attr_first)
        
        print(f"[DEBUG JoinLogicalPlanner] first_table_cols BEFORE extract: {[c.parse_full() if isinstance(c, astn.ColumnExpr) else str(c) for c in first_table_cols]}")
        
        # Build first table extract node with filter
        extract_first = LogicalExtract(columns=first_table_cols, table=first_table)
        
        if filter_first:
            # Create LogicalFilter node to apply WHERE clause conditions
            # CRITICAL: Only pass filter columns to the filter node, not projection columns
            # The filter evaluates WHERE conditions FIRST, then Extract handles projection
            filter_columns = []
            for attr in where_attrs:
                tbl = attr.parse_table()
                if tbl == first_table or tbl == sqlconst.DEFAULT_TABLE_NAME:
                    filter_columns.append(attr)
            logical_filter_first = LogicalFilter(columns=filter_columns, table=first_table, root=filter_first)
            logical_filter_first.append_input(retrieveDict[first_table])
            extract_first.append_input(logical_filter_first)
        else:
            extract_first.append_input(retrieveDict[first_table])
        
        extractDict[first_table] = extract_first
        
        # Step 3: TRANSFORM JOIN INTO IN FILTER (per paper Section 3.2)
        # Second table gets: IN filter on join attribute
        
        # Build second table columns
        second_table_cols = []
        for attr in proj_attrs:
            tbl = attr.parse_table()
            if tbl == second_table or tbl == sqlconst.DEFAULT_TABLE_NAME:
                second_table_cols.append(attr)
        for attr in where_attrs:
            tbl = attr.parse_table()
            if tbl == second_table or tbl == sqlconst.DEFAULT_TABLE_NAME:
                if attr not in second_table_cols:
                    second_table_cols.append(attr)
        # Add join attribute for IN filter
        if join_attr_second not in second_table_cols:
            second_table_cols.append(join_attr_second)
        
        # Create a logical join filter node that represents the IN filter
        # This will be executed as: extracted_values = extract_first.join_attr_values
        #                           filter_second where join_attr IN extracted_values
        
        extract_second = LogicalExtract(columns=second_table_cols, table=second_table)
        
        # Connect second table: retrieve -> extract
        extract_second = LogicalExtract(columns=second_table_cols, table=second_table)
        extract_second.append_input(retrieveDict[second_table])
        
        # Build join node
        join_node = LogicalJoin(
            join_type=['INNER'],
            join_order=[join_cond],
            type='Text',
            # Store extracted values from first table to use as IN filter
            extracted_join_attr=join_attr_first,
            join_filter_attr=join_attr_second
        )
        
        # Connect: first table extract -> join -> second table extract
        join_node.append_input(extract_first)
        join_node.append_input(extract_second)
        
        print(f"[DEBUG JoinLogicalPlanner] Final join_node created: {join_node}")
        print(f"[DEBUG JoinLogicalPlanner] join_node.join_filter_attr: {join_node.join_filter_attr}")
        print(f"[DEBUG JoinLogicalPlanner] join_node.extracted_join_attr: {join_node.extracted_join_attr}")
        
        # CRITICAL: Add Projection node to only return SELECT columns (per SQL semantics)
        # This ensures only explicitly requested columns are in the final output
        projnn = LogicalProjection(proj_attrs)
        projnn.append_input(join_node)
        
        print(f"[DEBUG JoinLogicalPlanner] Added LogicalProjection with columns: {[str(attr) for attr in proj_attrs]}")
        
        return projnn

    def build_logical_plan(self, root):
        self.root = self.build_select(root)
        return self.root

