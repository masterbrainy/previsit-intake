# Pre-Visit Intake: shared context for all sessions

**Plan version: v0.4** (bump on every pivot; see docs/PIVOTS.md)

Voice AI takes a patient's clinical history before a booked visit. It sends a structured history sheet to the physician, general self-care recommendations to the patient, and suggested investigations to the physician only. Nothing medical reaches the patient without physician approval. Results go to the physician uninterpreted.
Spec: [docs/PRD.md](docs/PRD.md) · Plan: [docs/ROADMAP.md](docs/ROADMAP.md) · Status: [docs/PROGRESS.md](docs/PROGRESS.md) · Decisions: [docs/PIVOTS.md](docs/PIVOTS.md)

## Hard product rules (never violate, whatever the session)
- No AI interpretation of test results; results never get sent to the LLM.
- No test or medical recommendation reaches the patient without explicit physician approval. There is no auto-approve and no approve-on-timeout.
- The agent never diagnoses, prescribes, or doses medication.
- Red-flag symptoms stop the intake and escalate to emergency care.

## Three sessions, one folder
All sessions read and write the **main checkout at `/Users/brianhuang/Projects/previsit-intake`** using absolute paths, even if the app gave a session its own worktree. This keeps the state shared and live.

| Session (exact title) | Role | Owns (only it edits) |
|---|---|---|
| **Build · Pre-visit intake** | Main. Implements roadmap tasks, makes **all git commits/pushes**, renders progress visuals for the user | `src/`, app config, `docs/PROGRESS.md` build rows |
| **Plan & Pivot · Pre-visit intake** | Mostly idle. Acts only when the user proposes a pivot | `docs/PRD.md`, `docs/ROADMAP.md`, `docs/PIVOTS.md`, the plan version line above |
| **Test & Support · Pre-visit intake** | Writes tests first (TDD), runs suites, builds the eval set, reviews Build's changes, debugs on request | `tests/`, `evals/`, test rows in `docs/PROGRESS.md` |

Need a change in a file you don't own? Message its owner instead of editing it.

## Messaging
Find the other sessions with `list_sessions` (match the exact titles above) and message them with `send_message`. Keep messages short: what changed, which files, and what you need.

## Pivot protocol (Plan & Pivot session)
1. Discuss the pivot with the user. Don't write anything until they confirm it.
2. Append an entry to `docs/PIVOTS.md`: what changed, why, impact on in-flight work, tasks added/removed.
3. Update `docs/PRD.md` / `docs/ROADMAP.md`, adjust tasks in `docs/PROGRESS.md`, and bump **Plan version** above.
4. Message Build and Test with the pivot ID and a one-paragraph summary.
5. Build commits the doc changes as `docs: pivot P-00N ...`.

**Every session:** before starting a new task, check the Plan version line. If it changed since you last looked, read the newest docs/PIVOTS.md entry first.

## Progress protocol
- `docs/PROGRESS.md` is the single source of truth for status: `todo` → `doing` → `done` (or `blocked: reason`).
- Update your rows when you start or finish a task, not at the end of the day.
- Build shows the user a progress visual after each finished task or milestone.
