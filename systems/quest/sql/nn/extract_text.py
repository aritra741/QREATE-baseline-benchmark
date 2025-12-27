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
            for i, pack in enumerate(output[:3]):  # Show first 3 packs
                if isinstance(pack, TextListPack):
                    print(f"  Pack {i}: TextListPack - doc_id={pack.doc_id}, column={pack.column}, text_len={len(str(pack.textList))}")
                elif isinstance(pack, TextDictPack):
                    print(f"  Pack {i}: TextDictPack - doc_id={pack.doc_id}, columns={list(pack.textDict.keys())}")
                elif isinstance(pack, DocListPack):
                    print(f"  Pack {i}: DocListPack - {len(pack.docList)} doc_ids")
                elif isinstance(pack, TablePack):
                    print(f"  Pack {i}: TablePack - shape={pack.table.shape if hasattr(pack.table, 'shape') else 'N/A'}")
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
        input_doc_list = None  # Store doc_ids from DocListPack if provided

        for data in dataList:

            # get table
            if isinstance(data, TablePack):
                now_table = table_util.merge_table(now_table, data.table, 'doc_id')

            # get doc list (from Filter output)
            if isinstance(data, DocListPack):
                input_doc_list = data.docList
                print(f"[DEBUG ExtractText] Received DocListPack with {len(input_doc_list)} doc_ids: {input_doc_list[:10]}...")

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
        
        # CRITICAL: If we received a DocListPack from Filter, use that instead of deriving from textDict
        if input_doc_list is not None:
            print(f"[DEBUG ExtractText] Using doc_ids from DocListPack (from Filter)")
            res_doc_id_list = input_doc_list
        else:
            print(f"[DEBUG ExtractText] Using doc_ids from textDict")

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
        
        # CRITICAL FIX: If we received filtered doc_ids from Filter, we need to extract ALL columns for those docs
        # Don't use cache check because the table has empty columns
        if input_doc_list is not None and len(input_doc_list) > 0:
            # We have specific doc_ids from Filter - extract all columns for them
            print(f"[DEBUG ExtractText] Filter provided specific doc_ids - extracting all columns for filtered documents")
            new_textDict = textDict  # Use the textDict as-is (might be empty)
            # But we need to get text for these documents to extract from!
            # The documents should be retrieved from the source
            # For now, assume the columns in now_table have the values we need
            # Actually, we should extract the missing columns!
            # Get text for the filtered doc_ids
            print(f"[DEBUG ExtractText] Need to retrieve text for filtered documents - this should have been done by Retrieve/Filter")
        else:
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
        