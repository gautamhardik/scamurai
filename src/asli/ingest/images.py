"""Screenshot handling: signature sniffing, safe decoding, re-encoding (drops EXIF/metadata),
and two derived JPEGs — one for the vision model, one ≤480 KB for the SerpApi Image API."""

from __future__ import annotations

import hashlib
import io
import warnings
from dataclasses import dataclass

from PIL import Image, ImageOps

from asli.errors import InputError

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
SERP_MAX_BYTES = 480 * 1024  # SerpApi Image API limit is 500 KB
LLM_MAX_EDGE = 1600
SERP_MAX_EDGE = 1280
Image.MAX_IMAGE_PIXELS = 40_000_000


@dataclass(frozen=True)
class PreparedImage:
    llm_jpeg: bytes
    serp_jpeg: bytes
    sha256: str
    width: int
    height: int


def sniff(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _encode(img: Image.Image, max_edge: int, quality: int) -> bytes:
    copy = img.copy()
    copy.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    copy.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def prepare_image(data: bytes) -> PreparedImage:
    if len(data) > MAX_UPLOAD_BYTES:
        raise InputError("image_too_large", "That image is over 5 MB. Try a smaller screenshot.", status=413)
    if sniff(data) is None:
        raise InputError("invalid_image", "Asli can read PNG, JPG or WebP screenshots only.", status=415)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                probe.verify()
            img = Image.open(io.BytesIO(data))
            img.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise InputError("invalid_image", "That image is too large to process.", status=413) from None
    except Exception:
        raise InputError("invalid_image", "That file doesn't look like a valid image.", status=415) from None

    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    llm_jpeg = _encode(img, LLM_MAX_EDGE, 85)
    edge, quality = SERP_MAX_EDGE, 85
    serp_jpeg = _encode(img, edge, quality)
    while len(serp_jpeg) > SERP_MAX_BYTES:
        if quality > 45:
            quality -= 10
        else:
            edge = int(edge * 0.8)
        serp_jpeg = _encode(img, edge, quality)

    return PreparedImage(
        llm_jpeg=llm_jpeg,
        serp_jpeg=serp_jpeg,
        sha256=hashlib.sha256(data).hexdigest(),
        width=img.width,
        height=img.height,
    )
