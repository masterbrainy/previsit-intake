# Caption review (PROGRESS D.6)

## Final pass: film `demo/output/20261009T214843` (PATH-demo.mp4), code `9856f48`, plan v0.8

P-007: the user accepted the simulated text-message overlay, the synthetic patient voice and having no limits card. Those aren't flagged. Captions must still be true, must not claim SMS works, and must not claim PATH triages or assesses.

Checked every caption in `demo/captions.py` against the code, the take's database (`var/demo/demo.db`: transcripts, sheet, alert, recs, messages) and the 29 check frames.

| Caption | Verdict | Evidence / replacement |
|---|---|---|
| TITLE kicker, title | OK | |
| TITLE lede, END line 03 | **CHANGE** | Ch. 2 shows self-care advice sent with no doctor approval, which contradicts "Nothing medical reaches the patient…". **Replace with:** "No test or medical recommendation reaches the patient without the doctor's approval." |
| Chapter 1 lede | **CHANGE** | "PATH suggests the right doctor" overclaims: suggestions match the words typed (rule-based). **Replace with:** "Online, in a minute. PATH suggests doctors from what the patient types." The booking page's own text ("we'll suggest the right doctor") needs the same fix (Build). |
| Chapter 2–4 ledes | OK | |
| SIGN_IN | **CHANGE** | "A one-time code arrives by text" claims SMS delivery works, and it isn't built (PP.8). The overlay is accepted (P-007); only the caption text changes. **Replace with:** "The patient signs in with just a phone number and a one-time code." |
| DETAILS, REASON, BOOKED | OK | The frame shows the "booked by patient" badge on the overview |
| RECOMMEND | **CHANGE** | **Replace with:** "PATH suggests doctors from the words the patient typed, using simple rules rather than AI, and shows why. The patient chooses a doctor and a time." |
| CONSENT | OK | Turn 1: recorded, shared with the doctor, automated, not a doctor, emergency number |
| IDENTITY, INTERVIEW | OK | Safety runs before the interviewer on every turn |
| FAST_FORWARD | OK | True for this take: turns 21–42 cover past illnesses, medicines, allergies, family, social and travel history. F.5 (a coverage check in code) is still open, so this is not guaranteed for every call. |
| READBACK | OK | Turn 52. Minor (Build): the read-back says "his thermometer" to the patient |
| ADVICE + "No diagnosis. No prescribing. No dosing." | OK | Turn 54: library text used verbatim; no drug or dose |
| DOCTOR_SIGN_IN, MY_PATIENTS | OK | H.9 tests |
| SHEET | OK | Complaints are in onset order |
| CITATION + "Statements without a source are dropped" | OK | All 63 statements cite the patient's own turns; 0 dropped. |
| SUGGESTED, PATIENT_WAITS, APPROVE, SENT | OK | CBC suggested, then approved by anika.rao@…; the MEDICAL message is sent only after approval |
| RED_START, RED_FAST_FORWARD ("Fast-forward: consent and identity check.") | OK | |
| RED_INTERVIEW | OK as worded; **user decision** (D.7) | On screen, PATH asks "Is the headache on one side or all over?" three times. Cause: the DEMO-002 script gave a pre-D2 headache answer with no location. Fixed in DEMO-002; 6/6 live runs now give D2 at the first headache question (`demo-20261010T050800Z`, `demo-20261010T051104Z`). |
| RED_STOP | **CHANGE** (minor) | RF-07 is fever with a stiff neck; light sensitivity isn't required. **Replace with:** "Fever with a stiff neck is a red flag. PATH stops and gives fixed emergency instructions." |
| RED_ALERT | **CHANGE** | It is a banner on the overview; nobody is paged. **Replace with:** "An emergency alert appears on the hospital overview at once, with the patient's contact details. (No paging or texting in this prototype.)" The alert time on screen (04:54) is UTC, a bug (`tests/test_time_display.py`). |
| END foot | Not flagged (P-007) | True as worded. The user chose no limits line; limits are stated in the README and the submission. |
| P-006 name | OK | "PATH" only; the acronym isn't spelled out on screen, and no caption claims triage or assessment |

**Build:** apply the caption changes and fix the UTC times on the overview and doctor page (also "Sent to patient 10 Oct 04:52" and "approved … 04:53" in ch. 3). **User (D.7):** whether to re-record the red-flag take with the fixed DEMO-002 to remove the repeated question and the UTC alert time. F.6 is also visible in every run: after the patient accepts ("My flatmate can drive me now") PATH replies with the refusal script. The film cuts before this.

---

## First pass (plan v0.2)

Plan v0.2 · Reviewed `demo/captions.py` against the code at `dba1c99` and eval report `20261010T025227Z`. A final pass is due at recording time, against the code and eval run actually used.

Verdicts: **OK** = true as worded · **CHANGE** = overclaims or could mislead a clinician; replacement given.

| Caption | Verdict | Evidence / replacement |
|---|---|---|
| INTRO_* | OK | Synthetic patient, simulated by `evals/simulator.py`; draft content |
| BOOKING, OPEN_LINK | OK | No SMS adapter exists (Twilio is blocked) |
| CONSENT | OK | `intake/engine.py:70` says recorded, shared, automated, not a doctor |
| IDENTITY | OK | `intake/gates.py:54-61`: exact DOB match plus name tokens; the interview only starts after a match |
| INTERVIEW, RED_INTERVIEW (rule) | OK | Safety runs before the interviewer on every turn; `tests/test_hard_rule_escalation.py` (no interview call on a red-flag turn, every turn screened) |
| FAST_FORWARD | OK | Recorder behaviour |
| READBACK | OK | `engine.py:35` READBACK_QUESTION asks to correct or add |
| ADVICE | **CHANGE** | "clinician-authored library" is not true yet: the library is a draft awaiting sign-off. Rule "No diagnosis, no medication advice" reads as a guarantee; it is enforced by an AI check on each sentence (`safety/scope_guard.py`), which fails closed. **Replace with:** "General self-care advice, picked only from a fixed, pre-written library (draft, awaiting clinician sign-off), ending with when to go to the emergency department." Rule: "Every sentence is checked for diagnosis or medication advice before it is spoken" |
| DASHBOARD, SHEET | OK | `_sheet.html` sections |
| CITATION | **CHANGE (minor)** | Demographics come from the record and are not cited, so "every line" is too broad. Also a citation shows where a line came from; it doesn't prove the line is right (the eval measures that). **Replace with:** "Every history statement cites the patient turn it came from. Clicking a citation jumps to the patient's own words." Rule: "Statements that cite no patient turn are dropped automatically" (`sheet/extract.py` `_validate`) |
| SCREEN | OK | `red_flag_screen` and `could_not_answer` sections |
| SUGGESTED | OK | Rationale includes module, version and rule (`recs/medical.py:52`); physician-only (`tests/test_hard_rule_outbox.py::test_patient_page_never_shows_a_suggested_rec`) |
| PATIENT_NOTHING, APPROVED, SENT | OK | Approve and send are separate steps (`approval.decide`, `notify_patient_of_approved`); outbox gate tests; no scheduler (`tests/test_hard_rule_no_auto_approve.py`) |
| TEMPS, TEMPS_DOCTOR | OK | Backdating is disclosed; table and chart in `patient_detail.html:81-89` |
| UPLOAD, RESULT | OK | Stored and served as uploaded; `tests/test_hard_rule_results_isolation.py` (import graph and payload sentinel) |
| RED_STOP | OK | Fixed template in `safety/escalation.py`; `test_escalation_text_is_a_fixed_template`. Note: *detecting* the red flag is done by AI; only the wording is fixed |
| RED_STAFF | **CHANGE** | "Clinic staff are alerted immediately" suggests someone is paged. In fact a StaffAlert row and a red dashboard banner are created at the trigger; nobody is called or texted. **Replace with:** "An emergency alert appears on the clinic dashboard at once (no paging or SMS in this prototype). The partial sheet is marked INTAKE STOPPED, and no advice or tests are generated." |
| RED_PATIENT | OK | FEV-018 withdrawal; `test_self_care_advice_is_withdrawn_from_the_patient_page_after_escalation` |
| LIMITS eval line | **CHANGE** | (1) `record.latest_eval()` takes the newest `summary.md`, which may be a partial run (e.g. `-s FEV-003`, so "2 simulated cases"); it must use the latest **full** phase-1 run. (2) Wording must say the cases are team-written drafts and that fabrication is judged by a second AI. **Replace with:** "Evaluation on {n} simulated cases (written by the team, not yet clinician-reviewed): red-flag recall {recall}; key-fact accuracy {accuracy} (target 90%); fabricated facts {fabricated} as judged by a second AI (target 0)." |

## Numbers at review time

The latest full run (`20261010T025227Z`, 21 phase-1 scenarios, one run each):
- red-flag recall 100% (12/12), 0 false positives
- key-fact accuracy 88.9%
- fabricated facts 4, including one confirmed false "no known allergies" (FEV-020)

The earlier figures of 79% / 0 fabricated are out of date and must not appear in captions.

## Recorder

`demo/config.py` should use the D.3 scripts: `FULL_FLOW_SCENARIO = "DEMO-001"`, `RED_FLAG_SCENARIO = "DEMO-002"`. `uv run python -m evals.demo_check --runs 3` confirmed every scene in 4/4 (DEMO-001, final script) and 3/3 (DEMO-002) live runs. Patient turns: 28–35 (full flow), 10–13 (red flag).

## Rules for the final pass (added at plan v0.7)

- **P-006 name:** captions say "PATH". They must never say or imply that PATH triages, assesses, diagnoses or prioritises. It **takes the history** and stops to escalate red flags with a fixed script. If the acronym is spelled out on screen, follow it at once with a plain line such as "PATH takes the patient's history before the visit. It does not triage or assess."
- **P-005 overview:** the RED_STAFF replacement above should say "hospital overview" instead of "clinic dashboard". Escalations show on the overview for every patient and can be acknowledged there even when the patient's doctor is signed out.
- **P-005 doctors:** any caption about the doctor's view must say each doctor sees only their own and referred patients. Do not show one doctor opening another doctor's patient.
- **Doctor suggestions:** if the booking scene shows suggested doctors, the caption calls them "suggested from the words you typed (rule-based, no AI)". It must not say "matched to your condition".
