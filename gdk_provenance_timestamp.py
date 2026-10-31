"""Validate user-supplied GDK Identity provenance at every CAS trust boundary.

The intake gate already rejects impossible/future RFC3339 timestamps. Repeat
that validation on the committed receipt: a regex alone is not provenance.
This module does not invent or normalize an operator-provided timestamp.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from package_identity_provisioner import ConflictError

RFC3339 = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})\Z"
)


def require_valid_provided_at(value: object, *, label: str = "GDK Identity provided_at") -> None:
    """Reject malformed, impossible, timezone-free or future timestamps.

    Match the original user-provided Identity gate's five-minute clock skew
    allowance. Keep the exact original value in the approved receipt.
    """
    if type(value) is not str or not RFC3339.fullmatch(value):
        raise ConflictError(label + " must be RFC3339 with timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConflictError(label + " calendar date/time invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConflictError(label + " timezone missing")
    if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ConflictError(label + " cannot be in the future")
