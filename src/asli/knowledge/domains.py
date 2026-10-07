"""Domain helpers: registrable domains, official-domain registry, lookalikes, risky TLDs.

No network access: tldextract runs from its bundled public-suffix snapshot.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import tldextract
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

_DATA = Path(__file__).resolve().parent / "data"
_EXTRACT = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)

SUSPICIOUS_TLDS = {
    "top", "xyz", "icu", "shop", "buzz", "click", "sbs", "cfd", "rest", "live", "online", "site",
    "monster", "lol", "quest", "cyou", "bond", "vip", "work", "loan", "win", "bid", "fun", "store",
}
SHORTENERS = {
    "bit.ly", "tinyurl.com", "cutt.ly", "is.gd", "t.ly", "rb.gy", "goo.gl", "ow.ly", "shorturl.at",
    "tiny.cc", "s.id", "v.gd", "bitly.com", "rebrand.ly", "t.co", "lnkd.in",
}
FREE_MAIL = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "yahoo.in", "outlook.com", "hotmail.com",
    "live.com", "rediffmail.com", "protonmail.com", "proton.me", "yandex.com", "yandex.ru", "aol.com",
    "zoho.com", "icloud.com", "mail.com", "gmx.com", "tutanota.com",
}
_HOMOGLYPHS = str.maketrans({"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "@": "a"})
# Cyrillic/Greek letters that render like Latin ones (IDN homograph attacks).
_CONFUSABLES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j",
    "ѕ": "s", "ԁ": "d", "ɡ": "g", "ո": "n", "ο": "o", "α": "a", "ν": "v", "κ": "k", "τ": "t",
})


# --------------------------------------------------------------------------- parsing
def refang(text: str) -> str:
    """Undo common defanging: hxxp, [.], (.), {.}, [dot]."""
    text = re.sub(r"hxxp", "http", text, flags=re.IGNORECASE)
    text = re.sub(r"\[\.\]|\(\.\)|\{\.\}|\[dot\]|\(dot\)", ".", text, flags=re.IGNORECASE)
    return text


def host_of(value: str) -> str | None:
    """Host from a URL or bare domain, lower-cased, without `www.`; IDNA labels kept as `xn--`."""
    value = refang(value.strip()).strip("<>()[]{}\"'.,;")
    if not value:
        return None
    if "://" not in value:
        value = "http://" + value
    try:
        host = urlsplit(value).hostname
    except ValueError:
        return None
    if not host or "." not in host:
        return None
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    host = host.lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


# Newer reserved Indian second-level domains the bundled public-suffix snapshot may not know.
_EXTRA_SUFFIXES = ("bank.in", "fin.in")


def registrable(host: str) -> str | None:
    for sfx in _EXTRA_SUFFIXES:
        if host.endswith("." + sfx):
            labels = host[: -len(sfx) - 1].split(".")
            return f"{labels[-1]}.{sfx}" if labels and labels[-1] else None
    ext = _EXTRACT(host)
    if not ext.suffix or not ext.domain:
        return None
    return f"{ext.domain}.{ext.suffix}"


def suffix_of(host: str) -> str:
    return _EXTRACT(host).suffix


def label_of(host: str) -> str:
    return _EXTRACT(host).domain


def is_valid_public_host(host: str) -> bool:
    return registrable(host) is not None


def defang(host: str) -> str:
    head, _, tail = host.rpartition(".")
    return f"{head}[.]{tail}" if head else host


def is_punycode(host: str) -> bool:
    return any(label.startswith("xn--") for label in host.split("."))


def unicode_host(host: str) -> str:
    try:
        return host.encode("ascii").decode("idna")
    except UnicodeError:
        return host


def is_gov(host: str) -> bool:
    return host.endswith((".gov.in", ".nic.in")) or host in {"gov.in", "nic.in"}


def is_bank_tld(host: str) -> bool:
    """`.bank.in` is reserved for RBI-regulated banks."""
    return host.endswith(".bank.in")


def is_suspicious_tld(host: str) -> bool:
    return suffix_of(host).split(".")[-1] in SUSPICIOUS_TLDS


def is_shortener(host: str) -> bool:
    reg = registrable(host) or host
    return host in SHORTENERS or reg in SHORTENERS


def is_free_mail(domain: str) -> bool:
    return domain.lower() in FREE_MAIL


# --------------------------------------------------------------------------- official registry
@dataclass(frozen=True)
class Org:
    key: str
    name: str
    category: str
    aliases: tuple[str, ...]
    domains: tuple[str, ...]
    tokens: tuple[str, ...] = field(default_factory=tuple)


@lru_cache
def orgs() -> tuple[Org, ...]:
    raw = json.loads((_DATA / "official_domains.json").read_text(encoding="utf-8"))
    return tuple(
        Org(
            key=o["key"],
            name=o["name"],
            category=o["category"],
            aliases=tuple(a.lower() for a in o["aliases"]),
            domains=tuple(o["domains"]),
            tokens=tuple(o.get("tokens", [])),
        )
        for o in raw["orgs"]
    )


@lru_cache
def source_classes() -> dict[str, str]:
    raw = json.loads((_DATA / "source_classes.json").read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    for cls, domains in raw.items():
        if cls.startswith("_"):
            continue
        for d in domains:
            mapping[d] = cls
    return mapping


def _norm_name(name: str) -> str:
    name = unicodedata.normalize("NFKC", name).lower()
    name = re.sub(r"\b(ltd|limited|pvt|private|inc|llp|india|co|company|corp|corporation)\b\.?", " ", name)
    return re.sub(r"[^a-z0-9 ]+", " ", name).strip()


def match_org(name: str | None) -> Org | None:
    """Curated org for a claimed organisation name (exact alias or strong fuzzy match)."""
    if not name:
        return None
    n = _norm_name(name)
    if not n:
        return None
    best: tuple[float, Org | None] = (0.0, None)
    for org in orgs():
        for alias in org.aliases:
            a = _norm_name(alias)
            if not a:
                continue
            if n == a:
                return org
            # short aliases (sbi, tcs, jio) must match as whole words
            if len(a) <= 4:
                if re.search(rf"\b{re.escape(a)}\b", n):
                    score = 92.0
                else:
                    continue
            else:
                score = fuzz.token_set_ratio(n, a)
            if score > best[0]:
                best = (score, org)
    return best[1] if best[0] >= 90 else None


_GENERIC_ORG_WORDS = {
    "electricity", "electric", "power", "bijli", "officer", "office", "department", "dept", "board", "bank",
    "customer", "care", "service", "services", "support", "helpline", "team", "government", "govt", "police",
    "cyber", "cell", "crime", "hr", "human", "resources", "manager", "executive", "admin", "the", "of", "your",
    "dear", "consumer", "authority", "company", "courier", "delivery", "telecom", "mobile", "kyc", "branch",
    "income", "tax", "customs", "official", "head", "desk", "centre", "center", "billing", "account", "accounts",
    "बिजली", "विभाग", "अधिकारी", "बैंक", "उपभोक्ता", "सेवा",
}


def is_generic_org_name(name: str) -> bool:
    """'Electricity Officer', 'Customer Care', 'HR Team' describe a role, not an organisation."""
    if re.fullmatch(r"[A-Z]{2}-[A-Z0-9]{3,9}(-[A-Z])?", name.strip()):  # TRAI SMS header, e.g. VM-ELECBD
        return True
    words = re.findall(r"[a-z]+|[ऀ-ॿ]+", unicodedata.normalize("NFKC", name).lower())
    return bool(words) and all(w in _GENERIC_ORG_WORDS for w in words)


def org_for_domain(reg_domain: str) -> Org | None:
    for org in orgs():
        if reg_domain in org.domains:
            return org
    if reg_domain.endswith(".bank.in"):  # RBI-reserved: <bank>.bank.in belongs to that bank
        label = reg_domain[: -len(".bank.in")]
        for org in orgs():
            if org.category == "bank" and (label in org.tokens or label == org.key):
                return org
    return None


def official_domains_for(org: Org) -> list[str]:
    extra = [f"{t}.bank.in" for t in (org.key, *org.tokens)] if org.category == "bank" else []
    return list(dict.fromkeys([*org.domains, *extra]))


def domain_matches(reg_domain: str, official: list[str] | tuple[str, ...]) -> bool:
    return any(reg_domain == d or reg_domain.endswith("." + d) for d in official)


def known_platform(reg_domain: str) -> bool:
    """Big, well-known sites that are never treated as 'suspicious domains' themselves."""
    return org_for_domain(reg_domain) is not None or source_classes().get(reg_domain) in {
        "marketplace", "social", "job_board", "news",
    }


def _tokens(label: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+|(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", label) if t]


def brand_in_domain(host: str) -> Org | None:
    """Brand token embedded in a non-official domain, e.g. `sbi-kyc-update.in`, `flipkartsale.xyz`."""
    reg = registrable(host)
    if not reg or org_for_domain(reg) or reg in _INFRA_DOMAINS:
        return None
    parts = _tokens(host.replace(".", "-"))
    for org in orgs():
        for token in org.tokens:
            if len(token) <= 4:
                if token in parts:
                    return org
            elif any(p == token or p.startswith(token) or p.endswith(token) for p in parts):
                return org
    return None


# Brand-named infrastructure that isn't impersonation by itself.
_INFRA_DOMAINS = {"amazonaws.com", "googleusercontent.com", "googleapis.com", "gstatic.com", "google.co.in"}


def lookalike_of(host: str) -> Org | None:
    """Typosquats of official labels: `amaz0n.in`, `paytrn.com`, `flipkarrt.com`."""
    reg = registrable(host)
    if not reg or org_for_domain(reg):
        return None
    label = label_of(unicode_host(host)).translate(_CONFUSABLES).translate(_HOMOGLYPHS)
    label = label.replace("rn", "m").replace("vv", "w")
    for org in orgs():
        for d in org.domains:
            official_label = label_of(d)
            if len(official_label) < 5:
                continue
            if label == official_label or Levenshtein.distance(label, official_label) <= 1:
                return org
    return None
