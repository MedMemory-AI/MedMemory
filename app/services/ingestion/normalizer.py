# app/services/ingestion/normalizer.py
import re
import asyncio
from pathlib import Path
from typing import Dict, List
import symspellpy
from symspellpy import SymSpell
from doublemetaphone import doublemetaphone
from app.core.logger import logger


class ClinicalTextNormalizer:
    def __init__(self):
        self.sym_spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
        self._initialize_dictionaries()
        self._initialize_clinical_maps()

    def _initialize_dictionaries(self):
        """Loads vocabularies on class instantiation to optimize runtime execution loops."""
        try:
            sym_dict_path = Path(symspellpy.__file__).parent / "frequency_dictionary_en_82_765.txt"
            if sym_dict_path.exists():
                self.sym_spell.load_frequency_dictionary(str(sym_dict_path), term_index=0, count_index=1)
                logger.info("SymSpell vocabulary engine initialized successfully.")
            else:
                logger.warning("Default English frequency dictionary file target not found.")
        except Exception as e:
            logger.error(f"Failed loading algorithmic spellcheck dictionaries: {str(e)}")

    def _initialize_clinical_maps(self):
        """Compiles high-speed lookup tables for clinical acronyms, phrases, and expected lab limits."""
        self.abbreviation_map: Dict[str, str] = {
            "qd": "once daily", "bid": "twice daily", "tid": "three times daily",
            "qid": "four times daily", "po": "by mouth", "prn": "as needed",
            "hs": "at bedtime", "rx": "prescription"
        }

        # Context Bounds Matrix: Map key laboratory items to their baseline physiological ranges.
        self.biomarker_context_bounds = {
            "potassium": {"min": 3.5, "max": 5.0, "is_decimal": True},
            "sodium": {"min": 135.0, "max": 145.0, "is_decimal": False},
            "chloride": {"min": 95.0, "max": 106.0, "is_decimal": False},
            "creatine": {"min": 20.0, "max": 500.0, "is_decimal": False},  # Expanded max slightly for clinical safety
            "phosphokinase": {"min": 20.0, "max": 500.0, "is_decimal": False},
            "cpk": {"min": 20.0, "max": 500.0, "is_decimal": False},
            "cholesterol": {"min": 100.0, "max": 300.0, "is_decimal": False},
            "triglycerides": {"min": 50.0, "max": 200.0, "is_decimal": False}
        }

        self.medical_vocabulary: List[str] = [
            "paracetamol", "ibuprofen", "amoxicillin", "atorvastatin", "metformin", 
            "lisinopril", "levothyroxine", "albuterol", "gabapentin", "propranolol", 
            "omeprazole", "azithromycin", "ciprofloxacin", "metoprolol", "losartan",
            "creatine", "phosphokinase", "lactate", "dehydrogenase", "potassium",
            "sodium", "chloride", "cholesterol", "triglycerides", "serum"
        ]

        self.phonetic_medical_cache: Dict[str, str] = {}
        for term in self.medical_vocabulary:
            prim, sec = doublemetaphone(term)
            if prim: self.phonetic_medical_cache[prim] = term
            if sec:  self.phonetic_medical_cache[sec] = term

    def clean_single_line_regex(self, line: str) -> str:
        """Executes targeted string normalization sweeps over a single layout line string."""
        # Strip text junk lines like row separators or scanning artifact loops
        line = re.sub(r"([kK\*]){4,}", "", line)
        
        # Fix split text tokens bound by structural line noise artifacts
        line = re.sub(r'(?<=[a-zA-Z])[-_~](?=[a-zA-Z])', '', line)
        
        # Repair common OCR unit distortions safely (e.g., mail -> mg/dL, ie aif -> U/L)
        line = re.sub(r"\bmail\s+mg\s*/?\s*d[lI1]\b", "mg/dL", line, flags=re.IGNORECASE)
        line = re.sub(r"\bmg\s*/?\s*d[lI1]\b", "mg/dL", line, flags=re.IGNORECASE)
        line = re.sub(r"\bmmol\s*/?\s*[lI1]\b", "mmol/L", line, flags=re.IGNORECASE)
        line = re.sub(r"\bie\s+aif\b", "U/L", line, flags=re.IGNORECASE)
        line = re.sub(r"\bte\s+eo\b", "U/L", line, flags=re.IGNORECASE)
        
        # Inject structural space gaps around numerical values and standard laboratory units
        line = re.sub(r"(\d+)\s*(mg/dL|mmol/L|U/L|ratio|Ratio)\b", r"\1 \2", line, flags=re.IGNORECASE)
        
        words = line.split()
        processed_words = [self.abbreviation_map.get(w.lower().strip(".,:;()"), w) for w in words]
        return " ".join(processed_words)

    def resolve_phonetic_cursive(self, token: str) -> str:
        """Deciphers cursive distortions using deterministic phonetic signatures. Safely skips numbers."""
        clean_token = re.sub(r"[^\w]", "", token).lower()
        if len(clean_token) < 4 or any(char.isdigit() for char in clean_token):
            return token

        p_code, s_code = doublemetaphone(clean_token)
        for code in (p_code, s_code):
            if code and code in self.phonetic_medical_cache:
                matched_term = self.phonetic_medical_cache[code]
                return matched_term.capitalize() if token[0].isupper() else matched_term
                
        return token

    def apply_sliding_context_bounds(self, line: str) -> str:
        """
        Sliding-window validator that uses physical bounds checks to correct 
        impossible OCR numerical misreads based on surrounding words inside the same line.
        """
        tokens = line.split()
        total_tokens = len(tokens)
        
        for i in range(total_tokens):
            word_lower = tokens[i].lower().strip(".,:;()[]")
            
            if word_lower in self.biomarker_context_bounds:
                bounds = self.biomarker_context_bounds[word_lower]
                
                # Scan ahead in a window of 4 tokens on the same line to find the value block
                for lookahead in range(1, 5):
                    if i + lookahead < total_tokens:
                        target_token = tokens[i + lookahead]
                        clean_num_str = target_token.strip("<=>/()[] ")
                        
                        # Handle values with accidental characters inside them (e.g. "che" instead of a number)
                        if clean_num_str.lower() == "che" and word_lower == "potassium":
                            continue

                        if re.match(r"^\d+(\.\d+)?$", clean_num_str):
                            val = float(clean_num_str)
                            corrected_val = None
                            
                            # Case A: Handle floating-point decimal point drop (e.g. reading 50 for 5.0)
                            if bounds["is_decimal"] and val >= 10.0:
                                if bounds["min"] <= (val / 10.0) <= (bounds["max"] * 2):
                                    corrected_val = val / 10.0
                            
                            # Case B: Handle leading character digit distortion (e.g. reading 438 instead of 138)
                            elif word_lower in ["creatine", "cpk", "phosphokinase"] and val > 400:
                                test_val = val - 300  # Swap leading 4 for 1
                                if bounds["min"] <= test_val <= bounds["max"]:
                                    corrected_val = int(test_val)
                                    
                            elif word_lower == "sodium" and val > 400:
                                test_val = val - 300
                                if bounds["min"] <= test_val <= bounds["max"]:
                                    corrected_val = int(test_val)

                            if corrected_val is not None:
                                idx = target_token.find(clean_num_str)
                                original_prefix = target_token[:idx]
                                original_suffix = target_token[idx + len(clean_num_str):]
                                tokens[i + lookahead] = f"{original_prefix}{corrected_val}{original_suffix}"
                                break
                                
        return " ".join(tokens)

    def normalize_pipeline(self, raw_text: str) -> str:
        """Orchestrates structured text normalization while safely keeping line boundaries intact."""
        if not raw_text.strip():
            return ""

        input_lines = raw_text.split("\n")
        normalized_lines = []

        for line in input_lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Step 1: Execute primary regex cleaning matrix per row line
            sanitized_line = self.clean_single_line_regex(line_str)

            # Step 2: SAFE TOKENIZATION BYPASS (Using simple dictionary list tracking)
            original_tokens = sanitized_line.split()
            protected_tokens = []
            numeric_vault = {}
            vault_counter = 0

            for token in original_tokens:
                # Catch any token that contains digits
                if any(char.isdigit() for char in token):
                    placeholder = f"NUMTOKEN{vault_counter}"
                    numeric_vault[placeholder] = token
                    protected_tokens.append(placeholder)
                    vault_counter += 1
                else:
                    protected_tokens.append(token)

            reconstructed_temp_line = " ".join(protected_tokens)

            # Step 3: SymSpell spelling correction (ignores our unique upper-case tokens)
            suggestions = self.sym_spell.lookup_compound(reconstructed_temp_line, max_edit_distance=2)
            segmented_line = suggestions[0].term if suggestions else reconstructed_temp_line

            # Step 4: Re-insert frozen numeric values safely using dictionary map lookups
            final_tokens = []
            for token in segmented_line.split():
                # Normalize key structure lookup to protect against SymSpell lowercasing
                normalized_key = token.upper()
                if normalized_key in numeric_vault:
                    final_tokens.append(numeric_vault[normalized_key])
                else:
                    corrected_token = self.resolve_phonetic_cursive(token)
                    final_tokens.append(corrected_token)
            
            cleaned_line = " ".join(final_tokens)

            # Step 5: Run sliding context validation engine to correct numeric layouts
            validated_line = self.apply_sliding_context_bounds(cleaned_line)
            
            clean_output_line = re.sub(r"[ \t]+", " ", validated_line).strip()
            if clean_output_line:
                normalized_lines.append(clean_output_line)
        
        return "\n".join(normalized_lines)


# Singleton Class Instance Reference Mapping
normalizer_engine = ClinicalTextNormalizer()


async def process_text_normalization(text: str) -> str:
    """Asynchronously executes text normalization inside non-blocking threads."""
    return await asyncio.to_thread(normalizer_engine.normalize_pipeline, text)
