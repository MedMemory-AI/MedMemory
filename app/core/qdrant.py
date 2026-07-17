import os

class QdrantSettings:
    """Configuration class for resolving containerized Qdrant instance endpoints."""
    HOST: str = os.getenv("MEDMEMORY_QDRANT_HOST", "localhost").strip()
    PORT: int = int(os.getenv("MEDMEMORY_QDRANT_PORT", "6333"))
    API_KEY: str | None = os.getenv("MEDMEMORY_QDRANT_API_KEY", None)
    
    # Collection tracking parameters
    COLLECTION_NAME: str = "clinical_documents"
    EMBEDDING_DIMENSION: int = 1024  # mxbai-embed-large:latest output shape
    
    # Ollama embedding reference
    OLLAMA_EMBED_MODEL: str = "mxbai-embed-large:latest"

qdrant_settings = QdrantSettings()
