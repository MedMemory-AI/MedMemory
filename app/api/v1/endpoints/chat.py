# api/v1/endpoints/chat.py
from fastapi import APIRouter, Depends, HTTPException, status
from sse_starlette.sse import EventSourceResponse
from app.api.deps import get_current_patient_id
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat.main import run_rag_pipeline, stream_rag_pipeline
from app.core.logger import logger

router = APIRouter(prefix="/chat", tags=["AI Copilot"])


# ---------------------------------------------------------------------
# STANDARD BATCH RUN API (HTTP POST)  { /api/v1/chat }
# ---------------------------------------------------------------------
@router.post("/", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def query_copilot(
    payload: ChatRequest,
    patient_id: str = Depends(get_current_patient_id)
) -> ChatResponse:
    """
    Executes the conversational LangGraph RAG pipeline over the authenticated patient's 
    clinical records (Prescriptions and Reports) stored in PostgreSQL & Qdrant.
    """
    try:
        # Run orchestrated state graph
        result = await run_rag_pipeline(patient_id=patient_id, raw_query=payload.query)
        
        return ChatResponse(
            answer=result["response"],
            sources=result.get("sources", []),
        )
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except Exception as exc:
        logger.error(f"[Chat Endpoint Error] Graph execution crashed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred compiling your clinical query response."
        )


# ---------------------------------------------------------------------
# REAL-TIME SSE STREAMING RUN API (EVENT SOURCE STREAM)
# ---------------------------------------------------------------------
@router.post("/stream", status_code=status.HTTP_200_OK)
async def query_copilot_stream(
    payload: ChatRequest,
    patient_id: str = Depends(get_current_patient_id)
) -> EventSourceResponse:
    """
    Streams the conversational pipeline lifecycle phases and live LLM tokens 
    back to the client UI layer via Server-Sent Events (SSE).
    """
    logger.info(f"[SSE Chat Request] Initiating real-time pipeline connection for patient: {patient_id}")
    
    # Generate the streaming generator iterator loop
    event_generator = stream_rag_pipeline(patient_id=patient_id, raw_query=payload.query)
    
    # Return EventSourceResponse configured for UI consumption
    return EventSourceResponse(event_generator)
