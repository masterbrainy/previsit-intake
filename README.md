# Pre-visit intake

A voice AI takes a patient's clinical history before a booked appointment. It then:

1. sends a structured **history sheet** to the physician (every line linked to the patient's own words);
2. gives the patient **general self-care advice**, chosen only from a clinician-approved library;
3. suggests **investigations to the physician only**. Nothing reaches the patient until the physician approves it.

Lab results go straight to the physician and are never read or interpreted by AI. Red-flag symptoms stop the call and send the patient to emergency care.

Spec: [docs/PRD.md](docs/PRD.md) · Roadmap: [docs/ROADMAP.md](docs/ROADMAP.md) · Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · Status: [docs/PROGRESS.md](docs/PROGRESS.md)

> **Not for real patients yet.** All clinical content (red flags, complaint modules, recommendation library, test rules) is a DRAFT pending clinician sign-off.

## Run it

```bash
cp .env.example .env        # then set OPENAI_API_KEY and PHYSICIAN_PASSWORD
uv sync
uv run uvicorn previsit.web.app:lazy_app --factory --reload
```

- Front page: http://localhost:8000/ with doors for clinicians and patients.
- Physician dashboard: http://localhost:8000/dashboard (basic auth, using `PHYSICIAN_USERNAME` / `PHYSICIAN_PASSWORD`)
- Create an appointment there with the patient's mobile number or email. The patient signs in to the portal with that
  contact and a 6-digit code; the text-message link (`/p/<token>`) only pre-fills sign-in. The patient can talk
  (tap the microphone) or type.
- No SMS/email provider is connected yet, so codes are only delivered in demo mode (`DEMO_MODE=true`, synthetic data
  only), where the code is shown on screen. The demo site does this for you:

```bash
uv run --group demo python -m demo.serve   # resets a synthetic demo site on http://localhost:8010
```

- Database tables are created on start but not migrated: after pulling schema changes, delete `var/previsit.db`.

## Test

```bash
uv run pytest            # unit + hard-rule tests, no API calls
uv run pytest -m live    # tests that call the real OpenAI API
```

## Layout

| Path | What |
|---|---|
| `src/previsit/intake/` | Intake state machine and interviewer |
| `src/previsit/safety/` | Red-flag detection, escalation script, scope guard |
| `src/previsit/sheet/` | History sheet schema and transcript-cited extraction |
| `src/previsit/recs/` | General advice (library only) and investigation rules (deterministic) |
| `src/previsit/modules/data/` | Complaint modules (YAML). Add a complaint or specialty here, not in code |
| `src/previsit/approval.py`, `outbox.py` | Physician approval gate and the only writer of patient messages |
| `src/previsit/results.py` | Result uploads (no LLM access by design) |
| `src/previsit/web/` | FastAPI pages for physicians and patients |
| `tests/`, `evals/` | Hard-rule tests and the simulated-patient eval set |

Phone calls (Twilio) aren't wired up yet. The intake runs in the browser through the same engine.
