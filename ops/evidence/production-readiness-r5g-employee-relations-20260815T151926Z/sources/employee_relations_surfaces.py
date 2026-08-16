#!/usr/bin/env python3
"""R5G Employee Relations product surfaces — thin composition over frozen Wave 6 C4.

HTTP and clients are adapters. Case, intake, triage, investigation, evidence,
finding, outcome, closure, and Wave 3 employment-change handoff stay
domain-authoritative. This module never invents a second ER model, scores
conduct, or mutates employment.
"""
from __future__ import annotations

from typing import Any, Mapping

import employee_relations_c4 as c4

PHASE = "employee_relations_surfaces_r5g"
CONTRACT_VERSION = "employee_relations_surfaces_v1"
PASS_STAMP = "PRODUCTION_READINESS_R5G_EMPLOYEE_RELATIONS_SURFACE_FULL_PASS"
COMMERCIAL_MODULE_KEY = "employee_relations"

GENERIC_ACTION_EN = "Employee Relations action requires your attention"
GENERIC_ACTION_AR = "إجراء في علاقات الموظفين يتطلب انتباهك"

RAW_URL_KEYS = frozenset(
    {
        "shared_document_ref",
        "provider_url",
        "signed_url",
        "download_url",
        "preview_url",
        "storage_url",
        "blob_url",
        "raw_url",
    }
)

NOTE_BODY_KEYS = frozenset({"body_en", "body_ar", "note_text"})
FINDING_BODY_KEYS = frozenset({"findings_en", "findings_ar"})
ALLEGATION_TEXT_KEYS = frozenset({"statement_en", "statement_ar", "allegation_text"})


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "canonical_authority": ("employee_relations_c4",),
        "submission_is_not_allegation_proven": True,
        "investigation_is_not_finding": True,
        "finding_is_not_outcome": True,
        "outcome_is_not_employment_mutation": True,
        "empty_assignment_is_not_company_wide": True,
        "ordinary_hr_not_er": True,
        "manager_not_er": True,
        "no_er_scoring": True,
        "wave5_excludes_sensitive_free_text": True,
        "assistant_mutations": False,
        "company_code": c4.company_code_norm(company_code) if company_code else None,
        **c4.honesty_payload(company_code=company_code),
    }


def ensure_schema(cur: Any) -> None:
    c4.ensure_employee_relations_c4_schema(cur)


def _upsert_company_module(cur: Any, company: str, enabled: bool) -> None:
    cur.execute(
        """
        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
        VALUES (%s, 'employee_relations', %s, 'employee_relations_surfaces', '{}'::jsonb, now())
        ON CONFLICT (company_code, module_key)
        DO UPDATE SET enabled=EXCLUDED.enabled, source='employee_relations_surfaces', updated_at=now()
        """,
        (company, bool(enabled)),
    )


def sync_catalog_entitlement(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    enabled: bool,
    reason: str = "sync employee relations catalog entitlement",
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c4.company_code_norm(company_code)
    if enabled:
        result = c4.enable_company_employee_relations(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
    else:
        result = c4.disable_company_employee_relations(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
    if result.get("ok"):
        _upsert_company_module(cur, company, bool(enabled))
    return {
        "ok": bool(result.get("ok")),
        "company_code": company,
        "enabled": bool(enabled),
        "history_preserved": True,
        "result": result,
        **honesty_payload(company_code=company),
    }


def _row(value: Any) -> dict[str, Any]:
    return dict(value) if value else {}


def _module_on(cur: Any, company: str, key: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM company_modules
         WHERE company_code=%s AND module_key=%s AND enabled IS TRUE
         LIMIT 1
        """,
        (company, key),
    )
    return bool(cur.fetchone())


def actor_key_from_context(context: Mapping[str, Any] | None) -> str:
    ctx = context or {}
    return str(ctx.get("actor_user_id") or ctx.get("actor_phone") or ctx.get("phone") or "").strip()


def map_actor_role(*, dashboard_role: str, permissions: set[str]) -> str:
    role = str(dashboard_role or "").strip().lower()
    perms = {str(p) for p in permissions}
    if role == "assistant":
        return "assistant"
    if role == "manager" and not (perms & {"er.read", "er.manage", "er.investigate", "er.decide"}):
        return "manager"
    if "er.manage" in perms:
        return "er_admin"
    if perms & {"er.investigate", "er.decide", "er.read"}:
        return "investigator"
    if role in {"owner", "hr_admin", "hr_manager", "admin", "hr"}:
        return "ordinary_hr"
    if role == "employee":
        return "employee"
    return "ordinary_hr"


def has_workspace_authority(permissions: set[str]) -> bool:
    return bool(permissions & {"er.read", "er.manage", "er.investigate", "er.decide"})


def _has_grant(cur: Any, company: str, case_id: str, actor_key: str, permission: str | None = None) -> bool:
    if permission:
        return bool(c4._has_grant(cur, company, case_id, actor_key, permission))
    cur.execute(
        """
        SELECT 1 FROM er_access_grants
         WHERE company_code=%s AND case_id=%s AND actor_key=%s AND revoked_at IS NULL
         LIMIT 1
        """,
        (company, case_id, actor_key),
    )
    return bool(cur.fetchone())


def _deny_need_to_know() -> dict[str, Any]:
    return {"ok": False, "error": "er_access_denied", "case_level_need_to_know": True}


def _require_grant(
    cur: Any, company: str, case_id: str, actor_key: str, permission: str
) -> dict[str, Any] | None:
    if not _has_grant(cur, company, case_id, actor_key, permission):
        return _deny_need_to_know()
    return None


def strip_raw_urls(value: Any) -> Any:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).strip().lower() in RAW_URL_KEYS:
                continue
            out[str(key)] = strip_raw_urls(item)
        return out
    if isinstance(value, list):
        return [strip_raw_urls(item) for item in value]
    return value


def _strip_keys(value: Any, keys: frozenset[str]) -> Any:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).strip().lower() in keys:
                continue
            out[str(key)] = _strip_keys(item, keys)
        return out
    if isinstance(value, list):
        return [_strip_keys(item, keys) for item in value]
    return value


def public_evidence(evid: Mapping[str, Any], *, allowed: bool) -> dict[str, Any]:
    evidence_id = str(evid.get("evidence_id") or "")
    return {
        "evidence_id": evidence_id,
        "case_id": evid.get("case_id"),
        "label_en": evid.get("label_en") or "",
        "label_ar": evid.get("label_ar") or "",
        "sensitive": bool(evid.get("sensitive")),
        "uploaded_by": evid.get("uploaded_by"),
        "created_at": evid.get("created_at"),
        "access_allowed": bool(allowed),
        "authorized_path": f"/dashboard/employee-relations/evidence/{evidence_id}/content" if allowed else None,
        "raw_provider_url": None,
    }


def _granted_case_ids(cur: Any, company: str, actor_key: str) -> list[str]:
    cur.execute(
        """
        SELECT DISTINCT case_id::text
          FROM er_access_grants
         WHERE company_code=%s AND actor_key=%s AND revoked_at IS NULL
        """,
        (company, actor_key),
    )
    return [str(dict(r)["case_id"]) for r in (cur.fetchall() or [])]


def workspace_summary(
    cur: Any, *, company_code: str, actor_key: str, actor_role: str
) -> dict[str, Any]:
    _ = actor_role
    ensure_schema(cur)
    company = c4.company_code_norm(company_code)
    if not c4.module_enabled_for_company(cur, company):
        return {
            "ok": True,
            "company_code": company,
            "enabled": False,
            "resource_state": "unavailable",
            "counts": None,
            **honesty_payload(company_code=company),
        }
    granted = _granted_case_ids(cur, company, actor_key)
    if not granted:
        return {
            "ok": True,
            "company_code": company,
            "enabled": True,
            "resource_state": "empty",
            "counts": {
                "requiring_my_action": 0,
                "assigned_open": 0,
                "overdue_investigation": 0,
            },
            "empty_assignment_is_not_company_wide": True,
            "performance_on": _module_on(cur, company, "performance"),
            "talent_on": _module_on(cur, company, "talent"),
            "payroll_on": _module_on(cur, company, "payroll"),
            "benefits_on": _module_on(cur, company, "benefits"),
            "engagement_on": _module_on(cur, company, "engagement"),
            **honesty_payload(company_code=company),
        }
    cur.execute(
        """
        SELECT
          COUNT(*) FILTER (
            WHERE status IN ('open','triage','investigating','decision_action')
          ) AS assigned_open,
          COUNT(*) FILTER (
            WHERE status IN ('open','triage','decision_action')
               OR assigned_investigator=%s
          ) AS requiring_my_action,
          COUNT(*) FILTER (
            WHERE due_date IS NOT NULL
              AND due_date < CURRENT_DATE
              AND status NOT IN ('closed','withdrawn','dismissed')
          ) AS overdue_investigation
          FROM er_cases
         WHERE company_code=%s AND case_id = ANY(%s::uuid[])
        """,
        (actor_key, company, granted),
    )
    counts = _row(cur.fetchone())
    return {
        "ok": True,
        "company_code": company,
        "enabled": True,
        "resource_state": "ready",
        "counts": {
            "requiring_my_action": int(counts.get("requiring_my_action") or 0),
            "assigned_open": int(counts.get("assigned_open") or 0),
            "overdue_investigation": int(counts.get("overdue_investigation") or 0),
        },
        "empty_assignment_is_not_company_wide": True,
        "performance_on": _module_on(cur, company, "performance"),
        "talent_on": _module_on(cur, company, "talent"),
        "payroll_on": _module_on(cur, company, "payroll"),
        "benefits_on": _module_on(cur, company, "benefits"),
        "engagement_on": _module_on(cur, company, "engagement"),
        **honesty_payload(company_code=company),
    }


def list_cases(
    cur: Any,
    *,
    company_code: str,
    actor_key: str,
    actor_role: str,
    status: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    _ = actor_role
    ensure_schema(cur)
    company = c4.company_code_norm(company_code)
    if not c4.module_enabled_for_company(cur, company):
        return {
            "ok": True,
            "cases": None,
            "total": None,
            "resource_state": "unavailable",
            **honesty_payload(company_code=company),
        }
    granted = _granted_case_ids(cur, company, actor_key)
    if not granted:
        return {
            "ok": True,
            "cases": [],
            "total": 0,
            "resource_state": "empty",
            "empty_assignment_is_not_company_wide": True,
            **honesty_payload(company_code=company),
        }
    where = ["company_code=%s", "case_id = ANY(%s::uuid[])"]
    params: list[Any] = [company, granted]
    if status:
        where.append("status=%s")
        params.append(str(status).strip().lower())
    cur.execute(f"SELECT COUNT(*) AS n FROM er_cases WHERE {' AND '.join(where)}", params)
    total = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        f"""
        SELECT case_id, company_code, case_type_code, case_type_version, status, severity,
               confidentiality_class, assigned_investigator, due_date, opened_at, closed_at,
               intake_source, created_by_phone, updated_at
          FROM er_cases
         WHERE {' AND '.join(where)}
         ORDER BY opened_at DESC
         LIMIT %s
        """,
        [*params, max(1, min(int(limit or 200), 400))],
    )
    items = [_row(r) for r in (cur.fetchall() or [])]
    for item in items:
        item["sla"] = c4.case_derived_sla(item)
        item["status_label_en"] = c4.status_label(str(item.get("status") or ""), lang="en")
        item["status_label_ar"] = c4.status_label(str(item.get("status") or ""), lang="ar")
        item.pop("summary_en", None)
        item.pop("summary_ar", None)
    return {
        "ok": True,
        "cases": items,
        "total": total,
        "resource_state": "empty" if total == 0 else "ready",
        "empty_assignment_is_not_company_wide": True,
        **honesty_payload(company_code=company),
    }


def list_case_types(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_schema(cur)
    company = c4.company_code_norm(company_code)
    cur.execute(
        """
        SELECT case_type_id, code, type_version, title_en, title_ar, confidentiality_default,
               allowed_outcomes, status
          FROM er_case_types
         WHERE company_code=%s AND status='active'
         ORDER BY code, type_version DESC
        """,
        (company,),
    )
    rows = [_row(r) for r in (cur.fetchall() or [])]
    return {"ok": True, "case_types": rows, **honesty_payload(company_code=company)}


def case_detail(
    cur: Any, *, company_code: str, actor_key: str, actor_role: str, case_id: str
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c4.company_code_norm(company_code)
    if not _has_grant(cur, company, case_id, actor_key):
        return _deny_need_to_know()
    detail = c4.er_case_detail(
        cur, company_code=company, actor_key=actor_key, actor_role=actor_role, case_id=case_id
    )
    if not detail.get("ok"):
        return detail
    can_investigate = _has_grant(cur, company, case_id, actor_key, "investigate")
    can_decide = _has_grant(cur, company, case_id, actor_key, "decide")
    can_manage = _has_grant(cur, company, case_id, actor_key, "manage")
    case = dict(detail.get("case") or {})
    case["status_label_en"] = c4.status_label(str(case.get("status") or ""), lang="en")
    case["status_label_ar"] = c4.status_label(str(case.get("status") or ""), lang="ar")
    if not can_investigate:
        case["summary_en"] = ""
        case["summary_ar"] = ""

    cur.execute(
        """
        SELECT party_id, party_role, employee_key, display_label, visibility, created_at
          FROM er_case_parties
         WHERE company_code=%s AND case_id=%s
         ORDER BY created_at
        """,
        (company, case_id),
    )
    parties = []
    for raw in cur.fetchall() or []:
        party = _row(raw)
        if party.get("party_role") == "witness" and not can_investigate:
            parties.append(
                {
                    "party_id": party.get("party_id"),
                    "party_role": "witness",
                    "visibility": party.get("visibility"),
                    "redacted": True,
                }
            )
        else:
            parties.append(party)

    cur.execute(
        """
        SELECT grant_id, actor_key, actor_role, permissions, granted_by_phone, created_at, revoked_at
          FROM er_access_grants
         WHERE company_code=%s AND case_id=%s
         ORDER BY created_at
        """,
        (company, case_id),
    )
    grants = [_row(r) for r in (cur.fetchall() or [])]

    cur.execute(
        """
        SELECT note_id, author_key, locked, created_at, updated_at, body_en, body_ar
          FROM er_investigation_notes
         WHERE company_code=%s AND case_id=%s
         ORDER BY created_at
        """,
        (company, case_id),
    )
    notes = []
    for raw in cur.fetchall() or []:
        note = _row(raw)
        if not can_investigate:
            note = {k: v for k, v in note.items() if k not in NOTE_BODY_KEYS}
            note["body_redacted"] = True
        notes.append(note)

    cur.execute(
        """
        SELECT finding_id, investigator_key, locked, submitted_at, created_at, findings_en, findings_ar
          FROM er_findings
         WHERE company_code=%s AND case_id=%s
         ORDER BY created_at
        """,
        (company, case_id),
    )
    findings = []
    for raw in cur.fetchall() or []:
        finding = _row(raw)
        if not (can_investigate or can_decide):
            finding = {k: v for k, v in finding.items() if k not in FINDING_BODY_KEYS}
            finding["body_redacted"] = True
        findings.append(finding)

    cur.execute(
        "SELECT * FROM er_evidence_refs WHERE company_code=%s AND case_id=%s ORDER BY created_at",
        (company, case_id),
    )
    evidence = []
    for raw in cur.fetchall() or []:
        evid = _row(raw)
        access = c4.access_evidence(
            cur,
            company_code=company,
            actor_key=actor_key,
            actor_role=actor_role,
            evidence_id=str(evid.get("evidence_id")),
            access_channel="api",
        )
        evidence.append(public_evidence(evid, allowed=bool(access.get("allowed"))))

    cur.execute(
        """
        SELECT outcome_id, outcome_code, outcome_version, employment_mutated, decided_by_phone,
               decided_at, summary_en, summary_ar
          FROM er_outcomes
         WHERE company_code=%s AND case_id=%s
         ORDER BY decided_at
        """,
        (company, case_id),
    )
    outcomes = []
    for raw in cur.fetchall() or []:
        outcome = _row(raw)
        if not (can_decide or can_manage):
            outcome["summary_en"] = ""
            outcome["summary_ar"] = ""
            outcome["reasoning_redacted"] = True
        outcomes.append(outcome)

    cur.execute(
        """
        SELECT handoff_id, outcome_id, target_authority, applied, employment_mutated_by_er,
               created_by_phone, created_at
          FROM er_employment_handoffs
         WHERE company_code=%s AND case_id=%s
         ORDER BY created_at
        """,
        (company, case_id),
    )
    handoffs = [_row(r) for r in (cur.fetchall() or [])]

    return strip_raw_urls(
        {
            "ok": True,
            "case": case,
            "intake": {
                "source": case.get("intake_source"),
                "submitted_at": case.get("opened_at"),
                "subject_employee_key": case.get("subject_employee_key"),
                "reporter_employee_key": case.get("reporter_employee_key") if can_investigate else None,
                "classification": case.get("case_type_code"),
                "allegation_proven": False,
                "submission_is_not_allegation_proven": True,
            },
            "allegations_meta": detail.get("allegations_meta") or [],
            "parties": parties,
            "participants": grants,
            "investigation": {
                "notes": notes,
                "status": case.get("status"),
                "assigned_investigator": case.get("assigned_investigator"),
                "investigation_is_not_finding": True,
            },
            "evidence": evidence,
            "findings": findings,
            "outcomes": outcomes,
            "handoffs": handoffs,
            "sla": detail.get("sla"),
            "finding_is_not_outcome": True,
            "outcome_is_not_employment_mutation": True,
            **honesty_payload(company_code=company),
        }
    )


def intake_case(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    actor_key: str,
    actor_role: str,
    case_type_id: str,
    subject_employee_key: str,
    intake_source: str,
    reporter_employee_key: str | None = None,
    summary_en: str = "",
    summary_ar: str = "",
    severity: str = "medium",
    due_date: str | None = None,
    allegation_en: str = "",
    allegation_ar: str = "",
) -> dict[str, Any]:
    ensure_schema(cur)
    result = c4.open_case(
        cur,
        company_code=company_code,
        actor_phone=actor_phone,
        case_type_id=case_type_id,
        subject_employee_key=subject_employee_key,
        intake_source=intake_source,
        actor_role=actor_role,
        actor_key=actor_key,
        reporter_employee_key=reporter_employee_key,
        summary_en=summary_en,
        summary_ar=summary_ar,
        severity=severity,
        due_date=due_date,
        allegation_en=allegation_en,
        allegation_ar=allegation_ar,
    )
    if result.get("ok"):
        result["intake_is_not_finding"] = True
        result["submission_is_not_allegation_proven"] = True
        result.update(honesty_payload(company_code=company_code))
    return result


def triage_case(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    actor_key: str,
    actor_role: str,
    case_id: str,
    reason: str = "triage",
) -> dict[str, Any]:
    denied = _require_grant(cur, c4.company_code_norm(company_code), case_id, actor_key, "manage")
    if denied:
        return denied
    return c4.transition_case(
        cur,
        company_code=company_code,
        actor_phone=actor_phone,
        actor_key=actor_key,
        actor_role=actor_role,
        case_id=case_id,
        to_status="triage",
        reason=reason,
    )


def assign_investigator(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    actor_key: str,
    actor_role: str,
    case_id: str,
    investigator_key: str,
) -> dict[str, Any]:
    denied = _require_grant(cur, c4.company_code_norm(company_code), case_id, actor_key, "manage")
    if denied:
        return denied
    return c4.assign_investigator(
        cur,
        company_code=company_code,
        actor_phone=actor_phone,
        actor_key=actor_key,
        actor_role=actor_role,
        case_id=case_id,
        investigator_key=investigator_key,
    )


def grant_access(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    actor_key: str,
    case_id: str,
    target_actor_key: str,
    target_actor_role: str,
    permissions: list[str],
) -> dict[str, Any]:
    denied = _require_grant(cur, c4.company_code_norm(company_code), case_id, actor_key, "manage")
    if denied:
        return denied
    return c4.grant_case_access(
        cur,
        company_code=company_code,
        actor_phone=actor_phone,
        case_id=case_id,
        actor_key=target_actor_key,
        actor_role=target_actor_role,
        permissions=permissions,
    )


def add_note(
    cur: Any,
    *,
    company_code: str,
    actor_key: str,
    actor_role: str,
    case_id: str,
    body_en: str,
    body_ar: str = "",
) -> dict[str, Any]:
    denied = _require_grant(cur, c4.company_code_norm(company_code), case_id, actor_key, "investigate")
    if denied:
        return denied
    return c4.add_investigation_note(
        cur,
        company_code=company_code,
        actor_key=actor_key,
        actor_role=actor_role,
        case_id=case_id,
        body_en=body_en,
        body_ar=body_ar,
    )


def attach_evidence(
    cur: Any,
    *,
    company_code: str,
    actor_key: str,
    actor_role: str,
    case_id: str,
    shared_document_ref: str,
    label_en: str = "",
    label_ar: str = "",
    sensitive: bool = True,
) -> dict[str, Any]:
    denied = _require_grant(cur, c4.company_code_norm(company_code), case_id, actor_key, "investigate")
    if denied:
        return denied
    result = c4.attach_evidence(
        cur,
        company_code=company_code,
        actor_key=actor_key,
        actor_role=actor_role,
        case_id=case_id,
        shared_document_ref=shared_document_ref,
        label_en=label_en,
        label_ar=label_ar,
        sensitive=sensitive,
    )
    if result.get("ok") and isinstance(result.get("evidence"), dict):
        result["evidence"] = public_evidence(result["evidence"], allowed=True)
    return strip_raw_urls(result)


def retrieve_evidence(
    cur: Any,
    *,
    company_code: str,
    actor_key: str,
    actor_role: str,
    evidence_id: str,
    access_channel: str = "api",
) -> dict[str, Any]:
    access = c4.access_evidence(
        cur,
        company_code=company_code,
        actor_key=actor_key,
        actor_role=actor_role,
        evidence_id=evidence_id,
        access_channel=access_channel,
    )
    if not access.get("allowed"):
        return strip_raw_urls(access)
    evid = dict(access.get("evidence") or {})
    return strip_raw_urls(
        {
            "ok": True,
            "allowed": True,
            "access_channel": access_channel,
            "sealed": True,
            "evidence": public_evidence(
                {
                    **evid,
                    "label_en": evid.get("label_en") or "",
                    "label_ar": evid.get("label_ar") or "",
                },
                allowed=True,
            ),
            "content_kind": "sealed_ref",
            "raw_provider_url": None,
        }
    )


def submit_finding(
    cur: Any,
    *,
    company_code: str,
    actor_key: str,
    actor_role: str,
    case_id: str,
    findings_en: str,
    findings_ar: str = "",
    lock: bool = True,
) -> dict[str, Any]:
    denied = _require_grant(cur, c4.company_code_norm(company_code), case_id, actor_key, "investigate")
    if denied:
        return denied
    result = c4.submit_finding(
        cur,
        company_code=company_code,
        actor_key=actor_key,
        actor_role=actor_role,
        case_id=case_id,
        findings_en=findings_en,
        findings_ar=findings_ar,
        lock=lock,
    )
    if result.get("ok"):
        result["investigation_is_not_finding"] = True
        result["finding_is_not_outcome"] = True
    return result


def record_outcome(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    actor_key: str,
    actor_role: str,
    case_id: str,
    outcome_code: str,
    summary_en: str = "",
    summary_ar: str = "",
) -> dict[str, Any]:
    denied = _require_grant(cur, c4.company_code_norm(company_code), case_id, actor_key, "decide")
    if denied:
        return denied
    result = c4.record_outcome(
        cur,
        company_code=company_code,
        actor_phone=actor_phone,
        actor_key=actor_key,
        actor_role=actor_role,
        case_id=case_id,
        outcome_code=outcome_code,
        summary_en=summary_en,
        summary_ar=summary_ar,
    )
    if result.get("ok"):
        result["outcome_is_not_employment_mutation"] = True
        result["employment_mutated"] = False
    return result


def close_case(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    actor_key: str,
    actor_role: str,
    case_id: str,
    reason: str = "closure",
) -> dict[str, Any]:
    denied = _require_grant(cur, c4.company_code_norm(company_code), case_id, actor_key, "manage")
    if denied:
        return denied
    return c4.transition_case(
        cur,
        company_code=company_code,
        actor_phone=actor_phone,
        actor_key=actor_key,
        actor_role=actor_role,
        case_id=case_id,
        to_status="closed",
        reason=reason,
    )


def create_handoff_idempotent(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    actor_key: str,
    actor_role: str,
    case_id: str,
    outcome_id: str,
    handoff_payload: dict | None = None,
) -> dict[str, Any]:
    company = c4.company_code_norm(company_code)
    denied = _require_grant(cur, company, case_id, actor_key, "decide")
    if denied:
        return denied
    cur.execute(
        """
        SELECT * FROM er_employment_handoffs
         WHERE company_code=%s AND case_id=%s AND outcome_id=%s
         ORDER BY created_at
         LIMIT 1
        """,
        (company, case_id, outcome_id),
    )
    existing = _row(cur.fetchone())
    if existing:
        return {
            "ok": True,
            "handoff": existing,
            "idempotent_replay": True,
            "applied": False,
            "employment_mutated_by_er": False,
            "outcome_is_not_employment_mutation": True,
            "wave3_employment_change_remains_authority": True,
        }
    result = c4.create_employment_change_handoff(
        cur,
        company_code=company,
        actor_phone=actor_phone,
        actor_key=actor_key,
        actor_role=actor_role,
        case_id=case_id,
        outcome_id=outcome_id,
        handoff_payload=handoff_payload,
    )
    if result.get("ok"):
        result["idempotent_replay"] = False
        result["outcome_is_not_employment_mutation"] = True
    return result


def case_history(
    cur: Any, *, company_code: str, actor_key: str, case_id: str, limit: int = 200
) -> dict[str, Any]:
    company = c4.company_code_norm(company_code)
    if not _has_grant(cur, company, case_id, actor_key):
        return _deny_need_to_know()
    cur.execute(
        """
        SELECT audit_id, case_id, actor_phone, action, entity_type, entity_id, detail, created_at
          FROM er_audit_events
         WHERE company_code=%s AND case_id=%s
         ORDER BY created_at
         LIMIT %s
        """,
        (company, case_id, max(1, min(int(limit or 200), 400))),
    )
    events = []
    for raw in cur.fetchall() or []:
        event = _row(raw)
        event["detail"] = _strip_keys(
            event.get("detail") or {}, NOTE_BODY_KEYS | FINDING_BODY_KEYS | ALLEGATION_TEXT_KEYS | RAW_URL_KEYS
        )
        events.append(event)
    return {
        "ok": True,
        "events": events,
        "total": len(events),
        "resource_state": "empty" if not events else "ready",
        "historically_reconstructable": True,
        **honesty_payload(company_code=company),
    }


def export_cases(
    cur: Any, *, company_code: str, actor_key: str, actor_role: str, limit: int = 200
) -> dict[str, Any]:
    listed = list_cases(
        cur, company_code=company_code, actor_key=actor_key, actor_role=actor_role, limit=limit
    )
    if listed.get("resource_state") == "unavailable":
        return listed
    rows = []
    for case in listed.get("cases") or []:
        rows.append(
            {
                "case_id": case.get("case_id"),
                "case_type_code": case.get("case_type_code"),
                "status": case.get("status"),
                "opened_at": case.get("opened_at"),
                "closed_at": case.get("closed_at"),
                "intake_source": case.get("intake_source"),
            }
        )
    return {
        "ok": True,
        "export": rows,
        "total": len(rows),
        "hidden_fields_excluded": True,
        "empty_assignment_is_not_company_wide": True,
        **honesty_payload(company_code=company_code),
    }


def scoped_contribution(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    actor_key: str,
    actor_role: str,
    case_id: str,
    body_en: str = "",
    body_ar: str = "",
) -> dict[str, Any]:
    company = c4.company_code_norm(company_code)
    if not _has_grant(cur, company, case_id, actor_key):
        return _deny_need_to_know()
    if _has_grant(cur, company, case_id, actor_key, "investigate"):
        note = c4.add_investigation_note(
            cur,
            company_code=company,
            actor_key=actor_key,
            actor_role=actor_role,
            case_id=case_id,
            body_en=body_en,
            body_ar=body_ar,
        )
        return {**note, "scoped_only": True, "full_case_access": False}
    c4._audit(
        cur,
        company=company,
        actor=actor_phone,
        action="scoped_contribution",
        entity_type="case",
        entity_id=case_id,
        case_id=case_id,
        detail={"scoped_only": True, "has_text": bool(body_en or body_ar)},
    )
    return {
        "ok": True,
        "scoped_only": True,
        "full_case_access": False,
        "contribution_recorded": True,
    }


def acknowledge_action(
    cur: Any, *, company_code: str, actor_phone: str, actor_key: str, case_id: str
) -> dict[str, Any]:
    company = c4.company_code_norm(company_code)
    if not _has_grant(cur, company, case_id, actor_key):
        return _deny_need_to_know()
    c4._audit(
        cur,
        company=company,
        actor=actor_phone,
        action="mobile_acknowledge",
        entity_type="case",
        entity_id=case_id,
        case_id=case_id,
        detail={"channel": "hr_mobile"},
    )
    return {"ok": True, "acknowledged": True, "safe_operational_action": True}


def mobile_queue(
    cur: Any, *, company_code: str, actor_key: str, actor_role: str, limit: int = 50
) -> dict[str, Any]:
    listed = list_cases(
        cur, company_code=company_code, actor_key=actor_key, actor_role=actor_role, limit=limit
    )
    if listed.get("resource_state") == "unavailable":
        return listed
    items = []
    for case in listed.get("cases") or []:
        if str(case.get("status") or "") in {"closed", "withdrawn", "dismissed"}:
            continue
        items.append(
            {
                "case_id": case.get("case_id"),
                "status": case.get("status"),
                "status_label_en": case.get("status_label_en"),
                "status_label_ar": case.get("status_label_ar"),
                "summary_en": GENERIC_ACTION_EN,
                "summary_ar": GENERIC_ACTION_AR,
                "destination": f"/employee-relations/{case.get('case_id')}",
                "allowed_actions": ["read", "acknowledge"],
            }
        )
    return {
        "ok": True,
        "items": items,
        "total": len(items),
        "resource_state": listed.get("resource_state"),
        "privacy_safe": True,
        **honesty_payload(company_code=company_code),
    }


def mobile_case_summary(
    cur: Any, *, company_code: str, actor_key: str, actor_role: str, case_id: str
) -> dict[str, Any]:
    if not _has_grant(cur, c4.company_code_norm(company_code), case_id, actor_key):
        return _deny_need_to_know()
    detail = c4.er_case_detail(
        cur, company_code=company_code, actor_key=actor_key, actor_role=actor_role, case_id=case_id
    )
    if not detail.get("ok"):
        return detail
    case = dict(detail.get("case") or {})
    return {
        "ok": True,
        "case_id": case.get("case_id"),
        "status": case.get("status"),
        "status_label_en": c4.status_label(str(case.get("status") or ""), lang="en"),
        "status_label_ar": c4.status_label(str(case.get("status") or ""), lang="ar"),
        "case_type_code": case.get("case_type_code"),
        "opened_at": case.get("opened_at"),
        "summary_en": GENERIC_ACTION_EN,
        "summary_ar": GENERIC_ACTION_AR,
        "web_deep_link": f"/employee-relations/{case.get('case_id')}",
        "notes_included": False,
        "evidence_included": False,
        "findings_included": False,
        "witnesses_included": False,
        "privacy_safe": True,
        **honesty_payload(company_code=company_code),
    }


def assistant_query(
    cur: Any,
    *,
    company_code: str,
    actor_key: str,
    question_kind: str,
    case_id: str | None = None,
) -> dict[str, Any]:
    if question_kind in {"mutate_case", "dump_notes", "access_evidence", "decide_outcome"}:
        return c4.assistant_query_er(
            cur, company_code=company_code, actor=actor_key, question_kind=question_kind, case_id=case_id
        )
    if case_id and not _has_grant(cur, c4.company_code_norm(company_code), case_id, actor_key):
        return {"ok": False, "error": "er_access_denied", "mutations": False, "no_case_narrative_dump": True}
    result = c4.assistant_query_er(
        cur, company_code=company_code, actor=actor_key, question_kind=question_kind, case_id=case_id
    )
    return strip_raw_urls(_strip_keys(result, NOTE_BODY_KEYS | FINDING_BODY_KEYS | ALLEGATION_TEXT_KEYS))


def privacy_safe_notification(*, template_key: str) -> dict[str, str]:
    _ = template_key
    return {
        "text": GENERIC_ACTION_EN,
        "text_ar": GENERIC_ACTION_AR,
        "subject": "Employee Relations",
        "payload_safe": "true",
    }
