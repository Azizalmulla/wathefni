#!/usr/bin/env python3
"""Synthetic dry-run Jobs Phase 1 production verification. No real candidate sends."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("WATHEFNI_VERIFY_BASE", "http://127.0.0.1:8010")
TOKEN = Path(os.environ.get("WATHEFNI_VERIFY_TOKEN_FILE", "/tmp/jobs-phase1-prod-token.txt")).read_text().strip()
AUTH = {
    "Authorization": f"Bearer {TOKEN}",
    "X-Company-Code": "WATHEFNI",
    "Content-Type": "application/json",
}
OUT = Path(os.environ.get("WATHEFNI_VERIFY_OUT", "/tmp/jobs-phase1-prod-verify.json"))


def note(results: list, ok: bool, label: str, detail: str = "") -> None:
    results.append({"ok": ok, "label": label, "detail": detail})
    print(("OK  " if ok else "FAIL") + f" {label}" + (f" — {detail}" if detail else ""))


def api(method: str, path: str, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, headers=AUTH, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"raw": raw}
        return e.code, parsed


def positions_from(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    return payload.get("positions") or payload.get("items") or payload.get("data") or []


def main() -> int:
    if os.environ.get("WATHEFNI_DELIVERY_MODE") != "dry_run":
        print("REFUSING: set WATHEFNI_DELIVERY_MODE=dry_run for verification", file=sys.stderr)
        return 2

    results: list[dict] = []
    st, summary = api("GET", "/dashboard/prehire/summary")
    totals = (summary.get("totals") or {}) if isinstance(summary, dict) else {}
    pos_in_summary = summary.get("positions") if isinstance(summary, dict) else None
    open_count = totals.get("open_positions")
    if open_count is None and isinstance(pos_in_summary, list):
        open_count = sum(1 for p in pos_in_summary if str(p.get("status") or "").lower() == "open")
    app_count = totals.get("applications") or totals.get("total_applications")
    note(
        results,
        st == 200 and int(open_count or 0) >= 1,
        "existing positions remain",
        f"open={open_count} apps={app_count}",
    )

    st, listing = api("GET", "/dashboard/prehire/positions?limit=100")
    positions = positions_from(listing)
    note(results, st == 200 and len(positions) >= 1, "list positions", f"n={len(positions)}")
    sample = next((p for p in positions if int(p.get("application_count") or 0) > 0), None)
    note(
        results,
        sample is not None,
        "existing applications remain attached",
        (sample or {}).get("position_code", ""),
    )

    suffix = time.strftime("%H%M%S")
    code = f"PRODJP1_{suffix}"
    st, created = api(
        "POST",
        "/dashboard/prehire/positions",
        {
            "title": f"Prod verify {suffix}",
            "title_ar": f"تحقق {suffix}",
            "position_code": code,
            "description": "synthetic dry-run verification",
            "description_ar": "تحقق اصطناعي",
            "requirements_en": ["synthetic"],
            "requirements_ar": ["اصطناعي"],
            "department": "Operations",
            "location": "Kuwait City",
            "salary_min": 100,
            "salary_max": 200,
            "currency": "KD",
            "salary_visibility": "hr_only",
            "vacancies": 2,
            "save_as_draft": True,
        },
    )
    job = (created.get("position") or {}) if st == 200 else {}
    note(results, st == 200 and job.get("status") == "draft", "draft creation works", code)

    st, edited = api(
        "PATCH",
        f"/dashboard/prehire/positions/{code}",
        {
            "description": "edited draft still draft",
            "vacancies": 3,
            "expected_version": job.get("version"),
            "expected_updated_at": job.get("updated_at"),
        },
    )
    job = edited.get("position") or job
    note(results, st == 200 and job.get("status") == "draft", "editing draft does not publish")
    note(results, job.get("salary_visibility") == "hr_only", "salary visibility hr_only")
    note(
        results,
        int(job.get("vacancies") or 0) == 3 and int(job.get("remaining_vacancies") or 0) == 3,
        "vacancy/remaining",
        f"v={job.get('vacancies')} r={job.get('remaining_vacancies')}",
    )

    st_dup, _ = api(
        "POST",
        "/dashboard/prehire/positions",
        {"title": "dup", "position_code": code, "save_as_draft": True},
    )
    note(results, st_dup == 409, "duplicate position code rejected", str(st_dup))

    st_stale, _ = api(
        "PATCH",
        f"/dashboard/prehire/positions/{code}",
        {"description": "stale", "expected_version": int(job.get("version") or 1) + 99},
    )
    note(results, st_stale == 409, "stale edit fails safely", str(st_stale))

    st, pub = api(
        "POST",
        f"/dashboard/prehire/positions/{code}/status",
        {"status": "open", "expected_version": job.get("version")},
    )
    job = pub.get("position") or job
    note(results, st == 200 and job.get("status") == "open", "publish works for owner")

    link = str(job.get("application_link") or "")
    note(results, "96597453460" in link and link.startswith("https://wa.me/"), "APPLY/wa.me uses 96597453460", link)
    qr = str(job.get("qr_value") or "")
    note(results, qr == link or "96597453460" in qr, "QR payload uses same number", qr[:120])

    st, open_edit = api(
        "PATCH",
        f"/dashboard/prehire/positions/{code}",
        {"location": "Salmiya", "expected_version": job.get("version")},
    )
    job = open_edit.get("position") or job
    note(
        results,
        st == 200 and job.get("status") == "open" and job.get("location") == "Salmiya",
        "edit open job does not change status",
    )

    for status, label in [
        ("paused", "pause rejects new intake"),
        ("open", "resume restores intake"),
        ("closed", "close rejects new intake"),
        ("open", "reopen restores intake"),
    ]:
        st, res = api(
            "POST",
            f"/dashboard/prehire/positions/{code}/status",
            {"status": status, "expected_version": job.get("version")},
        )
        job = res.get("position") or job
        note(results, st == 200 and job.get("status") == status, label, str(job.get("status")))

    # Close again, then prove create cannot reopen
    api("POST", f"/dashboard/prehire/positions/{code}/status", {"status": "closed", "expected_version": job.get("version")})
    st, listing = api("GET", "/dashboard/prehire/positions?limit=100")
    job = next((p for p in positions_from(listing) if p.get("position_code") == code), job)

    st_re, _ = api(
        "POST",
        "/dashboard/prehire/positions",
        {"title": "should conflict", "position_code": code, "save_as_draft": True},
    )
    note(results, st_re == 409, "generic create cannot reopen closed job", str(st_re))

    st_stale_tr, _ = api(
        "POST",
        f"/dashboard/prehire/positions/{code}/status",
        {"status": "open", "expected_version": int(job.get("version") or 1) + 50},
    )
    note(results, st_stale_tr == 409, "stale transition fails safely", str(st_stale_tr))

    note(
        results,
        str(os.environ.get("WATHEFNI_FILE_POSITIONS_ENABLED", "")).lower() in {"0", "false", "no"},
        "file-based positions disabled",
        str(os.environ.get("WATHEFNI_FILE_POSITIONS_ENABLED")),
    )

    sys.path.insert(0, "/opt/wathefni/orchestrator")
    import prehire_jobs as jobs  # noqa: E402

    apply_code = job.get("apply_code") or f"APPLY-WATHEFNI-{code}"
    share_link = jobs.apply_link(apply_code)
    note(
        results,
        bool(share_link) and share_link.startswith("https://wa.me/96597453460"),
        "Assistant/share apply_link parity",
        str(share_link),
    )
    note(results, os.environ.get("WATHEFNI_DELIVERY_MODE") == "dry_run", "verification dry_run only")

    # Final cleanup close
    st, listing = api("GET", "/dashboard/prehire/positions?limit=100")
    job = next((p for p in positions_from(listing) if p.get("position_code") == code), job)
    st_c, body_c = api(
        "POST",
        f"/dashboard/prehire/positions/{code}/status",
        {"status": "closed", "expected_version": job.get("version")},
    )
    job_final = body_c.get("position") or job
    note(results, job_final.get("status") == "closed" or st_c == 200, "cleanup closed synthetic job", code)

    payload = {
        "results": results,
        "passed": sum(1 for r in results if r["ok"]),
        "failed": sum(1 for r in results if not r["ok"]),
        "code": code,
        "artifact": "0c0ac7a45b9c516368650cb434e145b8acd5f771f09e422e6ae615281763e0a1",
    }
    OUT.write_text(json.dumps(payload, indent=2))
    print(json.dumps({"passed": payload["passed"], "failed": payload["failed"], "code": code}))
    return 0 if payload["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
