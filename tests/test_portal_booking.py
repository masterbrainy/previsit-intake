"""Patient self-registration and self-booking (P-004, PRD §8.10, PROGRESS PB.1): limits, identity and isolation."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from factories import all_rows, doctor_sign_in, make_appointment, make_patient, portal_client, sign_in_with_code

NEW_PHONE, CLINIC_PHONE = "+15551230001", "+15551230002"
DOB = "1988-04-02"


def _when(**delta) -> str:
    return (datetime.now() + timedelta(**delta)).strftime("%Y-%m-%dT%H:%M")


@pytest.fixture
def new_user(settings, llm):
    client = portal_client(settings, llm)
    sign_in_with_code(client, NEW_PHONE)
    return client


def _register(client, name="Rosa Diaz", dob=DOB, sex="F"):
    return client.post("/portal/people/new", data={"name": name, "dob": dob, "sex": sex})


def _patient_id(response) -> int:
    return int(response.headers["location"].split("patient_id=")[1])


def _book(client, doctor, patient_id, when=None, doctor_id=None):
    return client.post("/portal/book", data={"patient_id": patient_id, "scheduled_at": when or _when(days=2),
                                             "doctor_id": doctor_id or doctor.id, "reason": "fever"})


def _appointments(session):
    from previsit.models import Appointment

    return all_rows(session, Appointment)


# ---------- a new contact ----------

def test_a_new_contact_signs_in_to_an_empty_portal_and_is_sent_to_set_up(new_user):
    assert "/portal/appointments/" not in new_user.get("/portal").text
    response = new_user.get("/portal/book")

    assert response.status_code == 303 and response.headers["location"] == "/portal/people/new"


def test_self_registered_patient_is_flagged_and_can_book(new_user, doctor, session):
    from previsit.models import Patient

    patient_id = _patient_id(_register(new_user))
    response = _book(new_user, doctor, patient_id)

    patient = session.get(Patient, patient_id)
    session.refresh(patient)
    [appointment] = _appointments(session)
    assert response.status_code == 303 and patient.self_registered and patient.phone == NEW_PHONE
    assert appointment.booked_by == "patient" and appointment.doctor_id == doctor.id
    assert new_user.get(response.headers["location"]).status_code == 200


def test_doctor_sees_booked_by_patient_and_unchecked_identity(new_user, settings, session, doctor):
    patient_id = _patient_id(_register(new_user))
    _book(new_user, doctor, patient_id)
    [appointment] = _appointments(session)
    doctor_client = portal_client(settings, None)
    doctor_sign_in(doctor_client, session, doctor)

    page = doctor_client.get(f"/patients/{appointment.id}").text

    assert "booked by patient" in page and "identity not checked by clinic" in page


@pytest.mark.parametrize("name, dob", [("Rosa", DOB), ("Rosa Diaz", "2999-01-01"), ("Rosa Diaz", "1800-01-01"),
                                       ("Rosa Diaz", "not a date")])
def test_bad_person_details_are_refused(new_user, session, name, dob):
    from previsit.models import Patient

    assert _register(new_user, name=name, dob=dob).status_code == 422
    assert all_rows(session, Patient) == []


# ---------- identity and isolation ----------

def test_registering_as_someone_elses_name_and_dob_gives_no_access_to_them(settings, llm, session):
    """A stranger types an existing patient's name and DOB: they get a separate, self-registered record and nothing else."""
    victim = make_patient(session, name="Ana Silva", dob=date(1990, 5, 1), phone=CLINIC_PHONE)
    victim_appt = make_appointment(session, patient=victim)
    stranger = portal_client(settings, llm)
    sign_in_with_code(stranger, NEW_PHONE)

    new_id = _patient_id(_register(stranger, name="Ana Silva", dob="1990-05-01"))

    assert new_id != victim.id
    assert stranger.get(f"/portal/appointments/{victim_appt.id}").status_code == 404
    assert f"/portal/appointments/{victim_appt.id}" not in stranger.get("/portal").text


def test_clinic_registered_patient_is_not_flagged_when_they_add_themselves_again(settings, llm, session):
    from previsit.models import Patient

    patient = make_patient(session, name="Ana Silva", dob=date(1990, 5, 1), phone=CLINIC_PHONE)
    make_appointment(session, patient=patient)
    client = portal_client(settings, llm)
    sign_in_with_code(client, CLINIC_PHONE)

    same_id = _patient_id(_register(client, name="Ana Silva", dob="1990-05-01"))

    session.refresh(patient)
    assert same_id == patient.id and not patient.self_registered


def test_cannot_book_for_a_patient_on_someone_elses_contact(new_user, doctor, session):
    other = make_patient(session, name="Ana Silva", phone=CLINIC_PHONE)
    _register(new_user)

    assert _book(new_user, doctor, other.id).status_code == 422
    assert _appointments(session) == []


# ---------- booking limits ----------

@pytest.mark.parametrize("when", [_when(hours=-1), _when(days=366)])
def test_booking_must_be_in_the_future_and_within_a_year(new_user, doctor, session, when):
    patient_id = _patient_id(_register(new_user))

    assert _book(new_user, doctor, patient_id, when=when).status_code == 422
    assert _appointments(session) == []


def test_booking_needs_a_listed_doctor(new_user, doctor, session):
    patient_id = _patient_id(_register(new_user))

    assert _book(new_user, doctor, patient_id, doctor_id=doctor.id + 999).status_code == 422
    assert _appointments(session) == []


def test_at_most_five_upcoming_bookings_per_patient(new_user, doctor, session):
    patient_id = _patient_id(_register(new_user))
    for day in range(1, 6):
        assert _book(new_user, doctor, patient_id, when=_when(days=day)).status_code == 303

    assert _book(new_user, doctor, patient_id, when=_when(days=6)).status_code == 422
    assert len(_appointments(session)) == 5


def test_cross_site_booking_post_is_blocked(new_user, doctor, session):
    patient_id = _patient_id(_register(new_user))

    response = new_user.post("/portal/book", headers={"Origin": "http://evil.example"},
                             data={"patient_id": patient_id, "scheduled_at": _when(days=2), "doctor_id": doctor.id})

    assert response.status_code == 403 and _appointments(session) == []
