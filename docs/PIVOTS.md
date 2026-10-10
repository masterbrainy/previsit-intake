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
