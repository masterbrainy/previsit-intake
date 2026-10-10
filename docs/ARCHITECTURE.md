# Architecture (Build-owned contract)

Stack (PROGRESS 0.3): **Python 3.11 · FastAPI · SQLModel (SQLite dev, Postgres via `DATABASE_URL`) · Jinja2 server-rendered pages · OpenAI** (chat + structured outputs, `gpt-4o-transcribe` speech-to-text, `gpt-4o-mini-tts` text-to-speech). Package: `src/previsit`. Run: `uv run uvicorn previsit.web.app:lazy_app --factory --reload`. Tests: `uv run pytest` (live API tests are marked `@pytest.mark.live` and skipped by default).

The intake channel today is a browser voice page (push-to-talk + text fallback). Phone calls (Twilio) are Phase 5, behind the same `IntakeEngine`.

## Where the hard rules are enforced

| Hard rule | Single choke point | How to test it |
|---|---|---|
| No medical rec reaches the patient unapproved | `outbox.send_patient_message(kind=MessageKind.MEDICAL, rec_ids=...)` raises `UnapprovedRecommendationError` unless every rec has status `APPROVED`/`MODIFIED` and `decided_by` set. No other code writes `PatientMessage`. | Call it with suggested/rejected recs; patient page never shows a suggested rec |
| No auto-approve / approve-on-timeout | Only `approval.decide(...)` sets a rec to approved, and it requires a physician id. No scheduler exists | Grep/introspect: nothing else assigns `RecStatus.APPROVED` |
| Results never reach the LLM | `previsit.results` has no import of `previsit.llm` (or `openai`). `LLMClient` methods take transcripts/sheets only | Import-graph test on `previsit.results`; `FakeLLM` records every payload, so assert no result content appears in them |
| No diagnosis / prescribing / dosing | Interviewer system prompt + `safety.scope_guard.check_agent_utterance()` on every agent utterance; blocked text is replaced by a fixed redirect | FakeLLM returns a diagnosis; assert the patient sees the redirect |
| Red flags stop the intake | `safety.detector.assess_turn()` runs on **every** patient turn in every state (consent → read-back → after recs) and on symptom-log values/notes. Escalation text is a fixed template (`safety.escalation`), never LLM-written | FakeLLM flags RF; assert state `ESCALATED`, staff alert, no further questions, no recs generated |

## Modules and public functions

```
previsit/
  config.py        Settings (env / .env): OPENAI_API_KEY, DATABASE_URL, model names, EMERGENCY_NUMBER, CRISIS_LINE,
                   PHYSICIAN_USERNAME/PASSWORD, BASE_URL
  db.py            make_engine(url), init_db(engine), session_scope(engine)
  models.py        SQLModel tables: Patient, Appointment, Intake, Turn, HistorySheetRecord, RedFlagEvent,
                   MedicalRecommendation, PatientMessage, StaffAlert, SymptomLog, LabResult, AuditEvent
                   Enums: IntakeState, Speaker, RecStatus, MessageKind
  audit.py         record(session, actor, action, entity, entity_id, details: dict) -> AuditEvent
  llm.py           LLMClient protocol: complete_json(task: str, system: str, messages: list[dict], schema: type[BaseModel]) -> BaseModel
                   OpenAILLM(settings) and FakeLLM(handlers: dict[task, callable]) for tests. Records every call in .calls
  modules/         load_module(id) -> ComplaintModule, all_modules(); data/*.yaml (fever, general)
  safety/
    red_flags.py   BASELINE_RED_FLAGS (RF-01..RF-16, mirrors evals/red_flags.md)
    detector.py    assess_turn(llm, ctx: PatientContext, transcript: list[Turn], pending_clarification: str|None) -> SafetyAssessment
                   SafetyAssessment{status: CLEAR|AMBIGUOUS|RED_FLAG, rf_ids, evidence, clarifying_question}
    escalation.py  escalation_message(rf_ids, ctx, settings) -> str (deterministic);
                   record_red_flag(session, appointment_id, rf_ids, evidence, ctx, settings, source, intake_id, turn_id)
    scope_guard.py check_agent_utterance(llm, text) -> GuardResult{allowed: bool, reason}
  intake/
    engine.py      IntakeEngine(llm, settings).start(session, intake) -> AgentReply
                   .handle_patient_turn(session, intake, text) -> AgentReply{text, state, ended: bool}
                   States: CONSENT → IDENTITY → INTERVIEW → READBACK → COMPLETE | ESCALATED | DECLINED
    interviewer.py next_step(llm, modules, transcript, ctx) -> InterviewStep{utterance, interview_complete}
  sheet/
    schema.py      HistorySheet{particulars, chief_complaints, hopi, past_history, treatment_history, allergies,
                   family_history, personal_history, review_of_systems, specialty_addons, could_not_answer,
                   red_flag_screen, findings: dict}; every Statement has text + source_turn_ids
    extract.py     build_sheet(llm, transcript, modules, ctx) -> HistorySheet; statements citing no valid
                   patient turn are DROPPED (traceability rule)
  recs/
    general.py     select_general_recs(llm, module, sheet) -> list[LibraryItem]; only library IDs, text verbatim,
                   safety-netting always appended
    medical.py     suggest_investigations(module, findings) -> list[Suggestion]; deterministic module rules, no LLM
  approval.py      decide(session, rec_id, physician, action: approve|modify|reject, new_name=None, note=None)
                   add_investigation(session, appointment_id, physician, name, note) ; notify_patient_of_decisions(...)
  outbox.py        send_patient_message(session, appointment, kind, body, rec_ids=()) ; send_staff_alert(...)
  symptoms.py      log_symptom(session, llm, appointment, metric, value, note, settings, unit="°C") -> LogOutcome
                   (metric "temperature" is an alias of "temperature_c"; thresholds + note safety check)
  results.py       store_result(session, appointment, filename, content: bytes, uploaded_by, *, content_type=None,
                   upload_dir=None, max_bytes=10MB) -> LabResult  (NO llm import; content must match its type's magic bytes)
  voice.py         transcribe(settings, audio_bytes, mime) -> str ; synthesize(settings, text) -> bytes
  web/app.py       create_app(settings=None, llm=None) -> FastAPI ; lazy_app() for uvicorn --factory
  web/uploads.py   result upload route, kept apart from LLM-using routers
  portal/contact.py normalize_contact(raw) -> str (lower-case email or phone digits, raises ContactError) ; mask_contact
  portal/auth.py   request_code(session, key, contact, ip) -> CodeRequest ; verify_code(session, key, contact, code)
                   (raises SignInError) ; start_session / session_contact / end_session ; patients_for(session, contact)
                   6 digits, 10 min, 5 wrong tries, 3 requests per contact and 10 per IP per 15 min; codes stored as
                   HMAC (key = PORTAL_SECRET or random per process), session tokens as SHA-256. No AI.
  web/portal.py    Public: / (clinician + patient doors, no patient data), /portal/sign-in, /p/{token} (text-message
                   link: sign-in with contact pre-filled, opens no records), POST /portal/code, /portal/verify,
                   /portal/sign-out. Signed in: /portal (own appointments).
                   Dependencies: portal_user (cookie previsit_portal, HttpOnly, SameSite=Lax) and owned_appointment
                   (404 unless the appointment's patient matches the signed-in contact).
                   Physician (basic auth): /dashboard, /appointments/new, /appointments/import (CSV, column contact),
                   /patients/{appt_id}, /patients/{appt_id}/patient-view (read-only preview), /patients/{appt_id}/print,
                   /recs/{id}/decide, /appointments/{id}/recs/add
                   Patient portal (signed in, owned_appointment): /portal/appointments/{id} (+ /intake, /intake/start,
                   /intake/turn, /symptoms, /results)
  intake/engine.py IntakeEngine(llm, settings, *, defer=None, on_candidate=None). Web passes defer (FastAPI background
                   task via web/sheet_jobs.run_sheet_job, one job at a time per intake) so escalation and completion reply
                   before the sheet is rebuilt, and the read-back is two-step (AgentReply.follow_up, then
                   POST .../intake/readback). on_candidate lets web/speech.SpeechPrefetch synthesise while the scope guard
                   runs; only audio for the text the guard returned is sent. Without hooks (evals, tests) all runs inline.
  Settings         DEMO_MODE=true shows the sign-in code on screen (synthetic data only; never in a real deployment).
```

Tests should build the app with `create_app(settings=test_settings, llm=FakeLLM(...))` and a temp SQLite URL.
