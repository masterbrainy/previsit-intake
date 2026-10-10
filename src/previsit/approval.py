"""Physician decisions on suggested investigations. The only code that approves anything.

There is no scheduler and no default: a suggestion stays SUGGESTED until a named physician decides.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlmodel import Session, select

from previsit import audit, outbox
from previsit.models import Appointment, MedicalRecommendation, MessageKind, PatientMessage, RecStatus, utcnow


class Decision(StrEnum):
    APPROVE = "approve"
    MODIFY = "modify"
    REJECT = "reject"


class ApprovalError(ValueError):
    pass


def _require_physician(physician: str) -> str:
    name = physician.strip()
    if not name:
        raise ApprovalError("a physician must be named for every decision")
    return name


def decide(
    session: Session,
    rec_id: int,
    physician: str,
    decision: Decision | str,
    new_name: str | None = None,
    note: str = "",
    patient_instructions: str | None = None,
) -> MedicalRecommendation:
    physician = _require_physician(physician)
    try:
        decision = Decision(decision)
    except ValueError as exc:
        raise ApprovalError(f"unknown decision {decision!r}; use approve, modify or reject") from exc
    rec = session.get(MedicalRecommendation, rec_id)
    if rec is None:
        raise ApprovalError(f"recommendation {rec_id} not found")
    if rec.patient_notified_at is not None:
        raise ApprovalError("the patient has already been told about this test; add a new one instead")
    before = {"status": rec.status.value, "name": rec.name}
    if decision is Decision.MODIFY:
        if not new_name or not new_name.strip():
            raise ApprovalError("modify needs the new test name")
        rec.name = new_name.strip()
        rec.status = RecStatus.MODIFIED
    elif decision is Decision.APPROVE:
        rec.status = RecStatus.APPROVED
    elif decision is Decision.REJECT:
        rec.status = RecStatus.REJECTED
    else:  # pragma: no cover - Decision(...) above already rejects anything else
        raise ApprovalError(f"unhandled decision {decision!r}")
    rec.decided_by = physician
    rec.decided_at = utcnow()
    rec.physician_note = note.strip()
    if patient_instructions is not None:
        rec.patient_instructions = patient_instructions.strip()
    session.add(rec)
    session.flush()
    audit.record(
        session, physician, f"recommendation.{decision.value}", "medical_recommendation", rec.id,
        {"before": before, "after": {"status": rec.status.value, "name": rec.name}, "note": rec.physician_note},
    )
    return rec


def add_investigation(
    session: Session, appointment_id: int, physician: str, name: str, note: str = "", patient_instructions: str = ""
) -> MedicalRecommendation:
    physician = _require_physician(physician)
    if not name.strip():
        raise ApprovalError("test name is required")
    if session.get(Appointment, appointment_id) is None:
        raise ApprovalError(f"appointment {appointment_id} not found")
    rec = MedicalRecommendation(
        appointment_id=appointment_id,
        name=name.strip(),
        rationale="Added by physician",
        source="physician_added",
        status=RecStatus.APPROVED,
        decided_by=physician,
        decided_at=utcnow(),
        physician_note=note.strip(),
        patient_instructions=patient_instructions.strip(),
    )
    session.add(rec)
    session.flush()
    audit.record(session, physician, "recommendation.added", "medical_recommendation", rec.id, {"name": rec.name})
    return rec


@dataclass(frozen=True)
class NotifyResult:
    message: PatientMessage | None
    rec_count: int


def _format_time(value: datetime) -> str:
    return value.strftime("%A %d %B at %H:%M")


def notify_patient_of_approved(session: Session, appointment_id: int, physician: str) -> NotifyResult:
    """Tells the patient about every approved test not yet sent. Unapproved tests are never included."""
    physician = _require_physician(physician)
    appointment = session.get(Appointment, appointment_id)
    if appointment is None:
        raise ApprovalError(f"appointment {appointment_id} not found")
    pending = session.exec(
        select(MedicalRecommendation).where(
            MedicalRecommendation.appointment_id == appointment_id,
            MedicalRecommendation.status.in_([RecStatus.APPROVED, RecStatus.MODIFIED]),
            MedicalRecommendation.patient_notified_at.is_(None),
        )
    ).all()
    if not pending:
        return NotifyResult(None, 0)
    lines = [
        f"{appointment.physician_name} has asked you to have the following test(s) done before your appointment on "
        f"{_format_time(appointment.scheduled_at)}:"
    ]
    for rec in pending:
        detail = " ".join(part for part in (rec.patient_instructions, rec.physician_note) if part)
        lines.append(f"- {rec.name}" + (f". {detail}" if detail else ""))
    lines.append(
        "Please go to the lab as early as you can so the results are ready before your appointment, "
        "and upload the report on this page if the lab gives it to you."
    )
    message = outbox.send_patient_message(
        session, appointment_id, MessageKind.MEDICAL, "\n".join(lines), actor=physician,
        rec_ids=[rec.id for rec in pending],
    )
    return NotifyResult(message, len(pending))
