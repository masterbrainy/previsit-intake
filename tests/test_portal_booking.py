"""Patient self-registration and self-booking (P-004, PRD §8.10, PROGRESS PB.1): limits, identity and isolation."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from factories import (CRISIS_LINE, EMERGENCY_NUMBER, all_rows, doctor_sign_in, make_appointment, make_patient, make_rec, portal_client,
                       sign_in_with_code)

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


# ---------- hard rules hold on a self-booked visit ----------

def test_unapproved_rec_never_shows_on_a_self_booked_visit(new_user, doctor, session):
    from previsit import approval

    patient_id = _patient_id(_register(new_user))
    page_path = _book(new_user, doctor, patient_id).headers["location"]
    [appointment] = _appointments(session)
    rec = make_rec(session, appointment, name="ZZ-SELF-BOOKED-REC")

    assert "ZZ-SELF-BOOKED-REC" not in new_user.get(page_path).text

    approval.decide(session, rec.id, doctor.email, approval.Decision.APPROVE)
    session.commit()
    assert "ZZ-SELF-BOOKED-REC" not in new_user.get(page_path).text, "approved but not yet sent"

    approval.notify_patient_of_approved(session, appointment.id, doctor.email)
    session.commit()
    assert "ZZ-SELF-BOOKED-REC" in new_user.get(page_path).text, "control: once sent, the patient sees it"


# ---------- emergency words in the booking reason (P-005 adjustment 2, H.8) ----------

URGENT_REASON = "chest pain since this morning"


def _doctors_step(client, patient_id, reason):
    return client.post("/portal/book/doctors", data={"patient_id": patient_id, "reason": reason})


def test_emergency_words_show_the_full_emergency_script(new_user):
    from previsit.safety.escalation import booking_emergency_message

    patient_id = _patient_id(_register(new_user))

    page = _doctors_step(new_user, patient_id, URGENT_REASON).text

    script = booking_emergency_message(new_user.app.state.settings)
    assert EMERGENCY_NUMBER in script and script.replace("'", "&#39;") in page
    assert 'role="alert"' in page and 'name="urgent_ack"' in page


def test_ordinary_reason_shows_no_emergency_script(new_user):
    patient_id = _patient_id(_register(new_user))

    page = _doctors_step(new_user, patient_id, "fever for three days").text

    assert EMERGENCY_NUMBER not in page and 'name="urgent_ack"' not in page


def test_suicide_risk_words_at_booking_give_the_crisis_line(new_user):
    """Same rule as the intake's suicide-risk escalation (evals/red_flags.md): the crisis line is always given."""
    patient_id = _patient_id(_register(new_user))

    page = _doctors_step(new_user, patient_id, "I want to kill myself").text

    assert EMERGENCY_NUMBER in page and CRISIS_LINE in page


def test_urgent_booking_needs_the_acknowledgement(new_user, doctor, session):
    patient_id = _patient_id(_register(new_user))
    data = {"patient_id": patient_id, "doctor_id": doctor.id, "scheduled_at": _when(days=2), "reason": URGENT_REASON}

    assert new_user.post("/portal/book", data=data).status_code == 422
    assert _appointments(session) == []


def test_acknowledged_urgent_booking_is_audited_and_raises_no_staff_alert(new_user, doctor, session):
    from previsit.models import AuditEvent, StaffAlert

    patient_id = _patient_id(_register(new_user))
    data = {"patient_id": patient_id, "doctor_id": doctor.id, "scheduled_at": _when(days=2), "reason": URGENT_REASON,
            "urgent_ack": "yes"}

    assert new_user.post("/portal/book", data=data).status_code == 303

    [appointment] = _appointments(session)
    acks = [e for e in all_rows(session, AuditEvent) if e.action == "booking.emergency_advice_acknowledged"]
    assert [e.entity_id for e in acks] == [appointment.id]
    assert all_rows(session, StaffAlert) == []  # a keyword alone never alerts staff
