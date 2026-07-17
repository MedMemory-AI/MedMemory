from typing import Literal, Dict, Any, Optional
import json
import re
import httpx
from app.core.config import settings
from app.core.logger import logger

# Strict type definition for intent categories
IntentCategory = Literal["structured", "semantic", "hybrid"]

# Consolidated & optimized regex pattern to reduce regex engine passes
# Captures structured keywords (S) and semantic keywords (M) in a single regex search
INTENT_REGEX = re.compile(
    r"\b(?P<S>when|who|which|date|year|month|diagnosed|doctor|clinician|list|prescription|report|dr\.?)\b|"
    r"\b(?P<M>why|how|explain|treatment|symptom|finding|highlight|note|summary|detail|advice|complain|feel)\b",
    re.IGNORECASE
)

INTENT_SYSTEM_PROMPT = """
You are a highly precise clinical query classifier. Your sole objective is to classify the user's medical query into exactly one of three routing categories to optimize database retrieval.

# RAG ROUTING CATEGORIES:
1. "structured"
    - Scope: Queries retrieving discrete, explicit database fields, dates, or counts best resolved via SQL.
    - Examples: "When was diabetes diagnosed?", "Who is my primary doctor?", "Show me a list of my diseases."
2. "semantic"
    - Scope: Unstructured, qualitative questions requiring contextual search over narratives or summaries via Vector DB.
    - Examples: "What was my treatment plan?", "Explain my clinical findings.", "Why was I prescribed this medication?"
3. "hybrid"
    - Scope: Complex queries that merge strict metadata filters with qualitative, conceptual search.
    - Examples: "What did Dr. Srinivas note about my chest pain last year?", "Are there any reports from June showing elevated sugar levels?"

# CRITICAL FORMATTING RULES:
- Respond ONLY with a raw, valid JSON object containing the "intent" key.
- NEVER wrap your response in markdown code blocks (do NOT use ```json or ```).
- Provide absolutely NO explanations, NO conversational preamble, and NO postscript text.

# FEW-SHOT EXAMPLES:
Output: {{"intent": "hybrid"}}
Output: {{"intent": "semantic"}}
Output: {{"intent": "structured"}}
"""

# Prevents recreating connections for every fallback request
limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)
http_client = httpx.AsyncClient(limits=limits, timeout=10.0)


def classify_intent_heuristics(query: str) -> Optional[IntentCategory]:
    """
    Evaluates query patterns deterministically in microseconds using a single-pass regex search.
    """
    query_lower = query.lower()
    
    has_structured = False
    has_semantic = False

    # Single pass scanning over the input query
    for match in INTENT_REGEX.finditer(query_lower):
        if match.lastgroup == 'S':
            has_structured = True
        elif match.lastgroup == 'M':
            has_semantic = True
        
        # Micro-optimization: break early if both are found (hybrid)
        if has_structured and has_semantic:
            return "hybrid"

    if has_structured:
        return "structured"
    if has_semantic:
        return "semantic"

    return None


async def classify_query_intent(query: str) -> IntentCategory:
    """
    Infers query intent via Ollama LLM using strict JSON formatting.
    Defaults safely to 'hybrid' on parsing failures.
    """
    # 1. Fast Path: Single-pass regex rules (~0.02ms)
    heuristic_intent = classify_intent_heuristics(query)
    if heuristic_intent:
        logger.info(f"[Intent Router] Fast-Path Match Resolved: '{heuristic_intent.upper()}'")
        return heuristic_intent
    
    # 2. Slow Path: Fallback to pooled connection LLM (~150-300ms)
    logger.info("[Intent Router] Query ambiguous. Executing Slow-Path LLM Fallback...")
    
    url = f"{settings.OLLAMA_BASE_URL.strip().rstrip('/')}/api/generate"
    payload = {
        "model": getattr(settings, "OLLAMA_CHAT_MODEL", "qwen2.5:3b"),
        "prompt": f"Classify this query: \"{query}\"",
        "system": INTENT_SYSTEM_PROMPT,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.0,  # Zero variance for strict routing determinism
        }
    }
    
    try:
        # Reuses pooled HTTP connection safely
        response = await http_client.post(url, json=payload)
        response.raise_for_status()
        raw_output = response.json().get("response", "").strip()

        # Clean potential LLM markdown wraps
        cleaned_json = re.sub(r"^```json\s*|```$", "", raw_output, flags=re.MULTILINE).strip()
        
        parsed_data = json.loads(cleaned_json)
        intent = parsed_data.get("intent", "").lower().strip()

        if intent in ["structured", "semantic", "hybrid"]:
            return intent
        
        raise ValueError(f"Model returned invalid category payload: '{intent}'")

    except Exception as err:
        # Fail-safe default prevents production downtime
        logger.warning(f"[Intent Classifier] Failed classifying query. Falling back to 'hybrid'. Error: {err}")
        return "hybrid"
