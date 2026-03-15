import re
from util_order import *
import pandas as pd
import random
from cal_sel import *
import os
import time
from llm import *
from tqdm import tqdm

def generate_output(sql_query, result_dir, file_candidate_dir,data):
    where_clause = parse_sql(sql_query)
    where_filter_condition = extract_filter_condition(where_clause)
    where_filter_attribute = []
    for condition in where_filter_condition:
        attr = condition.split()[0]
        if attr not in where_filter_attribute:
            where_filter_attribute.append(attr)

    select_clause = re.search(r'SELECT (.+?) FROM', sql_query, re.IGNORECASE).group(1)
    select_attributes = [attr.strip() for attr in select_clause.split(',')]
    output = pd.DataFrame(columns=select_attributes)

    filter_data = {}
    all_total_token = 0
    all_actual_token = 0
    file_candidate_dir = file_candidate_dir + "/candi/"
    file_list = os.listdir(file_candidate_dir)

    infor = result_dir + "infor.txt"
    start_tie = time.time()

    for onefile in tqdm(file_list, desc="Processing files", unit="file"):
        ###############################################################
        ########################SQL updated parts######################
        ###############################################################
        
        
        input_text = ""
        file_path = file_candidate_dir + onefile
        with open(file_path, "r", encoding='utf-8',errors='ignore') as file:
            input_text = file.read()

        #extract filter condition
        where_clause = parse_sql(sql_query)
        

        ###########################################
        ########acculate selectivity#############
        ###########################################
        filter_cond = extract_filter_condition(where_clause)
        attributes = parse_input(input_text)

        #calculate total token
        total_token = 0
        total_token += len(input_text.split()) + 100
        all_total_token += total_token
        
        for filter_condtion in filter_cond:
            atrribute,operator,value = filter_condtion.split(maxsplit=2)
            selectivity = cal_sel(data, {"name": filter_condtion})
            if atrribute in attributes:
                filter_data[filter_condtion] = {
                    "name": filter_condtion,
                    "selectivity": selectivity,
                    's_value': calculate_s(selectivity, attributes[atrribute]['key_sentences']),
                    "key_sentences": attributes[atrribute]['key_sentences']
                }
            else:
                filter_data[filter_condtion] = {
                    "name": filter_condtion,
                    "selectivity": selectivity,
                    's_value': 0,
                    "key_sentences": []
                }
        ###########################################
        ######## Filter Order Optimization ########
        ###########################################
        try:
            sorted_filters = handle_sql(where_clause, filter_data)
        except:
            continue


        actual_token = 0
        skipthefile = 0
        sql_copy = sql_query
        remaining_attributes = select_attributes.copy()
        curdata = {}
        sorted_filter_cond = []
        mapfilter_cond = {}
        mapfilter_erro = {}

        for filter in sorted_filters:
            sorted_filter_cond.append(filter[0])
        for filter in sorted_filter_cond:
            mapfilter_cond[filter] = 0
            mapfilter_erro[filter] = 0
        remaining_sorted_filter_cond = sorted_filter_cond.copy()
        while remaining_sorted_filter_cond:
            filter_cond_tochange = []
            filter_cond = remaining_sorted_filter_cond[0]
            mapfilter_cond[filter_cond] += 1
            if mapfilter_cond[filter_cond] >= 2:
                if filter_cond in remaining_sorted_filter_cond:
                    remaining_sorted_filter_cond.remove(filter_cond)
                    tochange_filter = [filter_cond,'false']
                    filter_cond_tochange.append(tochange_filter)
                continue

            elif mapfilter_cond[filter_cond] == 1:
                attribute = filter_cond.split()[0].strip()
                key_sentences = ""
                try:
                    for sentence in attributes[attribute]['key_sentences']:
                        key_sentences += sentence
                except:
                    key_sentences = ""
                
                answer = ask_completion4filtercondANDattr(str(remaining_attributes),str(remaining_sorted_filter_cond),key_sentences)
                actual_token += len(key_sentences.split())+100
                answer = remove_punctuation(answer)
                try:
                    attributes_cur_all = answer.split("$$")[1]
                    filter_cond_cur_all = answer.split("$$")[0]
                except:
                    mapfilter_cond[filter_cond] -= 1
                    mapfilter_erro[filter_cond] += 1
                    tochange_filter = [filter_cond,'false']
                    actual_token -= len(key_sentences.split())+100
                    if key_sentences == "":
                        filter_cond_tochange.append(tochange_filter)
                        remaining_sorted_filter_cond.remove(filter_cond)
                        actual_token += len(key_sentences.split())+100
                    

                    for ask_filter_cond,bool_value in filter_cond_tochange:
                        sql_copy = sql_copy.replace(ask_filter_cond,bool_value)
                    

                    sql_copy2 = sql_copy
                    bool_value_set_true = calculate_bool_value_true(sql_copy)
                    bool_value_set_false = calculate_bool_value_false(sql_copy2)
                    #set true to false
                    if bool_value_set_true == False:
                        skipthefile = 1
                        break
                    #set false to true
                    if bool_value_set_false == True:
                        skipthefile = 0
                        break
                    else:
                        skipthefile = 1
                    continue

                #process attributes_cur_all
                try:
                    minidatas = attributes_cur_all.split("##")
                    for minidata in minidatas:
                        dataattr,datavalue = minidata.split(":")
                        curdata[dataattr] = datavalue
                        if dataattr in remaining_attributes:
                            if 'NAN' not in datavalue:
                                remaining_attributes.remove(dataattr)
                except:
                    a = 1
                #extract filter_cond_cur_all
                try:
                    minifilters = filter_cond_cur_all.split("##")
                    for minifilter in minifilters:
                        filter_cond_cur,bool_value = minifilter.split(":")
                        tochange_filter = [filter_cond_cur,bool_value]
                        if 'NAN' not in bool_value:
                            if filter_cond_cur in remaining_sorted_filter_cond:
                                filter_cond_tochange.append(tochange_filter)
                                remaining_sorted_filter_cond.remove(filter_cond_cur)
                        else:
                            if filter_cond_cur == filter_cond:
                                filter_cond_tochange.append([filter_cond_cur,'false'])
                except:
                    filter_cond_tochange.append([filter_cond,'false'])
            
            # set the filter_cond to the bool_value
            for ask_filter_cond,bool_value in filter_cond_tochange:
                sql_copy = sql_copy.replace(ask_filter_cond,bool_value)
            sql_copy2 = sql_copy
            bool_value_set_true = calculate_bool_value_true(sql_copy)
            bool_value_set_false = calculate_bool_value_false(sql_copy2)
            if bool_value_set_true == False:
                skipthefile = 1
                break
            if bool_value_set_false == True:
                skipthefile = 0
                break
            else:
                skipthefile = 1

            
        #if skipthefile == 1, then skip the file
        if skipthefile == 0:          
            key_sentences = ""
            mapattr = {}
            for attr in select_attributes:
                mapattr[attr] = 0
            while remaining_attributes:
                attr = remaining_attributes[0]
                mapattr[attr] += 1
                if mapattr[attr] == 2:
                    remaining_attributes.remove(attr)
                    curdata[attr] = "NAN"
                    continue
                if attr in attributes:
                    key_sentences = ""
                    try:
                        for sentence in attributes[attr]['key_sentences']:
                            key_sentences += sentence + " "
                    except:
                        key_sentences = ""
                    answer = ask_completion4Multattribute(str(remaining_attributes), key_sentences)
                    actual_token += len(key_sentences.split())+75
                    answer = remove_punctuation(answer)
                    try:
                        minidatas = answer.split("##")
                        for minidata in minidatas:
                            dataattr,datavalue = minidata.split(":")
                            curdata[dataattr] = datavalue
                            if dataattr in remaining_attributes:
                                if 'NAN' not in datavalue:
                                    remaining_attributes.remove(dataattr)
                    except:
                        actual_token -= len(key_sentences.split())+75
                
            if len(curdata) != 0:
                curdata['file'] = onefile
                output = output.append(curdata,ignore_index=True)
                data = data.append(curdata,ignore_index=True)
            output.dropna(axis=0, how='all', inplace=True) 
        
        all_actual_token += actual_token


    end_time = time.time()

    with open(infor, "w") as file:
        file.write("all_actual_token: "+str(all_actual_token)+"\n")
        file.write("all_total_token: "+str(all_total_token)+"\n")
        file.write("time: "+str(end_time-start_tie)+"\n")

    output.to_csv(result_dir + "output.csv", index=False)
    print("output saved to: ", result_dir + "output.csv")

    return output
    