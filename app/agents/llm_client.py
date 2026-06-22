"""
LLM Client - OpenAI
"""

from typing import Optional
from openai import OpenAI
from app.config.settings import settings
from app.agents.base_llm_client import BaseLLMClient


class OpenAIClient(BaseLLMClient):
    """OpenAI client"""

    def __init__(self, model: str = None, api_key: str = None):
        self.model = model or settings.openai_model
        self.client = OpenAI(api_key=api_key or settings.openai_api_key)

    def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs
        )
        return response.choices[0].message.content


def get_llm_client() -> BaseLLMClient:
    """Returns the configured LLM client."""
    return OpenAIClient()
