from query_optimization import *
from segment_index import *
from document_index import *

########################################################
####### replace the OPENAI_KEY with your own key #######
########################################################
OPENAI_KEY = 'sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
init_chatgpt(OPENAI_KEY)

########################################################
############### fill up the sql query ##################
########################################################
sql_query = """Your query here"""

########################################################
######### fill up the sql query description ############
########################################################
sql_query_description = """Your query description here"""

########################################################
################## fill up the dir #####################
########################################################
file_lake_dir = "Your directory of the data lake"               # the directory of the data lake
result_dir = 'Your directory of the result '                    # the directory of the result
file_candidate_dir = "Your directory of the candidate files"    # the directory of the candidate files

all_file_list = os.listdir(file_lake_dir)

if not os.path.exists(result_dir):
    os.makedirs(result_dir)
if not os.path.exists(file_candidate_dir):
    os.makedirs(file_candidate_dir)


# Ducument-level Index Construction
file_list = get_document_index(OPENAI_KEY, sql_query, sql_query_description, all_file_list, file_lake_dir, file_candidate_dir, n=20)

# Segment-level Index Construction
get_segment_index(OPENAI_KEY, sql_query, sql_query_description, file_list, file_lake_dir, file_candidate_dir, n=10)


# sampled data
sampled_data_path = file_candidate_dir + "/data.csv"
data = pd.read_csv(sampled_data_path)

# Query Optimization and Excute the Query
output = generate_output(sql_query, result_dir, file_candidate_dir, data)
