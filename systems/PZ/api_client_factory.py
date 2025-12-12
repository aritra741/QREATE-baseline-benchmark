from threading import Lock

from openai import OpenAI
from together import Together

from palimpzest.constants import APIClient


# Ollama configuration
OLLAMA_BASE_URL = "http://localhost:11434/v1"


class APIClientFactory:
    _instances = {}
    _lock = Lock()

    @classmethod
    def get_client(cls, api_client: APIClient, api_key: str = None):
        """Get a singleton instance of the requested API client."""
        if api_client not in cls._instances:
            with cls._lock:  # Ensure thread safety
                if api_client not in cls._instances:  # Double-check inside the lock
                    cls._instances[api_client] = cls._create_client(api_client, api_key)
        return cls._instances[api_client]

    @staticmethod
    def _create_client(api_client: APIClient, api_key: str = None):
        """Create a new client instance based on the api_client name."""
        if api_client == APIClient.OLLAMA:
            # Use Ollama for qwen3:8b with no-think mode
            return OpenAI(api_key="ollama", base_url=OLLAMA_BASE_URL)
        elif api_client == APIClient.OPENAI:
            # Redirect OpenAI calls to Ollama
            return OpenAI(api_key="ollama", base_url=OLLAMA_BASE_URL)
        elif api_client == APIClient.TOGETHER:
            # Redirect Together calls to Ollama
            return OpenAI(api_key="ollama", base_url=OLLAMA_BASE_URL)
        else:
            raise ValueError(f"Unknown api_client: {api_client}")
