# app/services/ingestion/background.py

import asyncio
from typing import Dict, Any

from app.core.logger import logger
from app.services.ingestion.main import execute_ingestion_pipeline


async def process_document_background(
    initial_state: Dict[str, Any],
) -> None:
    """
    Runs the complete ingestion pipeline asynchronously.
    Never propagates exceptions to FastAPI.
    """

    try:
        logger.info(
            f"[Background] Started processing: {initial_state['file'].filename}"
        )

        await execute_ingestion_pipeline(initial_state)

        logger.info(
            f"[Background] Finished processing: {initial_state['file'].filename}"
        )

    except Exception as exc:
        logger.exception(
            f"[Background] Processing failed: {exc}"
        )


def start_background_processing(
    initial_state: Dict[str, Any],
) -> None:
    """
    Fire-and-forget background task.
    """

    asyncio.create_task(
        process_document_background(initial_state)
    )
