"""Builds the final demo video from a recording (PROGRESS D.5).

Pass 1 shortens the logged AI waits. Pass 2 speeds up the visibly badged fast-forward range and lays the captured AI
speech in at the right moments. Then it extracts a check frame at every caption change.

    uv run --group demo python -m demo.assemble demo/output/<run>/timeline.json
"""

import json
import subprocess
import sys
from pathlib import Path

FPS = 25


def merge(ranges: list[list[float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted((float(a), float(b)) for a, b in ranges if b > a):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def keep_segments(duration: float, cuts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    segments, cursor = [], 0.0
    for start, end in cuts:
        if start > cursor:
            segments.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration:
        segments.append((cursor, duration))
    return segments


def remove_cuts(t: float, cuts: list[tuple[float, float]]) -> float:
    """Recording time -> time after pass 1."""
    removed = 0.0
    for start, end in cuts:
        if t >= end:
            removed += end - start
        elif t > start:
            removed += t - start
    return t - removed


def apply_speed(t: float, ff: tuple[float, float] | None, speed: float) -> float:
    """Pass-1 time -> final time, with the fast-forward range played `speed` times faster."""
    if ff is None or t <= ff[0]:
        return t
    if t <= ff[1]:
        return ff[0] + (t - ff[0]) / speed
    return t - (ff[1] - ff[0]) * (1 - 1 / speed)


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def probe_duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def pass_one(raw: Path, cuts: list[tuple[float, float]], duration: float, out: Path) -> None:
    select = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in keep_segments(duration, cuts))
    ffmpeg("-i", str(raw), "-vf", f"select='{select}',setpts=N/FRAME_RATE/TB,fps={FPS}",
           "-c:v", "libx264", "-preset", "fast", "-crf", "12", "-an", str(out))


def pass_two(cut: Path, ff: tuple[float, float] | None, speed: float, audio: list[tuple[str, float]], out: Path) -> None:
    inputs: list[str] = []
    if ff is None:
        inputs += ["-i", str(cut)]
        video = f"[0:v]fps={FPS},format=yuv420p[v]"
        n_video = 1
    else:
        a, b = ff
        inputs += ["-t", f"{a:.3f}", "-i", str(cut), "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(cut),
                   "-ss", f"{b:.3f}", "-i", str(cut)]
        video = (f"[1:v]setpts=(PTS-STARTPTS)/{speed}[fast];[0:v][fast][2:v]concat=n=3:v=1:a=0,"
                 f"fps={FPS},format=yuv420p[v]")
        n_video = 3
    filters, labels = [video], []
    for i, (file, at) in enumerate(audio):
        inputs += ["-i", file]
        delay = int(at * 1000)
        filters.append(f"[{n_video + i}:a]aresample=48000,adelay={delay}|{delay}[a{i}]")
        labels.append(f"[a{i}]")
    maps = ["-map", "[v]"]
    if labels:
        filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:dropout_transition=0[a]")
        maps += ["-map", "[a]", "-c:a", "aac", "-b:a", "160k"]
    ffmpeg(*inputs, "-filter_complex", ";".join(filters), *maps, "-c:v", "libx264", "-preset", "slow", "-crf", "18",
           "-r", str(FPS), "-movflags", "+faststart", str(out))


def build(timeline_path: Path) -> Path:
    timeline = json.loads(timeline_path.read_text())
    run_dir = timeline_path.parent
    raw = Path(timeline["video"])
    duration = probe_duration(raw)
    offset = max(0.0, duration - float(timeline["duration"]))  # video starts slightly before the recorder's clock
    cuts = merge([[a + offset, b + offset] for a, b in timeline["cuts"]])
    speed = float(timeline.get("ff_speed", 4))
    ff_ranges = timeline.get("fast_forward") or []
    ff = None
    if ff_ranges:
        a, b = ff_ranges[0]
        ff = (remove_cuts(a + offset, cuts), remove_cuts(b + offset, cuts))

    def final_time(t: float) -> float:
        return apply_speed(remove_cuts(t + offset, cuts), ff, speed)

    cut_video = run_dir / "pass1_cut.mp4"
    pass_one(raw, cuts, duration, cut_video)
    audio = [(clip["file"], final_time(float(clip["t"]))) for clip in timeline["audio"]]
    final = run_dir / "previsit-intake-demo.mp4"
    pass_two(cut_video, ff, speed, audio, final)
    cut_video.unlink()

    final_duration = probe_duration(final)
    frames = run_dir / "frames"
    frames.mkdir(exist_ok=True)
    for i, mark in enumerate(timeline["marks"]):
        at = min(final_time(float(mark["t"])) + 1.2, final_duration - 0.1)
        ffmpeg("-ss", f"{at:.2f}", "-i", str(final), "-frames:v", "1", str(frames / f"{i:02d}.png"))
    summary = {
        "final": str(final), "raw_seconds": round(duration, 1), "final_seconds": round(final_duration, 1),
        "pauses_cut": len(cuts), "seconds_cut": round(sum(b - a for a, b in cuts), 1),
        "fast_forward": [round(x, 1) for x in ff] if ff else None, "ff_speed": speed,
        "audio_clips": len(audio), "check_frames": len(timeline["marks"]),
    }
    (run_dir / "assembly.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return final


if __name__ == "__main__":
    build(Path(sys.argv[1]))
