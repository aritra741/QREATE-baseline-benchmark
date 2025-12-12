import os
from openai import OpenAI
import tiktoken

# Lazy database connection - only connect when actually needed
_opengauss_conn = None

def get_opengauss_conn():
    """Lazily create database connection only when needed."""
    global _opengauss_conn
    if _opengauss_conn is None:
        from quest.db.connector.connector import create_opengauss_engine
        _opengauss_conn = create_opengauss_engine()
    return _opengauss_conn

# For backward compatibility
opengauss_conn = None  # Will be None until get_opengauss_conn() is called

current_file_path = os.path.abspath(__file__)
dir_name = os.path.dirname(current_file_path)

# Project root (two levels up from this file)
RELATIVE_PROJECT_ROOT_PATH = os.path.join(dir_name, "../..")
ABS_PROJECT_ROOT_PATH = os.path.abspath(RELATIVE_PROJECT_ROOT_PATH)

# Prefer scratch for all generated index artifacts
_default_scratch = os.environ.get(
    "SCRATCH",
    f"/scratch/general/vast/{os.environ.get('USER', '')}"
)
INDEX_ROOT_DIR = os.path.join(
    os.environ.get("QUEST_INDEX_ROOT", _default_scratch),
    "UDA-Bench-main",
    "index"
)
# Global index config location (used by GlobalIndexer)
GLOBAL_INDEX_CONFIG = os.path.join(INDEX_ROOT_DIR, "global_index/global_index.json")


# THRESHOLD
JOIN_EDIT_DISTANCE_THRESHOLD = 0.8
JOIN_SEMANTIC_THRESHOLD = 0.9

RETRIEVE_FULL_THRESHOLD = 0.1


# LOG
LOG_DIR = os.path.join(dir_name, "../tests/log")  # make sure it exists
LOG_DIR_NAME = os.path.join(LOG_DIR, "log_sampling.log")

# local small model
LOCAL_MODEL_DIR = os.path.join(ABS_PROJECT_ROOT_PATH, "model/")

DATASET_DIR = os.path.join(ABS_PROJECT_ROOT_PATH, "data/dataset/")

# LOCAL LLM - Ollama configuration
# IMPORTANT: LiteLLM handles endpoint routing internally, so use base URL without /v1
OLLAMA_BASE = "http://localhost:11434"

# Primary model: qwen2.5:7b-instruct via Ollama (better at structured output)
# LiteLLM format: "ollama/<model_name>" with base URL (no /v1)
LLM_MODEL = 'ollama/qwen2.5:7b-instruct'
API_BASE = OLLAMA_BASE  # Use base URL, NOT /v1

# Embedding model configuration
# IMPORTANT: For Ollama embeddings with LiteLLM, api_base must be base URL (NOT /v1)
API_EMB_MODEL = "ollama/nomic-embed-text"
API_EMB_API_BASE = OLLAMA_BASE  # Use base URL without /v1 for embeddings
API_EMB_API_KEY = "ollama"

# LLM models use Ollama with qwen2.5:7b-instruct (superior structured output)
GPT_MODEL = 'ollama/qwen2.5:7b-instruct'
GPT_API_BASE = OLLAMA_BASE  # Use base URL, NOT /v1
GPT_API_KEY = "ollama"

# Qwen2.5 doesn't use thinking mode
ENABLE_THINKING = False

LLM_BATCH_SIZE = 10

os.environ['OPENAI_API_KEY'] = GPT_API_KEY
os.environ['OPENAI_BASE'] = OLLAMA_BASE
enc = tiktoken.get_encoding("cl100k_base")

Enc_token_cnt = enc

def count_tokens(text):
    tokens = Enc_token_cnt.encode(text)
    return len(tokens)

# OpenAI client for direct Ollama calls (uses /v1 compatible endpoint)
client = OpenAI(
    base_url=f"{OLLAMA_BASE}/v1",  # OpenAI SDK needs /v1, LiteLLM does NOT
    api_key="ollama"
)

# SAMPLE

SAMPLE_NUM = 5
TOPK = 5

ZENDB_TOPK = 5

GROUP_SAMPLE_NUM = 3

# CLUSTER

N_CLUSTERS = 3

# others

VALUE_OP = ['<', '>', '>=', '<=']
