"""General self-care recommendations: chosen only from clinician-approved library items, text used verbatim."""

from dataclasses import dataclass

from pydantic import BaseModel

from previsit.config import Settings
from previsit.llm import LLMClient, LLMError
from previsit.modules import GENERAL_MODULE_ID, ComplaintModule, LibraryItem
from previsit.safety.context import PatientContext
from previsit.sheet.schema import HistorySheet

SYSTEM_PROMPT = """Choose which self-care items from the library fit this patient. You may ONLY return item IDs from the
library. Do not write any advice yourself. Prefer the complaint-specific items; skip items that clearly do not apply
(e.g. child items for an adult). Return 3 to 7 IDs.

{patient}

Library:
{library}"""


class SelectionOut(BaseModel):
    item_ids: list[str]


@dataclass(frozen=True)
class GeneralRecommendations:
    items: tuple[LibraryItem, ...]
    safety_netting: tuple[str, ...]
    monitoring: tuple[str, ...]

    def render(self, settings: Settings) -> str:
        lines = ["Until your appointment:"]
        lines += [f"- {item.text}" for item in self.items]
        lines += [f"- {instruction}" for instruction in self.monitoring]
        lines.append(f"Go to the emergency department now or call {settings.emergency_number} if there is:")
        lines += [f"- {sign}" for sign in self.safety_netting]
        return "\n".join(lines)

    def spoken(self, settings: Settings) -> str:
        advice = " ".join(item.text for item in self.items)
        signs = "; ".join(self.safety_netting)
        return (
            f"Until your appointment, here is what you can do. {advice} "
            f"Please go to the emergency department or call {settings.emergency_number} straight away if there is {signs}."
        )


def _library(modules: list[ComplaintModule]) -> dict[str, LibraryItem]:
    ordered = sorted(modules, key=lambda m: m.id == GENERAL_MODULE_ID)  # complaint-specific first
    library: dict[str, LibraryItem] = {}
    for module in ordered:
        for item in module.general_recommendations:
            library.setdefault(item.id, item)
    return library


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def select_general_recs(
    llm: LLMClient, modules: list[ComplaintModule], sheet: HistorySheet, ctx: PatientContext
) -> GeneralRecommendations:
    library = _library(modules)
    library_text = "\n".join(f"- {item.id}: {item.text}" for item in library.values())
    summary = "; ".join(f"{c.complaint} ({c.duration})" for c in sheet.chief_complaints) or "not recorded"
    system = SYSTEM_PROMPT.format(patient=ctx.describe(), library=library_text)
    try:
        output = llm.complete_json(
            "general_recs", system, [{"role": "user", "content": f"Chief complaints: {summary}"}], SelectionOut
        )
        chosen = [library[i] for i in _dedupe(output.item_ids) if i in library]
    except LLMError:
        chosen = []
    if not chosen:
        chosen = list(library.values())[:5]
    safety = _dedupe([sign for m in modules if m.id != GENERAL_MODULE_ID for sign in m.safety_netting])
    if not safety:
        safety = _dedupe([sign for m in modules for sign in m.safety_netting])
    monitoring = _dedupe([spec.instructions for m in modules for spec in m.monitoring])
    return GeneralRecommendations(items=tuple(chosen), safety_netting=safety, monitoring=monitoring)
