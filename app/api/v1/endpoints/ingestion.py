from datetime import datetime, timezone
from enum import Enum
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Header, status
from app.api.deps import get_current_patient_id
from app.schemas.ingestion import IngestionSuccessResponse, UploadResponse
from app.services.ingestion.main import execute_ingestion_pipeline

# Initialize specialized ingestion router paths
router = APIRouter(prefix="/ingestion", tags=["Ingestion"])

class DocType(str, Enum):
    PRESCRIPTION = "prescription"
    REPORT = "report"


@router.post("/upload", response_model=IngestionSuccessResponse, status_code=status.HTTP_201_CREATED)
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
        initial_state = {
            "file": file,
            "patient_id": patient_id,
            "doc_type": x_doc_type.value
        }
        
        # Invoke the LangChain pipeline asynchronously
        output_state = await execute_ingestion_pipeline(initial_state)
        
        # Return the processed metadata back to the client (includes Step-4 NER/EL mesh)
        metadata = UploadResponse(
            filename=output_state["safe_filename"],
            mimeType=output_state["mime_type"],
            size=output_state["file_size"],
            filePath=output_state["file_path"],
            raw_text=output_state["raw_text"],
            cleaned_text=output_state["cleaned_text"],
            ner=output_state.get("ner"),
            extraction=output_state.get("clinical_metadata"),
            createdAt=datetime.now(timezone.utc)
        )
        
        return IngestionSuccessResponse(
            message="Document pipeline completed. PostgreSQL and Qdrant records successfully updated.",
            data=metadata
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
