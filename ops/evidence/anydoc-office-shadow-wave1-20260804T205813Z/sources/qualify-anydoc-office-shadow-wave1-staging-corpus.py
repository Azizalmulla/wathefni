#!/usr/bin/env python3
"""Offline corpus qualify for AnyDoc office shadow — staging_shadow mode.

Compares AnyDoc observation to current authoritative readers without changing authority.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "wathefni-orchestrator"
sys.path.insert(0, str(ORCH))

os.environ["WATHEFNI_ANYDOC_OFFICE_SHADOW"] = "staging_shadow"
os.environ.setdefault("WATHEFNI_ANYDOC_OFFICE_SHADOW_TIMEOUT_MS", "5000")

import anydoc_office_shadow as shadow  # noqa: E402

CORPUS = ROOT / "ops/evidence/anydoc-technical-audit-20260804/corpus"
OFFICIAL = ROOT / "ops/evidence/anydoc-technical-audit-20260804/research/anydoc/tests/fixtures"
OUT_DIR = Path(os.environ.get("ANYDOC_SHADOW_OUT") or ROOT / "ops/evidence/anydoc-office-shadow-wave1-local")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def auth_text_for(path: Path) -> str:
    """Best-effort current authoritative extract (local, no OCR, no network)."""
    ext = path.suffix.lower()
    try:
        if ext == ".docx":
            import cv_docx

            # Local parse only — never invoke embedded-image OCR in this qualify harness.
            blocks, _images, _meta = cv_docx.parse_docx_local(path)
            return cv_docx.blocks_to_text(blocks)
        if ext in {".csv", ".txt", ".md", ".rtf"}:
            return path.read_text(errors="ignore")
        if ext == ".xlsx":
            try:
                from openpyxl import load_workbook

                wb = load_workbook(path, read_only=True, data_only=True)
                rows = []
                for ws in wb.worksheets:
                    for row in ws.iter_rows(values_only=True):
                        rows.append("\t".join("" if c is None else str(c) for c in row))
                return "\n".join(rows)
            except Exception:
                return ""
        if ext in {".pptx", ".ppt", ".odt", ".ods", ".odp", ".doc", ".xls"}:
            return ""
    except Exception:
        return ""
    return ""


def collect_files() -> list[Path]:
    files: list[Path] = []
    # Prefer generated bilingual corpus + a light official subset (skip abuse/malformed for p95).
    generated = CORPUS / "generated"
    if generated.exists():
        for p in sorted(generated.rglob("*")):
            if p.is_file() and p.suffix.lower() in shadow.ALLOWED_EXTENSIONS:
                files.append(p)
    for rel in (
        "docx/text.docx",
        "docx/handmade-tables.docx",
        "pptx/pres.pptx",
        "xlsx/sheet.xlsx",
        "xlsx/handmade-merged.xlsx",
        "csv/sheet.csv",
        "rtf/text.rtf",
        "odt/text.odt",
        "ods/sheet.ods",
        "odp/pres.odp",
        "doc/text.doc",
        "ppt/pres.ppt",
        "xls/sheet.xls",
    ):
        p = OFFICIAL / rel
        if p.exists():
            files.append(p)
    # A few malformed/abuse to prove fail-open (bounded)
    for rel in (
        "malformed/truncated--errors.docx",
        "abuse/zipbomb--errors.docx",
        "abuse/deepxml--errors.docx",
    ):
        p = OFFICIAL / rel
        if p.exists():
            files.append(p)
    seen = set()
    out = []
    for p in files:
        key = (str(p.resolve()), p.stat().st_size)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def main() -> int:
    rows = []
    arabic_evidence = {}
    for path in collect_files():
        auth = auth_text_for(path)
        t0 = time.perf_counter()
        obs = shadow.run_anydoc_office_shadow(
            path,
            authoritative_text=auth,
            company_code="WATHEFNI",
        )
        # Determinism
        det = None
        if obs.get("ok") and obs.get("output_sha256"):
            again = shadow.run_anydoc_office_shadow(path, authoritative_text=auth, company_code="WATHEFNI")
            det = again.get("output_sha256") == obs.get("output_sha256")
        row = {
            "file": str(path),
            "ext": path.suffix.lower(),
            "auth_chars": len(auth),
            "shadow": {k: v for k, v in obs.items() if k != "markdown"},
            "deterministic": det,
            "wall_ms_outer": int((time.perf_counter() - t0) * 1000),
        }
        rows.append(row)
        q = (obs.get("quality") or {})
        if int(q.get("arabic_chars") or 0) > 0 or "ar" in path.name.lower():
            arabic_evidence[path.name] = {
                "arabic_chars": q.get("arabic_chars"),
                "ok": obs.get("ok"),
                "quality_ok": q.get("ok"),
                "disagreement": (obs.get("comparison") or {}).get("disagreement_reasons"),
            }
        status = "OK" if obs.get("ok") else f"SKIP/FAIL:{obs.get('skipped') or obs.get('error')}"
        print(f"{status:40} {path.suffix:6} {obs.get('latency_ms')}ms  {path.name}")

    by_ext: dict[str, dict] = {}
    for r in rows:
        ext = r["ext"]
        b = by_ext.setdefault(ext, {"n": 0, "ok": 0, "fail_open": 0, "skipped": 0, "disagreements": 0, "latencies": []})
        b["n"] += 1
        sh = r["shadow"]
        if sh.get("skipped"):
            b["skipped"] += 1
        elif sh.get("ok"):
            b["ok"] += 1
            if sh.get("latency_ms") is not None:
                b["latencies"].append(sh["latency_ms"])
            if (sh.get("comparison") or {}).get("material_disagreement"):
                b["disagreements"] += 1
        elif sh.get("fail_open"):
            b["fail_open"] += 1
        else:
            b["fail_open"] += 1
    for ext, b in by_ext.items():
        ms = sorted(b["latencies"])
        b["median_ms"] = ms[len(ms) // 2] if ms else None
        b["p95_ms"] = ms[min(len(ms) - 1, int(len(ms) * 0.95))] if ms else None
        del b["latencies"]

    ok_rows = [r for r in rows if r["shadow"].get("ok")]
    material_disagreements = sum(
        1
        for r in ok_rows
        if (r["shadow"].get("comparison") or {}).get("material_disagreement")
    )
    summary = {
        "mode": "staging_shadow",
        "files": len(rows),
        "ok": len(ok_rows),
        "fail_open": sum(1 for r in rows if r["shadow"].get("fail_open")),
        "skipped": sum(1 for r in rows if r["shadow"].get("skipped")),
        "disagreements": material_disagreements,
        "informational_anydoc_only": sum(
            1
            for r in rows
            if "anydoc_only_no_auth_baseline"
            in ((r["shadow"].get("comparison") or {}).get("disagreement_reasons") or [])
        ),
        "deterministic_ok": sum(1 for r in rows if r.get("deterministic") is True),
        "deterministic_checked": sum(1 for r in rows if r.get("deterministic") is not None),
        "by_extension": by_ext,
        "influences_routing_always_false": all(
            r["shadow"].get("influences_routing") is False for r in rows
        ),
        "pinned_version": shadow.PINNED_VERSION,
    }
    (OUT_DIR / "staging_corpus_results.json").write_text(
        json.dumps({"summary": summary, "rows": rows, "arabic_evidence": arabic_evidence}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    print("ANYDOC_OFFICE_SHADOW_STAGING_CORPUS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
