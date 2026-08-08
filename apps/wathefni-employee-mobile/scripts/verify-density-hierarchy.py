#!/usr/bin/env python3
"""Static proof for Employee App Visual Refinement Phase C+D.

Phase C+D is a hierarchy and density change, so most of it is structural: which
primitive a list is built from, whether a screen still owns a second route to a
tab, whether history is bounded, how many large coloured surfaces a screen paints.
Those are all readable in the source, and reading them here stops the next change
from quietly reintroducing what this phase removed.

Behavioural correctness (date ranges, relative time, year grouping, paging
arithmetic) is proven separately in scripts/density-hierarchy-test.js, and the
composition contract in scripts/composition-shapes-test.js. This file does not
duplicate them.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

passed = 0
failures: list[str] = []


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def check(label: str, ok: bool, detail: str = "") -> None:
    global passed
    if ok:
        passed += 1
        print(f"PASS  {label}")
    else:
        failures.append(label)
        print(f"FAIL  {label}{f' — {detail}' if detail else ''}")


def count(needle: str, haystack: str) -> int:
    return haystack.count(needle)


def strip_comments(source: str) -> str:
    """Drop comments so a note explaining why a value is absent is not read as its use."""
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"^\s*//.*$", "", source, flags=re.M)


def slice_between(source: str, start: str, end: str) -> str:
    """The part of a multi-screen file that belongs to the screens this phase touched."""
    return source[source.index(start) : source.index(end)]


def pastel_cards(source: str) -> int:
    """Large ambient surfaces on a screen. `<PastelCard` is the only one we paint."""
    return len(re.findall(r"<PastelCard\b", source))


def main() -> None:
    home = read("src/features/home/HomeView.tsx")
    tabs = read("app/(tabs)/_layout.tsx")
    root_layout = read("app/_layout.tsx")
    composition = read("src/composition/employeeAppComposition.ts")
    lists = read("src/components/lists.tsx")
    documents = read("src/features/documents/DocumentsView.tsx")
    remaining = read("src/features/remaining/RemainingViews.tsx")
    payslips = read("app/(tabs)/payslips.tsx")
    bank = read("src/features/bank/BankView.tsx")
    onboarding = read("src/features/onboarding/OnboardingView.tsx")
    profile = read("src/features/profile/ProfileView.tsx")
    schedule = read("src/features/schedule/ScheduleView.tsx")
    push = read("src/push/resolvePushDestination.ts")

    # --- 1. Home hierarchy: today, work, then only what the tab bar cannot reach
    check(
        "Home orders the day before the work and the work before the destinations",
        home.index("home.todayAtWork") < home.index("home.tasks") < home.index("home.destinations"),
    )
    check(
        "the workday reads larger than the label above it",
        bool(re.search(r"todayHeadline: \{[^}]*fontSize: font\.h1", home))
        and bool(re.search(r"todayLabel: \{[^}]*fontSize: font\.tiny", home)),
    )
    check(
        "Home takes its destinations from the contract and hardcodes no module list",
        "composition.homeDestinations.map" in home
        and "homeTiles.map" not in home
        and not re.search(r"onNavigate\('/\(tabs\)/(leave|schedule)'\)", home),
    )
    check(
        # The Leave tab, a Leave destination card and a Request leave button were
        # three routes to two jobs. Browsing leave is the tab; requesting it is a
        # different job and keeps its button.
        "Home keeps the leave request action but not a second route to the Leave tab",
        "composition.homePrimaryAction" in home
        and "TABBED_MODULE_SURFACES" in composition
        and "filter((id) => !tabbed.has(id))" in composition,
    )
    check(
        "the Home inbox strip is gone, replaced by the header bell",
        "inboxStrip" not in home
        and "InboxBell" in home
        # The projection's unread count is still read; only the strip that
        # duplicated the Inbox tab is gone.
        and "home.inbox.unread" in home,
    )
    check(
        "onboarding has one presence on Home, not a task and a progress card",
        "task.kind !== 'onboarding_documents'" in home and "showOnboardingCard" in home,
    )
    check(
        "an empty task list is only called 'all caught up' when the server says so",
        "home.caught_up" in home,
    )

    # --- 2. Bottom navigation
    check(
        "the tab bar is Home, Schedule, Leave, Payslips, Profile",
        [m for m in re.findall(r'<Tabs\.Screen\s+name="([^"]+)"', tabs)]
        == ["index", "schedule", "leave", "payslips", "profile"],
        str(re.findall(r'<Tabs\.Screen\s+name="([^"]+)"', tabs)),
    )
    check(
        "an unentitled module leaves no dead tab slot",
        count("href: hasFeature(", tabs) >= 3 and count("? undefined : null", tabs) >= 3,
    )
    check(
        "Inbox is a pushed screen, not a tab",
        'name="notifications"' in root_layout
        and "notifications" not in tabs
        and (ROOT / "app/notifications.tsx").exists()
        and not (ROOT / "app/(tabs)/notifications.tsx").exists(),
    )
    check(
        "Payslips is a tab and no longer also a pushed screen",
        (ROOT / "app/(tabs)/payslips.tsx").exists()
        and not (ROOT / "app/payslips.tsx").exists()
        and 'name="payslips"' not in root_layout,
    )
    check(
        "the Inbox route is declared once and reused by push and the bell",
        "export const INBOX_ROUTE" in composition
        and "INBOX_ROUTE" in push
        and "inboxEntry" in composition
        and composition.count("'/notifications'") >= 1,
    )
    check(
        "the pre-bell Inbox path is kept as an explicit alias, not guessed",
        "'/(tabs)/notifications': '/notifications'" in composition,
    )
    check(
        "unread is a number and a spoken label, never colour alone",
        "badgeText" in home and "home.unreadMessages" in home and "accessibilityLabel" in home,
    )

    # --- 3. Compact list primitive
    check(
        "a shared compact row primitive exists",
        "export function ListRow" in lists
        and "export function SectionHeader" in lists
        and "export function ShowMoreButton" in lists
        and "export function usePagedList" in lists,
    )
    check(
        "the row is a surface, and colour on it is opt-in",
        "backgroundColor: colors.surface" in lists and "icon ? (" in lists and "iconTint ?" in lists,
    )
    check(
        "emphasis on a row is semantic, not ambient",
        "colors.danger" in lists and "colors.warning" in lists and "colors.success" in lists,
    )
    for name, source in (
        ("Inbox", remaining),
        ("Documents", documents),
        ("Payslips", payslips),
        ("Onboarding", onboarding),
        ("Home", home),
    ):
        check(f"{name} builds its lists from the shared row", "ListRow" in source)

    # --- 4. Documents hierarchy
    check(
        "Documents keeps three visibly different sections",
        "documents.needsAttention" in documents
        and "documents.current" in documents
        and "documents.history" in documents,
    )
    check(
        "attention earns a card, current and history are rows",
        "function AttentionCard" in documents
        and "function CurrentRow" in documents
        and "function HistoryYear" in documents,
    )
    check(
        # Attention draws a semantic edge; current and history are plain rows. A
        # coloured edge on every document would mean nothing.
        "only items needing action get semantic emphasis",
        "borderColor: edge" in documents
        and "attentionCard" in documents
        and not re.search(r"<ListRow[^>]*emphasis=", documents, flags=re.S),
    )
    check(
        "history is grouped by year with older years closed",
        "groupHistoryByYear" in documents and "initiallyOpen={index === 0}" in documents,
    )
    check(
        "history is paged inside a year",
        "usePagedList" in documents and "HISTORY_PAGE" in documents and "ShowMoreButton" in documents,
    )
    check(
        "renew, re-upload and open flows survive the restructure",
        "onRenew" in documents and "onOpen" in documents and "onCancel" in documents,
    )
    check(
        # `documentType` is a lookup key for the i18n name, never printed. What must
        # never appear is a storage id or filename where a document name belongs.
        "no raw backend document key reaches the employee",
        "resolveLabel(entry.documentType, entry.label)" in documents
        # A row's name is always a resolved label, never a storage key or filename.
        and not re.search(r"title=\{(entry\.|item\.document_type|.*filename)", documents)
        and not re.search(r"<Text[^>]*>\s*\{\s*(entry\.fileId|entry\.id)\s*\}", documents),
    )

    # --- 5. Inbox
    check(
        "Inbox is a message list with unread first",
        "notifications.unread" in remaining
        and "function InboxRow" in remaining
        and "marked={!item.read}" in remaining,
    )
    check(
        "a row carries relative time",
        "formatRelativeTime" in remaining,
    )
    check(
        "repeated system activity is demoted but never hidden, and unread is never demoted",
        "SYSTEM_ACTIVITY_FLOWS" in remaining
        and "const unread = data.notifications.filter((item) => !item.read)" in remaining
        and "read.filter(isSystemActivity)" in remaining,
    )
    check(
        "an unrecognised backend flow is treated as real HR mail, not demoted",
        "!isSystemActivity(item)" in remaining,
    )
    check(
        "the Inbox invents no message authority: no compose, no reply, no chat",
        not re.search(r"\b(onReply|onCompose|sendMessage|conversation)\b", remaining),
    )
    check("Inbox pages long histories", "INBOX_PAGE" in remaining and "usePagedList" in remaining)

    # --- 6. Leave
    check(
        "a leave row is type, dates and status",
        "function LeaveRequestRowItem" in remaining and "formatDateRange" in remaining,
    )
    check("leave balances share one surface instead of one card each", "balanceRow" in remaining)
    check("leave requests are paged", "LEAVE_PAGE" in remaining)
    check(
        "leave authority is untouched: cancel still gated by the same capability",
        "canCancel" in remaining and "['requested', 'approved']" in remaining,
    )

    # --- 7. Payslips
    check(
        "net pay stays the headline of a payslip",
        "styles.net" in payslips and "typeScaling.display" in payslips,
    )
    check(
        "payslip history is grouped by year and paged, with only the current year open",
        "groupPayslipsByYear" in payslips
        and "initiallyOpen={index === 0}" in payslips
        and "PAYSLIP_PAGE" in payslips,
    )
    check(
        "a historical payslip is a row, not a coloured card",
        "function PayslipRow" in payslips and "PayslipRowCard" not in payslips,
    )
    check(
        "the PDF is still one tap from the payslip",
        "payslips.downloadPdf" in payslips and "download_available" in payslips,
    )

    # --- 8. Bank
    check(
        "Bank answers where the salary goes with one account surface",
        "paidAccount" in bank and "payroll_effective" in bank,
    )
    check(
        "the same masked account is not printed under two headings",
        "function sameDisplay" in bank and "showVerifiedSeparately" in bank,
    )
    check(
        "there is one human status line rather than a card per lifecycle state",
        "statusLine" in bank and "bank.nextStepTitle" in bank,
    )
    check(
        "a submitted change is shown only while it is still a change",
        "pendingChange" in bank and "submissionState !== 'applied'" in bank,
    )
    check(
        "Bank ESS lifecycle and canonical states are untouched",
        "rejection_reason" in bank
        and "bank.submittedTitle" in bank
        and "can_submit_new" in bank
        and "idempotency" in read("app/bank.tsx").lower(),
    )

    # --- 9. Onboarding
    check(
        # Upload progress bars are a different thing and are not counted here.
        "onboarding has one progress hierarchy: state, count, bar, next action",
        onboarding.count("<MotionProgressBar value={progress}") == 1
        and "onboarding.completionTitle" not in onboarding
        and "completionMessage" in onboarding
        and "progressBubble" not in onboarding,
    )
    check(
        "HR-owned work is named rather than reduced to a count",
        "handledByOthers.map" in onboarding and "{{count}}" not in read("src/i18n/en.json").split('"onboarding.handledByOthersNote": "')[1].split('"')[0],
    )
    check(
        "finished onboarding items are a closed record, not a task list",
        "function CompletedSection" in onboarding and "useState(false)" in onboarding,
    )
    check(
        "onboarding still reads the canonical Wave 2A completion contract",
        "completionState" in onboarding and "projection.requiredTotal" in onboarding,
    )

    # --- 10. Profile
    check(
        "the hero owns identity and no detail row repeats it",
        "profileName" in profile
        and "position_title" in profile.split("styles.section")[0]
        and "profile.name" not in profile
        and "profile.position" not in profile,
    )
    check(
        "Personal is contact detail",
        "profile.phone" in profile and "profile.email" in profile,
    )
    check(
        "Employment is department, start date and manager",
        "profile.department" in profile and "profile.startDate" in profile and "profile.manager" in profile,
    )
    check(
        "no raw internal identifier is presented as an employee-facing value",
        "employee_key" not in strip_comments(profile) and "company_code" not in strip_comments(profile),
    )
    check("Bank stays under Profile", "profile.bank" in profile and "bank.menuEntry" in profile)

    # --- 11. Restraint: cream and ink dominate, colour is deliberate
    budgets = {
        "src/features/home/HomeView.tsx": 4,
        "src/features/documents/DocumentsView.tsx": 3,
        # Only the Inbox and Leave screens are in this phase's scope; Settings,
        # Privacy and Not-found live in the same file and are measured separately.
        "src/features/remaining/RemainingViews.tsx": 2,
        "app/(tabs)/payslips.tsx": 3,
        "src/features/bank/BankView.tsx": 4,
        "src/features/onboarding/OnboardingView.tsx": 6,
        "src/features/profile/ProfileView.tsx": 2,
    }
    for path, budget in budgets.items():
        source = read(path)
        if path.endswith("RemainingViews.tsx"):
            source = slice_between(source, "export function NotificationsView", "export function LeaveRequestView")
        found = pastel_cards(source)
        check(
            f"{path} paints at most {budget} large ambient surfaces",
            found <= budget,
            f"{found} PastelCards",
        )
    check(
        "WathefniBloom stays a rare moment, not a decoration on every card",
        sum(read(p).count("<WathefniBloom") for p in budgets) <= 4,
        str({p: read(p).count("<WathefniBloom") for p in budgets}),
    )
    check(
        "IconBadge is opt-in: it is not applied by the shared row",
        "IconBadge" not in lists and "IconBadge" not in home,
    )
    check(
        "no list-position-driven colour survived the restructure",
        not re.search(r"index\s*%\s*\d\s*\?", "\n".join(read(p) for p in budgets)),
    )

    # --- 12. Long-history scalability
    growth_lists = {
        "src/features/documents/DocumentsView.tsx": "HISTORY_PAGE",
        "src/features/remaining/RemainingViews.tsx": "INBOX_PAGE",
        "app/(tabs)/payslips.tsx": "PAYSLIP_PAGE",
    }
    for path, const in growth_lists.items():
        source = read(path)
        check(
            f"{path} bounds its growth list ({const})",
            f"const {const}" in source and "usePagedList" in source,
        )
    check(
        "Schedule's capped recent history is unchanged",
        "data.recent.map" in schedule and "usePagedList" not in schedule,
    )

    print("---")
    if failures:
        print(f"FAIL density + hierarchy static scan: {len(failures)} failed — {', '.join(failures)}")
        sys.exit(1)
    print(f"PASS density + hierarchy static scan ({passed} checks) — not a physical QA pass")


if __name__ == "__main__":
    main()
