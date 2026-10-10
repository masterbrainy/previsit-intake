"""Physician dashboard: appointments, history sheets, test approvals, logs, results, alerts."""

import csv
import io
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from previsit import approval, audit
from previsit.approval import ApprovalError, Decision
from previsit.config import Settings
from previsit.models import Appointment, Intake, LabResult, MedicalRecommendation, Patient, StaffAlert, utcnow
from previsit.sheet.schema import SECTIONS
from previsit.web.app import get_session, get_settings_dep, require_physician, templates
from previsit.web.charts import sparkline
from previsit.portal.contact import ContactError, normalize_contact
from previsit.web.views import appointment_by_id, audit_trail, create_appointment, home_context, load_view

router = APIRouter(dependencies=[Depends(require_physician)])
CSV_COLUMNS = ("name", "dob", "sex", "contact", "physician", "scheduled_at", "reason")
REQUIRED_COLUMNS = {"name", "dob", "physician", "scheduled_at"}
MAX_CSV_BYTES = 1024 * 1024


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)):
    rows = session.exec(
        select(Appointment, Patient, Intake)
        .join(Patient, Patient.id == Appointment.patient_id)
        .join(Intake, Intake.appointment_id == Appointment.id, isouter=True)
        .order_by(Appointment.scheduled_at)
    ).all()
    recs = session.exec(select(MedicalRecommendation)).all()
    alerts = session.exec(select(StaffAlert).where(StaffAlert.acknowledged_at.is_(None)).order_by(StaffAlert.id.desc())).all()
    results = session.exec(select(LabResult.appointment_id)).all()
    by_appt: dict[int, dict[str, int]] = {}
    for rec in recs:
        counts = by_appt.setdefault(rec.appointment_id, {"suggested": 0, "approved": 0, "sent": 0})
        if rec.patient_notified_at:
            counts["sent"] += 1
        elif rec.status.is_approved:
            counts["approved"] += 1
        elif rec.status.value == "suggested":
            counts["suggested"] += 1
    result_counts: dict[int, int] = {}
    for appt_id in results:
        result_counts[appt_id] = result_counts.get(appt_id, 0) + 1
    alert_appts = {a.appointment_id for a in alerts if a.severity == "emergency"}
    items = [
        {"appointment": a, "patient": p, "intake": i, "recs": by_appt.get(a.id, {}), "results": result_counts.get(a.id, 0),
         "emergency": a.id in alert_appts}
        for a, p, i in rows
    ]
    return templates.TemplateResponse(request, "dashboard.html", {"items": items, "alerts": alerts})


@router.get("/appointments/new", response_class=HTMLResponse)
def new_appointment_form(request: Request, settings: Settings = Depends(get_settings_dep)):
    return templates.TemplateResponse(
        request, "appointment_new.html", {"physician": settings.physician_display_name, "errors": [], "created": None}
    )


def _parse_row(row: dict[str, str]) -> dict:
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
        "physician_name": row["physician"][:120], "scheduled_at": scheduled, "reason": (row.get("reason") or "")[:300],
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
        fields = _parse_row(raw)
    except ValueError as exc:
        return templates.TemplateResponse(
            request, "appointment_new.html", {"physician": physician, "errors": [str(exc)], "created": None}, status_code=422
        )
    appointment = create_appointment(session, settings, user, **fields)
    session.commit()
    created = [{"name": fields["name"], "link": f"{settings.base_url.rstrip('/')}/p/{appointment.token}", "id": appointment.id}]
    return templates.TemplateResponse(
        request, "appointment_new.html", {"physician": physician, "errors": [], "created": created}
    )


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
                    fields = _parse_row(row)
                except ValueError as exc:
                    errors.append(f"Row {line}: {exc}")
                    continue
                appointment = create_appointment(session, settings, user, **fields)
                created.append({"name": fields["name"], "id": appointment.id,
                                "link": f"{settings.base_url.rstrip('/')}/p/{appointment.token}"})
    session.commit()
    return templates.TemplateResponse(
        request, "appointment_new.html",
        {"physician": settings.physician_display_name, "errors": errors, "created": created},
        status_code=200 if created or not errors else 422,
    )


def _patient_page_context(session: Session, appointment_id: int) -> dict:
    view = load_view(session, appointment_by_id(session, appointment_id))
    temps = [log for log in view.logs if log.metric == "temperature_c"]
    return {
        "v": view,
        "sections": SECTIONS,
        "chart": sparkline([(log.recorded_at, log.value) for log in temps], threshold=38.0) if len(temps) > 1 else None,
        "audit": audit_trail(session, view.appointment, view.intake),
    }


@router.get("/patients/{appointment_id}", response_class=HTMLResponse)
def patient_detail(request: Request, appointment_id: int, session: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "patient_detail.html", _patient_page_context(session, appointment_id))


@router.get("/patients/{appointment_id}/patient-view", response_class=HTMLResponse)
def patient_view(
    request: Request, appointment_id: int, session: Session = Depends(get_session),
    user: str = Depends(require_physician),
):
    """Read-only preview of the patient's portal page. The physician cannot act as the patient: every form is
    disabled here, and the portal's action routes need the patient's own sign-in."""
    appointment = appointment_by_id(session, appointment_id)
    audit.record(session, user, "patient_view.opened", "appointment", appointment.id)
    context = home_context(session, appointment, readonly=True)
    session.commit()
    return templates.TemplateResponse(request, "patient_home.html", context)


@router.get("/patients/{appointment_id}/print", response_class=HTMLResponse)
def patient_print(request: Request, appointment_id: int, session: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "print.html", _patient_page_context(session, appointment_id))


@router.post("/recs/{rec_id}/decide")
def decide_rec(
    rec_id: int, decision: str = Form(...), new_name: str = Form(""), note: str = Form(""),
    patient_instructions: str = Form(""), session: Session = Depends(get_session),
    user: str = Depends(require_physician),
):
    rec = session.get(MedicalRecommendation, rec_id)
    if rec is None:
        raise HTTPException(404, "Recommendation not found")
    try:
        approval.decide(session, rec_id, user, Decision(decision), new_name=new_name or None, note=note,
                        patient_instructions=patient_instructions or None)
    except (ApprovalError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _redirect(f"/patients/{rec.appointment_id}#tests")


@router.post("/appointments/{appointment_id}/recs/add")
def add_rec(
    appointment_id: int, name: str = Form(...), note: str = Form(""), patient_instructions: str = Form(""),
    session: Session = Depends(get_session), user: str = Depends(require_physician),
):
    try:
        approval.add_investigation(session, appointment_id, user, name, note, patient_instructions)
    except ApprovalError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _redirect(f"/patients/{appointment_id}#tests")


@router.post("/appointments/{appointment_id}/notify")
def notify(appointment_id: int, session: Session = Depends(get_session), user: str = Depends(require_physician)):
    try:
        approval.notify_patient_of_approved(session, appointment_id, user)
    except ApprovalError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _redirect(f"/patients/{appointment_id}#tests")


@router.post("/alerts/{alert_id}/ack")
def acknowledge_alert(
    alert_id: int, next: str = Form("/dashboard"), session: Session = Depends(get_session),
    user: str = Depends(require_physician),
):
    alert = session.get(StaffAlert, alert_id)
    if alert is None:
        raise HTTPException(404, "Alert not found")
    alert.acknowledged_by = user
    alert.acknowledged_at = utcnow()
    session.add(alert)
    audit.record(session, user, "staff_alert.acknowledged", "appointment", alert.appointment_id, {"alert_id": alert.id})
    session.commit()
    return _redirect(next if next.startswith("/") and not next.startswith("//") else "/dashboard")


@router.get("/results/{result_id}")
def download_result(
    result_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_settings_dep),
    user: str = Depends(require_physician),
):
    result = session.get(LabResult, result_id)
    if result is None:
        raise HTTPException(404, "Result not found")
    path = Path(result.stored_path).resolve()
    if settings.upload_dir.resolve() not in path.parents or not path.is_file():
        raise HTTPException(404, "File missing")
    audit.record(session, user, "lab_result.viewed", "appointment", result.appointment_id, {"result_id": result.id})
    session.commit()
    return FileResponse(path, media_type=result.content_type, filename=result.filename, content_disposition_type="inline")
