from datetime import datetime, timezone
from enum import Enum
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Header, status
from app.api.deps import get_current_patient_id
from app.schemas.ingestion import IngestionSuccessResponse, ProcessingResponse, UploadResponse
from app.services.ingestion.background import start_background_processing
from app.services.ingestion.main import execute_ingestion_pipeline
from app.services.ingestion.validate_store import validate_and_save_file

# Initialize specialized ingestion router paths
router = APIRouter(prefix="/ingestion", tags=["Ingestion"])

class DocType(str, Enum):
    PRESCRIPTION = "prescription"
    REPORT = "report"


@router.post("/upload", response_model=IngestionSuccessResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_file(
    file: UploadFile = File(...),
    x_doc_type: DocType = Header(..., description="The type of clinical record being ingested (prescription/report)"),
    patient_id: str = Depends(get_current_patient_id)
    ) -> IngestionSuccessResponse:
    """
    Triggers the LangChain-managed multi-tier pipeline to ingest raw medical documents.
    """
    try:
        # Prepare the initial state dictionary
        file_path, file_size, safe_filename = (
            await validate_and_save_file(
                file,
                patient_id,
            )
        )
        initial_state = {
            "file": file,
            "patient_id": patient_id,
            "doc_type": x_doc_type.value,
            "file_path": file_path,
            "file_size": file_size,
            "safe_filename": safe_filename,
            "mime_type": file.content_type,
        }
        
        # Invoke the LangChain pipeline asynchronously
        start_background_processing(initial_state)
        
        return IngestionSuccessResponse(
            message="Document uploaded successfully. Processing has started.",
            data=ProcessingResponse(
                status="processing",
                estimatedTime="1-2 minutes",
            ),
        )
        
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Validation Error: {str(val_err)}"
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion Pipeline Failed: {str(exc)}"
        )
    # finally:
    #     run_file_cleanup(UPLOAD_DIR)
