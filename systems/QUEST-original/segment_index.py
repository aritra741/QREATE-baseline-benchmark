import json
import openai
import os
import pandas as pd
import random
from transformers import BertTokenizer, BertModel
import torch
import pickle
import cupy as cp
import numpy as np
from tqdm import tqdm
from torch import Tensor
from transformers import AutoTokenizer, AutoModel


# initialize the OpenAI API
def init_chatgpt(api_key):
    if hasattr(openai, "api_key"):
        openai.api_key = api_key
    base_url = os.getenv("QUEST_OPENAI_BASE_URL", "").strip()
    if base_url:
        if hasattr(openai, "base_url"):
            openai.base_url = base_url
        elif hasattr(openai, "api_base"):
            openai.api_base = base_url


def _chat_completion_create(messages, max_tokens=500, n=1, stop=None, temperature=0):
    model_name = os.getenv("QUEST_LLM_MODEL", "gpt-4o")
    # Prefer OpenAI SDK v1 interface; fall back to legacy v0.
    if hasattr(openai, "chat") and hasattr(openai.chat, "completions"):
        return openai.chat.completions.create(
            model=model_name,
            messages=messages,
            max_tokens=max_tokens,
            n=n,
            stop=stop,
            temperature=temperature,
        )
    return openai.ChatCompletion.create(
        model=model_name,
        messages=messages,
        max_tokens=max_tokens,
        n=n,
        stop=stop,
        temperature=temperature,
    )


def _response_text(response):
    message = response.choices[0].message
    if isinstance(message, dict):
        return str(message.get("content", "")).strip()
    return str(getattr(message, "content", "")).strip()


def remove_punctuation(s):
    s = s.replace("```\n", "")
    s = s.replace("\n```", "")
    s = s.replace("`", "")
    s = s.replace("plaintext\n", "")
    return s

# Function to call OpenAI API and get the domain
def ask_sample_file(sql_query, sql_query_description, text):
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": f"""
        I have a text, and I need to extract specific information from text to populate a table in a database. 
        If an attribute is not found, leave it empty. 
        Also, provide the key sentnce from the original text from which you inferred the corresponding attribute values. 
        Only list the key sentnce, and they must be complete and from the original text.
        Below is the query and query description of the table:{sql_query, sql_query_description}
        Hrer is the text:{text}


        ### Only attributes,values and key sentences without any other information.
        ### each attributes should be listed.
        ### If an value is not found, leave this value empty(e.g., [attribute1]: ).
        ### Format the output as follows:
        [attribute1]: [value1]
        Key sentnce 1: [Key sentnce 1]

        [attribute2]: [value2]
        Key sentnce 1: [Key sentnce 1]
        
        [attribute3]: [value3]
        Key sentnce 1: [Key sentnce 1]
        ...

        """
        }
    ]
    
    response = _chat_completion_create(
        messages=messages,
        max_tokens=500,
        n=1,
        stop=None,
        temperature=0,
    )
    
   # Extract the response text
    answer = _response_text(response)
    return remove_punctuation(answer)

def get_result(sql_query, sql_query_description, sample_flist, data, file_candidate_dir):
    for i in tqdm(sample_flist):
        # try:
            file = data + i + '/no_title.txt'
            output = file_candidate_dir + '/key/' +  i + ".txt"
            with open(file, 'r', encoding='utf-8',errors='ignore') as f:
                text = f.read()

            result = ask_sample_file(sql_query, sql_query_description, text)

            with open(output, 'w', encoding='utf-8',errors='ignore') as f:
                f.write(result)

# get sample file csv
def ground_truth(sample_flist, l, output, file_candidate_dir):
    dic = {key: [] for key in l}
    print(l)
    dic['file'] = []
    for i in tqdm(sample_flist):
        # try:
            dic_temp = {key: [''] for key in l}
            file = file_candidate_dir + '/key/' + i + ".txt"
            with open(file, 'r', encoding='utf-8',errors='ignore') as f:
                text = f.read().split('\n')
                for y in text:
                    j = y.split(': ')
                    if y == '':
                        continue
                    key = j[0]
                    if ']' in key:
                        key = key.split(']')[0].split('[')[-1]
                    if len(j) < 2:
                        value = ''
                    else:
                        value = j[1]
                    # print(key, value)
                    if '[' in value or 'None' in value or value == 'N/A' or 'information' in value:
                        value = ''
                    if key not in dic:
                        continue
                    else:
                        dic_temp[key] = [value]
                        # print(key, value)
                
            
            dic['file'].append(i)
            for k,v in dic_temp.items():
                dic[k].append(v[0])
        # except:
        #     print(i)
    df = pd.DataFrame(dic)

    df.to_csv(output, index=False) 


# embedding
def get_embed(sentences):
 
    tokenizer = AutoTokenizer.from_pretrained('/intfloat/multilingual-e5-large')
    model = AutoModel.from_pretrained('/intfloat/multilingual-e5-large')

    model = model.to('cuda')

    embeddings = []
    for x in sentences:
       
        inputs = tokenizer(x, return_tensors='pt', truncation=True, padding=True, max_length=512)
        inputs = {k: v.to('cuda') for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model(**inputs)

        embedding = outputs.last_hidden_state[:, 0, :].squeeze().cpu().numpy()
        embeddings.append(embedding)

    return np.array(embeddings)

# cosine_similarity
def cosine_similarity_gpu(vecs1, vecs2):
    
    vecs1 = cp.array(vecs1)
    vecs2 = cp.array(vecs2)

    vecs1 = vecs1 / cp.linalg.norm(vecs1, axis=1, keepdims=True)
    vecs2 = vecs2 / cp.linalg.norm(vecs2, axis=1, keepdims=True)

    cosine_sim = cp.dot(vecs1, vecs2.T)
    return cosine_sim

# all segments embedding
def get_all_embedding(flist, data, file_candidate_dir):
    all_index = {}
    for file in tqdm(flist):
        input_path = data  + file + '/content.txt'
        with open(input_path, 'r', encoding='utf-8',errors='ignore') as f1:
            input = f1.read().split('#'*50+'\n')
        vectors = np.array(get_embed(input))
        # print(len(vectors), file)
        all_index[file+'.txt'] = vectors
    index_save_path = file_candidate_dir + '/all.pkl'
    pickle.dump(all_index, open(index_save_path, 'wb'))
    return all_index


def get_sample_embedding(sample_list, k, data, file_candidate_dir):
    dic = {key: [] for key in k}
    sample_index = {}

    for file in tqdm(sample_list):
        content = []
        file_path = os.path.join(file_candidate_dir, 'key', f"{file}.txt")
        input_path = os.path.join(data, file, 'content.txt')
        output_path = os.path.join(file_candidate_dir, 'candi', f"{file}.txt")

        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            txt = f.read().split('\n\n')
        with open(input_path, 'r', encoding='utf-8', errors='ignore') as f1:
            input_segments = f1.read().split('#' * 50 + '\n')

        for i in txt:
            j = i.split('\n')
            if len(j) < 1 or ': ' not in j[0]:
                continue
            key_part = j[0].split(': ')[0]
            value_part = j[0].split(': ')[1] if ': ' in j[0] else ''
            
            if ']' in key_part:
                key = key_part.split(']')[0].split('[')[-1]
            else:
                key = key_part

            value = value_part.strip()
            
            if value:
                if len(j) > 1:
                    if ': ' in j[1]:
                        v = j[1].split(': ')[-1].strip()
                    else:
                        v = j[1].strip()  
                else:
                    v = ''  
                dic[key].append(v)
                
                found = False
                for z in input_segments:
                    if v and v[8:-8] in z:
                        content.append(f"{key}\nCandidate Sentences: {z}")
                        found = True
                        break
                if not found:
                    content.append(f"{key}\nCandidate Sentences: ")
            else:
                content.append(f"{key}\nCandidate Sentences: ")

        with open(output_path, 'w', encoding='utf-8', errors='ignore') as f:
            f.write('\n\n'.join(content))

    threshold = {}
    for keys, values in dic.items():
        if not values:
            continue  
        vectors = np.array(get_embed(values))
        sample_index[keys] = vectors
        cosine_sim = cosine_similarity_gpu(vectors, vectors)
        th = np.min(cosine_sim).item()
        if th > 0.8:
            th = 0.5
        threshold[keys] = th

    index_save_path = os.path.join(file_candidate_dir, 'sample.pkl')
    pickle.dump(sample_index, open(index_save_path, 'wb'))

    threshold_path = os.path.join(file_candidate_dir, 'threshold.json')
    json.dump(threshold, open(threshold_path, 'w'))

    return threshold, sample_index

# all file candidate segements
def get_candidate(origin_list, data, file_candidate_dir):
    all = pickle.load(open(file_candidate_dir + '/all.pkl', 'rb'))
    sample = pickle.load(open(file_candidate_dir + '/sample.pkl', 'rb'))
    threshold = json.load(open(file_candidate_dir + '/threshold.json', 'r'))

    for file in origin_list:
        content = []
        input_path = data + file + '/content.txt'
        output_path = file_candidate_dir + '/candi/' + file + '.txt'

        with open(input_path, 'r', encoding='utf-8', errors='ignore') as f1:
            input = f1.read().split('#'*50 + '\n')

        file_embedding = all[file + '.txt']

        for key, value in sample.items():
            text = key + '\n'
            cosine_sim = cosine_similarity_gpu(file_embedding, value)
            avg_cosine_sim = cp.mean(cosine_sim, axis=1).get()

            mask = cp.all(cosine_sim >= threshold[key], axis=1)
            indices = cp.where(mask)[0].get()

            if len(indices) == 0:
                text += 'Candidate Sentence: '
            else:
                filtered_avg_sim = avg_cosine_sim[indices]
                top_two_indices = np.argsort(filtered_avg_sim)[-2:][::-1]  
                for idx in top_two_indices:
                    text += 'Candidate Sentence: ' + input[indices[idx]]

            content.append(text)

        with open(output_path, 'w', encoding='utf-8', errors='ignore') as f:
            f.write('\n\n'.join(content))

def get_segment_index(OPENAI_KEY, sql_query, sql_query_description, file_list, file_lake_dir, file_candidate_dir, n=10):
# """
# n is sample file number
# """
    random.seed(42)
    init_chatgpt(OPENAI_KEY)
    k = [i.split(': ')[0] for i in sql_query_description.split('\n')][1:-1]
    sample_list = random.sample(file_list, n)
    origin_list = [i for i in file_list if i not in sample_list]
    print(sample_list)

    get_result(sql_query, sql_query_description, sample_list,file_lake_dir,file_candidate_dir)

    ground_truth(sample_list, k, file_candidate_dir+'/data.csv', file_candidate_dir)
    print("Ground Truth is done")
    
    #run at first time
    get_all_embedding(file_list, file_lake_dir, file_candidate_dir)
    
    get_sample_embedding(sample_list, k, file_lake_dir, file_candidate_dir)
    get_candidate(origin_list, file_lake_dir , file_candidate_dir)
    
    print("segment index is done")


