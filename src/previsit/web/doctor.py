"""Doctor pages (P-005): sign in as one doctor, see only your own and referred patients, and act on their records.

Every clinical route checks previsit.doctors.can_access for the signed-in doctor and returns 404 otherwise, so other
doctors' patients reveal nothing. Approvals and referrals are recorded under the doctor's email.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from previsit import approval, audit, doctors
from previsit.approval import ApprovalError, Decision
from previsit.config import Settings
from previsit.models import Appointment, Doctor, LabResult, MedicalRecommendation, Referral, StaffAlert, utcnow
from previsit.portal import auth
from previsit.sheet.schema import SECTIONS
from previsit.web.app import get_session, get_settings_dep, staff_user, templates
from previsit.web.charts import sparkline
from previsit.web.summaries import appointment_rows
from previsit.web.views import audit_trail, home_context, load_view

router = APIRouter()
COOKIE = "previsit_doctor"
SIGN_IN = "/doctor/sign-in"


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def current_doctor(request: Request, session: Session = Depends(get_session)) -> Doctor:
    email = auth.session_contact(session, request.cookies.get(COOKIE), role="doctor")
    doctor = session.exec(select(Doctor).where(Doctor.email == email)).first() if email else None
    if doctor is None:
        raise HTTPException(303, headers={"Location": SIGN_IN})
    return doctor


def _check(session: Session, doctor: Doctor, appointment_id: int) -> Appointment:
    appointment = session.get(Appointment, appointment_id)
    if appointment is None or not doctors.can_access(session, doctor.id, appointment.patient_id):
        raise HTTPException(404, "Not found")
    return appointment


def doctor_appointment(
    appointment_id: int, doctor: Doctor = Depends(current_doctor), session: Session = Depends(get_session)
) -> Appointment:
    return _check(session, doctor, appointment_id)


# ----- sign-in ----------------------------------------------------------------------------------------------------

def _sign_in_page(request: Request, session: Session, settings: Settings, doctor_id: int | None = None,
                  code: str | None = None, error: str = "", status_code: int = 200):
    return templates.TemplateResponse(request, "doctor_sign_in.html", {
        "doctors": session.exec(select(Doctor).order_by(Doctor.name)).all(), "doctor_id": doctor_id,
        "demo_code": code if settings.demo_mode else None, "code_step": doctor_id is not None, "error": error,
        "demo_mode": settings.demo_mode,
    }, status_code=status_code)


@router.get(SIGN_IN, response_class=HTMLResponse)
def sign_in_page(request: Request, session: Session = Depends(get_session),
                 settings: Settings = Depends(get_settings_dep)):
    return _sign_in_page(request, session, settings)


@router.post("/doctor/code", response_class=HTMLResponse)
def request_code(request: Request, doctor_id: int = Form(...), session: Session = Depends(get_session),
                 settings: Settings = Depends(get_settings_dep)):
    doctor = session.get(Doctor, doctor_id)
    if doctor is None:
        return _sign_in_page(request, session, settings, error="Please choose your name.", status_code=422)
    ip = request.client.host if request.client else ""
    try:
        issued = auth.request_code(session, request.app.state.portal_key, doctor.email, ip, role="doctor")
    except auth.SignInError as exc:
        session.commit()
        return _sign_in_page(request, session, settings, error=str(exc), status_code=429)
    auth.deliver_code(doctor.email, issued.code)
    session.commit()
    return _sign_in_page(request, session, settings, doctor_id=doctor.id, code=issued.code)


@router.post("/doctor/verify", response_class=HTMLResponse)
def verify_code(request: Request, doctor_id: int = Form(...), code: str = Form(...),
                session: Session = Depends(get_session), settings: Settings = Depends(get_settings_dep)):
    doctor = session.get(Doctor, doctor_id)
    if doctor is None:
        return _sign_in_page(request, session, settings, error="Please choose your name.", status_code=422)
    try:
        auth.verify_code(session, request.app.state.portal_key, doctor.email, code, role="doctor")
    except auth.SignInError as exc:
        session.commit()
        return _sign_in_page(request, session, settings, doctor_id=doctor.id, error=str(exc), status_code=422)
    token = auth.start_session(session, doctor.email, settings.portal_session_hours, role="doctor")
    session.commit()
    response = _redirect("/doctor")
    response.set_cookie(COOKIE, token, max_age=settings.portal_session_hours * 3600, httponly=True, samesite="lax",
                        secure=settings.base_url.startswith("https://"), path="/")
    return response


@router.post("/doctor/sign-out")
def sign_out(request: Request, session: Session = Depends(get_session)):
    auth.end_session(session, request.cookies.get(COOKIE))
    session.commit()
    response = _redirect(SIGN_IN)
    response.delete_cookie(COOKIE, path="/")
    return response


# ----- my patients ------------------------------------------------------------------------------------------------

@router.get("/doctor", response_class=HTMLResponse)
def my_patients(request: Request, doctor: Doctor = Depends(current_doctor), session: Session = Depends(get_session)):
    own, referred = doctors.patient_ids_for(session, doctor.id)
    rows = appointment_rows(session, own | referred)
    referrals = {r.patient_id: r for r in session.exec(select(Referral).where(Referral.to_doctor_id == doctor.id)).all()}
    names = {d.id: d.name for d in session.exec(select(Doctor)).all()}
    return templates.TemplateResponse(request, "doctor_home.html", {
        "doctor": doctor, "mine": [r for r in rows if r["patient"].id in own],
        "referred": [r for r in rows if r["patient"].id in referred], "referrals": referrals, "names": names,
    })


# ----- one patient's records --------------------------------------------------------------------------------------

def _patient_page_context(session: Session, doctor: Doctor, appointment: Appointment) -> dict:
    view = load_view(session, appointment)
    temps = [log for log in view.logs if log.metric == "temperature_c"]
    others = session.exec(select(Appointment).where(
        Appointment.patient_id == appointment.patient_id, Appointment.id != appointment.id)
        .order_by(Appointment.scheduled_at)).all()
    referrals = session.exec(select(Referral).where(Referral.patient_id == appointment.patient_id)
                             .order_by(Referral.created_at)).all()
    all_doctors = session.exec(select(Doctor).order_by(Doctor.name)).all()
    return {
        "v": view, "doctor": doctor, "sections": SECTIONS,
        "chart": sparkline([(log.recorded_at, log.value) for log in temps], threshold=38.0) if len(temps) > 1 else None,
        "audit": audit_trail(session, view.appointment, view.intake),
        "other_appointments": others, "referrals": referrals, "names": {d.id: d.name for d in all_doctors},
        "refer_to": [d for d in all_doctors if d.id != doctor.id],
    }


@router.get("/patients/{appointment_id}", response_class=HTMLResponse)
def patient_detail(request: Request, appointment: Appointment = Depends(doctor_appointment),
                   doctor: Doctor = Depends(current_doctor), session: Session = Depends(get_session)):
    audit.record(session, doctor.email, "patient_record.opened", "appointment", appointment.id)
    context = _patient_page_context(session, doctor, appointment)
    session.commit()
    return templates.TemplateResponse(request, "patient_detail.html", context)


@router.get("/patients/{appointment_id}/print", response_class=HTMLResponse)
def patient_print(request: Request, appointment: Appointment = Depends(doctor_appointment),
                  doctor: Doctor = Depends(current_doctor), session: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "print.html", _patient_page_context(session, doctor, appointment))


@router.get("/patients/{appointment_id}/patient-view", response_class=HTMLResponse)
def patient_view(request: Request, appointment: Appointment = Depends(doctor_appointment),
                 doctor: Doctor = Depends(current_doctor), session: Session = Depends(get_session)):
    """Read-only preview of the patient's portal page. Every form is disabled, and the portal's action routes need
    the patient's own sign-in, so the doctor cannot act as the patient."""
    audit.record(session, doctor.email, "patient_view.opened", "appointment", appointment.id)
    context = {**home_context(session, appointment, readonly=True), "doctor": doctor}
    session.commit()
    return templates.TemplateResponse(request, "patient_home.html", context)


@router.post("/patients/{appointment_id}/refer")
def refer(appointment: Appointment = Depends(doctor_appointment), to_doctor_id: int = Form(...),
          note: str = Form(""), doctor: Doctor = Depends(current_doctor), session: Session = Depends(get_session)):
    try:
        doctors.refer(session, doctor, to_doctor_id, appointment.patient_id, note)
    except doctors.ReferralError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _redirect(f"/patients/{appointment.id}#referrals")


@router.post("/recs/{rec_id}/decide")
def decide_rec(
    rec_id: int, decision: str = Form(...), new_name: str = Form(""), note: str = Form(""),
    patient_instructions: str = Form(""), doctor: Doctor = Depends(current_doctor),
    session: Session = Depends(get_session),
):
    rec = session.get(MedicalRecommendation, rec_id)
    if rec is None:
        raise HTTPException(404, "Not found")
    _check(session, doctor, rec.appointment_id)
    try:
        approval.decide(session, rec_id, doctor.email, Decision(decision), new_name=new_name or None, note=note,
                        patient_instructions=patient_instructions or None)
    except (ApprovalError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _redirect(f"/patients/{rec.appointment_id}#tests")


@router.post("/appointments/{appointment_id}/recs/add")
def add_rec(
    appointment: Appointment = Depends(doctor_appointment), name: str = Form(...), note: str = Form(""),
    patient_instructions: str = Form(""), doctor: Doctor = Depends(current_doctor),
    session: Session = Depends(get_session),
):
    try:
        approval.add_investigation(session, appointment.id, doctor.email, name, note, patient_instructions)
    except ApprovalError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _redirect(f"/patients/{appointment.id}#tests")


@router.post("/appointments/{appointment_id}/notify")
def notify(appointment: Appointment = Depends(doctor_appointment), doctor: Doctor = Depends(current_doctor),
           session: Session = Depends(get_session)):
    try:
        approval.notify_patient_of_approved(session, appointment.id, doctor.email)
    except ApprovalError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _redirect(f"/patients/{appointment.id}#tests")


def _optional_doctor(request: Request, session: Session = Depends(get_session)) -> Doctor | None:
    email = auth.session_contact(session, request.cookies.get(COOKIE), role="doctor")
    return session.exec(select(Doctor).where(Doctor.email == email)).first() if email else None


@router.post("/alerts/{alert_id}/ack")
def acknowledge_alert(request: Request, alert_id: int, next: str = Form("/doctor"),
                      doctor: Doctor | None = Depends(_optional_doctor), session: Session = Depends(get_session)):
    """The patient's doctor acknowledges any alert; hospital staff (staff login) may acknowledge emergencies for any
    patient, so an emergency is handled even when the doctor is offline (ROADMAP H.5)."""
    alert = session.get(StaffAlert, alert_id)
    staff = staff_user(request)
    if doctor is not None and alert is not None and doctors.can_access(session, doctor.id, _patient_of(session, alert)):
        actor = doctor.email
    elif staff is not None and alert is not None and alert.severity == "emergency":
        actor = f"staff:{staff}"
    elif doctor is None and staff is None:
        raise HTTPException(303, headers={"Location": SIGN_IN})
    else:
        raise HTTPException(404, "Not found")
    alert.acknowledged_by = actor
    alert.acknowledged_at = utcnow()
    session.add(alert)
    audit.record(session, actor, "staff_alert.acknowledged", "appointment", alert.appointment_id, {"alert_id": alert.id})
    session.commit()
    return _redirect(next if next.startswith("/") and not next.startswith("//") else "/doctor")


def _patient_of(session: Session, alert: StaffAlert) -> int:
    return session.get(Appointment, alert.appointment_id).patient_id


@router.get("/results/{result_id}")
def download_result(result_id: int, doctor: Doctor = Depends(current_doctor), session: Session = Depends(get_session),
                    settings: Settings = Depends(get_settings_dep)):
    result = session.get(LabResult, result_id)
    if result is None:
        raise HTTPException(404, "Not found")
    _check(session, doctor, result.appointment_id)
    path = Path(result.stored_path).resolve()
    if settings.upload_dir.resolve() not in path.parents or not path.is_file():
        raise HTTPException(404, "File missing")
    audit.record(session, doctor.email, "lab_result.viewed", "appointment", result.appointment_id,
                 {"result_id": result.id})
    session.commit()
    return FileResponse(path, media_type=result.content_type, filename=result.filename, content_disposition_type="inline")
