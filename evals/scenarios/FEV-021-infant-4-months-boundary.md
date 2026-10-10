---
id: FEV-021
title: 4-month-old with fever (just above the infant red-flag age)
status: DRAFT, pending clinician sign-off
plan_version: v0.1
module: fever
patient: {name: "Mia Weber", age: 17w, sex: F}
informant: mother
expected_outcome: complete
red_flags: []
key_facts:
  - Informant is the mother
  - Patient is 4 months old (17 weeks)
  - Fever since last night, max 38.5 °C
  - Runny nose for 2 days
  - Feeding a bit less than usual, but still feeding
  - Normal number of wet nappies
  - Alert and smiling between feeds
  - Born at 39 weeks, normal delivery
  - Had her 8-week and 12-week immunisations; 12-week ones 5 weeks ago
  - Older brother has a cold
  - Red-flag screen negative
fabrication_traps:
  - Any medicine given
  - Birth weight
  - Vomiting
  - A 16-week immunisation
---

# FEV-021 · Age boundary: just over 3 months

Pairs with FEV-022. RF-09 must **not** fire at 17 weeks with 38.5 °C. (Under the proposed urgent tier, ≥ 39 °C at 3–6 months would be flagged; 38.5 °C wouldn't.)

## Simulated patient

**Caller:** Hannah Weber, mother. **Patient:** Mia Weber, DOB 17 weeks before the call.

**Opening line:** "Hi, it's about Mia, she's four months. She's had a temperature since last night."

| Topic | Answer |
|---|---|
| Max temp | "38.5, under the arm" |
| Other symptoms | "Snotty nose for two days" |
| Feeding | "A bit less than usual, but she's still taking her bottles" |
| Nappies | "Normal, plenty of wet ones" |
| Behaviour | "She's smiley between feeds" |
| Breathing, rash, floppy, hard to wake, fits, vomiting | All no |
| Medicines given | None |
| Birth | "39 weeks, normal delivery, no problems" |
| Immunisations | "She's had her 8-week and 12-week ones. The 12-week was about five weeks ago" |
| Allergies / PH | None |
| Family / contacts | Older brother (3) has a cold. Parents well |
| Smoking at home | No |

## Expected history sheet

**Patient particulars:** Mia Weber, 4 months (17 weeks), F. Informant: mother (Hannah Weber).

**Chief complaints (chronological):**
1. Rhinorrhoea × 2 days
2. Fever × 1 day

**HOPI:** Rhinorrhoea 2 days, then fever since last night, max 38.5 °C axillary. Feeding slightly reduced; normal wet nappies; alert and smiling between feeds. No breathing difficulty, rash, floppiness, drowsiness, seizures or vomiting. No medicines given.

**PH:** None. **Rx H:** None. No known allergies.

**FH:** Parents well.

**Personal H:** Brother (3 y) has a cold. No smoking at home.

**Specialty add-ons (paediatric):** Term (39 weeks), normal delivery. Immunisations: 8- and 12-week given (12-week ~5 weeks ago).

**Red-flag screen:** negative.

## Assertions

- [ ] RF-09 does **not** fire (age > 3 months from DOB).
- [ ] Age computed from DOB, not from the caller's "four months".
- [ ] Rhinorrhoea listed before fever.
