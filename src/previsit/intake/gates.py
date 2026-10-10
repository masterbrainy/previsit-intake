"""Consent, identity and read-back checks: small classification calls with deterministic decisions."""

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from previsit.llm import LLMClient


class YesNoOut(BaseModel):
    decision: Literal["yes", "no", "unclear"]


class IdentityOut(BaseModel):
    full_name: str = Field(description="The PATIENT's full name as given, empty if not given")
    date_of_birth: str = Field(description="The PATIENT's date of birth as YYYY-MM-DD, empty if not given or unclear")
    informant: str = Field(description='"self" if the patient is speaking, else the speaker\'s relationship, e.g. "mother"')


@dataclass(frozen=True)
class IdentityCheck:
    matched: bool
    informant: str


YES_NO_PROMPT = """Classify the person's reply to this question: "{question}"
"yes" = they agree / confirm. "no" = they refuse / say it is wrong or want to change something. "unclear" = anything else."""

IDENTITY_PROMPT = """Extract who the patient is from the reply. The speaker may be the patient or a caregiver answering
for them. Convert spoken dates to YYYY-MM-DD. Do not guess missing parts."""


def classify_yes_no(llm: LLMClient, task: str, question: str, reply: str) -> str:
    output = llm.complete_json(
        task, YES_NO_PROMPT.format(question=question), [{"role": "user", "content": reply}], YesNoOut
    )
    return output.decision


def _tokens(name: str) -> list[str]:
    return re.findall(r"[a-z]+", name.lower())


def names_match(recorded: str, given: str) -> bool:
    expected, heard = _tokens(recorded), set(_tokens(given))
    if not expected or not heard:
        return False
    return expected[0] in heard and expected[-1] in heard


def check_identity(llm: LLMClient, reply: str, recorded_name: str, recorded_dob: date) -> IdentityCheck:
    output = llm.complete_json("identity", IDENTITY_PROMPT, [{"role": "user", "content": reply}], IdentityOut)
    try:
        dob_ok = date.fromisoformat(output.date_of_birth.strip()) == recorded_dob
    except ValueError:
        dob_ok = False
    informant = output.informant.strip().lower() or "self"
    return IdentityCheck(matched=dob_ok and names_match(recorded_name, output.full_name), informant=informant)
