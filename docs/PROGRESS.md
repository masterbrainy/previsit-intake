# Progress

Plan version: v0.1 · Status values: `todo` · `doing` · `done` · `blocked: <reason>`
Owner: **B** = Build · **T** = Test & Support · **U** = you (needs a human / clinician / decision)

## Phase 0: Foundations
| ID | Task | Owner | Status |
|---|---|---|---|
| 0.1 | Pick pilot site, specialty, market (PRD Q1–Q3) | U | todo |
| 0.2 | Name the clinical lead who signs off content | U | todo |
| 0.3 | Choose stack: telephony/voice, LLM, backend, frontend (see docs/ARCHITECTURE.md) | U+B | done |
| 0.4 | Draft history sheet template (PRD §7) as a schema | B | doing |
| 0.5 | Draft baseline red-flag list + escalation script (pending clinician sign-off) | T | done |
| 0.6 | Draft Fever (adult) complaint module (pending clinician sign-off) | B | doing |
| 0.7 | Eval set: 30–50 simulated patient scripts with expected sheets (22 fever drafts so far, see evals/README.md) | T | doing |
| 0.8 | Regulatory / privacy read for the chosen market | U | todo |

## Phase 1: Voice intake → history sheet
| ID | Task | Owner | Status |
|---|---|---|---|
| 1.1 | Project scaffold + test harness + CI | B+T | doing |
| 1.2 | Appointment trigger (manual / CSV) | B | todo |
| 1.3 | Outbound call / SMS link, identity check, consent | B | todo |
| 1.4 | Voice agent: §7 interview, module-driven follow-ups | B | todo |
| 1.5 | Red-flag detection + escalation | B | todo |
| 1.6 | End-of-call read-back | B | todo |
| 1.7 | History sheet generation with transcript links | B | todo |
| 1.8 | Physician view: patient list, sheet, PDF export | B | todo |
| 1.9 | Audit log | B | todo |
| 1.10 | Eval runner: accuracy, fabrication, red-flag recall | T | doing |
| 1.11 | Exit gate: eval ≥90% / 0 fabricated / 100% red-flag recall | T | todo |

## Phase 2: General recommendations + symptom logs
| ID | Task | Owner | Status |
|---|---|---|---|
| 2.1 | Recommendation library for Fever module | B | todo |
| 2.2 | Delivery at end of call + SMS, with safety-netting | B | todo |
| 2.3 | Symptom logging (SMS/app/voice) → physician sheet | B | todo |
| 2.4 | Threshold breach → escalation | B | todo |
| 2.5 | Tests: no out-of-library advice ever sent | T | doing |

## Phase 3: Medical recommendations + physician OK
| ID | Task | Owner | Status |
|---|---|---|---|
| 3.1 | Suggested investigations with rationale | B | todo |
| 3.2 | Approve / Modify / Reject / Add UI | B | todo |
| 3.3 | Patient notification on approval | B | todo |
| 3.4 | Tests: unapproved recommendation can never reach patient | T | doing |

## Phase 4: Results routing
| ID | Task | Owner | Status |
|---|---|---|---|
| 4.1 | Result upload + attach to sheet | B | todo |
| 4.2 | Physician notification on results | B | todo |
| 4.3 | Tests: results never sent to LLM | T | doing |
