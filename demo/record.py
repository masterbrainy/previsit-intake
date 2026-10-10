"""Films the PATH demo from the real running app (PROGRESS D.4).

Starts the demo site from a clean film state, opens a 1920x1080 stage (demo/stage.html) that frames the real hospital
pages in a browser window and the real patient portal in a phone, and drives four chapters: booking, the pre-visit
call, the doctor's review and the red-flag stop. Simulated patients (evals/simulator.py) answer the real assistant;
their answers are spoken with a synthetic voice and appear as a live transcript, the way a voice answer looks.

Frames are captured losslessly-ish with the Chrome screencast (sharper than Playwright's video). Waits for the AI are
logged as cuts and the fast-forward ranges as speed-ups; demo/assemble.py turns frames + timeline into the film.

    uv run --group demo python -m demo.record
"""

import asyncio
import base64
import json
import re
import socket
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from playwright.async_api import FrameLocator, Locator, Page, async_playwright
from sqlmodel import Session, create_engine, select

from demo import captions as C
from demo.config import (DEMO_PORT, DEMO_URL, FILM_CLINIC, FILM_FULL_SCENARIO, FILM_RED_SCENARIO, OUTPUT_DIR,
                         PHYSICIAN, demo_settings)
from evals.scenario import dob_for, load_all
from evals.simulator import SimulatedPatient
from previsit.config import PROJECT_ROOT
from previsit.llm import OpenAILLM
from previsit.models import HistorySheetRecord, Intake, MedicalRecommendation

STAGE_URL = f"{DEMO_URL}/__film_stage"
TYPE_MS = 40
KEEP_HEAD_S, KEEP_TAIL_S = 0.45, 0.15  # what is left of each cut wait
MIN_CUT_S = 0.9
CALL_FF_SPEED, RED_FF_SPEED = 5.0, 4.0
SETUP_SPEED = 2.5  # form filling the viewer has seen before
SILENT_PACE = 1.12  # stretches with nobody speaking (title, booking, the doctor's review) run a touch quicker
AGENT_SPEECH_CAP = {"consent": 6.0, "identity": 4.5, "interview": 5.5, "readback": 5.5, "complete": 8.0, "escalated": 9.0}
HOLDING_LINE_CAP = 2.0
# Scripted answers for the moments the film depends on (the rest of each call is the simulated patient).
OPENING_ANSWER = ("I've had a fever for four days, worse in the evenings, up to 38.9. A dry cough started the next day, "
                  "and for the last two days my whole body aches.")
RED_FLAG_ANSWER = ("I've had a fever and a bad headache since yesterday. And my neck's really stiff. It hurts to bend my "
                   "head forward, and the light hurts my eyes.")  # "let me put together the main points" before the read-back
PATIENT_SPEECH_CAP = 11.0  # a long answer fades out at a sentence end while the transcript finishes
AGENT_TEMPO, PATIENT_TEMPO = 1.1, 1.15
PATIENT_VOICES = {"DEMO-001": ("ash", "A man in his forties with a fever, a little tired, speaking naturally and briefly."),
                  "DEMO-002": ("verse", "A twenty-year-old student who feels unwell and a bit worried, speaking naturally.")}

# Every frame: no scrollbars, and the on-screen demo sign-in code is hidden (the film shows it arriving by text).
FRAME_SCRIPT = """
document.addEventListener('DOMContentLoaded', () => {
  const s = document.createElement('style');
  s.textContent = '::-webkit-scrollbar{display:none} html{scrollbar-width:none} .film-hide{display:none!important}';
  document.head.appendChild(s);
  document.querySelectorAll('.banner.warn').forEach((b) => { if (b.textContent.includes('Demo mode')) b.classList.add('film-hide'); });
});
"""


class Film:
    def __init__(self, page: Page, out: Path, settings) -> None:
        self.page, self.out, self.settings = page, out, settings
        self.frames: list[tuple[float, str]] = []
        self.cuts: list[tuple[float, float]] = []
        self.speeds: list[list[float]] = []  # [start, end, factor]
        self.paces: list[list[float]] = []  # gentle [start, end, factor] under the speeds above
        self._speeding = False
        self.audio: list[dict] = []
        self.marks: list[dict] = []
        self.replies: asyncio.Queue = asyncio.Queue()
        (out / "frames").mkdir(parents=True)
        (out / "audio").mkdir()

    # ----- capture ----------------------------------------------------------------------------------------------

    async def start_capture(self) -> None:
        self.cdp = await self.page.context.new_cdp_session(self.page)
        self.cdp.on("Page.screencastFrame", self._on_frame)
        await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": 1920, "maxHeight": 1080})

    async def _on_frame(self, params: dict) -> None:
        path = self.out / "frames" / f"{len(self.frames):06d}.jpg"
        path.write_bytes(base64.b64decode(params["data"]))
        self.frames.append((params["metadata"]["timestamp"], path.name))
        try:
            await self.cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
        except Exception:  # the session closes at the end of the film
            pass

    async def stop_capture(self) -> None:
        await self.cdp.send("Page.stopScreencast")

    # ----- timeline ---------------------------------------------------------------------------------------------

    @staticmethod
    def now() -> float:
        return time.time()

    async def hold(self, seconds: float) -> None:
        await asyncio.sleep(max(0.0, seconds))

    def cut(self, start: float, end: float | None = None) -> None:
        end = self.now() if end is None else end
        if end - start >= MIN_CUT_S:
            self.cuts.append((start + KEEP_HEAD_S, end - KEEP_TAIL_S))

    async def waiting(self, awaitable):
        """Awaits something slow (the AI, a page load) and cuts the wait from the film."""
        start = self.now()
        result = await awaitable
        self.cut(start)
        return result

    def speed(self, factor: float | None) -> None:
        """Starts a sped-up range (factor) or ends the open one (None)."""
        if factor:
            now = self.now()
            self.speeds.append([now, now, factor])
            self._speeding = True
        elif self._speeding:
            self.speeds[-1][1] = self.now()
            self._speeding = False

    def pace(self, start: float, factor: float = SILENT_PACE) -> None:
        self.paces.append([start, self.now(), factor])

    @property
    def speeding(self) -> bool:
        return self._speeding

    async def stage(self, js: str, *args) -> None:
        await self.page.evaluate(f"(a) => stage.{js}(...a)", list(args))

    async def caption(self, cap: tuple[str, str, str]) -> None:
        await self.stage("caption", *cap)
        self.marks.append({"t": self.now(), "text": cap[1]})
        print(f"[{len(self.marks):3d}] {cap[1][:90]}", flush=True)

    async def card(self, kind: str, data: dict, seconds: float) -> None:
        await self.stage("caption", "", "", "")
        await self.stage("card", kind, data)
        self.marks.append({"t": self.now(), "text": data.get("title", "")})
        await self.hold(seconds)
        await self.stage("card", None, None)
        await self.hold(0.7)

    # ----- frames and pointer -----------------------------------------------------------------------------------

    def frame(self, name: str):
        return self.page.frame(name=name)

    def loc(self, name: str, selector: str) -> Locator:
        frame: FrameLocator = self.page.frame_locator(f"#{name}")
        return frame.locator(selector).first

    async def goto(self, name: str, path: str) -> None:
        url = path if path.startswith("http") else f"{DEMO_URL}{path}"
        await self.waiting(self.frame(name).goto(url, wait_until="load"))
        if name == "doc":
            await self.stage("url", "riverside.health" + url.removeprefix(DEMO_URL).split("#")[0])

    async def centre(self, target: Locator) -> tuple[float, float]:
        await target.scroll_into_view_if_needed()
        box = await target.bounding_box()
        if box is None:
            raise RuntimeError("element has no box to point at")
        return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

    async def point(self, target: Locator, pause: float = 0.75) -> None:
        x, y = await self.centre(target)
        await self.stage("cursor", x, y, False)
        await self.hold(pause)

    async def tap(self, target: Locator) -> None:
        """Moves the stage cursor to the target and shows a click ripple, without clicking."""
        await self.point(target)
        x, y = await self.centre(target)
        await self.stage("cursor", x, y, True)
        await self.hold(0.15)

    async def click(self, target: Locator, pause: float = 0.6, navigates: str | None = None) -> None:
        await self.tap(target)
        if navigates:
            frame = self.frame(navigates)
            start = self.now()
            async with frame.expect_navigation(wait_until="load", timeout=60_000):
                await target.click()
            self.cut(start)
            if navigates == "doc":
                await self.stage("url", "riverside.health" + frame.url.removeprefix(DEMO_URL).split("#")[0])
        else:
            await target.click()
        await self.hold(pause)

    async def type(self, target: Locator, text: str, delay: int = TYPE_MS) -> None:
        await self.click(target, pause=0.1)
        await target.press_sequentially(text, delay=delay)
        await self.hold(0.3)

    async def scroll_to(self, name: str, selector: str, block: str = "start", hold: float = 1.0) -> None:
        await self.loc(name, selector).evaluate(f"el => el.scrollIntoView({{behavior: 'smooth', block: '{block}'}})")
        await self.hold(hold)

    async def zoom_on(self, target: Locator, scale: float) -> None:
        box = await target.bounding_box()
        await self.stage("zoom", scale, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        await self.hold(0.9)

    # ----- voices -----------------------------------------------------------------------------------------------

    def add_audio(self, path: Path, cap: float | None = None, text: str = "") -> float:
        duration = media_duration(path)
        length = speech_cut(text, duration, cap)
        self.audio.append({"file": str(path), "t": self.now(), "length": length, "trimmed": length < duration})
        return length

    def agent_audio(self, data: dict, cap: float | None) -> float:
        if not data.get("audio") or self.speeding:
            return 0.0
        raw = self.out / "audio" / f"agent_{len(self.audio):03d}_raw.mp3"
        raw.write_bytes(base64.b64decode(data["audio"]))
        return self.add_audio(quicken(raw, AGENT_TEMPO), cap, data.get("agent_text", ""))

    def patient_speech(self, text: str, voice: tuple[str, str]) -> Path:
        from openai import OpenAI

        client = OpenAI(api_key=self.settings.openai_api_key.get_secret_value(), timeout=45.0, max_retries=2)
        response = client.audio.speech.create(model=self.settings.tts_model, voice=voice[0], input=text,
                                              instructions=voice[1], response_format="mp3")
        path = self.out / "audio" / f"patient_{time.time_ns()}_raw.mp3"
        path.write_bytes(response.read())
        return quicken(path, PATIENT_TEMPO)

    async def on_response(self, response) -> None:
        if re.search(r"/intake/(start|turn|readback)$", response.url):
            try:
                self.replies.put_nowait(await response.json())
            except Exception as exc:  # a failed turn is surfaced to the driver, not swallowed
                self.replies.put_nowait({"error": f"unreadable reply: {exc}"})

    async def next_reply(self) -> dict:
        data = await self.waiting(asyncio.wait_for(self.replies.get(), timeout=180))
        if data.get("error"):
            raise RuntimeError(f"intake turn failed: {data['error']}")
        return data

    async def speak_patient(self, text: str, audio: Path) -> None:
        """A voice answer: the mic listens while the words appear as a live transcript, then it is sent."""
        await self.tap(self.loc("pt", "#mic"))  # visual only: a real tap would ask for the microphone
        pt = self.frame("pt")
        await pt.evaluate("""() => { const m = document.getElementById('mic'); m.classList.add('recording');
          document.getElementById('status').textContent = 'Listening…'; }""")
        length = self.add_audio(audio, PATIENT_SPEECH_CAP, text)
        words = text.split()
        step = length * 0.92 / max(1, len(words))
        for i in range(1, len(words) + 1):
            await pt.evaluate("(t) => { const el = document.getElementById('text'); el.value = t; el.scrollLeft = el.scrollWidth; }",
                              " ".join(words[:i]))
            await self.hold(step)
        await self.hold(length * 0.08 + 0.25)
        await pt.evaluate("""() => { document.getElementById('mic').classList.remove('recording');
          document.getElementById('status').textContent = ''; document.getElementById('textForm').requestSubmit(); }""")

    async def type_patient(self, text: str) -> None:
        await self.frame("pt").evaluate("(t) => { document.getElementById('text').value = t; document.getElementById('textForm').requestSubmit(); }", text)

    def save(self, meta: dict) -> Path:
        timeline = {"frames": self.frames, "cuts": self.cuts, "speeds": self.speeds, "paces": self.paces, "audio": self.audio,
                    "marks": self.marks, "end": self.now(), **meta}
        path = self.out / "timeline.json"
        path.write_text(json.dumps(timeline, indent=1))
        return path


def speech_cut(text: str, duration: float, cap: float | None) -> float:
    """How much of a voice clip to keep: all of it, or up to the last sentence end that fits the cap."""
    if cap is None or duration <= cap:
        return duration
    if text:
        ends = [m.end() for m in re.finditer(r"[.!?](?=\s|$)", text)]
        fits = [duration * e / len(text) for e in ends if 2.0 <= duration * e / len(text) <= cap + 1.5]
        if fits:
            return min(duration, max(fits) + 0.3)
    return cap


def quicken(path: Path, tempo: float) -> Path:
    """A slightly faster copy of a voice clip (pitch kept), so the film moves at a demo pace."""
    out = path.with_name(path.name.replace("_raw", ""))
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(path), "-filter:a", f"atempo={tempo}",
                    str(out)], check=True)
    return out


def media_duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


# ----- the pre-visit call -------------------------------------------------------------------------------------------

async def set_fast_forward(film: Film, speed: float | None, caption=None, on_fast_forward=None) -> None:
    if speed and not film.speeding:
        film.speed(speed)
        await film.stage("ff", f"Fast-forward ×{speed:g}")
        if caption:
            await film.caption(caption)
        if on_fast_forward:
            await on_fast_forward()
    elif not speed and film.speeding:
        film.speed(None)
        await film.stage("ff", "")


def scripted_reply(sim: SimulatedPatient, agent_text: str, line: str):
    """The patient says a scripted line; the simulator's history records it so later answers stay consistent."""
    from evals.simulator import PatientTurnOut

    sim._messages += [{"role": "user", "content": agent_text}, {"role": "assistant", "content": line}]
    return PatientTurnOut(utterance=line, disclosed=[], hang_up=False)


async def converse(film: Film, sim: SimulatedPatient, voice: tuple[str, str], live, captions: dict, ff_speed: float,
                   script=None, on_fast_forward=None) -> dict:
    """Runs a real intake against the simulated patient.

    live(state, interview_answers) picks real time or fast-forward for each assistant turn; script(state,
    interview_answers) may return a line the patient says instead of the simulator's answer.
    """
    loop = asyncio.get_running_loop()
    data = await film.next_reply()
    answers = 0
    for _ in range(45):
        state = data["state"]
        is_live = live(state, answers)
        ff_caption = captions.get(f"ff_{state}", captions["ff"])
        await set_fast_forward(film, None if is_live else ff_speed, ff_caption, on_fast_forward)
        if is_live and state in captions and (not film.marks or film.marks[-1]["text"] != captions[state][1]):
            await film.caption(captions[state])
        cap = HOLDING_LINE_CAP if data.get("follow_up") else AGENT_SPEECH_CAP.get(state)
        speaking = film.agent_audio(data, cap) if is_live else 0.0
        if data.get("follow_up"):  # read-back holding line: the summary is fetched straight away
            await film.hold(speaking + 0.3)
            data = await film.next_reply()
            continue
        if data.get("ended"):
            await set_fast_forward(film, None)
            await film.hold(max(speaking, 2.5) + 0.8)
            return data

        line = script(state, answers) if script else None
        if line:
            reply = asyncio.ensure_future(asyncio.sleep(0, scripted_reply(sim, data["agent_text"], line)))
        else:
            reply = loop.run_in_executor(None, sim.reply, data["agent_text"])
        if is_live:
            async def with_speech(reply=reply):
                out = await reply
                return out, await loop.run_in_executor(None, film.patient_speech, out.utterance, voice)
            ready = asyncio.ensure_future(with_speech())
            await film.hold(speaking + 0.5)
            out, audio = await film.waiting(ready)
            await film.speak_patient(out.utterance, audio)
        else:
            await film.hold(1.1)
            out = await film.waiting(reply)
            await film.type_patient(out.utterance)
        if state == "interview":
            answers += 1
        data = await film.next_reply()
    raise RuntimeError("the intake did not end")


def wait_for_sheet(settings, appointment_id: int, timeout: float = 240) -> None:
    """Polls the demo database until the history sheet and the suggested tests exist."""
    engine = create_engine(settings.database_url)
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            with Session(engine) as session:
                intake = session.exec(select(Intake).where(Intake.appointment_id == appointment_id)).first()
                sheet = intake and session.exec(select(HistorySheetRecord).where(HistorySheetRecord.intake_id == intake.id)).first()
                recs = session.exec(select(MedicalRecommendation).where(MedicalRecommendation.appointment_id == appointment_id)).all()
                if sheet and recs:
                    return
            time.sleep(1.0)
    finally:
        engine.dispose()
    raise RuntimeError("the history sheet was not ready in time")


# ----- chapters -----------------------------------------------------------------------------------------------------

async def portal_sign_in(film: Film, contact: str) -> None:
    await film.goto("pt", "/portal/sign-in")
    await film.type(film.loc("pt", "#contact"), contact)
    await film.click(film.loc("pt", "main button[type=submit]"), navigates="pt", pause=0.3)
    code = (await film.loc("pt", ".code").text_content()).strip()
    await film.stage("sms", f"{code} is your PATH sign-in code for {FILM_CLINIC}. It expires in 10 minutes.")
    await film.hold(1.3)
    await film.type(film.loc("pt", "#code"), code, delay=45)
    await film.click(film.loc("pt", "main button[type=submit]"), navigates="pt", pause=0.6)


async def chapter_booking(film: Film, scenario, dob: date) -> int:
    started = film.now()
    await film.card("chapter", C.CHAPTERS[1], 1.5)
    await film.stage("step", 1)
    await film.caption(C.SIGN_IN)
    await portal_sign_in(film, "+1 555 555 0142")
    await film.caption(C.DETAILS)
    await film.click(film.loc("pt", "a[href='/portal/people/new']"), navigates="pt")
    film.speed(SETUP_SPEED)
    await film.type(film.loc("pt", "#name"), scenario.patient_name)
    await film.loc("pt", "#dob").fill(dob.isoformat())
    await film.loc("pt", "#sex").select_option(scenario.sex)
    await film.hold(0.4)
    await film.click(film.loc("pt", "main button[type=submit]"), navigates="pt")
    film.speed(None)
    await film.caption(C.REASON)
    await film.type(film.loc("pt", "#reason"), "Fever and cough for 4 days")
    await film.click(film.loc("pt", "main button[type=submit]"), navigates="pt", pause=0.4)
    await film.caption(C.RECOMMEND)
    await film.point(film.loc("pt", ".choice"), pause=2.2)
    when = (date.today() + timedelta(days=1)).isoformat() + "T09:30"
    await film.scroll_to("pt", "#scheduled_at", block="center", hold=0.6)
    await film.click(film.loc("pt", "#scheduled_at"), pause=0.2)
    await film.loc("pt", "#scheduled_at").fill(when)
    await film.hold(0.8)
    await film.click(film.loc("pt", "button:has-text('Book appointment')"), navigates="pt", pause=0.8)
    appt_id = int(re.search(r"/portal/appointments/(\d+)", film.frame("pt").url).group(1))
    await film.goto("doc", "/dashboard")
    await film.stage("focus", "doc")
    await film.caption(C.BOOKED)
    row = film.loc("doc", f"tr:has(b:text-is('{scenario.patient_name}'))")
    await film.zoom_on(row, 1.18)
    await film.point(row, pause=2.4)
    await film.stage("zoom", 1)
    await film.stage("focus", "both")
    await film.hold(0.6)
    film.pace(started)
    return appt_id


async def chapter_call(film: Film, sim: SimulatedPatient, voice) -> None:
    await film.card("chapter", C.CHAPTERS[2], 1.5)
    await film.stage("step", 2)
    await film.stage("focus", "pt")
    await film.click(film.loc("pt", "a.button.big"), navigates="pt", pause=0)

    def live(state: str, answers: int) -> bool:
        return state in ("consent", "readback", "complete") or (state == "interview" and answers < 1)

    async def show_front_desk() -> None:
        await film.goto("doc", "/dashboard")
        await film.stage("focus", "both")

    def script(state: str, answers: int) -> str | None:
        return OPENING_ANSWER if state == "interview" and answers == 0 else None

    captions = {"consent": C.CONSENT, "ff_identity": C.IDENTITY, "interview": C.INTERVIEW, "ff": C.FAST_FORWARD,
                "readback": C.READBACK, "complete": C.ADVICE}
    await converse(film, sim, voice, live, captions, CALL_FF_SPEED, script, on_fast_forward=show_front_desk)


async def chapter_review(film: Film, settings, appt_id: int) -> None:
    started = film.now()
    await film.card("chapter", C.CHAPTERS[3], 1.5)
    await film.stage("step", 3)
    await film.stage("role", f"{PHYSICIAN} · General practice")
    await film.stage("focus", "doc")
    await film.caption(C.DOCTOR_SIGN_IN)
    film.speed(SETUP_SPEED + 1)
    await film.goto("doc", "/doctor/sign-in")
    await film.loc("doc", "#doctor_id").select_option(label=f"{PHYSICIAN} · General practice")
    await film.click(film.loc("doc", "main button[type=submit]"), navigates="doc", pause=0.2)
    code = (await film.loc("doc", ".code").text_content()).strip()
    await film.type(film.loc("doc", "#code"), code, delay=60)
    await film.waiting(asyncio.get_running_loop().run_in_executor(None, wait_for_sheet, settings, appt_id))
    await film.click(film.loc("doc", "main button[type=submit]"), navigates="doc", pause=0.3)
    film.speed(None)
    await film.caption(C.MY_PATIENTS)
    await film.point(film.loc("doc", f"a[href='/patients/{appt_id}']"), pause=2.3)
    await film.click(film.loc("doc", f"a[href='/patients/{appt_id}']"), navigates="doc", pause=0.4)

    await film.caption(C.SHEET)
    await film.scroll_to("doc", "section.card:has(h2:text-is('History sheet'))", hold=0.8)
    sheet = film.loc("doc", "section.card:has(h2:text-is('History sheet')) ol.cc")
    await film.zoom_on(sheet, 1.32)
    await film.hold(3.0)
    await film.caption(C.CITATION)
    cite = film.loc("doc", "section.card:has(h2:text-is('History sheet')) ol.cc a.cite")
    await film.point(cite, pause=0.9)
    await film.stage("zoom", 1)
    await film.click(cite, pause=0.3)
    target = film.loc("doc", ".turn:target")
    await film.hold(0.6)
    await film.zoom_on(target, 1.35)
    await film.hold(2.6)
    await film.stage("zoom", 1)
    await film.hold(0.5)

    await film.caption(C.SUGGESTED)
    await film.scroll_to("doc", "#tests", hold=0.6)
    await film.zoom_on(film.loc("doc", "#tests .rec"), 1.28)
    await film.point(film.loc("doc", "#tests .rec strong"), pause=2.6)
    await film.stage("zoom", 1)
    await film.stage("focus", "pt")
    await film.goto("pt", f"/portal/appointments/{appt_id}")
    await film.caption(C.PATIENT_WAITS)
    await film.scroll_to("pt", ".card:has(h2:text-is('What to do until your appointment'))", hold=2.4)
    await film.stage("focus", "both")
    await film.caption(C.APPROVE)
    await film.click(film.loc("doc", "#tests button[value='approve']"), navigates="doc", pause=0.6)
    await film.scroll_to("doc", "#tests", hold=0.5)
    await film.click(film.loc("doc", "#tests button:has-text('Send')"), navigates="doc", pause=0.6)
    await film.goto("pt", f"/portal/appointments/{appt_id}")
    await film.stage("focus", "pt")
    await film.caption(C.SENT)
    await film.scroll_to("pt", ".card:has(h2:text-is('Tests your doctor has asked for'))", hold=3.0)
    await film.stage("focus", "both")
    film.pace(started)


async def chapter_safety(film: Film, sim: SimulatedPatient, voice, contact: str, name: str, dob: date) -> None:
    await film.goto("doc", "/dashboard")
    await film.card("chapter", C.CHAPTERS[4], 1.5)
    await film.stage("step", 4)
    await film.stage("role", "Hospital · front desk")
    await film.stage("focus", "pt")
    await film.caption(C.RED_START)
    film.speed(SETUP_SPEED + 1)
    await portal_sign_in(film, contact)
    await film.click(film.loc("pt", "a.card.appt"), navigates="pt", pause=0.3)
    await film.click(film.loc("pt", "a.button.big"), navigates="pt", pause=0)
    film.speed(None)

    def live(state: str, answers: int) -> bool:
        return state in ("interview", "escalated")

    lines = {"consent": "Yes, that's fine.", "identity": f"{name}, born {dob.day} {dob:%B %Y}. It's me."}

    def script(state: str, answers: int) -> str | None:
        if state == "interview" and answers == 0:
            return RED_FLAG_ANSWER
        return lines.get(state)

    captions = {"ff": C.RED_FAST_FORWARD, "interview": C.RED_INTERVIEW, "escalated": C.RED_STOP}
    await converse(film, sim, voice, live, captions, RED_FF_SPEED, script)
    await film.hold(1.0)
    await film.goto("doc", "/dashboard")
    await film.stage("focus", "doc")
    alert_shown = film.now()
    await film.caption(C.RED_ALERT)
    banner = film.loc("doc", ".banner.danger")
    await film.zoom_on(banner, 1.25)
    await film.point(banner.locator("strong"), pause=3.6)
    await film.stage("zoom", 1)
    await film.stage("focus", "both")
    await film.hold(0.8)
    film.pace(alert_shown, 1.15)


# ----- run ----------------------------------------------------------------------------------------------------------

def wait_for_port(port: int, timeout: float = 40) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.3)
    raise RuntimeError(f"demo server did not start on port {port}")


async def film_it(out: Path) -> Path:
    settings = demo_settings(FILM_CLINIC)
    llm = OpenAILLM(settings)
    full, red = load_all([FILM_FULL_SCENARIO])[0], load_all([FILM_RED_SCENARIO])[0]
    full_dob, red_dob = dob_for(full.age, date.today()), dob_for(red.age, date.today())
    stage_html = (Path(__file__).parent / "stage.html").read_text()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080}, device_scale_factor=1,
            http_credentials={"username": settings.physician_username,
                              "password": settings.physician_password.get_secret_value()},
        )
        await context.add_init_script(FRAME_SCRIPT)
        await context.route(STAGE_URL, lambda route: route.fulfill(status=200, content_type="text/html", body=stage_html))
        page = await context.new_page()
        film = Film(page, out, settings)
        page.on("response", film.on_response)
        await page.goto(STAGE_URL, wait_until="networkidle")
        await page.evaluate("document.fonts.ready")
        await film.frame("doc").goto(f"{DEMO_URL}/dashboard")
        await film.frame("pt").goto(f"{DEMO_URL}/portal/sign-in")
        await film.stage("url", "riverside.health/dashboard")
        await film.stage("card", "title", C.TITLE)
        await film.hold(1.2)
        await film.start_capture()
        started = film.now()
        await film.hold(4.0)
        await film.stage("card", None, None)
        await film.hold(0.8)
        film.pace(started, 1.15)

        appt_id = await chapter_booking(film, full, full_dob)
        await chapter_call(film, SimulatedPatient(llm, full, full_dob), PATIENT_VOICES[FILM_FULL_SCENARIO])
        await chapter_review(film, settings, appt_id)
        await chapter_safety(film, SimulatedPatient(llm, red, red_dob), PATIENT_VOICES[FILM_RED_SCENARIO],
                             "+1 555 555 0143", red.patient_name, red_dob)

        await film.stage("caption", "", "", "")
        await film.stage("card", "end", C.END)
        film.marks.append({"t": film.now(), "text": "End card"})
        await film.hold(4.0)
        await film.stop_capture()
        await context.close()
        await browser.close()
    return film.save({"full_scenario": FILM_FULL_SCENARIO, "red_scenario": FILM_RED_SCENARIO})


def main() -> None:
    out = OUTPUT_DIR / time.strftime("%Y%m%dT%H%M%S")
    out.mkdir(parents=True)
    server = subprocess.Popen([sys.executable, "-m", "demo.serve", "--film"], cwd=PROJECT_ROOT)
    try:
        wait_for_port(DEMO_PORT)
        timeline = asyncio.run(film_it(out))
        print(f"Done. Timeline: {timeline}")
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    main()
