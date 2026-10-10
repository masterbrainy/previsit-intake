"""Database tables. Every patient-facing message lives in PatientMessage, written only by previsit.outbox."""

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from pydantic import NaiveDatetime
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class IntakeState(StrEnum):
    NOT_STARTED = "not_started"
    CONSENT = "consent"
    IDENTITY = "identity"
    INTERVIEW = "interview"
    READBACK = "readback"
    COMPLETE = "complete"
    ESCALATED = "escalated"
    DECLINED = "declined"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in {IntakeState.COMPLETE, IntakeState.ESCALATED, IntakeState.DECLINED, IntakeState.FAILED}


class Speaker(StrEnum):
    AGENT = "agent"
    PATIENT = "patient"


class RecStatus(StrEnum):
    SUGGESTED = "suggested"
    APPROVED = "approved"
    MODIFIED = "modified"
    REJECTED = "rejected"

    @property
    def is_approved(self) -> bool:
        return self in {RecStatus.APPROVED, RecStatus.MODIFIED}


class MessageKind(StrEnum):
    INVITE = "invite"
    GENERAL_RECS = "general_recs"
    MEDICAL = "medical"
    ESCALATION = "escalation"
    INFO = "info"


class Patient(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    dob: date
    sex: str = ""
    phone: str = Field(default="", index=True)  # normalised by previsit.portal.contact
    email: str = Field(default="", index=True)  # normalised (lower case)
    created_at: datetime = Field(default_factory=utcnow)


class Appointment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id", index=True)
    physician_name: str
    scheduled_at: NaiveDatetime = Field(index=True)  # clinic-local wall-clock time
    reason: str = ""
    token: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=utcnow)


class Intake(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    appointment_id: int = Field(foreign_key="appointment.id", unique=True, index=True)
    state: IntakeState = IntakeState.NOT_STARTED
    informant: str = "self"
    module_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    readback_pending: bool = False  # two-step read-back: holding line said, summary not yet read back
    pending_clarification: str | None = None
    identity_attempts: int = 0
    started_at: datetime | None = None
    ended_at: datetime | None = None


class Turn(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    intake_id: int = Field(foreign_key="intake.id", index=True)
    seq: int
    speaker: Speaker
    text: str
    created_at: datetime = Field(default_factory=utcnow)


class HistorySheetRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    intake_id: int = Field(foreign_key="intake.id", index=True)
    version: int
    data: dict[str, Any] = Field(sa_column=Column(JSON))
    dropped_statements: int = 0
    partial: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class RedFlagEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    appointment_id: int = Field(foreign_key="appointment.id", index=True)
    intake_id: int | None = Field(default=None, foreign_key="intake.id")
    turn_id: int | None = Field(default=None, foreign_key="turn.id")
    rf_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    evidence: str = ""
    source: str = "intake"
    patient_response: str | None = None  # the caller's first reply after being told to seek emergency care
    created_at: datetime = Field(default_factory=utcnow)


class MedicalRecommendation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    appointment_id: int = Field(foreign_key="appointment.id", index=True)
    name: str
    rationale: str = ""
    rule_id: str | None = None
    module_id: str | None = None
    source: str = "ai_suggested"
    status: RecStatus = RecStatus.SUGGESTED
    decided_by: str | None = None
    decided_at: datetime | None = None
    physician_note: str = ""
    patient_instructions: str = ""
    patient_notified_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class PatientMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    appointment_id: int = Field(foreign_key="appointment.id", index=True)
    kind: MessageKind
    body: str
    meta: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    channel: str = "portal"
    created_at: datetime = Field(default_factory=utcnow)


class StaffAlert(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    appointment_id: int = Field(foreign_key="appointment.id", index=True)
    severity: str = "emergency"
    title: str
    body: str
    created_at: datetime = Field(default_factory=utcnow)
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None


class SymptomLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    appointment_id: int = Field(foreign_key="appointment.id", index=True)
    metric: str
    value: float
    unit: str = ""
    note: str = ""
    flagged: bool = False
    recorded_at: datetime = Field(default_factory=utcnow)


class LabResult(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    appointment_id: int = Field(foreign_key="appointment.id", index=True)
    filename: str
    stored_path: str
    content_type: str
    size_bytes: int
    uploaded_by: str
    created_at: datetime = Field(default_factory=utcnow)


class AuditEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=utcnow, index=True)
    actor: str
    action: str
    entity: str
    entity_id: int | None = None
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class SignInCode(SQLModel, table=True):
    """A one-time portal sign-in code. Only its HMAC is stored. Times are naive UTC."""

    id: int | None = Field(default=None, primary_key=True)
    contact: str = Field(index=True)
    code_hash: str = ""  # empty for requests about an unknown contact (kept only for rate limiting)
    ip: str = Field(default="", index=True)
    created_at: NaiveDatetime = Field(index=True)
    expires_at: NaiveDatetime
    attempts: int = 0
    used_at: NaiveDatetime | None = None


class PortalSession(SQLModel, table=True):
    """A signed-in patient portal session. Only the SHA-256 of the cookie token is stored. Times are naive UTC."""

    id: int | None = Field(default=None, primary_key=True)
    token_hash: str = Field(unique=True, index=True)
    contact: str = Field(index=True)
    created_at: NaiveDatetime
    expires_at: NaiveDatetime
    ended_at: NaiveDatetime | None = None
