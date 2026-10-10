"""Symptom-specific red-flag screening gate (P-008, PROGRESS 1.13): when a patient mentions a symptom with its own red
flags, every screening item for it is asked within QUESTION_LIMIT agent questions. Items are exempt only if the call
escalated before that window filled. The mention is found in the patient's own words, not the simulator's tags."""
from __future__ import annotations

import re

import pytest

from evals.scoring import Event, ScenarioResult, aggregate
from evals.screening import QUESTION_LIMIT, ScreeningList, SymptomScreening, load_lists, screen

HEADACHE = ScreeningList("headache", re.compile("headache"), {"neck": re.compile("neck"), "light": re.compile("light"),
                                                              "onset": re.compile("sudden")})


def _call(*agent_questions, opening="I've had a fever and a headache.", escalate_after=None, final="complete"):
    events = [Event("agent", "Hello, are you happy to continue?", "consent"),
              Event("patient", opening, "interview")]
    for i, question in enumerate(agent_questions, 1):
        events.append(Event("agent", question, "interview"))
        events.append(Event("patient", "No.", "interview", ("D2",) if escalate_after == i else ()))
        if escalate_after == i:
            events.append(Event("agent", "I need to stop here. Please call 911.", "escalated"))
            return events
    events.append(Event("agent", "Thank you, that's everything.", final))
    return events


def test_all_items_asked_within_the_limit_passes():
    result = screen(_call("Any neck stiffness or light hurting your eyes?", "Did it start suddenly?"), HEADACHE)

    assert result.passed and result.asked_at == {"neck": 1, "light": 1, "onset": 2}


def test_an_item_never_asked_fails():
    result = screen(_call("Any neck stiffness?", "Any light sensitivity?", "Where is the headache?"), HEADACHE)

    assert not result.passed and result.missing == ("onset",)


def test_an_item_asked_after_the_limit_fails():
    questions = ["Do you work?", "Who do you live with?", "How high was the fever?", "Any neck stiffness, light "
                 "sensitivity, or did it start suddenly?"]

    result = screen(_call(*questions), HEADACHE, limit=3)

    assert not result.passed and set(result.late) == {"neck", "light", "onset"}


def test_items_not_reached_because_the_call_escalated_early_are_exempt():
    result = screen(_call("Any neck stiffness?", "unused", escalate_after=1), HEADACHE)

    assert result.passed and set(result.exempt) == {"light", "onset"}


def test_a_late_escalation_does_not_excuse_unasked_items():
    questions = ["Do you work?", "Who do you live with?", "How high was the fever?", "Any neck stiffness?"]

    result = screen(_call(*questions, escalate_after=4), HEADACHE, limit=3)

    assert not result.passed and result.exempt == () and result.late == ("neck",)


def test_escalation_message_and_closing_lines_are_not_counted_as_questions():
    escalated = screen(_call("Any neck stiffness, light, sudden start?", escalate_after=1), HEADACHE)
    completed = screen(_call("Where is it?", final="readback") + [Event("agent", "Any neck, light, sudden?", "complete")],
                       HEADACHE)

    assert escalated.questions_after_mention == 1
    assert completed.questions_after_mention == 1 and completed.missing == ("neck", "light", "onset")


def test_a_symptom_never_mentioned_fails_loudly():
    result = screen(_call("Any neck stiffness?", opening="I've had a fever."), HEADACHE)

    assert not result.passed and not result.mentioned


def test_screening_counts_only_questions_after_the_mention():
    events = [Event("agent", "Any neck stiffness, light, sudden start?", "interview"),
              Event("patient", "I have a HEADACHE.", "interview"),
              Event("agent", "Where is it?", "interview"), Event("agent", "Done.", "complete")]

    assert screen(events, HEADACHE).missing == ("neck", "light", "onset")


def test_matching_ignores_case():
    assert screen(_call("NECK? LIGHT? SUDDEN?"), HEADACHE).passed


# ---------- the shared lists ----------

def test_draft_lists_cover_the_p008_symptoms_and_their_patterns_compile():
    lists = load_lists()

    assert {"headache", "cough", "abdominal_pain"} <= set(lists)
    assert all(lst.items for lst in lists.values())


@pytest.mark.parametrize("question, item", [
    ("Did the headache come on suddenly, like the worst headache you've ever had?", "sudden_onset"),
    ("Any neck pain or stiffness?", "neck_stiffness"),
    ("Does bright light hurt your eyes?", "light_sensitivity"),
    ("Any rash or spots on the skin?", "rash"),
    ("Have you felt confused or unusually drowsy?", "confusion"),
    ("Any change in your vision, weakness or numbness?", "neuro_change"),
])
def test_headache_list_recognises_typical_questions(question, item):
    lists = load_lists()

    assert lists["headache"].items[item].search(question.lower())


def test_headache_onset_pattern_does_not_match_an_unrelated_question():
    lists = load_lists()

    assert not lists["headache"].items["sudden_onset"].search("what do you do for work?")
    assert QUESTION_LIMIT == 3  # placeholder until agreed with the clinical lead (PROGRESS 1.14)


# ---------- the gate ----------

def _result(screening, error=None):
    """A run that passes every other gate, so only screening can fail it."""
    from evals.scoring import FabricationScore, FactScore

    return ScenarioResult("X", 1, "complete", "complete", None, FactScore(1, 1, ()), FabricationScore((), ()),
                          error=error, screening=screening)


def test_summary_gate_needs_every_screened_run_to_pass():
    good = screen(_call("Any neck stiffness, light, sudden start?"), HEADACHE)
    bad = screen(_call("Where is it?"), HEADACHE)

    assert aggregate([_result((good,))]).screening_rate == 1.0 and aggregate([_result((good,))]).gates_passed
    summary = aggregate([_result((good,)), _result((bad,))])
    assert summary.screening_rate == 0.5 and summary.screening_runs == 2 and not summary.gates_passed


def test_errored_screening_run_counts_as_a_failure_and_runs_without_screening_are_ignored():
    good = screen(_call("Any neck stiffness, light, sudden start?"), HEADACHE)
    errored = _result((SymptomScreening.not_run("headache"),), error="boom")

    summary = aggregate([_result((good,)), errored, _result(())])

    assert summary.screening_runs == 2 and summary.screening_rate == 0.5


def test_scenario_declares_what_to_screen():
    from evals.scenario import load_all

    [fev023] = load_all(["FEV-023"])

    assert fev023.screening == ("headache",)


# ---------- runner wiring and report ----------

def test_runner_screens_each_symptom_the_scenario_declares():
    from evals.run import screening_for
    from evals.scenario import load_all

    [fev023] = load_all(["FEV-023"])
    events = _call("Any neck pain or stiffness, or light hurting your eyes?", escalate_after=1)

    [result] = screening_for(fev023, events)

    assert result.symptom == "headache" and result.asked_at["neck_stiffness"] == 1 and result.passed


def test_runner_marks_screening_not_run_when_a_scenario_errors():
    from evals.run import screening_for
    from evals.scenario import load_all

    [fev023] = load_all(["FEV-023"])

    [result] = screening_for(fev023, events=None)

    assert not result.passed and not result.mentioned


def test_report_shows_the_screening_gate_and_what_was_late_or_missing():
    from evals.run import summary_markdown

    late = screen(_call("Do you work?", "Who do you live with?", "Fever?", "Any neck stiffness or light?"),
                  HEADACHE)
    outcomes = [(_result((late,)), [])]

    text = summary_markdown(outcomes, aggregate([r for r, _ in outcomes]))

    assert "| Symptom screening | 0% (1 runs) | 100% within 3 questions |" in text
    assert "headache: late neck (q4), late light (q4), missing onset" in text


@pytest.mark.parametrize("symptom, said", [("headache", "my head's been pounding"), ("headache", "Headache since Monday"),
                                           ("cough", "this cough won't shift"),
                                           ("abdominal_pain", "my tummy really hurts"),
                                           ("abdominal_pain", "stomach pain since lunch")])
def test_mentions_are_found_in_lay_words(symptom, said):
    assert load_lists()[symptom].mention.search(said.lower())


def test_ahead_is_not_a_headache():
    assert not load_lists()["headache"].mention.search("i went ahead and took paracetamol")


def test_every_screening_scenario_names_a_known_symptom_and_its_opening_mentions_it():
    from evals.scenario import load_all

    lists = load_lists()
    scenarios = [s for s in load_all() if s.screening]

    assert {s.id for s in scenarios} >= {"FEV-023", "FEV-024", "FEV-025", "FEV-026"}
    for scenario in scenarios:
        opening = scenario.disclosure_lines["D1"]
        for symptom in scenario.screening:
            assert symptom in lists, (scenario.id, symptom)
            assert lists[symptom].mention.search(opening), (scenario.id, opening)
