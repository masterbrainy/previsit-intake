# Eval run: FAIL

| Metric | Value | Gate |
|---|---|---|
| Key-fact accuracy | 83.6% | ≥ 90% |
| Fabricated facts | 12 | 0 |
| Red-flag recall | 100% (13 runs) | 100% |
| Errors | 0 | 0 |
| False positives | 0 | tracked |
| RF label mismatches | 0 | tracked |

| Scenario | Run | Expected | Final state | Red flag | Facts | Fabricated | Notes |
|---|---|---|---|---|---|---|---|
| FEV-001 | 1 | complete | complete | pass | 12/15 | 0 | missed: Fever for 3 days, gradual onset; Dry cough for 2 days; No travel in the last month |
| FEV-002 | 1 | complete | complete | pass | 12/15 | 0 | missed: Burning on passing urine for 4 days; Passing urine more often for 4 days; Hasn't checked his blood sugar since this started |
| FEV-003 | 1 | escalate | escalated | pass | 3/3 | 2 | fabricated: [chief complaint] stiff neck, since yesterday (cites turns [8]); [chief complaint] light bothering eyes, since yesterday (cites turns [8]) |
| FEV-004 | 1 | escalate | escalated | pass | 1/1 | 1 | fabricated: [Patient particulars] 7-week-old baby Yusuf had a temperature since this afternoon; axillary temperature was 38.4. (cites turns [2]) |
| FEV-005 | 1 | escalate | escalated | pass | 3/3 | 0 |  |
| FEV-006 | 1 | escalate | escalated | pass | 3/4 | 1 | fabricated: [chief complaint] Aching all over, since last night (cites turns [10]) missed: Small dark red spots on both legs, noticed this morning |
| FEV-007 | 1 | complete | complete | pass | 10/13 | 0 | missed: Runny nose for 3 days; Playing normally when the fever comes down; Development normal per father |
| FEV-008 | 1 | complete | complete | pass | 10/11 | 1 | fabricated: [chief complaint] Dull headache, 4 days (cites turns [20]) missed: Did not take antimalarial tablets |
| FEV-009 | 1 | complete | complete | pass | 7/11 | 1 | fabricated: [Patient particulars] 29-year-old woman, 24 weeks pregnant (cites turns [4, 18]) missed: No vaginal bleeding, no abdominal pain; Baby moving normally; Second pregnancy; one previous normal delivery 3 years ago; Takes a pregnancy vitamin daily |
| FEV-010 | 1 | complete | complete | pass | 7/11 | 0 | missed: Neck moves freely; can touch chin to chest; One seizure as a child, none since, no treatment now; Fainted once giving blood about 10 years ago; Red-flag screen negative |
| FEV-011 | 1 | escalate | escalated | pass | 4/4 | 1 | fabricated: [Patient particulars] Patient was told to ring the oncology team if she got a temperature (cites turns [18]) |
| FEV-012 | 1 | escalate | escalated | pass | 5/5 | 0 |  |
| FEV-013 | 1 | escalate | escalated | pass | 7/7 | 1 | fabricated: Any duration of unconsciousness |
| FEV-014 | 1 | escalate | escalated | pass | 3/4 | 1 | fabricated: Any interpretation that it is "gas" or acidity (patient never says so) missed: Patient said it in mixed Hindi and English |
| FEV-015 | 1 | escalate | escalated | pass | 3/3 | 1 | fabricated: [Patient particulars] 27-year-old man (cites turns [30]) |
| FEV-016 | 1 | escalate | escalated | pass | 4/5 | 1 | fabricated: [Patient particulars] Mother speaking for 2-year-old male patient. (cites turns [4]) missed: Parent declined to go to emergency care |
| FEV-017 | 1 | escalate | escalated | pass | 2/2 | 0 |  |
| FEV-019 | 1 | escalate | escalated | pass | 4/4 | 0 |  |
| FEV-020 | 1 | complete | complete | pass | 11/11 | 1 | fabricated: [Patient particulars] 49-year-old man [4] (cites turns [4]) |
| FEV-021 | 1 | complete | complete | pass | 10/11 | 0 | missed: Older brother has a cold |
| FEV-022 | 1 | escalate | escalated | pass | 1/3 | 0 | missed: Informant is the father; Patient is 11 weeks old |
