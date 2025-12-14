from utils.contextManager import LLMContextManager
import os
import re


def clean_llm_response(response):
    """
    Clean LLM response by removing <think>...</think> tags.
    Some models (like qwen3) output reasoning in think tags before the actual response.
    
    Args:
        response (str): The raw LLM response.
    
    Returns:
        str: The cleaned response with think tags removed.
    """
    if response is None:
        return response
    
    # Remove complete <think>...</think> tags and their content (handles multiline)
    cleaned = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
    
    # Also remove incomplete <think> blocks (when model runs out of tokens before closing)
    # This handles cases like "<think>reasoning..." without closing tag
    cleaned = re.sub(r'<think>.*$', '', cleaned, flags=re.DOTALL)
    
    # Strip leading/trailing whitespace
    cleaned = cleaned.strip()
    
    return cleaned


class ModelConfig:
    def __init__(self, model_path=None):
        # Default model name for Ollama, can be adjusted according to the actual environment
        self.model_path = model_path or "qwen3:8b"
        self.validate_model_path()

    def validate_model_path(self):
        """Validate the model path/name"""
        # For Ollama, model names are strings like "qwen3:8b", not file paths
        # Only validate if it looks like a file path (contains /)
        if "/" in self.model_path and not self.model_path.startswith("http") and not os.path.exists(self.model_path):
            print(f"Warning: Model path {self.model_path} does not exist. Using default.")
            self.model_path = "qwen3:8b"

    def create_completion(self, client, temperature=0.1, top_p=0.9, max_tokens=1000, messages=None):
        """Unified LLM call method, using stored model configuration"""
        try:
            response = client.chat.completions.create(
                model=self.model_path,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens
            ).choices[0].message.content
            return response
        except Exception as e:
            print(f"LLM call failed with model {self.model_path}: {e}")
            print(f"Exception type: {type(e).__name__}")
            print(f"Exception details: {str(e)}")
            
            # Try with default model only once
            try:
                print(f"Attempting fallback with default model...")
                default_config = ModelConfig()
                response = client.chat.completions.create(
                    model=default_config.model_path,
                    messages=messages,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens
                ).choices[0].message.content
                return response
            except Exception as e2:
                print(f"LLM fallback also failed: {e2}")
                print(f"Exception type: {type(e2).__name__}")
                print(f"Exception details: {str(e2)}")
                # Return None instead of raising to allow graceful degradation
                return None

# Default debug model configuration
DEBUG_MODEL_CONFIG = ModelConfig(
    model_path="qwen3:8b"
)
