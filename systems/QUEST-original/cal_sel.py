#提取filter_conditions
import re
import pandas as pd

#extract filter conditions
def extract_filter_condition(where_clause):
    conditions = []
    current_condition = []
    paren_stack = 0
    
    # Split by AND/OR and parentheses, but keep the separators for further processing
    tokens = re.split(r'(\s+AND\s+|\s+OR\s+|\(|\))', where_clause, flags=re.IGNORECASE)
    
    for token in tokens:
        token = token.strip()
        if token == '':
            continue

        if token == '(':
            paren_stack += 1
            if current_condition:
                conditions.append(' '.join(current_condition).strip())
                current_condition = []
            current_condition.append(token)
        elif token == ')':
            paren_stack -= 1
            current_condition.append(token)
            if paren_stack == 0:
                conditions.append(' '.join(current_condition).strip())
                current_condition = []
        elif token.upper() == 'AND' or token.upper() == 'OR':
            if paren_stack == 0 and current_condition:
                conditions.append(' '.join(current_condition).strip())
                current_condition = []
            elif paren_stack > 0:
                current_condition.append(token.upper())
        else:
            current_condition.append(token)
            if paren_stack == 0 and (len(current_condition) == 3 or len(current_condition) > 3 and (current_condition[-2].upper() in ['AND', 'OR'])):
                conditions.append(' '.join(current_condition).strip())
                current_condition = []

    if current_condition:
        conditions.append(' '.join(current_condition).strip())

    # Recursively extract conditions from parentheses
    final_conditions = []
    for condition in conditions:
        if condition.startswith('(') and condition.endswith(')'):
            inner_conditions = extract_filter_condition(condition[1:-1].strip())
            final_conditions.extend(inner_conditions)
        else:
            final_conditions.append(condition)

    return final_conditions


def isDigit(value):
    for char in value:
        if char not in "0123456789":
            return False
    return True

def cal_sel(data,filter_data):
    filter_cond = filter_data['name']
    #print("filter_data: ",filter_cond)
    atrribute,operator,value = filter_cond.split(maxsplit=2)
    
    try:
        data[atrribute] = pd.to_numeric(data[atrribute], errors='coerce')
    except ValueError:
        pass

    if operator == ">":
        if isDigit(value):
            selectivity = pd.Series(data[atrribute]).gt(int(value)).sum() / len(data[atrribute])
        else:
            selectivity = pd.Series(data[atrribute]).gt(value).sum() / len(data[atrribute])
    elif operator == "<":
        if isDigit(value):
            selectivity = pd.Series(data[atrribute]).lt(int(value)).sum() / len(data[atrribute])
        else:
            selectivity = pd.Series(data[atrribute]).lt(value).sum() / len(data[atrribute])
    elif operator == "=":
        if isDigit(value):
            selectivity = pd.Series(data[atrribute]).eq(int(value)).sum() / len(data[atrribute])
        else:
            selectivity = pd.Series(data[atrribute]).eq(value).sum() / len(data[atrribute])
    elif operator == ">=":
        if isDigit(value):
            selectivity = pd.Series(data[atrribute]).ge(int(value)).sum() / len(data[atrribute])
        else:
            selectivity = pd.Series(data[atrribute]).ge(value).sum() / len(data[atrribute])
    elif operator == "<=":
        if isDigit(value):
            selectivity = pd.Series(data[atrribute]).le(int(value)).sum() / len(data[atrribute])
        else:
            selectivity = pd.Series(data[atrribute]).le(value).sum() / len(data[atrribute])
    elif operator == "!=":
        if isDigit(value):
            selectivity = pd.Series(data[atrribute]).ne(int(value)).sum() / len(data[atrribute])
        else:
            selectivity = pd.Series(data[atrribute]).ne(value).sum() / len(data[atrribute])
    
    return selectivity

