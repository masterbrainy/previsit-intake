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


def demo_settings() -> Settings:
    base = Settings()  # API key and physician login come from .env
    return base.model_copy(update={
        "database_url": f"sqlite:///{DEMO_DIR / 'demo.db'}",
        "upload_dir": DEMO_DIR / "uploads",
        "base_url": DEMO_URL,
        "clinic_name": CLINIC,
        "physician_display_name": PHYSICIAN,
    })


def ensure_dirs() -> None:
    for path in (DEMO_DIR, OUTPUT_DIR):
        Path(path).mkdir(parents=True, exist_ok=True)
