from __future__ import annotations
import uuid
import httpx
from typing import Any, Dict
from qdrant_client.http.models import PointStruct

from app.core.db import get_qdrant_client
from app.core.qdrant import qdrant_settings
from app.core.config import settings
from app.core.logger import logger
from app.core.exception import DatabaseError


async def generate_ollama_embeddings(text: str) -> list[float]:
    """
    Communicates with Ollama's server to generate dense vector representation
    of clinical summaries via mxbai-embed-large.
    """
    url = f"{settings.OLLAMA_BASE_URL.strip().rstrip('/')}/api/embeddings"
    payload = {
        "model": qdrant_settings.OLLAMA_EMBED_MODEL,
        "prompt": text
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["embedding"]
        except Exception as err:
            logger.error(f"[Embeddings Engine] Failed fetching vectors from local model host: {err}")
            raise DatabaseError(f"Embedding generation service failure: {str(err)}")


async def save_extracted_data_to_qdrant(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 7 Extraction Pipeline Task.
    Extracts the clinical 'summary' string, requests embeddings from Ollama,
    and commits vector and metadata attributes cleanly to the Qdrant DB.
    """
    patient_id = state.get("patient_id")
    doc_type = state.get("doc_type")
    db_record_id = state.get("db_record_id")
    clinical_metadata = state.get("clinical_metadata") or {}

    # 1. Pipeline Validation Check
    summary_text = clinical_metadata.get("summary", "").strip()
    if not summary_text:
        logger.warning("[Step 7/8 Aborted] Skipping vector search indexing: No 'summary' attribute present.")
        return state
    
    # 2. Dynamically resolve the client instance at runtime
    try:
        client = get_qdrant_client()
    except RuntimeError as r_err:
        raise DatabaseError(str(r_err))

    logger.info(f"[Step 7/8 Started] Target indexing: Patient '[REDACTED]' - DocType '{doc_type}'")

    # 3. Extract structured search filter variables
    raw_date = clinical_metadata.get("date") or "1970-01-01"
    doctor_name = clinical_metadata.get("doctor") or "Unknown Clinician"

    # 4. Retrieve dense embedding arrays
    dense_vector = await generate_ollama_embeddings(summary_text)

    # 5. Model Payload Structures
    point_payload = {
        "patient_id": patient_id,
        "doc_type": doc_type,
        "date": raw_date,
        "doctor": doctor_name,
        "postgres_id": db_record_id,
        "page_content": summary_text        # Stored as EMBEDDING for Semantic Search...
    }

    try:
        # Create unique Point ID
        point_id = str(uuid.uuid4())
        
        # Commit vector point directly to Qdrant cluster
        await client.upsert(
            collection_name=qdrant_settings.COLLECTION_NAME,
            wait=True,
            points=[
                PointStruct(
                    id=point_id,
                    vector=dense_vector,    # Vector Embeddings...
                    payload=point_payload   # metadata...
                )
            ]
        )
        
        state["qdrant_point_id"] = point_id
        logger.info(f"[Step 7/8 Completed] Vector stored successfully inside Qdrant point '{point_id}'.")
        
    except Exception as exc:
        logger.error(f"[Qdrant Write Error] Failed writing embeddings point into storage layout: {exc}", exc_info=True)
        raise DatabaseError(f"Vector engine execution failure: {str(exc)}")

    return state
