"""Patient portal appointment pages (signed-in patients only). Patients only ever see what previsit.outbox wrote for them."""

import base64
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlmodel import Session

from previsit import symptoms
from previsit.config import Settings
from previsit.intake.engine import AgentReply, IntakeEngine, SheetJob
from previsit.llm import LLMClient
from previsit.models import Appointment
from previsit.symptoms import SymptomLogError
from previsit.voice import VoiceError, transcribe
from previsit.web.app import get_llm, get_session, get_settings_dep, templates
from previsit.web.portal import owned_appointment
from previsit.web.sheet_jobs import run_sheet_job
from previsit.web.speech import SpeechPrefetch
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


def _engine(request: Request, settings: Settings, llm: LLMClient, background: BackgroundTasks,
            speech: SpeechPrefetch | None) -> IntakeEngine:
    """Web engine: slow sheet work runs after the response, and speech is prepared while the guard checks."""
    def defer(job: SheetJob) -> None:
        background.add_task(run_sheet_job, request.app.state.engine, settings, llm, job)

    return IntakeEngine(llm, settings, defer=defer, on_candidate=speech.start if speech else None)


def _reply_json(reply: AgentReply, patient_text: str, speech: SpeechPrefetch | None) -> JSONResponse:
    audio = speech.audio_for(reply.text) if speech else None
    return JSONResponse({
        "patient_text": patient_text, "agent_text": reply.text, "state": reply.state.value, "ended": reply.ended,
        "follow_up": reply.follow_up, "audio": base64.b64encode(audio).decode() if audio else None,
    })


@router.post("/intake/start")
def intake_start(
    request: Request, background: BackgroundTasks, speak: bool = Form(False),
    appointment: Appointment = Depends(owned_appointment), session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep), llm: LLMClient = Depends(get_llm),
):
    speech = SpeechPrefetch(settings) if speak else None
    reply = _engine(request, settings, llm, background, speech).start(session, load_view(session, appointment).intake)
    session.commit()
    return _reply_json(reply, "", speech)


@router.post("/intake/readback")
def intake_readback(
    request: Request, background: BackgroundTasks, speak: bool = Form(False),
    appointment: Appointment = Depends(owned_appointment), session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep), llm: LLMClient = Depends(get_llm),
):
    speech = SpeechPrefetch(settings) if speak else None
    engine = _engine(request, settings, llm, background, speech)
    reply = engine.read_back(session, load_view(session, appointment).intake)
    session.commit()
    return _reply_json(reply, "", speech)


def _patient_turn(
    request: Request, background: BackgroundTasks, appointment: Appointment, session: Session, settings: Settings,
    llm: LLMClient, text: str, audio: tuple[bytes, str] | None, speak: bool,
) -> JSONResponse:
    patient_text = text.strip()
    if audio is not None and not patient_text:
        try:
            patient_text = transcribe(settings, audio[0], audio[1])
        except VoiceError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
    if not patient_text:
        return JSONResponse({"error": "I didn't catch that. Please try again or type your answer."}, status_code=422)
    speech = SpeechPrefetch(settings) if speak else None
    engine = _engine(request, settings, llm, background, speech)
    reply = engine.handle_patient_turn(session, load_view(session, appointment).intake, patient_text)
    session.commit()
    return _reply_json(reply, patient_text, speech)


@router.post("/intake/turn")
async def intake_turn(
    request: Request, background: BackgroundTasks, text: str = Form(""), speak: bool = Form(False),
    audio: UploadFile | None = File(None), appointment: Appointment = Depends(owned_appointment),
    session: Session = Depends(get_session), settings: Settings = Depends(get_settings_dep),
    llm: LLMClient = Depends(get_llm),
):
    recording = None
    if audio is not None and not text.strip():
        content = await audio.read(MAX_AUDIO_BYTES + 1)
        if len(content) > MAX_AUDIO_BYTES:
            return JSONResponse({"error": "That recording is too long. Please try a shorter answer."}, status_code=413)
        recording = (content, audio.content_type or "audio/webm")
    # The model calls are blocking; run them off the event loop so other requests are not held up (F.1).
    return await run_in_threadpool(
        _patient_turn, request, background, appointment, session, settings, llm, text, recording, speak
    )


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
