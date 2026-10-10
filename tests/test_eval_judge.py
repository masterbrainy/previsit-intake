"""Judge result handling (PROGRESS 1.10), using a fake judge LLM."""
from __future__ import annotations

from evals.judge import judge_sheet
from factories import make_fake_llm

FACTS = ("Fever for 1 day", "Stiff neck", "Photophobia")
TRAPS = ("Rash",)


def _judge(mentioned, present):
    verdicts = [{"index": i, "present": p, "mentioned_in_transcript": m, "note": ""}
                for i, (m, p) in enumerate(zip(mentioned, present))]
    return make_fake_llm(judge_sheet=lambda s, m: {"facts": verdicts, "traps": [
        {"index": 0, "present": False, "mentioned_in_transcript": False, "note": ""}]})


def test_complete_scenario_counts_every_fact():
    llm = _judge(mentioned=(True, True, False), present=(True, True, False))

    score, traps = judge_sheet(llm, "sheet", "transcript", FACTS, TRAPS, only_mentioned=False)

    assert (score.correct, score.total) == (2, 3)
    assert score.missed == ("Photophobia",)
    assert traps == ()


def test_escalated_scenario_ignores_facts_never_said_before_the_stop():
    llm = _judge(mentioned=(True, True, False), present=(True, True, False))

    score, _ = judge_sheet(llm, "sheet", "transcript", FACTS, TRAPS, only_mentioned=True)

    assert (score.correct, score.total) == (2, 2)
    assert score.missed == ()


def test_a_mentioned_fact_missing_from_the_sheet_still_counts_as_missed():
    llm = _judge(mentioned=(True, True, True), present=(True, False, True))

    score, _ = judge_sheet(llm, "sheet", "transcript", FACTS, TRAPS, only_mentioned=True)

    assert (score.correct, score.total) == (2, 3)
    assert score.missed == ("Stiff neck",)


def test_simulator_disclosures_are_limited_to_the_scenario_table():
    from datetime import date

    from evals.scenario import SCENARIO_DIR, load_scenario
    from evals.simulator import SimulatedPatient

    scenario = load_scenario(SCENARIO_DIR / "FEV-003-fever-headache-stiff-neck.md")
    llm = make_fake_llm(sim_patient=lambda s, m: {"utterance": "hi", "disclosed": ["D2", "D9", "D"], "hang_up": False})

    said = SimulatedPatient(llm, scenario, date(2007, 8, 10)).reply("Hello")

    assert said.disclosed == ["D2"]


def test_support_judge_sees_the_patient_record():
    from evals.judge import judge_support

    llm = make_fake_llm(judge_support=lambda s, m: {"statements": [{"index": 0, "supported": True, "note": ""}]})

    judge_support(llm, "[1] PATIENT: hi", ["[particulars] 34-year-old woman (cites turns [1])"],
                  record="Patient: Meera Shah, 34 years old, sex F")

    assert "Meera Shah, 34 years old" in llm.calls[0]["messages"][0]["content"]
