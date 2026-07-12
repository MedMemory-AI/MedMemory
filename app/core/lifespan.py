from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.db import connect_db, disconnect_db
from app.core.logger import logger
# Assuming you will instantiate a shared qdrant client later
# from app.core.qdrant import init_qdrant, close_qdrant 


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """
    Centralized Lifespan Manager: Safely orchestrates startup and shutdown 
    sequences for all storage connections and third-party models.
    """
    # --- STARTUP SEQUENCE ---
    logger.info("⚡ Initializing MedMemory AI Storage Engines...")
    await connect_db()      # Connects to your PostgreSQL Docker container
    # await init_qdrant()   # Connects to your Qdrant Docker container
    logger.info("🚀 All core infrastructure layers are ready to route traffic.")
    
    yield
    
    # --- SHUTDOWN SEQUENCE ---
    logger.info("🛑 Terminating MedMemory AI Storage Engines...")
    await disconnect_db()   # Closes PostgreSQL connection pooling
    # await close_qdrant()  # Closes Qdrant network sockets
    logger.info("✨ Clean shutdown complete. Goodbye!")
