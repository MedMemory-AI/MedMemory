# app/services/ingestion/ocr.py
import os
import re
import shutil
import asyncio
from pathlib import Path
from PIL import Image
import fitz  # PyMuPDF

from app.core.logger import logger
from app.core.exception import ClinicalParsingError

try:
    import pytesseract
except ImportError:
    pytesseract = None
    logger.warning("`pytesseract` library is missing in this runtime environment.")


def configure_tesseract() -> None:
    """Dynamically maps the path to the Tesseract binary engine on Windows environments."""
    if pytesseract is None or shutil.which("tesseract"):
        return
        
    possible_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%USERPROFILE%\AppData\Local\Tesseract-OCR\tesseract.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            logger.info(f"Automatically bound PyTesseract binary path target to: {path}")
            return
            
    logger.warning("Tesseract OCR binary not found. Image extractions will fail.")


def rotate_image_upright(img: Image.Image) -> Image.Image:
    """Detects image orientation using Tesseract OSD and rotates it upright if needed."""
    if pytesseract is None:
        return img
    try:
        configure_tesseract()
        osd = pytesseract.image_to_osd(img)
        rotation_match = re.search(r"Rotate:\s*(\d+)", osd)
        if rotation_match:
            angle = int(rotation_match.group(1))
            if angle != 0:
                logger.info(f"Auto-correcting document rotation angle: Rotating {angle} degrees clockwise.")
                return img.rotate(360 - angle, expand=True)
    except Exception as exc:
        logger.warning(f"OSD orientation check skipped: {exc}")
    return img


def extract_layout_aware_words(words_list: list) -> str:
    """
    Sorts extracted word coordinate blocks spatially to build accurate tabular structures.
    Elements in words_list are tuples: (x0, y0, x1, y1, "text", block_no, line_no, word_no)
    """
    if not words_list:
        return ""
    
    # Sort primarily by the Top coordinate (y0) grouped by line thresholds, then by Left (x0)
    # A tolerance factor of 5 pixels handles variations in baseline layout spacing cleanly
    words_list.sort(key=lambda w: (round(w[1] / 5) * 5, w[0]))
    
    lines = []
    current_y = None
    current_line = []
    
    for w in words_list:
        x0, y0, x1, y1, text, b_no, l_no, w_no = w
        approx_y = round(y0 / 5) * 5
        
        if current_y is None or approx_y == current_y:
            current_line.append(text)
        else:
            lines.append(" ".join(current_line))
            current_line = [text]
        current_y = approx_y
        
    if current_line:
        lines.append(" ".join(current_line))
        
    return "\n".join(lines)


def extract_pdf_text_with_fallback(file_path: Path) -> str:
    """Parses PDFs programmatically using spatial layout awareness, with an OCR fallback."""
    doc_text = []
    has_digital_text = False
    
    try:
        logger.info(f"Opening PDF file with PyMuPDF layout parser: {file_path.name}")
        with fitz.open(str(file_path)) as doc:
            # Step 1: Scan for native programmatic coordinate words
            for page in doc:
                words = page.get_text("words")
                if words:
                    has_digital_text = True
                    page_layout_text = extract_layout_aware_words(words)
                    doc_text.append(page_layout_text)
            
            if has_digital_text and len("\n".join(doc_text).strip()) > 50:
                logger.info(f"Extracted layout-sorted digital text layers from PDF: {file_path.name}")
                return "\n\n".join(doc_text)
                
            # Step 2: Fallback to high-resolution page-by-page OCR
            logger.info(f"PDF matches scanned image patterns. Launching OCR fallback framework: {file_path.name}")
            configure_tesseract()
            if pytesseract is None:
                raise ClinicalParsingError("Cannot run Scanned PDF OCR: pytesseract library is uninstalled.")
                
            ocr_text = []
            for page_num, page in enumerate(doc):
                zoom = 2.0  # Scales DPI to 300 for clearer token matching
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                img = rotate_image_upright(img)
                
                logger.info(f"Extracting spatial layout via Tesseract OCR for page {page_num + 1}/{len(doc)}")
                # CRITICAL: Preserve line breaks directly from the image engine layout mapping
                page_text = pytesseract.image_to_string(img)
                if page_text.strip():
                    ocr_text.append(page_text)
                    
            return "\n\n".join(ocr_text)
            
    except Exception as exc:
        logger.error(f"PyMuPDF/Tesseract conversion failed for {file_path.name}: {str(exc)}", exc_info=True)
        raise ClinicalParsingError(f"PDF layout document rendering failed: {str(exc)}")


def extract_text_sync(file_path: Path, mime_type: str) -> str:
    """Synchronously routes documents to their optimized layout parser engines."""
    if not file_path.exists():
        raise ClinicalParsingError(f"Target file path missing from storage disk: {file_path}")
        
    ext = file_path.suffix.lower().lstrip(".")
    
    if mime_type.startswith("image/") or ext in ("png", "jpg", "jpeg"):
        if pytesseract is None:
            raise ClinicalParsingError("Cannot execute Image OCR: pytesseract library is uninstalled.")
            
        configure_tesseract()
        try:
            logger.info(f"Initiating PyTesseract image processing engine for: {file_path.name}")
            with Image.open(file_path) as img:
                img = rotate_image_upright(img)
                raw_text = pytesseract.image_to_string(img)
            return raw_text
        except Exception as exc:
            logger.error(f"PyTesseract extraction crashed for {file_path.name}: {str(exc)}", exc_info=True)
            raise ClinicalParsingError(f"Image matrix OCR conversion failed: {str(exc)}")
            
    elif mime_type == "application/pdf" or ext == "pdf":
        return extract_pdf_text_with_fallback(file_path)
            
    else:
        raise ClinicalParsingError(f"Unsupported file type structure for ingestion: {mime_type}")


def clean_text_sync(text: str) -> str:
    """Cleans raw text data layouts while strictly keeping line breaks (\n) for table structures."""
    if not text:
        return ""
        
    # Remove control character codes except for newlines
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        line_clean = line.strip()
        # Collapse multiple internal spaces or tabs into a single clean gap space
        line_clean = re.sub(r"[ \t]+", " ", line_clean)
        if line_clean:
            cleaned_lines.append(line_clean)
        
    # CRITICAL: Rejoin with true newline boundaries so lab metrics remain on individual rows
    cleaned_text = "\n".join(cleaned_lines)
    return cleaned_text.strip()


async def process_document_ocr(file_path: Path, mime_type: str) -> str:
    """Asynchronously processes OCR and spatial cleanup over worker threads to keep operations non-blocking."""
    raw_text = await asyncio.to_thread(extract_text_sync, file_path, mime_type)
    cleaned_text = await asyncio.to_thread(clean_text_sync, raw_text)
    return cleaned_text
