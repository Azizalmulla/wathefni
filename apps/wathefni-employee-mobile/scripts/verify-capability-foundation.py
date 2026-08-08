#!/usr/bin/env python3
"""Static, dependency-free verification of employee app authority wiring."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def check(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def composition_src(root) -> str:
    return (root / "src/composition/employeeAppComposition.ts").read_text(encoding="utf-8")


def main() -> None:
    auth = read("src/auth/AuthProvider.tsx")
    tabs = read("app/(tabs)/_layout.tsx")
    home = read("app/(tabs)/index.tsx")
    home_view = read("src/features/home/HomeView.tsx")
    premium = read("src/components/premium.tsx")
    motion = read("src/motion.ts")
    leave_request = read("app/leave/request.tsx")
    leave = read("app/(tabs)/leave.tsx")
    notifications = read("app/notifications.tsx")
    onboarding = read("app/onboarding.tsx")
    onboarding_view = read("src/features/onboarding/OnboardingView.tsx")
    documents = read("app/documents.tsx")
    settings = read("app/settings.tsx")
    privacy_support = read("app/privacy-support.tsx")

    check("AuthProvider stores typed /app/me", "MeResponse" in auth and "setMe(next)" in auth)
    refresh = read("src/lib/refresh.tsx")
    soft = read("src/lib/employeeSoftRefresh.ts")
    check(
        "entitlement soft-refresh on foreground",
        "AppState.addEventListener" in refresh and "softRefreshEmployeeSurfaces" in refresh and "refreshMe" in soft,
    )
    check("local PIN seals tokens while locked", "sealedSessionRef" in auth and "'locked'" in auth)
    check("local PIN setup status exists", "'needsPinSetup'" in auth and "createLocalPin" in auth)
    check("document download refreshes on 401", "result.status === 401" in auth and "rotateSessionAndLoadMe" in auth)
    check(
        "optional tabs are capability-driven",
        "hasFeature('shifts') || hasFeature('attendance')" in tabs
        and "hasFeature('leave')" in tabs
        and "hasFeature('payslips')" in tabs,
    )
    check(
        # The tab bar is for places an employee works. Inbox is a place things
        # arrive, so it moved to the Home bell and freed the slot for Payslips.
        "Inbox is not a bottom tab, and Payslips took the slot",
        "notifications" not in tabs
        and 'name="payslips"' in tabs
        and "'/notifications'" in composition_src(ROOT)
        and "inboxEntry" in composition_src(ROOT),
    )
    composition = read("src/composition/employeeAppComposition.ts")
    check(
        "home reads the server-owned projection instead of re-querying modules",
        "/app/home?locale=" in home
        and "HomeResponse" in home
        and "/app/shifts/today" not in home
        and "/app/attendance" not in home
        and "/app/leave" not in home
        and "/app/onboarding" not in home,
    )
    check(
        "home presents server tasks and never re-derives them from status strings",
        "homeTasksFromServer" in home
        and "homeTasksFromState" not in composition
        and "needs_correction" not in home
        and "'requested'" not in home,
    )
    check(
        "home actions are capability-driven",
        "homeDestinations" in home_view
        and "homePrimaryAction" in home_view
        and "canUseFeatureAction(me, 'leave', 'request')" in composition,
    )
    check(
        "phase5 composition contract exists",
        "compositionFromMe" in composition
        and "separateComplianceTab: false" in composition
        and "CORE_SURFACES" in composition
        and "MODULE_SURFACES" in composition,
    )
    check(
        "inbox not counted as purchased home module",
        "wideHomeTiles" in composition
        and "homeTiles" in composition
        and "InboxBell" in home_view
        and "inboxEntry" in composition
        and "moduleCount" not in home_view,
    )
    check(
        "home has a single launcher, not tiles plus duplicate quick actions",
        "homeDestinations" in composition
        and "quickAction" not in home_view
        and "home.quickActions" not in home_view,
    )
    check(
        "onboarding demotes when complete",
        "showOnboardingJourney" in home_view and "onboardingDemoted" in composition,
    )
    push = read("src/push/PushLifecycle.tsx")
    push_resolve = read("src/push/resolvePushDestination.ts")
    check(
        "deep links resolve through the strict route registry",
        "APP_ROUTES" in composition
        and "resolveRoute" in composition
        and "openableHref" in notifications
        and "openableHref" in home
        and "openableHref" in push_resolve
        and "pushFollowThroughHref" in push
        and "raw.includes('://')" in composition,
    )
    check(
        "push taps follow through when entitled, else Inbox/Home",
        "pushFollowThroughHref" in push_resolve
        and "candidatePathFromPushData" in push_resolve
        and "FLOW_DEFAULT_PATHS" in push_resolve
        and "getLastNotificationResponseAsync" in push
        # Registration may be off in production; tap handling must still run when signed in.
        and "signedIn" in push
        and "PUSH_REGISTRATION_ENABLED" in push,
    )
    check(
        "unknown or unentitled links fall back to Home calmly",
        "HOME_ROUTE" in home
        and "router.replace(HOME_ROUTE" in home
        and "home.linkUnavailable" in notifications,
    )
    module_state = read("src/lib/moduleState.ts")
    check(
        "home tracks per-module read state",
        "ModuleDataState" in module_state
        and "asModuleDataState" in module_state
        and "home.modules" in home_view
        and "HomeModuleReadState" in read("src/api/types.ts"),
    )
    check(
        "an unrecognized module state fails closed instead of claiming ready",
        "'error'" in module_state and "MODULE_DATA_STATES.includes" in module_state,
    )
    check(
        "home never states an unavailable module as an empty business fact",
        "isModuleFactual" in home_view
        and "ModuleValue" in home_view
        and "home.dataUnavailable" in home_view
        and "home.noAttendanceToday" not in home_view,
    )
    check(
        "today's attendance is proven to be today's record",
        "home.today.attendance" in home_view
        and "records?.[0]" not in home_view
        and "latestAttendance" not in home_view,
    )
    # --- Schedule: one read-only surface over the Shifts and Attendance authorities.
    schedule_route = read("app/(tabs)/schedule.tsx")
    schedule_view = read("src/features/schedule/ScheduleView.tsx")
    remaining = read("src/features/remaining/RemainingViews.tsx")
    check(
        "the split Shifts and Attendance surfaces are gone",
        not (ROOT / "app/(tabs)/shifts.tsx").exists()
        and not (ROOT / "app/attendance.tsx").exists()
        and "ShiftsView" not in remaining
        and "AttendanceView" not in remaining,
    )
    check(
        "Schedule opens on either contributing entitlement",
        "hasFeature('shifts') || hasFeature('attendance')" in schedule_route
        and "FeatureUnavailableState" in schedule_route,
    )
    check(
        "Schedule reads the server-owned workday projection, not the module endpoints",
        "/app/workday?locale=" in schedule_route
        and "WorkdayResponse" in schedule_route
        and "/app/shifts" not in schedule_route
        and "/app/attendance" not in schedule_route,
    )
    check(
        "Schedule shows today's expectation beside today's record",
        "schedule.expected" in schedule_view
        and "schedule.recorded" in schedule_view
        and "today.entries" in schedule_view,
    )
    check(
        "an unavailable authority stays informational instead of reading as empty",
        "AuthorityUnavailableCard" in schedule_view
        and "isModuleFactual" in schedule_view
        and "asModuleDataState" in schedule_view
        and "authority.shifts" in schedule_view
        and "authority.attendance" in schedule_view,
    )
    check(
        "Schedule is read-only: no clocking, correction or write of any kind",
        not any(
            token in (schedule_view + schedule_route)
            for token in (
                "clockIn",
                "clock_in",
                "onClock",
                "requestCorrection",
                "useAppMutation",
                "apiPost",
                "method: 'POST'",
            )
        ),
    )
    check(
        "Schedule states that HR owns the schedule and the record",
        "schedule.hrAuthority" in schedule_view,
    )
    check(
        "Schedule presents stored values and computes no lateness or duration of its own",
        "record.late_minutes" in schedule_view
        and "record.early_leave_minutes" in schedule_view
        and "Date.now()" not in schedule_view
        and ".getTime()" not in schedule_view,
    )
    check(
        "Schedule renders attendance times in Kuwait time, not device time",
        "formatClockTime" in schedule_view and "Asia/Kuwait" in read("src/lib/format.ts"),
    )
    payslips = read("app/(tabs)/payslips.tsx")
    profile_route = read("app/(tabs)/profile.tsx")
    profile_view = read("src/features/profile/ProfileView.tsx")
    documents_view = read("src/features/documents/DocumentsView.tsx")
    documents_hierarchy = read("src/features/documents/documentsHierarchy.ts")
    settings_route = read("app/settings.tsx")
    check(
        "Profile reads /app/profile instead of inventing a second employee store",
        "/app/profile" in profile_route
        and "ProfileResponse" in profile_route
        and "refreshMe()" in profile_route,
    )
    check(
        "Profile hierarchy is Personal / Employment / Bank / Account",
        "profile.personal" in profile_view
        and "profile.employment" in profile_view
        and "profile.bank" in profile_view
        and "onPayslips" not in profile_view
        and "onDocuments" not in profile_view,
    )
    check(
        # The hero states name and job title. Repeating them as the first row of
        # Personal and of Employment made the screen open with three identical facts.
        "Profile states identity once: hero only, never again as a detail row",
        "profile.name" not in profile_view and "profile.position" not in profile_view,
    )
    check(
        "Bank remains only under Profile, not Settings",
        "onBank=" in profile_route
        and "onBank=" not in settings_route
        and "onBank" not in remaining,
    )
    check(
        "Documents hierarchy separates attention, current, and history",
        "documents.needsAttention" in documents_view
        and "documents.current" in documents_view
        and "documents.history" in documents_view
        and "documentsHierarchy" in documents_hierarchy
        and "currentFileIds" in documents_hierarchy,
    )
    check(
        "Documents renew still invalidates onboarding and Home tasks",
        "queryKey: ['onboarding']" in read("app/documents.tsx")
        and "queryKey: ['home']" in read("app/documents.tsx")
        and "upload_document" in read("app/documents.tsx"),
    )
    check(
        "Payslips group earnings and deductions with net pay prominence",
        "payslips.earnings" in payslips
        and "payslips.deductions" in payslips
        and "payslips.net" in payslips
        and "FileSystem.deleteAsync(target" in payslips,
    )
    check(
        "Payslip payment date comes from payroll and is omitted when unconfirmed",
        # The row previously printed "Payment date: Not available" unconditionally
        # because it never read the API field. It must read payment_date and render
        # the row only when payroll has recorded one.
        "payslip?.payment_date" in payslips
        and "paymentDate ? (" in payslips
        and "paymentDateUnknown" not in payslips
        and "payslips.paymentDateUnknown" not in read("src/i18n/en.json")
        and "payslips.paymentDateUnknown" not in read("src/i18n/ar.json"),
    )
    check(
        "Inbox rows expose VoiceOver labels and keep Phase 1 deep-link gating",
        "accessibilityLabel" in remaining
        and "notifications.unread" in remaining
        and "openableHref" in notifications
        and "home.linkUnavailable" in notifications,
    )
    check(
        "Settings keeps Auth diagnostics build-gated and offers device-security retry",
        "isAutoLockDiagnosticsEnabled()" in settings_route
        and "onRetryDeviceSecurity" in settings_route
        and "deviceSecurity.unavailable" in remaining,
    )
    check(
        "payslip share copy is removed from the cache",
        "FileSystem.deleteAsync(target" in payslips and "finally" in payslips,
    )
    auto_lock_policy = read("src/auth/autoLockPolicy.ts")
    check(
        "auto-lock diagnostics are build-gated",
        "isAutoLockDiagnosticsEnabled" in auto_lock_policy
        and "EXPO_PUBLIC_LOCAL_AUTO_LOCK_DIAGNOSTICS" in auto_lock_policy
        and "isAutoLockDiagnosticsEnabled()" in settings,
    )
    check(
        "unsupported employee compliance tab remains absent",
        "compliance" not in tabs.lower() and "separateComplianceTab: false" in composition,
    )
    check(
        "temporary design preview does not ship",
        not (ROOT / "src/designPreview.ts").exists()
        and not (ROOT / "app/design-preview.tsx").exists(),
    )
    check(
        "Wathefni branding is typography only",
        "function Wordmark" in premium
        and "Newsreader_600SemiBold" in premium
        and "NotoKufiArabic_600SemiBold" in premium
        and "brandMark" not in premium,
    )
    check(
        "motion respects reduced-motion preference",
        "isReduceMotionEnabled" in motion and "reduceMotionChanged" in motion,
    )
    check("leave types come from backend", "me?.leave.types" in leave_request and "LEAVE_TYPES" not in leave_request)
    check("documents do not read secure-store tokens directly", "loadSession" not in documents and "downloadFile" in documents)
    check("documents expose an explicit back control", "onBack={() => router.back()}" in documents)
    check("settings expose an explicit back control", "onBack={() => router.back()}" in settings)
    check(
        "account deletion is capability-gated and repeat-locked",
        "can('settings', 'request_deletion')" in settings
        and "deletionLock.current" in settings
        and "deleteBusy={deletionBusy || deletionRequested}" in settings,
    )
    check(
        "onboarding uploads are capability-gated",
        "can('onboarding', 'upload_document')" in onboarding
        and "if (!canUploadDocuments" in onboarding
        and "const primaryAction = allowUpload" in onboarding_view,
    )
    check(
        "repeatable mobile mutations are locked",
        "cancelLocks.current" in leave and "markReadLocks.current" in notifications,
    )
    check(
        "privacy URL is centralized",
        "@/config" in privacy_support
        and "https://wathefni.ai/employee-app/privacy" not in privacy_support,
    )
    check("localized not-found route exists", (ROOT / "app/+not-found.tsx").is_file())

    bank_route = read("app/bank.tsx")
    bank_view = read("src/features/bank/BankView.tsx")
    projection = read("src/features/onboarding/lifecycleProjection.ts")

    check(
        "bank screen reads the backend bank contract only",
        "/app/bank?locale=" in bank_route
        and "/app/bank/requests" in bank_route
        and "/app/bank/evidence" in bank_route,
    )
    check(
        "bank submissions are idempotent across retries",
        "idempotencyKey.current" in bank_route and "idempotency_key: idempotencyKey.current" in bank_route,
    )
    check(
        "sensitive bank input is not retained after submit",
        "setForm({})" in bank_route,
    )
    check(
        "bank evidence opens through the authorized stream, never a raw URL",
        "openPrivateFile" in bank_route
        and "http://" not in bank_view
        and "https://" not in bank_view
        and "Linking.openURL" not in bank_view,
    )
    check(
        "bank screen separates verified, payroll-effective and submitted",
        "bank.verifiedTitle" in bank_view
        and "payroll_effective" in bank_view
        and "bank.submittedTitle" in bank_view,
    )
    check(
        "bank screen states cover every submission state",
        all(
            f"bank.state.{state}" in bank_view or f"'{state}'" in bank_view
            for state in ("draft", "pending_review", "approved", "rejected", "needs_correction", "withdrawn")
        ),
    )
    check(
        "bank rejection reason and next step are surfaced",
        "rejection_reason" in bank_view and "bank.nextStepTitle" in bank_view,
    )
    check(
        "controlled rollout renders an explained state, not an error loop",
        "bank_ess_not_allowlisted" in bank_route and "BankUnavailableView" in bank_route,
    )
    check(
        "onboarding completion comes from the canonical contract",
        "COMPLETION_STATES" in projection
        and "data.completion" in projection
        and "waiting_on_employee" in projection
        and "reopened" in projection,
    )
    check(
        "app never recomputes completion locally",
        "is_complete =" not in projection and "computeCompletion" not in projection,
    )
    check(
        "next action copy comes from the backend, not a local state table",
        projection.find("action?.message_en") < projection.find("onboarding.next."),
    )
    check(
        "onboarding bank CTA requires open_bank action from backend eligibility",
        "actions.has('open_bank')" in onboarding_view
        and "canOpenBank" in onboarding_view
        and "hasFeature('bank')" in onboarding,
    )
    check(
        "bank route respects the same feature gate as onboarding",
        "hasFeature('bank')" in bank_route and "BankUnavailableView" in bank_route,
    )

    optional_routes = {
        "app/(tabs)/leave.tsx": "leave",
        "app/onboarding.tsx": "onboarding",
        "app/documents.tsx": "documents",
        "app/leave/request.tsx": "leave",
    }
    for path, feature in optional_routes.items():
        source = read(path)
        check(
            f"{path} blocks direct access without {feature}",
            f"hasFeature('{feature}')" in source and "FeatureUnavailableState" in source,
        )

    access_states = read("src/components/AccessStates.tsx")
    feature_copy = read("src/lib/featureUnavailableCopy.ts")
    check(
        "FeatureUnavailable presents server features.reason as customer copy",
        "featureUnavailableMessageKey" in access_states
        and "featureUnavailableTitleKey" in access_states
        and "featureUnavailableReasonKind" in feature_copy
        and "module_disabled" in feature_copy
        and "feature.unavailable.moduleDisabled" in feature_copy,
    )
    for path, feature in {
        "app/(tabs)/leave.tsx": 'feature="leave"',
        "app/onboarding.tsx": 'feature="onboarding"',
        "app/documents.tsx": 'feature="documents"',
        "app/leave/request.tsx": 'feature="leave"',
        "app/(tabs)/payslips.tsx": 'feature="payslips"',
    }.items():
        source = read(path)
        check(
            f"{path} passes feature into FeatureUnavailableState",
            "FeatureUnavailableState" in source and feature in source,
        )
    check(
        "Schedule FeatureUnavailable covers both schedule authorities",
        'feature={["shifts", "attendance"]}' in read("app/(tabs)/schedule.tsx")
        or "feature={['shifts', 'attendance']}" in read("app/(tabs)/schedule.tsx"),
    )
    required_i18n = {
        "access.offline.title",
        "access.app_disabled.title",
        "access.company_disabled.title",
        "access.company_archived.title",
        "access.company_app_disabled.title",
        "access.employee_inactive.title",
        "access.session_expired.title",
        "feature.unavailable.title",
        "feature.unavailable.moduleDisabled",
        "feature.unavailable.noAccess",
        "feature.unavailable.temporarilyUnavailable",
        "feature.unavailable.temporarilyUnavailableTitle",
        "notFound.title",
        "status.unknown",
    }
    en = json.loads(read("src/i18n/en.json"))
    ar = json.loads(read("src/i18n/ar.json"))
    check("English account/capability copy complete", required_i18n <= set(en))
    check("Arabic account/capability copy complete", required_i18n <= set(ar))
    check("English/Arabic keysets match", set(en) == set(ar))
    check(
        "payslip authority copy is source-neutral and free of payroll jargon",
        # Still must not name where the payroll came from, and must now also read
        # as something an employee would say rather than "authoritative released
        # payroll record".
        "external" not in str(en.get("payslips.officialPdfNote") or "").lower()
        and "external" not in str(en.get("payslips.noOfficialPdf") or "").lower()
        and str(en.get("payslips.officialPdfNote") or "") == "Official payslip issued by your company.",
    )
    # Nothing an employee reads may leak internal programme, build or authority
    # vocabulary. Applies to both locales.
    internal_terms = (
        "canary",
        "wave 2a",
        "authoritative",
        "payroll-effective",
        "released payroll",
        "internal build",
        "not enforced",
        "paci",
    )
    leaks = sorted(
        f"{locale_name}:{key}"
        for locale_name, table in (("en", en), ("ar", ar))
        for key, value in table.items()
        for term in internal_terms
        if term in str(value).lower()
    )
    check(f"no internal terminology in employee-facing copy ({leaks})", not leaks)
    prefixes = {
        key
        for key in en
        if any(other.startswith(f"{key}.") for other in en if other != key)
    }
    check("translation keys have no scalar/object collisions", not prefixes)

    print("employee mobile capability foundation: GREEN")


if __name__ == "__main__":
    main()
