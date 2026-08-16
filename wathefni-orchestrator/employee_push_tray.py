"""Employee App push tray copy + policy helpers.

Tray notifications stay short (title + one line). Long WhatsApp/email bodies stay
on the outbound ladder for those channels only. Inbox still uses body_preview from
deliver_to_employee.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Any

# Flows / templates that must never interrupt via Expo push (Inbox + WA/email OK).
PUSH_INBOX_ONLY_FLOWS = frozenset({"app_activation"})
PUSH_INBOX_ONLY_TEMPLATES = frozenset({"app_activation"})

# Templates that default to iOS timeSensitive (further gated in interruption_level).
PUSH_TIME_SENSITIVE_TEMPLATES = frozenset({"shift_reminder"})

_EN_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
_AR_MONTHS = (
    "يناير",
    "فبراير",
    "مارس",
    "أبريل",
    "مايو",
    "يونيو",
    "يوليو",
    "أغسطس",
    "سبتمبر",
    "أكتوبر",
    "نوفمبر",
    "ديسمبر",
)
_EN_MONTHS_FULL = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

PUSH_TRAY: dict[str, dict[str, dict[str, str]]] = {
    "leave_request_approved": {
        "en": {"title": "Leave approved", "body": "Your leave from {date_text} has been approved."},
        "ar": {"title": "تمت الموافقة على الإجازة", "body": "تمت الموافقة على إجازتك من {date_text}."},
    },
    "leave_request_rejected": {
        "en": {"title": "Leave rejected", "body": "Your leave request for {date_text} was not approved."},
        "ar": {"title": "رُفض طلب الإجازة", "body": "لم تتم الموافقة على طلب إجازتك لـ {date_text}."},
    },
    "shift_assigned": {
        "en": {"title": "New shift", "body": "Your shift on {shift_date} is {shift_time}."},
        "ar": {"title": "مناوبة جديدة", "body": "مناوبتك يوم {shift_date} هي {shift_time}."},
    },
    "shift_rescheduled": {
        "en": {"title": "Shift updated", "body": "Your shift on {shift_date} is now {shift_time}."},
        "ar": {"title": "تم تحديث المناوبة", "body": "مناوبتك يوم {shift_date} أصبحت {shift_time}."},
    },
    "shift_reminder": {
        "en": {"title": "Shift reminder", "body": "Your shift starts at {shift_time} today."},
        "ar": {"title": "تذكير بالمناوبة", "body": "تبدأ مناوبتك اليوم الساعة {shift_time}."},
    },
    "shift_cancelled": {
        "en": {"title": "Shift cancelled", "body": "Your shift on {shift_date} was cancelled."},
        "ar": {"title": "تم إلغاء المناوبة", "body": "أُلغيت مناوبتك يوم {shift_date}."},
    },
    "employee_onboarding_welcome": {
        "en": {"title": "Onboarding started", "body": "You have onboarding steps waiting for you."},
        "ar": {"title": "بدأ الانضمام", "body": "لديك خطوات انضمام بانتظارك."},
    },
    "onboarding_reminder": {
        "en": {"title": "Onboarding action needed", "body": "You have an onboarding item waiting for you."},
        "ar": {"title": "إجراء انضمام مطلوب", "body": "لديك خطوة انضمام بانتظارك."},
    },
    "compliance_document_required": {
        "en": {"title": "Document action needed", "body": "Please update your {document_type}."},
        "ar": {"title": "مطلوب تحديث مستند", "body": "يرجى تحديث {document_type}."},
    },
    "compliance_document_expiring": {
        "en": {"title": "Document expiring", "body": "Your {document_type} expires on {expiry_date}."},
        "ar": {"title": "مستند ينتهي قريباً", "body": "{document_type} ينتهي في {expiry_date}."},
    },
    "payslip_ready": {
        "en": {"title": "Payslip ready", "body": "Your {period} payslip is ready."},
        "ar": {"title": "كشف الراتب جاهز", "body": "كشف راتبك لـ {period} جاهز."},
    },
    "bank_correction_required": {
        "en": {"title": "Bank details need attention", "body": "Please update your bank details."},
        "ar": {"title": "تفاصيل البنك تحتاج تصحيحاً", "body": "يرجى تحديث بياناتك البنكية."},
    },
}


def push_allowed(*, flow: str | None, template_key: str | None) -> bool:
    flow_key = str(flow or "").strip().lower()
    tmpl = str(template_key or "").strip().lower()
    if flow_key in PUSH_INBOX_ONLY_FLOWS:
        return False
    if tmpl in PUSH_INBOX_ONLY_TEMPLATES:
        return False
    return True


def _locale_bucket(locale: str | None) -> str:
    raw = str(locale or "en").strip().lower()
    if raw.startswith("ar"):
        return "ar"
    return "en"


def _parse_date(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    raw = raw[:10]
    try:
        return date.fromisoformat(raw)
    except Exception:
        pass
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except Exception:
            continue
    return None


def _format_friendly_date(value: Any, *, locale: str, today: date | None = None) -> str:
    """Human tray dates: 23 Aug, 23–25 Aug, 23 Aug 2026 (never ISO)."""
    parsed = _parse_date(value)
    if not parsed:
        text = str(value or "").strip()
        # Already friendly or empty — leave as-is (still scrub ISO fragments later).
        return text
    ref = today or date.today()
    months = _AR_MONTHS if locale == "ar" else _EN_MONTHS
    month = months[parsed.month - 1]
    day = parsed.day
    if parsed.year != ref.year:
        if locale == "ar":
            return f"{day} {month} {parsed.year}"
        return f"{day} {month} {parsed.year}"
    if locale == "ar":
        return f"{day} {month}"
    return f"{day} {month}"


def _format_friendly_range(start: Any, end: Any, *, locale: str, today: date | None = None) -> str:
    start_d = _parse_date(start)
    end_d = _parse_date(end)
    if not start_d and not end_d:
        return ""
    if start_d and not end_d:
        return _format_friendly_date(start_d, locale=locale, today=today)
    if end_d and not start_d:
        return _format_friendly_date(end_d, locale=locale, today=today)
    assert start_d and end_d
    if start_d == end_d:
        return _format_friendly_date(start_d, locale=locale, today=today)
    ref = today or date.today()
    months = _AR_MONTHS if locale == "ar" else _EN_MONTHS
    sep = "–"
    same_year = start_d.year == end_d.year
    show_year = start_d.year != ref.year or end_d.year != ref.year
    if start_d.month == end_d.month and same_year:
        month = months[start_d.month - 1]
        core = f"{start_d.day}{sep}{end_d.day} {month}"
        if show_year:
            return f"{core} {start_d.year}"
        return core
    left = _format_friendly_date(start_d, locale=locale, today=today)
    # Avoid repeating year on the right when same year already shown / omitted.
    if same_year and not show_year:
        right_month = months[end_d.month - 1]
        right = f"{end_d.day} {right_month}"
    else:
        right = _format_friendly_date(end_d, locale=locale, today=today)
    return f"{left}{sep}{right}"


def _parse_time_token(raw: str) -> time | None:
    token = raw.strip()
    if not token:
        return None
    # Strip seconds if present: 09:00:00
    m = re.match(r"^(\d{1,2}):(\d{2})(?::\d{2})?\s*([AaPp][Mm])?$", token)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2))
    ampm = (m.group(3) or "").upper()
    if ampm:
        if ampm == "PM" and hour < 12:
            hour += 12
        if ampm == "AM" and hour == 12:
            hour = 0
    if hour > 23 or minute > 59:
        return None
    return time(hour=hour, minute=minute)


def _format_friendly_time(value: Any, *, locale: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    # Ranges: 09:00-17:00 / 09:00 – 17:00 / 9:00 AM-5:00 PM
    parts = re.split(r"\s*[–\-—]\s*", raw, maxsplit=1)
    if len(parts) == 2:
        left = _format_friendly_time(parts[0], locale=locale)
        right = _format_friendly_time(parts[1], locale=locale)
        if left and right:
            return f"{left}–{right}"
        return raw
    parsed = _parse_time_token(raw)
    if not parsed:
        return raw
    hour24 = parsed.hour
    minute = parsed.minute
    if locale == "ar":
        # 24h is natural in Kuwait AR UI; keep compact.
        return f"{hour24}:{minute:02d}"
    hour12 = hour24 % 12 or 12
    suffix = "AM" if hour24 < 12 else "PM"
    if minute == 0:
        return f"{hour12}:00 {suffix}"
    return f"{hour12}:{minute:02d} {suffix}"


def _format_friendly_period(value: Any, *, locale: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    # Strip canary/test suffixes.
    cleaned = re.sub(r"\s+canary.*$", "", raw, flags=re.IGNORECASE).strip()
    # YYYY-MM
    m = re.match(r"^(\d{4})-(\d{2})$", cleaned)
    if m:
        year = int(m.group(1))
        month = int(m.group(2))
        if 1 <= month <= 12:
            if locale == "ar":
                return f"{_AR_MONTHS[month - 1]} {year}"
            return f"{_EN_MONTHS_FULL[month - 1]} {year}"
    # Already "August 2026" / "Aug 2026"
    return cleaned


def _humanize_date_text(value: Any, *, locale: str, today: date | None = None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    # ISO range variants: 2026-08-23 to 2026-08-25 / 2026-08-23 - 2026-08-25
    m = re.match(
        r"^(\d{4}-\d{2}-\d{2})\s*(?:to|–|-|—)\s*(\d{4}-\d{2}-\d{2})$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        return _format_friendly_range(m.group(1), m.group(2), locale=locale, today=today)
    if _parse_date(raw):
        return _format_friendly_date(raw, locale=locale, today=today)
    return raw


def _prepare_variables(variables: dict[str, Any] | None, *, locale: str) -> dict[str, str]:
    vars_in = {str(k): str(v if v is not None else "") for k, v in dict(variables or {}).items()}
    start = vars_in.get("start_date") or ""
    end = vars_in.get("end_date") or ""

    if start or end:
        vars_in["date_text"] = _format_friendly_range(start, end, locale=locale) or _humanize_date_text(
            vars_in.get("date_text"), locale=locale
        )
    elif vars_in.get("date_text"):
        vars_in["date_text"] = _humanize_date_text(vars_in.get("date_text"), locale=locale)

    if vars_in.get("shift_date"):
        vars_in["shift_date"] = _format_friendly_date(vars_in["shift_date"], locale=locale)
    if vars_in.get("expiry_date"):
        vars_in["expiry_date"] = _format_friendly_date(vars_in["expiry_date"], locale=locale)
    if vars_in.get("shift_time"):
        vars_in["shift_time"] = _format_friendly_time(vars_in["shift_time"], locale=locale)
    if vars_in.get("period"):
        vars_in["period"] = _format_friendly_period(vars_in["period"], locale=locale)
    return vars_in


def _format(template: str, variables: dict[str, Any] | None, *, locale: str) -> str:
    vars_in = _prepare_variables(variables, locale=locale)
    try:
        return template.format_map(_SafeDict(vars_in))
    except Exception:
        return template


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return ""


def tray_copy(
    template_key: str,
    *,
    locale: str | None = None,
    variables: dict[str, Any] | None = None,
    fallback_title: str | None = None,
    fallback_body: str | None = None,
) -> tuple[str, str]:
    """Return (title, body) for Expo tray. Never returns empty title/body when fallbacks exist."""
    tmpl = str(template_key or "").strip()
    bucket = _locale_bucket(locale)
    entry = PUSH_TRAY.get(tmpl) or {}
    localized = entry.get(bucket) or entry.get("en") or {}
    title = _format(
        str(localized.get("title") or fallback_title or tmpl.replace("_", " ").title()),
        variables,
        locale=bucket,
    )
    body = _format(str(localized.get("body") or fallback_body or title), variables, locale=bucket)
    # Hard cap tray body length (APNs / UX).
    if len(body) > 140:
        body = body[:137].rstrip() + "…"
    if len(title) > 60:
        title = title[:57].rstrip() + "…"
    return title, body


def collapse_id(*, company_code: str, flow: str, template_key: str, subject_key: str | None, dedupe_key: str | None = None) -> str:
    """Stable collapse key so superseded/duplicate events replace rather than spam."""
    company = str(company_code or "").strip().upper() or "WATHEFNI"
    if dedupe_key:
        raw = f"{company}:{dedupe_key}"
    else:
        raw = f"{company}:{flow}:{template_key}:{subject_key or ''}"
    # Expo/APNs collapseId max ~64 bytes practical.
    return raw[:64]


def interruption_level(template_key: str, *, time_sensitive: bool | None = None, variables: dict[str, Any] | None = None) -> str | None:
    tmpl = str(template_key or "").strip().lower()
    if time_sensitive is True:
        return "timeSensitive"
    if time_sensitive is False:
        return None
    if tmpl == "shift_reminder":
        return "timeSensitive"
    if tmpl == "shift_cancelled":
        # Same-day cancel is urgent; future-day cancel stays normal.
        shift_date = str((variables or {}).get("shift_date") or "").strip()[:10]
        if shift_date:
            try:
                if date.fromisoformat(shift_date) <= date.today():
                    return "timeSensitive"
            except Exception:
                return "timeSensitive"
        return None
    if tmpl in PUSH_TIME_SENSITIVE_TEMPLATES:
        return "timeSensitive"
    return None
