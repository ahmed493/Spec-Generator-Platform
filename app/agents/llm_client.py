"""
LLM Client - Supports Ollama, OpenAI, and Anthropic
Easy to switch between providers
"""


from typing import Optional
from app.config.settings import settings
from app.agents.base_llm_client import BaseLLMClient
from app.agents.huggingface_client import HuggingFaceClient




class OllamaClient(BaseLLMClient):
    """Ollama client for local LLM"""
    def __init__(self, model: str = None, base_url: str = None):
        import ollama
        self.model = model or settings.ollama_model
        self.base_url = base_url or settings.ollama_base_url
        self.client = ollama.Client(host=self.base_url)

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        response = self.client.chat(
            model=self.model,
            messages=messages
        )
        return response["message"]["content"]


class OpenAIClient(BaseLLMClient):
    """OpenAI client"""
    
    def __init__(self, model: str = None, api_key: str = None):
        from openai import OpenAI
        self.model = model or settings.openai_model
        self.client = OpenAI(api_key=api_key or settings.openai_api_key)
    
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )
        return response.choices[0].message.content


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude client"""
    
    def __init__(self, model: str = None, api_key: str = None):
        import anthropic
        self.model = model or settings.anthropic_model
        self.client = anthropic.Anthropic(api_key=api_key or settings.anthropic_api_key)
    
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt or "You are a helpful assistant.",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text


def get_llm_client() -> BaseLLMClient:
    """Factory function to get the appropriate LLM client based on settings"""
    provider = settings.llm_provider
    if provider == "ollama":
        return OllamaClient()
    elif provider == "openai":
        return OpenAIClient()
    elif provider == "anthropic":
        return AnthropicClient()
    elif provider == "huggingface":
        return HuggingFaceClient()
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
