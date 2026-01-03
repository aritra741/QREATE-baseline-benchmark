"""
Configuration for GEM system.

Defines constants, paths, and settings for the Global Entity Manager.
"""

from pathlib import Path

# ============================================================================
# PATHS
# ============================================================================

# Project root - adjust based on actual location
PROJECT_ROOT = Path(__file__).parent.parent.parent

# GEM system root
GEM_ROOT = PROJECT_ROOT / "systems" / "GEM"

# Cache directory for intermediate results
CACHE_DIR = GEM_ROOT / ".cache"

# Database path for persistent SQLite storage
DB_PATH = CACHE_DIR / "gem.sqlite"

# Source data directory
SOURCE_DATA_DIR = PROJECT_ROOT / "source_data"

# ============================================================================
# LLM SETTINGS
# ============================================================================

# Ollama configuration
OLLAMA_URL = "http://localhost:11434/v1"
OLLAMA_MODEL = "qwen2.5:7b-instruct"
OLLAMA_API_KEY = "ollama"

# Ollama settings for extraction
EXTRACTION_TIMEOUT = 60  # seconds
EXTRACTION_MAX_RETRIES = 3

# ============================================================================
# EMBEDDING SETTINGS
# ============================================================================

# Sentence transformer model for embeddings
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Embedding settings for blocking
EMBEDDING_DIM = 384  # Dimension of all-MiniLM-L6-v2
SIMILARITY_THRESHOLD = 0.92  # Cosine similarity threshold for blocking (increased from 0.85 to be conservative)
TOP_K_NEIGHBORS = 15  # Number of nearest neighbors to consider

# ============================================================================
# PROCESSING SETTINGS
# ============================================================================

# Tokenizer for chunking
CHUNK_TOKENIZER = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_SIZE = 4000  # Max tokens per chunk
CHUNK_OVERLAP = 200  # Overlap between chunks in tokens

# Batch settings
BATCH_SIZE_EXTRACTION = 5  # Number of documents to extract in parallel
BATCH_SIZE_EMBEDDING = 100  # Number of texts to embed in parallel

# ============================================================================
# RESOLUTION SETTINGS
# ============================================================================

# Resolution settings
RESOLUTION_TIMEOUT = 30  # seconds per resolution call
RESOLUTION_MAX_RETRIES = 2

# ============================================================================
# LOGGING
# ============================================================================

LOG_LEVEL = "INFO"
LOG_DIR = GEM_ROOT / "logs"

# ============================================================================
# INITIALIZATION
# ============================================================================

# Create cache directory on import
CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

