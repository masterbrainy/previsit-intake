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
