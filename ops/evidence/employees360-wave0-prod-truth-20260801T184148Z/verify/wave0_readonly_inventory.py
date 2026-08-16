#!/usr/bin/env python3
"""Employees 360 Wave 0 — READ-ONLY production truth inventory.

SELECT / information_schema / env inspection only.
Never INSERT/UPDATE/DELETE/DDL. Never merge, delete, constrain, or repair.

Safe to run against production with:
  conn.set_session(readonly=True, autocommit=True)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ENV = Path(os.environ.get("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env"))
if ENV.exists():
    for line in ENV.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import psycopg2
from psycopg2.extras import RealDictCursor

OUT_DIR = Path(os.environ.get("WAVE0_OUT_DIR", "/tmp/employees360-wave0"))
OUT_DIR.mkdir(parents=True, exist_ok=True)

FLAG_NAMES = [
    "WATHEFNI_ORG_HIERARCHY",
    "WATHEFNI_ONBOARDING_HR_MUTATE",
    "WATHEFNI_DOC_UPLOAD",
    "WATHEFNI_ONBOARDING_SEED",
    "WATHEFNI_EMPLOYEE_APP",
    "WATHEFNI_EMPLOYEE_NEXT_ACTIONS",
    "WATHEFNI_LEAVE_BALANCES",
    "WATHEFNI_INBOUND_EMAIL",
    "WATHEFNI_MAILBOX_SYNC",
    "WATHEFNI_ENV",
    "WATHEFNI_ENVIRONMENT",
    "WATHEFNI_EXPECTED_DATABASE_NAME",
    "WATHEFNI_DATABASE_ENVIRONMENT_MARKER",
]

# Soft-hub child tables that hang off (company_code, employee_key) or employee_key alone.
CHILD_TABLES = [
    ("attendance_records", "company_code", "employee_key"),
    ("leave_requests", "company_code", "employee_key"),
    ("shift_assignments", "company_code", "employee_key"),
    ("payroll_timesheets", "company_code", "employee_key"),
    ("employee_availability_requests", "company_code", "employee_key"),
    ("compliance_documents", "company_code", "employee_key"),
    ("onboarding_items", "company_code", "employee_key"),
    ("file_registry", "company_code", "subject_key"),  # subject_type='employee'
    ("employee_sessions", "company_code", "employee_key"),
    ("employee_push_tokens", "company_code", "employee_key"),
    ("employee_app_invites", "company_code", "employee_key"),
    ("employee_status_changes", "company_code", "employee_key"),
    ("employee_org_assignments", "company_code", "employee_key"),
    ("employee_messages", "company_code", "employee_key"),
    ("employee_notification_reads", "company_code", "employee_key"),
    ("employee_availability_events", "company_code", "employee_key"),
    ("employee_documents", "company_code", "employee_key"),
    ("manager_scope_members", "company_code", "employee_key"),
    ("hire_operations", "company_code", "employee_key"),
]


def digits(value: str | None) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def phone_candidates(value: str | None) -> set[str]:
    raw = digits(value)
    out = {raw} if raw else set()
    if len(raw) == 8:
        out.add(f"965{raw}")
    if len(raw) == 11 and raw.startswith("965"):
        out.add(raw[3:])
    return {x for x in out if x}


def canonical_employee_phone(value: str | None) -> str:
    raw = digits(value)
    if len(raw) == 8:
        return f"965{raw}"
    return raw


def redact_phone(value: str | None) -> str:
    d = digits(value)
    if not d:
        return ""
    return f"***{d[-4:]}" if len(d) >= 4 else "***"


def redact_email(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text or "@" not in text:
        return ""
    local, _, domain = text.partition("@")
    return f"{local[:1]}***@{domain}" if local else f"***@{domain}"


def short_hash(value: str | None) -> str:
    return hashlib.sha256(str(value or "").encode()).hexdigest()[:12]


def table_exists(cur, name: str) -> bool:
    cur.execute("SELECT to_regclass(%s) AS reg", (f"public.{name}",))
    return bool((cur.fetchone() or {}).get("reg"))


def column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND column_name=%s
        """,
        (table, column),
    )
    return bool(cur.fetchone())


def q(cur, sql: str, params=None):
    cur.execute(sql, params or ())
    return [dict(r) for r in cur.fetchall()]


def collect_flags() -> dict:
    flags = {}
    # Prefer live orchestrator process environment when available.
    try:
        out = subprocess.check_output(
            ["systemctl", "show", "wathefni-orchestrator", "-p", "Environment", "--value"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        env_map = {}
        for token in out.split():
            if "=" in token:
                k, v = token.split("=", 1)
                env_map[k] = v
        for name in FLAG_NAMES:
            if name in env_map:
                flags[name] = env_map[name]
    except Exception as exc:
        flags["_systemctl_error"] = str(exc)[:200]

    # Fall back to process env / common env files (read-only).
    for name in FLAG_NAMES:
        if name not in flags:
            flags[name] = os.environ.get(name)
    for path in [
        "/etc/wathefni/orchestrator.env",
        "/opt/wathefni/orchestrator/.env",
        "/opt/wathefni/production/orchestrator.env",
        "/root/.openclaw/secrets/wathefni.env",
    ]:
        p = Path(path)
        if not p.exists():
            continue
        try:
            for line in p.read_text().splitlines():
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                if k in FLAG_NAMES and flags.get(k) in (None, ""):
                    flags[k] = v.strip().strip('"').strip("'")
            flags.setdefault("_env_files_read", []).append(path)
        except Exception:
            pass
    return flags


def collect_backup_readiness() -> dict:
    info: dict = {"paths_checked": [], "recent_backups": [], "weekly_present": False}
    roots = [
        Path("/opt/wathefni/backups"),
        Path("/opt/wathefni/backups/weekly"),
        Path("/opt/wathefni/production-evidence"),
    ]
    for root in roots:
        info["paths_checked"].append({"path": str(root), "exists": root.exists()})
        if not root.exists():
            continue
        if root.name == "weekly" or (root / "weekly").exists():
            info["weekly_present"] = True
        try:
            entries = sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:15]
            for e in entries:
                st = e.stat()
                info["recent_backups"].append(
                    {
                        "path": str(e),
                        "is_dir": e.is_dir(),
                        "mtime_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                        "size_bytes": st.st_size if e.is_file() else None,
                    }
                )
        except Exception as exc:
            info["error"] = str(exc)[:300]
    # pg dump markers if any
    try:
        out = subprocess.check_output(
            ["bash", "-lc", "ls -lt /opt/wathefni/backups/weekly 2>/dev/null | head -8"],
            text=True,
        )
        info["weekly_ls"] = out
        info["weekly_present"] = bool(out.strip())
    except Exception:
        pass
    return info


def main() -> int:
    dsn = os.environ.get("WATHEFNI_DATABASE_URL")
    if not dsn:
        print("FATAL: WATHEFNI_DATABASE_URL missing", file=sys.stderr)
        return 2

    report: dict = {
        "stamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "mode": "read_only",
        "mutated": False,
        "database_name_hint": os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME"),
        "flags": collect_flags(),
        "backup_readiness": collect_backup_readiness(),
    }

    conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()

    # Confirm read-only + DB identity
    dbinfo = q(
        cur,
        """
        SELECT current_database() AS database,
               current_user AS db_user,
               inet_server_addr()::text AS server_addr,
               pg_is_in_recovery() AS is_replica,
               now() AS db_now
        """,
    )[0]
    report["database"] = {
        "database": dbinfo["database"],
        "db_user": dbinfo["db_user"],
        "server_addr": dbinfo["server_addr"],
        "is_replica": bool(dbinfo["is_replica"]),
        "db_now": str(dbinfo["db_now"]),
        "readonly_session": True,
    }

    # ---- Schema: employees + constraints/indexes ----
    schema: dict = {"employees": {}, "related": {}}
    if table_exists(cur, "employees"):
        schema["employees"]["columns"] = q(
            cur,
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='employees'
            ORDER BY ordinal_position
            """,
        )
        schema["employees"]["constraints"] = q(
            cur,
            """
            SELECT tc.constraint_name, tc.constraint_type,
                   string_agg(kcu.column_name, ',' ORDER BY kcu.ordinal_position) AS columns
            FROM information_schema.table_constraints tc
            LEFT JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema
            WHERE tc.table_schema='public' AND tc.table_name='employees'
            GROUP BY tc.constraint_name, tc.constraint_type
            ORDER BY tc.constraint_type, tc.constraint_name
            """,
        )
        schema["employees"]["indexes"] = q(
            cur,
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname='public' AND tablename='employees'
            ORDER BY indexname
            """,
        )
        # Unique on (company_code, phone)?
        uniq_phone = q(
            cur,
            """
            SELECT i.relname AS index_name, pg_get_indexdef(i.oid) AS indexdef
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname='public' AND t.relname='employees' AND ix.indisunique
            """,
        )
        schema["employees"]["unique_indexes"] = uniq_phone
        schema["employees"]["has_unique_company_phone"] = any(
            "phone" in (r.get("indexdef") or "").lower() and "company_code" in (r.get("indexdef") or "").lower()
            for r in uniq_phone
        )
        schema["employees"]["row_count"] = q(cur, "SELECT count(*)::bigint AS n FROM employees")[0]["n"]

    for t in [
        "employee_status_changes",
        "employee_org_assignments",
        "manager_scopes",
        "company_branches",
        "company_teams",
        "dashboard_user_permission_grants",
        "dashboard_users",
        "company_modules",
        "file_registry",
        "onboarding_items",
        "compliance_documents",
        "employee_identity",
        "hire_operations",
    ]:
        if table_exists(cur, t):
            schema["related"][t] = {
                "exists": True,
                "row_count": q(cur, f'SELECT count(*)::bigint AS n FROM "{t}"')[0]["n"],
                "columns": [
                    c["column_name"]
                    for c in q(
                        cur,
                        """
                        SELECT column_name FROM information_schema.columns
                        WHERE table_schema='public' AND table_name=%s
                        ORDER BY ordinal_position
                        """,
                        (t,),
                    )
                ],
            }
        else:
            schema["related"][t] = {"exists": False}
    report["schema"] = schema

    # ---- Modules / entitlements ----
    modules = []
    if table_exists(cur, "company_modules"):
        modules = q(
            cur,
            """
            SELECT company_code, module_key, enabled,
                   COALESCE(source::text, '') AS source
            FROM company_modules
            ORDER BY company_code, module_key
            """,
        )
    companies = []
    if table_exists(cur, "companies"):
        company_cols = {
            c["column_name"]
            for c in q(
                cur,
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='public' AND table_name='companies'
                """,
            )
        }
        select_cols = ["company_code"]
        if "name" in company_cols:
            select_cols.append("name")
        if "status" in company_cols:
            select_cols.append("status")
        companies = q(cur, f"SELECT {', '.join(select_cols)} FROM companies ORDER BY company_code")
    report["tenants"] = {
        "companies": companies,
        "modules": modules,
        "people_modules_enabled": [
            m for m in modules
            if m.get("enabled") and m.get("module_key") in {
                "onboarding", "compliance", "attendance", "shifts", "leave", "payroll", "employee_app"
            }
        ],
    }

    # ---- Employee inventory ----
    employees = q(
        cur,
        """
        SELECT company_code, employee_key, phone, email, name, app_key,
               employment_status, onboarding_status, position_title,
               start_date, created_at, updated_at,
               COALESCE(profile->>'department', '') AS department,
               COALESCE(raw_json->>'source', profile->>'source', '') AS source_hint
        FROM employees
        ORDER BY company_code, employee_key
        """,
    ) if table_exists(cur, "employees") else []

    status_dist: dict = defaultdict(lambda: defaultdict(int))
    phone_format: dict = defaultdict(int)
    key_phone_mismatch = []
    reused_phone_keys = []
    for e in employees:
        st = str(e.get("employment_status") or "").strip().lower() or "<null_or_blank>"
        status_dist[e["company_code"]][st] += 1
        status_dist["_all"][st] += 1
        d = digits(e.get("phone"))
        if not d:
            phone_format["empty"] += 1
        elif len(d) == 8:
            phone_format["local_8"] += 1
        elif len(d) == 11 and d.startswith("965"):
            phone_format["kw_965"] += 1
        else:
            phone_format["other"] += 1

        # employee_key derived from old/reused phone?
        key = str(e.get("employee_key") or "")
        expected_from_stored = f"{e['company_code']}-{d}" if d else None
        expected_from_canon = f"{e['company_code']}-{canonical_employee_phone(d)}" if d else None
        key_suffix = key.split("-", 1)[1] if "-" in key else ""
        if d and key_suffix and key_suffix != d:
            reused_phone_keys.append(
                {
                    "company_code": e["company_code"],
                    "employee_key": key,
                    "phone_redacted": redact_phone(d),
                    "phone_format": "local_8" if len(d) == 8 else ("kw_965" if len(d) == 11 and d.startswith("965") else "other"),
                    "key_phone_digits_len": len(digits(key_suffix)),
                    "stored_phone_digits_len": len(d),
                    "employment_status": st,
                    "classification": "key_suffix_ne_stored_phone",
                }
            )
        if expected_from_stored and key != expected_from_stored and key != expected_from_canon:
            # already covered; keep compact sample
            pass
        if d and key == expected_from_stored and len(d) == 8:
            key_phone_mismatch.append(
                {
                    "company_code": e["company_code"],
                    "employee_key": key,
                    "phone_redacted": redact_phone(d),
                    "classification": "key_uses_local_8_not_canonical_965",
                    "employment_status": st,
                }
            )

    report["employee_inventory"] = {
        "total": len(employees),
        "by_company": {
            c: sum(1 for e in employees if e["company_code"] == c)
            for c in sorted({e["company_code"] for e in employees})
        },
        "status_distribution": {k: dict(v) for k, v in status_dist.items()},
        "invalid_or_unknown_statuses": {
            k: v for k, v in status_dist["_all"].items()
            if k not in {"active", "left"}
        },
        "phone_format_counts": dict(phone_format),
        "keys_using_local_8_suffix": {
            "count": len(key_phone_mismatch),
            "samples": key_phone_mismatch[:50],
        },
        "keys_suffix_ne_stored_phone": {
            "count": len(reused_phone_keys),
            "samples": reused_phone_keys[:50],
        },
    }

    # ---- Duplicate classification (local vs 965, exact phone, email) ----
    # Exact (company, phone)
    exact_phone_dups = q(
        cur,
        """
        SELECT company_code, phone, count(*)::bigint AS n,
               array_agg(employee_key ORDER BY employee_key) AS employee_keys,
               array_agg(COALESCE(employment_status,'') ORDER BY employee_key) AS statuses
        FROM employees
        WHERE phone IS NOT NULL AND phone <> ''
        GROUP BY company_code, phone
        HAVING count(*) > 1
        """,
    ) if table_exists(cur, "employees") else []

    # Canonical-collision: different stored phones / keys that share candidate set
    by_company: dict[str, list] = defaultdict(list)
    for e in employees:
        by_company[e["company_code"]].append(e)

    canonical_collisions = []
    for company, rows in by_company.items():
        buckets: dict[str, list] = defaultdict(list)
        for e in rows:
            d = digits(e.get("phone"))
            if not d:
                continue
            # bucket by sorted candidate frozenset represented by canonical form
            canon = canonical_employee_phone(d)
            # also include key-derived phone candidates
            key_suffix = str(e.get("employee_key") or "").split("-", 1)
            key_digits = digits(key_suffix[1]) if len(key_suffix) == 2 else ""
            for token in phone_candidates(d) | phone_candidates(key_digits) | {canon}:
                # Use primary bucket = canonical of any 8/965 form
                buckets[canonical_employee_phone(token)].append(e)
        seen_pairs = set()
        for canon, group in buckets.items():
            # unique by employee_key
            uniq = {g["employee_key"]: g for g in group}
            if len(uniq) < 2:
                continue
            keys = tuple(sorted(uniq.keys()))
            if keys in seen_pairs:
                continue
            seen_pairs.add(keys)
            phones = sorted({digits(g.get("phone")) for g in uniq.values()})
            formats = sorted(
                {
                    ("local_8" if len(p) == 8 else "kw_965" if len(p) == 11 and p.startswith("965") else "other")
                    for p in phones if p
                }
            )
            classification = "local_vs_965" if {"local_8", "kw_965"} <= set(formats) or (
                len(phones) >= 2 and any(len(p) == 8 for p in phones) and any(len(p) == 11 and p.startswith("965") for p in phones)
            ) else "canonical_bucket_multi_row"
            canonical_collisions.append(
                {
                    "company_code": company,
                    "canonical_phone_redacted": redact_phone(canon),
                    "canonical_hash": short_hash(canon),
                    "employee_count": len(uniq),
                    "employee_keys": list(keys),
                    "phone_formats": formats,
                    "statuses": [str(uniq[k].get("employment_status") or "") for k in keys],
                    "emails_redacted": [redact_email(uniq[k].get("email")) for k in keys],
                    "classification": classification,
                    "active_count": sum(1 for k in keys if str(uniq[k].get("employment_status") or "active").lower() != "left"),
                    "left_count": sum(1 for k in keys if str(uniq[k].get("employment_status") or "").lower() == "left"),
                }
            )

    # Email duplicates across active/left
    email_dups = []
    email_buckets: dict[tuple, list] = defaultdict(list)
    for e in employees:
        em = str(e.get("email") or "").strip().lower()
        if not em:
            continue
        email_buckets[(e["company_code"], em)].append(e)
    for (company, em), group in email_buckets.items():
        if len(group) < 2:
            continue
        email_dups.append(
            {
                "company_code": company,
                "email_redacted": redact_email(em),
                "email_hash": short_hash(em),
                "employee_count": len(group),
                "employee_keys": [g["employee_key"] for g in group],
                "statuses": [str(g.get("employment_status") or "") for g in group],
                "classification": "repeated_email",
            }
        )

    # Exact phone repeated including across active/left (already in exact_phone_dups)
    exact_phone_classified = []
    for row in exact_phone_dups:
        statuses = [str(s or "").lower() for s in (row.get("statuses") or [])]
        exact_phone_classified.append(
            {
                "company_code": row["company_code"],
                "phone_redacted": redact_phone(row.get("phone")),
                "phone_hash": short_hash(digits(row.get("phone"))),
                "n": int(row["n"]),
                "employee_keys": list(row.get("employee_keys") or []),
                "statuses": statuses,
                "classification": "exact_phone_duplicate",
                "cross_status": len(set(statuses)) > 1,
            }
        )

    report["duplicates"] = {
        "exact_phone": {
            "count_groups": len(exact_phone_classified),
            "groups": exact_phone_classified,
        },
        "local_vs_965_or_canonical_collision": {
            "count_groups": len(canonical_collisions),
            "groups": canonical_collisions,
            "local_vs_965_count": sum(1 for g in canonical_collisions if g["classification"] == "local_vs_965"),
        },
        "repeated_email": {
            "count_groups": len(email_dups),
            "groups": email_dups[:100],
        },
        "summary": {
            "tenants_with_any_duplicate_signal": sorted(
                {
                    *(g["company_code"] for g in exact_phone_classified),
                    *(g["company_code"] for g in canonical_collisions),
                    *(g["company_code"] for g in email_dups),
                }
            ),
            "employees_in_local_vs_965_groups": sum(
                g["employee_count"] for g in canonical_collisions if g["classification"] == "local_vs_965"
            ),
        },
    }

    # ---- Former employees linked by recruiting while still left ----
    left_with_app_key = []
    if table_exists(cur, "employees"):
        for e in employees:
            if str(e.get("employment_status") or "").lower() == "left" and e.get("app_key"):
                left_with_app_key.append(
                    {
                        "company_code": e["company_code"],
                        "employee_key": e["employee_key"],
                        "app_key": e["app_key"],
                        "phone_redacted": redact_phone(e.get("phone")),
                        "updated_at": str(e.get("updated_at")),
                    }
                )
    # hire_operations completed pointing at left employees
    hire_left = []
    if table_exists(cur, "hire_operations") and column_exists(cur, "hire_operations", "employee_key"):
        hire_left = q(
            cur,
            """
            SELECT h.company_code, h.operation_id, h.employee_key, h.status AS hire_status,
                   e.employment_status, e.app_key
            FROM hire_operations h
            JOIN employees e
              ON e.company_code = h.company_code AND e.employee_key = h.employee_key
            WHERE lower(COALESCE(e.employment_status,'')) = 'left'
            ORDER BY h.company_code, h.employee_key
            LIMIT 200
            """,
        )
    report["rehire_left_linkage"] = {
        "left_employees_with_app_key": {
            "count": len(left_with_app_key),
            "samples": left_with_app_key[:50],
        },
        "hire_operations_pointing_at_left_employees": {
            "count": len(hire_left),
            "samples": [
                {
                    "company_code": r["company_code"],
                    "employee_key": r["employee_key"],
                    "hire_status": r.get("hire_status"),
                    "employment_status": r.get("employment_status"),
                    "app_key": r.get("app_key"),
                }
                for r in hire_left[:50]
            ],
        },
    }

    # ---- Orphans across every post-hire table ----
    orphans = {}
    for table, company_col, key_col in CHILD_TABLES:
        if not table_exists(cur, table):
            orphans[table] = {"present": False}
            continue
        has_company = column_exists(cur, table, company_col)
        has_key = column_exists(cur, table, key_col)
        if not has_key:
            orphans[table] = {"present": True, "skipped": "missing_key_column", "key_col": key_col}
            continue
        extra = ""
        params: list = []
        if table == "file_registry":
            if column_exists(cur, table, "subject_type"):
                extra = " AND t.subject_type='employee'"
        if has_company:
            sql = f"""
                SELECT count(*)::bigint AS orphans
                FROM {table} t
                LEFT JOIN employees e
                  ON e.employee_key = t.{key_col}
                 AND e.company_code = t.{company_col}
                WHERE t.{key_col} IS NOT NULL AND t.{key_col} <> ''
                  AND e.employee_key IS NULL
                  {extra}
            """
            cross_sql = f"""
                SELECT count(*)::bigint AS cross_tenant
                FROM {table} t
                JOIN employees e ON e.employee_key = t.{key_col}
                WHERE t.{company_col} IS NOT NULL
                  AND e.company_code IS DISTINCT FROM t.{company_col}
                  {extra}
            """
        else:
            sql = f"""
                SELECT count(*)::bigint AS orphans
                FROM {table} t
                LEFT JOIN employees e ON e.employee_key = t.{key_col}
                WHERE t.{key_col} IS NOT NULL AND t.{key_col} <> ''
                  AND e.employee_key IS NULL
                  {extra}
            """
            cross_sql = None
        orphan_n = int(q(cur, sql)[0]["orphans"])
        samples = []
        if orphan_n:
            sample_sql = f"""
                SELECT DISTINCT t.{company_col if has_company else "NULL::text"} AS company_code,
                       t.{key_col} AS employee_key
                FROM {table} t
                LEFT JOIN employees e
                  ON e.employee_key = t.{key_col}
                 {"AND e.company_code = t." + company_col if has_company else ""}
                WHERE t.{key_col} IS NOT NULL AND t.{key_col} <> ''
                  AND e.employee_key IS NULL
                  {extra}
                LIMIT 10
            """
            samples = q(cur, sample_sql)
        cross_n = int(q(cur, cross_sql)[0]["cross_tenant"]) if cross_sql else None
        orphans[table] = {
            "present": True,
            "orphans": orphan_n,
            "cross_tenant_key_collisions": cross_n,
            "samples": samples,
            "classification": (
                "orphan_employee_key"
                if orphan_n
                else ("cross_tenant" if cross_n else "clean")
            ),
        }
    # integrity scan coverage gap note
    covered_by_app_scan = {
        "attendance_records", "leave_requests", "shift_assignments",
        "payroll_timesheets", "employee_availability_requests", "compliance_documents",
    }
    report["orphans"] = {
        "tables": orphans,
        "total_orphan_rows": sum(int(v.get("orphans") or 0) for v in orphans.values() if v.get("present")),
        "tables_with_orphans": [t for t, v in orphans.items() if v.get("present") and int(v.get("orphans") or 0) > 0],
        "not_in_app_INTEGRITY_CHILD_TABLES": sorted(
            t for t in orphans if orphans[t].get("present") and t not in covered_by_app_scan
        ),
    }

    # ---- Grants + navigation/API mismatch risk ----
    grants = []
    if table_exists(cur, "dashboard_user_permission_grants"):
        grants = q(
            cur,
            """
            SELECT g.company_code, g.user_id, g.permission, g.status,
                   u.email, u.role, u.status AS user_status, u.phone
            FROM dashboard_user_permission_grants g
            LEFT JOIN dashboard_users u
              ON u.company_code=g.company_code AND u.user_id=g.user_id
            WHERE g.permission LIKE 'employees.%%'
            ORDER BY g.company_code, g.permission, g.user_id
            """,
        )
    users = q(
        cur,
        """
        SELECT company_code, user_id, email, role, status, phone
        FROM dashboard_users
        WHERE lower(COALESCE(status,'')) = 'active'
        ORDER BY company_code, role, email
        """,
    ) if table_exists(cur, "dashboard_users") else []

    people_enabled_companies = {
        m["company_code"]
        for m in modules
        if m.get("enabled") and m.get("module_key") in {
            "onboarding", "compliance", "attendance", "shifts", "leave", "payroll", "employee_app"
        }
    }
    read_grants = {
        (g["company_code"], g["user_id"])
        for g in grants
        if g.get("permission") == "employees.read" and str(g.get("status") or "").lower() == "active"
    }
    manage_grants = {
        (g["company_code"], g["user_id"])
        for g in grants
        if g.get("permission") == "employees.manage" and str(g.get("status") or "").lower() == "active"
    }
    approve_grants = {
        (g["company_code"], g["user_id"])
        for g in grants
        if g.get("permission") == "employees.status.approve" and str(g.get("status") or "").lower() == "active"
    }

    nav_api_mismatch = []
    for u in users:
        if u["company_code"] not in people_enabled_companies:
            continue
        if u["role"] in {"owner", "hr_admin", "admin", "manager", "team_manager"}:
            has_read = (u["company_code"], u["user_id"]) in read_grants
            if not has_read:
                nav_api_mismatch.append(
                    {
                        "company_code": u["company_code"],
                        "user_id": u["user_id"],
                        "email_redacted": redact_email(u.get("email")),
                        "role": u.get("role"),
                        "classification": "people_module_enabled_but_no_employees_read_grant",
                        "risk": "Nav soft-gate may show Employees while API 403s",
                    }
                )

    dual_manage_approve = []
    for pair in sorted(manage_grants & approve_grants):
        company, user_id = pair
        u = next((x for x in users if x["company_code"] == company and x["user_id"] == user_id), None)
        dual_manage_approve.append(
            {
                "company_code": company,
                "user_id": user_id,
                "email_redacted": redact_email(u.get("email") if u else None),
                "role": u.get("role") if u else None,
                "classification": "holds_employees_manage_and_status_approve",
                "canary_self_approval_risk": True,
            }
        )

    report["permissions"] = {
        "employee_grants_active": [
            {
                "company_code": g["company_code"],
                "user_id": g["user_id"],
                "permission": g["permission"],
                "status": g["status"],
                "role": g.get("role"),
                "email_redacted": redact_email(g.get("email")),
                "user_status": g.get("user_status"),
            }
            for g in grants
            if str(g.get("status") or "").lower() == "active"
        ],
        "counts": {
            "employees_read": len(read_grants),
            "employees_manage": len(manage_grants),
            "employees_status_approve": len(approve_grants),
            "dual_manage_and_approve": len(dual_manage_approve),
        },
        "dual_manage_and_approve_users": dual_manage_approve,
        "nav_api_mismatch_candidates": nav_api_mismatch,
        "people_enabled_companies": sorted(people_enabled_companies),
    }

    # ---- Manager scopes + out-of-scope mutation risk ----
    scopes = []
    scope_members = []
    if table_exists(cur, "manager_scopes"):
        scopes = q(
            cur,
            """
            SELECT scope_id, company_code, manager_phone, scope_type,
                   branch_key, team_key, dashboard_user_id, is_active, updated_at
            FROM manager_scopes
            ORDER BY company_code, manager_phone, scope_type
            """,
        )
    if table_exists(cur, "manager_scope_members"):
        scope_members = q(
            cur,
            """
            SELECT scope_id, company_code, employee_key
            FROM manager_scope_members
            """,
        )
    members_by_scope: dict = defaultdict(list)
    for m in scope_members:
        members_by_scope[str(m.get("scope_id"))].append(m.get("employee_key"))

    assignments_n = 0
    if table_exists(cur, "employee_org_assignments"):
        assignments_n = int(q(cur, "SELECT count(*)::bigint AS n FROM employee_org_assignments")[0]["n"])

    scoped_managers_with_manage = []
    for g in grants:
        if g.get("permission") != "employees.manage" or str(g.get("status") or "").lower() != "active":
            continue
        phone = digits(g.get("phone"))
        uid = str(g.get("user_id") or "")
        matched = []
        for s in scopes:
            if str(s.get("company_code")) != g["company_code"]:
                continue
            if not s.get("is_active"):
                continue
            same_user = str(s.get("dashboard_user_id") or "") == uid and uid != ""
            same_phone = bool(phone_candidates(s.get("manager_phone")) & phone_candidates(phone))
            if same_user or same_phone:
                matched.append(s)
        if matched:
            restricted = any(str(s.get("scope_type") or "").lower() != "company" for s in matched)
            scoped_managers_with_manage.append(
                {
                    "company_code": g["company_code"],
                    "user_id": g["user_id"],
                    "email_redacted": redact_email(g.get("email")),
                    "role": g.get("role"),
                    "manager_phone_redacted": redact_phone(phone),
                    "scopes": [
                        {
                            "scope_id": str(s.get("scope_id")),
                            "scope_type": s.get("scope_type"),
                            "branch_key": s.get("branch_key"),
                            "team_key": s.get("team_key"),
                            "direct_key_count": len(members_by_scope.get(str(s.get("scope_id")), [])),
                        }
                        for s in matched
                    ],
                    "restricted": restricted,
                    "mutation_scope_gap": restricted,
                    "classification": (
                        "scoped_manager_with_employees_manage_can_mutate_out_of_scope_via_api"
                        if restricted
                        else "company_scoped_or_unrestricted_manager_with_manage"
                    ),
                }
            )

    report["manager_scopes"] = {
        "scope_rows": len(scopes),
        "active_scopes": sum(1 for s in scopes if s.get("is_active")),
        "manager_scope_members": len(scope_members),
        "by_type": {},
        "employee_org_assignments": assignments_n,
        "scoped_managers_with_employees_manage": scoped_managers_with_manage,
        "out_of_scope_mutation_risk_count": sum(
            1 for r in scoped_managers_with_manage if r.get("mutation_scope_gap")
        ),
        "samples_active_scopes": [
            {
                "company_code": s["company_code"],
                "scope_id": str(s.get("scope_id")),
                "scope_type": s.get("scope_type"),
                "manager_phone_redacted": redact_phone(s.get("manager_phone")),
                "branch_key": s.get("branch_key"),
                "team_key": s.get("team_key"),
                "dashboard_user_id": s.get("dashboard_user_id"),
                "direct_key_count": len(members_by_scope.get(str(s.get("scope_id")), [])),
                "is_active": s.get("is_active"),
            }
            for s in scopes if s.get("is_active")
        ][:50],
    }
    type_counts: dict = defaultdict(int)
    for s in scopes:
        if s.get("is_active"):
            type_counts[str(s.get("scope_type") or "")] += 1
    report["manager_scopes"]["by_type"] = dict(type_counts)

    # ---- self_approved_internal_canary usage ----
    canary = {"table_present": table_exists(cur, "employee_status_changes"), "rows": []}
    if canary["table_present"]:
        cols = set(schema["related"].get("employee_status_changes", {}).get("columns") or [])
        if "approval_mode" in cols:
            rows = q(
                cur,
                """
                SELECT company_code, employee_key, approval_mode,
                       requester_user_id, approver_user_id,
                       previous_status, requested_status,
                       verification_status, created_at
                FROM employee_status_changes
                WHERE approval_mode = 'self_approved_internal_canary'
                ORDER BY created_at DESC NULLS LAST
                LIMIT 500
                """,
            )
            by_company: dict = defaultdict(int)
            for r in rows:
                by_company[r["company_code"]] += 1
            canary["total_matching_sampled"] = len(rows)
            canary["by_company"] = dict(by_company)
            canary["outside_wathefni"] = {
                k: v for k, v in by_company.items() if str(k).upper() != "WATHEFNI"
            }
            canary["samples"] = [
                {
                    "company_code": r["company_code"],
                    "employee_key": r["employee_key"],
                    "approval_mode": r["approval_mode"],
                    "requester_user_id": r.get("requester_user_id"),
                    "approver_user_id": r.get("approver_user_id"),
                    "previous_status": r.get("previous_status"),
                    "requested_status": r.get("requested_status"),
                    "verification_status": r.get("verification_status"),
                    "created_at": str(r.get("created_at")),
                    "outside_wathefni": str(r.get("company_code") or "").upper() != "WATHEFNI",
                }
                for r in rows[:50]
            ]
            # Full count
            canary["total_count"] = int(
                q(
                    cur,
                    "SELECT count(*)::bigint AS n FROM employee_status_changes WHERE approval_mode='self_approved_internal_canary'",
                )[0]["n"]
            )
            canary["outside_wathefni_count"] = int(
                q(
                    cur,
                    """
                    SELECT count(*)::bigint AS n FROM employee_status_changes
                    WHERE approval_mode='self_approved_internal_canary'
                      AND upper(company_code) <> 'WATHEFNI'
                    """,
                )[0]["n"]
            )
        else:
            canary["error"] = "approval_mode column missing"
        # also audit action_results if present
        if table_exists(cur, "action_results"):
            ar = q(
                cur,
                """
                SELECT company_code, count(*)::bigint AS n
                FROM action_results
                WHERE action_type IN ('employee_marked_left','employee_reactivated')
                GROUP BY company_code
                ORDER BY n DESC
                """,
            )
            canary["status_action_results_by_company"] = ar
    report["self_approved_internal_canary"] = canary

    # ---- Immediate risk assessment ----
    immediate = []
    if report["duplicates"]["local_vs_965_or_canonical_collision"]["local_vs_965_count"]:
        immediate.append(
            {
                "severity": "P0",
                "signal": "local_vs_965_duplicate_groups",
                "count": report["duplicates"]["local_vs_965_or_canonical_collision"]["local_vs_965_count"],
                "active_customer_data_at_risk": report["duplicates"]["summary"]["employees_in_local_vs_965_groups"] > 0,
            }
        )
    if report["manager_scopes"]["out_of_scope_mutation_risk_count"]:
        immediate.append(
            {
                "severity": "P0",
                "signal": "scoped_managers_with_employees_manage",
                "count": report["manager_scopes"]["out_of_scope_mutation_risk_count"],
                "active_customer_data_at_risk": True,
                "note": "Code gap confirmed; exploitation requires knowing out-of-scope employee_key",
            }
        )
    if canary.get("outside_wathefni_count"):
        immediate.append(
            {
                "severity": "P0",
                "signal": "self_approved_internal_canary_outside_WATHEFNI",
                "count": canary.get("outside_wathefni_count"),
                "active_customer_data_at_risk": True,
            }
        )
    elif canary.get("total_count"):
        immediate.append(
            {
                "severity": "P0",
                "signal": "self_approved_internal_canary_used_on_WATHEFNI",
                "count": canary.get("total_count"),
                "active_customer_data_at_risk": False,
                "note": "Internal-only usage observed; server still does not tenant-restrict the mode",
            }
        )
    if report["rehire_left_linkage"]["hire_operations_pointing_at_left_employees"]["count"]:
        immediate.append(
            {
                "severity": "P1",
                "signal": "hire_linked_left_employees",
                "count": report["rehire_left_linkage"]["hire_operations_pointing_at_left_employees"]["count"],
                "active_customer_data_at_risk": True,
            }
        )
    if report["orphans"]["total_orphan_rows"]:
        immediate.append(
            {
                "severity": "P1",
                "signal": "orphan_employee_linked_rows",
                "count": report["orphans"]["total_orphan_rows"],
                "tables": report["orphans"]["tables_with_orphans"],
                "active_customer_data_at_risk": True,
            }
        )
    if report["permissions"]["nav_api_mismatch_candidates"]:
        immediate.append(
            {
                "severity": "P2",
                "signal": "nav_api_grant_mismatch",
                "count": len(report["permissions"]["nav_api_mismatch_candidates"]),
                "active_customer_data_at_risk": False,
            }
        )

    report["immediate_risk"] = {
        "signals": immediate,
        "any_active_customer_data_at_immediate_risk": any(
            s.get("active_customer_data_at_risk") for s in immediate if s.get("severity") in {"P0", "P1"}
        ),
    }

    # Write outputs
    raw_path = OUT_DIR / "wave0-inventory.json"
    raw_path.write_text(json.dumps(report, indent=2, default=str) + "\n")
    summary = {
        "stamp_utc": report["stamp_utc"],
        "database": report["database"]["database"],
        "employee_total": report["employee_inventory"]["total"],
        "status_distribution": report["employee_inventory"]["status_distribution"].get("_all", {}),
        "invalid_statuses": report["employee_inventory"]["invalid_or_unknown_statuses"],
        "phone_formats": report["employee_inventory"]["phone_format_counts"],
        "exact_phone_dup_groups": report["duplicates"]["exact_phone"]["count_groups"],
        "local_vs_965_groups": report["duplicates"]["local_vs_965_or_canonical_collision"]["local_vs_965_count"],
        "email_dup_groups": report["duplicates"]["repeated_email"]["count_groups"],
        "keys_suffix_ne_phone": report["employee_inventory"]["keys_suffix_ne_stored_phone"]["count"],
        "keys_local_8": report["employee_inventory"]["keys_using_local_8_suffix"]["count"],
        "orphan_total": report["orphans"]["total_orphan_rows"],
        "orphan_tables": report["orphans"]["tables_with_orphans"],
        "dual_manage_approve": report["permissions"]["counts"]["dual_manage_and_approve"],
        "nav_api_mismatch": len(report["permissions"]["nav_api_mismatch_candidates"]),
        "scoped_manage_risk": report["manager_scopes"]["out_of_scope_mutation_risk_count"],
        "canary_total": canary.get("total_count"),
        "canary_outside_wathefni": canary.get("outside_wathefni_count"),
        "left_with_app_key": report["rehire_left_linkage"]["left_employees_with_app_key"]["count"],
        "hire_ops_on_left": report["rehire_left_linkage"]["hire_operations_pointing_at_left_employees"]["count"],
        "has_unique_company_phone": schema["employees"].get("has_unique_company_phone"),
        "flags": report["flags"],
        "immediate_risk": report["immediate_risk"],
        "mutated": False,
    }
    (OUT_DIR / "wave0-summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    print(json.dumps(summary, indent=2, default=str))
    print(f"\nWROTE {raw_path}")
    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
