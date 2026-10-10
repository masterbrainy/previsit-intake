"""Settings for the demo site: its own database, uploads and port, so it never touches the dev data."""

from pathlib import Path

from previsit.config import PROJECT_ROOT, Settings

DEMO_PORT = 8010
DEMO_URL = f"http://localhost:{DEMO_PORT}"
DEMO_DIR = PROJECT_ROOT / "var" / "demo"
OUTPUT_DIR = PROJECT_ROOT / "demo" / "output"
CLINIC = "Riverside Family Clinic (synthetic demo)"
PHYSICIAN = "Dr. Anika Rao"
# Simulated patients (Test & Support owns the scripts, D.3). Override with --full / --red-flag.
FULL_FLOW_SCENARIO = "FEV-001"
RED_FLAG_SCENARIO = "FEV-003"
# Fictional numbers (555-01xx is reserved for fiction) used to sign the demo patients in to the portal.
FULL_FLOW_CONTACT = "+15555550142"
RED_FLAG_CONTACT = "+15555550143"
# The demo film (demo/record.py): scripted patients for the full flow and the red-flag stop, and the clinic name it
# shows (the fictional people are named in the closing card instead of on every screen).
FILM_CLINIC = "Riverside Family Clinic"
FILM_FULL_SCENARIO = "DEMO-001"
FILM_RED_SCENARIO = "DEMO-002"


def demo_settings(clinic: str = CLINIC) -> Settings:
    base = Settings()  # API key and physician login come from .env
    return base.model_copy(update={
        "database_url": f"sqlite:///{DEMO_DIR / 'demo.db'}",
        "upload_dir": DEMO_DIR / "uploads",
        "base_url": DEMO_URL,
        "clinic_name": clinic,
        "physician_display_name": PHYSICIAN,
        "demo_mode": True,  # synthetic data only: sign-in codes are shown on screen
    })


def ensure_dirs() -> None:
    for path in (DEMO_DIR, OUTPUT_DIR):
        Path(path).mkdir(parents=True, exist_ok=True)
