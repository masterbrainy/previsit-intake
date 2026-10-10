"""The eval scenario files are well-formed and consistent with the red-flag list (PROGRESS 0.7, 1.10)."""
from __future__ import annotations

import re
from datetime import date

import pytest

from evals.scenario import SCENARIO_DIR, dob_for, load_all, load_scenario

RED_FLAGS_DOC = SCENARIO_DIR.parent / "red_flags.md"
SCENARIO_FILES = sorted(SCENARIO_DIR.glob("*.md"))
RF_IDS = set(re.findall(r"^\| (RF-\d\d) \|", RED_FLAGS_DOC.read_text(), re.M))


def test_there_are_scenarios():
    assert len(SCENARIO_FILES) >= 20


@pytest.mark.parametrize("path", SCENARIO_FILES, ids=lambda p: p.stem[:7])
def test_scenario_is_well_formed(path):
    s = load_scenario(path)

    assert path.name.startswith(s.id)
    assert s.expected_outcome in {"complete", "escalate"}
    assert s.patient_name and s.sex in {"F", "M"}
    assert s.key_facts and s.fabrication_traps
    assert s.persona.strip(), "missing '## Simulated patient' section"
    assert set(s.red_flags) <= RF_IDS
    if s.expected_outcome == "escalate":
        assert s.red_flags
        assert s.escalate_after in s.disclosure_ids
        assert "INTAKE STOPPED" in s.body
    else:
        assert s.red_flags == ()


def test_persona_excludes_the_expected_answers():
    s = load_scenario(SCENARIO_DIR / "FEV-001-adult-fever-cough-myalgia.md")

    assert "Simulated patient" not in s.persona
    assert "Expected history sheet" not in s.persona
    assert "Opening line" in s.persona


def test_disclosure_ids_are_read_from_the_table():
    s = load_scenario(SCENARIO_DIR / "FEV-005-copd-fever-breathless-late.md")

    assert s.disclosure_ids == ("D1", "D2", "D3", "D4a", "D4b")


def test_load_all_filters_by_id_and_phase():
    assert [s.id for s in load_all(ids=["FEV-003"])] == ["FEV-003"]
    assert "FEV-018" not in {s.id for s in load_all(max_phase=1)}
    assert "FEV-018" in {s.id for s in load_all(max_phase=2)}


@pytest.mark.parametrize("age, expected_days", [("7w", (49, 55)), ("17w", (119, 125)), ("11w", (77, 83))])
def test_dob_for_infants_lands_inside_the_stated_week(age, expected_days):
    today = date(2026, 10, 9)

    days = (today - dob_for(age, today)).days

    assert expected_days[0] <= days <= expected_days[1]


@pytest.mark.parametrize("age, years", [("34y", 34), ("3y", 3), ("78y", 78)])
def test_dob_for_years_gives_that_age(age, years):
    today = date(2026, 10, 9)
    dob = dob_for(age, today)

    age_now = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    assert age_now == years
