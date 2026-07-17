# services/chat/main.py
from typing import TypedDict, List, Dict, Any, Literal
import uuid
from app.core.logger import logger
from langgraph.graph import StateGraph, START, END
import json
from typing import AsyncGenerator

from app.services.chat.query_validate import clean_and_validate_query
from app.services.chat.intent import classify_query_intent
from app.services.chat.retriever import execute_retrieval_engine
from app.services.chat.generator import generation_engine


# LangGraph State definition
class RAGState(TypedDict):
    patient_id: str
    raw_query: str
    cleaned_query: str
    intent: Literal["structured", "semantic", "hybrid"]
    retrieved_docs: List[Dict[str, Any]]
    sources: List[Dict[str, Any]]
    response: str


async def validate_node(state: RAGState) -> Dict[str, Any]:
    """NODE 1: Validation ( Validates and sanitizes the user's input query. )"""
    logger.info("[Node 1/4] Validating and sanitizing input query")
    
    cleaned = clean_and_validate_query(state["raw_query"])
    return {"cleaned_query": cleaned}


async def classify_intent_node(state: RAGState) -> Dict[str, Any]:
    """NODE 2: Intent Classification ( Determines whether the query targets prescriptions, reports, both, or general knowledge. )"""
    logger.info(f"[Node 2/4] Classifying intent for query: '{state['cleaned_query']}'")
    
    intent = await classify_query_intent(state["cleaned_query"])
    
    logger.info(f"[Node 2/4 Completed] Identified Intent: '{intent.upper()}'")
    return {"intent": intent}


async def retrieve_node(state: RAGState) -> Dict[str, Any]:
    """
    NODE 3: Fetching Retriever ( Routes retrieval asynchronously to Qdrant, dynamically augmenting 
    with Postgres clinical metadata in a unified, non-duplicated list structure. )
    """
    logger.info(f"[Node 3/5] Starting retrieval stage. Intent: '{state['intent']}'")
    
    retrieval_results = await execute_retrieval_engine(
        patient_id=state["patient_id"],
        query=state["cleaned_query"],
        intent=state["intent"]
    )
    
    unique_sources = []
    seen_ids = set()
    
    for doc in retrieval_results.get("docs", []):
        postgres_id = doc.get("postgres_id")
        
        # 1. Skip if we have already captured this parent Postgres document
        if postgres_id and postgres_id in seen_ids:
            continue
            
        # 2. Determine unique ID: Use postgres_id, or fallback to a newly generated UUID
        source_id = postgres_id or str(uuid.uuid4())
        seen_ids.add(source_id)
        
        # 3. Format and append directly in the same pass
        unique_sources.append({
            "id": source_id,
            "docType": doc.get("doc_type", "Unknown"),
            "date": doc.get("date", "Unknown"),
            "doctor": doc.get("doctor") or "N/A"
        })

    return {
        "retrieved_docs": retrieval_results.get("docs", []),
        "sources": unique_sources
    }


async def generate_node(state: RAGState) -> Dict[str, Any]:
    """NODE 4: Generation ( Assembles prompt and gets answer from LLM model. )"""
    patient_id = state.get("patient_id", "")
    masked_patient_id = (
        f"{patient_id[:2]}***{patient_id[-2:]}" if isinstance(patient_id, str) and len(patient_id) > 4 else "***"
    )
    logger.info(f"[Node 4/4] Generating response for Patient ID: '{masked_patient_id}'")
    
    # Execute generation passing the clean query text and contextualized retrieval arrays
    generated_text = await generation_engine.generate_response(
        cleaned_query=state["cleaned_query"],
        retrieved_docs=state["retrieved_docs"]
    )
    return {"response": generated_text}


# --- Build State Graph ---
# Flow:     validate → Clean & Format → Intent Classification → Relevant Context Retrieval → LLM Generation...
workflow = StateGraph(RAGState)

# Add processing pipeline nodes
workflow.add_node("validate", validate_node)
workflow.add_node("classify", classify_intent_node)
workflow.add_node("retrieve", retrieve_node)
workflow.add_node("generate", generate_node)

# Set execution flow edges
workflow.add_edge(START, "validate")
workflow.add_edge("validate", "classify")
workflow.add_edge("classify", "retrieve")
workflow.add_edge("retrieve", "generate")
workflow.add_edge("generate", END)

# Compile LangGraph app
rag_pipeline = workflow.compile()


async def run_rag_pipeline(patient_id: str, raw_query: str) -> Dict[str, Any]:
    """Executes the compiled LangGraph pipeline workflow."""
    initial_state = {
        "patient_id": patient_id,
        
        "raw_query": raw_query,
        "cleaned_query": "",
        
        "intent": "hybrid",
        
        "retrieved_docs": [],
        
        "sources": [],
        "response": ""
    }
    # Invoke pipeline graph asynchronously
    final_state = await rag_pipeline.ainvoke(initial_state)
    return final_state


# =====================================================================
# REAL-TIME SSE EVENTS STREAM GENERATOR
# =====================================================================
async def stream_rag_pipeline(patient_id: str, raw_query: str) -> AsyncGenerator[str, None]:
    """
    Executes the graph using LangGraph event streaming, tracking lifecycle node states 
    and passing tokens out directly from the inner generation module.
    """
    initial_state = {
        "patient_id": patient_id, "raw_query": raw_query, "cleaned_query": "",
        "intent": "hybrid", "retrieved_docs": [], "sources": [], "response": ""
    }

    # Map node system execution paths to simplified frontend status texts
    status_mappings = {
        "validate": "Validating and cleaning clinical query...",
        "classify": "Analyzing clinical domain and query intent...",
        "retrieve": "Retrieving context records from vector space and databases...",
        "generate": "Synthesizing clinical response guidelines..."
    }
    current_state_snapshot = initial_state
    
    # Track accumulated response content to pass sanitization parameters at termination
    accumulated_response = ""

    try:
        # Use astream_events API version 2 to catch granular lifecycle hooks
        async for event in rag_pipeline.astream_events(initial_state, version="v2"):
            event_type = event.get("event")
            name = event.get("name")

            # 1. Capture LangGraph node starts to broadcast step transitions
            if event_type == "on_chain_start" and name in status_mappings:
                yield json.dumps({
                    "event": "status",
                    "status": status_mappings[name]
                })

            # 2. Capture final state changes at the termination of specific functional nodes
            elif event_type == "on_chain_end" and name in status_mappings:
                output_data = event.get("data", {}).get("output", {})
                if isinstance(output_data, dict):
                    current_state_snapshot.update(output_data)

            # 3. Intercept the custom stream token event loop inside the generation stage
            if name == "generate":
                # We skip running internal batch invoke; intercept generate_node and stream instead
                pass
        
        # Once context retrieval completes, stream tokens directly using our engine method
        yield json.dumps({"event": "status", "status": "Generating final response tokens..."})
        
        async for token in generation_engine.stream_response(
            cleaned_query=current_state_snapshot["cleaned_query"],
            retrieved_docs=current_state_snapshot["retrieved_docs"]
        ):
            accumulated_response += token
            yield json.dumps({
                "event": "token",
                "token": token
            })

        # Finalize and sanitize structural output formatting arrays
        cleaned_final_answer = generation_engine._clean_llm_markdown(accumulated_response)
        
        yield json.dumps({
            "event": "final",
            "token": "",
            "data": {
                "answer": cleaned_final_answer,
                "sources": current_state_snapshot.get("sources", [])
            }
        })

    except Exception as err:
        logger.error(f"[SSE Engine Error] Stream broken on runtime invocation: {err}", exc_info=True)
        yield json.dumps({
            "event": "error",
            "status": f"Pipeline execution aborted: {str(err)}"
        })
