"""Runs deferred sheet work after the patient has had their reply (F.2). One job at a time per intake."""

import logging
import threading
from collections import defaultdict

from sqlalchemy import Engine

from previsit import outbox
from previsit.config import Settings
from previsit.db import session_scope
from previsit.intake.engine import IntakeEngine, SheetJob
from previsit.llm import LLMClient, LLMError
from previsit.models import Intake

logger = logging.getLogger(__name__)
_locks: defaultdict[int, threading.Lock] = defaultdict(threading.Lock)
_locks_guard = threading.Lock()


def _lock_for(intake_id: int) -> threading.Lock:
    with _locks_guard:
        return _locks[intake_id]


def run_sheet_job(engine: Engine, settings: Settings, llm: LLMClient, job: SheetJob) -> None:
    with _lock_for(job.intake_id):
        try:
            with session_scope(engine) as session:
                IntakeEngine(llm, settings).run_sheet_job(session, job)
        except LLMError:
            logger.exception("Deferred sheet update failed for intake %s", job.intake_id)
            with session_scope(engine) as session:
                intake = session.get(Intake, job.intake_id)
                outbox.send_staff_alert(
                    session, intake.appointment_id, "review", "History sheet update failed",
                    "The latest history sheet could not be rebuilt after the call; the earlier version is shown.",
                )
