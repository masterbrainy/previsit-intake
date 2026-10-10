"""Doctors: who sees which patient, referrals, and doctor recommendations at booking (P-005). No AI here.

Access is per patient: a doctor may open a patient's records only if one of the patient's appointments is with them,
or another doctor with access referred the patient to them.
"""

import re
from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session, func, select

from previsit import audit
from previsit.models import Appointment, Doctor, Referral

GENERAL_PRACTICE = "General practice"
PAEDIATRICS = "Paediatrics"
CHILD_AGE_LIMIT = 16
# Words that mean "don't book, get help now". Shown as a warning on the booking page; the intake's red-flag check
# still runs on every answer later.
URGENT_WORDS = (
    "chest pain", "chest tightness", "can't breathe", "cannot breathe", "short of breath", "stiff neck", "fainted",
    "passed out", "seizure", "seizures", "fit", "fits", "unconscious", "bleeding heavily", "vomiting blood", "suicide",
    "suicidal", "kill myself",
    "overdose", "stroke", "face drooping", "slurred",
)


class ReferralError(ValueError):
    pass


@dataclass(frozen=True)
class Recommendation:
    doctor: Doctor
    reasons: tuple[str, ...]


def _words(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9']+", " ", text.lower()) + " "


def urgent_words_in(reason: str) -> list[str]:
    text = _words(reason)
    return [w for w in URGENT_WORDS if f" {w} " in text]  # whole words: "fit" must not match "fitness"


def recommend_doctors(
    session: Session, reason: str, age_years: int | None = None, limit: int = 3, now: datetime | None = None
) -> list[Recommendation]:
    """Ranks doctors by what the visit is about: keyword matches, then children to paediatrics, then general
    practice, then whoever has the fewest upcoming appointments."""
    now = now or datetime.now()
    text = _words(reason)
    load = dict(session.exec(
        select(Appointment.doctor_id, func.count()).where(Appointment.scheduled_at > now).group_by(Appointment.doctor_id)
    ).all())
    ranked = []
    for doctor in session.exec(select(Doctor)).all():
        matched = [k for k in doctor.keywords if f" {k.lower()} " in text or f" {k.lower()}s " in text]
        reasons = [f"sees {', '.join(matched)}"] if matched else []
        score = 10 * len(matched)
        if age_years is not None and age_years < CHILD_AGE_LIMIT and doctor.specialty == PAEDIATRICS:
            score += 8
            reasons.append("sees children")
        if age_years is not None and age_years >= CHILD_AGE_LIMIT and doctor.specialty == PAEDIATRICS:
            score -= 20
        if doctor.specialty == GENERAL_PRACTICE:
            score += 3
            reasons.append("general practice: sees most problems")
        ranked.append((score, load.get(doctor.id, 0), doctor.name, Recommendation(doctor, tuple(reasons))))
    ranked.sort(key=lambda r: (-r[0], r[1], r[2]))
    picks = [r[3] for r in ranked if r[0] > 0][:limit]  # unmatched specialists are listed as "other doctors"
    if picks and all(p.doctor.specialty != GENERAL_PRACTICE for p in picks):
        # A general practitioner is always offered (ROADMAP H.2).
        gp = next((r[3] for r in ranked if r[3].doctor.specialty == GENERAL_PRACTICE), None)
        if gp is not None:
            picks = [*picks[: limit - 1], gp]
    return picks


def can_access(session: Session, doctor_id: int | None, patient_id: int) -> bool:
    if doctor_id is None:
        return False
    own = session.exec(select(Appointment.id).where(
        Appointment.patient_id == patient_id, Appointment.doctor_id == doctor_id)).first()
    if own is not None:
        return True
    referred = session.exec(select(Referral.id).where(
        Referral.patient_id == patient_id, Referral.to_doctor_id == doctor_id)).first()
    return referred is not None


def patient_ids_for(session: Session, doctor_id: int) -> tuple[set[int], set[int]]:
    """(patients with an appointment with this doctor, patients referred to this doctor)."""
    own = set(session.exec(select(Appointment.patient_id).where(Appointment.doctor_id == doctor_id)).all())
    referred = set(session.exec(select(Referral.patient_id).where(Referral.to_doctor_id == doctor_id)).all())
    return own, referred - own


def refer(session: Session, from_doctor: Doctor, to_doctor_id: int, patient_id: int, note: str) -> Referral:
    if not can_access(session, from_doctor.id, patient_id):
        raise ReferralError("You can only refer your own patients.")
    to_doctor = session.get(Doctor, to_doctor_id)
    if to_doctor is None or to_doctor.id == from_doctor.id:
        raise ReferralError("Please choose another doctor.")
    referral = Referral(patient_id=patient_id, from_doctor_id=from_doctor.id, to_doctor_id=to_doctor.id,
                        note=note.strip()[:500])
    session.add(referral)
    session.flush()
    audit.record(session, from_doctor.email, "patient.referred", "patient", patient_id,
                 {"to_doctor_id": to_doctor.id, "referral_id": referral.id})
    return referral


def ensure_a_doctor(session: Session, name: str, email: str) -> None:
    """A fresh install gets one general-practice doctor so booking and sign-in work out of the box."""
    if session.exec(select(Doctor.id)).first() is None:
        session.add(Doctor(name=name, email=email.lower(), specialty=GENERAL_PRACTICE,
                           keywords=["fever", "cough", "cold", "flu", "tired", "check-up", "headache"]))
