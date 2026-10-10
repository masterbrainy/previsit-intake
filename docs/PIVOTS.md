# Pivot & decision log

Newest entry at the bottom. Only the Plan & Pivot session writes here, and only after the user confirms.

Entry template:

```
## P-00N · YYYY-MM-DD · <short title>
Plan version: vX.Y → vX.Z
What changed:
Why:
Impact on in-flight work:
Tasks added / removed / changed (PROGRESS.md IDs):
```

---

## P-000 · 2026-10-09 · Baseline
Plan version: — → v0.1
What changed: initial PRD and roadmap.
Why: kickoff, based on the whiteboard flow (patient ↔ AI → physician history sheet; general recs → patient; medical recs → physician → OK → patient).
Scope decisions already made: no recommendations based on blood test results; results go to the physician raw.

## P-001 · 2026-10-09 · Final step: demo-ready working site + captioned demo video for clinicians/researchers
Plan version: v0.1 → v0.2
What changed: the prototype build (Phases 1–4) now ends with a **Demo release** step (new roadmap section, PROGRESS IDs D.1–D.7). Two deliverables: (1) a working site that runs the full flow cleanly from a fresh start with synthetic patients, and (2) a video of that real site, recorded automatically (Playwright) and assembled with ffmpeg, with clear on-screen captions explaining each step. Audience: clinicians and researchers. The video shows the actual working flow, not diagrams or abstract concept graphics.
Why: the user wants to show the working system to clinicians/researchers. They care about the safety design (physician approval gate, transcript traceability, results never reaching the AI, red-flag stop) and about honest limits, so the video must show real behaviour and state limits plainly.
Impact on in-flight work: none blocked. Phases 1–4 code is done; the demo step uses it as built. Open follow-ups (F.1 latency, F.2 completion wait, F.4 shared login) stay open; the video cuts waiting time with a visible "pauses shortened" note and does not hide the shared login. Phone/SMS (F.3) stays out of the video; it shows the browser voice page, which is what exists.
Tasks added / removed / changed (PROGRESS.md IDs): added D.1–D.7. Nothing removed. Hosting (local vs a hosted URL clinicians can open) is an open user decision, D.2.

## P-002 · 2026-10-09 · Patient portal as a key part of the product
Plan version: v0.2 → v0.3
What changed: patients get a **portal**, not only a private link. A front page has clinician and patient doors. Patients sign in with a **one-time code** sent to the email/phone on their appointment (demo mode shows the code on screen; real delivery needs a messaging provider). The portal home lists the patient's own appointments; per appointment: the **intake call with the AI (OpenAI)**, self-care advice, approved tests, reading log, report upload, clinic messages. The text-message link opens portal sign-in. Doctors get a read-only "Open patient's view" button. The demo video now shows the portal sign-in and portal pages.
Decisions (user, 2026-10-09): (1) the AI in the portal **only conducts the intake call**; no open-ended chat assistant (added to PRD non-goals). (2) Sign-in by one-time code, no passwords. (3) Voice stays **tap-to-talk with every AI reply checked before it plays**; hands-free live voice (OpenAI Realtime) is out of scope until it can keep the check-before-speaking guarantee.
Why: the user sees the patient side as a key part of the product. The site's front page went straight to the doctor dashboard, and the patient page was only reachable through a link shown once at booking.
Hard rules: unchanged and still enforced. Risks pushed back on and excluded: a general patient chatbot (would invite diagnosis, medication and results questions); live speech-to-speech that bypasses the pre-play safety check.
Impact on in-flight work: patient routes move behind portal sign-in, so existing patient-page tests that use `/p/<token>` will need updating (Test). Phone/SMS and code delivery share the Twilio/messaging blocker (F.3, PP.8). F.1/F.2 (latency) matter more now that the portal call is the centrepiece. The demo release (D.*) now comes after the portal; scenes 1, 2, 4 and 5 updated. Shared physician login (F.4) is unchanged.
Tasks added / removed / changed (PROGRESS.md IDs): added PP.1–PP.8; D.3 updated to start from portal sign-in. Nothing removed. The earlier "front page + Open patient's view" proposal (D.8) is folded into PP.1 and PP.6.

## P-003 · 2026-10-09 · Portal identity rules; admin panel deferred; video kept
Plan version: v0.3 → v0.4
What changed:
- Portal rules written into PRD §8.10 (all three were Build's working assumptions; user decided):
  1. **A shared contact shows every patient booked with it**, each appointment labelled with the patient's name. Plan & Pivot recommended asking date of birth when several patients share a contact; the user chose "show everyone". The risk is logged in PRD §13 with a mitigation for before real use.
  2. Same name + DOB + contact = same patient across bookings.
  3. Physicians reach the patient side only through the read-only "Open patient's view".
- **Admin panel deferred** (A.1): the user asked for a read-only admin panel with links to everything plus a database browser, then dropped it from today's 15-minute push. The spec is kept on the row. Meanwhile the database can be browsed locally with Datasette (read-only; shows secrets unmasked, so local and synthetic data only).
- **Not changed:** the user was offered a pivot dropping the demo video for today's 15-minute scope cut and declined. The video (D.4–D.7) stays the final step of the plan; it is simply not done today. The working site (one command: `uv run --group demo python -m demo.serve`, port 8010) is delivered.
Why: user decisions on 2026-10-09 during the 15-minute finish push.
Impact on in-flight work: no code change needed for rules 1–3 (already built that way). New follow-ups: A.1 (deferred), A.2 (shared-contact warning on booking). Eval gate still unmet (~88% key-fact accuracy vs 90%, 0–1 fabricated, 100% red-flag recall); Phase 1 stays unpassed.
Tasks added / removed / changed (PROGRESS.md IDs): added A.1 (deferred) and A.2. D.* unchanged.

## P-004 · 2026-10-09 · Patient self-registration and self-booking
Plan version: v0.4 → v0.5
What changed: patients can set up their own details and book their own appointments in the portal. Decided by the user in the Build session (bookings live immediately with no clinic confirmation; anyone can register after verifying a phone or email with the code), already built and pushed by Build (cfded44, PB.1). Confirmed for logging by the user in this session, with pilot guards added.
Rules (PRD §8.10): every contact gets a code, including contacts not on file, so there is no account enumeration. Self-registered patients are marked `self_registered` ("identity not checked by clinic" on the doctor's page). Bookings are only for people on the contact, with a listed doctor, at a future time within a year, max 5 upcoming per patient. The doctor sees a "booked by patient" badge. Known gap: no availability/calendar check.
Reverses: the PRD non-goal "Appointment booking" (calendar/availability management stays out of scope).
Hard rules: unchanged. The physician approval gate, check-before-play, results-never-to-LLM and red-flag stop all still apply to self-booked visits.
Why: the user wants patients to be able to start on their own in the portal, not only from a clinic booking.
Risks raised by Plan & Pivot: double-bookings and visits the clinic doesn't know about; unchecked identities on history sheets; open sign-up running up OpenAI costs (in demo mode the code is shown on screen, so verification is effectively off); conflict with a clinic's real scheduling system.
Pilot guards (user-approved, required before any real-patient pilot): bookings come from or sync with the clinic scheduling system, or need clinic confirmation before the intake runs (PB.2); sign-up and AI-spend caps for any public hosting (PB.3); clinic checks self-registered identities before the visit.
Impact on in-flight work: demo video scenes may show self-booking as an alternative to scene 1 (optional). Test: extend portal tests to self-registration and booking limits if not already covered.
Tasks added / removed / changed (PROGRESS.md IDs): PB.1 (done, Build); added PB.2, PB.3 (pilot guards), PB.4 (availability check).

## P-005 · 2026-10-09 · Hospital overview, individual doctor accounts, doctor choice, referrals
Plan version: v0.5 → v0.6
What changed (user's reframe, given in the Build session, confirmed in this session with adjustments):
- Patients book in the portal; the system **suggests doctors** and the patient picks one.
- The clinician dashboard becomes a **hospital overview** of all patients with their assigned doctor.
- **Individual doctor sign-in**; each doctor sees all their own patients with quick notes.
- A **referral** automatically gives the receiving doctor access. A patient who is only with one doctor is visible only to that doctor unless referred.
Build's implementation choices (accepted): rule-based suggestions (specialty + keywords, paediatrics boost under 16, GP fallback, fewest-upcoming tiebreak, reasons shown); overview behind the staff login with names, doctor, time, status and emergency flag but no clinical details; doctor sign-in by email + one-time code; per-patient access (assigned or referred, else 404) on all clinical routes; approval.decide records the signed-in doctor; audited referrals; staff booking picks a doctor.
Adjustments by Plan & Pivot, accepted by the user:
1. Suggestion reasons only quote the patient's words and never name a condition; general practice is always offered (suggesting by symptoms sits close to the hard rule about unapproved medical recommendations reaching patients).
2. Emergency words in a booking reason show the full fixed emergency script, acknowledged before continuing, audit-logged (no staff alert from a keyword alone).
3. Emergency alerts stay visible and acknowledgeable on the hospital overview for every patient; an alert never depends on one doctor being signed in.
4. Pilot guards: break-glass access for a covering doctor (audited); demo-mode code display never on a public URL; individual staff accounts for the overview.
Hard rules: unchanged. Quick notes are clinician-only and never sent to the AI.
Why: the user reframed the clinician side as a hospital with individual doctors, their own patient lists, and referral-based sharing.
Impact on in-flight work: resolves F.4 (shared physician login) and the §8.6 approval-audit gap. All clinical routes move behind doctor sign-in, so Test's route tests and the demo recorder need updating. Demo scenes 1, 3 and 8 updated. Earlier pending proposal "individual doctor logins as a Phase 3 gate item" is now covered.
Tasks added / removed / changed (PROGRESS.md IDs): added H.1–H.11 (H.1–H.8 doing in Build, H.9 Test, H.10–H.11 pilot guards); F.4 marked superseded.

## P-006 · 2026-10-09 · Product named PATH
Plan version: v0.6 → v0.7
What changed: the product is named **PATH (Pre-visit Assessment & Triage Helper)**, replacing the placeholder "Pre-Visit Intake". PRD and ROADMAP titles updated. README, UI text, pyproject description and the GitHub description move to PATH (Build, N.1–N.3).
Not renamed (deliberately): the Python package `previsit`, the local folder `/Users/brianhuang/Projects/previsit-intake` (all sessions use this absolute path), and the session titles "… · Pre-visit intake" (the messaging protocol matches them exactly). Renaming the GitHub repository itself waits for the user's confirmation, because it changes the public URL.
Why: user decision for the hackathon pitch and write-up.
Note: Plan & Pivot flagged that "Triage" and "Assessment" in the expansion describe things PATH deliberately does not do; the user kept the name. The PRD states that PATH takes the history and does not triage or assess, and the non-goals are unchanged.
Impact on in-flight work: copy changes only; no behaviour change. Demo captions should use "PATH".
Tasks added / removed / changed (PROGRESS.md IDs): added N.1–N.3.

## P-007 · 2026-10-09 · Demo film is a best-vision cut
Plan version: v0.7 → v0.8
What changed: the user asked Build for an "ideal vision" film, and Build delivered `demo/output/PATH-demo.mp4` (2:56, captions, both sides). It departs from the P-001 spec in three ways, all confirmed by the user in this session: no closing limits card ("prototype / simulated patients / not for clinical use" is not on screen); the sign-in code arrives as a simulated text-message overlay although SMS is not built; the simulated patient's voice is synthetic and dubbed over typed answers rather than passing through the app's speech-to-text. The AI's replies, the doctor side and all other screens are the real running app.
Why: user decision; the film is for the hackathon pitch as a best-vision piece.
Plan & Pivot advised adding a "simulated" tag on the text message and a one-line "prototype, not for clinical use" closing line (~2 s), because clinician judges may read the SMS as a working feature and medical-AI demos without a disclaimer can look like overclaiming. The user chose to keep the film as is. Limits remain stated in the README and the written submission.
Impact on in-flight work: D.4/D.5 done as delivered. D.6 (caption review) can run now; captions must still be true and must not claim SMS works or that PATH triages/assesses. D.7 is the user's review. N.3 (GitHub description) approved by the user; repo rename not approved.
Tasks added / removed / changed (PROGRESS.md IDs): ROADMAP demo spec updated (staged elements listed, limits card dropped). No task IDs added.

## P-008 · 2026-10-09 · Symptom-specific red-flag screening as a Phase 1 gate item; red-flag film take re-recorded
Plan version: v0.8 → v0.9
What changed:
- **Safety gap → Phase 1 gate.** Test's new eval case FEV-023 (stiff neck revealed only when asked) is caught 4/4, but only 7–10 questions in, and in 3/4 runs the agent never asked about the headache itself, so a sudden "worst ever" headache (proposed RF-16) would go unscreened. New P0 requirement (PRD §8.2): any mentioned symptom with its own red flags gets its screening questions early. New Phase 1 exit-gate item: screening asked in reveal-only-when-asked cases, with escalation within a question limit agreed with the clinical lead. Tasks 1.12 (Build), 1.13 (Test), 1.14 (clinician sign-off, user).
- **Film fix.** The best-vision film's red-flag scene shows the same question asked three times (demo-script issue, fixed by Test, 6/6 clean runs) and the alert time in UTC (display bug, with Build). Re-record only that take and re-render with Test's 6 caption fixes (three of which corrected wording against plan rules: "code arrives by text", non-rule-based "suggests the right doctor", and an alert caption implying paging). Task D.8.
Why: user decisions in this session, on Test's D.6 findings.
Hard rules: unchanged; this strengthens "red-flag symptoms stop the intake and escalate".
Impact on in-flight work: Phase 1 stays unpassed until 1.12–1.14 are met, alongside the existing accuracy bar. Overlaps F.5 (coverage checklist); Build may implement both together. D.7 (user review) follows D.8.
Tasks added / removed / changed (PROGRESS.md IDs): added 1.12, 1.13, 1.14, D.8.

### P-008 addendum · 2026-10-09 · Long-standing symptoms (no version bump; clarifies P-008 scope)
Test's recall re-run after 1.15 (45/48; FEV-025 now 3/3) found a gap that already existed: "I'm always a bit short, with the COPD" is judged clear, so catching a worsening depends on the interviewer happening to ask. Within P-008's confirmed scope (breathlessness was already listed), PRD §8.2 now says a long-standing symptom gets "worse than usual?", and the safety check treats it as unclear until answered. Task 1.16 (Build). The other two misses were harness issues (scoring mis-tag, simulator never consenting), for Test to fix.
