"""Portal access (PRD §8.10, PROGRESS PP.7): a patient reaches only their own records; unapproved recs never show;
the doctor's preview is read-only; AI replies are checked before they are shown or spoken."""
from __future__ import annotations

import re

import pytest

from factories import (TEST_PHYSICIAN, all_rows, guard, interview, make_appointment, make_fake_llm, make_intake,
                       make_patient, make_rec, portal_client, sign_in_with_code)

PHONE_A, PHONE_B = "+15550000001", "+15550000002"
GUESSED_ID = 987654
UNAPPROVED = "ZZ-UNAPPROVED-PORTAL-TEST"
BLOCKED = "This sounds like a viral infection. Take 500 mg of paracetamol every 6 hours."
BLOCKED_FRAGMENTS = ("viral", "500 mg")
PREFIX = "/portal/appointments/{appointment_id}"
FORM_DATA = {"/intake/turn": {"text": "I have a fever"}, "/symptoms": {"metric": "temperature", "value": "38.2"}}
FILES = {"/results": {"file": ("report.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf")}}


@pytest.fixture
def people(session):
    a = make_patient(session, name="Ana Silva", phone=PHONE_A)
    b = make_patient(session, name="Bruno Costa", phone=PHONE_B)
    return {"a1": make_appointment(session, patient=a), "a2": make_appointment(session, patient=a),
            "b": make_appointment(session, patient=b)}


@pytest.fixture
def client_a(settings, llm, people):
    client = portal_client(settings, llm)
    assert sign_in_with_code(client, PHONE_A).status_code == 303
    return client


def _portal_routes(client) -> list[tuple[str, str]]:
    """Every (method, suffix) under /portal/appointments/{id}, read from the app's OpenAPI schema so new routes are
    covered automatically."""
    found = []
    for path, operations in client.app.openapi()["paths"].items():
        if path.startswith(PREFIX):
            found += [(method.upper(), path[len(PREFIX):]) for method in sorted(operations)]
    return found


def _call(client, method: str, appointment_id: int, suffix: str):
    url = f"/portal/appointments/{appointment_id}{suffix}"
    if method == "GET":
        return client.get(url)
    return client.post(url, data=FORM_DATA.get(suffix, {}), files=FILES.get(suffix))


# ---------- only your own records ----------

def test_portal_home_lists_only_your_appointments(client_a, people):
    page = client_a.get("/portal").text

    assert f"/portal/appointments/{people['a1'].id}" in page
    assert f"/portal/appointments/{people['a2'].id}" in page
    assert f"/portal/appointments/{people['b'].id}" not in page
    assert "Bruno Costa" not in page


def test_every_portal_route_refuses_someone_elses_or_a_guessed_appointment(client_a, session, people):
    from previsit.models import LabResult, SymptomLog, Turn

    routes = _portal_routes(client_a)
    assert len(routes) >= 6, f"control: expected the portal's appointment routes, found {routes}"

    for method, suffix in routes:
        for target in (people["b"].id, GUESSED_ID):
            response = _call(client_a, method, target, suffix)
            assert response.status_code == 404, f"{method} {suffix} on appointment {target}: {response.status_code}"
    assert all_rows(session, Turn) == [] and all_rows(session, SymptomLog) == [] and all_rows(session, LabResult) == []


def test_your_own_appointment_pages_open(client_a, people):
    for method, suffix in _portal_routes(client_a):
        if method == "GET":
            assert _call(client_a, "GET", people["a1"].id, suffix).status_code == 200, suffix


def test_signed_out_visitors_are_sent_to_sign_in(settings, llm, people):
    client = portal_client(settings, llm)
    appointment_id = people["a1"].id

    page = client.get(f"/portal/appointments/{appointment_id}")
    turn = client.post(f"/portal/appointments/{appointment_id}/intake/turn", data={"text": "hi"})

    assert page.status_code == 303 and "sign-in" in page.headers["location"]
    assert turn.status_code == 401


def test_physician_login_does_not_open_patient_routes(settings, llm, people, physician_auth):
    client = portal_client(settings, llm)

    response = client.get(f"/portal/appointments/{people['a1'].id}", auth=physician_auth)

    assert response.status_code in (303, 401)


def test_old_text_message_link_only_opens_sign_in(settings, llm, people, session):
    from previsit.models import Patient

    client = portal_client(settings, llm)
    page = client.get(f"/p/{people['a1'].token}").text

    assert "Ana Silva" not in page
    assert f"/portal/appointments/{people['a1'].id}" not in page
    assert session.get(Patient, people["a1"].patient_id).phone in page, "control: contact is pre-filled"


def test_someone_elses_link_does_not_grant_access(client_a, people):
    client_a.get(f"/p/{people['b'].token}")

    assert client_a.get(f"/portal/appointments/{people['b'].id}").status_code == 404


def test_front_page_shows_no_patient_data(settings, llm, people):
    page = portal_client(settings, llm).get("/").text

    assert "Ana Silva" not in page and "Bruno Costa" not in page


def test_portal_pages_are_not_cached(client_a, people):
    response = client_a.get(f"/portal/appointments/{people['a1'].id}")

    assert response.headers.get("cache-control") == "no-store"


# ---------- unapproved recommendations never appear ----------

def _every_patient_facing_page(client, appointment, physician_auth) -> dict[str, str]:
    pages = {"home": client.get("/portal").text, "link": client.get(f"/p/{appointment.token}").text}
    for method, suffix in _portal_routes(client):
        if method == "GET":
            pages[suffix or "appointment"] = _call(client, "GET", appointment.id, suffix).text
    pages["doctor preview"] = client.get(f"/patients/{appointment.id}/patient-view", auth=physician_auth).text
    return pages


def test_unapproved_rec_appears_on_no_portal_page(client_a, session, people, physician_auth):
    make_rec(session, people["a1"], name=UNAPPROVED)
    session.commit()

    pages = _every_patient_facing_page(client_a, people["a1"], physician_auth)

    assert [name for name, html in pages.items() if UNAPPROVED in html] == []


def test_approved_rec_stays_hidden_until_the_physician_sends_it(client_a, session, people, physician_auth):
    from previsit import approval

    rec = make_rec(session, people["a1"], name=UNAPPROVED)
    approval.decide(session, rec.id, TEST_PHYSICIAN, approval.Decision.APPROVE)
    session.commit()
    page_path = f"/portal/appointments/{people['a1'].id}"

    assert UNAPPROVED not in client_a.get(page_path).text

    approval.notify_patient_of_approved(session, people["a1"].id, TEST_PHYSICIAN)
    session.commit()
    assert UNAPPROVED in client_a.get(page_path).text, "control: once sent, the patient sees it"


# ---------- the doctor's preview is read-only ----------

def test_doctor_preview_has_no_working_forms(settings, llm, people, physician_auth):
    client = portal_client(settings, llm)
    url = f"/patients/{people['a1'].id}/patient-view"

    page = client.get(url, auth=physician_auth)
    forms = re.findall(r"<form\b[^>]*>.*?</form>", page.text, re.S)

    assert page.status_code == 200 and forms, "control: the preview shows the patient's forms"
    for form in forms:
        assert "action=" not in form.split(">", 1)[0]
        assert re.search(r"<fieldset[^>]*\bdisabled\b", form), form[:120]
    assert client.post(url, auth=physician_auth).status_code == 405
    assert client.get(url).status_code == 401


# ---------- AI replies are checked before they are shown or spoken ----------

def test_blocked_ai_reply_is_never_shown_or_spoken(settings, session, people, monkeypatch):
    import base64

    import previsit.web.speech as speech

    # Speech may be prepared while the guard runs (F.1), but only audio for the checked text may reach the patient.
    monkeypatch.setattr(speech, "synthesize", lambda settings, text: text.encode())
    llm = make_fake_llm(interview=lambda s, m: interview(BLOCKED), scope_guard=lambda s, m: guard(False, "dosing"))
    client = portal_client(settings, llm)
    sign_in_with_code(client, PHONE_A)
    make_intake(session, people["a1"], "INTERVIEW")
    session.commit()

    response = client.post(f"/portal/appointments/{people['a1'].id}/intake/turn",
                           data={"text": "I've had a fever for three days", "speak": "true"})

    data = response.json()
    sent_audio = base64.b64decode(data["audio"]).decode()
    assert response.status_code == 200 and sent_audio == data["agent_text"], "control: the reply was spoken"
    for fragment in BLOCKED_FRAGMENTS:
        assert fragment not in data["agent_text"]
        assert fragment not in sent_audio
