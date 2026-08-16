#!/usr/bin/env python3
"""Shadow Advisor Wave 1 smoke — behavioral invariance + fail-open + p95 budget.

Does not call Mistral. Does not change OCR routing. CV PDFs only.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EVID = Path(
    os.environ.get(
        "PDF_INSPECTOR_SHADOW_EVID",
        "/Users/azizalmulla/Desktop/claw/ops/evidence/pdf-inspector-shadow-wave1-20260804",
    )
)
FIXTURE_ROOT = Path(
    os.environ.get(
        "PDF_INSPECTOR_WAVE0_FIXTURES",
        "/Users/azizalmulla/Desktop/claw/ops/evidence/pdf-inspector-deep-eval-wave0-20260804/fixtures",
    )
)


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> None:
    import cv_extraction as cv
    import pdf_inspector_shadow as shadow

    EVID.mkdir(parents=True, exist_ok=True)
    (EVID / "run.out").parent.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(FIXTURE_ROOT.glob("*.pdf"))
    assert_true(len(pdfs) >= 8, f"need wave0 fixtures, found {len(pdfs)} in {FIXTURE_ROOT}")

    # 1) Flag off — no shadow payload attached
    os.environ["WATHEFNI_PDF_INSPECTOR_SHADOW"] = "0"
    sample = next(p for p in pdfs if p.name.startswith("cv_en_digital_01"))
    off = cv.extract_cv_document(sample, mime_type="application/pdf", company_code="WATHEFNI")
    assert_true(
        "pdf_inspector_shadow" not in (off.metadata or {}),
        f"flag-off leaked shadow payload: {off.metadata}",
    )
    # 2) Flag on — shadow present, routing unchanged vs flag off
    os.environ["WATHEFNI_PDF_INSPECTOR_SHADOW"] = "1"
    os.environ["WATHEFNI_PDF_INSPECTOR_SHADOW_TIMEOUT_MS"] = "500"
    # Keep OCR off so we don't call paid APIs during smoke.
    os.environ["WATHEFNI_CV_MISTRAL_OCR"] = "0"

    behavioral_rows = []
    walls = []
    for path in pdfs:
        if path.stat().st_size < 100:
            continue
        os.environ["WATHEFNI_PDF_INSPECTOR_SHADOW"] = "0"
        a = cv.extract_cv_document(path, mime_type="application/pdf", company_code="WATHEFNI")
        os.environ["WATHEFNI_PDF_INSPECTOR_SHADOW"] = "1"
        t0 = time.perf_counter()
        b = cv.extract_cv_document(path, mime_type="application/pdf", company_code="WATHEFNI")
        wall = int((time.perf_counter() - t0) * 1000)
        sh = (b.metadata or {}).get("pdf_inspector_shadow") or {}
        # Behavioral invariance on authoritative outputs
        assert_true(a.method == b.method, f"{path.name} method changed {a.method}->{b.method}")
        assert_true(a.error == b.error, f"{path.name} error changed {a.error}->{b.error}")
        assert_true(
            [p.disposition for p in a.page_assessments] == [p.disposition for p in b.page_assessments],
            f"{path.name} page dispositions changed",
        )
        assert_true(
            (a.text or "") == (b.text or ""),
            f"{path.name} authoritative text changed under shadow",
        )
        assert_true(sh.get("enabled") is True, f"{path.name} shadow not enabled: {sh}")
        assert_true(sh.get("influences_ocr_routing") is False, f"{path.name} influences routing")
        shadow_wall = int(sh.get("wall_ms") or 0)
        if len(b.page_assessments) <= 10:
            walls.append(shadow_wall)
        behavioral_rows.append(
            {
                "file": path.name,
                "pages": len(b.page_assessments),
                "method": b.method,
                "shadow_ok": sh.get("ok"),
                "fail_open": sh.get("fail_open"),
                "wall_ms": shadow_wall,
                "extract_wall_ms": wall,
                "false_skip_candidates": (sh.get("comparison") or {}).get("false_skip_candidates_1idx"),
                "detections": (sh.get("comparison") or {}).get("detections"),
                "pdf_type": (sh.get("inspector") or {}).get("pdf_type"),
            }
        )

    assert_true(walls, "no wall samples")
    p95 = sorted(walls)[max(0, int(round(0.95 * (len(walls) - 1))))]
    p95_alt = statistics.quantiles(walls, n=20)[18] if len(walls) >= 20 else max(walls)
    p95_use = max(p95, int(p95_alt)) if len(walls) >= 20 else p95
    assert_true(p95_use <= 150, f"p95 shadow overhead {p95_use}ms > 150ms walls={walls}")

    # 3) Fail-open on timeout
    os.environ["WATHEFNI_PDF_INSPECTOR_SHADOW"] = "1"
    os.environ["WATHEFNI_PDF_INSPECTOR_SHADOW_TIMEOUT_MS"] = "1"

    def _slow(*_a, **_k):
        time.sleep(0.25)
        raise RuntimeError("should_have_timed_out")

    original = shadow._call_process_pdf
    shadow._call_process_pdf = _slow  # type: ignore[assignment]
    try:
        timed = cv.extract_cv_document(sample, mime_type="application/pdf", company_code="WATHEFNI")
    finally:
        shadow._call_process_pdf = original  # type: ignore[assignment]
        os.environ["WATHEFNI_PDF_INSPECTOR_SHADOW_TIMEOUT_MS"] = "500"
    sh_t = (timed.metadata or {}).get("pdf_inspector_shadow") or {}
    assert_true(sh_t.get("fail_open") is True, f"timeout did not fail open: {sh_t}")
    assert_true(sh_t.get("error") == "timeout", f"expected timeout error: {sh_t}")
    assert_true(timed.method == off.method, "timeout path changed method")
    assert_true((timed.text or "") == (off.text or ""), "timeout path changed text")

    # 4) Fail-open on import/runtime error
    def _boom(*_a, **_k):
        raise RuntimeError("injected_inspector_failure")

    shadow._call_process_pdf = _boom  # type: ignore[assignment]
    try:
        bombed = cv.extract_cv_document(sample, mime_type="application/pdf", company_code="WATHEFNI")
    finally:
        shadow._call_process_pdf = original  # type: ignore[assignment]
    sh_b = (bombed.metadata or {}).get("pdf_inspector_shadow") or {}
    assert_true(sh_b.get("fail_open") is True, f"error did not fail open: {sh_b}")
    assert_true((bombed.text or "") == (off.text or ""), "error path changed text")

    # 5) Detection metrics present for broken encoding fixture when available
    broken = FIXTURE_ROOT / "cv_broken_encoding_01.pdf"
    detection_note = None
    if broken.exists():
        os.environ["WATHEFNI_PDF_INSPECTOR_SHADOW"] = "1"
        br = cv.extract_cv_document(broken, mime_type="application/pdf", company_code="WATHEFNI")
        sh = (br.metadata or {}).get("pdf_inspector_shadow") or {}
        comp = sh.get("comparison") or {}
        detection_note = {
            "false_skip_candidates": comp.get("false_skip_candidates_1idx"),
            "high_risk_false_skip_candidate": comp.get("high_risk_false_skip_candidate"),
            "detections": comp.get("detections"),
            "influences_ocr_routing": sh.get("influences_ocr_routing"),
        }
        assert_true(sh.get("influences_ocr_routing") is False, "broken fixture must not influence routing")

    out = {
        "ok": True,
        "verdict": "PASS",
        "fixtures": len(behavioral_rows),
        "p95_shadow_wall_ms": p95_use,
        "max_shadow_wall_ms": max(walls),
        "mean_shadow_wall_ms": round(sum(walls) / len(walls), 2),
        "behavioral_invariance": True,
        "fail_open_timeout": True,
        "fail_open_error": True,
        "broken_encoding_observation": detection_note,
        "rows": behavioral_rows,
    }
    (EVID / "smoke-result.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print("PDF_INSPECTOR_SHADOW_WAVE1_SMOKE_PASS")


if __name__ == "__main__":
    main()
