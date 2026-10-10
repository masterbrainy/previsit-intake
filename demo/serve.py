"""One command for the demo site: reset to a clean synthetic state, then serve it.

    uv run --group demo python -m demo.serve
    uv run --group demo python -m demo.serve --public https://<tunnel>.trycloudflare.com   # open demo for judges
"""

import logging
import os
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
    public_url = _public_url()
    if film:
        red = patient_from_scenario(FILM_RED_SCENARIO, "Fever and headache", RED_FLAG_CONTACT)
        seeded = reset(red, with_mid_intake=False, clinic=FILM_CLINIC)
        settings = demo_settings(FILM_CLINIC)
    else:
        seeded = reset(patient_from_scenario(RED_FLAG_SCENARIO, "Fever and headache", RED_FLAG_CONTACT))
        settings = demo_settings()
    if public_url:
        settings = settings.model_copy(update={"open_demo": True, "base_url": public_url.rstrip("/")})
    print(f"Demo site reset with {len(seeded)} synthetic appointments.")
    print(f"Front page: {DEMO_URL}/  (demo mode: patient sign-in codes are shown on screen)")
    print(f"Physician dashboard: {DEMO_URL}/dashboard (login: PHYSICIAN_USERNAME / PHYSICIAN_PASSWORD from .env)")
    # Public behind a local tunnel (cloudflared): it connects from 127.0.0.1 and appends the visitor's address, so only
    # that hop's forwarding headers are trusted and a visitor can't pick their own address.
    port = int(os.environ.get("PORT", DEMO_PORT))
    uvicorn.run(create_app(settings=settings), host="127.0.0.1", port=port, log_level="warning",
                proxy_headers=True, forwarded_allow_ips="127.0.0.1")


def _public_url() -> str | None:
    """The open demo for judges (one-click entry, no codes or passwords) runs when the site has a public address:
    `--public https://…` or DEMO_PUBLIC_URL. (The hosted version runs on Vercel: api/index.py, demo/hosted.py.)"""
    if "--public" in sys.argv:
        return sys.argv[sys.argv.index("--public") + 1]
    return os.environ.get("DEMO_PUBLIC_URL")


if __name__ == "__main__":
    main()
