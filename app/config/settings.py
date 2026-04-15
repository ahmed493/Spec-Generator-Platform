"""
Configuration settings for Spec Generator Platform
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # GitHub
    github_token: str = ""

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Database
    database_url: str = "sqlite:///./spec_generator.db"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
