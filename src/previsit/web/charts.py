"""Tiny server-rendered SVG chart for symptom logs (no JavaScript, prints cleanly)."""

from dataclasses import dataclass
from datetime import datetime

WIDTH, HEIGHT, PAD = 520, 140, 28


@dataclass(frozen=True)
class Chart:
    width: int
    height: int
    path: str
    points: tuple[tuple[float, float, str], ...]
    threshold_y: float | None
    y_labels: tuple[tuple[float, str], ...]


def sparkline(series: list[tuple[datetime, float]], threshold: float | None = None) -> Chart:
    times = [t.timestamp() for t, _ in series]
    values = [v for _, v in series]
    lo = min([*values, threshold or values[0]]) - 0.5
    hi = max([*values, threshold or values[0]]) + 0.5
    t0, t1 = min(times), max(times)
    span = (t1 - t0) or 1.0

    def x(t: float) -> float:
        return PAD + (t - t0) / span * (WIDTH - 2 * PAD)

    def y(v: float) -> float:
        return HEIGHT - PAD - (v - lo) / (hi - lo) * (HEIGHT - 2 * PAD)

    points = tuple((round(x(t), 1), round(y(v), 1), f"{v:.1f}") for t, v in zip(times, values, strict=True))
    path = "M " + " L ".join(f"{px} {py}" for px, py, _ in points)
    return Chart(
        width=WIDTH, height=HEIGHT, path=path, points=points,
        threshold_y=round(y(threshold), 1) if threshold is not None else None,
        y_labels=((round(y(lo + 0.5), 1), f"{lo + 0.5:.1f}"), (round(y(hi - 0.5), 1), f"{hi - 0.5:.1f}")),
    )
