"""R6 — customer notification / channel delivery policy via Setup.

Provider credentials stay in secure integration configuration.
WATHEFNI_PUSH_NOTIFICATIONS remains a deployment gate.
"""
from __future__ import annotations

import os
from typing import Any

import setup_console_effective_state as eff

PHASE = "setup_console_r6_delivery"
CONTRACT_VERSION = "delivery_policies_v1"
PRESETS = ("frontline", "office", "conservative")


def _env_on(name: str, default: str = "off") -> bool:
    return (os.environ.get(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def push_deployment_available() -> bool:
    if not _env_on("WATHEFNI_PUSH_NOTIFICATIONS", "off"):
        return False
    return bool(os.environ.get("EXPO_ACCESS_TOKEN") or os.environ.get("WATHEFNI_PUSH_PROVIDER"))


def get_delivery_policy(cur: Any, company_code: str) -> dict[str, Any]:
    company = str(company_code or "").strip().upper()
    preset = "office"
    explicit = False
    try:
        import setup_console_wave1_policies as w1

        raw = w1._get_company_setting(cur, company, "notification_preset", "")
        val = str(raw or "").strip().lower()
        if val in PRESETS:
            preset = val
            explicit = True
    except Exception:
        pass
    push_ok = push_deployment_available()
    payload = {
        "ok": True,
        "module_key": "notifications",
        "label_en": "Notifications & delivery",
        "label_ar": "الإشعارات والتسليم",
        "policy": {
            "enabled": True,
            "notification_preset": preset,
            "notification_preset_explicit": explicit,
            "notification_preset_options": list(PRESETS),
            "push_deployment_available": push_ok,
        },
        # Customer preset is Setup-owned even when push is a deployment kill switch.
        "runtime_gate": {"ok": True, "enabled": True, "error": None, "gate": "available"},
        "push_deployment": {
            "available": push_ok,
            "reason_code": "available" if push_ok else "unavailable_deployment",
            "message_en": (
                "Push is available in this deployment."
                if push_ok
                else "Push is unavailable in this deployment."
            ),
            "message_ar": "الدفع متاح في هذا النشر." if push_ok else "الدفع غير متاح في هذا النشر.",
        },
        "provider_secrets_exposed": False,
        "honesty": {
            "setup_owns_customer_preset": True,
            "provider_credentials_stay_integrations": True,
            "push_flag_is_deployment_only": True,
        },
    }
    return eff.annotate_with_effective_state("notifications", payload)


def patch_delivery_policy(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = str(company_code or "").strip().upper()
    body = dict(payload or {})
    if "required" in body and isinstance(body["required"], dict):
        body = {**body["required"], **{k: v for k, v in body.items() if k != "required"}}
    preset = str(body.get("notification_preset") or "").strip().lower()
    if preset and preset not in PRESETS:
        return {"ok": False, "error": "invalid_notification_preset", "allowed": list(PRESETS)}
    previous = None
    try:
        import setup_console_wave1_policies as w1

        previous = w1._get_company_setting(cur, company, "notification_preset", None)
        if preset:
            w1._set_company_setting(cur, company, "notification_preset", preset)
    except Exception as exc:
        return {"ok": False, "error": "notification_preset_write_failed", "message": str(exc)[:200]}
    return {
        "ok": True,
        "actions": [
            {
                "action": "set_notification_preset",
                "from": previous,
                "to": preset or previous,
                "actor": actor_phone,
                "reason": str(reason).strip()[:200],
            }
        ],
        **get_delivery_policy(cur, company),
    }
