"""Eval runner (PROGRESS 1.10): simulated patients vs IntakeEngine, scored against the Phase 1 exit gate.

    uv run python -m evals.run                      # all phase-1 scenarios, real OpenAI calls (needs .env)
    uv run python -m evals.run -s FEV-003 -s FEV-010 --repeat 3

Exit code 0 only if every gate passes: accuracy >= 90%, 0 fabricated facts, 100% red-flag recall, no errors.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlmodel import select

from evals import judge
from evals.scenario import Scenario, dob_for, load_all
from evals.scoring import ESCALATED, Event, ScenarioResult, Summary, aggregate, red_flag_outcome
from evals.simulator import SimulatedPatient

logger = logging.getLogger("evals")

MAX_PATIENT_TURNS = 60
POST_END_TURNS = 2  # let the caller react after the call ends (hesitation, refusal) for human review
REPORT_DIR = Path(__file__).resolve().parent / "reports"


# ---------- one scenario ----------

def run_scenario(scenario: Scenario, system_llm, sim_llm, judge_llm, settings, db_url: str,
                 today: date | None = None, run: int = 1) -> tuple[ScenarioResult, list[Event]]:
    events: list[Event] = []
    try:
        return _run(scenario, system_llm, sim_llm, judge_llm, settings, db_url, today or date.today(), run, events)
    except Exception as exc:  # one broken scenario must not stop the set; it fails the gate instead
        logger.exception("Scenario %s run %s errored", scenario.id, run)
        result = ScenarioResult(scenario_id=scenario.id, run=run, expected_outcome=scenario.expected_outcome,
                                final_state="error", red_flag=None, facts=None, fabrication=None,
                                error=f"{exc.__class__.__name__}: {exc}", turns=len(events))
        return result, events


def _run(scenario, system_llm, sim_llm, judge_llm, settings, db_url, today, run, events):
    from previsit.db import init_db, make_engine, session_scope
    from previsit.intake.engine import IntakeEngine
    from previsit.models import Appointment, Intake, Patient, RedFlagEvent

    db = make_engine(db_url)
    init_db(db)
    settings = settings.model_copy(update={"database_url": db_url})
    dob = dob_for(scenario.age, today)
    engine = IntakeEngine(system_llm, settings)
    patient_sim = SimulatedPatient(sim_llm, scenario, dob)

    with session_scope(db) as session:
        patient = _save(session, Patient(name=scenario.patient_name, dob=dob, sex=scenario.sex))
        appointment = _save(session, Appointment(
            patient_id=patient.id, physician_name="Dr. Eval", token=f"eval-{scenario.id}-{run}",
            scheduled_at=datetime.now(UTC) + timedelta(days=1), reason="fever"))
        intake = _save(session, Intake(appointment_id=appointment.id))

        reply = engine.start(session, intake)
        events.append(Event("agent", reply.text, str(reply.state)))
        _converse(engine, session, intake, patient_sim, reply, events)

        fired = tuple(sorted({rf for e in session.exec(select(RedFlagEvent)).all() for rf in e.rf_ids}))
        sheet, transcript_text = _sheet_and_transcript(session, intake)
        final_state = str(intake.state)

    rf = red_flag_outcome(scenario.expected_outcome, scenario.red_flags, scenario.escalate_after, events, fired)
    if sheet is None:
        facts, traps_hit, unsupported = judge.FactScore(len(scenario.key_facts), 0, scenario.key_facts), (), ()
    else:
        facts, traps_hit = judge.judge_sheet(judge_llm, render_sheet(sheet), transcript_text, scenario.key_facts,
                                             scenario.fabrication_traps,
                                             only_mentioned=scenario.expected_outcome == "escalate")
        record = (f"Patient: {scenario.patient_name}, date of birth {dob.isoformat()}, age {scenario.age}, "
                  f"sex {scenario.sex}. Speaking: {scenario.informant}.")
        unsupported = judge.judge_support(judge_llm, transcript_text, statement_lines(sheet), record=record)
    result = ScenarioResult(scenario_id=scenario.id, run=run, expected_outcome=scenario.expected_outcome,
                            final_state=final_state, red_flag=rf, facts=facts,
                            fabrication=judge.fabrication(traps_hit, unsupported),
                            error=None if sheet is not None else "no history sheet was saved",
                            turns=len(events))
    return result, events


def _save(session, row):
    session.add(row)
    session.flush()
    session.refresh(row)
    return row


def _converse(engine, session, intake, patient_sim, reply, events):
    patient_turns, after_end = 0, 0
    while patient_turns < MAX_PATIENT_TURNS and after_end <= POST_END_TURNS:
        if reply.ended:
            after_end += 1
            if after_end > POST_END_TURNS:
                break
        said = patient_sim.reply(reply.text)
        events.append(Event("patient", said.utterance, str(reply.state), tuple(said.disclosed)))
        patient_turns += 1
        if said.hang_up:
            break
        reply = engine.handle_patient_turn(session, intake, said.utterance)
        events.append(Event("agent", reply.text, str(reply.state)))
    if patient_turns >= MAX_PATIENT_TURNS:
        logger.warning("Turn limit reached")


def _sheet_and_transcript(session, intake):
    from previsit.models import HistorySheetRecord, Turn
    from previsit.sheet.schema import HistorySheet

    record = session.exec(select(HistorySheetRecord).where(HistorySheetRecord.intake_id == intake.id)
                          .order_by(HistorySheetRecord.version.desc())).first()
    turns = session.exec(select(Turn).where(Turn.intake_id == intake.id).order_by(Turn.seq)).all()
    transcript = "\n".join(f"[{t.seq}] {str(t.speaker).upper()}: {t.text}" for t in turns)
    return (HistorySheet.model_validate(record.data) if record else None), transcript


# ---------- sheet rendering for the judges ----------

def render_sheet(sheet) -> str:
    from previsit.sheet.schema import SECTIONS

    lines = ["Chief complaints:"]
    lines += [f"  {c.onset_order}. {c.complaint} ({c.duration})" for c in sheet.chief_complaints]
    for section in SECTIONS:
        statements = sheet.section(section.key)
        if statements:
            lines.append(f"{section.title}:")
            lines += [f"  - {s.text}" for s in statements]
    return "\n".join(lines)


def statement_lines(sheet) -> list[str]:
    from previsit.sheet.schema import SECTIONS

    lines = [f"[chief complaint] {c.complaint} (duration: {c.duration}) (cites turns {list(c.source_turn_ids)})"
             for c in sheet.chief_complaints]
    for section in SECTIONS:
        lines += [f"[{section.title}] {s.text} (cites turns {list(s.source_turn_ids)})"
                  for s in sheet.section(section.key)]
    return lines


# ---------- the whole set ----------

def run_all(scenarios: list[Scenario], repeat: int, workers: int, out_dir: Path) -> Summary:
    from previsit.config import Settings

    settings = Settings()
    system_llm, eval_llm = _live_llms(settings)
    jobs = [(s, r) for s in scenarios for r in range(1, repeat + 1)]
    tmp = Path(tempfile.mkdtemp(prefix="previsit-eval-"))

    def job(item):
        scenario, run = item
        db_url = f"sqlite:///{tmp / f'{scenario.id}-{run}.db'}"
        result, events = run_scenario(scenario, system_llm, eval_llm, eval_llm, settings, db_url, run=run)
        logger.info("%s run %s: %s", scenario.id, run, _one_line(result))
        return result, events

    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(job, jobs))
    summary = aggregate([r for r, _ in outcomes])
    write_report(out_dir, outcomes, summary)
    return summary


def _live_llms(settings):
    from previsit.llm import OpenAILLM

    class EvalLLM(OpenAILLM):
        """Judges use the stronger extraction model; the simulated patient uses the interview model."""

        def _model_for(self, task: str) -> str:
            return self._settings.extraction_model if task.startswith("judge") else self._settings.interview_model

    return OpenAILLM(settings), EvalLLM(settings)


def _one_line(r: ScenarioResult) -> str:
    if r.error and r.facts is None:
        return f"ERROR {r.error}"
    rf = "PASS" if r.red_flag and r.red_flag.passed else "FAIL"
    return (f"state={r.final_state} red-flag={rf} facts={r.facts.correct}/{r.facts.total} "
            f"fabricated={r.fabrication.count}" + (f" ({r.error})" if r.error else ""))


def write_report(out_dir: Path, outcomes, summary: Summary) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = out_dir / stamp
    target.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": {**asdict(summary), "gates_passed": summary.gates_passed},
        "runs": [{**asdict(r), "transcript": [asdict(e) for e in events]} for r, events in outcomes],
    }
    (target / "report.json").write_text(json.dumps(payload, indent=2, default=str))
    (target / "summary.md").write_text(summary_markdown(outcomes, summary))
    return target


def summary_markdown(outcomes, summary: Summary) -> str:
    gate = "PASS" if summary.gates_passed else "FAIL"
    lines = [
        f"# Eval run: {gate}", "",
        "| Metric | Value | Gate |", "|---|---|---|",
        f"| Key-fact accuracy | {summary.accuracy:.1%} | ≥ 90% |",
        f"| Fabricated facts | {summary.fabricated} | 0 |",
        f"| Red-flag recall | {summary.recall:.0%} ({summary.escalate_runs} runs) | 100% |",
        f"| Errors | {summary.errors} | 0 |",
        f"| False positives | {summary.false_positives} | tracked |",
        f"| RF label mismatches | {summary.rf_label_mismatches} | tracked |", "",
        "| Scenario | Run | Expected | Final state | Red flag | Facts | Fabricated | Notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r, _ in outcomes:
        rf = "–" if r.red_flag is None else ("pass" if r.red_flag.passed else "**FAIL**")
        facts = "–" if r.facts is None else f"{r.facts.correct}/{r.facts.total}"
        fab = "–" if r.fabrication is None else str(r.fabrication.count)
        notes = r.error or ""
        if r.fabrication and r.fabrication.count:
            notes += " fabricated: " + "; ".join(r.fabrication.traps_hit + r.fabrication.unsupported)
        if r.facts and r.facts.missed:
            notes += " missed: " + "; ".join(r.facts.missed)
        lines.append(f"| {r.scenario_id} | {r.run} | {r.expected_outcome} | {r.final_state} | {rf} | {facts} | {fab} "
                     f"| {notes.strip()} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-s", "--scenario", action="append", help="scenario ID; repeat to pick several")
    parser.add_argument("--phase", type=int, default=1, help="highest roadmap phase built so far")
    parser.add_argument("--repeat", type=int, default=1, help="runs per scenario (red-flag recall must hold on all)")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out", type=Path, default=REPORT_DIR)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    scenarios = load_all(ids=args.scenario, max_phase=args.phase)
    if not scenarios:
        print("No scenarios matched.", file=sys.stderr)
        return 2
    summary = run_all(scenarios, args.repeat, args.workers, args.out)
    print(f"accuracy={summary.accuracy:.1%} fabricated={summary.fabricated} recall={summary.recall:.0%} "
          f"errors={summary.errors} -> {'PASS' if summary.gates_passed else 'FAIL'}")
    return 0 if summary.gates_passed else 1


if __name__ == "__main__":
    sys.exit(main())
