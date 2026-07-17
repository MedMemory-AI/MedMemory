# app/services/ingestion/ner.py
from __future__ import annotations

import asyncio
import os
import threading
import re
from functools import lru_cache
from typing import Any, List, Optional, Tuple, Set

from app.core.exception import ClinicalNERError
from app.core.logger import logger
from app.schemas.ingestion import (
    ClinicalEntitySchema,
    ClinicalSentenceSchema,
    LinkedConceptSchema,
    NERProcessingResponseSchema,
)

try:
    import spacy
    from spacy.language import Language
except ImportError:
    spacy = None  
    Language = Any  

# Whitelist of structural substrings that represent valid lab biomarkers even if linker thresholds drop them
VALID_LAB_MARKERS: Set[str] = {
    "cholesterol", "triglycerides", "hdl", "ldl", "vldl", "cpk", "ldh", 
    "creatine", "phosphokinase", "lactate", "dehydrogenase", 
    "sodium", "potassium", "chloride", "serum", "rbc", "wbc", "hemoglobin"
}

# Compile noise regex flags once for high-throughput loop operations
NOISE_REGEX = re.compile(r'(^[0-9_\-\s\n\\\/]+$)|(page\s*\d+)|(date\s*)|(signature)', re.IGNORECASE)


class ClinicalNEREngine:
    _instance: Optional["ClinicalNEREngine"] = None
    _init_lock = threading.Lock()

    def __new__(cls) -> "ClinicalNEREngine":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._nlp = None
                    cls._instance._linker_name = None
                    cls._instance._model_name = os.getenv("MEDMEMORY_SCISPACY_MODEL", "en_core_sci_sm")
                    cls._instance._load_lock = threading.Lock()
                    cls._instance._loaded = False
        return cls._instance

    def _resolve_linker_preference(self) -> Optional[str]:
        raw = os.getenv("MEDMEMORY_ENTITY_LINKER", "mesh").strip().lower()
        if raw in {"", "none", "off", "false", "0"}:
            return None
        return "mesh" if raw not in {"umls", "mesh"} else raw

    def _prune_pipeline(self, nlp: "Language") -> "Language":
        for pipe in ["parser", "tagger", "attribute_ruler", "lemmatizer"]:
            if pipe in nlp.pipe_names:
                nlp.disable_pipe(pipe)
        if "sentencizer" not in nlp.pipe_names:
            nlp.add_pipe("sentencizer", config={"punct_chars": [".", "!", "?", "\n"]})
        return nlp

    def _attach_entity_linker(self, nlp: "Language", linker_name: str) -> Optional[str]:
        try:
            from scispacy.linking import EntityLinker  # noqa: F401
        except Exception:
            return None

        if "scispacy_linker" in nlp.pipe_names:
            return linker_name

        try:
            nlp.add_pipe("scispacy_linker", config={"resolve_abbreviations": False, "linker_name": linker_name, "max_entities_per_mention": 2, "threshold": 0.70})
            return linker_name
        except Exception:
            return None

    def _load_model(self) -> None:
        if self._loaded:
            return
        with self._load_lock:
            if self._loaded:
                return
            if spacy is None:
                raise ClinicalNERError("spaCy core wheel frameworks are missing.")
            try:
                nlp = spacy.load(self._model_name, exclude=["parser", "tagger", "attribute_ruler", "lemmatizer"])
            except OSError as exc:
                raise ClinicalNERError(f"sciSpacy weights missing: {exc}")

            nlp.max_length = max(nlp.max_length, 2_500_000)
            nlp = self._prune_pipeline(nlp)
            preferred = self._resolve_linker_preference()
            
            self._linker_name = self._attach_entity_linker(nlp, preferred) if preferred else None
            self._nlp = nlp
            self._loaded = True
            self._setup_cui_cache(nlp)

    def _setup_cui_cache(self, nlp: "Language"):
        linker_pipe = nlp.get_pipe("scispacy_linker") if "scispacy_linker" in nlp.pipe_names else None
        kb = getattr(linker_pipe, "kb", None) if linker_pipe else None

        @lru_cache(maxsize=4096)
        def get_cached_concept(cui: str, score: float) -> LinkedConceptSchema:
            canonical_name, definition = None, None
            if kb and hasattr(kb, "cui_to_entity"):
                entity_obj = kb.cui_to_entity.get(cui)
                if entity_obj:
                    canonical_name = getattr(entity_obj, "canonical_name", None)
                    raw_def = getattr(entity_obj, "definition", None) or ""
                    definition = (raw_def[:350] + "…") if len(raw_def) > 350 else (raw_def or None)
            return LinkedConceptSchema(cui=cui, score=float(score), canonical_name=canonical_name, definition=definition)
        self._get_concept_payload = get_cached_concept

    def _sentence_index_for_span(self, span_start: int, sentence_bounds: List[Tuple[int, int, int]]) -> int:
        for idx, start, end in sentence_bounds:
            if start <= span_start < end:
                return idx
        return 0

    def process_text(self, cleaned_text: str) -> NERProcessingResponseSchema:
        """Executes processing workflows filtering administrative OCR text noise out completely."""
        text = (cleaned_text or "").strip()
        if not text:
            return NERProcessingResponseSchema(model_name=self._model_name, linker_name=self._linker_name)

        nlp = self.nlp
        doc = nlp(text)

        sentence_bounds: List[Tuple[int, int, int]] = []
        clinical_sentences: List[ClinicalSentenceSchema] = []
        
        for sent_idx, sent in enumerate(doc.sents):
            sent_text = sent.text.strip()
            if not sent_text:
                continue
            clinical_sentences.append(ClinicalSentenceSchema(index=sent_idx, text=sent_text, start_char=sent.start_char, end_char=sent.end_char))
            sentence_bounds.append((sent_idx, sent.start_char, sent.end_char))

        entities: List[ClinicalEntitySchema] = []
        for ent in doc.ents:
            surface = ent.text.strip()
            surface_lower = surface.lower()

            # 1. Structural Regex & Length Check (Drops pure numbers, empty spacing, and OCR lines)
            if len(surface) < 2 or NOISE_REGEX.search(surface_lower):
                continue

            # 2. Extract mapped concepts from knowledge index layer
            concepts: List[LinkedConceptSchema] = []
            kb_ents = getattr(ent._, "kb_ents", None) or []
            for cui, score in kb_ents:
                concepts.append(self._get_concept_payload(cui, score))

            # 3. Guard Validation Matrix (Keep ONLY true entities or explicitly verified lab panels)
            has_valid_concept = len(concepts) > 0
            contains_biomarker = any(marker in surface_lower for marker in VALID_LAB_MARKERS)

            # Drop completely if it has no clinical concept map AND isn't explicitly on the biomarker list
            if not (has_valid_concept or contains_biomarker):
                continue

            # 4. Clean formatting glitches (e.g. extracts like "so-5\nserum chloride" become clean targets)
            clean_surface = re.sub(r'^.*\n', '', surface) if "\n" in surface else surface

            entities.append(
                ClinicalEntitySchema(
                    text=clean_surface.strip(),
                    label=ent.label_,
                    start_char=ent.start_char,
                    end_char=ent.end_char,
                    sentence_index=self._sentence_index_for_span(ent.start_char, sentence_bounds),
                    concepts=concepts,
                )
            )

        response = NERProcessingResponseSchema(
            clinical_sentences=clinical_sentences,
            entities=entities,
            entity_count=len(entities),
            sentence_count=len(clinical_sentences),
            linker_name=self._linker_name,
            model_name=self._model_name,
        )
        del doc
        return response

    @property
    def nlp(self) -> "Language":
        self._load_model()
        assert self._nlp is not None
        return self._nlp


ner_engine = ClinicalNEREngine()

async def extract_clinical_entities(cleaned_text: str) -> NERProcessingResponseSchema:
    return await asyncio.to_thread(ner_engine.process_text, cleaned_text)

async def warm_clinical_ner_engine() -> None:
    await asyncio.to_thread(ner_engine._load_model)
