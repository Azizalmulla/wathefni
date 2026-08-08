import { useEffect, useState } from 'react'
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
import type { AutoLockDiagnostics } from '@/auth/autoLockDiagnostics'
import {
  EditorialHeading,
  FadeIn,
  IconBadge,
  PastelCard,
  PremiumButton,
  WathefniBloom,
  Wordmark,
  type PastelTone,
} from '@/components/premium'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader, ShowMoreButton, usePagedList } from '@/components/lists'
import {
  balanceForLeaveType,
  balancesAreInformational,
  type LeaveBalanceFact,
} from '@/features/leave/leaveBalance'
import { StatusChip } from '@/components/ui'
import {
  formatDate,
  formatDateRange,
  formatDateTime,
  formatNumber,
  formatRelativeTime,
  statusLabel,
  statusTone,
} from '@/lib/format'
import { colors, font, layout, radius, shadows, spacing, typeScaling } from '@/theme'
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
}: BaseProps & {
  title: string
  subtitle?: string
  children: React.ReactNode
  refreshing?: boolean
  onRefresh?: () => void
}) {
  const { isRTL, t } = useI18n()
  const align = readingEdgeAlign(isRTL)
  return (
    <PageScreen>
      <PageScrollView refreshing={refreshing} onRefresh={onRefresh}>
        <View style={styles.nav}>
          {onBack ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={t('common.back')}
              onPress={onBack}
              style={styles.backButton}
            >
              <Ionicons name={isRTL ? 'arrow-forward' : 'arrow-back'} size={19} color={colors.ink} />
            </Pressable>
          ) : null}
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
  const { isRTL } = useI18n()
  return (
    <Text
      accessibilityRole="header"
      maxFontSizeMultiplier={typeScaling.heading}
      style={[styles.sectionLabel, readingEdgeAlign(isRTL)]}
    >
      {children}
    </Text>
  )
}

function EmptyCard({ icon, message, tone = 'cream' }: { icon: keyof typeof Ionicons.glyphMap; message: string; tone?: PastelTone }) {
  const { isRTL } = useI18n()
  return (
    <PastelCard tone={tone} style={styles.emptyCard}>
      <IconBadge name={icon} />
      <Text style={[styles.emptyText, readingEdgeAlign(isRTL)]}>{message}</Text>
      <WathefniBloom variant="watermark" />
    </PastelCard>
  )
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
  const { t, locale } = useI18n()
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
            <View style={styles.list}>
              <SectionHeader title={t('notifications.unread')} count={unread.length} />
              {unread.map((item) => (
                <InboxRow key={item.id} item={item} onPress={() => onMarkRead(item)} />
              ))}
            </View>
          ) : null}

          {earlier.length ? (
            <View style={styles.list}>
              <SectionHeader title={t('notifications.earlier')} count={earlier.length} />
              {earlierPage.visible.map((item) => (
                <InboxRow key={item.id} item={item} onPress={() => onMarkRead(item)} />
              ))}
              {earlierPage.hidden ? (
                <ShowMoreButton
                  label={t('common.showMore', { count: formatNumber(earlierPage.hidden, locale, 0) })}
                  onPress={earlierPage.showMore}
                />
              ) : null}
            </View>
          ) : null}

          {systemActivity.length ? (
            <View style={styles.list}>
              <SectionHeader
                title={t('notifications.systemActivity')}
                count={systemActivity.length}
                collapsible
                expanded={systemOpen}
                onToggle={() => setSystemOpen((open) => !open)}
              />
              {systemOpen ? (
                <>
                  {systemPage.visible.map((item) => (
                    <InboxRow key={item.id} item={item} onPress={() => onMarkRead(item)} />
                  ))}
                  {systemPage.hidden ? (
                    <ShowMoreButton
                      label={t('common.showMore', { count: formatNumber(systemPage.hidden, locale, 0) })}
                      onPress={systemPage.showMore}
                    />
                  ) : null}
                </>
              ) : null}
            </View>
          ) : null}
        </>
      ) : (
        <EmptyCard icon="mail-open-outline" message={t('notifications.empty')} />
      )}
    </Page>
  )
}

function InboxRow({ item, onPress }: { item: NotificationItem; onPress: () => void }) {
  const { t, locale } = useI18n()
  const state = item.read ? t('notifications.read') : t('notifications.unreadItem')
  const when = formatRelativeTime(item.created_at, locale, t)
  // Relative time answers "is this new?" at a glance, but it rounds. The exact
  // timestamp the server sent is still the fact, so it stays available to
  // VoiceOver rather than being replaced by the approximation.
  const exact = formatDateTime(item.created_at, locale)
  return (
    <ListRow
      title={item.title}
      subtitle={item.body}
      meta={when}
      marked={!item.read}
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
  cancelingId,
  refreshing,
  onRefresh,
}: {
  data: LeaveResponse
  canRequest: boolean
  canCancel: boolean
  onRequest: () => void
  onCancel: (leaveId: string) => void
  cancelingId?: string | null
  refreshing?: boolean
  onRefresh?: () => void
}) {
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const requests = usePagedList(data.requests, LEAVE_PAGE)
  const balanceFacts = (data.balances ?? [])
    .map((balance) => balanceForLeaveType(data, balance.leave_type))
    .filter((fact): fact is LeaveBalanceFact => fact !== null)
  return (
    <Page
      title={t('leave.title')}
      subtitle={t('remaining.leaveSubtitle')}
      refreshing={refreshing}
      onRefresh={onRefresh}
    >
      {/* One olive surface for all balances, rather than one 130pt card each.
          A type whose number the server did not send is left out entirely: this
          list previously read every balance as `balance_days`, a field the API
          has never sent, and printed a confident 0 for all of them. */}
      {balanceFacts.length ? (
        <View style={styles.list}>
          <SectionHeader title={t('leave.balance')} />
          <PastelCard tone="olive" style={styles.balanceCard}>
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
      <View style={styles.list}>
        <SectionHeader title={t('leave.requests')} count={data.requests.length || undefined} />
        {data.requests.length ? (
          <>
            {requests.visible.map((request) => (
              <LeaveRequestRowItem
                key={request.leave_id}
                request={request}
                canCancel={canCancel}
                canceling={cancelingId === request.leave_id}
                onCancel={onCancel}
              />
            ))}
            {requests.hidden ? (
              <ShowMoreButton
                label={t('common.showMore', { count: formatNumber(requests.hidden, locale, 0) })}
                onPress={requests.showMore}
              />
            ) : null}
          </>
        ) : (
          <EmptyCard icon="umbrella-outline" message={t('leave.empty')} />
        )}
      </View>
    </Page>
  )
}

const LEAVE_PAGE = 12

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
  const cancellable = canCancel && ['requested', 'approved'].includes(request.status.toLowerCase())
  const dates = formatDateRange(request.start_date, request.end_date, locale)
  const type = request.leave_type ? leaveTypeLabel(request.leave_type, t) : null
  const status = statusLabel(request.status, t)
  return (
    <ListRow
      title={type || dates}
      subtitle={type ? dates : null}
      meta={request.reason}
      trailing={<StatusChip label={status} tone={statusTone(request.status)} />}
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
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.safe}>
      <Page onBack={onBack} title={t('leave.request')} subtitle={t('remaining.leaveRequestSubtitle')}>
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
        <PastelCard tone="butter" style={styles.infoCard}>
          <Ionicons name="information-circle-outline" size={22} color={colors.warning} />
          <Text style={[styles.supporting, styles.flex, align]}>{t('remaining.leaveAuthorityNote')}</Text>
        </PastelCard>
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
  autoLockDiagnostics,
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
  autoLockDiagnostics?: AutoLockDiagnostics | null
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
  const diag = autoLockDiagnostics
  const formatTs = (ms: number | null | undefined) => {
    if (ms == null) return '—'
    try {
      return new Date(ms).toISOString()
    } catch {
      return String(ms)
    }
  }
  const formatTimeout = (timeoutMs: AutoLockTimeoutMs | undefined) => {
    if (timeoutMs === undefined) return '—'
    if (timeoutMs == null) return 'never'
    if (timeoutMs === 0) return 'immediate'
    return `${timeoutMs} ms`
  }
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
      {diag ? (
        <View style={styles.section}>
          <SectionLabel>{t('autoLock.diagnosticsTitle')}</SectionLabel>
          <PastelCard tone="butter" style={styles.settingsCard}>
            <Text style={[styles.diagLine, align]}>{t('autoLock.diagMarker')}: {diag.buildMarker || '—'}</Text>
            <Text style={[styles.diagLine, align]}>{t('autoLock.diagUpdate')}: {diag.updateId || '—'}</Text>
            <Text style={[styles.diagLine, align]}>
              {t('autoLock.diagEnabled')}: {diag.featureEnabled ? 'yes' : `no (master=${diag.masterFlagRaw} key=${diag.employeeKey})`}
            </Text>
            <Text style={[styles.diagLine, align]}>
              {t('autoLock.diagOverlayBio')}: {diag.overlayBiometricEnabled ? 'yes' : `no (flag=${diag.overlayBiometricFlagRaw})`}
            </Text>
            <Text style={[styles.diagLine, align]}>
              {t('autoLock.diagBioFeature')}: {diag.biometricFeatureOn ? 'yes' : 'no'}
            </Text>
            <Text style={[styles.diagLine, align]}>
              {t('autoLock.diagBioPref')}:{' '}
              {diag.biometricPreferenceOn == null ? '—' : diag.biometricPreferenceOn ? 'yes' : 'no'}
            </Text>
            <Text style={[styles.diagLine, align]}>
              {t('autoLock.diagBioGate')}: {diag.lastBioGateReason || '—'}
            </Text>
            <Text style={[styles.diagLine, align]}>{t('autoLock.diagTimeout')}: {formatTimeout(diag.timeoutMs)}</Text>
            <Text style={[styles.diagLine, align]}>{t('autoLock.diagAway')}: {formatTs(diag.lastAwayAt)}</Text>
            <Text style={[styles.diagLine, align]}>
              {t('autoLock.diagElapsed')}: {diag.lastElapsedMs == null ? '—' : `${diag.lastElapsedMs} ms`}
            </Text>
            <Text style={[styles.diagLine, align]}>{t('autoLock.diagDecision')}: {diag.lastDecision}</Text>
            <Text style={[styles.diagLine, align]}>{t('autoLock.diagNeedsUnlock')}: {diag.needsLocalUnlock ? 'yes' : 'no'}</Text>
            <Text style={[styles.diagLine, align]}>appState: {diag.lastAppState}</Text>
          </PastelCard>
        </View>
      ) : null}
      {canManagePush ? (
        <PastelCard tone="sky" style={styles.settingsCard}>
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
        </PastelCard>
      ) : null}
      {canManageBiometric && onToggleBiometric ? (
        <PastelCard tone="cream" style={styles.settingsCard}>
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
        </PastelCard>
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
        <PastelCard tone="butter" style={styles.settingsCard}>
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
        </PastelCard>
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
      <PastelCard tone="cream" style={styles.helpCard}>
        <IconBadge name="shield-checkmark-outline" />
        <Text style={[styles.itemTitle, align]}>{t('settings.privacy')}</Text>
        <Text style={[styles.supporting, align]}>{t('remaining.privacyCopy')}</Text>
        <PremiumButton label={t('remaining.readPrivacy')} onPress={onPrivacy} showDirection />
      </PastelCard>
      <PastelCard tone="butter" style={styles.helpCard}>
        <IconBadge name="chatbubble-ellipses-outline" />
        <Text style={[styles.itemTitle, align]}>{t('remaining.supportTitle')}</Text>
        <Text style={[styles.supporting, align]}>{t('remaining.supportCopy')}</Text>
        <PremiumButton label={t('remaining.contactSupport')} onPress={onSupport} showDirection />
      </PastelCard>
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
        <PastelCard tone="lilac" style={styles.stateCard}>
          <View style={styles.stateIcon}><Ionicons name="compass-outline" size={34} color={colors.ink} /></View>
          <EditorialHeading size="medium">{t('notFound.title')}</EditorialHeading>
          <Text style={[styles.stateCopy, align]}>{t('notFound.message')}</Text>
          <PremiumButton label={t('feature.backHome')} onPress={onHome} showDirection />
          <WathefniBloom variant="watermark" />
        </PastelCard>
      </View>
    </SafeAreaView>
  )
}

function leaveTypeLabel(type: string, t: (key: string) => string): string {
  if (type === 'annual') return t('leave.typeAnnual')
  if (type === 'sick') return t('leave.typeSick')
  return t('leave.typeOther')
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  screen: { flex: 1, backgroundColor: colors.bg },

  nav: { minHeight: 42, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  navSpacer: { width: 44 },
  backButton: { width: 44, height: 44, borderRadius: radius.pill, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', ...shadows.card },
  hero: { gap: spacing.xs },
  subtitle: { color: colors.subtle, fontSize: font.small, lineHeight: 20, maxWidth: 360 },
  flex: { flex: 1 },
  section: { gap: spacing.md },
  /** Compact list rhythm: rows sit closer together than top-level sections. */
  list: { gap: spacing.sm },
  sectionLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '800', letterSpacing: 0.65, textTransform: 'uppercase' },
  emptyCard: { minHeight: 150, justifyContent: 'center', gap: spacing.md, overflow: 'hidden' },
  emptyText: { color: colors.ink, fontSize: font.h3, fontWeight: '700', maxWidth: 230 },
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
  balanceRow: { flexDirection: 'row', alignItems: 'baseline', gap: spacing.sm, paddingVertical: spacing.sm },
  balanceDivider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  balanceType: { color: colors.ink, fontSize: font.small, fontWeight: '700' },
  balanceValue: { color: colors.ink, fontSize: font.h2, fontWeight: '800', letterSpacing: -0.4 },
  balanceUnit: { color: colors.subtle, fontSize: font.tiny },
  footnote: { color: colors.subtle, fontSize: font.tiny, lineHeight: 18 },
  textAction: { alignSelf: 'flex-start', paddingVertical: spacing.xs },
  dangerAction: { color: colors.danger, fontSize: font.small, fontWeight: '700' },
  formSection: { gap: spacing.lg },
  field: { gap: spacing.xs },
  fieldLabel: { color: colors.subtle, fontSize: font.small, fontWeight: '700' },
  segment: { flexDirection: 'row', gap: 4, backgroundColor: colors.surfaceMuted, borderRadius: radius.lg, padding: 4 },
  segmentItem: { flex: 1, minHeight: 44, alignItems: 'center', justifyContent: 'center', borderRadius: radius.md },
  segmentActive: { backgroundColor: colors.surface, ...shadows.card },
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
    ...shadows.card,
  },
  autoLockRowActive: { backgroundColor: colors.surfaceMuted, borderColor: colors.ink },
  autoLockText: { flex: 1, color: colors.ink, fontSize: font.body, fontWeight: '600' },
  autoLockTextActive: { fontWeight: '800' },
  diagLine: { color: colors.ink, fontSize: font.tiny, fontWeight: '600', marginBottom: spacing.xs },
  input: { minHeight: 52, backgroundColor: colors.surface, borderRadius: radius.lg, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, color: colors.ink, fontSize: font.body, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  multiline: { minHeight: 110, textAlignVertical: 'top' },
  inputWithIcon: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, minHeight: 52, backgroundColor: colors.surface, borderRadius: radius.lg, paddingHorizontal: spacing.lg, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  dateInput: { flex: 1, color: colors.ink, fontSize: font.body, paddingVertical: spacing.md, writingDirection: 'ltr' },
  pickerWrap: { marginTop: spacing.sm, borderRadius: radius.lg, backgroundColor: colors.surface, overflow: 'hidden' },
  pickerDone: { minHeight: 44, alignItems: 'center', justifyContent: 'center', borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  pickerDoneText: { color: colors.ink, fontSize: font.body, fontWeight: '700' },
  errorText: { color: colors.danger, fontSize: font.small },
  infoCard: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  shiftCard: { minHeight: 144, justifyContent: 'space-between' },
  shiftTime: { color: colors.ink, fontSize: 29, fontWeight: '800', letterSpacing: -0.6 },
  locationRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  attendanceSummary: { flexDirection: 'row', gap: spacing.sm },
  summaryMetric: { flex: 1, minHeight: 96, alignItems: 'center', justifyContent: 'center', paddingHorizontal: spacing.sm },
  summaryValue: { color: colors.ink, fontSize: font.h1, fontWeight: '800' },
  summaryLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700', textAlign: 'center' },
  recordRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, ...shadows.card },
  timelineDot: { width: 10, height: 10, borderRadius: 5 },
  recordDate: { color: colors.ink, fontSize: font.body, fontWeight: '600' },
  documentCard: { padding: spacing.lg, gap: spacing.md },
  documentRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  roundAction: { width: layout.touchTarget, height: layout.touchTarget, borderRadius: radius.pill, backgroundColor: colors.surfaceMuted, alignItems: 'center', justifyContent: 'center' },
  documentProgress: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  documentProgressTrack: { flex: 1, height: 6, borderRadius: radius.pill, overflow: 'hidden', backgroundColor: colors.surfaceMuted },
  documentProgressFill: { height: '100%', borderRadius: radius.pill, backgroundColor: colors.accent },
  profileHero: { minHeight: 160, justifyContent: 'center', overflow: 'hidden' },
  profileTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg },
  largeAvatar: { width: 72, height: 72, borderRadius: radius.pill, backgroundColor: colors.ink, alignItems: 'center', justifyContent: 'center' },
  largeAvatarText: { color: colors.surface, fontSize: font.h1, fontWeight: '800' },
  profileName: { color: colors.ink, fontSize: font.h1, fontWeight: '800', letterSpacing: -0.5 },
  detailsCard: { backgroundColor: colors.surface, borderRadius: radius.xl, paddingHorizontal: spacing.lg, ...shadows.card },
  detailRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingVertical: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  detailIcon: { width: 34, height: 34, borderRadius: radius.md, backgroundColor: colors.surfaceMuted, alignItems: 'center', justifyContent: 'center' },
  detailLabel: { flex: 1, color: colors.subtle, fontSize: font.small },
  detailValue: { flex: 1.2, color: colors.ink, fontSize: font.small, fontWeight: '700' },
  menuRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.md, ...shadows.card },
  menuIcon: { width: 38, height: 38, borderRadius: radius.md, backgroundColor: colors.surfaceMuted, alignItems: 'center', justifyContent: 'center' },
  menuIconDanger: { backgroundColor: colors.surfaceMuted },
  menuLabel: { color: colors.ink, fontSize: font.body, fontWeight: '600' },
  settingsCard: { padding: spacing.lg },
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
  helpCard: { gap: spacing.md, minHeight: 210, justifyContent: 'space-between' },
  stateSafe: { flex: 1, backgroundColor: colors.bg },
  stateWrap: { flex: 1, padding: spacing.xl, justifyContent: 'center', gap: spacing.xl },
  stateCard: { minHeight: 310, justifyContent: 'center', gap: spacing.lg, overflow: 'hidden' },
  stateIcon: { width: 58, height: 58, borderRadius: radius.xl, backgroundColor: colors.surfaceMuted, alignItems: 'center', justifyContent: 'center' },
  stateCopy: { color: colors.subtle, fontSize: font.body, lineHeight: 23 },
})
