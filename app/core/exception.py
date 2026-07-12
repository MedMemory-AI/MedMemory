from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from app.core.logger import logger


class MedMemoryException(Exception):
    """
    Base Custom Exception: All custom, domain-specific exceptions inherit from this 
    class to enable streamlined catch-all sorting.
    """
    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)

class ClinicalParsingError(MedMemoryException):
    """Raised when Docling or OCR fails to process unstructured inputs."""
    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)

class VectorStoreException(MedMemoryException):
    """Raised when Qdrant connections time out or read/write vectors fail."""
    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

def register_exception_handlers(app: FastAPI):
    """
    Registers global exception hooks across your FastAPI instance to translate 
    raw code crashes into predictable, clean JSON server responses.
    """
    @app.exception_handler(MedMemoryException)
    async def custom_exception_handler(request: Request, exc: MedMemoryException):
        """
        Catches intentional application errors, logs their context, 
        and sends a controlled error package to the client frontend.
        """
        logger.warning(f"Domain Exception Intercepted on {request.url.path}: {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"status": "error", "error_type": exc.__class__.__name__, "message": exc.detail}
        )

    @app.exception_handler(Exception)
    async def global_catch_all_handler(request: Request, exc: Exception):
        """
        Global Catch-All: Intercepts unhandled native runtime errors (e.g., NullPointer, KeyErrors),
        prevents raw stack traces from exposing security details, and logs the real trace.
        """
        # Capture the absolute failure stack depth into our active log files
        logger.error(f"CRITICAL SYSTEM CRASH on {request.url.path} ➔ {str(exc)}", exc_info=True)
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "fail",
                "error_type": "InternalServerError",
                "message": "An unexpected error occurred inside the medical core engine layer."
            }
        )
