"""Front page and patient portal sign-in (PRD §8.10). Plain pages: nothing here calls the AI.

A patient signs in with the email or phone on their appointment plus a one-time code, and can then reach only the
appointments of patients booked with that contact. The text-message link only pre-fills the sign-in form.
"""

from dataclasses import dataclass

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from previsit.config import Settings
from previsit.models import Appointment, Intake, IntakeState, Patient
from previsit.portal import auth
from previsit.portal.contact import ContactError, mask_contact, normalize_contact
from previsit.web.app import get_session, get_settings_dep, templates
from previsit.web.views import appointment_by_token

router = APIRouter()
COOKIE = "previsit_portal"
SIGN_IN = "/portal/sign-in"

INTAKE_STATUS = {
    IntakeState.NOT_STARTED: "Pre-visit questions: not started",
    IntakeState.CONSENT: "Pre-visit questions: in progress",
    IntakeState.IDENTITY: "Pre-visit questions: in progress",
    IntakeState.INTERVIEW: "Pre-visit questions: in progress",
    IntakeState.READBACK: "Pre-visit questions: in progress",
    IntakeState.COMPLETE: "Pre-visit questions: done",
    IntakeState.ESCALATED: "Please read the urgent message",
    IntakeState.DECLINED: "Pre-visit questions: not done",
    IntakeState.FAILED: "Pre-visit questions: stopped, the clinic will contact you",
}


@dataclass(frozen=True)
class PortalUser:
    contact: str
    patient_ids: frozenset[int]


def portal_user(request: Request, session: Session = Depends(get_session)) -> PortalUser:
    contact = auth.session_contact(session, request.cookies.get(COOKIE))
    if contact is None:
        if "/intake/" in request.url.path:
            raise HTTPException(401, "Your sign-in has expired. Please sign in again.")
        raise HTTPException(303, headers={"Location": SIGN_IN})
    return PortalUser(contact, frozenset(p.id for p in auth.patients_for(session, contact)))


def owned_appointment(
    appointment_id: int, user: PortalUser = Depends(portal_user), session: Session = Depends(get_session)
) -> Appointment:
    """404 (not 403) for anyone else's appointment, so guessed IDs reveal nothing."""
    appointment = session.get(Appointment, appointment_id)
    if appointment is None or appointment.patient_id not in user.patient_ids:
        raise HTTPException(404, "Not found")
    return appointment


def _key(request: Request) -> bytes:
    return request.app.state.portal_key


def _sign_in_page(request: Request, contact: str = "", error: str = "", status_code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "portal_sign_in.html", {"contact": contact, "error": error}, status_code=status_code
    )


def _code_page(request: Request, settings: Settings, contact: str, code: str | None = None, error: str = "",
               status_code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(request, "portal_code.html", {
        "contact": contact, "masked": mask_contact(contact), "error": error,
        "demo_code": code if settings.demo_mode else None, "demo_mode": settings.demo_mode,
    }, status_code=status_code)


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def front_page(request: Request, settings: Settings = Depends(get_settings_dep)):
    return templates.TemplateResponse(request, "index.html", {"clinic": settings.clinic_name})


@router.get(SIGN_IN, response_class=HTMLResponse)
def sign_in_page(request: Request):
    return _sign_in_page(request)


@router.get("/p/{token}", response_class=HTMLResponse)
def text_message_link(request: Request, token: str, session: Session = Depends(get_session)):
    """The link in the text message: sign-in with the contact pre-filled. The patient still needs the code."""
    appointment = appointment_by_token(session, token)
    patient = session.get(Patient, appointment.patient_id) if appointment else None
    return _sign_in_page(request, contact=(patient.phone or patient.email) if patient else "")


@router.post("/portal/code", response_class=HTMLResponse)
def request_code(
    request: Request, contact: str = Form(...), session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
):
    try:
        normalized = normalize_contact(contact)
    except ContactError as exc:
        return _sign_in_page(request, contact=contact[:120], error=str(exc), status_code=422)
    ip = request.client.host if request.client else ""
    try:
        issued = auth.request_code(session, _key(request), normalized, ip)
    except auth.SignInError as exc:
        session.commit()
        return _sign_in_page(request, contact=normalized, error=str(exc), status_code=429)
    auth.deliver_code(normalized, issued.code)
    session.commit()
    return _code_page(request, settings, normalized, issued.code)


@router.post("/portal/verify", response_class=HTMLResponse)
def verify_code(
    request: Request, contact: str = Form(...), code: str = Form(...), session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
):
    try:
        normalized = normalize_contact(contact)
        auth.verify_code(session, _key(request), normalized, code)
    except ContactError as exc:
        return _sign_in_page(request, error=str(exc), status_code=422)
    except auth.SignInError as exc:
        session.commit()
        return _code_page(request, settings, normalized, error=str(exc), status_code=422)
    token = auth.start_session(session, normalized, settings.portal_session_hours)
    session.commit()
    response = RedirectResponse("/portal", status_code=303)
    response.set_cookie(
        COOKIE, token, max_age=settings.portal_session_hours * 3600, httponly=True, samesite="lax",
        secure=settings.base_url.startswith("https://"), path="/",
    )
    return response


@router.post("/portal/sign-out")
def sign_out(request: Request, session: Session = Depends(get_session)):
    auth.end_session(session, request.cookies.get(COOKIE))
    session.commit()
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(COOKIE, path="/")
    return response


@router.get("/portal", response_class=HTMLResponse)
def portal_home(request: Request, user: PortalUser = Depends(portal_user), session: Session = Depends(get_session)):
    rows = session.exec(
        select(Appointment, Patient, Intake)
        .join(Patient, Patient.id == Appointment.patient_id)
        .join(Intake, Intake.appointment_id == Appointment.id, isouter=True)
        .where(Appointment.patient_id.in_(user.patient_ids))
        .order_by(Appointment.scheduled_at)
    ).all()
    items = [
        {"appointment": a, "patient": p, "state": (i.state if i else IntakeState.NOT_STARTED).value,
         "status": INTAKE_STATUS[i.state if i else IntakeState.NOT_STARTED]}
        for a, p, i in rows
    ]
    people = auth.patients_for(session, user.contact)  # includes people set up but not yet booked
    names = sorted({p.name.split()[0] for p in people})
    return templates.TemplateResponse(
        request, "portal_home.html", {"items": items, "names": names, "has_people": bool(people)}
    )
