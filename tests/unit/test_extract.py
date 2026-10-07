from asli.ingest import regex_extract as rx
from asli.ingest.redact import redact_pii
from asli.llm.extract import build_graph
from asli.models import InvestigationInput


def test_indian_phone_formats_normalize_to_e164():
    text = "Call +91 70000 12345 or 07000012346 or 70000-12347, landline 011 2345 6789"
    values = {f.value for f in rx.phones(text)}
    assert {"+917000012345", "+917000012346", "+917000012347"} <= values


def test_toll_free_numbers_are_kept_and_formatted():
    found = rx.phones("Call 1800 1234 or 1800 11 2211")
    kinds = {f.value: f.kind for f in found}
    assert kinds == {"18001234": "toll_free", "1800112211": "toll_free"}
    assert rx.phone_display("18001234") == "1800 1234"


def test_phone_query_variants_cover_common_formats():
    assert rx.phone_query_variants("+917000012345") == ["7000012345", "70000 12345", "+91 70000 12345"]


def test_urls_handle_bare_defanged_and_skip_emails_and_files():
    text = "Visit bijli-bill-pay.top/upd or hxxps://paytm-refund[.]online/x. Mail hr@infosys-careers.in. See photo.jpg"
    hosts = {f.value for f in rx.urls(text)}
    assert hosts == {"bijli-bill-pay.top", "paytm-refund.online"}


def test_upi_ids_are_not_confused_with_emails():
    text = "Pay infosyshr@ybl or mail hr.infosys.careers@gmail.com"
    assert [f.value for f in rx.upi_ids(text)] == ["infosyshr@ybl"]
    assert [f.value for f in rx.emails(text)] == ["hr.infosys.careers@gmail.com"]


def test_amounts_in_rupee_formats():
    found = {rx.rupees(f.value) for f in rx.amounts("Pay Rs. 2,500 now, ₹13 only, 1299/- or ४५ rupees")}
    assert {"₹2,500", "₹13", "₹1,299"} <= found


def test_indian_digit_grouping():
    assert rx.rupees(12345600) == "₹1,23,456"


def test_redaction_removes_secrets_but_keeps_phone_numbers():
    text = "Your OTP is 482913. Card 4111 1111 1111 1111. Aadhaar 2345 6789 0123. PAN ABCDE1234F. Call 917000012345"
    out, kinds = redact_pii(text)
    assert "482913" not in out and "4111" not in out and "ABCDE1234F" not in out and "2345 6789 0123" not in out
    assert "917000012345" in out
    assert kinds == ["aadhaar", "card", "otp", "pan"]


def test_regex_only_graph_without_llm():
    text = ("Selected for Data Entry at Infosys Ltd. Pay registration fee Rs 2,500 to hr.infosys.careers@gmail.com "
            "via UPI infosyshr@ybl. Contact 98765-43210.")
    g = build_graph(InvestigationInput(text=text), text, None, has_image=False)
    types = {e.type for e in g.entities}
    assert {"phone", "email", "upi_id", "amount", "org"} <= types
    assert g.extraction == "regex_fallback"
    assert g.scam_type == "job_offer"
    org = g.first("org")
    assert org.attrs["curated"] == "infosys"


def test_llm_values_must_be_grounded():
    text = "Your electricity will be cut tonight. Call 70000 12345."
    llm = {
        "scheme": "electricity_disconnection",
        "claimed_org": {"name": "Tata Power", "category": "utility"},  # not in the message
        "phones": ["+91 99999 88888"],  # hallucinated
        "urls": ["evil-example.top"],  # hallucinated
    }
    g = build_graph(InvestigationInput(text=text), text, llm, has_image=False)
    assert [e.value for e in g.of("phone")] == ["+917000012345"]
    assert not g.of("url") and not g.of("org")
    assert g.ungrounded_dropped == 3
    assert g.org_category == "utility"


def test_generic_roles_and_sender_ids_are_not_organisations():
    text = "VM-ELECBD: Electricity Officer says pay now at bijli-bill-pay.top"
    for name in ("Electricity Officer", "VM-ELECBD"):
        llm = {"scheme": "electricity_disconnection", "claimed_org": {"name": name, "category": "utility"}}
        g = build_graph(InvestigationInput(text=text), text, llm, has_image=False)
        assert not g.of("org"), name


def test_ocr_text_is_used_for_grounding():
    ocr = "प्रिय उपभोक्ता, बिजली कनेक्शन आज रात काट दिया जाएगा। Call +91 70000 12345"
    llm = {"ocr_text": ocr, "language": "mixed", "scheme": "electricity_disconnection", "phones": ["+91 70000 12345"]}
    g = build_graph(InvestigationInput(image=b"x"), "", llm, has_image=True)
    phone = g.first("phone")
    assert phone and phone.source == "ocr"
    assert g.first("image") is not None
