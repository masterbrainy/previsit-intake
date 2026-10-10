"""Portal one-time-code sign-in (PRD §8.10, PROGRESS PP.7): expiry, lockout, rate limits, sessions."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

import pytest
from factories import all_rows, make_appointment, make_patient, portal_client, sign_in_with_code

KEY = b"k" * 32
PHONE = "+15550001111"
T0 = datetime(2026, 10, 9, 12, 0, 0)


@pytest.fixture
def known(session):
    return make_patient(session, name="Ana Silva", phone=PHONE)


def _request(session, contact=PHONE, ip="10.0.0.1", now=T0):
    from previsit.portal import auth

    return auth.request_code(session, KEY, contact, ip, now=now).code


def _verify(session, code, contact=PHONE, now=T0):
    from previsit.portal import auth

    auth.verify_code(session, KEY, contact, code, now=now)


def _wrong(code: str) -> str:
    return f"{(int(code) + 1) % 1_000_000:06d}"


# ---------- codes ----------

def test_code_is_six_digits_and_works_once(session, known):
    from previsit.portal.auth import SignInError

    code = _request(session)

    assert re.fullmatch(r"\d{6}", code)
    _verify(session, code)
    with pytest.raises(SignInError):
        _verify(session, code)


def test_code_works_just_before_ten_minutes(session, known):
    code = _request(session)

    _verify(session, code, now=T0 + timedelta(minutes=9, seconds=59))


def test_code_expires_at_ten_minutes(session, known):
    from previsit.portal.auth import SignInError

    code = _request(session)

    with pytest.raises(SignInError, match="expired"):
        _verify(session, code, now=T0 + timedelta(minutes=10))


def test_five_wrong_tries_lock_the_code_even_against_the_right_one(session, known):
    from previsit.portal.auth import SignInError

    code = _request(session)
    for _ in range(5):
        with pytest.raises(SignInError):
            _verify(session, _wrong(code))

    with pytest.raises(SignInError, match="Too many"):
        _verify(session, code)


def test_a_new_code_replaces_the_old_one(session, known):
    from previsit.portal.auth import SignInError

    first = _request(session)
    second = _request(session, now=T0 + timedelta(minutes=1))

    if first != second:
        with pytest.raises(SignInError):
            _verify(session, first, now=T0 + timedelta(minutes=1))
    _verify(session, second, now=T0 + timedelta(minutes=1))


def test_fourth_request_for_one_contact_within_15_minutes_is_refused(session, known):
    from previsit.portal.auth import SignInError

    for minute in range(3):
        _request(session, now=T0 + timedelta(minutes=minute))

    with pytest.raises(SignInError, match="Too many"):
        _request(session, now=T0 + timedelta(minutes=3))
    _request(session, now=T0 + timedelta(minutes=16))  # window has passed


def test_one_ip_is_limited_across_contacts(session):
    from previsit.portal.auth import SignInError

    for i in range(10):
        _request(session, contact=f"+1555000{i:04d}", ip="10.9.9.9", now=T0 + timedelta(seconds=i))

    with pytest.raises(SignInError, match="Too many"):
        _request(session, contact="+15559999999", ip="10.9.9.9", now=T0 + timedelta(seconds=11))


def test_new_contact_gets_a_code_but_reaches_no_records(session, known):
    """P-004: new patients verify their contact with a code before setting up their details."""
    from previsit.portal.auth import patients_for

    code = _request(session, contact="+15558887777")
    assert code is not None and len(code) == 6
    _verify(session, code, contact="+15558887777")
    assert patients_for(session, "+15558887777") == []


def test_codes_are_not_stored_in_plain_text(session, known):
    from previsit.models import SignInCode

    code = _request(session)

    rows = all_rows(session, SignInCode)
    assert rows and all(code not in str(row.model_dump()) for row in rows)


# ---------- over HTTP ----------

def test_sign_in_sets_an_httponly_lax_session_cookie(settings, llm, session):
    make_appointment(session, patient=make_patient(session, name="Ana Silva", phone=PHONE))
    client = portal_client(settings, llm, demo=True)

    response = sign_in_with_code(client, PHONE)

    assert response.status_code == 303 and response.headers["location"] == "/portal"
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_outside_demo_mode_the_code_page_does_not_reveal_known_contacts(settings, llm, session):
    make_appointment(session, patient=make_patient(session, name="Ana Silva", phone=PHONE))
    client = portal_client(settings, llm, demo=False)

    from previsit.portal.contact import mask_contact

    unknown = "+15558887777"
    known_page = client.post("/portal/code", data={"contact": PHONE}).text
    unknown_page = client.post("/portal/code", data={"contact": unknown}).text

    def blank(page: str, contact: str) -> str:
        return page.replace(contact, "CONTACT").replace(mask_contact(contact), "MASKED")

    assert not re.search(r'class="mono code"', known_page)
    assert blank(known_page, PHONE) == blank(unknown_page, unknown)


def test_signed_out_session_cannot_be_replayed(settings, llm, session):
    from previsit.web.portal import COOKIE

    appointment = make_appointment(session, patient=make_patient(session, name="Ana Silva", phone=PHONE))
    client = portal_client(settings, llm, demo=True)
    sign_in_with_code(client, PHONE)
    token = client.cookies.get(COOKIE)
    assert client.get(f"/portal/appointments/{appointment.id}").status_code == 200

    client.post("/portal/sign-out")
    client.cookies.set(COOKIE, token)  # an attacker who kept the old cookie

    assert client.get(f"/portal/appointments/{appointment.id}").status_code in (303, 401)
