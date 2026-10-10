"""Demo script check (PROGRESS D.3): run each demo patient N times against the real engine and confirm every
scene the video needs actually happens.

    uv run python -m evals.demo_check --runs 3

Exit code 0 only if every run of every demo script reaches every scene.
"""
from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.run import REPORT_DIR, _live_llms, run_scenario
from evals.scenario import load_all
from evals.scoring import ESCALATED, Event, red_flag_outcome

logger = logging.getLogger("evals.demo")

FULL_FLOW_ID = "DEMO-001"
RED_FLAG_ID = "DEMO-002"
FULL_FLOW_STATES = ("consent", "identity", "interview", "readback", "complete")
MIN_HISTORY_QUESTIONS = 5
CBC_MIN_FEVER_DAYS = 3


@dataclass(frozen=True)
class Snapshot:
    """What the demo site would show after the intake, read back from its database."""
    sheet: dict[str, Any] | None
    findings: dict[str, Any]
    recs: list[tuple[str, str]]  # (name, status)
    message_kinds: list[str]  # patient messages sent
    red_flags: list[str]
    staff_alerts: int  # emergency alerts
    final_agent_text: str  # what the agent said on reaching the final state


def check_full_flow(events: list[Event], snap: Snapshot, emergency_number: str) -> list[str]:
    problems: list[str] = []
    order = _first_seen([e.state for e in events if e.speaker == "agent"])
    missing = [s for s in FULL_FLOW_STATES if s not in order]
    if missing:
        problems.append(f"never reached: {', '.join(missing)}")
    elif [s for s in order if s in FULL_FLOW_STATES] != list(FULL_FLOW_STATES):
        problems.append(f"states out of order: {order}")
    questions = sum(1 for e in events if e.speaker == "agent" and e.state == "interview")
    if questions < MIN_HISTORY_QUESTIONS:
        problems.append(f"only {questions} history questions (need {MIN_HISTORY_QUESTIONS}+ to show adaptive HOPI)")
    if emergency_number not in snap.final_agent_text:
        problems.append("closing advice has no emergency safety-netting")
    if "general_recs" not in snap.message_kinds:
        problems.append("no general advice message for the patient page")
    if "medical" in snap.message_kinds:
        problems.append("a medical message reached the patient before the demo's approval scene")
    if snap.red_flags:
        problems.append(f"unexpected red flag {snap.red_flags}")
    problems += _sheet_problems(snap)
    if not any("cbc" in name.lower() and status == "suggested" for name, status in snap.recs):
        problems.append(f"no suggested CBC for the physician (recs: {snap.recs})")
    return problems


def _sheet_problems(snap: Snapshot) -> list[str]:
    sheet = snap.sheet
    if sheet is None:
        return ["no history sheet saved"]
    problems = []
    if sheet.get("partial"):
        problems.append("sheet is marked partial")
    if len(sheet.get("chief_complaints") or []) < 2:
        problems.append("fewer than 2 chief complaints (the chronological list scene needs several)")
    if not sheet.get("could_not_answer"):
        problems.append("no 'could not answer' item")
    if not sheet.get("red_flag_screen"):
        problems.append("no red-flag screen on the sheet")
    days = snap.findings.get("fever_duration_days")
    if not isinstance(days, (int, float)) or days < CBC_MIN_FEVER_DAYS:
        problems.append(f"fever_duration_days={days!r}; the CBC rule needs >= {CBC_MIN_FEVER_DAYS}")
    return problems


def check_red_flag(events: list[Event], snap: Snapshot, emergency_number: str, rf_id: str = "RF-07") -> list[str]:
    problems: list[str] = []
    if not any(e.state == ESCALATED for e in events):
        problems.append("intake never escalated")
    if rf_id not in snap.red_flags:
        problems.append(f"{rf_id} not recorded (got {snap.red_flags})")
    if snap.staff_alerts < 1:
        problems.append("no staff alert")
    if snap.recs:
        problems.append(f"tests were suggested after escalation: {snap.recs}")
    if "general_recs" in snap.message_kinds:
        problems.append("self-care advice was sent after escalation")
    if emergency_number not in snap.final_agent_text:
        problems.append("escalation message has no emergency number")
    return problems


def _first_seen(states: list[str]) -> list[str]:
    return list(dict.fromkeys(states))


def snapshot(db_url: str, events: list[Event]) -> Snapshot:
    from sqlmodel import select

    from previsit.db import make_engine, session_scope
    from previsit.models import (HistorySheetRecord, MedicalRecommendation, PatientMessage, RedFlagEvent,
                                 StaffAlert)

    final_state = next((e.state for e in reversed(events) if e.speaker == "agent"), "")
    final_text = next((e.text for e in events if e.speaker == "agent" and e.state == final_state), "")
    with session_scope(make_engine(db_url)) as session:
        record = session.exec(select(HistorySheetRecord).order_by(HistorySheetRecord.version.desc())).first()
        sheet = dict(record.data) if record else None
        return Snapshot(
            sheet=sheet,
            findings=(sheet or {}).get("findings") or {},
            recs=[(r.name, str(r.status)) for r in session.exec(select(MedicalRecommendation)).all()],
            message_kinds=[str(m.kind) for m in session.exec(select(PatientMessage)).all()],
            red_flags=sorted({rf for e in session.exec(select(RedFlagEvent)).all() for rf in e.rf_ids}),
            staff_alerts=sum(1 for a in session.exec(select(StaffAlert)).all() if a.severity == "emergency"),
            final_agent_text=final_text,
        )


def run_checks(runs: int, workers: int) -> tuple[list[dict], bool]:
    from previsit.config import Settings

    settings = Settings()
    system_llm, sim_llm = _live_llms(settings)
    scenarios = {s.id: s for s in load_all(ids=[FULL_FLOW_ID, RED_FLAG_ID])}
    tmp = Path(tempfile.mkdtemp(prefix="previsit-demo-"))
    jobs = [(sid, r) for sid in (FULL_FLOW_ID, RED_FLAG_ID) for r in range(1, runs + 1)]

    def job(item):
        sid, run = item
        scenario = scenarios[sid]
        db_url = f"sqlite:///{tmp / f'{sid}-{run}.db'}"
        result, events = run_scenario(scenario, system_llm, sim_llm, sim_llm, settings, db_url, run=run)
        if result.final_state == "error":
            return {"id": sid, "run": run, "problems": [result.error], "turns": len(events)}
        snap = snapshot(db_url, events)
        if sid == FULL_FLOW_ID:
            problems = check_full_flow(events, snap, settings.emergency_number)
        else:
            problems = check_red_flag(events, snap, settings.emergency_number)
            timing = red_flag_outcome(scenario.expected_outcome, scenario.red_flags, scenario.escalate_after, events,
                                      tuple(snap.red_flags))
            if not timing.in_time:
                problems.append(f"{timing.agent_turns_after_disclosure} agent turns after the stiff neck (max 1)")
        patient_turns = sum(1 for e in events if e.speaker == "patient")
        logger.info("%s run %s: %s (%s patient turns)", sid, run, "OK" if not problems else problems, patient_turns)
        return {"id": sid, "run": run, "problems": problems, "turns": patient_turns}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(job, jobs))
    return rows, all(not r["problems"] for r in rows)


def write_report(rows: list[dict], passed: bool) -> Path:
    target = REPORT_DIR / f"demo-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    target.mkdir(parents=True, exist_ok=True)
    lines = [f"# Demo script check (D.3): {'PASS' if passed else 'FAIL'}", "",
             "| Script | Run | Patient turns | Result |", "|---|---|---|---|"]
    lines += [f"| {r['id']} | {r['run']} | {r['turns']} | {'all scenes' if not r['problems'] else '; '.join(r['problems'])} |"
              for r in rows]
    (target / "demo_check.md").write_text("\n".join(lines) + "\n")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rows, passed = run_checks(args.runs, args.workers)
    target = write_report(rows, passed)
    print(f"{'PASS' if passed else 'FAIL'}: report in {target / 'demo_check.md'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
