"""Hard rule: red flags stop the intake and escalate (PRD §9, evals/red_flags.md §4–5)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from factories import (CRISIS_LINE, EMERGENCY_NUMBER, all_rows, interview, make_appointment,
                       make_fake_llm, make_intake, safety, tasks_called)

RED_FLAGS_DOC = Path(__file__).resolve().parents[1] / "evals" / "red_flags.md"
LLM_SENTINEL = "LLM-AUTHORED-SENTINEL"


def _turn(llm, settings, session, intake, text):
    from previsit.intake.engine import IntakeEngine

    return IntakeEngine(llm, settings).handle_patient_turn(session, intake, text)


def _red_flag(*rf_ids):
    return lambda system, messages: safety("red_flag", rf_ids, evidence="test trigger")


def _dump(row) -> str:
    return str(row.model_dump())


def _state(name):
    from previsit.models import IntakeState

    return IntakeState[name]


@pytest.fixture
def escalated(settings, session, appointment):
    """One intake mid-interview, escalated on RF-07."""
    llm = make_fake_llm(safety=_red_flag("RF-07"), interview=lambda s, m: interview(LLM_SENTINEL))
    intake = make_intake(session, appointment, "INTERVIEW")
    reply = _turn(llm, settings, session, intake, "My neck is really stiff, it hurts to put my chin down")
    return llm, intake, reply


def test_red_flag_moves_intake_to_escalated(session, escalated):
    _, intake, reply = escalated

    session.refresh(intake)
    assert reply.state == _state("ESCALATED")
    assert intake.state == _state("ESCALATED")
    assert reply.ended is True


def test_red_flag_asks_no_further_interview_question(escalated):
    llm, _, reply = escalated

    assert "interview" not in tasks_called(llm)
    assert LLM_SENTINEL not in reply.text


def test_escalation_message_gives_the_emergency_number(escalated):
    _, _, reply = escalated

    assert EMERGENCY_NUMBER in reply.text


def test_red_flag_event_and_staff_alert_are_recorded_at_trigger(session, escalated):
    from previsit.models import RedFlagEvent, StaffAlert

    events = all_rows(session, RedFlagEvent)
    alerts = all_rows(session, StaffAlert)

    assert len(events) == 1 and "RF-07" in _dump(events[0])
    assert len(alerts) == 1


def test_escalated_intake_generates_no_recommendations(session, escalated):
    from previsit.models import MedicalRecommendation, PatientMessage, MessageKind

    llm, _, _ = escalated

    assert "general_recs" not in tasks_called(llm)
    assert all_rows(session, MedicalRecommendation) == []
    assert not [m for m in all_rows(session, PatientMessage)
                if m.kind in (MessageKind.GENERAL_RECS, MessageKind.MEDICAL)]


def test_escalated_intake_does_not_resume(settings, session, escalated):
    llm, intake, _ = escalated
    calls_before = len(llm.calls)

    reply = _turn(llm, settings, session, intake, "Sorry, can we carry on with the questions?")

    later_tasks = tasks_called(llm)[calls_before:]
    assert "interview" not in later_tasks
    assert reply.state == _state("ESCALATED")
    assert reply.ended is True


@pytest.mark.parametrize("state_name", ["CONSENT", "IDENTITY", "INTERVIEW", "READBACK", "COMPLETE"])
def test_red_flag_escalates_in_every_state(settings, session, appointment, state_name):
    llm = make_fake_llm(safety=_red_flag("RF-01"))
    intake = make_intake(session, appointment, state_name)

    reply = _turn(llm, settings, session, intake, "Yes, that's fine. Oh, and my chest feels really heavy.")

    assert "safety" in tasks_called(llm)
    assert reply.state == _state("ESCALATED")


def test_every_patient_turn_is_screened(settings, session, appointment, llm):
    intake = make_intake(session, appointment, "INTERVIEW")
    turns = ["I've had a fever for three days", "It's worse at night", "About 102 at the highest"]

    for text in turns:
        _turn(llm, settings, session, intake, text)

    safety_calls = [c for c in llm.calls if "safety" in str(c)]
    assert len([t for t in tasks_called(llm) if t == "safety"]) >= len(turns)
    for text in turns:
        assert any(text in str(c) for c in safety_calls), f"turn not screened: {text!r}"


def test_escalation_text_is_a_fixed_template(settings, session):
    texts = []
    for _ in range(2):
        llm = make_fake_llm(safety=_red_flag("RF-02"), interview=lambda s, m: interview(LLM_SENTINEL))
        intake = make_intake(session, make_appointment(session), "INTERVIEW")
        texts.append(_turn(llm, settings, session, intake, "I can't catch my breath").text)

    assert texts[0] == texts[1]
    assert LLM_SENTINEL not in texts[0]


def test_self_harm_escalation_gives_the_crisis_line(settings, session, appointment):
    llm = make_fake_llm(safety=_red_flag("RF-06"))
    intake = make_intake(session, appointment, "INTERVIEW")

    reply = _turn(llm, settings, session, intake, "Everyone would be better off if I wasn't around")

    assert reply.state == _state("ESCALATED")
    assert CRISIS_LINE in reply.text
    assert EMERGENCY_NUMBER in reply.text


def test_ambiguous_answer_gets_one_clarifying_question(settings, session, appointment):
    question = "Can you bend your head forward and touch your chin to your chest?"
    llm = make_fake_llm(safety=lambda s, m: safety("ambiguous", ("RF-07",), clarifying_question=question))
    intake = make_intake(session, appointment, "INTERVIEW")

    reply = _turn(llm, settings, session, intake, "My neck's a bit sore")

    assert question in reply.text
    assert reply.state != _state("ESCALATED")
    assert "interview" not in tasks_called(llm)


def test_still_ambiguous_after_clarifying_escalates(settings, session, appointment):
    """Rule D4: unclear after one clarifying question means escalate (fail-safe)."""
    question = "Do the spots fade when you press a glass on them?"
    llm = make_fake_llm(safety=lambda s, m: safety("ambiguous", ("RF-08",), clarifying_question=question))
    intake = make_intake(session, appointment, "INTERVIEW")

    _turn(llm, settings, session, intake, "He's got some spots on his tummy")
    reply = _turn(llm, settings, session, intake, "I really don't know, I haven't checked")

    assert reply.state == _state("ESCALATED")


def test_safety_check_failure_never_continues_the_interview(settings, session, appointment):
    def broken(system, messages):
        raise RuntimeError("safety model unavailable")

    from previsit.intake.engine import IntakeEngine  # outside the try: a missing engine must fail, not pass

    llm = make_fake_llm(safety=broken)
    intake = make_intake(session, appointment, "INTERVIEW")

    try:
        reply = IntakeEngine(llm, settings).handle_patient_turn(session, intake, "I've also been feeling faint")
    except Exception:
        reply = None

    assert "interview" not in tasks_called(llm)
    if reply is not None:
        assert reply.state == _state("ESCALATED")


def test_baseline_red_flags_mirror_the_clinical_list():
    from previsit.safety.red_flags import BASELINE_RED_FLAGS

    documented = set(re.findall(r"^\| (RF-\d\d) \|", RED_FLAGS_DOC.read_text(), re.M))
    items = BASELINE_RED_FLAGS.values() if isinstance(BASELINE_RED_FLAGS, dict) else BASELINE_RED_FLAGS
    in_code = set(BASELINE_RED_FLAGS) if isinstance(BASELINE_RED_FLAGS, dict) else {
        getattr(item, "id", None) or getattr(item, "rf_id", None) for item in items
    }

    assert in_code == documented
