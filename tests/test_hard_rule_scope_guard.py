"""Hard rule: the agent never diagnoses, prescribes or doses (PRD §8.2, §9 scope guard)."""
from __future__ import annotations

from factories import all_rows, guard, interview, make_fake_llm, make_intake, tasks_called

BLOCKED = "This sounds like a viral infection. Take 500 mg of paracetamol every 6 hours."
BLOCKED_FRAGMENTS = ("viral", "500 mg", "every 6 hours")


def _turn(llm, settings, session, intake, text="I've had a fever for three days"):
    from previsit.intake.engine import IntakeEngine

    return IntakeEngine(llm, settings).handle_patient_turn(session, intake, text)


def _agent_turn_dumps(session) -> list[str]:
    from previsit.models import Turn

    return [str(t.model_dump()) for t in all_rows(session, Turn)]


def _assert_nothing_blocked_reached_patient(session, reply):
    for fragment in BLOCKED_FRAGMENTS:
        assert fragment not in reply.text
        assert not any(fragment in dump for dump in _agent_turn_dumps(session))


def test_blocked_utterance_is_replaced_with_the_redirect(settings, session, appointment):
    llm = make_fake_llm(interview=lambda s, m: interview(BLOCKED),
                        scope_guard=lambda s, m: guard(False, "diagnosis and dosing"))
    intake = make_intake(session, appointment, "INTERVIEW")

    reply = _turn(llm, settings, session, intake)

    _assert_nothing_blocked_reached_patient(session, reply)
    assert reply.text.strip()
    assert "doctor" in reply.text.lower()


def test_allowed_utterance_passes_through(settings, session, appointment):
    question = "Does anything make the fever better or worse?"
    llm = make_fake_llm(interview=lambda s, m: interview(question))
    intake = make_intake(session, appointment, "INTERVIEW")

    reply = _turn(llm, settings, session, intake)

    assert question in reply.text


def test_every_interview_utterance_is_checked(settings, session, appointment, llm):
    intake = make_intake(session, appointment, "INTERVIEW")

    for text in ["Fever for three days", "Worse at night", "Max 102"]:
        _turn(llm, settings, session, intake, text)

    tasks = tasks_called(llm)
    assert tasks.count("scope_guard") >= tasks.count("interview") > 0


def test_guard_failure_fails_closed(settings, session, appointment):
    def broken(system, messages):
        raise RuntimeError("guard model unavailable")

    from previsit.intake.engine import IntakeEngine  # outside the try: a missing engine must fail, not pass

    llm = make_fake_llm(interview=lambda s, m: interview(BLOCKED), scope_guard=broken)
    intake = make_intake(session, appointment, "INTERVIEW")

    try:
        reply = IntakeEngine(llm, settings).handle_patient_turn(session, intake, "I've had a fever for three days")
    except Exception:
        reply = None

    if reply is not None:
        _assert_nothing_blocked_reached_patient(session, reply)
    else:
        assert not any(f in d for f in BLOCKED_FRAGMENTS for d in _agent_turn_dumps(session))
