# Roadmap: Pre-Visit AI History Taking

**Status:** Draft v0.1, ready for review · **Date:** 2026-10-09 · Companion to [PRD.md](PRD.md)

Each phase ships one arrow from the whiteboard and has to pass its exit gate before the next one starts. Safety (red-flag escalation) ships in Phase 1, because the agent talks to patients from day one.

Durations are rough estimates for a small team (2–3 engineers, 1 designer, a part-time clinical lead). Treat them as relative sizing, not commitments.

```
Phase 0  Foundations                  ████                         wk 0–4
Phase 1  Voice intake → history sheet     ██████                   wk 4–10
Phase 2  General recs + symptom logs            ████               wk 10–14
Phase 3  Medical recs + physician OK                ██████         wk 14–20
Phase 4  Results routing                                  ████     wk 20–24
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
