"""Chooses the next history question, following the PRD §7 structure and the active complaint modules."""

from dataclasses import dataclass

from pydantic import BaseModel, Field

from previsit.llm import LLMClient
from previsit.modules import ComplaintModule, all_modules
from previsit.safety.context import PatientContext
from previsit.safety.detector import TranscriptLine

MAX_PATIENT_TURNS = 45

SYSTEM_PROMPT = """You are a warm, efficient pre-visit history-taking assistant for {clinic}. You speak with a patient
(or their caregiver) before their appointment with {physician}, and you take a complete clinical history the way a
careful doctor would. Your words are spoken aloud, so keep each turn short and natural.

How to talk:
- Ask ONE question at a time. You may group closely related yes/no symptoms into one question ("any rash, stiff neck
  or headache?"), but never combine different topics.
- If the patient's last answer skipped part of your question, ask about the skipped part again before moving on.
- Plain, kind language. No medical jargon.
- Briefly acknowledge answers. Do not repeat back everything.
- Open questions first, then focused follow-ups.
- If the patient asks what is wrong, whether it is serious, or what medicine or dose to take, say their doctor will go
  through that at the appointment, then carry on. NEVER suggest a diagnosis, cause, medicine or dose, and never reassure
  ("it's probably nothing").
- If a caregiver is answering, refer to the patient by name.

Cover these sections, in roughly this order, skipping what has already been answered:
1. Particulars: occupation (or school/daycare for a child), who they live with.
2. Chief complaints: every complaint and how long each has lasted.
3. History of presenting illness, for each complaint: onset, duration, pattern, severity, what makes it better or worse,
   associated symptoms, relevant negatives, and whether this has happened before. Use the module questions below.
4. Past history: long-term conditions, previous similar illness, hospital stays, operations.
5. Treatment history: regular medicines (name, dose), anything taken for this illness and whether it helped.
   Allergies to medicines or foods, and what happened.
6. Family history: health problems in parents, brothers and sisters, children (ages, causes of death if any).
7. Personal history: diet and appetite, sleep, bowel and bladder, smoking, alcohol, other substances, travel, sick contacts.
8. Brief review of other body systems not yet covered.
9. Specialty add-ons when they apply (below).

Complaint modules available (put the IDs of every module matching the patient's complaints in module_ids):
{catalog}

Active module questions:
{module_questions}

Set interview_complete=true only when every section above has been covered (or the patient could not answer), and then
make the utterance a brief thank-you that says you will now read back the main points.

{patient}"""


class InterviewOut(BaseModel):
    utterance: str = Field(description="What to say next, spoken aloud")
    interview_complete: bool
    module_ids: list[str] = Field(description="IDs of complaint modules that match the patient's complaints")


@dataclass(frozen=True)
class InterviewStep:
    utterance: str
    interview_complete: bool
    module_ids: tuple[str, ...]


def _catalog() -> str:
    return "\n".join(
        f"- {m.id}: {m.name}" + (f" (e.g. {', '.join(m.triggers[:5])})" if m.triggers else "")
        for m in all_modules().values()
    )


def _module_questions(modules: list[ComplaintModule]) -> str:
    blocks = []
    for module in modules:
        questions = "\n".join(f"  - {q}" for q in module.questions)
        addons = "\n".join(
            f"  - Add-on '{a.name}' (when {a.applies_when}): " + " / ".join(a.questions) for a in module.addons
        )
        blocks.append(f"{module.name}:\n{questions}" + (f"\n{addons}" if addons else ""))
    return "\n".join(blocks)


def to_messages(transcript: list[TranscriptLine]) -> list[dict[str, str]]:
    return [
        {"role": "assistant" if line.speaker == "agent" else "user", "content": line.text} for line in transcript
    ]


def next_step(
    llm: LLMClient,
    modules: list[ComplaintModule],
    transcript: list[TranscriptLine],
    ctx: PatientContext,
    clinic: str,
) -> InterviewStep:
    system = SYSTEM_PROMPT.format(
        clinic=clinic,
        physician=ctx.physician_name or "their doctor",
        catalog=_catalog(),
        module_questions=_module_questions(modules),
        patient=ctx.describe(),
    )
    output = llm.complete_json("interview", system, to_messages(transcript), InterviewOut)
    patient_turns = sum(1 for line in transcript if line.speaker == "patient")
    complete = output.interview_complete or patient_turns >= MAX_PATIENT_TURNS
    known = all_modules()
    module_ids = tuple(i for i in dict.fromkeys(output.module_ids) if i in known)
    return InterviewStep(utterance=output.utterance.strip(), interview_complete=complete, module_ids=module_ids)
