from .filter import Filter
from quest.core.datapack import *
from quest.utils import *
import pandas as pd
import copy
from quest.core.llm.llm_query import TextLLMQuerier
from quest.core.node.logical_node import BinaryNode, FilterNode
from quest.core.node import ast_node as astn
from quest.utils.log import print_log

def list_and(x, y):
    if x == None:
        x = []
    if y == None:
        y = []
    return list(set(x) & set(y))

def list_or(x, y):
        if x == None:
            x = []
        if y == None:
            y = []
        return list(set(x) | set(y))

def list_xor(x, y):
    if x == None:
        x = []
    if y == None:
        y = []
    return list(set(x) ^ set(y))

class FilterText(Filter):
    """
    Info : columns - a list of ColumnExpr
            table - the filter tableName
            type - the filter type ('Photo'/'Text'/..)
            root - filter tree root
    Input : None
    """
    def __init__(self, columns, table, type, root):
        super().__init__(columns, table, type, root)
        self.name = 'FilterText'
        self.textDict = {} # {doc_id1 : { column1 :[text1, text2, ...], }
        self.now_tableDict = {}

    def solve(self, node : FilterNode, doc_idList):
        """
        dfs the filter tree, and get the result table 
        node : now tree node
        doc_idList : the doc_id list to be filter

        update --
        self.now_table : the result table after filter, may include muiltiple dataframe ()

        return --
        res_doc_idList : the rest doc_id list after filter list[int]


        You should use now_doc_idList to check filed
        use res_doc_idList to return
        """
        res_doc_idList = []
        now_doc_idList = copy.copy(doc_idList)
        if node.type == 'AND':
            for v in node.filterList:
                res_doc_idList = self.solve(v, now_doc_idList)
                now_doc_idList = copy.copy(res_doc_idList)
            return res_doc_idList
        elif node.type == 'OR':
            for v in node.filterList:
                res_doc_idList = list_or(res_doc_idList, self.solve(v, now_doc_idList))
                now_doc_idList = list_xor(res_doc_idList, doc_idList)
            return res_doc_idList
        else:
            # cmp try filter
            filter : BinaryNode = copy.copy(node.filterList[0])
            condition = filter.parse()
            condition = '`' + filter.lhs.parse_full() + '`' + ' ' + filter.op + ' ' + str(filter.rhs.parse_full())
            lcolumn = filter.lhs.parse_full()
            ltable = filter.lhs.parse_table()
            now_column = lcolumn # the filter column
            now_table = ltable

            print_log("\n now try filter - ", condition, " \n with space - ", now_doc_idList, "\n")
            
            # Extract first
            if filter.op != 'IN' and not isinstance(filter.rhs, astn.ColumnExpr) and not isinstance(filter.rhs, astn.StringValue):
                # if a normal value filters
                
                # Step 0 : get now textDict

                nowDict = table_util.check_dict_and_table(self.textDict, now_doc_idList, [lcolumn], self.now_tableDict[self.table])
                #nowDict = check_dict(self.textDict, now_doc_idList)

                # Step 1 : extract data
                df = self.querier.extract_attribute_from_textDict(nowDict, [lcolumn])

                # Step 2 : format the column
                if isinstance(filter.rhs, astn.IntegerValue):
                    #print("downcast: integer")
                    df[lcolumn] = pd.to_numeric(df[lcolumn], errors='coerce')
                    df.dropna(subset=[lcolumn], inplace=True)
                    df[lcolumn] = df[lcolumn].astype(int)
                elif isinstance(filter.rhs, astn.RealValue):
                    #print("downcast Fload")
                    df[lcolumn] = pd.to_numeric(df[lcolumn], errors='coerce')
                    df.dropna(subset=[lcolumn], inplace=True)
                    df[lcolumn] = df[lcolumn].astype(float)

                #print("after adjust type lhs:\n", df)

                # Step 3 : merge
                self.now_tableDict[self.table] = table_util.merge_table(self.now_tableDict[self.table], df, key='doc_id')
                #print("after merge:\n", self.now_tableDict[self.table])

                # Step 4 : check filter now
                now_data_table  = copy.copy(self.now_tableDict[self.table])
                now_data_table = now_data_table.set_index('doc_id', inplace = False)
                exist_idx = [idx for idx in now_doc_idList if idx in now_data_table.index] # check exist
                now_data_table = now_data_table.loc[exist_idx]
                now_data_table.reset_index(inplace=True)
                now_data_table = now_data_table.query(condition)
                
                #print("after filter:\n", now_data_table)

                # Step 5 : check the filed include
                res_doc_idList = format_util.remove_duplicates(now_data_table['doc_id'].tolist())
                res_doc_idList = list(map(int,res_doc_idList))
                #print("res_doc_id_List: ", res_doc_idList)
            
            else:
                # if columnExpr or IN need semantics

                if isinstance(filter.rhs, astn.ColumnExpr):
                    # we dont apply in here
                    # need to extract now_column in 
                    rcolumn = filter.rhs.parse_full()
                    rtable = filter.rhs.parse_table()
                    last_table = rtable
                    last_column = rcolumn
                    if self.table != ltable:
                        now_column = rcolumn
                        now_table = rtable
                        last_table = ltable
                        last_column = lcolumn

                    # if last_table not visited, only need to extract here
                    if last_table not in self.now_tableDict:
                        nowDict = table_util.check_dict_and_table(self.textDict, now_doc_idList, [now_column], self.now_tableDict[now_table])
                        #nowDict = check_dict(self.textDict, now_doc_idList)
                        df = self.querier.extract_attribute_from_textDict(nowDict, [now_column])
                        self.now_tableDict[self.table] = table_util.merge_table(self.now_tableDict[self.table], df, key='doc_id')
                        self.now_tableDict[self.table] = table_util.fill_cells(self.now_tableDict[self.table], [now_column], now_doc_idList, 'doc_id')
                        
                        return now_doc_idList
                    
                    # else process IN filter

                    # get already in value
                    df = copy.copy(self.now_tableDict[last_table])
                    df_list = df[last_column].tolist()
                    condition = str(now_column) + 'IN [' + ', '.join(df_list) + ']'

                    #print("condition : ", condition, '---- column : ',now_column)

                    nowDict = table_util.check_dict_and_table(self.textDict, now_doc_idList, [now_column], self.now_tableDict[now_table])
                    #nowDict = check_dict(self.textDict, now_doc_idList)
                    # Extract without semantic filter, then filter programmatically using pandas query
                    df = self.querier.extract_attribute_from_textDict(nowDict, [now_column])

                else:
                    # filter IN, or filter '=='string''
                    # rhs is astn.ListValue or a StringValue
                    lst = filter.rhs.parse_full()
                    condition = None
                    if isinstance(lst, list):
                        condition = str(now_column) + 'IN [' + ', '.join(lst) + ']'
                    elif isinstance(lst, str):
                        condition = str(now_column) + filter.op + lst 
                    else:
                        condition = lst

                    print("condition : ", condition, '---- column : ',now_column)

                    nowDict = table_util.check_dict_and_table(self.textDict, now_doc_idList, [now_column], self.now_tableDict[self.table])
                    #nowDict = check_dict(self.textDict, now_doc_idList)
                    # Extract without semantic filter, then filter programmatically using pandas query
                    df = self.querier.extract_attribute_from_textDict(nowDict, [now_column])

                # Format extracted columns and apply filter condition programmatically  
                # Step 2: Format the column if needed
                if isinstance(filter.rhs, astn.IntegerValue):
                    df[now_column] = pd.to_numeric(df[now_column], errors='coerce')
                    df.dropna(subset=[now_column], inplace=True)
                    df[now_column] = df[now_column].astype(int)
                elif isinstance(filter.rhs, astn.RealValue):
                    df[now_column] = pd.to_numeric(df[now_column], errors='coerce')
                    df.dropna(subset=[now_column], inplace=True)
                    df[now_column] = df[now_column].astype(float)
                
                # Add fcondition column by applying the condition filter
                extracted_df = df.copy()  # Save the extracted data with fcondition
                extracted_df['fcondition'] = 'False'  # Default to False
                
                try:
                    # Parse the condition - extract column name and value
                    # Condition format: "column = 'value'" or "column == 'value'"
                    import re
                    match = re.match(r"(`?[\w.]+`?)\s*(?:==|=|!=|<>|<=|>=|<|>)\s*'?([^']*)'?", condition)
                    if match:
                        col_name = match.group(1).strip('`')
                        val_right = match.group(2).strip("'\"")
                        print(f"[DEBUG filter_text] Parsing condition: column='{col_name}', value='{val_right}'")
                        
                        # Apply filter based on operator
                        if '==' in condition or ('=' in condition and '!=' not in condition and '<>' not in condition):
                            # Equality check - handle compound values separated by ||
                            # For disease_type and similar fields, values can be "type1 || type2"
                            # We need to check if val_right is one of the components
                            def check_equality(cell_val):
                                cell_str = str(cell_val).strip()
                                # Split by || and check if any component matches
                                components = [c.strip() for c in cell_str.split('||')]
                                return val_right in components or cell_str == val_right
                            
                            mask = extracted_df[col_name].apply(check_equality)
                            extracted_df.loc[mask, 'fcondition'] = 'True'
                        # TODO: Add support for other operators (<, >, !=, etc)
                        
                        print(f"[DEBUG filter_text] Applied condition: {len(extracted_df[extracted_df['fcondition'] == 'True'])} rows match")
                    else:
                        print(f"[DEBUG filter_text] Could not parse condition: {condition}")
                except Exception as e:
                    print(f"[DEBUG filter_text] Error applying condition '{condition}': {e}")
                    import traceback
                    traceback.print_exc()
                    # Keep all as False if parsing fails
                    extracted_df['fcondition'] = 'False'
                
                # Use extracted_df for now and merge it below
                #print_log("get filter df : \n", df)
                #print_log("extracted_df : \n", extracted_df)

                # Step 3 : merge
                #print_log("before merge tableDict : \n", self.now_tableDict[self.table])

                self.now_tableDict[self.table] = table_util.merge_table(self.now_tableDict[self.table], extracted_df, key='doc_id')

                #print_log("after merge tableDict : \n", self.now_tableDict[self.table])

                # Step 4 : check filter

                # Step 4-1 get the exist doc_ids that extract before
                ndf = extracted_df.set_index('doc_id', inplace = False)
                #print_log("after set index ndf : \n", ndf)
                checked_idx = [idx for idx in now_doc_idList if idx in ndf.index] # only filter this time docs index
                exist_idx = list_xor(now_doc_idList, checked_idx) # extract before, need to check samantics
                ndf.reset_index(inplace = True) # remember to reset
                
                #print_log("now_doc_idList : --- \n", now_doc_idList)
                #rint_log("checked_idx : ",checked_idx)
                #print_log("exist_idx : ", exist_idx)

                # Step 4-2 get the exist value
                gb_table = copy.copy(self.now_tableDict[self.table])
                gb_table = gb_table.set_index('doc_id', inplace = False)
                # CRITICAL FIX: Safely handle pandas Series/DataFrame .loc indexing
                try:
                    # Use direct indexing - more reliable than .loc for mixed cases
                    if len(exist_idx) == 0:
                        exist_check_text = []
                    elif len(exist_idx) == 1:
                        # Single index - get scalar value
                        val = gb_table.loc[exist_idx[0], now_column]
                        exist_check_text = [val] if not isinstance(val, list) else val
                    else:
                        # Multiple indices - get Series and convert to list
                        series_result = gb_table.loc[exist_idx, now_column]
                        if isinstance(series_result, pd.Series):
                            exist_check_text = series_result.tolist()
                        else:
                            # Fallback for unexpected type
                            exist_check_text = list(series_result) if hasattr(series_result, '__iter__') else [series_result]
                except Exception as e:
                    print(f"[ERROR filter_text] Failed to extract exist_check_text: {e}")
                    exist_check_text = []
                
                exist_df = self.querier.check_filter_condition(exist_check_text, exist_idx, [now_column], condition)
                gb_table.reset_index(inplace=True) # remember to reset

                #print_log("exist_df : \n", exist_df)

                df = table_util.merge_table(extracted_df, exist_df, key='doc_id') # filter this time merge fiter before with fcondition!

                #print_log("merge df and exist_df : \n", df)

                df = df[df['fcondition'].apply(lambda x: str(x).strip() == 'True')]
                #df = df[df['fcondition'].isin(['True', True])]

                #print_log("after check fcondition df : \n", df)

                # Step 5 : check the filed include
                if df.empty:
                    res_doc_idList = []
                    print(f"[DEBUG filter_text] df is empty, res_doc_idList = []")
                else:
                    res_doc_idList = format_util.remove_duplicates(df['doc_id'].tolist())
                    res_doc_idList = list(map(int,res_doc_idList))
                    print(f"[DEBUG filter_text] df has {len(df)} rows, res_doc_idList = {res_doc_idList[:10]}...")
                #print_log("res_doc_idList : ",res_doc_idList)

            # CRITICAL FIX: Don't call fill_cells after extraction+merge!
            # We just extracted and merged values for the filter column.
            # Calling fill_cells() would overwrite those extracted values with 'None' strings.
            # The merge_table() call already ensured all rows exist in the table.
            # For documents where extraction failed, they already have NaN in the column.
            # DO NOT: self.now_tableDict[self.table] = table_util.fill_cells(self.now_tableDict[self.table], [now_column], now_doc_idList, 'doc_id')

            return res_doc_idList

    def process(self):
        """
        Filter need to get: docList (from Retrieve or Filter), table (from Filter)
        """
        # CRITICAL: Clear output from previous query execution
        # This prevents state leakage between multiple query runs
        self.output = []
        self.textDict = {}
        
        dataList = []
        for node in self.input:
            dataList.extend(node.get_output())

        # step 1 : get_datapacks

        columns = column_util.parse_full(self.columns)
        full_columns = copy.copy(columns)
        full_columns.append('doc_id')
        self.now_tableDict[self.table] = pd.DataFrame(columns=full_columns, index=pd.Index([], name='doc_id'))
        #print_log("before data pack", self.now_tableDict[self.table])

        for data in dataList:

            # get table, note that may include other tables
            if isinstance(data, TablePack):
                now_table = data.tablename 
                if now_table != self.table:
                    # may check if exist
                    if now_table in self.now_tableDict.keys():
                        self.now_tableDict[now_table] = table_util.merge_table(self.now_tableDict[now_table], data.table)
                    else:
                        self.now_tableDict[now_table] = copy.copy(data.table)
                else:
                    self.now_tableDict[now_table] = table_util.merge_table(self.now_tableDict[now_table], data.table)

            # get text
            if isinstance(data, TextPack):
                doc_id = data.doc_id
                column = data.column
                text = data.text
                self.textDict.setdefault(doc_id, {})
                self.textDict[doc_id].setdefault(column, [])
                self.textDict[doc_id][column].append(text)
            
            if isinstance(data, TextListPack):
                doc_id = data.doc_id
                column = data.column
                text = data.textList
                self.textDict.setdefault(doc_id, {})
                self.textDict[doc_id].setdefault(column, [])
                self.textDict[doc_id][column].extend(text)

            if isinstance(data, TextDictPack):
                doc_id = data.doc_id
                # CRITICAL FIX: Convert doc_id to int for consistent type matching
                # TextDictPack may have string doc_ids, but res_doc_idList has integers
                doc_id = int(doc_id) if isinstance(doc_id, str) and doc_id.isdigit() else doc_id
                text = data.textDict
                print(f"[DEBUG FilterText] Received TextDictPack for doc_id={doc_id} (type: {type(doc_id).__name__})")
                print(f"[DEBUG FilterText] TextDictPack contains columns: {list(text.keys())}")
                print(f"[DEBUG FilterText] Sample text lengths: {[(col, len(str(text[col]))) for col in list(text.keys())[:3]]}")
                # CRITICAL FIX: Merge the text dict, don't just setdefault
                # setdefault keeps the old value if key exists, which loses new data
                if doc_id not in self.textDict:
                    self.textDict[doc_id] = text
                else:
                    # Merge columns - add any new columns from incoming text
                    for col, col_text in text.items():
                        if col not in self.textDict[doc_id]:
                            self.textDict[doc_id][col] = col_text
                        elif isinstance(col_text, list) and isinstance(self.textDict[doc_id][col], list):
                            # Both are lists - extend
                            self.textDict[doc_id][col].extend(col_text)
                        else:
                            # Replace if it's the newer value
                            self.textDict[doc_id][col] = col_text

        #print_log("after data pack", self.now_tableDict[self.table])

        doc_idList = list(self.textDict.keys())
            
        # step2 : filter from text

        # step2-1 : access local database and get cache

        # step2-2 : process filter tree
        res_doc_idList = self.solve(self.root, doc_idList)
        
        # step3 : output
        # CRITICAL FIX: Per QUEST paper (Section 2.4 & 3.1):
        # "QUEST adopts a lazy extraction strategy... only extracting an attribute when an 
        # analytical operation has to evaluate it"
        # FilterText has extracted the filter column(s). These MUST be passed to downstream
        # stages with their actual extracted VALUES, not as None.
        
        # Only include rows that pass the filter in the output table
        filtered_table = self.now_tableDict[self.table].copy()
        if res_doc_idList:
            # Filter to only include doc_ids that passed the filter
            if not filtered_table.empty:
                # Ensure doc_id column is int for comparison
                filtered_table['doc_id'] = filtered_table['doc_id'].astype(int)
                filtered_table = filtered_table[filtered_table['doc_id'].isin(res_doc_idList)].copy()
            print(f"[DEBUG filter_text.process] Output table: keeping {len(filtered_table)} rows out of {len(self.now_tableDict[self.table])} based on filter results")
        else:
            # No documents passed the filter - create empty dataframe with same columns
            filtered_table = self.now_tableDict[self.table].iloc[0:0].copy()  # Empty but with same structure
            print(f"[DEBUG filter_text.process] Output table: empty (no documents passed filter)")
        
        # CRITICAL: Remove the 'fcondition' column - it's just for internal filtering logic
        # The actual filter column values should be in the table
        if 'fcondition' in filtered_table.columns:
            filtered_table = filtered_table.drop(columns=['fcondition'])
        
        # CRITICAL FIX: Remove duplicate columns (keep first occurrence)
        # This can happen if the same column appears in both WHERE and SELECT columns
        filtered_table = filtered_table.loc[:, ~filtered_table.columns.duplicated(keep='first')]
        
        print(f"[DEBUG filter_text.process] Output columns after filter: {list(filtered_table.columns)}")
        if len(filtered_table) > 0:
            print(f"[DEBUG filter_text.process] Sample row 0: {filtered_table.iloc[0].to_dict()}")
            # Handle potential duplicate column names
            try:
                pos_vals = filtered_table['position']
                if isinstance(pos_vals, pd.DataFrame):
                    # Duplicate column - get first one
                    pos_vals = pos_vals.iloc[:, 0]
                print(f"[DEBUG filter_text.process] Position values: {pos_vals.unique()}")
            except Exception as e:
                print(f"[DEBUG filter_text.process] Could not get position values: {e}")
        
        self.output.append(TablePack(self.table, filtered_table))
        # CRITICAL: Also pass the filtered doc_ids so Extract knows which documents passed the filter
        self.output.append(DocListPack(self.table, res_doc_idList))

        #print_log("after filter res docs---: \n", res_doc_idList)

        # {doc_id1 : { column1 :[text1, text2, ...], }
        print(f"[DEBUG FilterText] Outputting TextListPacks for filtered documents")
        print(f"[DEBUG FilterText] res_doc_idList has {len(res_doc_idList)} documents: {res_doc_idList[:10]}")
        print(f"[DEBUG FilterText] self.textDict has {len(self.textDict)} total documents")
        if self.textDict:
            print(f"[DEBUG FilterText] Sample textDict keys: {list(self.textDict.keys())[:5]}")
            print(f"[DEBUG FilterText] Sample textDict[1]: {list(self.textDict[1].keys()) if 1 in self.textDict else 'N/A'}")
        
        textlist_count = 0
        for tid, value in self.textDict.items():
            if tid not in res_doc_idList:
                continue

            print(f"[DEBUG FilterText]   doc_id {tid}: has {len(value)} columns: {list(value.keys())}")
            #self.output.append(TextDictPack(tid, value))
            #print_log("continue to extract doc id is : ", tid)
            for col, lst in value.items():
                #print_log("append - ", tid, ' ' , lst, ' ', col, ' --- ', columns)
                self.output.append(TextListPack(tid, lst, col))
                textlist_count += 1
        
        print(f"[DEBUG FilterText] Total TextListPacks output: {textlist_count}") 
        print(f"[DEBUG FilterText] Total packs in output so far: {len(self.output)}")

        #print("filter_table:\n", self.now_tableDict[self.table])
        