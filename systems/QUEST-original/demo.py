from query_optimization import *
from segment_index import *
from document_index import *

########################################################
####### replace the OPENAI_KEY with your own key #######
########################################################
OPENAI_KEY = 'sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
init_chatgpt(OPENAI_KEY)

########################################################
############### fill up the sql query ##################
########################################################
sql_query = """SELECT university_name,setting,institutional_control  FROM University WHERE setting = urban OR institutional_control = public"""

########################################################
######### fill up the sql query description ############
########################################################
sql_query_description = """
university_name: The name of the university
setting: The setting of the university
institutional_control: The control of the university
"""

########################################################
################## fill up the dir #####################
########################################################
file_lake_dir = "./datalake/output/"               # the directory of the data lake
result_dir = './result/test2/'                    # the directory of the result
file_candidate_dir = "./candidate"    # the directory of the candidate files,need to contain the candi folder,key folder and data.csv

all_file_list = os.listdir(file_lake_dir)

if not os.path.exists(result_dir):
    os.makedirs(result_dir)
if not os.path.exists(file_candidate_dir):
    os.makedirs(file_candidate_dir)

# Ducument-level Index Construction
# n is sample file number
file_list = get_document_index(OPENAI_KEY, sql_query, sql_query_description, all_file_list, file_lake_dir, file_candidate_dir, n=5)
print("Document-level Index Construction is done")

# n is sample file number
get_segment_index(OPENAI_KEY, sql_query, sql_query_description, file_list, file_lake_dir, file_candidate_dir, n=3)
print("Segment-level Index Construction is done")

# sampled data
sampled_data_path = file_candidate_dir + "/data.csv"
data = pd.read_csv(sampled_data_path)

# # Query Optimization and Excute the Query
output = generate_output(sql_query, result_dir, file_candidate_dir, data)
print(output)
