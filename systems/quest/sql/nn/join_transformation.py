"""
Join Transformation Strategy from QUEST Paper Section 3.2

Implements the paper's approach:
1. Extract join attributes from first table with filters
2. Transform join into IN filter on second table
3. Reorder filters using cost model

This reduces LLM cost by converting expensive joins into cheaper filters.
"""

from quest.core.node import ast_node as astn
from quest.conf import sqlconst
import copy


class JoinTransformer:
    """
    Transforms join operations into IN filters according to QUEST paper.
    
    Key insight from paper (Section 3.2, p.309-311):
    "We propose an approach that transforms a join operation into a filter operation
    and progressively orders the operations during query execution. First, it chooses
    one table and executes the respective operations, i.e., pushing down the filters
    on it and then extracting the join attribute. Now, QUEST has acquired all the
    values of this join attribute that could potentially produce the final query output.
    Therefore, it is able to convert the join operation into an IN filter and apply it
    to the other table."
    """
    
    def __init__(self):
        pass
    
    def extract_join_conditions(self, where_clause):
        """
        Extract join conditions from WHERE clause.
        Join conditions have the form: table1.attr = table2.attr
        
        Returns list of (lhs_col, rhs_col, op) tuples
        """
        join_conditions = []
        if not where_clause:
            return join_conditions
        
        join_conditions = self._extract_joins_recursive(where_clause.value if hasattr(where_clause, 'value') else where_clause)
        return join_conditions
    
    def _extract_joins_recursive(self, node):
        """Recursively extract join conditions from expression tree"""
        if not isinstance(node, astn.BinaryOperationExpr):
            return []
        
        joins = []
        
        # Recurse on AND/OR
        if node.op in sqlconst.LOGIC_TUPLE:
            joins.extend(self._extract_joins_recursive(node.lhs))
            joins.extend(self._extract_joins_recursive(node.rhs))
        else:
            # Check if this is a join condition: column = column
            if (isinstance(node.lhs, astn.ColumnExpr) and 
                isinstance(node.rhs, astn.ColumnExpr)):
                # This is a join condition
                lhs_table = node.lhs.parse_table()
                rhs_table = node.rhs.parse_table()
                
                # Only include if comparing different tables
                if lhs_table != rhs_table and lhs_table != sqlconst.DEFAULT_TABLE_NAME and rhs_table != sqlconst.DEFAULT_TABLE_NAME:
                    joins.append((node.lhs, node.rhs, node.op))
        
        return joins
    
    def extract_filter_conditions(self, where_clause, table):
        """
        Extract filter conditions (not join conditions) for specific table.
        
        Returns list of (condition, op) tuples that apply to the given table
        """
        filters = []
        if not where_clause:
            return filters
        
        filters = self._extract_filters_recursive(
            where_clause.value if hasattr(where_clause, 'value') else where_clause,
            table
        )
        return filters
    
    def _extract_filters_recursive(self, node, table):
        """Recursively extract filter conditions for specific table"""
        if not isinstance(node, astn.BinaryOperationExpr):
            return []
        
        filters = []
        
        if node.op in sqlconst.LOGIC_TUPLE:
            # AND/OR: recurse both sides
            filters.extend(self._extract_filters_recursive(node.lhs, table))
            filters.extend(self._extract_filters_recursive(node.rhs, table))
        else:
            # Check if this is a filter (not a join)
            if isinstance(node.lhs, astn.ColumnExpr):
                lhs_table = node.lhs.parse_table()
                rhs_table = node.rhs.parse_table() if isinstance(node.rhs, astn.ColumnExpr) else sqlconst.DEFAULT_TABLE_NAME
                
                # Include if:
                # 1. Only left side is a column (e.g., age > 35)
                # 2. Both sides are columns from SAME table (e.g., col1 = col2 within table)
                # 3. Matches the target table
                if not isinstance(node.rhs, astn.ColumnExpr):
                    # Simple filter: column OP value
                    if (lhs_table == table or lhs_table == sqlconst.DEFAULT_TABLE_NAME):
                        filters.append((node.lhs, node.op, node.rhs))
                elif lhs_table == rhs_table == table:
                    # Same-table comparison
                    filters.append((node.lhs, node.op, node.rhs))
                # Skip if it's a join condition (different tables)
        
        return filters
    
    def create_in_filter(self, extracted_join_values, join_column_right, op='IN'):
        """
        Create an IN filter for the second table.
        
        Args:
            extracted_join_values: List of values extracted from first table's join column
            join_column_right: The column to filter in second table
            op: Operator (default 'IN')
        
        Returns:
            A new BinaryOperationExpr representing the IN filter
        """
        # Create a value list (this will be handled by the filter execution engine)
        in_values = astn.ValueList(extracted_join_values)
        return astn.BinaryOperationExpr(join_column_right, op, in_values)
    
    def get_join_attributes(self, where_clause):
        """
        Extract the attributes used in join conditions.
        
        Returns: dict mapping {table: [join_attributes]}
        """
        join_attrs = {}
        join_conditions = self.extract_join_conditions(where_clause)
        
        for lhs_col, rhs_col, op in join_conditions:
            lhs_table = lhs_col.parse_table()
            rhs_table = rhs_col.parse_table()
            
            if lhs_table not in join_attrs:
                join_attrs[lhs_table] = []
            if rhs_table not in join_attrs:
                join_attrs[rhs_table] = []
            
            join_attrs[lhs_table].append(lhs_col)
            join_attrs[rhs_table].append(rhs_col)
        
        return join_attrs


class ValueList:
    """Represents a list of values for IN filters"""
    def __init__(self, values):
        self.values = values
    
    def __repr__(self):
        return f"ValueList({self.values})"


# Add ValueList to ast_node if not present
if not hasattr(astn, 'ValueList'):
    astn.ValueList = ValueList

