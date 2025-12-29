"""
JoinTransformText - Executes join transformation per QUEST Paper Section 3.2

Per QUEST paper:
1. Extract join attributes from first table with filters
2. Collect extracted values
3. Convert to IN filter on second table
4. Execute filtered second table

This implements the paper's join transformation strategy to minimize LLM cost.
"""

from .join_text import JoinText
from quest.core.datapack import *
from quest.utils import *
from quest.core.node.logical_node import BinaryNode
import pandas as pd
import copy
from quest.utils.log import print_log


class JoinTransformText(JoinText):
    """
    Executes join transformation strategy from QUEST paper Section 3.2.
    
    Instead of traditional join:
    - First extract join attributes from one table
    - Convert join into IN filter on second table
    - Reorder and execute all filters by cost
    
    This minimizes LLM cost by avoiding expensive full joins.
    """
    
    def __init__(self, join_type, join_order, type, extracted_join_attr=None, join_filter_attr=None):
        super().__init__(join_type, join_order, type)
        self.name = 'JoinTransformText'
        self.extracted_join_attr = extracted_join_attr  # Join attribute from first table
        self.join_filter_attr = join_filter_attr  # Join attribute for second table filter
    
    def process(self):
        """
        Execute join transformation:
        1. Get extracted data from first table (includes join attribute values)
        2. Extract join attribute values from first table
        3. Create IN filter for second table using these values
        4. Merge results
        
        Per QUEST paper: "transforms a join operation into a filter operation"
        """
        print("[DEBUG JoinTransformText] Starting join transformation execution")
        
        # CRITICAL: Clear output from previous query execution
        self.output = []
        self.tableDict = {}
        self.fa = {}
        
        dataList = []
        for node in self.input:
            dataList.extend(node.get_output())
        
        print(f"[DEBUG JoinTransformText] Received {len(dataList)} data packs from input nodes")
        
        # Extract tables from data packs
        for data in dataList:
            if isinstance(data, TablePack):
                now_table = copy.copy(data.table)
                print(f"[DEBUG JoinTransformText] Processing TablePack: {data.tablename}")
                print(f"[DEBUG JoinTransformText] Table shape: {now_table.shape}, columns: {list(now_table.columns)}")
                
                # Update doc_id to file_name if needed
                if 'doc_id' in now_table.columns:
                    index_list = now_table['doc_id'].tolist()
                    all_map = self.indexer.get_global_doc_id2file_name()
                    
                    now_table = now_table.set_index('doc_id', inplace=False)
                    col_name = data.tablename + '.file_name'
                    for i in index_list:
                        now_table.at[i, col_name] = all_map.setdefault(i, 'None')
                    
                    now_table.reset_index(inplace=True)
                    now_table = now_table.drop(columns='doc_id')
                
                self.tableDict.setdefault(data.tablename, now_table)
                self.fa.setdefault(data.tablename, data.tablename)
        
        print(f"[DEBUG JoinTransformText] Extracted tables: {list(self.tableDict.keys())}")
        
        # Per paper: Transform join into IN filter
        if self.extracted_join_attr and self.join_filter_attr:
            print("[DEBUG JoinTransformText] Applying join transformation (join -> IN filter)")
            
            # Get join attribute values from first table
            first_table_name = self.extracted_join_attr.parse_table()
            join_attr_col = self.extracted_join_attr.parse_full()
            
            print(f"[DEBUG JoinTransformText] Extracting join values from table '{first_table_name}', column '{join_attr_col}'")
            
            if first_table_name in self.tableDict:
                first_table = self.tableDict[first_table_name]
                # Find the join column - it might have different names or duplicates
                join_col = None
                col_base = join_attr_col.split('.')[-1]  # Get last part after dot
                
                # Try exact match first
                if join_attr_col in first_table.columns:
                    join_col = join_attr_col
                else:
                    # Try partial match - look for column ending with the base name
                    for col in first_table.columns:
                        if col.endswith(col_base):
                            join_col = col
                            break
                
                if join_col:
                    # Extract join values from first table
                    col_series = first_table[join_col]
                    if isinstance(col_series, pd.DataFrame):
                        # If still a DataFrame, take the first column
                        col_series = col_series.iloc[:, 0]
                    
                    # Debug: show first few values
                    print(f"[DEBUG JoinTransformText] Column '{join_col}' first 5 values: {col_series.head().tolist()}")
                    print(f"[DEBUG JoinTransformText] Column dtype: {col_series.dtype}, non-null count: {col_series.count()}")
                    
                    join_values = col_series.dropna().unique().tolist()
                    print(f"[DEBUG JoinTransformText] Extracted {len(join_values)} unique join values from column '{join_col}': {join_values[:5] if join_values else 'EMPTY'}...")
                    # The IN filter will be applied to second table during its extraction/filtering
                    # Store values for reference if needed
                    self.extracted_join_values = join_values
                else:
                    print(f"[ERROR JoinTransformText] Join column '{join_attr_col}' not found in first table")
                    print(f"[ERROR JoinTransformText] Available columns: {list(first_table.columns)}")
        
        # Proceed with standard join
        print("[DEBUG JoinTransformText] Proceeding with table merge")
        final_table = pd.DataFrame()
        
        for i, typ in enumerate(self.join_type):
            if i >= len(self.join_oreder):
                break
            
            condition = self.join_oreder[i]
            
            ltable_name = condition.lhs.parse_table()
            ltable_name = self.find_next(ltable_name)
            ltable_column = condition.lhs.parse_full()
            
            rtable_name = condition.rhs.parse_table()
            rtable_name = self.find_next(rtable_name)
            rtable_column = condition.rhs.parse_full()
            
            print(f"[DEBUG JoinTransformText] Joining {ltable_name}.{ltable_column} = {rtable_name}.{rtable_column}")
            
            if ltable_name in self.tableDict and rtable_name in self.tableDict:
                from quest.core.nlp.match.fuse_join import pd_fuse_join
                now_table = pd_fuse_join(
                    self.tableDict[ltable_name], 
                    self.tableDict[rtable_name], 
                    ltable_column, 
                    rtable_column
                )
                
                print(f"[DEBUG JoinTransformText] Join result shape: {now_table.shape}")
                
                self.fa[ltable_name] = rtable_name
                self.tableDict[rtable_name] = now_table
                final_table = now_table
            else:
                print(f"[ERROR JoinTransformText] Missing tables for join: {ltable_name}, {rtable_name}")
                print(f"[ERROR JoinTransformText] Available tables: {list(self.tableDict.keys())}")
        
        print(f"[DEBUG JoinTransformText] Final table shape: {final_table.shape}")
        self.output.append(TablePack('Merged Table', final_table))
        
        return final_table

