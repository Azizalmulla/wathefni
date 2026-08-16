"""Person-aware Candidate profile authority.

Resolves a complete person profile from an anchor application using confirmed
identity only (person_id, grounded email, grounded phone). Never name-only.

Does not change lifecycle transitions, job-binding verification rules, or
intake_admit semantics — Add to job still promotes via the existing held
assign + intake_admit path after person-scoped duplicate preflight.
"""

from __future__ import annotations

import json
import re
from typing import Any

import unified_candidates as uc

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TECHNICAL_ACTIVITY = re.compile(
    r"held|intake|needs_role|provenance|taxonomy|completeness|privacy|retention|"
    r"classifier|talent.?pool|raw.?id|future.?action",
    re.I,
)


def normalize_email(value: Any) -> str | None:
    email = str(value or "").strip().lower()
    if not email or email.startswith("imp-"):
        return None
    if not _EMAIL_RE.match(email):
        return None
    return email


def normalize_phone_digits(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw or uc.is_surrogate_phone(raw):
        return None
    digits = re.sub(r"\D+", "", raw)
    if len(digits) < 8:
        return None
    return digits


def confirmed_merge_email(row: dict[str, Any]) -> str | None:
    """CV/application-grounded email only — never candidates.email alone.

    candidates.email can be polluted by shared workspace accounts and must not
    silently merge distinct people. Name is never a merge key.
    """
    raw = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
    profile = row.get("candidate_profile") if isinstance(row.get("candidate_profile"), dict) else {}
    contacts = profile.get("contacts") if isinstance(profile.get("contacts"), dict) else {}
    return normalize_email(
        contacts.get("email")
        or profile.get("email")
        or raw.get("candidate_email")
        or raw.get("email")
    )


def confirmed_identity_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Confirmed identity for person merge. Name is never a merge key."""
    person_id = str(row.get("person_id") or "").strip() or None
    membership_id = str(row.get("membership_id") or "").strip() or None
    email = confirmed_merge_email(row)
    phone = normalize_phone_digits(uc.grounded_contact_phone(row) or row.get("phone"))

    # person_id is highest authority when present — keeps membership clusters tight
    # even if a polluted candidates.email would otherwise collide.
    if person_id:
        return {
            "identity_key": f"person:{person_id}",
            "resolution_method": "person_id",
            "email": email,
            "phone": phone,
            "person_id": person_id,
            "membership_id": membership_id,
        }

    if email:
        return {
            "identity_key": f"email:{email}",
            "resolution_method": "grounded_email",
            "email": email,
            "phone": phone,
            "person_id": None,
            "membership_id": membership_id,
        }

    if phone:
        return {
            "identity_key": f"phone:{phone}",
            "resolution_method": "grounded_phone",
            "email": None,
            "phone": phone,
            "person_id": None,
            "membership_id": membership_id,
        }

    app_key = str(row.get("app_key") or "").strip()
    return {
        "identity_key": f"singleton:{app_key}",
        "resolution_method": "singleton",
        "email": None,
        "phone": None,
        "person_id": None,
        "membership_id": None,
    }


def _load_application_row(cur: Any, company: str, app_key: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT a.*, c.name AS candidate_name, c.email AS candidate_email,
               c.profile AS candidate_profile, c.raw_json AS candidate_raw_json,
               sd.content AS semantic_content
        FROM applications a
        LEFT JOIN candidates c ON c.phone=a.phone
        LEFT JOIN semantic_documents sd ON sd.entity_type='application' AND sd.entity_key=a.app_key
        WHERE a.company_code=%s AND a.app_key=%s
        LIMIT 1
        """,
        (company, app_key),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def resolve_person_application_keys(
    cur: Any,
    *,
    company: str,
    anchor_row: dict[str, Any],
) -> dict[str, Any]:
    """Return every authorized application key for the confirmed person.

    Order of authority:
    1. applications.person_id within the same company membership
    2. grounded email across tenant applications
    3. grounded/normalized phone across tenant applications
    4. singleton anchor only

    Name-only matching is never used.
    """
    identity = confirmed_identity_from_row(anchor_row)
    company = str(company or "").strip().upper()
    keys: list[str] = []
    method = identity["resolution_method"]

    person_id = identity.get("person_id")
    if person_id:
        cur.execute(
            """
            SELECT app_key
            FROM applications
            WHERE company_code=%s AND person_id=%s
            ORDER BY ingested_at DESC NULLS LAST, updated_at DESC NULLS LAST
            """,
            (company, person_id),
        )
        keys = [str(r["app_key"]) for r in cur.fetchall() if r.get("app_key")]
        if keys:
            method = "person_id"

    if not keys and identity.get("email"):
        email = identity["email"]
        # Broad SQL prefilter, then confirm with CV/application-grounded email only.
        # Do not treat candidates.email alone as merge authority.
        cur.execute(
            """
            SELECT a.app_key,
                   a.phone,
                   a.person_id,
                   a.raw_json,
                   c.email AS candidate_email,
                   c.profile AS candidate_profile
            FROM applications a
            LEFT JOIN candidates c ON c.phone=a.phone
            WHERE a.company_code=%s
              AND (
                lower(coalesce(a.raw_json->>'candidate_email','')) = %s
                OR lower(coalesce(a.raw_json->>'email','')) = %s
                OR lower(coalesce(c.profile->'contacts'->>'email','')) = %s
                OR lower(coalesce(c.profile->>'email','')) = %s
              )
            ORDER BY a.ingested_at DESC NULLS LAST
            """,
            (company, email, email, email, email),
        )
        matched: list[str] = []
        for item in cur.fetchall():
            row = dict(item)
            grounded = confirmed_merge_email(row)
            if grounded == email and not str(row.get("person_id") or "").strip():
                matched.append(str(row["app_key"]))
            elif grounded == email and str(row.get("person_id") or "").strip() == str(identity.get("person_id") or ""):
                matched.append(str(row["app_key"]))
        keys = matched
        if keys:
            method = "grounded_email"

    if not keys and identity.get("phone"):
        phone = identity["phone"]
        cur.execute(
            """
            SELECT a.app_key, a.phone, a.raw_json, c.profile AS candidate_profile,
                   c.email AS candidate_email
            FROM applications a
            LEFT JOIN candidates c ON c.phone=a.phone
            WHERE a.company_code=%s
              AND (
                regexp_replace(coalesce(a.phone,''), '\\D', '', 'g') = %s
                OR regexp_replace(coalesce(a.raw_json->>'candidate_phone',''), '\\D', '', 'g') = %s
                OR regexp_replace(coalesce(c.profile->'contacts'->>'phone',''), '\\D', '', 'g') = %s
              )
              AND coalesce(a.phone,'') NOT ILIKE 'imp-%%'
            ORDER BY a.ingested_at DESC NULLS LAST
            """,
            (company, phone, phone, phone),
        )
        matched = []
        for item in cur.fetchall():
            row = dict(item)
            digits = normalize_phone_digits(uc.grounded_contact_phone(row) or row.get("phone"))
            if digits == phone and not uc.is_surrogate_phone(row.get("phone")):
                matched.append(str(row["app_key"]))
            elif digits == phone:
                # Surrogate phone row but CV-grounded digits match — include.
                matched.append(str(row["app_key"]))
        keys = matched
        if keys:
            method = "grounded_phone"

    anchor_key = str(anchor_row.get("app_key") or "").strip()
    if not keys:
        keys = [anchor_key] if anchor_key else []
        method = "singleton"
    elif anchor_key and anchor_key not in keys:
        keys.insert(0, anchor_key)

    # De-dupe preserve order
    seen: set[str] = set()
    ordered: list[str] = []
    for key in keys:
        if key and key not in seen:
            seen.add(key)
            ordered.append(key)

    return {
        **identity,
        "resolution_method": method,
        "app_keys": ordered,
        "anchor_app_key": anchor_key,
    }


_ACTIVITY_LABELS = {
    "cv_received": "CV received",
    "cv received": "CV received",
    "application_created": "Application created",
    "application created": "Application created",
    "status_updated": "Stage updated",
    "interview_scheduled": "Interview scheduled",
    "assessment_sent": "Assessment sent",
    "assessment_completed": "Assessment completed",
    "shortlisted": "Shortlisted",
    "offer_sent": "Offer sent",
    "hired": "Hired",
    "rejected": "Rejected",
}


def _human_activity(summary: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for raw in summary.get("automatic_activity") or []:
        text = str(raw or "").strip()
        if not text or _TECHNICAL_ACTIVITY.search(text):
            continue
        label = _ACTIVITY_LABELS.get(text.lower()) or _ACTIVITY_LABELS.get(text)
        if not label:
            # Soften snake_case codes into readable labels.
            if re.fullmatch(r"[a-z0-9_]+", text.lower()):
                label = text.replace("_", " ").strip().capitalize()
            else:
                label = text
        if label and label not in items:
            items.append(label)
    for raw in summary.get("waiting_for_hr") or []:
        text = str(raw or "").strip()
        if text and not _TECHNICAL_ACTIVITY.search(text):
            label = _ACTIVITY_LABELS.get(text.lower()) or text
            item = f"Waiting on HR: {label}"
            if item not in items:
                items.append(item)
    return items[:20]


def _person_header_from_profile(
    summaries: list[dict[str, Any]],
    profile_facts: dict[str, Any] | None,
) -> dict[str, Any]:
    primary = summaries[0] if summaries else {}
    candidate = primary.get("candidate") if isinstance(primary.get("candidate"), dict) else {}
    contacts = primary.get("grounded_contacts") if isinstance(primary.get("grounded_contacts"), dict) else {}
    facts = profile_facts if isinstance(profile_facts, dict) else {}
    skills = facts.get("skills") if isinstance(facts.get("skills"), list) else []
    return {
        "display_name": candidate.get("name") or primary.get("candidate_name"),
        "email": contacts.get("email") or candidate.get("email"),
        "phone": contacts.get("phone"),
        "expertise": facts.get("primary_expertise"),
        "summary": facts.get("professional_summary"),
        "location": facts.get("location"),
        "top_skills": [str(s).strip() for s in skills if str(s).strip()][:12],
        "experience_years": facts.get("experience_years"),
        "source": primary.get("intake_source") or primary.get("data_source"),
        "received_at": primary.get("ingested_at"),
    }


def _dedupe_cv_versions(documents: list[dict[str, Any]], files: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_names: set[str] = set()
    for source in (*(documents or []), *(files or [])):
        if not isinstance(source, dict):
            continue
        doc_id = str(source.get("document_id") or source.get("file_id") or "").strip()
        filename = str(source.get("filename") or source.get("original_filename") or "").strip()
        key = doc_id or f"{filename}:{source.get('updated_at') or source.get('created_at') or ''}"
        if not key or key in seen:
            continue
        # Prefer candidate_documents over file_registry duplicates of the same filename.
        name_key = filename.casefold()
        if name_key and name_key in seen_names and not source.get("document_id"):
            continue
        seen.add(key)
        if name_key:
            seen_names.add(name_key)
        meta = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        latest = bool(meta.get("latest") or source.get("latest") or source.get("is_current"))
        superseded = bool(meta.get("superseded_at") or source.get("superseded_at"))
        rows.append(
            {
                "id": doc_id or key,
                "document_id": source.get("document_id"),
                "file_id": source.get("file_id"),
                "app_key": source.get("app_key"),
                "filename": filename or "CV",
                "created_at": source.get("created_at") or source.get("received_at") or source.get("stored_at"),
                "updated_at": source.get("updated_at"),
                "latest": latest and not superseded,
                "superseded": superseded,
            }
        )
    current = next((r for r in rows if r.get("latest")), rows[0] if rows else None)
    previous = [
        r
        for r in rows
        if current
        and r.get("id") != current.get("id")
        and not r.get("latest")
        and str(r.get("filename") or "").casefold() != str(current.get("filename") or "").casefold()
    ]
    return {"current": current, "previous": previous, "all": rows}


def build_person_profile(
    app_mod: Any,
    *,
    company: str,
    app_key: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Authoritative person profile for HR — independent of list pagination."""
    ensure_schema = app_mod.ensure_schema
    find_application_by_key = app_mod.find_application_by_key
    db_connect = app_mod.db_connect
    prehire_application_summary = app_mod.prehire_application_summary
    company_has_module = app_mod.company_has_module
    candidate_cv_truth = app_mod.candidate_cv_truth
    json_safe = app_mod.json_safe
    held_statuses = set(app_mod.HELD_IMPORT_STATUSES)

    ensure_schema()
    company = str(company or "").strip().upper()
    application = find_application_by_key(app_key, company_code=company)
    if not application:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail={"error": "application_not_found"})

    include_assessment = company_has_module(company, "assessments")
    permissions = context.get("permissions") or []
    cv_text: str | None = None
    documents: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    interviews: list[dict[str, Any]] = []
    assessments: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    gov = None
    resolution: dict[str, Any] = {}
    rows_by_key: dict[str, dict[str, Any]] = {}
    app_keys: list[str] = []
    anchor_row: dict[str, Any] = {}

    with db_connect() as conn:
        with conn.cursor() as cur:
            uc.ensure_unified_candidates_schema(cur)
            anchor_row = _load_application_row(cur, company, app_key)
            if not anchor_row:
                from fastapi import HTTPException

                raise HTTPException(status_code=404, detail={"error": "application_not_found"})

            resolution = resolve_person_application_keys(cur, company=company, anchor_row=anchor_row)
            app_keys: list[str] = resolution["app_keys"]

            rows_by_key: dict[str, dict[str, Any]] = {}
            for key in app_keys:
                row = _load_application_row(cur, company, key)
                if row:
                    rows_by_key[key] = row

            # CV documents across all person applications
            documents: list[dict[str, Any]] = []
            files: list[dict[str, Any]] = []
            if app_keys:
                try:
                    cur.execute(
                        """
                        SELECT d.document_id, d.app_key, d.document_type, d.filename, d.source,
                               d.extraction_status, d.received_at, d.created_at, d.updated_at,
                               jsonb_strip_nulls(jsonb_build_object(
                                 'latest', d.metadata->'latest',
                                 'superseded_at', d.metadata->'superseded_at',
                                 'superseded_by_document_id', d.metadata->'superseded_by_document_id'
                               )) AS metadata
                        FROM candidate_documents d
                        WHERE d.app_key = ANY(%s)
                        ORDER BY d.updated_at DESC NULLS LAST, d.created_at DESC
                        LIMIT 50
                        """,
                        (app_keys,),
                    )
                    documents = [json_safe(dict(item)) for item in cur.fetchall()]
                except Exception:
                    conn.rollback()
                    documents = []

                cur.execute(
                    """
                    SELECT file_id, subject_key AS app_key, file_kind, document_type, original_filename,
                           storage_provider, storage_url, storage_status, stored_at, updated_at, created_at
                    FROM file_registry
                    WHERE company_code=%s AND subject_type='application' AND subject_key = ANY(%s)
                    ORDER BY updated_at DESC, created_at DESC
                    LIMIT 50
                    """,
                    (company, app_keys),
                )
                files = [json_safe(dict(item)) for item in cur.fetchall()]

            interviews: list[dict[str, Any]] = []
            try:
                cur.execute(
                    """
                    SELECT interview_id, company_code, app_key, phone, candidate_name, candidate_email,
                           position_code, status, feedback_status, scheduled_start, scheduled_end,
                           timezone, meeting_type, meet_link, notes, notes_status, created_at, updated_at
                    FROM candidate_interviews
                    WHERE company_code=%s AND app_key = ANY(%s)
                    ORDER BY scheduled_start DESC NULLS LAST, updated_at DESC NULLS LAST
                    LIMIT 50
                    """,
                    (company, app_keys),
                )
                interviews = [json_safe(dict(item)) for item in cur.fetchall()]
            except Exception:
                conn.rollback()
                interviews = []

            assessments: list[dict[str, Any]] = []
            try:
                cur.execute(
                    """
                    SELECT attempt_id, company_code, app_key, phone, candidate_name, status,
                           delivery_status, review_status, battery_key, raw_score, max_score,
                           percent, band, summary, completed_at, created_at, updated_at
                    FROM assessment_attempts
                    WHERE company_code=%s AND app_key = ANY(%s)
                    ORDER BY updated_at DESC NULLS LAST, created_at DESC
                    LIMIT 50
                    """,
                    (company, app_keys),
                )
                assessments = [json_safe(dict(item)) for item in cur.fetchall()]
            except Exception:
                conn.rollback()
                assessments = []

            # Anchor facts (person overview uses anchor extraction)
            snap_row = None
            cv_text = None
            try:
                cur.execute(
                    """
                    SELECT facts_id, facts, facts_hash, document_id, contract_version, extractor_version,
                           materialized_at, is_current
                    FROM application_cv_fact_snapshots
                    WHERE company_code=%s AND app_key=%s AND is_current=true
                    LIMIT 1
                    """,
                    (company, app_key),
                )
                snap_row = cur.fetchone()
                if snap_row and isinstance(snap_row.get("facts"), dict):
                    anchor_row = dict(anchor_row)
                    anchor_row["_cv_fact_snapshot"] = dict(snap_row)
            except Exception:
                conn.rollback()
                snap_row = None

            if snap_row:
                if not cv_text and anchor_row.get("semantic_content"):
                    cv_text = str(anchor_row.get("semantic_content") or "")[:12000]
                if not cv_text:
                    try:
                        cur.execute("SAVEPOINT cpf_sem")
                        cur.execute(
                            """
                            SELECT left(coalesce(content, ''), 12000) AS content
                            FROM semantic_documents
                            WHERE entity_type='application' AND entity_key=%s
                            LIMIT 1
                            """,
                            (app_key,),
                        )
                        semantic = cur.fetchone()
                        if semantic and semantic.get("content"):
                            cv_text = str(semantic["content"])
                        cur.execute("RELEASE SAVEPOINT cpf_sem")
                    except Exception:
                        try:
                            cur.execute("ROLLBACK TO SAVEPOINT cpf_sem")
                        except Exception:
                            pass
                        cv_text = cv_text or None

            gov = uc.load_governance(cur, company_code=company, app_key=app_key)
            events = uc.list_fact_review_events(cur, company_code=company, app_key=app_key)
            conn.commit()

    summaries: list[dict[str, Any]] = []
    for key in app_keys:
        row = rows_by_key.get(key)
        if not row:
            continue
        summary = prehire_application_summary(
            row,
            include_raw=False,
            include_assessment=include_assessment,
            permissions=permissions,
        )
        summary = uc.enrich_application_summary(summary, row, gov=gov if key == app_key else None, permissions=permissions)
        summaries.append(summary)

    # Keep anchor first for stable UX when opening any sibling.
    summaries.sort(key=lambda s: 0 if str(s.get("app_key") or "") == app_key else 1)
    anchor_summary = next((s for s in summaries if str(s.get("app_key") or "") == app_key), summaries[0] if summaries else {})

    snapshot = uc.extract_facts_snapshot(anchor_row)
    facts_id = None
    facts_hash = None
    if isinstance(anchor_row.get("_cv_fact_snapshot"), dict):
        snap = anchor_row["_cv_fact_snapshot"]
        facts_id = str(snap.get("facts_id") or "") or None
        facts_hash = str(snap.get("facts_hash") or "") or None
        snapshot = {
            "schema": snap.get("contract_version") or "application-cv-facts-v1",
            "immutable": True,
            "snapshot": snap.get("facts") or {},
            "facts_hash": facts_hash,
            "facts_id": facts_id,
            "document_id": snap.get("document_id"),
            "extractor_version": snap.get("extractor_version"),
            "materialized_at": json_safe(snap.get("materialized_at")),
            "source": "application_cv_fact_snapshots",
        }
    effective = uc.effective_facts_from_events(snapshot, events)
    facts_effective = effective.get("effective") if isinstance(effective.get("effective"), dict) else {}
    reviews_by_path = effective.get("reviews_by_path") if isinstance(effective.get("reviews_by_path"), dict) else {}

    import candidate_profile_facts as cpf

    profile_facts = cpf.build_canonical_profile_facts(
        raw_facts=facts_effective,
        reviews_by_path=reviews_by_path,
        cv_text=cv_text,
        classification_chip=str(anchor_summary.get("classification_chip") or "") or None,
        facts_id=facts_id,
        source_facts_hash=facts_hash,
    )

    # Prefer CV Extraction V2 projection only after quality-gate publish switch.
    try:
        import cv_extraction_v2 as cv2

        if cv2.profile_facts_v2_published():
            with db_connect() as conn:
                with conn.cursor() as cur:
                    v2_row = cv2.load_current_v2(cur, company_code=company, app_key=app_key)
                    if v2_row and str(v2_row.get("status") or "") == "ready":
                        payload = v2_row.get("payload") if isinstance(v2_row.get("payload"), dict) else {}
                        projected = cv2.project_profile_facts_v2(payload)
                        projected["source_facts_id"] = facts_id
                        projected["source_extraction_id"] = str(v2_row.get("extraction_id") or "")
                        projected["source_contract_version"] = cv2.CV_EXTRACTION_V2_CONTRACT
                        projected["profile_hash"] = cpf.profile_hash(projected)
                        profile_facts = projected
                        if facts_id:
                            try:
                                cpf.materialize_profile_facts(
                                    cur,
                                    facts_id=facts_id,
                                    company_code=company,
                                    app_key=app_key,
                                    profile=profile_facts,
                                    source_facts_hash=facts_hash,
                                )
                                conn.commit()
                            except Exception:
                                pass
    except Exception:
        pass

    # Persist v1 projection when we have a snapshot (idempotent; never duplicates extraction).
    if facts_id and str(profile_facts.get("schema") or "") == cpf.PROFILE_FACTS_SCHEMA:
        try:
            with db_connect() as conn:
                with conn.cursor() as cur:
                    cpf.materialize_profile_facts(
                        cur,
                        facts_id=facts_id,
                        company_code=company,
                        app_key=app_key,
                        profile=profile_facts,
                        source_facts_hash=facts_hash,
                    )
                    conn.commit()
        except Exception:
            pass

    held_apps = [
        s for s in summaries
        if str(s.get("status") or "") in held_statuses or bool(s.get("is_held"))
    ]
    held_keys = {str(s.get("app_key") or "") for s in held_apps}
    live_apps = [s for s in summaries if str(s.get("app_key") or "") not in held_keys]
    # Applications tab: live job applications only. General-only people show zero.
    applications_for_ui = live_apps

    notes_enabled = False  # Hide until a real HR notes authority exists.
    notes: list[dict[str, Any]] = []

    activity: list[str] = []
    for summary in summaries:
        for item in _human_activity(summary):
            if item not in activity:
                activity.append(item)

    taken_positions: set[str] = set()
    for s in live_apps:
        pos = s.get("position") if isinstance(s.get("position"), dict) else {}
        code = str(pos.get("code") or s.get("position_code") or "").strip()
        if code:
            taken_positions.add(code)

    held_for_add = next(
        (
            s
            for s in summaries
            if str(s.get("status") or "") in {"needs_role", "import_review"}
            or (s.get("is_held") and str(s.get("status") or "") != "import_archived")
        ),
        None,
    )
    can_import = "candidate.import" in {str(p) for p in permissions}
    add_to_job = {
        "available": bool(held_for_add) and can_import,
        "enabled": bool(held_for_add) and can_import,
        "held_app_key": (held_for_add or {}).get("app_key"),
        "blocked_position_codes": sorted(taken_positions),
        "reason": None
        if (held_for_add and can_import)
        else (
            "missing_candidate_import_permission"
            if held_for_add and not can_import
            else "no_general_candidate_application"
        ),
    }

    person = _person_header_from_profile(summaries, profile_facts)
    cv_bundle = _dedupe_cv_versions(documents, files)

    # Public person-profile contract: clean profile facts only (no raw {value} shapes).
    return {
        "ok": True,
        "company_code": company,
        "schema": "candidate-person-profile-v2",
        "resolution": {
            "anchor_app_key": app_key,
            "person_id": resolution.get("person_id"),
            "membership_id": resolution.get("membership_id"),
            "identity_key": resolution.get("identity_key"),
            "resolution_method": resolution.get("resolution_method"),
            "email": resolution.get("email"),
            "phone": resolution.get("phone"),
            "application_count": len(applications_for_ui),
            "person_application_count": len(summaries),
        },
        "person": person,
        "profile_facts": {
            "schema": profile_facts.get("schema"),
            "skills": profile_facts.get("skills") or [],
            "education": profile_facts.get("education") or [],
            "employment": profile_facts.get("employment") or [],
            "languages": profile_facts.get("languages") or [],
            "certifications": profile_facts.get("certifications") or [],
            "projects": profile_facts.get("projects") or [],
            "publications": profile_facts.get("publications") or [],
            "training_courses": profile_facts.get("training_courses") or [],
            "memberships_activities": profile_facts.get("memberships_activities") or [],
            "awards_honors": profile_facts.get("awards_honors") or [],
            "volunteer_work": profile_facts.get("volunteer_work") or [],
            "references": profile_facts.get("references") or [],
            "location": profile_facts.get("location"),
            "professional_summary": profile_facts.get("professional_summary"),
            "primary_expertise": profile_facts.get("primary_expertise"),
            "experience_years": profile_facts.get("experience_years"),
            "availability": profile_facts.get("availability"),
            "unmodeled_sections": profile_facts.get("unmodeled_sections") or [],
            # Structured V2 records are presentation-safe projections of the
            # same canonical authority. They let HR clients render timelines
            # and cards without reparsing flattened CV strings.
            "structured": profile_facts.get("structured") or {},
            "field_sources": profile_facts.get("field_sources") or {},
        },
        "application": anchor_summary,
        "applications": applications_for_ui,
        "held_applications": held_apps,
        "live_applications": live_apps,
        "documents": documents,
        "files": files,
        "cv_versions": cv_bundle,
        "cv_truth": candidate_cv_truth(anchor_row),
        "interviews": interviews,
        "assessments": assessments,
        "notes_enabled": notes_enabled,
        "notes": notes,
        "activity": activity,
        "grounded_contacts": anchor_summary.get("grounded_contacts"),
        "record_state": anchor_summary.get("record_state"),
        "source_channel": anchor_summary.get("intake_source"),
        "add_to_job": add_to_job,
        "allowed_actions": anchor_summary.get("allowed_actions") or [],
        # Extraction evidence retained for platform/debug — not for normal HR UI rendering.
        "extraction_evidence": {
            "source_facts_id": facts_id,
            "source_facts_hash": facts_hash,
            "source_contract_version": snapshot.get("schema"),
            "immutable": True,
        },
    }


def person_add_to_job_preflight(
    person_profile: dict[str, Any],
    *,
    position_code: str,
) -> dict[str, Any]:
    """Person-scoped duplicate / eligibility checks before assign+promote."""
    code = str(position_code or "").strip()
    add = person_profile.get("add_to_job") if isinstance(person_profile.get("add_to_job"), dict) else {}
    if not code:
        return {"ok": False, "error": "position_code_required", "message": "Select an open job."}
    blocked = {str(c).strip() for c in (add.get("blocked_position_codes") or [])}
    # Duplicate check wins even when the held general record was already promoted.
    if code in blocked:
        return {
            "ok": False,
            "error": "duplicate_active_application",
            "http_status": 409,
            "message": "This candidate already has an application for that job.",
            "blocked_position_codes": sorted(blocked),
        }
    if not add.get("enabled"):
        return {
            "ok": False,
            "error": add.get("reason") or "add_to_job_unavailable",
            "http_status": 400,
            "message": "This person cannot be added to a job right now.",
            "blocked_position_codes": sorted(blocked),
        }
    held_app_key = str(add.get("held_app_key") or "").strip()
    if not held_app_key:
        return {
            "ok": False,
            "error": "no_general_candidate_application",
            "http_status": 400,
            "message": "No general candidate record is available to link.",
        }
    return {"ok": True, "held_app_key": held_app_key, "position_code": code}


__all__ = [
    "build_person_profile",
    "confirmed_identity_from_row",
    "confirmed_merge_email",
    "normalize_email",
    "normalize_phone_digits",
    "person_add_to_job_preflight",
    "resolve_person_application_keys",
]
