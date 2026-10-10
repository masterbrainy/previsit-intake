"""Who the patient is, as the safety and interview prompts need to know it."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PatientContext:
    name: str
    dob: date
    sex: str
    on_date: date
    informant: str = "self"
    physician_name: str = ""

    @property
    def age_days(self) -> int:
        return (self.on_date - self.dob).days

    @property
    def age_text(self) -> str:
        days = self.age_days
        if days < 7 * 13:
            return f"{days // 7} weeks"
        if days < 365 * 2:
            return f"{days // 30} months"
        years = self.on_date.year - self.dob.year - ((self.on_date.month, self.on_date.day) < (self.dob.month, self.dob.day))
        return f"{years} years"

    @property
    def first_name(self) -> str:
        return self.name.split()[0] if self.name.strip() else "the patient"

    @property
    def is_caregiver_call(self) -> bool:
        return self.informant.strip().lower() not in {"", "self"}

    def describe(self) -> str:
        speaker = "the patient themself" if not self.is_caregiver_call else f"the patient's {self.informant}"
        return f"Patient: {self.name}, {self.age_text} old, sex {self.sex or 'not recorded'}. Speaking: {speaker}."
