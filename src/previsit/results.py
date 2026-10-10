"""Lab result uploads. Stored and shown to the physician exactly as issued.

Hard rule: this module must never import previsit.llm or openai. Results are not read, summarised,
flagged or interpreted by AI.
"""

import re
import uuid
from pathlib import Path

from sqlmodel import Session

from previsit import audit, outbox
from previsit.config import get_settings
from previsit.models import Appointment, LabResult

ALLOWED_TYPES = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}
_MAGIC = {".pdf": b"%PDF", ".png": b"\x89PNG", ".jpg": b"\xff\xd8\xff"}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")
DEFAULT_MAX_BYTES = 10 * 1024 * 1024


class ResultUploadError(ValueError):
    pass


def _safe_filename(name: str) -> str:
    cleaned = _SAFE_NAME.sub("_", Path(name).name).strip() or "result"
    return cleaned[:120]


def _content_type_for(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(suffix, "")


def store_result(
    session: Session,
    appointment: Appointment,
    filename: str,
    content: bytes,
    uploaded_by: str,
    *,
    content_type: str | None = None,
    upload_dir: Path | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> LabResult:
    if appointment is None or appointment.id is None or session.get(Appointment, appointment.id) is None:
        raise ResultUploadError("appointment not found")
    appointment_id = appointment.id
    content_type = content_type or _content_type_for(filename)
    upload_dir = upload_dir or get_settings().upload_dir
    extension = ALLOWED_TYPES.get(content_type)
    if extension is None:
        raise ResultUploadError("Please upload a PDF, PNG or JPEG file.")
    if not content:
        raise ResultUploadError("The file is empty.")
    if len(content) > max_bytes:
        raise ResultUploadError(f"The file is larger than {max_bytes // (1024 * 1024)} MB.")
    if not content.startswith(_MAGIC[extension]):
        raise ResultUploadError("The file doesn't look like the type it claims to be.")

    target_dir = upload_dir / str(appointment_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    stored = target_dir / f"{uuid.uuid4().hex}{extension}"
    stored.write_bytes(content)

    result = LabResult(
        appointment_id=appointment_id,
        filename=_safe_filename(filename),
        stored_path=str(stored),
        content_type=content_type,
        size_bytes=len(content),
        uploaded_by=uploaded_by,
    )
    session.add(result)
    session.flush()
    audit.record(session, uploaded_by, "lab_result.uploaded", "appointment", appointment_id, {"result_id": result.id})
    outbox.send_staff_alert(
        session, appointment_id, "info", "Lab result uploaded", f"{result.filename} uploaded by {uploaded_by}."
    )
    return result
