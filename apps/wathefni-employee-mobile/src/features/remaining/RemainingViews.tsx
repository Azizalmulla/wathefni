import { useEffect, useMemo, useState } from 'react'
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import Ionicons from '@expo/vector-icons/Ionicons'
import DateTimePicker from '@react-native-community/datetimepicker'

import { useI18n, type AppLocale, readingEdgeAlign, trailingEdgeAlign } from '@/i18n'
import { listAutoLockTimeoutOptions, type AutoLockTimeoutMs } from '@/auth/autoLockPolicy'
import {
  EditorialHeading,
  FadeIn,
  IconBadge,
  PastelCard,
  PremiumButton,
  Wordmark,
} from '@/components/premium'
import { keyboardSafeBehavior } from '@/components/keyboardSafe'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, PageBackButton, QuietEmpty, SectionHeader, ShowMoreButton, usePagedList } from '@/components/lists'
import {
  InboxCalmNote,
  InboxLedger,
  InboxLedgerRow,
  InboxLedgerSection,
} from '@/components/inboxLedger'
import {
  balanceForLeaveType,
  balancesAreInformational,
  type LeaveBalanceFact,
} from '@/features/leave/leaveBalance'
import {
  canCancelLeaveRequest,
  leavePresentationStatus,
  partitionLeaveRequests,
} from '@/features/leave/leaveRequests'
import { LeaveStatusMark } from '@/features/leave/leaveStatusPills'
import {
  formatDate,
  formatDateRange,
  formatDateTime,
  formatNumber,
  formatRelativeTime,
  statusLabel,
} from '@/lib/format'
import { ambient, colors, font, layout, radius, spacing, typeScaling } from '@/theme'
import type {
  LeaveDurationResponse,
  LeaveRequestRow,
  LeaveResponse,
  NotificationItem,
  NotificationsResponse,
} from '@/api/types'

type BaseProps = {
  onBack?: () => void
}

/**
 * Shared page chrome.
 *
 * The magenta uppercase eyebrow and the decorative ribbon above every title were
 * three lines of packaging before the first useful pixel on Inbox, Leave, Settings
 * and Help. The bloom is now reserved for moments that are actually special.
 */
function Page({
  title,
  subtitle,
  children,
  onBack,
  refreshing,
  onRefresh,
  keyboardInsets = false,
}: BaseProps & {
  title: string
  subtitle?: string
  children: React.ReactNode
  refreshing?: boolean
  onRefresh?: () => void
  keyboardInsets?: boolean
}) {
  const { isRTL, t } = useI18n()
  const align = readingEdgeAlign(isRTL)
  return (
    <PageScreen>
      <PageScrollView refreshing={refreshing} onRefresh={onRefresh} keyboardInsets={keyboardInsets}>
        <View style={styles.nav}>
          {onBack ? <PageBackButton onPress={onBack} accessibilityLabel={t('common.back')} /> : null}
          <Wordmark compact align={onBack ? 'center' : undefined} />
          {onBack ? <View style={styles.navSpacer} /> : null}
        </View>
        <FadeIn style={styles.hero}>
          <EditorialHeading>{title}</EditorialHeading>
          {subtitle ? <Text style={[styles.subtitle, align]}>{subtitle}</Text> : null}
        </FadeIn>
        {children}
      </PageScrollView>
    </PageScreen>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <SectionHeader title={String(children)} />
}

function EmptyCard({ icon, message }: { icon: keyof typeof Ionicons.glyphMap; message: string }) {
  return <QuietEmpty icon={icon} message={message} />
}

/**
 * Flows whose messages are a record that the platform did something, not work the
 * employee has to think about: activation confirmations, device and sign-in
 * notices. Reactivating a phone twice used to push three weeks of real HR
 * messages off the first screen.
 *
 * This is presentation only — it partitions messages the server already labelled
 * and invents no message authority. An unrecognised flow is treated as HR/workflow
 * so a new backend flow can never be quietly demoted, and unread messages are
 * never demoted regardless of flow.
 */
const SYSTEM_ACTIVITY_FLOWS = new Set([
  'activation',
  'activation_reminder',
  // Backend activation-code delivery uses this flow name.
  'app_activation',
  'auth',
  'device',
  'device_security',
  'security',
  'session',
  'system',
  'test',
])

function isSystemActivity(item: NotificationItem): boolean {
  return SYSTEM_ACTIVITY_FLOWS.has(String(item.flow || '').trim().toLowerCase())
}

const INBOX_PAGE = 15

export function NotificationsView({
  data,
  onMarkRead,
  refreshing,
  onRefresh,
  onBack,
}: {
  data: NotificationsResponse
  onMarkRead: (item: NotificationItem) => void
  refreshing?: boolean
  onRefresh?: () => void
  onBack?: () => void
}) {
  const { t, locale, isRTL } = useI18n()
  const [systemOpen, setSystemOpen] = useState(false)
  const unread = data.notifications.filter((item) => !item.read)
  const read = data.notifications.filter((item) => item.read)
  const earlier = read.filter((item) => !isSystemActivity(item))
  const systemActivity = read.filter(isSystemActivity)
  const earlierPage = usePagedList(earlier, INBOX_PAGE)
  const systemPage = usePagedList(systemActivity, INBOX_PAGE)

  return (
    <Page
      title={t('notifications.title')}
      subtitle={
        data.unread
          ? t('remaining.inboxUnread', { count: formatNumber(data.unread, locale, 0) })
          : t('remaining.inboxClear')
      }
      refreshing={refreshing}
      onRefresh={onRefresh}
      onBack={onBack}
    >
      {data.notifications.length ? (
        <>
          {unread.length ? (
            <InboxLedgerSection>
              <SectionHeader title={t('notifications.unread')} count={unread.length} />
              <InboxLedger>
                {unread.map((item) => (
                  <NotificationInboxRow key={item.id} item={item} onPress={() => onMarkRead(item)} />
                ))}
              </InboxLedger>
            </InboxLedgerSection>
          ) : null}

          {earlier.length ? (
            <InboxLedgerSection>
              <SectionHeader title={t('notifications.updates')} count={earlier.length} />
              <InboxLedger>
                {earlierPage.visible.map((item) => (
                  <NotificationInboxRow key={item.id} item={item} onPress={() => onMarkRead(item)} />
                ))}
              </InboxLedger>
              {earlierPage.hidden ? (
                <ShowMoreButton
                  label={t('common.showMore', { count: formatNumber(earlierPage.hidden, locale, 0) })}
                  onPress={earlierPage.showMore}
                />
              ) : null}
            </InboxLedgerSection>
          ) : null}

          {systemActivity.length ? (
            <InboxLedgerSection>
              <SectionHeader
                title={t('notifications.systemActivity')}
                count={systemActivity.length}
                collapsible
                expanded={systemOpen}
                onToggle={() => setSystemOpen((open) => !open)}
              />
              {systemOpen ? (
                <>
                  <InboxLedger>
                    {systemPage.visible.map((item) => (
                      <NotificationInboxRow
                        key={item.id}
                        item={item}
                        quiet
                        onPress={() => onMarkRead(item)}
                      />
                    ))}
                  </InboxLedger>
                  {systemPage.hidden ? (
                    <ShowMoreButton
                      label={t('common.showMore', { count: formatNumber(systemPage.hidden, locale, 0) })}
                      onPress={systemPage.showMore}
                    />
                  ) : null}
                </>
              ) : null}
            </InboxLedgerSection>
          ) : null}
        </>
      ) : (
        <InboxCalmNote message={t('notifications.empty')} />
      )}
    </Page>
  )
}

function NotificationInboxRow({
  item,
  onPress,
  quiet = false,
}: {
  item: NotificationItem
  onPress: () => void
  quiet?: boolean
}) {
  const { t, locale } = useI18n()
  const unread = !item.read
  const state = unread ? t('notifications.unreadItem') : t('notifications.read')
  const when = formatRelativeTime(item.created_at, locale, t)
  const exact = formatDateTime(item.created_at, locale)
  return (
    <InboxLedgerRow
      title={item.title}
      body={item.body}
      when={when}
      emphasized={unread}
      quiet={quiet}
      accentColor={unread ? ambient.onboarding.fill : undefined}
      onPress={onPress}
      accessibilityLabel={`${item.title}. ${state}. ${when}${exact ? ` (${exact})` : ''}. ${item.body || ''}`}
      accessibilityHint={item.deep_link?.path ? t('notifications.openHint') : undefined}
    />
  )
}

export function LeaveView({
  data,
  canRequest,
  canCancel,
  onRequest,
  onCancel,
  onViewAllHistory,
  cancelingId,
  refreshing,
  onRefresh,
}: {
  data: LeaveResponse
  canRequest: boolean
  canCancel: boolean
  onRequest: () => void
  onCancel: (leaveId: string) => void
  onViewAllHistory: () => void
  cancelingId?: string | null
  refreshing?: boolean
  onRefresh?: () => void
}) {
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const balanceFacts = useMemo(
    () =>
      (data.balances ?? [])
        .map((balance) => balanceForLeaveType(data, balance.leave_type))
        .filter((fact): fact is LeaveBalanceFact => fact !== null),
    [data],
  )
  const showBalances = Boolean(data.balances_enabled) && balanceFacts.length > 0
  const partitioned = useMemo(() => partitionLeaveRequests(data.requests), [data.requests])
  const currentPage = usePagedList(partitioned.current, LEAVE_PAGE)
  const historyPage = usePagedList(partitioned.history, LEAVE_PAGE)
  const totalRequests = data.requests?.length ?? 0
  const subtitle = showBalances ? t('leave.subtitleWithBalances') : t('leave.subtitleRequestsOnly')

  return (
    <Page title={t('leave.title')} subtitle={subtitle} refreshing={refreshing} onRefresh={onRefresh}>
      {/* Balances only when the server enables them and supplies a usable number.
          Never invent entitlement/accrual fields the payload did not send. */}
      {showBalances ? (
        <View style={styles.list}>
          <SectionHeader title={t('leave.balance')} />
          <PastelCard tone="olive" style={[styles.balanceCard, styles.balanceAmbient]}>
            {balanceFacts.map((balance, index) => (
              <View
                key={balance.leaveType}
                style={[styles.balanceRow, index > 0 && styles.balanceDivider]}
                accessibilityLabel={`${leaveTypeLabel(balance.leaveType, t)}: ${formatNumber(
                  balance.days,
                  locale,
                )} ${t('remaining.daysAvailable')}`}
              >
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.balanceType, styles.flex, align]}>
                  {leaveTypeLabel(balance.leaveType, t)}
                </Text>
                <Text maxFontSizeMultiplier={typeScaling.heading} style={styles.balanceValue}>
                  {formatNumber(balance.days, locale)}
                </Text>
                <Text style={styles.balanceUnit}>{t('remaining.daysAvailable')}</Text>
              </View>
            ))}
          </PastelCard>
          {balancesAreInformational(data) ? (
            <Text style={[styles.footnote, align]}>{t('leave.notEnforced')}</Text>
          ) : null}
        </View>
      ) : null}

      {canRequest ? <PremiumButton label={t('leave.request')} onPress={onRequest} showDirection /> : null}

      {partitioned.current.length ? (
        <View style={styles.list}>
          <SectionHeader title={t('leave.currentRequests')} count={partitioned.current.length} />
          {currentPage.visible.map((request) => (
            <LeaveRequestRowItem
              key={request.leave_id}
              request={request}
              canCancel={canCancel}
              canceling={cancelingId === request.leave_id}
              onCancel={onCancel}
            />
          ))}
          {currentPage.hidden ? (
            <ShowMoreButton
              label={t('common.showMore', { count: formatNumber(currentPage.hidden, locale, 0) })}
              onPress={currentPage.showMore}
            />
          ) : null}
        </View>
      ) : null}

      <View style={styles.list}>
        {partitioned.history.length ? (
          <>
            <SectionHeader title={t('leave.history')} count={partitioned.history.length} />
            {historyPage.visible.map((request) => (
              <LeaveRequestRowItem
                key={request.leave_id}
                request={request}
                canCancel={false}
                canceling={false}
                onCancel={onCancel}
              />
            ))}
            {historyPage.hidden ? (
              <ShowMoreButton
                label={t('common.showMore', { count: formatNumber(historyPage.hidden, locale, 0) })}
                onPress={historyPage.showMore}
              />
            ) : null}
          </>
        ) : (
          <SectionHeader title={t('leave.history')} />
        )}
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t('leave.historyAll.view')}
          accessibilityHint={t('leave.historyAll.viewHint')}
          onPress={onViewAllHistory}
          style={({ pressed }) => [styles.historyLink, pressed && styles.pressed]}
        >
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.historyLinkText, align]}>
            {t('leave.historyAll.view')}
          </Text>
          <Ionicons name={isRTL ? 'chevron-back' : 'chevron-forward'} size={16} color={colors.accent} />
        </Pressable>
      </View>

      {!totalRequests ? <CalmNote message={t('leave.empty')} /> : null}

      {totalRequests >= LEAVE_API_WINDOW ? (
        <Text style={[styles.footnote, align]}>{t('leave.listWindowNote')}</Text>
      ) : null}
    </Page>
  )
}

/** Page size inside the fetched `/app/leave` window (~50). Not a deeper history API. */
const LEAVE_PAGE = 8
/** Server `_employee_leave_request_rows` default LIMIT — honest ceiling for this surface. */
const LEAVE_API_WINDOW = 50

/**
 * Type, dates, status — the three things an employee scans for. A one-day request
 * shows one date; it used to print the same date twice.
 */
function LeaveRequestRowItem({
  request,
  canCancel,
  canceling,
  onCancel,
}: {
  request: LeaveRequestRow
  canCancel: boolean
  canceling: boolean
  onCancel: (leaveId: string) => void
}) {
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  // Action eligibility comes only from the canonical backend read projection.
  const cancellable = canCancel && canCancelLeaveRequest(request)
  const dates = formatDateRange(request.start_date, request.end_date, locale)
  const type = request.leave_type ? leaveTypeLabel(request.leave_type, t) : null
  const presentationStatus = leavePresentationStatus(request)
  const status = statusLabel(presentationStatus, t)
  return (
    <ListRow
      title={type || dates}
      subtitle={type ? dates : null}
      meta={request.reason}
      trailing={<LeaveStatusMark status={presentationStatus} label={status} />}
      accessibilityLabel={`${type ? `${type}. ` : ''}${dates}. ${status}`}
    >
      {cancellable ? (
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: canceling }}
          disabled={canceling}
          onPress={() => onCancel(request.leave_id)}
          style={[styles.textAction, canceling && styles.disabled]}
        >
          <Text style={[styles.dangerAction, align]}>
            {canceling ? t('common.loading') : t('leave.cancel')}
          </Text>
        </Pressable>
      ) : null}
    </ListRow>
  )
}

export function LeaveRequestView({
  leaveTypes,
  busy,
  error,
  balances,
  onRangeChange,
  duration,
  onSubmit,
  onBack,
}: {
  leaveTypes: string[]
  busy: boolean
  error: string | null
  /** `/app/leave` balances, for answering "how much do I have?" before submitting. */
  balances?: Pick<LeaveResponse, 'balances_enabled' | 'balances' | 'balances_enforced' | 'balances_binding'> | null
  /** Reports the current selection so the screen above can price it server-side. */
  onRangeChange?: (value: { startDate: string; endDate: string; leaveType: string }) => void
  /** Server's answer for the current selection. Undefined while it has none. */
  duration?: LeaveDurationResponse | null
  onSubmit: (value: { startDate: string; endDate: string; leaveType: string; reason: string }) => void
  onBack: () => void
}) {
  const { t, locale, isRTL } = useI18n()
  const today = startOfLocalDay(new Date())
  const [startDate, setStartDate] = useState(today)
  const [endDate, setEndDate] = useState(today)
  const [leaveType, setLeaveType] = useState(leaveTypes[0] || '')
  const [reason, setReason] = useState('')
  const [picking, setPicking] = useState<'start' | 'end' | null>(null)
  const startIso = toIsoDate(startDate)
  const endIso = toIsoDate(endDate)
  const rangeValid = endDate.getTime() >= startDate.getTime()
  const valid = Boolean(leaveType) && rangeValid
  const align = readingEdgeAlign(isRTL)
  const balance = balanceForLeaveType(balances, leaveType)

  // The screen above owns the request; this view only reports what is selected.
  useEffect(() => {
    if (!rangeValid || !leaveType) return
    onRangeChange?.({ startDate: startIso, endDate: endIso, leaveType })
  }, [startIso, endIso, leaveType, rangeValid, onRangeChange])

  const chargeable =
    duration?.available && typeof duration.chargeable_days === 'number' ? duration.chargeable_days : null

  const applyPicked = (next: Date) => {
    const day = startOfLocalDay(next)
    if (picking === 'start') {
      setStartDate(day)
      if (day.getTime() > endDate.getTime()) setEndDate(day)
    } else if (picking === 'end') {
      setEndDate(day.getTime() < startDate.getTime() ? startDate : day)
    }
    if (Platform.OS !== 'ios') setPicking(null)
  }

  return (
    <KeyboardAvoidingView behavior={keyboardSafeBehavior()} style={styles.safe}>
      <Page
        onBack={onBack}
        title={t('leave.request')}
        subtitle={t('remaining.leaveRequestSubtitle')}
        keyboardInsets
      >
        <View style={styles.formSection}>
          <Text style={[styles.fieldLabel, align]}>{t('leave.type')}</Text>
          <View style={styles.segment}>
            {leaveTypes.map((type) => (
              <Pressable
                key={type}
                accessibilityRole="button"
                accessibilityState={{ selected: leaveType === type }}
                onPress={() => setLeaveType(type)}
                style={[styles.segmentItem, leaveType === type && styles.segmentActive]}
              >
                <Text style={[styles.segmentText, leaveType === type && styles.segmentTextActive]}>{leaveTypeLabel(type, t)}</Text>
              </Pressable>
            ))}
          </View>
          <DatePickerField
            label={t('leave.startDate')}
            value={startDate}
            locale={locale}
            isRTL={isRTL}
            open={picking === 'start'}
            onOpen={() => setPicking('start')}
            onClose={() => setPicking(null)}
            onChange={applyPicked}
          />
          <DatePickerField
            label={t('leave.endDate')}
            value={endDate}
            locale={locale}
            isRTL={isRTL}
            open={picking === 'end'}
            minimumDate={startDate}
            onOpen={() => setPicking('end')}
            onClose={() => setPicking(null)}
            onChange={applyPicked}
          />
          {!rangeValid ? <Text style={[styles.errorText, align]}>{t('leave.invalidRange')}</Text> : null}

          {/*
            What this request costs, and what the employee has — the two things
            they would otherwise open another screen to check.

            Both are the server's numbers. The day count is what the company's
            rest days and public holidays make it, which is why it is fetched
            rather than counted here; if the server has no answer the line is
            absent rather than guessed. The balance is observe-only, so it is
            stated as information and never as a limit.
          */}
          {chargeable !== null || balance ? (
            <View style={styles.requestSummary}>
              {chargeable !== null ? (
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.summaryLead, align]}>
                  {chargeable === 0
                    ? t('leave.noWorkingDays')
                    : t('leave.requestingDays', {
                        count: formatNumber(chargeable, locale),
                      })}
                </Text>
              ) : null}
              {balance ? (
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.summaryBalance, align]}>
                  {t('leave.youHaveDays', {
                    count: formatNumber(balance.days, locale),
                    type: leaveTypeLabel(balance.leaveType, t),
                  })}
                </Text>
              ) : null}
              {balance?.canTakeFrom ? (
                <Text style={[styles.footnote, align]}>
                  {t('leave.canTakeFrom', { date: formatDate(balance.canTakeFrom, locale) })}
                </Text>
              ) : null}
              {balance && balancesAreInformational(balances) ? (
                <Text style={[styles.footnote, align]}>{t('leave.notEnforced')}</Text>
              ) : null}
            </View>
          ) : null}

          <View style={styles.field}>
            <Text style={[styles.fieldLabel, align]}>{t('leave.reason')}</Text>
            <TextInput
              accessibilityLabel={t('leave.reason')}
              value={reason}
              onChangeText={setReason}
              multiline
              numberOfLines={3}
              placeholder={t('remaining.leaveReasonPlaceholder')}
              placeholderTextColor={colors.subtle}
              style={[styles.input, styles.multiline, align]}
            />
          </View>
          {error ? <Text style={[styles.errorText, align]}>{error}</Text> : null}
          <PremiumButton
            label={t('common.submit')}
            busy={busy}
            disabled={!valid || busy}
            onPress={() => {
              if (!valid || busy) return
              onSubmit({ startDate: startIso, endDate: endIso, leaveType, reason })
            }}
            showDirection
          />
        </View>
        <View style={styles.infoPanel}>
          <Ionicons name="information-circle-outline" size={20} color={colors.subtle} />
          <Text style={[styles.supporting, styles.flex, align]}>{t('remaining.leaveAuthorityNote')}</Text>
        </View>
      </Page>
    </KeyboardAvoidingView>
  )
}

function DatePickerField({
  label,
  value,
  locale,
  isRTL,
  open,
  minimumDate,
  onOpen,
  onClose,
  onChange,
}: {
  label: string
  value: Date
  locale: string
  isRTL: boolean
  open: boolean
  minimumDate?: Date
  onOpen: () => void
  onClose: () => void
  onChange: (next: Date) => void
}) {
  return (
    <View style={styles.field}>
      <Text style={[styles.fieldLabel, readingEdgeAlign(isRTL)]}>{label}</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={label}
        onPress={onOpen}
        style={styles.inputWithIcon}
      >
        <Ionicons name="calendar-outline" size={19} color={colors.subtle} />
        <Text style={[styles.dateInput, { ...readingEdgeAlign(isRTL), color: colors.ink, paddingVertical: 12 }]}>
          {formatDate(toIsoDate(value), locale)}
        </Text>
      </Pressable>
      {open ? (
        <View style={styles.pickerWrap}>
          <DateTimePicker
            value={value}
            mode="date"
            display={Platform.OS === 'ios' ? 'spinner' : 'default'}
            minimumDate={minimumDate}
            onChange={(_, selected) => {
              if (selected) onChange(selected)
              if (Platform.OS !== 'ios') onClose()
            }}
          />
          {Platform.OS === 'ios' ? (
            <Pressable accessibilityRole="button" onPress={onClose} style={styles.pickerDone}>
              <Text style={styles.pickerDoneText}>{tDone(locale)}</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}
    </View>
  )
}

function tDone(locale: string) {
  return locale === 'ar' ? 'تم' : 'Done'
}

function startOfLocalDay(value: Date): Date {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate())
}

function toIsoDate(value: Date): string {
  const y = value.getFullYear()
  const m = String(value.getMonth() + 1).padStart(2, '0')
  const d = String(value.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function DetailRow({ icon, label, value }: { icon: keyof typeof Ionicons.glyphMap; label: string; value: string }) {
  const { isRTL } = useI18n()
  return (
    <View style={styles.detailRow}>
      <View style={styles.detailIcon}><Ionicons name={icon} size={18} color={colors.ink} /></View>
      <Text style={[styles.detailLabel, readingEdgeAlign(isRTL)]}>{label}</Text>
      <Text style={[styles.detailValue, trailingEdgeAlign(isRTL)]}>{value}</Text>
    </View>
  )
}

function MenuRow({
  icon,
  label,
  onPress,
  danger = false,
  disabled = false,
}: {
  icon: keyof typeof Ionicons.glyphMap
  label: string
  onPress: () => void
  danger?: boolean
  disabled?: boolean
}) {
  const { isRTL } = useI18n()
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [styles.menuRow, pressed && styles.pressed, disabled && styles.disabled]}
    >
      <View style={[styles.menuIcon, danger && styles.menuIconDanger]}><Ionicons name={icon} size={19} color={danger ? colors.danger : colors.ink} /></View>
      <Text style={[styles.menuLabel, styles.flex, danger && { color: colors.danger }, readingEdgeAlign(isRTL)]}>{label}</Text>
      <Ionicons name={isRTL ? 'chevron-back' : 'chevron-forward'} size={18} color={colors.subtle} />
    </Pressable>
  )
}

export function SettingsView({
  locale,
  pushOn,
  pushBusy,
  canManagePush,
  canChangePin,
  canManageBiometric,
  biometricOn,
  biometricBusy,
  biometricLabel,
  canManageAutoLock,
  autoLockTimeoutMs,
  autoLockBusy,
  deviceSecurity,
  deviceSecurityLoading,
  version,
  onLocale,
  onTogglePush,
  onToggleBiometric,
  onAutoLockTimeout,
  onPrivacySupport,
  onChangePin,
  onSignOutDevice,
  onDelete,
  deleteBusy,
  onBack,
  onRetryDeviceSecurity,
}: {
  locale: AppLocale
  pushOn: boolean
  pushBusy: boolean
  canManagePush: boolean
  canChangePin?: boolean
  canManageBiometric?: boolean
  biometricOn?: boolean
  biometricBusy?: boolean
  biometricLabel?: string
  canManageAutoLock?: boolean
  autoLockTimeoutMs?: AutoLockTimeoutMs
  autoLockBusy?: boolean
  deviceSecurity?: {
    platform: string
    activatedAt: string | null
    lastActiveAt: string | null
    status: string
  } | null
  deviceSecurityLoading?: boolean
  version: string
  onLocale: (locale: AppLocale) => void
  onTogglePush: (value: boolean) => void
  onToggleBiometric?: (value: boolean) => void
  onAutoLockTimeout?: (value: AutoLockTimeoutMs) => void
  onPrivacySupport: () => void
  onChangePin?: () => void
  onSignOutDevice?: () => void
  onDelete?: () => void
  deleteBusy?: boolean
  onBack: () => void
  onRetryDeviceSecurity?: () => void
}) {
  const { t, isRTL, locale: uiLocale } = useI18n()
  const autoLockOptions = listAutoLockTimeoutOptions()
  const align = readingEdgeAlign(isRTL)
  const formatDeviceDate = (iso: string | null | undefined) => {
    if (!iso) return '—'
    try {
      return new Date(iso).toLocaleString(uiLocale === 'ar' ? 'ar-KW' : 'en-GB', {
        dateStyle: 'medium',
        timeStyle: 'short',
      })
    } catch {
      return iso
    }
  }
  const platformLabel =
    deviceSecurity?.platform === 'ios'
      ? t('deviceSecurity.platformIos')
      : deviceSecurity?.platform === 'android'
        ? t('deviceSecurity.platformAndroid')
        : t('deviceSecurity.platformUnknown')
  return (
    <Page onBack={onBack} title={t('settings.title')} subtitle={t('remaining.settingsSubtitle')}>
      <View style={styles.section}>
        <SectionLabel>{t('settings.language')}</SectionLabel>
        <View style={styles.segment}>
          {(['en', 'ar'] as const).map((code) => (
            <Pressable
              key={code}
              accessibilityRole="button"
              accessibilityState={{ selected: locale === code }}
              onPress={() => onLocale(code)}
              style={[styles.segmentItem, locale === code && styles.segmentActive]}
            >
              <Text style={[styles.segmentText, locale === code && styles.segmentTextActive]}>
                {t(code === 'en' ? 'settings.english' : 'settings.arabic')}
              </Text>
            </Pressable>
          ))}
        </View>
      </View>
      {canManagePush ? (
        <View style={styles.settingsPanel}>
          <View style={styles.settingsRow}>
            <IconBadge name="notifications-outline" />
            <View style={styles.flex}>
              <Text style={[styles.itemTitle, readingEdgeAlign(isRTL)]}>{t('settings.push')}</Text>
              <Text style={[styles.supporting, readingEdgeAlign(isRTL)]}>{t('remaining.pushSubtitle')}</Text>
            </View>
            <Switch
              accessibilityLabel={t('settings.push')}
              accessibilityState={{ disabled: pushBusy, checked: pushOn }}
              value={pushOn}
              onValueChange={onTogglePush}
              disabled={pushBusy}
            />
          </View>
        </View>
      ) : null}
      {canManageBiometric && onToggleBiometric ? (
        <View style={styles.settingsPanel}>
          <View style={styles.settingsRow}>
            <IconBadge name="scan-outline" />
            <View style={styles.flex}>
              <Text style={[styles.itemTitle, readingEdgeAlign(isRTL)]}>
                {biometricLabel || t('biometric.settings')}
              </Text>
              <Text style={[styles.supporting, readingEdgeAlign(isRTL)]}>
                {t('biometric.settingsSubtitle')}
              </Text>
            </View>
            <Switch
              accessibilityLabel={biometricLabel || t('biometric.settings')}
              accessibilityState={{ disabled: biometricBusy, checked: Boolean(biometricOn) }}
              value={Boolean(biometricOn)}
              onValueChange={onToggleBiometric}
              disabled={Boolean(biometricBusy)}
            />
          </View>
        </View>
      ) : null}
      {canManageAutoLock && onAutoLockTimeout ? (
        <View style={styles.section}>
          <SectionLabel>{t('autoLock.settings')}</SectionLabel>
          <Text style={[styles.supporting, { ...readingEdgeAlign(isRTL), marginBottom: spacing.sm }]}>
            {t('autoLock.settingsSubtitle')}
          </Text>
          <View style={styles.autoLockList}>
            {autoLockOptions.map((opt) => {
              const selected = autoLockTimeoutMs === opt.value
              return (
                <Pressable
                  key={String(opt.value)}
                  accessibilityRole="button"
                  accessibilityState={{ selected, disabled: Boolean(autoLockBusy) }}
                  disabled={Boolean(autoLockBusy)}
                  onPress={() => onAutoLockTimeout(opt.value)}
                  style={[styles.autoLockRow, selected && styles.autoLockRowActive]}
                >
                  <Text style={[styles.autoLockText, selected && styles.autoLockTextActive]}>
                    {t(opt.labelKey)}
                  </Text>
                  {selected ? <Ionicons name="checkmark" size={18} color={colors.ink} /> : null}
                </Pressable>
              )
            })}
          </View>
        </View>
      ) : null}
      <View style={styles.section}>
        <SectionLabel>{t('deviceSecurity.title')}</SectionLabel>
        <View style={styles.settingsPanel}>
          {deviceSecurityLoading && !deviceSecurity ? (
            <Text style={[styles.supporting, align]}>{t('common.loading')}</Text>
          ) : deviceSecurity ? (
            <>
              <Text style={[styles.itemTitle, align, { marginBottom: spacing.sm }]}>{t('deviceSecurity.currentDevice')}</Text>
              <DetailRow icon="hardware-chip-outline" label={t('deviceSecurity.platform')} value={platformLabel} />
              <DetailRow icon="calendar-outline" label={t('deviceSecurity.activated')} value={formatDeviceDate(deviceSecurity.activatedAt)} />
              <DetailRow icon="time-outline" label={t('deviceSecurity.lastActive')} value={formatDeviceDate(deviceSecurity.lastActiveAt)} />
              {/* A hardcoded "Status: Active" row was removed: this panel only ever
                  describes the device the employee is holding, so the value could
                  never say anything else. */}
            </>
          ) : (
            <View style={{ gap: spacing.sm }}>
              <Text style={[styles.supporting, align]}>{t('deviceSecurity.unavailable')}</Text>
              {onRetryDeviceSecurity ? (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={t('common.retry')}
                  onPress={onRetryDeviceSecurity}
                  style={styles.retryChip}
                  hitSlop={8}
                >
                  <Text style={styles.retryText}>{t('common.retry')}</Text>
                </Pressable>
              ) : null}
            </View>
          )}
        </View>
        {onSignOutDevice ? (
          <MenuRow icon="log-out-outline" label={t('deviceSecurity.signOutDevice')} onPress={onSignOutDevice} danger />
        ) : null}
      </View>
      <View style={styles.section}>
        <SectionLabel>{t('settings.security')}</SectionLabel>
        {canChangePin && onChangePin ? (
          <MenuRow icon="keypad-outline" label={t('pin.change')} onPress={onChangePin} />
        ) : null}
        <MenuRow icon="shield-checkmark-outline" label={t('remaining.privacySupportTitle')} onPress={onPrivacySupport} />
        {onDelete ? (
          <MenuRow
            icon="trash-outline"
            label={t('settings.deleteAccount')}
            onPress={onDelete}
            disabled={deleteBusy}
            danger
          />
        ) : null}
      </View>
      <Text style={styles.version}>{t('settings.version')} {version}</Text>
    </Page>
  )
}

export function PrivacySupportView({
  onPrivacy,
  onSupport,
  onBack,
}: {
  onPrivacy: () => void
  onSupport: () => void
  onBack: () => void
}) {
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  return (
    <Page onBack={onBack} title={t('remaining.privacySupportTitle')} subtitle={t('remaining.privacySupportSubtitle')}>
      <View style={styles.helpPanel}>
        <IconBadge name="shield-checkmark-outline" />
        <Text style={[styles.itemTitle, align]}>{t('settings.privacy')}</Text>
        <Text style={[styles.supporting, align]}>{t('remaining.privacyCopy')}</Text>
        <PremiumButton label={t('remaining.readPrivacy')} onPress={onPrivacy} showDirection />
      </View>
      <View style={styles.helpPanel}>
        <IconBadge name="chatbubble-ellipses-outline" />
        <Text style={[styles.itemTitle, align]}>{t('remaining.supportTitle')}</Text>
        <Text style={[styles.supporting, align]}>{t('remaining.supportCopy')}</Text>
        <PremiumButton label={t('remaining.contactSupport')} onPress={onSupport} showDirection />
      </View>
    </Page>
  )
}

export function NotFoundView({ onHome }: { onHome: () => void }) {
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  return (
    <SafeAreaView style={styles.stateSafe}>
      <View style={styles.stateWrap}>
        <Wordmark compact />
        <View style={styles.stateCard}>
          <View style={styles.stateIcon}><Ionicons name="compass-outline" size={34} color={colors.ink} /></View>
          <EditorialHeading size="medium">{t('notFound.title')}</EditorialHeading>
          <Text style={[styles.stateCopy, align]}>{t('notFound.message')}</Text>
          <PremiumButton label={t('feature.backHome')} onPress={onHome} showDirection />
        </View>
      </View>
    </SafeAreaView>
  )
}

function leaveTypeLabel(type: string, t: (key: string) => string): string {
  if (type === 'annual') return t('leave.typeAnnual')
  if (type === 'sick') return t('leave.typeSick')
  return t('leave.typeOther')
}

/** Cream-ground empty — no bordered white panel. */
function CalmNote({ message }: { message: string }) {
  const { isRTL } = useI18n()
  return (
    <Text
      maxFontSizeMultiplier={typeScaling.body}
      style={[styles.calmNote, readingEdgeAlign(isRTL)]}
      accessibilityRole="summary"
    >
      {message}
    </Text>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  screen: { flex: 1, backgroundColor: colors.bg },

  nav: { minHeight: 42, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  navSpacer: { width: 44 },
  backButton: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  hero: { gap: spacing.xs },
  subtitle: { color: colors.subtle, fontSize: font.small, lineHeight: 20, maxWidth: 360 },
  flex: { flex: 1 },
  section: { gap: spacing.md },
  /** Compact list rhythm: rows sit closer together than top-level sections. */
  list: { gap: spacing.sm },
  pressed: { opacity: 0.82 },
  disabled: { opacity: 0.5 },
  itemTitle: { color: colors.ink, fontSize: font.h3, fontWeight: '700', lineHeight: 22 },
  supporting: { color: colors.subtle, fontSize: font.small, lineHeight: 20 },
  meta: { color: colors.subtle, fontSize: font.tiny, marginTop: spacing.xs },
  metaStrong: { color: colors.subtle, fontSize: font.small, fontWeight: '700' },
  /** The two facts that decide a request, stated together above the reason box. */
  requestSummary: {
    gap: spacing.xs,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  summaryLead: { color: colors.ink, fontSize: font.body, fontWeight: '800', lineHeight: 22 },
  summaryBalance: { color: colors.subtle, fontSize: font.small, lineHeight: 19 },
  balanceCard: { paddingVertical: spacing.sm },
  balanceAmbient: { backgroundColor: ambient.leave.fill },
  balanceRow: { flexDirection: 'row', alignItems: 'baseline', gap: spacing.sm, paddingVertical: spacing.sm },
  balanceDivider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  balanceType: { color: colors.ink, fontSize: font.small, fontWeight: '700' },
  balanceValue: { color: colors.ink, fontSize: font.h2, fontWeight: '800', letterSpacing: -0.4 },
  balanceUnit: { color: colors.subtle, fontSize: font.tiny },
  footnote: { color: colors.subtle, fontSize: font.tiny, lineHeight: 18 },
  calmNote: {
    color: colors.subtle,
    fontSize: font.body,
    lineHeight: 22,
    fontWeight: '600',
    paddingVertical: spacing.sm,
  },
  historyLink: {
    minHeight: layout.touchTarget,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
  },
  historyLinkText: { flex: 1, color: colors.accent, fontSize: font.small, fontWeight: '700' },
  textAction: { alignSelf: 'flex-start', paddingVertical: spacing.xs },
  dangerAction: { color: colors.danger, fontSize: font.small, fontWeight: '700' },
  formSection: { gap: spacing.lg },
  field: { gap: spacing.xs },
  fieldLabel: { color: colors.subtle, fontSize: font.small, fontWeight: '700' },
  segment: { flexDirection: 'row', gap: 4, backgroundColor: colors.surfaceMuted, borderRadius: radius.lg, padding: 4 },
  segmentItem: { flex: 1, minHeight: 44, alignItems: 'center', justifyContent: 'center', borderRadius: radius.md },
  segmentActive: { backgroundColor: colors.surface },
  segmentText: { color: colors.subtle, fontSize: font.small, fontWeight: '700' },
  segmentTextActive: { color: colors.ink },
  autoLockList: { gap: spacing.xs },
  autoLockRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
    minHeight: 48,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  autoLockRowActive: { backgroundColor: colors.surfaceMuted, borderColor: colors.ink },
  autoLockText: { flex: 1, color: colors.ink, fontSize: font.body, fontWeight: '600' },
  autoLockTextActive: { fontWeight: '800' },
  input: { minHeight: 52, backgroundColor: colors.surface, borderRadius: radius.lg, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, color: colors.ink, fontSize: font.body, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  multiline: { minHeight: 110, textAlignVertical: 'top' },
  inputWithIcon: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, minHeight: 52, backgroundColor: colors.surface, borderRadius: radius.lg, paddingHorizontal: spacing.lg, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  dateInput: { flex: 1, color: colors.ink, fontSize: font.body, paddingVertical: spacing.md, writingDirection: 'ltr' },
  pickerWrap: { marginTop: spacing.sm, borderRadius: radius.lg, backgroundColor: colors.surface, overflow: 'hidden' },
  pickerDone: { minHeight: 44, alignItems: 'center', justifyContent: 'center', borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  pickerDoneText: { color: colors.ink, fontSize: font.body, fontWeight: '700' },
  errorText: { color: colors.danger, fontSize: font.small },
  infoPanel: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  roundAction: { width: layout.touchTarget, height: layout.touchTarget, borderRadius: radius.pill, backgroundColor: colors.surfaceMuted, alignItems: 'center', justifyContent: 'center' },
  detailRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingVertical: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  detailIcon: { width: 34, height: 34, borderRadius: radius.md, backgroundColor: colors.surfaceMuted, alignItems: 'center', justifyContent: 'center' },
  detailLabel: { flex: 1, color: colors.subtle, fontSize: font.small },
  detailValue: { flex: 1.2, color: colors.ink, fontSize: font.small, fontWeight: '700' },
  menuRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  menuIcon: { width: 38, height: 38, borderRadius: radius.md, backgroundColor: colors.surfaceMuted, alignItems: 'center', justifyContent: 'center' },
  menuIconDanger: { backgroundColor: colors.surfaceMuted },
  menuLabel: { color: colors.ink, fontSize: font.body, fontWeight: '600' },
  settingsPanel: {
    gap: spacing.sm,
    padding: spacing.lg,
    borderRadius: radius.xl,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  settingsRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  version: { color: colors.subtle, fontSize: font.tiny, textAlign: 'center' },
  retryChip: {
    alignSelf: 'flex-start',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: colors.ink,
    minHeight: 44,
    justifyContent: 'center',
  },
  retryText: { color: colors.surface, fontWeight: '700', fontSize: font.small },
  helpPanel: {
    gap: spacing.md,
    padding: spacing.lg,
    borderRadius: radius.xl,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  stateSafe: { flex: 1, backgroundColor: colors.bg },
  stateWrap: { flex: 1, padding: spacing.xl, justifyContent: 'center', gap: spacing.xl },
  stateCard: {
    minHeight: 220,
    justifyContent: 'center',
    gap: spacing.lg,
    padding: spacing.lg,
    borderRadius: radius.xl,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  stateIcon: { width: 58, height: 58, borderRadius: radius.xl, backgroundColor: colors.surfaceMuted, alignItems: 'center', justifyContent: 'center' },
  stateCopy: { color: colors.subtle, fontSize: font.body, lineHeight: 23 },
})
