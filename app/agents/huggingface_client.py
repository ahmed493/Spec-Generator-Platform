# Hugging Face inference client
import requests
from typing import Optional
from app.config.settings import settings
from app.agents.base_llm_client import BaseLLMClient

class HuggingFaceClient(BaseLLMClient):
    """Hugging Face Inference API client"""
    def __init__(self, model: str = None, api_key: str = None):
        self.model = model or settings.huggingface_model
        self.api_key = api_key or settings.huggingface_api_key
        self.api_url = f"https://api-inference.huggingface.co/models/{self.model}"

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "inputs": prompt,
            "parameters": {"max_new_tokens": 1024},
            "options": {"wait_for_model": True}
        }
        if system_prompt:
            # Some models support system prompt via "parameters" or prompt engineering
            payload["inputs"] = f"<|system|> {system_prompt}\n<|user|> {prompt}"
        response = requests.post(self.api_url, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        # Hugging Face returns a list of generated texts
        if isinstance(result, list) and "generated_text" in result[0]:
            return result[0]["generated_text"]
        elif "error" in result:
            raise RuntimeError(f"Hugging Face API error: {result['error']}")
        else:
            return str(result)
