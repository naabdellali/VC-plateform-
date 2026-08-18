"""
Small, deterministic helpers to turn a raw text fragment like "EUR 10bn" or
"$2.5M" into a float. Used only to pre-fill deck_value fields for display
and rough comparison - never used as a substitute for the platform's own
sourced calculations.
"""
from __future__ import annotations

import re

_MULTIPLIERS = {
    "k": 1_000,
    "thousand": 1_000,
    "m": 1_000_000,
    "mm": 1_000_000,
    "million": 1_000_000,
    "bn": 1_000_000_000,
    "b": 1_000_000_000,
    "billion": 1_000_000_000,
}

_MONEY_RE = re.compile(
    r"(?P<currency>[€$£]|EUR|USD|GBP)?\s?(?P<number>\d[\d.,]*)\s?(?P<suffix>k|m|mm|bn|b|thousand|million|billion)?",
    re.IGNORECASE,
)


def parse_money(text: str) -> float | None:
    if not text:
        return None
    match = _MONEY_RE.search(text)
    if not match or not match.group("number"):
        return None

    number_str = match.group("number").replace(" ", "")
    # Handle both "1,234.56" and European "1.234,56" - assume the LAST
    # separator encountered is the decimal separator.
    if "," in number_str and "." in number_str:
        if number_str.rfind(",") > number_str.rfind("."):
            number_str = number_str.replace(".", "").replace(",", ".")
        else:
            number_str = number_str.replace(",", "")
    elif "," in number_str:
        # Ambiguous: "10,000" (thousands) vs "10,5" (decimal) - treat 3-digit
        # groups after the comma as a thousands separator.
        parts = number_str.split(",")
        if len(parts[-1]) == 3:
            number_str = number_str.replace(",", "")
        else:
            number_str = number_str.replace(",", ".")

    try:
        value = float(number_str)
    except ValueError:
        return None

    suffix = (match.group("suffix") or "").lower()
    multiplier = _MULTIPLIERS.get(suffix, 1)
    return value * multiplier
