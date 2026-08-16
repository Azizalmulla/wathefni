"""R6 — environment vs Setup ownership classification.

A — legitimate infrastructure / deployment gate → env stays
B — customer policy → Setup
C — obsolete / dead → do not treat as customer authority
"""
from __future__ import annotations

from typing import Any

PHASE = "setup_console_r6_env_classification"
CONTRACT_VERSION = "env_classification_v1"

CLASS_A = "A_infrastructure_deployment"
CLASS_B = "B_customer_policy_setup"
CLASS_C = "C_obsolete_or_non_authoritative"

ENTRIES: tuple[dict[str, Any], ...] = (
    {
        "key": "WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1",
        "class": CLASS_A,
        "owns": "Wave 5 Intelligence kill switch",
        "setup": "Effective state shows unavailable_deployment when off",
    },
    {
        "key": "WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES",
        "class": CLASS_A,
        "owns": "Staged Intelligence rollout allowlist; empty admits after R6",
        "setup": "Explicit allowlist exclusion is unavailable_deployment",
    },
    {
        "key": "WATHEFNI_ANALYTICS_KILL",
        "class": CLASS_A,
        "owns": "Immediate Intelligence kill switch",
        "setup": "Unavailable in this deployment",
    },
    {
        "key": "WATHEFNI_*_C# / WATHEFNI_*_COMPANIES",
        "class": CLASS_A,
        "owns": "Wave 4/6 domain kill switches and staged allowlists",
        "setup": "Empty allowlist admits when customer_enableable; Setup never lies Enabled",
    },
    {
        "key": "WATHEFNI_EMPLOYEE_APP",
        "class": CLASS_A,
        "owns": "Employee App master kill switch",
        "setup": "Company employee_app module remains customer entitlement",
    },
    {
        "key": "WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST",
        "class": CLASS_A,
        "owns": "Staged employee-key rollout, not company policy",
        "setup": "Employee App Access card owns company entitlement",
    },
    {
        "key": "WATHEFNI_EMPLOYEE_APP_REQUIRE_ALLOWLIST",
        "class": CLASS_A,
        "owns": "Staged rollout fail-closed",
        "setup": "Not customer policy",
    },
    {
        "key": "WATHEFNI_PUSH_NOTIFICATIONS",
        "class": CLASS_A,
        "owns": "Push provider deployment gate",
        "setup": "Delivery card shows deployment availability; credentials stay integration-owned",
    },
    {
        "key": "EXPO_ACCESS_TOKEN / WATHEFNI_PUSH_PROVIDER",
        "class": CLASS_A,
        "owns": "Provider secrets",
        "setup": "Never exposed in Setup",
    },
    {
        "key": "WATHEFNI_ONBOARDING_SEED",
        "class": CLASS_A,
        "owns": "Synthetic / backfill checklist seed infrastructure",
        "setup": "Customer auto-start is Setup-owned; seed env is not customer policy",
    },
    {
        "key": "WATHEFNI_ONBOARDING_HR_MUTATE",
        "class": CLASS_A,
        "owns": "Dashboard onboarding mutation kill switch",
        "setup": "Empty company allowlist already admits when flag is on",
    },
    {
        "key": "onboarding.auto_start_on_hire",
        "class": CLASS_B,
        "owns": "Customer hire→onboarding auto-start",
        "setup": "Canonical company_settings + onboarding overlay write-through",
    },
    {
        "key": "notification_preset",
        "class": CLASS_B,
        "owns": "Customer notification preset",
        "setup": "Company settings via Setup delivery card (not legacy HTML only)",
    },
    {
        "key": "channel_policy / channel accounts",
        "class": CLASS_B,
        "owns": "Customer delivery channels",
        "setup": "Existing Setup channel cards; provider secrets stay integrations",
    },
    {
        "key": "leave_policies + leave_setup overlay",
        "class": CLASS_B,
        "owns": "Customer leave policy",
        "setup": "leave_policies is canonical; Wave 2 enforced writes through",
    },
    {
        "key": "attendance_setup + wave2 attendance ingest",
        "class": CLASS_B,
        "owns": "Customer attendance ops vs Wave 2 ingest flags",
        "setup": "One write path per concern; payroll mode stays Payroll Setup",
    },
    {
        "key": "legacy HTML notification_preset (~app.py:42600)",
        "class": CLASS_C,
        "owns": "Display-only leftover",
        "setup": "No longer authoritative; Setup delivery card is the customer UI",
    },
)


def classification_matrix() -> dict[str, Any]:
    return {
        "ok": True,
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "entries": list(ENTRIES),
        "counts": {
            "A": sum(1 for item in ENTRIES if item["class"] == CLASS_A),
            "B": sum(1 for item in ENTRIES if item["class"] == CLASS_B),
            "C": sum(1 for item in ENTRIES if item["class"] == CLASS_C),
        },
        "secrets_never_moved_to_setup": True,
    }
