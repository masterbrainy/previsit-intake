"""Red-flag catalogue. Mirrors evals/red_flags.md (DRAFT, pending clinician sign-off). IDs are stable."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RedFlag:
    id: str
    label: str
    examples: tuple[str, ...]
    proposed: bool = False


BASELINE_RED_FLAGS: tuple[RedFlag, ...] = (
    RedFlag("RF-01", "Chest pain, pressure or tightness", ("my chest feels heavy", "pain going down my left arm")),
    RedFlag(
        "RF-02",
        "Difficulty breathing: breathless at rest, can't finish a sentence, lips or face turning blue",
        ("I can't catch my breath", "out of breath just sitting here", "his ribs are sucking in"),
    ),
    RedFlag(
        "RF-03",
        "Stroke signs (BE-FAST): sudden loss of balance, vision loss, face drooping, arm or leg weakness, slurred or confused speech",
        ("her face looks lopsided", "I can't lift my right arm", "my words are coming out wrong"),
    ),
    RedFlag(
        "RF-04",
        "Loss of consciousness, fainting, or a seizure (including a febrile seizure in a child) during this illness",
        ("I passed out in the bathroom", "she had a fit", "his whole body was jerking"),
    ),
    RedFlag(
        "RF-05",
        "Severe bleeding: won't stop, vomiting blood, black or tarry stools, coughing up more than streaks of blood",
        ("I threw up blood", "my poo is black like tar"),
    ),
    RedFlag(
        "RF-06",
        "Suicidal thoughts, self-harm, or intent to harm others",
        ("I don't see the point anymore", "I've been thinking of ending it", "I cut myself last night"),
    ),
    RedFlag("RF-07", "Fever with a stiff neck", ("it hurts to bend my head forward", "my neck is really stiff")),
    RedFlag(
        "RF-08",
        "Fever with a rash that doesn't fade under pressure",
        ("little purple spots that don't go when I press them",),
    ),
    RedFlag(
        "RF-09",
        "Fever in an infant under 3 months (38.0 °C / 100.4 °F or higher, or feels hot with no thermometer)",
        ("my 6-week-old is 38.4", "she's 2 months and burning up"),
    ),
    RedFlag("RF-10", "Pregnancy with vaginal bleeding or severe abdominal pain", ("I'm 20 weeks and I'm bleeding",)),
    RedFlag(
        "RF-11",
        "New confusion, unusual drowsiness or hard to wake",
        ("Mum doesn't know where she is", "he's really hard to wake up"),
    ),
    RedFlag(
        "RF-12",
        "Signs of anaphylaxis: swelling of lips, tongue or throat, throat tightness, sudden wheeze after a new food, drug or sting",
        ("my lips are swelling up", "my throat feels tight since the new tablets"),
        proposed=True,
    ),
    RedFlag(
        "RF-13",
        "Fever while on chemotherapy or with severe immunosuppression (transplant, high-dose steroids)",
        ("I'm on chemo and I've got a temperature",),
        proposed=True,
    ),
    RedFlag(
        "RF-14",
        "Sepsis signs: mottled, blue or very pale skin; no urine for 18 h (adult) or 12 h (child); breathing very fast; 'never felt this ill'",
        ("I've never felt this ill", "haven't weed since yesterday"),
        proposed=True,
    ),
    RedFlag(
        "RF-15",
        "Can't keep any fluids down for 6 h or more, or (child) far fewer wet nappies",
        ("I can't keep even water down",),
        proposed=True,
    ),
    RedFlag("RF-16", "Sudden, severe 'worst ever' headache", ("worst headache of my life",), proposed=True),
)

RED_FLAGS_BY_ID: dict[str, RedFlag] = {rf.id: rf for rf in BASELINE_RED_FLAGS}
SUICIDE_RISK_ID = "RF-06"


def describe(rf_ids: list[str] | tuple[str, ...]) -> str:
    return "; ".join(f"{i} {RED_FLAGS_BY_ID[i].label}" if i in RED_FLAGS_BY_ID else i for i in rf_ids)
