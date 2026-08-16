#!/usr/bin/env python3
"""Wave 2 C1 — Attendance Truth company-scoped ingest gates.

Owner-approved under WAVE2_WORKFORCE_TRUTH_CHARTER (2026-08-11).

Gates (fail-closed):
  1) WATHEFNI_ATTENDANCE_CAPTURE_INGEST must be on (global kill switch; prod stays off)
  2) company must be in WATHEFNI_ATTENDANCE_CAPTURE_INGEST_COMPANIES
     (empty allowlist = nobody — never “all companies”)
  3) optional umbrella WATHEFNI_ATTENDANCE_TRUTH_C1=on for explicit C1 entitle

Does not rewrite punches. Does not merge approve into apply.
Does not enable Assistant mutations. Does not touch payroll money.
"""
from __future__ import annotations

import os
from typing import Any

PHASE = "attendance_truth_c1"
CONTRACT_VERSION = "attendance_truth_c1_v1"
_ON = {"1", "true", "yes", "on"}


def _env_on(name: str, default: str = "off") -> bool:
    return (os.environ.get(name) or default).strip().lower() in _ON


def attendance_truth_c1_flag_on() -> bool:
    """Explicit C1 umbrella (optional but recommended for canary deploys)."""
    return _env_on("WATHEFNI_ATTENDANCE_TRUTH_C1", "off")


def capture_ingest_runtime_on() -> bool:
    return _env_on("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off")


def capture_ingest_company_allowlist() -> set[str]:
    """Empty = nobody (fail closed). Prefer INGEST_COMPANIES; TRUTH_COMPANIES is alias."""
    raw = str(
        os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST_COMPANIES")
        or os.environ.get("WATHEFNI_ATTENDANCE_TRUTH_COMPANIES")
        or ""
    ).strip()
    if not raw:
        return set()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def company_code_norm(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def capture_ingest_enabled_for_company(company_code: str | None) -> dict[str, Any]:
    """Company-entitled real punch ingest gate. Global default remains off."""
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if not capture_ingest_runtime_on():
        return {
            "ok": False,
            "enabled": False,
            "error": "capture_ingest_off",
            "gate": "runtime_flag",
            "phase": PHASE,
            "message": "Global CAPTURE_INGEST is off (production default).",
        }
    allow = capture_ingest_company_allowlist()
    if not allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "capture_ingest_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "message": "Ingest allowlist empty — fail closed (nobody).",
        }
    if company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "capture_ingest_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "company_code": company,
        }
    return {
        "ok": True,
        "enabled": True,
        "company_code": company,
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "truth_c1_flag": attendance_truth_c1_flag_on(),
    }


def entitled_ingest_canonical(
    pipeline: Any,
    punch: Any,
    *,
    company_code: str | None = None,
    shift: dict[str, Any] | None = None,
    work_date: Any = None,
    reproject: bool = True,
) -> dict[str, Any]:
    """Gate then ingest. Use from capture-ops HTTP / C1 prove paths."""
    company = company_code_norm(company_code)
    if not company and isinstance(punch, dict):
        company = company_code_norm(punch.get("company_code"))
    gate = capture_ingest_enabled_for_company(company)
    if not gate.get("ok"):
        return gate
    return pipeline.ingest_canonical(punch, shift=shift, work_date=work_date, reproject=reproject)


def rollback_guidance() -> dict[str, Any]:
    return {
        "ok": True,
        "phase": PHASE,
        "steps": [
            "Set WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off (global kill)",
            "Clear WATHEFNI_ATTENDANCE_CAPTURE_INGEST_COMPANIES / WATHEFNI_ATTENDANCE_TRUTH_COMPANIES",
            "Set WATHEFNI_ATTENDANCE_TRUTH_C1=off",
            "Keep AUTHORITY_SYNTHETIC_ONLY / OPS_SYNTHETIC_ONLY at prior freeze posture unless a later slice amends them",
            "Do not DROP attendance_punches / projections / ops tables",
        ],
    }
