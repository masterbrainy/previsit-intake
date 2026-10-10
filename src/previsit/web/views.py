"""Read-side helpers that gather everything a page needs for one appointment."""

import secrets
from dataclasses import dataclass, field
from datetime import date, datetime

from fastapi import HTTPException
from sqlmodel import Session, select

from previsit import audit, outbox
from previsit.config import Settings
from previsit.models import (
    IntakeState, Appointment, AuditEvent, HistorySheetRecord, Intake, LabResult, MedicalRecommendation, MessageKind, Patient,
    PatientMessage, RedFlagEvent, StaffAlert, SymptomLog, Turn,
)
from previsit.modules import ComplaintModule, modules_for
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


def appointment_by_token(session: Session, token: str) -> Appointment:
    appointment = session.exec(select(Appointment).where(Appointment.token == token)).first() if token else None
    if appointment is None:
        raise HTTPException(404, "This link is not valid. Please contact your clinic.")
    return appointment


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


def create_appointment(
    session: Session, settings: Settings, actor: str, name: str, dob: date, sex: str, phone: str,
    physician_name: str, scheduled_at: datetime, reason: str,
) -> Appointment:
    patient = Patient(name=name.strip(), dob=dob, sex=sex.strip(), phone=phone.strip())
    session.add(patient)
    session.flush()
    appointment = Appointment(
        patient_id=patient.id, physician_name=physician_name.strip(), scheduled_at=scheduled_at,
        reason=reason.strip(), token=secrets.token_urlsafe(32),
    )
    session.add(appointment)
    session.flush()
    ensure_intake(session, appointment)
    audit.record(session, actor, "appointment.created", "appointment", appointment.id)
    link = f"{settings.base_url.rstrip('/')}/p/{appointment.token}"
    outbox.send_patient_message(
        session, appointment.id, MessageKind.INVITE,
        f"Hello from {settings.clinic_name}. Before your appointment with {appointment.physician_name} on "
        f"{scheduled_at:%A %d %B at %H:%M}, please answer a few questions about your health: {link}",
        actor=actor, meta={"link": link},
    )
    return appointment


def home_context(session: Session, token: str, notice: str = "", error: str = "", warning: str = "") -> dict:
    view = load_view(session, appointment_by_token(session, token))
    visible = [m for m in reversed(view.messages) if m.kind in PATIENT_VISIBLE]
    return {
        "v": view,
        "token": token,
        "escalations": [m for m in visible if m.kind is MessageKind.ESCALATION],
        "messages": [m for m in visible if m.kind is not MessageKind.ESCALATION],
        "monitoring": list(monitoring_specs(view.modules).values()),
        "can_start": view.intake.state in {IntakeState.NOT_STARTED, IntakeState.CONSENT, IntakeState.IDENTITY,
                                          IntakeState.INTERVIEW, IntakeState.READBACK},
        "notice": notice,
        "error": error,
        "warning": warning,
    }
