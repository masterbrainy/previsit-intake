"""Times are stored in UTC (models.utcnow) but appointments are clinic-local wall-clock times. Every time a person
reads must be clinic-local, or an alert raised at 21:54 shows as 04:54 next day beside a 12:00 appointment."""
from __future__ import annotations

import re
import time
from datetime import UTC, datetime

import pytest

from factories import doctor_sign_in, make_rec, portal_client

def _times(page: str) -> list[str]:
    return re.findall(r"\d{2} Oct,? \d{2}:\d{2}", page)


RAISED_UTC = datetime(2026, 10, 10, 4, 54, tzinfo=UTC)  # 21:54 on Fri 9 Oct in Los Angeles


@pytest.fixture
def los_angeles(monkeypatch):
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_overview_alert_time_is_clinic_local(los_angeles, settings, llm, session, appointment, physician_auth):
    from previsit.models import StaffAlert

    session.add(StaffAlert(appointment_id=appointment.id, title="Emergency", body="call", created_at=RAISED_UTC))
    session.commit()

    page = portal_client(settings, llm).get("/dashboard", auth=physician_auth).text

    assert "Fri 09 Oct, 21:54" in page and "04:54" not in page, _times(page)


def test_decision_time_on_the_doctor_page_is_clinic_local(los_angeles, settings, llm, session, appointment, doctor):
    rec = make_rec(session, appointment, status_name="APPROVED", decided_by=doctor.email)
    rec.decided_at = RAISED_UTC
    session.add(rec)
    session.commit()
    client = portal_client(settings, llm)
    doctor_sign_in(client, session, doctor)

    page = client.get(f"/patients/{appointment.id}").text

    assert "09 Oct 21:54" in page and "04:54" not in page, _times(page)
