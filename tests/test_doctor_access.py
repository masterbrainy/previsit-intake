"""P-005 (PROGRESS H.9): a doctor reaches only patients they are assigned to or were referred to; patient and doctor
sessions never stand in for each other; staff basic auth opens the hospital overview, which carries no clinical text."""
from __future__ import annotations

import re

import pytest

from factories import (DOCTOR_COOKIE, TEST_PHYSICIAN, all_rows, doctor_sign_in, make_appointment, make_doctor,
                       make_intake, make_patient, make_rec, portal_client, portal_sign_in)

PDF = b"%PDF-1.4\n%test\n"
# Clinical text planted in the patient's record. None of it may appear on the overview or reach another doctor.
MARKERS = {"rec": "ZZREC-MARKER", "turn": "ZZTURN-MARKER", "symptom": "ZZSYMPTOM-MARKER",
           "evidence": "ZZEVIDENCE-MARKER", "result": "zzresult-marker.pdf"}
PATIENT_NAME = "Pat Hospital"
SIGN_IN = "/doctor/sign-in"


class Hospital:
    """Doctors A, B and C; one patient who is booked with A only, with a full clinical record."""

    def __init__(self, session, tmp_path):
        from previsit.models import LabResult, RedFlagEvent, Speaker, StaffAlert, SymptomLog, Turn

        self.a = make_doctor(session, "Dr. Ada Alpha")
        self.b = make_doctor(session, "Dr. Ben Beta")
        self.c = make_doctor(session, "Dr. Cy Gamma")
        self.patient = make_patient(session, PATIENT_NAME, phone="+15550001111")
        self.appt = make_appointment(session, self.patient, doctor=self.a)
        intake = make_intake(session, self.appt, "COMPLETE")
        self.rec = make_rec(session, self.appt, name=MARKERS["rec"])
        pdf = tmp_path / "uploads" / str(self.appt.id) / "result.pdf"  # inside upload_dir, as results.py stores it
        pdf.parent.mkdir(parents=True)
        pdf.write_bytes(PDF)
        self.alert = StaffAlert(appointment_id=self.appt.id, title="Emergency escalation", body="call the patient")
        self.result = LabResult(appointment_id=self.appt.id, filename=MARKERS["result"], stored_path=str(pdf),
                                content_type="application/pdf", size_bytes=len(PDF), uploaded_by="patient")
        session.add_all([
            Turn(intake_id=intake.id, seq=1, speaker=Speaker.PATIENT, text=MARKERS["turn"]),
            SymptomLog(appointment_id=self.appt.id, metric="temperature", value=38.4, unit="C",
                       note=MARKERS["symptom"]),
            RedFlagEvent(appointment_id=self.appt.id, intake_id=intake.id, rf_ids=["RF-01"],
                         evidence=MARKERS["evidence"]),
            self.alert, self.result,
        ])
        session.commit()
        for row in (self.alert, self.result):
            session.refresh(row)

    def requests(self) -> dict[str, tuple[str, str, dict | None]]:
        """Every clinical route, keyed by name: (method, path, form)."""
        appt = self.appt.id
        return {
            "detail": ("GET", f"/patients/{appt}", None),
            "print": ("GET", f"/patients/{appt}/print", None),
            "patient preview": ("GET", f"/patients/{appt}/patient-view", None),
            "result download": ("GET", f"/results/{self.result.id}", None),
            "decide": ("POST", f"/recs/{self.rec.id}/decide", {"decision": "approve"}),
            "add rec": ("POST", f"/appointments/{appt}/recs/add", {"name": "Chest X-ray"}),
            "notify": ("POST", f"/appointments/{appt}/notify", {}),
            "ack alert": ("POST", f"/alerts/{self.alert.id}/ack", {}),
            "refer": ("POST", f"/patients/{appt}/refer", {"to_doctor_id": str(self.c.id), "note": "please see"}),
        }


ROUTES = ["detail", "print", "patient preview", "result download", "decide", "add rec", "notify", "ack alert", "refer"]
PAGES = ["detail", "print", "patient preview", "result download"]


@pytest.fixture
def hospital(session, tmp_path):
    return Hospital(session, tmp_path)


@pytest.fixture
def client(settings, llm, tmp_path):
    return portal_client(settings.model_copy(update={"upload_dir": tmp_path / "uploads"}), llm)


def _call(client, request, **kwargs):
    method, path, form = request
    return client.get(path, **kwargs) if method == "GET" else client.post(path, data=form, **kwargs)


def _nothing_changed(session, hospital):
    from previsit.models import MedicalRecommendation, PatientMessage, RecStatus, Referral, StaffAlert

    session.expire_all()
    assert [r.name for r in all_rows(session, MedicalRecommendation)] == [MARKERS["rec"]]
    assert session.get(MedicalRecommendation, hospital.rec.id).status == RecStatus.SUGGESTED
    assert session.get(StaffAlert, hospital.alert.id).acknowledged_at is None
    assert all_rows(session, PatientMessage) == [] and all_rows(session, Referral) == []


# ---------- per-patient access ----------

@pytest.mark.parametrize("page", PAGES)
def test_assigned_doctor_opens_the_patients_pages(client, session, hospital, page):
    doctor_sign_in(client, session, hospital.a)

    response = _call(client, hospital.requests()[page])

    assert response.status_code == 200
    if page == "detail":
        assert MARKERS["rec"] in response.text and MARKERS["turn"] in response.text


@pytest.mark.parametrize("route", ROUTES)
def test_other_doctor_gets_404_on_every_clinical_route(client, session, hospital, route):
    doctor_sign_in(client, session, hospital.b)

    response = _call(client, hospital.requests()[route])

    assert response.status_code == 404
    assert not any(marker in response.text for marker in MARKERS.values())
    _nothing_changed(session, hospital)


@pytest.mark.parametrize("route", ROUTES)
def test_signed_out_goes_to_doctor_sign_in(client, session, hospital, route):
    response = _call(client, hospital.requests()[route])

    assert response.status_code == 303 and response.headers["location"].startswith(SIGN_IN)
    _nothing_changed(session, hospital)


@pytest.mark.parametrize("route", ROUTES)
def test_staff_basic_auth_alone_opens_no_clinical_route_except_alert_ack(client, session, hospital, physician_auth,
                                                                          route):
    response = _call(client, hospital.requests()[route], auth=physician_auth)

    if route == "ack alert":  # P-005 adjustment 3: staff acknowledge emergencies for every patient
        assert response.status_code in (200, 303)
        return
    assert response.status_code == 303 and response.headers["location"].startswith(SIGN_IN)
    _nothing_changed(session, hospital)


def test_unknown_and_forbidden_ids_look_the_same(client, session, hospital):
    """No enumeration: another doctor's patient and a patient who doesn't exist give the same answer."""
    doctor_sign_in(client, session, hospital.b)

    forbidden = client.get(f"/patients/{hospital.appt.id}")
    missing = client.get(f"/patients/{hospital.appt.id + 999}")

    assert forbidden.status_code == missing.status_code == 404
    assert forbidden.text == missing.text


def test_access_is_per_patient_not_per_appointment(client, session, hospital):
    """Booked with B for a later visit: B sees the patient's earlier visit with A too (PRD §8.11 per-patient access)."""
    make_appointment(session, hospital.patient, doctor=hospital.b)
    doctor_sign_in(client, session, hospital.b)

    assert client.get(f"/patients/{hospital.appt.id}").status_code == 200


def test_my_patients_lists_only_my_own(client, session, hospital):
    doctor_sign_in(client, session, hospital.a)
    assert PATIENT_NAME in client.get("/doctor").text

    doctor_sign_in(client, session, hospital.b)
    page = client.get("/doctor")
    assert page.status_code == 200 and PATIENT_NAME not in page.text


# ---------- referrals ----------

def test_referral_gives_the_receiving_doctor_access_and_no_one_else(client, session, hospital):
    from previsit.models import AuditEvent, Referral

    doctor_sign_in(client, session, hospital.a)
    response = client.post(f"/patients/{hospital.appt.id}/refer",
                           data={"to_doctor_id": str(hospital.b.id), "note": "please review"})
    assert response.status_code == 303

    [referral] = all_rows(session, Referral)
    assert (referral.from_doctor_id, referral.to_doctor_id, referral.patient_id) == (
        hospital.a.id, hospital.b.id, hospital.patient.id)
    assert any(e.action == "patient.referred" and e.actor == hospital.a.email for e in all_rows(session, AuditEvent))

    doctor_sign_in(client, session, hospital.b)
    assert client.get(f"/patients/{hospital.appt.id}").status_code == 200
    assert PATIENT_NAME in client.get("/doctor").text

    doctor_sign_in(client, session, hospital.c)
    assert client.get(f"/patients/{hospital.appt.id}").status_code == 404


def test_doctor_without_access_cannot_refer(session, hospital):
    from previsit.doctors import ReferralError, refer
    from previsit.models import Referral

    with pytest.raises(ReferralError):
        refer(session, hospital.b, hospital.c.id, hospital.patient.id, "let me in")
    assert all_rows(session, Referral) == []


@pytest.mark.parametrize("target", ["self", "missing"])
def test_referral_needs_another_real_doctor(session, hospital, target):
    from previsit.doctors import ReferralError, refer

    to_id = hospital.a.id if target == "self" else hospital.c.id + 999
    with pytest.raises(ReferralError):
        refer(session, hospital.a, to_id, hospital.patient.id, "")


def test_a_referred_doctor_cannot_be_used_to_refer_onwards_without_access(client, session, hospital):
    """C was never referred: C's refer POST is a 404 and gives nobody access."""
    doctor_sign_in(client, session, hospital.c)

    response = client.post(f"/patients/{hospital.appt.id}/refer",
                           data={"to_doctor_id": str(hospital.c.id), "note": ""})

    assert response.status_code == 404
    _nothing_changed(session, hospital)


# ---------- sessions don't stand in for each other ----------

def test_patient_session_opens_no_doctor_route(client, session, hospital, settings):
    portal_sign_in(client, session, settings, hospital.appt)

    assert client.get("/doctor").status_code == 303
    assert client.get(f"/patients/{hospital.appt.id}").status_code == 303


def test_patient_token_in_the_doctor_cookie_is_refused(client, session, hospital, settings):
    from previsit.portal import auth

    token = auth.start_session(session, hospital.a.email, 8)  # a *patient* session for the doctor's address
    session.commit()
    client.cookies.set(DOCTOR_COOKIE, token)

    assert client.get(f"/patients/{hospital.appt.id}").status_code == 303


def test_doctor_session_opens_no_portal_page(client, session, hospital):
    from previsit.web.portal import COOKIE

    token = doctor_sign_in(client, session, hospital.a)
    client.cookies.set(COOKIE, token)  # and the same token in the portal cookie

    response = client.get(f"/portal/appointments/{hospital.appt.id}")

    assert response.status_code in (303, 404)
    assert MARKERS["rec"] not in response.text


def test_a_patient_code_does_not_sign_in_a_doctor(session, hospital):
    from previsit.portal import auth

    key = b"k" * 32
    code = auth.request_code(session, key, hospital.a.email, "1.2.3.4").code  # role="patient"

    with pytest.raises(auth.SignInError):
        auth.verify_code(session, key, hospital.a.email, code, role="doctor")
    auth.verify_code(session, key, hospital.a.email, code)  # control: the code is good for what it was issued for


def test_sign_out_ends_the_doctor_session(client, session, hospital):
    doctor_sign_in(client, session, hospital.a)
    assert client.post("/doctor/sign-out").status_code == 303

    assert client.get(f"/patients/{hospital.appt.id}").status_code == 303


def test_doctor_signs_in_with_a_one_time_code(client, session, hospital):
    assert hospital.a.name in client.get(SIGN_IN).text

    page = client.post("/doctor/code", data={"doctor_id": str(hospital.a.id)}).text
    match = re.search(r'class="mono code">\s*(\d{6})', page)
    assert match, "demo mode should show the code"
    bad = "000000" if match.group(1) != "000000" else "111111"
    assert DOCTOR_COOKIE not in client.post("/doctor/verify", data={"doctor_id": str(hospital.a.id), "code": bad}
                                            ).headers.get("set-cookie", "")

    response = client.post("/doctor/verify", data={"doctor_id": str(hospital.a.id), "code": match.group(1)})

    cookie = response.headers.get("set-cookie", "")
    assert response.status_code == 303 and response.headers["location"] == "/doctor"
    assert DOCTOR_COOKIE in cookie and "httponly" in cookie.lower()
    assert client.get(f"/patients/{hospital.appt.id}").status_code == 200


# ---------- approvals name the doctor ----------

def test_decision_is_recorded_with_the_signed_in_doctor(client, session, hospital):
    from previsit.models import AuditEvent, MedicalRecommendation, RecStatus

    doctor_sign_in(client, session, hospital.a)
    assert client.post(f"/recs/{hospital.rec.id}/decide", data={"decision": "approve"}).status_code == 303

    session.expire_all()
    rec = session.get(MedicalRecommendation, hospital.rec.id)
    assert rec.status == RecStatus.APPROVED and rec.decided_by == hospital.a.email
    actors = {e.actor for e in all_rows(session, AuditEvent) if e.entity_id == rec.id}
    assert hospital.a.email in actors and TEST_PHYSICIAN not in actors


# ---------- hospital overview ----------

def test_overview_shows_who_and_when_but_no_clinical_text(client, session, hospital, physician_auth):
    page = client.get("/dashboard", auth=physician_auth)

    assert page.status_code == 200
    assert PATIENT_NAME in page.text and hospital.a.name in page.text
    leaked = [name for name, marker in MARKERS.items() if marker in page.text]
    assert leaked == []


def test_staff_see_and_acknowledge_emergencies_with_no_doctor_signed_in(client, session, hospital, physician_auth):
    """P-005 adjustment 3: an alert never depends on one doctor being signed in."""
    from previsit.models import StaffAlert

    page = client.get("/dashboard", auth=physician_auth).text
    assert f"/alerts/{hospital.alert.id}/ack" in page

    response = client.post(f"/alerts/{hospital.alert.id}/ack", auth=physician_auth)

    session.expire_all()
    assert response.status_code in (200, 303)
    assert session.get(StaffAlert, hospital.alert.id).acknowledged_at is not None
