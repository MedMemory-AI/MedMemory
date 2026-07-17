from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class ChatRequest(BaseModel):
    """Payload representing a patient context query."""
    query: str = Field(..., min_length=1, max_length=1000, description="The clinical query from the user")

class SourceDocument(BaseModel):
    """Metadata wrapper for retrieved sources used in generation."""
    id: str
    docType: str
    date: str
    doctor: Optional[str] = None

class ChatResponse(BaseModel):
    """Validated structured RAG output payload."""
    success: bool = True
    answer: str = Field(..., description="LLM generated markdown response")
    sources: List[SourceDocument] = Field(default_factory=list, description="Documents fetched to ground this answer")

class StreamEventSchema(BaseModel):
    """Structured SSE wrapper payload payload for frontend consumption."""
    event: str = Field(..., description="Event type: status | token | final | error")
    status: Optional[str] = Field(None, description="Current phase text (e.g., 'Classifying Intent')")
    token: Optional[str] = Field(None, description="Incremental LLM response chunk string")
    data: Optional[Dict[str, Any]] = Field(None, description="Metadata payload like final source maps")
