"""Runtime settings, read from environment variables and the gitignored .env file."""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore", frozen=True)

    openai_api_key: SecretStr = SecretStr("")
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'var' / 'previsit.db'}"
    upload_dir: Path = PROJECT_ROOT / "var" / "uploads"
    base_url: str = "http://localhost:8000"

    interview_model: str = "gpt-5.4-mini"
    extraction_model: str = "gpt-5.4"
    safety_model: str = "gpt-5.4-mini"
    transcribe_model: str = "gpt-4o-transcribe"
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice: str = "alloy"

    emergency_number: str = "911"
    crisis_line: str = "988"
    clinic_name: str = "your clinic"

    physician_username: str = "doctor"
    physician_password: SecretStr = SecretStr("")
    physician_display_name: str = "Dr. Demo"

    max_upload_bytes: int = 10 * 1024 * 1024

    # Patient portal sign-in (PRD §8.10). Codes are HMAC'd with this key; if empty, a random key is made at startup.
    portal_secret: SecretStr = SecretStr("")
    portal_session_hours: int = 12
    # Demo mode (synthetic data only): the sign-in code is shown on screen because no SMS/email provider exists yet.
    demo_mode: bool = False


def get_settings() -> Settings:
    return Settings()
