# app/core/config.py
import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application Settings Configuration.
    Automatically maps validated environment configurations from a local .env file.
    """
    APP_NAME: str = "MedMemory AI Engine"
    API_V1_STR: str = "/api/v1"

    ENV: str = "development"
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/medmemory"
    
    MEDMEMORY_QDRANT_HOST: str = "localhost"
    MEDMEMORY_QDRANT_PORT: str = "6333"
    MEDMEMORY_QDRANT_API_KEY: str = ""
    OLLAMA_EMBED_MODEL: str = "mxbai-embed-large:latest"

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    MEDMEMORY_OLLAMA_MODEL: str = "qwen3:4b"
    MEDMEMORY_LLM_TIMEOUT: float = 60.0
    
    JWT_SECRET_KEY: str = os.getenv("MEDMEMORY_JWT_SECRET", "super_secret_system_level_crypto_key_change_me_in_prod")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440   # 24hrs expiry...

    # Configures strict casing match and ignores extra internal system environment tokens
    model_config = SettingsConfigDict(
        env_file=".env", 
        case_sensitive=True,
        extra="ignore"  # Prevents extra_forbidden crashes for missing declarations
    )

settings = Settings()
