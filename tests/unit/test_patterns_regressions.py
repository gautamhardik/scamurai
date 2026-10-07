"""Regressions found by running fresh real-world-style messages through the live pipeline."""

import pytest

from asli.i18n import flag_text
from asli.knowledge.patterns import detect_message_patterns


def signals(text):
    return {h.signal: h.detail for h in detect_message_patterns(text)}


def test_digital_arrest_extortion_in_hinglish():
    text = ("Aapke Aadhaar se ek parcel mein drugs mile hain, CBI officer baat karenge. Video call par raho warna "
            "arrest warrant nikal jayega. Abhi 50,000 security deposit bhejo is UPI par: cbi.verify@okaxis")
    assert "extortion_threat" in signals(text)


@pytest.mark.parametrize(
    "advice",
    [
        "Never share your OTP. If you lost money, report to cyber crime police at 1930 or cybercrime.gov.in.",
        "Beware: police never ask for payment over video call. Do not send money.",
    ],
)
def test_safety_advice_is_not_extortion(advice):
    assert "extortion_threat" not in signals(advice)


@pytest.mark.parametrize(
    "text",
    [
        "482913 is your OTP for a transaction of Rs. 1,250.00 at AMAZON PAY on your HDFC Bank Credit Card XX4321.",
        "Use Google Pay or PhonePe for faster checkout",
        "Pay later with Simpl",
    ],
)
def test_wallet_names_are_not_payment_requests(text):
    assert "payment_request" not in signals(text)


def test_imperative_payment_is_still_detected():
    assert "payment_request" in signals("Pay Rs 13 now to avoid disconnection")
    assert "payment_request" in signals("Ya ₹13 pay karke bill update karein")


def test_task_scam_hook_is_specific():
    s = signals("Simply like videos and earn Rs 3000 per day from home. Complete 3 tasks to get your first payment.")
    assert s.get("too_good_to_be_true") == "task"
    title, _ = flag_text("too_good_to_be_true", "task", "en", {})
    assert "task" in title.lower()


def test_ordinary_optimism_is_not_a_task_scam():
    s = signals("Guaranteed returns of 12% per year on our fixed deposit.")
    assert s.get("too_good_to_be_true") == ""
