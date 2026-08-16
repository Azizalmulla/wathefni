"""Wave 1 — Hire → Ready lifecycle bridge.

Orchestrates optional integrations across Offer / pending_start / Preboarding /
Hire / Onboarding without rewriting frozen Preboarding SM or forcing modules on.

Flags (process-scoped; never require systemd-global enable):
  WATHEFNI_HIRE_READY_WAVE1=on
  ∧ company in WATHEFNI_HIRE_READY_COMPANIES (optional allowlist; empty = all when flag on)

Truth-sync writers (joining-date from offer) remain dark unless:
  WATHEFNI_EMPLOYMENT_TRUTH_SYNC_WRITERS=on
  ∧ company in WATHEFNI_EMPLOYMENT_TRUTH_SYNC_COMPANIES
  ∧ dry-run pending_start invariants pass (caller should prove first)

Onboarding auto-start writers:
  WATHEFNI_ONBOARDING_AUTO_START_WRITERS=on
  ∧ company setting onboarding.auto_start_on_hire
  ∧ onboarding module enabled
  (does NOT require global WATHEFNI_ONBOARDING_SEED=on)
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any

BRIDGE_VERSION = "1.0.0"
_ON_VALUES = {"1", "true", "yes", "on"}


def _env_on(name: str, default: str = "off") -> bool:
    return str(os.environ.get(name, default) or default).strip().lower() in _ON_VALUES


def company_code_norm(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def digits_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _actor_uuid(actor_user_id: str | None) -> str | None:
    """Lifecycle actor_user_id columns are uuid — reject non-uuid strings."""
    raw = str(actor_user_id or "").strip()
    if not raw:
        return None
    try:
        return str(uuid.UUID(raw))
    except ValueError:
        return None


def _with_savepoint(cur: Any, name: str, fn: Any) -> Any:
    sp = f"hrb_{name}_{uuid.uuid4().hex[:8]}"
    try:
        cur.execute(f"SAVEPOINT {sp}")
        result = fn()
        cur.execute(f"RELEASE SAVEPOINT {sp}")
        return result
    except Exception as exc:
        try:
            cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            cur.execute(f"RELEASE SAVEPOINT {sp}")
        except Exception:
            pass
        raise exc


def wave1_runtime_flag_on() -> bool:
    return _env_on("WATHEFNI_HIRE_READY_WAVE1", "off")


def wave1_company_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_HIRE_READY_COMPANIES", "") or "")
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def wave1_enabled_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not wave1_runtime_flag_on():
        return {"ok": False, "enabled": False, "reason": "hire_ready_wave1_off", "company_code": company}
    allow = wave1_company_allowlist()
    if allow and company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "reason": "hire_ready_company_not_allowlisted",
            "company_code": company,
        }
    return {"ok": True, "enabled": True, "company_code": company, "version": BRIDGE_VERSION}


def truth_sync_company_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_EMPLOYMENT_TRUTH_SYNC_COMPANIES", "") or "")
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def writers_enabled_for_company(company_code: str | None) -> bool:
    """Company-scoped canary for truth-sync writers. Never global-only."""
    import employment_truth_sync as ets

    if not ets.writers_enabled():
        return False
    company = company_code_norm(company_code)
    allow = truth_sync_company_allowlist()
    if not allow:
        # Explicit empty allowlist = writers stay dark even if global flag on.
        return False
    return company in allow


def onboarding_auto_start_writers_on() -> bool:
    return _env_on("WATHEFNI_ONBOARDING_AUTO_START_WRITERS", "off")


def _enabled_modules(cur: Any, company: str) -> set[str]:
    try:
        cur.execute(
            """
            SELECT module_key FROM company_modules
             WHERE company_code=%s AND enabled=true
            """,
            (company,),
        )
        return {str(r["module_key"] if isinstance(r, dict) else r[0]) for r in (cur.fetchall() or [])}
    except Exception:
        return set()


def _company_settings_blob(cur: Any, company: str) -> dict[str, Any]:
    try:
        cur.execute(
            "SELECT settings FROM company_settings WHERE company_code=%s LIMIT 1",
            (company,),
        )
        row = cur.fetchone()
        if not row:
            return {}
        settings = dict(row).get("settings") if isinstance(row, dict) else row[0]
        return dict(settings or {}) if isinstance(settings, dict) else {}
    except Exception:
        return {}


def _merge_company_setting(cur: Any, company: str, key: str, value: Any) -> None:
    cur.execute(
        """
        INSERT INTO company_settings (company_code, settings, updated_at)
        VALUES (%s, %s::jsonb, now())
        ON CONFLICT (company_code) DO UPDATE
          SET settings = COALESCE(company_settings.settings, '{}'::jsonb) || EXCLUDED.settings,
              updated_at = now()
        """,
        (company, json.dumps({key: value})),
    )


def _audit(
    cur: Any,
    *,
    company: str,
    event_type: str,
    employee_key: str | None = None,
    employment_id: str | None = None,
    actor_user_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS hire_ready_bridge_events (
              event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
              company_code text NOT NULL,
              event_type text NOT NULL,
              employee_key text,
              employment_id text,
              actor_user_id text,
              payload jsonb NOT NULL DEFAULT '{}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            """
            INSERT INTO hire_ready_bridge_events (
              event_id, company_code, event_type, employee_key, employment_id, actor_user_id, payload
            ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            (
                str(uuid.uuid4()),
                company,
                event_type,
                employee_key,
                employment_id,
                actor_user_id,
                json.dumps(payload or {}, default=str),
            ),
        )
    except Exception:
        pass


def resolve_offer_employee_key(offer: dict[str, Any]) -> str | None:
    company = company_code_norm(offer.get("company_code"))
    phone = digits_phone(offer.get("candidate_phone_snapshot") or offer.get("phone"))
    if company and phone:
        return f"{company}-{phone}"
    app_key = str(offer.get("app_key") or "").strip()
    if company and app_key:
        return f"{company}-{app_key}"
    return None


def write_joining_date(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    joining_date: date,
    source: str,
    actor_user_id: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Canonical joining-date writer: hub employees.start_date + employment + preboard + onboarding."""
    import employment_truth_sync as ets

    company = company_code_norm(company_code)
    key = str(employee_key or "").strip()
    jd = as_date(joining_date)
    if not company or not key or not jd:
        return {"ok": False, "error": "joining_date_write_invalid"}

    rank = ets.joining_date_authority_rank(source)
    # Offer-accept writers require company canary; HR explicit / hire_tx always allowed when bridge on.
    if source == "offer_accept" and not writers_enabled_for_company(company) and not force:
        return {
            "ok": True,
            "skipped": True,
            "reason": "truth_sync_writers_dark_or_not_canary",
            "suggested": jd.isoformat(),
            "rank": rank,
        }

    cur.execute(
        """
        SELECT start_date FROM employees
         WHERE company_code=%s AND employee_key=%s
         LIMIT 1
        """,
        (company, key),
    )
    hub = cur.fetchone()
    existing = as_date(dict(hub).get("start_date") if hub else None)
    # Priority: hr_explicit_edit > hire_tx > offer_accept — never overwrite higher/equal non-null with lower.
    if existing and source == "offer_accept" and not force:
        return {
            "ok": True,
            "skipped": True,
            "reason": "employment_joining_already_set",
            "joining_date": existing.isoformat(),
            "rank": rank,
        }

    cur.execute(
        """
        UPDATE employees
           SET start_date=%s, updated_at=now()
         WHERE company_code=%s AND employee_key=%s
        """,
        (jd, company, key),
    )
    try:
        cur.execute(
            """
            UPDATE employee_employments
               SET start_date=%s, updated_at=now()
             WHERE company_code=%s AND legacy_employee_key=%s
               AND COALESCE(lifecycle_state,'') <> 'terminated'
            """,
            (jd, company, key),
        )
    except Exception:
        pass

    # Propagate to open preboard assignments (always — same canonical date).
    try:
        cur.execute(
            """
            UPDATE preboard_assignments
               SET joining_date=%s, updated_at=now(), row_version=row_version+1
             WHERE company_code=%s AND employee_key=%s
               AND status NOT IN ('converted','cancelled')
            """,
            (jd, company, key),
        )
    except Exception:
        pass

    # Propagate to onboarding planned_start when assignment exists.
    try:
        cur.execute(
            """
            UPDATE employee_onboarding_assignments
               SET planned_start_date=%s, updated_at=now()
             WHERE employee_key=%s
               AND COALESCE(status,'') NOT IN ('completed','cancelled','waived')
            """,
            (jd, key),
        )
    except Exception:
        pass

    _audit(
        cur,
        company=company,
        event_type="joining_date_written",
        employee_key=key,
        actor_user_id=actor_user_id,
        payload={"joining_date": jd.isoformat(), "source": source, "rank": rank},
    )
    return {"ok": True, "joining_date": jd.isoformat(), "source": source, "rank": rank}


def close_provisional_employment(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    cancel_reason: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """P6 — cancel/no-show/withdrawn closes provisional pending_start cleanly."""
    company = company_code_norm(company_code)
    key = str(employee_key or "").strip()
    reason = str(cancel_reason or "cancelled").strip().lower()
    if reason not in {"cancelled", "no_show", "withdrawn", "other"}:
        reason = "cancelled"

    cur.execute(
        """
        SELECT employment_id, lifecycle_state, employment_status, person_id, start_date
          FROM employee_employments
         WHERE company_code=%s AND legacy_employee_key=%s
           AND COALESCE(lifecycle_state,'') = 'pending_start'
         ORDER BY updated_at DESC NULLS LAST
         LIMIT 1
        """,
        (company, key),
    )
    emp = cur.fetchone()
    employment_id = None
    if emp:
        ed = dict(emp)
        employment_id = str(ed.get("employment_id") or "") or None
        # Future joiners may have start_date > today; end_date must not precede start.
        start = as_date(ed.get("start_date"))
        close_on = date.today()
        if start and close_on < start:
            close_on = start
        try:
            import employee_lifecycle_wave3 as life

            def _close():
                life._apply_transition(
                    cur,
                    company=company,
                    employment={
                        **ed,
                        "employee_key": key,
                        "person_id": ed.get("person_id"),
                        "lifecycle_version": int(ed.get("lifecycle_version") or 1),
                    },
                    to_state="terminated",
                    event_type="provisional_closed",
                    actor_user_id=_actor_uuid(actor_user_id) or str(uuid.uuid4()),
                    case_id=None,
                    request_id=None,
                    effective_on=close_on,
                    last_working_day=close_on,
                    termination_type="other",
                    reason=f"future_joiner_{reason}",
                    payload={"cancel_reason": reason, "source": "hire_ready_bridge"},
                )

            _with_savepoint(cur, "close_prov", _close)
        except Exception:
            cur.execute(
                """
                UPDATE employee_employments
                   SET lifecycle_state='terminated',
                       employment_status='left',
                       end_date=%s,
                       termination_effective_on=%s,
                       last_working_day=%s,
                       termination_type='other',
                       termination_reason=%s,
                       updated_at=now()
                 WHERE employment_id=%s AND company_code=%s
                """,
                (
                    close_on,
                    close_on,
                    close_on,
                    f"future_joiner_{reason}",
                    employment_id,
                    company,
                ),
            )

    cur.execute(
        """
        UPDATE employees
           SET employment_status='left', updated_at=now()
         WHERE company_code=%s AND employee_key=%s
           AND lower(coalesce(employment_status,'')) IN ('pending_start','joining','future_start','')
        """,
        (company, key),
    )
    _audit(
        cur,
        company=company,
        event_type="provisional_closed",
        employee_key=key,
        employment_id=employment_id,
        actor_user_id=actor_user_id,
        payload={"cancel_reason": reason},
    )
    return {"ok": True, "employee_key": key, "employment_id": employment_id, "cancel_reason": reason}


def advance_pending_start_on_hire(
    cur: Any,
    *,
    company_code: str,
    employee: dict[str, Any],
    hired: dict[str, Any] | None = None,
    operation_id: str | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """P7 — hire advances the same pending_start employment; never duplicates.

    Future joining dates stay pending_start (never active before start).
    Join date today/past → activate to active in the same TX.
    """
    company = company_code_norm(company_code)
    key = str(employee.get("employee_key") or "").strip()
    if not company or not key:
        return {"ok": False, "error": "employee_required", "handled_employment": False}

    joining = as_date(employee.get("start_date")) or as_date((hired or {}).get("proposed_start_date"))
    app_key = str((hired or {}).get("app_key") or employee.get("app_key") or "").strip() or None

    cur.execute(
        """
        SELECT *
          FROM employee_employments
         WHERE company_code=%s AND legacy_employee_key=%s
           AND COALESCE(lifecycle_state,'') NOT IN ('terminated')
         ORDER BY
           CASE WHEN lifecycle_state='pending_start' THEN 0 ELSE 1 END,
           updated_at DESC NULLS LAST
         LIMIT 2
        """,
        (company, key),
    )
    rows = [dict(r) for r in (cur.fetchall() or [])]
    if len(rows) > 1:
        # Prefer pending_start; still fail-soft but flag for audit.
        _audit(
            cur,
            company=company,
            event_type="duplicate_employment_detected",
            employee_key=key,
            payload={"count": len(rows), "ids": [str(r.get("employment_id")) for r in rows]},
        )

    pending = next((r for r in rows if str(r.get("lifecycle_state") or "") == "pending_start"), None)
    if not pending and rows:
        # Existing non-pending employment — reuse same id; do not insert.
        emp = rows[0]
        employment_id = str(emp.get("employment_id"))
        if joining:
            cur.execute(
                "UPDATE employee_employments SET start_date=COALESCE(start_date, %s), updated_at=now() WHERE employment_id=%s",
                (joining, employment_id),
            )
        if app_key:
            try:
                cur.execute(
                    "UPDATE employee_employments SET app_key=%s, updated_at=now() WHERE employment_id=%s",
                    (app_key, employment_id),
                )
            except Exception:
                pass
        return {
            "ok": True,
            "handled_employment": True,
            "employment_id": employment_id,
            "lifecycle_state": emp.get("lifecycle_state"),
            "action": "reused_existing",
        }

    if not pending:
        return {"ok": True, "handled_employment": False, "action": "no_pending_start"}

    employment_id = str(pending["employment_id"])
    if joining is None:
        joining = as_date(pending.get("start_date"))
    activate_now = bool(joining and joining <= date.today())

    # Link hire metadata on the same employment_id.
    try:
        cur.execute(
            """
            UPDATE employee_employments
               SET start_date=COALESCE(%s, start_date),
                   app_key=COALESCE(%s, app_key),
                   hire_source=COALESCE(hire_source, 'canonical_hire'),
                   provenance=COALESCE(provenance,'{}'::jsonb) || %s::jsonb,
                   updated_at=now()
             WHERE employment_id=%s AND company_code=%s
            RETURNING *
            """,
            (
                joining,
                app_key,
                json.dumps({"hire_operation_id": operation_id, "bridge": BRIDGE_VERSION}),
                employment_id,
                company,
            ),
        )
        pending = dict(cur.fetchone() or pending)
    except Exception:
        cur.execute(
            """
            UPDATE employee_employments
               SET start_date=COALESCE(%s, start_date), updated_at=now()
             WHERE employment_id=%s AND company_code=%s
            """,
            (joining, employment_id, company),
        )

    if activate_now:
        try:
            import employee_lifecycle_wave3 as life

            def _activate():
                life._apply_transition(
                    cur,
                    company=company,
                    employment={**pending, "employee_key": key},
                    to_state="active",
                    event_type="started",
                    actor_user_id=_actor_uuid(actor_user_id) or str(uuid.uuid4()),
                    case_id=None,
                    request_id=None,
                    effective_on=joining or date.today(),
                    last_working_day=None,
                    termination_type=None,
                    reason="hire_conversion",
                    payload={"operation_id": operation_id, "source": "hire_ready_bridge"},
                )

            _with_savepoint(cur, "activate", _activate)
            hub_status = "active"
            life_state = "active"
        except Exception:
            cur.execute(
                """
                UPDATE employee_employments
                   SET lifecycle_state='active', employment_status='active', updated_at=now()
                 WHERE employment_id=%s
                """,
                (employment_id,),
            )
            cur.execute(
                """
                UPDATE employees
                   SET employment_status='active', updated_at=now()
                 WHERE company_code=%s AND employee_key=%s
                """,
                (company, key),
            )
            hub_status = "active"
            life_state = "active"
    else:
        # Preserve pending_start invariants — never active before actual start.
        cur.execute(
            """
            UPDATE employee_employments
               SET lifecycle_state='pending_start',
                   employment_status='pending_start',
                   updated_at=now()
             WHERE employment_id=%s
            """,
            (employment_id,),
        )
        cur.execute(
            """
            UPDATE employees
               SET employment_status='pending_start',
                   start_date=COALESCE(%s, start_date),
                   updated_at=now()
             WHERE company_code=%s AND employee_key=%s
            """,
            (joining, company, key),
        )
        try:
            import employee_lifecycle_wave3 as life

            life.repair_pending_start_hub_projection(cur, company_code=company)
        except Exception:
            pass
        hub_status = "pending_start"
        life_state = "pending_start"

    _audit(
        cur,
        company=company,
        event_type="pending_start_advanced",
        employee_key=key,
        employment_id=employment_id,
        actor_user_id=actor_user_id,
        payload={
            "activated": activate_now,
            "lifecycle_state": life_state,
            "joining_date": joining.isoformat() if joining else None,
            "operation_id": operation_id,
        },
    )
    return {
        "ok": True,
        "handled_employment": True,
        "employment_id": employment_id,
        "lifecycle_state": life_state,
        "hub_status": hub_status,
        "activated": activate_now,
        "action": "advanced_same_employment",
    }


def convert_ready_preboard(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Preboarding ready → converted (status-only SM; employment handled separately)."""
    import preboarding as pb

    company = company_code_norm(company_code)
    key = str(employee_key or "").strip()
    gate = pb.preboarding_enabled_for_company(cur, company)
    if not gate.get("ok"):
        return {"ok": True, "skipped": True, "reason": gate.get("error") or "preboarding_off"}

    cur.execute(
        """
        SELECT assignment_id, status FROM preboard_assignments
         WHERE company_code=%s AND employee_key=%s
           AND status NOT IN ('converted','cancelled')
         ORDER BY updated_at DESC
         LIMIT 1
        """,
        (company, key),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": True, "skipped": True, "reason": "no_open_assignment"}
    asn = dict(row)
    result = pb.transition_assignment(
        cur,
        company_code=company,
        assignment_id=str(asn["assignment_id"]),
        to_status="converted",
        actor_user_id=actor_user_id,
        actor_role="hr",
    )
    return result


def apply_preboard_to_onboarding_dedupe(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Mark overlapping onboarding items satisfied from completed preboard evidence."""
    import preboarding as pb

    company = company_code_norm(company_code)
    key = str(employee_key or "").strip()
    modules = _enabled_modules(cur, company)
    if "onboarding" not in modules or "preboarding" not in modules:
        return {"ok": True, "skipped": True, "reason": "modules_off"}

    try:
        import capability_contracts as cc

        ev = cc.evaluate_contract(
            "preboarding.handoff_onboarding",
            enabled_modules=modules,
        )
        if not ev.get("active"):
            return {"ok": True, "skipped": True, "reason": "contract_inactive"}
    except Exception:
        pass

    # Prefer assignment-level handoff (preboard ← onboarding) already in preboarding.py,
    # then also stamp onboarding items when preboard docs are done (preboard → onboard).
    cur.execute(
        """
        SELECT assignment_id FROM preboard_assignments
         WHERE company_code=%s AND employee_key=%s
         ORDER BY CASE WHEN status='converted' THEN 0 ELSE 1 END, updated_at DESC
         LIMIT 1
        """,
        (company, key),
    )
    row = cur.fetchone()
    applied_pb: list[str] = []
    if row:
        pb.apply_onboarding_handoff_dedupe(
            cur,
            company_code=company,
            assignment_id=str(dict(row)["assignment_id"]),
            actor_user_id=actor_user_id,
        )

    done_keys: set[str] = set()
    try:
        cur.execute(
            """
            SELECT i.item_key, i.status
              FROM preboard_items i
              JOIN preboard_assignments a ON a.assignment_id=i.assignment_id
             WHERE a.company_code=%s AND a.employee_key=%s
               AND i.status IN ('done','waived')
            """,
            (company, key),
        )
        for r in cur.fetchall() or []:
            d = dict(r)
            ik = str(d.get("item_key") or "")
            if ik in pb.ONBOARDING_OVERLAP_KEYS:
                done_keys.add(ik)
    except Exception:
        done_keys = set()

    stamped: list[str] = []
    for ik in sorted(done_keys):
        try:
            cur.execute(
                """
                UPDATE onboarding_items
                   SET status=CASE
                         WHEN lower(coalesce(status,'')) IN ('received','verified','completed','done','waived','approved')
                         THEN status ELSE 'waived'
                       END,
                       updated_at=now(),
                       raw_json=COALESCE(raw_json,'{}'::jsonb) || %s::jsonb
                 WHERE employee_key=%s AND item_id=%s
                """,
                (
                    json.dumps({"dedupe_from": "preboarding", "preboard_item_key": ik}),
                    key,
                    ik,
                ),
            )
            if cur.rowcount:
                stamped.append(ik)
        except Exception:
            continue

    _audit(
        cur,
        company=company,
        event_type="preboard_onboarding_dedupe",
        employee_key=key,
        actor_user_id=actor_user_id,
        payload={"stamped": stamped, "preboard_done": sorted(done_keys)},
    )
    return {"ok": True, "stamped": stamped, "preboard_done": sorted(done_keys), "applied_pb": applied_pb}


def maybe_auto_start_onboarding(
    cur: Any,
    *,
    company_code: str,
    employee: dict[str, Any],
    planned_start: date | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """W1.5 — company-entitled auto-start without global SEED."""
    company = company_code_norm(company_code)
    modules = _enabled_modules(cur, company)
    settings = _company_settings_blob(cur, company)
    auto = settings.get("onboarding.auto_start_on_hire")
    if auto is None:
        auto = False
    try:
        import capability_contracts as cc

        ev = cc.evaluate_contract(
            "onboarding.auto_start_on_hire",
            enabled_modules=modules,
            company_settings={"onboarding.auto_start_on_hire": bool(auto)},
        )
        if not ev.get("active"):
            return {"ok": True, "skipped": True, "reason": ev.get("reason") or "contract_inactive", "eval": ev}
        if not ev.get("writers_enabled") and not onboarding_auto_start_writers_on():
            return {"ok": True, "skipped": True, "reason": "auto_start_writers_off", "eval": ev}
    except Exception as exc:
        return {"ok": True, "skipped": True, "reason": f"contract_eval_error:{exc}"}

    if not onboarding_auto_start_writers_on():
        return {"ok": True, "skipped": True, "reason": "auto_start_writers_off"}

    planned = as_date(planned_start) or as_date(employee.get("start_date")) or date.today()
    try:
        import onboarding_wave2 as ow2

        result = ow2.start_onboarding_wave2(
            cur,
            dict(employee),
            planned_start_date=planned,
            delayed=bool(planned > date.today()),
            actor_user_id=actor_user_id,
        )
    except Exception as exc:
        return {"ok": False, "error": "onboarding_auto_start_failed", "detail": str(exc)}

    # After seed, apply preboard→onboarding dedupe.
    dedupe = apply_preboard_to_onboarding_dedupe(
        cur,
        company_code=company,
        employee_key=str(employee.get("employee_key") or ""),
        actor_user_id=actor_user_id,
    )
    _audit(
        cur,
        company=company,
        event_type="onboarding_auto_started",
        employee_key=str(employee.get("employee_key") or ""),
        actor_user_id=actor_user_id,
        payload={"result": {"ok": result.get("ok"), "status": result.get("status"), "seeded": result.get("seeded")}, "dedupe": dedupe},
    )
    return {"ok": bool(result.get("ok")), "onboarding": result, "dedupe": dedupe}


def on_offer_accepted(
    cur: Any,
    *,
    company_code: str,
    offer: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Hook after offer accept (same TX): joining date + optional preboard create."""
    company = company_code_norm(company_code or offer.get("company_code"))
    gate = wave1_enabled_for_company(company)
    if not gate.get("enabled"):
        return {"ok": True, "skipped": True, "reason": gate.get("reason")}

    employee_key = resolve_offer_employee_key(offer)
    if not employee_key:
        return {"ok": False, "error": "offer_employee_key_unresolved"}

    joining = as_date(offer.get("proposed_start_date"))
    name = str(offer.get("candidate_name_snapshot") or offer.get("candidate_name") or employee_key)
    phone = digits_phone(offer.get("candidate_phone_snapshot") or offer.get("phone"))

    provisional = None
    if joining:
        try:
            import preboarding as pb

            # Provisional pending_start even when preboarding module off — Core HR truth.
            provisional = pb.ensure_provisional_pending_start(
                cur,
                company_code=company,
                employee_key=employee_key,
                name=name,
                joining_date=joining,
                phone=phone or None,
            )
        except Exception as exc:
            provisional = {"ok": False, "error": str(exc)}

        jd_write = write_joining_date(
            cur,
            company_code=company,
            employee_key=employee_key,
            joining_date=joining,
            source="offer_accept",
            actor_user_id=actor_user_id,
        )
    else:
        jd_write = {"ok": True, "skipped": True, "reason": "no_proposed_start_date"}

    preboard = {"ok": True, "skipped": True, "reason": "not_attempted"}
    try:
        import preboarding as pb

        preboard = pb.maybe_create_assignment_from_offer(
            cur,
            company_code=company,
            employee_key=employee_key,
            offer_id=str(offer.get("offer_id") or ""),
            joining_date=joining,
            actor_user_id=actor_user_id,
        )
    except Exception as exc:
        preboard = {"ok": False, "error": str(exc)}

    _audit(
        cur,
        company=company,
        event_type="offer_accepted_bridge",
        employee_key=employee_key,
        actor_user_id=actor_user_id,
        payload={
            "offer_id": offer.get("offer_id"),
            "joining": jd_write,
            "provisional": {
                "ok": (provisional or {}).get("ok"),
                "employment_id": (provisional or {}).get("employment_id"),
            },
            "preboard": {
                "ok": preboard.get("ok"),
                "skipped": preboard.get("skipped"),
                "reason": preboard.get("reason") or preboard.get("error"),
                "assignment_id": (preboard.get("assignment") or {}).get("assignment_id"),
            },
        },
    )
    return {
        "ok": True,
        "employee_key": employee_key,
        "joining_date": jd_write,
        "provisional": provisional,
        "preboard": preboard,
    }


def on_hire_employee_tx(
    cur: Any,
    *,
    company_code: str,
    employee: dict[str, Any],
    hired: dict[str, Any] | None = None,
    operation_id: str | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Inside hire employee TX — convert pending_start, preboard, optional onboard."""
    company = company_code_norm(company_code)
    gate = wave1_enabled_for_company(company)
    if not gate.get("enabled"):
        return {"ok": True, "skipped": True, "reason": gate.get("reason"), "handled_employment": False}

    key = str(employee.get("employee_key") or "")
    joining = as_date(employee.get("start_date")) or as_date((hired or {}).get("proposed_start_date"))
    if joining:
        write_joining_date(
            cur,
            company_code=company,
            employee_key=key,
            joining_date=joining,
            source="hire_tx",
            actor_user_id=actor_user_id,
            force=False,
        )

    employment = advance_pending_start_on_hire(
        cur,
        company_code=company,
        employee=employee,
        hired=hired,
        operation_id=operation_id,
        actor_user_id=actor_user_id,
    )

    # Refresh employee row after projection changes.
    cur.execute(
        "SELECT * FROM employees WHERE company_code=%s AND employee_key=%s",
        (company, key),
    )
    refreshed = dict(cur.fetchone() or employee)

    preboard = convert_ready_preboard(
        cur,
        company_code=company,
        employee_key=key,
        actor_user_id=actor_user_id,
    )

    onboard = maybe_auto_start_onboarding(
        cur,
        company_code=company,
        employee=refreshed,
        planned_start=joining or as_date(refreshed.get("start_date")),
        actor_user_id=actor_user_id,
    )

    # If auto-start skipped but both modules on, still attempt dedupe for existing onboard.
    if onboard.get("skipped"):
        apply_preboard_to_onboarding_dedupe(
            cur, company_code=company, employee_key=key, actor_user_id=actor_user_id
        )

    _audit(
        cur,
        company=company,
        event_type="hire_employee_tx_bridge",
        employee_key=key,
        employment_id=employment.get("employment_id"),
        actor_user_id=actor_user_id,
        payload={
            "operation_id": operation_id,
            "employment": employment,
            "preboard_ok": preboard.get("ok"),
            "preboard_skipped": preboard.get("skipped"),
            "onboarding": {
                "skipped": onboard.get("skipped"),
                "reason": onboard.get("reason"),
                "ok": onboard.get("ok"),
            },
        },
    )
    return {
        "ok": True,
        "handled_employment": bool(employment.get("handled_employment")),
        "employment": employment,
        "preboard": preboard,
        "onboarding": onboard,
        "employee": refreshed,
    }


def convert_ready_assignment_to_hire(
    cur: Any,
    *,
    company_code: str,
    assignment_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Manual/future-joiner path: Preboarding ready → convert + advance same employment."""
    import preboarding as pb

    company = company_code_norm(company_code)
    gate = wave1_enabled_for_company(company)
    if not gate.get("enabled"):
        return {"ok": False, "error": gate.get("reason") or "hire_ready_off"}

    asn = pb.get_assignment(cur, company_code=company, assignment_id=assignment_id)
    if not asn:
        return {"ok": False, "error": "assignment_not_found"}

    conv = pb.transition_assignment(
        cur,
        company_code=company,
        assignment_id=assignment_id,
        to_status="converted",
        actor_user_id=actor_user_id,
        actor_role="hr",
    )
    if not conv.get("ok"):
        return conv

    cur.execute(
        "SELECT * FROM employees WHERE company_code=%s AND employee_key=%s",
        (company, asn["employee_key"]),
    )
    employee = dict(cur.fetchone() or {"employee_key": asn["employee_key"], "company_code": company})
    if asn.get("joining_date") and not employee.get("start_date"):
        employee["start_date"] = asn["joining_date"]

    employment = advance_pending_start_on_hire(
        cur,
        company_code=company,
        employee=employee,
        hired={"proposed_start_date": asn.get("joining_date")},
        operation_id=f"preboard_convert:{assignment_id}",
        actor_user_id=actor_user_id,
    )
    onboard = maybe_auto_start_onboarding(
        cur,
        company_code=company,
        employee=employee,
        planned_start=as_date(asn.get("joining_date")),
        actor_user_id=actor_user_id,
    )
    return {
        "ok": True,
        "assignment": conv.get("assignment"),
        "employment": employment,
        "onboarding": onboard,
    }


def on_preboard_cancelled(
    cur: Any,
    *,
    company_code: str,
    assignment: dict[str, Any],
    cancel_reason: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    gate = wave1_enabled_for_company(company_code)
    if not gate.get("enabled"):
        return {"ok": True, "skipped": True, "reason": gate.get("reason")}
    return close_provisional_employment(
        cur,
        company_code=company_code,
        employee_key=str(assignment.get("employee_key") or ""),
        cancel_reason=cancel_reason,
        actor_user_id=actor_user_id,
    )


def on_joining_date_changed(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    joining_date: date,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """HR explicit joining-date fan-out (P8)."""
    gate = wave1_enabled_for_company(company_code)
    if not gate.get("enabled"):
        # Still write via existing preboarding.set_joining_date; bridge adds onboarding fan-out when on.
        return {"ok": True, "skipped": True, "reason": gate.get("reason")}
    return write_joining_date(
        cur,
        company_code=company_code,
        employee_key=employee_key,
        joining_date=joining_date,
        source="hr_explicit_edit",
        actor_user_id=actor_user_id,
        force=True,
    )


def rollback_guidance() -> dict[str, Any]:
    return {
        "runtime": [
            "Set WATHEFNI_HIRE_READY_WAVE1=off",
            "Clear WATHEFNI_HIRE_READY_COMPANIES",
            "Keep WATHEFNI_EMPLOYMENT_TRUTH_SYNC_WRITERS=off unless staging company canary",
            "Keep WATHEFNI_ONBOARDING_AUTO_START_WRITERS=off unless company setting entitled",
            "Never enable writers globally in systemd",
        ],
        "version": BRIDGE_VERSION,
    }
