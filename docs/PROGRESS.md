# Progress

Plan version: v0.9 · Status values: `todo` · `doing` · `done` · `blocked: <reason>`
Owner: **B** = Build · **T** = Test & Support · **U** = you (needs a human / clinician / decision)

## Phase 0: Foundations
| ID | Task | Owner | Status |
|---|---|---|---|
| 0.1 | Pick pilot site, specialty, market (PRD Q1–Q3) | U | todo |
| 0.2 | Name the clinical lead who signs off content | U | todo |
| 0.3 | Choose stack: telephony/voice, LLM, backend, frontend (see docs/ARCHITECTURE.md) | U+B | done |
| 0.4 | Draft history sheet template (PRD §7) as a schema | B | done |
| 0.5 | Draft baseline red-flag list + escalation script (pending clinician sign-off) | T | done |
| 0.6 | Draft Fever (adult) complaint module (pending clinician sign-off) | B | done |
| 0.7 | Eval set: 30–50 simulated patient scripts with expected sheets (23 fever drafts so far, see evals/README.md) | T | doing |
| 0.8 | Regulatory / privacy read for the chosen market | U | todo |

## Phase 1: Voice intake → history sheet
| ID | Task | Owner | Status |
|---|---|---|---|
| 1.1 | Project scaffold + test harness + CI | B+T | done |
| 1.2 | Appointment trigger (manual / CSV) | B | done |
| 1.3 | Outbound call / SMS link, identity check, consent (link + identity + consent done; real SMS/phone needs a Twilio account) | B | done |
| 1.4 | Voice agent: §7 interview, module-driven follow-ups | B | done |
| 1.5 | Red-flag detection + escalation | B | done |
| 1.6 | End-of-call read-back | B | done |
| 1.7 | History sheet generation with transcript links | B | done |
| 1.8 | Physician view: patient list, sheet, PDF export (print-to-PDF view) | B | done |
| 1.9 | Audit log | B | done |
| 1.10 | Eval runner: accuracy, fabrication, red-flag recall | T | done |
| 1.11 | Exit gate: eval ≥90% / 0 fabricated / 100% red-flag recall | T | todo |
| 1.12 | Symptom-specific red-flag screening: any mentioned symptom with its own red flags (headache, chest pain, abdominal pain, breathlessness) gets its screening questions early; screening lists live in module content (P-008) | B | todo |
| 1.13 | Eval cases where red-flag features appear only when asked (FEV-023 and siblings for chest pain, abdominal pain); gate on screening asked + escalation within the agreed question limit (P-008) | T | doing: gate built (evals/screening.py, FEV-023–026); live baseline 0/8 screened, awaiting 1.12 |
| 1.14 | Clinician sign-off of symptom screening lists and proposed RF-16 (thunderclap headache) (P-008) | U | todo |
| 1.15 | Safety detector sees the whole call, not the last 14 lines, so two-fact red flags said far apart fire as soon as the second fact appears (FEV-025); symptom-log notes are checked against the call and earlier logs | B | doing: built, awaiting Test's red-flag re-run |

## Phase 2: General recommendations + symptom logs
| ID | Task | Owner | Status |
|---|---|---|---|
| 2.1 | Recommendation library for Fever module | B | done |
| 2.2 | Delivery at end of call + patient page, with safety-netting (SMS needs Twilio) | B | done |
| 2.3 | Symptom logging (SMS/app/voice) → physician sheet | B | done |
| 2.4 | Threshold breach → escalation | B | done |
| 2.5 | Tests: no out-of-library advice ever sent | T | todo |

## Phase 3: Medical recommendations + physician OK
| ID | Task | Owner | Status |
|---|---|---|---|
| 3.1 | Suggested investigations with rationale | B | done |
| 3.2 | Approve / Modify / Reject / Add UI | B | done |
| 3.3 | Patient notification on approval (patient page; SMS needs Twilio) | B | done |
| 3.4 | Tests: unapproved recommendation can never reach patient | T | done |

## Phase 4: Results routing
| ID | Task | Owner | Status |
|---|---|---|---|
| 4.1 | Result upload + attach to sheet | B | done |
| 4.2 | Physician notification on results | B | done |
| 4.3 | Tests: results never sent to LLM | T | done |

## Patient portal (P-002, before the demo release)
| ID | Task | Owner | Status |
|---|---|---|---|
| PP.1 | Front page: clinician and patient doors; no patient data on public pages | B | done |
| PP.2 | Patient contact (email or phone) on appointment form + CSV import | B | done |
| PP.3 | One-time-code sign-in: 6 digits, 10-min expiry, lockout after 5 tries, rate limit, HttpOnly session, sign-out; demo mode shows the code on screen | B | done |
| PP.4 | Portal home: patient's own appointments; per appointment intake call, advice, approved tests, reading log, report upload, messages | B | done |
| PP.5 | Text-message link opens portal sign-in with contact pre-filled | B | done |
| PP.6 | Doctor's read-only "Open patient's view" button | B | done |
| PP.7 | Tests: patient sees only own records (guessed IDs, old links); code expiry/lockout/rate limit; unapproved recs never shown in portal; preview is read-only; AI replies still checked before play | T | done |
| PP.8 | Real sign-in code delivery by SMS/email | U+B | blocked: needs a messaging provider (same as F.3) |
| PB.1 | Patient self-service: new patients set up their details after verifying their contact; patients book visits themselves (live immediately, marked for the doctor) | B | done |
| PB.2 | Pilot guard: self-bookings come from / sync with the clinic scheduling system, or need clinic confirmation before the intake runs (P-004) | U+B | todo: before any pilot |
| PB.3 | Pilot guard: cap self-registrations and AI-call spend on any publicly hosted site (P-004, ties to D.2) | B | todo: before public hosting |
| PB.4 | Availability/calendar check to prevent double-booking (P-004 known gap) | B | todo |
| PB.5 | Test: self-registration and booking limits, identity reuse and isolation (tests/test_portal_booking.py, 15 tests, 7/7 mutants killed) | T | done |

## Hospital overview + doctor accounts (P-005, before the demo release)
| ID | Task | Owner | Status |
|---|---|---|---|
| H.1 | Doctors list (specialty, keywords); staff booking form + CSV pick a doctor | B | done |
| H.2 | Portal booking suggests doctors (rule-based; reasons quote patient's words, never a condition; GP always offered); patient picks | B | done |
| H.3 | Individual doctor sign-in (email + one-time code, role "doctor"); replaces shared login on clinical pages | B | done |
| H.4 | Per-patient access check on every clinical route (404 otherwise); approval.decide records the signed-in doctor | B | done |
| H.5 | Hospital overview: all patients, assigned doctor, time, status, emergency flag; no clinical details; staff see and acknowledge emergency alerts for every patient | B | done |
| H.6 | Doctor's own patient list with quick notes (clinician-only, never to patient or AI) | B | done |
| H.7 | Referrals (patient, from, to, note): receiving doctor gets access; audited; only a doctor with access can refer | B | done |
| H.8 | Emergency words in booking reason show the full emergency script; acknowledge to continue; audited | B | done |
| H.9 | Tests: doctor can't reach unassigned/unreferred patients (IDs, URLs); approvals name the doctor; staff see alerts with doctor offline; suggestion text never names a condition; hard-rule tests pass under doctor sign-in | T | done: tests/test_doctor_access.py, test_doctor_suggestions.py, booking emergency tests in test_portal_booking.py; hard-rule tests run under doctor sign-in |
| H.10 | Pilot guard: break-glass access for a covering doctor, with reason and audit | B | todo: before any pilot |
| H.11 | Pilot guard: demo mode never on a public URL; individual staff accounts for the overview | U+B | todo: before any pilot or public hosting |

## Demo release: working site + captioned video (final step, P-001)
| ID | Task | Owner | Status |
|---|---|---|---|
| D.1 | Demo-ready site: one-command start, clean reset script, synthetic demo patients (incl. backdated temperature readings) | B | done: `uv run --group demo python -m demo.serve` (resets, seeds, serves :8010 in demo mode) |
| D.2 | Decide hosting: local only, or a URL clinicians/researchers can open | U | todo |
| D.3 | Demo patient scripts (portal sign-in → fever full flow, + stiff-neck escalation); run each ≥3× through the simulator to confirm they reliably hit every scene | T | done |
| D.4 | Automated recorder in `demo/`: Playwright drives physician + patient windows, records each | B | done: `python -m demo.record` films the real app on a stage (browser + phone), screencast frames, simulated patients with synthetic voices |
| D.5 | Assemble video with ffmpeg: side by side, captions on every step, AI voice audio, pauses-shortened note, closing limits card; check extracted frames | B | done: `python -m demo.assemble` → `demo/output/PATH-demo.mp4` (175.8 s, 1080p30, voices + ducked music bed). User asked for an ideal-vision film: no limits card; AI waits cut, fast-forwards badged on screen |
| D.6 | Caption review: every claim true vs code and latest eval results; wording right for clinicians | T | done: final pass in evals/caption_review.md (6 caption changes for Build; re-recording the red-flag take is a user decision, D.7) |
| D.8 | Re-record the red-flag take only (fixed demo script, local-time alert display) and re-render with Test's 6 caption fixes (P-008) | B | todo |
| D.7 | Final review: user watches and accepts the video | U | todo |

## Rename to PATH (P-006)
| ID | Task | Owner | Status |
|---|---|---|---|
| N.1 | README rewritten for PATH (what it is, safety rules, current run instructions, current auth, status/limits) | B | done: README.md rewritten (flows for patient, doctor and staff; safety rules; demo and dev quick start; tests, evals, film; layout; latest eval numbers and limits) |
| N.2 | Product name "PATH" in the UI (page titles, headers, portal, emails/messages copy), pyproject description, CLAUDE.md heading | B | done: wordmark, page titles, portal header, the assistant's greeting ("I'm PATH…"), FastAPI title, pyproject, CLAUDE.md heading |
| N.3 | GitHub repo description/topics updated to PATH (repo rename only if the user confirms) | B | done: description and topics (healthcare, voice-ai, fastapi, clinical-safety) set via `gh repo edit`; repo not renamed (user declined) |

## Build follow-ups (found while building)
| ID | Task | Owner | Status |
|---|---|---|---|
| F.1 | Turn latency ~3–4 s (safety → interview → scope guard run in sequence). Options: faster models per task, streaming TTS | B | done (partial): speech prepared while the scope guard runs, turn route off the event loop. Measured 3.5–4.5 s per spoken turn (was ~4.6–5 s). The 3 checks in sequence (~2.9 s) are the floor while every reply is checked first |
| F.2 | Completion step ~10 s (final sheet + recommendations). Say a holding line first, or generate in background | B | done: escalation and completion reply without waiting for the sheet (rebuilt in the background); read-back says a holding line, then the summary (~17 s sheet build still behind it) |
| F.5 | Coverage checklist in code for every PRD §7 section (past history, medicines, family, smoking/alcohol, travel), like the allergy check (DEMO-001 run 2 skipped them) | B | todo |
| F.6 | After an escalation, a patient who accepts gets a fixed acknowledgement and close, not the refusal script | B | todo |
| F.3 | Twilio adapter for real SMS invites and phone calls (needs account) | U+B | blocked: no Twilio account |
| F.4 | Physician auth is a single shared basic-auth login; needs per-physician accounts before any pilot | B | superseded by H.3/H.4 (P-005) |
| A.1 | Read-only admin panel (/admin): links to every page + browse every table; secrets masked, no edits, no LLM, views audited (spec in P-003) | B | todo: deferred by user (P-003); use Datasette locally meanwhile |
| A.2 | Booking form warns when a contact is already used by another patient (shared-contact risk, P-003) | B | todo |
