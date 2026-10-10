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
from evals.screening import QUESTION_LIMIT, SymptomScreening, load_lists, screen
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
                                error=f"{exc.__class__.__name__}: {exc}", turns=len(events),
                                screening=screening_for(scenario, None))
        return result, events


def screening_for(scenario: Scenario, events: list[Event] | None) -> tuple[SymptomScreening, ...]:
    """P-008 gate: one result per symptom the scenario declares. A run that errored screens nothing, so it fails."""
    if events is None:
        return tuple(SymptomScreening.not_run(symptom) for symptom in scenario.screening)
    lists = load_lists()
    return tuple(screen(events, lists[symptom]) for symptom in scenario.screening)


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
            scheduled_at=datetime.now() + timedelta(days=1), reason="fever"))  # clinic-local, naive
        intake = _save(session, Intake(appointment_id=appointment.id))

        reply = engine.start(session, intake)
        events.append(Event("agent", reply.text, str(reply.state)))
        _converse(engine, session, intake, patient_sim, reply, events)

        fired = tuple(sorted({rf for e in session.exec(select(RedFlagEvent)).all() for rf in e.rf_ids}))
        sheet, transcript_text = _sheet_and_transcript(session, intake)
        final_state = str(intake.state)
        informant = intake.informant

    header = judge_header(sheet, fallback=record_header(scenario.patient_name, dob, scenario.sex, informant, today))
    rf = red_flag_outcome(scenario.expected_outcome, scenario.red_flags, scenario.escalate_after, events, fired)
    if sheet is None:
        facts, traps_hit, unsupported = judge.FactScore(len(scenario.key_facts), 0, scenario.key_facts), (), ()
    else:
        facts, traps_hit = judge.judge_sheet(judge_llm, f"{header}\n{render_sheet(sheet)}", transcript_text, scenario.key_facts,
                                             scenario.fabrication_traps,
                                             only_mentioned=scenario.expected_outcome == "escalate")
        unsupported = judge.judge_support(judge_llm, transcript_text, statement_lines(sheet), record=header)
    result = ScenarioResult(scenario_id=scenario.id, run=run, expected_outcome=scenario.expected_outcome,
                            final_state=final_state, red_flag=rf, facts=facts,
                            fabrication=judge.fabrication(traps_hit, unsupported),
                            error=None if sheet is not None else "no history sheet was saved",
                            turns=len(events), screening=screening_for(scenario, events))
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

def judge_header(sheet, fallback: str) -> str:
    """Demographics as the physician sees them: the sheet's record block (clinic record + identity step)."""
    record = getattr(sheet, "record", None) or {}
    if not record:
        return fallback
    return "Record: " + ", ".join(f"{key}: {value}" for key, value in record.items())


def record_header(name: str, dob: date, sex: str, informant: str, today: date) -> str:
    """The patient line the physician page renders from the record (web/templates/_sheet.html)."""
    from previsit.safety.context import PatientContext

    ctx = PatientContext(name=name, dob=dob, sex=sex, on_date=today, informant=informant)
    speaker = "Self" if not ctx.is_caregiver_call else informant.capitalize()
    return f"Patient: {name}, {ctx.age_text}, {sex}, DOB {dob.isoformat()}\nInformant: {speaker}"


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

def run_all(scenarios: list[Scenario], repeat: int, workers: int, out_dir: Path,
            overrides: list[str] | None = None) -> Summary:
    from previsit.config import Settings

    settings = apply_overrides(Settings(), overrides or [])
    logger.info("App models: interview=%s safety=%s extraction=%s", settings.interview_model, settings.safety_model,
                settings.extraction_model)
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
    models = {"interview": settings.interview_model, "safety": settings.safety_model,
              "extraction": settings.extraction_model, "simulator": SIM_MODEL, "judge": JUDGE_MODEL}
    write_report(out_dir, outcomes, summary, models)
    return summary


# The simulated patient and the judges are the measuring instrument: they stay fixed while the app's models change.
SIM_MODEL = "gpt-5.4-mini"
JUDGE_MODEL = "gpt-5.4"


def eval_model_for(task: str) -> str:
    return JUDGE_MODEL if task.startswith("judge") else SIM_MODEL


def apply_overrides(settings, overrides: list[str]):
    """KEY=VALUE pairs (e.g. interview_model=gpt-5.4-nano) applied to the app's settings for this run only."""
    updates = {}
    for item in overrides or []:
        key, sep, value = item.partition("=")
        key = key.strip()
        if not sep or not key or key not in type(settings).model_fields:
            raise ValueError(f"bad --set {item!r}; expected SETTING=value with a known setting name")
        updates[key] = value.strip()
    return settings.model_copy(update=updates)


def _live_llms(settings):
    from previsit.llm import OpenAILLM

    class EvalLLM(OpenAILLM):
        def _model_for(self, task: str) -> str:
            return eval_model_for(task)

    return OpenAILLM(settings), EvalLLM(settings)


def _one_line(r: ScenarioResult) -> str:
    if r.error and r.facts is None:
        return f"ERROR {r.error}"
    rf = "PASS" if r.red_flag and r.red_flag.passed else "FAIL"
    screening = "" if not r.screening else " screening=" + ("PASS" if all(s.passed for s in r.screening) else "FAIL")
    return (f"state={r.final_state} red-flag={rf} facts={r.facts.correct}/{r.facts.total} "
            f"fabricated={r.fabrication.count}{screening}" + (f" ({r.error})" if r.error else ""))


def write_report(out_dir: Path, outcomes, summary: Summary, models: dict[str, str] | None = None) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = out_dir / stamp
    target.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": {**asdict(summary), "gates_passed": summary.gates_passed},
        "models": models or {},
        "runs": [{**asdict(r), "transcript": [asdict(e) for e in events]} for r, events in outcomes],
    }
    (target / "report.json").write_text(json.dumps(payload, indent=2, default=str))
    (target / "summary.md").write_text(summary_markdown(outcomes, summary, models))
    return target


def summary_markdown(outcomes, summary: Summary, models: dict[str, str] | None = None) -> str:
    gate = "PASS" if summary.gates_passed else "FAIL"
    lines = [
        f"# Eval run: {gate}", "",
        "Models: " + (", ".join(f"{k}={v}" for k, v in (models or {}).items()) or "not recorded"), "",
        "| Metric | Value | Gate |", "|---|---|---|",
        f"| Key-fact accuracy | {summary.accuracy:.1%} | ≥ 90% |",
        f"| Fabricated facts | {summary.fabricated} | 0 |",
        f"| Red-flag recall | {summary.recall:.0%} ({summary.escalate_runs} runs) | 100% |",
        f"| Symptom screening | {summary.screening_rate:.0%} ({summary.screening_runs} runs) "
        f"| 100% within {QUESTION_LIMIT} questions |",
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
        for s in r.screening:
            if not s.passed:
                notes += " " + _screening_note(s)
        lines.append(f"| {r.scenario_id} | {r.run} | {r.expected_outcome} | {r.final_state} | {rf} | {facts} | {fab} "
                     f"| {notes.strip()} |")
    return "\n".join(lines) + "\n"


def _screening_note(s: SymptomScreening) -> str:
    if not s.mentioned:
        return f"{s.symptom}: never mentioned (scenario or simulator problem)"
    parts = [f"late {i} (q{s.asked_at[i]})" for i in s.late] + [f"missing {i}" for i in s.missing]
    return f"{s.symptom}: " + ", ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-s", "--scenario", action="append", help="scenario ID; repeat to pick several")
    parser.add_argument("--phase", type=int, default=1, help="highest roadmap phase built so far")
    parser.add_argument("--repeat", type=int, default=1, help="runs per scenario (red-flag recall must hold on all)")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out", type=Path, default=REPORT_DIR)
    parser.add_argument("--set", dest="overrides", action="append", default=[], metavar="SETTING=VALUE",
                        help="override an app setting for this run, e.g. --set safety_model=gpt-5.4-nano")
    parser.add_argument("--red-flags-only", action="store_true", help="only the escalate scenarios (recall check)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    scenarios = load_all(ids=args.scenario, max_phase=args.phase)
    if args.red_flags_only:
        scenarios = [s for s in scenarios if s.expected_outcome == "escalate"]
    if not scenarios:
        print("No scenarios matched.", file=sys.stderr)
        return 2
    summary = run_all(scenarios, args.repeat, args.workers, args.out, args.overrides)
    print(f"accuracy={summary.accuracy:.1%} fabricated={summary.fabricated} recall={summary.recall:.0%} "
          f"errors={summary.errors} -> {'PASS' if summary.gates_passed else 'FAIL'}")
    return 0 if summary.gates_passed else 1


if __name__ == "__main__":
    sys.exit(main())
