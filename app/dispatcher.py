"""Detect what kind of identifier the user gave us."""
from __future__ import annotations

import re

from .schema import InputKind

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# +country and 7-15 digits, allowing spaces/dashes/parens
_PHONE = re.compile(r"^\+?[\d][\d\s().-]{6,17}\d$")
_USERNAME = re.compile(r"^[A-Za-z0-9._-]{2,40}$")


def is_safe(query: str) -> bool:
    """Reject inputs that could be misread as CLI flags or contain control chars.

    Every engine receives the query as an argv positional. A value like
    ``--proxy=evil`` or ``-o /etc/x`` would be parsed as an *option* by the
    engine's argparse. Legit usernames/emails/phones/names never start with '-'
    and never contain control characters, so we reject those outright.
    """
    q = query.strip()
    if not q or len(q) > 254:
        return False
    if q[0] == "-":
        return False
    if any(ord(c) < 32 for c in q):  # newlines, nulls, etc.
        return False
    return True


def detect(query: str) -> InputKind:
    q = query.strip()
    if _EMAIL.match(q):
        return InputKind.email
    # phone: strip formatting, must be mostly digits
    digits = re.sub(r"[\s().-]", "", q)
    if _PHONE.match(q) and digits.lstrip("+").isdigit() and 7 <= len(digits.lstrip("+")) <= 15:
        return InputKind.phone
    if _USERNAME.match(q):
        return InputKind.username
    # anything with a space and letters -> treat as a real name
    if " " in q and any(c.isalpha() for c in q):
        return InputKind.name
    return InputKind.username


def username_candidates_from_name(name: str) -> list[str]:
    """Turn 'Ravi Kumar' into likely handles, ranked."""
    parts = [p for p in re.split(r"\s+", name.strip().lower()) if p]
    if not parts:
        return []
    joined = "".join(parts)
    out = [joined]
    if len(parts) >= 2:
        out += [".".join(parts), "_".join(parts), parts[0] + parts[-1]]
    # dedup preserving order
    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def username_from_email(email: str) -> str:
    return email.split("@", 1)[0]
