"""Setup Console Phase 4 — Team & access + Integrations catalog.

Reuses canonical dashboard_users / ROLE_PERMISSIONS and existing integration
stores. Does not invent parallel role, permission, connector, or credential SoT.
Day-to-day invites remain Settings → Team; Setup owns summary + Owner seed.
"""
from __future__ import annotations

import json
from typing import Any

PHASE = "setup_console_phase4"
CONTRACT_VERSION = "admin_integrations_v1"

# Human access buckets — never expose raw permission codes to normal admins.
ACCESS_BUCKETS: tuple[tuple[str, str, str, frozenset[str]], ...] = (
    ("company_admin", "Company administration", "إدارة الشركة", frozenset({"users.manage", "settings.manage", "audit.read"})),
    ("hiring", "Hiring", "التوظيف", frozenset({"jobs.create", "jobs.edit", "candidate.manage", "interview.manage", "offer.manage"})),
    ("hr_ops", "HR operations", "عمليات الموارد البشرية", frozenset({"leave.decide", "attendance.manage", "shifts.manage", "onboarding.manage", "compliance.manage"})),
    ("payroll", "Payroll", "الرواتب", frozenset({"payroll.manage", "payroll.approve", "payroll.export"})),
    ("reports", "Reports", "التقارير", frozenset({"report.export", "analytics.read"})),
)

OWNER_ROLE_KEYS = frozenset({"owner", "admin", "company_admin"})

# Customer-facing integration catalog — only real/supported surfaces.
# Do not list IMAP / SMS / future stubs as available products.
INTEGRATION_CARDS: tuple[dict[str, Any], ...] = (
    {
        "key": "company_messaging",
        "label_en": "Company messaging",
        "label_ar": "مراسلة الشركة",
        "purpose_en": "Company WhatsApp account and channel policy for candidates and employees.",
        "purpose_ar": "حساب واتساب الشركة وسياسة القنوات للمرشحين والموظفين.",
        "configure_href": "/setup-console#classic-channels",
        "activity_href": None,
        "family": "channels",
    },
    {
        "key": "connected_systems",
        "label_en": "Connected systems",
        "label_ar": "الأنظمة المتصلة",
        "purpose_en": "HR / payroll file feeds and sync into employee records.",
        "purpose_ar": "تغذيات ملفات الموارد البشرية/الرواتب ومزامنتها إلى سجلات الموظفين.",
        "configure_href": "/dashboard?page=employees&view=migration",
        "activity_href": "/dashboard?page=employees&view=migration",
        "family": "migration",
    },
    {
        "key": "outbound_email",
        "label_en": "Company email delivery",
        "label_ar": "تسليم بريد الشركة",
        "purpose_en": "How the company sends email through OctoHR.",
        "purpose_ar": "كيف ترسل الشركة البريد عبر OctoHR.",
        "configure_href": "/setup-console#control",
        "activity_href": None,
        "family": "email",
        "tc_providers": ("postmark_outbound",),
    },
    {
        "key": "inbound_email",
        "label_en": "Recruitment inbox",
        "label_ar": "صندوق الوارد للتوظيف",
        "purpose_en": "Inbound CV / application email for hiring.",
        "purpose_ar": "بريد السير الذاتية والطلبات الوارد للتوظيف.",
        "configure_href": "/dashboard?page=settings",
        "activity_href": None,
        "family": "email",
        "tc_providers": ("postmark_inbound", "gmail_gog"),
    },
    {
        "key": "google_calendar",
        "label_en": "Google Calendar",
        "label_ar": "تقويم Google",
        "purpose_en": "Company calendar and meeting connection.",
        "purpose_ar": "ربط تقويم الشركة والاجتماعات.",
        "configure_href": "/dashboard?page=settings",
        "activity_href": None,
        "family": "calendar",
        "platform_provider": "google_workspace",
        "tc_providers": ("google_calendar",),
    },
    {
        "key": "microsoft_365",
        "label_en": "Microsoft 365",
        "label_ar": "Microsoft 365",
        "purpose_en": "Outlook calendar and Teams meeting connection.",
        "purpose_ar": "ربط تقويم Outlook واجتماعات Teams.",
        "configure_href": "/dashboard?page=settings",
        "activity_href": None,
        "family": "calendar",
        "platform_provider": "microsoft_365",
        "tc_providers": ("microsoft_365", "microsoft_teams"),
    },
)


def _company(code: str) -> str:
    return str(code or "").upper()


def access_summary_for_permissions(permissions: set[str] | list[str] | frozenset[str]) -> dict[str, Any]:
    perms = set(permissions or [])
    labels_en: list[str] = []
    labels_ar: list[str] = []
    keys: list[str] = []
    for key, en, ar, needles in ACCESS_BUCKETS:
        if perms & needles:
            keys.append(key)
            labels_en.append(en)
            labels_ar.append(ar)
    if not labels_en:
        labels_en = ["View access"]
        labels_ar = ["وصول للعرض"]
        keys = ["view"]
    return {
        "keys": keys,
        "summary_en": " · ".join(labels_en),
        "summary_ar": " · ".join(labels_ar),
    }


def role_preset_catalog(legacy: Any) -> list[dict[str, Any]]:
    labels = getattr(legacy, "ROLE_LABELS", {}) or {}
    perms_map = getattr(legacy, "ROLE_PERMISSIONS", {}) or {}
    out = []
    for role_key, label in labels.items():
        perms = set(perms_map.get(role_key) or [])
        summary = access_summary_for_permissions(perms)
        out.append(
            {
                "role": role_key,
                "label_en": label,
                "label_ar": label,  # Arabic role labels not yet localized in ROLE_LABELS
                "access_summary_en": summary["summary_en"],
                "access_summary_ar": summary["summary_ar"],
                "is_company_admin": role_key in OWNER_ROLE_KEYS or role_key == "owner",
                "can_manage_team": "users.manage" in perms,
            }
        )
    return out


def count_active_owners(cur: Any, company_code: str) -> int:
    company = _company(company_code)
    cur.execute(
        """
        SELECT count(*) AS c
        FROM dashboard_users
        WHERE company_code=%s
          AND lower(COALESCE(role,'')) IN ('owner','admin','company_admin')
          AND lower(COALESCE(status,'')) = 'active'
        """,
        (company,),
    )
    row = cur.fetchone()
    if isinstance(row, dict):
        return int(row.get("c") or 0)
    return int((row or [0])[0] or 0)


def role_grant_allowed(*, actor_permissions: set[str] | list[str] | frozenset[str], target_role: str, legacy: Any) -> tuple[bool, str | None]:
    """Admins cannot assign a role whose preset permissions exceed their own."""
    role_key = legacy.dashboard_role_key(target_role) if hasattr(legacy, "dashboard_role_key") else str(target_role or "").strip().lower()
    if not hasattr(legacy, "dashboard_role_allowed") or not legacy.dashboard_role_allowed(target_role):
        return False, "invalid_role"
    target_perms = set((getattr(legacy, "ROLE_PERMISSIONS", {}) or {}).get(role_key) or [])
    actor = set(actor_permissions or [])
    if not target_perms.issubset(actor):
        return False, "privilege_escalation_denied"
    return True, None


def assert_last_owner_safe(
    cur: Any,
    *,
    company_code: str,
    target_user: dict[str, Any],
    new_role: str | None,
    new_status: str | None,
    legacy: Any,
) -> dict[str, Any] | None:
    """Return error detail if change would orphan the company (no active owner)."""
    company = _company(company_code)
    current_role = str(target_user.get("role") or "").strip().lower()
    current_status = str(target_user.get("status") or "").strip().lower()
    if current_role not in OWNER_ROLE_KEYS or current_status != "active":
        return None
    demoting = False
    if new_role is not None:
        next_role = legacy.dashboard_role_key(new_role) if hasattr(legacy, "dashboard_role_key") else str(new_role).strip().lower()
        if next_role not in OWNER_ROLE_KEYS:
            demoting = True
    if new_status is not None and str(new_status).strip().lower() == "disabled":
        demoting = True
    if not demoting:
        return None
    owners = count_active_owners(cur, company)
    if owners <= 1:
        return {
            "error": "last_owner_protected",
            "message_en": "This company needs at least one active Company Admin. Add or activate another admin before changing this one.",
            "message_ar": "تحتاج هذه الشركة إلى مسؤول شركة نشط واحد على الأقل. أضف أو فعّل مسؤولاً آخر قبل تغيير هذا الحساب.",
        }
    return None


def get_team_access(cur: Any, company_code: str, *, legacy: Any) -> dict[str, Any]:
    company = _company(company_code)
    cur.execute(
        """
        SELECT user_id, email, name, phone, role, status, invited_at, accepted_at, disabled_at, created_at, updated_at
        FROM dashboard_users
        WHERE company_code=%s
        ORDER BY
          CASE lower(COALESCE(status,''))
            WHEN 'active' THEN 0 WHEN 'invited' THEN 1 WHEN 'disabled' THEN 2 ELSE 3 END,
          lower(COALESCE(name,'')), lower(COALESCE(email,''))
        """,
        (company,),
    )
    members = []
    owner_count = 0
    for row in cur.fetchall() or []:
        d = dict(row) if isinstance(row, dict) else {
            "user_id": row[0], "email": row[1], "name": row[2], "phone": row[3],
            "role": row[4], "status": row[5], "invited_at": row[6], "accepted_at": row[7],
            "disabled_at": row[8], "created_at": row[9], "updated_at": row[10],
        }
        role_key = legacy.dashboard_role_key(d.get("role")) if hasattr(legacy, "dashboard_role_key") else str(d.get("role") or "")
        if role_key in OWNER_ROLE_KEYS and str(d.get("status") or "").lower() == "active":
            owner_count += 1
        try:
            perms = set(legacy.dashboard_effective_permissions_for_user(d, cur=cur) or [])
        except Exception:
            perms = set((getattr(legacy, "ROLE_PERMISSIONS", {}) or {}).get(role_key) or [])
        summary = access_summary_for_permissions(perms)
        label = (getattr(legacy, "ROLE_LABELS", {}) or {}).get(role_key) or role_key.replace("_", " ").title()
        members.append(
            {
                "user_id": str(d.get("user_id") or ""),
                "name": d.get("name") or "",
                "email": d.get("email") or "",
                "phone": d.get("phone") or "",
                "role": role_key,
                "role_label_en": label,
                "role_label_ar": label,
                "status": str(d.get("status") or ""),
                "access_summary_en": summary["summary_en"],
                "access_summary_ar": summary["summary_ar"],
                "access_keys": summary["keys"],
                # Never include raw permission codes for normal admin UX.
            }
        )
    pending = sum(1 for m in members if m.get("status") == "invited")
    return {
        "ok": True,
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "company_code": company,
        "members": members,
        "active_owner_count": owner_count,
        "pending_invites": pending,
        "role_presets": role_preset_catalog(legacy),
        "ownership": {
            "owner_seed": "setup_console",
            "day_to_day_invites": "settings_team",
            "permission_authority": "backend_role_presets",
            "writer": "settings_team",
            "setup_href": "/setup-console#classic-team-access",
            "manage_href": "/dashboard?page=settings",
        },
        "safety": {
            "last_owner_protected": True,
            "privilege_escalation_denied": True,
            "grants_ui": False,
            "grants_note_en": "Extra permissions beyond role presets stay on the audited ops path.",
            "grants_note_ar": "الصلاحيات الإضافية خارج الأدوار تبقى في مسار العمليات الخاضع للتدقيق.",
        },
    }


def _tc_integration_rows(cur: Any, company: str) -> dict[str, dict[str, Any]]:
    try:
        cur.execute(
            """
            SELECT provider_key, state, support_tier, kill_switch, last_verified_at
            FROM tc_integrations
            WHERE company_code=%s
            """,
            (company,),
        )
    except Exception:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in cur.fetchall() or []:
        d = dict(row) if isinstance(row, dict) else {
            "provider_key": row[0], "state": row[1], "support_tier": row[2],
            "kill_switch": row[3], "last_verified_at": row[4],
        }
        out[str(d.get("provider_key") or "")] = d
    return out


def _channel_status(cur: Any, company: str, legacy: Any) -> dict[str, Any]:
    account = None
    try:
        cur.execute(
            """
            SELECT provider, provider_account_id, sender_phone, status, audiences
            FROM company_channel_accounts
            WHERE company_code=%s
            LIMIT 1
            """,
            (company,),
        )
        row = cur.fetchone()
        if row:
            account = dict(row) if isinstance(row, dict) else {
                "provider": row[0], "provider_account_id": row[1], "sender_phone": row[2],
                "status": row[3], "audiences": row[4],
            }
    except Exception:
        account = None
    policy_reviewed = False
    try:
        # company_settings jsonb
        if hasattr(legacy, "company_settings_payload"):
            settings = legacy.company_settings_payload(company) or {}
        else:
            cur.execute("SELECT settings FROM company_settings WHERE company_code=%s LIMIT 1", (company,))
            row = cur.fetchone()
            settings = dict(row).get("settings") if row else {}
            if isinstance(settings, str):
                settings = json.loads(settings)
        if isinstance(settings, dict):
            policy_reviewed = bool(settings.get("channel_policy_reviewed") or settings.get("reviewed"))
    except Exception:
        policy_reviewed = False
    if account and str(account.get("status") or "").lower() in {"verified", "active", "live"}:
        status = "connected"
    elif account:
        status = "needs_attention"
    elif policy_reviewed:
        status = "needs_attention"
    else:
        status = "not_connected"
    return {
        "status": status,
        "has_credentials": False,  # channel account stores ids only
        "detail_en": "Verified" if status == "connected" else ("Account pending" if account else "Not configured"),
        "detail_ar": "موثّق" if status == "connected" else ("الحساب قيد الإكمال" if account else "غير مضبوط"),
        "account_status": (account or {}).get("status"),
        "policy_reviewed": policy_reviewed,
    }


def _migration_status(cur: Any, company: str) -> dict[str, Any]:
    try:
        cur.execute(
            """
            SELECT connection_id, name, connector_kind, status, last_success_at, last_error_summary,
                   EXISTS (
                     SELECT 1 FROM employee_migration_connection_secrets s
                     WHERE s.connection_id = c.connection_id
                   ) AS has_credentials
            FROM employee_migration_connections c
            WHERE company_code=%s AND status <> 'deleted'
            ORDER BY updated_at DESC NULLS LAST
            """,
            (company,),
        )
        rows = [dict(r) if isinstance(r, dict) else {
            "connection_id": r[0], "name": r[1], "connector_kind": r[2], "status": r[3],
            "last_success_at": r[4], "last_error_summary": r[5], "has_credentials": r[6],
        } for r in (cur.fetchall() or [])]
    except Exception:
        rows = []
    # Filter out unavailable stubs from catalog advertising
    real = [r for r in rows if str(r.get("connector_kind") or "") not in {"api_stub", "sftp_stub"}]
    if not real:
        return {
            "status": "not_connected",
            "has_credentials": False,
            "connection_count": 0,
            "detail_en": "No connected systems yet",
            "detail_ar": "لا توجد أنظمة متصلة بعد",
            "connections": [],
        }
    attention = [
        r for r in real
        if str(r.get("status") or "").lower() in {"error", "needs_attention", "disabled"}
        or str(r.get("last_error_summary") or "").startswith("credentials_require_reentry")
    ]
    live = [r for r in real if str(r.get("status") or "").lower() in {"active", "ready", "connected", "live"}]
    if attention:
        status = "needs_attention"
    elif live:
        status = "connected"
    else:
        status = "needs_attention"
    # Never return secrets — only has_credentials flags
    public_connections = [
        {
            "name": r.get("name"),
            "kind": r.get("connector_kind"),
            "status": r.get("status"),
            "has_credentials": bool(r.get("has_credentials")),
            "last_success_at": str(r.get("last_success_at") or "") or None,
        }
        for r in real[:8]
    ]
    return {
        "status": status,
        "has_credentials": any(bool(r.get("has_credentials")) for r in real),
        "connection_count": len(real),
        "detail_en": f"{len(real)} connection(s)",
        "detail_ar": f"{len(real)} اتصال",
        "connections": public_connections,
    }


def _platform_status(cur: Any, company: str, provider: str) -> dict[str, Any]:
    try:
        cur.execute(
            """
            SELECT i.status, i.account_email,
                   EXISTS (
                     SELECT 1 FROM platform_company_integration_credentials c
                     WHERE c.integration_id = i.integration_id
                   ) AS has_credentials
            FROM platform_company_integrations i
            WHERE i.company_code=%s AND i.provider_key=%s
            LIMIT 1
            """,
            (company, provider),
        )
        row = cur.fetchone()
    except Exception:
        row = None
    if not row:
        return {
            "status": "not_connected",
            "has_credentials": False,
            "detail_en": "Not connected",
            "detail_ar": "غير متصل",
        }
    d = dict(row) if isinstance(row, dict) else {"status": row[0], "account_email": row[1], "has_credentials": row[2]}
    st = str(d.get("status") or "").lower()
    if st in {"connected", "active", "live", "healthy"}:
        status = "connected"
    elif st in {"error", "needs_reauth", "revoked"}:
        status = "needs_attention"
    else:
        status = "needs_attention" if d.get("has_credentials") else "not_connected"
    email = d.get("account_email") or ""
    return {
        "status": status,
        "has_credentials": bool(d.get("has_credentials")),
        "detail_en": email or ("Configured" if d.get("has_credentials") else "Not connected"),
        "detail_ar": email or ("مضبوط" if d.get("has_credentials") else "غير متصل"),
        # Never return tokens
    }


def _email_card_status(tc: dict[str, dict[str, Any]], providers: tuple[str, ...]) -> dict[str, Any]:
    hits = [tc[p] for p in providers if p in tc]
    if not hits:
        return {"status": "not_connected", "has_credentials": False, "detail_en": "Not configured", "detail_ar": "غير مضبوط"}
    if any(bool(h.get("kill_switch")) for h in hits):
        return {"status": "needs_attention", "has_credentials": False, "detail_en": "Paused", "detail_ar": "متوقف"}
    live = [h for h in hits if str(h.get("state") or "").lower() in {"live", "active", "connected", "ready"}]
    if live:
        return {"status": "connected", "has_credentials": False, "detail_en": "Live", "detail_ar": "يعمل"}
    return {"status": "needs_attention", "has_credentials": False, "detail_en": "Needs attention", "detail_ar": "يحتاج انتباهاً"}


def get_integrations_catalog(cur: Any, company_code: str, *, legacy: Any) -> dict[str, Any]:
    company = _company(company_code)
    tc = _tc_integration_rows(cur, company)
    channel = _channel_status(cur, company, legacy)
    migration = _migration_status(cur, company)
    cards = []
    for spec in INTEGRATION_CARDS:
        key = spec["key"]
        if key == "company_messaging":
            state = channel
        elif key == "connected_systems":
            state = migration
        elif key in {"outbound_email", "inbound_email"}:
            state = _email_card_status(tc, tuple(spec.get("tc_providers") or ()))
        elif key in {"google_calendar", "microsoft_365"}:
            state = _platform_status(cur, company, str(spec.get("platform_provider") or ""))
            # Enrich from tc if platform row missing but tc says live
            if state.get("status") == "not_connected":
                tc_state = _email_card_status(tc, tuple(spec.get("tc_providers") or ()))
                if tc_state.get("status") == "connected":
                    state = tc_state
        else:
            continue
        cards.append(
            {
                "key": key,
                "label_en": spec["label_en"],
                "label_ar": spec["label_ar"],
                "purpose_en": spec["purpose_en"],
                "purpose_ar": spec["purpose_ar"],
                "status": state.get("status") or "not_connected",
                "has_credentials": bool(state.get("has_credentials")),
                "credentials_label_en": "Configured" if state.get("has_credentials") else "Not configured",
                "credentials_label_ar": "مضبوط" if state.get("has_credentials") else "غير مضبوط",
                "detail_en": state.get("detail_en"),
                "detail_ar": state.get("detail_ar"),
                "configure_href": spec["configure_href"],
                "activity_href": spec.get("activity_href"),
                "family": spec["family"],
                # Never include secrets / ciphertext / tokens
            }
        )
    return {
        "ok": True,
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "company_code": company,
        "cards": cards,
        "ownership": {
            "catalog": "setup_console",
            "connected_systems_ops": "migration_sync",
            "calendar_oauth": "settings_integrations",
            "mailbox_connect": "settings_communications",
            "company_channels": "setup_console",
            "personal_hr_whatsapp": "settings_account",
            "secrets": "canonical_sealed_stores",
        },
        "honesty": {
            "secrets_never_returned": True,
            "no_duplicate_connector_admin": True,
            "api_stub_not_advertised": True,
            "attendance_devices_not_from_setup": True,
        },
    }
