"""Patient contact (mobile number or email): one normal form for booking and portal sign-in, and masking for display."""

import re

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}")
_PHONE_PUNCTUATION = re.compile(r"[\s().-]")
_PHONE = re.compile(r"\+?\d{7,15}")


class ContactError(ValueError):
    pass


def normalize_contact(raw: str) -> str:
    """Lower-cased email, or phone digits with an optional leading +. Raises ContactError if it is neither."""
    text = raw.strip()
    if "@" in text:
        email = text.lower()
        if _EMAIL.fullmatch(email):
            return email
        raise ContactError("Please enter a valid email address.")
    phone = _PHONE_PUNCTUATION.sub("", text)
    if _PHONE.fullmatch(phone):
        return phone
    raise ContactError("Please enter a mobile number (digits only, with country code if you have one) or an email.")


def is_email(contact: str) -> bool:
    return "@" in contact


def mask_contact(contact: str) -> str:
    """For display after sign-in starts: "m•••@example.com" or "••••0142"."""
    if is_email(contact):
        local, _, domain = contact.partition("@")
        return f"{local[:1]}•••@{domain}"
    return f"••••{contact[-4:]}"
