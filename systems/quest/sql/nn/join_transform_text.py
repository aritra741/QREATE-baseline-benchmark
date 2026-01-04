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
                
                # Show what data we have
                if 'player.team' in now_table.columns:
                    team_col = now_table['player.team']
                    print(f"[DEBUG JoinTransformText] player.team column - non-null count: {team_col.count()}, non-null values: {team_col.dropna().unique().tolist()}")
                if 'team.team_name' in now_table.columns:
                    team_name_col = now_table['team.team_name']
                    print(f"[DEBUG JoinTransformText] team.team_name column - non-null count: {team_name_col.count()}, sample values: {team_name_col.dropna().unique().tolist()[:5]}")
                
                print(f"[DEBUG JoinTransformText] First row of {data.tablename}:\n{now_table.head(1)}")
                
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
            print(f"[DEBUG JoinTransformText] extracted_join_attr (first table): {self.extracted_join_attr.parse_full()}")
            print(f"[DEBUG JoinTransformText] join_filter_attr (second table): {self.join_filter_attr.parse_full()}")
            
            # Get join attribute values from first table
            first_table_name = self.extracted_join_attr.parse_table()
            join_attr_col = self.extracted_join_attr.parse_full()
            
            print(f"[DEBUG JoinTransformText] Looking for first table: '{first_table_name}' in tableDict keys: {list(self.tableDict.keys())}")
            print(f"[DEBUG JoinTransformText] Looking for join column: '{join_attr_col}'")
            
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
                    
                    # CRITICAL: Apply IN filter to second table BEFORE joining
                    # Per QUEST paper: transform join into IN filter on second table
                    second_table_name = self.join_filter_attr.parse_table()
                    second_join_col = self.join_filter_attr.parse_full()
                    
                    print(f"[DEBUG JoinTransformText] About to apply IN filter. join_values={join_values}")
                    
                    if second_table_name in self.tableDict:
                        second_table = self.tableDict[second_table_name]
                        
                        # Find the join column in second table
                        second_join_col_found = None
                        col_base_second = second_join_col.split('.')[-1]
                        
                        if second_join_col in second_table.columns:
                            second_join_col_found = second_join_col
                        else:
                            for col in second_table.columns:
                                if col.endswith(col_base_second):
                                    second_join_col_found = col
                                    break
                        
                        if second_join_col_found:
                            # Apply IN filter: keep only rows where join column value matches join_values
                            # CRITICAL: Use fuzzy matching instead of exact matching for better join results
                            join_values_list = [str(v).strip() for v in join_values if v]
                            
                            # Handle duplicate columns - get the first occurrence
                            col_data = second_table[second_join_col_found]
                            if isinstance(col_data, pd.DataFrame):
                                # Multiple columns with same name - take first
                                col_data = col_data.iloc[:, 0]
                            
                            # Use fuzzy matching: keep rows where similarity >= threshold
                            from fuzzywuzzy import fuzz
                            threshold = 70  # 70% similarity threshold (lowered for better matches)
                            
                            print(f"[DEBUG FUZZY] Join values to match: {join_values_list}")
                            print(f"[DEBUG FUZZY] Team column values (first 10): {col_data.head(10).tolist()}")
                            
                            def matches_any_fuzzy(val, target_list, thresh=80):
                                """Check if val fuzzy-matches any item in target_list"""
                                if not val or not target_list:
                                    return False
                                val_str = str(val).strip().lower()
                                for target in target_list:
                                    target_str = str(target).lower()
                                    # Use token_set_ratio for better matching (handles reordering)
                                    similarity = fuzz.token_set_ratio(val_str, target_str)
                                    if similarity >= thresh:
                                        return True
                                return False
                            
                            # Filter using fuzzy matching
                            mask = col_data.apply(lambda x: matches_any_fuzzy(x, join_values_list, threshold))
                            second_table_filtered = second_table[mask]
                            
                            print(f"[DEBUG JoinTransformText] Applied FUZZY IN filter to '{second_table_name}': {len(second_table)} -> {len(second_table_filtered)} rows (threshold={threshold}%)")
                            print(f"[DEBUG JoinTransformText] Filtered values that matched: {second_table_filtered[second_join_col_found].unique().tolist()[:5] if len(second_table_filtered) > 0 else 'NONE'}")
                            
                            # Update the tableDict with filtered table
                            self.tableDict[second_table_name] = second_table_filtered
                        else:
                            print(f"[WARNING JoinTransformText] Could not find join column '{second_join_col}' in second table '{second_table_name}'")
                            print(f"[WARNING JoinTransformText] Available columns: {list(second_table.columns)}")
                    
                    # Store values for reference
                    self.extracted_join_values = join_values
                else:
                    print(f"[ERROR JoinTransformText] Join column '{join_attr_col}' not found in first table")
                    print(f"[ERROR JoinTransformText] Available columns: {list(first_table.columns)}")
        
        # Proceed with standard join (now on filtered second table)
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

