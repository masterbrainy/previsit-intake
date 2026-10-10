"""Smoke test: the eval runner drives IntakeEngine end to end with fake LLMs (no API calls)."""
from __future__ import annotations

from datetime import date

from evals.run import run_scenario
from evals.scenario import SCENARIO_DIR, dob_for, load_scenario
from factories import interview, make_fake_llm, safety

TODAY = date(2026, 10, 9)
FEV_003 = load_scenario(SCENARIO_DIR / "FEV-003-fever-headache-stiff-neck.md")


def _scripted(lines):
    """A fake simulated patient that says each (utterance, disclosed) in turn, then repeats the last."""
    queue = list(lines)

    def handler(system, messages):
        utterance, disclosed = queue.pop(0) if len(queue) > 1 else queue[0]
        return {"utterance": utterance, "disclosed": list(disclosed), "hang_up": False}

    return handler


def _system_llm():
    def detect(system, messages):
        latest = messages[-1]["content"].lower()
        return safety("red_flag", ("RF-07",), "stiff neck") if "stiff" in latest else safety()

    return make_fake_llm(
        safety=detect,
        identity=lambda s, m: {"full_name": FEV_003.patient_name,
                               "date_of_birth": dob_for(FEV_003.age, TODAY).isoformat(), "informant": "self"},
        interview=lambda s, m: interview("Can you tell me more about that?"),
    )


def _judge_llm():
    return make_fake_llm(
        judge_sheet=lambda s, m: {"facts": [], "traps": []},
        judge_support=lambda s, m: {"statements": []},
    )


def test_runner_scores_an_escalation_scenario(tmp_path, settings):
    sim = make_fake_llm(sim_patient=_scripted([
        ("Yes, that's fine.", ()),
        (f"{FEV_003.patient_name}, born {dob_for(FEV_003.age, TODAY).isoformat()}.", ()),
        ("I've had a really bad headache and a temperature since yesterday.", ("D1",)),
        ("My neck's really stiff too, it hurts to put my chin down.", ("D2",)),
        ("Seriously? Can't I just wait for the appointment?", ()),
    ]))

    result, events = run_scenario(FEV_003, _system_llm(), sim, _judge_llm(), settings,
                                  db_url=f"sqlite:///{tmp_path / 'eval.db'}", today=TODAY)

    assert result.error is None, result.error
    assert result.final_state == "escalated"
    assert result.red_flag.passed and result.red_flag.rf_label_match
    assert any(e.speaker == "patient" and "D2" in e.disclosed for e in events)
