#!/usr/bin/env python3
"""Non-production AnyDoc audit harness for Wathefni document foundation research."""
from __future__ import annotations

import hashlib
import json
import os
import re
import resource
import subprocess
import time
import traceback
from pathlib import Path

import anydoc

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus"
OUT = ROOT / "results"
OUT.mkdir(parents=True, exist_ok=True)

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def metrics(text: str | None) -> dict:
    if text is None:
        return {"chars": 0, "words": 0, "arabic_chars": 0, "lines": 0, "has_table_md": False, "has_heading_md": False}
    words = re.findall(r"\S+", text)
    return {
        "chars": len(text),
        "words": len(words),
        "arabic_chars": len(ARABIC_RE.findall(text)),
        "lines": text.count("\n") + 1,
        "has_table_md": "|" in text and "---" in text,
        "has_heading_md": bool(re.search(r"(?m)^#{1,6}\s", text)),
        "sha256": hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest(),
    }


def rss_mb() -> float:
    # macOS ru_maxrss is bytes
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


def run_anydoc(path: Path) -> dict:
    t0 = time.perf_counter()
    try:
        md = anydoc.to_markdown(str(path))
        ms = (time.perf_counter() - t0) * 1000
        return {"ok": True, "ms": ms, "error": None, "text": md, **metrics(md)}
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return {"ok": False, "ms": ms, "error": f"{type(e).__name__}: {e}", "text": None, **metrics(None)}


def run_pdf_inspector(path: Path) -> dict | None:
    if path.suffix.lower() != ".pdf":
        return None
    try:
        import pdf_inspector as pi
    except Exception as e:
        return {"ok": False, "ms": 0, "error": f"import:{e}", "text": None, **metrics(None)}
    t0 = time.perf_counter()
    try:
        # Prefer process_pdf_bytes / process_pdf depending on binding
        if hasattr(pi, "process_pdf_bytes"):
            result = pi.process_pdf_bytes(path.read_bytes())
        elif hasattr(pi, "process_pdf"):
            result = pi.process_pdf(str(path))
        else:
            return {"ok": False, "ms": 0, "error": "no process_pdf API", "text": None, **metrics(None)}
        ms = (time.perf_counter() - t0) * 1000
        md = getattr(result, "markdown", None)
        if md is None and isinstance(result, dict):
            md = result.get("markdown")
        pages_ocr = getattr(result, "pages_needing_ocr", None)
        if pages_ocr is None and isinstance(result, dict):
            pages_ocr = result.get("pages_needing_ocr")
        pdf_type = getattr(result, "pdf_type", None)
        if pdf_type is None and isinstance(result, dict):
            pdf_type = result.get("pdf_type")
        ok = bool(md and str(md).strip())
        out = {"ok": ok, "ms": ms, "error": None if ok else "empty_or_ocr_required", "text": md if ok else None, **metrics(md if ok else None)}
        out["pages_needing_ocr"] = list(pages_ocr) if pages_ocr is not None else None
        out["pdf_type"] = str(pdf_type) if pdf_type is not None else None
        return out
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return {"ok": False, "ms": ms, "error": f"{type(e).__name__}: {e}", "text": None, **metrics(None)}


def run_pdftotext(path: Path) -> dict | None:
    if path.suffix.lower() != ".pdf":
        return None
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        ms = (time.perf_counter() - t0) * 1000
        if proc.returncode != 0:
            return {"ok": False, "ms": ms, "error": proc.stderr.strip()[:300], "text": None, **metrics(None)}
        text = proc.stdout or ""
        return {"ok": bool(text.strip()), "ms": ms, "error": None if text.strip() else "empty", "text": text, **metrics(text)}
    except FileNotFoundError:
        return {"ok": False, "ms": 0, "error": "pdftotext_missing", "text": None, **metrics(None)}
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return {"ok": False, "ms": ms, "error": f"{type(e).__name__}: {e}", "text": None, **metrics(None)}


def classify_case(path: Path) -> str:
    name = path.name.lower()
    if "malformed" in str(path) or "stub" in name or "truncated" in name or "not_a_" in name or "zip_bomb" in name:
        return "malformed_or_stub"
    if "scan" in name or "image_only" in name:
        return "scanned_or_image"
    if "mixed" in name:
        return "mixed"
    if path.suffix.lower() == ".pdf":
        return "pdf_textish"
    return path.suffix.lower().lstrip(".") or "unknown"


def main() -> int:
    files = sorted(
        [p for p in CORPUS.rglob("*") if p.is_file() and p.name != "_scan.png" and not p.name.startswith(".")]
    )
    rows = []
    samples = {}
    rss_before = rss_mb()
    for path in files:
        rel = str(path.relative_to(CORPUS))
        case = classify_case(path)
        row = {
            "file": rel,
            "ext": path.suffix.lower(),
            "case": case,
            "bytes": path.stat().st_size,
            "content_sha256": sha256(path),
            "format_detect": None,
        }
        try:
            fmt = anydoc.format_from_path(str(path))
            row["format_detect"] = str(fmt) if fmt is not None else None
        except Exception as e:
            row["format_detect_error"] = str(e)

        any_res = run_anydoc(path)
        # Drop full text from row; keep snippet separately for Arabic evidence
        snippet = (any_res.get("text") or "")[:500]
        row["anydoc"] = {k: v for k, v in any_res.items() if k != "text"}
        if any_res.get("arabic_chars", 0) > 0 or "ar" in path.name.lower():
            samples[rel] = {"anydoc_snippet": snippet}

        pi_res = run_pdf_inspector(path)
        if pi_res:
            if pi_res.get("arabic_chars", 0) > 0 or "ar" in path.name.lower():
                samples.setdefault(rel, {})["pdf_inspector_snippet"] = (pi_res.get("text") or "")[:500]
            row["pdf_inspector_0_2_6"] = {k: v for k, v in pi_res.items() if k != "text"}

        pop = run_pdftotext(path)
        if pop:
            if pop.get("arabic_chars", 0) > 0 or "ar" in path.name.lower():
                samples.setdefault(rel, {})["pdftotext_snippet"] = (pop.get("text") or "")[:500]
            row["pdftotext"] = {k: v for k, v in pop.items() if k != "text"}

        # Determinism: second anydoc pass
        if any_res.get("ok"):
            again = run_anydoc(path)
            row["anydoc_deterministic"] = again.get("sha256") == any_res.get("sha256")
        rows.append(row)
        print(f"{'OK' if any_res.get('ok') else 'FAIL':4} {any_res.get('ms',0):8.2f}ms  {rel}  err={any_res.get('error')}")

    summary = {
        "corpus_files": len(rows),
        "anydoc_ok": sum(1 for r in rows if r["anydoc"].get("ok")),
        "anydoc_fail": sum(1 for r in rows if not r["anydoc"].get("ok")),
        "rss_max_mb_approx": rss_mb(),
        "rss_delta_mb_approx": rss_mb() - rss_before,
        "median_ok_ms": None,
    }
    ok_ms = sorted(r["anydoc"]["ms"] for r in rows if r["anydoc"].get("ok"))
    if ok_ms:
        summary["median_ok_ms"] = ok_ms[len(ok_ms) // 2]
        summary["p95_ok_ms"] = ok_ms[min(len(ok_ms) - 1, int(len(ok_ms) * 0.95))]
        summary["max_ok_ms"] = ok_ms[-1]

    # Format matrix rollup
    by_ext: dict[str, dict] = {}
    for r in rows:
        ext = r["ext"] or "(none)"
        bucket = by_ext.setdefault(ext, {"n": 0, "ok": 0, "fail": 0, "median_ms": []})
        bucket["n"] += 1
        if r["anydoc"].get("ok"):
            bucket["ok"] += 1
            bucket["median_ms"].append(r["anydoc"]["ms"])
        else:
            bucket["fail"] += 1
    for ext, b in by_ext.items():
        ms = sorted(b["median_ms"])
        b["median_ms"] = ms[len(ms) // 2] if ms else None
        b["errors"] = [r["anydoc"].get("error") for r in rows if r["ext"] == ext and not r["anydoc"].get("ok")]

    report = {
        "contract": "anydoc_technical_audit_nonprod_20260804",
        "anydoc_package": "firecrawl-anydoc==0.1.2",
        "pdf_inspector_compare": "0.2.6 (Wathefni pin; AnyDoc Rust crate pins 0.1.7 internally)",
        "summary": summary,
        "by_extension": by_ext,
        "rows": rows,
        "arabic_bilingual_samples": samples,
    }
    (OUT / "benchmark.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    # compact CSV-ish markdown table
    lines = ["| file | case | anydoc | ms | chars | ar | pi | poppler |", "|---|---|---|---:|---:|---:|---|---|"]
    for r in rows:
        a = r["anydoc"]
        pi = r.get("pdf_inspector_0_2_6") or {}
        pop = r.get("pdftotext") or {}
        lines.append(
            f"| `{r['file']}` | {r['case']} | {'OK' if a.get('ok') else 'FAIL'} | {a.get('ms',0):.1f} | {a.get('chars',0)} | {a.get('arabic_chars',0)} | "
            f"{'OK' if pi.get('ok') else ('FAIL' if pi else '—')} | {'OK' if pop.get('ok') else ('FAIL' if pop else '—')} |"
        )
    (OUT / "benchmark_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("WROTE", OUT / "benchmark.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
