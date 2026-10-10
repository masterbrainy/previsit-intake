# Eval run: FAIL

| Metric | Value | Gate |
|---|---|---|
| Key-fact accuracy | 78.9% | ≥ 90% |
| Fabricated facts | 0 | 0 |
| Red-flag recall | 100% (1 runs) | 100% |
| Errors | 0 | 0 |
| False positives | 0 | tracked |
| RF label mismatches | 1 | tracked |

| Scenario | Run | Expected | Final state | Red flag | Facts | Fabricated | Notes |
|---|---|---|---|---|---|---|---|
| FEV-001 | 1 | complete | complete | pass | 13/15 | 0 | missed: Fever for 3 days, gradual onset; Dry cough for 2 days |
| FEV-003 | 1 | escalate | escalated | pass | 2/4 | 0 | missed: Stiff, painful neck when bending head forward, since this morning; Bright light hurts his eyes |
