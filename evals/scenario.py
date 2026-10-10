"""Load simulated-patient scenarios (evals/scenarios/*.md, format in evals/README.md)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"
FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
DISCLOSURE_ROW = re.compile(r"^\| (D\d+[a-z]?) \|", re.M)
AGE = re.compile(r"^(\d+)([ywmd])$")
PERSONA_SECTION = "Simulated patient"


@dataclass(frozen=True)
class Scenario:
    id: str
    path: Path
    meta: dict[str, Any] = field(repr=False)
    body: str = field(repr=False)

    @property
    def expected_outcome(self) -> str:
        return self.meta["expected_outcome"]

    @property
    def red_flags(self) -> tuple[str, ...]:
        return tuple(self.meta.get("red_flags") or ())

    @property
    def escalate_after(self) -> str | None:
        return self.meta.get("escalate_after")

    @property
    def key_facts(self) -> tuple[str, ...]:
        return tuple(self.meta.get("key_facts") or ())

    @property
    def fabrication_traps(self) -> tuple[str, ...]:
        return tuple(self.meta.get("fabrication_traps") or ())

    @property
    def phase(self) -> int:
        return int(self.meta.get("phase", 1))

    @property
    def informant(self) -> str:
        return str(self.meta.get("informant", "self"))

    @property
    def patient_name(self) -> str:
        return self.meta["patient"]["name"]

    @property
    def sex(self) -> str:
        return self.meta["patient"]["sex"]

    @property
    def age(self) -> str:
        return str(self.meta["patient"]["age"])

    @property
    def disclosure_ids(self) -> tuple[str, ...]:
        return tuple(DISCLOSURE_ROW.findall(self.body))

    @property
    def persona(self) -> str:
        """The simulated-patient instructions only: no expected sheet, no assertions."""
        return section(self.body, PERSONA_SECTION)


def section(body: str, title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\s*\n(.*?)(?=^## |\Z)", body, re.S | re.M)
    return match.group(1).strip() if match else ""


def load_scenario(path: Path) -> Scenario:
    text = path.read_text()
    match = FRONT_MATTER.match(text)
    if not match:
        raise ValueError(f"{path.name}: missing YAML front matter")
    meta = yaml.safe_load(match.group(1))
    return Scenario(id=meta["id"], path=path, meta=meta, body=text[match.end():])


def load_all(ids: list[str] | None = None, max_phase: int | None = None,
             directory: Path = SCENARIO_DIR) -> list[Scenario]:
    scenarios = [load_scenario(p) for p in sorted(directory.glob("*.md"))]
    if ids:
        wanted = set(ids)
        scenarios = [s for s in scenarios if s.id in wanted]
    if max_phase is not None:
        scenarios = [s for s in scenarios if s.phase <= max_phase]
    return scenarios


def dob_for(age: str, today: date) -> date:
    """A date of birth that puts the patient safely inside the stated age (not on a boundary)."""
    match = AGE.match(age.strip())
    if not match:
        raise ValueError(f"unparseable age {age!r}; expected e.g. 34y, 7w, 4m, 10d")
    n, unit = int(match.group(1)), match.group(2)
    if unit == "d":
        return today - timedelta(days=n)
    if unit == "w":
        return today - timedelta(weeks=n, days=3)
    if unit == "m":
        return today - timedelta(days=n * 30 + 10)
    anniversary = date(today.year - n, today.month, min(today.day, 28))
    return anniversary - timedelta(days=60)
