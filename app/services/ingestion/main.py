# services/ingestion/main.py
import os
from pathlib import Path
from typing import Dict, Any
from fastapi import UploadFile
from langchain_core.runnables import RunnableLambda

from app.core.logger import logger
from app.services.ingestion.validate_store import validate_and_save_file, BASE_DIR
from app.services.ingestion.ocr import process_document_ocr
from app.services.ingestion.normalizer import process_text_normalization
from app.services.ingestion.ner import extract_clinical_entities
from app.services.ingestion.extraction import extract_structured_clinical_data
from app.services.ingestion.store_sql import save_extracted_data_to_postgres
from app.services.ingestion.store_qdrant import save_extracted_data_to_qdrant



# --- LANGCHAIN RUNNABLE STEPS ---
async def run_validation_and_storage(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    1. Step: Validates the metadata constraints and flushes the buffer 
    to an isolated disk directory asynchronously without thread loop blockers.
    """
    file: UploadFile = inputs["file"]
    patient_id: str = inputs["patient_id"]
    redacted_patient_id = f"***{patient_id[-4:]}" if patient_id and len(patient_id) > 4 else "***"
    
    logger.info(
        f"Step 1/8: Validating and saving document '{file.filename}'"
    )
    
    # CLEAN REFACTOR: Cleanly await the asynchronous storage engine instead of calling asyncio.run()
    file_path, file_size, safe_filename = await validate_and_save_file(file, patient_id)
    
    inputs.update({
        "file_path": file_path,
        "file_size": file_size,
        "safe_filename": safe_filename,
        "mime_type": file.content_type
    })
    return inputs


async def run_ocr_parser(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """2. Step: Extract and clean raw document/image text."""
    file_path_relative = Path(inputs["file_path"])
    mime_type = inputs["mime_type"]
    file_path = BASE_DIR / file_path_relative
    
    logger.info(f"Step 2/8: Extracting and cleaning raw text from {file_path.name}")
    
    raw_cleaned_text = await process_document_ocr(file_path, mime_type)
    
    inputs.update({
        "raw_text": raw_cleaned_text
    })
    return inputs


async def run_text_normalizer(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """3. Step: Algorithmic typo correction and unit normalization."""
    raw_text = inputs.get("raw_text", "")
    logger.info("Step 3/8: Normalizing text strings and fixing structural typos algorithmic-side...")
    
    normalized_text = await process_text_normalization(raw_text)
    
    inputs["cleaned_text"] = normalized_text
    return inputs


async def run_clinical_ner(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    4. Step: Clinical sentence segmentation + medical NER / Entity Linking.
    """
    cleaned_text = inputs.get("cleaned_text", "")
    logger.info(
        "Step 4/8: Segmenting clinical sentences and linking medical entities (sciSpacy CPU)..."
    )

    ner_result = await extract_clinical_entities(cleaned_text)
    # Persist both the pydantic model (API serialization) and a dict for LCEL state.
    inputs["ner"] = ner_result
    inputs["clinical_sentences"] = [s.model_dump() for s in ner_result.clinical_sentences]
    inputs["clinical_entities"] = [e.model_dump() for e in ner_result.entities]
    return inputs


async def run_clinical_extraction(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    5. Step: Structured Clinical Extraction using Ollama (qwen2.5:3b) via LCEL.
    """
    logger.info("Step 5/8: Running structured clinical extraction with qwen2.5:3b via LCEL...")
    return await extract_structured_clinical_data(inputs)


async def run_postgres_storage(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 6: Persisting extracted clinical schemas into Postgres via Prisma.
    """
    logger.info("Step 6/8: Writing structured clinical data into Postgres database...")
    return await save_extracted_data_to_postgres(inputs)


async def run_qdrant_storage(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 7: Generating embeddings and indexing metadata in Qdrant Vector DB.
    """
    logger.info("Step 7/8: Generating embeddings and indexing metadata in Qdrant...")
    return await save_extracted_data_to_qdrant(inputs)


def run_file_cleanup(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """8. Step: Delete local uploaded file (Placeholder)."""
    file_path = BASE_DIR / inputs["file_path"]
    logger.info(f"Step 8/8: Purging temporary file from storage path: {file_path}")
    if file_path.exists():
        os.remove(file_path)
    return inputs


# --- CONSTRUCT THE COUPLING LCEL PIPELINE ---
# Flow:     validate → store → OCR → normalize → NER/EL → LLM → SQL → Embeddings + Qdrant → cleanup
ingestion_pipeline = (
    RunnableLambda(run_validation_and_storage)
    | RunnableLambda(run_ocr_parser)
    | RunnableLambda(run_text_normalizer)
    | RunnableLambda(run_clinical_ner)
    | RunnableLambda(run_clinical_extraction)
    | RunnableLambda(run_postgres_storage)
    | RunnableLambda(run_qdrant_storage)
    | RunnableLambda(run_file_cleanup)
)


async def execute_ingestion_pipeline(initial_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Wraps the LCEL pipeline execution. Guarantees that the temporary file
    is cleaned up even if steps in the middle of the pipeline crash.
    """
    state = initial_state.copy()  # Prevent mutating original request state
    try:
        # Run the pipeline
        final_state = await ingestion_pipeline.ainvoke(state)
        return final_state
    except Exception as exc:
        logger.error(f"Pipeline failed mid-execution: {exc}")
        raise exc
    finally:
        # This block ALWAYS runs, whether it succeeded or raised an exception.
        if "file_path" in state:
            run_file_cleanup(state)
