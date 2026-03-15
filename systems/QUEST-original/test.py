from query_optimization import *

########################################################
####### replace the OPENAI_KEY with your own key #######
########################################################
OPENAI_KEY = 'sk-1Zssb4A7L2lFfna7D109859e3f014c23B9Ed567e602dEf46'
init_chatgpt(OPENAI_KEY)

########################################################
############### fill up the sql query ##################
########################################################
sql_query = """
SELECT name, age, team FROM NBA_players WHERE age < 40
"""

########################################################
######### fill up the sql query description ############
########################################################
sql_query_description = """
name : name of NBA player
age  : NBA player's age
team : NBA player's team
"""

########################################################
################## fill up the dir #####################
########################################################
file_lake_dir = "./datalakes/nbadata"      # the directory of the data lake
result_dir = './result/test/'             # the directory of the result
file_candidate_dir = "./datalakes/nbadata" # the directory of the candidate files

if not os.path.exists(result_dir):
    os.makedirs(result_dir)
if not os.path.exists(file_candidate_dir):
    os.makedirs(file_candidate_dir)


# Two-level Index Construction is done
# offline 阶段

# sampled data
data = pd.read_csv("./datalake/sampled_data/nba.csv")

# Query Optimization and Excute the Query
output = generate_output(sql_query, result_dir, file_candidate_dir,data)
print(output)
