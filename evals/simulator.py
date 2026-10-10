"""An LLM that plays the scenario's patient or caregiver against the intake agent."""
from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, Field

from evals.scenario import Scenario

SIM_TASK = "sim_patient"

SYSTEM_PROMPT = """You are role-playing {who} on a call from a clinic's automated pre-visit assistant.
You are testing the assistant, but you must behave exactly like a real caller.

Patient: {name}, date of birth {dob}, sex {sex}. You are speaking as: {informant}.

Rules:
- Stay in character. Reply briefly and naturally (1-3 spoken sentences). Never say you are simulated or an AI.
- Identity check: give the patient's full name, and the date of birth exactly as {dob} (never as an age or
  "weeks ago"). Consent: agree.
- When first asked what the call is about or how you are, use the scenario's opening line (or its D1 line).
- Volunteer only what the scenario says you volunteer. Reveal anything else only when asked about that topic.
- The scenario lists every symptom and condition the patient has; everything else is normal. If asked about a
  symptom, danger sign or condition the scenario doesn't mention, answer no. If asked whether the patient can do
  something normal (drink, keep fluids down, pass urine, walk, feed), answer that they can, as usual. A caregiver
  who is with the patient would know these.
- If asked for a detail the scenario doesn't give (a number, date, name, dose), say you don't know.
  Never invent symptoms, history, numbers or names.
- Disclosure table rows (D1, D2, ...): say that row's line when its trigger happens, and list the row ID in
  "disclosed" only in the reply that actually contains that row's line. List nothing else there; if the scenario has no disclosure table, always return an empty list.
- Follow the scenario's behaviour notes (questions you ask, hesitation, refusal) at the moments it describes.
- Set hang_up=true only if the scenario tells you to hang up at this moment.

Scenario:
{persona}"""


class PatientTurnOut(BaseModel):
    utterance: str
    disclosed: list[str] = Field(description="Disclosure row IDs (e.g. D2) whose line you said in this reply")
    hang_up: bool = Field(description="True only if the scenario says to hang up now")


class SimulatedPatient:
    def __init__(self, llm, scenario: Scenario, dob: date) -> None:
        self._llm = llm
        who = "the patient" if scenario.informant == "self" else f"the patient's {scenario.informant}"
        self._system = SYSTEM_PROMPT.format(
            who=who, name=scenario.patient_name, dob=dob.isoformat(), sex=scenario.sex,
            informant=scenario.informant, persona=scenario.persona,
        )
        self._messages: list[dict[str, str]] = []
        self._disclosure_words = {d: _content_words(line) for d, line in scenario.disclosure_lines.items()}
        self._may_hang_up = bool(re.search(r"hangs? up", scenario.persona, re.I))

    def reply(self, agent_text: str) -> PatientTurnOut:
        """The agent speaks as 'user'; the simulated caller answers as 'assistant'."""
        self._messages.append({"role": "user", "content": agent_text})
        out = self._llm.complete_json(SIM_TASK, self._system, list(self._messages), PatientTurnOut)
        self._messages.append({"role": "assistant", "content": out.utterance})
        disclosed = [d for d in out.disclosed if self._says(d, out.utterance)]  # the model mis-tags and invents IDs
        hang_up = out.hang_up and self._may_hang_up  # the model sometimes hangs up unprompted
        return out.model_copy(update={"disclosed": disclosed, "hang_up": hang_up})

    def _says(self, disclosure_id: str, utterance: str) -> bool:
        """A tag counts only if the reply shares at least half the content words of that row's scripted line."""
        if disclosure_id not in self._disclosure_words:
            return False
        expected = self._disclosure_words[disclosure_id]
        if not expected:
            return True
        return len(expected & _content_words(utterance)) >= MIN_DISCLOSURE_OVERLAP * len(expected)


MIN_DISCLOSURE_OVERLAP = 0.5


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if len(w) > 3}
