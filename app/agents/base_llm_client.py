from abc import ABC, abstractmethod
from typing import Optional

class BaseLLMClient(ABC):
    """Abstract base class for LLM clients"""
    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        pass
