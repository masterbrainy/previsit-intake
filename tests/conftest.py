from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # lets tests import the evals package
    sys.path.insert(0, str(REPO_ROOT))

from factories import CRISIS_LINE, EMERGENCY_NUMBER, TEST_PHYSICIAN, make_appointment, make_fake_llm

TEST_PASSWORD = "pw-test-only"


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """Settings from env vars only (no .env), so the real API key is never picked up in unit tests."""
    env = {
        "OPENAI_API_KEY": "sk-test-not-a-real-key",
        "DATABASE_URL": f"sqlite:///{tmp_path / 'test.db'}",
        "EMERGENCY_NUMBER": EMERGENCY_NUMBER,
        "CRISIS_LINE": CRISIS_LINE,
        "PHYSICIAN_USERNAME": TEST_PHYSICIAN,
        "PHYSICIAN_PASSWORD": TEST_PASSWORD,
        "BASE_URL": "http://testserver",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    from previsit.config import Settings

    return Settings(_env_file=None)


@pytest.fixture
def db_url(tmp_path):
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def db_engine(db_url):
    from previsit.db import init_db, make_engine

    engine = make_engine(db_url)
    init_db(engine)
    return engine


@pytest.fixture
def session(db_engine):
    from previsit.db import session_scope

    with session_scope(db_engine) as s:
        yield s


@pytest.fixture
def appointment(session):
    return make_appointment(session)


@pytest.fixture
def llm():
    return make_fake_llm()


@pytest.fixture
def physician_auth():
    return (TEST_PHYSICIAN, TEST_PASSWORD)
