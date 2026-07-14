import { useState } from 'react'
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import Ionicons from '@expo/vector-icons/Ionicons'

import { useI18n, type AppLocale } from '@/i18n'
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
import { StatusChip } from '@/components/ui'
import { formatDate, formatNumber, formatTimeRange, statusLabel, statusTone } from '@/lib/format'
import { colors, font, radius, shadows, spacing } from '@/theme'
import type {
  AttendanceResponse,
  EmployeeDocument,
  EmployeeProfile,
  LeaveRequestRow,
  LeaveResponse,
  NotificationItem,
  NotificationsResponse,
  ShiftRow,
} from '@/api/types'

type BaseProps = {
  onBack?: () => void
}

function Page({
  title,
  subtitle,
  eyebrow,
  children,
  onBack,
  bloom = true,
  safeTop = false,
}: BaseProps & {
  title: string
  subtitle?: string
  eyebrow?: string
  children: React.ReactNode
  bloom?: boolean
  safeTop?: boolean
}) {
  const { isRTL, t } = useI18n()
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  return (
    <SafeAreaView style={styles.safe} edges={onBack || safeTop ? ['top'] : []}>
      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
        automaticallyAdjustKeyboardInsets={Platform.OS === 'ios'}
      >
        <View style={[styles.nav, isRTL && styles.rowReverse]}>
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
          {eyebrow ? <Text style={[styles.eyebrow, align]}>{eyebrow}</Text> : null}
          <EditorialHeading>{title}</EditorialHeading>
          {subtitle ? <Text style={[styles.subtitle, align]}>{subtitle}</Text> : null}
          {bloom ? <WathefniBloom variant="ribbon" style={styles.heroBloom} /> : null}
        </FadeIn>
        {children}
      </ScrollView>
    </SafeAreaView>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  const { isRTL } = useI18n()
  return <Text style={[styles.sectionLabel, { textAlign: isRTL ? 'right' : 'left' }]}>{children}</Text>
}

function EmptyCard({ icon, message, tone = 'lilac' }: { icon: keyof typeof Ionicons.glyphMap; message: string; tone?: PastelTone }) {
  const { isRTL } = useI18n()
  return (
    <PastelCard tone={tone} style={styles.emptyCard}>
      <IconBadge name={icon} />
      <Text style={[styles.emptyText, { textAlign: isRTL ? 'right' : 'left' }]}>{message}</Text>
      <WathefniBloom variant="watermark" />
    </PastelCard>
  )
}

export function NotificationsView({
  data,
  onMarkRead,
}: {
  data: NotificationsResponse
  onMarkRead: (item: NotificationItem) => void
}) {
  const { t, locale, isRTL } = useI18n()
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  return (
    <Page
      eyebrow={t('remaining.inboxEyebrow')}
      title={t('notifications.title')}
      subtitle={data.unread ? t('remaining.inboxUnread', { count: formatNumber(data.unread, locale, 0) }) : t('remaining.inboxClear')}
    >
      {data.notifications.length ? (
        <View style={styles.section}>
          {data.notifications.map((item, index) => (
            <FadeIn key={item.id} delay={70 + index * 30}>
              <Pressable
                accessibilityRole="button"
                onPress={() => onMarkRead(item)}
                style={({ pressed }) => [styles.notificationCard, !item.read && styles.notificationUnread, pressed && styles.pressed]}
              >
                <View style={[styles.notificationHead, isRTL && styles.rowReverse]}>
                  <View style={[styles.notificationIcon, { backgroundColor: item.read ? colors.surfaceMuted : colors.pastelBlush }]}>
                    <Ionicons name={item.read ? 'mail-open-outline' : 'mail-outline'} size={20} color={colors.ink} />
                  </View>
                  <View style={styles.flex}>
                    <Text style={[styles.itemTitle, align]}>{item.title}</Text>
                    {item.body ? <Text style={[styles.supporting, align]}>{item.body}</Text> : null}
                    <Text style={[styles.meta, align]}>{formatDate(item.created_at, locale)}</Text>
                  </View>
                  {!item.read ? <View style={styles.unreadDot} /> : null}
                </View>
              </Pressable>
            </FadeIn>
          ))}
        </View>
      ) : (
        <EmptyCard icon="mail-open-outline" message={t('notifications.empty')} tone="blush" />
      )}
    </Page>
  )
}

export function LeaveView({
  data,
  canRequest,
  canCancel,
  onRequest,
  onCancel,
}: {
  data: LeaveResponse
  canRequest: boolean
  canCancel: boolean
  onRequest: () => void
  onCancel: (leaveId: string) => void
}) {
  const { t, locale, isRTL } = useI18n()
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  return (
    <Page eyebrow={t('remaining.leaveEyebrow')} title={t('leave.title')} subtitle={t('remaining.leaveSubtitle')}>
      {data.balances_enabled && data.balances.length ? (
        <View style={styles.section}>
          <SectionLabel>{t('leave.balance')}</SectionLabel>
          <View style={styles.balanceGrid}>
            {data.balances.map((balance, index) => (
              <PastelCard
                key={`${balance.leave_type}-${balance.period_year ?? ''}`}
                tone={index % 2 ? 'sky' : 'sage'}
                style={styles.balanceCard}
              >
                <Text style={[styles.balanceType, align]}>{leaveTypeLabel(balance.leave_type, t)}</Text>
                <Text style={[styles.balanceValue, align]}>
                  {formatNumber(balance.balance_days ?? 0, locale)}
                </Text>
                <Text style={[styles.balanceUnit, align]}>{t('remaining.daysAvailable')}</Text>
              </PastelCard>
            ))}
          </View>
          <Text style={[styles.footnote, align]}>{t('leave.notEnforced')}</Text>
        </View>
      ) : null}
      {canRequest ? <PremiumButton label={t('leave.request')} onPress={onRequest} showDirection /> : null}
      <View style={styles.section}>
        <SectionLabel>{t('leave.requests')}</SectionLabel>
        {data.requests.length ? (
          data.requests.map((request, index) => (
            <LeaveRequestCard
              key={request.leave_id}
              request={request}
              index={index}
              canCancel={canCancel}
              onCancel={onCancel}
            />
          ))
        ) : (
          <EmptyCard icon="umbrella-outline" message={t('leave.empty')} tone="sage" />
        )}
      </View>
    </Page>
  )
}

function LeaveRequestCard({
  request,
  index,
  canCancel,
  onCancel,
}: {
  request: LeaveRequestRow
  index: number
  canCancel: boolean
  onCancel: (leaveId: string) => void
}) {
  const { t, locale, isRTL } = useI18n()
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  const cancellable = canCancel && ['requested', 'approved'].includes(request.status.toLowerCase())
  return (
    <PastelCard tone={index % 2 ? 'lilac' : 'butter'} style={styles.requestCard}>
      <View style={[styles.cardHead, isRTL && styles.rowReverse]}>
        <Text style={[styles.itemTitle, styles.flex, align]}>
          {formatDate(request.start_date, locale)} – {formatDate(request.end_date, locale)}
        </Text>
        <StatusChip label={statusLabel(request.status, t)} tone={statusTone(request.status)} />
      </View>
      {request.leave_type ? <Text style={[styles.supporting, align]}>{leaveTypeLabel(request.leave_type, t)}</Text> : null}
      {request.reason ? <Text style={[styles.meta, align]}>{request.reason}</Text> : null}
      {cancellable ? (
        <Pressable accessibilityRole="button" onPress={() => onCancel(request.leave_id)} style={styles.textAction}>
          <Text style={styles.dangerAction}>{t('leave.cancel')}</Text>
        </Pressable>
      ) : null}
    </PastelCard>
  )
}

export function LeaveRequestView({
  leaveTypes,
  busy,
  error,
  onSubmit,
  onBack,
}: {
  leaveTypes: string[]
  busy: boolean
  error: string | null
  onSubmit: (value: { startDate: string; endDate: string; leaveType: string; reason: string }) => void
  onBack: () => void
}) {
  const { t, isRTL } = useI18n()
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [leaveType, setLeaveType] = useState(leaveTypes[0] || '')
  const [reason, setReason] = useState('')
  const valid = /^\d{4}-\d{2}-\d{2}$/.test(startDate) && /^\d{4}-\d{2}-\d{2}$/.test(endDate) && Boolean(leaveType)
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.safe}>
      <Page onBack={onBack} eyebrow={t('remaining.leaveRequestEyebrow')} title={t('leave.request')} subtitle={t('remaining.leaveRequestSubtitle')}>
        <View style={styles.formSection}>
          <Text style={[styles.fieldLabel, align]}>{t('leave.type')}</Text>
          <View style={[styles.segment, isRTL && styles.rowReverse]}>
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
          <DateField label={t('leave.startDate')} value={startDate} onChange={setStartDate} isRTL={isRTL} />
          <DateField label={t('leave.endDate')} value={endDate} onChange={setEndDate} isRTL={isRTL} />
          <View style={styles.field}>
            <Text style={[styles.fieldLabel, align]}>{t('leave.reason')}</Text>
            <TextInput
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
            disabled={!valid}
            onPress={() => onSubmit({ startDate, endDate, leaveType, reason })}
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

function DateField({ label, value, onChange, isRTL }: { label: string; value: string; onChange: (value: string) => void; isRTL: boolean }) {
  return (
    <View style={styles.field}>
      <Text style={[styles.fieldLabel, { textAlign: isRTL ? 'right' : 'left' }]}>{label}</Text>
      <View style={[styles.inputWithIcon, isRTL && styles.rowReverse]}>
        <Ionicons name="calendar-outline" size={19} color={colors.subtle} />
        <TextInput
          value={value}
          onChangeText={onChange}
          placeholder="YYYY-MM-DD"
          placeholderTextColor={colors.subtle}
          autoCapitalize="none"
          keyboardType="numbers-and-punctuation"
          style={[styles.dateInput, { textAlign: isRTL ? 'right' : 'left' }]}
        />
      </View>
    </View>
  )
}

export function ShiftsView({ today, upcoming }: { today: ShiftRow[]; upcoming: ShiftRow[] }) {
  const { t } = useI18n()
  return (
    <Page eyebrow={t('remaining.shiftsEyebrow')} title={t('shifts.title')} subtitle={t('remaining.shiftsSubtitle')}>
      <View style={styles.section}>
        <SectionLabel>{t('shifts.today')}</SectionLabel>
        {today.length ? today.map((shift, index) => <ShiftCard key={shift.shift_id} shift={shift} index={index} />) : (
          <EmptyCard icon="calendar-clear-outline" message={t('home.noShiftToday')} tone="sky" />
        )}
      </View>
      <View style={styles.section}>
        <SectionLabel>{t('shifts.upcoming')}</SectionLabel>
        {upcoming.length ? upcoming.map((shift, index) => <ShiftCard key={shift.shift_id} shift={shift} index={index + 1} />) : (
          <EmptyCard icon="calendar-outline" message={t('shifts.empty')} tone="lilac" />
        )}
      </View>
    </Page>
  )
}

function ShiftCard({ shift, index }: { shift: ShiftRow; index: number }) {
  const { t, locale, isRTL } = useI18n()
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  return (
    <PastelCard tone={index % 2 ? 'lilac' : 'sky'} style={styles.shiftCard}>
      <View style={[styles.cardHead, isRTL && styles.rowReverse]}>
        <Text style={[styles.metaStrong, align]}>{formatDate(shift.shift_date, locale)}</Text>
        <StatusChip label={statusLabel(shift.status, t)} tone={statusTone(shift.status)} />
      </View>
      <Text style={[styles.shiftTime, align]}>{formatTimeRange(shift.start_time, shift.end_time, locale)}</Text>
      {shift.role || shift.location ? (
        <View style={[styles.locationRow, isRTL && styles.rowReverse]}>
          <Ionicons name="location-outline" size={17} color={colors.subtle} />
          <Text style={[styles.supporting, align]}>{shift.location || shift.role}</Text>
        </View>
      ) : null}
    </PastelCard>
  )
}

export function AttendanceView({ data }: { data: AttendanceResponse }) {
  const { t, locale, isRTL } = useI18n()
  return (
    <Page safeTop={false} eyebrow={t('remaining.attendanceEyebrow')} title={t('attendance.title')} subtitle={t('remaining.attendanceSubtitle')}>
      <View style={[styles.attendanceSummary, isRTL && styles.rowReverse]}>
        <SummaryMetric tone="sage" label={t('attendance.present')} value={data.summary.present} locale={locale} />
        <SummaryMetric tone="butter" label={t('attendance.late')} value={data.summary.late} locale={locale} />
        <SummaryMetric tone="blush" label={t('attendance.absent')} value={data.summary.absent} locale={locale} />
      </View>
      <View style={styles.section}>
        <SectionLabel>{t('remaining.recentActivity')}</SectionLabel>
        {data.records.length ? data.records.map((record, index) => (
          <View key={`${record.attendance_date}-${index}`} style={[styles.recordRow, isRTL && styles.rowReverse]}>
            <View style={[styles.timelineDot, { backgroundColor: statusColor(record.status) }]} />
            <Text style={[styles.recordDate, styles.flex, { textAlign: isRTL ? 'right' : 'left' }]}>
              {formatDate(record.attendance_date, locale)}
            </Text>
            <StatusChip label={statusLabel(record.status, t)} tone={statusTone(record.status)} />
          </View>
        )) : <EmptyCard icon="time-outline" message={t('attendance.empty')} tone="butter" />}
      </View>
    </Page>
  )
}

function SummaryMetric({ tone, label, value, locale }: { tone: PastelTone; label: string; value: number; locale: string }) {
  return (
    <PastelCard tone={tone} style={styles.summaryMetric}>
      <Text style={styles.summaryValue}>{formatNumber(value, locale, 0)}</Text>
      <Text style={styles.summaryLabel}>{label}</Text>
    </PastelCard>
  )
}

export function DocumentsView({
  documents,
  openingId,
  downloadProgress = 0,
  onOpen,
  onCancel,
}: {
  documents: EmployeeDocument[]
  openingId: string | null
  downloadProgress?: number
  onOpen: (fileId: string, filename: string | null) => void
  onCancel?: () => void
}) {
  const { t, locale, isRTL } = useI18n()
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  return (
    <Page safeTop={false} eyebrow={t('remaining.documentsEyebrow')} title={t('documents.title')} subtitle={t('remaining.documentsSubtitle')}>
      {documents.length ? (
        <View style={styles.section}>
          {documents.map((document, index) => (
            <PastelCard key={document.file_id} tone={index % 2 ? 'sage' : 'lilac'} style={styles.documentCard}>
              <View style={[styles.documentRow, isRTL && styles.rowReverse]}>
                <IconBadge name="document-text-outline" />
                <View style={styles.flex}>
                  <Text style={[styles.itemTitle, align]}>{document.label || document.document_type || document.filename}</Text>
                  <Text style={[styles.meta, align]}>{formatDate(document.stored_at, locale)}</Text>
                </View>
                {document.has_file ? (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={openingId === document.file_id ? t('common.cancel') : t('documents.view')}
                    onPress={() => openingId === document.file_id ? onCancel?.() : onOpen(document.file_id, document.filename)}
                    style={styles.roundAction}
                  >
                    {openingId === document.file_id ? (
                      <Ionicons name="close" size={19} color={colors.ink} />
                    ) : (
                      <Ionicons name="eye-outline" size={19} color={colors.ink} />
                    )}
                  </Pressable>
                ) : null}
              </View>
              {openingId === document.file_id ? (
                <View style={styles.documentProgress}>
                  <ActivityIndicator size="small" color={colors.ink} />
                  <View style={styles.documentProgressTrack}>
                    <View style={[styles.documentProgressFill, { width: `${Math.round(downloadProgress * 100)}%` }]} />
                  </View>
                  <Text style={styles.meta}>{Math.round(downloadProgress * 100)}%</Text>
                </View>
              ) : null}
            </PastelCard>
          ))}
        </View>
      ) : <EmptyCard icon="documents-outline" message={t('documents.empty')} tone="lilac" />}
      <PastelCard tone="butter" style={styles.infoCard}>
        <Ionicons name="shield-checkmark-outline" size={22} color={colors.warning} />
        <Text style={[styles.supporting, styles.flex, align]}>{t('remaining.documentsSecure')}</Text>
      </PastelCard>
    </Page>
  )
}

export function ProfileView({
  profile,
  onSettings,
  onPrivacySupport,
  onSignOut,
}: {
  profile: EmployeeProfile | null
  onSettings: () => void
  onPrivacySupport: () => void
  onSignOut: () => void
}) {
  const { t, isRTL } = useI18n()
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  const initials = initialsFor(profile?.name || '')
  return (
    <Page eyebrow={t('remaining.profileEyebrow')} title={t('profile.title')} subtitle={t('remaining.profileSubtitle')}>
      <PastelCard tone="lilac" style={styles.profileHero}>
        <View style={[styles.profileTop, isRTL && styles.rowReverse]}>
          <View style={styles.largeAvatar}><Text style={styles.largeAvatarText}>{initials || 'W'}</Text></View>
          <View style={styles.flex}>
            <Text style={[styles.profileName, align]}>{profile?.name || '—'}</Text>
            {profile?.position_title ? <Text style={[styles.supporting, align]}>{profile.position_title}</Text> : null}
          </View>
        </View>
        <WathefniBloom variant="watermark" />
      </PastelCard>
      <View style={styles.section}>
        <SectionLabel>{t('profile.details')}</SectionLabel>
        <View style={styles.detailsCard}>
          <DetailRow icon="briefcase-outline" label={t('profile.position')} value={profile?.position_title || '—'} />
          <DetailRow icon="people-outline" label={t('profile.department')} value={profile?.department || '—'} />
          <DetailRow icon="business-outline" label={t('profile.company')} value={profile?.company_code || '—'} />
          <DetailRow icon="call-outline" label={t('profile.phone')} value={profile?.phone || '—'} />
        </View>
      </View>
      <View style={styles.section}>
        <SectionLabel>{t('profile.account')}</SectionLabel>
        <MenuRow icon="settings-outline" label={t('settings.title')} onPress={onSettings} />
        <MenuRow icon="help-circle-outline" label={t('remaining.privacySupportTitle')} onPress={onPrivacySupport} />
        <MenuRow icon="log-out-outline" label={t('auth.signOut')} onPress={onSignOut} danger />
      </View>
    </Page>
  )
}

function DetailRow({ icon, label, value }: { icon: keyof typeof Ionicons.glyphMap; label: string; value: string }) {
  const { isRTL } = useI18n()
  return (
    <View style={[styles.detailRow, isRTL && styles.rowReverse]}>
      <View style={styles.detailIcon}><Ionicons name={icon} size={18} color={colors.ink} /></View>
      <Text style={[styles.detailLabel, { textAlign: isRTL ? 'right' : 'left' }]}>{label}</Text>
      <Text style={[styles.detailValue, { textAlign: isRTL ? 'left' : 'right' }]}>{value}</Text>
    </View>
  )
}

function MenuRow({ icon, label, onPress, danger = false }: { icon: keyof typeof Ionicons.glyphMap; label: string; onPress: () => void; danger?: boolean }) {
  const { isRTL } = useI18n()
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => [styles.menuRow, isRTL && styles.rowReverse, pressed && styles.pressed]}>
      <View style={[styles.menuIcon, danger && styles.menuIconDanger]}><Ionicons name={icon} size={19} color={danger ? colors.danger : colors.ink} /></View>
      <Text style={[styles.menuLabel, styles.flex, danger && { color: colors.danger }, { textAlign: isRTL ? 'right' : 'left' }]}>{label}</Text>
      <Ionicons name={isRTL ? 'chevron-back' : 'chevron-forward'} size={18} color={colors.subtle} />
    </Pressable>
  )
}

export function SettingsView({
  locale,
  pushOn,
  pushBusy,
  canManagePush,
  version,
  onLocale,
  onTogglePush,
  onPrivacySupport,
  onDelete,
}: {
  locale: AppLocale
  pushOn: boolean
  pushBusy: boolean
  canManagePush: boolean
  version: string
  onLocale: (locale: AppLocale) => void
  onTogglePush: (value: boolean) => void
  onPrivacySupport: () => void
  onDelete: () => void
}) {
  const { t, isRTL } = useI18n()
  return (
    <Page safeTop={false} eyebrow={t('remaining.settingsEyebrow')} title={t('settings.title')} subtitle={t('remaining.settingsSubtitle')}>
      <View style={styles.section}>
        <SectionLabel>{t('settings.language')}</SectionLabel>
        <View style={[styles.segment, isRTL && styles.rowReverse]}>
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
        <PastelCard tone="sky" style={styles.settingsCard}>
          <View style={[styles.settingsRow, isRTL && styles.rowReverse]}>
            <IconBadge name="notifications-outline" />
            <View style={styles.flex}>
              <Text style={[styles.itemTitle, { textAlign: isRTL ? 'right' : 'left' }]}>{t('settings.push')}</Text>
              <Text style={[styles.supporting, { textAlign: isRTL ? 'right' : 'left' }]}>{t('remaining.pushSubtitle')}</Text>
            </View>
            <Switch value={pushOn} onValueChange={onTogglePush} disabled={pushBusy} />
          </View>
        </PastelCard>
      ) : null}
      <View style={styles.section}>
        <MenuRow icon="shield-checkmark-outline" label={t('remaining.privacySupportTitle')} onPress={onPrivacySupport} />
        <MenuRow icon="trash-outline" label={t('settings.deleteAccount')} onPress={onDelete} danger />
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
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
  return (
    <Page onBack={onBack} eyebrow={t('remaining.helpEyebrow')} title={t('remaining.privacySupportTitle')} subtitle={t('remaining.privacySupportSubtitle')}>
      <PastelCard tone="sage" style={styles.helpCard}>
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
  const align = { textAlign: isRTL ? 'right' : 'left' } as const
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

function initialsFor(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join('')
}

function statusColor(status: string): string {
  if (status === 'present') return colors.success
  if (status === 'late') return colors.warning
  if (status === 'absent') return colors.danger
  return colors.subtle
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { paddingHorizontal: spacing.xl, paddingTop: spacing.md, paddingBottom: 120, gap: spacing.xl },
  nav: { minHeight: 42, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  navSpacer: { width: 44 },
  backButton: { width: 44, height: 44, borderRadius: radius.pill, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', ...shadows.card },
  hero: { gap: spacing.sm, position: 'relative', overflow: 'hidden', paddingBottom: spacing.xs },
  eyebrow: { color: colors.accent, fontSize: font.tiny, fontWeight: '800', letterSpacing: 0.9, textTransform: 'uppercase' },
  subtitle: { color: colors.subtle, fontSize: font.body, lineHeight: 22, maxWidth: 360 },
  heroBloom: { position: 'absolute', opacity: 0.32, right: -24, bottom: -9 },
  rowReverse: { flexDirection: 'row-reverse' },
  flex: { flex: 1 },
  section: { gap: spacing.md },
  sectionLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '800', letterSpacing: 0.65, textTransform: 'uppercase' },
  emptyCard: { minHeight: 150, justifyContent: 'center', gap: spacing.md, overflow: 'hidden' },
  emptyText: { color: colors.ink, fontSize: font.h3, fontWeight: '700', maxWidth: 230 },
  pressed: { opacity: 0.82 },
  notificationCard: { backgroundColor: colors.surface, borderRadius: radius.xl, padding: spacing.lg, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, ...shadows.card },
  notificationUnread: { backgroundColor: colors.pastelBlush, borderColor: colors.pastelBlush },
  notificationHead: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  notificationIcon: { width: 42, height: 42, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center' },
  itemTitle: { color: colors.ink, fontSize: font.h3, fontWeight: '700', lineHeight: 22 },
  supporting: { color: colors.subtle, fontSize: font.small, lineHeight: 20 },
  meta: { color: colors.subtle, fontSize: font.tiny, marginTop: spacing.xs },
  metaStrong: { color: colors.subtle, fontSize: font.small, fontWeight: '700' },
  unreadDot: { width: 9, height: 9, borderRadius: 5, backgroundColor: colors.accent, marginTop: 5 },
  balanceGrid: { flexDirection: 'row', gap: spacing.md },
  balanceCard: { flex: 1, minHeight: 130, justifyContent: 'space-between' },
  balanceType: { color: colors.subtle, fontSize: font.small, fontWeight: '700' },
  balanceValue: { color: colors.ink, fontSize: 38, fontWeight: '800', letterSpacing: -1 },
  balanceUnit: { color: colors.subtle, fontSize: font.tiny },
  footnote: { color: colors.subtle, fontSize: font.tiny, lineHeight: 18 },
  requestCard: { gap: spacing.sm },
  cardHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: spacing.md },
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
  input: { minHeight: 52, backgroundColor: colors.surface, borderRadius: radius.lg, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, color: colors.ink, fontSize: font.body, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  multiline: { minHeight: 110, textAlignVertical: 'top' },
  inputWithIcon: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, minHeight: 52, backgroundColor: colors.surface, borderRadius: radius.lg, paddingHorizontal: spacing.lg, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  dateInput: { flex: 1, color: colors.ink, fontSize: font.body, paddingVertical: spacing.md, writingDirection: 'ltr' },
  errorText: { color: colors.danger, fontSize: font.small },
  infoCard: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  shiftCard: { minHeight: 144, justifyContent: 'space-between' },
  shiftTime: { color: colors.ink, fontSize: 29, fontWeight: '800', letterSpacing: -0.6 },
  locationRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  attendanceSummary: { flexDirection: 'row', gap: spacing.sm },
  summaryMetric: { flex: 1, minHeight: 110, alignItems: 'center', justifyContent: 'center', paddingHorizontal: spacing.sm },
  summaryValue: { color: colors.ink, fontSize: font.h1, fontWeight: '800' },
  summaryLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700', textAlign: 'center' },
  recordRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, ...shadows.card },
  timelineDot: { width: 10, height: 10, borderRadius: 5 },
  recordDate: { color: colors.ink, fontSize: font.body, fontWeight: '600' },
  documentCard: { padding: spacing.lg, gap: spacing.md },
  documentRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  roundAction: { width: 44, height: 44, borderRadius: radius.pill, backgroundColor: 'rgba(255,255,255,0.62)', alignItems: 'center', justifyContent: 'center' },
  documentProgress: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  documentProgressTrack: { flex: 1, height: 6, borderRadius: radius.pill, overflow: 'hidden', backgroundColor: 'rgba(255,255,255,0.58)' },
  documentProgressFill: { height: '100%', borderRadius: radius.pill, backgroundColor: colors.accent },
  profileHero: { minHeight: 160, justifyContent: 'center', overflow: 'hidden' },
  profileTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg },
  largeAvatar: { width: 72, height: 72, borderRadius: radius.pill, backgroundColor: colors.ink, alignItems: 'center', justifyContent: 'center' },
  largeAvatarText: { color: colors.surface, fontSize: font.h1, fontWeight: '800' },
  profileName: { color: colors.ink, fontSize: font.h1, fontWeight: '800', letterSpacing: -0.5 },
  detailsCard: { backgroundColor: colors.surface, borderRadius: radius.xl, paddingHorizontal: spacing.lg, ...shadows.card },
  detailRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingVertical: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  detailIcon: { width: 34, height: 34, borderRadius: radius.md, backgroundColor: colors.pastelSky, alignItems: 'center', justifyContent: 'center' },
  detailLabel: { flex: 1, color: colors.subtle, fontSize: font.small },
  detailValue: { flex: 1.2, color: colors.ink, fontSize: font.small, fontWeight: '700' },
  menuRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.md, ...shadows.card },
  menuIcon: { width: 38, height: 38, borderRadius: radius.md, backgroundColor: colors.pastelLilac, alignItems: 'center', justifyContent: 'center' },
  menuIconDanger: { backgroundColor: colors.dangerSoft },
  menuLabel: { color: colors.ink, fontSize: font.body, fontWeight: '600' },
  settingsCard: { padding: spacing.lg },
  settingsRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  version: { color: colors.subtle, fontSize: font.tiny, textAlign: 'center' },
  helpCard: { gap: spacing.md, minHeight: 210, justifyContent: 'space-between' },
  stateSafe: { flex: 1, backgroundColor: colors.bg },
  stateWrap: { flex: 1, padding: spacing.xl, justifyContent: 'center', gap: spacing.xl },
  stateCard: { minHeight: 310, justifyContent: 'center', gap: spacing.lg, overflow: 'hidden' },
  stateIcon: { width: 58, height: 58, borderRadius: radius.xl, backgroundColor: 'rgba(255,255,255,0.58)', alignItems: 'center', justifyContent: 'center' },
  stateCopy: { color: colors.subtle, fontSize: font.body, lineHeight: 23 },
})
