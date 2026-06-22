from abc import ABC, abstractmethod
from typing import Any, Optional

class BaseLLMClient(ABC):
    """Abstract base class for LLM clients"""
    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs: Any) -> str:
        pass
