import os
import re
import asyncio
from typing import Set, Tuple
from datetime import datetime, timezone
from pathlib import Path
from fastapi import UploadFile


BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
UPLOAD_DIR = BASE_DIR / "data" / "uploads"

ALLOWED_EXTENSIONS: Set[str] = {"png", "jpg", "jpeg", "pdf", "doc", "docx"}
ALLOWED_MIME_TYPES: Set[str] = {
    "image/png",
    "image/jpeg",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
}


def validate_file(filename: str | None, content_type: str | None) -> None:
    """Validates file extension and mime type to prevent malicious uploads."""
    if not filename or "." not in filename:
        raise ValueError("A valid filename with an extension is required.")
        
    ext = filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported extension '.{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
        
    if not content_type or content_type.lower() not in ALLOWED_MIME_TYPES:
        raise ValueError(f"Unsupported MIME type '{content_type}'.")


def _save_file_chunks_sync(upload_file: UploadFile, target_path: Path) -> int:
    """Synchronously writes file streams in chunks inside a separate worker thread."""
    total_bytes = 0
    upload_file.file.seek(0)
    with open(target_path, "wb") as buffer:
        while True:
            chunk = upload_file.file.read(1024 * 1024)  # 1MB chunk
            if not chunk:
                break
            buffer.write(chunk)
            total_bytes += len(chunk)
    return total_bytes


async def save_uploaded_file(upload_file: UploadFile, patient_id: str) -> Tuple[str, int, str]:
    """Saves the clinical file securely inside an isolated tenant directory partition."""
    patient_dir = UPLOAD_DIR / f"patient_{patient_id}"
    patient_dir.mkdir(parents=True, exist_ok=True)
    
    safe_name = os.path.basename(upload_file.filename or "unnamed_file")
    stem = Path(safe_name).stem
    suffix = Path(safe_name).suffix
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    new_filename = f"{stem}-{timestamp}{suffix}"
    target_path = patient_dir / new_filename
    
    # Offload blocking disk writing safely to the async engine thread worker pool
    total_bytes = await asyncio.to_thread(_save_file_chunks_sync, upload_file, target_path)
    relative_path = target_path.relative_to(BASE_DIR).as_posix()
    
    return relative_path, total_bytes, new_filename


async def validate_and_save_file(file: UploadFile, patient_id: str) -> Tuple[str, int, str]:
    """Orchestrates sequential validation and asynchronous storage in one execution track."""
    validate_file(file.filename, file.content_type)
    return await save_uploaded_file(file, patient_id)
