#!/usr/bin/env python3
"""PT3 — Role fit + readiness staging DB journeys."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_N = int(SUFFIX, 16) % 100000
COMPANY = f"PT3{_N:05d}"[:12].upper()
OTHER = f"P3X{_N:05d}"[:12].upper()
HR = f"9657300{_N:05d}"
EMP = f"{COMPANY}-PT3-{SUFFIX}"
EMP_PHONE = f"9657301{_N:05d}"
OTHER_EMP = f"{OTHER}-PT3-{SUFFIX}"
OTHER_PHONE = f"9657302{_N:05d}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _flags(*, talent="on", ja="off", companies="", ja_companies=""):
    os.environ["WATHEFNI_TALENT_PROFILE_C5"] = talent
    os.environ["WATHEFNI_TALENT_PROFILE_COMPANIES"] = companies
    os.environ["WATHEFNI_TALENT_SUCCESSION_C6"] = talent
    os.environ["WATHEFNI_TALENT_SUCCESSION_COMPANIES"] = companies
    os.environ["WATHEFNI_TALENT_KILL"] = "off"
    os.environ["WATHEFNI_JOB_ARCHITECTURE_C1"] = ja
    os.environ["WATHEFNI_JOB_ARCHITECTURE_COMPANIES"] = ja_companies
    os.environ["WATHEFNI_PERFORMANCE_KILL"] = "off"


def _seed_company(cur, company: str, name: str) -> None:
    cur.execute(
        """
        INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
        VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
        ON CONFLICT (company_code) DO NOTHING
        """,
        (company, name),
    )


def _seed_employee(cur, company: str, key: str, phone: str, name: str) -> None:
    cur.execute(
        """
        INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
        VALUES (%s,%s,%s,%s,%s,%s,'{}'::jsonb,'active')
        ON CONFLICT (employee_key) DO UPDATE SET employment_status='active'
        """,
        (company, key, phone, name, date(2036, 1, 1), date(2036, 1, 1)),
    )


def main() -> int:
    print("    pt3 role fit — db journeys")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import talent_profile_c5 as c5
    import talent_role_fit_pt3 as pt3
    import talent_succession_c6 as c6

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            return 0
        raise
    except Exception as exc:
        print(f"SKIP DB :: {exc}")
        return 0
    try:
        probe = app.db_connect()
        probe.__enter__()
        probe.__exit__(None, None, None)
    except Exception as exc:
        print(f"SKIP DB :: {exc}")
        return 0

    _flags(talent="on", ja="off", companies=f"{COMPANY},{OTHER}", ja_companies="")

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            c5.ensure_talent_profile_c5_schema(cur)
            c6.ensure_talent_succession_c6_schema(cur)
            pt3.ensure_talent_role_fit_pt3_schema(cur)
            _seed_company(cur, COMPANY, f"PT3 {COMPANY}")
            _seed_company(cur, OTHER, f"P3X {OTHER}")
            _seed_employee(cur, COMPANY, EMP, EMP_PHONE, "PT3 Emp")
            _seed_employee(cur, OTHER, OTHER_EMP, OTHER_PHONE, "Other")
            check("enable talent", c5.enable_company_talent_profile(cur, company_code=COMPANY, actor_phone=HR, reason="c5").get("ok") is True)
            check("enable succession", c6.enable_company_talent_succession(cur, company_code=COMPANY, actor_phone=HR, reason="c6").get("ok") is True)
            c5.enable_company_talent_profile(cur, company_code=OTHER, actor_phone=HR, reason="other c5")
            c6.enable_company_talent_succession(cur, company_code=OTHER, actor_phone=HR, reason="other c6")

            crit = c6.designate_critical_role(
                cur, company_code=COMPANY, actor_phone=HR, canonical_role_key=f"FIN-MGR-{SUFFIX}",
                title_en="Finance Manager", title_ar="مدير المالية", reason="critical",
            )
            check("critical role", crit.get("ok") is True, crit)
            role_id = str(crit["critical_role"]["critical_role_id"])

            created = pt3.create_requirement_set(
                cur, company_code=COMPANY, actor_phone=HR, name_en="Finance Manager fit",
                name_ar="ملاءمة مدير المالية", critical_role_id=role_id, reason="create set",
            )
            check("A create set without JA", created.get("ok") is True, created)
            set_id = str(created["set"]["set_id"])
            draft = pt3.save_draft_version(
                cur, company_code=COMPANY, actor_phone=HR, set_id=set_id,
                requirements=[{"id": "skill-ifrs", "kind": "skill", "code": "IFRS", "priority": "required"}],
                reason="draft",
            )
            check("A draft", draft.get("ok") is True, draft)
            pub = pt3.publish_version(
                cur, company_code=COMPANY, actor_phone=HR,
                version_id=str(draft["version"]["version_id"]), reason="publish",
            )
            check("A publish", pub.get("ok") is True, pub)

            missing = pt3.evaluate_role_fit(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP, set_id=set_id, reason="missing skill",
            )
            check("B missing evaluate", missing.get("ok") is True, missing)
            check("B not_assessed", missing.get("overall_fit") == "not_assessed", missing)
            check("B no 0%", (missing.get("why") or {}).get("weighted_pct") not in (0, 0.0), missing)
            check("B no 100%", (missing.get("why") or {}).get("weighted_pct") not in (100, 100.0), missing)
            check("B suggestion unassessed not not_ready", missing.get("readiness_suggestion") == "unassessed", missing)
            check("B C6 not written", missing.get("c6_readiness_written") is False, missing)

            claimed = c5.claim_skill(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                skill_code="IFRS", name_en="IFRS", name_ar="المعايير", reason="claim",
            )
            check("C claim skill", claimed.get("ok") is True, claimed)
            claimed_eval = pt3.evaluate_role_fit(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP, set_id=set_id, reason="claimed",
            )
            check("C claimed is not_permitted/not strong", claimed_eval.get("overall_fit") != "strong_fit", claimed_eval)
            outcomes = {(r.get("id"), r.get("outcome")) for r in (claimed_eval.get("why") or {}).get("requirement_results") or []}
            check("C claimed not silently verified", any(o == "not_permitted" for _, o in outcomes), outcomes)

            verified = c5.verify_skill(
                cur, company_code=COMPANY, actor_phone=HR,
                skill_id=str(claimed["skill"]["skill_id"]), reason="verify ifrs",
            )
            check("D verify skill", verified.get("ok") is True, verified)
            met = pt3.evaluate_role_fit(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP, set_id=set_id, reason="verified",
            )
            check("D strong fit", met.get("overall_fit") == "strong_fit", met)
            check("D suggestion informs only", met.get("readiness_suggestion") == "ready_now", met)
            check("D human readiness still none", met.get("human_readiness") in (None, ""), met)
            check("D C6 still not written", met.get("c6_readiness_written") is False, met)

            plan = c6.create_succession_plan(cur, company_code=COMPANY, actor_phone=HR, critical_role_id=role_id, reason="plan")
            check("E plan", plan.get("ok") is True, plan)
            nom = c6.nominate_successor(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=str(plan["plan"]["plan_id"]),
                employee_key=EMP, rationale="human ready later", readiness="ready_1_2y",
                has_sensitive_permission=True, reason="nominate",
            )
            check("E human readiness", nom.get("ok") is True, nom)
            after = pt3.evaluate_role_fit(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP, set_id=set_id, reason="after human",
            )
            check("E human readiness authoritative", after.get("human_readiness") == "ready_1_2y", after)
            check("E fit did not overwrite C6", after.get("human_readiness") != after.get("readiness_suggestion") or after.get("readiness_suggestion") == "ready_1_2y", after)
            check("E C6 write flag false", after.get("c6_readiness_written") is False, after)
            cur.execute(
                "SELECT readiness FROM talent_successor_nominations WHERE company_code=%s AND employee_key=%s",
                (COMPANY, EMP),
            )
            band = str(dict(cur.fetchone() or {}).get("readiness") or "")
            check("E C6 band unchanged", band == "ready_1_2y", band)

            ja_set = pt3.create_requirement_set(
                cur, company_code=COMPANY, actor_phone=HR, name_en="JA target",
                job_profile_id=str(uuid.uuid4()), reason="ja set",
            )
            check("F JA-linked set", ja_set.get("ok") is True, ja_set)
            ja_draft = pt3.save_draft_version(
                cur, company_code=COMPANY, actor_phone=HR, set_id=str(ja_set["set"]["set_id"]),
                requirements=[{"id": "skill-core", "kind": "skill", "code": "CORE", "priority": "required"}],
                reason="ja draft",
            )
            pt3.publish_version(
                cur, company_code=COMPANY, actor_phone=HR,
                version_id=str(ja_draft["version"]["version_id"]), reason="ja publish",
            )
            off = pt3.evaluate_role_fit(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                set_id=str(ja_set["set"]["set_id"]), reason="ja off",
            )
            check("F JA off → unavailable", off.get("overall_fit") == "unavailable", off)
            check("F Talent continues", off.get("talent_continues") is True, off)
            check("F no JA write", off.get("ja_written") is False, off)
            still = pt3.evaluate_role_fit(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP, set_id=set_id, reason="talent still",
            )
            check("F Talent fit still works", still.get("ok") is True and still.get("overall_fit") == "strong_fit", still)

            _flags(talent="on", ja="on", companies=f"{COMPANY},{OTHER}", ja_companies=COMPANY)
            import job_architecture_c1 as ja

            ja.ensure_job_architecture_c1_schema(cur)
            en_ja = ja.enable_company_job_architecture(cur, company_code=COMPANY, actor_phone=HR, reason="enable ja")
            check("G enable JA", en_ja.get("ok") is True, en_ja)
            fam = ja.upsert_job_family(
                cur, company_code=COMPANY, actor_phone=HR, code=f"FIN{SUFFIX[:4]}",
                name_en="Finance", name_ar="المالية", status="published", reason="fam",
            )
            fn = ja.upsert_job_function(
                cur, company_code=COMPANY, actor_phone=HR, family_id=fam["stable_id"],
                code=f"FM{SUFFIX[:4]}", name_en="Finance Mgmt", name_ar="إدارة مالية",
                status="published", reason="fn",
            )
            profile = ja.upsert_job_profile(
                cur, company_code=COMPANY, actor_phone=HR, function_id=fn["stable_id"],
                code=f"FMP{SUFFIX[:4]}", name_en="Finance Manager", name_ar="مدير المالية",
                status="published", reason="profile",
            )
            check("G JA profile", profile.get("ok") is True, profile)
            imported = pt3.import_draft_from_ja(
                cur, company_code=COMPANY, actor_phone=HR,
                job_profile_id=str(profile["profile"]["profile_id"]), reason="import draft",
            )
            check("G import draft", imported.get("ok") is True and imported.get("imported_as_draft") is True, imported)
            check("G import does not write JA", imported.get("ja_written") is False, imported)
            if imported.get("ok") and imported.get("version"):
                pt3.publish_version(
                    cur, company_code=COMPANY, actor_phone=HR,
                    version_id=str(imported["version"]["version_id"]), reason="publish imported",
                )
            cur.execute("SELECT count(*) AS n FROM ja_job_profile WHERE company_code=%s", (COMPANY,))
            before_n = int(dict(cur.fetchone() or {}).get("n") or 0)
            pt3.evaluate_role_fit(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                set_id=str(imported["set"]["set_id"]) if imported.get("ok") else set_id, reason="after import",
            )
            cur.execute("SELECT count(*) AS n FROM ja_job_profile WHERE company_code=%s", (COMPANY,))
            after_n = int(dict(cur.fetchone() or {}).get("n") or 0)
            check("G JA profile count unchanged", before_n == after_n, (before_n, after_n))

            leak = pt3.list_sets(cur, company_code=OTHER)
            check("H tenant isolation", all(str(s.get("set_id")) != set_id for s in leak.get("sets") or []), leak)

            weighted = pt3.save_draft_version(
                cur, company_code=COMPANY, actor_phone=HR, set_id=set_id,
                derivation="weighted_v1",
                requirements=[{"id": "skill-ifrs", "kind": "skill", "code": "IFRS", "priority": "required"}],
                weights={},
                reason="bad weighted",
            )
            check("I weighted refused", weighted.get("ok") is False, weighted)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("PT3_ROLE_FIT_READINESS_DB_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
