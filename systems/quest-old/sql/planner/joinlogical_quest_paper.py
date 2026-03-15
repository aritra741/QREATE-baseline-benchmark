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
        
        def resolve_column_alias(col_expr):
            if not isinstance(col_expr, astn.ColumnExpr):
                return col_expr
            table_prefix = col_expr.parse_table()
            if table_prefix in alias_to_table:
                actual_table = alias_to_table[table_prefix]
                column_name = col_expr.parse_column()
                alias_name = col_expr.column[2] if len(col_expr.column) > 2 else None
                return astn.ColumnExpr([actual_table, column_name, alias_name])
            return col_expr

        # Resolve and deduplicate join conditions from WHERE + explicit JOIN clauses.
        resolved_join_conditions = []
        seen_join_keys = set()
        for cond in join_conditions:
            lhs = resolve_column_alias(cond.lhs)
            rhs = resolve_column_alias(cond.rhs)
            if not isinstance(lhs, astn.ColumnExpr) or not isinstance(rhs, astn.ColumnExpr):
                continue
            key = (lhs.parse_full(), cond.op, rhs.parse_full())
            rev_key = (rhs.parse_full(), cond.op, lhs.parse_full())
            if key in seen_join_keys or rev_key in seen_join_keys:
                continue
            seen_join_keys.add(key)
            resolved_join_conditions.append(BinaryNode(lhs, cond.op, rhs))

        if not resolved_join_conditions:
            raise Exception("No resolved join conditions found")

        # Step 2: Build per-table extract nodes (retrieve -> optional filter -> extract)
        # and ensure each table contains all join attrs it participates in.
        table_join_attrs = {t: [] for t in tableList}
        for cond in resolved_join_conditions:
            ltbl = cond.lhs.parse_table()
            rtbl = cond.rhs.parse_table()
            if ltbl in table_join_attrs and cond.lhs not in table_join_attrs[ltbl]:
                table_join_attrs[ltbl].append(cond.lhs)
            if rtbl in table_join_attrs and cond.rhs not in table_join_attrs[rtbl]:
                table_join_attrs[rtbl].append(cond.rhs)

        extractDict = {}
        for table in tableList:
            table_cols = []
            for attr in proj_attrs:
                tbl = attr.parse_table()
                if tbl == table or tbl == sqlconst.DEFAULT_TABLE_NAME:
                    table_cols.append(attr)
            for attr in where_attrs:
                tbl = attr.parse_table()
                if tbl == table or tbl == sqlconst.DEFAULT_TABLE_NAME:
                    if attr not in table_cols:
                        table_cols.append(attr)
            for attr in table_join_attrs.get(table, []):
                if attr not in table_cols:
                    table_cols.append(attr)

            filter_root = self.extract_filter_conditions_for_table(selectStmt.whereClause, table)
            extract_node = LogicalExtract(columns=table_cols, table=table)
            if filter_root:
                filter_columns = []
                for attr in where_attrs:
                    tbl = attr.parse_table()
                    if tbl == table or tbl == sqlconst.DEFAULT_TABLE_NAME:
                        filter_columns.append(attr)
                logical_filter = LogicalFilter(columns=filter_columns, table=table, root=filter_root)
                logical_filter.append_input(retrieveDict[table])
                extract_node.append_input(logical_filter)
            else:
                extract_node.append_input(retrieveDict[table])
            extractDict[table] = extract_node

        # Step 3: Progressive join transformation across all join conditions.
        # Start from first FROM table and fold connected joins left-deep.
        current_table = tableList[0]
        current_node = extractDict[current_table]
        joined_tables = {current_table}
        remaining = list(resolved_join_conditions)

        while remaining:
            selected_idx = None
            selected_cond = None
            join_attr_first = None
            join_attr_second = None
            next_table = None

            for i, cond in enumerate(remaining):
                ltbl = cond.lhs.parse_table()
                rtbl = cond.rhs.parse_table()
                if ltbl in joined_tables and rtbl not in joined_tables:
                    selected_idx = i
                    selected_cond = cond
                    join_attr_first = cond.lhs
                    join_attr_second = cond.rhs
                    next_table = rtbl
                    break
                if rtbl in joined_tables and ltbl not in joined_tables:
                    selected_idx = i
                    selected_cond = cond
                    join_attr_first = cond.rhs
                    join_attr_second = cond.lhs
                    next_table = ltbl
                    break

            if selected_cond is None or next_table is None:
                raise Exception(
                    f"Join graph is not connected from anchor table '{tableList[0]}'. "
                    f"Remaining conditions: {[c.lhs.parse_full() + ' = ' + c.rhs.parse_full() for c in remaining]}"
                )

            join_node = LogicalJoin(
                join_type=['INNER'],
                join_order=[selected_cond],
                type='Text',
                extracted_join_attr=join_attr_first,
                join_filter_attr=join_attr_second,
            )
            join_node.append_input(current_node)
            join_node.append_input(extractDict[next_table])

            current_node = join_node
            joined_tables.add(next_table)
            remaining.pop(selected_idx)

        # Final projection to SELECT columns only.
        projnn = LogicalProjection(proj_attrs)
        projnn.append_input(current_node)
        print(f"[DEBUG JoinLogicalPlanner] Added LogicalProjection with columns: {[str(attr) for attr in proj_attrs]}")
        return projnn

    def build_logical_plan(self, root):
        self.root = self.build_select(root)
        return self.root

