"""Assistant-facing Jobs inventory presentation and operational visibility.

Does not change Jobs authority math, Stage B routing, or position records.
Display-only helpers for Pre-Hiring Assistant chat.
"""

from __future__ import annotations

import os
import re
from typing import Any

ASSISTANT_JOB_INVENTORY_FETCH_MAX = 100
ASSISTANT_JOB_INVENTORY_PAGE_SIZE = 50

_HIDDEN_POSITIONS_ENV = "WATHEFNI_ASSISTANT_HIDDEN_POSITIONS"

# Typed production canary identities (not title substrings). Stage B routing still
# depends on env pins; these only hide ordinary Assistant inventory when present.
KNOWN_ASSISTANT_HIDDEN_POSITION_CODES = {"J2P2_PROD_TEST"}
KNOWN_ASSISTANT_HIDDEN_APPLY_CODES = {"APPLY-WATHEFNI-J2P2_PROD_TEST"}

_ACRONYMS = {
    "IT",
    "HR",
    "CV",
    "AI",
    "API",
    "QA",
    "UX",
    "UI",
    "CEO",
    "CTO",
    "CFO",
    "COO",
    "KPI",
    "SQL",
    "NBK",
}

_ELIGIBILITY_LABELS = {
    "job_content_incomplete": "Job setup incomplete",
    "not_shareable": "Not ready to share externally",
    "job_not_publishable": "Not ready to publish",
}

_BLOCKER_LABELS = {
    "visibility": "public/internal visibility not set",
    "vacancies": "number of vacancies missing",
    "approved_language_pack": "Arabic/English content not approved",
    "location_or_fully_remote": "job location or remote setup missing",
    "employment_type": "employment type missing",
    "apply_identity": "apply identity missing",
    "company_display_name": "company display name missing",
    "salary_visibility": "salary visibility not set",
    "public_salary": "public salary range incomplete",
    "apply_whatsapp_number": "WhatsApp apply number missing",
}

_OPERATIONAL_ASK_RE = re.compile(
    r"\b("
    r"canary|stage\s*b|test\s+job|production\s+test|"
    r"operational\s+job|hidden\s+job|j2p2"
    r")\b",
    re.I,
)

_SETUP_ASK_RE = re.compile(
    r"\b("
    r"why\s+can'?t|why\s+cannot|incomplete\s+setup|job\s+setup|"
    r"not\s+shareable|can'?t\s+be\s+shared|cannot\s+be\s+shared|"
    r"apply\s+code|share\s+link|publish\s+blocker"
    r")\b",
    re.I,
)


def _split_csv_env(name: str) -> set[str]:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return set()
    return {part.strip().upper() for part in raw.split(",") if part.strip()}


def assistant_hidden_position_codes() -> set[str]:
    """Typed operational hide-list for ordinary Assistant inventory."""
    codes = set(KNOWN_ASSISTANT_HIDDEN_POSITION_CODES)
    codes |= _split_csv_env(_HIDDEN_POSITIONS_ENV)
    try:
        import jobs_phase2_stage_b as stage_b

        codes |= {str(c).upper() for c in stage_b.public_canary_positions()}
    except Exception:
        pass
    return codes


def assistant_hidden_apply_codes() -> set[str]:
    codes = set(KNOWN_ASSISTANT_HIDDEN_APPLY_CODES)
    try:
        import jobs_phase2_stage_b as stage_b

        codes |= {str(c).upper() for c in stage_b.public_canary_apply_codes()}
    except Exception:
        pass
    return codes


def _row_metadata(row: dict[str, Any]) -> dict[str, Any]:
    meta = row.get("metadata")
    if isinstance(meta, dict):
        return meta
    raw = row.get("raw_json")
    if isinstance(raw, dict) and isinstance(raw.get("metadata"), dict):
        return raw["metadata"]
    return {}


def is_operational_canary_job(row: dict[str, Any] | None) -> bool:
    """True when the position is operational/canary and hidden from ordinary inventory."""
    if not isinstance(row, dict):
        return False
    position_code = str(row.get("position_code") or "").strip().upper()
    apply_code = str(row.get("apply_code") or "").strip().upper()
    meta = _row_metadata(row)
    visibility = str(meta.get("assistant_visibility") or "").strip().lower()
    if visibility in {"operational_only", "hidden_from_assistant"}:
        return True
    if bool(meta.get("operational_canary") or meta.get("stage_b_canary") or meta.get("assistant_hide_from_inventory")):
        return True
    if position_code and position_code in assistant_hidden_position_codes():
        return True
    if apply_code and apply_code in assistant_hidden_apply_codes():
        return True
    try:
        import jobs_phase2_stage_b as stage_b

        if stage_b.is_public_canary_job(position_code=position_code, apply_code=apply_code):
            return True
    except Exception:
        pass
    return False


def looks_like_operational_inventory_request(text: str | None) -> bool:
    return bool(_OPERATIONAL_ASK_RE.search(str(text or "")))


def looks_like_job_setup_detail_request(text: str | None) -> bool:
    return bool(_SETUP_ASK_RE.search(str(text or "")))


def search_targets_operational_job(search: str | None) -> bool:
    """Exact code/APPLY lookup or explicit operational ask → include canary rows."""
    raw = str(search or "").strip()
    if not raw:
        return False
    if looks_like_operational_inventory_request(raw):
        return True
    token = raw.upper().replace(" ", "_")
    apply = raw.strip().upper()
    if token in assistant_hidden_position_codes():
        return True
    if apply in assistant_hidden_apply_codes():
        return True
    if apply.startswith("APPLY-") and apply in assistant_hidden_apply_codes():
        return True
    try:
        import jobs_phase2_stage_b as stage_b

        if stage_b.is_public_canary_job(position_code=token, apply_code=apply):
            return True
    except Exception:
        pass
    return False


def filter_assistant_inventory_rows(
    rows: list[dict[str, Any]],
    *,
    include_operational: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (visible, hidden) for Assistant inventory."""
    visible: list[dict[str, Any]] = []
    hidden: list[dict[str, Any]] = []
    for row in rows:
        if not include_operational and is_operational_canary_job(row):
            hidden.append(row)
        else:
            visible.append(row)
    return visible, hidden


def normalize_display_job_title(title: str | None, *, fallback: str = "Role") -> str:
    """Display-only title capitalization. Does not rewrite stored records."""
    raw = str(title or "").strip()
    if not raw:
        return fallback
    parts: list[str] = []
    for token in re.split(r"(\s+|-|/)", raw):
        if not token or token.isspace() or token in {"-", "/"}:
            parts.append(token)
            continue
        upper = token.upper()
        if upper in _ACRONYMS:
            parts.append(upper)
        elif token.isupper() and len(token) <= 3 and token.isalpha():
            parts.append(upper)
        else:
            parts.append(token[:1].upper() + token[1:].lower() if token else token)
    return "".join(parts).strip() or fallback


def humanize_eligibility_reason(reason: str | None) -> str | None:
    raw = str(reason or "").strip()
    if not raw:
        return None
    return _ELIGIBILITY_LABELS.get(raw, "Job setup incomplete")


def humanize_publish_blockers(blockers: list[str] | None) -> list[str]:
    out: list[str] = []
    for item in blockers or []:
        key = str(item or "").strip()
        if not key:
            continue
        out.append(_BLOCKER_LABELS.get(key, key.replace("_", " ")))
    return out


def format_candidate_count_phrase(active_count: int, *, total_count: int | None = None) -> str | None:
    active = max(0, int(active_count or 0))
    if active <= 0:
        return "no active candidates"
    noun = "candidate" if active == 1 else "candidates"
    phrase = f"{active} {noun}"
    if total_count is not None:
        total = max(0, int(total_count or 0))
        if total > active:
            # Only when callers explicitly request the dual phrasing.
            return f"{active} active candidate{'s' if active != 1 else ''}, {total} total applications"
    return phrase


def format_job_setup_detail_reply(item: dict[str, Any]) -> str:
    title = normalize_display_job_title(
        str(item.get("position_title") or item.get("title") or item.get("position_code") or "This role")
    )
    reason = humanize_eligibility_reason(item.get("eligibility_reason"))
    blockers = humanize_publish_blockers(item.get("publish_blockers") if isinstance(item.get("publish_blockers"), list) else [])
    if not blockers and isinstance(item.get("eligibility"), dict):
        blockers = humanize_publish_blockers(item["eligibility"].get("blockers"))
    lines = [f"{title}: {reason or 'Job setup incomplete'}."]
    if blockers:
        lines.append("Still needed:")
        for blocker in blockers:
            lines.append(f"- {blocker}")
    else:
        lines.append("Complete the remaining job fields in Jobs before sharing externally.")
    return "\n".join(lines)


def format_assistant_job_openings_reply(result: dict[str, Any] | None) -> str:
    """Owner-ready inventory reply. No APPLY codes, enums, or dual count mechanics."""
    data = result if isinstance(result, dict) else {}
    positions = data.get("positions") if isinstance(data.get("positions"), list) else []
    status = str(data.get("status_filter") or "open").strip().lower() or "open"
    detail_mode = str(data.get("detail_mode") or "").strip().lower()
    try:
        total = int(data.get("total_matching") if data.get("total_matching") is not None else len(positions))
    except Exception:
        total = len(positions)

    if detail_mode in {"setup", "shareability"} and positions:
        first = positions[0] if isinstance(positions[0], dict) else {}
        return format_job_setup_detail_reply(first)

    if total <= 0 or not positions:
        if status == "open":
            return "You currently have no open roles."
        if status == "closed":
            return "No closed job openings right now."
        return "No job openings found."

    if status == "open":
        header = f"You currently have {total} open role{'s' if total != 1 else ''}:"
    elif status == "closed":
        header = f"Closed roles ({total}):"
    else:
        header = f"Roles ({total}):"

    lines: list[str] = [header]
    page = positions[:ASSISTANT_JOB_INVENTORY_PAGE_SIZE]
    for item in page:
        if not isinstance(item, dict):
            continue
        title = normalize_display_job_title(
            str(item.get("position_title") or item.get("title") or item.get("position_code") or "Role")
        )
        active = int(item.get("active_count") or 0)
        count_phrase = format_candidate_count_phrase(active)
        if active > 0:
            lines.append(f"- {title} — {count_phrase}")
        elif int(item.get("application_count") or 0) > 0:
            lines.append(f"- {title} — no active candidates")
        else:
            lines.append(f"- {title}")

    remaining = max(0, total - len(page))
    continuation = data.get("continuation") if isinstance(data.get("continuation"), dict) else {}
    if remaining > 0:
        label = str(continuation.get("label") or "Show more roles").strip() or "Show more roles"
        lines.append(f"There are {remaining} more. Ask me to “{label}” to continue.")
    elif status == "open":
        lines.append("")
        lines.append("Which role would you like me to use?")
    return "\n".join(lines)


def ranking_recalculate_preview_message(
    *,
    title: str,
    position_code: str,
    pool_count: int,
) -> str:
    display = normalize_display_job_title(title or position_code)
    noun = "candidate" if pool_count == 1 else "candidates"
    return (
        f"{display} hasn’t been ranked yet.\n\n"
        f"I can calculate a new advisory Ranking using the current {display} job requirements "
        f"and its {pool_count} {noun}. This will create a new Ranking run.\n\n"
        "Would you like me to proceed?\n\n"
        "HR makes the final decision."
    )
