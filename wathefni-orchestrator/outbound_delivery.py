"""Shared employee outbound delivery layer (Phase A — dark behind a flag).

Goal (product rule): *No critical HR workflow should silently fail because the
WhatsApp conversation is closed.* Every employee-facing message goes through one
entry point — ``deliver_to_employee`` — which records the message in
``employee_messages`` (the source of truth) and walks a resilient channel ladder:

    1. WhatsApp session (free-form, requires an open 24h conversation)
    2. WhatsApp approved template (HSM) via the provider abstraction
    3. Employee email fallback (Postmark/Gmail)
    4. Dashboard HR task / "needs action" (for critical flows)

The channel primitives live in ``app`` (Octopus + email). This module never
talks to Meta/360dialog directly: the path is
``Wathefni -> Outbound Delivery Layer -> Octopus -> 360dialog``.

Phase A is *dark*: nothing in production calls this yet. It is exercised only by
the smoke harness and is gated by ``WATHEFNI_OUTBOUND_LAYER`` at the call sites
we add later (Phases C+). To avoid an import cycle, ``app`` is imported lazily
inside functions (``app`` finishes importing this module first, then this module
resolves ``app`` at call time, when it is fully initialised).
"""

from __future__ import annotations

import datetime as _dt
from typing import Any


# --- Criticality + sensitivity vocabularies ---------------------------------
# criticality drives the terminal behaviour when no channel succeeds:
#   critical      -> raise a visible HR task (needs_hr_action)
#   standard      -> mark failed; surfaced in the dashboard "needs follow-up" view
#   informational -> mark failed; log only (no HR task, low priority)
#
# NOTE (semantics cleanup, Phase 1): `criticality` historically conflated three
# unrelated ideas. It is being split into the three orthogonal fields below.
# `criticality` REMAINS the runtime source of truth for failure escalation +
# needs-follow-up sort; the new fields are additive metadata with NO consumer yet
# (channel presets will read them later). `failure_escalation` is a strict 1:1
# alias of `criticality` so Phase 1 is byte-for-byte behavior-frozen.
CRITICALITY_CRITICAL = "critical"
CRITICALITY_STANDARD = "standard"
CRITICALITY_INFORMATIONAL = "informational"

# delivery_urgency — how fast the employee needs it (channel-preset weighting).
URGENCY_ACTION_NOW = "action_now"
URGENCY_REMINDER = "reminder"
URGENCY_INFORMATIONAL = "informational"
DELIVERY_URGENCIES = {URGENCY_ACTION_NOW, URGENCY_REMINDER, URGENCY_INFORMATIONAL}

# failure_escalation — what happens when NO channel succeeds. 1:1 with criticality.
ESCALATION_HR_TASK = "hr_task"
ESCALATION_DELIVERY_ISSUE = "delivery_issue_only"
ESCALATION_AUDIT_ONLY = "audit_only"
FAILURE_ESCALATIONS = {ESCALATION_HR_TASK, ESCALATION_DELIVERY_ISSUE, ESCALATION_AUDIT_ONLY}

# employee_channel_intent — the LOUDEST channel a preset may use for this template.
# A company preset may only go calmer than this, never louder.
CHANNEL_WHATSAPP_OK = "whatsapp_ok"
CHANNEL_EMAIL_FIRST = "email_first"
CHANNEL_EMAIL_ONLY = "email_only"
CHANNEL_DASHBOARD_ONLY = "dashboard_only"
CHANNEL_INTENTS = {CHANNEL_WHATSAPP_OK, CHANNEL_EMAIL_FIRST, CHANNEL_EMAIL_ONLY, CHANNEL_DASHBOARD_ONLY}

# Strict 1:1 alias so derived_criticality(failure_escalation) == legacy criticality.
FAILURE_ESCALATION_TO_CRITICALITY = {
    ESCALATION_HR_TASK: CRITICALITY_CRITICAL,
    ESCALATION_DELIVERY_ISSUE: CRITICALITY_STANDARD,
    ESCALATION_AUDIT_ONLY: CRITICALITY_INFORMATIONAL,
}


def derived_criticality(failure_escalation: str) -> str:
    """Map the (new) failure_escalation back to the (legacy) criticality. Used by
    the Phase-1 contract test to prove no behavior change."""
    return FAILURE_ESCALATION_TO_CRITICALITY.get(str(failure_escalation), CRITICALITY_STANDARD)


# --- Company notification presets (operator-selected; downgrade-only) -------
# A preset is a per-company channel policy that can only make routing CALMER than
# the template's employee_channel_intent ceiling, never louder. It composes
# delivery_urgency + employee_channel_intent; it NEVER reads failure_escalation.
PRESET_FRONTLINE = "frontline"
PRESET_OFFICE = "office"
PRESET_CONSERVATIVE = "conservative"
NOTIFICATION_PRESETS = {PRESET_FRONTLINE, PRESET_OFFICE, PRESET_CONSERVATIVE}
DEFAULT_NOTIFICATION_PRESET = PRESET_FRONTLINE


def channel_plan_for(preset: str, intent: str, urgency: str) -> dict[str, Any]:
    """Pure policy decision (no I/O): given a company preset + a template's channel
    intent (ceiling) + delivery urgency, decide which channels may be used.

    Invariants:
      - WhatsApp is only ever possible when intent == whatsapp_ok.
      - A preset can only REMOVE channels, never add one above the ceiling.
      - dashboard_only intent -> no proactive send on any preset.
      - conservative never uses WhatsApp; office uses it only for action_now.
    """
    preset = preset if preset in NOTIFICATION_PRESETS else DEFAULT_NOTIFICATION_PRESET

    if intent == CHANNEL_DASHBOARD_ONLY:
        return {"whatsapp": False, "email": False, "dashboard_only": True, "reason": "intent_dashboard_only"}

    # Email is the always-available fallback for every non-dashboard intent.
    email_ok = intent in (CHANNEL_WHATSAPP_OK, CHANNEL_EMAIL_FIRST, CHANNEL_EMAIL_ONLY)

    if intent != CHANNEL_WHATSAPP_OK:
        # email_first / email_only — WhatsApp is above the ceiling, never allowed.
        return {"whatsapp": False, "email": email_ok, "dashboard_only": False, "reason": f"intent_{intent}_no_whatsapp"}

    # intent == whatsapp_ok: the preset decides whether WhatsApp is actually used.
    if preset == PRESET_FRONTLINE:
        return {"whatsapp": True, "email": email_ok, "dashboard_only": False, "reason": "frontline_whatsapp_first"}
    if preset == PRESET_OFFICE:
        if urgency == URGENCY_ACTION_NOW:
            return {"whatsapp": True, "email": email_ok, "dashboard_only": False, "reason": "office_action_now_whatsapp"}
        return {"whatsapp": False, "email": email_ok, "dashboard_only": False, "reason": "office_non_urgent_email_first"}
    # conservative
    return {"whatsapp": False, "email": email_ok, "dashboard_only": False, "reason": "conservative_no_whatsapp"}


def resolve_channel_plan(legacy: Any, company_code: str, template_key: str) -> dict[str, Any]:
    """Bind the pure channel policy to a company's saved preset + the template's
    catalog semantics. Reads the preset (one settings lookup); no sends."""
    entry = catalog_entry(template_key)
    intent = entry.get("employee_channel_intent") or CHANNEL_WHATSAPP_OK
    urgency = entry.get("delivery_urgency") or URGENCY_REMINDER
    preset = legacy.company_notification_preset(company_code)
    plan = channel_plan_for(preset, intent, urgency)
    plan.update({"preset": preset, "intent": intent, "urgency": urgency, "template_key": template_key})
    return plan

# sensitivity drives how the message body is stored:
#   plain         -> store full text (low sensitivity, fine for HR to read)
#   preview       -> store a short safe preview only
#   encrypted     -> store Fernet-encrypted body + a generic preview label
#   metadata_only -> store no body, only a generic label (payroll/legal/compliance)
SENS_PLAIN = "plain"
SENS_PREVIEW = "preview"
SENS_ENCRYPTED = "encrypted"
SENS_METADATA = "metadata_only"

# HR-readable terminal statuses (see app flag docs / dashboard copy).
STATUS_PENDING = "pending"
STATUS_DELIVERED_PUSH = "delivered_push"
STATUS_DELIVERED_WHATSAPP = "delivered_whatsapp"
STATUS_DELIVERED_TEMPLATE = "delivered_template"
STATUS_SENT_EMAIL = "sent_email_fallback"
STATUS_NEEDS_HR = "needs_hr_action"
STATUS_FAILED = "failed"
STATUS_SUPPRESSED = "suppressed"
# Reminder was intentionally not (re)sent because one already went out within the
# flow's cooldown window. Terminal, non-retryable, and NOT a failure — surfaced
# calmly so HR sees "we stayed quiet on purpose," never a scary delivery error.
STATUS_THROTTLED = "throttled"
# Message was intentionally NOT pushed to any employee channel because the company
# notification preset + template channel-intent route it to the dashboard only
# (e.g. attendance nudges). Terminal, non-retryable, info-tone, never an HR task.
STATUS_DASHBOARD_ONLY = "dashboard_only"

_TERMINAL_STATUSES = {
    STATUS_DELIVERED_PUSH,
    STATUS_DELIVERED_WHATSAPP,
    STATUS_DELIVERED_TEMPLATE,
    STATUS_SENT_EMAIL,
    STATUS_NEEDS_HR,
    STATUS_FAILED,
    STATUS_SUPPRESSED,
    STATUS_THROTTLED,
    STATUS_DASHBOARD_ONLY,
}
_DELIVERED_STATUSES = {STATUS_DELIVERED_PUSH, STATUS_DELIVERED_WHATSAPP, STATUS_DELIVERED_TEMPLATE, STATUS_SENT_EMAIL}

# WhatsApp session errors that will NOT fix themselves on retry (the conversation
# is closed / there is no usable conversation). For these we go straight down the
# ladder instead of scheduling a session retry.
_NON_RETRYABLE_SESSION_ERRORS = {
    "conversation_closed",
    "missing_candidate_conversation_id",
    "no_usable_conversation_id",
    "missing_ai_octopus_bearer_token",
}

_DEFAULT_MAX_ATTEMPTS = 6
# Backoff in minutes, indexed by attempt number (capped at the last entry).
_BACKOFF_MINUTES = [1, 5, 15, 30, 60, 120]


# --- Template catalog -------------------------------------------------------
# Wathefni template *keys* + their default criticality/sensitivity and a
# free-form fallback body (used for the WhatsApp session step and email, and as
# a safe preview). Approved provider template names are resolved separately via
# message_template_map (Phase F); keys here are stable and provider-agnostic.
TEMPLATE_CATALOG: dict[str, dict[str, Any]] = {
    "employee_onboarding_welcome": {
        "criticality": CRITICALITY_CRITICAL,
        "delivery_urgency": URGENCY_ACTION_NOW,
        "failure_escalation": ESCALATION_HR_TASK,
        "employee_channel_intent": CHANNEL_WHATSAPP_OK,
        "sensitivity": SENS_PREVIEW,
        "label": "Onboarding welcome",
        "label_ar": "ترحيب بالانضمام",
        "text": {
            "en": "Hi {employee_name}, welcome to {company_name}! We've started your onboarding. Please reply here to continue your first steps.",
            "ar": "مرحباً {employee_name}، أهلاً بك في {company_name}! بدأنا إجراءات انضمامك. يرجى الرد هنا لإكمال خطواتك الأولى.",
        },
    },
    "onboarding_reminder": {
        "criticality": CRITICALITY_STANDARD,
        "delivery_urgency": URGENCY_REMINDER,
        "failure_escalation": ESCALATION_DELIVERY_ISSUE,
        "employee_channel_intent": CHANNEL_WHATSAPP_OK,
        "sensitivity": SENS_PREVIEW,
        "label": "Onboarding reminder",
        "label_ar": "تذكير بالانضمام",
        "text": {
            "en": "Hi {employee_name}, a quick reminder to finish your onboarding steps for {company_name}.",
            "ar": "مرحباً {employee_name}، تذكير بسيط لإكمال خطوات الانضمام في {company_name}.",
        },
    },
    "compliance_document_required": {
        "criticality": CRITICALITY_CRITICAL,
        "delivery_urgency": URGENCY_REMINDER,
        "failure_escalation": ESCALATION_HR_TASK,
        "employee_channel_intent": CHANNEL_EMAIL_FIRST,
        "sensitivity": SENS_METADATA,
        "label": "Document required",
        "label_ar": "مستند مطلوب",
        "text": {
            "en": "Hi {employee_name}, HR needs your {document_type} to keep your file complete. Please send it when you can.",
            "ar": "مرحباً {employee_name}، يحتاج قسم الموارد البشرية إلى {document_type} لإكمال ملفك. يرجى إرساله عند الإمكان.",
        },
    },
    "compliance_document_expiring": {
        "criticality": CRITICALITY_CRITICAL,
        "delivery_urgency": URGENCY_REMINDER,
        "failure_escalation": ESCALATION_HR_TASK,
        "employee_channel_intent": CHANNEL_EMAIL_FIRST,
        "sensitivity": SENS_METADATA,
        "label": "Document expiring",
        "label_ar": "مستند ينتهي قريباً",
        "text": {
            "en": "Hi {employee_name}, your {document_type} is expiring on {expiry_date}. Please renew it and send the updated copy.",
            "ar": "مرحباً {employee_name}، {document_type} الخاص بك ينتهي في {expiry_date}. يرجى تجديده وإرسال النسخة المحدثة.",
        },
    },
    "shift_assigned": {
        "criticality": CRITICALITY_STANDARD,
        "delivery_urgency": URGENCY_ACTION_NOW,
        "failure_escalation": ESCALATION_DELIVERY_ISSUE,
        "employee_channel_intent": CHANNEL_WHATSAPP_OK,
        "sensitivity": SENS_PREVIEW,
        "label": "Shift assigned",
        "label_ar": "تم تعيين مناوبة",
        "text": {
            "en": "Hi {employee_name}, you have a shift on {shift_date} from {shift_time}. Location: {location}.",
            "ar": "مرحباً {employee_name}، لديك مناوبة يوم {shift_date} من {shift_time}. الموقع: {location}.",
        },
    },
    "shift_rescheduled": {
        "criticality": CRITICALITY_STANDARD,
        "delivery_urgency": URGENCY_ACTION_NOW,
        "failure_escalation": ESCALATION_DELIVERY_ISSUE,
        "employee_channel_intent": CHANNEL_WHATSAPP_OK,
        "sensitivity": SENS_PREVIEW,
        "label": "Shift updated",
        "label_ar": "تم تحديث المناوبة",
        "text": {
            "en": "Hi {employee_name}, your shift has been moved to {shift_date} from {shift_time}. Location: {location}. Please check the new time.",
            "ar": "مرحباً {employee_name}، تم تغيير موعد مناوبتك إلى {shift_date} من {shift_time}. الموقع: {location}. يرجى مراجعة الموعد الجديد.",
        },
    },
    "shift_reminder": {
        "criticality": CRITICALITY_INFORMATIONAL,
        "delivery_urgency": URGENCY_REMINDER,
        "failure_escalation": ESCALATION_AUDIT_ONLY,
        "employee_channel_intent": CHANNEL_WHATSAPP_OK,
        "sensitivity": SENS_PREVIEW,
        "label": "Shift reminder",
        "label_ar": "تذكير بالمناوبة",
        "text": {
            "en": "Reminder: your shift starts on {shift_date} at {shift_time}.",
            "ar": "تذكير: تبدأ مناوبتك يوم {shift_date} الساعة {shift_time}.",
        },
    },
    "shift_cancelled": {
        "criticality": CRITICALITY_STANDARD,
        "delivery_urgency": URGENCY_ACTION_NOW,
        "failure_escalation": ESCALATION_DELIVERY_ISSUE,
        "employee_channel_intent": CHANNEL_WHATSAPP_OK,
        "sensitivity": SENS_PREVIEW,
        "label": "Shift cancelled",
        "label_ar": "تم إلغاء المناوبة",
        "text": {
            "en": "Hi {employee_name}, your shift on {shift_date} has been cancelled. You don't need to come in for it.",
            "ar": "مرحباً {employee_name}، تم إلغاء مناوبتك يوم {shift_date}. لا حاجة للحضور لها.",
        },
    },
    "attendance_missed_checkin": {
        "criticality": CRITICALITY_STANDARD,
        "delivery_urgency": URGENCY_INFORMATIONAL,
        "failure_escalation": ESCALATION_DELIVERY_ISSUE,
        "employee_channel_intent": CHANNEL_DASHBOARD_ONLY,
        "sensitivity": SENS_PREVIEW,
        "label": "Missed check-in",
        "label_ar": "لم يتم تسجيل الحضور",
        "text": {
            "en": "Hi {employee_name}, we didn't see a check-in for your shift on {shift_date}. Please check in or reply if there's an issue.",
            "ar": "مرحباً {employee_name}، لم نسجّل حضورك لمناوبة {shift_date}. يرجى تسجيل الحضور أو الرد إذا كان هناك أمر ما.",
        },
    },
    "leave_request_approved": {
        "criticality": CRITICALITY_CRITICAL,
        "delivery_urgency": URGENCY_ACTION_NOW,
        "failure_escalation": ESCALATION_HR_TASK,
        "employee_channel_intent": CHANNEL_WHATSAPP_OK,
        "sensitivity": SENS_PREVIEW,
        "label": "Leave approved",
        "label_ar": "تمت الموافقة على الإجازة",
        "text": {
            "en": "Hi {employee_name}, your leave from {start_date} to {end_date} has been approved.",
            "ar": "مرحباً {employee_name}، تمت الموافقة على إجازتك من {start_date} إلى {end_date}.",
        },
    },
    "leave_request_rejected": {
        "criticality": CRITICALITY_CRITICAL,
        "delivery_urgency": URGENCY_ACTION_NOW,
        "failure_escalation": ESCALATION_HR_TASK,
        "employee_channel_intent": CHANNEL_WHATSAPP_OK,
        "sensitivity": SENS_PREVIEW,
        "label": "Leave decision",
        "label_ar": "قرار الإجازة",
        "text": {
            "en": "Hi {employee_name}, your leave request from {start_date} to {end_date} was not approved. Please speak with HR for details.",
            "ar": "مرحباً {employee_name}، لم تتم الموافقة على طلب إجازتك من {start_date} إلى {end_date}. يرجى التواصل مع الموارد البشرية للتفاصيل.",
        },
    },
    "payroll_timesheet_ready": {
        "criticality": CRITICALITY_STANDARD,
        "delivery_urgency": URGENCY_INFORMATIONAL,
        "failure_escalation": ESCALATION_DELIVERY_ISSUE,
        "employee_channel_intent": CHANNEL_EMAIL_ONLY,
        "sensitivity": SENS_METADATA,
        "label": "Payroll update",
        "label_ar": "تحديث الرواتب",
        "text": {
            "en": "Hi {employee_name}, there's a payroll update for the {period} period. Please check with HR.",
            "ar": "مرحباً {employee_name}، يوجد تحديث في الرواتب لفترة {period}. يرجى المراجعة مع الموارد البشرية.",
        },
    },
    "payslip_ready": {
        "criticality": CRITICALITY_STANDARD,
        "delivery_urgency": URGENCY_INFORMATIONAL,
        "failure_escalation": ESCALATION_AUDIT_ONLY,
        "employee_channel_intent": CHANNEL_DASHBOARD_ONLY,
        "sensitivity": SENS_PREVIEW,
        "label": "Payslip ready",
        "label_ar": "كشف الراتب جاهز",
        "text": {
            "en": "Your payslip for {period} is ready to view in the app.",
            "ar": "كشف راتبك لفترة {period} جاهز للعرض في التطبيق.",
        },
    },
    "bank_correction_required": {
        "criticality": CRITICALITY_STANDARD,
        "delivery_urgency": URGENCY_ACTION_NOW,
        "failure_escalation": ESCALATION_DELIVERY_ISSUE,
        "employee_channel_intent": CHANNEL_WHATSAPP_OK,
        "sensitivity": SENS_PREVIEW,
        "label": "Bank details need attention",
        "label_ar": "تفاصيل البنك تحتاج تصحيحاً",
        "text": {
            "en": "Hi {employee_name}, your bank details need a correction. Please open Bank in the OctoHR app.",
            "ar": "مرحباً {employee_name}، تفاصيل حسابك البنكي تحتاج تصحيحاً. يرجى فتح البنك في تطبيق OctoHR.",
        },
    },
    # Employee App activation code. Critical so a code that reaches nobody raises a
    # visible HR task (HR can then hand the code over). metadata_only so the code
    # itself is NEVER persisted in the message body_preview/audit row.
    "app_activation": {
        "criticality": CRITICALITY_CRITICAL,
        "delivery_urgency": URGENCY_ACTION_NOW,
        "failure_escalation": ESCALATION_HR_TASK,
        "employee_channel_intent": CHANNEL_WHATSAPP_OK,
        "sensitivity": SENS_METADATA,
        "label": "App activation code",
        "label_ar": "رمز تفعيل التطبيق",
        "text": {
            "en": "Hi {employee_name}, your {company_name} app activation code is {code}. It expires in {expiry_hours} hours.",
            "ar": "مرحباً {employee_name}، رمز تفعيل تطبيق {company_name} هو {code}. ينتهي خلال {expiry_hours} ساعة.",
        },
    },
}


class _SafeDict(dict):
    """str.format_map helper that renders unknown placeholders as empty."""

    def __missing__(self, key: str) -> str:  # noqa: D401
        return ""


def _now(legacy: Any) -> _dt.datetime:
    return legacy.now_utc()


def catalog_entry(template_key: str) -> dict[str, Any]:
    return TEMPLATE_CATALOG.get(template_key, {})


def catalog_label(template_key: str, locale: str = "en") -> str:
    """Employee-facing inbox title; prefers label_ar when locale is Arabic."""
    entry = catalog_entry(template_key)
    loc = str(locale or "en").lower()
    if loc.startswith("ar"):
        label = entry.get("label_ar") or entry.get("label")
    else:
        label = entry.get("label")
    if label:
        return str(label)
    return str(template_key or "").replace("_", " ").strip().title() or "Message"



def render_body(template_key: str, variables: dict[str, Any] | None, locale: str = "en") -> str:
    """Render the free-form fallback body for a template key. Falls back to the
    English copy, then to a generic label, so we never produce an empty body."""
    entry = catalog_entry(template_key)
    texts = entry.get("text") or {}
    template = texts.get(locale) or texts.get("en")
    safe_vars = _SafeDict(variables or {})
    if template:
        try:
            rendered = template.format_map(safe_vars).strip()
        except Exception:
            rendered = template
        if rendered:
            return rendered
    return entry.get("label") or template_key.replace("_", " ").strip().capitalize()


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"


def _generic_label(template_key: str, flow: str) -> str:
    entry = catalog_entry(template_key)
    return entry.get("label") or f"{flow.replace('_', ' ').strip().capitalize()} message"


def _body_storage(
    legacy: Any,
    *,
    template_key: str,
    flow: str,
    sensitivity: str,
    full_text: str,
) -> dict[str, Any]:
    """Decide what (if anything) of the body is persisted, per sensitivity policy.

    Returns body_preview / body_encrypted / body_key_version / event_text, where
    event_text is the HR-safe string used for delivery-event logging."""
    label = _generic_label(template_key, flow)
    if sensitivity == SENS_PLAIN:
        preview = _truncate(full_text, 600)
        return {"body_preview": preview, "body_encrypted": None, "body_key_version": None, "event_text": preview}
    if sensitivity == SENS_PREVIEW:
        preview = _truncate(full_text, 280)
        return {"body_preview": preview, "body_encrypted": None, "body_key_version": None, "event_text": preview}
    if sensitivity == SENS_ENCRYPTED:
        if legacy.sensitive_encryption_available():
            enc = legacy.encrypt_sensitive_text(full_text)
            return {
                "body_preview": label,
                "body_encrypted": enc.get("ciphertext"),
                "body_key_version": enc.get("key_version"),
                "event_text": label,
            }
        # No keyring configured -> degrade to metadata-only (never log the body).
        return {"body_preview": label, "body_encrypted": None, "body_key_version": None, "event_text": label}
    # metadata_only (default-safe for anything unexpected)
    return {"body_preview": label, "body_encrypted": None, "body_key_version": None, "event_text": label}


# --- Provider abstraction ---------------------------------------------------
# Business flows never call Octopus/email directly. They call deliver_to_employee,
# which uses these thin providers. Swapping providers (or adding SMS later) means
# adding a provider here, not touching every flow.
class OctopusProvider:
    @staticmethod
    def send_session(legacy: Any, *, account_id, phone, text, subject_type, subject_key, message_kind, company_code=None) -> dict[str, Any]:
        return legacy.send_octopus_whatsapp(
            account_id=account_id,
            phone=phone,
            text=text,
            subject_type=subject_type,
            subject_key=subject_key,
            message_kind=message_kind,
            company_code=company_code,
        )

    @staticmethod
    def send_template(legacy: Any, *, account_id, phone, template_key, locale, variables, fallback_text, subject_type, subject_key, company_code, message_kind) -> dict[str, Any]:
        return legacy.octopus_send_template(
            account_id=account_id,
            phone=phone,
            template_key=template_key,
            locale=locale,
            variables=variables,
            fallback_text=fallback_text,
            subject_type=subject_type,
            subject_key=subject_key,
            company_code=company_code,
            message_kind=message_kind,
        )


class PushProvider:
    @staticmethod
    def send(
        legacy: Any,
        *,
        company_code,
        employee_key,
        title,
        body,
        flow,
        subject_type,
        subject_key,
        account_id,
        variables=None,
        deep_link=None,
        template_key=None,
        locale=None,
        dedupe_key=None,
        time_sensitive=None,
    ) -> dict[str, Any]:
        return legacy.send_outbound_push(
            company_code=company_code,
            employee_key=employee_key,
            title=title,
            body=body,
            flow=flow,
            subject_type=subject_type,
            subject_key=subject_key,
            account_id=account_id,
            message_kind=flow,
            deep_link=deep_link,
            variables=variables,
            template_key=template_key,
            locale=locale,
            dedupe_key=dedupe_key,
            time_sensitive=time_sensitive,
        )


class EmailProvider:
    @staticmethod
    def send(legacy: Any, *, to, subject, body, company_code, subject_type, subject_key, account_id, message_kind) -> dict[str, Any]:
        return legacy.send_outbound_email(
            to=to,
            subject=subject,
            body=body,
            company_code=company_code,
            subject_type=subject_type,
            subject_key=subject_key,
            account_id=account_id,
            message_kind=message_kind,
        )


def _resolve_recipient(employee: dict[str, Any] | None) -> dict[str, Any]:
    employee = employee or {}
    phone = (
        employee.get("phone")
        or employee.get("whatsapp")
        or employee.get("whatsapp_phone")
        or employee.get("employee_phone")
        or employee.get("contact_phone")
    )
    email = employee.get("email") or employee.get("employee_email") or employee.get("contact_email")
    return {
        "employee_key": employee.get("employee_key") or employee.get("key") or employee.get("id"),
        "phone": phone,
        "email": email,
        "name": employee.get("name") or employee.get("full_name") or employee.get("employee_name") or "",
        "locale": employee.get("locale") or employee.get("language"),
    }


def _backoff_minutes(attempts: int) -> int:
    idx = max(0, min(attempts, len(_BACKOFF_MINUTES) - 1))
    return _BACKOFF_MINUTES[idx]


def _attempt_ladder(
    legacy: Any,
    *,
    account_id,
    phone,
    email,
    template_key,
    flow,
    locale,
    variables,
    full_text,
    email_subject,
    subject_type,
    subject_key,
    company_code,
    dedupe_key=None,
) -> dict[str, Any]:
    """Walk the channel ladder once. Returns the outcome of this attempt without
    deciding terminal vs retry (the caller owns that, using criticality)."""
    reasons: list[str] = []

    # 0. Opt-out / suppression gate (GLOBAL BY PHONE). A clear opt-out blocks every
    #    proactive WhatsApp + template send BEFORE any provider call. scope='whatsapp'
    #    still allows the email fallback; scope='all' blocks email too. This runs in
    #    both deliver_to_employee and the retry sweep, so a mid-flight opt-out is
    #    honoured on the next attempt as well.
    sup = legacy.whatsapp_suppression_state(phone) if phone else {"suppressed": False, "scope": None}
    wa_suppressed = bool(sup.get("suppressed"))
    all_suppressed = wa_suppressed and str(sup.get("scope")) == "all"

    # 0b. Company notification preset (flag-gated, downgrade-only). Composes the
    #     template's channel-intent ceiling + delivery_urgency with the company's
    #     preset to decide which channels may be used. It can only make routing
    #     CALMER than suppression already does, never louder. When the flag is off,
    #     the ladder behaves exactly as before (all channels allowed).
    if legacy.channel_presets_enabled():
        plan = resolve_channel_plan(legacy, company_code, template_key)
    else:
        plan = {"whatsapp": True, "email": True, "dashboard_only": False, "preset": None, "reason": "presets_off"}
    wa_allowed = bool(plan.get("whatsapp")) and not wa_suppressed
    email_allowed = bool(plan.get("email")) and not all_suppressed

    # dashboard_only routing: no proactive employee send at all. Terminal, calm,
    # auditable — never a failure or an HR task.
    if plan.get("dashboard_only"):
        return {
            "status": None,
            "channel": None,
            "reasons": [f"channel:dashboard_only:{plan.get('reason') or 'preset'}"],
            "retryable": False,
            "dashboard_only": True,
        }

    # 0c. Push (Employee App, owned channel). Tried FIRST when enabled because it's
    #     the cheapest/fastest channel and the whole point of the app is to reduce
    #     WhatsApp-template dependency. It is NEVER load-bearing: no token / not
    #     configured / send failure all fall straight through to WhatsApp/email.
    #     A scope='all' opt-out blocks push too; a WhatsApp-only opt-out does not.
    #     Activation/session codes stay Inbox+WA/email — never Expo push.
    try:
        import employee_push_tray as _push_tray
    except Exception:
        _push_tray = None  # type: ignore
    push_ok = True
    if _push_tray is not None and not _push_tray.push_allowed(flow=flow, template_key=template_key):
        push_ok = False
        reasons.append("push:inbox_only_policy")
    if push_ok and not all_suppressed and legacy.push_notifications_enabled():
        tray_title, tray_body = (email_subject, full_text)
        if _push_tray is not None:
            tray_title, tray_body = _push_tray.tray_copy(
                str(template_key or ""),
                locale=locale,
                variables=variables if isinstance(variables, dict) else None,
                fallback_title=email_subject,
                fallback_body=full_text,
            )
        p = PushProvider.send(
            legacy,
            company_code=company_code,
            employee_key=subject_key,
            title=tray_title,
            body=tray_body,
            flow=flow,
            subject_type=subject_type,
            subject_key=subject_key,
            account_id=account_id,
            variables=variables,
            template_key=template_key,
            locale=locale,
            dedupe_key=dedupe_key,
        )
        if p.get("ok"):
            return {"status": STATUS_DELIVERED_PUSH, "channel": "push", "reasons": reasons, "retryable": False}
        reasons.append(f"push:{str(p.get('error') or 'push_failed')}")
    elif all_suppressed:
        reasons.append("push:suppressed_opt_out")

    # 1. WhatsApp session (free-form) — only if allowed by preset, has a phone, not suppressed.
    session_retryable = False
    if phone and wa_allowed:
        r = OctopusProvider.send_session(
            legacy,
            account_id=account_id,
            phone=phone,
            text=full_text,
            subject_type=subject_type,
            subject_key=subject_key,
            message_kind=flow,
            company_code=company_code,
        )
        if r.get("ok"):
            return {"status": STATUS_DELIVERED_WHATSAPP, "channel": "whatsapp_session", "reasons": reasons, "retryable": False}
        err = str(r.get("error") or "whatsapp_failed")
        reasons.append(f"session:{err}")
        session_retryable = err not in _NON_RETRYABLE_SESSION_ERRORS
    elif not phone:
        reasons.append("session:no_phone")
    elif wa_suppressed:
        reasons.append("session:suppressed_opt_out")
    else:
        reasons.append("session:preset_no_whatsapp")

    # 2. WhatsApp approved template (HSM) — only if allowed by preset, has a phone, not suppressed.
    if phone and wa_allowed:
        t = OctopusProvider.send_template(
            legacy,
            account_id=account_id,
            phone=phone,
            template_key=template_key,
            locale=locale,
            variables=variables,
            fallback_text=full_text,
            subject_type=subject_type,
            subject_key=subject_key,
            company_code=company_code,
            message_kind=flow,
        )
        if t.get("ok"):
            return {"status": STATUS_DELIVERED_TEMPLATE, "channel": "whatsapp_template", "reasons": reasons, "retryable": False}
        reasons.append(f"template:{str(t.get('error') or 'template_failed')}")
    elif phone and wa_suppressed:
        reasons.append("template:suppressed_opt_out")
    elif phone and not wa_allowed:
        reasons.append("template:preset_no_whatsapp")

    # 3. Email fallback — allowed unless the employee opted out of ALL channels or the
    #    preset routes this template away from email.
    if not email_allowed:
        reasons.append("email:suppressed_opt_out" if all_suppressed else "email:preset_blocked")
    elif legacy.outbound_email_fallback_enabled():
        if email:
            e = EmailProvider.send(
                legacy,
                to=email,
                subject=email_subject,
                body=full_text,
                company_code=company_code,
                subject_type=subject_type,
                subject_key=subject_key,
                account_id=account_id,
                message_kind=flow,
            )
            if e.get("ok"):
                return {"status": STATUS_SENT_EMAIL, "channel": "email", "reasons": reasons, "retryable": False}
            reasons.append(f"email:{str(e.get('error') or 'email_failed')}")
        else:
            reasons.append("email:no_employee_email")
    else:
        reasons.append("email:disabled")

    # Nothing landed. A suppressed message is terminal (not a transient failure);
    # otherwise a retry only helps if the session error was retryable.
    return {
        "status": None,
        "channel": None,
        "reasons": reasons,
        "retryable": session_retryable and not wa_suppressed,
        "suppressed": wa_suppressed,
    }


def create_hr_task(
    legacy: Any,
    *,
    company_code: str,
    employee_key: str | None,
    title: str,
    detail: str | None,
    source: str,
    related_message_id: str | None = None,
    priority: str = "high",
    task_type: str = "delivery_failed",
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """Create a visible HR follow-up task. Returns the new task_id."""
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO hr_tasks
                  (company_code, employee_key, task_type, source, title, detail, priority, related_message_id, metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING task_id
                """,
                (
                    str(company_code or "").strip().upper(),
                    employee_key,
                    task_type,
                    source,
                    title,
                    detail,
                    priority,
                    related_message_id,
                    legacy.Json(legacy.json_safe(metadata or {})),
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return str(row["task_id"]) if row else None


def _record_layer_event(
    legacy: Any,
    *,
    message_id: str,
    company_code: str,
    flow: str,
    template_key: str,
    status: str,
    channel_used: str | None,
    reasons: list[str],
    event_text: str,
    target_phone,
    target_email,
    subject_type,
    subject_key,
    account_id,
) -> None:
    """Write one consolidated, HR-safe audit row for the layer outcome (in
    addition to the per-attempt technical events the channel primitives log)."""
    legacy.record_outbound_delivery_event(
        account_id=account_id,
        target_phone=target_phone,
        target_conversation_id=None,
        status=(
            "sent" if status in _DELIVERED_STATUSES
            else "dry_run" if status == STATUS_PENDING
            else "skipped" if status == STATUS_DASHBOARD_ONLY
            else "failed"
        ),
        message_text=event_text,
        last_error=None if status in _DELIVERED_STATUSES else "; ".join(reasons)[:300] or None,
        payload={
            "outbound_layer": True,
            "employee_message_id": message_id,
            "flow": flow,
            "template_key": template_key,
            "delivery_status": status,
            "channel_used": channel_used,
            "attempt_reasons": reasons,
            "recipient_email": target_email,
        },
        subject_type=subject_type,
        subject_key=subject_key,
        channel="outbound_layer",
        message_kind=flow,
        company_code=company_code,
    )


def _finalize(
    legacy: Any,
    *,
    row: dict[str, Any],
    outcome: dict[str, Any],
    full_text: str,
) -> dict[str, Any]:
    """Apply an attempt outcome to a message row: persist status, schedule retry
    or raise an HR task, log the consolidated event, and return the result dict."""
    message_id = str(row["message_id"])
    company_code = row["company_code"]
    flow = row["flow"]
    template_key = row["template_key"]
    criticality = row["criticality"]
    attempts = int(row.get("attempts") or 0) + 1
    max_attempts = int(row.get("max_attempts") or _DEFAULT_MAX_ATTEMPTS)
    reasons = list(outcome.get("reasons") or [])
    subject_type = row.get("subject_type") or "employee"
    subject_key = row.get("subject_key") or row.get("employee_key")
    event_text = row.get("event_text") or _generic_label(template_key, flow)

    hr_task_id = row.get("hr_task_id")
    next_attempt_at = None

    if outcome.get("status") in _DELIVERED_STATUSES:
        status = outcome["status"]
        channel_used = outcome.get("channel")
    else:
        channel_used = None
        retryable = bool(outcome.get("retryable")) and attempts < max_attempts
        if retryable:
            status = STATUS_PENDING
            next_attempt_at = _now(legacy) + _dt.timedelta(minutes=_backoff_minutes(attempts))
        elif outcome.get("dashboard_only"):
            # Company preset routes this template to the dashboard only (e.g. attendance
            # nudges). Terminal + no HR task: this is a deliberate, calm routing choice,
            # not a failure. Surfaced as info-tone in Delivery Issues.
            status = STATUS_DASHBOARD_ONLY
        elif outcome.get("suppressed"):
            # Employee opted out of WhatsApp and email couldn't (or mustn't) carry it.
            # Terminal + no HR task: this is a deliberate opt-out, not a failure. It is
            # still surfaced calmly in Delivery Issues so HR can reach them another way.
            status = STATUS_SUPPRESSED
        elif criticality == CRITICALITY_CRITICAL:
            status = STATUS_NEEDS_HR
            if not hr_task_id:
                hr_task_id = create_hr_task(
                    legacy,
                    company_code=company_code,
                    employee_key=row.get("employee_key"),
                    title=f"Couldn't reach employee: {_generic_label(template_key, flow)}",
                    # HR-visible text stays channel-agnostic and calm; raw reason
                    # codes are kept in metadata (attempt_reasons) for diagnosis.
                    detail="OctoHR could not reach this employee through the currently enabled channels. Follow up directly, then mark this done.",
                    source=flow,
                    related_message_id=message_id,
                    priority="high",
                    metadata={"flow": flow, "template_key": template_key, "attempt_reasons": reasons},
                )
        else:
            status = STATUS_FAILED

    # Append a compact attempt-log entry (HR-safe: reasons only, no body).
    attempt_entry = {
        "at": _now(legacy).isoformat(),
        "attempt": attempts,
        "status": status,
        "channel": channel_used,
        "reasons": reasons,
    }

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE employee_messages
                   SET status = %s,
                       channel_used = %s,
                       last_error = %s,
                       attempts = %s,
                       next_attempt_at = %s,
                       hr_task_id = %s,
                       delivered_at = CASE WHEN %s THEN now() ELSE delivered_at END,
                       attempt_log = COALESCE(attempt_log, '[]'::jsonb) || %s::jsonb,
                       updated_at = now()
                 WHERE message_id = %s
                """,
                (
                    status,
                    channel_used,
                    ("; ".join(reasons)[:300] or None) if status not in _DELIVERED_STATUSES else None,
                    attempts,
                    next_attempt_at,
                    hr_task_id,
                    status in _DELIVERED_STATUSES,
                    legacy.json.dumps([attempt_entry]),
                    message_id,
                ),
            )
        conn.commit()

    if status in _TERMINAL_STATUSES:
        _record_layer_event(
            legacy,
            message_id=message_id,
            company_code=company_code,
            flow=flow,
            template_key=template_key,
            status=status,
            channel_used=channel_used,
            reasons=reasons,
            event_text=event_text,
            target_phone=row.get("target_phone"),
            target_email=row.get("target_email"),
            subject_type=subject_type,
            subject_key=subject_key,
            account_id=row.get("account_id"),
        )

    return {
        "ok": status in _DELIVERED_STATUSES,
        "message_id": message_id,
        "status": status,
        "channel_used": channel_used,
        "attempts": attempts,
        "reason": reasons[-1] if reasons else None,
        "attempt_reasons": reasons,
        "hr_task_id": hr_task_id,
        "next_attempt_at": next_attempt_at.isoformat() if next_attempt_at else None,
    }


def deliver_to_employee(
    *,
    company_code: str,
    flow: str,
    template_key: str,
    employee: dict[str, Any] | None = None,
    employee_key: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    locale: str | None = None,
    variables: dict[str, Any] | None = None,
    text: str | None = None,
    email_subject: str | None = None,
    criticality: str | None = None,
    sensitivity: str | None = None,
    account_id: str | None = None,
    subject_type: str = "employee",
    subject_key: str | None = None,
    dedupe_key: str | None = None,
    created_by_phone: str | None = None,
    metadata: dict[str, Any] | None = None,
    max_attempts: int | None = None,
) -> dict[str, Any]:
    """Single entry point for every employee-facing message.

    Records the message in ``employee_messages`` then walks the channel ladder
    (WhatsApp session -> approved template -> email -> HR task). Honours dry-run
    delivery mode and the per-message sensitivity storage policy. Idempotent on
    ``dedupe_key`` within a company.
    """
    import app as legacy  # lazy import to avoid an import cycle at module load

    company = str(company_code or "").strip().upper()
    if not company:
        return {"ok": False, "status": STATUS_FAILED, "error": "missing_company_code"}
    if not flow or not template_key:
        return {"ok": False, "status": STATUS_FAILED, "error": "missing_flow_or_template"}

    # Wave 2: observe/enforce outbound notifications (shadow unless canary authority).
    try:
        import tenant_control_decision as _tc_decision
        import tenant_control_surfaces as _tc_surfaces

        if _tc_decision.decision_enabled():
            queued_epoch = None
            if isinstance(metadata, dict) and metadata.get("activation_epoch") is not None:
                try:
                    queued_epoch = int(metadata.get("activation_epoch"))
                except Exception:
                    queued_epoch = None
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    result = _tc_surfaces.observe_or_enforce(
                        cur,
                        company_code=company,
                        surface="outbound_notifications",
                        module_key=(metadata or {}).get("module_key") if isinstance(metadata, dict) else None,
                        legacy_allow=True,
                        queued_epoch=queued_epoch,
                        work_kind="outbound_delivery",
                        work_ref=f"{flow}:{template_key}",
                    )
                    conn.commit()
                    if result.mode == "authoritative" and not result.allow:
                        return {
                            "ok": False,
                            "status": STATUS_FAILED,
                            "error": result.reason_code,
                            "message": result.remediation or "Outbound delivery blocked by tenant control.",
                            "correlation_id": result.audit_correlation_id,
                        }
    except Exception:
        pass

    # Wave 3: block when a required outbound integration is degraded/kill-switched.
    try:
        import tenant_control_integrations as _tc_integ

        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                blocked_providers = []
                for provider_key in ("octopus_whatsapp", "postmark_outbound"):
                    if _tc_integ.integration_blocks_side_effects(
                        cur, company_code=company, provider_key=provider_key
                    ):
                        blocked_providers.append(provider_key)
                conn.commit()
                if blocked_providers:
                    return {
                        "ok": False,
                        "status": STATUS_FAILED,
                        "error": "integration_degraded_or_kill_switch",
                        "message": "Outbound delivery blocked while integration is degraded or kill-switched.",
                        "providers": blocked_providers,
                    }
    except Exception:
        pass

    recipient = _resolve_recipient(employee)
    employee_key = employee_key or recipient["employee_key"]
    phone = phone or recipient["phone"]
    email = email or recipient["email"]
    locale = (locale or recipient["locale"] or "en").strip().lower()[:5] or "en"
    variables = dict(variables or {})
    variables.setdefault("employee_name", recipient["name"])
    # {company_name} is a first-class template variable (e.g. onboarding welcome,
    # and the "[Company] via Wathefni" shared-sender wording). Inject it centrally
    # so every flow gets it without each call site passing it.
    if not variables.get("company_name"):
        try:
            variables["company_name"] = legacy.company_display_name(company)
        except Exception:
            variables["company_name"] = company
    subject_key = subject_key or employee_key

    entry = catalog_entry(template_key)
    criticality = (criticality or entry.get("criticality") or CRITICALITY_STANDARD)
    sensitivity = (sensitivity or entry.get("sensitivity") or SENS_PREVIEW)
    max_attempts = int(max_attempts or _DEFAULT_MAX_ATTEMPTS)

    full_text = text or render_body(template_key, variables, locale)
    email_subject = email_subject or _generic_label(template_key, flow)
    storage = _body_storage(legacy, template_key=template_key, flow=flow, sensitivity=sensitivity, full_text=full_text)

    # Idempotency: a repeated submit with the same dedupe_key returns the existing
    # message instead of creating a duplicate (and re-sending).
    if dedupe_key:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT message_id, status, channel_used, hr_task_id FROM employee_messages WHERE company_code=%s AND dedupe_key=%s ORDER BY created_at DESC LIMIT 1",
                    (company, dedupe_key),
                )
                existing = cur.fetchone()
        if existing:
            return {
                "ok": existing["status"] in _DELIVERED_STATUSES,
                "message_id": str(existing["message_id"]),
                "status": existing["status"],
                "channel_used": existing.get("channel_used"),
                "hr_task_id": existing.get("hr_task_id"),
                "deduped": True,
            }

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee_messages
                  (company_code, employee_key, flow, template_key, criticality, sensitivity, locale,
                   target_phone, target_email, account_id, variables, body_preview, body_encrypted,
                   body_key_version, status, max_attempts, dedupe_key, metadata, created_by_phone)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING message_id
                """,
                (
                    company,
                    employee_key,
                    flow,
                    template_key,
                    criticality,
                    sensitivity,
                    locale,
                    legacy.digits(phone) if phone else None,
                    email,
                    account_id,
                    legacy.Json(legacy.json_safe(variables)),
                    storage["body_preview"],
                    storage["body_encrypted"],
                    storage["body_key_version"],
                    STATUS_PENDING,
                    max_attempts,
                    dedupe_key,
                    legacy.Json(legacy.json_safe(metadata or {})),
                    legacy.digits(created_by_phone) if created_by_phone else None,
                ),
            )
            row = cur.fetchone()
        conn.commit()

    message_id = str(row["message_id"])
    row_ctx = {
        "message_id": message_id,
        "company_code": company,
        "employee_key": employee_key,
        "flow": flow,
        "template_key": template_key,
        "criticality": criticality,
        "attempts": 0,
        "max_attempts": max_attempts,
        "hr_task_id": None,
        "subject_type": subject_type,
        "subject_key": subject_key,
        "event_text": storage["event_text"],
        "target_phone": phone,
        "target_email": email,
        "account_id": account_id,
    }

    outcome = _attempt_ladder(
        legacy,
        account_id=account_id,
        phone=phone,
        email=email,
        template_key=template_key,
        flow=flow,
        locale=locale,
        variables=variables,
        full_text=full_text,
        email_subject=email_subject,
        subject_type=subject_type,
        subject_key=subject_key,
        company_code=company,
        dedupe_key=dedupe_key,
    )
    return _finalize(legacy, row=row_ctx, outcome=outcome, full_text=full_text)


def _scope_clause(legacy: Any, alias: str, scope: dict[str, Any] | None) -> tuple[str, list[Any]]:
    """Reuse the org/manager scope SQL. An unrestricted viewer (HR/admin) gets no
    clause; a scoped manager only sees rows for employees in their scope. Rows
    with a NULL employee_key (company-wide tasks) are intentionally hidden from a
    scoped manager — they belong to company HR."""
    if not scope or not scope.get("restricted"):
        return "", []
    return legacy.employee_scope_sql(alias, scope)


def list_hr_tasks(
    *,
    company_code: str,
    scope: dict[str, Any] | None = None,
    statuses: list[str] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """HR follow-up tasks for a company (joined to the employee name when known),
    ordered urgent > high > normal > low, then newest first.

    Priority is a free-text column; anything unrecognised sorts as normal so an
    unexpected value can never jump the queue or sink below `low`."""
    import app as legacy

    company = str(company_code or "").strip().upper()
    statuses = statuses or ["open"]
    clause, params = _scope_clause(legacy, "t", scope)
    sql = f"""
        SELECT t.task_id, t.company_code, t.employee_key, t.task_type, t.source,
               t.title, t.detail, t.status, t.priority, t.related_message_id,
               t.created_at, t.updated_at, e.name AS employee_name
          FROM hr_tasks t
          LEFT JOIN employees e
            ON e.company_code = t.company_code AND e.employee_key = t.employee_key
         WHERE t.company_code = %s AND t.status = ANY(%s) {clause}
         ORDER BY CASE lower(coalesce(t.priority,'normal'))
                    WHEN 'urgent' THEN 0
                    WHEN 'high' THEN 1
                    WHEN 'normal' THEN 2
                    WHEN 'low' THEN 3
                    ELSE 2
                  END ASC,
                  t.created_at DESC, t.task_id
         LIMIT %s OFFSET %s
    """
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, [company, statuses, *params, int(limit), int(offset)])
            return [dict(r) for r in cur.fetchall()]


def hr_task_open_count(*, company_code: str, scope: dict[str, Any] | None = None) -> int:
    import app as legacy

    company = str(company_code or "").strip().upper()
    clause, params = _scope_clause(legacy, "t", scope)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT count(*) AS n FROM hr_tasks t WHERE t.company_code=%s AND t.status='open' {clause}",
                [company, *params],
            )
            return int(cur.fetchone()["n"])


def count_hr_tasks(*, company_code: str, scope: dict[str, Any] | None = None, statuses: list[str] | None = None) -> int:
    """True company-wide count of tasks matching `statuses`, independent of any
    page size — the number the dashboard badge/pagination footer must use, never
    the length of a possibly-truncated page."""
    import app as legacy

    company = str(company_code or "").strip().upper()
    statuses = statuses or ["open"]
    clause, params = _scope_clause(legacy, "t", scope)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT count(*) AS n FROM hr_tasks t WHERE t.company_code=%s AND t.status = ANY(%s) {clause}",
                [company, statuses, *params],
            )
            return int(cur.fetchone()["n"])


def get_hr_task(
    *,
    company_code: str,
    task_id: str,
    scope: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Load one HR task under the same company + manager scope as list_hr_tasks.

    Restricted managers never see ``employee_key IS NULL`` company-wide tasks.
    """
    import app as legacy

    company = str(company_code or "").strip().upper()
    tid = str(task_id or "").strip()
    if not company or not tid:
        return None
    clause, params = _scope_clause(legacy, "t", scope)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT t.task_id, t.company_code, t.employee_key, t.task_type, t.source,
                       t.title, t.detail, t.status, t.priority, t.related_message_id,
                       t.metadata, t.created_at, t.updated_at, e.name AS employee_name
                  FROM hr_tasks t
                  LEFT JOIN employees e
                    ON e.company_code = t.company_code AND e.employee_key = t.employee_key
                 WHERE t.company_code = %s AND t.task_id = %s {clause}
                 LIMIT 1
                """,
                [company, tid, *params],
            )
            row = cur.fetchone()
    return dict(row) if row else None


def resolve_hr_task(
    *,
    company_code: str,
    task_id: str,
    status: str = "done",
    resolver_phone: str | None = None,
    expected_status: str | None = None,
) -> dict[str, Any]:
    """Close an HR task (done/dismissed). Company-scoped: a task from another
    company is never touched.

    ``expected_status`` is the optimistic-concurrency guard shared by web and
    mobile: the status the actor was looking at when they decided. It is part
    of the UPDATE predicate, so two HR actors racing on the same task cannot
    silently overwrite each other — the loser gets ``stale_decision``.

    Returns ``task_type`` and ``metadata`` so callers (web + mobile) can run
    ``candidate_handoff`` resume side effects after resolve.
    """
    import app as legacy

    status = (status or "done").strip().lower()
    if status not in {"done", "dismissed", "open"}:
        return {"ok": False, "error": "invalid_status"}
    company = str(company_code or "").strip().upper()
    expected = str(expected_status or "").strip().lower() or None
    guard_sql = " AND status = %s" if expected else ""
    guard_params: tuple[Any, ...] = (expected,) if expected else ()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE hr_tasks
                   SET status = %s,
                       resolved_by_phone = %s,
                       resolved_at = CASE WHEN %s IN ('done','dismissed') THEN now() ELSE NULL END,
                       updated_at = now()
                 WHERE task_id = %s AND company_code = %s"""
                + guard_sql
                + """
                 RETURNING task_id, status, employee_key, source, task_type, metadata
                """,
                (status, legacy.digits(resolver_phone) if resolver_phone else None, status, task_id, company)
                + guard_params,
            )
            row = cur.fetchone()
            current_status: str | None = None
            if not row and expected:
                cur.execute(
                    "SELECT status FROM hr_tasks WHERE task_id = %s AND company_code = %s",
                    (task_id, company),
                )
                existing = cur.fetchone()
                current_status = str(existing["status"]) if existing else None
        conn.commit()
    if not row:
        if expected and current_status is not None:
            return {"ok": False, "error": "stale_decision", "current_status": current_status}
        return {"ok": False, "error": "task_not_found"}
    task = dict(row)
    if isinstance(task.get("metadata"), str):
        try:
            import json as _json

            task["metadata"] = _json.loads(task["metadata"])
        except Exception:
            task["metadata"] = {}
    return {"ok": True, "task": task}


_NEEDS_FOLLOW_UP_STATUSES = (STATUS_NEEDS_HR, STATUS_FAILED, STATUS_SUPPRESSED, STATUS_THROTTLED, STATUS_DASHBOARD_ONLY)


def list_needs_follow_up(
    *,
    company_code: str,
    scope: dict[str, Any] | None = None,
    limit: int = 100,
    offset: int = 0,
    exclude_linked_tasks: bool = False,
) -> list[dict[str, Any]]:
    """Employee messages that did not reach the employee and need attention.
    Only HR-safe fields are returned (body_preview honours the sensitivity
    policy; the raw/encrypted body is never exposed here).

    ``exclude_linked_tasks`` mirrors web Alerts & Delivery ``has_task`` dedupe:
    when True, rows already linked to an open HR task are omitted.
    """
    import app as legacy

    company = str(company_code or "").strip().upper()
    clause, params = _scope_clause(legacy, "m", scope)
    task_clause = " AND m.hr_task_id IS NULL" if exclude_linked_tasks else ""
    sql = f"""
        SELECT m.message_id, m.employee_key, m.flow, m.template_key, m.criticality,
               m.status, m.channel_used, m.last_error, m.attempts, m.hr_task_id,
               m.body_preview, m.target_email, m.created_at, m.updated_at, e.name AS employee_name
          FROM employee_messages m
          LEFT JOIN employees e
            ON e.company_code = m.company_code AND e.employee_key = m.employee_key
         WHERE m.company_code = %s
           AND m.status = ANY(%s) {clause}{task_clause}
         ORDER BY (m.criticality = '{CRITICALITY_CRITICAL}') DESC, m.updated_at DESC, m.message_id
         LIMIT %s OFFSET %s
    """
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, [company, list(_NEEDS_FOLLOW_UP_STATUSES), *params, int(limit), int(offset)])
            return [dict(r) for r in cur.fetchall()]


def count_needs_follow_up(
    *,
    company_code: str,
    scope: dict[str, Any] | None = None,
    exclude_linked_tasks: bool = False,
) -> int:
    """True company-wide count backing the needs-follow-up list, independent of
    the page size — used for the badge/footer instead of a page's length."""
    import app as legacy

    company = str(company_code or "").strip().upper()
    clause, params = _scope_clause(legacy, "m", scope)
    task_clause = " AND m.hr_task_id IS NULL" if exclude_linked_tasks else ""
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT count(*) AS n FROM employee_messages m WHERE m.company_code=%s AND m.status = ANY(%s) {clause}{task_clause}",
                [company, list(_NEEDS_FOLLOW_UP_STATUSES), *params],
            )
            return int(cur.fetchone()["n"])


def run_delivery_sweep(*, limit: int = 50) -> dict[str, Any]:
    """Retry worker: re-walk the ladder for pending messages whose next_attempt_at
    has passed. Phase A ships this callable but does not schedule it (Phase B adds
    the systemd timer + dashboard surfacing)."""
    import app as legacy

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT message_id, company_code, employee_key, flow, template_key, criticality,
                       sensitivity, locale, target_phone, target_email, account_id, variables,
                       body_preview, attempts, max_attempts, hr_task_id, dedupe_key
                  FROM employee_messages
                 WHERE status = %s
                   AND (next_attempt_at IS NULL OR next_attempt_at <= now())
                 ORDER BY next_attempt_at NULLS FIRST, created_at
                 LIMIT %s
                """,
                (STATUS_PENDING, int(limit)),
            )
            rows = [dict(r) for r in cur.fetchall()]

    processed = 0
    skipped = 0
    results: dict[str, int] = {}
    for r in rows:
        # Wave 3: epoch/lifecycle gate before retry side effects.
        try:
            import tenant_control_queue_gate as _tc_qg

            with legacy.db_connect() as gate_conn:
                with gate_conn.cursor() as gate_cur:
                    queued_epoch = _tc_qg.load_work_epoch(
                        gate_cur,
                        company_code=r["company_code"],
                        work_kind="outbound_delivery_sweep",
                        work_ref=str(r["message_id"]),
                    )
                    if queued_epoch is None:
                        queued_epoch = _tc_qg.persist_work_epoch(
                            gate_cur,
                            company_code=r["company_code"],
                            work_kind="outbound_delivery_sweep",
                            work_ref=str(r["message_id"]),
                            module_key=None,
                        )
                    allowed, decision = _tc_qg.gate_or_skip(
                        gate_cur,
                        company_code=r["company_code"],
                        module_key=None,
                        work_kind="outbound_delivery_sweep",
                        work_ref=str(r["message_id"]),
                        queued_epoch=int(queued_epoch),
                        surface="outbound_notifications",
                    )
                    gate_conn.commit()
                    if not allowed:
                        skipped += 1
                        results["held"] = results.get("held", 0) + 1
                        continue
        except Exception:
            pass
        template_key = r["template_key"]
        flow = r["flow"]
        locale = r.get("locale") or "en"
        variables = r.get("variables") or {}
        full_text = render_body(template_key, variables, locale)
        outcome = _attempt_ladder(
            legacy,
            account_id=r.get("account_id"),
            phone=r.get("target_phone"),
            email=r.get("target_email"),
            template_key=template_key,
            flow=flow,
            locale=locale,
            variables=variables,
            full_text=full_text,
            email_subject=_generic_label(template_key, flow),
            subject_type="employee",
            subject_key=r.get("employee_key"),
            company_code=r["company_code"],
            dedupe_key=r.get("dedupe_key"),
        )
        r["subject_type"] = "employee"
        r["subject_key"] = r.get("employee_key")
        r["event_text"] = r.get("body_preview") or _generic_label(template_key, flow)
        res = _finalize(legacy, row=r, outcome=outcome, full_text=full_text)
        processed += 1
        results[res["status"]] = results.get(res["status"], 0) + 1

    return {"ok": True, "processed": processed, "skipped": skipped, "by_status": results}
