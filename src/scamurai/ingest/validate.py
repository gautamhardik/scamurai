"""Input validation. Scamurai never fetches user-supplied URLs — links are only parsed and searched."""

from __future__ import annotations

import re

import phonenumbers

from scamurai.errors import InputError
from scamurai.knowledge import domains
from scamurai.models import InvestigationInput

MAX_TEXT_CHARS = 4000
MAX_URL_CHARS = 2048


def validate_input(
    *,
    text: str | None = None,
    image: bytes | None = None,
    image_url: str | None = None,
    url: str | None = None,
    phone: str | None = None,
    lang: str = "auto",
    example_id: str | None = None,
) -> InvestigationInput:
    text = (text or "").strip() or None
    url = (url or "").strip() or None
    phone = (phone or "").strip() or None
    image_url = (image_url or "").strip() or None

    if not any([text, image, url, phone, image_url]):
        raise InputError("empty_input", "Paste a message, add a screenshot, a link or a phone number.", status=422)
    if text and len(text) > MAX_TEXT_CHARS:
        raise InputError(
            "text_too_long", f"That's a long message. Paste up to {MAX_TEXT_CHARS:,} characters.", status=422
        )
    if url:
        if len(url) > MAX_URL_CHARS:
            raise InputError("invalid_url", "That link is too long.", status=422)
        if re.match(r"^[a-z][a-z0-9+.-]*:", url, re.IGNORECASE) and not re.match(
            r"^(https?|hxxps?)://", url, re.IGNORECASE
        ):
            raise InputError("invalid_url", "Only web links (http/https) can be checked.", status=422)
        host = domains.host_of(url)
        if not host or not domains.is_valid_public_host(host):
            raise InputError("invalid_url", "That doesn't look like a web link.", status=422)
    if image_url:
        if len(image_url) > MAX_URL_CHARS or not re.match(r"^https://", image_url, re.IGNORECASE):
            raise InputError("invalid_url", "Image links must start with https://", status=422)
        host = domains.host_of(image_url)
        if not host or not domains.is_valid_public_host(host):
            raise InputError("invalid_url", "That image link doesn't look valid.", status=422)
    if phone:
        digits = re.sub(r"\D", "", phone)
        if not (digits.startswith(("1800", "1860")) and 8 <= len(digits) <= 11):
            try:
                parsed = phonenumbers.parse(phone, "IN")
            except phonenumbers.NumberParseException:
                parsed = None
            if parsed is None or not phonenumbers.is_possible_number(parsed):
                raise InputError(
                    "invalid_phone", "That number doesn't look valid. Include all 10 digits.", status=422
                )
    if lang not in ("auto", "en", "hi", "hinglish"):
        lang = "auto"
    return InvestigationInput(
        text=text, image=image, image_url=image_url, url=url, phone=phone, lang=lang, example_id=example_id
    )
