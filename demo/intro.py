"""Edits the team's two phone clips into the film's opening (the PATH team introduces the product).

Keeps the good takes (clip 2 up to "like fasting", then clip 1's redo), drops fumbles and pauses, speeds the speech
up a little, punches in on alternate segments to hide the jump cuts, cleans the audio, and burns in captions rendered
in the film's own type (demo/stage.html fonts, via headless Chromium).

    uv run --group demo python -m demo.intro "<IMG_1843 2.mov>" "<IMG_1843.mov>" <dir with a.json, b.json> demo/output/intro.mp4
"""

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright

TEMPO = 1.2
MAX_GAP_S = 0.18  # longest pause kept between words
PAD_S = 0.06
PUNCH_IN = 1.07
# Segments kept whole: five people saying their names overlap too much for the word timings to cut between them.
UNSPLIT_SEGMENTS = {0}
FPS = 30

# (clip, start, end) in source seconds, at word boundaries from the whisper word timings.
# Clip "b" is IMG_1843 2.mov (the first take), clip "a" is IMG_1843.mov (the redo).
SEGMENTS = (
    ("b", 0.00, 3.86),    # I'm Dr. Megh. I'm Nikhil. I'm Brian. I'm John. I'm Om.
    ("b", 3.94, 11.62),   # And did you know that doctors lose consulting time … delay diagnosis.
    ("b", 11.98, 20.32),  # Pre-visit Assessment and Triage Helper, or PATH for short, … already knows their story.
    ("b", 20.58, 23.32),  # Approved tests come with their prep instructions, like fasting. ("fasting" ends 23.18)
    ("a", 0.90, 4.52),    # So no visit slips because the patient did not maintain NPO.
    ("a", 4.84, 10.06),   # The doctor goes straight to the follow-up questions that matter, …
    ("a", 10.24, 16.90),  # And for patients who take a while to tell their story, … already on the page.
    ("a", 17.08, 18.18),  # That's what we created.
    ("a", 18.58, 19.00),  # PATH.
)

# Captions: (clip, first word start, last word end, text). Whisper's mishearings are corrected here
# ("wizard slips" → "visit slips", "FASFA" → "fasting", "he created" → "we created").
CAPTIONS = (
    ("b", 0.00, 3.84, "TEAM_NAMES"),
    ("b", 3.94, 7.52, "Did you know doctors lose consulting time taking histories,"),
    ("b", 8.32, 11.60, "and tests ordered on the visit day delay diagnosis?"),
    ("b", 12.00, 14.86, "Pre-visit Assessment & Triage Helper, or PATH for short,"),
    ("b", 14.86, 17.32, "takes the full history by voice before the visit."),
    ("b", 17.48, 20.28, "By the time the patient walks in, the doctor already knows their story."),
    ("b", 20.62, 23.12, "Approved tests come with their prep instructions, like fasting,"),
    ("a", 0.94, 4.50, "no visit slips because a patient did not maintain NPO."),
    ("a", 4.86, 7.68, "The doctor goes straight to the follow-up questions that matter,"),
    ("a", 7.92, 10.04, "instead of spending the consult working out what they are."),
    ("a", 10.26, 14.18, "And for patients who take a while to tell their story, like many older patients,"),
    ("a", 14.74, 16.86, "five or ten minutes of their history is already on the page."),
    ("a", 17.12, 18.14, "That's what we created."),
    ("a", 18.62, 18.94, "PATH."),
)
TEAM_NAMES = "I'm Dr. Megh. I'm Nikhil. I'm Brian. I'm John. I'm Om."

CAPTION_HTML = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@700&family=Bricolage+Grotesque:opsz,wght@12..96,750&display=swap">
<style>html,body{margin:0;width:1920px;height:1080px;background:transparent}
.cap{position:absolute;left:50%;bottom:86px;transform:translateX(-50%);max-width:1500px;padding:16px 30px;border-radius:18px;
background:rgba(10,21,32,.78);color:#fff;font:700 44px/1.28 "Atkinson Hyperlegible",system-ui,sans-serif;text-align:center;
box-shadow:0 10px 30px rgba(0,0,0,.25)}
.cap.big{font:750 92px/1 "Bricolage Grotesque",system-ui,sans-serif;letter-spacing:-.03em;padding:18px 40px;color:#f2c230}
.bug{position:absolute;left:48px;top:40px;display:flex;align-items:center;gap:12px;color:#fff;font:750 26px "Bricolage Grotesque",sans-serif;
text-shadow:0 2px 8px rgba(0,0,0,.4)}
.mark{position:relative;width:38px;height:38px;border-radius:10px;background:#0b6b66;box-shadow:inset 0 -3px 0 #f2c230}
.mark:before,.mark:after{content:"";position:absolute;inset:0;margin:auto;background:#fff;border-radius:2px}
.mark:before{width:18px;height:6px}.mark:after{width:6px;height:18px}</style></head>
<body><div class="bug"><span class="mark"></span>PATH</div><div id="c" class="cap"></div></body></html>"""


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def words(transcript: Path) -> list[tuple[float, float]]:
    return [(w["start"], w["end"]) for w in json.loads(transcript.read_text())["words"]]


def keep_ranges(segments, word_times: dict) -> list[tuple[str, float, float, int]]:
    """Splits each segment at pauses longer than MAX_GAP_S, so pauses inside sentences go too."""
    pieces = []
    for n, (clip, start, end) in enumerate(segments):
        inside = [] if n in UNSPLIT_SEGMENTS else [
            (a, b) for a, b in word_times[clip] if a >= start - 0.01 and b <= end + 0.01]
        run_start, last_end = start, None
        for a, b in inside:
            if last_end is not None and a - last_end > MAX_GAP_S:
                pieces.append((clip, run_start, min(last_end + PAD_S, end), n))
                run_start = max(start, a - PAD_S)
            last_end = b
        pieces.append((clip, run_start, end, n))
    return [(c, a, b, n) for c, a, b, n in pieces if b - a > 0.05]


def film_time(pieces, clip: str, t: float) -> float:
    """Source time in a clip → time in the edited intro (after cuts and the tempo change)."""
    out = 0.0
    for c, a, b, _ in pieces:
        if c == clip and a - 0.2 <= t <= b + 0.2:
            return out + (min(max(t, a), b) - a) / TEMPO
        out += (b - a) / TEMPO
    raise ValueError(f"{clip}@{t} is not in the edit")


async def render_captions(texts: list[str], out_dir: Path) -> list[Path]:
    paths = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.set_content(CAPTION_HTML, wait_until="networkidle")
        await page.evaluate("document.fonts.ready")
        for i, text in enumerate(texts):
            await page.evaluate("([t, big]) => { const c = document.getElementById('c'); c.textContent = t; c.className = big ? 'cap big' : 'cap'; }",
                                [text, text == "PATH."])
            path = out_dir / f"cap_{i:02d}.png"
            await page.screenshot(path=str(path), omit_background=True)
            paths.append(path)
        await browser.close()
    return paths


def build(clip_b: Path, clip_a: Path, transcripts: Path, out: Path) -> float:
    sources = {"b": clip_b, "a": clip_a}
    word_times = {c: words(transcripts / f"{c}.json") for c in sources}
    pieces = keep_ranges(SEGMENTS, word_times)
    work = Path(tempfile.mkdtemp(prefix="intro_"))

    # 1. cut each piece, punching in on alternate segments; normalise to 1080p30
    parts = []
    for i, (clip, a, b, seg) in enumerate(pieces):
        zoom = PUNCH_IN if seg % 2 else 1.0
        vf = (f"scale=1920:1080,crop=iw/{zoom}:ih/{zoom}:(iw-iw/{zoom})*0.35:(ih-ih/{zoom})*0.3,scale=1920:1080,"
              f"eq=contrast=1.05:saturation=1.08:brightness=0.01,fps={FPS},setpts=(PTS-STARTPTS)/{TEMPO}")
        af = f"asetpts=PTS-STARTPTS,atempo={TEMPO},afade=t=in:d=0.02,afade=t=out:st={max(0.0, (b - a) / TEMPO - 0.03):.3f}:d=0.03"
        part = work / f"p{i:02d}.mp4"
        ffmpeg("-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(sources[clip]), "-vf", vf, "-af", af,
               "-c:v", "libx264", "-preset", "fast", "-crf", "14", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", str(part))
        parts.append(part)
    listing = work / "parts.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts))
    joined = work / "joined.mp4"
    ffmpeg("-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(joined))
    duration = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                     str(joined)], capture_output=True, text=True, check=True).stdout)

    # 2. captions as overlays at their edited times
    texts = [TEAM_NAMES if t == "TEAM_NAMES" else t for _, _, _, t in CAPTIONS]
    images = asyncio.run(render_captions(texts, work))
    inputs, chain, last = ["-i", str(joined)], [], "[0:v]"
    for i, ((clip, a, b, _), image) in enumerate(zip(CAPTIONS, images)):
        start, end = film_time(pieces, clip, a), film_time(pieces, clip, b) + 0.25
        if i + 1 < len(CAPTIONS):
            nxt = CAPTIONS[i + 1]
            end = min(end, film_time(pieces, nxt[0], nxt[1]))
        inputs += ["-i", str(image)]
        label = f"[v{i}]"
        chain.append(f"{last}[{i + 1}:v]overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'{label}")
        last = label

    # 3. audio: rumble cut, noise reduction, presence, gentle compression, broadcast level
    voice = ("highpass=f=90,lowpass=f=12000,afftdn=nf=-28,equalizer=f=250:t=q:w=1.2:g=-2,"
             "equalizer=f=3200:t=q:w=1.0:g=3,acompressor=threshold=-20dB:ratio=3:attack=10:release=150:makeup=3,"
             "loudnorm=I=-16:TP=-1.5:LRA=7")
    chain.append(f"{last}fade=t=in:d=0.4,fade=t=out:st={duration - 0.35:.3f}:d=0.35[v]")
    chain.append(f"[0:a]{voice},afade=t=in:d=0.3,afade=t=out:st={duration - 0.35:.3f}:d=0.35[a]")
    ffmpeg(*inputs, "-filter_complex", ";".join(chain), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "slow",
           "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(out))
    return duration


if __name__ == "__main__":
    length = build(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
    print(f"intro: {length:.1f}s → {sys.argv[4]}")
