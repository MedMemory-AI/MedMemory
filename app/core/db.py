from prisma import Prisma
from qdrant_client import AsyncQdrantClient
from app.core.qdrant import qdrant_settings
from app.core.logger import logger


# Instantiate the globally shared database clients
db = Prisma(auto_register=True)
qdrant_client: AsyncQdrantClient | None = None


async def connect_db():
    """
    Evaluates connection states. If inactive, establishes connections 
    to both PostgreSQL and Qdrant.
    """
    global qdrant_client
    
    # 1. PostgreSQL/Prisma Pool Initialization
    if not db.is_connected():
        await db.connect()
        logger.info("[Lifecycle] Connected to PostgreSQL via Prisma Client.")

    # 2. Qdrant Connection Pool Initialization
    if qdrant_client is None:
        qdrant_client = AsyncQdrantClient(
            host=qdrant_settings.HOST,
            port=qdrant_settings.PORT,
            api_key=qdrant_settings.API_KEY,
            timeout=10.0,
            check_compatibility=False
        )
        logger.info(f"[Lifecycle] AsyncQdrantClient connected successfully to {qdrant_settings.HOST}:{qdrant_settings.PORT}")
        
        # Self-healing index orchestration check
        await init_qdrant_collections()


async def disconnect_db():
    """Tears down all shared container socket links gracefully on process kill."""
    global qdrant_client
    if db.is_connected():
        await db.disconnect()
        logger.info("[Lifecycle] PostgreSQL disconnected cleanly.")
        
    if qdrant_client is not None:
        await qdrant_client.close()
        qdrant_client = None
        logger.info("[Lifecycle] Qdrant Async Connection Pool closed cleanly.")


async def init_qdrant_collections():
    """Creates collection if missing, setting up Cosine metric indexes."""
    from qdrant_client.http.models import Distance, VectorParams
    global qdrant_client
    
    try:
        exists = await qdrant_client.collection_exists(qdrant_settings.COLLECTION_NAME)
        if not exists:
            logger.info(f"[Qdrant Init] Creating collection '{qdrant_settings.COLLECTION_NAME}'...")
            await qdrant_client.create_collection(
                collection_name=qdrant_settings.COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=qdrant_settings.EMBEDDING_DIMENSION,
                    distance=Distance.COSINE
                )
            )
            logger.info(f"[Qdrant Init] Collection '{qdrant_settings.COLLECTION_NAME}' initialized successfully.")
    except Exception as e:
        logger.error(f"[Qdrant Init] Critical error orchestrating vector collections: {e}")


def get_qdrant_client() -> AsyncQdrantClient:
    """Returns the globally active and initialized Qdrant client."""
    global qdrant_client
    if qdrant_client is None:
        raise RuntimeError("Qdrant database client context uninitialized. Call connect_db() first.")
    return qdrant_client
