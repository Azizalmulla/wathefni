"""Close/reopen job opening smoke test (staging).

Covers the product gap identified during the Jobs page audit: there was no way
to stop a role from accepting new applicants. This proves:

  - `dashboard_set_position_status()` flips `positions.status` open<->closed,
    preserves apply_code/title, and is idempotent + company-scoped,
  - closing/reopening an "orphan" position (one that only exists via
    `applications`, no `positions` row yet) creates the row with a sensible
    derived title instead of erroring,
  - an unknown position_code (no positions row AND no applications) is
    rejected rather than silently creating a phantom job,
  - closing a job takes effect immediately for new WhatsApp/QR applicants —
    `public_role_by_apply_code()` (the actual intake gate) stops returning the
    role the moment it's closed, and returns it again once reopened,
  - tenant isolation: closing a position in company A never touches the same
    position_code in company B,
  - the Assistant/WhatsApp tools (`close_job_opening` / `reopen_job_opening`)
    resolve a job by exact APPLY code or fuzzy title through the same
    preflight-then-confirm shape as the rest of the action registry, and
    ask for clarification on zero/multiple matches instead of guessing,
  - the audit trail categorizes both dashboard and chat action types under
    "Candidates" so they don't fall into a generic "Other" bucket.

Run on a host with the orchestrator venv + (staging) database, e.g.:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-job-close-reopen.py

NEVER point this at the production database: it writes and deletes test companies.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

import action_registry
import app
from psycopg2.extras import Json

COMPANY_A = "JOBCLOSEA"
COMPANY_B = "JOBCLOSEB"
MARKER = "temporary_job_close_reopen_smoke"


class Checks:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, label: str, fn: Callable[[], bool]) -> None:
        try:
            ok = bool(fn())
        except Exception as exc:
            self.failed.append(f"{label} -> raised {type(exc).__name__}: {exc}")
            return
        (self.passed if ok else self.failed).append(label)

    def check_raises(self, label: str, fn: Callable[[], Any], exc_type: type[BaseException] = ValueError) -> None:
        try:
            fn()
        except exc_type:
            self.passed.append(label)
            return
        except Exception as exc:
            self.failed.append(f"{label} -> raised wrong type {type(exc).__name__}: {exc}")
            return
        self.failed.append(f"{label} -> did not raise")

    def report(self) -> int:
        for label in self.passed:
            print(f"      PASS  {label}")
        for label in self.failed:
            print(f"      FAIL  {label}")
        print(f"\n    {len(self.passed)} passed, {len(self.failed)} failed")
        return 1 if self.failed else 0


def _insert_position(cur: Any, company: str, code: str, title: str, status: str, apply_code: str | None) -> None:
    cur.execute(
        """
        INSERT INTO positions (company_code, position_code, title, status, apply_code, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,now(),now())
        ON CONFLICT (company_code, position_code) DO UPDATE SET status=EXCLUDED.status, apply_code=EXCLUDED.apply_code
        """,
        (company, code, title, status, apply_code),
    )


def _insert_application(cur: Any, company: str, app_key: str, position_code: str, position_title: str, phone: str) -> None:
    cur.execute(
        """
        INSERT INTO applications
            (app_key, phone, company_code, position_code, position_title, status, current_step,
             cv_received, screening_status, raw_json, data_source, ingested_at, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,'screening_complete','review',TRUE,'complete',%s,'production',now(),now(),now())
        ON CONFLICT (app_key) DO NOTHING
        """,
        (app_key, phone, company, position_code, position_title, Json({"smoke": MARKER, "cv": {"received": True}})),
    )


def _purge(cur: Any) -> None:
    companies = [COMPANY_A, COMPANY_B]
    cur.execute("DELETE FROM applications WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM positions WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM candidates WHERE phone LIKE %s", (f"{COMPANY_A}-%",))
    cur.execute("DELETE FROM candidates WHERE phone LIKE %s", (f"{COMPANY_B}-%",))
    cur.execute("DELETE FROM company_modules WHERE company_code = ANY(%s)", (companies,))


def setup() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company in (COMPANY_A, COMPANY_B):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                    (company, f"Job Close Reopen {company[-1]}", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
                )
                cur.execute(
                    "INSERT INTO company_modules (company_code, module_key, enabled, source, updated_at) "
                    "VALUES (%s,'pre_hiring',TRUE,'smoke',now()) "
                    "ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=TRUE",
                    (company,),
                )
            _purge(cur)
            # A real positions row with an apply_code, open, in both companies —
            # used to prove tenant isolation on the UPDATE.
            _insert_position(cur, COMPANY_A, "WELDER", "Senior Welder", "open", "APPLY-JOBCLOSEA-WELDER")
            _insert_position(cur, COMPANY_B, "WELDER", "Senior Welder", "open", "APPLY-JOBCLOSEB-WELDER")
            # An orphan position: only referenced by applications, no positions row.
            phone = f"{COMPANY_A}-cand0"
            cur.execute(
                "INSERT INTO candidates (phone, name) VALUES (%s,%s) ON CONFLICT (phone) DO NOTHING",
                (phone, "Candidate Zero"),
            )
            _insert_application(cur, COMPANY_A, f"{COMPANY_A}-app0", "ORPHANROLE", "Orphan Warehouse Lead", phone)
            # Two positions sharing a fuzzy-searchable word, to exercise the
            # "more than one match" clarification path.
            _insert_position(cur, COMPANY_A, "DRIVER1", "Delivery Driver North", "open", "APPLY-JOBCLOSEA-DRIVER1")
            _insert_position(cur, COMPANY_A, "DRIVER2", "Delivery Driver South", "open", "APPLY-JOBCLOSEA-DRIVER2")
        conn.commit()


def teardown() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            _purge(cur)
            cur.execute("DELETE FROM companies WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
        conn.commit()


def _fake_request(company: str) -> Any:
    return app.WhatsAppTurnRequest(
        account_id="default",
        conversation_id=f"smoke-job-close-{company}",
        sender_phone="00000000000",
        sender_role="hr_admin",
        raw_text="close the welder job",
        metadata={"company_code": company, "channel": "web_dashboard"},
    )


def run_checks(checks: Checks) -> None:
    # 1) Basic close -> reopen cycle preserves apply_code/title, flips status.
    closed = app.dashboard_set_position_status(COMPANY_A, "WELDER", "closed")
    checks.check("close sets status=closed", lambda: closed["status"] == "closed")
    checks.check("close preserves apply_code", lambda: closed["apply_code"] == "APPLY-JOBCLOSEA-WELDER")
    checks.check("close preserves title", lambda: closed["title"] == "Senior Welder")
    reopened = app.dashboard_set_position_status(COMPANY_A, "WELDER", "open")
    checks.check("reopen sets status=open", lambda: reopened["status"] == "open")
    checks.check("reopen preserves apply_code (QR unchanged)", lambda: reopened["apply_code"] == "APPLY-JOBCLOSEA-WELDER")

    # 2) Invalid status is rejected.
    checks.check_raises("invalid status raises ValueError", lambda: app.dashboard_set_position_status(COMPANY_A, "WELDER", "paused"))

    # 3) Unknown position_code (no positions row, no applications) is rejected —
    # must never silently create a phantom job from a typo'd code.
    checks.check_raises(
        "unknown position_code raises ValueError",
        lambda: app.dashboard_set_position_status(COMPANY_A, "NO-SUCH-CODE", "closed"),
    )

    # 4) Orphan position (applications only, no positions row yet): closing
    # creates the row with a title derived from the application data.
    orphan = app.dashboard_set_position_status(COMPANY_A, "ORPHANROLE", "closed")
    checks.check("orphan close derives title from applications", lambda: orphan["title"] == "Orphan Warehouse Lead")
    checks.check("orphan close sets status=closed", lambda: orphan["status"] == "closed")

    # 5) The actual intake gate: public_role_by_apply_code stops returning the
    # role once closed, and returns it again once reopened. This is the exact
    # mechanism WhatsApp candidate intake uses today (handle_public_candidate_apply_code_turn).
    app.dashboard_set_position_status(COMPANY_A, "WELDER", "open")
    live = app.public_role_by_apply_code("APPLY-JOBCLOSEA-WELDER")
    checks.check("open role is visible to public intake", lambda: bool(live) and live.get("position_code") == "WELDER")
    app.dashboard_set_position_status(COMPANY_A, "WELDER", "closed")
    gone = app.public_role_by_apply_code("APPLY-JOBCLOSEA-WELDER")
    checks.check("closed role disappears from public intake", lambda: gone is None)
    app.dashboard_set_position_status(COMPANY_A, "WELDER", "open")
    back = app.public_role_by_apply_code("APPLY-JOBCLOSEA-WELDER")
    checks.check("reopened role reappears in public intake", lambda: bool(back) and back.get("position_code") == "WELDER")

    # 6) Tenant isolation: closing WELDER in company A must not touch company B's
    # WELDER (same position_code, different tenant).
    app.dashboard_set_position_status(COMPANY_A, "WELDER", "closed")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM positions WHERE company_code=%s AND position_code=%s", (COMPANY_B, "WELDER"))
            b_status = cur.fetchone()["status"]
    checks.check("closing A's WELDER leaves B's WELDER open", lambda: b_status == "open")
    app.dashboard_set_position_status(COMPANY_A, "WELDER", "open")

    # 7) Action-registry match resolution: exact code, unique fuzzy title,
    # ambiguous title (2 matches), and no match.
    by_code = action_registry._find_job_opening_matches(app, COMPANY_A, position_code="WELDER", title=None)
    checks.check("match by exact code finds exactly WELDER", lambda: len(by_code) == 1 and by_code[0]["position_code"] == "WELDER")
    by_title = action_registry._find_job_opening_matches(app, COMPANY_A, position_code=None, title="orphan")
    checks.check("match by unique fuzzy title finds ORPHANROLE", lambda: len(by_title) == 1 and by_title[0]["position_code"] == "ORPHANROLE")
    ambiguous = action_registry._find_job_opening_matches(app, COMPANY_A, position_code=None, title="delivery driver")
    checks.check("ambiguous title returns both drivers", lambda: len(ambiguous) == 2)
    no_match = action_registry._find_job_opening_matches(app, COMPANY_A, position_code=None, title="no-such-role-xyz")
    checks.check("no match returns empty list", lambda: no_match == [])

    # 8) Full preflight-then-confirm round trip via ExecutionContext, resolving
    # by title (not code) — the realistic chat path ("close the welder job").
    request = _fake_request(COMPANY_A)
    ctx = action_registry.ExecutionContext(
        request=request,
        action={"title": "senior welder"},
        state={},
        graph_state={},
        intent={},
        legacy=app,
    )
    preflight = action_registry._close_job_opening_preflight(ctx)
    checks.check("close preflight resolves WELDER by fuzzy title", lambda: preflight["status"] == "ready" and preflight["position_code"] == "WELDER")
    executed = action_registry._close_job_opening_executor(ctx)
    checks.check("close executor sets status=closed", lambda: executed["status"] == "completed" and executed["position"]["status"] == "closed")
    checks.check("post-close intake gate closed", lambda: app.public_role_by_apply_code("APPLY-JOBCLOSEA-WELDER") is None)

    reopen_ctx = action_registry.ExecutionContext(
        request=request,
        action={"position_code": "WELDER"},
        state={},
        graph_state={},
        intent={},
        legacy=app,
    )
    reopen_preflight = action_registry._reopen_job_opening_preflight(reopen_ctx)
    checks.check("reopen preflight resolves WELDER by code", lambda: reopen_preflight["status"] == "ready")
    reopen_executed = action_registry._reopen_job_opening_executor(reopen_ctx)
    checks.check("reopen executor sets status=open", lambda: reopen_executed["status"] == "completed" and reopen_executed["position"]["status"] == "open")
    checks.check("post-reopen intake gate open again", lambda: app.public_role_by_apply_code("APPLY-JOBCLOSEA-WELDER") is not None)

    # 9) No identifier given -> needs_clarification, not a guess or a crash.
    blank_ctx = action_registry.ExecutionContext(
        request=request, action={}, state={}, graph_state={}, intent={}, legacy=app,
    )
    blank_preflight = action_registry._close_job_opening_preflight(blank_ctx)
    checks.check("no identifier -> needs_clarification", lambda: blank_preflight.get("needs_clarification") is True)

    # 10) Both dashboard and chat action types are categorized under
    # "Candidates" in the audit trail, not the generic "Other" bucket.
    checks.check("dashboard close audit category is Candidates", lambda: app._audit_category("job_opening_closed") == "Candidates")
    checks.check("dashboard reopen audit category is Candidates", lambda: app._audit_category("job_opening_reopened") == "Candidates")
    checks.check("chat close_job_opening audit category is Candidates", lambda: app._audit_category("close_job_opening") == "Candidates")
    checks.check("chat reopen_job_opening audit category is Candidates", lambda: app._audit_category("reopen_job_opening") == "Candidates")


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"job close/reopen smoke — companies {COMPANY_A}/{COMPANY_B} (env: {env or 'default'})")
    setup()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        teardown()
    code = checks.report()
    print("    JOB CLOSE/REOPEN: " + ("ALL CHECKS PASSED" if not code else "FAILURES PRESENT"))
    sys.exit(code)


if __name__ == "__main__":
    main()
