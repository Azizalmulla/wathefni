"""Phase A — Offer → employment → onboarding truth-sync (dry-run foundation).

Writers are OFF by default (`WATHEFNI_EMPLOYMENT_TRUTH_SYNC_WRITERS=off`).
This module reconciles joining-date / probation terms / pending_start invariants
without mutating rows until an explicit future writer entitle.

Preserves HARD / OPTIONAL / ENHANCEMENT classifications via capability_contracts.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

TRUTH_SYNC_VERSION = "1.0.0"
_ON_VALUES = {"1", "true", "yes", "on"}

# pending_start P1–P9 (charter §3.2 / §19.1)
PENDING_START_INVARIANTS = (
    "P1_canonical_sot",
    "P2_joining_vs_active_visibility",
    "P3_exclude_active_headcount",
    "P4_exclude_payroll_attendance_leave_shifts",
    "P5_no_normal_employee_app",
    "P6_cancel_close_with_audit",
    "P7_convert_same_record",
    "P8_joining_date_single_authority",
    "P9_tenant_rbac_before_activation",
)


def _env_on(name: str, default: str = "off") -> bool:
    return str(os.environ.get(name, default) or default).strip().lower() in _ON_VALUES


def writers_enabled() -> bool:
    """Mutating sync is dark until explicitly entitled."""
    return _env_on("WATHEFNI_EMPLOYMENT_TRUTH_SYNC_WRITERS", "off")


def company_code_norm(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def expected_probation_end(start: date | None, probation_days: Any) -> date | None:
    if not start:
        return None
    try:
        days = int(probation_days)
    except (TypeError, ValueError):
        return None
    if days <= 0:
        return None
    return start + timedelta(days=days)


def joining_date_authority_rank(source: str) -> int:
    """Higher wins for conflict reporting (writers not applied here)."""
    order = {
        "hr_explicit_edit": 300,
        "hire_tx": 200,
        "offer_accept": 100,
        "unknown": 0,
    }
    return int(order.get(source, 0))


def evaluate_pending_start_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Static invariant checks for one provisional employment / hub row."""
    findings: list[dict[str, Any]] = []
    life = str(row.get("lifecycle_state") or "").strip()
    if life != "pending_start":
        return findings

    hub = str(row.get("hub_status") or row.get("employment_status") or "").strip().lower()
    # P2/P3: hub treating pending_start as generic "active" risks headcount/visibility bleed.
    if hub in {"active", "employed"}:
        findings.append(
            {
                "invariant": "P2_joining_vs_active_visibility",
                "severity": "warning",
                "code": "pending_start_hub_looks_active",
                "detail": "hub/employment_status presents as active while lifecycle_state=pending_start",
            }
        )
        findings.append(
            {
                "invariant": "P3_exclude_active_headcount",
                "severity": "warning",
                "code": "pending_start_may_inflate_headcount",
                "detail": "active-status presentation may include pending starters in headcount KPIs",
            }
        )

    # P4 probes — eligibility flags if present on the row/projection
    for flag, label in (
        ("payroll_eligible", "payroll"),
        ("attendance_eligible", "attendance"),
        ("leave_eligible", "leave"),
        ("shifts_eligible", "shifts"),
    ):
        if row.get(flag) is True:
            findings.append(
                {
                    "invariant": "P4_exclude_payroll_attendance_leave_shifts",
                    "severity": "fail",
                    "code": f"pending_start_{label}_eligible",
                    "detail": f"{flag}=true is forbidden for pending_start",
                }
            )

    if row.get("employee_app_normal_capabilities") is True:
        findings.append(
            {
                "invariant": "P5_no_normal_employee_app",
                "severity": "fail",
                "code": "pending_start_normal_ess",
                "detail": "normal Employee App capabilities must not auto-grant before activation",
            }
        )

    if not row.get("company_code"):
        findings.append(
            {
                "invariant": "P9_tenant_rbac_before_activation",
                "severity": "fail",
                "code": "pending_start_missing_company",
                "detail": "tenant scope missing on provisional employment",
            }
        )

    return findings


def diff_joining_date(
    *,
    employment_start: Any,
    offer_proposed_start: Any,
    applicability_proposed_start: Any = None,
) -> dict[str, Any] | None:
    emp = as_date(employment_start)
    offer = as_date(offer_proposed_start)
    snap = as_date(applicability_proposed_start)
    if offer is None and snap is None:
        return None
    authority_candidate = offer or snap
    if emp is None and authority_candidate is not None:
        return {
            "code": "joining_date_missing_on_employment",
            "severity": "info",
            "employment_start": None,
            "offer_proposed_start": offer.isoformat() if offer else None,
            "applicability_proposed_start": snap.isoformat() if snap else None,
            "suggested_write": authority_candidate.isoformat(),
            "writer_blocked": not writers_enabled(),
        }
    if emp is not None and authority_candidate is not None and emp != authority_candidate:
        return {
            "code": "joining_date_mismatch",
            "severity": "warning",
            "employment_start": emp.isoformat(),
            "offer_proposed_start": offer.isoformat() if offer else None,
            "applicability_proposed_start": snap.isoformat() if snap else None,
            "suggested_write": None,  # do not overwrite non-null without HR authority
            "writer_blocked": True,
        }
    return None


def diff_probation_terms(
    *,
    employment_start: Any,
    offer_probation_days: Any,
    applicability_probation_days: Any = None,
    employment_probation_end: Any = None,
) -> dict[str, Any] | None:
    days = offer_probation_days if offer_probation_days is not None else applicability_probation_days
    if days is None:
        return None
    start = as_date(employment_start)
    expected = expected_probation_end(start, days)
    actual = as_date(employment_probation_end)
    if expected is None:
        return None
    if actual is None:
        return {
            "code": "probation_end_missing",
            "severity": "info",
            "offer_probation_days": int(days) if str(days).isdigit() or isinstance(days, int) else days,
            "expected_probation_end": expected.isoformat(),
            "employment_probation_end": None,
            "suggested_write": expected.isoformat(),
            "writer_blocked": not writers_enabled(),
        }
    if actual != expected:
        return {
            "code": "probation_end_mismatch",
            "severity": "warning",
            "offer_probation_days": days,
            "expected_probation_end": expected.isoformat(),
            "employment_probation_end": actual.isoformat(),
            "suggested_write": None,
            "writer_blocked": True,
        }
    return None


def detect_duplicate_employments(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flag multiple non-terminated employments for the same person/app_key."""
    by_person: dict[str, list[dict[str, Any]]] = {}
    by_app: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        person = str(r.get("person_id") or "").strip()
        app_key = str(r.get("app_key") or "").strip()
        life = str(r.get("lifecycle_state") or "").strip()
        if life == "terminated" or str(r.get("employment_status") or "") == "left":
            continue
        if person:
            by_person.setdefault(person, []).append(r)
        if app_key:
            by_app.setdefault(app_key, []).append(r)
    findings: list[dict[str, Any]] = []
    for person, items in by_person.items():
        if len(items) > 1:
            findings.append(
                {
                    "invariant": "P7_convert_same_record",
                    "severity": "fail",
                    "code": "duplicate_active_employment_person",
                    "person_id": person,
                    "employment_ids": [str(i.get("employment_id")) for i in items],
                }
            )
    for app_key, items in by_app.items():
        if len(items) > 1:
            findings.append(
                {
                    "invariant": "P7_convert_same_record",
                    "severity": "fail",
                    "code": "duplicate_active_employment_app_key",
                    "app_key": app_key,
                    "employment_ids": [str(i.get("employment_id")) for i in items],
                }
            )
    return findings


def module_off_behavior(*, enabled_modules: set[str] | list[str]) -> dict[str, Any]:
    import capability_contracts as cc

    enabled = set(enabled_modules)
    joining = cc.evaluate_contract(
        "employment.joining_date_from_offer", enabled_modules=enabled
    )
    probation = cc.evaluate_contract("probation.sync_from_offer", enabled_modules=enabled)
    onboard = cc.evaluate_contract(
        "onboarding.auto_start_on_hire",
        enabled_modules=enabled,
        company_settings={"onboarding.auto_start_on_hire": True},
    )
    return {
        "joining_sync_active": bool(joining.get("active")),
        "probation_sync_active": bool(probation.get("active")),
        "onboarding_auto_start_active": bool(onboard.get("active")),
        "offers_module_on": "employment_offers" in enabled,
        "onboarding_module_on": "onboarding" in enabled,
        "writers_enabled": writers_enabled(),
        "note": "When modules/settings off, domain hire/offer/onboarding paths remain usable without sync writers",
    }


def rollback_guidance() -> dict[str, Any]:
    return {
        "runtime": [
            "Keep WATHEFNI_EMPLOYMENT_TRUTH_SYNC_WRITERS=off (default)",
            "Do not entitle company writer allowlists until dry-run is clean",
        ],
        "data": [
            "Dry-run emits findings only; no employment/offer/onboarding rows are rewritten",
            "If writers were ever enabled, restore from audit/export before drop",
        ],
        "pending_start": list(PENDING_START_INVARIANTS),
        "version": TRUTH_SYNC_VERSION,
    }


def dry_run_company(cur: Any, company_code: str, *, limit: int = 200) -> dict[str, Any]:
    """Read-only reconciliation against existing company data."""
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "error": "company_required"}

    findings: list[dict[str, Any]] = []
    sample_pending: list[dict[str, Any]] = []
    sample_mismatches: list[dict[str, Any]] = []

    # Enabled modules (best-effort)
    enabled_modules: set[str] = set()
    try:
        cur.execute(
            """
            SELECT module_key FROM company_modules
             WHERE company_code=%s AND enabled=true
            """,
            (company,),
        )
        enabled_modules = {str(r["module_key"] if isinstance(r, dict) else r[0]) for r in (cur.fetchall() or [])}
    except Exception:
        enabled_modules = set()

    mod = module_off_behavior(enabled_modules=enabled_modules)

    # Pending_start employments
    employments: list[dict[str, Any]] = []
    try:
        cur.execute(
            """
            SELECT e.employment_id, e.company_code, e.person_id, e.employment_status,
                   e.lifecycle_state, e.start_date, e.app_key, e.legacy_employee_key,
                   e.provenance
              FROM employee_employments e
             WHERE e.company_code=%s
             ORDER BY e.updated_at DESC NULLS LAST
             LIMIT %s
            """,
            (company, int(limit)),
        )
        employments = [dict(r) for r in (cur.fetchall() or [])]
    except Exception as exc:
        findings.append(
            {
                "severity": "info",
                "code": "employments_query_skipped",
                "detail": str(exc.__class__.__name__),
            }
        )

    for emp in employments:
        if str(emp.get("lifecycle_state") or "") == "pending_start":
            # Enrich with hub status when available
            hub_status = None
            key = emp.get("legacy_employee_key")
            if key:
                try:
                    cur.execute(
                        """
                        SELECT employment_status AS hub_status
                          FROM employees
                         WHERE company_code=%s AND employee_key=%s
                         LIMIT 1
                        """,
                        (company, key),
                    )
                    h = cur.fetchone()
                    if h:
                        hub_status = dict(h).get("hub_status")
                except Exception:
                    pass
            probe = {**emp, "hub_status": hub_status}
            ps_findings = evaluate_pending_start_row(probe)
            if ps_findings:
                findings.extend([{**f, "employment_id": str(emp.get("employment_id"))} for f in ps_findings])
            sample_pending.append(
                {
                    "employment_id": str(emp.get("employment_id")),
                    "lifecycle_state": emp.get("lifecycle_state"),
                    "hub_status": hub_status,
                    "start_date": str(emp.get("start_date") or ""),
                }
            )

    dupes = detect_duplicate_employments(employments)
    findings.extend(dupes)

    # Offer ↔ employment via applicability snapshots (accepted_offer path)
    try:
        cur.execute(
            """
            SELECT s.employee_key, s.accepted_offer_id, s.proposed_start_date, s.probation_days,
                   s.source_path, s.app_key
              FROM employment_applicability_snapshots s
             WHERE s.company_code=%s
             ORDER BY s.created_at DESC
             LIMIT %s
            """,
            (company, int(limit)),
        )
        snaps = [dict(r) for r in (cur.fetchall() or [])]
    except Exception:
        snaps = []

    for snap in snaps:
        emp_start = None
        emp_prob_end = None
        # Hub employees.start_date is the common joining authority today
        try:
            cur.execute(
                """
                SELECT start_date, employment_status
                  FROM employees
                 WHERE company_code=%s AND employee_key=%s
                 LIMIT 1
                """,
                (company, snap.get("employee_key")),
            )
            erow = cur.fetchone()
            if erow:
                erow = dict(erow)
                emp_start = erow.get("start_date")
        except Exception:
            pass

        # Optional employment row by legacy key
        try:
            cur.execute(
                """
                SELECT start_date, lifecycle_state
                  FROM employee_employments
                 WHERE company_code=%s AND legacy_employee_key=%s
                 LIMIT 1
                """,
                (company, snap.get("employee_key")),
            )
            er2 = cur.fetchone()
            if er2:
                er2 = dict(er2)
                emp_start = emp_start or er2.get("start_date")
        except Exception:
            pass

        offer_start = None
        offer_prob = None
        oid = snap.get("accepted_offer_id")
        if oid:
            try:
                cur.execute(
                    """
                    SELECT proposed_start_date, probation_days, status
                      FROM employment_offers
                     WHERE company_code=%s AND offer_id=%s
                     LIMIT 1
                    """,
                    (company, oid),
                )
                o = cur.fetchone()
                if o:
                    o = dict(o)
                    offer_start = o.get("proposed_start_date")
                    offer_prob = o.get("probation_days")
            except Exception:
                pass

        jd = diff_joining_date(
            employment_start=emp_start,
            offer_proposed_start=offer_start,
            applicability_proposed_start=snap.get("proposed_start_date"),
        )
        if jd:
            item = {**jd, "employee_key": snap.get("employee_key"), "accepted_offer_id": oid}
            findings.append(item)
            sample_mismatches.append(item)

        pd = diff_probation_terms(
            employment_start=emp_start or snap.get("proposed_start_date") or offer_start,
            offer_probation_days=offer_prob,
            applicability_probation_days=snap.get("probation_days"),
            employment_probation_end=emp_prob_end,
        )
        if pd:
            item = {**pd, "employee_key": snap.get("employee_key"), "accepted_offer_id": oid}
            findings.append(item)
            sample_mismatches.append(item)

    # Static lifecycle helper honesty (P2/P3)
    try:
        from employee_lifecycle_wave3 import hub_status_for_lifecycle

        hub_for_pending = hub_status_for_lifecycle("pending_start")
        if hub_for_pending == "active":
            findings.append(
                {
                    "invariant": "P2_joining_vs_active_visibility",
                    "severity": "warning",
                    "code": "hub_status_for_lifecycle_maps_pending_start_to_active",
                    "detail": "Platform helper currently maps pending_start→active; Wave 1 must distinguish joining vs active",
                }
            )
    except Exception:
        pass

    fail_count = sum(1 for f in findings if f.get("severity") == "fail")
    warn_count = sum(1 for f in findings if f.get("severity") == "warning")

    return {
        "ok": True,
        "mode": "dry_run",
        "company_code": company,
        "version": TRUTH_SYNC_VERSION,
        "writers_enabled": writers_enabled(),
        "module_behavior": mod,
        "counts": {
            "employments_scanned": len(employments),
            "pending_start_seen": len(sample_pending),
            "applicability_snapshots_scanned": len(snaps),
            "findings": len(findings),
            "fail": fail_count,
            "warning": warn_count,
        },
        "findings": findings[:500],
        "sample_pending_start": sample_pending[:50],
        "sample_mismatches": sample_mismatches[:50],
        "rollback": rollback_guidance(),
        "proved_at": datetime.now(timezone.utc).isoformat(),
    }


def assert_writers_dark() -> dict[str, Any]:
    if writers_enabled():
        return {"ok": False, "error": "writers_must_stay_off_for_phase_a_foundation"}
    return {"ok": True, "writers_enabled": False}
