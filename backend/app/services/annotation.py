"""Screenshot annotation using Pillow.

Given a full-page screenshot and a bounding box, produces a cropped + labeled
image highlighting the issue region. Severity controls the box color so the
annotated artifact is readable at a glance.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from ..core.logging import get_logger
from ..utils.paths import annotations_dir

_log = get_logger(__name__)

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = None  # type: ignore

SEVERITY_COLORS = {
    "critical": (220, 38, 38),   # red
    "serious": (234, 88, 12),    # orange
    "moderate": (234, 179, 8),   # amber
    "minor": (59, 130, 246),     # blue
}


@dataclass
class AnnotationResult:
    annotated_path: Optional[str]
    bbox: Optional[Dict[str, float]]


def _load_font(size: int = 16):
    # Pillow ships a default font; keep things dependency-free.
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except Exception:
        return ImageFont.load_default()


def annotate_finding(
    *,
    screenshot_path: str,
    bbox: Dict[str, float],
    rule_id: str,
    severity: str,
    out_name: str,
    pad: int = 60,
) -> AnnotationResult:
    """Draw a highlight box on a copy of the screenshot and crop around it."""
    if Image is None:
        return AnnotationResult(annotated_path=None, bbox=bbox)

    try:
        src = Image.open(screenshot_path).convert("RGB")
    except Exception as e:
        _log.warning("could not open screenshot %s: %s", screenshot_path, e)
        return AnnotationResult(annotated_path=None, bbox=bbox)

    color = SEVERITY_COLORS.get(severity, SEVERITY_COLORS["minor"])
    x, y = float(bbox.get("x", 0)), float(bbox.get("y", 0))
    w, h = float(bbox.get("width", 0)), float(bbox.get("height", 0))
    if w <= 0 or h <= 0:
        return AnnotationResult(annotated_path=None, bbox=bbox)

    draw = ImageDraw.Draw(src)
    draw.rectangle([x, y, x + w, y + h], outline=color, width=4)

    # Label box.
    label = f"{severity.upper()} · {rule_id}"
    font = _load_font(16)
    tbox = draw.textbbox((0, 0), label, font=font)
    tw, th = tbox[2] - tbox[0], tbox[3] - tbox[1]
    lx, ly = x, max(0, y - th - 8)
    draw.rectangle([lx, ly, lx + tw + 10, ly + th + 6], fill=color)
    draw.text((lx + 5, ly + 3), label, fill=(255, 255, 255), font=font)

    # Crop to a readable window around the element.
    cw, ch = src.size
    crop_box = (
        max(0, int(x - pad)),
        max(0, int(y - pad - th)),
        min(cw, int(x + w + pad)),
        min(ch, int(y + h + pad)),
    )
    cropped = src.crop(crop_box)

    out = annotations_dir() / out_name
    try:
        cropped.save(out, "PNG", optimize=True)
    except Exception as e:
        _log.warning("could not save annotation %s: %s", out, e)
        return AnnotationResult(annotated_path=None, bbox=bbox)

    return AnnotationResult(annotated_path=str(out), bbox=bbox)
