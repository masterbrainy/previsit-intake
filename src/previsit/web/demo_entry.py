"""Open demo: one-click entry for judges (Settings.is_open_demo only; the router isn't mounted otherwise).

"Be the patient" books a fresh fictional patient with the demo doctor and signs them in to the portal, so every
visitor has their own patient and nobody walks into someone else's call. "Be the doctor" signs in as that doctor,
who sees every visitor's patient. No codes, no passwords: everyone here is fictional.
"""

import secrets
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, func, select

from previsit.config import Settings
from previsit.models import Appointment, Doctor, Patient, utcnow
from previsit.portal import auth
from previsit.web import doctor as doctor_pages
from previsit.web import portal
from previsit.web.app import get_session, get_settings_dep
from previsit.web.views import create_appointment

router = APIRouter(prefix="/demo")

# Fictional people only. A visitor gets one at random; the portal shows them the name and date of birth to give.
PERSONAS = (
    ("Alex Morgan", date(1988, 3, 14), "F"), ("Sam Rivera", date(1975, 9, 2), "M"),
    ("Jamie Patel", date(1993, 6, 21), "F"), ("Chris Novak", date(1969, 12, 5), "M"),
    ("Taylor Brooks", date(1981, 1, 30), "F"), ("Jordan Ellis", date(1996, 8, 11), "M"),
)
VISIT_REASON = "Feeling unwell"
GUEST_DOMAIN = "guest.example.org"  # reserved for examples: nothing is ever delivered there
NEW_PATIENTS_PER_HOUR_PER_VISITOR = 8
NEW_PATIENTS_PER_DAY = 400
_recent: dict[str, deque[float]] = defaultdict(deque)  # per server process; the daily cap is counted in the database


def is_guest(contact: str) -> bool:
    return contact.endswith("@" + GUEST_DOMAIN)


def _visitor(request: Request) -> str:
    # Behind a proxy or tunnel every request comes from the proxy; the edge passes the visitor's address.
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return request.headers.get("cf-connecting-ip") or forwarded or (request.client.host if request.client else "")


def _allow_new_patient(session: Session, visitor: str, now: float) -> bool:
    """Bounds what one visitor, and everyone together, can spend on the AI through new demo patients."""
    mine = _recent[visitor]
    while mine and now - mine[0] > 3600:
        mine.popleft()
    if len(mine) >= NEW_PATIENTS_PER_HOUR_PER_VISITOR or _guests_today(session) >= NEW_PATIENTS_PER_DAY:
        return False
    mine.append(now)
    return True


def _guests_today(session: Session) -> int:
    return session.exec(
        select(func.count()).select_from(Appointment).join(Patient, Patient.id == Appointment.patient_id)
        .where(Patient.email.like(f"%@{GUEST_DOMAIN}"), Appointment.created_at > utcnow() - timedelta(days=1))
    ).one()


def demo_doctor(session: Session, settings: Settings) -> Doctor:
    named = session.exec(select(Doctor).where(Doctor.name == settings.physician_display_name)).first()
    doctor = named or session.exec(select(Doctor).order_by(Doctor.id)).first()
    if doctor is None:
        raise HTTPException(503, "The demo has no doctors yet. Please try again in a minute.")
    return doctor


def _signed_in(response: RedirectResponse, cookie: str, token: str, settings: Settings) -> RedirectResponse:
    response.set_cookie(cookie, token, max_age=settings.portal_session_hours * 3600, httponly=True, samesite="lax",
                        secure=settings.base_url.startswith("https://"), path="/")
    return response


@router.post("/patient")
def be_the_patient(request: Request, fresh: bool = Form(False), session: Session = Depends(get_session),
                   settings: Settings = Depends(get_settings_dep)) -> RedirectResponse:
    """Back to your own patient if you already have one; otherwise (or with `fresh`) a new one, booked tomorrow."""
    current = auth.session_contact(session, request.cookies.get(portal.COOKIE))
    if current and is_guest(current) and not fresh:
        return RedirectResponse("/portal", status_code=303)
    if not _allow_new_patient(session, _visitor(request), time.monotonic()):
        raise HTTPException(429, "That's a lot of new demo patients. Please carry on with the one you have, "
                                 "or try again later.")
    name, dob, sex = secrets.choice(PERSONAS)
    contact = f"visitor-{secrets.token_hex(5)}@{GUEST_DOMAIN}"
    when = (datetime.now() + timedelta(days=1)).replace(hour=9 + secrets.randbelow(8), minute=secrets.choice((0, 30)),
                                                        second=0, microsecond=0)
    create_appointment(session, settings, "demo-visitor", name, dob, sex, contact, demo_doctor(session, settings),
                       when, VISIT_REASON)
    token = auth.start_session(session, contact, settings.portal_session_hours)
    session.commit()
    return _signed_in(RedirectResponse("/portal", status_code=303), portal.COOKIE, token, settings)


@router.post("/doctor")
def be_the_doctor(session: Session = Depends(get_session),
                  settings: Settings = Depends(get_settings_dep)) -> RedirectResponse:
    doctor = demo_doctor(session, settings)
    token = auth.start_session(session, doctor.email, settings.portal_session_hours, role="doctor")
    session.commit()
    return _signed_in(RedirectResponse("/doctor", status_code=303), doctor_pages.COOKIE, token, settings)
