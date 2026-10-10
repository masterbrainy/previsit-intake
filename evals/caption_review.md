# Caption review (PROGRESS D.6), first pass

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
