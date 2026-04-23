"""
Configuration settings for Spec Generator Platform
"""
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    # LLM Provider Selection
    llm_provider: str = "openai"  # Options: "openai", "anthropic", "ollama"
    
    # GitHub
    github_token: str = ""

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-sonnet-20240229"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "mistral"

    # Database
    database_url: str = "sqlite:///./spec_generator.db"

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # Ignore extra fields from .env
    )


settings = Settings()
