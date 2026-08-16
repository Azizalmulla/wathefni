"""Super Admin onboarding wizard state machine (Wave 4).

Autosaved drafts. Selecting modules never makes them live.
Candidate Knowledge / Talent Pool never appear as purchased products.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import module_catalog as modules
import tenant_control_config as tc_config
import tenant_control_decision as decision
import tenant_control_integrations as tc_integ
import tenant_control_lifecycle as lifecycle
import tenant_control_readiness as tc_ready
import tenant_control_wave4_schema as wave4


WIZARD_STEPS: tuple[dict[str, Any], ...] = (
    {"step": 1, "key": "company", "en": "Company", "ar": "الشركة"},
    {"step": 2, "key": "modules", "en": "Purchased modules", "ar": "الوحدات المشتراة"},
    {"step": 3, "key": "structure", "en": "Company structure", "ar": "هيكل الشركة"},
    {"step": 4, "key": "admins", "en": "Administrators and roles", "ar": "المسؤولون والأدوار"},
    {"step": 5, "key": "module_config", "en": "Module configuration", "ar": "إعداد الوحدات"},
    {"step": 6, "key": "policies", "en": "Policies and workflows", "ar": "السياسات وسير العمل"},
    {"step": 7, "key": "integrations", "en": "Integrations", "ar": "التكاملات"},
    {"step": 8, "key": "data", "en": "Data and imports", "ar": "البيانات والاستيراد"},
    {"step": 9, "key": "readiness", "en": "Readiness", "ar": "الجاهزية"},
    {"step": 10, "key": "review", "en": "Review and activate", "ar": "المراجعة والتفعيل"},
)

BACKEND_ONLY_MODULE_KEYS = frozenset({"candidate_knowledge", "talent_pool"})


def ensure_schema(cur: Any) -> dict[str, Any]:
    return wave4.ensure_tenant_control_schema(cur)


def wizard_steps(*, locale: str = "en") -> list[dict[str, Any]]:
    loc = "ar" if str(locale).lower().startswith("ar") else "en"
    return [
        {"step": s["step"], "key": s["key"], "label": s[loc], "label_en": s["en"], "label_ar": s["ar"]}
        for s in WIZARD_STEPS
    ]


def purchasable_modules() -> list[dict[str, Any]]:
    out = []
    for spec in modules.MODULE_CATALOG:
        if spec.key in BACKEND_ONLY_MODULE_KEYS:
            continue
        out.append(
            {
                "key": spec.key,
                "label": spec.label,
                "suite": spec.suite,
                "depends_on": list(spec.depends_on),
                "backend_only": False,
            }
        )
    return out


def create_or_resume_draft(
    cur: Any,
    *,
    actor: str,
    company_code: str | None = None,
    synthetic: bool = False,
    locale: str = "en",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    ensure_schema(cur)
    if company_code and not synthetic:
        # External company creation remains blocked in Wave 4 qualification.
        # Existing company drafts (WATHEFNI) are allowed for control-plane editing.
        company = str(company_code).upper()
        cur.execute("SELECT 1 FROM companies WHERE company_code=%s", (company,))
        if not cur.fetchone() and company != "WATHEFNI":
            return {"ok": False, "error": "external_company_creation_blocked"}
    idem = idempotency_key or f"wizard-{uuid4().hex}"
    cur.execute(
        """
        INSERT INTO tc_onboarding_wizard_drafts (
          company_code, synthetic, externally_usable, current_step, status, locale,
          draft_json, progress_json, owned_by, idempotency_key, correlation_id
        ) VALUES (%s,%s,false,1,'in_progress',%s,%s::jsonb,%s::jsonb,%s,%s,%s)
        ON CONFLICT (idempotency_key) DO UPDATE SET updated_at=now()
        RETURNING draft_id::text AS draft_id, current_step, status, draft_json, progress_json,
                  company_code, synthetic, locale
        """,
        (
            (company_code or "").upper() or None,
            synthetic,
            "ar" if str(locale).lower().startswith("ar") else "en",
            json.dumps({"modules_purchased": [], "modules_live": []}),
            json.dumps({"completed_steps": []}),
            actor,
            idem,
            uuid4().hex,
        ),
    )
    row = dict(cur.fetchone())
    return {"ok": True, **row, "steps": wizard_steps(locale=row.get("locale") or "en")}


def get_draft(cur: Any, *, draft_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT draft_id::text AS draft_id, company_code, synthetic, externally_usable,
               current_step, status, locale, draft_json, progress_json, updated_at
        FROM tc_onboarding_wizard_drafts WHERE draft_id=%s
        """,
        (draft_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def autosave_draft(
    cur: Any,
    *,
    draft_id: str,
    patch: dict[str, Any],
    current_step: int | None = None,
    actor: str,
) -> dict[str, Any]:
    draft = get_draft(cur, draft_id=draft_id)
    if not draft:
        return {"ok": False, "error": "draft_not_found"}
    body = draft.get("draft_json") or {}
    if isinstance(body, str):
        body = json.loads(body)
    body = {**body, **(patch or {})}
    # Never allow backend-only products as purchased.
    purchased = [m for m in (body.get("modules_purchased") or []) if m not in BACKEND_ONLY_MODULE_KEYS]
    body["modules_purchased"] = purchased
    body["modules_live"] = []  # selecting never makes live
    body["backend_capabilities"] = {
        "candidate_knowledge": True,
        "talent_pool": True,
        "hr_visible_products": ["Candidates"],
    }
    progress = draft.get("progress_json") or {}
    if isinstance(progress, str):
        progress = json.loads(progress)
    completed = set(progress.get("completed_steps") or [])
    step = int(current_step or draft["current_step"])
    if step >= 1:
        completed.add(step)
    progress["completed_steps"] = sorted(completed)
    progress["last_actor"] = actor
    cur.execute(
        """
        UPDATE tc_onboarding_wizard_drafts
        SET draft_json=%s::jsonb,
            progress_json=%s::jsonb,
            current_step=%s,
            updated_at=now()
        WHERE draft_id=%s
        RETURNING draft_id::text AS draft_id, current_step, status, draft_json, progress_json
        """,
        (json.dumps(body), json.dumps(progress), step, draft_id),
    )
    row = dict(cur.fetchone())
    return {"ok": True, **row, "autosaved": True}


def validate_step(cur: Any, *, draft_id: str, step: int) -> dict[str, Any]:
    draft = get_draft(cur, draft_id=draft_id)
    if not draft:
        return {"ok": False, "error": "draft_not_found"}
    body = draft.get("draft_json") or {}
    if isinstance(body, str):
        body = json.loads(body)
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if step == 1 and not (body.get("company") or {}).get("display_name"):
        blockers.append({"code": "company_name_required", "remediation": "Enter the company display name."})
    if step == 2:
        purchased = body.get("modules_purchased") or []
        if not purchased:
            blockers.append({"code": "modules_required", "remediation": "Select at least one purchased module."})
        if any(m in BACKEND_ONLY_MODULE_KEYS for m in purchased):
            blockers.append({"code": "backend_capability_not_purchasable", "remediation": "Candidate Knowledge and Talent Pool are not separate products."})
        gaps = modules.missing_module_dependencies(purchased)
        for gap in gaps:
            blockers.append({"code": "dependency_missing", "remediation": f"Enable required dependency for {gap}."})
    if step == 7:
        for provider in body.get("integrations_selected") or []:
            p = tc_integ.PROVIDER_BY_KEY.get(provider)
            if p and not p.selectable:
                blockers.append({"code": "provider_unavailable", "remediation": f"{p.label} is not available."})
    if step == 9:
        company = draft.get("company_code") or (body.get("company") or {}).get("company_code")
        if company:
            report = tc_ready.evaluate_readiness(cur, company_code=str(company).upper())
            if not report.get("ready"):
                blockers.append({"code": "readiness_incomplete", "remediation": "Resolve readiness blockers before activation."})
        else:
            warnings.append({"code": "readiness_deferred", "remediation": "Bind a company code before final readiness."})
    if step == 10 and (body.get("modules_live") or []):
        blockers.append({"code": "live_without_activation", "remediation": "Modules become live only after activation approval."})
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, "step": step}


def impact_preview(
    cur: Any,
    *,
    company_code: str,
    action: str,
    module_key: str | None = None,
    actor: str = "system",
) -> dict[str, Any]:
    ensure_schema(cur)
    company = company_code.upper()
    tenant = decision.load_tenant_state(cur, company)
    preview = {
        "action": action,
        "module_key": module_key,
        "navigation": "filtered by enabled/live modules after activation",
        "apis": "entitlement + lifecycle gates",
        "mobile": "same module surface filters",
        "ai_tools": "tool entitlement gates",
        "workers": "epoch + lifecycle claim gates",
        "timers": "per-company module automation gates",
        "queued_work": "stale-epoch hold/cancel",
        "webhooks": "surface gate",
        "intake": "pre_hiring surface gate",
        "integrations": "kill switch / degraded block side effects",
        "notifications": "outbound delivery gates",
        "dependent_modules": [],
    }
    if module_key:
        deps = modules.missing_module_dependencies([module_key])
        preview["dependent_modules"] = deps
        state = decision.load_module_state(cur, tenant["tenant_id"], module_key) if tenant else None
        preview["current_state"] = state
    cur.execute(
        """
        INSERT INTO tc_impact_previews (company_code, action, module_key, preview_json, actor)
        VALUES (%s,%s,%s,%s::jsonb,%s)
        RETURNING preview_id::text AS preview_id
        """,
        (company, action, module_key, json.dumps(preview, default=str), actor),
    )
    preview_id = (cur.fetchone() or {}).get("preview_id")
    return {"ok": True, "preview_id": preview_id, "preview": preview}


def control_page_snapshot(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_schema(cur)
    company = company_code.upper()
    tenant = decision.load_tenant_state(cur, company)
    if not tenant:
        return {"ok": False, "error": "tenant_not_imported"}
    cur.execute(
        """
        SELECT module_key, purchased, enabled, configured, tested, ready, live, paused, degraded, blocked,
               activation_epoch
        FROM tc_tenant_module_instances WHERE tenant_id=%s ORDER BY module_key
        """,
        (tenant["tenant_id"],),
    )
    module_rows = [dict(r) for r in cur.fetchall()]
    # Hide backend-only keys if present
    module_rows = [m for m in module_rows if m["module_key"] not in BACKEND_ONLY_MODULE_KEYS]
    for row in module_rows:
        row["testing"] = bool(row.get("tested"))
        row["setup_required"] = bool(row.get("purchased") or row.get("enabled")) and not bool(row.get("configured"))
    cur.execute(
        """
        SELECT provider_key, channel_key, state, support_tier, kill_switch, last_tested_at, last_verified_at
        FROM tc_integrations WHERE company_code=%s ORDER BY provider_key
        """,
        (company,),
    )
    integrations = [dict(r) for r in cur.fetchall()]
    readiness = tc_ready.evaluate_readiness(cur, company_code=company)
    cur.execute(
        """
        SELECT event_type, actor, created_at, detail
        FROM tc_audit_events WHERE company_code=%s
        ORDER BY created_at DESC LIMIT 50
        """,
        (company,),
    )
    audit = [dict(r) for r in cur.fetchall()]
    domains = {d: tc_config.get_published(cur, company_code=company, domain=d) for d in tc_config.DOMAIN_SCHEMAS}
    return {
        "ok": True,
        "company_code": company,
        "overview": {
            "lifecycle_status": tenant.get("lifecycle_status"),
            "activation_epoch": tenant.get("activation_epoch"),
            "externally_usable": tenant.get("externally_usable"),
            "synthetic": tenant.get("synthetic"),
        },
        "modules": module_rows,
        "integrations": integrations,
        "policies": {k: (v.get("version_number") if v else None) for k, v in domains.items()},
        "readiness": readiness,
        "health": {"orchestrator": "see /health", "delivery_sweep": "see systemd"},
        "audit_history": audit,
        "providers_unavailable": [p.provider_key for p in tc_integ.PROVIDER_CATALOG if not p.selectable],
    }


def create_import_batch(
    cur: Any,
    *,
    company_code: str,
    import_kind: str,
    mapping: dict[str, Any],
    rows: list[dict[str, Any]],
    actor: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    ensure_schema(cur)
    # Validation + duplicate detection (deterministic, no external import).
    seen = set()
    duplicates = []
    valid = []
    for idx, row in enumerate(rows):
        key = json.dumps(row, sort_keys=True, default=str)
        if key in seen:
            duplicates.append({"index": idx, "row": row})
        else:
            seen.add(key)
            valid.append(row)
    validation = {
        "ok": True,
        "row_count": len(rows),
        "valid_count": len(valid),
        "duplicate_count": len(duplicates),
        "duplicates": duplicates[:20],
    }
    preview = {"would_import": len(valid), "dry_run": dry_run, "sample": valid[:5]}
    cur.execute(
        """
        INSERT INTO tc_import_batches (
          company_code, import_kind, status, mapping_json, validation_json, preview_json, dry_run, actor
        ) VALUES (%s,%s,'previewed',%s::jsonb,%s::jsonb,%s::jsonb,%s,%s)
        RETURNING batch_id::text AS batch_id, status
        """,
        (
            company_code.upper(),
            import_kind,
            json.dumps(mapping),
            json.dumps(validation),
            json.dumps(preview),
            dry_run,
            actor,
        ),
    )
    row = dict(cur.fetchone())
    return {"ok": True, **row, "validation": validation, "preview": preview, "imported": False if dry_run else None}


def offboarding_preview(cur: Any, *, company_code: str, actor: str) -> dict[str, Any]:
    ensure_schema(cur)
    company = company_code.upper()
    in_flight = {
        "queued_jobs": "hold or cancel",
        "webhooks": "reject while suspended",
        "notifications": "blocked by lifecycle/integration gates",
        "safe_choices": ["hold", "cancel"],
        "drain_allowed": False,
    }
    if company == "WATHEFNI":
        in_flight["wathefni_suspension"] = "requires explicit canary authorization token"
    cur.execute(
        """
        INSERT INTO tc_offboarding_runs (company_code, status, in_flight_json, choices_json, actor)
        VALUES (%s,'draft',%s::jsonb,%s::jsonb,%s)
        RETURNING run_id::text AS run_id
        """,
        (company, json.dumps(in_flight), json.dumps({"hold": True, "cancel": True, "drain": False}), actor),
    )
    run_id = (cur.fetchone() or {}).get("run_id")
    return {"ok": True, "run_id": run_id, "in_flight": in_flight}
