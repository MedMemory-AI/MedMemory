from __future__ import annotations
import os
import asyncio
import threading
from typing import Any, Dict, List, Optional

# LangChain and Pydantic Core Components
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings
from app.core.logger import logger
from app.core.exception import ClinicalExtractionError
from app.schemas.ingestion import ClinicalExtractionSchema


# =====================================================================
# 1. DETERMINISTIC STRUCTURAL SCHEMAS FOR LLM COMPLIANCE
# =====================================================================

class LLMClinicalDocumentSchema(BaseModel):
    """
    Unified clinical extraction format capturing prescriptions, treatments, 
    diagnostics, biomarker findings, and active conditions in a single pass.
    """
    date: Optional[str] = Field(
        None,
        description="The official date written on the document. Standardize strictly to YYYY-MM-DD if present."
    )
    doctor: Optional[str] = Field(
        None,
        description="Full name, medical registry title, or identifier of the clinician (e.g., 'Dr. Jane Smith')."
    )
    highlights: Optional[str] = Field(
        "",
        description="Capture of chief complaints, physical findings, or clinical symptoms."
    )
    treatment: Optional[str] = Field(
        "",
        description="Comprehensive list of prescribed drugs, dosages, frequencies, routes, or therapy plans."
    )
    pre_diagnosis: Optional[str] = Field(
        "",
        description="Planned clinical diagnostics, ordered laboratory panels, imaging studies, or screening exams."
    )
    findings: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Raw lab results mapping biomarker names to exact raw numerical metrics and units (e.g., {'Serum Chloride': '104 mmol/L'})."
    )
    diseases: Optional[List[str]] = Field(
        default_factory=list,
        description="List of detected or confirmed conditions, metabolic abnormalities, or active diseases."
    )
    summary: str = Field(
        ...,
        description="A highly concise, dense 2-3 sentence clinical summary containing solely active treatments, biomarker findings, and ordered diagnostics. Optimized for search."
    )


# =====================================================================
# 2. RUNTIME ENGINE STATE MANAGER (PURE OLLAMA DRIVEN - QWEN2.5:3B)
# =====================================================================

class ClinicalExtractionEngine:
    """
    Thread-safe engine for structured medical extraction and semantic summarization.
    Orchestrates local or hosted Ollama instances for deterministic extraction.
    """
    _instance: Optional["ClinicalExtractionEngine"] = None
    _init_lock = threading.Lock()

    def __new__(cls) -> "ClinicalExtractionEngine":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        try:
            self.timeout = float(os.getenv("MEDMEMORY_LLM_TIMEOUT", "60.0"))
        except ValueError:
            self.timeout = 60.0

        self.model_name = os.getenv("MEDMEMORY_OLLAMA_MODEL", "qwen2.5:3b").strip()
        self.base_url = settings.OLLAMA_BASE_URL.strip()
        
        logger.info(f"[Extraction Engine] Initializing client runtime: Ollama Endpoint={self.base_url} Model={self.model_name}")
        
        from langchain_ollama import ChatOllama
        self.llm = ChatOllama(
            model=self.model_name,
            base_url=self.base_url,
            temperature=0.0,
            timeout=self.timeout
        )

        # Unified holistic medical parser prompt optimized for Qwen 2.5 (3B)
        self.unified_prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "You are an elite clinical NLP system designed to convert raw clinical texts into structured JSON metadata.\n"
                "Your task is to extract all present medical entities and synthesize them into the specified schema parameters.\n\n"
                "CRITICAL EXTRACTION RULEBOOK:\n"
                "1. Extract ONLY information directly supported by the raw text or clinical context. Never assume or extrapolate.\n"
                "2. If a field has no evidence or is absent in the clinical text, output the exact default fallback value specified below. Do not omit the field keys.\n\n"
                "FIELD-SPECIFIC RULES & FALLBACKS:\n"
                "- 'date': Standardize strictly to 'YYYY-MM-DD' (e.g., '2026-03-29'). Fallback: null\n"
                "- 'doctor': Name of the prescribing or validating clinician. Fallback: null\n"
                "- 'highlights': Dense text capturing chief complaints, symptoms, or physical observations. Fallback: \"\"\n"
                "- 'treatment': Prescribed drugs, exact dosages, frequencies, or therapy guidelines. Fallback: \"\"\n"
                "- 'pre_diagnosis': Planned/ordered diagnostics, labs, or imaging (e.g., 'CBC', 'Chest X-Ray'). Fallback: \"\"\n"
                "- 'findings': A flat key-value JSON object mapping clinical biomarkers or vitals to exact raw values (e.g., {{\"Serum Creatine\": \"138 U/L\", \"HbA1c\": \"6.4%\"}}). Fallback: {{}}\n"
                "- 'diseases': A list of active chronic conditions, pathologic abnormalities, or diagnoses. Fallback: []\n"
                "- 'summary': Synthesize all extracted facts into a highly concise, objective 2-3 sentence summary optimized for vector search embeddings. Omit any introductory filler or conversational fluff.\n\n"
                "Remember: Even if the document is a 'prescription', actively look for laboratory 'findings' or 'diseases' and extract them if found."
            )),
            ("user", (
                "--- RAW MEDICAL DOCUMENT TEXT ---\n"
                "<raw_text>\n"
                "{cleaned_text}\n"
                "</raw_text>\n\n"
                "--- SEGMENTED CLINICAL SENTENCES & LINKED ENTITIES ---\n"
                "<clinical_context>\n"
                "{clinical_context}\n"
                "</clinical_context>"
            ))
        ])
        self.extraction_chain = (
            self.unified_prompt 
            | self.llm.with_structured_output(LLMClinicalDocumentSchema, method="json_schema")
        )

        self._initialized = True

    async def extract(
        self,
        doc_type: str,
        cleaned_text: str,
        clinical_context: str
    ) -> ClinicalExtractionSchema:
        """
        Executes unified structural extraction via Ollama.
        """
        try:
            logger.info(f"[Extraction] Invoking Unified Medical Extraction Engine via Ollama [{self.model_name}]")
            raw_extracted: LLMClinicalDocumentSchema = await self.extraction_chain.ainvoke({
                "cleaned_text": cleaned_text,
                "clinical_context": clinical_context
            })

            # Maps all parsed values safely to the agnostic schema
            return ClinicalExtractionSchema(
                date=raw_extracted.date or None,
                doctor=raw_extracted.doctor or None,
                highlights=raw_extracted.highlights or None,
                treatment=raw_extracted.treatment or None,
                pre_diagnosis=raw_extracted.pre_diagnosis or None,
                findings=raw_extracted.findings,
                diseases=raw_extracted.diseases,
                summary=raw_extracted.summary
            )

        except ValidationError as val_err:
            logger.error(f"[Extraction Error] Structural schema divergence detected: {val_err}")
            raise ClinicalExtractionError(f"LLM validation alignment failure: {str(val_err)}")
        except Exception as exc:
            logger.error(f"[Extraction Error] Pipeline abort on Ollama instance configuration: {exc}", exc_info=True)
            raise ClinicalExtractionError(f"Structured execution pipeline failure: {str(exc)}")


extraction_engine = ClinicalExtractionEngine()


# =====================================================================
# 3. INTERACTION ENTRYPOINT PIPELINE STAGE TASK
# =====================================================================

async def extract_structured_clinical_data(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 5 Extraction Pipeline Task.
    """
    doc_type = state.get("doc_type", "report")
    cleaned_text = state.get("cleaned_text", "")
    ner_data = state.get("ner", {})
    
    clinical_sentences = []
    clinical_entities = []

    if ner_data:
        if hasattr(ner_data, "clinical_sentences"):
            clinical_sentences = [{"index": s.index, "text": s.text} for s in ner_data.clinical_sentences]
            if hasattr(ner_data, "clinical_entities"):
                clinical_entities = [
                    {
                        "text": e.text, 
                        "label": e.label, 
                        "sentence_index": e.sentence_index,
                        "concepts": [{"canonical_name": c.canonical_name} for c in getattr(e, "concepts", [])]
                    } for e in ner_data.clinical_entities
                ]
        elif isinstance(ner_data, dict):
            clinical_sentences = ner_data.get("clinical_sentences", [])
            clinical_entities = ner_data.get("clinical_entities", [])

    context_builder = []
    if clinical_sentences:
        context_builder.append("### Segmented Sentences:")
        for s in clinical_sentences:
            idx = s.get("index", 0)
            text = s.get("text", "").strip()
            context_builder.append(f"Sentence {idx}: {text}")
            
            related_ents = [e for e in clinical_entities if e.get("sentence_index") == idx]
            if related_ents:
                ent_strings = []
                for re in related_ents:
                    concepts = re.get("concepts", [])
                    c_names = [c.get("canonical_name") for c in concepts if c.get("canonical_name")]
                    concept_lbl = f" (UMLS: {', '.join(c_names)})" if c_names else ""
                    ent_strings.append(f"'{re.get('text')}' [{re.get('label')}{concept_lbl}]")
                context_builder.append(f"  └─ Linked Identifiers: {', '.join(ent_strings)}")
    else:
        context_builder.append("### Raw Cleaned Text Lines:")
        context_builder.extend([f"Line {idx}: {line.strip()}" for idx, line in enumerate(cleaned_text.split("\n")) if line.strip()])

    unified_clinical_context = "\n".join(context_builder)

    extracted_model = await extraction_engine.extract(
        doc_type=doc_type,
        cleaned_text=cleaned_text,
        clinical_context=unified_clinical_context
    )

    state["clinical_metadata"] = extracted_model.model_dump()
    logger.info("[Step 5/8 Completed] Unified data maps and embeddings-optimized summary committed to state.")

    return state
