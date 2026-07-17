# app/services/chat/generator.py
from __future__ import annotations
import io
import os
import re
import threading
from typing import Any, Dict, List, Optional
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from app.core.config import settings
from app.core.logger import logger


class ClinicalGenerationError(Exception):
    """Raised when the LLM text generation pipeline encounters a failure."""
    pass

# =====================================================================
# RUNTIME GENERATION ENGINE (PURE OLLAMA DRIVEN - QWEN2.5:3B)
# =====================================================================
class ClinicalGenerationEngine:
    """
    Thread-safe engine for orchestrating medical text generation.
    Connects to local/hosted Ollama instances to generate patient and clinician-friendly
    responses based strictly on retrieved contextual documents without hallucination.
    """
    _instance: Optional["ClinicalGenerationEngine"] = None
    _init_lock = threading.Lock()

    def __new__(cls) -> "ClinicalGenerationEngine":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        # 1. Resolve configuration parameters from context settings Safely
        try:
            self.timeout = float(os.getenv("MEDMEMORY_LLM_TIMEOUT", "60.0"))
        except ValueError:
            self.timeout = 60.0

        self.model_name = os.getenv("MEDMEMORY_OLLAMA_MODEL", "qwen2.5:3b").strip()
        self.base_url = settings.OLLAMA_BASE_URL.strip()
        
        logger.info(f"[Generation Engine] Initializing client runtime: Ollama Endpoint={self.base_url} Model={self.model_name}")
        
        # 2. Instantiate high-performance local ChatOllama client
        from langchain_ollama import ChatOllama
        self.llm = ChatOllama(
            model=self.model_name,
            base_url=self.base_url,
            streaming=True,  # CRITICAL FOR REAL-TIME TOKENS
            temperature=0.1,  # Kept low for high factual compliance while maintaining natural prose
            timeout=self.timeout
        )

        # 3. Construct explicit, non-hallucinating system instructions optimized for Qwen 2.5 (3B)
        self.generation_prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "You are an expert clinical AI communicator. Your objective is to formulate a response to the user's query "
                "based strictly on the verified clinical records provided. You must adhere to the following rules:\n\n"
                "CRITICAL COMMUNICATION & ANTI-HALLUCINATION RULES:\n"
                "1. STRICT FACTUAL COMPLIANCE: Answer using only the explicitly stated facts within the retrieved medical context. "
                "If the context does not contain the answer, state clearly: 'I am sorry, but that information is not available in the current medical records.'\n"
                "2. NO EXTRAPOLATION: Do not make assumptions, invent dates, create clinical histories, or predict laboratory trends.\n"
                "3. TONE & ACCESSIBILITY: Provide a response that is simple, professional, empathetic, shorter to medium sized and highly readable for both patients and doctors.\n"
                "4. FORMATTING RULES:\n"
                "   - Organize data points using bold headers, horizontal lines, or bullet points.\n"
                "   - Avoid dense blocks of text.\n"
                "   - Keep it concise, professional, and clear.\n"
                "   - Do not mention or reference system internals, nodes, or database models."
            )),
            ("user", (
                "--- RETRIEVED CLINICAL CONTEXT RECORDS ---\n"
                "<context>\n"
                "{formatted_context}\n"
                "</context>\n\n"
                "--- USER QUERY ---\n"
                "Query: {cleaned_query}\n\n"
                "Synthesize a well-structured, clear response following all compliance guidelines above."
            ))
        ])
        
        # 4. Standard linear compilation string chain execution path
        self.generation_chain = self.generation_prompt | self.llm | StrOutputParser()
        self._initialized = True


    def _clean_llm_markdown(self, text: str) -> str:
        """
        Cleans the raw LLM output text stream to make it perfectly safe for frontend UI rendering.
        Removes chain-of-thought tags, leading system leaks, and structural noise.
        """
        if not text:
            return ""

        # Remove explicit local reasoning tokens (<think>...</think>) if present
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

        # Normalize carriage returns and line ending combinations
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Strip any accidental wrapping Markdown codeblocks (e.g., ```markdown ... ```)
        text = re.sub(r"^```(?:markdown)?\n", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n```$", "", text)

        # Final strip of stray whitespace wrappers
        return text.strip()


    async def generate_response(self, cleaned_query: str, retrieved_docs: List[Dict[str, Any]]) -> str:
        """
        Formats retrieved medical context records and passes them to the LLM for generation.
        """
        try:
            # Using StringIO for O(N) performance memory overhead inside serialization loops
            buffer = io.StringIO()

            if not retrieved_docs:
                buffer.write("No clinical documents retrieved for this patient.")
            else:
                for idx, doc in enumerate(retrieved_docs, 1):
                    if idx > 1:
                        buffer.write("\n---\n")
                    
                    buffer.write(f"Document [{idx}]:\n")
                    buffer.write(f"- Type: {doc.get('doc_type', 'Unknown')}\n")
                    buffer.write(f"- Date: {doc.get('date', 'Unknown')}\n")
                    buffer.write(f"- Clinician: {doc.get('doctor', 'N/A')}\n")
                    buffer.write(f"- Content: {doc.get('content', '')}\n")
                    
                    # Append structured details block if hybrid enrichment step was triggered
                    sd = doc.get("structured_details")
                    if isinstance(sd, dict) and sd:
                        buffer.write(f"- Key Highlights: {sd.get('highlights', '')}\n")
                        buffer.write(f"- Prescribed Treatments: {sd.get('treatment', '')}\n")
                        buffer.write(f"- Ordered Labs/Diagnostics: {sd.get('pre_diagnosis', '')}\n")
                        buffer.write(f"- Tracked Biomarkers: {sd.get('findings', {})}\n")
                        buffer.write(f"- Active Diagnoses: {sd.get('diseases', [])}\n")

            formatted_context = buffer.getvalue()
            buffer.close()

            logger.info(f"[Generation Engine] Dispatching generation payload via Ollama [{self.model_name}]")
            
            # Asynchronously execute prompt sequence parsing
            raw_response = await self.generation_chain.ainvoke({
                "formatted_context": formatted_context,
                "cleaned_query": cleaned_query
            })
            
            # Clean response parameters to guarantee UI alignment stability
            return self._clean_llm_markdown(raw_response)

        except Exception as exc:
            logger.error(f"[Generation Error] Pipeline abort during execution: {exc}", exc_info=True)
            raise ClinicalGenerationError(f"Text generation pipeline runtime failure: {str(exc)}") from exc


    # For Streaming Response in Production via SSE...
    async def stream_response(self, cleaned_query: str, retrieved_docs: List[Dict[str, Any]]):
        """
        Asynchronously streams token updates out directly from the Ollama runtime instance.
        """
        try:
            buffer = io.StringIO()
            if not retrieved_docs:
                buffer.write("No clinical documents retrieved for this patient.")
            else:
                for idx, doc in enumerate(retrieved_docs, 1):
                    if idx > 1:
                        buffer.write("\n---\n")
                    buffer.write(f"Document [{idx}]:\n")
                    buffer.write(f"- Type: {doc.get('doc_type', 'Unknown')}\n")
                    buffer.write(f"- Date: {doc.get('date', 'Unknown')}\n")
                    buffer.write(f"- Clinician: {doc.get('doctor', 'N/A')}\n")
                    buffer.write(f"- Content: {doc.get('content', '')}\n")
                    
                    sd = doc.get("structured_details")
                    if isinstance(sd, dict) and sd:
                        buffer.write(f"- Key Highlights: {sd.get('highlights', '')}\n")
                        buffer.write(f"- Prescribed Treatments: {sd.get('treatment', '')}\n")
                        buffer.write(f"- Ordered Labs/Diagnostics: {sd.get('pre_diagnosis', '')}\n")
                        buffer.write(f"- Tracked Biomarkers: {sd.get('findings', {})}\n")
                        buffer.write(f"- Active Diagnoses: {sd.get('diseases', [])}\n")

            formatted_context = buffer.getvalue()
            buffer.close()

            logger.info(f"[Generation Engine] Initializing dynamic token stream via Ollama [{self.model_name}]")
            
            # Use standard astream parser runner 
            async for chunk in self.generation_chain.astream({
                "formatted_context": formatted_context,
                "cleaned_query": cleaned_query
            }):
                # Yield tokens immediately to the caller node loop
                yield chunk

        except Exception as exc:
            logger.error(f"[Generation Stream Error] Failed to yield tokens: {exc}", exc_info=True)
            raise ClinicalGenerationError(f"Streaming token generation pipeline failure: {str(exc)}")


generation_engine = ClinicalGenerationEngine()
