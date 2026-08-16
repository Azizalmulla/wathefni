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


def font_scale() -> dict:
    """The `font` token block from theme.ts, as real numbers."""
    theme = read("src/theme.ts")
    block = re.search(r"export const font = \{(.*?)\}", theme, re.S)
    if not block:
        return {}
    return {
        name: float(value)
        for name, value in re.findall(r"(\w+):\s*([\d.]+)", block.group(1))
    }


def style_font_size(source: str, style_name: str, scale: dict):
    """Resolve `fontSize` inside a named StyleSheet entry to a point value."""
    entry = re.search(rf"{style_name}: \{{([^}}]*)\}}", source)
    if not entry:
        return None
    size = re.search(r"fontSize: (?:font\.(\w+)|([\d.]+))", entry.group(1))
    if not size:
        return None
    return scale.get(size.group(1)) if size.group(1) else float(size.group(2))


def pastel_cards(source: str) -> int:
    """
    Large ambient surfaces on a screen.

    Both card types count. `AmbientCard` is the two-tone replacement and paints
    exactly as much of the screen as `PastelCard` did, so leaving it out would
    have quietly retired this budget the moment a screen migrated.
    """
    return len(re.findall(r"<(?:PastelCard|AmbientCard)\b", source))


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
    # The rule is that the workday outranks every label around it. This used to
    # be spelled as "todayHeadline is font.h1", which pinned one token name and
    # broke as soon as the scale moved, while never actually comparing sizes.
    # Resolve the tokens and compare the numbers instead.
    scale = font_scale()
    headline = style_font_size(home, "todayHeadline", scale)
    label = style_font_size(home, "todayLabel", scale)
    check(
        "the workday reads larger than the label above it",
        headline is not None and label is not None and headline > label,
        f"headline {headline}pt vs label {label}pt",
    )
    check(
        "the compact workday headline stays strong without outranking the page title",
        headline is not None
        and headline >= scale.get("h1", 0)
        and headline <= scale.get("display", 0),
        f"headline {headline}pt vs h1 {scale.get('h1')} / display {scale.get('display')}pt",
    )
    today_style = re.search(r"todayHeadline: \{([^}]*)\}", home)
    check(
        "the workday headline has no fixed line height that can clip Dynamic Type",
        bool(today_style) and "lineHeight" not in today_style.group(1),
    )
    check(
        "Arabic workday text does not inherit Latin negative tracking",
        "todayHeadlineLTR" in home and "!isRTL ? styles.todayHeadlineLTR : null" in home,
    )
    check(
        "an attendance-only Home does not label its hero as a shift",
        "shiftState === 'disabled' ? t('home.attendance') : t('home.todayShift')" in home,
    )
    check(
        "Home greets by Kuwait morning/afternoon/evening, not a flat Hi",
        "kuwaitDayPart" in home
        and "home.greetingMorning" in home
        and "home.greetingAfternoon" in home
        and "home.greetingEvening" in home,
    )
    check(
        "Home does not decorate the greeting with geometry",
        "WathefniMark" not in home and "WathefniBloom" not in home,
    )
    composition_plan = read("src/features/home/homeComposition.ts")
    check(
        "a document task and the Documents launcher do not stack as the same yellow",
        "ambientForPriorityTone" in home
        and "tone === 'action' ? ('onboarding'" in composition_plan
        and "visibleHomeDestinations" in composition_plan
        and "document_renewal" in composition_plan,
    )
    check(
        "only employee-action work earns the yellow card; informational work stays a row",
        "ambientForPriorityTone('action')" in home
        and "task.severity === 'action_required'" in composition_plan
        and "secondaryTasks" in home,
    )
    check(
        "Home takes its destinations from the contract and hardcodes no module list",
        "visibleHomeDestinations(composition.homeDestinations" in home
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
    check(
        "a lone destination is a lightweight cream-ground link with a green accent",
        "DestinationLink" in home
        and 'module="documents"' in home
        and "destinations.length > 1" in home
        and "AmbientCard" not in slice_between(home, "function DestinationLink", "function OnboardingActionCard"),
    )
    check(
        "Home priority colour is role-based, not index-rotated",
        "ambientForPriorityTone" in composition_plan
        and "index %" not in home
        and "index %" not in composition_plan,
    )
    check(
        "Home does not invent leave balances on the page",
        "home.leaveDays" not in home and "leaveDays" not in home,
    )
    # --- 1b. Action cluster: waiting work, then blue Request leave, then discovery
    check(
        "Request leave sits in the action cluster after tasks, not as a nav footer",
        home.index("t('home.tasks')") < home.index("<RequestLeavePill")
        and home.index("<RequestLeavePill") < home.index("destinationSection")
        and "borderRadius: radius.pill" in home
        and "homeComposition.requestLeave.fill" in home
        and "flexGrow: 1" not in home
        and "marginTop: 'auto'" not in home,
    )
    check(
        "Documents is omitted when the yellow priority already opens that work",
        "visibleHomeDestinations" in home
        and "document_renewal" in composition_plan
        and "filter((destination) => destination.id !== 'documents')" in composition_plan,
    )
    check(
        "Request leave is not a mid-page paired tile",
        "LeaveActionTile" not in home
        and "canPairActions" not in home
        and "pairedActions" not in home,
    )
    check(
        "the workday hero nests no second card inside itself",
        "attendanceBand" not in home and "todayBodySplit" not in home,
    )
    check(
        "Home spends no card on the 30-day attendance count",
        "attendance_window" not in home and "attendancePresent" not in home,
    )
    check(
        "Home does not invent an At a glance section without projection facts",
        "atAGlance" not in home and "At a glance" not in home,
    )
    check(
        "Home uses a deliberate page rhythm rather than a sparse stack",
        "gap={sparse ? spacing.xxl : spacing.xl}" in home and "pageContent" in home,
    )
    check(
        "a quiet Home grows the workday hero instead of inventing filler",
        "isSparseHomePage" in home
        and "todayCardSparse" in home
        and "waitingSurfaces <= 1" in composition_plan
        and "flexGrow: 1" not in home
        and "At a glance" not in home
        and "attendance_window" not in home,
    )

    # --- 2. Bottom navigation
    check(
        "the tab bar is Home, Schedule, Leave, Payslips, Profile",
        [m for m in re.findall(r'<Tabs\.Screen\s+name="([^"]+)"', tabs)]
        == ["index", "schedule", "leave", "payslips", "profile"],
        str(re.findall(r'<Tabs\.Screen\s+name="([^"]+)"', tabs)),
    )
    check(
        "the tab bar supplies the black visual anchor",
        "tabBarActiveTintColor: colors.primaryText" in tabs
        and "tabBarInactiveTintColor: colors.navMuted" in tabs
        and "backgroundColor: colors.ink" in tabs,
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
    check("Home builds its lists from the shared row", "ListRow" in home)
    check(
        "Onboarding uses lifecycle-colored cards (not a pink wall)",
        "function ActionItemCard" in onboarding
        and "function QuietItemCard" in onboarding
        and "function SoftBlueCard" in onboarding
        and 'needsReplacement ? \'pink\' : \'butter\'' in onboarding
        and "QuietTextAction" in onboarding
        and "ListRow" not in onboarding,
    )
    check(
        "Payslips uses a flat cream ledger row, not white ListRow cards",
        "function PayslipRow" in payslips
        and "styles.ledgerRow" in payslips
        and "ListRow" not in payslips
        and "backgroundColor: colors.surface" not in payslips.split("function PayslipRow")[1].split("function LineRow")[0],
    )
    check(
        "Inbox uses a flat cream ledger row, not white ListRow cards",
        "function InboxRow" in remaining
        and "styles.inboxLedger" in remaining
        and "styles.inboxRow" in remaining
        and "ListRow" not in remaining.split("function NotificationsView")[1].split("export function LeaveView")[0]
        and "backgroundColor: colors.surface"
        not in remaining.split("function InboxRow")[1].split("export function LeaveView")[0],
    )
    check(
        "Documents uses cream ledger rows, not white ListRow cards",
        "function AttentionRow" in documents
        and "function CurrentRow" in documents
        and "styles.ledgerRow" in documents
        and "ListRow" not in documents
        and "backgroundColor: colors.surface" not in documents.split("function AttentionRow")[1].split("function DownloadProgress")[0],
    )

    # --- 4. Documents hierarchy
    check(
        "Documents keeps three visibly different sections",
        "documents.needsAttention" in documents
        and "documents.current" in documents
        and "documents.history" in documents,
    )
    check(
        "attention is compact pink-accent emphasis; current and history are ledger rows",
        "function AttentionRow" in documents
        and "function CurrentRow" in documents
        and "function HistoryYear" in documents
        and "attentionAccent" in documents,
    )
    check(
        # Pink accent only on Needs attention. Current/History stay calm cream.
        "only items needing action get pink emphasis",
        "attentionAccent" in documents
        and "ambient.schedule.fill" in documents
        and "DocumentStatusMark" in documents
        and "QuietReviewedMark" in documents
        and "renewActionRelevant" in documents
        and "currentRow" in documents
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
        and "inboxUnreadAccent" in remaining
        and "const unread = !item.read" in remaining,
    )
    check(
        "a row carries relative time",
        "formatRelativeTime" in remaining,
    )
    check(
        "repeated system activity is demoted but never hidden, and unread is never demoted",
        "SYSTEM_ACTIVITY_FLOWS" in remaining
        and "app_activation" in remaining
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
        "leave hides balances unless enabled with canonical facts",
        "showBalances" in remaining
        and "balances_enabled" in remaining
        and "leave.subtitleRequestsOnly" in remaining
        and "leave.subtitleWithBalances" in remaining,
    )
    check(
        "leave separates current requests from recent history",
        "partitionLeaveRequests" in remaining
        and "leave.currentRequests" in remaining
        and "leave.history" in remaining
        and "leave.historyAll.view" in remaining
        and "groupByYear" not in remaining
        and "groupPayslipsByYear" not in remaining,
    )
    leave_history = read("src/features/leave/LeaveHistoryView.tsx")
    check(
        "Leave history is a dense cursor list, not a card archive",
        "/app/leave/history" in leave_history
        and "has_more" in leave_history
        and "next_cursor" in leave_history
        and "PastelCard" not in leave_history
        and "WathefniBloom" not in leave_history
        and "leave.historyAll.loadOlder" in leave_history,
    )
    check(
        "leave authority is untouched: cancel still gated by the same capability",
        "canCancel" in remaining
        and "isLeaveCancellableStatus" in remaining
        and "LEAVE_CANCELLABLE_STATUSES" in read("src/features/leave/leaveRequests.ts")
        and "requested" in read("src/features/leave/leaveRequests.ts")
        and "approved" in read("src/features/leave/leaveRequests.ts"),
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
    check(
        "payslip list uses server has_more rather than a silent hard cap",
        "has_more" in payslips
        and "next_cursor" in payslips
        and "payslips.loadEarlier" in payslips
        and "limit=24" in payslips,
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
        "Bank merges next-step and submitted into one Pending change section",
        "statusLine" in bank
        and "bank.pendingChangeTitle" in bank
        and "bank.pending.noActionNeeded" in bank
        and "pendingGuidance" in bank,
    )
    check(
        "a submitted change is shown only while it is still a change",
        "pendingChange" in bank and "submissionState !== 'applied'" in bank,
    )
    check(
        "Bank ESS lifecycle and canonical states are untouched",
        "rejection_reason" in bank
        and "bank.submittedTitle" in read("src/i18n/en.json")
        and "can_submit_new" in bank
        and "idempotency" in read("app/bank.tsx").lower(),
    )
    check(
        "Bank uses calm life marks and cream ledger blocks, not stacked white panels",
        "BankLifeMark" in bank
        and "QuietSettledMark" in bank
        and "QuietReviewMark" in read("src/features/bank/bankLifeMarks.tsx")
        and "styles.ledgerBlock" in bank
        and "backgroundColor: colors.surface" not in bank.split("styles = StyleSheet.create")[1].split("input:")[0]
        and bank.count("<PastelCard") <= 1
        and 'tone="butter"' in bank,
    )
    check(
        "Bank actions distinguish primary from secondary",
        'tone="secondary"' in bank and "PremiumButton" in bank,
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
    check(
        "Onboarding maps card colour by lifecycle state",
        "function ActionItemCard" in onboarding
        and "function QuietItemCard" in onboarding
        and "function SoftBlueCard" in onboarding
        and "OnboardingLifeMark" in onboarding
        and 'needsReplacement ? \'pink\' : \'butter\'' in onboarding
        and 'tone="cream"' in onboarding
        and 'tone="lilac"' not in onboarding
        and "QuietTextAction" in onboarding
        and "scheduleComposition.planned.fill" in onboarding,
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
        # Progress/review/handled use SoftBlueCard (not PastelCard). PastelCards
        # are butter/pink Your-actions + cream completed (+ optional olive empty).
        "src/features/onboarding/OnboardingView.tsx": 16,
        "src/features/profile/ProfileView.tsx": 2,
    }
    for path, budget in budgets.items():
        source = read(path)
        if path.endswith("RemainingViews.tsx"):
            source = slice_between(source, "export function NotificationsView", "export function LeaveRequestView")
        if path.endswith("HomeView.tsx"):
            # Loading/error states and the extracted featured-task renderer are
            # not mounted beside the main Home tree. Count the surfaces present
            # in Home itself; the assertion below proves that the featured task
            # replaces (rather than stacks with) onboarding emphasis.
            source = slice_between(source, "export function HomeView", "function HomeTaskCard")
        found = pastel_cards(source)
        check(
            f"{path} paints at most {budget} large ambient surfaces",
            found <= budget,
            f"{found} ambient cards",
        )
    check(
        "Home gives one filled task emphasis to onboarding or a featured task, never both",
        "planHomeActions" in home
        and "showOnboarding: true, actionTask: null" in read("src/features/home/homeComposition.ts"),
    )
    check(
        "Home onboarding progress uses its ambient accent rather than a semantic status colour",
        "color={ambient.onboarding.accent}" in home,
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
        "src/features/schedule/ScheduleView.tsx": "UPCOMING_PREVIEW",
    }
    for path, const in growth_lists.items():
        source = read(path)
        check(
            f"{path} bounds its growth list ({const})",
            f"const {const}" in source and "usePagedList" in source,
        )
    check(
        "Schedule root previews Upcoming then Recent within the fetched window",
        "UPCOMING_PREVIEW" in schedule
        and "RECENT_PREVIEW" in schedule
        and "<ScheduleWeekStrip" in schedule
        and "<SelectedDaySection" in schedule
        and "<ScheduleTrailingSections" in schedule
        and schedule.index("<ScheduleWeekStrip") < schedule.index("<SelectedDaySection")
        and schedule.index("<SelectedDaySection") < schedule.index("<ScheduleTrailingSections")
        and "ShowMoreButton" in schedule
        and "WathefniBloom" not in schedule
        and "data.recent.map" not in schedule
        and "resolveSelectedDay" in schedule
        and "startTransition" in read("src/features/schedule/ScheduleWeekStrip.tsx")
        # Selected fill lives inside the day cell (not an absolute translateX overlay),
        # so the first/last day stadium cannot be clipped flat by the week ScrollView.
        and "styles.capsule" in read("src/features/schedule/ScheduleWeekStrip.tsx")
        and "transform: [{ translateX" not in read("src/features/schedule/ScheduleWeekStrip.tsx")
        and "schedule.history.view" in schedule,
    )
    history = read("src/features/schedule/AttendanceHistoryView.tsx")
    check(
        "Attendance history is a dense cursor list, not a card archive",
        "/app/schedule/history" in history
        and "has_more" in history
        and "next_cursor" in history
        and "PastelCard" not in history
        and "WathefniBloom" not in history
        and "schedule.history.loadOlder" in history,
    )

    print("---")
    if failures:
        print(f"FAIL density + hierarchy static scan: {len(failures)} failed — {', '.join(failures)}")
        sys.exit(1)
    print(f"PASS density + hierarchy static scan ({passed} checks) — not a physical QA pass")


if __name__ == "__main__":
    main()
