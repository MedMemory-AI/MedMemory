# services/chat/retriever.py
from typing import List, Dict, Any, Literal
import httpx
from app.core.db import db, get_qdrant_client
from app.core.config import settings
from app.core.qdrant import qdrant_settings
from app.core.logger import logger

# Global client with connection pooling for Ollama Embeddings API
limits = httpx.Limits(max_keepalive_connections=10, max_connections=50)
embedding_client = httpx.AsyncClient(limits=limits, timeout=10.0)


async def retrieve_qdrant_docs(patient_id: str, query_vector: List[float], limit: int = 10) -> List[Dict[str, Any]]:
    """
    Performs vector similarity search on Qdrant, filtered strictly by patient_id.
    Returns up to top-10 chunks, sorted descending by similarity score.
    """
    try:
        qdrant_client = get_qdrant_client()
        
        response = await qdrant_client.query_points(
            collection_name=qdrant_settings.COLLECTION_NAME,
            query=query_vector, 
            query_filter={
                "must": [
                    {"key": "patient_id", "match": {"value": patient_id}}
                ]
            },
            limit=limit
        )

        # Extract the matched points from the response
        search_result = response.points

        retrieved_chunks = []
        for hit in search_result:
            payload = hit.payload or {}
            retrieved_chunks.append({
                "score": round(hit.score, 4),
                "postgres_id": payload.get("postgres_id"),
                "doc_type": payload.get("doc_type"),
                "date": str(payload.get("date")),
                "doctor": payload.get("doctor"),
                "content": payload.get("page_content", "")
            })
            
        return retrieved_chunks

    except Exception as exc:
        logger.error(f"[Qdrant Retriever] Failed to execute vector search: {exc}", exc_info=True)
        return []


async def retrieve_postgres_docs(doc_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Fetches structured clinical documents from Postgres using Prisma.
    Returns a dictionary mapped by document ID for efficient O(1) lookup during merging.
    """
    if not doc_ids:
        return {}
        
    try:
        records = await db.document.find_many(
            where={
                "id": {
                    "in": doc_ids
                }
            }
        )
        
        structured_map = {}
        for record in records:
            rec_dict = record.dict() if hasattr(record, "dict") else record.__dict__
            doc_id = str(rec_dict.get("id"))

            # FIX: Swapped bitwise OR `|` with logical fallback `or` to prevent TypeErrors
            structured_data = {
                "findings": rec_dict.get("findings"),
                "diseases": rec_dict.get("diseases", []),
                "highlights": rec_dict.get("highlights") or "",
                "treatment": rec_dict.get("treatment") or "",
                "pre_diagnosis": rec_dict.get("preDiagnosis") or ""
            }
            structured_map[doc_id] = structured_data

        return structured_map

    except Exception as exc:
        logger.error(f"[Postgres Retriever] Failed to execute Prisma batch fetch: {exc}", exc_info=True)
        return {}


async def get_query_embedding(text: str) -> List[float]:
    """
    Generates high-performance embeddings locally using the Ollama Embeddings API.
    """
    url = f"{settings.OLLAMA_BASE_URL.strip().rstrip('/')}/api/embeddings"
    payload = {
        "model": getattr(settings, "OLLAMA_EMBED_MODEL", "mxbai-embed-large:latest"),
        "prompt": text
    }
    
    try:
        response = await embedding_client.post(url, json=payload)
        response.raise_for_status()
        return response.json().get("embedding", [])
    except Exception as exc:
        logger.error(f"[Embeddings Service] Local generation failed: {exc}")
        raise RuntimeError("Failed to generate vector representation of user query.")


async def execute_retrieval_engine(
    patient_id: str, 
    query: str, 
    intent: Literal["structured", "semantic", "hybrid"]
) -> Dict[str, Any]:
    """
    Orchestrates the hybrid semantic-to-structured retrieval flow.
    Enriches semantic vector chunks with structured database data to prevent payload duplication.
    """
    # Step 1: Vectorize query
    logger.info(f"[Retrieval Engine] Embedding query: '{query}'")
    query_vector = await get_query_embedding(query)
    
    # Step 2: Extract top relevant chunks from Qdrant first (Max 10)
    logger.info(f"[Retrieval Engine] Fetching Qdrant matches for Patient: {patient_id}")
    semantic_chunks = await retrieve_qdrant_docs(patient_id, query_vector, limit=10)
    
    if not semantic_chunks:
        return {"docs": []}

    # Step 3: Conditional structured database retrieval & merging
    if intent in ("hybrid", "structured"):
        logger.info(f"[Retrieval Engine] Intent is '{intent.upper()}'. Activating Postgres fetch...")
        
        # Gather unique parent database keys while preserving score rank order
        postgres_ids = list({
            chunk["postgres_id"] 
            for chunk in semantic_chunks 
            if chunk.get("postgres_id")
        })
        
        # Batch query Postgres for structured details (Returns mapped dictionary)
        structured_map = await retrieve_postgres_docs(postgres_ids)
        
        # Merge structured fields directly into the matching semantic chunks to avoid duplication
        enriched_docs = []
        for chunk in semantic_chunks:
            p_id = chunk.get("postgres_id")
            
            # Form baseline doc structure
            doc_item = {
                "score": chunk["score"],
                "doc_type": chunk["doc_type"],
                "date": chunk["date"],
                "doctor": chunk["doctor"],
                "content": chunk["content"]
            }
            
            # Inject corresponding non-duplicated database attributes if available
            if p_id and p_id in structured_map:
                doc_item["structured_details"] = structured_map[p_id]
                
            enriched_docs.append(doc_item)
            
        return {"docs": enriched_docs}
    
    # Step 4: Pure Semantic fallback (without database details)
    logger.info("[Retrieval Engine] Intent is 'SEMANTIC'. Returning Qdrant results directly.")
    return {"docs": semantic_chunks}
