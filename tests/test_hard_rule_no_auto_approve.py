"""Hard rule: no auto-approve and no approve-on-timeout. Only a named physician approves (PRD §8.5, ARCHITECTURE)."""
from __future__ import annotations

import pytest

import source_scan
from factories import TEST_PHYSICIAN, make_rec

APPROVING = {"APPROVED", "MODIFIED"}
SCHEDULER_LIBS = ("apscheduler", "celery", "rq", "schedule", "sched", "huey", "dramatiq", "arq")


def test_new_recommendation_defaults_to_suggested(session, appointment):
    from previsit.models import RecStatus

    rec = make_rec(session, appointment)

    assert rec.status == RecStatus.SUGGESTED
    assert rec.decided_by is None


@pytest.mark.parametrize("physician", ["", "   "])
def test_decide_without_a_physician_is_refused(session, appointment, physician):
    from previsit import approval
    from previsit.models import RecStatus

    rec = make_rec(session, appointment)

    with pytest.raises(approval.ApprovalError):
        approval.decide(session, rec.id, physician, approval.Decision.APPROVE)

    session.refresh(rec)
    assert rec.status == RecStatus.SUGGESTED
    assert rec.decided_by is None


def test_decide_approve_records_physician(session, appointment):
    from previsit import approval
    from previsit.models import RecStatus

    rec = make_rec(session, appointment)

    approval.decide(session, rec.id, TEST_PHYSICIAN, approval.Decision.APPROVE)

    session.refresh(rec)
    assert rec.status == RecStatus.APPROVED
    assert rec.decided_by == TEST_PHYSICIAN


@pytest.mark.parametrize("action, expected", [("approve", "APPROVED"), ("reject", "REJECTED")])
def test_decide_accepts_the_action_as_a_string(session, appointment, action, expected):
    """ARCHITECTURE.md spells the action as approve|modify|reject; a string must not fall through to another branch."""
    from previsit import approval
    from previsit.models import RecStatus

    rec = make_rec(session, appointment)

    approval.decide(session, rec.id, TEST_PHYSICIAN, action)

    session.refresh(rec)
    assert rec.status == RecStatus[expected]


def test_decide_rejects_an_unknown_action(session, appointment):
    from previsit import approval
    from previsit.models import RecStatus

    rec = make_rec(session, appointment)

    with pytest.raises(ValueError):
        approval.decide(session, rec.id, TEST_PHYSICIAN, "maybe")

    session.refresh(rec)
    assert rec.status == RecStatus.SUGGESTED


def test_only_approval_module_sets_an_approving_status():
    assert source_scan.module_path("previsit.approval").exists(), "previsit/approval.py missing"
    assert source_scan.assignments_of_enum("previsit.approval", "RecStatus", APPROVING), (
        "approval.py never sets RecStatus.APPROVED/MODIFIED; the scan below would be vacuous"
    )

    offenders = {
        mod: lines
        for mod in source_scan.all_modules()
        if mod != "previsit.approval"
        and (lines := source_scan.assignments_of_enum(mod, "RecStatus", APPROVING))
    }

    assert offenders == {}, f"RecStatus.APPROVED/MODIFIED assigned outside approval.py: {offenders}"


def test_no_scheduler_or_background_job_library_is_used():
    offenders = {
        mod: hits
        for mod in source_scan.all_modules()
        if (hits := source_scan.imports_any(source_scan.direct_imports(mod), SCHEDULER_LIBS))
    }

    assert offenders == {}, f"Scheduler imports found (approve-on-timeout risk): {offenders}"


@pytest.mark.parametrize("module", ["previsit.approval", "previsit.recs.medical"])
def test_approval_and_suggestion_logic_never_touch_the_llm(module):
    assert source_scan.module_path(module).exists(), f"{module} missing"

    hits = source_scan.imports_any(source_scan.transitive_imports(module), ("previsit.llm", "openai"))

    assert hits == [], f"{module} reaches the LLM via {hits}"
