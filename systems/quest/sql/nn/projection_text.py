import pandas as pd
import copy

from .projection import Projection
from quest.utils import column_util, table_util
from quest.core.datapack import *
from quest.conf import sqlconst

class ProjectionText(Projection):
    """
    Info : columns - a list of ColumnExpr
            type - the extract type ('Photo'/'Text'/..)
    Input : None
    """
    def __init__(self, columns, type):
        super().__init__(columns, type)
        self.name = 'ProjectionText'
    
    def process(self):
        """
        Porjecion only need to project certain columns
        """
        # CRITICAL: Clear output from previous query execution
        # This prevents state leakage between multiple query runs
        self.output = []
        
        dataList = []
        for node in self.input:
            dataList.extend(node.get_output())

        # Step 1 : get_datapacks

        full_columns = column_util.parse_column_and_func(self.columns)
        now_table = pd.DataFrame()

        for data in dataList:
            # get table
            if isinstance(data, TablePack):
                now_table = data.table
        
        print(f"[DEBUG ProjectionText] Input table shape: {now_table.shape}")
        print(f"[DEBUG ProjectionText] Input table columns: {list(now_table.columns)}")
        print(f"[DEBUG ProjectionText] Requested columns (from SELECT): {full_columns}")

        # CRITICAL FIX per QUEST paper & SQL semantics:
        # Only output columns explicitly requested in SELECT clause.
        # Do NOT automatically add doc_id, file_name, or other internal columns
        # unless they were explicitly requested.
        
        if 'count_ALL_COLUMNS_STAR_TABLE.ALL_COLUMNS_STAR' in full_columns:
            full_columns.remove('count_ALL_COLUMNS_STAR_TABLE.ALL_COLUMNS_STAR')
            full_columns.append('Count(*)')
        
        print(f"[DEBUG ProjectionText] Full columns from SELECT: {full_columns}")
        
        # Filter to only existing columns that were explicitly requested
        existing_columns = [col for col in full_columns if col in now_table.columns]
        missing_columns = [col for col in full_columns if col not in now_table.columns]
        if missing_columns:
            print(f"[DEBUG ProjectionText] WARNING: Missing columns {missing_columns}, using only: {existing_columns}")
        
        # Select only the requested columns (no doc_id, file_name, etc unless explicitly asked)
        now_table = now_table[existing_columns]
        print(f"[DEBUG ProjectionText] After projection: {now_table.shape}, columns: {list(now_table.columns)}")

        self.output.append(TablePack('Result', now_table))

        #print("projection_table:\n", now_table)

        return now_table