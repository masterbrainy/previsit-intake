"""Clean reset and synthetic seed data for the demo site. Every person here is fictional."""

import shutil
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from PIL import Image, ImageDraw, ImageFont
from sqlmodel import select

from demo.config import DEMO_DIR, PHYSICIAN, demo_settings, ensure_dirs
from previsit.db import init_db, make_engine, session_scope
from previsit.models import Appointment, SymptomLog, utcnow
from previsit.web.views import create_appointment


@dataclass(frozen=True)
class DemoPatient:
    name: str
    dob: date
    sex: str
    reason: str


# The fever patient is booked live in the video; these fill the dashboard and run the red-flag case.
BACKGROUND = (
    DemoPatient("Samuel Okafor", date(1979, 6, 2), "M", "Follow-up: blood pressure"),
    DemoPatient("Grace Lindqvist", date(1958, 11, 20), "F", "Knee pain"),
)


def tomorrow_at(hour: int, minute: int = 0) -> datetime:
    return (datetime.now() + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)


def reset(red_flag_case: DemoPatient | None = None) -> dict[str, int]:
    """Deletes the demo database and uploads, then seeds fresh synthetic appointments."""
    if DEMO_DIR.exists():
        shutil.rmtree(DEMO_DIR)
    ensure_dirs()
    settings = demo_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    ids: dict[str, int] = {}
    with session_scope(engine) as session:
        for i, p in enumerate((*BACKGROUND, *([red_flag_case] if red_flag_case else []))):
            appt = create_appointment(
                session, settings, "demo-seed", p.name, p.dob, p.sex, "", PHYSICIAN, tomorrow_at(10 + i), p.reason
            )
            ids[p.name] = appt.id
    engine.dispose()
    return ids


def token_for(name: str) -> str:
    settings = demo_settings()
    engine = make_engine(settings.database_url)
    with session_scope(engine) as session:
        from previsit.models import Patient

        appt = session.exec(
            select(Appointment).join(Patient, Patient.id == Appointment.patient_id).where(Patient.name == name)
        ).first()
        if appt is None:
            raise LookupError(f"no demo appointment for {name}")
        token = appt.token
    engine.dispose()
    return token


def backdate_readings(appointment_id: int, readings: list[tuple[float, float]]) -> None:
    """Pre-loads earlier temperature readings as (hours_ago, celsius); the video says these were pre-entered."""
    settings = demo_settings()
    engine = make_engine(settings.database_url)
    now = utcnow()
    with session_scope(engine) as session:
        for hours_ago, celsius in readings:
            session.add(SymptomLog(
                appointment_id=appointment_id, metric="temperature_c", value=celsius, unit="°C",
                note="(pre-entered for demo)", recorded_at=now - timedelta(hours=hours_ago),
            ))
    engine.dispose()


def lab_report_png(path, patient_name: str, dob: date) -> None:
    """A synthetic CBC report image. Values are made up; the app never reads them."""
    img = Image.new("RGB", (1100, 820), "white")
    draw = ImageDraw.Draw(img)
    try:
        title = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 34)
        body = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
        small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except OSError:
        title = body = small = ImageFont.load_default()
    draw.rectangle((0, 0, 1100, 70), fill="#b3261e")
    draw.text((30, 18), "SYNTHETIC DEMO REPORT · NOT A REAL PATIENT", font=body, fill="white")
    draw.text((30, 100), "Riverside Lab Services (fictional)", font=title, fill="#1d1d1b")
    draw.text((30, 150), f"Patient: {patient_name}    DOB: {dob.isoformat()}", font=body, fill="#1d1d1b")
    draw.text((30, 185), f"Collected: {date.today().isoformat()}    Test: Complete blood count (CBC)", font=body, fill="#1d1d1b")
    rows = [
        ("Haemoglobin", "12.9", "g/dL", "12.0 – 15.5"),
        ("White cell count", "9.8", "x10^9/L", "4.0 – 11.0"),
        ("Neutrophils", "6.9", "x10^9/L", "2.0 – 7.5"),
        ("Lymphocytes", "2.1", "x10^9/L", "1.0 – 4.0"),
        ("Platelets", "214", "x10^9/L", "150 – 400"),
        ("Haematocrit", "0.39", "L/L", "0.36 – 0.46"),
    ]
    y = 250
    for header, x in (("Test", 30), ("Result", 430), ("Units", 600), ("Reference range", 800)):
        draw.text((x, y), header, font=body, fill="#5f5e5a")
    draw.line((30, y + 38, 1070, y + 38), fill="#cccccc", width=2)
    for name, value, unit, ref in rows:
        y += 60
        for text, x in ((name, 30), (value, 430), (unit, 600), (ref, 800)):
            draw.text((x, y), text, font=body, fill="#1d1d1b")
    draw.text((30, 760), "All values are invented for a software demonstration.", font=small, fill="#5f5e5a")
    img.save(path)


def patient_from_scenario(scenario_id: str, reason: str) -> DemoPatient:
    """Books the simulated patient with exactly the name and age its scenario uses, so identity checks match."""
    from evals.scenario import dob_for, load_all

    scenario = load_all([scenario_id])[0]
    return DemoPatient(scenario.patient_name, dob_for(scenario.age, date.today()), scenario.sex, reason)


if __name__ == "__main__":
    print(reset())
