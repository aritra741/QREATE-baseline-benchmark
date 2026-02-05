"""
Configuration management for QAIRS system.
"""
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
import yaml


class OllamaConfig(BaseModel):
    """Ollama LLM configuration."""
    host: str = "http://localhost:11434"
    model: str = "qwen2.5:7b-instruct"
    temperature: float = 0.0
    max_tokens: int = 4096
    timeout: int = 300


class DatabaseConfig(BaseModel):
    """PostgreSQL database configuration."""
    host: str = "localhost"
    port: int = 5432
    database: str = "qairs"
    user: str = "postgres"
    password: str = ""
    
    @property
    def connection_string(self) -> str:
        """Generate SQLAlchemy connection string."""
        # Support SQLite for testing
        if not self.host or self.host == "":
            # SQLite mode
            if self.database == ":memory:":
                return "sqlite:///:memory:"
            else:
                return f"sqlite:///{self.database}"
        # PostgreSQL mode
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class SieveConfig(BaseModel):
    """Sieve preprocessing configuration."""
    enable_dictionary: bool = True
    enable_regex: bool = True
    enable_ner: bool = False  # Optional, requires GLiNER or spacy model
    
    # Dictionary settings
    dictionary_expansion: bool = True
    max_synonyms_per_term: int = 10
    
    # Regex patterns for type detection
    regex_patterns: Dict[str, str] = Field(default_factory=lambda: {
        "has_date": r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b',
        "has_money": r'\$\s?\d+(?:,\d{3})*(?:\.\d{2})?|\b\d+(?:,\d{3})*(?:\.\d{2})?\s?(?:dollars?|USD)\b',
        "has_phone": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
        "has_email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "has_ssn": r'\b\d{3}-\d{2}-\d{4}\b',
    })
    
    # Storage
    sieve_path: str = "sieve_index.pkl"


class ExtractionConfig(BaseModel):
    """Extraction engine configuration."""
    batch_size: int = 10  # Number of chunks per LLM call
    max_retries: int = 3
    retry_delay: int = 2  # seconds
    
    # Parallel processing
    enable_parallel: bool = True
    max_workers: int = 4  # Number of parallel workers
    
    # View synthesis settings
    extract_denormalized: bool = True  # Extract joined views
    validate_schema: bool = True
    
    # Prompt templates
    system_prompt: str = "You are a strict data extraction engine. Extract structured data from text according to the provided schema."


class QAIRSConfig(BaseModel):
    """Main QAIRS system configuration."""
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    sieve: SieveConfig = Field(default_factory=SieveConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    
    # Corpus settings
    corpus_path: Optional[str] = None
    chunk_size: int = 1000  # characters
    chunk_overlap: int = 100
    
    # System paths
    base_dir: Path = Field(default_factory=lambda: Path(__file__).parent)
    
    @classmethod
    def from_yaml(cls, path: str) -> "QAIRSConfig":
        """Load configuration from YAML file."""
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        return cls(**data)
    
    def to_yaml(self, path: str) -> None:
        """Save configuration to YAML file."""
        with open(path, 'w') as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False)


# Default configuration instance
default_config = QAIRSConfig()
