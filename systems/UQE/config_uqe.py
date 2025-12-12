USE_BART = False

BATCH_SIZE = 15
BUDGET = 0
# without filter sampling
# small sample
# BUDGET = 0
# BATCH_SIZE = 10

# aggregation strategy
AGGR_STRATEGY = 'normal'
# AGGR_STRATEGY = 'skip-filter'

# cluster parameters
N_CENTROIDS = 6
N_ITER = 40
# Sampling ratio for extracting classification labels
GROUP_EXTRACT_SAMPLE_RATIO = 0.2
# Sampling ratio in each clustering core
AGGR_CLUSTER_SAMPLE_RATIO = 0.6

# Ollama configuration for qwen2.5:7b-instruct
MODEL = "qwen2.5:7b-instruct"
OPENAI_KEY = "ollama"  # Ollama doesn't require API key
BASE_URL = "http://localhost:11434/v1"

# No-think configuration
ENABLE_THINKING = False
