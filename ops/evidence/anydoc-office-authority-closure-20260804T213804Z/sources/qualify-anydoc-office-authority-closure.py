#!/usr/bin/env python3
"""Build production-shaped Office corpus + qualify AnyDoc authority closure."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "wathefni-orchestrator"
sys.path.insert(0, str(ORCH))

os.environ["WATHEFNI_ANYDOC_OFFICE_AUTHORITY"] = os.environ.get("WATHEFNI_ANYDOC_OFFICE_AUTHORITY") or "staging"
os.environ.setdefault("WATHEFNI_ANYDOC_OFFICE_SHADOW", "production_shadow")
os.environ.setdefault("WATHEFNI_ANYDOC_OFFICE_SHADOW_TIMEOUT_MS", "5000")

import anydoc_office_authority as auth  # noqa: E402
import anydoc_office_shadow as shadow  # noqa: E402

OUT = Path(os.environ.get("ANYDOC_AUTH_OUT") or ROOT / "ops/evidence/anydoc-office-authority-closure-local")
CORPUS = OUT / "corpus"
CORPUS.mkdir(parents=True, exist_ok=True)


def _docx_minimal(paragraphs: list[str]) -> bytes:
    """Minimal OOXML DOCX (no python-docx required)."""
    body = []
    for p in paragraphs:
        body.append(
            f'<w:p><w:r><w:t xml:space="preserve">{_xml_escape(p)}</w:t></w:r></w:p>'
        )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body>{"".join(body)}<w:sectPr/></w:body></w:document>'
    )
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document)
    return buf.getvalue()


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _pptx_minimal(slides: list[str]) -> bytes:
    """Minimal PPTX with one text shape per slide."""
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
"""
    for i in range(1, len(slides) + 1):
        content_types += (
            f'  <Override PartName="/ppt/slides/slide{i}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>\n'
        )
    content_types += "</Types>"
    rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>"""
    pres_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
"""
    for i in range(1, len(slides) + 1):
        pres_rels += (
            f'  <Relationship Id="rId{i}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
            f'Target="slides/slide{i}.xml"/>\n'
        )
    pres_rels += "</Relationships>"
    sld_ids = "".join(
        f'<p:sldId id="{255 + i}" r:id="rId{i}"/>' for i in range(1, len(slides) + 1)
    )
    presentation = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldIdLst>{sld_ids}</p:sldIdLst>
</p:presentation>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("ppt/presentation.xml", presentation)
        zf.writestr("ppt/_rels/presentation.xml.rels", pres_rels)
        for i, text in enumerate(slides, start=1):
            slide = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree>
    <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
    <p:grpSpPr/>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr/>
      <p:txBody><a:bodyPr/><a:lstStyle/>
        <a:p><a:r><a:t>{_xml_escape(text)}</a:t></a:r></a:p>
      </p:txBody>
    </p:sp>
  </p:spTree></p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>"""
            zf.writestr(f"ppt/slides/slide{i}.xml", slide)
    return buf.getvalue()


def _odt_minimal(text: str) -> bytes:
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
 xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0">
  <office:body><office:text>
    <text:h text:style-name="Heading_20_1" text:outline-level="1">وثيقة رسمية</text:h>
    <text:p>{_xml_escape(text)}</text:p>
    <table:table table:name="T1">
      <table:table-column/><table:table-column/>
      <table:table-row>
        <table:table-cell><text:p>البند</text:p></table:table-cell>
        <table:table-cell><text:p>القيمة</text:p></table:table-cell>
      </table:table-row>
      <table:table-row>
        <table:table-cell><text:p>المرجع</text:p></table:table-cell>
        <table:table-cell><text:p>KW-GOV-2026</text:p></table:table-cell>
      </table:table-row>
    </table:table>
  </office:text></office:body>
</office:document-content>"""
    manifest = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">
  <manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>
  <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
</manifest:manifest>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/vnd.oasis.opendocument.text", compress_type=zipfile.ZIP_STORED)
        zf.writestr("content.xml", content)
        zf.writestr("META-INF/manifest.xml", manifest)
    return buf.getvalue()


def _ods_minimal() -> bytes:
    content = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
  <office:body><office:spreadsheet>
    <table:table table:name="Employees">
      <table:table-row>
        <table:table-cell office:value-type="string"><text:p>الاسم</text:p></table:table-cell>
        <table:table-cell office:value-type="string"><text:p>القسم</text:p></table:table-cell>
        <table:table-cell office:value-type="string"><text:p>الراتب</text:p></table:table-cell>
      </table:table-row>
      <table:table-row>
        <table:table-cell office:value-type="string"><text:p>علي محمد</text:p></table:table-cell>
        <table:table-cell office:value-type="string"><text:p>Operations</text:p></table:table-cell>
        <table:table-cell office:value-type="float" office:value="450"><text:p>450</text:p></table:table-cell>
      </table:table-row>
    </table:table>
  </office:spreadsheet></office:body>
</office:document-content>"""
    manifest = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">
  <manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.spreadsheet"/>
  <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
</manifest:manifest>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet", compress_type=zipfile.ZIP_STORED)
        zf.writestr("content.xml", content)
        zf.writestr("META-INF/manifest.xml", manifest)
    return buf.getvalue()


def build_corpus() -> list[dict]:
    """Create + symlink production-shaped fixtures. Returns catalog entries."""
    catalog: list[dict] = []
    prior = ROOT / "ops/evidence/anydoc-technical-audit-20260804/corpus/generated"

    def add(name: str, data: bytes, kind: str, lang: str) -> Path:
        path = CORPUS / name
        path.write_bytes(data)
        catalog.append({"name": name, "kind": kind, "lang": lang, "sha256": hashlib.sha256(data).hexdigest()})
        return path

    # CVs
    add(
        "cv_en.docx",
        _docx_minimal(
            [
                "Curriculum Vitae",
                "Name: Sara Al-Ali",
                "Role: Senior Software Engineer",
                "Experience: Built HR platforms in Kuwait and GCC markets for five years.",
                "Skills: Python, FastAPI, PostgreSQL, Arabic/English communication.",
            ]
        ),
        "cv",
        "en",
    )
    add(
        "cv_ar_en.docx",
        _docx_minimal(
            [
                "سيرة ذاتية / Curriculum Vitae",
                "الاسم: علي محمد / Name: Ali Mohammad",
                "المسمى: مهندس برمجيات أول / Senior Software Engineer",
                "الخبرة: خمس سنوات في أنظمة الموارد البشرية بالكويت.",
                "Bilingual note: Fluent Arabic and English professional writing.",
            ]
        ),
        "cv",
        "ar_en",
    )
    # Contracts / letters
    add(
        "contract_offer_ar_en.docx",
        _docx_minimal(
            [
                "عرض عمل / Offer Letter",
                "الشركة: وظفني / Company: Wathefni",
                "الموظف: نورة أحمد / Employee: Noura Ahmad",
                "الراتب الأساسي: 800 د.ك / Basic salary: 800 KWD",
                "This letter confirms employment terms under Kuwait Labor Law.",
                "يُرجى التوقيع وإعادة النسخة خلال سبعة أيام عمل.",
            ]
        ),
        "contract_letter",
        "ar_en",
    )
    add(
        "hr_letter_en.docx",
        _docx_minimal(
            [
                "To Whom It May Concern",
                "This confirms that the employee is in good standing.",
                "Employment start date: 2024-01-15. Department: People Operations.",
                "Authorized by Human Resources, Wathefni Kuwait.",
            ]
        ),
        "contract_letter",
        "en",
    )
    # Decks
    add(
        "deck_onboarding_en.pptx",
        _pptx_minimal(
            [
                "Wathefni Onboarding Week 1",
                "Agenda: contracts, civil ID, payroll setup",
                "Action items for HR coordinators",
            ]
        ),
        "deck",
        "en",
    )
    add(
        "deck_ar.pptx",
        _pptx_minimal(
            [
                "عرض التوظيف",
                "النقاط الرئيسية للاستقبال والترتيب",
                "Bilingual hiring checklist / قائمة التحقق",
            ]
        ),
        "deck",
        "ar_en",
    )
    # Employee list + payroll spreadsheets
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Employees"
    ws.append(["employee_id", "name_ar", "name_en", "site", "role", "hours"])
    ws.append(["E001", "علي محمد", "Ali Mohammad", "Kuwait City", "Engineer", 40])
    ws.append(["E002", "سارة أحمد", "Sara Ahmad", "Hawalli", "Ops", 36])
    emp_path = CORPUS / "employee_list_ar_en.xlsx"
    wb.save(emp_path)
    catalog.append(
        {
            "name": emp_path.name,
            "kind": "employee_list",
            "lang": "ar_en",
            "sha256": hashlib.sha256(emp_path.read_bytes()).hexdigest(),
        }
    )

    wb2 = Workbook()
    ws2 = wb2.active
    ws2.title = "Payroll"
    ws2.append(["emp_code", "name", "basic", "allowance", "deduction", "net"])
    ws2.append(["E001", "Ali Mohammad", 500, 100, 25, 575])
    ws2.append(["E002", "Sara Ahmad", 450, 80, 20, 510])
    # Formula-like values preserved as numbers (openpyxl authority)
    pay_path = CORPUS / "payroll_aug2026.xlsx"
    wb2.save(pay_path)
    catalog.append(
        {
            "name": pay_path.name,
            "kind": "payroll",
            "lang": "en",
            "sha256": hashlib.sha256(pay_path.read_bytes()).hexdigest(),
        }
    )

    csv_path = CORPUS / "payroll_aug2026.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["emp_code", "name", "basic", "allowance", "deduction", "net"])
        w.writerow(["E001", "علي محمد", 500, 100, 25, 575])
        w.writerow(["E002", "سارة أحمد", 450, 80, 20, 510])
    catalog.append(
        {
            "name": csv_path.name,
            "kind": "payroll",
            "lang": "ar_en",
            "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        }
    )

    # Government-style ODF
    add(
        "gov_notice_ar.odt",
        _odt_minimal(
            "إشعار رسمي من جهة حكومية بشأن تجديد الإقامة للموظفين غير الكويتيين. "
            "Official notice regarding residency renewal for non-Kuwaiti employees."
        ),
        "gov_odf",
        "ar_en",
    )
    add("gov_roster.ods", _ods_minimal(), "gov_odf", "ar_en")

    # Copy prior bilingual fixtures when present
    for name in ("cv_ar_en.docx", "deck_ar.pptx", "roster_ar.xlsx", "table_ar.csv", "sample_ar.odt", "sample.ods"):
        src = prior / name
        if src.exists() and not (CORPUS / f"prior_{name}").exists():
            data = src.read_bytes()
            (CORPUS / f"prior_{name}").write_bytes(data)
            catalog.append(
                {
                    "name": f"prior_{name}",
                    "kind": "prior_fixture",
                    "lang": "ar_en",
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )

    # Legacy shadow-only samples (should not promote)
    for name in ("memo_ar.rtf", "legacy_stub.doc"):
        src = prior / name
        if src.exists():
            data = src.read_bytes()
            (CORPUS / name).write_bytes(data)
            catalog.append({"name": name, "kind": "legacy_shadow", "lang": "ar" if "ar" in name else "en", "sha256": hashlib.sha256(data).hexdigest()})

    (OUT / "corpus_catalog.json").write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    return catalog


class _Result:
    def __init__(self, text: str, method: str = "existing"):
        self.text = text
        self.method = method
        self.error = None if text else "no_text"
        self.quality_ok = bool(text and len(text) > 20)
        self.blocks = [{"source": "baseline"}]
        self.provenance = []
        self.content_sha256 = None
        self.metadata: dict = {}


def baseline_text(path: Path) -> tuple[str, str]:
    ext = path.suffix.lower()
    if ext == ".docx":
        try:
            import cv_docx

            blocks, _i, _m = cv_docx.parse_docx_local(path)
            return cv_docx.blocks_to_text(blocks), "docx-local"
        except Exception:
            return "", "docx-local"
    if ext == ".csv":
        return path.read_text(encoding="utf-8", errors="ignore"), "text"
    if ext == ".xlsx":
        from openpyxl import load_workbook

        wb = load_workbook(path, read_only=True, data_only=True)
        rows = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                rows.append("\t".join("" if c is None else str(c) for c in row))
        return "\n".join(rows), "openpyxl"
    return "", "existing"


def structured_xlsx_rows(path: Path) -> list[tuple]:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            out.append(tuple(row))
    return out


def structured_csv_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    catalog = build_corpus()
    rows = []
    arabic = {}
    structured_proof = {}

    for entry in catalog:
        path = CORPUS / entry["name"]
        ext = path.suffix.lower()
        base_text, base_method = baseline_text(path)
        result = _Result(base_text, base_method)
        result.content_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()

        # Structured integrity snapshot before
        before_x = structured_xlsx_rows(path) if ext == ".xlsx" else None
        before_c = structured_csv_rows(path) if ext == ".csv" else None

        out = auth.apply_office_authority(result, path, company_code="WATHEFNI")
        decision = (out.metadata or {}).get("anydoc_office_authority") or {}

        after_x = structured_xlsx_rows(path) if ext == ".xlsx" else None
        after_c = structured_csv_rows(path) if ext == ".csv" else None
        if ext in {".xlsx", ".csv"}:
            structured_proof[path.name] = {
                "text_unchanged": out.text == base_text,
                "method_unchanged": out.method == base_method,
                "structured_rows_unchanged": (before_x == after_x) if ext == ".xlsx" else (before_c == after_c),
                "md_attached": bool(decision.get("normalized_markdown_attached")),
                "influences_payroll": decision.get("influences_payroll"),
                "role": decision.get("role"),
            }

        # Determinism for promoted / md paths
        det = None
        if decision.get("output_sha256"):
            out2 = auth.apply_office_authority(
                _Result(base_text, base_method), path, company_code="WATHEFNI"
            )
            d2 = (out2.metadata or {}).get("anydoc_office_authority") or {}
            det = d2.get("output_sha256") == decision.get("output_sha256")

        q = decision.get("quality") or {}
        if int(q.get("arabic_chars") or 0) > 0 or "ar" in path.name.lower():
            arabic[path.name] = {
                "arabic_chars": q.get("arabic_chars"),
                "selected_engine": decision.get("selected_engine"),
                "promoted": decision.get("promoted"),
                "role": decision.get("role"),
                "fallback_reason": decision.get("fallback_reason"),
            }

        row = {
            "name": path.name,
            "kind": entry["kind"],
            "ext": ext,
            "role": decision.get("role") or auth.role_for_extension(ext),
            "selected_engine": decision.get("selected_engine"),
            "promoted": decision.get("promoted"),
            "fallback_reason": decision.get("fallback_reason"),
            "material_disagreement": decision.get("material_disagreement"),
            "comparison_outcome": decision.get("comparison_outcome"),
            "latency_ms": decision.get("latency_ms"),
            "output_sha256": decision.get("output_sha256"),
            "text_chars": len(out.text or ""),
            "method": out.method,
            "blocks_preserved": bool(out.blocks),
            "deterministic": det,
            "decision": {k: decision.get(k) for k in decision if k != "normalized_markdown"},
        }
        rows.append(row)
        status = decision.get("selected_engine") or "n/a"
        print(f"{status:22} {ext:6} promoted={decision.get('promoted')} {path.name}")

    by_ext: dict = {}
    for r in rows:
        b = by_ext.setdefault(
            r["ext"],
            {"n": 0, "promoted": 0, "fallback": 0, "shadow_only": 0, "md_only": 0, "disagree": 0},
        )
        b["n"] += 1
        if r.get("promoted"):
            b["promoted"] += 1
        if r.get("fallback_reason"):
            b["fallback"] += 1
        if r.get("role") == auth.ROLE_SHADOW_ONLY:
            b["shadow_only"] += 1
        if r.get("role") == auth.ROLE_MARKDOWN_ONLY:
            b["md_only"] += 1
        if r.get("material_disagreement"):
            b["disagree"] += 1

    # Gates
    xlsx_ok = all(v["structured_rows_unchanged"] and v["text_unchanged"] for k, v in structured_proof.items() if k.endswith(".xlsx"))
    csv_ok = all(v["structured_rows_unchanged"] and v["text_unchanged"] for k, v in structured_proof.items() if k.endswith(".csv"))
    pdf_denied = auth.apply_office_authority(_Result("x"), CORPUS / "cv_en.docx", document_class="passport", company_code="WATHEFNI")
    # identity on docx
    id_decision = (pdf_denied.metadata or {}).get("anydoc_office_authority") or {}

    with tempfile_pdf() as pdf_path:
        denied = auth.apply_office_authority(_Result("x"), pdf_path, company_code="WATHEFNI")
        pdf_reason = ((denied.metadata or {}).get("anydoc_office_authority") or {}).get("fallback_reason")

    summary = {
        "mode": auth.authority_mode(),
        "files": len(rows),
        "by_extension": by_ext,
        "promoted_total": sum(1 for r in rows if r.get("promoted")),
        "fallback_total": sum(1 for r in rows if r.get("fallback_reason")),
        "material_disagreement_total": sum(1 for r in rows if r.get("material_disagreement")),
        "deterministic_ok": sum(1 for r in rows if r.get("deterministic") is True),
        "deterministic_checked": sum(1 for r in rows if r.get("deterministic") is not None),
        "structured_xlsx_integrity": xlsx_ok,
        "structured_csv_integrity": csv_ok,
        "identity_denied": id_decision.get("fallback_reason") == "identity_document_denied",
        "pdf_denied": pdf_reason == "denied_extension_or_mime",
        "pinned_version": auth.PINNED_VERSION,
        "no_gpt": True,
    }
    (OUT / "authority_qualify_results.json").write_text(
        json.dumps(
            {
                "summary": summary,
                "rows": rows,
                "arabic_evidence": arabic,
                "structured_proof": structured_proof,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    assert summary["structured_xlsx_integrity"], "XLSX structured integrity failed"
    assert summary["structured_csv_integrity"], "CSV structured integrity failed"
    assert summary["identity_denied"]
    assert summary["pdf_denied"]
    assert summary["deterministic_ok"] == summary["deterministic_checked"]
    # Authority candidates should have at least some promotions or md attach for green formats
    docx_rows = [r for r in rows if r["ext"] == ".docx" and r["kind"] != "legacy_shadow"]
    assert any(r.get("promoted") or r.get("selected_engine") == "existing_docx" for r in docx_rows)
    print("ANYDOC_OFFICE_AUTHORITY_QUALIFY_OK")
    return 0


def tempfile_pdf():
    import tempfile
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as t:
            t.write(b"%PDF-1.4\n")
            p = Path(t.name)
        try:
            yield p
        finally:
            p.unlink(missing_ok=True)

    return _cm()


if __name__ == "__main__":
    raise SystemExit(main())
