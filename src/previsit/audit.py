"""Append-only audit trail. Every call, output, approval, notification and upload is recorded."""

from typing import Any

from sqlmodel import Session

from previsit.models import AuditEvent


def record(
    session: Session,
    actor: str,
    action: str,
    entity: str,
    entity_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(actor=actor, action=action, entity=entity, entity_id=entity_id, details=details or {})
    session.add(event)
    session.flush()
    return event
