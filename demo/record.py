"""Records the demo from the real running site (PROGRESS D.4).

Starts the demo site from a clean reset, opens a 1920x1080 "stage" page that frames the real physician and patient
pages side by side, and drives the full flow plus a red-flag stop. A simulated patient (evals/simulator.py) types the
answers. Writes the raw video, the captured AI speech and a timeline for demo/assemble.py.

    uv run --group demo python -m demo.record            # record
    uv run --group demo python -m demo.record --no-video # rehearsal: same run, no video
"""

import argparse
import base64
import json
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from playwright.sync_api import Frame, Locator, Page, sync_playwright

from demo import captions as C
from demo.config import DEMO_URL, FULL_FLOW_SCENARIO, OUTPUT_DIR, PHYSICIAN, RED_FLAG_SCENARIO, demo_settings
from demo.seed import backdate_readings, lab_report_png, token_for
from evals.scenario import dob_for, load_all
from evals.simulator import SimulatedPatient
from previsit.config import PROJECT_ROOT
from previsit.llm import OpenAILLM

STAGE_URL = f"{DEMO_URL}/__demo_stage"
TYPE_DELAY_MS = 28
FF_TYPE_DELAY_MS = 6
FF_AFTER_ANSWERS = 4  # real-time interview answers shown before fast-forwarding
FF_SPEED = 4
MAX_TURNS = 40
MIN_CUT_S = 1.2  # waits shorter than this stay in the video
KEEP_HEAD_S, KEEP_TAIL_S = 0.5, 0.3  # what remains of each shortened pause


class Recorder:
    def __init__(self, page: Page, out: Path) -> None:
        self.page = page
        self.out = out
        self.t0 = time.monotonic()
        self.cuts: list[tuple[float, float]] = []
        self.audio: list[dict] = []
        self.marks: list[dict] = []
        self.fast_forward: list[list[float]] = []
        self.type_delay = TYPE_DELAY_MS

    # ----- timeline ---------------------------------------------------------------------------------------------

    def now(self) -> float:
        return time.monotonic() - self.t0

    def caption(self, cap: tuple[str, str, str]) -> None:
        self.page.evaluate("([s, t, r]) => stage.caption(s, t, r)", list(cap))
        self.marks.append({"t": self.now(), "scene": cap[0], "text": cap[1]})
        print(f"[{self.now():6.1f}s] {cap[0]}: {cap[1][:70]}")

    def hold(self, seconds: float) -> None:
        self.page.wait_for_timeout(int(seconds * 1000))

    def cut_since(self, start: float) -> None:
        end = self.now()
        if end - start >= MIN_CUT_S:
            self.cuts.append((start + KEEP_HEAD_S, end - KEEP_TAIL_S))

    # ----- frames and pointer -----------------------------------------------------------------------------------

    def frame(self, name: str) -> Frame:
        return self.page.frame(name=name)

    def loc(self, name: str, selector: str) -> Locator:
        return self.page.frame_locator(f"#{name}").locator(selector).first

    def goto(self, name: str, path: str) -> None:
        start = self.now()
        self.frame(name).goto(path if path.startswith("http") else f"{DEMO_URL}{path}", wait_until="load")
        self.cut_since(start)

    def point(self, target: Locator) -> None:
        target.scroll_into_view_if_needed()
        box = target.bounding_box()
        if box is None:
            raise RuntimeError("element has no box to point at")
        self.page.evaluate("([x, y]) => stage.cursor(x, y, false)", [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2])
        self.hold(0.55)

    def click(self, target: Locator, pause: float = 0.8) -> None:
        self.point(target)
        box = target.bounding_box()
        self.page.evaluate("([x, y]) => stage.cursor(x, y, true)", [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2])
        start = self.now()
        target.click()
        self.cut_since(start)
        self.hold(pause)

    def type(self, target: Locator, text: str) -> None:
        self.click(target, pause=0.2)
        target.press_sequentially(text, delay=self.type_delay)
        self.hold(0.4)

    def reveal(self, name: str, selector: str, hold: float = 2.5) -> None:
        self.loc(name, selector).evaluate("el => el.scrollIntoView({behavior: 'smooth', block: 'start'})")
        self.hold(hold)

    # ----- AI speech --------------------------------------------------------------------------------------------

    def set_fast_forward(self, on: bool) -> None:
        self.page.evaluate("on => stage.ff(on)", on)
        if on:
            self.fast_forward.append([self.now(), self.now()])
            self.type_delay = FF_TYPE_DELAY_MS
        else:
            self.fast_forward[-1][1] = self.now()
            self.type_delay = TYPE_DELAY_MS

    @property
    def fast_forwarding(self) -> bool:
        return bool(self.fast_forward) and self.fast_forward[-1][0] == self.fast_forward[-1][1]

    def keep_audio(self, data: dict) -> float:
        if not data.get("audio") or self.fast_forwarding:
            return 0.0
        path = self.out / "audio" / f"{len(self.audio):03d}.mp3"
        path.write_bytes(base64.b64decode(data["audio"]))
        duration = media_duration(path)
        self.audio.append({"file": str(path), "t": self.now(), "duration": duration})
        return duration

    def save(self, video: Path | None, meta: dict) -> Path:
        timeline = {"video": str(video) if video else None, "duration": self.now(), "cuts": self.cuts,
                    "fast_forward": self.fast_forward, "ff_speed": FF_SPEED,
                    "audio": self.audio, "marks": self.marks, **meta}
        path = self.out / "timeline.json"
        path.write_text(json.dumps(timeline, indent=2))
        return path


def media_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


# ----- intake driver ------------------------------------------------------------------------------------------------

STATE_CAPTIONS = {
    "consent": C.CONSENT, "identity": C.IDENTITY, "interview": C.INTERVIEW, "readback": C.READBACK,
    "complete": C.ADVICE, "escalated": C.RED_STOP,
}


def run_intake(rec: Recorder, sim: SimulatedPatient, red_case: bool, fast_forward: bool = False) -> dict:
    """Starts the conversation, then lets the simulated patient type until the intake ends."""
    with rec.page.expect_response(lambda r: "/intake/start" in r.url, timeout=120_000) as info:
        start = rec.now()
        rec.click(rec.loc("pt", "a.button.big"), pause=0)
    data = info.value.json()
    rec.cut_since(start)
    rec.loc("pt", ".bubble.agent").wait_for()
    answers = 0
    for turn in range(MAX_TURNS):
        in_interview = data["state"] == "interview"
        if fast_forward and in_interview and answers >= FF_AFTER_ANSWERS and not rec.fast_forwarding:
            rec.set_fast_forward(True)
        if rec.fast_forwarding and not in_interview:
            rec.set_fast_forward(False)
        state_cap = STATE_CAPTIONS.get(data["state"], C.INTERVIEW)
        if red_case and in_interview:
            state_cap = C.RED_INTERVIEW
        if rec.fast_forwarding:
            state_cap = C.FAST_FORWARD
        rec.caption(state_cap)
        speaking = rec.keep_audio(data)
        began = time.monotonic()
        if data.get("ended"):
            if rec.fast_forwarding:
                rec.set_fast_forward(False)
            rec.hold(max(speaking, 3.0) + 1.5)
            return data
        thinking = rec.now()
        answer = sim.reply(data["agent_text"]).utterance  # thought up while the assistant is still speaking
        if not speaking:
            rec.cut_since(thinking)  # nothing on screen changes while the simulated patient thinks
        rec.hold(max(0.0, speaking - (time.monotonic() - began)) + 0.6)
        box = rec.loc("pt", "#text")
        rec.type(box, answer)
        answers += 1 if in_interview else 0
        with rec.page.expect_response(lambda r: "/intake/turn" in r.url, timeout=180_000) as info:
            start = rec.now()
            box.press("Enter")
        data = info.value.json()
        rec.cut_since(start)
        rec.page.wait_for_timeout(300)
    raise RuntimeError(f"intake did not end within {MAX_TURNS} turns")


# ----- scenes -------------------------------------------------------------------------------------------------------

def scene_booking(rec: Recorder, scenario, dob: date) -> tuple[int, str]:
    rec.goto("doc", "/dashboard")
    rec.caption(C.BOOKING)
    rec.hold(2.0)
    rec.click(rec.loc("doc", "a[href='/appointments/new']"))
    rec.type(rec.loc("doc", "#name"), scenario.patient_name)
    rec.loc("doc", "#dob").fill(dob.isoformat())
    rec.loc("doc", "#sex").select_option(scenario.sex)
    rec.type(rec.loc("doc", "#phone"), "555-0142")
    when = (date.today() + timedelta(days=1)).isoformat() + "T09:30"
    rec.loc("doc", "#scheduled_at").fill(when)
    rec.type(rec.loc("doc", "#reason"), "Fever and cough")
    rec.hold(0.8)
    rec.click(rec.loc("doc", "button:has-text('Create and get link')"), pause=2.5)
    link = rec.loc("doc", ".banner.ok a[href*='/p/']").get_attribute("href")
    appt_id = int(re.search(r"/patients/(\d+)", rec.loc("doc", ".banner.ok a[href*='/patients/']").get_attribute("href")).group(1))
    rec.point(rec.loc("doc", ".banner.ok a[href*='/p/']"))
    rec.hold(1.5)
    rec.goto("pt", link)
    rec.caption(C.OPEN_LINK)
    rec.hold(3.5)
    rec.goto("doc", "/dashboard")
    return appt_id, link


def scene_sheet(rec: Recorder, appt_id: int) -> None:
    rec.goto("doc", "/dashboard")
    rec.caption(C.DASHBOARD)
    rec.hold(3.0)
    rec.click(rec.loc("doc", f"a[href='/patients/{appt_id}']"))
    rec.caption(C.SHEET)
    rec.hold(3.5)
    rec.reveal("doc", "ol.cc", hold=3.5)
    rec.caption(C.CITATION)
    cite = rec.loc("doc", "ul.stmts a.cite")
    rec.click(cite, pause=3.5)
    rec.caption(C.SCREEN)
    rec.reveal("doc", "h3:has-text('Danger symptoms'), h3:has-text('Red-flag screen')", hold=4.0)


def scene_approval(rec: Recorder, appt_id: int, link: str) -> None:
    rec.goto("doc", f"/patients/{appt_id}")
    rec.reveal("doc", "#tests", hold=0.5)
    rec.caption(C.SUGGESTED)
    rec.point(rec.loc("doc", "#tests .rec .why"))
    rec.hold(4.0)
    rec.goto("pt", link)
    rec.caption(C.PATIENT_NOTHING)
    rec.hold(3.0)
    rec.reveal("pt", ".card h2", hold=3.0)
    rec.click(rec.loc("doc", "#tests button[value='approve']"), pause=1.0)
    rec.reveal("doc", "#tests", hold=0.5)
    rec.caption(C.APPROVED)
    rec.hold(3.0)
    rec.goto("pt", link)
    rec.hold(2.5)
    rec.click(rec.loc("doc", "#tests button:has-text('Send')"), pause=1.0)
    rec.reveal("doc", "#tests", hold=1.0)
    rec.goto("pt", link)
    rec.caption(C.SENT)
    rec.reveal("pt", "h2:has-text('Tests your doctor')", hold=5.0)


def scene_temperatures(rec: Recorder, appt_id: int, link: str) -> None:
    backdate_readings(appt_id, [(7.0, 38.9), (4.0, 38.6)])
    rec.goto("pt", link)
    rec.reveal("pt", "h2:has-text('Log your')", hold=1.0)
    rec.caption(C.TEMPS)
    rec.type(rec.loc("pt", "#value"), "38.2")
    rec.type(rec.loc("pt", "#note"), "Feeling a little better this morning")
    rec.click(rec.loc("pt", "button:has-text('Save reading')"), pause=2.5)
    rec.goto("doc", f"/patients/{appt_id}")
    rec.caption(C.TEMPS_DOCTOR)
    rec.point(rec.loc("doc", "svg.chart"))
    rec.hold(5.0)


def scene_result(rec: Recorder, appt_id: int, link: str, report: Path) -> None:
    rec.goto("pt", link)
    rec.reveal("pt", "h2:has-text('Upload a test report')", hold=1.0)
    rec.caption(C.UPLOAD)
    rec.point(rec.loc("pt", "input[type=file]"))
    rec.loc("pt", "input[type=file]").set_input_files(str(report))
    rec.hold(1.2)
    rec.click(rec.loc("pt", "button:has-text('Send to my doctor')"), pause=2.5)
    rec.goto("doc", f"/patients/{appt_id}")
    rec.caption(C.RESULT)
    rec.point(rec.loc("doc", ".banner"))
    rec.hold(2.5)
    href = rec.loc("doc", "a[href^='/results/']").get_attribute("href")
    rec.reveal("doc", "a[href^='/results/']", hold=1.0)
    rec.point(rec.loc("doc", "a[href^='/results/']"))
    rec.goto("doc", href)
    rec.hold(5.0)


def scene_red_flag(rec: Recorder, sim: SimulatedPatient, red_name: str) -> None:
    token = token_for(red_name)
    link = f"{DEMO_URL}/p/{token}"
    rec.goto("doc", "/dashboard")
    rec.goto("pt", link)
    rec.caption(C.RED_OPEN)
    rec.hold(3.0)
    run_intake(rec, sim, red_case=True)
    rec.goto("doc", "/dashboard")
    rec.caption(C.RED_STAFF)
    rec.point(rec.loc("doc", ".banner.danger"))
    rec.hold(3.5)
    rec.click(rec.loc("doc", ".banner.danger a"), pause=1.0)
    rec.hold(3.0)
    rec.reveal("doc", "#tests", hold=3.5)
    rec.goto("pt", link)
    rec.caption(C.RED_PATIENT)
    rec.hold(5.0)


# ----- run ----------------------------------------------------------------------------------------------------------

def latest_eval() -> dict:
    reports = sorted((PROJECT_ROOT / "evals" / "reports").glob("*/summary.md"))
    if not reports:
        return {"n_scenarios": "?", "recall": "not run", "accuracy": "not run", "fabricated": "not run", "report": None}
    text = reports[-1].read_text()

    def metric(name: str) -> str:
        match = re.search(rf"\| {re.escape(name)} \| ([^|]+) \|", text)
        return match.group(1).strip() if match else "?"

    scenarios = len(set(re.findall(r"^\| ([A-Z]+-\d+) \|", text, re.M)))
    return {"n_scenarios": scenarios, "recall": metric("Red-flag recall").split(" (")[0],
            "accuracy": metric("Key-fact accuracy"), "fabricated": metric("Fabricated facts"), "report": str(reports[-1])}


def wait_for_port(port: int, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.3)
    raise RuntimeError(f"demo server did not start on port {port}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-video", action="store_true", help="rehearsal run without recording")
    parser.add_argument("--full", default=FULL_FLOW_SCENARIO, help="scenario for the full-flow patient")
    parser.add_argument("--red-flag", default=RED_FLAG_SCENARIO, help="scenario for the red-flag patient")
    args = parser.parse_args()

    settings = demo_settings()
    out = OUTPUT_DIR / time.strftime("%Y%m%dT%H%M%S")
    (out / "audio").mkdir(parents=True)
    full, red = load_all([args.full])[0], load_all([args.red_flag])[0]
    dob = dob_for(full.age, date.today())
    report = out / "synthetic_cbc_report.png"
    lab_report_png(report, full.patient_name, dob)
    llm = OpenAILLM(settings)
    evals = latest_eval()

    server = subprocess.Popen([sys.executable, "-m", "demo.serve"], cwd=PROJECT_ROOT)
    try:
        wait_for_port(8010)
        stage_html = (Path(__file__).parent / "stage.html").read_text()
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                device_scale_factor=1,
                http_credentials={"username": settings.physician_username,
                                  "password": settings.physician_password.get_secret_value()},
                **({} if args.no_video else {"record_video_dir": str(out / "raw"),
                                             "record_video_size": {"width": 1920, "height": 1080}}),
            )
            context.route(STAGE_URL, lambda route: route.fulfill(status=200, content_type="text/html", body=stage_html))
            page = context.new_page()
            rec = Recorder(page, out)
            page.goto(STAGE_URL)
            page.evaluate("t => stage.note(t)", C.PAUSES_NOTE)
            page.evaluate("([t, l]) => stage.card(t, l, '')", [C.INTRO_TITLE, list(C.INTRO_LINES)])
            rec.marks.append({"t": rec.now(), "scene": "Intro", "text": C.INTRO_TITLE})
            rec.hold(6.0)
            page.evaluate("() => stage.card(null)")

            appt_id, link = scene_booking(rec, full, dob)
            run_intake(rec, SimulatedPatient(llm, full, dob), red_case=False, fast_forward=True)
            scene_sheet(rec, appt_id)
            scene_approval(rec, appt_id, link)
            scene_temperatures(rec, appt_id, link)
            scene_result(rec, appt_id, link, report)
            scene_red_flag(rec, SimulatedPatient(llm, red, dob_for(red.age, date.today())), red.patient_name)

            limits = [line.format(**evals) for line in C.LIMITS_LINES]
            page.evaluate("([t, l, f]) => stage.card(t, l, f)",
                          [C.LIMITS_TITLE, limits, f"{PHYSICIAN} and all patients are fictional. Recorded {date.today().isoformat()}."])
            rec.marks.append({"t": rec.now(), "scene": "Limits", "text": C.LIMITS_TITLE})
            rec.hold(12.0)
            video_path = page.video.path() if page.video else None
            context.close()
            browser.close()
        raw = None
        if video_path:
            raw = out / "raw.webm"
            shutil.move(video_path, raw)
        timeline = rec.save(raw, {"eval": evals, "full_scenario": args.full, "red_flag_scenario": args.red_flag})
        print(f"Done. Timeline: {timeline}")
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    main()
