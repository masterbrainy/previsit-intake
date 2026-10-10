"""Checks every agent utterance for diagnosis, medication advice, result interpretation or false reassurance."""

from dataclasses import dataclass

from pydantic import BaseModel

from previsit.llm import LLMClient, LLMError

REDIRECT = (
    "That's something your doctor will go through with you at your appointment. "
    "Is there anything else about how you've been feeling that you'd like your doctor to know?"
)
CAREGIVER_REDIRECT = (
    "That's something the doctor will go through with you at {name}'s appointment. "
    "Is there anything else about how {name} has been feeling that you'd like the doctor to know?"
)


def redirect_for(patient_first_name: str | None = None) -> str:
    """The fixed redirect; on a caregiver call it names the patient instead of saying "you"."""
    return CAREGIVER_REDIRECT.format(name=patient_first_name) if patient_first_name else REDIRECT

SYSTEM_PROMPT = """You review one sentence-group that an automated pre-visit history-taking assistant is about to say to a patient.
The assistant must ONLY ask history questions, acknowledge answers, and give logistics.
Block it (allowed=false) if it does any of these:
- names, suggests or hints at a diagnosis or cause ("sounds like flu", "could be an infection", "probably viral")
- recommends, names for use, or doses any medication, including over-the-counter drugs
- interprets or comments on test results
- reassures or minimises symptoms ("it's probably nothing", "no need to worry", "you can wait")
Asking whether the patient takes a medication, or what they took, is allowed.
Return allowed=true otherwise, with a short reason either way."""


class GuardOutput(BaseModel):
    allowed: bool
    reason: str


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    reason: str
    text: str


def check_agent_utterance(llm: LLMClient, text: str, redirect: str = REDIRECT) -> GuardResult:
    """Fails closed: if the guard can't run, the utterance is replaced by the redirect."""
    try:
        output = llm.complete_json(
            "scope_guard", SYSTEM_PROMPT, [{"role": "user", "content": text}], GuardOutput
        )
    except LLMError:
        return GuardResult(False, "guard unavailable", redirect)
    return GuardResult(output.allowed, output.reason, text if output.allowed else redirect)
