#!/usr/bin/env python3
"""Smoke: lightweight onboarding capture-quality (PIL/NumPy only)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import onboarding_capture_quality as cq
import onboarding_doc_validation_parity as v


def check(name: str, cond: bool, detail: object = None) -> None:
    if cond:
        print(f"PASS {name}")
        return
    print(f"FAIL {name}: {detail}")
    raise SystemExit(1)


def _save(arr: np.ndarray, path: Path) -> None:
    Image.fromarray(arr.astype(np.uint8)).save(path, format="JPEG", quality=92)


def _doc_card(w: int = 1000, h: int = 640) -> np.ndarray:
    """Synthetic Civil-ID-like card with text edges and quiet margin."""
    img = Image.new("RGB", (w, h), (168, 172, 178))
    draw = ImageDraw.Draw(img)
    # Card body inset so clean photos have margins.
    draw.rounded_rectangle((80, 60, w - 80, h - 60), radius=18, fill=(214, 216, 220), outline=(40, 40, 50), width=3)
    draw.rectangle((110, 100, 340, 360), fill=(170, 180, 190), outline=(30, 30, 30), width=2)
    for i, text in enumerate(
        ["CIVIL ID", "ABDULAZIZ H R ALMULLA", "302082900873", "DOB 2002-08-29", "EXP 2026-11-17"]
    ):
        draw.text((380, 120 + i * 42), text, fill=(20, 20, 20))
    # Fine detail lines for sharpness signal.
    for y in range(420, 540, 3):
        draw.line((380, y, w - 120, y), fill=(60, 60, 70))
    return np.asarray(img, dtype=np.uint8)


def test_assess_levels(tmpdir: Path) -> None:
    clear = tmpdir / "clear.jpg"
    _save(_doc_card(), clear)
    clear_a = cq.assess_capture_quality(path=clear, extension=".jpg")
    check("clear status clean", clear_a.get("status") == "clean", clear_a)

    # Obvious blur
    blur_img = Image.fromarray(_doc_card()).filter(ImageFilter.GaussianBlur(radius=8))
    blur = tmpdir / "blur.jpg"
    blur_img.save(blur, format="JPEG", quality=85)
    blur_a = cq.assess_capture_quality(path=blur, extension=".jpg")
    check("blur rejects or borderline", blur_a.get("status") in {"reject", "borderline"}, blur_a)
    if blur_a.get("status") == "reject":
        check("blur reason too_blurry", blur_a.get("reason") == "too_blurry", blur_a)

    # Severe glare / overexposure
    glare_arr = _doc_card().astype(np.float32)
    glare_arr[:, :, :] = np.maximum(glare_arr, 252)
    glare_arr[80:560, 100:900, :] = 255
    glare = tmpdir / "glare.jpg"
    _save(glare_arr, glare)
    glare_a = cq.assess_capture_quality(path=glare, extension=".jpg")
    check("glare rejects", glare_a.get("status") == "reject", glare_a)
    check("glare reason", glare_a.get("reason") == "glare_or_shadow", glare_a)

    # Heavily cropped (content to all edges) — take the card body only, no desk margin.
    crop_src = _doc_card(1000, 640)
    cropped = crop_src[60:580, 80:920]
    crop_img = Image.fromarray(cropped).resize((1000, 640), Image.Resampling.BILINEAR)
    crop = tmpdir / "crop.jpg"
    crop_img.save(crop, format="JPEG", quality=90)
    crop_a = cq.assess_capture_quality(path=crop, extension=".jpg")
    check("crop reject or borderline", crop_a.get("status") in {"reject", "borderline"}, crop_a)

    # Tiny resolution
    tiny = tmpdir / "tiny.jpg"
    Image.fromarray(_doc_card()).resize((240, 150)).save(tiny, format="JPEG", quality=90)
    tiny_a = cq.assess_capture_quality(path=tiny, extension=".jpg")
    check("tiny rejects", tiny_a.get("status") == "reject", tiny_a)
    check("tiny reason resolution", tiny_a.get("reason") == "resolution_too_low", tiny_a)

    # Mild blur → borderline (HR), not hard reject
    mild = tmpdir / "mild_blur.jpg"
    Image.fromarray(_doc_card()).filter(ImageFilter.GaussianBlur(radius=1.6)).save(mild, format="JPEG", quality=90)
    mild_a = cq.assess_capture_quality(path=mild, extension=".jpg")
    check("mild blur borderline", mild_a.get("status") == "borderline", mild_a)
    check("mild blur HR reason", mild_a.get("reason") == "capture_quality_borderline", mild_a)


def test_gate_wiring(tmpdir: Path) -> None:
    os.environ[v.FLAG_SOFT] = "on"
    os.environ[v.FLAG_HARD] = "off"
    os.environ[v.FLAG_COMPANIES] = "WATHEFNI"
    os.environ[v.FLAG_ALLOWLIST] = "WATHEFNI-96599338566"

    clear = tmpdir / "gate_clear.jpg"
    _save(_doc_card(), clear)
    blur = tmpdir / "gate_blur.jpg"
    Image.fromarray(_doc_card()).filter(ImageFilter.GaussianBlur(radius=10)).save(blur, format="JPEG", quality=80)

    def verify_ok(*_a, **_k):
        return {
            "detected_item": "civil_id",
            "matches_expected_item": True,
            "confidence": 0.95,
            "extraction_status": "extracted",
        }

    def identity_ok(**_k):
        return (
            True,
            None,
            {
                "extraction_status": "extracted",
                "confidence": 0.95,
                "full_name": "ABDULAZIZ H R ALMULLA",
                "document_number": "302082900873",
                "expiry_date": "2027-01-01",
                "identity_check": {"match": True, "status": "matched"},
                "gpt_used": False,
            },
        )

    emp = {"employee_key": "WATHEFNI-96599338566", "company_code": "WATHEFNI", "name": "W5C-SYNTH|Aziz Mobile QA"}
    clear_r = v.evaluate_employee_upload(
        employee=emp,
        item_id="civil_id",
        media={"path": str(clear), "type": "image/jpeg"},
        filename="clear.jpg",
        size_bytes=clear.stat().st_size,
        extension=".jpg",
        verify_fn=verify_ok,
        identity_fn=identity_ok,
    )
    check("clear gate allows", clear_r.get("decision") == "allow", clear_r)
    check("clear capture clean", (clear_r.get("capture_quality") or {}).get("status") == "clean", clear_r.get("capture_quality"))

    blur_r = v.evaluate_employee_upload(
        employee=emp,
        item_id="civil_id",
        media={"path": str(blur), "type": "image/jpeg"},
        filename="blur.jpg",
        size_bytes=blur.stat().st_size,
        extension=".jpg",
        verify_fn=verify_ok,
        identity_fn=identity_ok,
    )
    check("severe blur blocks before/without needing mistral mismatch", v.should_block(blur_r), blur_r)
    check("severe blur reason too_blurry", blur_r.get("reason") == "too_blurry", blur_r.get("reason"))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="capq-") as td:
        tmp = Path(td)
        test_assess_levels(tmp)
        test_gate_wiring(tmp)
    print("OK onboarding capture quality smoke")


if __name__ == "__main__":
    main()
