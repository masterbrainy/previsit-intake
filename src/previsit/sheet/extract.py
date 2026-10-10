"""Builds the history sheet from the transcript. Statements without a valid patient-turn citation are dropped."""

import re
from dataclasses import dataclass

from pydantic import BaseModel, Field

from previsit.llm import LLMClient
from previsit.modules import ComplaintModule, FindingSpec
from previsit.safety.context import PatientContext
from previsit.safety.detector import TranscriptLine, format_transcript
from previsit.sheet.schema import SECTIONS, ChiefComplaint, HistorySheet, Statement


class StatementOut(BaseModel):
    text: str
    source_turns: list[int] = Field(description="Bracketed numbers of the PATIENT turns this statement comes from")


class ComplaintOut(BaseModel):
    complaint: str
    duration: str = Field(description='e.g. "3 days"')
    onset_order: int = Field(description="1 = the complaint that started first")
    source_turns: list[int]


class FindingOut(BaseModel):
    key: str
    value: str
    source_turns: list[int]


class SheetOut(BaseModel):
    chief_complaints: list[ComplaintOut]
    particulars: list[StatementOut]
    hopi: list[StatementOut]
    past_history: list[StatementOut]
    treatment_history: list[StatementOut]
    allergies: list[StatementOut]
    family_history: list[StatementOut]
    personal_history: list[StatementOut]
    review_of_systems: list[StatementOut]
    specialty_addons: list[StatementOut]
    could_not_answer: list[StatementOut]
    red_flag_screen: list[StatementOut] = Field(default_factory=list)
    findings: list[FindingOut]


SYSTEM_PROMPT = """You write a physician's history sheet from a pre-visit history-taking conversation.

Strict rules:
- Use ONLY what the patient (or caregiver) said. Never add facts, labels, diagnoses or interpretations they did not give
  (e.g. do not write "vasovagal" if they said "I fainted giving blood").
- Every statement must cite the bracketed numbers of the PATIENT turns it comes from. A "no" answer to the assistant's
  question counts: cite the patient's answer turn.
- Record a negative ("no chest pain") ONLY if the patient explicitly answered that specific item. If the assistant asked
  about several things and the patient answered only some of them, record nothing for the unanswered ones.
- Never write statements about what was "not mentioned" or "not reported"; leave it out instead.
- If the patient later corrects something, use the corrected version.
- Write concise clinical phrases in the physician's language (English). Keep the patient's own words for symptoms.
- Chief complaints: each with its duration EXACTLY as the patient gave it for that complaint. If they never said when
  that complaint started, set duration to an empty string. Never copy another complaint's duration. onset_order 1 = started first.
- Particulars: occupation, school, who they live with only. Never name, age, sex or informant (those come from the
  clinic record), never symptoms or measurements.
- Red-flag screen: one statement per danger symptom the patient explicitly denied when asked, written exactly as
  "No <symptom as asked>" (e.g. "No chest pain", "No rash"). Never add qualifiers the patient didn't confirm
  (a patient who said "no rash" has "No rash", NOT "No rash that fades when pressed").
- A single "no" to a question listing several symptoms denies exactly the symptoms in that question, nothing more.
- HOPI: onset, duration, progression, character, severity, timing, aggravating/relieving factors, associated symptoms,
  relevant negatives, previous similar episodes. Include every detail given in the opening answers too (e.g. highest
  temperature, "since this morning", "no thermometer"), even if the conversation stopped early.
- Past history (PH): chronic illnesses, previous episodes, hospitalisations, surgeries. Resolved childhood events go here.
- Treatment history: current medicines with dose if given, what was taken for this illness and its effect.
- Allergies: drug and food allergies and reactions. Write "No known allergies" ONLY if the patient answered a question
  about allergies with a denial, citing that answer. If allergies were never asked about, leave the section empty.
- Family history: relatives' conditions, ages; never attribute a relative's condition to the patient.
- Personal history: diet, appetite, sleep, bowel/bladder, smoking, alcohol, substances, occupation, travel, contacts, living situation.
- Review of systems: other symptoms asked about, positives and negatives.
- Specialty add-ons: menstrual/obstetric (weeks pregnant, previous pregnancies and deliveries, fetal movements,
  antenatal care, pregnancy vitamins), paediatric birth/feeding/development/immunisation, when discussed.
- Travel: record where, when, and any preventive tablets (e.g. malaria prophylaxis) taken or not taken.
- Could not answer: things the patient said they did not know.
- Findings: fill only these keys, and only if the patient stated it:
{findings}
  Values: numbers as plain numbers (convert Fahrenheit to Celsius for temperatures), booleans as "true"/"false".
- Leave a section empty if nothing was said about it.
- Be complete. Before answering, go through EVERY patient turn and check each fact in it is on the sheet somewhere:
  places (nursery, school, work), how a temperature was measured (ear, mouth, armpit) and the highest reading,
  wet nappies, pregnancy counts and vitamins, preventive tablets, inhaler names or colours, gradual or sudden onset,
  and plain denials the patient gave to a question (e.g. "No travel in the last 3 months").

{patient}"""


@dataclass(frozen=True)
class ExtractionResult:
    sheet: HistorySheet
    dropped: int


def finding_specs(modules: list[ComplaintModule]) -> dict[str, FindingSpec]:
    return {spec.key: spec for module in modules for spec in module.findings}


def build_sheet(
    llm: LLMClient,
    transcript: list[TranscriptLine],
    modules: list[ComplaintModule],
    ctx: PatientContext,
    partial: bool = False,
) -> ExtractionResult:
    specs = finding_specs(modules)
    findings_text = "\n".join(f"  - {s.key} ({s.type}): {s.description}" for s in specs.values()) or "  (none)"
    system = SYSTEM_PROMPT.format(findings=findings_text, patient=ctx.describe())
    user = f"Conversation:\n{format_transcript(transcript)}"
    output = llm.complete_json("sheet", system, [{"role": "user", "content": user}], SheetOut)
    patient_turns = {line.seq for line in transcript if line.speaker == "patient"}
    allergy_turns = allergy_answer_turns(transcript)
    result = _validate(output, patient_turns, allergy_turns, specs, tuple(m.id for m in modules), partial)
    record = {
        "name": ctx.name,
        "age": ctx.age_text,
        "sex": ctx.sex or "not recorded",
        "informant": "self" if not ctx.is_caregiver_call else ctx.informant,
    }
    return ExtractionResult(sheet=result.sheet.model_copy(update={"record": record}), dropped=result.dropped)


# "Not stated" lines are not history; the sheet leaves unanswered items out (eval FEV-002).
_NOT_STATED = re.compile(r"\bnot (?:stated|mentioned|reported|specified|discussed|provided|asked|documented)\b", re.I)
# "No known allergies" and similar. Only kept when the patient actually answered an allergy question (eval FEV-020).
_NO_ALLERGY = re.compile(r"\b(?:nkda|nka|no (?:known )?(?:drug |food |medication )?allerg|denies (?:any )?allerg)", re.I)


def allergy_answer_turns(transcript: list[TranscriptLine]) -> set[int]:
    """Patient turns that talk about allergies or answer an assistant question that asked about them."""
    turns, asked = set(), False
    for line in transcript:
        if line.speaker == "agent":
            asked = "allerg" in line.text.lower()
        elif asked or "allerg" in line.text.lower():
            turns.add(line.seq)
    return turns


def _keep(section_key: str, text: str, cited: tuple[int, ...], allergy_turns: set[int]) -> bool:
    if not cited or not text or _NOT_STATED.search(text):
        return False
    if section_key == "allergies" and _NO_ALLERGY.search(text):
        return any(t in allergy_turns for t in cited)
    return True


def _cited(turns: list[int], patient_turns: set[int]) -> tuple[int, ...]:
    valid = tuple(sorted({t for t in turns if t in patient_turns}))
    return valid if valid and len(valid) == len(set(turns)) else ()


def _validate(
    output: SheetOut,
    patient_turns: set[int],
    allergy_turns: set[int],
    specs: dict[str, FindingSpec],
    module_ids: tuple[str, ...],
    partial: bool,
) -> ExtractionResult:
    dropped = 0
    sections: dict[str, tuple[Statement, ...]] = {}
    for section in SECTIONS:
        kept = []
        for item in getattr(output, section.key):
            cited = _cited(item.source_turns, patient_turns)
            text = item.text.strip()
            if _keep(section.key, text, cited, allergy_turns):
                kept.append(Statement(text=text, source_turn_ids=cited))
            else:
                dropped += 1
        sections[section.key] = tuple(kept)

    complaints = []
    for c in output.chief_complaints:
        cited = _cited(c.source_turns, patient_turns)
        if cited:
            complaints.append(
                ChiefComplaint(complaint=c.complaint, duration=c.duration, onset_order=c.onset_order, source_turn_ids=cited)
            )
        else:
            dropped += 1
    complaints.sort(key=lambda c: c.onset_order)

    findings: dict[str, float | bool | str] = {}
    for f in output.findings:
        spec = specs.get(f.key)
        value = _parse_finding(spec, f.value) if spec else None
        if value is None or not _cited(f.source_turns, patient_turns):
            dropped += 1
            continue
        findings[f.key] = value

    sheet = HistorySheet(
        chief_complaints=tuple(complaints), findings=findings, module_ids=module_ids, partial=partial, **sections
    )
    return ExtractionResult(sheet=sheet, dropped=dropped)


_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _parse_finding(spec: FindingSpec, raw: str) -> float | bool | str | None:
    text = raw.strip().lower()
    if spec.type == "number":
        match = _NUMBER.search(text)
        return float(match.group()) if match else None
    if spec.type == "boolean":
        if text in {"true", "yes"}:
            return True
        if text in {"false", "no"}:
            return False
        return None
    return raw.strip() or None
