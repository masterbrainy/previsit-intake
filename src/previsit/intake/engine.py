"""Intake state machine: CONSENT → IDENTITY → INTERVIEW → READBACK → COMPLETE, or ESCALATED / DECLINED / FAILED.

Every patient turn, in every state (including after completion), goes through red-flag detection first.
"""

import logging
from dataclasses import dataclass

from sqlmodel import Session, func, select

from previsit import audit, outbox
from previsit.config import Settings
from previsit.intake import gates
from previsit.intake.interviewer import next_step
from previsit.llm import LLMClient, LLMError
from previsit.models import (
    Appointment, HistorySheetRecord, Intake, IntakeState, MedicalRecommendation, MessageKind, Patient,
    RedFlagEvent, Speaker, Turn, utcnow,
)
from previsit.modules import ComplaintModule, modules_for
from previsit.recs.general import select_general_recs
from previsit.recs.medical import suggest_investigations
from previsit.safety import escalation
from previsit.safety.context import PatientContext
from previsit.safety.detector import SafetyStatus, TranscriptLine, assess_turn
from previsit.safety.scope_guard import check_agent_utterance, redirect_for
from previsit.sheet.extract import build_sheet
from previsit.sheet.schema import HistorySheet

logger = logging.getLogger(__name__)

MAX_TURN_CHARS = 2000
MAX_IDENTITY_ATTEMPTS = 2
MAX_READBACK_ROUNDS = 3
READBACK_QUESTION = "Is that right, or is there anything you'd like to correct or add?"
ANYTHING_ELSE_QUESTION = "Is there anything else you'd like your doctor to know?"
IDENTITY_QUESTION = (
    "Thank you. First, please tell me the patient's full name and date of birth. "
    "If you're answering for someone else, please also tell me how you're related to them."
)


@dataclass(frozen=True)
class AgentReply:
    text: str
    state: IntakeState
    ended: bool = False


class IntakeEngine:
    def __init__(self, llm: LLMClient, settings: Settings) -> None:
        self.llm = llm
        self.settings = settings

    # ----- public API -------------------------------------------------------------------------------

    def start(self, session: Session, intake: Intake) -> AgentReply:
        if intake.state is not IntakeState.NOT_STARTED:
            last = self._last_agent_text(session, intake)
            return AgentReply(f"Welcome back. {last}" if last else last, intake.state, intake.state.is_terminal)
        ctx = self._context(session, intake)
        intake.state = IntakeState.CONSENT
        intake.started_at = utcnow()
        session.add(intake)
        audit.record(session, "patient", "intake.started", "intake", intake.id)
        when = self._appointment(session, intake).scheduled_at.strftime("%A %d %B at %H:%M")
        text = (
            f"Hello, I'm the pre-visit assistant for {self.settings.clinic_name}. Before the appointment with "
            f"{ctx.physician_name} on {when}, I'd like to ask some questions about your health so your doctor is "
            "prepared. This conversation is recorded and shared with your doctor. I'm an automated assistant, not a "
            f"doctor, so I can't tell you what's wrong. If at any point you feel very unwell, please call "
            f"{self.settings.emergency_number}. Are you happy to continue?"
        )
        return self._say(session, intake, text)

    def handle_patient_turn(self, session: Session, intake: Intake, text: str) -> AgentReply:
        text = text.strip()[:MAX_TURN_CHARS]
        if not text:
            return AgentReply("Sorry, I didn't catch that. Could you say it again?", intake.state)
        if intake.state is IntakeState.NOT_STARTED:
            return self.start(session, intake)
        turn = self._add_turn(session, intake, Speaker.PATIENT, text)
        if intake.state in {IntakeState.ESCALATED, IntakeState.DECLINED, IntakeState.FAILED}:
            return self._after_end(session, intake)

        ctx = self._context(session, intake)
        modules = modules_for(intake.module_ids)
        transcript = self._transcript(session, intake)
        try:
            assessment = assess_turn(self.llm, ctx, modules, transcript, intake.pending_clarification)
        except LLMError:
            return self._fail(session, intake, "Safety check unavailable")

        if assessment.status is SafetyStatus.RED_FLAG:
            return self._escalate(session, intake, ctx, modules, assessment.rf_ids, assessment.evidence or text, turn)
        if assessment.status is SafetyStatus.AMBIGUOUS:
            intake.pending_clarification = ",".join(assessment.rf_ids)
            session.add(intake)
            return self._say_guarded(session, intake, assessment.clarifying_question)
        if intake.pending_clarification:
            intake.pending_clarification = None
            session.add(intake)

        try:
            return self._advance(session, intake, ctx, modules, text)
        except LLMError:
            return self._fail(session, intake, "Model unavailable during intake")

    # ----- state handlers ---------------------------------------------------------------------------

    def _advance(
        self, session: Session, intake: Intake, ctx: PatientContext, modules: list[ComplaintModule], text: str
    ) -> AgentReply:
        if intake.state is IntakeState.CONSENT:
            return self._on_consent(session, intake, text)
        if intake.state is IntakeState.IDENTITY:
            return self._on_identity(session, intake, ctx, text)
        if intake.state is IntakeState.INTERVIEW:
            return self._on_interview(session, intake, ctx, modules)
        if intake.state is IntakeState.READBACK:
            return self._on_readback(session, intake, ctx, modules, text)
        return self._on_after_complete(session, intake, ctx, modules, text)

    def _on_consent(self, session: Session, intake: Intake, text: str) -> AgentReply:
        decision = gates.classify_yes_no(self.llm, "consent", "Are you happy to continue?", text)
        if decision == "yes":
            intake.state = IntakeState.IDENTITY
            session.add(intake)
            audit.record(session, "patient", "intake.consented", "intake", intake.id)
            return self._say(session, intake, IDENTITY_QUESTION)
        if decision == "no":
            intake.state = IntakeState.DECLINED
            intake.ended_at = utcnow()
            session.add(intake)
            audit.record(session, "patient", "intake.declined", "intake", intake.id)
            return self._say(
                session, intake,
                "That's fine, we'll stop here. Your appointment is unchanged. If you feel very unwell, please call "
                f"{self.settings.emergency_number}. Goodbye.",
                ended=True,
            )
        return self._say(session, intake, "Sorry, I didn't quite catch that. Are you happy to continue? Yes or no is fine.")

    def _on_identity(self, session: Session, intake: Intake, ctx: PatientContext, text: str) -> AgentReply:
        check = gates.check_identity(self.llm, text, ctx.name, ctx.dob)
        if check.matched:
            intake.state = IntakeState.INTERVIEW
            intake.informant = check.informant
            session.add(intake)
            audit.record(session, "patient", "intake.identity_confirmed", "intake", intake.id, {"informant": check.informant})
            subject = "you" if check.informant == "self" else ctx.first_name
            return self._say(
                session, intake,
                f"Thank you. What's been troubling {subject}? Please tell me about each problem and when it started.",
            )
        intake.identity_attempts += 1
        session.add(intake)
        if intake.identity_attempts >= MAX_IDENTITY_ATTEMPTS:
            intake.state = IntakeState.FAILED
            intake.ended_at = utcnow()
            audit.record(session, "system", "intake.identity_failed", "intake", intake.id)
            outbox.send_staff_alert(session, intake.appointment_id, "review", "Identity check failed",
                                    "The caller could not confirm the patient's name and date of birth.")
            return self._say(
                session, intake,
                "I'm sorry, I couldn't confirm those details, so I'll stop here. Please contact your clinic. "
                f"If you feel very unwell, call {self.settings.emergency_number}.",
                ended=True,
            )
        return self._say(
            session, intake,
            "Sorry, those details don't match what I have. Could you tell me the patient's full name and date of birth again?",
        )

    def _on_interview(
        self, session: Session, intake: Intake, ctx: PatientContext, modules: list[ComplaintModule]
    ) -> AgentReply:
        # Runs only after the safety check came back clear: no question is even generated after a red flag.
        step = next_step(self.llm, modules, self._transcript(session, intake), ctx, self.settings.clinic_name)
        if step.module_ids:
            intake.module_ids = list(dict.fromkeys([*intake.module_ids, *step.module_ids]))
            session.add(intake)
        if not step.interview_complete:
            return self._say_guarded(session, intake, step.utterance)
        modules = modules_for(intake.module_ids)
        sheet = self._save_sheet(session, intake, ctx, modules)
        intake.state = IntakeState.READBACK
        session.add(intake)
        return self._say(session, intake, f"Thank you. {readback_text(sheet)} {READBACK_QUESTION}")

    def _on_readback(
        self, session: Session, intake: Intake, ctx: PatientContext, modules: list[ComplaintModule], text: str
    ) -> AgentReply:
        decision = gates.classify_yes_no(self.llm, "consent", READBACK_QUESTION, text)
        rounds = self._count_agent_turns_since_readback(session, intake)
        if decision != "yes" and rounds < MAX_READBACK_ROUNDS:
            return self._say(
                session, intake,
                "Thank you, I've noted that for your doctor. Is there anything else to correct, or is the rest right?",
            )
        return self._complete(session, intake, ctx, modules)

    def _on_after_complete(
        self, session: Session, intake: Intake, ctx: PatientContext, modules: list[ComplaintModule], text: str
    ) -> AgentReply:
        decision = gates.classify_yes_no(self.llm, "consent", ANYTHING_ELSE_QUESTION, text)
        if decision == "no":
            return self._say(session, intake, "Thank you. Take care, and goodbye.", ended=True)
        sheet = self._save_sheet(session, intake, ctx, modules)
        self._save_suggestions(session, intake, modules, sheet)
        return self._say(
            session, intake,
            "Thank you, I've added that for your doctor. You can end the call whenever you're ready.",
            ended=True,
        )

    def _complete(
        self, session: Session, intake: Intake, ctx: PatientContext, modules: list[ComplaintModule]
    ) -> AgentReply:
        sheet = self._save_sheet(session, intake, ctx, modules)
        recs = select_general_recs(self.llm, modules, sheet, ctx)
        outbox.send_patient_message(
            session, intake.appointment_id, MessageKind.GENERAL_RECS, recs.render(self.settings), actor="system",
            meta={"item_ids": [item.id for item in recs.items]},
        )
        self._save_suggestions(session, intake, modules, sheet)
        intake.state = IntakeState.COMPLETE
        intake.ended_at = utcnow()
        session.add(intake)
        audit.record(session, "system", "intake.completed", "intake", intake.id)
        return self._say(
            session, intake,
            f"Thank you, that's everything I need. Your doctor will see this before your appointment. "
            f"{recs.spoken(self.settings)} You'll find this advice on your patient page too, where you can also log "
            f"your readings. {ANYTHING_ELSE_QUESTION}",
            ended=True,
        )

    # ----- escalation and failure -------------------------------------------------------------------

    def _escalate(
        self, session: Session, intake: Intake, ctx: PatientContext, modules: list[ComplaintModule],
        rf_ids: tuple[str, ...], evidence: str, turn: Turn,
    ) -> AgentReply:
        escalation.record_red_flag(
            session, intake.appointment_id, rf_ids, evidence, ctx, self.settings, "intake",
            intake_id=intake.id, turn_id=turn.id,
        )
        intake.state = IntakeState.ESCALATED
        intake.pending_clarification = None
        intake.ended_at = utcnow()
        session.add(intake)
        reply = self._say(session, intake, escalation.escalation_message(rf_ids, ctx, self.settings), ended=True)
        try:
            self._save_sheet(session, intake, ctx, modules, partial=True)
        except LLMError:
            logger.exception("Partial sheet failed for intake %s", intake.id)
        return reply

    def _after_end(self, session: Session, intake: Intake) -> AgentReply:
        if intake.state is IntakeState.ESCALATED:
            event = session.exec(
                select(RedFlagEvent).where(RedFlagEvent.intake_id == intake.id).order_by(RedFlagEvent.id.desc())
            ).first()
            rf_ids = tuple(event.rf_ids) if event else ()
            if event is not None and event.patient_response is None:
                event.patient_response = self._last_patient_text(session, intake)
                session.add(event)
                audit.record(session, "patient", "red_flag.response", "appointment", intake.appointment_id,
                             {"event_id": event.id, "response": event.patient_response})
            if self._follow_up_already_given(session, intake, event):
                # red_flags.md §5.2: say the follow-up once, then close so the line is free.
                return self._say(
                    session, intake, f"This call has ended. Please call {self.settings.emergency_number} now.", ended=True
                )
            return self._say(session, intake, escalation.follow_up_message(rf_ids, self.settings), ended=True)
        return self._say(
            session, intake,
            f"This conversation has ended. Your appointment is unchanged. If you feel very unwell, please call "
            f"{self.settings.emergency_number}.",
            ended=True,
        )

    def _last_patient_text(self, session: Session, intake: Intake) -> str:
        turn = session.exec(
            select(Turn).where(Turn.intake_id == intake.id, Turn.speaker == Speaker.PATIENT).order_by(Turn.seq.desc())
        ).first()
        return turn.text if turn else ""

    def _follow_up_already_given(self, session: Session, intake: Intake, event: RedFlagEvent | None) -> bool:
        trigger = session.get(Turn, event.turn_id) if event and event.turn_id else None
        since = trigger.seq if trigger else 0
        agent_turns = session.exec(
            select(func.count()).select_from(Turn).where(
                Turn.intake_id == intake.id, Turn.speaker == Speaker.AGENT, Turn.seq > since
            )
        ).one()
        return agent_turns >= 2  # the escalation message itself, then one follow-up

    def _fail(self, session: Session, intake: Intake, reason: str) -> AgentReply:
        logger.error("Intake %s failed: %s", intake.id, reason)
        intake.state = IntakeState.FAILED
        intake.ended_at = utcnow()
        session.add(intake)
        audit.record(session, "system", "intake.failed", "intake", intake.id, {"reason": reason})
        outbox.send_staff_alert(session, intake.appointment_id, "review", "Intake stopped: technical problem", reason)
        return self._say(session, intake, escalation.technical_failure_message(self.settings), ended=True)

    # ----- helpers ----------------------------------------------------------------------------------

    def _say(self, session: Session, intake: Intake, text: str, ended: bool = False) -> AgentReply:
        self._add_turn(session, intake, Speaker.AGENT, text)
        return AgentReply(text, intake.state, ended or intake.state.is_terminal)

    def _say_guarded(self, session: Session, intake: Intake, text: str) -> AgentReply:
        ctx = self._context(session, intake)
        redirect = redirect_for(ctx.first_name if ctx.is_caregiver_call else None)
        result = check_agent_utterance(self.llm, text, redirect)
        if not result.allowed:
            audit.record(session, "system", "scope_guard.blocked", "intake", intake.id,
                         {"reason": result.reason, "blocked_text": text})
        return self._say(session, intake, result.text)

    def _add_turn(self, session: Session, intake: Intake, speaker: Speaker, text: str) -> Turn:
        count = session.exec(select(func.count()).select_from(Turn).where(Turn.intake_id == intake.id)).one()
        turn = Turn(intake_id=intake.id, seq=count + 1, speaker=speaker, text=text)
        session.add(turn)
        session.flush()
        return turn

    def _transcript(self, session: Session, intake: Intake) -> list[TranscriptLine]:
        turns = session.exec(select(Turn).where(Turn.intake_id == intake.id).order_by(Turn.seq)).all()
        return [TranscriptLine(t.seq, t.speaker.value, t.text) for t in turns]

    def _last_agent_text(self, session: Session, intake: Intake) -> str:
        turn = session.exec(
            select(Turn).where(Turn.intake_id == intake.id, Turn.speaker == Speaker.AGENT).order_by(Turn.seq.desc())
        ).first()
        return turn.text if turn else ""

    def _count_agent_turns_since_readback(self, session: Session, intake: Intake) -> int:
        turns = self._transcript(session, intake)
        start = max((t.seq for t in turns if t.speaker == "agent" and READBACK_QUESTION in t.text), default=0)
        return sum(1 for t in turns if t.speaker == "agent" and t.seq >= start)

    def _appointment(self, session: Session, intake: Intake) -> Appointment:
        return session.get(Appointment, intake.appointment_id)

    def _context(self, session: Session, intake: Intake) -> PatientContext:
        appointment = self._appointment(session, intake)
        patient = session.get(Patient, appointment.patient_id)
        return PatientContext(
            name=patient.name, dob=patient.dob, sex=patient.sex, on_date=appointment.scheduled_at.date(),
            informant=intake.informant, physician_name=appointment.physician_name,
        )

    def _save_sheet(
        self, session: Session, intake: Intake, ctx: PatientContext, modules: list[ComplaintModule], partial: bool = False
    ) -> HistorySheet:
        result = build_sheet(self.llm, self._transcript(session, intake), modules, ctx, partial=partial)
        version = session.exec(
            select(func.count()).select_from(HistorySheetRecord).where(HistorySheetRecord.intake_id == intake.id)
        ).one() + 1
        session.add(HistorySheetRecord(
            intake_id=intake.id, version=version, data=result.sheet.model_dump(mode="json"),
            dropped_statements=result.dropped, partial=partial,
        ))
        audit.record(session, "system", "sheet.generated", "intake", intake.id,
                     {"version": version, "dropped_statements": result.dropped, "partial": partial})
        return result.sheet

    def _save_suggestions(
        self, session: Session, intake: Intake, modules: list[ComplaintModule], sheet: HistorySheet
    ) -> None:
        existing = set(session.exec(
            select(MedicalRecommendation.rule_id).where(MedicalRecommendation.appointment_id == intake.appointment_id)
        ).all())
        for suggestion in suggest_investigations(modules, sheet.findings):
            if suggestion.rule_id in existing:
                continue
            session.add(MedicalRecommendation(
                appointment_id=intake.appointment_id, name=suggestion.name, rationale=suggestion.rationale,
                rule_id=suggestion.rule_id, module_id=suggestion.module_id,
                patient_instructions=suggestion.patient_instructions,
            ))
            audit.record(session, "system", "recommendation.suggested", "appointment", intake.appointment_id,
                         {"rule_id": suggestion.rule_id, "name": suggestion.name})


def _complaint_phrase(complaint: str, duration: str) -> str:
    duration = duration.strip()
    if not duration:
        return complaint
    joiner = " " if duration.lower().startswith(("since", "for ", "about", "over", "under")) else " for "
    return f"{complaint}{joiner}{duration}"


def readback_text(sheet: HistorySheet) -> str:
    complaints = ", ".join(_complaint_phrase(c.complaint, c.duration) for c in sheet.chief_complaints)
    complaint_texts = {c.complaint.lower() for c in sheet.chief_complaints}
    extra = [s for s in sheet.hopi if not any(s.text.lower().startswith(t) for t in complaint_texts)]
    details = " ".join(s.text.rstrip(".") + "." for s in extra[:3])
    opening = f"Here are the main points: {complaints}." if complaints else "Here are the main points."
    return f"{opening} {details}".strip()
