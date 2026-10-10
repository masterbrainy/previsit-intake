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
ARP_STEP_S = 0.5  # a soft plucked note every half beat-ish: 16 per chord
ARP_PATTERN = (0, 1, 2, 3, 2, 1, 2, 3, 0, 1, 2, 3, 2, 3, 1, 2)
MUSIC_GAIN = 0.13
MIN_SPEEDUP_FILM_S = 2.2  # a fast-forward stays on screen long enough to read its caption
MAX_VOICE_TEMPO = 1.3  # voices in a gently paced stretch speed up with it; faster stretches (fast-forwards) have none


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

    def factor_at(self, t: float) -> float:
        return next((factor for a, b, factor, _ in self.pieces if a <= t < b), 1.0)

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


def _pad_expr(notes: tuple[float, ...], detune: float) -> str:
    swell = "(1+0.25*sin(2*PI*0.13*t))"
    pad = "+".join(f"sin(2*PI*{f * detune:.3f}*t)" for f in notes)
    bass = f"0.35*sin(2*PI*{notes[0] / 2 * detune:.3f}*t)"
    return f"{swell}*({pad})/{len(notes)}+{bass}"


def _arp_expr(notes: tuple[float, ...], detune: float) -> str:
    """Plucked chord tones an octave up: a short attack, a fast decay, a touch of second harmonic."""
    tones = [f * 2 * detune for f in notes[1:]]
    freq = "0"
    for i in reversed(range(len(ARP_PATTERN))):
        freq = f"if(eq(floor(t/{ARP_STEP_S}),{i}),{tones[ARP_PATTERN[i] % len(tones)]:.3f},{freq})"
    phase = f"mod(t,{ARP_STEP_S})"
    env = f"min(1,{phase}*250)*exp(-7*{phase})"
    return f"{env}*(sin(2*PI*({freq})*t)+0.25*sin(4*PI*({freq})*t))"


def music_bed(duration: float, out: Path) -> None:
    """A slow pad with a low root, overlapping chord to chord, plus a soft arpeggio on the same chords."""
    inputs, filters, pads, arps = [], [], [], []
    n = int(duration // CHORD_STEP_S) + 1
    for k in range(n):
        notes = CHORDS[k % len(CHORDS)]
        delay = int(k * CHORD_STEP_S * 1000)
        pad = f"{_pad_expr(notes, 1.0)}|{_pad_expr(notes, 1.003)}"
        inputs += ["-f", "lavfi", "-i", f"aevalsrc='{pad}':s=48000:d={CHORD_LEN_S}"]
        filters.append(f"[{2 * k}:a]afade=t=in:d=3.5,afade=t=out:st={CHORD_LEN_S - 4.0}:d=4.0,adelay={delay}|{delay}[p{k}]")
        arp = f"{_arp_expr(notes, 1.0)}|{_arp_expr(notes, 1.002)}"
        inputs += ["-f", "lavfi", "-i", f"aevalsrc='{arp}':s=48000:d={CHORD_STEP_S}"]
        filters.append(f"[{2 * k + 1}:a]afade=t=in:d=0.02,afade=t=out:st={CHORD_STEP_S - 0.05}:d=0.05,"
                       f"adelay={delay}|{delay}[a{k}]")
        pads.append(f"[p{k}]")
        arps.append(f"[a{k}]")
    filters.append(f"{''.join(pads)}amix=inputs={n}:normalize=0,lowpass=f=1200,volume=1.0[pad]")
    filters.append(f"{''.join(arps)}amix=inputs={n}:normalize=0,highpass=f=300,lowpass=f=3200,"
                   f"aecho=0.8:0.55:{int(ARP_STEP_S * 1500)}|{int(ARP_STEP_S * 3000)}:0.3|0.15,volume=0.4[arp]")
    filters.append(f"[pad][arp]amix=inputs=2:normalize=0,aecho=0.8:0.6:140|310:0.2|0.12,"
                   f"volume={MUSIC_GAIN},atrim=0:{duration:.3f}[m]")
    ffmpeg(*inputs, "-filter_complex", ";".join(filters), "-map", "[m]", "-ar", "48000", str(out))


def readable_speeds(speeds: list, cuts: list) -> list:
    """Slows any fast-forward that would flash by too quickly to read its caption."""
    out = []
    for a, b, factor in speeds:
        shown = (b - a) - sum(max(0.0, min(b, cb) - max(a, ca)) for ca, cb in cuts)
        out.append([a, b, max(1.0, min(factor, shown / MIN_SPEEDUP_FILM_S))])
    return out


def _paced_voice(clip: dict, factor: float, out_dir: Path) -> tuple[str, float]:
    """A voice clip sped up with the stretch it starts in, rendered to its own file (atempo inside the big amix graph
    ends the whole mix early). Returns the file and its length on the film."""
    length = float(clip["length"])
    if not 1.0 < factor <= MAX_VOICE_TEMPO:
        return clip["file"], length
    out_dir.mkdir(exist_ok=True)
    paced = out_dir / f"{Path(clip['file']).stem}_x{factor:.2f}.wav"
    ffmpeg("-i", clip["file"], "-af", f"aresample=48000,atrim=0:{length:.3f},atempo={factor:.4f}", str(paced))
    return str(paced), length / factor


def mix_audio(clips: list, tmap: TimeMap, duration: float, music: Path, out: Path) -> int:
    inputs, filters, labels = [], [], []
    for i, clip in enumerate(clips):
        at = tmap.film_time(float(clip["t"]))
        source, length = _paced_voice(clip, tmap.factor_at(float(clip["t"])), out.parent / "paced")
        inputs += ["-i", source]
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
    # fast-forwards first: where they overlap a gentle pace, the fast-forward wins (TimeMap takes the first match)
    timeline["speeds"] = readable_speeds(timeline["speeds"], timeline["cuts"]) + timeline.get("paces", [])
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
    if final_duration < duration - 0.5:
        raise RuntimeError(f"film is {final_duration:.1f}s but the timeline is {duration:.1f}s: a track ended early")
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
