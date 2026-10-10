"""The only writer of patient-facing messages and staff alerts.

Hard rule: a MEDICAL message can only be sent for recommendations a physician has approved.
"""

import logging
from collections.abc import Sequence
from typing import Any

from sqlmodel import Session, select

from previsit import audit
from previsit.models import MedicalRecommendation, MessageKind, PatientMessage, StaffAlert, utcnow

logger = logging.getLogger(__name__)


class UnapprovedRecommendationError(PermissionError):
    """Raised when anything tries to tell a patient about a recommendation a physician has not approved."""


def _require_approved(session: Session, appointment_id: int, rec_ids: Sequence[int]) -> list[MedicalRecommendation]:
    if not rec_ids:
        raise UnapprovedRecommendationError("a medical message must reference approved recommendations")
    recs = session.exec(select(MedicalRecommendation).where(MedicalRecommendation.id.in_(list(rec_ids)))).all()
    if len(recs) != len(set(rec_ids)):
        raise UnapprovedRecommendationError("unknown recommendation id")
    for rec in recs:
        if rec.appointment_id != appointment_id:
            raise UnapprovedRecommendationError(f"recommendation {rec.id} belongs to another appointment")
        if not rec.status.is_approved or not rec.decided_by:
            raise UnapprovedRecommendationError(f"recommendation {rec.id} is {rec.status.value}, not approved")
    return list(recs)


def send_patient_message(
    session: Session,
    appointment_id: int,
    kind: MessageKind,
    body: str,
    actor: str,
    rec_ids: Sequence[int] = (),
    meta: dict[str, Any] | None = None,
) -> PatientMessage:
    if kind is MessageKind.MEDICAL:
        recs = _require_approved(session, appointment_id, rec_ids)
        now = utcnow()
        for rec in recs:
            rec.patient_notified_at = now
            session.add(rec)
    elif rec_ids:
        raise UnapprovedRecommendationError("only MEDICAL messages may reference recommendations")
    message = PatientMessage(
        appointment_id=appointment_id,
        kind=kind,
        body=body,
        meta={**(meta or {}), "rec_ids": list(rec_ids)},
    )
    session.add(message)
    session.flush()
    audit.record(session, actor, "patient_message.sent", "appointment", appointment_id, {"kind": kind.value, "message_id": message.id})
    logger.info("Patient message %s (%s) queued for appointment %s", message.id, kind.value, appointment_id)
    return message


def send_staff_alert(
    session: Session, appointment_id: int, severity: str, title: str, body: str, actor: str = "system"
) -> StaffAlert:
    alert = StaffAlert(appointment_id=appointment_id, severity=severity, title=title, body=body)
    session.add(alert)
    session.flush()
    audit.record(session, actor, "staff_alert.sent", "appointment", appointment_id, {"alert_id": alert.id, "severity": severity})
    logger.warning("STAFF ALERT [%s] appointment %s: %s", severity, appointment_id, title)
    return alert
