"""One-time-code sign-in and portal sessions (PRD §8.10).

6-digit codes, valid 10 minutes, dead after 5 wrong tries, rate-limited per contact and per IP. Only an HMAC of each
code and a SHA-256 of each session token are stored. All times are naive UTC (SQLite drops time zones).
"""

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, func, select

from previsit import audit
from previsit.models import Patient, PortalSession, SignInCode
from previsit.portal.contact import is_email, mask_contact

logger = logging.getLogger(__name__)

CODE_DIGITS = 6
CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
RATE_WINDOW = timedelta(minutes=15)
MAX_CODES_PER_CONTACT = 3
MAX_CODES_PER_IP = 10


class SignInError(Exception):
    """Message is safe to show to the patient."""


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def patients_for(session: Session, contact: str) -> list[Patient]:
    column = Patient.email if is_email(contact) else Patient.phone
    return list(session.exec(select(Patient).where(column == contact)).all()) if contact else []


def _code_hash(key: bytes, contact: str, code: str) -> str:
    return hmac.new(key, f"{contact}:{code}".encode(), hashlib.sha256).hexdigest()


def _recent_requests(session: Session, column, value: str, now: datetime) -> int:
    query = select(func.count()).select_from(SignInCode).where(column == value, SignInCode.created_at > now - RATE_WINDOW)
    return session.exec(query).one()


@dataclass(frozen=True)
class CodeRequest:
    code: str  # never shown outside demo mode


def request_code(
    session: Session, key: bytes, contact: str, ip: str, now: datetime | None = None, *, role: str = "patient"
) -> CodeRequest:
    """Issues a new code (replacing any earlier one). Every contact gets one: new patients verify their contact this
    way before setting up their details (P-004), so the response never reveals whether the contact was known."""
    now = now or now_utc()
    if (_recent_requests(session, SignInCode.contact, contact, now) >= MAX_CODES_PER_CONTACT
            or (ip and _recent_requests(session, SignInCode.ip, ip, now) >= MAX_CODES_PER_IP)):
        audit.record(session, "patient", "portal.code_rate_limited", "contact", None, {"contact": mask_contact(contact)})
        raise SignInError("Too many code requests. Please wait 15 minutes and try again.")
    live = select(SignInCode).where(SignInCode.contact == contact, SignInCode.role == role, SignInCode.used_at.is_(None))
    for old in session.exec(live).all():
        old.used_at = now
        session.add(old)
    known = bool(patients_for(session, contact))
    code = f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"
    session.add(SignInCode(
        role=role, contact=contact, code_hash=_code_hash(key, f"{role}:{contact}", code), ip=ip,
        created_at=now, expires_at=now + CODE_TTL,
    ))
    audit.record(session, "patient", "portal.code_requested", "contact", None,
                 {"contact": mask_contact(contact), "known": known})
    session.flush()
    return CodeRequest(code=code)


def verify_code(
    session: Session, key: bytes, contact: str, code: str, now: datetime | None = None, *, role: str = "patient"
) -> None:
    """Raises SignInError with a patient-facing message unless the code is right, live and not locked."""
    now = now or now_utc()
    row = session.exec(
        select(SignInCode).where(SignInCode.contact == contact, SignInCode.role == role, SignInCode.used_at.is_(None))
        .order_by(SignInCode.id.desc())
    ).first()
    if row is None or not row.code_hash:
        raise SignInError("That code is not right. Please request a new code.")
    if now >= row.expires_at:
        raise SignInError("That code has expired. Please request a new code.")
    if row.attempts >= MAX_ATTEMPTS:
        raise SignInError("Too many wrong tries. Please request a new code.")
    if hmac.compare_digest(row.code_hash, _code_hash(key, f"{role}:{contact}", code.strip())):
        row.used_at = now
        session.add(row)
        audit.record(session, "patient", "portal.signed_in", "contact", None, {"contact": mask_contact(contact)})
        return
    row.attempts += 1
    session.add(row)
    audit.record(session, "patient", "portal.code_wrong", "contact", None,
                 {"contact": mask_contact(contact), "attempts": row.attempts})
    left = MAX_ATTEMPTS - row.attempts
    if left <= 0:
        raise SignInError("Too many wrong tries. Please request a new code.")
    raise SignInError(f"That code is not right. {left} {'try' if left == 1 else 'tries'} left.")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(
    session: Session, contact: str, hours: int, now: datetime | None = None, *, role: str = "patient"
) -> str:
    now = now or now_utc()
    token = secrets.token_urlsafe(32)
    session.add(PortalSession(role=role, token_hash=_token_hash(token), contact=contact, created_at=now,
                              expires_at=now + timedelta(hours=hours)))
    session.flush()
    return token


def session_contact(
    session: Session, token: str | None, now: datetime | None = None, *, role: str = "patient"
) -> str | None:
    """The contact of a live session of this role; a patient session never counts as a doctor's, or vice versa."""
    if not token:
        return None
    now = now or now_utc()
    row = session.exec(select(PortalSession).where(PortalSession.token_hash == _token_hash(token))).first()
    if row is None or row.role != role or row.ended_at is not None or now >= row.expires_at:
        return None
    return row.contact


def end_session(session: Session, token: str | None, now: datetime | None = None) -> None:
    if not token:
        return
    row = session.exec(select(PortalSession).where(PortalSession.token_hash == _token_hash(token))).first()
    if row is not None and row.ended_at is None:
        row.ended_at = now or now_utc()
        session.add(row)
        audit.record(session, "patient", "portal.signed_out", "contact", None, {"contact": mask_contact(row.contact)})


def deliver_code(contact: str, code: str) -> bool:
    """Real SMS/email delivery waits for a messaging provider (PROGRESS PP.8). Never logs the code."""
    logger.warning("Sign-in code for %s not delivered: no messaging provider is configured (PP.8)", mask_contact(contact))
    return False

