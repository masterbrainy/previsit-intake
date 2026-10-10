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
    # Reasoning effort per task group ("none", "minimal", "low", ...); lower is faster.
    interview_reasoning: str = "none"  # 0.9 s vs 1.4 s per question (benchmarked); safety stays "low"
    safety_reasoning: str = "low"
    extraction_reasoning: str = "low"

    emergency_number: str = "911"
    crisis_line: str = "988"
    clinic_name: str = "your clinic"

    physician_username: str = "doctor"
    physician_password: SecretStr = SecretStr("")
    physician_display_name: str = "Dr. Demo"
    physician_email: str = "doctor@clinic.example"  # the first doctor account, created if none exist

    max_upload_bytes: int = 10 * 1024 * 1024

    # Patient portal sign-in (PRD §8.10). Codes are HMAC'd with this key; if empty, a random key is made at startup.
    portal_secret: SecretStr = SecretStr("")
    portal_session_hours: int = 12
    # Demo mode (synthetic data only): the sign-in code is shown on screen because no SMS/email provider exists yet.
    demo_mode: bool = False
    # Open demo (judges, no instructions): one-click entry as a fresh fictional patient, a demo doctor or hospital
    # staff, with no codes or passwords. Only takes effect together with demo_mode; synthetic data only.
    open_demo: bool = False

    @property
    def is_open_demo(self) -> bool:
        return self.demo_mode and self.open_demo


def get_settings() -> Settings:
    return Settings()
