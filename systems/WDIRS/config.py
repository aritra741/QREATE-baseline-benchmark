"""
Configuration module for WDIRS system.
Defines all constants, paths, and system parameters.
"""

import os
from pathlib import Path

# ============================================================================
# Directory Paths
# ============================================================================

# Base directories
WDIRS_DIR = Path(__file__).parent
PROJECT_ROOT = WDIRS_DIR.parent.parent
SOURCE_DATA_DIR = PROJECT_ROOT / "source_data"
QUERY_DIR = PROJECT_ROOT / "Query"
RESULTS_DIR = PROJECT_ROOT / "results"

# WDIRS-specific directories
CACHE_DIR = WDIRS_DIR / ".cache"
DB_DIR = WDIRS_DIR / ".databases"
INDEX_DIR = WDIRS_DIR / ".indexes"
SIEVE_DIR = WDIRS_DIR / ".sieves"

# Create directories if they don't exist
for directory in [CACHE_DIR, DB_DIR, INDEX_DIR, SIEVE_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# ============================================================================
# Database Configuration (SQLite)
# ============================================================================

# SQLite database path (relative to WDIRS directory or absolute)
DB_PATH = os.getenv("WDIRS_DB_PATH", str(DB_DIR / "wdirs.db"))

# Connection string for SQLAlchemy
DATABASE_URI = f"sqlite:///{DB_PATH}"

# ============================================================================
# Text Chunking Configuration
# ============================================================================

# Recursive character splitting parameters
CHUNK_SIZE = 500  # tokens
CHUNK_OVERLAP = 50  # tokens
CHUNK_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

# ============================================================================
# LLM Configuration (Ollama)
# ============================================================================

# Ollama settings
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
OLLAMA_TIMEOUT = 120  # seconds
OLLAMA_MAX_RETRIES = 3
OLLAMA_RETRY_DELAY = 2  # seconds

# LLM extraction parameters
EXTRACTION_BATCH_SIZE = 5  # chunks per batch
EXTRACTION_TEMPERATURE = 0.1  # low temperature for consistency
EXTRACTION_MAX_TOKENS = 2000

# ============================================================================
# Entity Resolution Configuration
# ============================================================================

# Embedding models
BI_ENCODER_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Resolution thresholds
BI_ENCODER_THRESHOLD = 0.75  # for blocking
CROSS_ENCODER_THRESHOLD = 0.95  # for matching
TOP_K_CANDIDATES = 20  # number of candidates to retrieve

# ============================================================================
# Sieve Synthesis Configuration
# ============================================================================

# Sieve synthesis parameters
SIEVE_SAMPLE_SIZE = 5  # chunks to sample for synthesis
SIEVE_REFINEMENT_ITERATIONS = 3  # max refinement iterations
SIEVE_TEST_SIZE = 5  # chunks to test refined sieve

# ============================================================================
# Schema Stabilization Configuration
# ============================================================================

# Schema discovery parameters
SCHEMA_SAMPLE_SIZE = 50  # chunks for schema discovery
SCHEMA_KEY_FREQUENCY_THRESHOLD = 0.20  # 20% frequency to freeze key

# ============================================================================
# Workload Lattice Configuration
# ============================================================================

# Semantic types for column classification
SEMANTIC_TYPES = [
    "PERSON",
    "ORG",
    "DATE",
    "GPE",  # Geo-Political Entity
    "CODE",
    "MONEY",
    "QUANTITY",
    "PRODUCT",
    "EVENT",
    "OTHER"
]

# ============================================================================
# Metadata Registry Configuration
# ============================================================================

# Status values for metadata registry
STATUS_PARTIAL = "PARTIAL"
STATUS_FULL = "FULL"

# ============================================================================
# Logging Configuration
# ============================================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = WDIRS_DIR / "wdirs.log"

# ============================================================================
# Performance Configuration
# ============================================================================

# Parallel processing
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))

# Caching
ENABLE_CACHE = True
CACHE_TTL = 86400  # 24 hours in seconds

# ============================================================================
# Validation Configuration
# ============================================================================

# Data validation
MAX_NULL_RATIO = 0.5  # max ratio of null values in a column
MIN_RECORDS_PER_TABLE = 1  # minimum records to create table

# ============================================================================
# Helper Functions
# ============================================================================

def get_dataset_path(dataset: str) -> Path:
    """Get path to dataset source files."""
    return SOURCE_DATA_DIR / dataset

def get_schema_path(dataset: str) -> Path:
    """Get path to dataset schema file."""
    return QUERY_DIR / dataset / f"{dataset}_attributes.json"

def get_workload_path(dataset: str, query_type: str) -> Path:
    """Get path to SQL workload file."""
    return QUERY_DIR / dataset / query_type / f"{query_type}_queries.sql"

def get_db_path(dataset: str) -> Path:
    """Get path to dataset database."""
    return DB_DIR / f"{dataset}.db"

def get_cache_path(dataset: str, entity: str) -> Path:
    """Get path to cache directory for dataset/entity."""
    cache_path = CACHE_DIR / dataset / entity
    cache_path.mkdir(parents=True, exist_ok=True)
    return cache_path
