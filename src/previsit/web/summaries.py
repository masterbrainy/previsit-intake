"""One summary row per appointment, for the hospital overview (non-clinical fields only) and a doctor's patient list
(with quick notes: chief complaints, tests, results, alerts)."""

from sqlmodel import Session, select

from previsit.models import (
    Appointment, Doctor, HistorySheetRecord, Intake, LabResult, MedicalRecommendation, Patient, StaffAlert,
)


def _latest_complaints(session: Session, intake_ids: list[int]) -> dict[int, list[str]]:
    if not intake_ids:
        return {}
    records = session.exec(
        select(HistorySheetRecord).where(HistorySheetRecord.intake_id.in_(intake_ids))
        .order_by(HistorySheetRecord.version)
    ).all()
    latest = {r.intake_id: r for r in records}  # later versions overwrite earlier ones
    return {
        intake_id: [f"{c['complaint']}" + (f" ({c['duration']})" if c.get("duration") else "")
                    for c in record.data.get("chief_complaints", [])]
        for intake_id, record in latest.items()
    }


def appointment_rows(session: Session, patient_ids: set[int] | None = None) -> list[dict]:
    """All appointments (or those of `patient_ids`), soonest first."""
    query = (
        select(Appointment, Patient, Intake, Doctor)
        .join(Patient, Patient.id == Appointment.patient_id)
        .join(Intake, Intake.appointment_id == Appointment.id, isouter=True)
        .join(Doctor, Doctor.id == Appointment.doctor_id, isouter=True)
        .order_by(Appointment.scheduled_at)
    )
    if patient_ids is not None:
        query = query.where(Appointment.patient_id.in_(patient_ids))
    rows = session.exec(query).all()
    ids = [a.id for a, _, _, _ in rows]
    recs = session.exec(select(MedicalRecommendation).where(MedicalRecommendation.appointment_id.in_(ids))).all()
    alerts = session.exec(select(StaffAlert).where(
        StaffAlert.appointment_id.in_(ids), StaffAlert.acknowledged_at.is_(None))).all()
    results = session.exec(select(LabResult.appointment_id).where(LabResult.appointment_id.in_(ids))).all()
    complaints = _latest_complaints(session, [i.id for _, _, i, _ in rows if i])

    rec_counts: dict[int, dict[str, int]] = {}
    for rec in recs:
        counts = rec_counts.setdefault(rec.appointment_id, {"suggested": 0, "approved": 0, "sent": 0})
        if rec.patient_notified_at:
            counts["sent"] += 1
        elif rec.status.is_approved:
            counts["approved"] += 1
        elif rec.status.value == "suggested":
            counts["suggested"] += 1
    emergency = {a.appointment_id for a in alerts if a.severity == "emergency"}
    return [
        {"appointment": a, "patient": p, "intake": i, "doctor": d,
         "state": i.state.value if i else "not_started",
         "emergency": a.id in emergency,
         "alerts": [al for al in alerts if al.appointment_id == a.id],
         "recs": rec_counts.get(a.id, {}),
         "results": sum(1 for r in results if r == a.id),
         "complaints": complaints.get(i.id, []) if i else []}
        for a, p, i, d in rows
    ]
