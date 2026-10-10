"""Scene checks for the demo scripts (PROGRESS D.3): every scene the video needs must be reachable."""
from __future__ import annotations

from evals.demo_check import Snapshot, check_full_flow, check_red_flag
from evals.scoring import Event


def _events(*states):
    return [Event("agent", f"agent says ({s})", s) for s in states]


GOOD_SHEET = {
    "chief_complaints": [{"complaint": "Fever", "duration": "4 days"}, {"complaint": "Cough", "duration": "3 days"}],
    "could_not_answer": [{"text": "Mother's age at diagnosis", "source_turn_ids": [9]}],
    "red_flag_screen": [{"text": "No chest pain", "source_turn_ids": [12]}],
    "partial": False,
}


def _full_snapshot(**overrides):
    base = dict(sheet=GOOD_SHEET, findings={"fever_duration_days": 4}, recs=[("Complete blood count (CBC)", "suggested")],
                message_kinds=["general_recs"], red_flags=[], staff_alerts=0, final_agent_text="... call 999-TEST ...")
    return Snapshot(**{**base, **overrides})


FULL_STATES = ("consent", "identity") + ("interview",) * 6 + ("readback", "complete")


def test_full_flow_passes_when_every_scene_is_present():
    assert check_full_flow(_events(*FULL_STATES), _full_snapshot(), "999-TEST") == []


def test_full_flow_fails_without_a_cbc_suggestion():
    problems = check_full_flow(_events(*FULL_STATES), _full_snapshot(recs=[]), "999-TEST")

    assert any("CBC" in p for p in problems)


def test_full_flow_fails_if_a_medical_message_reached_the_patient():
    problems = check_full_flow(_events(*FULL_STATES), _full_snapshot(message_kinds=["general_recs", "medical"]),
                               "999-TEST")

    assert any("medical" in p.lower() for p in problems)


def test_full_flow_fails_without_could_not_answer_items():
    sheet = {**GOOD_SHEET, "could_not_answer": []}

    assert any("could not answer" in p.lower() for p in
               check_full_flow(_events(*FULL_STATES), _full_snapshot(sheet=sheet), "999-TEST"))


def test_red_flag_passes_on_a_clean_stop():
    snap = Snapshot(sheet=None, findings={}, recs=[], message_kinds=["escalation"], red_flags=["RF-07"],
                    staff_alerts=1, final_agent_text="Please call 999-TEST now.")

    assert check_red_flag(_events("consent", "identity", "interview", "escalated"), snap, "999-TEST") == []


def test_red_flag_fails_if_advice_or_tests_were_generated():
    snap = Snapshot(sheet=None, findings={}, recs=[("CBC", "suggested")], message_kinds=["escalation", "general_recs"],
                    red_flags=["RF-07"], staff_alerts=1, final_agent_text="Please call 999-TEST now.")

    problems = check_red_flag(_events("interview", "escalated"), snap, "999-TEST")

    assert len(problems) == 2
