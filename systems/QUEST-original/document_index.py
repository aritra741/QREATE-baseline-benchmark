from transformers import BertTokenizer, BertModel
import cupy as cp
import torch
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords
from collections import defaultdict
import string
import numpy as np
import openai
import os
import random
from tqdm import tqdm
import pickle
from torch import Tensor
from transformers import AutoTokenizer, AutoModel

nltk.download('punkt')
nltk.download('stopwords')

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


def _chat_completion_create(messages, max_tokens=512, n=1, stop=None, temperature=0):
    model_name = os.getenv("QUEST_LLM_MODEL", "gpt-4o")
    if hasattr(openai, "ChatCompletion"):
        return openai.ChatCompletion.create(
            model=model_name,
            messages=messages,
            max_tokens=max_tokens,
            n=n,
            stop=stop,
            temperature=temperature,
        )
    return openai.chat.completions.create(
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



# Function to call OpenAI API and get the domain
def ask_sample_file(sql_query, sql_query_description, text):
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": f"""
        I have a text, SQL and SQL descriptions. Please determine whether the attributes provided by the SQL and the text belong to the same category, such as sports, finance, etc.
        Below is the query and query description:{sql_query, sql_query_description}
        Hrer is the text:{text}

        ### The output only give the result(True/False) without any other information.
        """
        }
    ]
    
    response = _chat_completion_create(
        messages=messages,
        max_tokens=512,
        n=1,
        stop=None,
        temperature=0,
    )
    
   # Extract the response text
    answer = _response_text(response)
    return answer

# get text summarize
def summarize_text(text):
    summary_length= 20
    sentences = sent_tokenize(text)
    stop_words = set(stopwords.words('english') + list(string.punctuation))
    word_frequencies = defaultdict(int)
    for sentence in sentences:
        for word in word_tokenize(sentence):
            if word.lower() not in stop_words:
                word_frequencies[word.lower()] += 1
    sentence_scores = {}
    for sentence in sentences:
        for word in word_tokenize(sentence.lower()):
            if word in word_frequencies:
                if sentence not in sentence_scores:
                    sentence_scores[sentence] = word_frequencies[word]
                else:
                    sentence_scores[sentence] += word_frequencies[word]
    summary_sentences = sorted(sentence_scores, key=sentence_scores.get, reverse=True)[:summary_length]
    
    return summary_sentences

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

def get_result(sql_query, sql_query_description, sample_flist, data):
    document_list = []
    # print("get result")
    for i in sample_flist:
        # try:
        # file = input + i + '/no_title.txt'
        file = data +  i + '/no_title.txt'
        print(file)
        with open(file, 'r', encoding='utf-8',errors='ignore') as f:
            text = f.read()
        # if len(text) > 6500:
        #     text = text[:6500]
        if len(text) > 2500:
            text = text[:2500]
        
        # print(text)
        result = ask_sample_file(sql_query, sql_query_description, text)
        print(result)
        if result == 'True':
            document_list.append(i)

    return document_list

def get_all_embedding(document_list, data,file_candidate_dir):
    all_index = {}
    for file in tqdm(document_list):
        input_path = data  + file + '/no_title.txt'
        with open(input_path, 'r', encoding='utf-8',errors='ignore') as f1:
            text = f1.read()
        summary = [' '.join(summarize_text(text))]
        vectors = np.array(get_embed(summary))
        # print(len(vectors), file)
        all_index[file+'.txt'] = vectors
    index_save_path = file_candidate_dir + '/document_all.pkl'
    pickle.dump(all_index, open(index_save_path, 'wb'))
    
    

def get_sample_embedding(document_list, data):
    summary = []
    for file in tqdm(document_list):
        input_path = data + file + '/no_title.txt'
        with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
            summary.append(' '.join(summarize_text(text)))

    vectors = np.array(get_embed(summary))

    cosine_sim = cosine_similarity_gpu(vectors, vectors)
    threshold = np.min(cosine_sim).item()
    # if threshold > 0.7:
    #     threshold = 0.5

    return threshold, vectors

def get_candidate(origin_list, data, document_list, sample_list, file_candidate_dir):
    file_list = sample_list
    all_index = pickle.load(open(file_candidate_dir + '/document_all.pkl', 'rb'))

    threshold, sample_vectors = get_sample_embedding(document_list, data)
    for i in tqdm(origin_list):
        vectors = all_index[i + '.txt']

        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)

        cosine_sim = cosine_similarity_gpu(vectors, sample_vectors)

        mask = cp.all(cosine_sim >= threshold, axis=1)
        indices = cp.where(mask)[0].get()

        if len(indices) != 0:
            file_list.append(i)

    return file_list


def get_document_index(OPENAI_KEY, sql_query, sql_query_description, all_file_list, file_lake_dir, file_candidate_dir, n=20):
# """
# n is sample file number
# """

    init_chatgpt(OPENAI_KEY)
    print("OpenAI API is initialized")
    if n > len(all_file_list):
        n = len(all_file_list)
    print("n:", n)
    random.seed(42)
    sample_list = random.sample(all_file_list, n)
    origin_list = [i for i in all_file_list if i not in sample_list]
    
    print("Sample list is done")
    
    #run at first time
    get_all_embedding(all_file_list, file_lake_dir,file_candidate_dir)
    
    document_list = get_result(sql_query, sql_query_description, sample_list, file_lake_dir)
    print("Document-level get result is done")
    file_list = get_candidate(origin_list, file_lake_dir, document_list, sample_list, file_candidate_dir)
    print("Document-level get candidate is done", len(file_list))

    return file_list



