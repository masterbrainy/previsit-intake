# Progress

Plan version: v0.3 · Status values: `todo` · `doing` · `done` · `blocked: <reason>`
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
| 0.7 | Eval set: 30–50 simulated patient scripts with expected sheets (22 fever drafts so far, see evals/README.md) | T | doing |
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
| PP.7 | Tests: patient sees only own records (guessed IDs, old links); code expiry/lockout/rate limit; unapproved recs never shown in portal; preview is read-only; AI replies still checked before play | T | todo |
| PP.8 | Real sign-in code delivery by SMS/email | U+B | blocked: needs a messaging provider (same as F.3) |

## Demo release: working site + captioned video (final step, P-001)
| ID | Task | Owner | Status |
|---|---|---|---|
| D.1 | Demo-ready site: one-command start, clean reset script, synthetic demo patients (incl. backdated temperature readings) | B | todo |
| D.2 | Decide hosting: local only, or a URL clinicians/researchers can open | U | todo |
| D.3 | Demo patient scripts (portal sign-in → fever full flow, + stiff-neck escalation); run each ≥3× through the simulator to confirm they reliably hit every scene | T | done |
| D.4 | Automated recorder in `demo/`: Playwright drives physician + patient windows, records each | B | todo |
| D.5 | Assemble video with ffmpeg: side by side, captions on every step, AI voice audio, pauses-shortened note, closing limits card; check extracted frames | B | todo |
| D.6 | Caption review: every claim true vs code and latest eval results; wording right for clinicians | T | todo |
| D.7 | Final review: user watches and accepts the video | U | todo |

## Build follow-ups (found while building)
| ID | Task | Owner | Status |
|---|---|---|---|
| F.1 | Turn latency ~3–4 s (safety → interview → scope guard run in sequence). Options: faster models per task, streaming TTS | B | todo |
| F.2 | Completion step ~10 s (final sheet + recommendations). Say a holding line first, or generate in background | B | todo |
| F.3 | Twilio adapter for real SMS invites and phone calls (needs account) | U+B | blocked: no Twilio account |
| F.4 | Physician auth is a single shared basic-auth login; needs per-physician accounts before any pilot | B | todo |
