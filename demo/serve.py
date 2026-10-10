"""One command for the demo site: reset to a clean synthetic state, then serve it.

    uv run --group demo python -m demo.serve
"""

import logging

import uvicorn

from demo.config import DEMO_PORT, DEMO_URL, RED_FLAG_SCENARIO, demo_settings
from demo.seed import patient_from_scenario, reset
from previsit.web.app import create_app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    seeded = reset(patient_from_scenario(RED_FLAG_SCENARIO, "Fever and headache"))
    settings = demo_settings()
    print(f"Demo site reset with {len(seeded)} synthetic appointments.")
    print(f"Physician dashboard: {DEMO_URL}/dashboard (login: PHYSICIAN_USERNAME / PHYSICIAN_PASSWORD from .env)")
    uvicorn.run(create_app(settings=settings), host="127.0.0.1", port=DEMO_PORT, log_level="warning")


if __name__ == "__main__":
    main()
