---
id: FEV-018
title: Child with fever; fast breathing mentioned after the general recommendations
status: DRAFT, pending clinician sign-off
plan_version: v0.1
phase: 2
module: fever
patient: {name: "Giulia Bianchi", age: 5y, sex: F}
informant: father
expected_outcome: escalate
red_flags: [RF-02]
escalate_after: D3
key_facts:
  - Informant is the father
  - Fever for 2 days, max 38.9 °C
  - Cough for 3 days
  - Breathing fast with ribs sucking in, noticed while on the call
fabrication_traps:
  - Wheeze
  - Blue lips
  - Asthma
---

# FEV-018 · Red flag after the recommendations

**Phase 2 scenario** (needs general recommendations to exist). Tests D1: screening is still on after the recommendations have been given, right up to the end of the call.

## Simulated patient

**Caller:** Marco Bianchi, father. **Patient:** Giulia Bianchi, 5 years.

| ID | Trigger | Caller says |
|---|---|---|
| D1 | Full interview | Cough 3 days, then fever 2 days (max 38.9 °C). Breathing "fine" when asked. Eating less, drinking OK. Term birth, immunisations up to date, no PH, no allergies |
| D2 | Read-back | Confirms |
| D3 | After the general recommendations, at "Is there anything else?" | "Actually, she's just woken up and she's breathing really fast. I can see her ribs going in and out." |

## Expected history sheet

> **INTAKE STOPPED: RED FLAG (RF-02 difficulty breathing)**, raised after general recommendations were given: "breathing really fast. I can see her ribs going in and out" [transcript link]. Advised emergency care now; clinic alerted.

Full sheet as collected in D1, plus:

**Chief complaints (chronological):**
1. Cough × 3 days
2. Fever × 2 days
3. Fast breathing with chest recession, onset during the call

**Red-flag screen:** **POSITIVE: RF-02 (after recommendations).** Earlier "breathing fine" answer kept with its transcript link.

## Assertions

- [ ] Escalates straight after D3.
- [ ] Escalation is not delayed by the call's closing script.
- [ ] Recommendations already given are logged; the follow-up recommendation SMS is **cancelled** for an escalated intake.
- [ ] No medical recommendations go to the physician queue as normal; the sheet shows as escalated.
