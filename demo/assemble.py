"""Edits the PATH demo film from a recording (PROGRESS D.5).

Maps recording time to film time (waits for the AI cut, fast-forward ranges sped up), lays the captured frames on a
30 fps timeline, mixes the assistant's and the patients' voices at the right moments, and writes check frames at every
caption change.

    uv run --group demo python -m demo.assemble demo/output/<run>/timeline.json
"""

import bisect
import json
import subprocess
import sys
from pathlib import Path

FPS = 30
FADE_IN_S, FADE_OUT_S = 0.6, 1.0
# A quiet synthesized pad under the film, ducked whenever someone speaks. Chords as note frequencies (Hz):
# Dmaj9, Bm7, Gmaj7, A6sus.
CHORDS = ((146.83, 220.0, 329.63, 369.99, 554.37), (123.47, 185.0, 220.0, 293.66, 440.0),
          (98.0, 146.83, 185.0, 246.94, 369.99), (110.0, 164.81, 185.0, 246.94, 329.63))
CHORD_STEP_S, CHORD_LEN_S = 8.0, 11.0
MUSIC_GAIN = 0.2


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def probe_duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


class TimeMap:
    """Piecewise map from recording time to film time. Cut pieces take no film time; sped-up pieces take less."""

    def __init__(self, start: float, end: float, cuts: list, speeds: list) -> None:
        points = {start, end}
        for a, b in cuts:
            points.update((a, b))
        for a, b, _ in speeds:
            points.update((a, b))
        bounds = sorted(p for p in points if start <= p <= end)
        self.pieces: list[tuple[float, float, float, float]] = []  # (rec_a, rec_b, factor or 0 for a cut, film_a)
        film = 0.0
        for a, b in zip(bounds, bounds[1:]):
            mid = (a + b) / 2
            if any(ca <= mid < cb for ca, cb in cuts):
                factor = 0.0
            else:
                factor = next((f for sa, sb, f in speeds if sa <= mid < sb), 1.0)
            self.pieces.append((a, b, factor, film))
            if factor:
                film += (b - a) / factor
        self.duration = film

    def film_time(self, t: float) -> float:
        for a, b, factor, film in self.pieces:
            if t < b:
                if not factor:
                    return film
                return film + (max(t, a) - a) / factor
        return self.duration

    def rec_time(self, film_t: float) -> float:
        for a, b, factor, film in self.pieces:
            if not factor:
                continue
            length = (b - a) / factor
            if film_t < film + length:
                return a + (film_t - film) * factor
        return self.pieces[-1][1]


def video_list(frames: list, tmap: TimeMap, frames_dir: Path, out: Path) -> int:
    """A concat list showing, for each film frame, the newest captured frame at that moment of the recording."""
    stamps = [t for t, _ in frames]
    n = int(tmap.duration * FPS)
    lines, last, run = [], None, 0
    for k in range(n):
        i = max(0, bisect.bisect_right(stamps, tmap.rec_time(k / FPS)) - 1)
        name = frames[i][1]
        if name == last:
            run += 1
            continue
        if last is not None:
            lines += [f"file '{frames_dir / last}'", f"duration {run / FPS:.5f}"]
        last, run = name, 1
    lines += [f"file '{frames_dir / last}'", f"duration {run / FPS:.5f}", f"file '{frames_dir / last}'"]
    out.write_text("\n".join(lines) + "\n")
    return n


def music_bed(duration: float, out: Path) -> None:
    """Overlapping, slowly faded chords with a slight left/right detune, softened and given some space."""
    inputs, filters, labels = [], [], []
    n = int(duration // CHORD_STEP_S) + 1
    for k in range(n):
        notes = CHORDS[k % len(CHORDS)]
        left = "+".join(f"sin(2*PI*{f}*t)" for f in notes)
        right = "+".join(f"sin(2*PI*{f * 1.003:.3f}*t)" for f in notes)
        swell = "(1+0.25*sin(2*PI*0.13*t))"
        expr = f"{swell}*({left})/{len(notes)}|{swell}*({right})/{len(notes)}"
        inputs += ["-f", "lavfi", "-i", f"aevalsrc='{expr}':s=48000:d={CHORD_LEN_S}"]
        delay = int(k * CHORD_STEP_S * 1000)
        filters.append(f"[{k}:a]afade=t=in:d=3.5,afade=t=out:st={CHORD_LEN_S - 4.0}:d=4.0,adelay={delay}|{delay}[c{k}]")
        labels.append(f"[c{k}]")
    filters.append(f"{''.join(labels)}amix=inputs={n}:normalize=0,lowpass=f=1400,aecho=0.8:0.6:140|310:0.22|0.15,"
                   f"volume={MUSIC_GAIN},atrim=0:{duration:.3f}[m]")
    ffmpeg(*inputs, "-filter_complex", ";".join(filters), "-map", "[m]", "-ar", "48000", str(out))


def mix_audio(clips: list, tmap: TimeMap, duration: float, music: Path, out: Path) -> int:
    inputs, filters, labels = [], [], []
    for i, clip in enumerate(clips):
        at = tmap.film_time(float(clip["t"]))
        length = float(clip["length"])
        inputs += ["-i", clip["file"]]
        fade = f",afade=t=out:st={max(0.0, length - 0.35):.3f}:d=0.35" if clip.get("trimmed") else ""
        delay = int(at * 1000)
        filters.append(f"[{i}:a]aresample=48000,atrim=0:{length:.3f}{fade},adelay={delay}|{delay}[a{i}]")
        labels.append(f"[a{i}]")
    m = len(clips)
    inputs += ["-i", str(music)]
    filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:dropout_transition=0,"
                   f"apad,atrim=0:{duration:.3f},aformat=channel_layouts=stereo,loudnorm=I=-16:TP=-2:LRA=11,"
                   f"aresample=48000,asplit=2[v1][v2]")
    # the music is mixed after the voices are normalised, so quiet stretches don't get pulled up to speech level
    filters.append(f"[{m}:a][v2]sidechaincompress=threshold=0.015:ratio=10:attack=40:release=600[duck]")
    filters.append(f"[v1][duck]amix=inputs=2:normalize=0,alimiter=limit=0.89,"
                   f"afade=t=in:d={FADE_IN_S},afade=t=out:st={duration - FADE_OUT_S:.3f}:d={FADE_OUT_S}[a]")
    ffmpeg(*inputs, "-filter_complex", ";".join(filters), "-map", "[a]", "-ar", "48000", str(out))
    return len(clips)


def build(timeline_path: Path) -> Path:
    timeline = json.loads(timeline_path.read_text())
    run_dir = timeline_path.parent
    frames = sorted(timeline["frames"])
    tmap = TimeMap(frames[0][0], float(timeline["end"]), timeline["cuts"], timeline["speeds"])
    duration = tmap.duration

    concat = run_dir / "frames.txt"
    n_frames = video_list(frames, tmap, run_dir / "frames", concat)
    music = run_dir / "music.wav"
    music_bed(duration, music)
    audio = run_dir / "soundtrack.wav"
    n_clips = mix_audio(timeline["audio"], tmap, duration, music, audio)
    final = run_dir / "PATH-demo.mp4"
    ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat), "-i", str(audio),
           "-vf", f"fps={FPS},scale=1920:1080:flags=lanczos,format=yuv420p,fade=t=in:st=0:d={FADE_IN_S},"
                  f"fade=t=out:st={duration - FADE_OUT_S:.3f}:d={FADE_OUT_S}",
           "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-tune", "stillimage", "-r", str(FPS),
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(final))

    final_duration = probe_duration(final)
    checks = run_dir / "check_frames"
    checks.mkdir(exist_ok=True)
    for i, mark in enumerate(timeline["marks"]):
        at = min(tmap.film_time(float(mark["t"])) + 1.4, final_duration - 0.2)
        ffmpeg("-ss", f"{at:.2f}", "-i", str(final), "-frames:v", "1", "-q:v", "3", str(checks / f"{i:02d}.jpg"))
    summary = {
        "final": str(final), "film_seconds": round(final_duration, 1),
        "recorded_seconds": round(float(timeline["end"]) - frames[0][0], 1),
        "captured_frames": len(frames), "film_frames": n_frames, "cuts": len(timeline["cuts"]),
        "seconds_cut": round(sum(b - a for a, b in timeline["cuts"]), 1),
        "sped_up": [[round(tmap.film_time(a), 1), round(tmap.film_time(b), 1), f] for a, b, f in timeline["speeds"]],
        "voice_clips": n_clips, "check_frames": len(timeline["marks"]),
    }
    (run_dir / "assembly.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return final


if __name__ == "__main__":
    build(Path(sys.argv[1]).resolve())
