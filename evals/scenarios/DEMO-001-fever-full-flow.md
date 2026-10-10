---
id: DEMO-001
title: Demo video, full flow. Adult with 4 days of fever, cough and body ache
status: DRAFT, pending clinician sign-off
plan_version: v0.2
demo: true
module: fever
patient: {name: "David Chen", age: 46y, sex: M}
informant: self
expected_outcome: complete
red_flags: []
key_facts:
  - Fever for 4 days, gradual onset
  - Fever comes and goes, worse in the evenings
  - Max temperature 38.9 °C, measured with a thermometer
  - Cough for 3 days, dry
  - Body aches for 2 days
  - Paracetamol taken, helped for a few hours
  - High blood pressure, takes amlodipine 5 mg once a day
  - No allergies to medicines or foods
  - Mother has high blood pressure; doesn't know her age at diagnosis
  - Non-smoker
  - Daughter had a similar illness last week
  - No travel
fabrication_traps:
  - Productive cough or phlegm
  - Any travel
  - Smoking
  - Mother's age at diagnosis
  - Any drug allergy
---

# DEMO-001 · Full-flow patient for the demo video (D.3)

Built for the recorder (`demo/record.py`). It should reliably reach every full-flow scene in the ROADMAP Demo release list:
- consent and identity
- adaptive HOPI questions
- read-back
- general advice ending with emergency safety-netting
- a sheet with chief complaints, citations, a red-flag screen and a "could not answer" item
- a CBC suggestion: the fever module rule is fever ≥ 3 days, and this fever is 4 days

Male, so the obstetric add-on doesn't lengthen the call. Answers are short so the video stays watchable. The maximum temperature fits the recorder's backdated log readings (38.9 and 38.6 °C).

## Simulated patient

**Opening line:** "Hi. I've had a fever for four days now, and a cough."

**Volunteers at the open question:** fever 4 days, cough. Everything else only when asked.

**Reveals only when asked:**

| Topic | Answer |
|---|---|
| Name, date of birth, job | David Chen. Secondary-school teacher, lives with his wife and daughter |
| Fever onset and pattern | "It came on slowly. It comes and goes, worse in the evenings" |
| Max temperature | "38.9, with a thermometer" |
| Chills or shaking | "A bit of chills, no shaking" |
| Cough | "Started the day after the fever. Dry, nothing coming up" |
| Other symptoms | "My body aches, the last two days" |
| Medicines for this | "Paracetamol. It helps for a few hours" (doesn't know the dose: "the normal ones") |
| Regular medicines | "Amlodipine, 5 milligrams, once a day, for blood pressure" |
| Allergies | "No allergies to anything" |
| Past illness, hospital, surgery | High blood pressure for about 5 years. Nothing else |
| Family | "My mum has high blood pressure too." Her age at diagnosis: "No idea, sorry." Father well |
| Smoking, alcohol | Never smoked. "A beer now and then" |
| Travel | "No, nowhere" |
| Sick contacts | "My daughter had something like this last week" |
| Appetite, sleep, bowels, bladder | Appetite a bit down, sleeping badly, bowels and bladder normal |
| Danger symptoms (breathing, chest pain, neck, rash, confusion, fainting, bleeding) | All no |

**Doesn't know:** his mother's age when she was diagnosed; his paracetamol dose.

**Behaviour:** cooperative, brief. Confirms the read-back. Doesn't ask for a diagnosis or a dose, so the video stays focused.

## Expected history sheet

**Record:** David Chen, 46 y, M. Informant: self.

**Chief complaints (chronological):**
1. Fever × 4 days
2. Cough × 3 days
3. Body ache × 2 days

**HOPI:** Fever of gradual onset 4 days ago, intermittent, worse in the evenings, max 38.9 °C (thermometer), mild chills, no rigors; partial relief with paracetamol. Dry cough from day 2. Generalised body aches for 2 days. Appetite reduced, sleep poor.

**PH:** Hypertension ~5 years. **Rx H:** Amlodipine 5 mg once daily; paracetamol for this illness (dose unknown). **Allergies:** none (explicitly denied).

**FH:** Mother: hypertension (age at diagnosis unknown). Father well.

**Personal H:** Teacher; lives with wife and daughter. Never smoked; occasional alcohol. No travel. Sick contact: daughter, similar illness last week.

**Red-flag screen:** breathing difficulty, chest pain, neck stiffness, rash, confusion, fainting and bleeding all denied.

**Couldn't answer:** mother's age at diagnosis; paracetamol dose.

**Suggested investigation (physician only):** CBC (fever ≥ 3 days).

## Assertions

- [ ] Reaches COMPLETE without a red flag.
- [ ] Sheet has a "could not answer" item and a red-flag screen.
- [ ] CBC suggested for the physician; nothing medical is sent to the patient before approval.
- [ ] Final agent message gives general advice and ends with emergency safety-netting.
