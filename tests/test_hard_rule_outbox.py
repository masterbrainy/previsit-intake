"""Hard rule: no medical recommendation reaches the patient without explicit physician approval (PROGRESS 3.4)."""
from __future__ import annotations

import pytest

import source_scan
from factories import TEST_PHYSICIAN, all_rows, make_appointment, make_rec, portal_sign_in

UNAPPROVED_NAME = "ZZ-UNAPPROVED-TEST-INVESTIGATION"


def _send_medical(session, appointment, rec_ids):
    from previsit import outbox
    from previsit.models import MessageKind

    return outbox.send_patient_message(session, appointment.id, MessageKind.MEDICAL,
                                       "Please get this test done before your visit.", actor=TEST_PHYSICIAN,
                                       rec_ids=rec_ids)


def _patient_messages(session):
    from previsit.models import PatientMessage

    return all_rows(session, PatientMessage)


def _assert_refused(session, appointment, rec_ids):
    from previsit.outbox import UnapprovedRecommendationError

    with pytest.raises(UnapprovedRecommendationError):
        _send_medical(session, appointment, rec_ids)
    assert _patient_messages(session) == []


def test_suggested_rec_is_refused(session, appointment):
    rec = make_rec(session, appointment)

    _assert_refused(session, appointment, [rec.id])


def test_rejected_rec_is_refused(session, appointment):
    from previsit import approval

    rec = make_rec(session, appointment)
    approval.decide(session, rec.id, TEST_PHYSICIAN, approval.Decision.REJECT)

    _assert_refused(session, appointment, [rec.id])


def test_approved_status_without_a_deciding_physician_is_refused(session, appointment):
    rec = make_rec(session, appointment, status_name="APPROVED", decided_by=None)

    _assert_refused(session, appointment, [rec.id])


def test_one_unapproved_rec_blocks_the_whole_message(session, appointment):
    from previsit import approval

    approved = make_rec(session, appointment, name="CBC")
    approval.decide(session, approved.id, TEST_PHYSICIAN, approval.Decision.APPROVE)
    pending = make_rec(session, appointment, name="CRP")

    _assert_refused(session, appointment, [approved.id, pending.id])


def test_medical_message_with_no_recs_is_refused(session, appointment):
    """Otherwise free-text medical advice could skip the approval check entirely."""
    _assert_refused(session, appointment, [])


def test_rec_approved_for_another_patient_is_refused(session, appointment):
    from previsit import approval

    other = make_appointment(session)
    rec = make_rec(session, other)
    approval.decide(session, rec.id, TEST_PHYSICIAN, approval.Decision.APPROVE)

    _assert_refused(session, appointment, [rec.id])


def test_unknown_rec_id_is_refused(session, appointment):
    _assert_refused(session, appointment, [987654])


@pytest.mark.parametrize("action, extra", [("APPROVE", {}), ("MODIFY", {"new_name": "CBC with differential"})])
def test_physician_decided_rec_is_sent(session, appointment, action, extra):
    from previsit import approval

    rec = make_rec(session, appointment)
    approval.decide(session, rec.id, TEST_PHYSICIAN, approval.Decision[action], **extra)

    _send_medical(session, appointment, [rec.id])

    assert len(_patient_messages(session)) == 1


def test_general_message_needs_no_approval(session, appointment):
    """Control: the gate is about medical recs, not a blanket refusal."""
    from previsit import outbox
    from previsit.models import MessageKind

    outbox.send_patient_message(session, appointment.id, MessageKind.GENERAL_RECS, "Drink plenty of fluids.",
                                actor="system")

    assert len(_patient_messages(session)) == 1


def test_only_outbox_creates_patient_messages():
    assert source_scan.constructor_calls("previsit.outbox", "PatientMessage"), (
        "outbox.py never constructs PatientMessage; the scan below would be vacuous"
    )

    offenders = {
        mod: lines
        for mod in source_scan.all_modules()
        if mod != "previsit.outbox" and (lines := source_scan.constructor_calls(mod, "PatientMessage"))
    }

    assert offenders == {}, f"PatientMessage constructed outside outbox.py: {offenders}"


def test_patient_page_never_shows_a_suggested_rec(settings, session, appointment, llm, physician_auth):
    from fastapi.testclient import TestClient

    from previsit.web.app import create_app

    make_rec(session, appointment, name=UNAPPROVED_NAME)
    client = TestClient(create_app(settings=settings, llm=llm))

    physician_page = client.get(f"/patients/{appointment.id}", auth=physician_auth)
    patient_page = client.get(portal_sign_in(client, session, settings, appointment))

    assert physician_page.status_code == 200
    assert UNAPPROVED_NAME in physician_page.text, "control: the physician must see the suggestion"
    assert patient_page.status_code == 200
    assert UNAPPROVED_NAME not in patient_page.text
