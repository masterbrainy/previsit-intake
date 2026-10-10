"""Doctor forms: same-origin posts work, cross-site posts are blocked (CSRF), referrer policy keeps Origin usable."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from factories import doctor_sign_in, make_rec

SAME_ORIGIN = "http://testserver"


@pytest.fixture
def client(settings, llm):
    from previsit.web.app import create_app

    return TestClient(create_app(settings=settings, llm=llm), follow_redirects=False)


def _decide(client, rec_id, origin):
    return client.post(f"/recs/{rec_id}/decide", data={"decision": "approve"}, headers={"Origin": origin})


def _status(session, rec):
    session.refresh(rec)
    return rec.status


def test_same_origin_decision_is_accepted(client, session, appointment, doctor):
    from previsit.models import RecStatus

    rec = make_rec(session, appointment)
    doctor_sign_in(client, session, doctor)

    response = _decide(client, rec.id, SAME_ORIGIN)

    assert response.status_code in (200, 303)
    assert _status(session, rec) == RecStatus.APPROVED


@pytest.mark.parametrize("origin", ["http://evil.example", "null"])
def test_cross_site_decision_is_blocked(client, session, appointment, doctor, origin):
    """'null' is what browsers send under Referrer-Policy: no-referrer; it must not be treated as same-origin."""
    from previsit.models import RecStatus

    rec = make_rec(session, appointment)
    doctor_sign_in(client, session, doctor)

    response = _decide(client, rec.id, origin)

    assert response.status_code == 403
    assert _status(session, rec) == RecStatus.SUGGESTED


def test_decision_without_doctor_sign_in_is_refused(client, session, appointment):
    from previsit.models import RecStatus

    rec = make_rec(session, appointment)

    response = client.post(f"/recs/{rec.id}/decide", data={"decision": "approve"}, headers={"Origin": SAME_ORIGIN})

    assert response.status_code == 303 and response.headers["location"].startswith("/doctor/sign-in")
    assert _status(session, rec) == RecStatus.SUGGESTED


def test_referrer_policy_lets_browsers_send_a_real_origin(client, session, appointment, doctor):
    """no-referrer makes browsers send Origin: null on our own forms, which the CSRF check then blocks."""
    doctor_sign_in(client, session, doctor)
    response = client.get(f"/patients/{appointment.id}")

    assert response.status_code == 200

    assert response.headers.get("referrer-policy", "").lower() not in ("", "no-referrer")


@pytest.mark.parametrize("path", ["/", "/portal/sign-in", "/dashboard", "/doctor/sign-in"])
def test_pages_can_only_be_framed_by_this_site(client, physician_auth, path):
    """The recorder frames real pages side by side on the same origin; any other site must not frame them."""
    response = client.get(path, auth=physician_auth)
    csp = response.headers.get("content-security-policy", "")

    assert response.headers.get("x-frame-options", "").upper() in ("SAMEORIGIN", "DENY")
    ancestors = re.search(r"frame-ancestors ([^;]+)", csp)
    assert ancestors, f"no frame-ancestors in CSP for {path}"
    assert ancestors.group(1).split() in (["'self'"], ["'none'"])
