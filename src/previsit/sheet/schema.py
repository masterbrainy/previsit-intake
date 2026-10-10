"""History sheet in the PRD §7 format. Every statement cites the patient turns it came from."""

from pydantic import BaseModel, ConfigDict


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Statement(Frozen):
    text: str
    source_turn_ids: tuple[int, ...]


class ChiefComplaint(Frozen):
    complaint: str
    duration: str
    onset_order: int
    source_turn_ids: tuple[int, ...]


class SectionDef(Frozen):
    key: str
    title: str
    abbrev: str


SECTIONS: tuple[SectionDef, ...] = (
    SectionDef(key="particulars", title="Patient particulars", abbrev=""),
    SectionDef(key="hopi", title="History of presenting illness", abbrev="HOPI"),
    SectionDef(key="past_history", title="Past history", abbrev="PH"),
    SectionDef(key="treatment_history", title="Treatment / drug history", abbrev="Rx H"),
    SectionDef(key="allergies", title="Allergies", abbrev=""),
    SectionDef(key="family_history", title="Family history", abbrev="FH"),
    SectionDef(key="personal_history", title="Personal / social history", abbrev="Personal H"),
    SectionDef(key="review_of_systems", title="Review of systems", abbrev="ROS"),
    SectionDef(key="specialty_addons", title="Specialty add-ons", abbrev=""),
    SectionDef(key="could_not_answer", title="Couldn't answer", abbrev=""),
    SectionDef(key="red_flag_screen", title="Danger symptoms asked about and denied", abbrev=""),
)


class HistorySheet(Frozen):
    chief_complaints: tuple[ChiefComplaint, ...] = ()
    particulars: tuple[Statement, ...] = ()
    hopi: tuple[Statement, ...] = ()
    past_history: tuple[Statement, ...] = ()
    treatment_history: tuple[Statement, ...] = ()
    allergies: tuple[Statement, ...] = ()
    family_history: tuple[Statement, ...] = ()
    personal_history: tuple[Statement, ...] = ()
    review_of_systems: tuple[Statement, ...] = ()
    specialty_addons: tuple[Statement, ...] = ()
    could_not_answer: tuple[Statement, ...] = ()
    red_flag_screen: tuple[Statement, ...] = ()
    record: dict[str, str] = {}  # name, age, sex, informant from the clinic record and identity step, not the LLM
    findings: dict[str, float | bool | str] = {}
    module_ids: tuple[str, ...] = ()
    partial: bool = False

    def section(self, key: str) -> tuple[Statement, ...]:
        return getattr(self, key)

    def all_statements(self) -> list[Statement]:
        return [s for section in SECTIONS for s in self.section(section.key)]
