from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.router import api_router

from app.core.logger import logger  # Imports logger and boots up setup_centralized_logging()
from app.core.exception import register_exception_handlers
from app.core.lifespan import app_lifespan


app = FastAPI(
    title=settings.APP_NAME,
    description="Production-grade local RAG & clinical analytics engine.",
    version="1.0.0",
    lifespan=app_lifespan
)

# Register the global exception routers
register_exception_handlers(app)

# Set up open-source sandbox cross-origin accessibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Tighten down to app sandbox protocols in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Bind the global router network
app.include_router(api_router, prefix=settings.API_V1_STR)
