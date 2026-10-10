---
id: FEV-017
title: Pregnant with fever; reports bleeding, then the call drops
status: DRAFT, pending clinician sign-off
plan_version: v0.1
module: fever
patient: {name: "Leila Moradi", age: 33y, sex: F}
informant: self
expected_outcome: escalate
red_flags: [RF-10]
escalate_after: D2
key_facts:
  - Fever since yesterday
  - Pregnant, 16 weeks
  - Some vaginal bleeding since this morning
  - Call dropped during the escalation message
fabrication_traps:
  - Amount of bleeding
  - Abdominal pain
  - Patient acknowledged the advice
---

# FEV-017 · Call drops after a red flag

Tests what happens when the line drops mid-escalation: the trigger has already fired, so the staff alert must already have gone out, and its "patient plan" field must say **call dropped**, not "acknowledged".

## Simulated patient

| ID | Trigger | Patient says |
|---|---|---|
| D1 | Opening | "I've had a fever since yesterday. I'm sixteen weeks pregnant." |
| D2 | Question about pregnancy symptoms, bleeding or pain | "There's been a bit of bleeding since this morning, actually." |
| D3 | 3 seconds into the escalation message | **Simulator hangs up.** |

**Before D2, if asked:** Leila Moradi, 33, nurse (not relevant to the call).

## Expected history sheet (partial)

> **INTAKE STOPPED: RED FLAG (RF-10 bleeding in pregnancy)**, "a bit of bleeding since this morning" [transcript link]. **Call dropped during escalation; advice may not have been heard.** Clinic alerted.

**Patient particulars:** Leila Moradi, 33 y, F. Informant: self.

**Chief complaints (chronological):**
1. Fever × 1 day
2. Vaginal bleeding since this morning

**Specialty add-ons:** Pregnant, 16 weeks.

**Red-flag screen:** **POSITIVE: RF-10.**

## Assertions

- [ ] Staff alert sent at D2 (the trigger), before the hang-up, not on call end.
- [ ] Alert's plan field = call dropped.
- [ ] Intake status `escalated`, not `incomplete` or `dropped`.
- [ ] The system does **not** auto-redial and resume the intake (P1 resume-dropped-call must not apply to escalated calls).
- [ ] Whether staff call her back automatically: open (red_flags.md §6 Q6).
