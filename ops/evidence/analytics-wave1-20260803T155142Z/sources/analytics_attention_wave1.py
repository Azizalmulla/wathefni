"""Analytics Wave 1 — Attention Contract helpers.

Pure builders for ranked attention items, metric definitions, and partial-source
disclosure. Read-only; does not mutate operational modules or payroll money.
"""

from __future__ import annotations

from typing import Any


SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}

# Decorative / vanity metrics — kept only as optional supporting context, never
# as primary attention headlines.
DEMOTED_METRICS = frozenset({"Scheduled shifts", "Best attendance"})

HOURS_ABOVE_SCHEDULE_METRIC = "Hours above schedule"
HOURS_ABOVE_SCHEDULE_DETAIL = (
    "Worked minutes above scheduled minutes. Non-payroll signal — not money authority."
)


def analytics_metric_definitions() -> list[dict[str, str]]:
    return [
        {
            "key": "window",
            "label_en": "Period",
            "label_ar": "الفترة",
            "definition_en": "Kuwait month-to-date (1st of the month through today, Asia/Kuwait).",
            "definition_ar": "من بداية الشهر حتى اليوم بتوقيت الكويت (آسيا/الكويت).",
        },
        {
            "key": "pending_leave",
            "label_en": "Pending leave",
            "label_ar": "إجازات معلّقة",
            "definition_en": "Leave requests in requested status overlapping the period.",
            "definition_ar": "طلبات إجازة بحالة مطلوب ضمن الفترة.",
        },
        {
            "key": "pending_swaps",
            "label_en": "Pending swaps",
            "label_ar": "تبديلات معلّقة",
            "definition_en": "Shift swap requests awaiting a decision in the period.",
            "definition_ar": "طلبات تبديل ورديات بانتظار القرار ضمن الفترة.",
        },
        {
            "key": "pending_availability",
            "label_en": "Pending availability",
            "label_ar": "توفر معلّق",
            "definition_en": "Availability requests awaiting review in the period.",
            "definition_ar": "طلبات التوفر بانتظار المراجعة ضمن الفترة.",
        },
        {
            "key": "absences",
            "label_en": "Absences",
            "label_ar": "الغياب",
            "definition_en": "Attendance records marked absent in the period.",
            "definition_ar": "سجلات حضور بحالة غياب ضمن الفترة.",
        },
        {
            "key": "late_records",
            "label_en": "Late records",
            "label_ar": "سجلات التأخر",
            "definition_en": "Attendance with late minutes > 0 or status late.",
            "definition_ar": "حضور بدقائق تأخر > 0 أو حالة متأخر.",
        },
        {
            "key": "hours_above_schedule",
            "label_en": "Hours above schedule",
            "label_ar": "ساعات فوق الجدول",
            "definition_en": HOURS_ABOVE_SCHEDULE_DETAIL,
            "definition_ar": "دقائق عمل فوق الدقائق المجدولة. إشارة غير راتبية — ليست سلطة دفع.",
        },
        {
            "key": "branch_absences",
            "label_en": "Branch absences",
            "label_ar": "غياب الفروع",
            "definition_en": "Absence counts grouped by the employee’s primary branch.",
            "definition_ar": "عدد الغياب حسب الفرع الأساسي للموظف.",
        },
        {
            "key": "authority",
            "label_en": "Authority",
            "label_ar": "السلطة",
            "definition_en": "Analytics is a read projection. Attendance, Leave, Shifts, and Employees remain systems of action. Hiring Reports stay separate. Alerts & Delivery owns communication/delivery operations.",
            "definition_ar": "التحليلات قراءة فقط. الحضور والإجازات والورديات والموظفون تبقى أنظمة التنفيذ. تقارير التوظيف منفصلة. التنبيهات والتسليم تملك عمليات التواصل.",
        },
    ]


def analytics_source_availability(enabled_modules: set[str] | list[str] | tuple[str, ...] | None) -> dict[str, Any]:
    enabled = {str(m).strip().lower() for m in (enabled_modules or []) if str(m).strip()}
    def _src(module: str, *, note_en: str, note_ar: str, authority: str = "operational") -> dict[str, Any]:
        available = module in enabled
        return {
            "module": module,
            "available": available,
            "status": "live" if available else "unavailable",
            "authority": authority,
            "note_en": note_en if available else f"{module} is not enabled for this company.",
            "note_ar": note_ar if available else f"وحدة {module} غير مفعّلة لهذه الشركة.",
        }

    hours_available = bool(enabled & {"attendance", "shifts", "payroll"})
    sources = {
        "attendance": _src(
            "attendance",
            note_en="Absences and late records from attendance_records.",
            note_ar="الغياب والتأخر من سجلات الحضور.",
        ),
        "leave": _src(
            "leave",
            note_en="Pending leave from leave_requests.",
            note_ar="الإجازات المعلّقة من طلبات الإجازة.",
        ),
        "shifts": _src(
            "shifts",
            note_en="Scheduled shifts, swaps, and availability from shift operations.",
            note_ar="الورديات والتبديلات والتوفر من عمليات الورديات.",
        ),
        "employees": _src(
            "employees",
            note_en="Person drill-through uses the Employees directory.",
            note_ar="الانتقال للشخص يستخدم دليل الموظفين.",
            authority="directory",
        ),
        "hours_summary": {
            "module": "hours_summary",
            "available": hours_available,
            "status": "live" if hours_available else "unavailable",
            "authority": "non_payroll_hours_projection",
            "note_en": (
                "Hours-above-schedule is a non-payroll projection from attendance/shifts."
                if hours_available
                else "Hours summary needs attendance, shifts, or payroll enabled."
            ),
            "note_ar": (
                "ساعات فوق الجدول إسقاط غير راتبي من الحضور/الورديات."
                if hours_available
                else "ملخص الساعات يحتاج تفعيل الحضور أو الورديات أو الرواتب."
            ),
        },
    }
    # Employees directory is offered whenever any people-producing module is on;
    # Analytics itself does not require the employees catalog key.
    if not sources["employees"]["available"] and enabled & {
        "attendance",
        "leave",
        "shifts",
        "onboarding",
        "payroll",
        "compliance",
    }:
        sources["employees"] = {
            **sources["employees"],
            "available": True,
            "status": "live",
            "note_en": "Person drill-through uses the Employees directory (people surface).",
            "note_ar": "الانتقال للشخص يستخدم دليل الموظفين (واجهة الأفراد).",
        }
    unavailable = [key for key, row in sources.items() if not row.get("available")]
    return {
        "sources": sources,
        "unavailable_source_keys": unavailable,
        "partial": bool(unavailable),
    }


def _attention_item(
    *,
    item_id: str,
    severity: str,
    reason_en: str,
    reason_ar: str,
    subject: str,
    source_module: str,
    deep_link: dict[str, str],
    count: int | float = 0,
    value: Any = None,
    location: str | None = None,
    team: str | None = None,
    subject_key: str | None = None,
    definition_key: str | None = None,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "severity": severity if severity in SEVERITY_RANK else "low",
        "reason": reason_en,
        "reason_en": reason_en,
        "reason_ar": reason_ar,
        "subject": subject,
        "subject_key": subject_key,
        "location": location,
        "team": team,
        "source_module": source_module,
        "count": count,
        "value": value if value is not None else count,
        "deep_link": deep_link,
        "definition_key": definition_key or item_id,
    }


def build_analytics_attention(
    *,
    counts: dict[str, Any],
    summaries: list[dict[str, Any]],
    branch_rows: list[dict[str, Any]],
    sources: dict[str, Any],
    employees_deep_link_ok: bool = True,
) -> list[dict[str, Any]]:
    """Ranked attention items. Higher severity first, then larger counts."""
    src = sources.get("sources") if isinstance(sources.get("sources"), dict) else sources
    items: list[dict[str, Any]] = []

    if src.get("leave", {}).get("available"):
        pending_leave = int(counts.get("pending_leave") or 0)
        if pending_leave:
            items.append(
                _attention_item(
                    item_id="pending_leave",
                    severity="high",
                    reason_en=f"{pending_leave} leave request{'s' if pending_leave != 1 else ''} await a decision",
                    reason_ar=f"{pending_leave} طلب{'ات' if pending_leave != 1 else ''} إجازة بانتظار القرار",
                    subject="Leave queue",
                    source_module="leave",
                    count=pending_leave,
                    deep_link={"page": "leave"},
                    definition_key="pending_leave",
                )
            )

    if src.get("shifts", {}).get("available"):
        pending_swaps = int(counts.get("pending_swaps") or 0)
        if pending_swaps:
            items.append(
                _attention_item(
                    item_id="pending_swaps",
                    severity="high",
                    reason_en=f"{pending_swaps} shift swap{'s' if pending_swaps != 1 else ''} await a decision",
                    reason_ar=f"{pending_swaps} تبديل{'ات' if pending_swaps != 1 else ''} وردية بانتظار القرار",
                    subject="Shift swaps",
                    source_module="shifts",
                    count=pending_swaps,
                    deep_link={"page": "shifts"},
                    definition_key="pending_swaps",
                )
            )
        pending_availability = int(counts.get("pending_availability") or 0)
        if pending_availability:
            items.append(
                _attention_item(
                    item_id="pending_availability",
                    severity="medium",
                    reason_en=f"{pending_availability} availability request{'s' if pending_availability != 1 else ''} need review",
                    reason_ar=f"{pending_availability} طلب{'ات' if pending_availability != 1 else ''} توفر تحتاج مراجعة",
                    subject="Availability queue",
                    source_module="shifts",
                    count=pending_availability,
                    deep_link={"page": "shifts"},
                    definition_key="pending_availability",
                )
            )

    if src.get("attendance", {}).get("available"):
        absences = int(counts.get("absent_records") or 0)
        if absences:
            items.append(
                _attention_item(
                    item_id="absences",
                    severity="high",
                    reason_en=f"{absences} absence record{'s' if absences != 1 else ''} in the period",
                    reason_ar=f"{absences} سجل{'ات' if absences != 1 else ''} غياب ضمن الفترة",
                    subject="Attendance exceptions",
                    source_module="attendance",
                    count=absences,
                    deep_link={"page": "attendance"},
                    definition_key="absences",
                )
            )
        late_records = int(counts.get("late_records") or 0)
        late_minutes = int(counts.get("late_minutes") or 0)
        if late_records:
            items.append(
                _attention_item(
                    item_id="late_records",
                    severity="medium" if late_records < 5 else "high",
                    reason_en=f"{late_records} late record{'s' if late_records != 1 else ''} ({late_minutes} late minutes)",
                    reason_ar=f"{late_records} سجل{'ات' if late_records != 1 else ''} تأخر ({late_minutes} دقيقة)",
                    subject="Lateness pattern",
                    source_module="attendance",
                    count=late_records,
                    value=late_minutes,
                    deep_link={"page": "attendance"},
                    definition_key="late_records",
                )
            )

    # Person / branch concentration (patterns that still need action)
    if src.get("attendance", {}).get("available"):
        for idx, row in enumerate(branch_rows[:5]):
            branch_name = str(row.get("branch_name") or "Unassigned")
            absent_count = int(row.get("absent_count") or 0)
            if absent_count <= 0:
                continue
            items.append(
                _attention_item(
                    item_id=f"branch_absence:{branch_name}",
                    severity="medium" if absent_count < 3 else "high",
                    reason_en=f"{absent_count} absence{'s' if absent_count != 1 else ''} concentrated at {branch_name}",
                    reason_ar=f"{absent_count} غياب مركّز في {branch_name}",
                    subject=branch_name,
                    location=branch_name,
                    source_module="attendance",
                    count=absent_count,
                    deep_link={"page": "attendance"},
                    definition_key="branch_absences",
                )
            )

    hours_ok = bool(src.get("hours_summary", {}).get("available"))
    for row in sorted(
        [r for r in summaries if int(r.get("late_minutes") or 0) > 0],
        key=lambda r: int(r.get("late_minutes") or 0),
        reverse=True,
    )[:5]:
        name = str(row.get("employee_name") or row.get("employee_phone") or "Employee")
        key = str(row.get("employee_key") or "") or None
        late_m = int(row.get("late_minutes") or 0)
        deep = (
            {"page": "employees", "employee": key}
            if key and employees_deep_link_ok and src.get("employees", {}).get("available")
            else {"page": "attendance"}
        )
        items.append(
            _attention_item(
                item_id=f"top_lateness:{key or name}",
                severity="medium",
                reason_en=f"{name} has {late_m} late minutes in the period",
                reason_ar=f"{name} لديه/ها {late_m} دقيقة تأخر ضمن الفترة",
                subject=name,
                subject_key=key,
                source_module="attendance",
                count=late_m,
                deep_link=deep,
                definition_key="late_records",
            )
        )

    for row in sorted(
        [r for r in summaries if int(r.get("absent_minutes") or 0) > 0],
        key=lambda r: int(r.get("absent_minutes") or 0),
        reverse=True,
    )[:5]:
        name = str(row.get("employee_name") or row.get("employee_phone") or "Employee")
        key = str(row.get("employee_key") or "") or None
        absent_h = round(int(row.get("absent_minutes") or 0) / 60.0, 2)
        deep = (
            {"page": "employees", "employee": key}
            if key and employees_deep_link_ok and src.get("employees", {}).get("available")
            else {"page": "attendance"}
        )
        items.append(
            _attention_item(
                item_id=f"top_absence:{key or name}",
                severity="medium",
                reason_en=f"{name} has {absent_h}h absent scheduled time",
                reason_ar=f"{name} لديه/ها {absent_h} ساعة غياب مجدولة",
                subject=name,
                subject_key=key,
                source_module="attendance",
                count=absent_h,
                deep_link=deep,
                definition_key="absences",
            )
        )

    if hours_ok:
        for row in sorted(
            [r for r in summaries if int(r.get("overtime_minutes") or 0) > 0],
            key=lambda r: int(r.get("overtime_minutes") or 0),
            reverse=True,
        )[:5]:
            name = str(row.get("employee_name") or row.get("employee_phone") or "Employee")
            key = str(row.get("employee_key") or "") or None
            ot_h = round(int(row.get("overtime_minutes") or 0) / 60.0, 2)
            deep = (
                {"page": "employees", "employee": key}
                if key and employees_deep_link_ok and src.get("employees", {}).get("available")
                else {"page": "attendance"}
            )
            items.append(
                _attention_item(
                    item_id=f"hours_above_schedule:{key or name}",
                    severity="low",
                    reason_en=f"{name} worked {ot_h}h above schedule (non-payroll signal)",
                    reason_ar=f"{name} عمل/ت {ot_h} ساعة فوق الجدول (إشارة غير راتبية)",
                    subject=name,
                    subject_key=key,
                    source_module="hours_summary",
                    count=ot_h,
                    deep_link=deep,
                    definition_key="hours_above_schedule",
                )
            )

    items.sort(
        key=lambda item: (
            SEVERITY_RANK.get(str(item.get("severity")), 9),
            -float(item.get("count") or 0),
            str(item.get("id") or ""),
        )
    )
    return items


def build_analytics_pattern_insights(
    *,
    counts: dict[str, Any],
    summaries: list[dict[str, Any]],
    branch_rows: list[dict[str, Any]],
    sources: dict[str, Any],
    decimal_hours_fn,
) -> list[dict[str, Any]]:
    """Supporting pattern rows for Assistant/legacy consumers. Demotes vanity metrics."""
    src = sources.get("sources") if isinstance(sources.get("sources"), dict) else sources
    insights: list[dict[str, Any]] = []

    # Keep operational headlines for Assistant replies — not decorative scheduled/best.
    if src.get("attendance", {}).get("available"):
        insights.append(
            {
                "metric": "Absences",
                "subject": "All employees",
                "value": int(counts.get("absent_records") or 0),
                "detail": "Attendance records marked absent.",
            }
        )
        insights.append(
            {
                "metric": "Late records",
                "subject": "All employees",
                "value": int(counts.get("late_records") or 0),
                "detail": f"{int(counts.get('late_minutes') or 0)} total late minutes.",
            }
        )

    pending_review = (
        int(counts.get("pending_leave") or 0)
        + int(counts.get("pending_availability") or 0)
        + int(counts.get("pending_swaps") or 0)
    )
    if pending_review or src.get("leave", {}).get("available") or src.get("shifts", {}).get("available"):
        insights.append(
            {
                "metric": "Pending review",
                "subject": "Leave / availability / swaps",
                "value": pending_review,
                "detail": "Open operational items needing HR or manager review.",
            }
        )

    # Context-only (demoted): scheduled shifts — never primary attention.
    if src.get("shifts", {}).get("available"):
        insights.append(
            {
                "metric": "Scheduled shifts",
                "subject": "All employees",
                "value": int(counts.get("scheduled_shifts") or 0),
                "detail": "Context only — not an attention headline.",
                "demoted": True,
            }
        )

    late_rows = sorted(
        [row for row in summaries if int(row.get("late_minutes") or 0) > 0],
        key=lambda row: int(row.get("late_minutes") or 0),
        reverse=True,
    )
    for row in late_rows[:5]:
        insights.append(
            {
                "metric": "Top lateness",
                "subject": row.get("employee_name") or row.get("employee_phone") or "Employee",
                "value": int(row.get("late_minutes") or 0),
                "detail": f"{row.get('attendance_count', 0)} attendance record(s).",
                "subject_key": row.get("employee_key"),
            }
        )

    absent_rows = sorted(
        [row for row in summaries if int(row.get("absent_minutes") or 0) > 0],
        key=lambda row: int(row.get("absent_minutes") or 0),
        reverse=True,
    )
    for row in absent_rows[:5]:
        insights.append(
            {
                "metric": "Top absence",
                "subject": row.get("employee_name") or row.get("employee_phone") or "Employee",
                "value": decimal_hours_fn(row.get("absent_minutes")),
                "detail": "Absent scheduled hours.",
                "subject_key": row.get("employee_key"),
            }
        )

    if src.get("hours_summary", {}).get("available"):
        overtime_rows = sorted(
            [row for row in summaries if int(row.get("overtime_minutes") or 0) > 0],
            key=lambda row: int(row.get("overtime_minutes") or 0),
            reverse=True,
        )
        for row in overtime_rows[:5]:
            insights.append(
                {
                    "metric": HOURS_ABOVE_SCHEDULE_METRIC,
                    "subject": row.get("employee_name") or row.get("employee_phone") or "Employee",
                    "value": decimal_hours_fn(row.get("overtime_minutes")),
                    "detail": HOURS_ABOVE_SCHEDULE_DETAIL,
                    "subject_key": row.get("employee_key"),
                }
            )

    # Best attendance intentionally omitted from Wave 1 primary/supporting surface.

    for row in branch_rows[:5]:
        insights.append(
            {
                "metric": "Branch absences",
                "subject": row.get("branch_name") or "Unassigned",
                "value": int(row.get("absent_count") or 0),
                "detail": "Absence records by primary branch.",
            }
        )

    return insights


def attention_headline_stats(counts: dict[str, Any], sources: dict[str, Any]) -> list[dict[str, Any]]:
    """Compact headlines for the UI — no scheduled-shifts vanity card."""
    src = sources.get("sources") if isinstance(sources.get("sources"), dict) else sources
    pending_review = (
        int(counts.get("pending_leave") or 0)
        + int(counts.get("pending_availability") or 0)
        + int(counts.get("pending_swaps") or 0)
    )
    stats: list[dict[str, Any]] = []
    if src.get("attendance", {}).get("available"):
        stats.append(
            {
                "key": "absences",
                "label_en": "Absences",
                "label_ar": "الغياب",
                "value": int(counts.get("absent_records") or 0),
            }
        )
        stats.append(
            {
                "key": "late_records",
                "label_en": "Late records",
                "label_ar": "سجلات التأخر",
                "value": int(counts.get("late_records") or 0),
                "hint_en": f"{int(counts.get('late_minutes') or 0)} late minutes"
                if int(counts.get("late_minutes") or 0)
                else None,
                "hint_ar": f"{int(counts.get('late_minutes') or 0)} دقيقة تأخر"
                if int(counts.get("late_minutes") or 0)
                else None,
            }
        )
    if src.get("leave", {}).get("available") or src.get("shifts", {}).get("available"):
        stats.append(
            {
                "key": "pending_review",
                "label_en": "Pending review",
                "label_ar": "بانتظار المراجعة",
                "value": pending_review,
                "hint_en": "Leave · availability · swaps",
                "hint_ar": "إجازة · توفر · تبديلات",
            }
        )
    return stats
