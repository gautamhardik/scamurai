"""Remove secrets a frightened user might paste (OTPs, card numbers, Aadhaar, PAN) before
any text leaves the machine. Phone numbers and links are kept: they're what Asli checks."""

from __future__ import annotations

import re

_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
# Grouped 4-4-4, or 12 contiguous digits right after the word Aadhaar (a bare 12-digit run
# is more often a phone number with its 91 prefix, which must be kept).
_AADHAAR = re.compile(r"\b[2-9]\d{3}[ -]\d{4}[ -]\d{4}\b|(?:aadhaa?r|आधार)\D{0,15}\b([2-9]\d{11})\b", re.IGNORECASE)
_PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
_OTP = re.compile(
    r"((?:otp|one[\s-]?time[\s-]?password|verification code|security code|ओटीपी)\D{0,25}?)(\d{4,8})\b",
    re.IGNORECASE,
)


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def redact_pii(text: str) -> tuple[str, list[str]]:
    kinds: list[str] = []

    def card(m: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            kinds.append("card")
            return "[card number removed]"
        return m.group(0)

    text = _CARD.sub(card, text)

    def aadhaar(m: re.Match[str]) -> str:
        kinds.append("aadhaar")
        if m.group(1):  # keep the "Aadhaar" label, drop only the digits
            return m.group(0)[: m.start(1) - m.start(0)] + "[ID number removed]"
        return "[ID number removed]"

    text = _AADHAAR.sub(aadhaar, text)
    if _PAN.search(text):
        kinds.append("pan")
        text = _PAN.sub("[PAN removed]", text)
    if _OTP.search(text):
        kinds.append("otp")
        text = _OTP.sub(lambda m: m.group(1) + "[code removed]", text)
    return text, sorted(set(kinds))
