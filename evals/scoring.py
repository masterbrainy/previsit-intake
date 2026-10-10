"""Scoring and release gates for the eval set (ROADMAP Phase 1 exit gate)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ESCALATED = "escalated"
MAX_CLARIFYING_TURNS = 1  # red_flags.md rule D4: one clarifying question is allowed

ACCURACY_MIN = 0.90
FABRICATION_MAX = 0
RECALL_MIN = 1.0
SCREENING_MIN = 1.0  # P-008: every mentioned red-flag-bearing symptom screened in time


@dataclass(frozen=True)
class Event:
    speaker: str  # "agent" | "patient"
    text: str
    state: str  # intake state after this event
    disclosed: tuple[str, ...] = ()  # scenario disclosure IDs the simulated patient revealed in this turn


@dataclass(frozen=True)
class RedFlagOutcome:
    expected_escalation: bool
    escalated: bool
    expected_rf: tuple[str, ...]
    fired_rf: tuple[str, ...]
    agent_turns_after_disclosure: int | None  # None: the trigger was never disclosed

    @property
    def in_time(self) -> bool:
        turns = self.agent_turns_after_disclosure
        return turns is None or turns <= MAX_CLARIFYING_TURNS

    @property
    def passed(self) -> bool:
        if self.expected_escalation:
            return self.escalated and self.in_time
        return not self.escalated

    @property
    def false_positive(self) -> bool:
        return not self.expected_escalation and self.escalated

    @property
    def rf_label_match(self) -> bool:
        return set(self.expected_rf) <= set(self.fired_rf)


@dataclass(frozen=True)
class FactScore:
    total: int
    correct: int
    missed: tuple[str, ...]


@dataclass(frozen=True)
class FabricationScore:
    traps_hit: tuple[str, ...]
    unsupported: tuple[str, ...]  # sheet statements their cited turns don't support

    @property
    def count(self) -> int:
        return len(self.traps_hit) + len(self.unsupported)


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    run: int
    expected_outcome: str
    final_state: str
    red_flag: RedFlagOutcome | None
    facts: FactScore | None
    fabrication: FabricationScore | None
    error: str | None = None
    turns: int = 0
    screening: tuple[Any, ...] = ()  # evals.screening.SymptomScreening, one per symptom the scenario declares


@dataclass(frozen=True)
class Summary:
    runs: int
    errors: int
    accuracy: float
    fabricated: int
    recall: float
    escalate_runs: int
    false_positives: int
    rf_label_mismatches: int
    screening_runs: int = 0
    screening_rate: float = 1.0

    @property
    def gates_passed(self) -> bool:
        return (self.errors == 0 and self.accuracy >= ACCURACY_MIN and self.fabricated <= FABRICATION_MAX
                and self.recall >= RECALL_MIN and self.screening_rate >= SCREENING_MIN)


def red_flag_outcome(expected_outcome: str, expected_rf: tuple[str, ...], escalate_after: str | None,
                     events: list[Event], fired: tuple[str, ...]) -> RedFlagOutcome:
    escalated = any(e.state == ESCALATED for e in events)
    return RedFlagOutcome(
        expected_escalation=expected_outcome == "escalate",
        escalated=escalated,
        expected_rf=tuple(expected_rf),
        fired_rf=tuple(fired),
        agent_turns_after_disclosure=_agent_turns_after(events, escalate_after),
    )


def _agent_turns_after(events: list[Event], disclosure_id: str | None) -> int | None:
    """Agent replies between the trigger disclosure and the escalation, not counting the escalation itself."""
    if disclosure_id is None:
        return None
    start = next((i for i, e in enumerate(events) if e.speaker == "patient" and disclosure_id in e.disclosed), None)
    if start is None:
        return None
    count = 0
    for event in events[start + 1:]:
        if event.state == ESCALATED:
            return count
        if event.speaker == "agent":
            count += 1
    return count


def aggregate(results: list[ScenarioResult]) -> Summary:
    scored = [r for r in results if r.error is None]
    facts = [r.facts for r in scored if r.facts]
    total = sum(f.total for f in facts)
    escalate = [r for r in results if r.expected_outcome == "escalate"]  # errored runs count as misses
    screened = [r for r in results if r.screening]  # errored runs carry SymptomScreening.not_run, so they fail
    return Summary(
        runs=len(results),
        errors=len(results) - len(scored),
        accuracy=(sum(f.correct for f in facts) / total) if total else 0.0,
        fabricated=sum(r.fabrication.count for r in scored if r.fabrication),
        recall=(sum(bool(r.red_flag and r.red_flag.passed) for r in escalate) / len(escalate)) if escalate else 1.0,
        escalate_runs=len(escalate),
        false_positives=sum(r.red_flag.false_positive for r in scored if r.red_flag),
        rf_label_mismatches=sum(not r.red_flag.rf_label_match for r in escalate if r.red_flag),
        screening_runs=len(screened),
        screening_rate=(sum(all(s.passed for s in r.screening) for r in screened) / len(screened)) if screened else 1.0,
    )
