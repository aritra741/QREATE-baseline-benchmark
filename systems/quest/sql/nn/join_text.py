from .join import Join
from quest.utils import *
from quest.core.datapack import *
import pandas as pd
from quest.utils.log import print_log
import copy

class JoinText(Join):
    """
    Info : join_type - a list of join type ['INNER', ..]
            join_oreder - a list of equal order U.a1 = V.a2 by tuple, [(U, V) , (Team = Player)], table is a tring
            join_condition - a list of  BinaryNode (e.g. U.a1 == V.a2) ,
            type - the extract type ('Photo'/'Text'/..)

    Input : tables

    Process : we use a dsu to merge tables 
    """
    def __init__(self, join_type, join_order, type):
        super().__init__(join_type, join_order, type)
        self.name = 'JoinText'
        self.tableDict = {}
        self.fa = {} # this use for dsu

    def find_next(self, x):
        if self.fa[x] != x:
            self.fa[x] = self.find_next(self.fa[x])
        return self.fa[x]

    def process(self):
        """
        merge the tables from output
        """
        def _as_series(col_data):
            if isinstance(col_data, pd.DataFrame):
                return col_data.iloc[:, 0]
            return col_data

        def _prepare_merge_key(table: pd.DataFrame, key_name: str, side: str):
            key_series = _as_series(table[key_name])
            work = table.copy()
            merge_key = f"__quest_merge_key_{side}"
            work[merge_key] = key_series.values
            return work, merge_key

        # CRITICAL: Clear output from previous query execution
        # This prevents state leakage between multiple query runs
        self.output = []
        self.tableDict = {}
        self.fa = {}

        dataList = []
        for node in self.input:
            dataList.extend(node.get_output())

        # Step1 : get extracted tables
        for data in dataList:
            if isinstance(data, TablePack):

                # change to file name
                now_table = copy.copy(data.table)
                if 'doc_id' in now_table.columns:
                    # Step 2 : update doc_id to file_name
                    index_list = now_table['doc_id'].tolist()
                    all_map : dict = self.indexer.get_global_doc_id2file_name()
                    #print("total map:\n", all_map)

                    now_table = now_table.set_index('doc_id', inplace=False)
                    col_name = data.tablename + '.file_name'
                    for i in index_list:
                        now_table.at[i, col_name] = all_map.setdefault(i, 'None')
                    #print("index_list:\n",index_list)
                
                    now_table.reset_index(inplace=True)
                    now_table = now_table.drop(columns='doc_id')



                self.tableDict.setdefault(data.tablename, now_table)
                self.fa.setdefault(data.tablename, data.tablename)

        # Step2 : Join table by table

        final_table = pd.DataFrame()
        for i, typ in enumerate(self.join_type):
            # join the table  , condition is a core.node.logical_node.BinaryNode 
            condition = self.join_oreder[i]

            ltable_name = condition.lhs.parse_table()
            ltable_name = self.find_next(ltable_name)
            ltable_column = condition.lhs.parse_full()

            rtable_name = condition.rhs.parse_table()
            rtable_name = self.find_next(rtable_name)
            rtable_column = condition.rhs.parse_full()

            #print_log("mergeL : \n",self.tableDict[ltable_name])

            #print_log("mergeR : \n",self.tableDict[rtable_name])

            left_table = self.tableDict[ltable_name]
            right_table = self.tableDict[rtable_name]

            left_key = ltable_column if ltable_column in left_table.columns else None
            right_key = rtable_column if rtable_column in right_table.columns else None

            if left_key is None:
                left_base = ltable_column.split(".")[-1]
                for col in left_table.columns:
                    if col.endswith(left_base):
                        left_key = col
                        break
            if right_key is None:
                right_base = rtable_column.split(".")[-1]
                for col in right_table.columns:
                    if col.endswith(right_base):
                        right_key = col
                        break

            if left_key is None or right_key is None:
                raise KeyError(
                    f"Exact join keys not found: left='{ltable_column}' right='{rtable_column}' "
                    f"(resolved left='{left_key}' right='{right_key}')"
                )

            left_work, left_merge_key = _prepare_merge_key(left_table, left_key, "left")
            right_work, right_merge_key = _prepare_merge_key(right_table, right_key, "right")

            now_table = pd.merge(
                left_work,
                right_work,
                left_on=left_merge_key,
                right_on=right_merge_key,
                how="inner",
                suffixes=("_left", "_right"),
            )
            now_table = now_table.drop(columns=[left_merge_key, right_merge_key], errors="ignore")

            self.fa[ltable_name] = rtable_name
            self.tableDict[rtable_name] = now_table
            final_table  = now_table

            print_log("merge result : \n",now_table)

        # Step 3 : return 

        #print_log(final_table)

        self.output.append(TablePack('Merged Table', final_table))
        return final_table

            

            


        
            
        

