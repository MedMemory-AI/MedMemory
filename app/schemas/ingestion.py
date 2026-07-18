from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, List, Optional


class LinkedConceptSchema(BaseModel):
    """Single UMLS/MeSH knowledge-base hit for a medical entity span."""
    cui: str = Field(..., description="Concept Unique Identifier (UMLS CUI or MeSH ID)")
    score: float = Field(..., description="Linker similarity score (char-3gram ANN match)")
    canonical_name: Optional[str] = Field(
        None, description="Preferred concept name from the knowledge base"
    )
    definition: Optional[str] = Field(
        None, description="Short clinical definition when available in the KB"
    )


class ClinicalEntitySchema(BaseModel):
    """One medical entity span grounded to sentence context for RAG payloads."""
    text: str
    label: str = Field(..., description="spaCy/sciSpacy entity label (e.g. ENTITY, DISEASE)")
    start_char: int
    end_char: int
    sentence_index: int = Field(..., description="0-based index into clinical_sentences")
    concepts: List[LinkedConceptSchema] = Field(default_factory=list)


class ClinicalSentenceSchema(BaseModel):
    """Sentence unit optimized for downstream chunking / Qdrant embedding."""
    index: int
    text: str
    start_char: int
    end_char: int


class NERProcessingResponseSchema(BaseModel):
    """
    Step-4 output: clinical sentence mesh + linked medical entities.
    Designed as the structured intermediate for RAG vector ingestion and LLM context packing.
    """
    clinical_sentences: List[ClinicalSentenceSchema] = Field(default_factory=list)
    entities: List[ClinicalEntitySchema] = Field(default_factory=list)
    entity_count: int = 0
    sentence_count: int = 0
    linker_name: Optional[str] = Field(
        None, description="Active EntityLinker KB name (umls|mesh) or None if linking disabled"
    )
    model_name: str = "en_core_sci_sm"


class ClinicalExtractionSchema(BaseModel):
    """
    Structured extraction of clinical information from normalized medical records.
    Contains findings, treatments, diagnoses, and medical highlights.
    """
    highlights: Optional[str] = Field(
        None,
        description="Symptoms, patient-reported observations, or chief complaints noted by the clinician. Focus for prescriptions."
    )
    treatment: Optional[str] = Field(
        None,
        description="Structured lists of medications, dosages, frequencies, routes of administration, or active therapies. Focus for prescriptions."
    )
    pre_diagnosis: Optional[str] = Field(
        None,
        description="Ordered diagnostics (e.g., specific lab panels, blood tests, X-rays, MRI scans, biopsies). Focus for prescriptions."
    )
    
    findings: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Exact raw numerical values or text metrics mapped to their respective clinical biomarkers. Must not be null. Focus for lab reports."
    )
    diseases: Optional[List[str]] = Field(
        None,
        description="Array of confirmed or highly suspected clinical conditions, diseases, or pathological states detected. Focus for lab reports."
    )
    
    summary: str = Field(
        ...,
        description="A highly concise, clinical paragraph summarizing the patient's symptoms, active treatments, and ordered diagnostics. Cleaned and optimized for generating vector database embeddings."
    )
    date: Optional[str] = Field(
        None,
        description="The official date the prescription was written by the medical professional. Format as YYYY-MM-DD if found."
    )
    doctor: Optional[str] = Field(
        None,
        description="Name or professional identifier of the prescribing medical professional (e.g. 'Dr. John Doe')."
    )


class UploadResponse(BaseModel):
    """
    Structured metadata representing a successfully written medical record.
    """
    filePath: str
    mimeType: str
    size: int
    cleaned_text: str
    ner: Optional[NERProcessingResponseSchema] = None
    extraction: Optional[ClinicalExtractionSchema] = None
    createdAt: datetime



class IngestionSuccessResponse(BaseModel):
    success: bool = True
    message: str
    data: UploadResponse
