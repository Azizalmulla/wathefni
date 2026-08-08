#!/usr/bin/env python3
"""Static proof for Employee App Visual Refinement Phase E.

Phase E adds six small things, and every one of them puts a claim on screen:
you have this much leave, you are asking for this many days, your manager is
reachable at this number, this document expires this soon. The way this phase
fails is not visually — it is by stating one of those claims when no system
actually asserted it, or by growing a second place that decides them.

So this file reads for provenance: does the number come from the server, is
there a local fallback that would fill in for it, does the screen still route
the way Phase C+D settled, and did any of the explicitly deferred features
appear anyway.

Arithmetic and abstention behaviour are proven in
scripts/high-value-additions-test.js; the server side of the two new reads is
proven in wathefni-orchestrator/smoke-test-employee-app-phaseE.py. This file
does not duplicate either.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]

passed = 0
failures: list[str] = []


def read(path: str, base: Path = ROOT) -> str:
    return (base / path).read_text(encoding="utf-8")


def check(label: str, ok: bool, detail: str = "") -> None:
    global passed
    if ok:
        passed += 1
        print(f"PASS  {label}")
    else:
        failures.append(label)
        print(f"FAIL  {label}{f' — {detail}' if detail else ''}")


def strip_comments(source: str) -> str:
    """Drop comments so a note explaining why a value is absent is not read as its use."""
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"^\s*//.*$", "", source, flags=re.M)


def function_body(source: str, signature: str) -> str:
    """Source from a declaration to the next top-level declaration."""
    start = source.index(signature)
    rest = source[start + len(signature):]
    end = re.search(r"\n(?:export )?function \w", rest)
    return signature + (rest[: end.start()] if end else rest)


print("Employee App Phase E — high-value additions\n")

leave_balance = read("src/features/leave/leaveBalance.ts")
remaining = read("src/features/remaining/RemainingViews.tsx")
remaining_code = strip_comments(remaining)
request_screen = read("app/leave/request.tsx")
request_code = strip_comments(request_screen)
profile = read("src/features/profile/ProfileView.tsx")
profile_code = strip_comments(profile)
home = read("src/features/home/HomeView.tsx")
home_code = strip_comments(home)
composition = read("src/composition/employeeAppComposition.ts")
composition_code = strip_comments(composition)
types = read("src/api/types.ts")
payslips = read("app/(tabs)/payslips.tsx")
documents = read("src/features/documents/DocumentsView.tsx")
contact = read("src/lib/contact.ts")
fmt = read("src/lib/format.ts")
en = read("src/i18n/en.json")
ar = read("src/i18n/ar.json")

# ---------------------------------------------------------------------------
# 1. Request Leave — balance is the server's, or it is absent
# ---------------------------------------------------------------------------
print("\n-- Request Leave: balance --")

check(
    "balance display is gated on the server's balances_enabled flag",
    "if (!data?.balances_enabled) return null" in leave_balance,
)
check(
    "only fields the API actually emits are read",
    "row.current_balance" in leave_balance and "row.available" in leave_balance,
)
check(
    "the phantom fields that produced a fake zero are gone from the contract",
    all(f not in strip_comments(types) for f in ("balance_days", "accrued_days", "consumed_days")),
    "types.ts still declares a field /app/leave has never sent",
)
check(
    "no screen still reads balance_days",
    "balance_days" not in remaining_code and "balance_days" not in request_code,
)
check(
    "a missing number is never coerced to zero",
    "?? 0" not in leave_balance and "|| 0" not in leave_balance,
)
check(
    "non-numeric values are refused rather than cast",
    "Number.isFinite" in leave_balance,
)
check(
    "Request Leave reads the balance through the shared accessor",
    "balanceForLeaveType(balances, leaveType)" in remaining_code,
)
check(
    "the balance shown is for the leave type being requested, not the first row",
    "balances.balances[0]" not in remaining_code and "balances[0]" not in remaining_code,
)
check(
    "Request Leave reuses the Leave tab's query key rather than a second fetch path",
    "['leave']" in request_code and "'/app/leave'" in request_code,
)
check(
    "balances are labelled as information while the server calls them non-binding",
    "balancesAreInformational" in remaining_code and "leave.notEnforced" in remaining_code,
)
check(
    "eligibility date is surfaced when the balance cannot yet be taken",
    "canTakeFrom" in remaining_code and "leave.canTakeFrom" in remaining_code,
)

# ---------------------------------------------------------------------------
# 2. Request Leave — duration comes from the server or not at all
# ---------------------------------------------------------------------------
print("\n-- Request Leave: requested duration --")

check(
    "duration is fetched from the server",
    "/app/leave/duration" in request_code,
)
check(
    "the request is keyed on the exact selection so a stale count cannot show",
    "'duration', selection?.startDate, selection?.endDate, selection?.leaveType" in request_code,
)
check(
    "the count is only rendered when the server says it is available",
    "duration?.available && typeof duration.chargeable_days === 'number'" in remaining_code,
)
check(
    "there is no local day-count fallback anywhere in the request flow",
    not re.search(r"getTime\(\)\s*-\s*\w+\.getTime\(\)\s*\)\s*/\s*86", remaining_code)
    and "86_400_000" not in remaining_code
    and "86400000" not in remaining_code,
    "a local millisecond day count would become a second answer",
)
check(
    "the copy says working days, matching what the server computes",
    '"You\'re requesting {{count}} working days"' in en or "working days" in en,
)
check(
    "a range with no working days says so instead of showing 0",
    "leave.noWorkingDays" in remaining_code,
)
check(
    "duration failures are not retried into an error state",
    "retry: false" in request_code,
)

# ---------------------------------------------------------------------------
# 3. Manager contact
# ---------------------------------------------------------------------------
print("\n-- Profile: manager contact --")

check(
    "the manager's name is shown when the roster has one",
    "employment.manager.name ||" in profile_code,
)
check(
    "the contact action appears only when the stored number is dialable",
    "telHref(employment.manager.phone)" in profile_code and "? {" in profile_code,
)
check(
    "an unrecognised number produces no action rather than a bad tel: link",
    "return null" in contact and "digits.length >= 9" in contact,
)
check(
    "dialling is a discrete control, not the whole row",
    "styles.detailAction" in profile_code and "accessibilityRole=\"button\"" in profile_code,
)
check(
    "the call target meets the touch-target floor",
    "width: layout.touchTarget" in profile and "height: layout.touchTarget" in profile,
)
check(
    "a device that cannot dial fails quietly",
    "Linking.canOpenURL" in profile_code,
)
check(
    "no chat, messaging or third-party contact channel was introduced",
    not any(w in profile_code.lower() for w in ("whatsapp", "wa.me", "sms:", "chat")),
)
check(
    "no manager contact field beyond what /app/profile returns is read",
    "manager.email" not in profile_code,
)

# ---------------------------------------------------------------------------
# 4. Inbox relative time
# ---------------------------------------------------------------------------
print("\n-- Inbox: relative time --")

check(
    "rows show relative time",
    "formatRelativeTime(item.created_at, locale, t)" in remaining_code,
)
check(
    "the exact timestamp is preserved for assistive technology",
    "formatDateTime(item.created_at, locale)" in remaining_code
    and "${exact}" in remaining_code,
)
check(
    "the exact timestamp is rendered in Kuwait time",
    "timeZone: 'Asia/Kuwait'" in fmt,
)
for key in ("time.justNow", "time.minutesAgo", "time.hoursAgo", "time.yesterday"):
    check(f"relative-time key {key} exists in EN and AR", f'"{key}"' in en and f'"{key}"' in ar)
check(
    "older messages fall back to a localized date rather than a growing day count",
    "formatDate(" in strip_comments(fmt).split("formatRelativeTime")[-1],
)

# ---------------------------------------------------------------------------
# 5. Payslips — multi-year history stays scalable and never a dead end
# ---------------------------------------------------------------------------
print("\n-- Payslips: year grouping --")

check("history is grouped by year", "groupPayslipsByYear(rows)" in payslips)
check("only the most recent year opens on arrival", "initiallyOpen={index === 0}" in payslips)
check(
    "a lone year cannot be collapsed into an empty screen",
    "collapsible={groups.length > 1}" in payslips,
)
check(
    "a non-collapsible group always renders its rows",
    "const expanded = open || !collapsible" in payslips,
)
check("each year is paged rather than rendered whole", "usePagedList(rows, PAYSLIP_PAGE)" in payslips)
check(
    "net pay keeps its prominence",
    "styles.netValue" in payslips or "payslips.net" in payslips,
)
check(
    "no search or filter chrome was added for a 12-per-year dataset",
    not any(w in strip_comments(payslips) for w in ("TextInput", "searchQuery", "onChangeText")),
)
check(
    "documents history gets the same single-year treatment",
    "collapsible={groups.length > 1}" in documents
    and "const expanded = open || !collapsible" in documents,
)

# ---------------------------------------------------------------------------
# 6. Document expiry task
# ---------------------------------------------------------------------------
print("\n-- Home: document expiry task --")

headline = function_body(home, "function taskHeadline(")
headline_code = strip_comments(headline)

check(
    "the task detail rides on the server projection, not a second Home fetch",
    "task.detail" in home_code and "'/app/documents'" not in home_code,
)
check(
    "Home does not re-query the documents module",
    "useAppQuery" not in home_code,
)
check(
    "the day count is derived from the server's expiry date",
    "daysUntil(task.detail?.expiry_date)" in headline_code,
)
check(
    "the document is named with the module's own label",
    "task.detail?.label" in headline_code,
)
check(
    "no detail means the generic label, never an implied urgency",
    headline_code.count("return generic") >= 3,
)
check(
    "an unparseable expiry falls back rather than rendering a wrong count",
    "if (days === null) return generic" in headline_code,
)
check(
    "already-expired and expiring-today are stated correctly, not as negative days",
    "days < 0" in headline_code and "days === 0" in headline_code,
)
check(
    "the expiry copy exists in both locales",
    all(f'"{k}"' in en and f'"{k}"' in ar
        for k in ("home.documentExpiresIn", "home.documentExpiresToday", "home.documentExpired")),
)
check(
    "empty detail fields cannot masquerade as present",
    "normalizeTaskDetail" in composition_code and "Object.keys(out).length" in composition_code,
)
check(
    "the task still routes to Documents",
    "document_renewal: '/documents'" in composition_code,
)
check(
    "no permanent expiry dashboard or new compliance surface was added",
    not (ROOT / "app" / "expiry.tsx").exists() and "expiryDashboard" not in home_code,
)

# ---------------------------------------------------------------------------
# 7. Settled navigation is untouched
# ---------------------------------------------------------------------------
print("\n-- Navigation from Phase C+D is unchanged --")

tabs_layout = read("app/(tabs)/_layout.tsx")
tab_order = re.findall(r'<Tabs\.Screen\s+name="([^"]+)"', tabs_layout)
check(
    "bottom tabs remain Home · Schedule · Leave · Payslips · Profile",
    tab_order == ["index", "schedule", "leave", "payslips", "profile"],
    str(tab_order),
)
check("Inbox is not a bottom tab", "notifications" not in tab_order)
check("Inbox remains the Home header bell", "InboxBell" in home_code)
check("Inbox route is still the canonical standalone route", "INBOX_ROUTE = '/notifications'" in composition)
check(
    "an unentitled module still leaves no dead tab slot",
    "? undefined : null" in tabs_layout,
)
check(
    "Documents is reachable without taking a tab slot",
    "'/documents'" in composition_code and "documents" not in tab_order,
)
check(
    "employeeAppComposition remains the only composition contract",
    not any((ROOT / "src" / "composition" / f).exists()
            for f in ("appComposition.ts", "navigationComposition.ts")),
)

# ---------------------------------------------------------------------------
# 8. Nothing deferred crept in; no raw keys returned
# ---------------------------------------------------------------------------
print("\n-- Scope guard --")

app_sources = "\n".join(
    strip_comments(p.read_text(encoding="utf-8"))
    for p in list((ROOT / "src").rglob("*.ts*")) + list((ROOT / "app").rglob("*.tsx"))
)

for feature, needles in {
    "certificates": ("certificateRequest", "requestCertificate", "salaryCertificate"),
    "announcements": ("announcement",),
    "shift acknowledgement": ("acknowledgeShift", "shiftAcknowledg"),
    "leave edit": ("editLeave", "updateLeaveRequest"),
    "YTD earnings": ("ytdEarnings", "yearToDate"),
    "chat": ("sendMessage(", "chatThread"),
    "clock in/out": ("clockIn", "clockOut", "punchIn"),
    "attendance dispute": ("disputeAttendance", "attendanceDispute"),
    "editable employment profile": ("updateEmployment", "editProfile("),
    "org chart / directory": ("orgChart", "employeeDirectory"),
    "payments / WPS": ("wpsFile", "paymentsRun"),
}.items():
    found = [n for n in needles if n in app_sources]
    check(f"deferred feature not introduced: {feature}", not found, str(found))

check(
    "no raw employee key is displayed to the employee",
    "employment?.employee_key" not in profile_code
    and "employment.employee_key" not in profile_code,
)
check(
    "no raw company code is displayed to the employee",
    "employment?.company_code" not in profile_code
    and "employment.company_code" not in profile_code,
)
check(
    "no invented staff number was fabricated in place of the missing field",
    not any(w in profile_code for w in ("staffNumber", "employeeNumber", "staff_number")),
)

# ---------------------------------------------------------------------------
# 9. Server side holds the authority
# ---------------------------------------------------------------------------
print("\n-- No new business authority on the client --")

orchestrator = REPO / "wathefni-orchestrator"
app_py = read("app.py", base=orchestrator)

check(
    "the duration endpoint exists server-side",
    '@app.get("/app/leave/duration")' in app_py,
)
check(
    "the client never computes chargeable days",
    "chargeable_leave_days" not in app_sources and "weekend_days" not in app_sources,
)
# The Documents screen reads `renewal_required` — that is the documents module's
# verdict arriving over the wire, which is exactly what it should render. What it
# must never do is assign one.
check(
    "the client reads the renewal verdict but never assigns one",
    not re.search(r"renewal_required\s*[:=][^:=]", app_sources),
    "the client is setting renewal_required rather than reading it",
)
check(
    "the client never decides whether a balance is enforceable",
    "balances_enforced = " not in app_sources and "enforce(" not in app_sources,
)
check(
    "leave submission is unchanged",
    "'/app/leave/request'" in request_code and "method: 'POST'" in request_code,
)

print(f"\n{passed} passed, {len(failures)} failed")
if failures:
    print("failing:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
