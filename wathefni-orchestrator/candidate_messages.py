"""Versioned bilingual copy for the contained candidate WhatsApp flow.

Only candidate-visible, externally meaningful moments belong here. Internal
workflow states, ranking, AI analysis, and HR task details are intentionally
excluded.
"""

from __future__ import annotations

import re
from typing import Any

CATALOG_VERSION = "candidate_flow_v1"
SUPPORTED_LOCALES = frozenset({"en", "ar"})

TEMPLATES: dict[str, dict[str, str]] = {
    "welcome": {
        "en": "Welcome to Wathefni. Send your APPLY code, or tell me which role you want to apply for.",
        "ar": "حياك في وظفني. أرسل رمز التقديم (APPLY)، أو اكتب اسم الوظيفة التي ترغب بالتقديم عليها.",
    },
    "role_resolved_cv_request": {
        "en": "Your application for {role} is ready. Please send your CV as a PDF, DOCX, or clear image.",
        "ar": "تم تحديد طلبك لوظيفة {role}. أرسل سيرتك الذاتية بصيغة PDF أو DOCX أو صورة واضحة.",
    },
    "job_context_ready": {
        "en": "{role} — {company}. {facts}. {summary} Ask me about the role, or tell me when you are ready to apply. Your application has not started yet.",
        "ar": "{role} — {company}. {facts}. {summary} اسألني عن الوظيفة، أو قل لي عندما تكون جاهزاً للتقديم. لم يبدأ طلب التوظيف بعد.",
    },
    "apply_confirm_needed": {
        "en": "Your application for {role} has not started yet. Reply \"ready to apply\" when you want to start, or send your CV after you have reviewed the role.",
        "ar": "لم يبدأ طلبك لوظيفة {role} بعد. اكتب \"جاهز للتقديم\" عندما تريد البدء، أو أرسل سيرتك الذاتية بعد مراجعة الوظيفة.",
    },
    "job_context_existing_application": {
        "en": "You already have an active application for {role}. I did not create or reset it. You can ask for its status or update your CV.",
        "ar": "لديك طلب توظيف نشط بالفعل لوظيفة {role}. لم أنشئ طلباً جديداً ولم أعد ضبط طلبك. يمكنك السؤال عن الحالة أو تحديث سيرتك الذاتية.",
    },
    "job_unavailable": {
        "en": "This job link is not available for new applications. Please check with the company for the latest role information.",
        "ar": "رابط الوظيفة غير متاح لطلبات جديدة. يرجى التواصل مع الشركة للحصول على أحدث معلومات الوظيفة.",
    },
    "job_paused": {
        "en": "This role is temporarily not accepting new applications.",
        "ar": "هذه الوظيفة لا تستقبل طلبات جديدة مؤقتاً.",
    },
    "job_closed": {
        "en": "This role is no longer accepting new applications.",
        "ar": "هذه الوظيفة لم تعد تستقبل طلبات جديدة.",
    },
    "job_deadline_passed": {
        "en": "The application period for this role has ended.",
        "ar": "انتهت فترة التقديم على هذه الوظيفة.",
    },
    "job_vacancies_exhausted": {
        "en": "This role is no longer accepting new applications.",
        "ar": "هذه الوظيفة لم تعد تستقبل طلبات جديدة.",
    },
    "cv_held_needs_role": {
        "en": "I am holding this file temporarily, but I need one exact job before an application can start. Send the APPLY code or tell me which role you mean.",
        "ar": "سأحتفظ بالملف مؤقتاً، لكن أحتاج تحديد وظيفة واحدة بالضبط قبل بدء طلب التوظيف. أرسل رمز APPLY أو اكتب اسم الوظيفة المقصودة.",
    },
    "cv_held_for_job_context": {
        "en": "I am holding this CV temporarily for {role}. Your application has not started yet.",
        "ar": "سأحتفظ بالسيرة الذاتية مؤقتاً لوظيفة {role}. لم يبدأ طلب التوظيف بعد.",
    },
    "file_received_checking": {
        "en": "We received your file and are checking that it is a supported, readable CV.",
        "ar": "استلمنا الملف ونتحقق الآن من أنه سيرة ذاتية مدعومة وقابلة للقراءة.",
    },
    "cv_accepted": {
        "en": "Your CV was accepted successfully. HR will handle the next step of your application.",
        "ar": "تم قبول سيرتك الذاتية بنجاح. سيتولى فريق الموارد البشرية الخطوة التالية في طلبك.",
    },
    "cv_invalid": {
        "en": "We could not accept this CV because it is unsupported, blank, corrupt, password-protected, or unreadable. Please send a readable PDF, DOCX, or clear image.",
        "ar": "تعذر قبول السيرة الذاتية لأنها غير مدعومة أو فارغة أو تالفة أو محمية بكلمة مرور أو غير قابلة للقراءة. أرسل ملف PDF أو DOCX قابلاً للقراءة أو صورة واضحة.",
    },
    "ambiguous_application": {
        "en": "You have more than one active application. Please send the APPLY code for the application you mean.",
        "ar": "لديك أكثر من طلب توظيف نشط. أرسل رمز التقديم (APPLY) الخاص بالطلب المقصود.",
    },
    "no_active_application": {
        "en": "I could not find an active application for you. Please send an APPLY code or tell me which role you want to apply for.",
        "ar": "لم أجد لك طلب توظيف نشطاً. أرسل رمز التقديم (APPLY) أو اكتب اسم الوظيفة التي ترغب بالتقديم عليها.",
    },
    "cv_replacement_requested": {
        "en": "Please send the replacement CV as a PDF, DOCX, or clear image. We will check it before updating your application.",
        "ar": "أرسل السيرة الذاتية البديلة بصيغة PDF أو DOCX أو صورة واضحة. سنتحقق منها قبل تحديث طلبك.",
    },
    "cv_updated_accepted": {
        "en": "Your updated CV was accepted successfully and is now attached to your application.",
        "ar": "تم قبول سيرتك الذاتية المحدثة بنجاح وإرفاقها بطلبك.",
    },
    "application_status": {
        "en": "Your application for {role} is currently: {status}.",
        "ar": "حالة طلبك لوظيفة {role} حالياً: {status}.",
    },
    "assessment_invitation": {
        "en": "You have an assessment for {role}. Open your secure link: {link}",
        "ar": "لديك تقييم خاص بطلبك لوظيفة {role}. افتح الرابط الآمن: {link}",
    },
    "interview_invitation": {
        "en": "You have an interview for {role}. {details} {link}",
        "ar": "لديك مقابلة لوظيفة {role}. {details} {link}",
    },
    "interview_update": {
        "en": "Your interview for {role} was updated. {details} {link}",
        "ar": "تم تحديث مقابلتك لوظيفة {role}. {details} {link}",
    },
    "offer_invitation": {
        "en": "You have an employment offer for {role}. Review and respond using this secure link: {link}",
        "ar": "لديك عرض وظيفي لوظيفة {role}. راجع العرض وأرسل ردك عبر الرابط الآمن: {link}",
    },
    "withdrawal_confirm_prompt": {
        "en": "Please confirm that you want to withdraw your application for {role}. Reply CONFIRM to withdraw or CANCEL to keep it active.",
        "ar": "يرجى تأكيد رغبتك في سحب طلبك لوظيفة {role}. أرسل «تأكيد» للسحب أو «إلغاء» للإبقاء على الطلب.",
    },
    "withdrawal_confirmation": {
        "en": "Your application for {role} has been withdrawn.",
        "ar": "تم سحب طلبك لوظيفة {role}.",
    },
    "hr_handoff_confirmation": {
        "en": "Your request to speak to HR was recorded. Automated application messages are paused until HR completes the handoff.",
        "ar": "تم تسجيل طلبك للتحدث مع الموارد البشرية. تم إيقاف رسائل الطلب التلقائية مؤقتاً حتى ينهي فريق الموارد البشرية المتابعة.",
    },
    "intent_clarification": {
        "en": "I want to help, but I am not sure what you need. Reply with one of: apply for a role, application status, replace CV, withdraw, speak to HR, assessment, interview, or offer.",
        "ar": "ودي أساعدك، بس مو واضح المطلوب. رد بواحد فقط: تقديم على وظيفة، حالة الطلب، استبدال السيرة، سحب الطلب، التحدث مع الموارد البشرية، التقييم، المقابلة، أو العرض الوظيفي.",
    },
    "assessment_inquiry_none": {
        "en": "I do not see an active assessment for your application right now. HR will send a secure assessment link when it is ready.",
        "ar": "ما عندي تقييم نشط لطلبك حالياً. يرسل فريق الموارد البشرية رابط التقييم الآمن عند الجاهزية.",
    },
    "interview_inquiry_none": {
        "en": "I do not see an interview invitation for your application right now. HR will share interview details when scheduled.",
        "ar": "ما عندي دعوة مقابلة لطلبك حالياً. يشارك فريق الموارد البشرية تفاصيل المقابلة عند جدولتها.",
    },
    "offer_inquiry_none": {
        "en": "I do not see an employment offer for your application right now. HR will send a secure offer link if an offer is issued.",
        "ar": "ما عندي عرض وظيفي لطلبك حالياً. يرسل فريق الموارد البشرية رابط العرض الآمن إذا صدر عرض.",
    },
}

STATUS_LABELS: dict[str, dict[str, str]] = {
    "awaiting_cv": {"en": "waiting for your CV", "ar": "بانتظار السيرة الذاتية"},
    "cv_processing": {"en": "CV being checked", "ar": "جارٍ التحقق من السيرة الذاتية"},
    "ready_for_review": {"en": "with HR for review", "ar": "قيد مراجعة الموارد البشرية"},
    "shortlisted": {"en": "with HR for the next step", "ar": "لدى الموارد البشرية للخطوة التالية"},
    "interview": {"en": "interview stage", "ar": "مرحلة المقابلة"},
    "hired": {"en": "hired", "ar": "تم التوظيف"},
    "rejected": {"en": "closed", "ar": "مغلق"},
    "withdrawn": {"en": "withdrawn", "ar": "تم السحب"},
}


def normalize_locale(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("_", "-")
    return "ar" if raw == "ar" or raw.startswith("ar-") else "en"


def infer_locale(text: Any = None, *, preferred: Any = None) -> str:
    if str(preferred or "").strip():
        return normalize_locale(preferred)
    return "ar" if re.search(r"[\u0600-\u06FF]", str(text or "")) else "en"


def status_label(status: Any, locale: Any = "en") -> str:
    loc = normalize_locale(locale)
    key = str(status or "").strip().lower()
    labels = STATUS_LABELS.get(key)
    if labels:
        return labels[loc]
    return key.replace("_", " ") or ("غير معروف" if loc == "ar" else "unknown")


def render(template_key: str, locale: Any = "en", **values: Any) -> dict[str, str]:
    if template_key not in TEMPLATES:
        raise KeyError(f"unknown_candidate_template:{template_key}")
    loc = normalize_locale(locale)
    safe_values = {key: str(value or "").strip() for key, value in values.items()}
    text = " ".join(TEMPLATES[template_key][loc].format(**safe_values).split())
    return {
        "template_key": template_key,
        "template_version": CATALOG_VERSION,
        "locale": loc,
        "text": text,
    }


def inventory() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key in sorted(TEMPLATES):
        rows.append(
            {
                "template_key": key,
                "template_version": CATALOG_VERSION,
                "en": TEMPLATES[key]["en"],
                "ar": TEMPLATES[key]["ar"],
            }
        )
    return rows
