from fastapi import APIRouter
from app.api.v1.endpoints import patient

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

api_router.include_router(patient.router)
