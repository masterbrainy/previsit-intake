"""Suggested investigations for the physician: deterministic module rules over sheet findings. No LLM."""

import operator
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from previsit.modules import ComplaintModule, Condition

OPS: dict[str, Callable[[Any, Any], bool]] = {
    ">=": operator.ge,
    ">": operator.gt,
    "<=": operator.le,
    "<": operator.lt,
    "==": operator.eq,
    "!=": operator.ne,
}


@dataclass(frozen=True)
class Suggestion:
    rule_id: str
    module_id: str
    name: str
    rationale: str
    patient_instructions: str


def _holds(condition: Condition, findings: dict[str, Any]) -> bool:
    if condition.finding not in findings:
        return False
    actual, expected = findings[condition.finding], condition.value
    if isinstance(expected, bool) != isinstance(actual, bool):
        return False
    try:
        return OPS[condition.op](actual, expected)
    except TypeError:
        return False


def suggest_investigations(modules: list[ComplaintModule], findings: dict[str, Any]) -> list[Suggestion]:
    suggestions: dict[str, Suggestion] = {}
    for module in modules:
        for rule in module.investigations:
            if rule.when and all(_holds(c, findings) for c in rule.when):
                suggestions.setdefault(
                    rule.name,
                    Suggestion(
                        rule_id=rule.id,
                        module_id=module.id,
                        name=rule.name,
                        rationale=f"{rule.rationale} (module {module.name} v{module.version}, rule {rule.id})",
                        patient_instructions=rule.patient_instructions,
                    ),
                )
    return list(suggestions.values())
