"""Hospital staff pages (shared staff login): the hospital overview and booking appointments for patients.

Nothing clinical is shown here. Patient records are only on doctor pages (previsit.web.doctor), for the patient's own
or referring doctors (P-005).
"""

import csv
import io
from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select

from previsit.config import Settings
from previsit.models import Doctor
from previsit.portal.contact import ContactError, normalize_contact
from previsit.web.app import get_session, get_settings_dep, require_physician, templates
from previsit.web.summaries import appointment_rows
from previsit.web.views import create_appointment

router = APIRouter(dependencies=[Depends(require_physician)])
CSV_COLUMNS = ("name", "dob", "sex", "contact", "physician", "scheduled_at", "reason")
REQUIRED_COLUMNS = {"name", "dob", "physician", "scheduled_at"}
MAX_CSV_BYTES = 1024 * 1024


@router.get("/dashboard", response_class=HTMLResponse)
def hospital_overview(request: Request, session: Session = Depends(get_session)):
    doctors = session.exec(select(Doctor).order_by(Doctor.name)).all()
    items = appointment_rows(session)
    # Emergency alerts for every patient, so staff can act when the doctor is offline (ROADMAP H.5).
    emergencies = [(row, alert) for row in items for alert in row["alerts"] if alert.severity == "emergency"]
    return templates.TemplateResponse(
        request, "dashboard.html", {"items": items, "doctors": doctors, "emergencies": emergencies}
    )



def _form(request: Request, session: Session, errors: list[str], created: list | None, status_code: int = 200):
    doctors = session.exec(select(Doctor).order_by(Doctor.name)).all()
    return templates.TemplateResponse(
        request, "appointment_new.html", {"doctors": doctors, "errors": errors, "created": created},
        status_code=status_code,
    )


@router.get("/appointments/new", response_class=HTMLResponse)
def new_appointment_form(request: Request, session: Session = Depends(get_session)):
    return _form(request, session, [], None)


def _doctor_named(session: Session, value: str) -> Doctor:
    """CSV/form value: a doctor's id, name or email."""
    value = value.strip()
    doctor = session.get(Doctor, int(value)) if value.isdigit() else session.exec(
        select(Doctor).where((Doctor.name == value) | (Doctor.email == value.lower()))).first()
    if doctor is None:
        raise ValueError(f"no doctor called {value!r}")
    return doctor


def _parse_row(session: Session, row: dict[str, str]) -> dict:
    # "phone" is the column name used before P-002; either works.
    raw_contact = (row.get("contact") or row.get("phone") or "").strip()
    missing = [c for c in ("name", "dob", "physician", "scheduled_at") if not (row.get(c) or "").strip()]
    missing += [] if raw_contact else ["contact (mobile number or email)"]
    if missing:
        raise ValueError(f"missing {', '.join(missing)}")
    try:
        contact = normalize_contact(raw_contact[:120])
    except ContactError as exc:
        raise ValueError(f"contact: {exc}") from exc
    try:
        dob = date.fromisoformat(row["dob"].strip())
        scheduled = datetime.fromisoformat(row["scheduled_at"].strip()).replace(tzinfo=None)
    except ValueError as exc:
        raise ValueError("dates must be YYYY-MM-DD and YYYY-MM-DDTHH:MM") from exc
    if dob > date.today():
        raise ValueError("date of birth is in the future")
    return {
        "name": row["name"][:120], "dob": dob, "sex": (row.get("sex") or "")[:20], "contact": contact,
        "doctor": _doctor_named(session, row["physician"][:120]), "scheduled_at": scheduled,
        "reason": (row.get("reason") or "")[:300],
    }


@router.post("/appointments/new", response_class=HTMLResponse)
def create_appointment_route(
    request: Request,
    name: str = Form(...), dob: str = Form(...), sex: str = Form(""), contact: str = Form(""),
    physician: str = Form(...), scheduled_at: str = Form(...), reason: str = Form(""),
    session: Session = Depends(get_session), settings: Settings = Depends(get_settings_dep),
    user: str = Depends(require_physician),
):
    raw = {"name": name, "dob": dob, "sex": sex, "contact": contact, "physician": physician,
           "scheduled_at": scheduled_at, "reason": reason}
    try:
        fields = _parse_row(session, raw)
    except ValueError as exc:
        return _form(request, session, [str(exc)], None, status_code=422)
    appointment = create_appointment(session, settings, user, **fields)
    session.commit()
    created = [{"name": fields["name"], "link": f"{settings.base_url.rstrip('/')}/p/{appointment.token}"}]
    return _form(request, session, [], created)


@router.post("/appointments/import", response_class=HTMLResponse)
async def import_csv(
    request: Request, file: UploadFile, session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep), user: str = Depends(require_physician),
):
    content = await file.read(MAX_CSV_BYTES + 1)
    errors: list[str] = []
    created = []
    if len(content) > MAX_CSV_BYTES:
        errors.append("CSV is larger than 1 MB.")
    else:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig", errors="replace")))
        columns = set(reader.fieldnames or ())
        if not REQUIRED_COLUMNS <= columns or not columns & {"contact", "phone"}:
            errors.append(f"CSV header must include: {', '.join(CSV_COLUMNS)}")
        else:
            for line, row in enumerate(reader, start=2):
                try:
                    fields = _parse_row(session, row)
                except ValueError as exc:
                    errors.append(f"Row {line}: {exc}")
                    continue
                appointment = create_appointment(session, settings, user, **fields)
                created.append({"name": fields["name"], "link": f"{settings.base_url.rstrip('/')}/p/{appointment.token}"})
    session.commit()
    return _form(request, session, errors, created, status_code=200 if created or not errors else 422)
