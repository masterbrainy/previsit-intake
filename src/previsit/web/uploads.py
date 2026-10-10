"""Lab result upload route. Kept apart from the patient router so nothing here can reach the LLM (hard rule)."""

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from previsit.config import Settings
from previsit.results import ResultUploadError, store_result
from previsit.web.app import get_session, get_settings_dep, templates
from previsit.web.views import appointment_by_token, home_context

router = APIRouter(prefix="/p")


@router.post("/{token}/results", response_class=HTMLResponse)
async def upload_result(
    request: Request, token: str, file: UploadFile, session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
):
    appointment = appointment_by_token(session, token)
    content = await file.read(settings.max_upload_bytes + 1)
    try:
        store_result(
            session, appointment, file.filename or "result", content, "patient",
            content_type=file.content_type or None, upload_dir=settings.upload_dir, max_bytes=settings.max_upload_bytes,
        )
        session.commit()
    except ResultUploadError as exc:
        return templates.TemplateResponse(
            request, "patient_home.html", home_context(session, token, error=str(exc)), status_code=422
        )
    return RedirectResponse(f"/p/{token}?notice=uploaded", status_code=303)
