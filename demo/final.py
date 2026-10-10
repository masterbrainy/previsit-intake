"""Cuts the final film: a tighter pace on a recorded take, then the team intro in front of it.

Silent stretches (typing, page loads, reading the screen) play SILENT_PACE times faster. Stretches where someone
speaks play VOICE_PACE times faster, voices included (assemble.py speeds a clip up with the stretch it starts in).
Long fast-forwards are squeezed to FAST_FORWARD_FILM_S on screen.

    uv run --group demo python -m demo.final demo/output/<run>/timeline_edit.json demo/output/intro.mp4 demo/output/PATH-demo.mp4
"""

import json
import sys
from pathlib import Path

from demo.assemble import TimeMap, build, ffmpeg, probe_duration, readable_speeds

SILENT_PACE = 1.5
VOICE_PACE = 1.1
FAST_FORWARD_FILM_S = 3.0
END_CARD_PACE = 1.0  # the end card's three lines stay up long enough to read
MAX_FILM_S = 180.0


def voiced_ranges(timeline: dict, tmap: TimeMap) -> list[list[float]]:
    """Recording-time spans during which a voice clip plays, merged where they touch."""
    spans = []
    for clip in sorted(timeline["audio"], key=lambda c: float(c["t"])):
        start = float(clip["t"])
        end = tmap.rec_time(tmap.film_time(start) + float(clip["length"]))
        if spans and start <= spans[-1][1] + 0.3:
            spans[-1][1] = max(spans[-1][1], end)
        else:
            spans.append([start, end])
    return spans


def tighten(timeline: dict) -> dict:
    frames = sorted(timeline["frames"])
    start, end = frames[0][0], float(timeline["end"])
    fast_forwards = [[a, b, max(f, shown / FAST_FORWARD_FILM_S)]
                     for (a, b, f), (_, _, shown) in zip(timeline["speeds"], _shown(timeline))]
    original = TimeMap(start, end, timeline["cuts"], readable_speeds(timeline["speeds"], timeline["cuts"])
                       + timeline.get("paces", []))
    voiced = [[a, b, VOICE_PACE] for a, b in voiced_ranges(timeline, original)]
    end_card = next(float(m["t"]) for m in timeline["marks"] if m.get("text") == "End card")
    paces = voiced + [[end_card, end, END_CARD_PACE], [start, end, SILENT_PACE]]
    return {**timeline, "speeds": fast_forwards, "paces": paces}


def _shown(timeline: dict) -> list[tuple[float, float, float]]:
    """Recording seconds actually on screen in each fast-forward (cuts inside it removed)."""
    return [(a, b, (b - a) - sum(max(0.0, min(b, cb) - max(a, ca)) for ca, cb in timeline["cuts"]))
            for a, b, _ in timeline["speeds"]]


def join(intro: Path, film: Path, out: Path) -> float:
    """Intro, a dip through black (both pieces already fade), then the film."""
    ffmpeg("-i", str(intro), "-i", str(film), "-filter_complex",
           "[0:v]fps=30,format=yuv420p,setsar=1[v0];[1:v]fps=30,format=yuv420p,setsar=1[v1];"
           "[0:a]aresample=48000,aformat=channel_layouts=stereo[a0];[1:a]aresample=48000,aformat=channel_layouts=stereo[a1];"
           "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]",
           "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-c:a", "aac", "-b:a", "192k",
           "-movflags", "+faststart", str(out))
    return probe_duration(out)


def main(timeline_path: Path, intro: Path, out: Path) -> None:
    tight = timeline_path.with_name("timeline_tight.json")
    tight.write_text(json.dumps(tighten(json.loads(timeline_path.read_text()))))
    film = build(tight)
    total = join(intro, film, out)
    print(f"final: {total:.1f}s → {out}")
    if total > MAX_FILM_S:
        sys.exit(f"too long: {total:.1f}s (limit {MAX_FILM_S:.0f}s)")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve())
