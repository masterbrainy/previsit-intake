"""Symptom-specific red-flag screening gate (P-008, PRD §8.2, PROGRESS 1.13).

When the simulated patient first mentions a symptom (found in their words by the list's `mention` pattern) that has its own red flags, every screening item for that symptom
must be asked within QUESTION_LIMIT agent questions. An item is exempt only if the call escalated before that window
filled. Matching is deterministic (regular expressions in screening.yaml), so the gate needs no AI judge.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

SCREENING_FILE = Path(__file__).resolve().parent / "screening.yaml"
QUESTION_LIMIT = 3  # placeholder until agreed with the clinical lead (PROGRESS 1.14)
QUESTION_STATES = {"interview"}  # agent turns that are history questions (not read-back, closing or escalation)
ESCALATED = "escalated"


@dataclass(frozen=True)
class ScreeningList:
    symptom: str
    mention: re.Pattern  # finds the symptom in the patient's own words
    items: dict[str, re.Pattern]


@dataclass(frozen=True)
class SymptomScreening:
    symptom: str
    mentioned: bool
    asked_at: dict[str, int | None]  # item -> number of the first agent question asking it, counted from the mention
    exempt: tuple[str, ...]  # not reached because the call escalated before the window filled
    limit: int
    questions_after_mention: int = 0

    @classmethod
    def not_run(cls, symptom: str) -> SymptomScreening:
        return cls(symptom, False, {}, (), QUESTION_LIMIT)

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(i for i, n in self.asked_at.items() if n is None and i not in self.exempt)

    @property
    def late(self) -> tuple[str, ...]:
        return tuple(i for i, n in self.asked_at.items() if n is not None and n > self.limit)

    @property
    def passed(self) -> bool:
        return self.mentioned and not self.missing and not self.late


def load_lists(path: Path = SCREENING_FILE) -> dict[str, ScreeningList]:
    raw = yaml.safe_load(path.read_text())
    return {symptom: ScreeningList(symptom, re.compile(spec["mention"], re.I),
                                   {item: re.compile(pattern, re.I) for item, pattern in spec["items"].items()})
            for symptom, spec in raw.items()}


def screen(events, screening_list: ScreeningList, limit: int = QUESTION_LIMIT) -> SymptomScreening:
    """Counts agent questions from the first patient turn that mentions the symptom."""
    start = next((i for i, e in enumerate(events)
                  if e.speaker == "patient" and screening_list.mention.search(e.text)), None)
    items = screening_list.items
    if start is None:
        return SymptomScreening(screening_list.symptom, False, dict.fromkeys(items), (), limit)
    questions, escalated = _questions_after(events[start + 1:])
    asked_at = {item: next((n for n, q in enumerate(questions, 1) if pattern.search(q)), None)
                for item, pattern in items.items()}
    window_cut_short = escalated and len(questions) < limit
    exempt = tuple(i for i, n in asked_at.items() if n is None and window_cut_short)
    return SymptomScreening(screening_list.symptom, True, asked_at, exempt, limit, len(questions))


def _questions_after(events) -> tuple[list[str], bool]:
    questions = []
    for event in events:
        if event.state == ESCALATED:
            return questions, True
        if event.speaker == "agent" and event.state in QUESTION_STATES:
            questions.append(event.text.lower())
    return questions, False
