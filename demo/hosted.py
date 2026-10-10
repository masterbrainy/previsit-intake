"""The hosted open demo for judges (Vercel, see api/index.py): fictional data in a hosted Postgres database.

Unlike demo.serve, it never wipes anything. Serverless instances start and stop all the time, so the first one seeds
an empty database and later ones find it seeded. Needs DATABASE_URL (or POSTGRES_URL) and OPENAI_API_KEY from the
host; sign-in codes are keyed from the database URL, so every instance accepts the same codes.
"""

import hashlib
import logging
import os
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from demo.config import CLINIC, PHYSICIAN, RED_FLAG_CONTACT, RED_FLAG_SCENARIO
from demo import mid_intake
from demo.seed import BACKGROUND, patient_from_scenario, seed, tomorrow_at
from previsit.config import Settings
from previsit.db import init_db, make_engine, session_scope
from previsit.models import Appointment, Doctor, Patient
from previsit.web.app import create_app

logger = logging.getLogger(__name__)
SEEDED_CONTACTS = {p.contact for p in BACKGROUND} | {RED_FLAG_CONTACT, mid_intake.CONTACT}


def hosted_settings() -> Settings:
    database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set: connect a Postgres database to the project")
    host = os.environ.get("DEMO_PUBLIC_URL") or "https://" + (
        os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") or os.environ.get("VERCEL_URL") or "localhost")
    portal_secret = hashlib.sha256(b"path-portal-codes:" + database_url.encode()).hexdigest()
    return Settings().model_copy(update={
        "database_url": database_url, "upload_dir": Path("/tmp/path-uploads"), "base_url": host.rstrip("/"),
        "clinic_name": CLINIC, "physician_display_name": PHYSICIAN, "portal_secret": SecretStr(portal_secret),
        "demo_mode": True, "open_demo": True,
    })


def seed_once(settings: Settings) -> None:
    """Seeds an empty database; keeps the fictional appointments in the future however long the demo runs."""
    engine = make_engine(settings.database_url)
    init_db(engine)
    try:
        with session_scope(engine) as session:
            if session.exec(select(Doctor)).first() is None:
                seed(session, settings, patient_from_scenario(RED_FLAG_SCENARIO, "Fever and headache",
                                                              RED_FLAG_CONTACT))
    except IntegrityError:
        logger.info("Another instance seeded the demo database first")
    with session_scope(engine) as session:
        _keep_seed_dates_ahead(session)
    engine.dispose()


def _keep_seed_dates_ahead(session) -> None:
    stale = session.exec(
        select(Appointment).join(Patient, Patient.id == Appointment.patient_id)
        .where(Patient.phone.in_(SEEDED_CONTACTS), Appointment.scheduled_at < tomorrow_at(0) - timedelta(hours=12))
    ).all()
    for appointment in stale:
        appointment.scheduled_at = tomorrow_at(appointment.scheduled_at.hour, appointment.scheduled_at.minute)
        session.add(appointment)


def build_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = hosted_settings()
    seed_once(settings)
    return create_app(settings=settings)
