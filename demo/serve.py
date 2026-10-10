"""One command for the demo site: reset to a clean synthetic state, then serve it.

    uv run --group demo python -m demo.serve
"""

import logging
import sys

import uvicorn

from demo.config import (DEMO_PORT, DEMO_URL, FILM_CLINIC, FILM_RED_SCENARIO, RED_FLAG_CONTACT, RED_FLAG_SCENARIO,
                         demo_settings)
from demo.seed import patient_from_scenario, reset
from previsit.web.app import create_app


def main() -> None:
    """`--film` serves the clean state the demo film starts from (demo/record.py)."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    film = "--film" in sys.argv
    if film:
        red = patient_from_scenario(FILM_RED_SCENARIO, "Fever and headache", RED_FLAG_CONTACT)
        seeded = reset(red, with_mid_intake=False, clinic=FILM_CLINIC)
        settings = demo_settings(FILM_CLINIC)
    else:
        seeded = reset(patient_from_scenario(RED_FLAG_SCENARIO, "Fever and headache", RED_FLAG_CONTACT))
        settings = demo_settings()
    print(f"Demo site reset with {len(seeded)} synthetic appointments.")
    print(f"Front page: {DEMO_URL}/  (demo mode: patient sign-in codes are shown on screen)")
    print(f"Physician dashboard: {DEMO_URL}/dashboard (login: PHYSICIAN_USERNAME / PHYSICIAN_PASSWORD from .env)")
    uvicorn.run(create_app(settings=settings), host="127.0.0.1", port=DEMO_PORT, log_level="warning")


if __name__ == "__main__":
    main()
