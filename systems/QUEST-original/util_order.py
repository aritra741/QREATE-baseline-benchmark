import re
######################################handle sql##############################################
def parse_sql(sql_query):
    where_clause = re.search(r'WHERE (.+)', sql_query, re.IGNORECASE).group(1)
    return where_clause

def extract_composite_expressions(expression):
    composite_expressions = []
    start = 0
    stack = 0
    for i, char in enumerate(expression):
        if char == '(':
            if stack == 0:
                start = i
            stack += 1
        elif char == ')':
            stack -= 1
            if stack == 0:
                composite_expressions.append(expression[start:i + 1])
    return composite_expressions


def parse_input(input_text):
    attributes = {}
    attribute_blocks = input_text.strip().split('\n\n')
    for block in attribute_blocks:
        lines = block.strip().split('\n')
        name = lines[0].strip()
        key_sentences = []
        for line in lines[1:]:
            if ':' in line:
                key_sentences.append(line.split(':')[1].strip())
            else:
                key_sentences.append(line)
        attributes[name] = {
            'key_sentences': key_sentences,
        }
    return attributes

def remove_punctuation(s):
    s = s.replace("[", "")
    s = s.replace("]", "")
    s = s.replace("'''", "")
    s = s.replace("```\n", "")
    s = s.replace("\n```", "")
    s = s.replace("`", "")
    s = s.replace("'", "")
    s = s.replace("\"", "")
    s = s.replace("\n", "")
    return s

######################################handle sql##############################################

######################################caculate filter_condition's S value##############################################

# calculate selectivity
def calculate_s(selectivity, key_sentences, formula='default'):
    total_tokens = sum(len(re.findall(r'\w+', sentence)) for sentence in key_sentences)
    if formula == 'default':
        s_value = (1 - selectivity) / total_tokens
    elif formula == 'alternate':
        s_value = selectivity / total_tokens
    return s_value

# calculate composite selectivity
def calculate_composite_s(filters, filter_dqtq, operator):
    selectivities = [filter_dqtq[f]['selectivity'] for f in filters if f in filter_dqtq]
    tokens = [len(re.findall(r'\w+', filter_dqtq[f]['key_sentences'][0])) for f in filters if f in filter_dqtq]

    if not tokens:  # Ensure there are tokens to avoid division by zero
        return 0

    if operator == 'AND':
        composite_selectivity = 1
        for sel in selectivities:
            composite_selectivity *= sel
        composite_tokens = sum(tokens)
    elif operator == 'OR':
        composite_selectivity = 1
        for sel in selectivities:
            composite_selectivity *= (1-sel)
        composite_selectivity = 1 - composite_selectivity
        composite_tokens = sum(tokens)
    
    composite_s = (1 - composite_selectivity) / composite_tokens
    return composite_s

# split the logical expression into parts and evaluate each part and combine them
def parse_logical_expression(expression):
    stack = []
    current = []
    paren_stack = []

    for token in re.split(r'(\s+AND\s+|\s+OR\s+|\(|\))', expression, flags=re.IGNORECASE):
        token = token.strip()
        if token == '':
            continue

        if token == '(':
            if current:
                paren_stack.append(current)
                current = []
            paren_stack.append(token)
        elif token == ')':
            if current:
                stack.append(current)
                current = []
            while paren_stack and paren_stack[-1] != '(':
                stack.append(paren_stack.pop())
            paren_stack.pop() 
            if paren_stack:
                current = paren_stack.pop()
        elif token.upper() == 'AND' or token.upper() == 'OR':
            if current:
                stack.append(current)
                current = []
            stack.append(token.upper())
        else:
            current.append(token)

    if current:
        stack.append(current)
    
    return stack

# function to evaluate the logical expression
def evaluate_logical_expression(expression_parts, filter_data):
    if isinstance(expression_parts, list) and len(expression_parts) == 1:
        sub_filters = expression_parts[0]
        composite_s = calculate_composite_s(sub_filters, filter_data, 'AND')
        return sub_filters, composite_s

    while 'AND' in expression_parts or 'OR' in expression_parts:
        if 'AND' in expression_parts:
            and_index = expression_parts.index('AND')
            left = expression_parts[and_index - 1]
            right = expression_parts[and_index + 1]
            combined_filters = left + right
            composite_s = calculate_composite_s([f for f in combined_filters if isinstance(f, str)], filter_data, 'AND')
            expression_parts = expression_parts[:and_index - 1] + [[combined_filters, composite_s]] + expression_parts[and_index + 2:]
        elif 'OR' in expression_parts:
            or_index = expression_parts.index('OR')
            left = expression_parts[or_index - 1]
            right = expression_parts[or_index + 1]
            combined_filters = left + right
            composite_s = calculate_composite_s([f for f in combined_filters if isinstance(f, str)], filter_data, 'OR')
            expression_parts = expression_parts[:or_index - 1] + [[combined_filters, composite_s]] + expression_parts[or_index + 2:]

    return expression_parts[0]

def handle_sql(where_clause, filter_data):
    #print("where_clause: ", where_clause)
    composite_expressions = extract_composite_expressions(where_clause)
    #print("composite_expressions: ", composite_expressions)

    if len(filter_data) == 1:
        #print("there is only one filter_condition")
        return [(list(filter_data.keys())[0], filter_data[list(filter_data.keys())[0]]['s_value'])]


    composite_s_values = []
    final_sorted_filters = []
    flat_internal_filters = []

    for idx, composite_expression in enumerate(composite_expressions):
        #print("\nProcessing composite_expression: ", composite_expression)
        
        internal_expression_parts = parse_logical_expression(composite_expression[1:-1])
        internal_filters, composite_s = evaluate_logical_expression(internal_expression_parts, filter_data)

        #print(f"internal_filters for composite_expression {idx + 1}: {internal_filters}")
        #print(f"S value for composite_expression {idx + 1}: {composite_s:.4f}")

        for item in internal_filters:
            if isinstance(item, list):
                flat_internal_filters.extend(item)
            elif isinstance(item, str):
                flat_internal_filters.append(item)

        unique_internal_filters = list(set(flat_internal_filters))
        sorted_internal_s_values = sorted([(f, filter_data[f]['s_value']) for f in unique_internal_filters if isinstance(f, str)], key=lambda x: x[1], reverse=True)
        final_sorted_filters.extend(sorted_internal_s_values)

        composite_s_values.append((composite_expression, composite_s))

    remaining_clause = where_clause
    for idx, composite_expression in enumerate(composite_expressions):
        remaining_clause = remaining_clause.replace(composite_expression, f"composite_filter_{idx + 1}")
    
    expression_parts = parse_logical_expression(remaining_clause)
    #print("\nRemaining Expression Parts:", expression_parts)
    best_composite_filters, remaining_s = evaluate_logical_expression(expression_parts, filter_data)
    #print(f"Best composite filters: {best_composite_filters}")

    flat_best_composite_filters = []
    for item in best_composite_filters:
        if isinstance(item, list):
            for sub_item in item:
                if isinstance(sub_item, list):
                    flat_best_composite_filters.extend(sub_item)
                else:
                    flat_best_composite_filters.append(sub_item)
        elif isinstance(item, str):
            flat_best_composite_filters.append(item)

    #print(f"Remaining filters: {flat_best_composite_filters}")

    remaining_s_values = [(f, filter_data[f]['s_value']) for f in flat_best_composite_filters if isinstance(f, str) and f in filter_data]
    
    for f, s_value in remaining_s_values:
        composite_s_values.append((f, s_value))
        final_sorted_filters.append((f, s_value))

    sorted_composite_s_values = sorted(composite_s_values, key=lambda x: x[1], reverse=True)
    
    final_priority_order = []
    seen_expressions = set()  
    for expression, s_value in sorted_composite_s_values:
        if expression in seen_expressions:
            continue  
        seen_expressions.add(expression)
        #print(f"expression: {expression}, s_value: {s_value}")
        if expression not in composite_expressions:
            final_priority_order.append((expression, s_value))
        else:
            internal_sorted_filters = [item for item in final_sorted_filters if item[0] in expression]
            unique_internal_sorted_filters = list(dict.fromkeys(internal_sorted_filters))
            #print(f"Internal sorted filters for {expression}: {unique_internal_sorted_filters}")
            final_priority_order.extend(unique_internal_sorted_filters)

    # print("\nFinal Priority Order:")
    # for expression, s_value in final_priority_order:
    #     print(f"{expression}: S = {s_value:.4f}")

    return final_priority_order

# get the best filters order based on the s_value
def get_best_filter(filters, filter_data):
    filter_s_values = []
    for filter_cond in filters:
        filter_name = filter_cond.split()[0].strip()  # Extracting the attribute name
        if filter_name in filter_data:
            filter_s_values.append((filter_cond, filter_data[filter_name]['s_value']))
    return sorted(filter_s_values, key=lambda x: x[1], reverse=True)

###############################################caculate filter_condition's S value##############################################

#########################################caculate filter_condition's bool value###########################################


def evaluate_logical_expression_bool_true(expression_parts):
    #print("Initial expression_parts:", expression_parts) 

    for i in range(len(expression_parts)):
        if isinstance(expression_parts[i], list):
            expression_parts[i] = evaluate_logical_expression_bool_true(expression_parts[i])
            #print("Evaluated nested expression_parts:", expression_parts)  

    while 'AND' in expression_parts or 'OR' in expression_parts:
        if 'AND' in expression_parts:
            and_index = expression_parts.index('AND')
            left = expression_parts[and_index - 1]
            right = expression_parts[and_index + 1]
            #print(f"Evaluating AND between: {left} AND {right}") 

            combined_bool = (left if isinstance(left, bool) else evaluate_condition_true(left)) and \
                            (right if isinstance(right, bool) else evaluate_condition_true(right))

            #print(f"Combined result for AND: {combined_bool}")  
            expression_parts = expression_parts[:and_index - 1] + [combined_bool] + expression_parts[and_index + 2:]
            #print("Updated expression_parts after AND:", expression_parts) 

        elif 'OR' in expression_parts and ('AND' not in expression_parts or expression_parts.index('OR') < expression_parts.index('AND')):
            or_index = expression_parts.index('OR')
            left = expression_parts[or_index - 1]
            right = expression_parts[or_index + 1]
            #print(f"Evaluating OR between: {left} OR {right}")  

            combined_bool = (left if isinstance(left, bool) else evaluate_condition_true(left)) or \
                            (right if isinstance(right, bool) else evaluate_condition_true(right))

            #print(f"Combined result for OR: {combined_bool}")  
            expression_parts = expression_parts[:or_index - 1] + [combined_bool] + expression_parts[or_index + 2:]
            #print("Updated expression_parts after OR:", expression_parts) 

    final_result = expression_parts[0] if isinstance(expression_parts, list) else expression_parts
    final_result = final_result if isinstance(final_result, bool) else evaluate_condition_true(final_result)
    #print("set true Final result:", final_result) 
    return final_result

def calculate_bool_value_true(sql_query) -> bool:
    # Extracting the WHERE clause
    where_clause = re.search(r'WHERE (.+)', sql_query, re.IGNORECASE).group(1)
    
    # Parse the logical expression
    expression_parts = parse_logical_expression4booltrue(where_clause)
    
    # Evaluate the logical expression
    bool_value = evaluate_logical_expression_bool_true(expression_parts)
    
    return bool_value

def evaluate_condition_true(condition):
    if 'True' in condition or 'true' in condition:
        return True
    elif 'False' in condition or 'false' in condition:
        return False
    elif isinstance(condition, bool):
        return condition

    # Assume all other conditions are true for simplicity
    return True

def parse_logical_expression4booltrue(expression):
    stack = []
    current = []
    paren_stack = []

    for token in re.split(r'(\s+AND\s+|\s+OR\s+|\(|\))', expression, flags=re.IGNORECASE):
        token = token.strip()
        if token == '':
            continue

        if token == '(':
            if current:
                stack.append(current)
                current = []
            stack.append(token)
        elif token == ')':
            if current:
                stack.append(current)
                current = []
            nested_expr = []
            while stack and stack[-1] != '(':
                nested_expr.insert(0, stack.pop())
            stack.pop()  
            current = evaluate_logical_expression_bool_true(nested_expr)
            stack.append(current)
            current = []
        elif token.upper() == 'AND' or token.upper() == 'OR':
            if current:
                stack.append(current)
                current = []
            stack.append(token.upper())
        else:
            current.append(token)

    if current:
        stack.append(current)
    
    return stack

def parse_logical_expression4boolfalse(expression):
    stack = []
    current = []
    paren_stack = []

    for token in re.split(r'(\s+AND\s+|\s+OR\s+|\(|\))', expression, flags=re.IGNORECASE):
        token = token.strip()
        if token == '':
            continue

        if token == '(':
            if current:
                stack.append(current)
                current = []
            stack.append(token)
        elif token == ')':
            if current:
                stack.append(current)
                current = []
            nested_expr = []
            while stack and stack[-1] != '(':
                nested_expr.insert(0, stack.pop())
            stack.pop()  
            current = evaluate_logical_expression_bool_false(nested_expr)
            stack.append(current)
            current = []
        elif token.upper() == 'AND' or token.upper() == 'OR':
            if current:
                stack.append(current)
                current = []
            stack.append(token.upper())
        else:
            current.append(token)

    if current:
        stack.append(current)
    
    return stack

def calculate_bool_value_false(sql_query) -> bool:
    # Extracting the WHERE clause
    where_clause = re.search(r'WHERE (.+)', sql_query, re.IGNORECASE).group(1)
    
    # Parse the logical expression
    expression_parts = parse_logical_expression4boolfalse(where_clause)
    
    # Evaluate the logical expression
    bool_value = evaluate_logical_expression_bool_false(expression_parts)
    
    return bool_value

def evaluate_logical_expression_bool_false(expression_parts):
    #print("Initial expression_parts:", expression_parts)  

    for i in range(len(expression_parts)):
        if isinstance(expression_parts[i], list):
            expression_parts[i] = evaluate_logical_expression_bool_false(expression_parts[i])
            #print("Evaluated nested expression_parts:", expression_parts)  

    
    while 'AND' in expression_parts or 'OR' in expression_parts:
        if 'AND' in expression_parts:
            and_index = expression_parts.index('AND')
            left = expression_parts[and_index - 1]
            right = expression_parts[and_index + 1]
            #print(f"Evaluating AND between: {left} AND {right}")  

            combined_bool = (left if isinstance(left, bool) else evaluate_condition_false(left)) and \
                            (right if isinstance(right, bool) else evaluate_condition_false(right))

            #print(f"Combined result for AND: {combined_bool}") 
            expression_parts = expression_parts[:and_index - 1] + [combined_bool] + expression_parts[and_index + 2:]
            #print("Updated expression_parts after AND:", expression_parts) 

        elif 'OR' in expression_parts and ('AND' not in expression_parts or expression_parts.index('OR') < expression_parts.index('AND')):
            or_index = expression_parts.index('OR')
            left = expression_parts[or_index - 1]
            right = expression_parts[or_index + 1]
            #print(f"Evaluating OR between: {left} OR {right}")  

            combined_bool = (left if isinstance(left, bool) else evaluate_condition_false(left)) or \
                            (right if isinstance(right, bool) else evaluate_condition_false(right))

            #print(f"Combined result for OR: {combined_bool}")  
            expression_parts = expression_parts[:or_index - 1] + [combined_bool] + expression_parts[or_index + 2:]
            #print("Updated expression_parts after OR:", expression_parts)  

    final_result = expression_parts[0] if isinstance(expression_parts, list) else expression_parts
    final_result = final_result if isinstance(final_result, bool) else evaluate_condition_false(final_result)
    #print("set false Final result:", final_result)  
    return final_result


def evaluate_condition_false(condition):
    #print("condition: ",condition)
    if 'True' in condition or 'true' in condition:
        return True
    elif 'False' in condition or 'false' in condition:
        return False
    elif isinstance(condition, bool):
        return condition
    
    # For simplicity, assume all other conditions are false for now
    return False

#########################################caculate filter_condition's bool value############################################