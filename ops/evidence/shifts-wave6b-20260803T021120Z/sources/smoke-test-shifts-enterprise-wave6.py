#!/usr/bin/env python3
"""Shifts Wave 6A — rotations, remote roster metadata, compliance, PAM export smoke (local/staging).

Proves rotation patterns/assignments feeding Wave 5 draft → review → approve → publish,
non-work (rest/travel) planning rows, compliance profile evaluation, PAM-style read-only
export from a published version, cycle-edit regeneration, and cancelled-held detection.
Synthetic SHW6 / 965536* only.
Does NOT: production deploy, PAM submission, Payroll money, Leave balance mutation,
Attendance authority mutation, real allowlists, timers, real reminders.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("WATHEFNI_ENV", os.environ.get("WATHEFNI_ENV") or "staging")

# Wave 6A synthetic gate
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE6", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE6_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_KEY_MARKERS", "SHW6,SHW6-SYNTH|")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_PHONE_PREFIXES", "965536")

# Wave 5 publish/open/coverage gate — merge SHW6 markers so rotation drafts can publish
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE5", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE5_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_KEY_MARKERS", "SHW5,SHW5-SYNTH|,SHW6,SHW6-SYNTH|")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_PHONE_PREFIXES", "965534,965536")

# Wave 4 templates/recurrences gate — merge SHW6 markers so templates/classify recognize SHW6
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE4", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE4_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_KEY_MARKERS", "SHW4,SHW4-SYNTH|,SHW6,SHW6-SYNTH|")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_PHONE_PREFIXES", "965532,965536")

PASS = FAIL = 0


def check(name: str, ok: bool, detail=None) -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name} :: {detail}")


def _to_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _fingerprint_rows(rows: list[dict]) -> str:
    normalized = sorted(
        (
            {
                "shift_id": str(r.get("shift_id")),
                "employee_key": r.get("employee_key"),
                "shift_date": str(r.get("shift_date"))[:10],
                "start_time": str(r.get("start_time"))[:8],
                "end_time": str(r.get("end_time"))[:8],
                "status": r.get("status"),
            }
            for r in rows
        ),
        key=lambda x: (x["employee_key"], x["shift_date"], x["shift_id"]),
    )
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, default=str).encode()).hexdigest()


def main() -> int:
    import app
    import shifts_enterprise_wave6 as w6
    import shifts_publish_wave5 as w5
    import shifts_templates_wave4 as w4
    import shifts_synthetic_cleanup as cleanup

    tag = uuid.uuid4().hex[:8].upper()
    company = "WATHEFNI"
    key = f"WATHEFNI-SHW6-{tag}"
    key_b = f"WATHEFNI-SHW6-B-{tag}"
    _digits = "".join(ch for ch in tag if ch.isdigit()) or "123456"
    phone = f"9655360{_digits[:5].ljust(5, '0')}"
    phone_b = f"9655361{_digits[1:6].ljust(5, '0')}"
    name = f"SHW6-SYNTH| Emp {tag}"
    name_b = f"SHW6-SYNTH| EmpB {tag}"
    today = date.today()
    start1 = today + timedelta(days=7)
    end1 = today + timedelta(days=20)
    start2 = today + timedelta(days=21)
    end2 = today + timedelta(days=34)
    acks = {
        "acknowledge_availability": True,
        "ack_availability_conflict": True,
        "allow_availability_conflicts": True,
        "allow_leave_conflicts": True,
        "ack_leave_conflict": True,
        "acknowledge_seasonal": True,
        "ack_seasonal": True,
        "confirm_overlap": True,
    }

    known_ids: dict[str, object] = {"shift_ids": []}

    # --- Honesty / unit (no DB) ------------------------------------------------
    check("version 6.0.0", w6.SHIFTS_WAVE6_VERSION == "6.0.0")
    check("wave6 enabled", w6.shifts_wave6_enabled())
    check("company WATHEFNI", w6.shifts_wave6_enabled_for_company(company))
    h = w6.honesty_payload()
    check("honesty rotations true", h.get("rotations") is True)
    check("honesty pam_export true", h.get("pam_export") is True)
    check("honesty pam_submission false", h.get("pam_submission") is False)
    check("honesty payroll_money false", h.get("payroll_money") is False)
    check("honesty leave_balances_mutated false", h.get("leave_balances_mutated") is False)
    check("honesty attendance_authority_mutated false", h.get("attendance_authority_mutated") is False)
    check("honesty publishing true", h.get("publishing") is True)
    check("honesty templates true", h.get("templates") is True)
    check("honesty remote_rosters true", h.get("remote_rosters") is True)
    check("honesty compliance_profiles true", h.get("compliance_profiles") is True)
    check("honesty coverage_rules true", h.get("coverage_rules") is True)
    check("w5 honesty rotations false", w5.honesty_payload().get("rotations") is False)
    check("w5 honesty pam_export false", w5.honesty_payload().get("pam_export") is False)
    check("w4 honesty publishing false", w4.honesty_payload().get("publishing") is False)
    check("shw6 synthetic key", w6.is_wave6_synthetic_employee(employee_key=key, phone=phone, name=name))
    check("real phone not synth", not w6.is_wave6_synthetic_employee(employee_key="EMP-1", phone="96550001111"))
    pm = w6.permission_matrix()
    check("permission_matrix export_pam hr/admin", set(pm.get("export_pam") or []) >= {"hr", "admin"})
    src = Path(w6.__file__).read_text(encoding="utf-8")
    check(
        "no leave_balances mutation SQL",
        "UPDATE leave_balances" not in src and "INSERT INTO leave_balances" not in src,
    )
    check("no payroll money calc", '"payroll_money": False' in src)

    # --- Unit: preset_cycle_sequence lengths (no DB) ----------------------------
    seq_44 = w6.preset_cycle_sequence("four_on_four_off")
    check("four_on_four_off length 8", len(seq_44) == 8, len(seq_44))
    check("four_on_four_off work/rest split 4/4", sum(1 for s in seq_44 if s["kind"] == "work") == 4
          and sum(1 for s in seq_44 if s["kind"] == "rest") == 4, seq_44)

    seq_panama = w6.preset_cycle_sequence("panama_223")
    check("panama_223 length 14", len(seq_panama) == 14, len(seq_panama))

    seq_hitch = w6.preset_cycle_sequence("hitch_n_n", {"hitch_on_days": 14, "hitch_off_days": 14, "travel_edges": True})
    check("hitch_n_n 14/14 length 28", len(seq_hitch) == 28, len(seq_hitch))
    check("hitch_n_n travel edges present (2)", sum(1 for s in seq_hitch if s["kind"] == "travel") == 2, seq_hitch)
    check("hitch_n_n work count 13", sum(1 for s in seq_hitch if s["kind"] == "work") == 13, seq_hitch)
    check("hitch_n_n rest count 13", sum(1 for s in seq_hitch if s["kind"] == "rest") == 13, seq_hitch)

    # --- DB section --------------------------------------------------------------
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w6.ensure_shifts_enterprise_wave6_schema(cur)
            w4.ensure_shifts_templates_wave4_schema(cur)

            # 1. Seed employees
            for k, p, n in ((key, phone, name), (key_b, phone_b, name_b)):
                cur.execute(
                    """
                    INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,%s::jsonb, now(), now())
                    ON CONFLICT DO NOTHING
                    """,
                    (company, k, n, p, json.dumps({"shw6": True, "tag": tag})),
                )
                cur.execute(
                    """
                    UPDATE employees SET name=%s, phone=%s, employment_status='active', raw_json=%s::jsonb, updated_at=now()
                    WHERE company_code=%s AND employee_key=%s
                    """,
                    (n, p, json.dumps({"shw6": True, "tag": tag}), company, k),
                )
                cur.execute("SELECT 1 FROM employees WHERE company_code=%s AND employee_key=%s", (company, k))
                if not cur.fetchone():
                    raise RuntimeError(f"failed to seed employee {k}")
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w6.ensure_shifts_enterprise_wave6_schema(cur)
            w4.ensure_shifts_templates_wave4_schema(cur)

            # 2. Day + night templates
            day_t = w4.create_template(
                cur,
                company_code=company,
                payload={"name": f"SHW6 Day {tag}", "start_time": "09:00", "end_time": "17:00", "role": "ops", "site_key": "SITE-A"},
            )
            check("day template", day_t.get("ok") and day_t.get("template"), day_t)
            day_id = str((day_t.get("template") or {}).get("template_id"))

            night_t = w4.create_template(
                cur,
                company_code=company,
                payload={"name": f"SHW6 Night {tag}", "start_time": "22:00", "end_time": "06:00"},
            )
            check("night template ends_next_day", night_t.get("ok") and bool((night_t.get("template") or {}).get("ends_next_day")), night_t)
            night_id = str((night_t.get("template") or {}).get("template_id"))

            # 3. Patterns
            pattern_a = w6.create_rotation_pattern(
                cur,
                company_code=company,
                payload={"name": f"SHW6 4x4 {tag}", "pattern_kind": "four_on_four_off", "day_template_id": day_id},
                actor_phone=phone,
            )
            check("pattern four_on_four_off", pattern_a.get("ok"), pattern_a)
            pattern_a_id = str((pattern_a.get("pattern") or {}).get("pattern_id"))

            pattern_b = w6.create_rotation_pattern(
                cur,
                company_code=company,
                payload={
                    "name": f"SHW6 AltDN {tag}",
                    "pattern_kind": "alternating_day_night",
                    "day_template_id": day_id,
                    "night_template_id": night_id,
                },
                actor_phone=phone,
            )
            check("pattern alternating_day_night", pattern_b.get("ok"), pattern_b)
            pattern_b_id = str((pattern_b.get("pattern") or {}).get("pattern_id"))

            pattern_c = w6.create_rotation_pattern(
                cur,
                company_code=company,
                payload={
                    "name": f"SHW6 Hitch {tag}",
                    "pattern_kind": "hitch_n_n",
                    "hitch_on_days": 14,
                    "hitch_off_days": 14,
                    "travel_edges": True,
                    "day_template_id": day_id,
                },
                actor_phone=phone,
            )
            check("pattern hitch_n_n", pattern_c.get("ok"), pattern_c)
            pattern_c_id = str((pattern_c.get("pattern") or {}).get("pattern_id"))

            # 4. Assignments with different cycle_offsets for two employees
            assign_a = w6.assign_rotation(
                cur,
                company_code=company,
                payload={
                    "pattern_id": pattern_a_id,
                    "target_type": "employee",
                    "target_key": key,
                    "employee_key": key,
                    "employee_name": name,
                    "employee_phone": phone,
                    "cycle_anchor_date": start1.isoformat(),
                    "effective_start": start1.isoformat(),
                    "cycle_offset": 0,
                },
                actor_phone=phone,
            )
            check("assign rotation A", assign_a.get("ok"), assign_a)
            assignment_a_id = str((assign_a.get("assignment") or {}).get("assignment_id"))

            assign_b = w6.assign_rotation(
                cur,
                company_code=company,
                payload={
                    "pattern_id": pattern_b_id,
                    "target_type": "employee",
                    "target_key": key_b,
                    "employee_key": key_b,
                    "employee_name": name_b,
                    "employee_phone": phone_b,
                    "cycle_anchor_date": start1.isoformat(),
                    "effective_start": start1.isoformat(),
                    "cycle_offset": 4,
                },
                actor_phone=phone,
            )
            check("assign rotation B (overnight, different offset)", assign_b.get("ok"), assign_b)
            assignment_b_id = str((assign_b.get("assignment") or {}).get("assignment_id"))

            assign_c = w6.assign_rotation(
                cur,
                company_code=company,
                payload={
                    "pattern_id": pattern_c_id,
                    "target_type": "employee",
                    "target_key": key,
                    "employee_key": key,
                    "employee_name": name,
                    "employee_phone": phone,
                    "cycle_anchor_date": start1.isoformat(),
                    "effective_start": start1.isoformat(),
                    "cycle_offset": 0,
                },
                actor_phone=phone,
            )
            check("assign rotation C (hitch, preview only)", assign_c.get("ok"), assign_c)
            assignment_c_id = str((assign_c.get("assignment") or {}).get("assignment_id"))

            offset_a = int((assign_a.get("assignment") or {}).get("cycle_offset") or 0)
            offset_b = int((assign_b.get("assignment") or {}).get("cycle_offset") or 0)
            check("different cycle_offsets for two employees", offset_a != offset_b, {"a": offset_a, "b": offset_b})

            # 5. Preview shows work/rest/travel counts
            preview_a = w6.preview_rotation(cur, company_code=company, assignment_id=assignment_a_id)
            check("preview A ok", preview_a.get("ok"), preview_a)
            counts_a = preview_a.get("counts") or {}
            check("preview A work counts", counts_a.get("work", 0) > 0, counts_a)
            check("preview A rest counts", counts_a.get("rest", 0) > 0, counts_a)

            preview_c = w6.preview_rotation(cur, company_code=company, assignment_id=assignment_c_id)
            check("preview C (hitch) ok", preview_c.get("ok"), preview_c)
            counts_c = preview_c.get("counts") or {}
            check("preview C work counts", counts_c.get("work", 0) > 0, counts_c)
            check("preview C rest counts", counts_c.get("rest", 0) > 0, counts_c)
            check("preview C travel counts", counts_c.get("travel", 0) > 0, counts_c)
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w6.ensure_shifts_enterprise_wave6_schema(cur)

            # 6. Create schedule period 1 (four-on-four-off draft)
            period1_res = w5.create_period(
                cur,
                company_code=company,
                payload={
                    "name": f"SHW6 Period {tag}",
                    "start_date": start1.isoformat(),
                    "end_date": end1.isoformat(),
                    "require_publish": True,
                },
                actor_phone=phone,
            )
            check("create period1", period1_res.get("ok"), period1_res)
            period1_id = str((period1_res.get("period") or {}).get("period_id"))
            version1_id = str((period1_res.get("version") or {}).get("version_id"))
            known_ids["period_id"] = period1_id

            # L0 count before draft
            cur.execute(
                "SELECT count(*) AS c FROM shift_assignments WHERE company_code=%s AND employee_key=%s AND status <> 'cancelled'",
                (company, key),
            )
            l0_before = int(dict(cur.fetchone())["c"])

            # 7. Generate draft from rotation (four-on-four-off, includes non-work rows)
            draft_a = w6.generate_draft_from_rotation(
                cur,
                company_code=company,
                period_id=period1_id,
                assignment_id=assignment_a_id,
                actor_phone=phone,
                action_acks=acks,
                include_non_work_rows=True,
            )
            check("generate_draft_from_rotation ok", draft_a.get("ok"), draft_a)
            check("draft_rows > 0", int(draft_a.get("draft_rows") or 0) > 0, draft_a.get("draft_rows"))
            check("l0_written false", draft_a.get("l0_written") is False, draft_a)

            cur.execute(
                "SELECT count(*) AS c FROM shift_assignments WHERE company_code=%s AND employee_key=%s AND status <> 'cancelled'",
                (company, key),
            )
            l0_after_draft = int(dict(cur.fetchone())["c"])
            check("L0 unchanged after draft", l0_after_draft == l0_before, {"before": l0_before, "after": l0_after_draft})

            # 8. Non-work rows (travel/rest) with day_kind present
            draft_rows = w5.list_draft_rows(cur, company_code=company, version_id=version1_id)
            day_kinds = {r.get("day_kind") for r in draft_rows}
            check("draft includes work day_kind", "work" in day_kinds, day_kinds)
            check("draft includes rest day_kind", "rest" in day_kinds, day_kinds)

            work_rows = sorted((r for r in draft_rows if r.get("day_kind") == "work"), key=lambda r: str(r.get("shift_date")))
            check("at least one work row for compliance rules", len(work_rows) > 0, len(work_rows))
            work_date = _to_date(work_rows[0]["shift_date"])
            weekday_sun0 = (work_date.weekday() + 1) % 7

            # 9. Compliance profile: ramadan_hours warn + midday_restriction warn + daily_hours + weekly_rest + public_holiday
            profile = w6.upsert_compliance_profile(
                cur,
                company_code=company,
                payload={
                    "name": f"SHW6 Compliance {tag}",
                    "sector_key": "industrial",
                    "enabled": True,
                    "default_enforcement": "warn",
                    "effective_start": start1.isoformat(),
                    "effective_end": end1.isoformat(),
                    "rules": [
                        {
                            "type": "ramadan_hours",
                            "enforcement": "warn",
                            "max_daily_hours": 6,
                            "effective_start": start1.isoformat(),
                            "effective_end": end1.isoformat(),
                        },
                        {
                            "type": "midday_restriction",
                            "enforcement": "warn",
                            "window_start": "11:00",
                            "window_end": "16:00",
                            "effective_start": start1.isoformat(),
                            "effective_end": end1.isoformat(),
                        },
                        {"type": "daily_hours_warning", "enforcement": "warn", "max_daily_hours": 6},
                        {"type": "weekly_rest_days", "enforcement": "warn", "rest_weekdays_sun0": [weekday_sun0]},
                        {"type": "public_holiday_warning", "enforcement": "warn", "dates": [work_date.isoformat()]},
                    ],
                },
                actor_phone=phone,
            )
            check("compliance profile upsert", profile.get("ok"), profile)

            # 10. Evaluate compliance findings
            compliance = w6.evaluate_compliance_for_version(cur, company_code=company, version_id=version1_id, period=period1_res.get("period"))
            check("compliance evaluate ok", compliance.get("ok"), compliance)
            check("compliance payroll_money false", compliance.get("payroll_money") is False, compliance)
            findings = compliance.get("findings") or []
            types_found = {f.get("type") for f in findings}
            check(
                "compliance ramadan_hours warn",
                any(f.get("type") == "ramadan_hours" and f.get("mode") == "warn" for f in findings),
                findings,
            )
            check(
                "compliance midday_restriction warn",
                any(f.get("type") == "midday_restriction" and f.get("mode") == "warn" for f in findings),
                findings,
            )
            check("compliance daily_hours_warning present", "daily_hours_warning" in types_found, types_found)
            check("compliance weekly_rest_days present", "weekly_rest_days" in types_found, types_found)
            check("compliance public_holiday_warning present", "public_holiday_warning" in types_found, types_found)
            check("compliance blocks_publish false (all warn)", compliance.get("blocks_publish") is False, compliance)

            # 11. Transition in_review → draft (return) → in_review → approved
            tr1 = w5.transition_version(cur, company_code=company, version_id=version1_id, to_state="in_review", actor_phone=phone)
            check("transition draft->in_review", tr1.get("ok"), tr1)
            tr2 = w5.transition_version(cur, company_code=company, version_id=version1_id, to_state="draft", actor_phone=phone)
            check("transition in_review->draft (return)", tr2.get("ok"), tr2)
            tr3 = w5.transition_version(cur, company_code=company, version_id=version1_id, to_state="in_review", actor_phone=phone)
            check("transition draft->in_review (again)", tr3.get("ok"), tr3)
            tr4 = w5.transition_version(cur, company_code=company, version_id=version1_id, to_state="approved", actor_phone=phone)
            check("transition in_review->approved", tr4.get("ok"), tr4)
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            # 12. Publish version1 — work rows become L0; rest/travel skipped
            pub1 = w5.publish_version(
                cur,
                company_code=company,
                version_id=version1_id,
                create_fn=app.create_shift_assignment,
                actor_phone=phone,
                publish_idempotency_key=f"SHW6-PUB1|{tag}",
                action_acks=acks,
            )
            check("publish version1 ok", pub1.get("ok"), pub1)
            results1 = pub1.get("results") or {}
            check("publish created work rows", int(results1.get("created") or 0) > 0, results1)
            check("publish skipped non-work rows", int(results1.get("skipped_non_work") or 0) > 0, results1)
            if results1.get("created_ids"):
                known_ids["shift_ids"] = list(known_ids.get("shift_ids") or []) + list(results1["created_ids"])

            cur.execute(
                """
                SELECT count(*) AS c FROM shift_assignments
                WHERE company_code=%s AND schedule_version_id=%s AND schedule_source='published' AND status <> 'cancelled'
                """,
                (company, version1_id),
            )
            pub_l0_count = int(dict(cur.fetchone())["c"])
            check("published L0 rows present", pub_l0_count > 0, pub_l0_count)
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            # 13. PAM export from published version
            pam = w6.build_pam_export(cur, company_code=company, version_id=version1_id, locale="both", actor_phone=phone)
            check("pam export ok", pam.get("ok"), pam)
            check("pam export fingerprint present", bool(pam.get("fingerprint")), pam.get("fingerprint"))
            check("pam export csv_en present", bool(pam.get("csv_en")), pam.get("csv_en") is not None)
            check("pam export csv_ar present", bool(pam.get("csv_ar")), pam.get("csv_ar") is not None)
            check("pam export report_en present", bool(pam.get("report_en")), pam.get("report_en") is not None)
            check("pam export report_ar present", bool(pam.get("report_ar")), pam.get("report_ar") is not None)
            check(
                "pam export status manual_submission_required",
                (pam.get("export") or {}).get("status") == "manual_submission_required",
                pam.get("export"),
            )
            check("pam export submission false", pam.get("submission") is False, pam)
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            # 14. Cycle edit eligibility — create new draft from published, regenerate rotation.
            # Historical/published L0 fingerprint must stay unchanged.
            cur.execute(
                """
                SELECT shift_id::text, employee_key, shift_date::text, start_time::text, end_time::text, status
                FROM shift_assignments
                WHERE company_code=%s AND schedule_version_id=%s AND status <> 'cancelled'
                ORDER BY shift_date, employee_key
                """,
                (company, version1_id),
            )
            pub_rows_before = [dict(r) for r in cur.fetchall()]
            fp_before = _fingerprint_rows(pub_rows_before)
            check("published rows exist before regenerate", len(pub_rows_before) > 0, len(pub_rows_before))

            draft2 = w5.create_draft_from_published(cur, company_code=company, period_id=period1_id, actor_phone=phone)
            check("create_draft_from_published (cycle edit)", draft2.get("ok"), draft2)
            version2_id = str((draft2.get("version") or {}).get("version_id"))

            regen1 = w6.generate_draft_from_rotation(
                cur,
                company_code=company,
                period_id=period1_id,
                assignment_id=assignment_a_id,
                actor_phone=phone,
                action_acks=acks,
            )
            check("regenerate rotation into new draft ok", regen1.get("ok"), regen1)
            check("regenerate l0_written false", regen1.get("l0_written") is False, regen1)

            cur.execute(
                """
                SELECT shift_id::text, employee_key, shift_date::text, start_time::text, end_time::text, status
                FROM shift_assignments
                WHERE company_code=%s AND schedule_version_id=%s AND status <> 'cancelled'
                ORDER BY shift_date, employee_key
                """,
                (company, version1_id),
            )
            pub_rows_after = [dict(r) for r in cur.fetchall()]
            fp_after = _fingerprint_rows(pub_rows_after)
            check("published L0 fingerprint unchanged after regenerate", fp_before == fp_after, {"before": fp_before, "after": fp_after})

            # 15. Cancelled held — soft-cancel one published shift, regenerate draft, assert cancelled_held
            target_row = pub_rows_before[0]
            target_date = _to_date(target_row["shift_date"])
            cur.execute(
                "UPDATE shift_assignments SET status='cancelled', updated_at=now() WHERE shift_id=%s",
                (target_row["shift_id"],),
            )

            regen2 = w6.generate_draft_from_rotation(
                cur,
                company_code=company,
                period_id=period1_id,
                assignment_id=assignment_a_id,
                actor_phone=phone,
                action_acks=acks,
            )
            check("regenerate after soft-cancel ok", regen2.get("ok"), regen2)

            cur.execute(
                "SELECT row_class FROM shift_schedule_draft_rows WHERE version_id=%s AND employee_key=%s AND shift_date=%s",
                (version2_id, target_row["employee_key"], target_date),
            )
            held_row = cur.fetchone()
            check(
                "cancelled_held row_class present",
                bool(held_row) and dict(held_row).get("row_class") == "cancelled_held",
                dict(held_row) if held_row else None,
            )
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            # 16. Overnight from night template — alternating pattern publish in a second period
            period2_res = w5.create_period(
                cur,
                company_code=company,
                payload={
                    "name": f"SHW6 Overnight Period {tag}",
                    "start_date": start2.isoformat(),
                    "end_date": end2.isoformat(),
                    "require_publish": True,
                },
                actor_phone=phone,
            )
            check("create period2 (overnight)", period2_res.get("ok"), period2_res)
            period2_id = str((period2_res.get("period") or {}).get("period_id"))
            version2b_id = str((period2_res.get("version") or {}).get("version_id"))

            draft_b = w6.generate_draft_from_rotation(
                cur,
                company_code=company,
                period_id=period2_id,
                assignment_id=assignment_b_id,
                actor_phone=phone,
                action_acks=acks,
            )
            check("generate_draft_from_rotation B (overnight) ok", draft_b.get("ok"), draft_b)
            check("draftB l0_written false", draft_b.get("l0_written") is False, draft_b)
            check("draftB rows > 0", int(draft_b.get("draft_rows") or 0) > 0, draft_b)

            tr_b1 = w5.transition_version(cur, company_code=company, version_id=version2b_id, to_state="in_review", actor_phone=phone)
            check("transition B draft->in_review", tr_b1.get("ok"), tr_b1)
            tr_b2 = w5.transition_version(cur, company_code=company, version_id=version2b_id, to_state="approved", actor_phone=phone)
            check("transition B in_review->approved", tr_b2.get("ok"), tr_b2)
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            pub2 = w5.publish_version(
                cur,
                company_code=company,
                version_id=version2b_id,
                create_fn=app.create_shift_assignment,
                actor_phone=phone,
                publish_idempotency_key=f"SHW6-PUB2|{tag}",
                action_acks=acks,
            )
            check("publish overnight version ok", pub2.get("ok"), pub2)
            results2 = pub2.get("results") or {}
            check("publish overnight created rows", int(results2.get("created") or 0) > 0, results2)
            if results2.get("created_ids"):
                known_ids["shift_ids"] = list(known_ids.get("shift_ids") or []) + list(results2["created_ids"])

            cur.execute(
                """
                SELECT count(*) AS c FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s AND schedule_version_id=%s
                  AND ends_next_day=true AND schedule_source='published' AND status <> 'cancelled'
                """,
                (company, key_b, version2b_id),
            )
            overnight_l0 = int(dict(cur.fetchone())["c"])
            check("overnight L0 rows via night template", overnight_l0 > 0, overnight_l0)
        conn.commit()

    # 17. Cleanup
    scope = cleanup.wave6_scope(company_code=company, tag=tag, extra_employee_keys=(key, key_b))
    cleaned = cleanup.cleanup_synthetic_scope(app.db_connect, scope, known_ids=known_ids)
    check("cleanup residual_total", int(cleaned.get("residual_total") or 0) == 0, cleaned)
    check("cleanup contract version 1.3+|1.4+", str(cleanup.CLEANUP_CONTRACT_VERSION).startswith(("1.3", "1.4")), cleanup.CLEANUP_CONTRACT_VERSION)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
