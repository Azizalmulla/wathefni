#!/usr/bin/env python3
"""Wave 1 — Requisitions DB integration prove (staging/canary).

Synthetic canary company only. Process-scoped flags — never systemd-global.
Covers:
  - schema apply idempotent
  - fail-closed gates (flag / allowlist / company setting)
  - create → submit → approve (SoD) → open → link job
  - OPTIONAL job publish gate deny/allow
  - M-02: pre_hiring off → gate not required
  - M-01 style: requisitions alone works without inventing jobs

Run on staging:
  WATHEFNI_ENV=staging ... python3 smoke-test-requisitions-wave1-db.py
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _connect():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("WATHEFNI_DATABASE_URL")
        or os.environ.get("POSTGRES_URL")
        or ""
    ).strip()
    if not url:
        try:
            import app

            return app.db_connect(), True, RealDictCursor
        except Exception as exc:
            raise RuntimeError(f"no_database_url:{exc}") from exc
    conn = psycopg2.connect(url)
    return conn, False, RealDictCursor


def _upsert_module(cur, company: str, module_key: str, enabled: bool) -> None:
    cur.execute(
        """
        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
        VALUES (%s, %s, %s, 'wave1_canary', '{}'::jsonb, now())
        ON CONFLICT (company_code, module_key) DO UPDATE
          SET enabled=EXCLUDED.enabled, updated_at=now(), source='wave1_canary'
        """,
        (company, module_key, enabled),
    )


def main() -> int:
    print("    requisitions wave1 — DB integration prove")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))

    import requisitions as rq

    company = f"REQ{SUFFIX}".upper()
    other = f"REX{SUFFIX}".upper()
    pos_code = f"POS-{SUFFIX}"

    os.environ["WATHEFNI_REQUISITIONS"] = "on"
    os.environ["WATHEFNI_REQUISITIONS_COMPANIES"] = company

    try:
        conn_tuple = _connect()
    except Exception as exc:
        print(f"FAIL DB connect: {exc}")
        return 2
    conn, _via_app, RealDictCursor = conn_tuple

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            rq.ensure_requisitions_schema(cur)
            conn.commit()
            rq.ensure_requisitions_schema(cur)
            conn.commit()
            cur.execute(
                """
                SELECT count(*) AS c FROM information_schema.tables
                 WHERE table_schema='public'
                   AND table_name IN (
                     'requisition_settings',
                     'requisitions',
                     'requisition_job_links',
                     'requisition_events'
                   )
                """
            )
            table_count = int(dict(cur.fetchone())["c"])
            check("migration tables present", table_count == 4, table_count)
            check("migration second apply idempotent", True)

            settings = rq.get_settings(cur, company)
            check("settings default disabled", settings.get("enabled") is False, settings)
            check(
                "gate setting default true",
                settings.get("jobs_require_approved_requisition") is True,
                settings,
            )
            conn.commit()

            gate0 = rq.requisitions_enabled_for_company(cur, company)
            check(
                "gate closed: company setting",
                gate0.get("ok") is False and gate0.get("gate") == "company_setting",
                gate0,
            )

            os.environ["WATHEFNI_REQUISITIONS"] = "off"
            gate_flag = rq.requisitions_enabled_for_company(cur, company)
            check(
                "gate closed: runtime flag",
                gate_flag.get("ok") is False and gate_flag.get("gate") == "runtime_flag",
                gate_flag,
            )

            os.environ["WATHEFNI_REQUISITIONS"] = "on"
            os.environ["WATHEFNI_REQUISITIONS_COMPANIES"] = "NOTTHIS"
            gate_al = rq.requisitions_enabled_for_company(cur, company)
            check(
                "gate closed: allowlist",
                gate_al.get("ok") is False and gate_al.get("gate") == "company_allowlist",
                gate_al,
            )

            os.environ["WATHEFNI_REQUISITIONS_COMPANIES"] = company
            rq.set_settings(cur, company, enabled=True)
            gate_ok = rq.requisitions_enabled_for_company(cur, company)
            check("gate open when all three set", gate_ok.get("ok") is True, gate_ok)
            conn.commit()

            # M-02 prep: enable pre_hiring for gate tests, then toggle
            _upsert_module(cur, company, "pre_hiring", True)
            _upsert_module(cur, company, "requisitions", True)
            conn.commit()

            created = rq.create_requisition(
                cur,
                company_code=company,
                title_en=f"Canary Req {SUFFIX}",
                title_ar="طلب تجريبي",
                department="Engineering",
                headcount=2,
                created_by_user_id="u-creator",
                created_by_phone="96550001111",
                idempotency_key=f"idem-{SUFFIX}",
                submit=False,
            )
            check("create draft", created.get("ok") is True and created.get("requisition", {}).get("status") == "draft", created)
            rid = created["requisition"]["requisition_id"]
            conn.commit()

            replay = rq.create_requisition(
                cur,
                company_code=company,
                title_en="ignored",
                created_by_user_id="u-creator",
                idempotency_key=f"idem-{SUFFIX}",
            )
            check("idempotent create replay", replay.get("ok") is True and replay.get("replayed") is True, replay)
            check("idempotent same id", replay.get("requisition", {}).get("requisition_id") == rid)

            submitted = rq.transition_requisition(
                cur,
                company_code=company,
                requisition_id=rid,
                to_status="pending_approval",
                actor_user_id="u-creator",
                expected_row_version=1,
            )
            check("submit pending_approval", submitted.get("ok") is True, submitted)
            conn.commit()

            self_approve = rq.transition_requisition(
                cur,
                company_code=company,
                requisition_id=rid,
                to_status="approved",
                actor_user_id="u-creator",
                actor_phone="96550001111",
            )
            check(
                "SoD blocks self-approve",
                self_approve.get("ok") is False and self_approve.get("error") == "self_approval_forbidden",
                self_approve,
            )

            approved = rq.transition_requisition(
                cur,
                company_code=company,
                requisition_id=rid,
                to_status="approved",
                actor_user_id="u-approver",
                actor_phone="96559999999",
                expected_row_version=2,
            )
            check("approve by other actor", approved.get("ok") is True, approved)
            check(
                "status approved",
                approved.get("requisition", {}).get("status") == "approved",
                approved,
            )
            conn.commit()

            # Publish gate required when both modules + setting
            need = rq.job_publish_gate_required(cur, company)
            check("publish gate required (both modules)", need.get("required") is True, need)

            denied = rq.assert_job_publish_allowed(cur, company_code=company, position_code=pos_code)
            check(
                "publish denied without link",
                denied.get("allowed") is False and denied.get("error") == "requisition_required",
                denied,
            )

            linked = rq.link_job_to_requisition(
                cur,
                company_code=company,
                requisition_id=rid,
                position_code=pos_code,
                actor_user_id="u-hr",
            )
            check("link job to approved req", linked.get("ok") is True, linked)
            conn.commit()

            allowed = rq.assert_job_publish_allowed(cur, company_code=company, position_code=pos_code)
            check("publish allowed after link", allowed.get("allowed") is True, allowed)
            check("gate reports requisition_id", allowed.get("requisition_id") == rid, allowed)

            opened = rq.transition_requisition(
                cur,
                company_code=company,
                requisition_id=rid,
                to_status="open",
                actor_user_id="u-hr",
            )
            check("approved→open", opened.get("ok") is True, opened)
            conn.commit()

            # M-02: only pre_hiring (requisitions company setting off) → no gate
            rq.set_settings(cur, company, enabled=False)
            _upsert_module(cur, company, "requisitions", False)
            need_off = rq.job_publish_gate_required(cur, company)
            check(
                "M-02 gate off when requisitions disabled",
                need_off.get("required") is False,
                need_off,
            )
            allow_off = rq.assert_job_publish_allowed(cur, company_code=company, position_code="ANY")
            check("M-02 publish allowed without req", allow_off.get("allowed") is True, allow_off)

            # Re-enable for isolation check
            rq.set_settings(cur, company, enabled=True)
            _upsert_module(cur, company, "requisitions", True)
            os.environ["WATHEFNI_REQUISITIONS_COMPANIES"] = company
            cross = rq.create_requisition(
                cur,
                company_code=other,
                title_en="cross",
                created_by_user_id="u-x",
            )
            check(
                "cross-tenant create blocked",
                cross.get("ok") is False
                and cross.get("error")
                in {
                    "requisitions_company_not_allowlisted",
                    "requisitions_company_disabled",
                },
                cross,
            )
            conn.commit()

            # pre_hiring off while requisitions on → gate not required (OPTIONAL)
            _upsert_module(cur, company, "pre_hiring", False)
            need_no_prehire = rq.job_publish_gate_required(cur, company)
            check(
                "gate off when pre_hiring off",
                need_no_prehire.get("required") is False and need_no_prehire.get("reason") == "pre_hiring_off",
                need_no_prehire,
            )
            conn.commit()

            rb = rq.rollback_guidance()
            check("rollback guidance", "WATHEFNI_REQUISITIONS=off" in str(rb.get("runtime")))

        print(f"\n{PASS} passed, {FAIL} failed")
        if FAIL:
            print("REQUISITIONS_WAVE1_DB_FAIL")
            return 1
        print("REQUISITIONS_WAVE1_DB_FULL_PASS")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
