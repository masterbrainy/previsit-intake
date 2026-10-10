"""Patient self-service in the portal (P-004): set up a person's details and book a visit. Plain pages, no AI.

The contact is already verified by the sign-in code. Name, date of birth and sex are self-declared, so such patients
are marked self_registered and the physician sees that. Bookings are live immediately (booked_by="patient").
"""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, func, select

from previsit import audit
from previsit.config import Settings
from previsit.models import Appointment, Patient
from previsit.portal import auth
from previsit.web.app import get_session, get_settings_dep, templates
from previsit.web.portal import PortalUser, portal_user
from previsit.web.views import book_appointment, find_or_create_patient, portal_base

router = APIRouter(prefix="/portal")
MAX_AGE_YEARS = 120
BOOKING_HORIZON = timedelta(days=365)
MAX_UPCOMING_PER_PATIENT = 5


def physicians(session: Session, settings: Settings) -> list[str]:
    booked = session.exec(select(Appointment.physician_name).distinct()).all()
    return sorted({settings.physician_display_name, *[name for name in booked if name]})


def _person_form(request: Request, error: str = "", values: dict | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        request, "portal_person.html", {"error": error, "values": values or {}}, status_code=status_code
    )


@router.get("/people/new", response_class=HTMLResponse)
def new_person_form(request: Request, user: PortalUser = Depends(portal_user)):
    return _person_form(request)


def _parse_person(name: str, dob: str, today: date) -> tuple[str, date]:
    clean = " ".join(name.split())[:120]
    if len(clean.split()) < 2:
        raise ValueError("Please enter a full name (first and last name).")
    try:
        born = date.fromisoformat(dob)
    except ValueError as exc:
        raise ValueError("Please enter a valid date of birth.") from exc
    if born > today or born.year < today.year - MAX_AGE_YEARS:
        raise ValueError("Please check the date of birth.")
    return clean, born


@router.post("/people/new", response_class=HTMLResponse)
def create_person(
    request: Request, name: str = Form(...), dob: str = Form(...), sex: str = Form(""),
    user: PortalUser = Depends(portal_user), session: Session = Depends(get_session),
):
    values = {"name": name[:120], "dob": dob, "sex": sex}
    try:
        clean, born = _parse_person(name, dob, date.today())
    except ValueError as exc:
        return _person_form(request, str(exc), values, status_code=422)
    existing = {p.id for p in auth.patients_for(session, user.contact)}
    patient = find_or_create_patient(session, clean, born, sex if sex in {"F", "M", "Other"} else "", user.contact)
    if patient.id not in existing:
        patient.self_registered = True
        session.add(patient)
        audit.record(session, "patient", "patient.self_registered", "patient", patient.id)
    session.commit()
    return RedirectResponse(f"/portal/book?patient_id={patient.id}", status_code=303)


def _book_form(request: Request, session: Session, settings: Settings, user: PortalUser, error: str = "",
               values: dict | None = None, status_code: int = 200):
    people = sorted(auth.patients_for(session, user.contact), key=lambda p: p.name)
    return templates.TemplateResponse(request, "portal_book.html", {
        "people": people, "physicians": physicians(session, settings), "error": error, "values": values or {},
    }, status_code=status_code)


@router.get("/book", response_class=HTMLResponse)
def book_form(
    request: Request, patient_id: int | None = None, user: PortalUser = Depends(portal_user),
    session: Session = Depends(get_session), settings: Settings = Depends(get_settings_dep),
):
    if not user.patient_ids:
        return RedirectResponse("/portal/people/new", status_code=303)
    return _book_form(request, session, settings, user, values={"patient_id": patient_id})


def _check_booking(session: Session, settings: Settings, user: PortalUser, patient_id: int, physician: str,
                   when: str, now: datetime) -> tuple[Patient, datetime]:
    patient = session.get(Patient, patient_id) if patient_id in user.patient_ids else None
    if patient is None:
        raise ValueError("Please choose who the appointment is for.")
    if physician not in physicians(session, settings):
        raise ValueError("Please choose a doctor from the list.")
    try:
        scheduled = datetime.fromisoformat(when).replace(tzinfo=None, second=0, microsecond=0)
    except ValueError as exc:
        raise ValueError("Please choose a date and time.") from exc
    if not now < scheduled <= now + BOOKING_HORIZON:
        raise ValueError("Please choose a time in the future, within the next year.")
    upcoming = session.exec(select(func.count()).select_from(Appointment).where(
        Appointment.patient_id == patient.id, Appointment.scheduled_at > now)).one()
    if upcoming >= MAX_UPCOMING_PER_PATIENT:
        raise ValueError(f"{patient.name} already has {upcoming} upcoming appointments. Please contact the clinic.")
    return patient, scheduled


@router.post("/book", response_class=HTMLResponse)
def book(
    request: Request, patient_id: int = Form(...), physician: str = Form(...), scheduled_at: str = Form(...),
    reason: str = Form(""), user: PortalUser = Depends(portal_user), session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
):
    values = {"patient_id": patient_id, "physician": physician, "scheduled_at": scheduled_at, "reason": reason[:300]}
    try:
        patient, when = _check_booking(session, settings, user, patient_id, physician, scheduled_at, datetime.now())
    except ValueError as exc:
        return _book_form(request, session, settings, user, str(exc), values, status_code=422)
    appointment = book_appointment(session, settings, "patient", patient, physician, when, reason[:300],
                                   booked_by="patient")
    session.commit()
    return RedirectResponse(portal_base(appointment), status_code=303)
