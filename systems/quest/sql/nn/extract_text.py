from .base import Base
from .extract import Extract
from quest.core.datapack import *
from quest.utils import *
import pandas as pd
import copy
from quest.core.llm.llm_query import TextLLMQuerier
from quest.utils.log import print_log

class ExtractText(Extract):
    """
    Info : columns - a list of ColumnExpr
            table - the extract tableName
            type - the extract type ('Photo'/'Text'/..)
    Input : None
    """
    def __init__(self, columns, table, type):
        super().__init__(columns, table, type)
        self.name = 'ExtractText'

    def process(self):
        """
        Extract need to get: docList (from Retrieve or Filter), table (from Filter)
        """
        # CRITICAL: Clear output from previous query execution
        # This prevents state leakage between multiple query runs
        self.output = []
        
        print(f"\n[DEBUG ExtractText.process] STARTING - inputs from: {[type(n).__name__ for n in self.input]}")
        print(f"[DEBUG ExtractText.process] Number of input nodes: {len(self.input)}")
        
        dataList = []
        for node in self.input:
            output = node.get_output()
            print(f"[DEBUG ExtractText.process] Input node {type(node).__name__} returned {len(output)} data packs")
            dataList.extend(output)

        print(f"[DEBUG ExtractText.process] Total dataList size: {len(dataList)}")
        if not dataList:
            print(f"[WARNING ExtractText] No data packs received - extraction will fail!")

        # step 1 : get_datapacks
        columns = column_util.parse_full(self.columns)
        full_columns = copy.copy(columns)
        full_columns.append('doc_id')
        textDict = {} # {doc_id1 : { column1 :[text1, text2, ...], }
        now_table = pd.DataFrame(columns=full_columns, index=pd.Index([], name='doc_id'))

        for data in dataList:

            # get table
            if isinstance(data, TablePack):
                now_table = table_util.merge_table(now_table, data.table, 'doc_id')

            # get text
            if isinstance(data, TextPack):
                doc_id = data.doc_id
                column = data.column
                text = data.text
                textDict.setdefault(doc_id, {})
                textDict[doc_id].setdefault(column, [])
                textDict[doc_id][column].append(text)
            
            if isinstance(data, TextListPack):
                doc_id = data.doc_id
                column = data.column
                text = data.textList
                textDict.setdefault(doc_id, {})
                textDict[doc_id].setdefault(column, [])
                textDict[doc_id][column].extend(text)

            if isinstance(data, TextDictPack):
                doc_id = data.doc_id
                text = data.textDict
                textDict.setdefault(doc_id, text)
        
        #print_log("extract after data pack : \n", now_table)

        #print_log("accessed text dict : \n", textDict)

        res_doc_list = list(textDict.keys())
        res_doc_id_list = [int(x) for x in res_doc_list]

        print(f"[DEBUG ExtractText] textDict has {len(res_doc_list)} documents")
        print(f"[DEBUG ExtractText] First 5 doc IDs in textDict: {res_doc_id_list[:5] if res_doc_id_list else 'NONE'}")

        #rint_log("res_doc_list:", res_doc_list)
            
        # step2 : extract from text

        # step2-1 : access local database and get cache
        print(f"[DEBUG ExtractText] now_table shape BEFORE cache check: {now_table.shape}")
        print(f"[DEBUG ExtractText] now_table columns: {list(now_table.columns)}")
        if not now_table.empty:
            print(f"[DEBUG ExtractText] now_table has data: {len(now_table)} rows")
        else:
            print(f"[DEBUG ExtractText] now_table is EMPTY")
        
        new_textDict = table_util.check_dict_and_table(textDict, res_doc_id_list, columns, now_table)

        print(f"[DEBUG ExtractText] After cache check: {len(new_textDict)} documents need extraction")

        #print_log("need to extract text dict : \n", new_textDict)

        # delete no used ones

        # step2-2 : query input, build the input and the query in LLM
        print(f"[DEBUG ExtractText] Calling LLM extraction for {len(new_textDict)} documents")
        df = self.querier.extract_attribute_from_textDict(textDict = new_textDict, attributeList = columns)
        print(f"[DEBUG ExtractText] LLM extraction returned df with {len(df)} rows, {len(df.columns)} columns")

        # step2-3 : merge
        print(f"[DEBUG ExtractText] Merging: now_table has {len(now_table)} rows, df has {len(df)} rows")
        now_table = table_util.merge_table(now_table, df, key='doc_id')
        print(f"[DEBUG ExtractText] After merge: now_table has {len(now_table)} rows")
        #print_log("merge extract_table:\n", now_table)

        # step3 : output

        now_table = table_util.keep_table(now_table, res_doc_id_list, 'doc_id')

        print_log("fianl_table:\n",now_table)

        self.output.append(TablePack(self.table, now_table))
        self.output.append(DocListPack(self.table, res_doc_id_list))

        return None
        