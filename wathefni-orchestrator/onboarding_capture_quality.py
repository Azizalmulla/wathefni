#!/usr/bin/env python3
"""Lightweight local capture-quality checks for onboarding document photos.

PIL + NumPy only. No GPT, OpenCV, or paid KYC SDKs.

Outcomes (conservative — prefer low false rejection):
  reject     → clearly bad / fixable capture (ask retake)
  borderline → imperfect but likely readable (HR review)
  clean      → continue normal validation

Crop / frame-fill (`crop_hot_sides`) is a **weak supporting signal only**.
It never hard-rejects or borderlines by itself — callers must combine it with
OCR/side/page/partial evidence before blocking as cut-off.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("wathefni.onboarding_capture_quality")

# Resolution (short side / long side in px after EXIF transpose)
MIN_SHORT_REJECT = 360
MIN_SHORT_BORDERLINE = 520
MIN_LONG_REJECT = 480

# Laplacian variance (higher = sharper). Conservative — only severe blur hard-rejects.
BLUR_REJECT_MAX = 6.0
BLUR_BORDERLINE_MAX = 40.0

# Fraction of near-white pixels (glare / overexposure).
# Conservative: only severe clipped whites count as glare.
GLARE_REJECT_MIN = 0.28
GLARE_BORDERLINE_MIN = 0.18
GLARE_VALUE = 250

# Border content energy — weak crop signal only (never standalone hard block).
CROP_WEAK_SIDES = 2
CROP_BORDER_FRAC = 0.04
CROP_ENERGY_RATIO = 0.55


def _media_path(media: dict[str, Any] | None) -> Path | None:
    if not isinstance(media, dict):
        return None
    raw = str(
        media.get("path")
        or media.get("local_path")
        or media.get("source_path")
        or ""
    ).strip()
    if not raw or raw.startswith(("http://", "https://", "data:")):
        return None
    path = Path(raw)
    if not path.is_file():
        return None
    return path


def _load_rgb(path: Path):
    from PIL import Image, ImageOps
    import numpy as np

    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode not in {"RGB", "L"}:
            img = img.convert("RGB")
        elif img.mode == "L":
            img = img.convert("RGB")
        arr = np.asarray(img, dtype=np.float32)
    if arr.ndim != 3 or arr.shape[2] < 3:
        raise ValueError("unsupported_image_shape")
    return arr


def _laplacian_variance(gray) -> float:
    import numpy as np

    # 3x3 Laplacian without OpenCV.
    padded = np.pad(gray, 1, mode="edge")
    center = padded[1:-1, 1:-1]
    up = padded[:-2, 1:-1]
    down = padded[2:, 1:-1]
    left = padded[1:-1, :-2]
    right = padded[1:-1, 2:]
    lap = (up + down + left + right) - (4.0 * center)
    return float(lap.var())


def _border_content_sides(gray, *, border_frac: float = CROP_BORDER_FRAC) -> int:
    """Count sides where border strip has high content energy (weak crop signal)."""
    import numpy as np

    h, w = gray.shape
    by = max(2, int(h * border_frac))
    bx = max(2, int(w * border_frac))
    interior = gray[by : h - by, bx : w - bx]
    if interior.size < 16:
        return 0
    interior_std = float(interior.std()) + 1e-6

    strips = {
        "top": gray[:by, :],
        "bottom": gray[h - by :, :],
        "left": gray[:, :bx],
        "right": gray[:, w - bx :],
    }
    hot = 0
    for strip in strips.values():
        std = float(strip.std())
        # Quiet desk/margin borders are low-std; text/photo at the edge is high-std.
        if std >= 28.0 or (std / interior_std >= CROP_ENERGY_RATIO and std > 14.0):
            hot += 1
    return hot


def assess_capture_quality(
    *,
    media: dict[str, Any] | None = None,
    path: str | Path | None = None,
    extension: str | None = None,
) -> dict[str, Any]:
    """Return capture-quality assessment for an image upload."""
    ext = (extension or "").lower()
    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".tif", ".tiff", ".bmp"}
    resolved = Path(path) if path else _media_path(media)
    if ext and ext not in image_exts:
        return {
            "status": "skip",
            "reason": None,
            "metrics": {"skipped": "non_image"},
            "engine": "pil_numpy_v1",
        }
    if resolved is None:
        if media and str(media.get("type") or "").startswith("image/"):
            return {
                "status": "skip",
                "reason": None,
                "metrics": {"skipped": "missing_path"},
                "engine": "pil_numpy_v1",
            }
        return {
            "status": "skip",
            "reason": None,
            "metrics": {"skipped": "no_media"},
            "engine": "pil_numpy_v1",
        }

    try:
        import numpy as np

        rgb = _load_rgb(resolved)
        h, w = int(rgb.shape[0]), int(rgb.shape[1])
        short_side, long_side = (w, h) if w < h else (h, w)
        gray = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]).astype(np.float32)
        blur_var = _laplacian_variance(gray)
        glare_frac = float(np.mean(gray >= GLARE_VALUE))
        crop_sides = _border_content_sides(gray)
        metrics = {
            "width": w,
            "height": h,
            "short_side": short_side,
            "long_side": long_side,
            "laplacian_var": round(blur_var, 3),
            "glare_frac": round(glare_frac, 4),
            "crop_hot_sides": crop_sides,
            "crop_signal": "weak" if crop_sides >= CROP_WEAK_SIDES else "none",
        }
    except Exception as exc:
        logger.exception("capture quality assess failed path=%s", resolved)
        return {
            "status": "skip",
            "reason": None,
            "metrics": {"error": str(exc)[:160]},
            "engine": "pil_numpy_v1",
        }

    # Reject: clearly bad / fixable (resolution → glare → blur). Crop is never standalone.
    if short_side < MIN_SHORT_REJECT or long_side < MIN_LONG_REJECT:
        return {"status": "reject", "reason": "resolution_too_low", "metrics": metrics, "engine": "pil_numpy_v1"}
    if glare_frac >= GLARE_REJECT_MIN:
        return {"status": "reject", "reason": "glare_or_shadow", "metrics": metrics, "engine": "pil_numpy_v1"}
    if blur_var < BLUR_REJECT_MAX:
        return {"status": "reject", "reason": "too_blurry", "metrics": metrics, "engine": "pil_numpy_v1"}

    # Borderline: imperfect but possibly readable → HR (crop alone does not borderline).
    borderline_reason = None
    if short_side < MIN_SHORT_BORDERLINE:
        borderline_reason = "resolution_too_low"
    elif glare_frac >= GLARE_BORDERLINE_MIN:
        borderline_reason = "glare_or_shadow"
    elif blur_var < BLUR_BORDERLINE_MAX:
        borderline_reason = "too_blurry"

    if borderline_reason:
        return {
            "status": "borderline",
            "reason": "capture_quality_borderline",
            "signal_reason": borderline_reason,
            "metrics": metrics,
            "engine": "pil_numpy_v1",
        }

    return {"status": "clean", "reason": None, "metrics": metrics, "engine": "pil_numpy_v1"}
