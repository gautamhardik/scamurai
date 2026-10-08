import io

import pytest
from PIL import Image

from scamurai.errors import InputError
from scamurai.ingest.images import SERP_MAX_BYTES, prepare_image
from scamurai.ingest.validate import validate_input


def _png(w=1200, h=900, noise=True) -> bytes:
    import random

    img = Image.new("RGB", (w, h), (240, 240, 240))
    if noise:
        px = img.load()
        rnd = random.Random(1)
        for x in range(0, w, 2):
            for y in range(0, h, 2):
                px[x, y] = (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_prepare_image_makes_small_serpapi_jpeg():
    prepared = prepare_image(_png())
    assert len(prepared.serp_jpeg) <= SERP_MAX_BYTES
    assert prepared.llm_jpeg.startswith(b"\xff\xd8")
    assert Image.open(io.BytesIO(prepared.serp_jpeg)).getexif() == {}


def test_rejects_non_images_and_spoofed_types():
    with pytest.raises(InputError) as e:
        prepare_image(b"<svg onload=alert(1)>")
    assert e.value.code == "invalid_image"
    with pytest.raises(InputError):
        prepare_image(b"\x89PNG\r\n\x1a\n" + b"garbage" * 10)


def test_rejects_oversized_upload():
    with pytest.raises(InputError) as e:
        prepare_image(b"\xff\xd8\xff" + b"0" * (5 * 1024 * 1024 + 1))
    assert e.value.code == "image_too_large"


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({}, "empty_input"),
        ({"text": "x" * 4001}, "text_too_long"),
        ({"url": "javascript:alert(1)"}, "invalid_url"),
        ({"url": "not a link"}, "invalid_url"),
        ({"phone": "12"}, "invalid_phone"),
        ({"image_url": "http://insecure.example/x.jpg"}, "invalid_url"),
    ],
)
def test_validation_errors(kwargs, code):
    with pytest.raises(InputError) as e:
        validate_input(**kwargs)
    assert e.value.code == code


def test_valid_inputs():
    inp = validate_input(text=" hi ", url="sbi-kyc-update.in", phone="1800 1234")
    assert inp.text == "hi" and inp.kinds == ["text", "url", "phone"]
