#!/usr/bin/env python3
"""Employee App Phase E — the two read-only exposures added for the mobile app.

Phase E surfaces two facts the app could not previously state without guessing:
how many days a leave range actually charges, and which document is expiring
next. Both are exposures of information the server already had. The risk is not
that they compute the wrong answer, it is that they quietly become a *second*
answer that drifts from the one the create path and the documents module give.

So these tests check agreement and abstention, not arithmetic:

  * the duration endpoint composes the same primitives as the create path, in
    the same order, and writes nothing;
  * the working-day arithmetic it exposes is the shared Kuwait function, so it
    cannot disagree with what a submitted request is charged;
  * the home task detail picks a row, and never dates, classifies, or invents.

Unit-only: `app.py` needs psycopg2 and a database, so the pure helper is read out
of the source tree and the endpoint is checked structurally.
"""

from __future__ import annotations

import ast
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

PASS = 0
FAILURES: list[str] = []

HERE = Path(__file__).resolve().parent


def check(label: str, cond: bool, detail: object = None) -> None:
    global PASS
    if cond:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAILURES.append(label)
        print(f"      FAIL  {label} :: {detail}")


def load_function(tree: ast.Module, name: str):
    """Exec a single top-level function in isolation, so app.py is never imported."""
    node = next(
        (n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name),
        None,
    )
    if node is None:
        return None, None
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    scope: dict = {"Any": object, "dict": dict, "list": list, "str": str}
    exec(compile(module, "<phaseE>", "exec"), scope)  # noqa: S102 - fixed local source
    return scope[name], node


def source_of(node: ast.AST, src: str) -> str:
    return ast.get_source_segment(src, node) or ""


def code_of(node: ast.AST, src: str) -> str:
    """Executable source only. Docstrings explain the rules, so scanning them for
    the very words the rules forbid would fail every well-documented function."""
    body = list(getattr(node, "body", []))
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return "\n".join(source_of(stmt, src) for stmt in body)


def main() -> int:
    print("    employee app phase E — leave duration exposure + home renewal detail")
    sys.path.insert(0, str(HERE))

    app_src = (HERE / "app.py").read_text()
    tree = ast.parse(app_src)

    # ---------------------------------------------------------------- duration
    duration_fn = next(
        (
            n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "app_leave_duration"
        ),
        None,
    )
    check("GET /app/leave/duration exists", duration_fn is not None)
    if duration_fn is None:
        print(f"\n    {PASS} passed, {len(FAILURES)} failed")
        return 1

    dsrc = source_of(duration_fn, app_src)
    decorators = [ast.unparse(d) for d in duration_fn.decorator_list]

    check(
        "route is a GET",
        any(d.replace("'", '"') == 'app.get("/app/leave/duration")' for d in decorators),
        decorators,
    )
    check(
        "gated on the same leave/request permission as submitting",
        'require_employee_app_feature(context, "leave", action="request")' in dsrc,
    )
    check(
        "scoped to the caller's company from the auth context, not a parameter",
        'context["company_code"]' in dsrc and "company_code:" not in dsrc,
    )

    # Read-only: an endpoint that priced a range and also reserved it would be a
    # second write path into leave.
    writes = [w for w in ("INSERT", "UPDATE ", "DELETE", "conn.commit()", "reserve_leave") if w in dsrc]
    check("writes nothing", not writes, writes)

    check(
        "reuses the create path's rest-day source (get_leave_policy)",
        "get_leave_policy(company, resolved_type)" in dsrc,
    )
    check(
        "reuses the create path's holiday calendar (holiday_dates_for_range)",
        "_leave_policy_w2.holiday_dates_for_range(cur, company, start, end)" in dsrc,
    )
    check(
        "reuses the shared chargeable-days function rather than counting locally",
        "chargeable_leave_days(" in dsrc,
    )
    check(
        "no local day arithmetic stands in for the shared function",
        ".days + 1" not in dsrc.split("chargeable_days")[0],
    )
    check(
        "same weekend fallback as the create path",
        '["fri", "sat"]' in dsrc,
    )
    check(
        "unreadable holiday calendar is reported, not silently priced as working days",
        "excluded_holidays = False" in dsrc and "excludes_public_holidays" in dsrc,
    )
    check(
        "an unanswerable range returns available:false instead of raising",
        '"available": False' in dsrc and "raise HTTPException" not in dsrc,
    )
    check(
        "reversed and unparseable ranges are refused before pricing",
        "end < start" in dsrc and '"invalid_range"' in dsrc,
    )
    check(
        "leave type is validated against the company's own list",
        "employee_app_leave_types(company)" in dsrc,
    )
    check(
        "no private cross-module helper is reached into",
        "_leave_policy_w2._" not in dsrc,
    )

    # The arithmetic itself is the shared Kuwait function; prove its semantics
    # are working days, so "N working days" in the app is a true statement.
    import leave_policy_wave2 as w2

    days = w2.chargeable_leave_days_kuwait(
        date(2026, 3, 12), date(2026, 3, 16), weekend_days=["fri", "sat"], holiday_dates=set()
    )
    check("Thu-Mon spanning a Fri/Sat weekend charges 3, not 5", days == Decimal("3"), days)

    days = w2.chargeable_leave_days_kuwait(
        date(2026, 3, 12), date(2026, 3, 16), weekend_days=["fri", "sat"], holiday_dates={date(2026, 3, 16)}
    )
    check("a public holiday inside the range is not charged", days == Decimal("2"), days)

    days = w2.chargeable_leave_days_kuwait(
        date(2026, 3, 13), date(2026, 3, 14), weekend_days=["fri", "sat"], holiday_dates=set()
    )
    check("a weekend-only range charges nothing", days == Decimal("0"), days)

    days = w2.chargeable_leave_days_kuwait(
        date(2026, 3, 12), date(2026, 3, 12), weekend_days=["fri", "sat"], holiday_dates=set()
    )
    check("a single working day charges 1", days == Decimal("1"), days)

    # ------------------------------------------------------- home task detail
    detail_fn, detail_node = load_function(tree, "_home_document_renewal_detail")
    check("home renewal detail helper exists", detail_fn is not None)
    if detail_fn is None:
        print(f"\n    {PASS} passed, {len(FAILURES)} failed")
        return 1

    hsrc = code_of(detail_node, app_src)
    check("detail helper touches no database", "cur." not in hsrc and "db_connect" not in hsrc)
    check(
        "detail helper computes no dates and no urgency of its own",
        "today" not in hsrc and "timedelta" not in hsrc and "days" not in hsrc,
    )
    check(
        "detail helper does not re-decide renewal_required",
        "renewal_required" not in hsrc,
    )

    check("no renewals means no detail", detail_fn([], locale="en") is None)

    rows = [
        {"document_type": "passport", "label": "Passport", "expiry_date": "2027-01-01",
         "label_ar": "جواز السفر", "review_status": "expiring_soon"},
        {"document_type": "civil_id", "label": "Civil ID", "expiry_date": "2026-08-26",
         "label_ar": "البطاقة المدنية", "review_status": "expiring_soon"},
    ]
    got = detail_fn(rows, locale="en")
    check("the soonest expiry is the one surfaced", got["document_type"] == "civil_id", got)
    check("canonical expiry date is passed through unchanged", got["expiry_date"] == "2026-08-26", got)
    check("the module's own label is used", got["label"] == "Civil ID", got)
    check("arabic locale uses the module's arabic label",
          detail_fn(rows, locale="ar")["label"] == "البطاقة المدنية")

    undated = [
        {"document_type": "medical", "label": "Medical", "expiry_date": None},
        {"document_type": "civil_id", "label": "Civil ID", "expiry_date": "2026-09-01"},
    ]
    got = detail_fn(undated, locale="en")
    check("a dated renewal outranks an undated one", got["document_type"] == "civil_id", got)

    only_undated = [{"document_type": "medical", "label": "Medical", "expiry_date": None}]
    got = detail_fn(only_undated, locale="en")
    check("an undated renewal yields no expiry date rather than a guessed one",
          got is not None and got["expiry_date"] is None, got)

    empty_row = [{"document_type": "", "label": "", "expiry_date": "", "review_status": ""}]
    check("a row with nothing to say produces no detail at all",
          detail_fn(empty_row, locale="en") is None)

    # -------------------------------------------------------------- home wiring
    home_fn = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "app_home"), None
    )
    home_src = source_of(home_fn, app_src) if home_fn else ""
    check(
        "home attaches detail from rows the documents module already produced",
        "_home_document_renewal_detail(renewals, locale=loc)" in home_src,
    )
    check(
        "home still counts renewals the documents module flagged",
        'row.get("renewal_required")' in home_src,
    )
    check(
        "detail is optional: a task without it is still emitted",
        "if detail:" in home_src,
    )

    print(f"\n    {PASS} passed, {len(FAILURES)} failed")
    if FAILURES:
        print(f"    failing: {', '.join(FAILURES)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
