"""
LLM client for Ollama integration.
"""
import json
import time
from typing import Dict, Any, Optional
import requests
from loguru import logger

from config import QAIRSConfig


class OllamaClient:
    """
    Client for interacting with Ollama API.
    """
    
    def __init__(self, config: QAIRSConfig):
        self.config = config
        self.base_url = config.ollama.host
        self.model = config.ollama.model
        self.temperature = config.ollama.temperature
        self.max_tokens = config.ollama.max_tokens
        self.timeout = config.ollama.timeout
        
        # Verify connection
        self._check_connection()
    
    def _check_connection(self) -> None:
        """Verify Ollama is running and model is available."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            
            models = response.json().get('models', [])
            model_names = [m['name'] for m in models]
            
            if self.model not in model_names:
                logger.warning(f"Model {self.model} not found. Available: {model_names}")
            else:
                logger.info(f"Connected to Ollama. Using model: {self.model}")
        
        except Exception as e:
            logger.error(f"Failed to connect to Ollama: {e}")
            raise
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        json_mode: bool = False
    ) -> str:
        """
        Generate text completion.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            max_tokens: Override default max tokens
            temperature: Override default temperature
            json_mode: Enable JSON response format
        
        Returns:
            Generated text
        """
        url = f"{self.base_url}/api/generate"
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature or self.temperature,
                "num_predict": max_tokens or self.max_tokens,
            }
        }
        
        if system_prompt:
            payload["system"] = system_prompt
        
        if json_mode:
            payload["format"] = "json"
        
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            result = response.json()
            return result.get('response', '').strip()
        
        except requests.exceptions.Timeout:
            logger.error("Ollama request timed out")
            raise
        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            raise
    
    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Generate JSON response with retry logic.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            max_retries: Number of retries on parse failure
        
        Returns:
            Parsed JSON object
        """
        for attempt in range(max_retries):
            try:
                response = self.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    json_mode=True
                )
                
                # Try to parse JSON
                return json.loads(response)
            
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse failed (attempt {attempt + 1}/{max_retries}): {e}")
                
                if attempt < max_retries - 1:
                    time.sleep(self.config.extraction.retry_delay)
                    continue
                else:
                    # Last attempt - try to extract JSON from response
                    return self._extract_json_fallback(response)
        
        raise ValueError("Failed to generate valid JSON after all retries")
    
    def _extract_json_fallback(self, text: str) -> Dict[str, Any]:
        """
        Attempt to extract JSON from malformed response.
        """
        # Try to find JSON block in markdown
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()
        
        # Try to find JSON object
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except:
                pass
        
        # Give up and return empty
        logger.error(f"Could not extract JSON from: {text[:200]}")
        return {"data": [], "has_more": False}
    
    def batch_generate(
        self,
        prompts: list[str],
        system_prompt: Optional[str] = None
    ) -> list[str]:
        """
        Generate completions for multiple prompts.
        
        Note: This is sequential. For true parallel processing,
        use async or threading.
        """
        results = []
        for prompt in prompts:
            result = self.generate(prompt, system_prompt)
            results.append(result)
        return results
