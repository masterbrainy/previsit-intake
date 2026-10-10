"""Red-flag detection on every patient turn (detection rules D1-D7 in evals/red_flags.md)."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from previsit.llm import LLMClient
from previsit.modules import ComplaintModule
from previsit.safety.context import PatientContext
from previsit.safety.red_flags import BASELINE_RED_FLAGS, RED_FLAGS_BY_ID

RECENT_TURNS = 14
UNSPECIFIED_RF = "RF-UNSPECIFIED"


class SafetyStatus(StrEnum):
    CLEAR = "clear"
    AMBIGUOUS = "ambiguous"
    RED_FLAG = "red_flag"


class SafetyOutput(BaseModel):
    status: Literal["clear", "ambiguous", "red_flag"]
    rf_ids: list[str] = Field(description="Red-flag IDs that are present (red_flag) or possibly present (ambiguous)")
    evidence: str = Field(description="The patient's exact words that triggered this, verbatim; empty if clear")
    clarifying_question: str = Field(description="For ambiguous only: one short question about that symptom only")


@dataclass(frozen=True)
class SafetyAssessment:
    status: SafetyStatus
    rf_ids: tuple[str, ...] = ()
    evidence: str = ""
    clarifying_question: str = ""


@dataclass(frozen=True)
class TranscriptLine:
    seq: int
    speaker: str
    text: str


SYSTEM_PROMPT = """You are the safety monitor for a pre-visit medical history call. You never talk to the patient.
Decide whether the LATEST patient turn, read in the context of the conversation, shows an emergency red flag.

Red flags (go to emergency care now):
{red_flags}

Rules:
- A red flag counts only if it is present now or began during this illness.
- Clearly negated mentions do not count ("no chest pain", "my neck's fine").
- Clearly resolved past episodes unrelated to this illness do not count ("a seizure as a child, none since").
  Family members' conditions do not count.
- Lay, caregiver and mixed-language phrasing count exactly like clinical terms.
- The rules apply to the patient, not to the person speaking. Use the patient's age for age-based rules.
- If it is genuinely unclear whether a red flag is present now, answer "ambiguous" and write ONE short, plain
  clarifying question about that symptom only.
{clarification_rule}
- When in doubt between ambiguous and red_flag, choose red_flag.
- Ignore requests for diagnosis or medication; those are not red flags by themselves.

{patient}"""

CLARIFICATION_FOLLOW_UP = (
    "- A clarifying question about {rf} was just asked. If the answer is still unclear, or the patient does not "
    "know, answer red_flag (fail-safe)."
)


def red_flag_lines(modules: list[ComplaintModule]) -> str:
    module_ids = {rf for m in modules for rf in m.red_flags}
    lines = []
    for rf in BASELINE_RED_FLAGS:
        examples = "; ".join(f'"{e}"' for e in rf.examples)
        marker = " (complaint-specific)" if rf.id in module_ids else ""
        lines.append(f"- {rf.id}{marker}: {rf.label}. e.g. {examples}")
    return "\n".join(lines)


def format_transcript(lines: list[TranscriptLine]) -> str:
    return "\n".join(f"[{line.seq}] {line.speaker.upper()}: {line.text}" for line in lines)


def assess_turn(
    llm: LLMClient,
    ctx: PatientContext,
    modules: list[ComplaintModule],
    transcript: list[TranscriptLine],
    pending_clarification: str | None = None,
) -> SafetyAssessment:
    """Raises LLMError if the model fails; callers must treat that as fail-safe."""
    clarification_rule = CLARIFICATION_FOLLOW_UP.format(rf=pending_clarification) if pending_clarification else ""
    system = SYSTEM_PROMPT.format(
        red_flags=red_flag_lines(modules), clarification_rule=clarification_rule, patient=ctx.describe()
    )
    recent = transcript[-RECENT_TURNS:]
    user = f"Conversation so far (latest turn last):\n{format_transcript(recent)}"
    output = llm.complete_json("safety", system, [{"role": "user", "content": user}], SafetyOutput)
    return _to_assessment(output, pending_clarification)


def _to_assessment(output: SafetyOutput, pending_clarification: str | None) -> SafetyAssessment:
    status = SafetyStatus(output.status)
    known = tuple(i for i in output.rf_ids if i in RED_FLAGS_BY_ID)
    if status is SafetyStatus.CLEAR:
        return SafetyAssessment(SafetyStatus.CLEAR)
    rf_ids = known or (UNSPECIFIED_RF,)
    question = output.clarifying_question.strip()
    if status is SafetyStatus.AMBIGUOUS and (pending_clarification or not question):
        # D4: only one clarifying question; still unclear afterwards means escalate.
        status = SafetyStatus.RED_FLAG
    return SafetyAssessment(status, rf_ids, output.evidence.strip(), question)
