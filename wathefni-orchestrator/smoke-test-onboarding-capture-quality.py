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
    draw.rounded_rectangle((80, 60, w - 80, h - 60), radius=18, fill=(214, 216, 220), outline=(40, 40, 50), width=3)
    draw.rectangle((110, 100, 340, 360), fill=(170, 180, 190), outline=(30, 30, 30), width=2)
    for i, text in enumerate(
        ["CIVIL ID", "ABDULAZIZ H R ALMULLA", "302082900873", "DOB 2002-08-29", "EXP 2026-11-17"]
    ):
        draw.text((380, 120 + i * 42), text, fill=(20, 20, 20))
    for y in range(420, 540, 3):
        draw.line((380, y, w - 120, y), fill=(60, 60, 70))
    return np.asarray(img, dtype=np.uint8)


def _verify_ok(*_a, **_k):
    return {
        "detected_item": "civil_id",
        "matches_expected_item": True,
        "confidence": 0.95,
        "extraction_status": "extracted",
    }


def _identity_ok(**_k):
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


def _emp() -> dict:
    return {"employee_key": "WATHEFNI-96599338566", "company_code": "WATHEFNI", "name": "W5C-SYNTH|Aziz Mobile QA"}


def test_assess_levels(tmpdir: Path) -> None:
    clear = tmpdir / "clear.jpg"
    _save(_doc_card(), clear)
    clear_a = cq.assess_capture_quality(path=clear, extension=".jpg")
    check("clear status clean", clear_a.get("status") == "clean", clear_a)
    check("clear crop_signal none", (clear_a.get("metrics") or {}).get("crop_signal") == "none", clear_a)

    blur_img = Image.fromarray(_doc_card()).filter(ImageFilter.GaussianBlur(radius=8))
    blur = tmpdir / "blur.jpg"
    blur_img.save(blur, format="JPEG", quality=85)
    blur_a = cq.assess_capture_quality(path=blur, extension=".jpg")
    check("blur rejects or borderline", blur_a.get("status") in {"reject", "borderline"}, blur_a)
    if blur_a.get("status") == "reject":
        check("blur reason too_blurry", blur_a.get("reason") == "too_blurry", blur_a)

    glare_arr = _doc_card().astype(np.float32)
    glare_arr[:, :, :] = np.maximum(glare_arr, 252)
    glare_arr[80:560, 100:900, :] = 255
    glare = tmpdir / "glare.jpg"
    _save(glare_arr, glare)
    glare_a = cq.assess_capture_quality(path=glare, extension=".jpg")
    check("glare rejects", glare_a.get("status") == "reject", glare_a)
    check("glare reason", glare_a.get("reason") == "glare_or_shadow", glare_a)

    # Frame-filling / edge-touching: weak crop signal only — NOT hard reject.
    crop_src = _doc_card(1000, 640)
    cropped = crop_src[60:580, 80:920]
    crop_img = Image.fromarray(cropped).resize((1000, 640), Image.Resampling.BILINEAR)
    crop = tmpdir / "frame_fill.jpg"
    crop_img.save(crop, format="JPEG", quality=90)
    crop_a = cq.assess_capture_quality(path=crop, extension=".jpg")
    check("frame-fill not hard reject", crop_a.get("status") != "reject", crop_a)
    check("frame-fill not crop reason", crop_a.get("reason") != "document_not_fully_visible", crop_a)
    check(
        "frame-fill weak crop signal",
        (crop_a.get("metrics") or {}).get("crop_signal") == "weak"
        or int((crop_a.get("metrics") or {}).get("crop_hot_sides") or 0) >= cq.CROP_WEAK_SIDES,
        crop_a,
    )

    tiny = tmpdir / "tiny.jpg"
    Image.fromarray(_doc_card()).resize((240, 150)).save(tiny, format="JPEG", quality=90)
    tiny_a = cq.assess_capture_quality(path=tiny, extension=".jpg")
    check("tiny rejects", tiny_a.get("status") == "reject", tiny_a)
    check("tiny reason resolution", tiny_a.get("reason") == "resolution_too_low", tiny_a)

    mild = tmpdir / "mild_blur.jpg"
    Image.fromarray(_doc_card()).filter(ImageFilter.GaussianBlur(radius=1.6)).save(mild, format="JPEG", quality=90)
    mild_a = cq.assess_capture_quality(path=mild, extension=".jpg")
    check("mild blur borderline", mild_a.get("status") == "borderline", mild_a)
    check("mild blur HR reason", mild_a.get("reason") == "capture_quality_borderline", mild_a)


def test_gate_crop_contract(tmpdir: Path) -> None:
    os.environ[v.FLAG_SOFT] = "on"
    os.environ[v.FLAG_HARD] = "off"
    os.environ[v.FLAG_COMPANIES] = "WATHEFNI"
    os.environ[v.FLAG_ALLOWLIST] = "WATHEFNI-96599338566"
    emp = _emp()

    inset = tmpdir / "inset.jpg"
    _save(_doc_card(), inset)

    frame = tmpdir / "frame.jpg"
    fill = np.asarray(_doc_card())[60:580, 80:920]
    Image.fromarray(fill).resize((1000, 640), Image.Resampling.BILINEAR).save(frame, format="JPEG", quality=90)

    # Edge-touching: card flush to one/two edges but still complete OCR.
    edge = tmpdir / "edge.jpg"
    card = _doc_card()
    edge_arr = np.full_like(card, 168)
    edge_arr[0:580, 0:920] = card[60:640, 80:1000][:580, :920]
    _save(edge_arr, edge)

    cutoff = tmpdir / "cutoff.jpg"
    Image.fromarray(_doc_card()[60:580, 80:920]).resize((1000, 640)).save(cutoff, format="JPEG", quality=90)

    inset_r = v.evaluate_employee_upload(
        employee=emp,
        item_id="civil_id",
        media={"path": str(inset), "type": "image/jpeg"},
        filename="inset.jpg",
        size_bytes=inset.stat().st_size,
        extension=".jpg",
        verify_fn=_verify_ok,
        identity_fn=_identity_ok,
    )
    check("clear inset allows", inset_r.get("decision") == "allow", inset_r)

    frame_r = v.evaluate_employee_upload(
        employee=emp,
        item_id="civil_id",
        media={"path": str(frame), "type": "image/jpeg"},
        filename="frame.jpg",
        size_bytes=frame.stat().st_size,
        extension=".jpg",
        verify_fn=_verify_ok,
        identity_fn=_identity_ok,
    )
    check("clear frame-filling allows", frame_r.get("decision") == "allow", frame_r)
    check("frame-fill not document_not_fully_visible", frame_r.get("reason") != "document_not_fully_visible", frame_r)

    edge_r = v.evaluate_employee_upload(
        employee=emp,
        item_id="civil_id",
        media={"path": str(edge), "type": "image/jpeg"},
        filename="edge.jpg",
        size_bytes=edge.stat().st_size,
        extension=".jpg",
        verify_fn=_verify_ok,
        identity_fn=_identity_ok,
    )
    check("edge-touching valid allows", edge_r.get("decision") == "allow", edge_r)

    def verify_partial(*_a, **_k):
        return {
            "detected_item": "civil_id",
            "matches_expected_item": False,
            "confidence": 0.42,
            "extraction_status": "needs_review",
            "unreadable_reason": "cropped / not fully visible",
            "document_number": "302",
            "full_name": "AB",
        }

    cutoff_r = v.evaluate_employee_upload(
        employee=emp,
        item_id="civil_id",
        media={"path": str(cutoff), "type": "image/jpeg"},
        filename="cutoff.jpg",
        size_bytes=cutoff.stat().st_size,
        extension=".jpg",
        verify_fn=verify_partial,
        identity_fn=lambda **_k: (False, "needs_review", {"gpt_used": False, "confidence": 0.4}),
    )
    check("genuinely cut-off blocks", v.should_block(cutoff_r), cutoff_r)
    check(
        "cut-off reason document_not_fully_visible",
        cutoff_r.get("reason") == "document_not_fully_visible",
        cutoff_r.get("reason"),
    )

    def verify_back(*_a, **_k):
        return {
            "detected_item": "civil_id",
            "matches_expected_item": True,
            "confidence": 0.9,
            "extraction_status": "extracted",
            "side": "back",
        }

    def identity_back(**_k):
        return (
            True,
            None,
            {
                "extraction_status": "extracted",
                "confidence": 0.9,
                "full_name": "ABDULAZIZ H R ALMULLA",
                "document_number": "302082900873",
                "side": "back",
                "expiry_date": "2027-01-01",
                "identity_check": {"match": True, "status": "matched"},
                "gpt_used": False,
            },
        )

    missing = v.evaluate_employee_upload(
        employee=emp,
        item_id="civil_id",
        media={"path": str(inset), "type": "image/jpeg"},
        filename="back.jpg",
        size_bytes=inset.stat().st_size,
        extension=".jpg",
        verify_fn=verify_back,
        identity_fn=identity_back,
    )
    check("missing side blocks", v.should_block(missing), missing)
    check("missing_side reason", missing.get("reason") == "missing_side", missing.get("reason"))

    blur = tmpdir / "gate_blur.jpg"
    Image.fromarray(_doc_card()).filter(ImageFilter.GaussianBlur(radius=10)).save(blur, format="JPEG", quality=80)
    blur_r = v.evaluate_employee_upload(
        employee=emp,
        item_id="civil_id",
        media={"path": str(blur), "type": "image/jpeg"},
        filename="blur.jpg",
        size_bytes=blur.stat().st_size,
        extension=".jpg",
        verify_fn=_verify_ok,
        identity_fn=_identity_ok,
    )
    check("severe blur still blocks", v.should_block(blur_r), blur_r)
    check("severe blur reason too_blurry", blur_r.get("reason") == "too_blurry", blur_r.get("reason"))

    glare_arr = _doc_card().astype(np.float32)
    glare_arr[:, :, :] = 255
    nondoc = tmpdir / "random_nondoc_glare.jpg"
    _save(glare_arr, nondoc)

    def verify_lifestyle(*_a, **_k):
        return {
            "detected_item": "lifestyle",
            "matches_expected_item": False,
            "confidence": 0.91,
            "extraction_status": "extracted",
        }

    nondoc_r = v.evaluate_employee_upload(
        employee=emp,
        item_id="civil_id",
        media={"path": str(nondoc), "type": "image/jpeg"},
        filename="random.jpg",
        size_bytes=nondoc.stat().st_size,
        extension=".jpg",
        verify_fn=verify_lifestyle,
        identity_fn=_identity_ok,
    )
    check("nondoc wrong-document wins", nondoc_r.get("reason") in {"looks_like_photo_not_document", "not_a_document"}, nondoc_r)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="capq-") as td:
        tmp = Path(td)
        test_assess_levels(tmp)
        test_gate_crop_contract(tmp)
    print("OK onboarding capture quality smoke")


if __name__ == "__main__":
    main()
