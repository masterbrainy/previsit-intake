# PATH

**PATH (Pre-visit Assessment & Triage Helper)** takes a patient's clinical history before a booked appointment, by voice, at home. The doctor walks into the visit with a structured history sheet in which every line links back to the patient's own words. PATH takes the history and stops there: it does not diagnose, triage or assess. Anything medical reaches the patient only after the doctor approves it.

Spec: [docs/PRD.md](docs/PRD.md) · Roadmap: [docs/ROADMAP.md](docs/ROADMAP.md) · Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · Status: [docs/PROGRESS.md](docs/PROGRESS.md) · Decisions: [docs/PIVOTS.md](docs/PIVOTS.md)

> **Prototype. Not for real patients.** All clinical content (red flags, complaint modules, advice library, test rules) is a draft pending clinician sign-off.

## How it works

**Patient (phone browser)**
1. Signs in to the portal with a mobile number or email and a 6-digit one-time code. No password.
2. Adds who the visit is for, says what it is about, and books. PATH recommends doctors with a reason for each match (rule-based, no AI); the patient picks a doctor and a time. Emergency words in the reason show the emergency script before booking.
3. Before the visit, has the pre-visit conversation with PATH, by voice (tap the microphone) or by typing. PATH asks for consent, checks name and date of birth against the booking, takes the history adaptively, reads back the main points, and ends with general self-care advice from a clinician-written library.
4. Later sees tests only once the doctor has approved and sent them, can log temperatures, and can upload lab reports.

**Doctor**
- Signs in to a personal account with a one-time code sent to their work email.
- Sees only their own patients and patients referred to them. Other doctors can't open those records unless the patient is referred.
- Per patient: the history sheet (chief complaints in order of onset, HOPI, past, drug, family and personal history, red-flag screen, what the patient couldn't answer), each line cited to the transcript; suggested investigations with their rule; approve, modify, reject or add tests, then send; symptom log; uploaded results; a read-only view of what the patient sees; referral to another doctor.

**Hospital staff**
- The hospital overview lists every appointment and the doctor it is booked with, and shows emergency escalations with the patient's contact details. It doesn't open clinical records.
- Staff can also book appointments or import them from CSV.

## Safety rules (enforced in code and covered by tests)

- No AI interpretation of results. Uploaded results are never sent to the LLM.
- No test or medical recommendation reaches the patient without explicit doctor approval. No auto-approve, no approve-on-timeout.
- PATH never diagnoses, prescribes or doses medication. A scope guard checks every line it says before the patient hears it.
- Every patient answer is screened for red flags first. A red flag stops the intake, gives fixed (not AI-written) emergency instructions, alerts staff and generates no advice or tests.
- History-sheet statements without a valid transcript citation are dropped.

## Quick start: demo site

Synthetic patients and doctors, sign-in codes shown on screen (no SMS or email is connected yet):

```bash
cp .env.example .env          # set OPENAI_API_KEY and PHYSICIAN_PASSWORD
uv sync --group demo
uv run --group demo python -m demo.serve
```

The demo site resets on every start and runs on http://localhost:8010.

| Who | Where | Sign in with |
|---|---|---|
| Patient | `/portal/sign-in` | `+15555550144` (David Chen, part-way through a pre-visit call) or any new number to register |
| Doctor | `/doctor/sign-in` | pick a doctor, e.g. Dr. Anika Rao; the code is shown on screen |
| Staff | `/dashboard` | `PHYSICIAN_USERNAME` / `PHYSICIAN_PASSWORD` from `.env` |

Demo mode must only ever be used with synthetic data and never on a public URL.

## Run for development

```bash
uv sync
uv run uvicorn previsit.web.app:lazy_app --factory --reload   # http://localhost:8000
```

Tables are created on start but not migrated: after pulling schema changes, delete `var/previsit.db`.

## Tests and evals

```bash
uv run pytest                                   # unit and hard-rule tests, no API calls
uv run pytest -m live                           # tests that call the real OpenAI API
uv run python -m evals.run                      # simulated-patient eval set (real API calls)
uv run python -m evals.run -s FEV-003 --repeat 3
```

## Demo film

```bash
uv run --group demo python -m demo.record                                      # films the real app
uv run --group demo python -m demo.assemble demo/output/<run>/timeline.json   # edits it into demo/output/<run>/PATH-demo.mp4
```

## Layout

| Path | What |
|---|---|
| `src/previsit/intake/` | Intake state machine and interviewer |
| `src/previsit/safety/` | Red-flag detection, escalation scripts, scope guard |
| `src/previsit/sheet/` | History-sheet schema and transcript-cited extraction |
| `src/previsit/recs/` | General advice (library only) and investigation rules (deterministic) |
| `src/previsit/modules/data/` | Complaint modules (YAML). Add a complaint or specialty here, not in code |
| `src/previsit/approval.py`, `outbox.py` | The doctor approval gate and the only writer of patient messages |
| `src/previsit/portal/`, `doctors.py` | One-time-code sign-in; doctor access, recommendations and referrals |
| `src/previsit/results.py` | Result uploads (no LLM access by design) |
| `src/previsit/web/` | FastAPI pages: patient portal, doctor views, hospital overview |
| `tests/`, `evals/` | Hard-rule tests and the simulated-patient eval set |
| `demo/` | Demo site, seed data and the demo-film recorder |

The Python package is still called `previsit`.

## Status and limits

- Prototype with synthetic data only; clinical content is a draft pending clinician sign-off.
- Latest eval runs: red-flag recall below 100% (45/48 on the latest run; one real miss, FEV-005, where a long-standing symptom wasn't clarified). Key-fact accuracy 89.8–91.7% (target ≥ 90%), 1–3 fabricated facts per full run (target 0). Not yet at the bar.
- No SMS, email or phone calls yet. The intake runs in the browser; sign-in codes reach users only in demo mode.
- The hospital overview uses one shared staff login; doctors have individual accounts.
- Not for clinical use.
