# Roadmap: PATH (pre-visit AI history taking)

**Status:** Draft v0.6 (P-001 demo release; P-002 patient portal; P-005 hospital view + doctor accounts) · **Date:** 2026-10-09 · Companion to [PRD.md](PRD.md)

Each phase ships one arrow from the whiteboard and has to pass its exit gate before the next one starts. Safety (red-flag escalation) ships in Phase 1, because the agent talks to patients from day one.

Durations are rough estimates for a small team (2–3 engineers, 1 designer, a part-time clinical lead). Treat them as relative sizing, not commitments.

```
Phase 0  Foundations                  ████                         wk 0–4
Phase 1  Voice intake → history sheet     ██████                   wk 4–10
Phase 2  General recs + symptom logs            ████               wk 10–14
Phase 3  Medical recs + physician OK                ██████         wk 14–20
Phase 4  Results routing                                  ████     wk 20–24
Portal   Patient portal (sign-in, intake, advice, tests)          █     before the demo (P-002)
Hospital Hospital overview + doctor accounts + referrals      █     before the demo (P-005)
Demo     Working site + captioned demo video                  █     final step of the prototype
Phase 5  Scale: modules, specialties, integrations            ███→ wk 24+
```

---

## Phase 0: Foundations (weeks 0–4)

**Goal:** decide where we pilot and lock the clinical content before building.

- Pick the pilot site, specialty (likely general medicine) and market, which also settles the regulatory regime (PRD Q1–Q3)
- Appoint the clinical lead who signs off content
- Finalise the history sheet template (PRD §7) with 2–3 physicians at the pilot site
- Write the **baseline red-flag list** and escalation script
- Author the **Fever (adult) complaint module**: questions, red flags, general recs, candidate tests
- Get an initial regulatory and privacy read (CDS positioning, consent wording)
- Build the **evaluation set**: 30–50 scripted simulated patients written by clinicians, including red-flag cases, with the expected history sheet for each

**Exit gate:** template, red-flag list and Fever module signed off; eval set ready; pilot site committed.

---

## Phase 1: MVP, voice intake → history sheet (weeks 4–10)

**Whiteboard arrows:** Patient ↔ AI model → Physician (CC / HOPI / FH / PH / Rx H)

- Appointment trigger (manual entry / CSV)
- Outbound call or SMS link, identity check, consent
- Voice agent covering the full §7 structure, adaptive via the Fever module
- **Red-flag escalation** to the patient and clinic staff
- Read-back confirmation at the end of the call
- History sheet with **transcript-linked statements**
- Basic physician view: tomorrow's patients, status, sheet, PDF export
- Audit log

**Not yet:** any recommendations to anyone.

**Exit gate:**
- Eval set: ≥ 90% key-fact accuracy, **0 fabricated facts**, **100% red-flag recall**
- Shadow pilot with 20+ real patients: physicians compare the sheet to their own history and rate it useful (≥ 4/5)

---

## Phase 2: General recommendations + symptom logs (weeks 10–14)

**Whiteboard arrow:** AI model → Patient (General Recommendations)

- Clinician-approved general recommendation library for the Fever module
- Delivered at the end of the call and as a follow-up SMS
- Safety-netting ("go to the ER if...") in every message
- **Monitoring logs:** patient logs readings (e.g. temperature every 2h); logs show on the physician sheet; threshold breaches escalate

**Exit gate:** clinical lead reviews 100% of the recommendations sent during the first 2 pilot weeks with zero out-of-library advice; logging used by ≥ 40% of patients who were asked to log.

> Phases 2 and 3 can run in parallel if the team is large enough. They share no code path.

---

## Phase 3: Medical recommendations + physician approval loop (weeks 14–20)

**Whiteboard arrows:** AI model → Medical recommendation → Physician → **OK** → Patient

- Suggested investigations with rationale, tied to module rules
- Physician **Approve / Modify / Reject / Add**, mobile-friendly
- No auto-approve; silence = nothing happens
- Patient notification on approval: test, where, prep, latest time to test
- Staff hand-off for the lab order (manual)
- Approval audit trail

**Exit gate:**
- Zero cases of an unapproved recommendation reaching a patient (tested + audited)
- Physician median time-to-decision fits the window before the visit (target set in Phase 0, PRD Q8)
- Approval rate and modification patterns reviewed with the clinical lead

---

## Phase 4: Results routing (weeks 20–24)

**Whiteboard:** test results return to the physician before the visit

- Result upload (PDF/photo) by patient, lab or staff, attached to the sheet
- Physician notified when results land
- **No AI processing of results.** Enforced architecturally: results are stored and displayed, never sent to the LLM
- Dashboard status: tests approved → done → resulted

**Exit gate:** ≥ 70% of approved tests have results on the sheet before the visit; the pilot's physicians confirm the single-view workflow saves time.

**Pilot readout:** compare against PRD §12 metrics and decide go / no-go on scaling.

---

## Patient portal (added in P-002, before the demo release)

**Goal:** patients have their own portal, a key part of the product, not just a private link. Full requirements: PRD §8.10.

- Front page with **clinician** and **patient** doors; no patient data on any public page
- Patient contact (email or phone) on the appointment form and CSV import
- **One-time-code sign-in** (6 digits, 10-minute expiry, lockout after 5 wrong tries, rate limit, HttpOnly session, sign-out). Demo mode shows the code on screen; real SMS/email delivery waits for a messaging provider
- Portal home: the patient's own appointments; per appointment the intake call with the AI (OpenAI), self-care advice, approved tests, reading log, report upload, clinic messages
- The text-message link opens portal sign-in with the contact pre-filled
- Doctor's read-only **"Open patient's view"** button
- Voice stays **tap-to-talk with every AI reply checked before it plays**; make it faster and smoother (F.1, F.2)
- The AI in the portal only conducts the intake call. No chat assistant

**Exit gate:**
- A patient can only ever reach their own records (tested, including guessed IDs and old links)
- Codes expire, lock out and rate-limit as specified (tested)
- An unapproved recommendation still never appears anywhere in the portal (existing hard-rule tests extended to the portal)
- Every AI reply in the portal still passes the safety check and scope guard before the patient sees or hears it

## Hospital overview, doctor accounts, doctor choice, referrals (added in P-005, before the demo release)

**Goal:** the clinician side becomes a hospital: an overview of all patients and their doctors, individual doctor sign-in, each doctor sees only their own patients, and referrals share access. Full requirements: PRD §8.11.

- Portal booking suggests doctors (rule-based, no AI; reasons quote the patient's words, never a condition; general practice always offered); patient picks one. Emergency words show the full emergency script
- Hospital overview at `/dashboard`: all patients, assigned doctor, time, status, emergency flag; no clinical details. Staff see and acknowledge emergency alerts for every patient
- Individual doctor sign-in (email + one-time code)
- Per-patient access check on every clinical page; approvals record the signed-in doctor
- Doctor's own patient list with quick notes (never shown to patients, never sent to the AI)
- Referrals with note; receiving doctor gets access automatically; audited

**Exit gate:**
- A doctor can never open a patient they are not assigned to or referred (tested, including guessed IDs and direct URLs)
- Every approval in the audit log names the individual signed-in doctor
- An emergency alert is visible to hospital staff even when the assigned doctor is not signed in (tested)
- Doctor-suggestion text never names a condition (tested against the module keyword list)
- All existing hard-rule tests still pass under doctor sign-in

---

## Demo release: working site + demo video (final step of the prototype)

**Added in P-001.** The prototype build ends here. Audience: **clinicians and researchers**.

**Deliverable 1: a working site.** One command starts the app from a clean state with synthetic demo patients. The full flow runs without errors: booking → intake → history sheet → suggested test → physician approval → patient notification → symptom log → result upload, plus a red-flag stop. Hosting (local only, or a URL clinicians can open) is an open decision for the user.

**Deliverable 2: a demo video of that real site.**
- Recorded automatically from the running app (Playwright drives the physician and patient windows, ffmpeg assembles them side by side). It shows the **actual working flow**: no diagrams, mock-ups or abstract concept graphics.
- **Clear on-screen captions** on every step say what is happening and which safety rule it shows. Short scene labels are fine; explanation lives in the captions over real screens.
- Synthetic patient only. The patient types and the AI speaks (the AI's real text-to-speech audio is laid into the video); spoken patient input is an optional second pass.
- Waiting time may be cut, with a visible "pauses shortened" note. Nothing else is staged.

**Scenes the video must show** (clinician/researcher cut, ~5–8 min):
1. Front page with clinician and patient doors. Patient books in the portal and picks from suggested doctors (caption: rule-based, no AI, never names a condition); hospital overview shows the new booking with its assigned doctor
2. Patient signs in to the **patient portal** with a one-time code (caption notes the code is shown on screen in demo mode only), sees their appointment, and starts the intake call. Intake: consent and identity check, adaptive history questions (HOPI), read-back, general advice ending with ER safety-netting
3. The assigned doctor signs in and sees only their own patients. History sheet in the PRD §7 structure; click a statement to show the patient's own words it came from; "could not answer" items; red-flag screen
4. Suggested investigation (CBC) with its rationale and module rule, visible to the physician only. The patient's portal shows nothing until the physician approves **and** sends it, then shows the instruction
5. Patient logs temperatures in the portal; the physician sees them on the sheet
6. Lab report upload appears for the physician exactly as issued; caption states that results are never sent to the AI
7. Separate case: a red-flag symptom (stiff neck) stops the intake, sends the patient to emergency care, alerts staff, and generates no advice or tests
8. Closing card with honest limits: draft clinical content pending clinician sign-off, current eval results, demo-mode sign-in codes shown on screen, browser channel only (no phone/SMS yet), not for clinical use

**Exit gate:**
- The demo runs end to end from a clean start, twice in a row, without manual fixes
- Every scene above is in the video, recorded from the real site, with captions
- Every claim in the captions is true at the time of recording (checked by Test against the code and eval results)
- The user has watched and accepted the video

---

## Phase 5: Scale (week 24+)

Pick the order after the pilot readout.

- **More complaint modules:** cough, sore throat, abdominal pain, headache, diarrhoea, back pain, UTI symptoms, rash
- **Specialty packs:** OB/GYN (menstrual/obstetric history), pediatrics (birth, developmental, immunisation; caregiver mode), cardiology, psychiatry. Each needs its own clinical owner and red flags
- **Languages:** multilingual calls, with the sheet always in the physician's language
- **Integrations:** scheduling API, FHIR push to EHR, LIS order + results, WhatsApp
- **Physician presets** for routine approvals (opt-in only)
- Patient uploads of old prescriptions and reports during intake

---

## Never on the roadmap (by design)

- AI interpretation of results, or recommendations based on results
- AI diagnosis shown to patients
- Prescribing or dosing medication
- Ordering any test without physician approval, or auto-approving on timeout

## Key dependencies

| Dependency | Needed by |
|------------|-----------|
| Pilot site + clinical lead | Phase 0 |
| Regulatory/privacy read for the chosen market | End of Phase 0 |
| Telephony + speech provider (with a BAA or equivalent data agreement) | Phase 1 |
| Pilot lab workflow agreed with the hospital | Phase 3 |
| EHR/LIS access | Phase 5 (manual workarounds until then) |
