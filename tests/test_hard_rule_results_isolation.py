"""Hard rule: lab results are never sent to, or interpreted by, the LLM (PRD §8.7, PROGRESS 4.3)."""
from __future__ import annotations

import inspect

import pytest

import source_scan
from factories import interview, make_fake_llm, make_intake

RESULT_FILENAME = "SENTINEL_RESULT_cbc_report.pdf"
RESULT_CONTENT = b"HAEMOGLOBIN SENTINEL-7f3a 9.1 g/dL (L) WBC SENTINEL-7f3a 14.2 (H)"
SENTINELS = ("SENTINEL-7f3a", "SENTINEL_RESULT")
LLM_PACKAGES = ("previsit.llm", "openai")
COMPOSITION_ROOTS = {"previsit.web.app", "previsit.web"}


def test_results_module_cannot_reach_the_llm():
    assert source_scan.module_path("previsit.results").exists(), "previsit/results.py missing"

    hits = source_scan.imports_any(source_scan.transitive_imports("previsit.results"), LLM_PACKAGES)

    assert hits == [], f"previsit.results reaches the LLM via {hits}"


def test_llm_callers_do_not_import_results():
    """Only the web composition root may hold both; nothing that talks to the LLM may read results."""
    offenders = [
        mod for mod in source_scan.all_modules()
        if mod not in COMPOSITION_ROOTS
        and source_scan.imports_any(source_scan.direct_imports(mod), LLM_PACKAGES)
        and source_scan.imports_any(source_scan.direct_imports(mod), ("previsit.results",))
    ]

    assert offenders == []


def test_llm_client_accepts_no_attachment_channel():
    from previsit.llm import LLMClient

    params = list(inspect.signature(LLMClient.complete_json).parameters)

    assert params == ["self", "task", "system", "messages", "schema"]


def test_stored_result_never_appears_in_any_llm_payload(settings, session, appointment, physician_auth):
    from fastapi.testclient import TestClient

    from previsit import results, symptoms
    from previsit.intake.engine import IntakeEngine
    from previsit.web.app import create_app

    steps = iter([interview("Any other symptoms?"), interview("Thanks, that's everything.", complete=True)])
    llm = make_fake_llm(interview=lambda s, m: next(steps, interview(complete=True)))
    results.store_result(session, appointment, RESULT_FILENAME, RESULT_CONTENT, uploaded_by="lab")

    engine = IntakeEngine(llm, settings)
    intake = make_intake(session, appointment, "INTERVIEW")
    for text in ["Fever three days", "No, nothing else", "Yes, that's all correct"]:
        engine.handle_patient_turn(session, intake, text)
    symptoms.log_symptom(session, llm, appointment, "temperature", 38.1, "a bit better today", settings)

    client = TestClient(create_app(settings=settings, llm=llm))
    physician_page = client.get(f"/patients/{appointment.id}", auth=physician_auth)
    client.get(f"/p/{appointment.token}")

    assert RESULT_FILENAME in physician_page.text, "control: the result must be attached for the physician"
    assert llm.calls, "control: the flow must have used the LLM"
    leaked = [str(c)[:200] for c in llm.calls if any(s in str(c) for s in SENTINELS)]
    assert leaked == []
