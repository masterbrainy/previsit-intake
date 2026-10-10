"""Vercel entry point: the PATH open demo for judges (demo/hosted.py). vercel.json routes every path here."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]  # the previsit package, plus demo/ and evals/ for the seed data

from demo.hosted import build_app  # noqa: E402

app = build_app()
