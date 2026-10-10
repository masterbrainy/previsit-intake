"""Lab result upload route. Kept apart from the patient router so nothing here can reach the LLM (hard rule)."""

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from previsit.config import Settings
from previsit.models import Appointment
from previsit.results import ResultUploadError, store_result
from previsit.web.app import get_session, get_settings_dep, templates
from previsit.web.portal import owned_appointment
from previsit.web.views import home_context, portal_base

router = APIRouter(prefix="/portal/appointments/{appointment_id}")


@router.post("/results", response_class=HTMLResponse)
async def upload_result(
    request: Request, file: UploadFile, appointment: Appointment = Depends(owned_appointment),
    session: Session = Depends(get_session), settings: Settings = Depends(get_settings_dep),
):
    content = await file.read(settings.max_upload_bytes + 1)
    try:
        store_result(
            session, appointment, file.filename or "result", content, "patient",
            content_type=file.content_type or None, upload_dir=settings.upload_dir, max_bytes=settings.max_upload_bytes,
        )
        session.commit()
    except ResultUploadError as exc:
        return templates.TemplateResponse(
            request, "patient_home.html", home_context(session, appointment, error=str(exc)), status_code=422
        )
    return RedirectResponse(f"{portal_base(appointment)}?notice=uploaded", status_code=303)
