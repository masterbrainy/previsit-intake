"""Physician forms: same-origin posts work, cross-site posts are blocked (CSRF), referrer policy keeps Origin usable."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from factories import make_rec

SAME_ORIGIN = "http://testserver"


@pytest.fixture
def client(settings, llm):
    from previsit.web.app import create_app

    return TestClient(create_app(settings=settings, llm=llm), follow_redirects=False)


def _decide(client, rec_id, physician_auth, origin):
    return client.post(f"/recs/{rec_id}/decide", data={"decision": "approve"}, auth=physician_auth,
                       headers={"Origin": origin})


def _status(session, rec):
    session.refresh(rec)
    return rec.status


def test_same_origin_decision_is_accepted(client, session, appointment, physician_auth):
    from previsit.models import RecStatus

    rec = make_rec(session, appointment)

    response = _decide(client, rec.id, physician_auth, SAME_ORIGIN)

    assert response.status_code in (200, 303)
    assert _status(session, rec) == RecStatus.APPROVED


@pytest.mark.parametrize("origin", ["http://evil.example", "null"])
def test_cross_site_decision_is_blocked(client, session, appointment, physician_auth, origin):
    """'null' is what browsers send under Referrer-Policy: no-referrer; it must not be treated as same-origin."""
    from previsit.models import RecStatus

    rec = make_rec(session, appointment)

    response = _decide(client, rec.id, physician_auth, origin)

    assert response.status_code == 403
    assert _status(session, rec) == RecStatus.SUGGESTED


def test_decision_without_physician_login_is_refused(client, session, appointment):
    from previsit.models import RecStatus

    rec = make_rec(session, appointment)

    response = client.post(f"/recs/{rec.id}/decide", data={"decision": "approve"}, headers={"Origin": SAME_ORIGIN})

    assert response.status_code == 401
    assert _status(session, rec) == RecStatus.SUGGESTED


def test_referrer_policy_lets_browsers_send_a_real_origin(client, appointment, physician_auth):
    """no-referrer makes browsers send Origin: null on our own forms, which the CSRF check then blocks."""
    response = client.get(f"/patients/{appointment.id}", auth=physician_auth)

    assert response.headers.get("referrer-policy", "").lower() not in ("", "no-referrer")
