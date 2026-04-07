"""
Configuration settings for Spec Generator Platform
Supports: Ollama (local), OpenAI, Anthropic
"""
import os
from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    # GitHub
    github_token: str = ""

    # LLM Provider
    llm_provider: Literal["ollama", "openai", "anthropic", "huggingface"] = "ollama"

    # Ollama (local)
    ollama_model: str = "llama3.1"
    ollama_base_url: str = "http://localhost:11434"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-opus-20240229"

    # Hugging Face
    huggingface_api_key: str = ""
    huggingface_model: str = "HuggingFaceH4/zephyr-7b-beta"

    # Database
    database_url: str = "sqlite:///./spec_generator.db"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
