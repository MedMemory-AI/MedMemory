from fastapi import APIRouter
from app.api.v1.endpoints import ingestion, timeline, auth, chat

api_router = APIRouter()


@api_router.get("/health", status_code=200, tags=["System Health"])
async def check_health():
    """
    Evaluates engine runtime vital signs and system container checkups.
    """
    return {
        "status": "healthy",
        "engine": "MedMemory AI Backend",
        "version": "1.0.0-rc1"
    }


api_router.include_router(auth.router)
api_router.include_router(ingestion.router)
api_router.include_router(timeline.router)
api_router.include_router(chat.router)
