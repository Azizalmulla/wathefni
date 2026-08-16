#!/usr/bin/env python3
"""Local qualification for Kuwait first-client foundation remediation.

Uses an isolated Postgres schema (no product deploy). Covers legal entities,
hire-time applicability snapshots, identity masking/confirmation, residence
vocabulary compatibility, Arabic contract upload link, concurrency/replay,
and tenant isolation.

Does not encode leave/EOS/PIFSS/fines/OT multipliers or government filings.
"""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import traceback
import uuid

from cryptography.fernet import Fernet
import psycopg2
from psycopg2.extras import Json, RealDictCursor

import hire_operations
import kuwait_first_client_foundation as kw
import offer_lifecycle as offers
import recruiting_lifecycle as lifecycle


MARKER = "kuwait-first-client-foundation-local-v1"
FULL_PERMS = {
    kw.LEGAL_ENTITY_MANAGE,
    kw.LEGAL_ENTITY_READ,
    kw.IDENTITY_READ,
    kw.IDENTITY_READ_FULL,
    kw.IDENTITY_WRITE,
    "candidate.hire",
    "candidate.decide",
    "offer.hire_override",
    "prehire.manage",
}
ACTOR = "a0a10000-0000-4000-8000-0000000000aa"


class Gate:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append({"gate": name, "ok": bool(ok), "detail": str(detail)[:1200]})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {str(detail)[:200]}" if detail else ""), flush=True)

    @property
    def failed(self) -> list[dict]:
        return [r for r in self.rows if not r["ok"]]


class LocalLegacy:
    def __init__(self, schema: str, root: Path, *, offers_enabled: bool = True) -> None:
        self.schema = schema
        self.root = root
        self.Json = Json
        self._offers_enabled = offers_enabled
        self._settings: dict = {
            "employment_offer_document_defaults": {
                "country_of_employment": "KW",
                "currency": "KWD",
                "document_language": "ar",
                "template_id": "KW-CONTRACT-PILOT",
                "template_version": "2026.7",
                "template_approval_ref": "COUNSEL-PILOT-1",
                "employer_policy_version": "HR-POLICY-KW-1",
                "authorized_signatory": "Pilot Signatory",
                "configuration_effective_date": "2026-07-01",
                "probation_days": 90,
            }
        }

    def db_connect(self):
        dsn = os.environ.get("WATHEFNI_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if dsn:
            conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
        else:
            conn = psycopg2.connect(dbname="postgres", cursor_factory=RealDictCursor)
        with conn.cursor() as cur:
            cur.execute(f'SET search_path TO "{self.schema}"')
        return conn

    def company_has_module(self, company: str, module: str) -> bool:
        if module == "employment_offers":
            return bool(self._offers_enabled)
        return True

    def get_company_settings(self, company: str) -> dict:
        return {"settings": self._settings}

    def json_safe(self, value):
        return value

    def digits(self, value):
        return "".join(ch for ch in str(value or "") if ch.isdigit())

    def onboarding_seed_enabled(self):
        return False

    def _seed_employee_compliance_documents(self, cur, company, employee_key, employee_category=None):
        types = kw.compliance_seed_types_for_category(employee_category)
        for doc_type in types:
            cur.execute(
                """
                INSERT INTO compliance_documents (employee_key, document_type, label, status, warning_days, company_code, updated_at)
                VALUES (%s,%s,%s,'missing',30,%s, now())
                ON CONFLICT (employee_key, document_type) DO NOTHING
                """,
                (employee_key, doc_type, doc_type, company),
            )


def _ensure_min_schema(cur) -> None:
    cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    for sql in (
        """
        CREATE TABLE IF NOT EXISTS companies(
          company_code text PRIMARY KEY, name text, country text,
          status text DEFAULT 'active',
          metadata jsonb DEFAULT '{}'::jsonb, raw_json jsonb DEFAULT '{}'::jsonb,
          created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS company_settings(
          company_code text PRIMARY KEY, settings jsonb NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS company_modules(
          company_code text NOT NULL, module_key text NOT NULL, enabled boolean NOT NULL DEFAULT true,
          source text, updated_at timestamptz DEFAULT now(), PRIMARY KEY(company_code, module_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS candidates(
          phone text PRIMARY KEY, name text, email text,
          current_status text DEFAULT 'active',
          raw_json jsonb DEFAULT '{}'::jsonb
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS applications(
          app_key text PRIMARY KEY, phone text, company_code text, position_code text,
          position_title text, status text, lifecycle_version bigint DEFAULT 1,
          candidate_name text, candidate_email text,
          raw_json jsonb DEFAULT '{}'::jsonb, updated_at timestamptz DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS employees(
          employee_key text PRIMARY KEY, phone text, company_code text, app_key text,
          name text, email text, position_title text, start_date date,
          profile jsonb DEFAULT '{}'::jsonb, raw_json jsonb DEFAULT '{}'::jsonb,
          onboarding_status text, employment_status text DEFAULT 'active',
          updated_at timestamptz DEFAULT now(), created_at timestamptz DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS compliance_documents(
          id bigserial PRIMARY KEY,
          employee_key text NOT NULL, document_type text NOT NULL, label text,
          status text, warning_days int, company_code text, expiry_date date,
          updated_at timestamptz DEFAULT now(),
          UNIQUE(employee_key, document_type)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS onboarding_items(
          id bigserial PRIMARY KEY,
          employee_key text, company_code text, item_id text, label text,
          status text DEFAULT 'pending', document_type text
        )
        """,
    ):
        cur.execute(sql)
    hire_operations.ensure_hire_schema(cur)
    offers.ensure_offer_schema(cur)
    kw.ensure_foundation_schema(cur)


@contextmanager
def local_env(offers_enabled: bool = True):
    schema = f"kw_foundation_{uuid.uuid4().hex[:10]}"
    key = Fernet.generate_key().decode()
    os.environ["WATHEFNI_CIVIL_ID_KEY"] = key
    root = tempfile.TemporaryDirectory(prefix="kw-foundation-")
    legacy = LocalLegacy(schema, Path(root.name), offers_enabled=offers_enabled)
    dsn = os.environ.get("WATHEFNI_DATABASE_URL") or os.environ.get("DATABASE_URL")
    admin = psycopg2.connect(dsn, cursor_factory=RealDictCursor) if dsn else psycopg2.connect(dbname="postgres", cursor_factory=RealDictCursor)
    try:
        with admin.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{schema}"')
        admin.commit()
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                _ensure_min_schema(cur)
            conn.commit()
        yield legacy
    finally:
        with admin.cursor() as cur:
            cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        admin.commit()
        admin.close()
        root.cleanup()


def _seed_company(legacy: LocalLegacy, code: str, *, country: str = "KW") -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO companies(company_code, name, country, metadata)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (company_code) DO UPDATE SET country=EXCLUDED.country
                """,
                (code, f"Pilot {code}", country, Json({"marker": MARKER})),
            )
            cur.execute(
                """
                INSERT INTO company_modules(company_code, module_key, enabled, source)
                VALUES (%s,'employment_offers',%s,%s), (%s,'pre_hiring',true,%s),
                       (%s,'onboarding',true,%s), (%s,'compliance',true,%s)
                ON CONFLICT DO NOTHING
                """,
                (
                    code, legacy._offers_enabled, MARKER,
                    code, MARKER,
                    code, MARKER,
                    code, MARKER,
                ),
            )
        conn.commit()


def _seed_application(legacy: LocalLegacy, *, company: str, app_key: str, phone: str, stage: str = "shortlisted") -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO candidates(phone, name, email) VALUES (%s,%s,%s) ON CONFLICT (phone) DO UPDATE SET name=EXCLUDED.name",
                (phone, f"Candidate {phone[-4:]}", f"{phone}@example.invalid"),
            )
            cur.execute(
                """
                INSERT INTO applications(app_key, phone, company_code, position_code, position_title, status, lifecycle_version, candidate_name, candidate_email)
                VALUES (%s,%s,%s,'KW_ROLE','Pilot Role',%s,3,%s,%s)
                ON CONFLICT (app_key) DO UPDATE SET status=EXCLUDED.status, phone=EXCLUDED.phone
                """,
                (app_key, phone, company, stage, f"Candidate {phone[-4:]}", f"{phone}@example.invalid"),
            )
        conn.commit()


def _insert_accepted_offer(legacy: LocalLegacy, *, company: str, app_key: str, legal_name: str) -> str:
    offer_id = str(uuid.uuid4())
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employment_offers(
                  offer_id, company_code, app_key, status, current_version, accepted_version,
                  country_of_employment, employing_legal_entity, document_language, currency,
                  base_salary, allowances_json, proposed_start_date, probation_days,
                  template_id, template_version, template_approval_ref, employer_policy_version,
                  authorized_signatory, configuration_effective_date, responded_at
                )
                VALUES (
                  %s,%s,%s,'accepted',1,1,
                  'KW',%s,'ar','KWD',
                  900.000,'[]'::jsonb,%s,90,
                  'KW-CONTRACT-PILOT','2026.7','COUNSEL-PILOT-1','HR-POLICY-KW-1',
                  'Pilot Signatory','2026-07-01', now()
                )
                """,
                (offer_id, company, app_key, legal_name, date.today() + timedelta(days=14)),
            )
        conn.commit()
    return offer_id


def _atomic_hire_side_effect(
    legacy: LocalLegacy,
    *,
    company: str,
    app_key: str,
    phone: str,
    override: bool = False,
) -> dict:
    """Exercise the same transactional hook used by execute_hire_operation."""
    operation_id = str(uuid.uuid4())
    confirmation_id = str(uuid.uuid4())
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            hire_operations.ensure_hire_schema(cur)
            cur.execute(
                """
                INSERT INTO hire_operations(
                  operation_id, company_code, app_key, idempotency_key, status,
                  expected_from_stage, expected_version, actor_user_id, channel, structured_reason
                ) VALUES (%s,%s,%s,%s,'processing','shortlisted',3,%s,%s,%s)
                """,
                (
                    operation_id,
                    company,
                    app_key,
                    f"idem:{operation_id}",
                    ACTOR,
                    MARKER,
                    Json({"hire_override": override, "override_reason": "pilot override"} if override else {}),
                ),
            )
            hired = {
                "company_code": company,
                "app_key": app_key,
                "phone": phone,
                "candidate_name": f"Candidate {phone[-4:]}",
                "candidate_email": f"{phone}@example.invalid",
                "position_title": "Pilot Role",
                "position_code": "KW_ROLE",
            }
            apply = hire_operations._employee_transaction(legacy, operation_id, confirmation_id)
            result = apply(cur, {"status": "shortlisted"}, hired)
            if result.get("ok"):
                cur.execute(
                    "UPDATE applications SET status='hired', lifecycle_version=lifecycle_version+1 WHERE app_key=%s",
                    (app_key,),
                )
        conn.commit()
    return result


def _canonical_hire(legacy: LocalLegacy, *, company: str, app_key: str, phone: str, override: bool = False) -> dict:
    return _atomic_hire_side_effect(legacy, company=company, app_key=app_key, phone=phone, override=override)


def main() -> int:
    gate = Gate()
    evidence: dict = {"marker": MARKER, "gates": [], "started_at": datetime.now(timezone.utc).isoformat()}

    # --- pure logic (no DB) ---
    gate.check("normalize_residence_from_residency_iqama", kw.normalize_document_type("residency_iqama") == "residence")
    gate.check("normalize_residence_from_residency", kw.normalize_document_type("residency") == "residence")
    gate.check("normalize_residence_canonical", kw.normalize_document_type("residence") == "residence")
    gate.check("no_iqama_canonical_token", "iqama" not in kw.CANONICAL_RESIDENCE)
    gate.check("gov_attachments_blocked_as_master", kw.is_government_process_attachment("police_clearance"))
    gate.check("national_seed_no_residence", "residence" not in kw.compliance_seed_types_for_category("kuwaiti_national"))
    gate.check("expat_seed_has_residence_and_work_permit", set(kw.compliance_seed_types_for_category("article_18_expatriate")) >= {"residence", "work_permit", "civil_id"})

    # --- architecture acceptance (country-neutral core + KW profile scope) ---
    src = Path(kw.__file__).read_text(encoding="utf-8")
    gate.check("arch_core_tables_country_neutral_names", all(t in src for t in (
        "legal_entities", "employment_applicability_snapshots", "employee_identity", "employee_document_metadata"
    )) and "CREATE TABLE IF NOT EXISTS kuwait_" not in src)
    gate.check("arch_no_sql_default_kw_on_legal_entities", "country_code text NOT NULL DEFAULT 'KW'" not in src)
    gate.check("arch_kw_profile_scoped", "COUNTRY_PROFILES" in src and '"KW"' in src and "article_18_expatriate" in src)
    gate.check("arch_no_saudi_uae_country_profiles_enabled", "COUNTRY_PROFILES" in src and "\"SA\"" not in src.split("COUNTRY_PROFILES", 1)[1].split("SOURCE_PATHS", 1)[0] and "\"AE\"" not in src.split("COUNTRY_PROFILES", 1)[1].split("SOURCE_PATHS", 1)[0])
    gate.check("arch_no_leave_eos_pifss_enforcement", not any(x in src.lower() for x in ("enforce_leave", "eos_calculate", "pifss_calculate", "statutory_ot_multiplier", "fine_calculate")))
    gate.check("arch_no_gov_filing_or_api_verify", not any(x in src.lower() for x in ("pam_submit", "moi_file", "paci_verify", "government_api")))
    # KW-only category/PAM guards
    try:
        kw.assert_category_allowed_for_country("article_18_expatriate", "SA")
        sa_cat_blocked = False
    except kw.FoundationError as exc:
        sa_cat_blocked = exc.code == "employee_category_country_mismatch"
    gate.check("arch_article_18_not_universal", sa_cat_blocked)
    try:
        kw.assert_pam_allowed("SA", "PAM-1")
        pam_blocked = False
    except kw.FoundationError as exc:
        pam_blocked = exc.code == "pam_ref_kw_only"
    gate.check("arch_pam_not_universal", pam_blocked)
    gate.check("arch_sa_currency_bootstrap_only", kw.currency_for_country("SA") == "SAR" and "SA" not in kw.COUNTRY_PROFILES)

    try:
        with local_env(offers_enabled=True) as legacy:
            company = "KWPILOT"
            peer = "KWPEER"
            _seed_company(legacy, company)
            _seed_company(legacy, peer)

            # Legal entities
            e1 = kw.create_legal_entity(
                legacy,
                company_code=company,
                registered_name_en="Pilot Trading Co. W.L.L.",
                registered_name_ar="شركة بايلوت للتجارة ذ.م.م.",
                country_code="KW",
                commercial_registration_no="CR-1001",
                licence_no="LIC-55",
                pam_employer_file_no="PAM-777",
                default_currency="KWD",
                is_default=True,
                actor_user_id=ACTOR,
                permissions=FULL_PERMS,
            )
            e2 = kw.create_legal_entity(
                legacy,
                company_code=company,
                registered_name_en="Pilot Services Co. W.L.L.",
                registered_name_ar="شركة بايلوت للخدمات ذ.م.م.",
                country_code="KW",
                default_currency="KWD",
                is_default=False,
                actor_user_id=ACTOR,
                permissions=FULL_PERMS,
            )
            entities = kw.list_legal_entities(legacy, company_code=company, permissions=FULL_PERMS)
            defaults = [x for x in entities if x.get("is_default")]
            gate.check("default_legal_entity_exactly_one", len(defaults) == 1, str([d["legal_entity_id"] for d in defaults]))
            gate.check("arabic_and_english_legal_names", bool(e1.get("registered_name_ar")) and bool(e1.get("registered_name_en")))
            gate.check("multiple_legal_entities_allowed", len(entities) >= 2)
            kw.set_default_legal_entity(legacy, company_code=company, legal_entity_id=str(e2["legal_entity_id"]), actor_user_id=ACTOR, permissions=FULL_PERMS)
            kw.set_default_legal_entity(legacy, company_code=company, legal_entity_id=str(e1["legal_entity_id"]), actor_user_id=ACTOR, permissions=FULL_PERMS)
            entities2 = kw.list_legal_entities(legacy, company_code=company, permissions=FULL_PERMS)
            gate.check("default_entity_uniqueness_after_switch", sum(1 for x in entities2 if x.get("is_default")) == 1)

            # National hire via accepted offer
            app_n = f"{company}-NAT-1"
            phone_n = "965886300101"
            _seed_application(legacy, company=company, app_key=app_n, phone=phone_n)
            offer_n = _insert_accepted_offer(legacy, company=company, app_key=app_n, legal_name=e1["registered_name_en"])
            hire_n = _canonical_hire(legacy, company=company, app_key=app_n, phone=phone_n)
            gate.check("accepted_offer_hire_ok", bool(hire_n.get("ok")), json.dumps(hire_n, default=str)[:300])
            emp_n = f"{company}-{phone_n}"
            snap_n = kw.get_applicability_snapshot(legacy, company_code=company, employee_key=emp_n)
            gate.check("snapshot_created_for_national", bool(snap_n), str(snap_n))
            gate.check("snapshot_from_accepted_offer", (snap_n or {}).get("source_path") == "accepted_offer")
            gate.check("snapshot_binds_legal_entity", str((snap_n or {}).get("legal_entity_id")) == str(e1["legal_entity_id"]))
            gate.check("snapshot_has_offer_version", (snap_n or {}).get("accepted_offer_id") == offer_n and (snap_n or {}).get("accepted_offer_version") == 1)

            kw.set_employee_category(legacy, company_code=company, employee_key=emp_n, category="kuwaiti_national", actor_user_id=ACTOR, permissions=FULL_PERMS)
            kw.stage_ocr_identity_value(legacy, company_code=company, employee_key=emp_n, field_name="civil_id_number", value="289010101234", actor_user_id=ACTOR, permissions=FULL_PERMS)
            ident_pending = kw.get_employee_identity(legacy, company_code=company, employee_key=emp_n, permissions=FULL_PERMS)
            gate.check("ocr_not_authoritative_until_confirm", ident_pending["civil_id_number"]["confirmed"] is False and ident_pending["civil_id_number"]["has_value"] is False)
            kw.confirm_identity_field(legacy, company_code=company, employee_key=emp_n, field_name="civil_id_number", actor_user_id=ACTOR, permissions=FULL_PERMS)
            kw.confirm_identity_field(legacy, company_code=company, employee_key=emp_n, field_name="nationality_country_code", value="KW", actor_user_id=ACTOR, permissions=FULL_PERMS)
            masked = kw.get_employee_identity(legacy, company_code=company, employee_key=emp_n, permissions={kw.IDENTITY_READ})
            full = kw.get_employee_identity(legacy, company_code=company, employee_key=emp_n, permissions={kw.IDENTITY_READ_FULL})
            gate.check("civil_id_masked_by_default", masked["civil_id_number"]["value"] is None and bool(masked["civil_id_number"]["masked"]))
            gate.check("civil_id_full_reveal_privileged", full["civil_id_number"]["value"] == "289010101234")

            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT document_type FROM compliance_documents WHERE employee_key=%s", (emp_n,))
                    ctypes = {r["document_type"] for r in cur.fetchall()}
            gate.check("national_compliance_no_residence_or_work_permit", "residence" not in ctypes and "work_permit" not in ctypes, str(ctypes))

            # Expat hire
            app_e = f"{company}-EXP-1"
            phone_e = "965886300202"
            _seed_application(legacy, company=company, app_key=app_e, phone=phone_e)
            _insert_accepted_offer(legacy, company=company, app_key=app_e, legal_name=e1["registered_name_en"])
            hire_e = _canonical_hire(legacy, company=company, app_key=app_e, phone=phone_e)
            emp_e = f"{company}-{phone_e}"
            gate.check("expat_hire_ok", bool(hire_e.get("ok")), json.dumps(hire_e, default=str)[:300])
            kw.set_employee_category(legacy, company_code=company, employee_key=emp_e, category="article_18_expatriate", actor_user_id=ACTOR, permissions=FULL_PERMS)
            # Re-seed compliance for category (simulate HR classification after hire)
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    legacy._seed_employee_compliance_documents(cur, company, emp_e, employee_category="article_18_expatriate")
                conn.commit()
            meta_r = kw.upsert_document_metadata(
                legacy,
                company_code=company,
                employee_key=emp_e,
                document_type="residence",
                issuing_authority="MOI",
                expiry_date="2027-07-01",
                file_id="file-res-1",
                verification_status="hr_confirmed",
                source="onboarding_upload",
                permissions=FULL_PERMS,
            )
            meta_w = kw.upsert_document_metadata(
                legacy,
                company_code=company,
                employee_key=emp_e,
                document_type="work_permit",
                issuing_authority="PAM",
                expiry_date="2027-07-01",
                file_id="file-wp-1",
                permissions=FULL_PERMS,
            )
            gate.check("expat_residence_metadata_canonical", meta_r["document_type"] == "residence")
            gate.check("expat_work_permit_metadata", meta_w["document_type"] == "work_permit")
            blocked = False
            try:
                kw.upsert_document_metadata(
                    legacy, company_code=company, employee_key=emp_e, document_type="police_clearance", permissions=FULL_PERMS
                )
            except kw.FoundationError as exc:
                blocked = exc.code == "government_process_attachment_not_master"
            gate.check("police_certificate_not_master_metadata", blocked)

            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT document_type FROM compliance_documents WHERE employee_key=%s", (emp_e,))
                    etypes = {r["document_type"] for r in cur.fetchall()}
            gate.check("expat_compliance_has_residence_and_work_permit", {"residence", "work_permit"} <= etypes, str(etypes))

            # Historical residency_iqama readability without destructive merge
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO compliance_documents(employee_key, document_type, label, status, warning_days, company_code)
                        VALUES (%s,'residency_iqama','legacy', 'missing',30,%s)
                        ON CONFLICT DO NOTHING
                        """,
                        (emp_e, company),
                    )
                    cur.execute(
                        "SELECT document_type FROM compliance_documents WHERE employee_key=%s AND document_type='residency_iqama'",
                        (emp_e,),
                    )
                    legacy_row = cur.fetchone()
                conn.commit()
            gate.check("historical_residency_iqama_still_readable", bool(legacy_row))
            gate.check("compat_maps_legacy_to_residence", kw.resolve_compat_document_type("residency_iqama") == "residence")

            # Arabic contract link
            snap_before = kw.get_applicability_snapshot(legacy, company_code=company, employee_key=emp_e)
            linked = kw.link_arabic_contract_to_snapshot(
                legacy,
                company_code=company,
                employee_key=emp_e,
                file_id="file-ar-contract-1",
                template_id="KW-CONTRACT-PILOT",
                template_version="2026.7",
                template_approval_ref="COUNSEL-PILOT-1",
                document_language="ar",
                effective_date="2026-07-15",
                authorized_signatory="Pilot Signatory",
                actor_user_id=ACTOR,
                permissions=FULL_PERMS,
            )
            gate.check("arabic_contract_linked", linked.get("arabic_contract_file_id") == "file-ar-contract-1")
            gate.check(
                "arabic_contract_metadata_complete",
                (linked.get("arabic_contract_metadata") or {}).get("generation") == "upload_only"
                and (linked.get("arabic_contract_metadata") or {}).get("rtl_verified") is True,
            )
            # Immutability of core snapshot hash fields: legal entity / source path unchanged
            gate.check(
                "snapshot_core_immutable_after_contract_link",
                str(linked.get("legal_entity_id")) == str((snap_before or {}).get("legal_entity_id"))
                and linked.get("source_path") == (snap_before or {}).get("source_path"),
            )

            # Replay hire → no second employee / snapshot
            replay = _canonical_hire(legacy, company=company, app_key=app_e, phone=phone_e)
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT count(*) AS c FROM employees WHERE company_code=%s AND app_key=%s", (company, app_e))
                    emp_count = int((cur.fetchone() or {}).get("c") or 0)
                    cur.execute(
                        "SELECT count(*) AS c FROM employment_applicability_snapshots WHERE company_code=%s AND employee_key=%s",
                        (company, emp_e),
                    )
                    snap_count = int((cur.fetchone() or {}).get("c") or 0)
            gate.check("replay_hire_one_employee", emp_count == 1)
            gate.check("replay_hire_one_snapshot", snap_count == 1)
            gate.check("replay_reported_ok_or_idempotent", bool(replay.get("ok")) or bool((replay.get("transition") or {}).get("ok")))

            # Concurrent hire attempt on a fresh app
            app_c = f"{company}-CONC-1"
            phone_c = "965886300303"
            _seed_application(legacy, company=company, app_key=app_c, phone=phone_c)
            _insert_accepted_offer(legacy, company=company, app_key=app_c, legal_name=e1["registered_name_en"])

            def _hire_once():
                try:
                    return _canonical_hire(legacy, company=company, app_key=app_c, phone=phone_c)
                except Exception as exc:
                    return {"ok": False, "error": str(exc)}

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: _hire_once(), range(2)))
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT count(*) AS c FROM employees WHERE company_code=%s AND app_key=%s", (company, app_c))
                    conc_emp = int((cur.fetchone() or {}).get("c") or 0)
                    cur.execute(
                        "SELECT count(*) AS c FROM employment_applicability_snapshots WHERE employee_key=%s",
                        (f"{company}-{phone_c}",),
                    )
                    conc_snap = int((cur.fetchone() or {}).get("c") or 0)
            gate.check("concurrent_hire_single_employee", conc_emp == 1, str(results)[:300])
            gate.check("concurrent_hire_single_snapshot", conc_snap == 1)

            # Tenant isolation
            peer_ent = kw.create_legal_entity(
                legacy,
                company_code=peer,
                registered_name_en="Peer Co",
                registered_name_ar="شركة الند",
                country_code="KW",
                default_currency="KWD",
                is_default=True,
                actor_user_id=ACTOR,
                permissions=FULL_PERMS,
            )
            peer_list = kw.list_legal_entities(legacy, company_code=peer, permissions=FULL_PERMS)
            company_list = kw.list_legal_entities(legacy, company_code=company, permissions=FULL_PERMS)
            gate.check(
                "tenant_isolation_legal_entities",
                all(str(x["company_code"]) == peer for x in peer_list)
                and str(peer_ent["legal_entity_id"]) not in {str(x["legal_entity_id"]) for x in company_list},
            )
            cross_blocked = False
            try:
                kw.get_employee_identity(legacy, company_code=peer, employee_key=emp_n, permissions=FULL_PERMS)
            except kw.FoundationError as exc:
                cross_blocked = exc.code == "identity_not_found"
            gate.check("tenant_isolation_identity", cross_blocked)

            # Future entity change must not rewrite snapshot
            kw.set_default_legal_entity(legacy, company_code=company, legal_entity_id=str(e2["legal_entity_id"]), actor_user_id=ACTOR, permissions=FULL_PERMS)
            snap_after_switch = kw.get_applicability_snapshot(legacy, company_code=company, employee_key=emp_n)
            gate.check(
                "entity_switch_does_not_rewrite_snapshot",
                str((snap_after_switch or {}).get("legal_entity_id")) == str(e1["legal_entity_id"]),
            )

        # Offers-disabled hire path
        with local_env(offers_enabled=False) as legacy2:
            company2 = "KWNOOFF"
            _seed_company(legacy2, company2)
            entity = kw.ensure_default_legal_entity(
                legacy2,
                company_code=company2,
                registered_name_en="No Offer Co",
                registered_name_ar="شركة بدون عرض",
                country_code="KW",
            )
            app_o = f"{company2}-OFF-1"
            phone_o = "965886300404"
            _seed_application(legacy2, company=company2, app_key=app_o, phone=phone_o)
            hire_o = _canonical_hire(legacy2, company=company2, app_key=app_o, phone=phone_o)
            emp_o = f"{company2}-{phone_o}"
            snap_o = kw.get_applicability_snapshot(legacy2, company_code=company2, employee_key=emp_o)
            gate.check("offers_disabled_hire_ok", bool(hire_o.get("ok")), json.dumps(hire_o, default=str)[:300])
            gate.check("offers_disabled_source_path", (snap_o or {}).get("source_path") == "offers_disabled_defaults")
            gate.check("offers_disabled_uses_default_entity", str((snap_o or {}).get("legal_entity_id")) == str(entity["legal_entity_id"]))
            gate.check("offers_disabled_template_from_defaults", (snap_o or {}).get("template_id") == "KW-CONTRACT-PILOT")

        # Hire override path (offers on, no accepted offer)
        with local_env(offers_enabled=True) as legacy3:
            company3 = "KWOVR"
            _seed_company(legacy3, company3)
            kw.ensure_default_legal_entity(
                legacy3,
                company_code=company3,
                registered_name_en="Override Co",
                registered_name_ar="شركة تجاوز",
                country_code="KW",
            )
            app_v = f"{company3}-OVR-1"
            phone_v = "965886300505"
            _seed_application(legacy3, company=company3, app_key=app_v, phone=phone_v)
            hire_v = _canonical_hire(legacy3, company=company3, app_key=app_v, phone=phone_v, override=True)
            snap_v = kw.get_applicability_snapshot(legacy3, company_code=company3, employee_key=f"{company3}-{phone_v}")
            gate.check("hire_override_ok", bool(hire_v.get("ok")), json.dumps(hire_v, default=str)[:300])
            gate.check("hire_override_source_path", (snap_v or {}).get("source_path") == "hire_override")

    except Exception as exc:
        gate.check("matrix_uncaught_exception", False, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-1200:]}")

    evidence["gates"] = gate.rows
    evidence["passed"] = sum(1 for r in gate.rows if r["ok"])
    evidence["failed"] = len(gate.failed)
    evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
    out_dir = Path(__file__).resolve().parents[1] / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamped = out_dir / f"kuwait-first-client-foundation-local-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    stamped.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "kuwait-first-client-foundation-local.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"suite": MARKER, "passed": evidence["passed"], "failed": evidence["failed"], "evidence": str(stamped)}))
    return 0 if not gate.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
