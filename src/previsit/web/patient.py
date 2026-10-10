"""Patient portal appointment pages (signed-in patients only). Patients only ever see what previsit.outbox wrote for them."""

import base64
import logging

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlmodel import Session

from previsit import symptoms
from previsit.config import Settings
from previsit.intake.engine import AgentReply, IntakeEngine
from previsit.llm import LLMClient
from previsit.models import Appointment
from previsit.symptoms import SymptomLogError
from previsit.voice import VoiceError, synthesize, transcribe
from previsit.web.app import get_llm, get_session, get_settings_dep, templates
from previsit.web.portal import owned_appointment
from previsit.web.views import home_context, load_view, portal_base

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portal/appointments/{appointment_id}")
NOTICES = {"logged": "Thank you, your reading has been saved for your doctor.",
           "uploaded": "Thank you, your report has been sent to your doctor."}
MAX_AUDIO_BYTES = 10 * 1024 * 1024


@router.get("", response_class=HTMLResponse)
def patient_home(
    request: Request, notice: str = "", appointment: Appointment = Depends(owned_appointment),
    session: Session = Depends(get_session),
):
    return templates.TemplateResponse(
        request, "patient_home.html", home_context(session, appointment, NOTICES.get(notice, ""))
    )


@router.get("/intake", response_class=HTMLResponse)
def intake_page(request: Request, appointment: Appointment = Depends(owned_appointment),
                session: Session = Depends(get_session)):
    view = load_view(session, appointment)
    return templates.TemplateResponse(request, "intake.html", {"v": view, "base": portal_base(appointment)})


def _reply_json(settings: Settings, reply: AgentReply, patient_text: str, speak: bool) -> JSONResponse:
    audio = None
    if speak and reply.text:
        try:
            audio = base64.b64encode(synthesize(settings, reply.text)).decode()
        except VoiceError:
            audio = None
    return JSONResponse({"patient_text": patient_text, "agent_text": reply.text, "state": reply.state.value,
                         "ended": reply.ended, "audio": audio})


@router.post("/intake/start")
def intake_start(
    speak: bool = Form(False), appointment: Appointment = Depends(owned_appointment),
    session: Session = Depends(get_session), settings: Settings = Depends(get_settings_dep),
    llm: LLMClient = Depends(get_llm),
):
    view = load_view(session, appointment)
    reply = IntakeEngine(llm, settings).start(session, view.intake)
    session.commit()
    return _reply_json(settings, reply, "", speak)


@router.post("/intake/turn")
async def intake_turn(
    text: str = Form(""), speak: bool = Form(False), audio: UploadFile | None = File(None),
    appointment: Appointment = Depends(owned_appointment), session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep), llm: LLMClient = Depends(get_llm),
):
    view = load_view(session, appointment)
    patient_text = text.strip()
    if audio is not None and not patient_text:
        content = await audio.read(MAX_AUDIO_BYTES + 1)
        if len(content) > MAX_AUDIO_BYTES:
            return JSONResponse({"error": "That recording is too long. Please try a shorter answer."}, status_code=413)
        try:
            patient_text = transcribe(settings, content, audio.content_type or "audio/webm")
        except VoiceError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
    if not patient_text:
        return JSONResponse({"error": "I didn't catch that. Please try again or type your answer."}, status_code=422)
    reply = IntakeEngine(llm, settings).handle_patient_turn(session, view.intake, patient_text)
    session.commit()
    return _reply_json(settings, reply, patient_text, speak)


@router.post("/symptoms", response_class=HTMLResponse)
def log_symptom_route(
    request: Request, metric: str = Form(...), value: float = Form(...), unit: str = Form("°C"), note: str = Form(""),
    appointment: Appointment = Depends(owned_appointment), session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep), llm: LLMClient = Depends(get_llm),
):
    try:
        outcome = symptoms.log_symptom(session, llm, appointment, metric, value, note, settings, unit=unit)
        session.commit()
    except SymptomLogError as exc:
        return templates.TemplateResponse(
            request, "patient_home.html", home_context(session, appointment, error=str(exc)), status_code=422
        )
    if outcome.escalated:
        return templates.TemplateResponse(request, "patient_home.html", home_context(session, appointment))
    if outcome.flagged:
        return templates.TemplateResponse(
            request, "patient_home.html", home_context(session, appointment, warning=outcome.message)
        )
    return RedirectResponse(f"{portal_base(appointment)}?notice=logged", status_code=303)
