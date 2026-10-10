"""Read-side helpers that gather everything a page needs for one appointment."""

import secrets
from dataclasses import dataclass, field
from datetime import date, datetime

from fastapi import HTTPException
from sqlmodel import Session, select

from previsit import audit, outbox
from previsit.config import Settings
from previsit.models import (
    IntakeState, Appointment, AuditEvent, Doctor, HistorySheetRecord, Intake, LabResult, MedicalRecommendation, MessageKind, Patient,
    PatientMessage, RedFlagEvent, StaffAlert, SymptomLog, Turn,
)
from previsit.modules import ComplaintModule, modules_for
from previsit.portal.auth import patients_for
from previsit.portal.contact import is_email
from previsit.safety.context import PatientContext
from previsit.safety.red_flags import describe
from previsit.sheet.schema import HistorySheet
from previsit.symptoms import monitoring_specs

PATIENT_VISIBLE = (MessageKind.ESCALATION, MessageKind.MEDICAL, MessageKind.GENERAL_RECS, MessageKind.INFO)


@dataclass
class AppointmentView:
    appointment: Appointment
    patient: Patient
    intake: Intake
    sheet: HistorySheet | None = None
    sheet_record: HistorySheetRecord | None = None
    turns: list[Turn] = field(default_factory=list)
    red_flags: list[RedFlagEvent] = field(default_factory=list)
    recs: list[MedicalRecommendation] = field(default_factory=list)
    messages: list[PatientMessage] = field(default_factory=list)
    logs: list[SymptomLog] = field(default_factory=list)
    results: list[LabResult] = field(default_factory=list)
    alerts: list[StaffAlert] = field(default_factory=list)

    @property
    def ctx(self) -> PatientContext:
        return context_for(self.appointment, self.patient, self.intake)

    @property
    def modules(self) -> list[ComplaintModule]:
        return modules_for(self.intake.module_ids)

    @property
    def rf_labels(self) -> list[str]:
        return [describe(tuple(event.rf_ids)) for event in self.red_flags]

    @property
    def open_alerts(self) -> list[StaffAlert]:
        return [a for a in self.alerts if a.acknowledged_at is None]

    @property
    def unsent_approved(self) -> list[MedicalRecommendation]:
        return [r for r in self.recs if r.status.is_approved and r.patient_notified_at is None]


def context_for(appointment: Appointment, patient: Patient, intake: Intake | None) -> PatientContext:
    return PatientContext(
        name=patient.name, dob=patient.dob, sex=patient.sex, on_date=appointment.scheduled_at.date(),
        informant=intake.informant if intake else "self", physician_name=appointment.physician_name,
    )


def _all(session: Session, model, appointment_id: int, order=None) -> list:
    query = select(model).where(model.appointment_id == appointment_id)
    return list(session.exec(query.order_by(order if order is not None else model.id)).all())


def load_view(session: Session, appointment: Appointment) -> AppointmentView:
    patient = session.get(Patient, appointment.patient_id)
    intake = ensure_intake(session, appointment)
    record = session.exec(
        select(HistorySheetRecord).where(HistorySheetRecord.intake_id == intake.id).order_by(HistorySheetRecord.version.desc())
    ).first()
    turns = list(session.exec(select(Turn).where(Turn.intake_id == intake.id).order_by(Turn.seq)).all())
    return AppointmentView(
        appointment=appointment, patient=patient, intake=intake,
        sheet=HistorySheet.model_validate(record.data) if record else None, sheet_record=record, turns=turns,
        red_flags=_all(session, RedFlagEvent, appointment.id), recs=_all(session, MedicalRecommendation, appointment.id),
        messages=_all(session, PatientMessage, appointment.id), logs=_all(session, SymptomLog, appointment.id, SymptomLog.recorded_at),
        results=_all(session, LabResult, appointment.id), alerts=_all(session, StaffAlert, appointment.id),
    )


def ensure_intake(session: Session, appointment: Appointment) -> Intake:
    intake = session.exec(select(Intake).where(Intake.appointment_id == appointment.id)).first()
    if intake is None:
        intake = Intake(appointment_id=appointment.id)
        session.add(intake)
        session.flush()
    return intake


def appointment_by_token(session: Session, token: str) -> Appointment | None:
    """The text-message link only pre-fills portal sign-in; it never opens records by itself."""
    return session.exec(select(Appointment).where(Appointment.token == token)).first() if token else None


def appointment_by_id(session: Session, appointment_id: int) -> Appointment:
    appointment = session.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(404, "Appointment not found")
    return appointment


def audit_trail(session: Session, appointment: Appointment, intake: Intake) -> list[AuditEvent]:
    query = select(AuditEvent).where(
        ((AuditEvent.entity == "appointment") & (AuditEvent.entity_id == appointment.id))
        | ((AuditEvent.entity == "intake") & (AuditEvent.entity_id == intake.id))
    )
    return list(session.exec(query.order_by(AuditEvent.at)).all())


def find_or_create_patient(session: Session, name: str, dob: date, sex: str, contact: str) -> Patient:
    """Same name, date of birth and contact = same patient, so their portal lists every appointment together."""
    for patient in patients_for(session, contact):
        if patient.dob == dob and patient.name.strip().casefold() == name.strip().casefold():
            return patient
    patient = Patient(name=name.strip(), dob=dob, sex=sex.strip(),
                      email=contact if is_email(contact) else "", phone="" if is_email(contact) else contact)
    session.add(patient)
    session.flush()
    return patient


def create_appointment(
    session: Session, settings: Settings, actor: str, name: str, dob: date, sex: str, contact: str,
    doctor: Doctor, scheduled_at: datetime, reason: str,
) -> Appointment:
    """`contact` must already be normalised (previsit.portal.contact.normalize_contact)."""
    patient = find_or_create_patient(session, name, dob, sex, contact)
    return book_appointment(session, settings, actor, patient, doctor, scheduled_at, reason)


def book_appointment(
    session: Session, settings: Settings, actor: str, patient: Patient, doctor: Doctor, scheduled_at: datetime,
    reason: str, booked_by: str = "clinic",
) -> Appointment:
    appointment = Appointment(
        patient_id=patient.id, doctor_id=doctor.id, physician_name=doctor.name, scheduled_at=scheduled_at,
        reason=reason.strip(), token=secrets.token_urlsafe(32), booked_by=booked_by,
    )
    session.add(appointment)
    session.flush()
    ensure_intake(session, appointment)
    audit.record(session, actor, "appointment.created", "appointment", appointment.id, {"booked_by": booked_by})
    link = f"{settings.base_url.rstrip('/')}/p/{appointment.token}"
    outbox.send_patient_message(
        session, appointment.id, MessageKind.INVITE,
        f"Hello from {settings.clinic_name}. Before your appointment with {appointment.physician_name} on "
        f"{scheduled_at:%A %d %B at %H:%M}, please sign in to your patient portal and answer a few questions "
        f"about your health: {link}",
        actor=actor, meta={"link": link},
    )
    return appointment


def portal_base(appointment: Appointment) -> str:
    return f"/portal/appointments/{appointment.id}"


def home_context(
    session: Session, appointment: Appointment, notice: str = "", error: str = "", warning: str = "",
    readonly: bool = False,
) -> dict:
    """Everything the patient's appointment page shows. `readonly` is the physician's preview: no actions."""
    view = load_view(session, appointment)
    visible = [m for m in reversed(view.messages) if m.kind in PATIENT_VISIBLE]
    return {
        "v": view,
        "base": portal_base(appointment),
        "readonly": readonly,
        "escalations": [m for m in visible if m.kind is MessageKind.ESCALATION],
        # After an escalation, stay-at-home advice no longer applies (FEV-018), so it is withdrawn from the page.
        "messages": [m for m in visible if m.kind is not MessageKind.ESCALATION
                     and not (view.red_flags and m.kind is MessageKind.GENERAL_RECS)],
        "monitoring": list(monitoring_specs(view.modules).values()),
        "can_start": view.intake.state in {IntakeState.NOT_STARTED, IntakeState.CONSENT, IntakeState.IDENTITY,
                                          IntakeState.INTERVIEW, IntakeState.READBACK},
        "notice": notice,
        "error": error,
        "warning": warning,
    }
