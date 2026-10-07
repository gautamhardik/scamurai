"""Scam-report vocabulary (English + Hindi/Hinglish), matched within a single search result."""

from __future__ import annotations

import re

_EN = [
    r"scams?", r"scammers?", r"scammed", r"fraud(?:s|ulent|ster|sters)?", r"fake", r"cheat(?:ed|ing|er|ers)?",
    r"complaints?", r"phishing", r"spam(?:mer|mers)?", r"duped", r"hoax", r"beware", r"impersonat\w*",
    r"swindl\w*", r"extort\w*", r"cyber\s?crime", r"lost (?:money|rs|₹)", r"money lost", r"not delivered",
    r"never (?:received|delivered)", r"do not pay", r"don'?t pay", r"looted", r"con(?:ned)? (?:artist|men)",
    r"fake (?:website|call|number|offer|job)", r"cyber fraud", r"blacklist(?:ed)?", r"warning",
]
_HI = [
    "ठगी", "ठग", "धोखा", "धोखाधड़ी", "फ्रॉड", "फर्जी", "फ़र्ज़ी", "नकली", "साइबर अपराध", "ठगे", "जालसाज",
]
_HINGLISH = [r"dhokha", r"thagi", r"farzi", r"nakli", r"thag"]

_EN_RE = re.compile(r"\b(" + "|".join(_EN + _HINGLISH) + r")\b", re.IGNORECASE)


def lexicon_hits(text: str | None) -> list[str]:
    if not text:
        return []
    hits = {m.group(0).lower() for m in _EN_RE.finditer(text)}
    hits.update(term for term in _HI if term in text)
    return sorted(hits)
