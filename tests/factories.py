"""Test-only builders for DB rows and FakeLLM responses.

This is the ONLY file that guesses model field names and LLM response shapes
beyond what docs/ARCHITECTURE.md spells out. When src/previsit/models.py or a
schema changes, fix it here, not in each test.
"""
from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta

from sqlmodel import Session, select

TEST_PHYSICIAN = "dr_test"
EMERGENCY_NUMBER = "999-TEST"
CRISIS_LINE = "CRISIS-TEST-LINE"


# ---------- DB rows ----------

def _save(session: Session, row):
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def make_patient(session: Session, name: str = "Test Patient", dob: date = date(1992, 3, 14)):
    from previsit.models import Patient

    return _save(session, Patient(name=name, dob=dob))


def make_appointment(session: Session, patient=None, physician: str = TEST_PHYSICIAN):
    from previsit.models import Appointment

    patient = patient or make_patient(session)
    return _save(
        session,
        Appointment(
            patient_id=patient.id,
            physician_name=physician,
            scheduled_at=datetime.now() + timedelta(days=1),  # clinic-local wall-clock time (naive)
            token=secrets.token_urlsafe(16),
        ),
    )


def make_intake(session: Session, appointment, state_name: str = "INTERVIEW"):
    """The appointment's intake in the given state (reusing one the web layer may already have created)."""
    from previsit.models import Intake, IntakeState

    intake = session.exec(select(Intake).where(Intake.appointment_id == appointment.id)).first()
    if intake is None:
        intake = Intake(appointment_id=appointment.id)
    intake.state = IntakeState[state_name]
    return _save(session, intake)


def make_rec(session: Session, appointment, name: str = "CBC", status_name: str | None = None,
             decided_by: str | None = None):
    """A suggested investigation. status_name=None relies on the model's default."""
    from previsit.models import MedicalRecommendation, RecStatus

    fields = dict(appointment_id=appointment.id, name=name, rationale="fever > 72h (test)")
    if status_name is not None:
        fields["status"] = RecStatus[status_name]
    if decided_by is not None:
        fields["decided_by"] = decided_by
    return _save(session, MedicalRecommendation(**fields))


def all_rows(session: Session, model) -> list:
    """Each test gets a fresh database, so 'all rows' means 'rows this test created'."""
    return list(session.exec(select(model)).all())


# ---------- FakeLLM responses (dicts; FakeLLM validates them against the task schema) ----------

def safety(status: str = "clear", rf_ids: tuple[str, ...] = (), evidence: str = "",
           clarifying_question: str = "") -> dict:
    """status: clear | ambiguous | red_flag (previsit.safety.detector.SafetyOutput)."""
    return {"status": status, "rf_ids": list(rf_ids), "evidence": evidence,
            "clarifying_question": clarifying_question}


def interview(utterance: str = "How many days have you had the fever?", complete: bool = False,
              module_ids: tuple[str, ...] = ("fever",)) -> dict:
    return {"utterance": utterance, "interview_complete": complete, "module_ids": list(module_ids)}


def guard(allowed: bool = True, reason: str = "") -> dict:
    return {"allowed": allowed, "reason": reason}


def minimal_sheet() -> dict:
    """An empty SheetOut (previsit.sheet.extract); every field is a list, so new sections need no change here."""
    from previsit.sheet.extract import SheetOut

    return {name: [] for name in SheetOut.model_fields}


DEFAULT_RESPONSES = {
    "safety": lambda system, messages: safety(),
    "scope_guard": lambda system, messages: guard(),
    "interview": lambda system, messages: interview(),
    "consent": lambda system, messages: {"decision": "yes"},
    "identity": lambda system, messages: {"full_name": "Test Patient", "date_of_birth": "1992-03-14",
                                          "informant": "self"},
    "sheet": lambda system, messages: minimal_sheet(),
    "general_recs": lambda system, messages: {"item_ids": []},
}


def make_fake_llm(**overrides):
    """FakeLLM with safe defaults; pass task=handler to override, e.g. safety=lambda s, m: {...}."""
    from previsit.llm import FakeLLM

    return FakeLLM({**DEFAULT_RESPONSES, **overrides})


def task_of(call) -> str | None:
    if isinstance(call, dict):
        return call.get("task")
    if hasattr(call, "task"):
        return call.task
    if isinstance(call, (tuple, list)) and call:
        return call[0]
    return None


def tasks_called(llm) -> list[str]:
    return [task_of(c) for c in llm.calls]
