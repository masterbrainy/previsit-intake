"""P-005 doctor suggestions at booking (H.2) and emergency words in the booking reason (H.8).

Suggestions sit next to the hard rule that nothing medical reaches the patient unapproved, so their reasons may only
quote the patient's own words or say something generic, and general practice is always offered."""
from __future__ import annotations

import re

import pytest

from factories import make_doctor

FIXED_REASONS = {"sees children", "general practice: sees most problems"}


@pytest.fixture
def specialists(session):
    return [
        make_doctor(session, "Dr. Gina General"),
        make_doctor(session, "Dr. Ray Resp", specialty="Respiratory", keywords=("cough", "wheeze", "asthma")),
        make_doctor(session, "Dr. Ella Ent", specialty="ENT", keywords=("cough", "ear", "sore throat")),
        make_doctor(session, "Dr. Ida Infect", specialty="Infectious disease", keywords=("cough", "fever")),
        make_doctor(session, "Dr. Pia Paeds", specialty="Paediatrics", keywords=("fever",)),
        make_doctor(session, "Dr. Max Migraine", specialty="Neurology", keywords=("migraine", "meningitis")),
    ]


def _recommend(session, reason, age=None):
    from previsit.doctors import recommend_doctors

    return recommend_doctors(session, reason, age_years=age)


def _words(text):
    return set(re.findall(r"[a-z0-9']+", text.lower()))


@pytest.mark.parametrize("reason, age", [("cough and fever for 3 days", 40), ("cough, fever, sore ear", 7),
                                         ("cough", 30), ("", 50)])
def test_general_practice_is_always_among_the_suggestions(session, specialists, reason, age):
    names = [r.doctor.name for r in _recommend(session, reason, age)]

    assert "Dr. Gina General" in names, names


@pytest.mark.parametrize("reason", ["cough and fever, worried it's asthma or meningitis", "fever and a bad headache",
                                    "my ear hurts"])
def test_reasons_only_quote_the_patients_words_or_say_something_generic(session, specialists, reason):
    said = _words(reason)
    for rec in _recommend(session, reason, 30):
        for text in rec.reasons:
            quoted = text.removeprefix("sees ")
            assert text in FIXED_REASONS or _words(quoted) <= said, (rec.doctor.name, text)


def test_a_condition_the_patient_never_said_is_never_shown(session, specialists):
    texts = " ".join(t for rec in _recommend(session, "fever and a stiff, sore head", 30) for t in rec.reasons)

    assert "meningitis" not in texts.lower() and "migraine" not in texts.lower()


def test_children_are_offered_paediatrics_and_adults_are_not(session, specialists):
    child = [r.doctor.specialty for r in _recommend(session, "fever", 5)]
    adult = [r.doctor.specialty for r in _recommend(session, "fever", 40)]

    assert child[0] == "Paediatrics" and "Paediatrics" not in adult


# ---------- emergency words (H.8) ----------

@pytest.mark.parametrize("reason", ["Chest pain since this morning", "stiff neck and fever", "I want to kill myself",
                                    "she had a seizure", "he FAINTED at school",
                                    "he had a fit this morning"])
def test_emergency_words_are_caught(reason):
    from previsit.doctors import urgent_words_in

    assert urgent_words_in(reason)


@pytest.mark.parametrize("reason", ["fitness check before a marathon", "benefits form", "heartburn after meals"])
def test_ordinary_words_do_not_trigger_the_emergency_script(reason):
    """A false alarm here shows the full emergency script to someone booking a routine visit."""
    from previsit.doctors import urgent_words_in

    assert urgent_words_in(reason) == []
