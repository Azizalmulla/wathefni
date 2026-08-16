"""CV text extraction: local Poppler first, Mistral OCR 4 when needed, GPT rescue last.

Privacy / retention (Mistral):
  Uploaded files may be retained by Mistral for up to ~30 days unless deleted earlier
  (see https://docs.mistral.ai/resources/known-limitations). This adapter prefers
  direct base64 `document_url` / `image_url` processing so no Files API object is
  created. If a temporary Files API upload is required, it is deleted immediately
  after OCR in a finally block. CV body text and PII are never written to general logs.

Pinned OCR model: mistral-ocr-4-0 (never mistral-ocr-latest in production).
SDK pin: mistralai==2.6.0 (see requirements.txt). API: POST /v1/ocr.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import request as urllib_request

logger = logging.getLogger("wathefni.cv_extraction")

# --- Pins / versions ---------------------------------------------------------
MISTRAL_OCR_MODEL = "mistral-ocr-4-0"
MISTRAL_OCR_API_VERSION = "v1"
MISTRAL_SDK_PIN = "mistralai==2.6.0"
PREPROCESSING_VERSION = "cv_ocr_preprocess_v1"
EXTRACTION_OPTIONS_VERSION = "cv_extract_opts_v1"
MISTRAL_OCR_COST_USD_PER_PAGE = 0.004  # $4 / 1,000 pages (standard API)
LEASE_TTL_SECONDS = 180
HUMAN_AUTHORITY = frozenset({"human_verified", "human_corrected"})

_ON = frozenset({"1", "true", "on", "yes", "all", "enabled"})

# Arabic-Indic (U+0660–U+0669) and Extended Arabic-Indic / Persian (U+06F0–U+06F9)
_ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

_AR_MONTHS = {
    "يناير": 1,
    "فبراير": 2,
    "مارس": 3,
    "ابريل": 4,
    "أبريل": 4,
    "مايو": 5,
    "يونيو": 6,
    "يوليو": 7,
    "اغسطس": 8,
    "أغسطس": 8,
    "سبتمبر": 9,
    "اكتوبر": 10,
    "أكتوبر": 10,
    "نوفمبر": 11,
    "ديسمبر": 12,
}
_EN_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_AR_HEADINGS = (
    "المهارات",
    "الخبرات",
    "الخبرة",
    "التعليم",
    "المؤهلات",
    "اللغات",
    "الملخص",
    "نبذة",
    "البيانات الشخصية",
    "معلومات الاتصال",
    "التواصل",
    "الشهادات",
    "المشاريع",
)
_EN_HEADINGS = (
    "skills",
    "experience",
    "education",
    "languages",
    "summary",
    "profile",
    "contact",
    "certifications",
    "projects",
    "work history",
    "professional summary",
    "key skills",
    "technical skills",
)

_EMAIL_RE = re.compile(
    r"(?<![\w./-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24})(?![\w.-])"
)
# Allow emails split by RTL marks / zero-width chars.
_EMAIL_RTL_CLEAN = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\u061c]")
_URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>\]\)\"']+",
    re.IGNORECASE,
)
_KW_PHONE_RE = re.compile(
    r"(?:\+?965[\s\-]*)?(?:0?5|0?6|0?9)[\s\-]*\d(?:[\s\-]?\d){6}\b"
)


@dataclass
class FieldProvenance:
    field: str
    value: Any
    document_id: str | None = None
    page: int | None = None
    block_id: str | None = None
    source_text: str | None = None
    engine: str | None = None
    model: str | None = None
    confidence: float | None = None
    authority_status: str = "machine_extracted"
    coordinates: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class PageAssessment:
    page_number: int  # 1-based for humans / provenance
    page_index: int  # 0-based for Mistral `pages`
    local_text: str
    page_hash: str
    disposition: str  # accepted_local | needs_ocr | empty
    reason: str
    char_count: int = 0
    word_count: int = 0
    arabic_ratio: float = 0.0


@dataclass
class EngineCallMeta:
    stage: str
    tier: str
    provider: str
    actual_request_model: str
    provider_response_model: str | None = None
    provider_request_id: str | None = None
    latency_ms: int | None = None
    billable_pages: int | None = None
    estimated_cost_usd: float | None = None
    pages: list[int] = field(default_factory=list)
    cache_hit: bool = False
    quality_ok: bool | None = None
    error: str | None = None
    retention: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractionResult:
    text: str
    method: str
    error: str | None = None
    quality_ok: bool = False
    page_assessments: list[PageAssessment] = field(default_factory=list)
    engine_calls: list[EngineCallMeta] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    content_sha256: str | None = None
    cache_key: str | None = None
    cache_hit: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def legacy_tuple(self) -> tuple[str, str, str | None]:
        return self.text, self.method, self.error

    def to_dict(self) -> dict[str, Any]:
        return {
            "text_chars": len(self.text or ""),
            "method": self.method,
            "error": self.error,
            "quality_ok": self.quality_ok,
            "page_assessments": [asdict(p) for p in self.page_assessments],
            "engine_calls": [c.to_dict() for c in self.engine_calls],
            "blocks": self.blocks,
            "provenance": self.provenance,
            "content_sha256": self.content_sha256,
            "cache_key": self.cache_key,
            "cache_hit": self.cache_hit,
            "metadata": self.metadata,
            # Never include full CV text in structured metadata dumps by default.
        }


def env_flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in _ON


def mistral_ocr_enabled() -> bool:
    """Master switch. Default OFF — no production CVs to Mistral until owner approval."""
    return env_flag("WATHEFNI_CV_MISTRAL_OCR", default=False)


def gpt_vision_rescue_enabled() -> bool:
    """Bounded GPT-5.4 vision rescue after Mistral OCR quality failure. Default ON when OCR on.

    CV Extraction V2 uses Mistral Document AI as the main path — GPT Vision is
    disabled in normal V2 processing unless explicitly forced on.
    """
    if not mistral_ocr_enabled():
        return False
    # V2 normal path: no GPT Vision unless forced.
    if env_flag("WATHEFNI_CV_EXTRACTION_V2", default=True):
        forced = (os.environ.get("WATHEFNI_CV_GPT_VISION_RESCUE") or "").strip().lower()
        return forced in {"force", "force_on", "1_force"}
    raw = (os.environ.get("WATHEFNI_CV_GPT_VISION_RESCUE") or "").strip().lower()
    if not raw:
        return True
    return raw in _ON


def normalize_digits(text: str) -> str:
    return str(text or "").translate(_ARABIC_INDIC_DIGITS)


def strip_bidi_marks(text: str) -> str:
    return _EMAIL_RTL_CLEAN.sub("", str(text or ""))


def normalize_cv_text_for_contacts(text: str) -> str:
    """Deterministic prep for contact/date extraction. Does not trigger OCR."""
    return normalize_digits(strip_bidi_marks(text))


def extract_emails(text: str) -> list[dict[str, Any]]:
    cleaned = normalize_cv_text_for_contacts(text)
    out: list[dict[str, Any]] = []
    for match in _EMAIL_RE.finditer(cleaned):
        email = match.group(1).strip().lower()
        out.append(
            {
                "value": email,
                "source_text": match.group(0),
                "span": [match.start(1), match.end(1)],
            }
        )
    return out


def extract_urls(text: str) -> list[dict[str, Any]]:
    cleaned = normalize_cv_text_for_contacts(text)
    out: list[dict[str, Any]] = []
    for match in _URL_RE.finditer(cleaned):
        url = match.group(0).rstrip(".,;:)")
        out.append({"value": url, "source_text": match.group(0), "span": [match.start(), match.end()]})
    return out


def extract_kuwait_phones(text: str) -> list[dict[str, Any]]:
    cleaned = normalize_cv_text_for_contacts(text)
    out: list[dict[str, Any]] = []
    for match in _KW_PHONE_RE.finditer(cleaned):
        digits = re.sub(r"\D", "", match.group(0))
        if digits.startswith("965") and len(digits) >= 11:
            local = digits[-8:]
            e164 = f"965{local}"
        elif len(digits) == 8 and digits[0] in "569":
            local = digits
            e164 = f"965{local}"
        elif len(digits) == 9 and digits[0] == "0" and digits[1] in "569":
            local = digits[1:]
            e164 = f"965{local}"
        else:
            continue
        out.append(
            {
                "value": e164,
                "local": local,
                "source_text": match.group(0),
                "span": [match.start(), match.end()],
            }
        )
    return out


def detect_headings(text: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for line in str(text or "").splitlines():
        raw = line.strip()
        if not raw:
            continue
        lower = raw.lower()
        for heading in _EN_HEADINGS:
            if lower == heading or lower.startswith(heading + ":") or lower.startswith(heading + " -"):
                found.append({"heading": heading, "lang": "en", "source_text": raw})
                break
        else:
            for heading in _AR_HEADINGS:
                if raw == heading or raw.startswith(heading + ":") or raw.startswith(heading + " -") or raw.startswith(heading + "–"):
                    found.append({"heading": heading, "lang": "ar", "source_text": raw})
                    break
    return found


def parse_bilingual_dates(text: str) -> list[dict[str, Any]]:
    cleaned = normalize_cv_text_for_contacts(text)
    results: list[dict[str, Any]] = []
    # 15 يناير 2020 / January 15, 2020 / 15/01/2020
    patterns = [
        re.compile(r"(\d{1,2})\s+([A-Za-z\u0600-\u06FF]+)\s+(\d{4})"),
        re.compile(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})"),
        re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})"),
    ]
    for pat in patterns:
        for match in pat.finditer(cleaned):
            groups = match.groups()
            month = None
            day = None
            year = None
            if pat.pattern.startswith(r"(\d{1,2})\s+"):
                day = int(groups[0])
                month_token = groups[1].lower()
                month = _EN_MONTHS.get(month_token) or _AR_MONTHS.get(groups[1]) or _AR_MONTHS.get(month_token)
                year = int(groups[2])
            elif pat.pattern.startswith(r"([A-Za-z]+)"):
                month = _EN_MONTHS.get(groups[0].lower())
                day = int(groups[1])
                year = int(groups[2])
            else:
                day = int(groups[0])
                month = int(groups[1])
                year = int(groups[2])
            if month and 1 <= month <= 12 and 1 <= day <= 31 and 1950 <= year <= 2100:
                results.append(
                    {
                        "iso": f"{year:04d}-{month:02d}-{day:02d}",
                        "source_text": match.group(0),
                        "span": [match.start(), match.end()],
                    }
                )
    return results


def arabic_ratio(text: str) -> float:
    arabic = sum(1 for ch in text if "\u0600" <= ch <= "\u06FF")
    alpha = sum(1 for ch in text if ch.isalpha())
    if alpha == 0:
        return 0.0
    return arabic / alpha


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z\u0600-\u06FF][A-Za-z\u0600-\u06FF0-9+#.'\-]{1,}", text or ""))


def cv_text_quality_ok(text: str | None, *, min_chars: int = 80, min_words: int = 12) -> bool:
    raw = str(text or "").strip()
    if len(raw) < min_chars:
        return False
    words = word_count(raw)
    if words < min_words:
        return False
    alpha_chars = sum(1 for ch in raw if ch.isalpha())
    printable_chars = sum(1 for ch in raw if ch.isprintable() and not ch.isspace())
    if printable_chars and alpha_chars / max(printable_chars, 1) < 0.35:
        return False
    metadata_markers = sum(
        raw.lower().count(marker) for marker in ("reportlab", "anonymous", "unspecified", "obj", "endobj", "xref")
    )
    if metadata_markers >= 3 and words < 40:
        return False
    # Garbage / mojibake density
    replacement = raw.count("\ufffd") + raw.count("�")
    if replacement >= 8 and words < 40:
        return False
    return True


def page_text_usable(text: str | None) -> tuple[bool, str]:
    raw = str(text or "").strip()
    if not raw:
        return False, "empty"
    if len(raw) < 40:
        return False, "too_short"
    if word_count(raw) < 6:
        return False, "too_few_words"
    if not cv_text_quality_ok(raw, min_chars=40, min_words=6):
        return False, "quality_gate_failed"
    # Arabic alone is NOT a failure — only unusable extraction is.
    return True, "accepted_local"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_cache_key(
    *,
    content_sha256: str,
    page_hashes: list[str],
    preprocessing_version: str = PREPROCESSING_VERSION,
    provider: str,
    ocr_model: str,
    api_version: str,
    extraction_options: dict[str, Any],
) -> str:
    payload = {
        "content_sha256": content_sha256,
        "page_hashes": page_hashes,
        "preprocessing_version": preprocessing_version,
        "provider": provider,
        "ocr_model": ocr_model,
        "api_version": api_version,
        "extraction_options": extraction_options,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256_text(canonical)


def default_extraction_options() -> dict[str, Any]:
    return {
        "version": EXTRACTION_OPTIONS_VERSION,
        "include_blocks": True,
        "table_format": "markdown",
        "confidence_scores_granularity": "page",
        "prefer_base64_direct": True,
        "delete_uploaded_files": True,
    }


def mistral_api_key() -> str | None:
    direct = (os.environ.get("MISTRAL_API_KEY") or os.environ.get("WATHEFNI_MISTRAL_API_KEY") or "").strip()
    if direct:
        return direct
    env_path = (os.environ.get("WATHEFNI_MISTRAL_ENV") or "").strip()
    if not env_path:
        env_path = "/root/.openclaw/secrets/mistral.env"
    path = Path(env_path)
    if not path.is_file():
        return None
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() in {"MISTRAL_API_KEY", "WATHEFNI_MISTRAL_API_KEY"}:
                return value.strip().strip('"').strip("'")
    except Exception:
        return None
    return None


def pdf_page_count(path: Path) -> int | None:
    pdfinfo = shutil.which("pdfinfo")
    if not pdfinfo:
        return None
    try:
        proc = subprocess.run([pdfinfo, str(path)], capture_output=True, text=True, timeout=20)
        if proc.returncode != 0:
            return None
        for line in proc.stdout.splitlines():
            if line.lower().startswith("pages:"):
                return int(line.split(":", 1)[1].strip())
    except Exception:
        return None
    return None


def pdf_page_has_images(path: Path, page_number: int) -> bool | None:
    """Return True/False/None when pdfimages is unavailable."""
    pdfimages = shutil.which("pdfimages")
    if not pdfimages:
        return None
    try:
        proc = subprocess.run(
            [pdfimages, "-f", str(page_number), "-l", str(page_number), "-list", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if proc.returncode != 0:
            return None
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip() and not ln.lower().startswith("page")]
        # Header + rows; any data row means images present.
        data_rows = [ln for ln in lines if re.match(r"^\s*\d+", ln)]
        return bool(data_rows)
    except Exception:
        return None


def extract_pdf_page_text(path: Path, page_number: int) -> str:
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        return ""
    try:
        proc = subprocess.run(
            [pdftotext, "-f", str(page_number), "-l", str(page_number), "-layout", str(path), "-"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            return (proc.stdout or "").strip()
    except Exception:
        return ""
    return ""


def extract_pdf_full_text_layout(path: Path) -> tuple[str, str | None]:
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        return "", "pdftotext_missing"
    try:
        proc = subprocess.run(
            [pdftotext, "-layout", str(path), "-"],
            capture_output=True,
            text=True,
            timeout=45,
        )
        if proc.returncode == 0:
            return (proc.stdout or "").strip(), None
        return "", f"pdftotext_rc_{proc.returncode}"
    except Exception as exc:
        return "", str(exc)


def assess_pdf_pages(path: Path) -> list[PageAssessment]:
    count = pdf_page_count(path) or 1
    assessments: list[PageAssessment] = []
    for page_number in range(1, count + 1):
        local = extract_pdf_page_text(path, page_number)
        usable, reason = page_text_usable(local)
        has_images = pdf_page_has_images(path, page_number)
        disposition = "accepted_local"
        if not usable:
            if not local and has_images is True:
                reason = "image_only_page"
            elif not local:
                reason = "scanned_or_empty"
            elif reason == "quality_gate_failed":
                reason = "corrupt_or_unusable_text"
            disposition = "needs_ocr"
        elif has_images is True and word_count(local) < 10:
            disposition = "needs_ocr"
            reason = "image_dominant_sparse_text"
        assessments.append(
            PageAssessment(
                page_number=page_number,
                page_index=page_number - 1,
                local_text=local,
                page_hash=sha256_text(local or f"empty:{page_number}"),
                disposition=disposition,
                reason=reason,
                char_count=len(local),
                word_count=word_count(local),
                arabic_ratio=arabic_ratio(local),
            )
        )
    return assessments


def render_pdf_pages_to_png(path: Path, page_numbers: list[int], dest_dir: Path) -> dict[int, Path]:
    """Render specific 1-based pages to PNG via pdftoppm. Returns {page_number: path}."""
    pdftoppm = shutil.which("pdftoppm")
    out: dict[int, Path] = {}
    if not pdftoppm or not page_numbers:
        return out
    dest_dir.mkdir(parents=True, exist_ok=True)
    for page_number in page_numbers:
        prefix = dest_dir / f"page-{page_number}"
        try:
            proc = subprocess.run(
                [
                    pdftoppm,
                    "-png",
                    "-r",
                    "200",
                    "-f",
                    str(page_number),
                    "-l",
                    str(page_number),
                    str(path),
                    str(prefix),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if proc.returncode != 0:
                continue
            candidate = Path(f"{prefix}-{page_number}.png")
            if not candidate.exists():
                # Some poppler builds omit the page suffix when -f==-l
                matches = sorted(dest_dir.glob(f"page-{page_number}*.png"))
                if matches:
                    candidate = matches[0]
            if candidate.exists():
                out[page_number] = candidate
        except Exception:
            continue
    return out


def ocr_quality_ok(text: str | None, *, pages: int = 1) -> tuple[bool, str]:
    raw = str(text or "").strip()
    min_chars = max(40, 60 * max(pages, 1) // 2)
    min_words = max(6, 8 * max(pages, 1) // 2)
    if not cv_text_quality_ok(raw, min_chars=min_chars, min_words=min_words):
        return False, "ocr_quality_gate_failed"
    # Extremely low average confidence handled by caller via metadata.
    return True, "accepted_ocr"


def estimate_mistral_cost(billable_pages: int) -> float:
    return round(max(0, billable_pages) * MISTRAL_OCR_COST_USD_PER_PAGE, 6)


def _response_header(headers: Any, name: str) -> str | None:
    try:
        value = headers.get(name) if headers is not None else None
        if value:
            return str(value)
    except Exception:
        pass
    return None


def mistral_ocr_process(
    *,
    document_payload: dict[str, Any],
    pages: list[int] | None = None,
    include_blocks: bool = True,
) -> tuple[dict[str, Any], EngineCallMeta]:
    """Call Mistral OCR with pinned model mistral-ocr-4-0 via HTTP /v1/ocr.

    Prefer base64 document/image URLs (no Files API retention). Captures request
    model, response model, request id, latency, billable pages, estimated cost.
    """
    api_key = mistral_api_key()
    if not api_key:
        meta = EngineCallMeta(
            stage="ocr",
            tier="mistral_ocr",
            provider="mistral",
            actual_request_model=MISTRAL_OCR_MODEL,
            error="missing_mistral_api_key",
            retention="none_sent",
        )
        return {}, meta

    body: dict[str, Any] = {
        "model": MISTRAL_OCR_MODEL,
        "document": document_payload,
        "include_image_base64": False,
        "include_blocks": include_blocks,
        "table_format": "markdown",
        "confidence_scores_granularity": "page",
    }
    if pages is not None:
        body["pages"] = pages

    started = time.perf_counter()
    req = urllib_request.Request(
        "https://api.mistral.ai/v1/ocr",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            request_id = (
                _response_header(resp.headers, "x-request-id")
                or _response_header(resp.headers, "x-mistral-request-id")
                or _response_header(resp.headers, "request-id")
            )
            parsed = json.loads(raw) if raw else {}
    except urllib_error.HTTPError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            detail = str(exc)
        # Never log document content — only status + truncated error class.
        logger.warning("mistral_ocr_http_error status=%s", getattr(exc, "code", "?"))
        meta = EngineCallMeta(
            stage="ocr",
            tier="mistral_ocr",
            provider="mistral",
            actual_request_model=MISTRAL_OCR_MODEL,
            latency_ms=latency_ms,
            pages=list(pages or []),
            error=f"http_{getattr(exc, 'code', 'error')}:{detail[:200]}",
            retention="base64_direct_no_files_api",
        )
        return {}, meta
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.warning("mistral_ocr_request_failed class=%s", type(exc).__name__)
        meta = EngineCallMeta(
            stage="ocr",
            tier="mistral_ocr",
            provider="mistral",
            actual_request_model=MISTRAL_OCR_MODEL,
            latency_ms=latency_ms,
            pages=list(pages or []),
            error=f"{type(exc).__name__}",
            retention="base64_direct_no_files_api",
        )
        return {}, meta

    latency_ms = int((time.perf_counter() - started) * 1000)
    pages_processed = 0
    if isinstance(parsed, dict):
        usage = parsed.get("usage_info") if isinstance(parsed.get("usage_info"), dict) else {}
        pages_processed = int(usage.get("pages_processed") or len(parsed.get("pages") or []) or 0)
        response_model = str(parsed.get("model") or MISTRAL_OCR_MODEL)
    else:
        response_model = MISTRAL_OCR_MODEL
        parsed = {}

    meta = EngineCallMeta(
        stage="ocr",
        tier="mistral_ocr",
        provider="mistral",
        actual_request_model=MISTRAL_OCR_MODEL,
        provider_response_model=response_model,
        provider_request_id=request_id,
        latency_ms=latency_ms,
        billable_pages=pages_processed,
        estimated_cost_usd=estimate_mistral_cost(pages_processed),
        pages=list(pages or []),
        retention="base64_direct_no_files_api",
    )
    return parsed if isinstance(parsed, dict) else {}, meta


def mistral_delete_file(file_id: str) -> bool:
    """Best-effort immediate deletion of a temporary Files API upload."""
    api_key = mistral_api_key()
    if not api_key or not file_id:
        return False
    req = urllib_request.Request(
        f"https://api.mistral.ai/v1/files/{file_id}",
        headers={"Authorization": f"Bearer {api_key}"},
        method="DELETE",
    )
    try:
        with urllib_request.urlopen(req, timeout=30) as resp:
            resp.read()
        return True
    except Exception:
        logger.warning("mistral_file_delete_failed file_id_suffix=%s", file_id[-8:])
        return False


def parse_mistral_ocr_pages(response: dict[str, Any]) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (joined_markdown, blocks, page_summaries)."""
    pages = response.get("pages") if isinstance(response, dict) else None
    if not isinstance(pages, list):
        return "", [], []
    texts: list[str] = []
    blocks: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        index = int(page.get("index") or 0)
        markdown = str(page.get("markdown") or "").strip()
        texts.append(markdown)
        conf = page.get("confidence_scores") if isinstance(page.get("confidence_scores"), dict) else {}
        summaries.append(
            {
                "page_index": index,
                "page_number": index + 1,
                "chars": len(markdown),
                "average_confidence": conf.get("average_page_confidence_score"),
                "minimum_confidence": conf.get("minimum_page_confidence_score"),
            }
        )
        for i, block in enumerate(page.get("blocks") or []):
            if not isinstance(block, dict):
                continue
            bbox = block.get("bbox") or block.get("bounding_box") or block.get("boundingBox")
            blocks.append(
                {
                    "block_id": str(block.get("id") or f"p{index}-b{i}"),
                    "page_index": index,
                    "page_number": index + 1,
                    "type": block.get("type") or block.get("label"),
                    "content": block.get("content") or block.get("text") or block.get("markdown"),
                    "bbox": bbox,
                    "confidence": block.get("confidence"),
                    "engine": "mistral",
                    "model": str(response.get("model") or MISTRAL_OCR_MODEL),
                }
            )
    return "\n\n".join(t for t in texts if t).strip(), blocks, summaries


def merge_page_texts(assessments: list[PageAssessment], ocr_by_page_number: dict[int, str]) -> str:
    parts: list[str] = []
    for page in assessments:
        if page.disposition == "accepted_local" and page.local_text.strip():
            parts.append(page.local_text.strip())
        elif page.page_number in ocr_by_page_number and ocr_by_page_number[page.page_number].strip():
            parts.append(ocr_by_page_number[page.page_number].strip())
        elif page.local_text.strip():
            parts.append(page.local_text.strip())
    return "\n\n".join(parts).strip()


def preserve_human_fields(
    existing_profile: dict[str, Any] | None,
    incoming: dict[str, Any],
    *,
    provenance_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Never overwrite human-verified / human-corrected fields."""
    existing = existing_profile if isinstance(existing_profile, dict) else {}
    existing_prov = existing.get("field_provenance") if isinstance(existing.get("field_provenance"), dict) else {}
    incoming_prov = provenance_map or {}
    merged = dict(incoming)
    for field_name, prov in existing_prov.items():
        if not isinstance(prov, dict):
            continue
        if str(prov.get("authority_status") or "") in HUMAN_AUTHORITY:
            if field_name in existing:
                merged[field_name] = existing[field_name]
            incoming_prov[field_name] = prov
    # Also honor top-level markers
    for field_name in list(merged.keys()):
        marker = existing.get(f"{field_name}__authority")
        if str(marker or "") in HUMAN_AUTHORITY and field_name in existing:
            merged[field_name] = existing[field_name]
    merged["field_provenance"] = {**incoming_prov, **{k: v for k, v in existing_prov.items() if str((v or {}).get("authority_status") or "") in HUMAN_AUTHORITY}}
    return merged


def deterministic_contact_profile(text: str, *, document_id: str | None = None, engine: str = "deterministic") -> dict[str, Any]:
    emails = extract_emails(text)
    phones = extract_kuwait_phones(text)
    urls = extract_urls(text)
    headings = detect_headings(text)
    dates = parse_bilingual_dates(text)
    provenance: dict[str, dict[str, Any]] = {}
    profile: dict[str, Any] = {
        "email": emails[0]["value"] if emails else None,
        "phone": phones[0]["value"] if phones else None,
        "urls": [u["value"] for u in urls[:10]],
        "headings": headings[:30],
        "dates": [d["iso"] for d in dates[:20]],
        "parser": "deterministic_contacts_v1",
    }
    if emails:
        provenance["email"] = FieldProvenance(
            field="email",
            value=emails[0]["value"],
            document_id=document_id,
            source_text=emails[0]["source_text"],
            engine=engine,
            model=None,
            confidence=1.0,
            authority_status="machine_extracted",
        ).to_dict()
    if phones:
        provenance["phone"] = FieldProvenance(
            field="phone",
            value=phones[0]["value"],
            document_id=document_id,
            source_text=phones[0]["source_text"],
            engine=engine,
            model=None,
            confidence=1.0,
            authority_status="machine_extracted",
        ).to_dict()
    profile["field_provenance"] = provenance
    return profile


# --- DB helpers (injected by app) --------------------------------------------

DbExecute = Callable[..., Any]


def ensure_cv_extraction_schema(execute: DbExecute) -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS cv_extraction_cache (
          cache_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          cache_key text NOT NULL,
          content_sha256 text NOT NULL,
          page_hashes jsonb NOT NULL DEFAULT '[]'::jsonb,
          preprocessing_version text NOT NULL,
          provider text NOT NULL,
          ocr_model text NOT NULL,
          api_version text NOT NULL,
          extraction_options jsonb NOT NULL DEFAULT '{}'::jsonb,
          result jsonb NOT NULL DEFAULT '{}'::jsonb,
          billable_pages integer,
          estimated_cost_usd numeric,
          latency_ms integer,
          provider_request_id text,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, cache_key)
        );
        CREATE INDEX IF NOT EXISTS idx_cv_extraction_cache_company_sha
          ON cv_extraction_cache(company_code, content_sha256);

        CREATE TABLE IF NOT EXISTS cv_extraction_leases (
          lease_key text PRIMARY KEY,
          company_code text NOT NULL,
          document_id text NOT NULL,
          stage text NOT NULL,
          owner text NOT NULL,
          expires_at timestamptz NOT NULL,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_cv_extraction_leases_expires
          ON cv_extraction_leases(expires_at);

        CREATE TABLE IF NOT EXISTS cv_extraction_runs (
          run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          document_id text,
          app_key text,
          content_sha256 text,
          stage text NOT NULL,
          tier text,
          provider text,
          actual_request_model text,
          provider_response_model text,
          pages_requested integer[],
          pages_processed integer,
          billable_pages integer,
          estimated_cost_usd numeric,
          latency_ms integer,
          provider_request_id text,
          quality_ok boolean,
          cache_hit boolean NOT NULL DEFAULT false,
          error text,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_cv_extraction_runs_company_created
          ON cv_extraction_runs(company_code, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cv_extraction_runs_document
          ON cv_extraction_runs(document_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS cv_extraction_finalizations (
          finalization_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          document_id text NOT NULL,
          app_key text NOT NULL,
          source_content_sha256 text NOT NULL,
          extracted_text_hash text NOT NULL,
          extraction_method text,
          quality_ok boolean NOT NULL DEFAULT false,
          status text NOT NULL,
          error text,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          finalized_at timestamptz NOT NULL DEFAULT now(),
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (
            company_code, app_key, document_id, source_content_sha256,
            extracted_text_hash
          )
        );
        CREATE INDEX IF NOT EXISTS idx_cv_extraction_finalizations_app
          ON cv_extraction_finalizations(company_code, app_key, finalized_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cv_extraction_finalizations_document
          ON cv_extraction_finalizations(company_code, document_id, finalized_at DESC);
        """
    )


def acquire_extraction_lease(
    execute: DbExecute,
    *,
    company_code: str,
    document_id: str,
    stage: str,
    owner: str,
    ttl_seconds: int = LEASE_TTL_SECONDS,
) -> dict[str, Any]:
    """Single-flight lease. Returns {acquired: bool, ...}."""
    lease_key = f"cv:{company_code}:{document_id}:{stage}"
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=max(30, ttl_seconds))
    execute(
        """
        DELETE FROM cv_extraction_leases
        WHERE lease_key=%s AND expires_at < now()
        """,
        (lease_key,),
    )
    execute(
        """
        INSERT INTO cv_extraction_leases (lease_key, company_code, document_id, stage, owner, expires_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,now())
        ON CONFLICT (lease_key) DO NOTHING
        """,
        (lease_key, company_code, document_id, stage, owner, expires),
    )
    row = execute(
        """
        SELECT lease_key, owner, expires_at
        FROM cv_extraction_leases
        WHERE lease_key=%s
        """,
        (lease_key,),
        fetchone=True,
    )
    if not row:
        return {"acquired": False, "reason": "lease_missing", "lease_key": lease_key}
    if str(row.get("owner") or "") != owner and row.get("expires_at") and row["expires_at"] > now:
        return {
            "acquired": False,
            "reason": "held_by_other",
            "lease_key": lease_key,
            "owner": row.get("owner"),
            "expires_at": row.get("expires_at").isoformat() if hasattr(row.get("expires_at"), "isoformat") else str(row.get("expires_at")),
        }
    if str(row.get("owner") or "") != owner:
        execute(
            """
            UPDATE cv_extraction_leases
            SET owner=%s, expires_at=%s, updated_at=now()
            WHERE lease_key=%s AND expires_at < now()
            """,
            (owner, expires, lease_key),
        )
        row = execute(
            "SELECT owner FROM cv_extraction_leases WHERE lease_key=%s",
            (lease_key,),
            fetchone=True,
        )
        if not row or str(row.get("owner") or "") != owner:
            return {"acquired": False, "reason": "race_lost", "lease_key": lease_key}
    else:
        execute(
            "UPDATE cv_extraction_leases SET expires_at=%s, updated_at=now() WHERE lease_key=%s AND owner=%s",
            (expires, lease_key, owner),
        )
    return {"acquired": True, "lease_key": lease_key, "owner": owner, "expires_at": expires.isoformat()}


def release_extraction_lease(execute: DbExecute, *, lease_key: str, owner: str) -> None:
    execute(
        "DELETE FROM cv_extraction_leases WHERE lease_key=%s AND owner=%s",
        (lease_key, owner),
    )


def lookup_extraction_cache(execute: DbExecute, *, company_code: str, cache_key: str) -> dict[str, Any] | None:
    row = execute(
        """
        SELECT result, billable_pages, estimated_cost_usd, latency_ms, provider_request_id, ocr_model, provider
        FROM cv_extraction_cache
        WHERE company_code=%s AND cache_key=%s
        """,
        (company_code, cache_key),
        fetchone=True,
    )
    return dict(row) if row else None


def store_extraction_cache(
    execute: DbExecute,
    *,
    company_code: str,
    cache_key: str,
    content_sha256: str,
    page_hashes: list[str],
    provider: str,
    ocr_model: str,
    api_version: str,
    extraction_options: dict[str, Any],
    result: dict[str, Any],
    billable_pages: int | None,
    estimated_cost_usd: float | None,
    latency_ms: int | None,
    provider_request_id: str | None,
) -> None:
    execute(
        """
        INSERT INTO cv_extraction_cache
          (company_code, cache_key, content_sha256, page_hashes, preprocessing_version,
           provider, ocr_model, api_version, extraction_options, result,
           billable_pages, estimated_cost_usd, latency_ms, provider_request_id)
        VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s)
        ON CONFLICT (company_code, cache_key) DO UPDATE SET
          result=EXCLUDED.result,
          billable_pages=EXCLUDED.billable_pages,
          estimated_cost_usd=EXCLUDED.estimated_cost_usd,
          latency_ms=EXCLUDED.latency_ms,
          provider_request_id=EXCLUDED.provider_request_id
        """,
        (
            company_code,
            cache_key,
            content_sha256,
            json.dumps(page_hashes),
            PREPROCESSING_VERSION,
            provider,
            ocr_model,
            api_version,
            json.dumps(extraction_options),
            json.dumps(result),
            billable_pages,
            estimated_cost_usd,
            latency_ms,
            provider_request_id,
        ),
    )


def record_extraction_run(execute: DbExecute, **fields: Any) -> None:
    execute(
        """
        INSERT INTO cv_extraction_runs
          (company_code, document_id, app_key, content_sha256, stage, tier, provider,
           actual_request_model, provider_response_model, pages_requested, pages_processed,
           billable_pages, estimated_cost_usd, latency_ms, provider_request_id,
           quality_ok, cache_hit, error, metadata)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            fields.get("company_code"),
            fields.get("document_id"),
            fields.get("app_key"),
            fields.get("content_sha256"),
            fields.get("stage"),
            fields.get("tier"),
            fields.get("provider"),
            fields.get("actual_request_model"),
            fields.get("provider_response_model"),
            fields.get("pages_requested"),
            fields.get("pages_processed"),
            fields.get("billable_pages"),
            fields.get("estimated_cost_usd"),
            fields.get("latency_ms"),
            fields.get("provider_request_id"),
            fields.get("quality_ok"),
            bool(fields.get("cache_hit")),
            fields.get("error"),
            json.dumps(fields.get("metadata") or {}),
        ),
    )


def record_extraction_finalization(
    execute: DbExecute,
    *,
    company_code: str,
    document_id: str,
    app_key: str,
    source_content_sha256: str,
    extracted_text: str,
    extraction_method: str | None,
    quality_ok: bool,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record the final accepted output, separate from engine-stage audit rows."""
    company = str(company_code or "").strip().upper()
    document = str(document_id or "").strip()
    application = str(app_key or "").strip()
    source_hash = str(source_content_sha256 or "").strip().lower()
    text_hash = hashlib.sha256(str(extracted_text or "").encode("utf-8")).hexdigest()
    if not all((company, document, application, source_hash)):
        raise ValueError("cv_extraction_finalization_fields_required")
    status = "completed" if quality_ok and extracted_text else "failed"
    row = execute(
        """
        INSERT INTO cv_extraction_finalizations(
          company_code, document_id, app_key, source_content_sha256,
          extracted_text_hash, extraction_method, quality_ok, status, error,
          metadata, finalized_at, created_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,now(),now())
        ON CONFLICT (
          company_code, app_key, document_id, source_content_sha256,
          extracted_text_hash
        ) DO UPDATE SET
          extraction_method=EXCLUDED.extraction_method,
          quality_ok=EXCLUDED.quality_ok,
          status=EXCLUDED.status,
          error=EXCLUDED.error,
          metadata=EXCLUDED.metadata,
          finalized_at=now()
        RETURNING finalization_id, status, quality_ok, extracted_text_hash
        """,
        (
            company,
            document,
            application,
            source_hash,
            text_hash,
            extraction_method,
            bool(quality_ok),
            status,
            error,
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
        fetchone=True,
    )
    return dict(row or {})


def extract_image_with_mistral(path: Path, mime_type: str) -> tuple[str, list[dict[str, Any]], EngineCallMeta]:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    data_uri = f"data:{mime_type};base64,{encoded}"
    response, meta = mistral_ocr_process(
        document_payload={"type": "image_url", "image_url": data_uri},
        pages=None,
        include_blocks=True,
    )
    text, blocks, _summaries = parse_mistral_ocr_pages(response)
    ok, reason = ocr_quality_ok(text, pages=1)
    meta.quality_ok = ok
    if not ok and not meta.error:
        meta.error = reason
    return text, blocks, meta


def extract_pdf_pages_with_mistral(path: Path, page_indexes: list[int]) -> tuple[dict[int, str], list[dict[str, Any]], EngineCallMeta]:
    """OCR specific 0-based page indexes from a PDF via base64 document_url + pages filter."""
    if not page_indexes:
        meta = EngineCallMeta(
            stage="ocr",
            tier="mistral_ocr",
            provider="mistral",
            actual_request_model=MISTRAL_OCR_MODEL,
            error="no_pages_requested",
            retention="none_sent",
        )
        return {}, [], meta
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    data_uri = f"data:application/pdf;base64,{encoded}"
    response, meta = mistral_ocr_process(
        document_payload={"type": "document_url", "document_url": data_uri},
        pages=page_indexes,
        include_blocks=True,
    )
    text, blocks, summaries = parse_mistral_ocr_pages(response)
    by_page: dict[int, str] = {}
    # When pages filter is used, response pages still carry their original indexes.
    pages = response.get("pages") if isinstance(response, dict) else None
    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, dict):
                continue
            idx = int(page.get("index") or 0)
            by_page[idx + 1] = str(page.get("markdown") or "").strip()
    elif text:
        # Fallback: single blob — assign to first requested page only.
        by_page[page_indexes[0] + 1] = text
    joined = "\n\n".join(by_page[p] for p in sorted(by_page) if by_page[p])
    ok, reason = ocr_quality_ok(joined, pages=len(page_indexes))
    meta.quality_ok = ok
    if not ok and not meta.error:
        meta.error = reason
    _ = summaries  # available for callers via blocks / response pages
    return by_page, blocks, meta


VisionRescueFn = Callable[[Path, str], tuple[str, EngineCallMeta]]


def extract_cv_document(
    path: Path,
    *,
    mime_type: str | None = None,
    company_code: str | None = None,
    document_id: str | None = None,
    app_key: str | None = None,
    db_execute: DbExecute | None = None,
    vision_rescue: VisionRescueFn | None = None,
    force_ocr: bool = False,
) -> ExtractionResult:
    """Main entry: local Poppler → Mistral OCR for failed pages → GPT rescue."""
    company = str(company_code or "").strip().upper()
    if not company:
        return ExtractionResult(text="", method="scope-check", error="tenant_scope_required")
    if not path.exists() or not path.is_file():
        return ExtractionResult(text="", method="missing-file", error="file_not_found")

    content = path.read_bytes()
    content_sha = sha256_bytes(content)
    guessed = str(mime_type or mimetypes.guess_type(path.name)[0] or "").lower()
    suffix = path.suffix.lower()
    engine_calls: list[EngineCallMeta] = []
    options = default_extraction_options()

    # Plain text / docx handled by caller; this module focuses on PDF + images.
    if guessed.startswith("text/") or suffix in {".txt", ".md", ".csv"}:
        text = path.read_text(errors="ignore").strip()
        ok = cv_text_quality_ok(text)
        return ExtractionResult(
            text=text,
            method="text",
            error=None if ok else "low_quality_text",
            quality_ok=ok,
            content_sha256=content_sha,
            metadata={"stage": "local", "tier": "plaintext"},
        )

    is_pdf = guessed == "application/pdf" or suffix == ".pdf"
    is_image = guessed.startswith("image/") or suffix in {".jpg", ".jpeg", ".png", ".webp"}

    if is_pdf:
        assessments = assess_pdf_pages(path)
        # Shadow advisor only — must not influence needs/accepted/OCR routing.
        pdf_inspector_shadow: dict[str, Any] | None = None
        try:
            import pdf_inspector_shadow as _pdf_inspector_shadow

            if _pdf_inspector_shadow.shadow_enabled():
                pdf_inspector_shadow = _pdf_inspector_shadow.run_pdf_inspector_shadow(
                    path,
                    assessments,
                    page_count_hint=len(assessments),
                )
                if db_execute is not None:
                    _pdf_inspector_shadow.record_shadow_run(
                        lambda **fields: record_extraction_run(db_execute, **fields),
                        company_code=company,
                        document_id=document_id,
                        app_key=app_key,
                        content_sha256=content_sha,
                        shadow=pdf_inspector_shadow,
                    )
        except Exception:  # noqa: BLE001 — fail-open; never block CV extraction
            logger.exception("pdf_inspector_shadow_outer_fail_open")
            pdf_inspector_shadow = {
                "contract": "pdf_inspector_shadow_advisor_wave1",
                "enabled": True,
                "ok": False,
                "fail_open": True,
                "error": "outer_exception",
                "influences_ocr_routing": False,
            }
        needs = [p for p in assessments if p.disposition == "needs_ocr" or force_ocr]
        accepted = [p for p in assessments if p.disposition == "accepted_local" and not force_ocr]
        page_hashes = [p.page_hash for p in assessments]

        def _with_shadow(meta: dict[str, Any]) -> dict[str, Any]:
            out = dict(meta or {})
            if pdf_inspector_shadow is not None:
                out["pdf_inspector_shadow"] = pdf_inspector_shadow
            return out

        # Clean digital PDF — all pages accepted locally.
        if not needs and assessments:
            full_text = merge_page_texts(assessments, {})
            if not full_text:
                full_text, _err = extract_pdf_full_text_layout(path)
            ok = cv_text_quality_ok(full_text)
            meta = EngineCallMeta(
                stage="local_extract",
                tier="poppler",
                provider="local",
                actual_request_model="pdftotext",
                provider_response_model="pdftotext",
                latency_ms=0,
                billable_pages=0,
                estimated_cost_usd=0.0,
                pages=[p.page_index for p in assessments],
                quality_ok=ok,
                retention="local_only",
            )
            engine_calls.append(meta)
            if db_execute is not None:
                record_extraction_run(
                    db_execute,
                    company_code=company,
                    document_id=document_id,
                    app_key=app_key,
                    content_sha256=content_sha,
                    stage=meta.stage,
                    tier=meta.tier,
                    provider=meta.provider,
                    actual_request_model=meta.actual_request_model,
                    provider_response_model=meta.provider_response_model,
                    pages_requested=meta.pages,
                    pages_processed=len(assessments),
                    billable_pages=0,
                    estimated_cost_usd=0.0,
                    latency_ms=0,
                    provider_request_id=None,
                    quality_ok=ok,
                    cache_hit=False,
                    error=None if ok else "low_quality_text",
                    metadata=_with_shadow({"page_dispositions": [p.disposition for p in assessments]}),
                )
            return ExtractionResult(
                text=full_text if ok else full_text,
                method="pdftotext",
                error=None if ok else "low_quality_text",
                quality_ok=ok,
                page_assessments=assessments,
                engine_calls=engine_calls,
                content_sha256=content_sha,
                metadata=_with_shadow(
                    {
                        "stage": "local_extract",
                        "tier": "poppler",
                        "provider": "local",
                        "actual_request_model": "pdftotext",
                        "provider_response_model": "pdftotext",
                        "pages_accepted_local": len(accepted),
                        "pages_needs_ocr": 0,
                        "mixed_pdf": False,
                    }
                ),
            )

        # Mixed / scanned — OCR only failed pages when flag enabled.
        if not mistral_ocr_enabled():
            # Preserve prior scanned-PDF failure behavior; do not silently GPT every page.
            local_only = merge_page_texts(assessments, {})
            if local_only and cv_text_quality_ok(local_only) and not needs:
                return ExtractionResult(
                    text=local_only,
                    method="pdftotext",
                    quality_ok=True,
                    page_assessments=assessments,
                    content_sha256=content_sha,
                    metadata=_with_shadow({"stage": "local_extract", "tier": "poppler"}),
                )
            return ExtractionResult(
                text=local_only,
                method="pdftotext",
                error="ocr_required_mistral_disabled",
                quality_ok=False,
                page_assessments=assessments,
                content_sha256=content_sha,
                metadata=_with_shadow(
                    {
                        "stage": "local_extract",
                        "tier": "poppler",
                        "pages_needs_ocr": [p.page_number for p in needs],
                        "hint": "Enable WATHEFNI_CV_MISTRAL_OCR after staging proof + privacy approval",
                    }
                ),
            )

        cache_key = build_cache_key(
            content_sha256=content_sha,
            page_hashes=page_hashes,
            provider="mistral",
            ocr_model=MISTRAL_OCR_MODEL,
            api_version=MISTRAL_OCR_API_VERSION,
            extraction_options={**options, "page_indexes": [p.page_index for p in needs]},
        )

        if db_execute is not None:
            cached = lookup_extraction_cache(db_execute, company_code=company, cache_key=cache_key)
            if cached and isinstance(cached.get("result"), dict):
                result_payload = cached["result"]
                text = str(result_payload.get("text") or "")
                meta = EngineCallMeta(
                    stage="ocr",
                    tier="mistral_ocr",
                    provider="mistral",
                    actual_request_model=MISTRAL_OCR_MODEL,
                    provider_response_model=str(cached.get("ocr_model") or MISTRAL_OCR_MODEL),
                    provider_request_id=cached.get("provider_request_id"),
                    latency_ms=int(cached.get("latency_ms") or 0),
                    billable_pages=0,
                    estimated_cost_usd=0.0,
                    pages=[p.page_index for p in needs],
                    cache_hit=True,
                    quality_ok=cv_text_quality_ok(text),
                    retention="cache_hit_no_provider_call",
                )
                engine_calls.append(meta)
                record_extraction_run(
                    db_execute,
                    company_code=company,
                    document_id=document_id,
                    app_key=app_key,
                    content_sha256=content_sha,
                    stage=meta.stage,
                    tier=meta.tier,
                    provider=meta.provider,
                    actual_request_model=meta.actual_request_model,
                    provider_response_model=meta.provider_response_model,
                    pages_requested=meta.pages,
                    pages_processed=0,
                    billable_pages=0,
                    estimated_cost_usd=0.0,
                    latency_ms=meta.latency_ms,
                    provider_request_id=meta.provider_request_id,
                    quality_ok=meta.quality_ok,
                    cache_hit=True,
                    error=None,
                    metadata=_with_shadow({"cache_key": cache_key}),
                )
                return ExtractionResult(
                    text=text,
                    method="mistral-ocr-4-0+cache",
                    quality_ok=bool(meta.quality_ok),
                    page_assessments=assessments,
                    engine_calls=engine_calls,
                    blocks=list(result_payload.get("blocks") or []),
                    content_sha256=content_sha,
                    cache_key=cache_key,
                    cache_hit=True,
                    metadata=_with_shadow(
                        {
                            "stage": "ocr",
                            "tier": "mistral_ocr",
                            "provider": "mistral",
                            "actual_request_model": MISTRAL_OCR_MODEL,
                            "provider_response_model": meta.provider_response_model,
                            "cache_hit": True,
                        }
                    ),
                )

        page_indexes = [p.page_index for p in needs]
        ocr_by_page, blocks, ocr_meta = extract_pdf_pages_with_mistral(path, page_indexes)
        engine_calls.append(ocr_meta)
        if db_execute is not None:
            record_extraction_run(
                db_execute,
                company_code=company,
                document_id=document_id,
                app_key=app_key,
                content_sha256=content_sha,
                stage=ocr_meta.stage,
                tier=ocr_meta.tier,
                provider=ocr_meta.provider,
                actual_request_model=ocr_meta.actual_request_model,
                provider_response_model=ocr_meta.provider_response_model,
                pages_requested=page_indexes,
                pages_processed=ocr_meta.billable_pages,
                billable_pages=ocr_meta.billable_pages,
                estimated_cost_usd=ocr_meta.estimated_cost_usd,
                latency_ms=ocr_meta.latency_ms,
                provider_request_id=ocr_meta.provider_request_id,
                quality_ok=ocr_meta.quality_ok,
                cache_hit=False,
                error=ocr_meta.error,
                metadata=_with_shadow({"mixed_pdf": bool(accepted and needs)}),
            )

        merged = merge_page_texts(assessments, ocr_by_page)
        failed_pages = [
            p.page_number
            for p in needs
            if not ocr_quality_ok(ocr_by_page.get(p.page_number, ""), pages=1)[0]
        ]

        # GPT rescue only for pages that still fail after Mistral.
        if failed_pages and gpt_vision_rescue_enabled() and vision_rescue is not None:
            import tempfile

            with tempfile.TemporaryDirectory(prefix="cv-ocr-rescue-") as tmp:
                rendered = render_pdf_pages_to_png(path, failed_pages, Path(tmp))
                for page_number, png_path in rendered.items():
                    rescue_text, rescue_meta = vision_rescue(png_path, "image/png")
                    rescue_meta.stage = "vision_rescue"
                    rescue_meta.tier = "gpt_vision_rescue"
                    rescue_meta.pages = [page_number - 1]
                    engine_calls.append(rescue_meta)
                    if db_execute is not None:
                        record_extraction_run(
                            db_execute,
                            company_code=company,
                            document_id=document_id,
                            app_key=app_key,
                            content_sha256=content_sha,
                            stage=rescue_meta.stage,
                            tier=rescue_meta.tier,
                            provider=rescue_meta.provider,
                            actual_request_model=rescue_meta.actual_request_model,
                            provider_response_model=rescue_meta.provider_response_model,
                            pages_requested=rescue_meta.pages,
                            pages_processed=1 if rescue_text else 0,
                            billable_pages=None,
                            estimated_cost_usd=None,
                            latency_ms=rescue_meta.latency_ms,
                            provider_request_id=rescue_meta.provider_request_id,
                            quality_ok=bool(rescue_text and cv_text_quality_ok(rescue_text, min_chars=40, min_words=6)),
                            cache_hit=False,
                            error=rescue_meta.error,
                            metadata={"rescued_page": page_number},
                        )
                    if rescue_text and cv_text_quality_ok(rescue_text, min_chars=40, min_words=6):
                        ocr_by_page[page_number] = rescue_text
            merged = merge_page_texts(assessments, ocr_by_page)

        ok = cv_text_quality_ok(merged)
        method = "mistral-ocr-4-0"
        if any(c.tier == "gpt_vision_rescue" and c.quality_ok for c in engine_calls):
            method = "mistral-ocr-4-0+gpt-rescue"
        if accepted and needs:
            method = f"pdftotext+{method}"

        if ok and db_execute is not None and not ocr_meta.cache_hit and ocr_meta.billable_pages:
            store_extraction_cache(
                db_execute,
                company_code=company,
                cache_key=cache_key,
                content_sha256=content_sha,
                page_hashes=page_hashes,
                provider="mistral",
                ocr_model=MISTRAL_OCR_MODEL,
                api_version=MISTRAL_OCR_API_VERSION,
                extraction_options={**options, "page_indexes": page_indexes},
                result={"text": merged, "blocks": blocks},
                billable_pages=ocr_meta.billable_pages,
                estimated_cost_usd=ocr_meta.estimated_cost_usd,
                latency_ms=ocr_meta.latency_ms,
                provider_request_id=ocr_meta.provider_request_id,
            )

        return ExtractionResult(
            text=merged,
            method=method,
            error=None if ok else (ocr_meta.error or "no_text_extracted"),
            quality_ok=ok,
            page_assessments=assessments,
            engine_calls=engine_calls,
            blocks=blocks,
            content_sha256=content_sha,
            cache_key=cache_key,
            metadata=_with_shadow(
                {
                    "stage": "ocr" if needs else "local_extract",
                    "tier": "mistral_ocr" if needs else "poppler",
                    "provider": "mistral" if needs else "local",
                    "actual_request_model": MISTRAL_OCR_MODEL if needs else "pdftotext",
                    "provider_response_model": ocr_meta.provider_response_model if needs else "pdftotext",
                    "pages_accepted_local": len(accepted),
                    "pages_ocr": [p.page_number for p in needs],
                    "pages_rescue": failed_pages if gpt_vision_rescue_enabled() else [],
                    "mixed_pdf": bool(accepted and needs),
                    "billable_pages": ocr_meta.billable_pages,
                    "estimated_cost_usd": ocr_meta.estimated_cost_usd,
                    "latency_ms": ocr_meta.latency_ms,
                    "provider_request_id": ocr_meta.provider_request_id,
                    "retention": ocr_meta.retention,
                }
            ),
        )

    if is_image:
        mime = guessed if guessed.startswith("image/") else (mimetypes.guess_type(path.name)[0] or "image/jpeg")
        if mistral_ocr_enabled():
            page_hashes = [sha256_bytes(content)]
            cache_key = build_cache_key(
                content_sha256=content_sha,
                page_hashes=page_hashes,
                provider="mistral",
                ocr_model=MISTRAL_OCR_MODEL,
                api_version=MISTRAL_OCR_API_VERSION,
                extraction_options=options,
            )
            if db_execute is not None:
                cached = lookup_extraction_cache(db_execute, company_code=company, cache_key=cache_key)
                if cached and isinstance(cached.get("result"), dict):
                    text = str(cached["result"].get("text") or "")
                    return ExtractionResult(
                        text=text,
                        method="mistral-ocr-4-0+cache",
                        quality_ok=cv_text_quality_ok(text),
                        content_sha256=content_sha,
                        cache_key=cache_key,
                        cache_hit=True,
                        metadata={
                            "stage": "ocr",
                            "tier": "mistral_ocr",
                            "provider": "mistral",
                            "actual_request_model": MISTRAL_OCR_MODEL,
                            "provider_response_model": str(cached.get("ocr_model") or MISTRAL_OCR_MODEL),
                            "cache_hit": True,
                        },
                    )
            text, blocks, meta = extract_image_with_mistral(path, mime)
            engine_calls.append(meta)
            if db_execute is not None:
                record_extraction_run(
                    db_execute,
                    company_code=company,
                    document_id=document_id,
                    app_key=app_key,
                    content_sha256=content_sha,
                    stage=meta.stage,
                    tier=meta.tier,
                    provider=meta.provider,
                    actual_request_model=meta.actual_request_model,
                    provider_response_model=meta.provider_response_model,
                    pages_requested=[0],
                    pages_processed=meta.billable_pages,
                    billable_pages=meta.billable_pages,
                    estimated_cost_usd=meta.estimated_cost_usd,
                    latency_ms=meta.latency_ms,
                    provider_request_id=meta.provider_request_id,
                    quality_ok=meta.quality_ok,
                    cache_hit=False,
                    error=meta.error,
                    metadata={"mime": mime},
                )
            if meta.quality_ok and text:
                if db_execute is not None and meta.billable_pages:
                    store_extraction_cache(
                        db_execute,
                        company_code=company,
                        cache_key=cache_key,
                        content_sha256=content_sha,
                        page_hashes=page_hashes,
                        provider="mistral",
                        ocr_model=MISTRAL_OCR_MODEL,
                        api_version=MISTRAL_OCR_API_VERSION,
                        extraction_options=options,
                        result={"text": text, "blocks": blocks},
                        billable_pages=meta.billable_pages,
                        estimated_cost_usd=meta.estimated_cost_usd,
                        latency_ms=meta.latency_ms,
                        provider_request_id=meta.provider_request_id,
                    )
                return ExtractionResult(
                    text=text,
                    method="mistral-ocr-4-0",
                    quality_ok=True,
                    engine_calls=engine_calls,
                    blocks=blocks,
                    content_sha256=content_sha,
                    cache_key=cache_key,
                    metadata={
                        "stage": "ocr",
                        "tier": "mistral_ocr",
                        "provider": "mistral",
                        "actual_request_model": MISTRAL_OCR_MODEL,
                        "provider_response_model": meta.provider_response_model,
                        "billable_pages": meta.billable_pages,
                        "estimated_cost_usd": meta.estimated_cost_usd,
                        "latency_ms": meta.latency_ms,
                        "provider_request_id": meta.provider_request_id,
                        "retention": meta.retention,
                    },
                )
            # Rescue after OCR failure.
            if gpt_vision_rescue_enabled() and vision_rescue is not None:
                rescue_text, rescue_meta = vision_rescue(path, mime)
                rescue_meta.stage = "vision_rescue"
                rescue_meta.tier = "gpt_vision_rescue"
                engine_calls.append(rescue_meta)
                if db_execute is not None:
                    record_extraction_run(
                        db_execute,
                        company_code=company,
                        document_id=document_id,
                        app_key=app_key,
                        content_sha256=content_sha,
                        stage=rescue_meta.stage,
                        tier=rescue_meta.tier,
                        provider=rescue_meta.provider,
                        actual_request_model=rescue_meta.actual_request_model,
                        provider_response_model=rescue_meta.provider_response_model,
                        pages_requested=[0],
                        pages_processed=1 if rescue_text else 0,
                        billable_pages=None,
                        estimated_cost_usd=None,
                        latency_ms=rescue_meta.latency_ms,
                        provider_request_id=rescue_meta.provider_request_id,
                        quality_ok=bool(rescue_text and cv_text_quality_ok(rescue_text)),
                        cache_hit=False,
                        error=rescue_meta.error,
                        metadata={"after": "mistral_ocr_failed"},
                    )
                ok = bool(rescue_text and cv_text_quality_ok(rescue_text))
                return ExtractionResult(
                    text=rescue_text,
                    method="gpt-vision-rescue",
                    error=None if ok else (rescue_meta.error or "rescue_failed"),
                    quality_ok=ok,
                    engine_calls=engine_calls,
                    content_sha256=content_sha,
                    metadata={
                        "stage": "vision_rescue",
                        "tier": "gpt_vision_rescue",
                        "provider": rescue_meta.provider,
                        "actual_request_model": rescue_meta.actual_request_model,
                        "provider_response_model": rescue_meta.provider_response_model,
                    },
                )
            return ExtractionResult(
                text=text,
                method="mistral-ocr-4-0",
                error=meta.error or "ocr_failed",
                quality_ok=False,
                engine_calls=engine_calls,
                content_sha256=content_sha,
            )

        # Flag off: legacy image path via vision_rescue callback if provided.
        if vision_rescue is not None:
            text, meta = vision_rescue(path, mime)
            # Rewrite misleading labels at the source.
            if meta.actual_request_model and "vision" in (meta.tier or ""):
                pass
            engine_calls.append(meta)
            ok = bool(text and cv_text_quality_ok(text))
            return ExtractionResult(
                text=text,
                method=meta.tier or "gpt_vision_legacy",
                error=None if ok else (meta.error or "vision_failed"),
                quality_ok=ok,
                engine_calls=engine_calls,
                content_sha256=content_sha,
                metadata={
                    "stage": meta.stage or "vision_legacy",
                    "tier": meta.tier,
                    "provider": meta.provider,
                    "actual_request_model": meta.actual_request_model,
                    "provider_response_model": meta.provider_response_model,
                },
            )
        return ExtractionResult(text="", method="image", error="mistral_ocr_disabled_no_rescue", content_sha256=content_sha)

    return ExtractionResult(text="", method="unsupported", error=f"unsupported_mime:{guessed or suffix}", content_sha256=content_sha)
