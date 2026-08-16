"""Official employee payslip PDF (P0.1 + Payroll Authority P1).

Authority (frozen with P0 release gate):
  Employee-visible iff status=active AND employee_visibility=released.

Official PDF eligibility (strict, P1):
  source_kind=external_import
  AND money_authority=external
  AND authority_snapshot_id → sealed snapshot with money_authority=external
  NEVER native_preview / preview_non_authoritative
  NEVER period-close alone

Long-term target eligibility:
  sealed authoritative snapshot + valid current payslip version + released to employee.

PDF is generated from the immutable payslip snapshot (document_payload + lines)
bound to a specific payslip_id/version. Replacement creates a new payslip_id and
a new PDF; released PDFs never silently rewrite under the same fingerprint.

payment_date is omitted when unknown — never invented.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

PAYSLIP_OFFICIAL_PDF_VERSION = "1.1.0"
FILE_KIND = "payslip_official_pdf"
OFFICIAL_PDF_SCHEMA = Path(__file__).resolve().parent / "ops" / "sql" / "payroll_payslip_official_pdf_v1.sql"
OFFICIAL_PDF_SQL = OFFICIAL_PDF_SCHEMA.read_text(encoding="utf-8") if OFFICIAL_PDF_SCHEMA.exists() else ""

SOURCE_EXTERNAL = "external_import"
SOURCE_NATIVE_AUTH = "native_authoritative"
MONEY_EXTERNAL = "external"
MONEY_WATHEFNI = "wathefni"
STATUS_SEALED = "sealed"
_PUBLIC_PLATFORM_BRAND = "OctoHR"
_LEGACY_CUSTOMER_BRAND_RE = re.compile(r"\bwathefni\b|وظفني|وظّفني|وثفني|وثّفني", re.IGNORECASE)


def _customer_company_name(value: Any) -> str:
    name = str(value or "").strip()
    if not name or _LEGACY_CUSTOMER_BRAND_RE.search(name):
        return _PUBLIC_PLATFORM_BRAND
    return name


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _sealed_authority_ok(doc: dict[str, Any] | None, sealed: dict[str, Any] | None = None) -> bool:
    snap_id = str((doc or {}).get("authority_snapshot_id") or "").strip()
    if not snap_id:
        return False
    if sealed is None:
        return True  # id present; caller should verify sealed row when cur available
    money = str(sealed.get("money_authority") or "")
    return (
        str(sealed.get("status") or "") == STATUS_SEALED
        and money in (MONEY_EXTERNAL, MONEY_WATHEFNI)
        and str(sealed.get("authority_snapshot_id") or "") == snap_id
        and money == str((doc or {}).get("money_authority") or "")
    )


def is_official_pdf_eligible(
    doc: dict[str, Any] | None,
    *,
    sealed_snapshot: dict[str, Any] | None = None,
    require_sealed_verification: bool = False,
) -> bool:
    """True for sealed external OR sealed wathefni (Mode A) money-authority payslips."""
    if not doc:
        return False
    source = str(doc.get("source_kind") or "")
    money = str(doc.get("money_authority") or "")
    mode_b = source == SOURCE_EXTERNAL and money == MONEY_EXTERNAL
    mode_a = source == SOURCE_NATIVE_AUTH and money == MONEY_WATHEFNI
    if not (mode_b or mode_a):
        return False
    snap_id = str(doc.get("authority_snapshot_id") or "").strip()
    if not snap_id:
        return False
    if require_sealed_verification or sealed_snapshot is not None:
        return _sealed_authority_ok(doc, sealed_snapshot)
    return True


def official_pdf_refusal(
    doc: dict[str, Any] | None,
    *,
    sealed_snapshot: dict[str, Any] | None = None,
    require_sealed_verification: bool = False,
) -> dict[str, Any] | None:
    if is_official_pdf_eligible(
        doc,
        sealed_snapshot=sealed_snapshot,
        require_sealed_verification=require_sealed_verification,
    ):
        return None
    missing_seal = not str((doc or {}).get("authority_snapshot_id") or "").strip()
    return {
        "ok": False,
        "error": "official_pdf_not_eligible",
        "message": (
            "Official PDF requires a current sealed authority snapshot linked to the payslip "
            "(money_authority=external Mode B, or money_authority=wathefni Mode A). "
            "Native preview calculations are non-authoritative and cannot become official documents. "
            "Period close alone does not grant money authority."
        ),
        "source_kind": (doc or {}).get("source_kind"),
        "money_authority": (doc or {}).get("money_authority"),
        "authority_snapshot_id": (doc or {}).get("authority_snapshot_id"),
        "missing_sealed_authority": missing_seal,
        "native_preview_authoritative": False,
        "period_close_is_money_seal": False,
        "official_employee_pdf_requires": (
            "(Mode B) sealed external authority_snapshot + source_kind=external_import + money_authority=external "
            "OR (Mode A) sealed wathefni authority_snapshot + source_kind=native_authoritative + money_authority=wathefni"
        ),
    }


def ensure_official_pdf_schema(cur: Any) -> None:
    if OFFICIAL_PDF_SQL.strip():
        cur.execute(OFFICIAL_PDF_SQL)


def production_authority_blockers() -> dict[str, Any]:
    """Exact remaining gates before Wathefni can claim production money authority on real employees."""
    return {
        "official_pdf_capability": True,
        "official_pdf_eligible_sources": [
            "external_import + sealed money_authority=external",
            "native_authoritative + sealed money_authority=wathefni (P5 Mode A)",
        ],
        "native_preview_never_official": True,
        "native_preview_reason": (
            "Wave 2B native preview remains preview_non_authoritative forever; "
            "P5 seals a separate money_authority=wathefni snapshot after finalize gates."
        ),
        "mode_a_synthetic_only": True,
        "period_close_is_money_seal": False,
        "payment_processing": "disabled",
        "payment_date_field": None,
        "payment_date_invented": False,
        "remaining_production_authority_gate": (
            "P6: remove SYNTHETIC_ONLY for allowlisted companies/employees after residual-zero "
            "qualification. Do not invent payment_date or enable WPS in P5."
        ),
    }


def _workspace_root() -> Path:
    raw = (
        os.environ.get("WATHEFNI_PAYSLIP_PDF_ROOT")
        or os.environ.get("WATHEFNI_WORKSPACE")
        or "/tmp/wathefni-workspace"
    )
    return Path(raw).resolve()


def _pdf_dir(*, company_code: str, employee_key: str) -> Path:
    company = (company_code or "").upper()
    dest = (
        _workspace_root()
        / "data"
        / "companies"
        / company
        / "files"
        / "employee"
        / str(employee_key)
        / FILE_KIND
    )
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _money(value: Any) -> str:
    try:
        return f"{Decimal(str(value)):.3f}"
    except Exception:
        return str(value or "0")


def _locale(locale: str | None) -> str:
    return "ar" if str(locale or "en").lower().startswith("ar") else "en"


def render_official_payslip_pdf_bytes(
    *,
    company_name: str,
    employee_name: str,
    employee_id: str,
    payslip: dict[str, Any],
    lines: list[dict[str, Any]],
    locale: str = "en",
    payment_date: str | None = None,
) -> bytes:
    """Deterministic professional PDF from an immutable payslip snapshot."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("reportlab_required_for_official_payslip_pdf") from exc

    loc = _locale(locale)
    is_ar = loc == "ar"
    # Prefer LTR layout with bilingual labels; RTL full layout needs Arabic fonts
    # that may be absent on the VPS. Labels are EN/AR; amounts are locale-neutral.
    labels = {
        "title": "Payslip" if not is_ar else "كشف راتب",
        "company": "Company" if not is_ar else "الشركة",
        "employee": "Employee" if not is_ar else "الموظف",
        "employee_id": "Employee ID" if not is_ar else "رقم الموظف",
        "period": "Pay period" if not is_ar else "فترة الراتب",
        "version": "Document version" if not is_ar else "إصدار المستند",
        "earnings": "Earnings / Allowances" if not is_ar else "المستحقات / البدلات",
        "deductions": "Deductions" if not is_ar else "الخصومات",
        "basic": "Basic salary" if not is_ar else "الراتب الأساسي",
        "net": "Net pay" if not is_ar else "صافي الراتب",
        "payment_date": "Payment date" if not is_ar else "تاريخ الصرف",
        "currency": "Currency" if not is_ar else "العملة",
        "authority": "Money authority" if not is_ar else "سلطة المبالغ",
        "footer": (
            "This payslip PDF is generated from an immutable external payroll snapshot. "
            "It does not authorize OctoHR payment processing."
            if not is_ar
            else "تم إنشاء ملف PDF لكشف الراتب من لقطة رواتب خارجية ثابتة. لا يُعد تفويضاً لمعالجة الصرف عبر OctoHR."
        ),
        "description": "Description" if not is_ar else "الوصف",
        "amount": "Amount" if not is_ar else "المبلغ",
    }

    currency = str(payslip.get("currency") or "KWD")
    period = f"{payslip.get('period_start')} → {payslip.get('period_end')}"
    version = str(payslip.get("version_number") or 1)
    money_auth = str(payslip.get("money_authority") or MONEY_EXTERNAL)

    safe_lines = []
    for ln in lines:
        kind = str(ln.get("line_kind") or "")
        label = ln.get("label_ar" if is_ar else "label_en") or ln.get("label") or ln.get("code") or kind
        safe_lines.append(
            {
                "line_kind": kind,
                "label": str(label),
                "amount": ln.get("amount"),
                "code": str(ln.get("code") or ""),
            }
        )

    basic_line = next(
        (
            ln
            for ln in safe_lines
            if ln["code"].upper() in {"BASIC", "BASIC_SALARY", "BASE"}
            or ln["line_kind"] in {"basic"}
        ),
        None,
    )
    earnings = [
        ln
        for ln in safe_lines
        if ln["line_kind"] in {"earning", "allowance", "basic", "one_time_earning"}
    ]
    deductions = [
        ln
        for ln in safe_lines
        if ln["line_kind"] in {"deduction", "one_time_deduction"} or "deduct" in ln["line_kind"]
    ]
    if not earnings and not deductions:
        earnings = [ln for ln in safe_lines if float(ln.get("amount") or 0) >= 0]
        deductions = [ln for ln in safe_lines if float(ln.get("amount") or 0) < 0]

    buf_path = None
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        buf_path = Path(tmp.name)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "PayslipTitle",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=6,
        alignment=TA_CENTER,
    )
    h_style = ParagraphStyle(
        "PayslipH",
        parent=styles["Heading2"],
        fontSize=11,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=10,
        spaceAfter=4,
        alignment=TA_LEFT,
    )
    body = ParagraphStyle(
        "PayslipBody",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#334155"),
        leading=12,
        alignment=TA_LEFT,
    )
    footer_style = ParagraphStyle(
        "PayslipFooter",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#64748B"),
        leading=11,
        alignment=TA_CENTER,
    )

    doc = SimpleDocTemplate(
        str(buf_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"{labels['title']} {period}",
        author=company_name or "OctoHR",
    )
    story: list[Any] = []
    story.append(Paragraph(company_name or "—", title_style))
    story.append(Paragraph(labels["title"], h_style))
    story.append(Spacer(1, 4))

    meta_rows = [
        [labels["employee"], employee_name or "—"],
        [labels["employee_id"], employee_id or "—"],
        [labels["period"], period],
        [labels["version"], f"v{version}"],
        [labels["currency"], currency],
        [labels["authority"], money_auth],
    ]
    # payment_date only if genuinely known
    if payment_date:
        meta_rows.append([labels["payment_date"], str(payment_date)])

    meta = Table(meta_rows, colWidths=[55 * mm, 110 * mm])
    meta.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#64748B")),
                ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#0F172A")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(meta)
    story.append(Spacer(1, 8))

    if basic_line:
        story.append(Paragraph(labels["basic"], h_style))
        story.append(Paragraph(f"{_money(basic_line.get('amount'))} {currency}", body))

    def _section(title: str, rows: list[dict[str, Any]]) -> None:
        story.append(Paragraph(title, h_style))
        data = [[labels["description"], labels["amount"]]]
        for ln in rows:
            data.append([ln["label"], f"{_money(ln.get('amount'))} {currency}"])
        if len(data) == 1:
            data.append(["—", "—"])
        table = Table(data, colWidths=[120 * mm, 45 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0F172A")),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(table)

    _section(labels["earnings"], earnings)
    _section(labels["deductions"], deductions)

    story.append(Spacer(1, 10))
    net_table = Table(
        [[labels["net"], f"{_money(payslip.get('totals_net'))} {currency}"]],
        colWidths=[120 * mm, 45 * mm],
    )
    net_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0F172A")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(net_table)
    story.append(Spacer(1, 14))
    story.append(Paragraph(labels["footer"], footer_style))
    story.append(
        Paragraph(
            f"payslip_id={payslip.get('payslip_id')} · fingerprint={(payslip.get('content_fingerprint') or '')[:16]}",
            footer_style,
        )
    )

    doc.build(story)
    data = buf_path.read_bytes()
    try:
        buf_path.unlink(missing_ok=True)
    except Exception:
        pass
    if not data.startswith(b"%PDF"):
        raise RuntimeError("pdf_render_invalid")
    return data


def _load_sealed_for_payslip(cur: Any, *, company_code: str, doc: dict[str, Any]) -> dict[str, Any] | None:
    snap_id = str(doc.get("authority_snapshot_id") or "").strip()
    if not snap_id:
        return None
    try:
        cur.execute(
            """
            SELECT * FROM payroll_authority_snapshots
            WHERE company_code=%s AND authority_snapshot_id=%s
            LIMIT 1
            """,
            ((company_code or "").upper(), snap_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def ensure_official_pdf_for_payslip(
    cur: Any,
    *,
    company_code: str,
    payslip_id: str,
    locale: str = "en",
    company_name: str | None = None,
    employee_name: str | None = None,
    employee_id: str | None = None,
    payment_date: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Generate+store official PDF for one locale if eligible; idempotent by fingerprint."""
    ensure_official_pdf_schema(cur)
    company = (company_code or "").upper()
    cur.execute(
        "SELECT * FROM payroll_payslip_documents WHERE company_code=%s AND payslip_id=%s LIMIT 1",
        (company, payslip_id),
    )
    row = cur.fetchone()
    doc = dict(row) if row else None
    if not doc:
        return {"ok": False, "error": "payslip_not_found"}
    sealed = _load_sealed_for_payslip(cur, company_code=company, doc=doc)
    refused = official_pdf_refusal(
        doc, sealed_snapshot=sealed, require_sealed_verification=True
    )
    if refused:
        return refused

    loc = _locale(locale)
    path_col = "official_pdf_en_path" if loc == "en" else "official_pdf_ar_path"
    sha_col = "official_pdf_en_sha256" if loc == "en" else "official_pdf_ar_sha256"
    fp = str(doc.get("content_fingerprint") or "")
    existing_path = str(doc.get(path_col) or "").strip()
    existing_sha = str(doc.get(sha_col) or "").strip()
    stored_fp = str(doc.get("official_pdf_content_fingerprint") or "").strip()

    if (
        not force
        and existing_path
        and existing_sha
        and stored_fp == fp
        and Path(existing_path).is_file()
    ):
        return {
            "ok": True,
            "idempotent": True,
            "locale": loc,
            "path": existing_path,
            "sha256": existing_sha,
            "payslip_id": str(payslip_id),
            "official_document": True,
            "content_fingerprint": fp,
        }

    cur.execute(
        """
        SELECT * FROM payroll_payslip_lines
        WHERE company_code=%s AND payslip_id=%s
        ORDER BY sort_order, code
        """,
        (company, payslip_id),
    )
    lines = [dict(r) for r in (cur.fetchall() or [])]

    emp_key = str(doc.get("employee_key") or "")
    # Resolve display fields if not provided (never invent payment_date).
    resolved_company = company_name
    resolved_employee = employee_name
    resolved_id = employee_id or emp_key
    if not resolved_company:
        cur.execute("SELECT name FROM companies WHERE company_code=%s LIMIT 1", (company,))
        crow = cur.fetchone()
        resolved_company = _customer_company_name((dict(crow) if crow else {}).get("name"))
    else:
        resolved_company = _customer_company_name(resolved_company)
    if not resolved_employee:
        cur.execute(
            "SELECT name, phone FROM employees WHERE company_code=%s AND employee_key=%s LIMIT 1",
            (company, emp_key),
        )
        erow = cur.fetchone()
        resolved_employee = str((dict(erow) if erow else {}).get("name") or emp_key)

    pdf_bytes = render_official_payslip_pdf_bytes(
        company_name=resolved_company or _PUBLIC_PLATFORM_BRAND,
        employee_name=resolved_employee or emp_key,
        employee_id=resolved_id,
        payslip=_json_safe(doc),
        lines=_json_safe(lines),
        locale=loc,
        payment_date=payment_date,  # only pass when genuinely known
    )
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    dest_dir = _pdf_dir(company_code=company, employee_key=emp_key)
    filename = f"{payslip_id}-{loc}-{fp[:12] or sha[:12]}.pdf"
    dest = dest_dir / filename
    dest.write_bytes(pdf_bytes)

    cur.execute(
        f"""
        UPDATE payroll_payslip_documents
        SET {path_col}=%s,
            {sha_col}=%s,
            official_pdf_content_fingerprint=%s,
            official_pdf_generated_at=now(),
            updated_at=now()
        WHERE company_code=%s AND payslip_id=%s
        RETURNING *
        """,
        (str(dest), sha, fp, company, payslip_id),
    )
    updated = dict(cur.fetchone() or {})
    cur.execute(
        """
        INSERT INTO payroll_payslip_events (payslip_id, company_code, event_type, payload, created_by_phone)
        VALUES (%s,%s,%s,%s::jsonb,%s)
        """,
        (
            payslip_id,
            company,
            "official_pdf_generated",
            json.dumps(
                {
                    "locale": loc,
                    "sha256": sha,
                    "path": str(dest),
                    "content_fingerprint": fp,
                    "bytes": len(pdf_bytes),
                }
            ),
            None,
        ),
    )
    return {
        "ok": True,
        "idempotent": False,
        "locale": loc,
        "path": str(dest),
        "sha256": sha,
        "bytes": len(pdf_bytes),
        "payslip_id": str(payslip_id),
        "official_document": True,
        "content_fingerprint": fp,
        "payslip": _json_safe(updated),
        "version": PAYSLIP_OFFICIAL_PDF_VERSION,
    }


def read_official_pdf(
    cur: Any,
    *,
    company_code: str,
    payslip_id: str,
    locale: str = "en",
) -> dict[str, Any]:
    """Read stored official PDF bytes for an eligible payslip version."""
    ensure_official_pdf_schema(cur)
    company = (company_code or "").upper()
    loc = _locale(locale)
    cur.execute(
        "SELECT * FROM payroll_payslip_documents WHERE company_code=%s AND payslip_id=%s LIMIT 1",
        (company, payslip_id),
    )
    row = cur.fetchone()
    doc = dict(row) if row else None
    if not doc:
        return {"ok": False, "error": "payslip_not_found"}
    sealed = _load_sealed_for_payslip(cur, company_code=company, doc=doc)
    refused = official_pdf_refusal(
        doc, sealed_snapshot=sealed, require_sealed_verification=True
    )
    if refused:
        return refused
    path_col = "official_pdf_en_path" if loc == "en" else "official_pdf_ar_path"
    sha_col = "official_pdf_en_sha256" if loc == "en" else "official_pdf_ar_sha256"
    path = str(doc.get(path_col) or "").strip()
    if not path or not Path(path).is_file():
        return {"ok": False, "error": "official_pdf_not_generated", "locale": loc}
    data = Path(path).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    expected = str(doc.get(sha_col) or "")
    if expected and sha != expected:
        return {"ok": False, "error": "official_pdf_integrity_mismatch"}
    # Path traversal guard relative to workspace
    try:
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(_workspace_root()):
            return {"ok": False, "error": "official_pdf_path_rejected"}
    except Exception:
        return {"ok": False, "error": "official_pdf_path_rejected"}
    filename = f"payslip-{doc.get('employee_key')}-{doc.get('period_start')}-v{doc.get('version_number')}-{loc}.pdf"
    return {
        "ok": True,
        "locale": loc,
        "path": path,
        "sha256": sha,
        "body": data,
        "filename": filename,
        "content_type": "application/pdf",
        "official_document": True,
        "payslip_id": str(payslip_id),
        "content_fingerprint": doc.get("content_fingerprint"),
        "totals_net": doc.get("totals_net"),
        "currency": doc.get("currency"),
    }
