from __future__ import annotations
from datetime import date as date_type, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class TimelineDocumentResponse(BaseModel):
    """
    Unified representation of a Patient Document (Prescription or Report) 
    tailored for frontend timeline visualization.
    """
    id: str = Field(..., description="Unique UUID identifier of the document")
    patient_id: str = Field(..., alias="patientId", description="The owner patient ID")
    doc_type: str = Field(..., alias="docType", description="Document categorization: 'prescription' or 'report'")
    date: date_type = Field(..., description="The clinical event date")
    doctor: Optional[str] = Field(None, description="Name of the diagnosing clinician")
    
    # Report-specific fields
    findings: Optional[Dict[str, Any]] = Field(None, description="JSON clinical findings structure")
    diseases: List[str] = Field(default_factory=list, description="Extracted diagnostic disease labels")
    
    # Prescription-specific fields
    highlights: Optional[str] = Field(None, description="Extracted prescription highpoints")
    treatment: Optional[str] = Field(None, description="Suggested medication treatment plans")
    pre_diagnosis: Optional[str] = Field(None, alias="preDiagnosis", description="Preliminary physical diagnosis")
    
    created_at: datetime = Field(..., alias="createdAt", description="Backend generation timestamp")

    class Config:
        populate_by_name = True
        from_attributes = True


class TimelineSuccessResponse(BaseModel):
    """Successful payload returned containing the sorted historical records."""
    success: bool = True
    message: str = "Patient health timeline retrieved successfully."
    patient_id: str = Field(..., description="Target patient identity context")
    count: int = Field(..., description="Number of historical events matched")
    timeline: List[TimelineDocumentResponse] = Field(..., description="Chronologically organized records")
