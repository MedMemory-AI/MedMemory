from pydantic_settings import BaseSettings, SettingsConfigDict # type: ignore

class Settings(BaseSettings):
    """
    Application Settings Configuration.
    Uses Pydantic BaseSettings to automatically load configuration values from environment 
    variables or an absolute .env file, providing safe runtime validation.
    """
    APP_NAME: str = "MedMemory AI Engine"
    API_V1_STR: str = "/api/v1"
    
    DATABASE_URL: str = "postgresql://postgres:local_secret@localhost:5432/medmemory"
    
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

settings = Settings()
