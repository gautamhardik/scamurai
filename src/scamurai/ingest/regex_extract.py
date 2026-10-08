"""Deterministic extractors. They always run, so an LLM outage never loses phones, links or amounts."""

from __future__ import annotations

import re
from dataclasses import dataclass

import phonenumbers

from scamurai.knowledge import domains

_URL = re.compile(
    r"(?:h(?:tt|xx)ps?://|www\.)[^\s<>\"'`]+"
    r"|\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.|\[\.\]|\(\.\)))+[a-z]{2,24}(?:/[^\s<>\"'`]*)?",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"\b[a-z0-9._%+-]{1,64}@[a-z0-9-]{1,63}(?:\.[a-z0-9-]{1,63}){0,8}\.[a-z]{2,24}\b", re.IGNORECASE)
_UPI = re.compile(r"\b[a-z0-9._-]{2,64}@[a-z]{2,20}\b(?!\.[a-z0-9])(?!@)", re.IGNORECASE)
_TOLL_FREE = re.compile(r"\b1(?:800|860)[\s-]?\d{2,4}[\s-]?\d{2,4}(?:[\s-]?\d{2,4})?\b")
_AMOUNT = re.compile(
    r"(?:₹|\brs\.?|\binr\b|rupees?|रु\.?)\s*([\d,]{1,15}(?:\.\d{1,2})?)"
    # bounded, and anchored at the start of a number: unanchored, a long digit run backtracks quadratically
    r"|(?<![\d,.])([\d,]{1,15}(?:\.\d{1,2})?)\s*(?:/-|\brs\b\.?|rupees?|रुपये|रुपए|रु\.?)",
    re.IGNORECASE,
)
_FILE_EXT = {"jpg", "jpeg", "png", "gif", "pdf", "doc", "docx", "apk", "webp", "mp4", "txt", "zip", "html"}


@dataclass(frozen=True)
class Found:
    raw: str
    value: str
    kind: str


def phones(text: str) -> list[Found]:
    out: dict[str, Found] = {}
    for match in phonenumbers.PhoneNumberMatcher(text, "IN", leniency=phonenumbers.Leniency.POSSIBLE):
        num = match.number
        if not phonenumbers.is_possible_number(num):
            continue
        national = str(num.national_number)
        if num.country_code == 91 and national.startswith(("1800", "1860")):
            out.setdefault(national, Found(match.raw_string.strip(), national, "toll_free"))
            continue
        if num.country_code == 91 and len(national) != 10:
            continue
        e164 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
        out.setdefault(e164, Found(match.raw_string.strip(), e164, "mobile" if national[0] in "6789" else "landline"))
    for match in _TOLL_FREE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if 8 <= len(digits) <= 11 and not any(f.value.endswith(digits) for f in out.values()):
            out.setdefault(digits, Found(match.group(0).strip(), digits, "toll_free"))
    return list(out.values())


def phone_query_variants(value: str) -> list[str]:
    """Formats the same number is written in on the web (one search covers all via OR)."""
    digits = re.sub(r"\D", "", value)
    if value.startswith("+91") and len(digits) == 12:
        n = digits[2:]
        return [n, f"{n[:5]} {n[5:]}", f"+91 {n[:5]} {n[5:]}"]
    if digits.startswith(("1800", "1860")):
        rest = digits[4:]
        return [digits, f"{digits[:4]} {rest}", f"{digits[:4]}-{rest}"]
    return [digits]


def phone_display(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if value.startswith("+91") and len(digits) == 12:
        return f"+91 {digits[2:7]} {digits[7:]}"
    if digits.startswith(("1800", "1860")):
        rest = digits[4:]
        if len(rest) == 6:  # 1800 11 2211
            return f"{digits[:4]} {rest[:2]} {rest[2:]}"
        return f"{digits[:4]} {rest[:3]} {rest[3:]}" if len(rest) == 7 else f"{digits[:4]} {rest}"  # 1800 425 3800
    return value


def urls(text: str) -> list[Found]:
    # "amazonhr.jobs@ybl" is a UPI ID, not the website amazonhr.jobs (.jobs is a real TLD)
    taken = [m.span() for m in _EMAIL.finditer(text)] + [m.span() for m in _UPI.finditer(text)]
    out: dict[str, Found] = {}
    for m in _URL.finditer(text):
        if any(s <= m.start() < e for s, e in taken) or text[m.end():m.end() + 1] == "@":
            continue
        raw = m.group(0).rstrip(".,;:!?)]}'\"")
        host = domains.host_of(raw)
        if not host or not domains.is_valid_public_host(host):
            continue
        if domains.suffix_of(host).split(".")[-1].lower() in _FILE_EXT:
            continue
        if re.fullmatch(r"[\d.]+", host):
            continue
        out.setdefault(host, Found(raw, host, "url"))
    return list(out.values())


def emails(text: str) -> list[Found]:
    out: dict[str, Found] = {}
    for m in _EMAIL.finditer(text):
        addr = m.group(0).lower()
        domain = addr.split("@", 1)[1]
        if domains.is_valid_public_host(domain):
            out.setdefault(addr, Found(m.group(0), addr, "email"))
    return list(out.values())


def upi_ids(text: str) -> list[Found]:
    email_set = {e.value for e in emails(text)}
    out: dict[str, Found] = {}
    for m in _UPI.finditer(text):
        vpa = m.group(0).lower()
        if vpa in email_set or any(e.startswith(vpa + ".") for e in email_set):
            continue
        out.setdefault(vpa, Found(m.group(0), vpa, "upi"))
    return list(out.values())


def amounts(text: str) -> list[Found]:
    out: list[Found] = []
    seen: set[int] = set()
    for m in _AMOUNT.finditer(text):
        num = (m.group(1) or m.group(2) or "").replace(",", "")
        try:
            paise = round(float(num) * 100)
        except ValueError:
            continue
        if paise <= 0 or paise in seen:
            continue
        seen.add(paise)
        out.append(Found(m.group(0).strip(), str(paise), "amount"))
    return out


def rupees(paise: str | int) -> str:
    value = int(paise) / 100
    whole = int(value)
    s = str(whole)
    if len(s) > 3:  # Indian grouping: 1,23,456
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d{2})+$)", r"\1,", head)
        s = f"{head},{tail}"
    return f"₹{s}" if value == whole else f"₹{s}.{round((value - whole) * 100):02d}"
