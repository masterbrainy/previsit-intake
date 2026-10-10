"""Symptom logs between the call and the visit. Values and notes are red-flag checked (rule D1)."""

from dataclasses import dataclass

from sqlmodel import Session, select

from previsit import audit, outbox
from previsit.config import Settings
from previsit.llm import LLMClient, LLMError
from previsit.models import Appointment, Intake, Patient, SymptomLog
from previsit.modules import ComplaintModule, MonitoringSpec, all_modules, modules_for
from previsit.recs.medical import OPS
from previsit.safety import escalation
from previsit.safety.context import PatientContext
from previsit.safety.detector import SafetyStatus, TranscriptLine, assess_turn

TEMPERATURE_METRIC = "temperature_c"
METRIC_ALIASES = {"temperature": TEMPERATURE_METRIC, "temp": TEMPERATURE_METRIC}
MIN_TEMP_C, MAX_TEMP_C = 30.0, 45.0


class SymptomLogError(ValueError):
    pass


@dataclass(frozen=True)
class LogOutcome:
    log: SymptomLog
    escalated: bool
    flagged: bool
    message: str


def monitoring_specs(modules: list[ComplaintModule]) -> dict[str, MonitoringSpec]:
    return {spec.metric: spec for module in modules for spec in module.monitoring}


def normalise(metric: str, value: float, unit: str) -> float:
    if metric == TEMPERATURE_METRIC:
        celsius = (value - 32) * 5 / 9 if unit.upper().endswith("F") else value
        if not MIN_TEMP_C <= celsius <= MAX_TEMP_C:
            raise SymptomLogError("That temperature looks out of range. Please check the reading and the unit.")
        return round(celsius, 1)
    return value


def _patient_context(session: Session, appointment: Appointment) -> tuple[PatientContext, list[str]]:
    patient = session.get(Patient, appointment.patient_id)
    intake = session.exec(select(Intake).where(Intake.appointment_id == appointment.id)).first()
    ctx = PatientContext(
        name=patient.name, dob=patient.dob, sex=patient.sex, on_date=appointment.scheduled_at.date(),
        informant=intake.informant if intake else "self", physician_name=appointment.physician_name,
    )
    return ctx, list(intake.module_ids) if intake else []


def log_symptom(
    session: Session,
    llm: LLMClient,
    appointment: Appointment,
    metric: str,
    value: float,
    note: str,
    settings: Settings,
    unit: str = "°C",
) -> LogOutcome:
    """Unknown metrics are refused. Modules the intake didn't activate still count, so a log is never silently lost."""
    ctx, module_ids = _patient_context(session, appointment)
    modules = modules_for(module_ids)
    metric = METRIC_ALIASES.get(metric, metric)
    spec = monitoring_specs(modules).get(metric) or monitoring_specs(list(all_modules().values())).get(metric)
    if spec is None:
        raise SymptomLogError("This reading isn't being tracked for this appointment.")
    appointment_id = appointment.id
    normalised = normalise(metric, value, unit)
    log = SymptomLog(appointment_id=appointment_id, metric=metric, value=normalised, unit=spec.unit, note=note.strip()[:500])
    session.add(log)
    session.flush()
    audit.record(session, "patient", "symptom.logged", "appointment", appointment_id, {"log_id": log.id})

    for threshold in spec.thresholds:
        if threshold.max_age_days is not None and ctx.age_days > threshold.max_age_days:
            continue
        if not OPS[threshold.op](normalised, threshold.value):
            continue
        if threshold.action == "escalate":
            log.flagged = True
            rf_ids = (threshold.rf_id,) if threshold.rf_id else (escalation.UNSPECIFIED_LOG_RF,)
            escalation.record_red_flag(
                session, appointment_id, rf_ids, f"Logged {spec.label.lower()} {normalised}{spec.unit}", ctx, settings,
                "symptom_log",
            )
            return LogOutcome(log, True, True, escalation.escalation_message(rf_ids, ctx, settings))
        log.flagged = True
        outbox.send_staff_alert(
            session, appointment_id, "review", f"Symptom log: {threshold.label}",
            f"{ctx.name} logged {spec.label.lower()} {normalised}{spec.unit}.",
        )

    if log.note:
        outcome = _check_note(session, llm, settings, appointment_id, ctx, modules, log)
        if outcome:
            return outcome
    session.add(log)
    return LogOutcome(log, False, log.flagged, "Thank you, your reading has been saved for your doctor.")


def _check_note(
    session: Session, llm: LLMClient, settings: Settings, appointment_id: int, ctx: PatientContext,
    modules: list[ComplaintModule], log: SymptomLog,
) -> LogOutcome | None:
    line = TranscriptLine(seq=1, speaker="patient", text=log.note)
    try:
        assessment = assess_turn(llm, ctx, modules, [line])
    except LLMError:
        outbox.send_staff_alert(session, appointment_id, "review", "Symptom note not safety-checked",
                                f'Safety check unavailable for note: "{log.note}"')
        return None
    if assessment.status is SafetyStatus.RED_FLAG:
        log.flagged = True
        escalation.record_red_flag(session, appointment_id, assessment.rf_ids, log.note, ctx, settings, "symptom_log")
        return LogOutcome(log, True, True, escalation.escalation_message(assessment.rf_ids, ctx, settings))
    if assessment.status is SafetyStatus.AMBIGUOUS:
        # No conversation to ask a clarifying question in, so staff review it and the patient gets the safety-net text.
        log.flagged = True
        outbox.send_staff_alert(session, appointment_id, "review", "Symptom note needs review",
                                f'Possible red flag in note: "{log.note}"')
        return LogOutcome(
            log, False, True,
            "Your reading has been saved and your clinic will review your note. If you feel very unwell or are "
            f"worried, please call {settings.emergency_number} now.",
        )
    return None
