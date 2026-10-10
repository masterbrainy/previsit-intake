"""Patient self-service in the portal (P-004, P-005): set up a person's details and book a visit. Plain pages, no AI.

The contact is already verified by the sign-in code. Name, date of birth and sex are self-declared, so such patients
are marked self_registered and the doctor sees that. Booking is two steps: the patient says what the visit is about,
the system recommends doctors (previsit.doctors.recommend_doctors, rule-based), and the patient picks one and a time.
Bookings are live immediately (booked_by="patient").
"""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, func, select

from previsit import audit
from previsit.config import Settings
from previsit.doctors import SUICIDE_RISK_WORDS, recommend_doctors, urgent_words_in
from previsit.safety.escalation import booking_emergency_message
from previsit.models import Appointment, Doctor, Patient
from previsit.portal import auth
from previsit.web.app import get_session, get_settings_dep, templates
from previsit.web.portal import PortalUser, portal_user
from previsit.web.views import book_appointment, find_or_create_patient, portal_base

router = APIRouter(prefix="/portal")
MAX_AGE_YEARS = 120
BOOKING_HORIZON = timedelta(days=365)
MAX_UPCOMING_PER_PATIENT = 5


def _age(dob: date, today: date) -> int:
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


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


def _people(session: Session, user: PortalUser) -> list[Patient]:
    return sorted(auth.patients_for(session, user.contact), key=lambda p: p.name)


def _step_one(request: Request, session: Session, user: PortalUser, error: str = "", values: dict | None = None,
              status_code: int = 200):
    return templates.TemplateResponse(request, "portal_book.html", {
        "people": _people(session, user), "error": error, "values": values or {},
    }, status_code=status_code)


def _owned_patient(session: Session, user: PortalUser, patient_id: int) -> Patient:
    patient = session.get(Patient, patient_id) if patient_id in user.patient_ids else None
    if patient is None:
        raise ValueError("Please choose who the appointment is for.")
    return patient


def _step_two(request: Request, session: Session, patient: Patient, reason: str, error: str = "",
              values: dict | None = None, status_code: int = 200):
    recommended = recommend_doctors(session, reason, _age(patient.dob, date.today()))
    urgent = urgent_words_in(reason)
    picked = {r.doctor.id for r in recommended}
    others = [d for d in session.exec(select(Doctor).order_by(Doctor.name)).all() if d.id not in picked]
    return templates.TemplateResponse(request, "portal_book_doctor.html", {
        "patient": patient, "reason": reason, "recommended": recommended, "others": others,
        "urgent": urgent, "emergency_script": booking_emergency_message(
            request.app.state.settings, suicide_risk=bool(SUICIDE_RISK_WORDS & set(urgent))),
        "error": error, "values": values or {},
    }, status_code=status_code)


@router.get("/book", response_class=HTMLResponse)
def book_form(
    request: Request, patient_id: int | None = None, user: PortalUser = Depends(portal_user),
    session: Session = Depends(get_session),
):
    if not user.patient_ids:
        return RedirectResponse("/portal/people/new", status_code=303)
    return _step_one(request, session, user, values={"patient_id": patient_id})


@router.post("/book/doctors", response_class=HTMLResponse)
def choose_doctor(
    request: Request, patient_id: int = Form(...), reason: str = Form(""), user: PortalUser = Depends(portal_user),
    session: Session = Depends(get_session),
):
    reason = " ".join(reason.split())[:300]
    values = {"patient_id": patient_id, "reason": reason}
    try:
        patient = _owned_patient(session, user, patient_id)
    except ValueError as exc:
        return _step_one(request, session, user, str(exc), values, status_code=422)
    if len(reason) < 3:
        return _step_one(request, session, user, "Please say briefly what the visit is about.", values, 422)
    return _step_two(request, session, patient, reason)


def _check_booking(session: Session, user: PortalUser, patient_id: int, doctor_id: int, when: str,
                   now: datetime) -> tuple[Patient, Doctor, datetime]:
    patient = _owned_patient(session, user, patient_id)
    doctor = session.get(Doctor, doctor_id)
    if doctor is None:
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
    return patient, doctor, scheduled


@router.post("/book", response_class=HTMLResponse)
def book(
    request: Request, patient_id: int = Form(...), doctor_id: int = Form(0), scheduled_at: str = Form(""),
    reason: str = Form(""), urgent_ack: str = Form(""), user: PortalUser = Depends(portal_user),
    session: Session = Depends(get_session), settings: Settings = Depends(get_settings_dep),
):
    reason = " ".join(reason.split())[:300]
    values = {"doctor_id": doctor_id, "scheduled_at": scheduled_at}
    urgent = urgent_words_in(reason)
    try:
        if urgent and urgent_ack != "yes":
            raise ValueError("Please confirm you have read the emergency advice before booking.")
        patient, doctor, when = _check_booking(session, user, patient_id, doctor_id, scheduled_at, datetime.now())
    except ValueError as exc:
        if patient_id not in user.patient_ids:
            return _step_one(request, session, user, str(exc), {"reason": reason}, status_code=422)
        return _step_two(request, session, session.get(Patient, patient_id), reason, str(exc), values, 422)
    appointment = book_appointment(session, settings, "patient", patient, doctor, when, reason, booked_by="patient")
    if urgent:
        audit.record(session, "patient", "booking.emergency_advice_acknowledged", "appointment", appointment.id,
                     {"words": urgent})
    session.commit()
    return RedirectResponse(portal_base(appointment), status_code=303)
