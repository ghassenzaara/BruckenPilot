"""Defensive German number/date parsing.

The LLM normalizes formats during extraction, so these are *fallbacks* for the
rare malformed value (and for use on raw text outside the LLM path). All return
None on failure rather than raising — the caller decides what a missing value means.
"""
import re
from datetime import date

_NUM_RE = re.compile(r"-?\d[\d.]*(?:,\d+)?")


def parse_german_number(value) -> float | None:
    """'1.776,57' -> 1776.57 ; '2,2' -> 2.2 ; passes through real numbers."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = _NUM_RE.search(str(value))
    if not m:
        return None
    token = m.group().replace(".", "").replace(",", ".")
    try:
        return float(token)
    except ValueError:
        return None


def parse_german_date(value) -> date | None:
    """'20.08.2025' -> date(2025, 8, 20). Also accepts ISO 'YYYY-MM-DD'."""
    if value is None:
        return None
    s = str(value).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y"):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None
