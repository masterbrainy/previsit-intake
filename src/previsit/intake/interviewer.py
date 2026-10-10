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
  Never ask the same thing more than twice: after a second unanswered attempt, move on (it will be recorded as unanswered).
- Plain, kind language. No medical jargon.
- Briefly acknowledge answers. Do not repeat back everything.
- Open questions first, then focused follow-ups.
- If the patient asks what is wrong, whether it is serious, or what medicine or dose to take, say their doctor will go
  through that at the appointment, then carry on. NEVER suggest a diagnosis, cause, medicine or dose, and never reassure
  ("it's probably nothing").
- If a caregiver is answering, refer to the patient by name.

Cover these sections, in roughly this order, skipping only what the patient has ALREADY clearly answered:
1. Particulars: occupation (or school/daycare for a child), who they live with.
2. Chief complaints: keep a running list of EVERY complaint the patient mentions, including those in their very first
   answer and anything they felt BEFORE the main problem (e.g. tired for weeks before the fever). For EACH complaint,
   ask when it started unless the patient gave that exact complaint's start themselves. Never assume one complaint
   started when another did.
3. History of presenting illness: walk through EACH complaint on the list, one at a time, before moving to section 4:
   onset (sudden or gradual), duration, pattern, severity, what makes it better or worse, associated symptoms, relevant
   negatives, and whether this has happened before. Use the module questions below.
4. Past history: long-term conditions, previous similar illness, hospital stays, operations, and any past fits,
   faints or serious illnesses.
5. Treatment history: regular medicines and supplements (name, dose), anything taken for this illness, when, and whether
   it helped. Then ALWAYS ask about allergies as its own question: any allergy to medicines or foods, and what happened.
6. Family history: health problems in parents, brothers and sisters, children (ages, causes of death if any).
7. Personal history: diet and appetite, sleep, bowel and bladder, smoking, alcohol, other substances, sick contacts,
   and travel in the last 3 months (always ask; if they travelled, where, and any preventive tablets or vaccines).
8. Specialty add-ons: MANDATORY whenever they apply (pregnancy, children). Ask every add-on question listed below,
   one at a time; before finishing, check none was skipped.
9. Safety screen, before finishing: ask plainly about each of these that has not already been asked, a few per question:
{screen}
10. Brief review of other body systems not yet covered.

Complaint modules available (put the IDs of every module matching the patient's complaints in module_ids):
{catalog}

Active module questions:
{module_questions}

Set interview_complete=true only when every section above has been covered (or the patient could not answer). Before
finishing, check you have asked about allergies, travel, every add-on and the safety screen. Then make the utterance a
brief thank-you that says you will now read back the main points.

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


SCREEN_QUESTIONS = {
    "RF-01": "chest pain or tightness",
    "RF-02": "trouble breathing or breathlessness at rest",
    "RF-04": "fainting, passing out or fits during this illness",
    "RF-05": "bleeding that won't stop, vomiting blood or black stools",
    "RF-07": "a stiff neck (can they bend their head forward)",
    "RF-08": "any rash, and whether it fades when pressed",
    "RF-10": "if pregnant: vaginal bleeding or severe tummy pain",
    "RF-11": "confusion, unusual sleepiness or being hard to wake",
    "RF-15": "being able to keep fluids down",
}
BASELINE_SCREEN = ("RF-01", "RF-02", "RF-04", "RF-05", "RF-11")


def _screen(modules: list[ComplaintModule]) -> str:
    ids = dict.fromkeys([*BASELINE_SCREEN, *[rf for m in modules for rf in m.red_flags]])
    return "\n".join(f"   - {SCREEN_QUESTIONS[i]}" for i in ids if i in SCREEN_QUESTIONS)


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
        screen=_screen(modules),
        patient=ctx.describe(),
    )
    output = llm.complete_json("interview", system, to_messages(transcript), InterviewOut)
    patient_turns = sum(1 for line in transcript if line.speaker == "patient")
    known = all_modules()
    module_ids = tuple(i for i in dict.fromkeys(output.module_ids) if i in known)
    if patient_turns >= MAX_PATIENT_TURNS:
        return InterviewStep(utterance=output.utterance.strip(), interview_complete=True, module_ids=module_ids)
    if output.interview_complete and not allergies_asked(transcript):
        return InterviewStep(utterance=allergy_question(ctx), interview_complete=False, module_ids=module_ids)
    return InterviewStep(
        utterance=output.utterance.strip(), interview_complete=output.interview_complete, module_ids=module_ids
    )


def allergies_asked(transcript: list[TranscriptLine]) -> bool:
    return any(line.speaker == "agent" and "allerg" in line.text.lower() for line in transcript)


def allergy_question(ctx: PatientContext) -> str:
    """Allergies are mandatory: asked by code if the interviewer tries to finish without them (eval FEV-020)."""
    who = ctx.first_name if ctx.is_caregiver_call else "you"
    verb = "is" if ctx.is_caregiver_call else "are"
    return f"Before we finish, {verb} {who} allergic to any medicines or foods? If so, what happened?"
