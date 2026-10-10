"""Complaint modules: clinician-authored content that drives questions, red flags, recommendations and rules.

Adding a complaint or specialty means adding a YAML file in modules/data, not code.
"""

from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

DATA_DIR = Path(__file__).parent / "data"
GENERAL_MODULE_ID = "general"

Op = Literal[">=", ">", "<=", "<", "==", "!="]


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FindingSpec(Frozen):
    key: str
    type: Literal["number", "boolean", "string"]
    description: str


class Condition(Frozen):
    finding: str
    op: Op
    value: float | bool | str


class InvestigationRule(Frozen):
    id: str
    name: str
    rationale: str
    patient_instructions: str = ""
    when: tuple[Condition, ...]


class LibraryItem(Frozen):
    id: str
    text: str


class Threshold(Frozen):
    op: Op
    value: float
    action: Literal["escalate", "flag"]
    rf_id: str | None = None
    label: str
    max_age_days: int | None = None


class MonitoringSpec(Frozen):
    metric: str
    label: str
    unit: str
    interval_hours: int
    instructions: str
    thresholds: tuple[Threshold, ...] = ()


class AddonSection(Frozen):
    name: str
    applies_when: str
    questions: tuple[str, ...]


class ComplaintModule(Frozen):
    id: str
    name: str
    version: str
    status: str
    approved_by: str | None = None
    triggers: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()
    red_flags: tuple[str, ...] = ()
    addons: tuple[AddonSection, ...] = ()
    findings: tuple[FindingSpec, ...] = ()
    general_recommendations: tuple[LibraryItem, ...] = ()
    safety_netting: tuple[str, ...] = Field(default=())
    monitoring: tuple[MonitoringSpec, ...] = ()
    investigations: tuple[InvestigationRule, ...] = ()

    def library_item(self, item_id: str) -> LibraryItem | None:
        return next((item for item in self.general_recommendations if item.id == item_id), None)


@cache
def all_modules() -> dict[str, ComplaintModule]:
    modules = {}
    for path in sorted(DATA_DIR.glob("*.yaml")):
        module = ComplaintModule.model_validate(yaml.safe_load(path.read_text()))
        modules[module.id] = module
    if GENERAL_MODULE_ID not in modules:
        raise RuntimeError("the general module is required")
    return modules


def load_module(module_id: str) -> ComplaintModule:
    try:
        return all_modules()[module_id]
    except KeyError as exc:
        raise KeyError(f"unknown complaint module {module_id!r}") from exc


def modules_for(ids: list[str]) -> list[ComplaintModule]:
    """Requested modules plus the general module, unknown IDs ignored, in a stable order."""
    known = all_modules()
    wanted = [GENERAL_MODULE_ID, *[i for i in ids if i in known and i != GENERAL_MODULE_ID]]
    return [known[i] for i in wanted]
