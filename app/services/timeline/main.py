# services/timeline/main.py
from __future__ import annotations
from typing import List
from prisma.models import Document
from app.core.db import db, connect_db
from app.core.logger import logger
from app.core.exception import DatabaseError

async def get_patient_timeline(
    patient_id: str, 
    ascending: bool = False
) -> List[Document]:
    """
    Fetches all historical health documents associated with a patient, 
    sorted primarily by clinical 'date' and secondarily by 'createdAt' timestamp.
    """
    # 1. Open and verify database session pool
    await connect_db()
    
    sort_order = "asc" if ascending else "desc"
    
    try:
        logger.info(f"[Timeline Service] Fetching history for patient: {patient_id} (Sort: {sort_order.upper()})")
        
        # 2. Query documents with multi-key database sorting
        documents = await db.document.find_many(
            where={
                "patientId": patient_id
            },
            order=[
                {"date": sort_order},
                {"createdAt": sort_order}
            ]
        )
        
        logger.info(f"[Timeline Service] Retrieved {len(documents)} records successfully.")
        return documents
        
    except Exception as err:
        logger.error(f"[Timeline Service Error] DB query execution crash: {err}", exc_info=True)
        raise DatabaseError(f"Failed to compile clinical timeline data: {str(err)}")
