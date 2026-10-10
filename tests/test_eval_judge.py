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
    said = "My neck's really stiff too, it hurts to put my chin down. And the light's bothering my eyes."
    llm = make_fake_llm(sim_patient=lambda s, m: {"utterance": said, "disclosed": ["D2", "D9", "D"], "hang_up": False})

    said = SimulatedPatient(llm, scenario, date(2007, 8, 10)).reply("Hello")

    assert said.disclosed == ["D2"]


def test_support_judge_sees_the_patient_record():
    from evals.judge import judge_support

    llm = make_fake_llm(judge_support=lambda s, m: {"statements": [{"index": 0, "supported": True, "note": ""}]})

    judge_support(llm, "[1] PATIENT: hi", ["[particulars] 34-year-old woman (cites turns [1])"],
                  record="Patient: Meera Shah, 34 years old, sex F")

    assert "Meera Shah, 34 years old" in llm.calls[0]["messages"][0]["content"]


def test_judge_sees_the_record_header_the_physician_sees():
    from datetime import date

    from evals.run import record_header

    header = record_header("Ada Okoye", date(2026, 7, 21), "F", "father", today=date(2026, 10, 9))

    assert "Ada Okoye" in header and "11 weeks" in header and "father" in header.lower()


def test_simulator_denies_unscripted_symptoms_but_not_unscripted_details():
    from evals.simulator import SYSTEM_PROMPT

    assert "answer no" in SYSTEM_PROMPT.lower()
    assert "don't know" in SYSTEM_PROMPT


def test_judge_header_comes_from_the_sheet_record_when_present():
    from datetime import date

    from evals.run import judge_header
    from previsit.sheet.schema import HistorySheet

    sheet = HistorySheet(record={"name": "Ada Okoye", "age": "11 weeks", "sex": "F", "informant": "father"})

    header = judge_header(sheet, fallback="FALLBACK")

    assert "11 weeks" in header and "father" in header and "FALLBACK" not in header
    assert judge_header(HistorySheet(), fallback="FALLBACK") == "FALLBACK"


def _sim(scenario_file, handler):
    from datetime import date

    from evals.scenario import SCENARIO_DIR, load_scenario
    from evals.simulator import SimulatedPatient

    return SimulatedPatient(make_fake_llm(sim_patient=handler), load_scenario(SCENARIO_DIR / scenario_file),
                            date(2026, 7, 21))


def test_simulator_cannot_hang_up_unless_the_scenario_says_so():
    hang = lambda s, m: {"utterance": "bye", "disclosed": [], "hang_up": True}

    assert _sim("FEV-021-infant-4-months-boundary.md", hang).reply("Any rash?").hang_up is False
    assert _sim("FEV-017-pregnant-bleeding-call-drops.md", hang).reply("Any bleeding?").hang_up is True


def test_simulator_is_told_the_exact_date_of_birth_to_give():
    sim = _sim("FEV-022-infant-11-weeks-feels-hot.md", lambda s, m: {"utterance": "x", "disclosed": [], "hang_up": False})
    sim.reply("Name and date of birth?")

    assert "date of birth exactly as 2026-07-21" in sim._system


def test_a_disclosure_tag_only_counts_if_the_reply_contains_that_line():
    """The simulator has tagged a bare "No." as the read-back faint (FEV-013), which made a timely escalation look late."""
    tag = lambda text: lambda s, m: {"utterance": text, "disclosed": ["D2"], "hang_up": False}

    plain = _sim("FEV-013-faint-disclosed-at-read-back.md", tag("No.")).reply("Any travel?")
    real = _sim("FEV-013-faint-disclosed-at-read-back.md",
                tag("Oh, actually, I passed out in the bathroom this morning, just for a second.")).reply("Is that right?")

    assert plain.disclosed == [] and real.disclosed == ["D2"]


def test_disclosure_lines_are_read_from_the_table():
    from evals.scenario import SCENARIO_DIR, load_scenario

    lines = load_scenario(SCENARIO_DIR / "FEV-003-fever-headache-stiff-neck.md").disclosure_lines

    assert "neck" in lines["D2"].lower() and set(lines) == {"D1", "D2"}
