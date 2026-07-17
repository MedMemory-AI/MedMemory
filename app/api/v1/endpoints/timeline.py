from fastapi import APIRouter, Depends, Query, HTTPException, status, Path
from app.schemas.timeline import TimelineSuccessResponse
from app.services.timeline.main import get_patient_timeline
from app.api.deps import get_current_patient_id
from app.core.exception import DatabaseError
import uuid

router = APIRouter(prefix="/timeline", tags=["Timeline"])


@router.get("/", response_model=TimelineSuccessResponse, status_code=status.HTTP_200_OK)
async def fetch_patient_timeline(
    ascending: bool = Query(False, description="Flag to sort timeline ascending (Chrono-forward) or descending (Newest first)"),
    patient_id: str = Depends(get_current_patient_id)
) -> TimelineSuccessResponse:
    """
    Retrieves a unified historical stream of prescriptions and diagnostic reports 
    for a patient, sorted chronologically to build a visual lifelong health timeline.
    """
    # 1. Route validation block
    try:
        uuid.UUID(patient_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Value '{patient_id}' is not a valid UUID format."
        )

    # 2. Execute business query logic
    try:
        raw_documents = await get_patient_timeline(patient_id=patient_id, ascending=ascending)
        
        # 3. Structural response generation
        return TimelineSuccessResponse(
            patient_id=patient_id,
            count=len(raw_documents),
            timeline=raw_documents  # Pydantic populates aliases dynamically using 'from_attributes'
        )
        
    except DatabaseError as db_err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(db_err)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during timeline retrieval: {str(exc)}"
        )
