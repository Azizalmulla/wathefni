#!/usr/bin/env python3
"""Regression harness for CV Extraction V2 across WATHEFNI CVs + Yasser proof gates."""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
from typing import Any


YASSER_APP = "imp-wathefni-837eb9b1bf14506b-WATHEFNI-IMPORT"


def _load_proc_env(pid: str) -> None:
    for item in pathlib.Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"):
        if not item or b"=" not in item:
            continue
        k, v = item.split(b"=", 1)
        os.environ.setdefault(k.decode(), v.decode(errors="replace"))


def _text(v: Any) -> str:
    return str(v or "").strip()


def _skill_contamination(skills: list[Any]) -> list[str]:
    bad = []
    for item in skills:
        name = _text(item.get("name") if isinstance(item, dict) else item)
        if re.search(
            r"publication|report|reference|@|online course|languages?\s*:|selected publications|http",
            name,
            re.I,
        ):
            bad.append(name)
    return bad


def yasser_gates(payload: dict[str, Any]) -> dict[str, Any]:
    langs = [
        _text(i.get("language") if isinstance(i, dict) else i).casefold()
        for i in payload.get("languages") or []
    ]
    has_ar = any("arabic" in x or "عربي" in x for x in langs)
    has_en = any("english" in x or "إنجليز" in x for x in langs)
    employment = payload.get("employment") or []
    skills = payload.get("skills") or []
    pubs = payload.get("publications") or []
    courses = payload.get("training_courses") or []
    memberships = payload.get("memberships_activities") or []
    awards = payload.get("awards_honors") or []
    volunteer = payload.get("volunteer_work") or []
    education = payload.get("education") or []
    contamination = _skill_contamination(skills)

    checks = {
        "languages_ar_en": has_ar and has_en,
        "four_work_roles": len(employment) >= 4,
        "genuine_skills_only": len(contamination) == 0,
        "publications_present": len(pubs) >= 1,
        "training_courses_present": len(courses) >= 1,
        "memberships_present": len(memberships) >= 1,
        "awards_present": len(awards) >= 1,
        "volunteer_separate": isinstance(payload.get("volunteer_work"), list),
        "education_clean": len(education) >= 1
        and not any(
            re.search(r"\b(course|bootcamp|member)\b", _text(e.get("degree") if isinstance(e, dict) else e), re.I)
            for e in education
        ),
        "content_preserved": any(
            payload.get(k)
            for k in (
                "employment",
                "education",
                "skills",
                "languages",
                "publications",
                "training_courses",
                "unmodeled_sections",
            )
        ),
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "counts": {
            "employment": len(employment),
            "volunteer_work": len(volunteer),
            "education": len(education),
            "skills": len(skills),
            "languages": len(langs),
            "publications": len(pubs),
            "training_courses": len(courses),
            "memberships_activities": len(memberships),
            "awards_honors": len(awards),
            "unmodeled_sections": len(payload.get("unmodeled_sections") or []),
            "skill_contamination": len(contamination),
        },
        "contamination_samples": contamination[:5],
        "languages": langs,
    }


def main() -> int:
    pid = os.environ.get("PROOF_PID") or ""
    if pid:
        _load_proc_env(pid)
    company = (os.environ.get("COMPANY_CODE") or "WATHEFNI").strip().upper()

    import app
    import cv_extraction_v2 as cv2
    import candidate_cv_facts as cvf

    rows_out: list[dict[str, Any]] = []
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cv2.ensure_schema(cur)
            cur.execute(
                """
                SELECT v.app_key, v.status, v.payload, v.validation, v.provenance,
                       v.estimated_cost_usd, v.source_content_sha256, v.document_id,
                       v.extraction_id, v.raw_provider_response
                FROM application_cv_extraction_v2 v
                WHERE v.company_code=%s AND v.is_current=true
                ORDER BY v.updated_at DESC
                """,
                (company,),
            )
            v2_rows = [dict(r) for r in cur.fetchall()]

            # Compare against v1 facts for old-vs-new improvement.
            for row in v2_rows:
                app_key = str(row["app_key"])
                payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
                validation = row.get("validation") if isinstance(row.get("validation"), dict) else {}
                stats = validation.get("stats") or {}
                contamination = _skill_contamination(payload.get("skills") or [])

                cur.execute(
                    """
                    SELECT facts FROM application_cv_fact_snapshots
                    WHERE company_code=%s AND app_key=%s AND is_current=true
                    LIMIT 1
                    """,
                    (company, app_key),
                )
                v1 = cur.fetchone()
                v1_facts = (v1 or {}).get("facts") if isinstance((v1 or {}).get("facts"), dict) else {}
                v1_langs = v1_facts.get("languages") if isinstance(v1_facts.get("languages"), list) else []
                v1_skills = v1_facts.get("skills") if isinstance(v1_facts.get("skills"), list) else []
                v1_emp = v1_facts.get("employment") if isinstance(v1_facts.get("employment"), list) else []

                path = ((row.get("provenance") or {}) if isinstance(row.get("provenance"), dict) else {}).get("path")
                fmt = "unknown"
                doc = str(row.get("document_id") or "")
                if doc.lower().endswith(".pdf") or "pdf" in doc.lower():
                    fmt = "pdf"
                elif "docx" in doc.lower():
                    fmt = "docx"
                elif path and "docx" in str(path):
                    fmt = "docx"
                elif path and "ocr" in str(path):
                    fmt = "pdf_or_image"

                rows_out.append(
                    {
                        "app_key": app_key,
                        "status": row.get("status"),
                        "path": path,
                        "format_guess": fmt,
                        "stats": stats,
                        "contamination_rate": (
                            len(contamination) / max(1, len(payload.get("skills") or []))
                        ),
                        "unmodeled_rate": (
                            int(stats.get("unmodeled_sections") or 0)
                            / max(
                                1,
                                sum(int(stats.get(k) or 0) for k in stats.keys()),
                            )
                        ),
                        "v1_languages": len(v1_langs),
                        "v2_languages": int(stats.get("languages") or 0),
                        "v1_employment": len(v1_emp),
                        "v2_employment": int(stats.get("employment") or 0),
                        "v1_skills": len(v1_skills),
                        "v2_skills": int(stats.get("skills") or 0),
                        "language_improved": int(stats.get("languages") or 0) > len(v1_langs),
                        "employment_improved": int(stats.get("employment") or 0) >= max(1, len(v1_emp)),
                        "cost_usd": float(row.get("estimated_cost_usd") or 0),
                        "failed": row.get("status") == "failed",
                    }
                )

            yasser = next((r for r in v2_rows if r.get("app_key") == YASSER_APP), None)
            yasser_proof = None
            if yasser:
                yasser_proof = yasser_gates(
                    yasser.get("payload") if isinstance(yasser.get("payload"), dict) else {}
                )

            # Idempotency: current rows unique per app
            cur.execute(
                """
                SELECT app_key, count(*) AS n
                FROM application_cv_extraction_v2
                WHERE company_code=%s AND is_current=true
                GROUP BY app_key HAVING count(*) > 1
                """,
                (company,),
            )
            dup_current = [dict(r) for r in cur.fetchall()]
            cur.execute(
                """
                SELECT count(*) AS n FROM application_cv_fact_snapshots
                WHERE company_code=%s AND is_current=true
                """,
                (company,),
            )
            facts_current = int((cur.fetchone() or {}).get("n") or 0)

    n = max(1, len(rows_out))
    failed = [r for r in rows_out if r.get("failed")]
    summary = {
        "company_code": company,
        "cv_count": len(rows_out),
        "section_classification_proxy": {
            # Proxy: share of CVs with languages and employment populated under V2.
            "languages_nonempty_rate": round(
                sum(1 for r in rows_out if (r.get("stats") or {}).get("languages", 0) > 0) / n, 3
            ),
            "employment_nonempty_rate": round(
                sum(1 for r in rows_out if (r.get("stats") or {}).get("employment", 0) > 0) / n, 3
            ),
            "publications_or_unmodeled_present_rate": round(
                sum(
                    1
                    for r in rows_out
                    if (r.get("stats") or {}).get("publications", 0) > 0
                    or (r.get("stats") or {}).get("unmodeled_sections", 0) > 0
                )
                / n,
                3,
            ),
        },
        "field_completeness": {
            "avg_employment": round(
                sum(int((r.get("stats") or {}).get("employment") or 0) for r in rows_out) / n, 2
            ),
            "avg_education": round(
                sum(int((r.get("stats") or {}).get("education") or 0) for r in rows_out) / n, 2
            ),
            "avg_skills": round(
                sum(int((r.get("stats") or {}).get("skills") or 0) for r in rows_out) / n, 2
            ),
            "avg_languages": round(
                sum(int((r.get("stats") or {}).get("languages") or 0) for r in rows_out) / n, 2
            ),
        },
        "contamination_rate": round(sum(float(r.get("contamination_rate") or 0) for r in rows_out) / n, 3),
        "unmodeled_content_rate": round(sum(float(r.get("unmodeled_rate") or 0) for r in rows_out) / n, 3),
        "old_versus_new_improvement": {
            "language_improved_rate": round(
                sum(1 for r in rows_out if r.get("language_improved")) / n, 3
            ),
            "employment_not_regressed_rate": round(
                sum(1 for r in rows_out if r.get("employment_improved")) / n, 3
            ),
        },
        "failures_by_format": {},
        "mistral_usage": {
            "total_estimated_cost_usd": round(sum(float(r.get("cost_usd") or 0) for r in rows_out), 6),
            "avg_cost_usd": round(sum(float(r.get("cost_usd") or 0) for r in rows_out) / n, 6),
        },
        "idempotency": {
            "duplicate_current_apps": dup_current,
            "current_fact_snapshots": facts_current,
            "duplicate_proof_ok": len(dup_current) == 0,
        },
        "yasser_proof": yasser_proof,
        "rows": rows_out,
    }

    by_fmt: dict[str, int] = {}
    for r in failed:
        fmt = str(r.get("format_guess") or "unknown")
        by_fmt[fmt] = by_fmt.get(fmt, 0) + 1
    summary["failures_by_format"] = by_fmt

    yasser_ok = bool(yasser_proof and yasser_proof.get("pass"))
    quality_ok = (
        summary["contamination_rate"] <= 0.15
        and summary["section_classification_proxy"]["languages_nonempty_rate"] >= 0.5
        and summary["idempotency"]["duplicate_proof_ok"]
        and yasser_ok
    )
    summary["quality_gates_pass"] = quality_ok
    summary["recommend_publish_profile_facts_v2"] = quality_ok

    print(json.dumps(summary, default=str, indent=2))
    return 0 if quality_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
