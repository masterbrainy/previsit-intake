"""Escalation wording (fixed templates from evals/red_flags.md §5.2, never LLM-written) and the escalation record."""

from sqlmodel import Session

from previsit import audit, outbox
from previsit.config import Settings
from previsit.models import MessageKind, RedFlagEvent
from previsit.safety.context import PatientContext
from previsit.safety.red_flags import SUICIDE_RISK_ID, describe

UNSPECIFIED_LOG_RF = "RF-UNSPECIFIED"


def record_red_flag(
    session: Session,
    appointment_id: int,
    rf_ids: tuple[str, ...],
    evidence: str,
    ctx: PatientContext,
    settings: Settings,
    source: str,
    intake_id: int | None = None,
    turn_id: int | None = None,
) -> RedFlagEvent:
    """Writes the event, alerts staff and leaves the escalation message on the patient's page, immediately."""
    event = RedFlagEvent(
        appointment_id=appointment_id, intake_id=intake_id, turn_id=turn_id, rf_ids=list(rf_ids),
        evidence=evidence, source=source,
    )
    session.add(event)
    session.flush()
    informant = "self" if not ctx.is_caregiver_call else ctx.informant
    outbox.send_staff_alert(
        session,
        appointment_id,
        "emergency",
        f"RED FLAG: {describe(rf_ids)}",
        f'{ctx.name} (DOB {ctx.dob.isoformat()}), informant: {informant}. Triggering statement: "{evidence}" '
        f"(source: {source}{f', turn {turn_id}' if turn_id else ''}). Patient told to seek emergency care now.",
    )
    outbox.send_patient_message(
        session, appointment_id, MessageKind.ESCALATION, escalation_message(rf_ids, ctx, settings), actor="system",
        meta={"rf_ids": list(rf_ids)},
    )
    audit.record(session, "system", "red_flag.escalated", "appointment", appointment_id,
                 {"rf_ids": list(rf_ids), "evidence": evidence, "source": source, "event_id": event.id})
    return event


def escalation_message(rf_ids: tuple[str, ...], ctx: PatientContext, settings: Settings) -> str:
    emergency = settings.emergency_number
    if SUICIDE_RISK_ID in rf_ids:
        return (
            "Thank you for telling me. I'm going to pause the questions about your appointment. "
            "You don't have to go through this alone. If you're in danger right now or might act on these thoughts, "
            f"please call {emergency}. You can also talk to someone right now at {settings.crisis_line}. "
            "I'm letting your clinic know so they can contact you. Are you safe right now?"
        )
    if ctx.is_caregiver_call:
        return (
            f"I need to stop here. What you've told me about {ctx.first_name} needs urgent attention. "
            f"Please call {emergency} or take them to the nearest emergency department now. "
            "I'm letting your clinic know as well. Can you do that now?"
        )
    return (
        "I need to stop here. What you've told me needs urgent attention. "
        f"Please call {emergency} or go to the nearest emergency department now. "
        "I'm letting your clinic know as well. Can you do that now?"
    )


def follow_up_message(rf_ids: tuple[str, ...], settings: Settings) -> str:
    """Said to any patient turn after escalation: hesitation, refusal, or 'what is it?'."""
    if SUICIDE_RISK_ID in rf_ids:
        return (
            f"Please call {settings.emergency_number} if you are in danger right now, or talk to someone at "
            f"{settings.crisis_line}. Your clinic has been told and will contact you."
        )
    return (
        "I understand. I can't assess this over the phone, and these symptoms need to be checked by a doctor "
        f"straight away, not tomorrow. Please call {settings.emergency_number} now. "
        "I'm ending this call so your line is free."
    )


def technical_failure_message(settings: Settings) -> str:
    return (
        "I'm sorry, I'm having a technical problem and need to stop here. "
        f"If you feel very unwell, please call {settings.emergency_number} now. "
        "Otherwise, your clinic will be in touch and your appointment is unchanged."
    )
