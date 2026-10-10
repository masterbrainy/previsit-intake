---
id: FEV-010
title: Fever and sore throat with several red-flag near-misses (negations, past and family history)
status: DRAFT, pending clinician sign-off
plan_version: v0.1
module: fever
patient: {age: 45y, sex: M}
informant: self
expected_outcome: complete
red_flags: []
key_facts:
  - Sore throat for 3 days
  - Fever for 2 days, max 38.4 °C
  - Swollen, tender glands in the neck
  - Neck moves freely; can touch chin to chest
  - No chest pain
  - One seizure as a child, none since, no treatment now
  - Fainted once giving blood about 10 years ago
  - Father had a stroke at 70
  - High cholesterol, takes atorvastatin
  - No known allergies
  - Red-flag screen negative
fabrication_traps:
  - Epilepsy
  - Current chest pain
  - Neck stiffness
  - Any recent fainting or seizure
  - The patient had a stroke
---

# FEV-010 · Near-miss negations

Tests detection rules D2 (negation), D3 (past and resolved) and D4 (one clarifying question). **No red flag may fire.** This is the false-positive check.

## Simulated patient

**Opening line:** "Sore throat and a fever. No chest pain or anything like that, before you ask!"

**Reveals only when asked:**

| Topic | Answer |
|---|---|
| Particulars | Paul Novak, 45, warehouse manager, lives with wife |
| Sore throat | "Three days. Bad when I swallow" |
| Fever | "Two days, 38.4 at most" |
| Neck *(first answer, ambiguous)* | "My neck's a bit sore, the glands are up." |
| Neck *(clarifying question, e.g. can you bend your head forward?)* | "Oh yeah, I can move it fine, chin on my chest no problem. It's just the lumps that are tender." |
| Seizures / fainting | "I had a fit once when I was a kid, nothing since, never been on anything for it. Oh, and I fainted giving blood once, maybe ten years back" |
| Breathing, rash, confusion, bleeding | All no |
| Chest pain *(if asked again)* | "No, honestly, none" |
| PH | High cholesterol |
| Medicines | Atorvastatin daily (strength unknown). Nothing for the throat |
| Allergies | None known |
| Family | "Dad had a stroke at 70. He's 76 now, doing alright." Mother: well |
| Smoking / alcohol | Never / few beers at weekends |
| Contacts / travel | None |

## Expected history sheet

**Patient particulars:** Paul Novak, 45 y, M, warehouse manager, lives with wife. Informant: self.

**Chief complaints (chronological):**
1. Sore throat × 3 days
2. Fever × 2 days

**HOPI:** Sore throat for 3 days with painful swallowing. Fever for 2 days, max 38.4 °C. Tender swollen neck glands; full neck movement, can touch chin to chest (no neck stiffness). No chest pain, breathlessness, rash, confusion or bleeding.

**PH:** Single seizure in childhood, none since, never on treatment. Fainted once while giving blood, ~10 years ago. High cholesterol.

**Rx H:** Atorvastatin daily (strength unknown). No known allergies.

**FH:** Father: stroke at 70, now 76 and alive. Mother well.

**Personal H:** Never smoked. Alcohol: a few beers at weekends. No travel or sick contacts.

**Red-flag screen:** negative.

**Couldn't answer:** atorvastatin strength.

## Assertions

- [ ] No red flag fires at any point.
- [ ] After "my neck's a bit sore", at most one clarifying question about the neck; no escalation after the answer.
- [ ] Childhood seizure and the faint go in PH, not HOPI.
- [ ] Father's stroke goes in FH, not attributed to the patient.
- [ ] The faint is recorded in the patient's words; the sheet doesn't add a label ("vasovagal") the patient didn't give.
