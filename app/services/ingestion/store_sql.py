from __future__ import annotations
import re
from datetime import datetime
from typing import Any, Dict
import json
from prisma import Prisma, Json
from app.core.logger import logger
from app.core.exception import ClinicalExtractionError, DatabaseError
from app.core.db import db, connect_db


def sanitize_json_payload(data: Any) -> Any:
    """
    Recursively sanitizes JSON keys and string values to prevent Prisma's internal 
    GraphQL query engine parser from breaking on bracket syntax like "Creatine[Name]".
    """
    if isinstance(data, dict):
        sanitized_dict = {}
        for key, value in data.items():
            clean_key = re.sub(r'[\[\]\(\)]', '_', str(key))
            clean_key = re.sub(r'_{2,}', '_', clean_key).strip('_')
            sanitized_dict[clean_key] = sanitize_json_payload(value)
        return sanitized_dict
        
    elif isinstance(data, list):
        return [sanitize_json_payload(item) for item in data]
        
    elif isinstance(data, str):
        clean_value = re.sub(r'[\[\]\(\)]', ' ', data)
        return re.sub(r'\s+', ' ', clean_value).strip()
        
    return data


async def save_extracted_data_to_postgres(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 6 Extraction Pipeline Task.
    Extracts structured data components from state context maps and writes them
    persistently into the unified postgres documents schema.
    """
    patient_id = state.get("patient_id")
    doc_type = state.get("doc_type")
    clinical_metadata = state.get("clinical_metadata")

    if not patient_id:
        raise ClinicalExtractionError("Missing state validation property: 'patient_id' is required.")
    if not clinical_metadata:
        raise ClinicalExtractionError("Aborting Step 6 execution: State key 'clinical_metadata' is unallocated.")

    await connect_db()
    
    persistence_summary = await store_clinical_metadata(
        db=db,
        patient_id=patient_id,
        doc_type=doc_type,
        metadata=clinical_metadata
    )

    state["db_record_id"] = persistence_summary["record_id"]
    state["db_target_table"] = persistence_summary["table"]

    logger.info(
        f"[Step 6/8 Completed] Row record '{persistence_summary['record_id']}' successfully committed "
        f"into unified PostgreSQL table structure: '{persistence_summary['table']}'."
    )

    return state


async def store_clinical_metadata(
    db: Prisma, 
    patient_id: str, 
    doc_type: str, 
    metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Step 6 Database Ingestion Worker.
    Persists clinical document records into the 'documents' table structure via Prisma.
    Implicitly skips 'summary' and handles empty values gracefully as NULL.
    """
    raw_date = metadata.get("date")
    parsed_date = datetime.utcnow()
    
    if raw_date:
        try:
            parsed_date = datetime.strptime(raw_date.strip(), "%Y-%m-%d")
        except ValueError:
            logger.warning(f"[DB Ingestion] Date string '{raw_date}' failed YYYY-MM-DD validation. Defaulting to current timestamp.")

    try:
        normalized_type = doc_type.lower().strip()
        if normalized_type not in ["prescription", "report"]:
            raise ValueError(f"Unsupported clinical doc_type parameter variant: '{doc_type}'")

        logger.info(f"[DB Ingestion] Writing record to unified documents table ({normalized_type})")

        # 1. Parse findings JSON gracefully
        raw_findings = metadata.get("findings")
        findings_data = None
        if isinstance(raw_findings, dict) and raw_findings:
            findings_data = Json(sanitize_json_payload(raw_findings))
        else:
            findings_data = Json({})

        # 2. Parse diseases list safely
        raw_diseases = metadata.get("diseases")
        diseases_data = raw_diseases if isinstance(raw_diseases, list) else []

        # 3. Parse and standardize string fields with safe fallbacks
        highlights_data = metadata.get("highlights")
        treatment_data = metadata.get("treatment")
        pre_diagnosis_data = metadata.get("pre_diagnosis")

        if isinstance(highlights_data, list):
            highlights_data = ", ".join(highlights_data)
        if isinstance(treatment_data, list):
            treatment_data = ", ".join(treatment_data)
        if isinstance(pre_diagnosis_data, list):
            pre_diagnosis_data = ", ".join(pre_diagnosis_data)

        # 4. Construct high-fidelity write payload (Notice 'summary' is omitted)
        insert_data = {
            "patientId": patient_id,
            "docType": normalized_type,
            "date": parsed_date,
            "doctor": metadata.get("doctor") or None,
            "findings": findings_data,
            "diseases": diseases_data,
            "highlights": highlights_data or None,
            "treatment": treatment_data or None,
            "preDiagnosis": pre_diagnosis_data or None,
        }

        record = await db.document.create(data=insert_data)
        
        return {"record_id": record.id, "table": "documents"}

    except Exception as db_err:
        logger.error(f"[DB Ingestion Error] Operational write failure on unified documents execution: {db_err}", exc_info=True)
        raise DatabaseError(f"Failed to commit unified document metadata to database: {str(db_err)}")
