import pandas as pd
import numpy as np
import itertools
import sys
import logging

from expression import ComparisonExpr, ConjunctionAndExpr, ConjunctionOrExpr
from f import llm_filter, llm_extractor, llm_groupby_labels, llm_cluster, llm_groupby_labels_split
from cluster import gen_embeds, Aggregator
from config_uqe import AGGR_STRATEGY, N_CENTROIDS, N_ITER, GROUP_EXTRACT_SAMPLE_RATIO

# Setup logger
logger = logging.getLogger('UQE.oper')
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('[UQE-OPER] %(levelname)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

class Operator():
    def __init__(self, source_data=None, name=None):
        self.name = name
        self.data_schema = source_data
        self.children = []

        self.ok_col_type_without_llm = ['int', 'float', 'varchar']

    def next(self):
        pass

    def check_col_ok_without_llm(self, col_type):
        if col_type not in self.ok_col_type_without_llm:
            return False
        else:
            return True


    def add_child(self, child):
        if not isinstance(child, Operator):
            raise ValueError("Child must be an instance of Operator")
        self.children.append(child)
    
    def print_plan(self, level=0):
        print(''.join([' ' for _ in range(level)]) + self.name)
        if self.children:
            for child in self.children:
                child.print_plan(level+1)


class ProjectOperator(Operator):
    def __init__(self, source_data, project_columns):
        super().__init__(source_data, 'PROJECT')
        self.project_columns = [column.strip() for column in project_columns]

    def next(self, skip=False):
        logger.info(f"Executing PROJECT operator on columns: {self.project_columns}")
        logger.debug(f"Input DataFrame shape: {self.children[0].name if self.children else 'N/A'}")
        
        # Try to pass skip parameter to child if it accepts it
        try:
            child_df = self.children[0].next(skip=skip)
        except TypeError:
            # Child doesn't accept skip parameter
            child_df = self.children[0].next()
        logger.debug(f"Child operator returned DataFrame shape: {child_df.shape if child_df is not None else 'None'}")
        
        # Handle SELECT * - expand to all columns
        if self.project_columns[0] == '*':
            logger.debug("SELECT * - returning all columns")
            return child_df
        elif '*' in self.project_columns:
            # If * is mixed with other columns like PROJECT(id, *), expand * to include all columns
            logger.debug("SELECT with * mixed with other columns - expanding *")
            expanded_cols = []
            for col in self.project_columns:
                if col == '*':
                    # Add all child_df columns that aren't already in expanded_cols
                    for child_col in child_df.columns:
                        if child_col not in expanded_cols:
                            expanded_cols.append(child_col)
                else:
                    if col not in expanded_cols:
                        expanded_cols.append(col)
            logger.debug(f"Expanded columns: {expanded_cols}")
            return child_df[expanded_cols]
        else:
            exist_cols = []
            to_extract_cols = {}

            logger.debug("Analyzing projection columns...")
            for col in self.project_columns:
                # Skip aggregate expressions - they should be handled by GROUP BY operator
                col_lower = col.lower()
                if any(agg_func in col_lower for agg_func in ['count(', 'sum(', 'avg(', 'min(', 'max(']):
                    logger.debug(f"  Column '{col}' is an aggregate expression - checking if it exists in child_df")
                    # Extract the aggregate column name from the expression
                    # Examples: "COUNT(name) AS player_count" -> need to match "count(name)"
                    # Split on case-insensitive ' as ' to handle both 'AS' and 'as'
                    parts = col.split(' as ')
                    if len(parts) < 2:
                        parts = col.split(' AS ')
                    if len(parts) < 2:
                        parts = col.split(' As ')
                    
                    agg_expr = parts[0].strip().lower()
                    logger.debug(f"    Looking for aggregate expression: '{agg_expr}'")
                    
                    # Check if this aggregate expression exists in child_df (case-insensitive)
                    found_col = None
                    for df_col in child_df.columns:
                        if df_col.lower() == agg_expr:
                            found_col = df_col
                            logger.debug(f"    Found aggregate column '{found_col}' in child_df")
                            break
                    
                    if found_col:
                        exist_cols.append(found_col)
                    else:
                        logger.debug(f"    Aggregate column '{agg_expr}' not found in child_df")
                    continue
                # Try exact match first
                if col in child_df.columns:
                    logger.debug(f"  Column '{col}' exists in DataFrame")
                    exist_cols.append(col)
                else:
                    # Try case-insensitive match
                    actual_col_name = None
                    for df_col in child_df.columns:
                        if df_col.lower() == col.lower():
                            actual_col_name = df_col
                            break
                    
                    if actual_col_name:
                        logger.debug(f"  Column '{col}' found as '{actual_col_name}' in DataFrame (case-insensitive)")
                        exist_cols.append(actual_col_name)
                    else:
                        # Check if this is a virtual attribute (not in DataFrame)
                        # It could be a simple column name or column.attribute format
                        if '.' in col:
                            # Format: column.attribute (explicit virtual attribute)
                            column_name = col.split('.')[0]
                            attribute_name = col.split('.')[1]
                            logger.debug(f"  Column '{col}' is virtual attribute of '{column_name}'")
                        else:
                            # Format: just attribute name (implicit, treat as virtual from 'description')
                            # Check if it's in the schema and is a "simple" type that might be in the data
                            # But only treat it as concrete if it actually exists in the DataFrame
                            is_schema_defined = False
                            try:
                                col_type = self.data_schema.get_col_type(col)
                                is_schema_defined = True
                                logger.debug(f"  Column '{col}' is defined in schema with type: {col_type}")
                                
                                # Even if it's a simple type in the schema, if it's not in the DataFrame,
                                # it must be extracted from description
                                if self.check_col_ok_without_llm(col_type) and col in child_df.columns:
                                    logger.debug(f"  Column '{col}' is concrete structured column (exists in data)")
                                    exist_cols.append(col)
                                    continue
                            except (KeyError, AttributeError):
                                logger.debug(f"  Column '{col}' is not defined in schema")
                                pass
                            
                            # It's a virtual attribute - extract from 'description' column
                            column_name = 'description'
                            attribute_name = col
                            logger.debug(f"  Column '{col}' is virtual attribute - will extract from '{column_name}' column")
                        
                        # Add to extraction list
                        if column_name not in to_extract_cols:
                            to_extract_cols[column_name] = [attribute_name]
                        else:
                            to_extract_cols[column_name].append(attribute_name)

            logger.info(f"Columns to extract directly: {exist_cols}")
            logger.info(f"Columns requiring LLM extraction: {to_extract_cols}")
            
            result_df = child_df[exist_cols].reset_index(drop=True)
            for col, attrs in to_extract_cols.items():
                if col not in child_df.columns:
                    logger.error(f"Column '{col}' not in DataFrame columns: {list(child_df.columns)}")
                logger.info(f"Extracting attributes {attrs} from column '{col}' using LLM (processing {len(child_df)} rows)...")
                prompt = self.data_schema.get_extract_prompt(col, attrs)
                if "id" not in child_df.columns:
                    df_id = None
                else:
                    df_id = child_df["id"]
                tmp_df = llm_extractor(child_df[col], col, attrs, prompt, self.data_schema, df_id=df_id)
                logger.debug(f"LLM extraction completed, extracted shape: {tmp_df.shape}")
                result_df = pd.concat([result_df, tmp_df], axis=1)

            logger.info(f"PROJECT completed. Result shape: {result_df.shape}")
            return result_df

    def print_plan(self, level=0):
        print(''.join([' ' for _ in range(level)]) + self.name + '(' + ', '.join(self.project_columns) + ')')
        if self.children:
            for child in self.children:
                child.print_plan(level+1)


class FilterOperator(Operator):
    def __init__(self, source_data, expression):
        super().__init__(source_data, 'FILTER')
        self.expression = expression
        assert isinstance(self.expression, ConjunctionAndExpr) or isinstance(self.expression, ConjunctionOrExpr)

    def get_filter_info(self):
        def extract_comparison_info(expr):
            left = expr.left
            if '.' in left:
                col_name = left.split('.')[0]
                attr_name = left.split('.')[1]
                return col_name, attr_name
            else:
                return left, None
        
        def get_and_info(and_expr):
            comp_strings = []
            column_attrs = {}
            
            for expr in and_expr.children:
                if isinstance(expr, ComparisonExpr):
                    comp_string = f"({expr.left} {expr.op} {expr.right})"
                    comp_strings.append(comp_string)
                    
                    col_name, attr_name = extract_comparison_info(expr)
                    if col_name not in column_attrs:
                        column_attrs[col_name] = []
                    if attr_name and attr_name not in column_attrs[col_name]:
                        column_attrs[col_name].append(attr_name)
            
            return f"AND([{', '.join(comp_strings)}])", [f"AND([{', '.join(comp_strings)}])"], column_attrs
        
        def get_or_info(or_expr):
            and_strings = []
            all_column_attrs = {}
            
            for and_expr in or_expr.children:
                if isinstance(and_expr, ConjunctionAndExpr):
                    and_string, _,column_attrs = get_and_info(and_expr)
                    and_strings.append(and_string)
                    
                    for col_name, attrs in column_attrs.items():
                        if col_name not in all_column_attrs:
                            all_column_attrs[col_name] = []
                        for attr in attrs:
                            if attr not in all_column_attrs[col_name]:
                                all_column_attrs[col_name].append(attr)
            
            return f"OR([{', '.join(and_strings)}])", and_strings, all_column_attrs
        
        if isinstance(self.expression, ConjunctionAndExpr):
            filter_string, and_strings, column_attrs_dict = get_and_info(self.expression)
        elif isinstance(self.expression, ConjunctionOrExpr):
            filter_string, and_strings, column_attrs_dict = get_or_info(self.expression)
        else:
            raise ValueError("Unsupported expression type")
        
        return filter_string, and_strings, column_attrs_dict

    def next_test(self, skip=False):
        logger.info(f"Executing FILTER operator: {self.expression}")
        child_df = self.children[0].next(skip=skip)
        logger.debug(f"Child operator returned DataFrame shape: {child_df.shape if child_df is not None else 'None'}")

        if skip:
            return child_df

        print(self.expression)
        if isinstance(self.expression, ConjunctionAndExpr):
            and_expr = self.expression
            row_indices_list = []
            for expr in and_expr.children:
                assert isinstance(expr, ComparisonExpr)
                left = expr.left
                left_type = self.data_schema.get_col_type(left)
                if self.check_col_ok_without_llm(left_type):
                    row_indices = expr.get_row_indices_structured(left_type, child_df)
                    row_indices_list.append(row_indices)
            
            row_indices = and_expr.get_row_indices_unstructured(child_df, self.data_schema)
            row_indices_list.append(row_indices)
            print(row_indices)

            filtered_indices = set(row_indices_list[0])
            for row_indices in row_indices_list[1:]:
                filtered_indices &= set(row_indices)

        elif isinstance(self.expression, ConjunctionOrExpr):
            or_indices_list = []
            for and_expr in self.expression.children:
                assert isinstance(and_expr, ConjunctionAndExpr)
                and_indices_list = []
                row_indices_list = []
                for expr in and_expr.children:
                    assert isinstance(expr, ComparisonExpr)
                    left = expr.left
                    left_type = self.data_schema.get_col_type(left)
                    if self.check_col_ok_without_llm(left_type):
                        row_indices = expr.get_row_indices_structured(left_type, child_df)
                        row_indices_list.append(row_indices)
                row_indices = and_expr.get_row_indices_unstructured(child_df, self.data_schema)
                row_indices_list.append(row_indices)

                and_filtered_indices = set(row_indices_list[0])
                for row_indices in row_indices_list[1:]:
                    and_filtered_indices &= set(row_indices)

                or_indices_list.append(and_filtered_indices)
                
            filtered_indices = set(or_indices_list[0])
            for row_indices in or_indices_list[1:]:
                filtered_indices |= set(row_indices)

        filtered_indices = list(filtered_indices)
        filtered_indices.sort()
        child_df = child_df.iloc[list(filtered_indices)].reset_index(drop=True)
        return child_df

    def next(self, skip=False):
        logger.info(f"Executing FILTER operator: {self.expression}")
        child_df = self.children[0].next(skip=skip)
        logger.debug(f"Child operator returned DataFrame shape: {child_df.shape if child_df is not None else 'None'}")

        if skip:
            logger.debug("Skipping filter execution (skip=True)")
            return child_df

        logger.debug(f"Filter expression: {self.expression}")

        def _column_exists_for_expr(frame, expr_left: str) -> bool:
            # Direct match (e.g., age)
            if any(str(c).lower() == expr_left.lower() for c in frame.columns):
                return True
            # Base column match when expr is "col.attr"
            base_col = expr_left.split('.')[0] if '.' in expr_left else expr_left
            return any(str(c).lower() == base_col.lower() for c in frame.columns)

        if isinstance(self.expression, ConjunctionAndExpr):
            logger.debug("Processing AND expression")
            and_expr = self.expression
            row_indices_list = []
            
            # Check if we have any semantic predicates
            has_semantic = any(expr.op == 'SEMANTIC' for expr in and_expr.children)
            
            for expr in and_expr.children:
                assert isinstance(expr, ComparisonExpr)
                left = expr.left
                left_type = self.data_schema.get_col_type(left)
                logger.debug(f"  Filter condition: {expr.left} {expr.op} {expr.right}")
                logger.debug(f"    Column type: {left_type}")
                logger.debug(f"    Operator: {expr.op}")
                
                # Handle semantic predicates with direct LLM filtering
                if expr.op == 'SEMANTIC':
                    logger.debug(f"    Semantic predicate: {expr.right} (using LLM filtering)")
                    # For semantic predicates, use LLM to filter rows
                    from f import llm_filter
                    semantic_query = expr.right
                    # Create a prompt for LLM filtering
                    prompt = f"Does the following text discuss: {semantic_query}?\n\nText: {{text}}\n\nAnswer with YES or NO."
                    
                    matched_indices = []
                    for idx, row in child_df.iterrows():
                        if 'description' in child_df.columns:
                            text = row['description']
                            try:
                                result = llm_filter(text, prompt)
                                if result == 1:  # llm_filter returns 1 for match, 0 for no match
                                    matched_indices.append(idx)
                            except Exception as e:
                                logger.debug(f"Error filtering row {idx}: {e}")
                    
                    logger.debug(f"    Semantic filter matched {len(matched_indices)} rows")
                    row_indices_list.append(matched_indices)
                    continue
                
                is_structured = self.check_col_ok_without_llm(left_type)
                has_column = _column_exists_for_expr(child_df, expr.left)
                logger.debug(f"    Is structured (ok without LLM): {is_structured}")
                logger.debug(f"    Column present in current frame: {has_column}")
                if is_structured and has_column:
                    row_indices = expr.get_row_indices_structured(left_type, child_df)
                    logger.debug(f"    Structured filter matched {len(row_indices)} rows")
                    if len(row_indices) <= 20:
                        logger.debug(f"    Matched indices: {row_indices}")
                    row_indices_list.append(row_indices)
                elif is_structured and not has_column:
                    logger.debug(
                        "    Structured attribute missing in current frame; "
                        "deferring to unstructured filter path"
                    )
            
            # Only call get_row_indices_unstructured if there are non-semantic predicates needing it
            if not has_semantic or len(row_indices_list) == 0:
                # If we only have semantic predicates or no predicates yet, check for unstructured ones
                non_semantic_indices = and_expr.get_row_indices_unstructured(child_df, self.data_schema)
                if non_semantic_indices and len(non_semantic_indices) > 0:
                    row_indices_list.append(non_semantic_indices)
                    logger.debug(f"Unstructured filter matched {len(non_semantic_indices)} rows")
            
            logger.debug(f"Total filter groups: {len(row_indices_list)}")
            
            if len(row_indices_list) == 0:
                logger.warning("No filter conditions matched any rows - returning empty DataFrame")
                return child_df.iloc[[]].reset_index(drop=True)

            filtered_indices = set(row_indices_list[0])
            for row_indices in row_indices_list[1:]:
                filtered_indices &= set(row_indices)
            filtered_indices = list(filtered_indices)
            filtered_indices.sort()
            logger.info(f"AND filter: {len(child_df)} -> {len(filtered_indices)} rows after filtering")
            child_df = child_df.iloc[list(filtered_indices)].reset_index(drop=True)

        elif isinstance(self.expression, ConjunctionOrExpr):
            logger.debug("Processing OR expression")
            remain_df = child_df.copy()
            new_df = pd.DataFrame()
            logger.debug(f"OR expression has {len(self.expression.children)} AND groups")
            for and_expr in self.expression.children:
                assert isinstance(and_expr, ConjunctionAndExpr)
                and_indices_list = []
                row_indices_list = []
                for expr in and_expr.children:
                    assert isinstance(expr, ComparisonExpr)
                    left = expr.left
                    left_type = self.data_schema.get_col_type(left)
                    is_structured = self.check_col_ok_without_llm(left_type)
                    has_column = _column_exists_for_expr(remain_df, expr.left)
                    if is_structured and has_column:
                        row_indices = expr.get_row_indices_structured(left_type, remain_df)
                        row_indices_list.append(row_indices)
                row_indices = and_expr.get_row_indices_unstructured(remain_df, self.data_schema)
                row_indices_list.append(row_indices)

                and_filtered_indices = set(row_indices_list[0])
                for row_indices in row_indices_list[1:]:
                    and_filtered_indices &= set(row_indices)

                and_filtered_indices = list(and_filtered_indices)
                and_filtered_indices.sort()
                new_df = pd.concat([new_df, remain_df.iloc[and_filtered_indices]])
                remain_df = remain_df.drop(and_filtered_indices).reset_index(drop=True)

                if remain_df.empty:
                    logger.debug("All rows matched, breaking early")
                    break
            logger.info(f"OR filter: {len(child_df)} -> {len(new_df)} rows after filtering")
            child_df = new_df.reset_index(drop=True)
        return child_df
    
    def print_plan(self, level=0):
        print(''.join([' ' for _ in range(level)]) + self.name + '(' + str(self.expression) + ')')
        if self.children:
            for child in self.children:
                child.print_plan(level+1)

class GroupbyOperator(Operator):
    # groupby + aggregate
    def __init__(self, source_data, groupby_columns=None, aggregate_columns=None):
        super().__init__(source_data, 'GROUP_BY')
        if groupby_columns is None and aggregate_columns is None:
            raise ValueError("Either groupby_columns or aggregate_columns must be provided")
        
        if groupby_columns is None:
            self.groupby_columns = []
        else:
            self.groupby_columns = [col.strip() for col in groupby_columns]
        if aggregate_columns is None:
            self.aggregate_columns = []
        else:
            self.aggregate_columns = aggregate_columns
    
    def next(self, skip=False):
        logger.info(f"Executing GROUP_BY operator")
        logger.info(f"  Group by columns: {self.groupby_columns}")
        logger.info(f"  Aggregate columns: {self.aggregate_columns}")
        logger.debug(f"  Aggregation strategy: {AGGR_STRATEGY}")

        if AGGR_STRATEGY == 'skip-filter':
            logger.debug("Skipping filter (AGGR_STRATEGY='skip-filter')")
            skip = True

        # Try to pass skip to child if it supports it
        try:
            child_df = self.children[0].next(skip=skip)
        except TypeError:
            child_df = self.children[0].next()
        logger.debug(f"Child operator returned DataFrame shape: {child_df.shape if child_df is not None else 'None'}")

        filter_sys_prompt = None
        if skip:
            if self.children[0].name == 'FILTER':
                filter_cond_str, and_strings, filter_column_attrs = self.children[0].get_filter_info()
                print(filter_cond_str, and_strings, filter_column_attrs)
                filter_sys_prompt = self.data_schema.get_filter_aggr_prompt(filter_cond_str, filter_column_attrs)
                filter_sys_prompt_split = self.data_schema.get_filter_aggr_prompt_split(and_strings, filter_column_attrs)

        if child_df.empty:
            aggr_columns = []
            for col_dict in self.aggregate_columns:
                col = list(col_dict.keys())[0]
                func = list(col_dict.values())[0]
                aggr_columns.append(func + '(' + col + ')')
            all_columns =  self.groupby_columns + aggr_columns
            result_df = pd.DataFrame(columns=all_columns)
            for g_col in self.groupby_columns:
                col = g_col.split('.')[0]
                attr = g_col.split('.')[1]
                attr_type = self.data_schema.get_attr_type(col, attr)
                if attr_type == "varchar":
                    attr_type = "str"
                elif attr_type == "int":
                    attr_type = "int"
                elif attr_type == "float":
                    attr_type = "float"
                result_df[g_col] = result_df[g_col].astype(attr_type)
            for a_col in aggr_columns:
                if a_col.startswith('count'):
                    result_df[a_col] = result_df[a_col].astype('int')
                elif a_col.startswith('sum'):
                    result_df[a_col] = result_df[a_col].astype('float')
                elif a_col.startswith('avg'):
                    result_df[a_col] = result_df[a_col].astype('float')
            for g_col in self.groupby_columns:
                result_df.loc[0, g_col] = pd.NA
            for a_col in aggr_columns:
                result_df.loc[0, a_col] = pd.NA

            return result_df

        if self.groupby_columns:
            is_all_normal = True
            is_all_llm = True
            for col in self.groupby_columns:
                col_type = self.data_schema.get_col_type(col)
                if not self.check_col_ok_without_llm(col_type):
                    is_all_normal = False
                if self.check_col_ok_without_llm(col_type):
                    is_all_llm = False

            if is_all_normal:
                columns_to_agg = set()
                agg_dict = {}
                count_star = False
                for col_dict in self.aggregate_columns:
                    col = list(col_dict.keys())[0]
                    func = list(col_dict.values())[0]
                    if func == 'avg':
                        pd_func = 'mean'
                    elif func == 'count':
                        pd_func = 'count'
                        if col == '*':
                            count_star = True
                            continue
                    elif func == 'sum':
                        pd_func = 'sum'
                    columns_to_agg.add(col)
                    agg_dict[func+'('+col+')'] = (col, pd_func)

                columns_to_agg = list(columns_to_agg)

                child_df = child_df[columns_to_agg + self.groupby_columns].reset_index(drop=True)
                
                # Handle COUNT(*) case - if agg_dict is empty and we have count_star, use size()
                if count_star and not agg_dict:
                    result_df = child_df.groupby(self.groupby_columns).size().reset_index(name='count(*)')
                else:
                    result_df = child_df.groupby(self.groupby_columns).agg(**agg_dict)
                    if count_star:
                        result_df['count(*)'] = child_df.groupby(self.groupby_columns).size()
                    result_df = result_df.reset_index()

            elif is_all_llm:
                labels_dict = {}
                for col in self.groupby_columns:
                    col_name = col.split('.')[0]
                    attr_name = col.split('.')[1]

                    sampled_df = child_df[col_name].sample(frac=GROUP_EXTRACT_SAMPLE_RATIO).reset_index(drop=True)
                    sys_prompt = self.data_schema.get_groupby_labels_split_prompt(col_name, attr_name)
                    labels = llm_groupby_labels_split(sampled_df, col_name, sys_prompt, self.data_schema)
                    labels.append('None')
                    labels_dict[col] = labels
                print(labels_dict)

                n = child_df.shape[0]
                array = np.empty((n, 0))
                column_list = []
                for col in self.groupby_columns:
                    col_name = col.split('.')[0]
                    col_type = self.data_schema.get_col_type(col_name)
                    if col_name not in column_list:
                        column_list.append(col_name)
                        col_embeds = gen_embeds(child_df, col_name, col_type, self.data_schema)
                        array = np.hstack((array, col_embeds))
                dim = array.shape[1]
                if n < N_CENTROIDS * 2:
                    agg = Aggregator(1, dim, N_ITER, verbose=True, gpu=True, ratio_samples=1.)
                else:
                    agg = Aggregator(N_CENTROIDS, dim, N_ITER, verbose=True, gpu=True)
                agg.fit(array.astype('float32'))

                cluster_dict = agg.get_cluster_dict()
                sampled_cluster_dict = agg.stratified_sample(cluster_dict)

                sample_idx = []
                for key in sampled_cluster_dict.keys():
                    sample_idx.extend(sampled_cluster_dict[key])
                weights = agg.compute_weights(cluster_dict, sampled_cluster_dict)
                
                keys = list(labels_dict.keys())
                values = list(labels_dict.values())

                cartesian_product = list(itertools.product(*values))
                candidate_groups = [dict(zip(keys, combination)) for combination in cartesian_product]
                sampled_df = child_df.iloc[sample_idx]
            
                sys_prompt = self.data_schema.get_groupby_classify_prompt(labels_dict, candidate_groups)
                sampled_cluster_result = llm_cluster(sampled_df, column_list, labels_dict, sys_prompt, self.data_schema, candidate_groups)
                sampled_cluster_result_id = [candidate_groups.index(cluster) for cluster in sampled_cluster_result]
                
                print(len(sampled_cluster_result_id), len(sample_idx))
                assert len(sampled_cluster_result_id) == len(sample_idx)
                print(candidate_groups)
                result_dict = {}
                aggr_columns = []
                for sample_cluster_id in set(sampled_cluster_result_id):
                    result_dict[sample_cluster_id] = {}
                for col_dict in self.aggregate_columns:
                    col = list(col_dict.keys())[0]
                    func = list(col_dict.values())[0]
                    aggr_columns.append(func + '(' + col + ')')
                    if col == '*':
                        assert func == 'count'
                        for sample_cluster_id in set(sampled_cluster_result_id):
                            new_sample_idx = [sample_idx[i] for i in range(len(sample_idx)) if sampled_cluster_result_id[i] == sample_cluster_id]
                            new_sampled_df = child_df.iloc[new_sample_idx]
                            if skip:
                                count_result = agg.count_aggregator_df_test(new_sampled_df, weights, self.data_schema, 
                                    filter_columns_attrs=filter_column_attrs, filter_sys_prompt=filter_sys_prompt, filter_sys_prompt_split=filter_sys_prompt_split)
                            else:
                                count_result = agg.count_aggregator_df(new_sampled_df, weights)
                            result_dict[sample_cluster_id]['count(*)'] = count_result
                    else:
                        col_name = col.split('.')[0]
                        attr_name = col.split('.')[1]
                        sys_prompt = self.data_schema.get_extract_prompt(col_name, [attr_name])
                        extract_df = llm_extractor(sampled_df[col_name], col_name, [attr_name], sys_prompt, self.data_schema)
                        assert sampled_df.shape[0] == extract_df.shape[0]
                        sampled_df = sampled_df.reset_index(drop=True)
                        extract_df = extract_df.reset_index(drop=True)
                        sampled_df = pd.concat([sampled_df, extract_df], axis=1)
                        for sample_cluster_id in set(sampled_cluster_result_id):
                            new_sample_idx = [i for i in range(len(sample_idx)) if sampled_cluster_result_id[i] == sample_cluster_id]
                            if skip:
                                new_sampled_df = sampled_df.iloc[new_sample_idx]
                                if func == 'count':
                                    count_result = agg.count_aggregator_df_test(new_sampled_df, weights, self.data_schema, 
                                        filter_columns_attrs=filter_column_attrs, filter_sys_prompt=filter_sys_prompt, filter_sys_prompt_split=filter_sys_prompt_split)
                                    result_dict[sample_cluster_id]['count('+col+')'] = count_result
                                elif func == 'sum':
                                    sum_result = agg.sum_aggregator_df_test(new_sampled_df, col, weights, self.data_schema, 
                                        filter_columns_attrs=filter_column_attrs, filter_sys_prompt=filter_sys_prompt, filter_sys_prompt_split=filter_sys_prompt_split)
                                    result_dict[sample_cluster_id]['sum('+col+')'] = sum_result
                                elif func == 'avg':
                                    sum_result = agg.sum_aggregator_df_test(new_sampled_df, col, weights, self.data_schema, 
                                        filter_columns_attrs=filter_column_attrs, filter_sys_prompt=filter_sys_prompt, filter_sys_prompt_split=filter_sys_prompt_split)
                                    count_result = agg.count_aggregator_df_test(new_sampled_df, weights, self.data_schema, 
                                        filter_columns_attrs=filter_column_attrs, filter_sys_prompt=filter_sys_prompt, filter_sys_prompt_split=filter_sys_prompt_split)
                                    if count_result == 0:
                                        avg_result = 0
                                    else:
                                        avg_result = sum_result / count_result
                                    result_dict[sample_cluster_id]['avg('+col+')'] = avg_result
                            else:
                                new_sampled_df = sampled_df[col].iloc[new_sample_idx]
                                if func == 'count':
                                    count_result = agg.count_aggregator_df(new_sampled_df, weights)
                                    result_dict[sample_cluster_id]['count('+col+')'] = count_result
                                elif func == 'sum':
                                    sum_result = agg.sum_aggregator_df(new_sampled_df, weights)
                                    result_dict[sample_cluster_id]['sum('+col+')'] = sum_result
                                elif func == 'avg':
                                    sum_result = agg.sum_aggregator_df(new_sampled_df, weights)
                                    count_result = agg.count_aggregator_df(new_sampled_df, weights)
                                    if count_result == 0:
                                        avg_result = 0
                                    else:
                                        avg_result = sum_result / count_result
                                    result_dict[sample_cluster_id]['avg('+col+')'] = avg_result

                all_columns = self.groupby_columns + aggr_columns
                result_df = pd.DataFrame(columns=all_columns)
                for g_col in self.groupby_columns:
                    col = g_col.split('.')[0]
                    attr = g_col.split('.')[1]
                    attr_type = self.data_schema.get_attr_type(col, attr)
                    if attr_type == "varchar":
                        attr_type = "str"
                    elif attr_type == "int":
                        attr_type = "int"
                    elif attr_type == "float":
                        attr_type = "float"
                    result_df[g_col] = result_df[g_col].astype(attr_type)
                for a_col in aggr_columns:
                    if a_col.startswith('count'):
                        result_df[a_col] = result_df[a_col].astype('int')
                    elif a_col.startswith('sum'):
                        result_df[a_col] = result_df[a_col].astype('float')
                    elif a_col.startswith('avg'):
                        result_df[a_col] = result_df[a_col].astype('float')
                for sample_cluster_id in set(sampled_cluster_result_id):
                    for g_col in self.groupby_columns:
                        if g_col in candidate_groups[sample_cluster_id]:
                            result_df.loc[sample_cluster_id, g_col] = candidate_groups[sample_cluster_id][g_col]
                        else:
                            result_df.loc[sample_cluster_id, g_col] = pd.NA
                    for a_col in aggr_columns:
                        if a_col in result_dict[sample_cluster_id]:
                            result_df.loc[sample_cluster_id, a_col] = result_dict[sample_cluster_id][a_col]
                        else:
                            result_df.loc[sample_cluster_id, a_col] = pd.NA
                result_df = result_df.reset_index(drop=True)
                
        else:
            columns_to_agg = set()
            for col_dict in self.aggregate_columns:
                col = list(col_dict.keys())[0]
                func = list(col_dict.values())[0]
                if col == '*':
                    continue
                columns_to_agg.add(col)
            columns_to_agg = list(columns_to_agg)
            is_all_normal = True
            is_all_llm = True
            for col in columns_to_agg:
                col_type = self.data_schema.get_col_type(col)
                if not self.check_col_ok_without_llm(col_type):
                    is_all_normal = False
                if self.check_col_ok_without_llm(col_type):
                    is_all_llm = False
            # 没有groupby_columns
            # 选出发生聚合的列
            if is_all_normal:
                agg_dict = {}
                count_star = False
                for col_dict in self.aggregate_columns:
                    col = list(col_dict.keys())[0]
                    func = list(col_dict.values())[0]
                    if func == 'avg':
                        pd_func = 'mean'
                    elif func == 'count':
                        pd_func = 'count'
                        if col == '*':
                            count_star = True
                            continue
                    elif func == 'sum':
                        pd_func = 'sum'
                    agg_dict[func+'('+col+')'] = (col, pd_func)
                child_df = child_df[columns_to_agg].reset_index(drop=True)
                result_df = child_df.agg(**agg_dict).reset_index()
            
            else: 
                n = child_df.shape[0]
                array = np.empty((n, 0))
                column_list = []
                for col_dict in self.aggregate_columns:
                    col = list(col_dict.keys())[0]
                    func = list(col_dict.values())[0]
                    if col != "*":
                        col_name = col.split('.')[0]
                        col_type = self.data_schema.get_col_type(col_name)
                        if col_name not in column_list:
                            column_list.append(col_name)
                            col_embeds = gen_embeds(child_df, col_name, col_type, self.data_schema)
                            array = np.hstack((array, col_embeds))
                    elif col == "*":
                        all_columns = self.data_schema.get_all_columns()
                        for col_name in all_columns:
                            col_type = self.data_schema.get_col_type(col_name)
                            if not self.check_col_ok_without_llm(col_type):
                                if col_name not in column_list:
                                    column_list.append(col_name)
                                    col_embeds = gen_embeds(child_df, col_name, col_type, self.data_schema)
                                    array = np.hstack((array, col_embeds))

                dim = array.shape[1]
                if n < N_CENTROIDS * 2:
                    agg = Aggregator(1, dim, N_ITER, verbose=True, gpu=True, ratio_samples=1.)
                else:
                    agg = Aggregator(N_CENTROIDS, dim, N_ITER, verbose=True, gpu=True)
                agg.fit(array.astype('float32'))

                cluster_dict = agg.get_cluster_dict()
                sampled_cluster_dict = agg.stratified_sample(cluster_dict)

                sample_idx = []
                for key in sampled_cluster_dict.keys():
                    sample_idx.extend(sampled_cluster_dict[key])
                weights = agg.compute_weights(cluster_dict, sampled_cluster_dict)

                sampled_df = child_df.iloc[sample_idx]

                result_dict = {}
                aggr_columns = []
                for col_dict in self.aggregate_columns:
                    col = list(col_dict.keys())[0]
                    func = list(col_dict.values())[0]
                    aggr_columns.append(func + '(' + col + ')')
                    if col == '*':
                        assert func == 'count'
                        if skip:
                            count_result = agg.count_aggregator_df_test(sampled_df, weights, self.data_schema, 
                                filter_columns_attrs=filter_column_attrs, filter_sys_prompt=filter_sys_prompt, filter_sys_prompt_split=filter_sys_prompt_split)
                        else:
                            count_result = agg.count_aggregator_df(sampled_df, weights)
                        result_dict['count(*)'] = count_result
                    else:
                        col_name = col.split('.')[0]
                        attr_name = col.split('.')[1]
                        sys_prompt = self.data_schema.get_extract_prompt(col_name, [attr_name])
                        extract_df = llm_extractor(sampled_df[col_name], col_name, [attr_name], sys_prompt, self.data_schema)
                        assert sampled_df.shape[0] == extract_df.shape[0]
                        sampled_df = sampled_df.reset_index(drop=True)
                        extract_df = extract_df.reset_index(drop=True)
                        sampled_df = pd.concat([sampled_df, extract_df], axis=1)
                        if skip:
                            new_sampled_df = sampled_df
                            if func == 'count':
                                count_result = agg.count_aggregator_df_test(new_sampled_df, weights, self.data_schema, 
                                    filter_columns_attrs=filter_column_attrs, filter_sys_prompt=filter_sys_prompt, filter_sys_prompt_split=filter_sys_prompt_split)
                                result_dict['count('+col+')'] = count_result
                            elif func == 'sum':
                                sum_result = agg.sum_aggregator_df_test(new_sampled_df, col, weights, self.data_schema, 
                                    filter_columns_attrs=filter_column_attrs, filter_sys_prompt=filter_sys_prompt, filter_sys_prompt_split=filter_sys_prompt_split)
                                result_dict['sum('+col+')'] = sum_result
                            elif func == 'avg':
                                sum_result = agg.sum_aggregator_df_test(new_sampled_df, col, weights, self.data_schema, 
                                    filter_columns_attrs=filter_column_attrs, filter_sys_prompt=filter_sys_prompt, filter_sys_prompt_split=filter_sys_prompt_split)
                                count_result = agg.count_aggregator_df_test(new_sampled_df, weights, self.data_schema, 
                                    filter_columns_attrs=filter_column_attrs, filter_sys_prompt=filter_sys_prompt, filter_sys_prompt_split=filter_sys_prompt_split)
                                if count_result == 0:
                                    avg_result = 0
                                else:
                                    avg_result = sum_result / count_result
                                result_dict['avg('+col+')'] = avg_result
                        else:
                            new_sampled_df = sampled_df[col]
                            if func == 'count':
                                count_result = agg.count_aggregator_df(new_sampled_df, weights)
                                result_dict['count('+col+')'] = count_result
                            elif func == 'sum':
                                sum_result = agg.sum_aggregator_df(new_sampled_df, weights)
                                result_dict['sum('+col+')'] = sum_result
                            elif func == 'avg':
                                sum_result = agg.sum_aggregator_df(new_sampled_df, weights)
                                count_result = agg.count_aggregator_df(new_sampled_df, weights)
                                if count_result == 0:
                                    avg_result = 0
                                else:
                                    avg_result = sum_result / count_result
                                result_dict['avg('+col+')'] = avg_result

                all_columns = aggr_columns
                result_df = pd.DataFrame(columns=all_columns)
                for a_col in aggr_columns:
                    if a_col.startswith('count'):
                        result_df[a_col] = result_df[a_col].astype('int')
                    elif a_col.startswith('sum'):
                        result_df[a_col] = result_df[a_col].astype('float')
                    elif a_col.startswith('avg'):
                        result_df[a_col] = result_df[a_col].astype('float')
                for a_col in aggr_columns:
                    result_df.loc[0, a_col] = result_dict[a_col]
                result_df = result_df.reset_index(drop=True)
        return result_df
    
    def print_plan(self, level=0):
        if self.aggregate_columns:
            print(''.join([' ' for _ in range(level)]) + 'AGGREGATE' + 
                  '(' + ', '.join([list(col.values())[0] + '(' + list(col.keys())[0] + ')' for col in self.aggregate_columns]) + ')')

        if self.groupby_columns:
            print(''.join([' ' for _ in range(level+1)]) + 'GROUP_BY' + '(' + ', '.join(self.groupby_columns) + ')')
        
        if self.children:
            for child in self.children:
                child.print_plan(level+2)

class OrderbyOperator(Operator):
    def __init__(self, source_data, orderby_columns):
        super().__init__(source_data, 'ORDER_BY')
        self.orderby_columns = []
        self.ascending = []
        for orderby_column in orderby_columns:
            orderby_column = orderby_column.strip()
            if orderby_column.endswith('DESC'):
                self.orderby_columns.append(orderby_column[:-4].strip())
                self.ascending.append(False)
            elif orderby_column.endswith('ASC'):
                self.orderby_columns.append(orderby_column[:-3].strip())
                self.ascending.append(True)
            else:
                self.orderby_columns.append(orderby_column)
                self.ascending.append(True)

    def next(self):
        print('Exec ORDER_BY:', self.orderby_columns)
        child_df = self.children[0].next()
        return child_df.sort_values(by=self.orderby_columns,
                                    ascending=self.ascending).reset_index(drop=True)
    
    def print_plan(self, level=0):
        print(''.join([' ' for _ in range(level)]) + self.name + '(' + ', '.join(self.orderby_columns) + ')')
        if self.children:
            for child in self.children:
                child.print_plan(level+1)

class ScanOperator(Operator):
    def __init__(self, source_data, tables):
        super().__init__(source_data, 'SCAN')
        assert len(tables) == 1
        self.tables = []
        for table in tables:
            assert table.strip() in source_data.tables_name
            self.tables.append(table.strip())
    
    def next(self, skip=False):
        logger.info(f"Executing SCAN operator on table: {self.tables[0]}")
        json_data = self.data_schema.source_data[self.tables[0]]
        df = pd.DataFrame(json_data)
        logger.info(f"SCAN completed. Loaded {len(df)} rows from table '{self.tables[0]}'")
        logger.debug(f"Columns: {list(df.columns)}")
        return df
    
    def is_empty(self):
        return not self.tables
    
    def print_plan(self, level=0):
        print(''.join([' ' for _ in range(level)]) + self.name + '(' + ', '.join(self.tables) + ')')
    
class LimitOperator(Operator):
    def __init__(self, source_data, limit):
        super().__init__(source_data, 'LIMIT')
        self.limit = limit[0]

    def next(self):
        logger.info(f"Executing LIMIT operator: {self.limit}")
        child_df = self.children[0].next()
        logger.debug(f"Child returned {len(child_df)} rows, limiting to {self.limit}")
        result = child_df.head(int(self.limit))
        logger.info(f"LIMIT completed. Result: {len(result)} rows")
        return result

    def print_plan(self, level=0):
        print(''.join([' ' for _ in range(level)]) + self.name + '(' + self.limit + ')')
        if self.children:
            for child in self.children:
                child.print_plan(level+1)