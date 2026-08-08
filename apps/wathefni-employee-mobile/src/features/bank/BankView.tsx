import { useMemo } from 'react'
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import Ionicons from '@expo/vector-icons/Ionicons'

import { useI18n, readingEdgeAlign } from '@/i18n'
import { StatusChip } from '@/components/ui'
import {
  ContentSkeleton,
  EditorialHeading,
  FadeIn,
  PastelCard,
  PremiumButton,
  Wordmark,
} from '@/components/premium'
import { PageScreen, PageScrollView } from '@/components/layout'
import { formatDate } from '@/lib/format'
import { colors, font, layout, radius, spacing, typeScaling } from '@/theme'
import type {
  BankDisplayValues,
  BankEvidenceRow,
  BankStatusResponse,
  BankSubmissionState,
} from '@/api/types'

/** Order is deliberate: the account identifier first, then the descriptive fields. */
export const BANK_FIELDS = [
  'iban',
  'account_number',
  'bank_name',
  'account_holder',
  'branch',
  'swift',
] as const

export type BankField = (typeof BANK_FIELDS)[number]

export type BankFormValues = Partial<Record<BankField, string>>

export type BankViewProps = {
  data: BankStatusResponse
  form: BankFormValues
  onChangeField: (field: BankField, value: string) => void
  formOpen: boolean
  onOpenForm: () => void
  onCloseForm: () => void
  submitting: boolean
  savingDraft: boolean
  withdrawing: boolean
  uploading: boolean
  onSubmit: () => void
  onSaveDraft: () => void
  onSubmitDraft: () => void
  onWithdraw: () => void
  onUploadEvidence: () => void
  onOpenEvidence: (evidence: BankEvidenceRow) => void
  openingEvidenceId?: string | null
  refreshing?: boolean
  onRefresh?: () => void
  onBack: () => void
  fieldErrors?: Partial<Record<BankField, string>>
  formError?: string | null
  extractionNote?: string | null
  onUploadCertificate?: () => void
}

function chipTone(state: string): 'neutral' | 'success' | 'warning' | 'danger' {
  switch (state) {
    case 'applied':
      return 'success'
    case 'approved':
    case 'pending_payroll':
      return 'warning'
    case 'pending_hr':
    case 'pending_review':
    case 'draft':
      return 'warning'
    case 'rejected':
    case 'needs_correction':
      return 'danger'
    default:
      return 'neutral'
  }
}

export function BankView({
  data,
  form,
  onChangeField,
  formOpen,
  onOpenForm,
  onCloseForm,
  submitting,
  savingDraft,
  withdrawing,
  uploading,
  onSubmit,
  onSaveDraft,
  onSubmitDraft,
  onWithdraw,
  onUploadEvidence,
  onOpenEvidence,
  openingEvidenceId = null,
  refreshing,
  onRefresh,
  onBack,
  fieldErrors = {},
  formError = null,
  extractionNote = null,
}: BankViewProps) {
  const { t, isRTL, locale } = useI18n()
  const align = readingEdgeAlign(isRTL)

  const submissionState = String(data.submission_state || 'none') as BankSubmissionState
  const submission = data.submission || null
  const hasVerified = Boolean(data.has_verified_bank)
  const hasEffective = Boolean(data.has_payroll_effective_bank || data.payroll_effective)
  const underReview =
    submissionState === 'pending_hr' ||
    submissionState === 'pending_review' ||
    submissionState === 'pending_payroll' ||
    submissionState === 'approved'
  const isDraft = submissionState === 'draft'
  const needsFix = submissionState === 'rejected' || submissionState === 'needs_correction'
  // The backend owns "what next"; the app only chooses the wording.
  const nextStep = data.next_step?.message || nextStepCopy(submissionState, hasVerified, t) || ''
  const evidence = submission?.evidence || []
  const proposedDisplay = submission?.proposed?.display || {}
  const showProposed = Boolean(submission) && submissionState !== 'none'

  const requiredMissing = useMemo(
    () => !String(form.iban || '').trim() && !String(form.account_number || '').trim(),
    [form.iban, form.account_number],
  )

  // The screen answers one question first: which account will be paid, and is it
  // settled? Payroll's effective account is that answer when it exists, otherwise
  // the account HR confirmed.
  const effectiveDisplay = data.payroll_effective?.display || {}
  const verifiedDisplay = data.verified?.display || {}
  const paidAccount = hasEffective ? effectiveDisplay : hasVerified ? verifiedDisplay : null
  // The confirmed account is only worth its own card while it differs from the
  // account payroll is actually using. Printing the same masked IBAN under two
  // headings read as two accounts.
  const showVerifiedSeparately =
    hasEffective && hasVerified && !sameDisplay(effectiveDisplay, verifiedDisplay)
  // A submission that payroll has already applied is the paid account above, not
  // a pending change.
  const pendingChange = showProposed && submissionState !== 'applied'

  return (
    <PageScreen>
      <PageScrollView refreshing={refreshing} onRefresh={onRefresh}>
        <View style={styles.nav}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t('common.back')}
            onPress={onBack}
            style={styles.backButton}
          >
            <Ionicons name={isRTL ? 'arrow-forward' : 'arrow-back'} size={19} color={colors.ink} />
          </Pressable>
          <Wordmark compact align="center" />
          <View style={styles.navSpacer} />
        </View>

        <FadeIn style={styles.hero}>
          <EditorialHeading>{t('bank.title')}</EditorialHeading>
          <Text style={[styles.subtitle, align]}>{t('bank.subtitle')}</Text>
        </FadeIn>

        {/* One account surface: the account that will be paid, stated once.
            Butter is the single colour moment on this screen. */}
        <PastelCard tone="butter" style={styles.card}>
          <View style={styles.cardHead}>
            <Text style={[styles.cardTitle, align]}>
              {hasEffective ? t('bank.payrollEffectiveTitle') : t('bank.verifiedTitle')}
            </Text>
            {paidAccount ? (
              <StatusChip
                label={hasEffective ? t('bank.payrollEffectiveChip') : t('bank.verifiedChip')}
                tone="success"
              />
            ) : null}
          </View>
          {paidAccount ? (
            <>
              <FieldList values={paidAccount} t={t} align={align} />
              {hasEffective && data.payroll_effective?.effective_from ? (
                <Text style={[styles.note, align]}>
                  {t('bank.payrollEffectiveFrom', {
                    date: formatDate(data.payroll_effective.effective_from, locale),
                  })}
                </Text>
              ) : null}
              {!hasEffective && data.verified?.verified_at ? (
                <Text style={[styles.note, align]}>
                  {t('bank.verifiedAt', { date: formatDate(data.verified.verified_at, locale) })}
                </Text>
              ) : null}
            </>
          ) : (
            <Text style={[styles.body, align]}>{t('bank.noVerifiedYet')}</Text>
          )}
        </PastelCard>

        {/* One human status line: what happens next, never a dead end. */}
        {nextStep ? (
          <View style={styles.statusLine}>
            <View style={styles.cardHead}>
              <Text style={[styles.subTitle, align]}>{t('bank.nextStepTitle')}</Text>
              <StatusChip label={submissionLabel(submissionState, t)} tone={chipTone(submissionState)} />
            </View>
            <Text style={[styles.body, align]}>{nextStep}</Text>
            {underReview ? (
              <Text style={[styles.note, align]}>{t('bank.payrollEffectiveUnchangedNote')}</Text>
            ) : null}
          </View>
        ) : null}

        {/* Only shown while HR's confirmed account and payroll's differ — otherwise
            it would be the masked IBAN above under a second heading. */}
        {showVerifiedSeparately ? (
          <View style={styles.statusLine}>
            <View style={styles.cardHead}>
              <Text style={[styles.subTitle, align]}>{t('bank.verifiedTitle')}</Text>
              <StatusChip label={t('bank.verifiedChip')} tone="success" />
            </View>
            <FieldList values={verifiedDisplay} t={t} align={align} />
            <Text style={[styles.note, align]}>{t('bank.verifiedUnchangedNote')}</Text>
          </View>
        ) : null}

        {/* The change the employee asked for, and why it came back. */}
        {pendingChange ? (
          <PastelCard tone="cream" style={styles.card}>
            <View style={styles.cardHead}>
              <Text style={[styles.cardTitle, align]}>{t('bank.submittedTitle')}</Text>
              <StatusChip label={submissionLabel(submissionState, t)} tone={chipTone(submissionState)} />
            </View>
            <FieldList values={proposedDisplay} t={t} align={align} />
            {submission?.submitted_at ? (
              <Text style={[styles.note, align]}>
                {/* Compose outside i18n interpolation — returned/resubmitted states
                    previously showed the literal "{date}" placeholder on device. */}
                {`${t('bank.submittedOn')} ${formatDate(submission.submitted_at, locale)}`}
              </Text>
            ) : null}
            {needsFix ? (
              <View style={styles.reasonBox}>
                <Text style={[styles.reasonTitle, align]}>{t('bank.rejectionReasonTitle')}</Text>
                <Text style={[styles.reasonText, align]}>
                  {submission?.rejection_reason || t('bank.rejectionReasonMissing')}
                </Text>
              </View>
            ) : null}

            {evidence.length ? (
              <View style={styles.evidenceList}>
                <Text style={[styles.subTitle, align]}>{t('bank.evidenceTitle')}</Text>
                {evidence.map((row) => (
                  <Pressable
                    key={row.evidence_id}
                    accessibilityRole="button"
                    accessibilityLabel={row.filename || t('bank.evidenceTitle')}
                    onPress={() => onOpenEvidence(row)}
                    style={styles.evidenceRow}
                  >
                    <Ionicons name="document-attach-outline" size={18} color={colors.ink} />
                    <Text style={[styles.evidenceName, align]} numberOfLines={1}>
                      {openingEvidenceId === row.evidence_id
                        ? t('common.loading')
                        : row.filename || row.evidence_id}
                    </Text>
                  </Pressable>
                ))}
              </View>
            ) : null}

            <View style={styles.actionRow}>
              {isDraft ? (
                <PremiumButton
                  label={t('bank.submitDraft')}
                  onPress={onSubmitDraft}
                  busy={submitting}
                  disabled={submitting || withdrawing}
                />
              ) : null}
              {submission?.can_withdraw ? (
                <PremiumButton
                  label={t('bank.withdraw')}
                  onPress={onWithdraw}
                  busy={withdrawing}
                  disabled={submitting || withdrawing}
                />
              ) : null}
              {(isDraft || underReview) && !uploading ? (
                <PremiumButton label={t('bank.attachEvidence')} onPress={onUploadEvidence} />
              ) : null}
              {uploading ? <PremiumButton label={t('bank.uploading')} onPress={() => {}} busy /> : null}
            </View>
          </PastelCard>
        ) : null}

        {/* Document-first: upload certificate, then confirm/correct. One change
            action, and only while a change is actually allowed. */}
        {!formOpen && !underReview && (data.can_submit_new !== false || needsFix) ? (
          <PastelCard tone="cream" style={styles.card}>
            <Text style={[styles.cardTitle, align]}>
              {needsFix
                ? t('bank.correctAndResubmit')
                : hasVerified || hasEffective
                  ? t('bank.changeFormTitle')
                  : t('bank.addFormTitle')}
            </Text>
            <Text style={[styles.body, align]}>
              {needsFix ? t('bank.extraction.correctHint') : t('bank.documentFirstHint')}
            </Text>
            <View style={styles.actionRow}>
              <PremiumButton
                label={uploading ? t('bank.uploading') : t('bank.uploadCertificate')}
                onPress={onUploadEvidence}
                busy={uploading}
                disabled={uploading || submitting || withdrawing}
              />
              <PremiumButton
                label={needsFix ? t('bank.correctAndResubmit') : t('bank.enterManually')}
                onPress={onOpenForm}
                disabled={uploading || submitting || withdrawing}
              />
            </View>
          </PastelCard>
        ) : null}

        {/* Add or change — confirm/correct extracted values or manual entry. */}
        {formOpen ? (
          <PastelCard tone="cream" style={styles.card}>
            <Text style={[styles.cardTitle, align]}>
              {needsFix
                ? t('bank.correctAndResubmit')
                : hasVerified || hasEffective
                  ? t('bank.changeFormTitle')
                  : t('bank.addFormTitle')}
            </Text>
            <Text style={[styles.note, align]}>{t('bank.formHint')}</Text>
            {extractionNote ? <Text style={[styles.body, align]}>{extractionNote}</Text> : null}
            <View style={styles.actionRow}>
              <PremiumButton
                label={uploading ? t('bank.uploading') : t('bank.replaceCertificate')}
                onPress={onUploadEvidence}
                busy={uploading}
                disabled={uploading || submitting || savingDraft}
              />
            </View>
            {BANK_FIELDS.map((field) => (
              <View key={field} style={styles.fieldBlock}>
                <Text style={[styles.fieldLabel, align]}>
                  {t(`bank.field.${field}`)}
                  {field === 'iban' ? ` ${t('bank.orAccountNumber')}` : ''}
                </Text>
                <TextInput
                  style={[
                    styles.input,
                    readingEdgeAlign(isRTL),
                    fieldErrors[field] ? styles.inputError : null,
                  ]}
                  value={form[field] || ''}
                  onChangeText={(value) => onChangeField(field, value)}
                  placeholder={t(`bank.placeholder.${field}`)}
                  placeholderTextColor={colors.subtle}
                  autoCapitalize={field === 'iban' || field === 'swift' ? 'characters' : 'words'}
                  autoCorrect={false}
                  keyboardType={field === 'account_number' ? 'number-pad' : 'default'}
                  accessibilityLabel={t(`bank.field.${field}`)}
                  editable={!submitting && !savingDraft}
                />
                {fieldErrors[field] ? (
                  <Text style={[styles.reasonText, align]} accessibilityLiveRegion="polite">
                    {fieldErrors[field]}
                  </Text>
                ) : null}
              </View>
            ))}
            {requiredMissing ? (
              <Text style={[styles.reasonText, align]}>{t('bank.identifierRequired')}</Text>
            ) : null}
            {formError ? <Text style={[styles.reasonText, align]}>{formError}</Text> : null}
            <View style={styles.actionRow}>
              <PremiumButton
                label={t('bank.submitForReview')}
                onPress={onSubmit}
                busy={submitting}
                disabled={requiredMissing || submitting || savingDraft}
              />
              <PremiumButton
                label={t('bank.saveDraft')}
                onPress={onSaveDraft}
                busy={savingDraft}
                disabled={requiredMissing || submitting || savingDraft}
              />
              <Pressable
                accessibilityRole="button"
                onPress={onCloseForm}
                disabled={submitting || savingDraft}
                style={styles.linkButton}
              >
                <Text style={styles.linkText}>{t('common.cancel')}</Text>
              </Pressable>
            </View>
          </PastelCard>
        ) : null}

        {/* Masking and encryption are reassurance, not a section: footnotes. */}
        <View style={styles.footnotes}>
          <Text style={[styles.note, align]}>{t('bank.maskedNote')}</Text>
          <View style={styles.securityRow}>
            <Ionicons name="lock-closed-outline" size={16} color={colors.success} />
            <Text style={[styles.note, styles.flex, align]}>{t('bank.secureMessage')}</Text>
          </View>
        </View>
      </PageScrollView>
    </PageScreen>
  )
}

/**
 * Two display maps describe the same account when every field the backend chose
 * to expose matches. Only masked/plain values are compared — the app never sees
 * the underlying number, so this is a presentation-level equality, used purely to
 * decide whether a second card would say anything new.
 */
function sameDisplay(a: BankDisplayValues, b: BankDisplayValues): boolean {
  return BANK_FIELDS.every((field) => String(a[field] ?? '') === String(b[field] ?? ''))
}

/**
 * Renders only masked/plain values the backend chose to expose. `<field>_masked`
 * and `<field>_last4` are markers, not user-facing rows.
 */
function FieldList({
  values,
  t,
  align,
}: {
  values: BankDisplayValues
  t: (key: string, vars?: Record<string, string | number>) => string
  align: { textAlign: 'left' | 'right' }
}) {
  const rows = BANK_FIELDS.map((field) => ({ field, value: values[field] })).filter(
    (row) => row.value !== undefined && row.value !== null && row.value !== '',
  )
  if (!rows.length) {
    return <Text style={[styles.body, align]}>{t('bank.noValues')}</Text>
  }
  return (
    <View style={styles.fieldList}>
      {rows.map((row) => (
        <View key={row.field} style={styles.fieldRow}>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.fieldLabel, align]}>
            {t(`bank.field.${row.field}`)}
          </Text>
          <Text
            maxFontSizeMultiplier={typeScaling.body}
            selectable
            style={[styles.fieldValue, align]}
          >
            {String(row.value)}
          </Text>
        </View>
      ))}
    </View>
  )
}

function submissionLabel(
  state: string,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string {
  switch (state) {
    case 'draft':
      return t('bank.state.draft')
    case 'pending_hr':
    case 'pending_review':
      return t('bank.state.pending_hr')
    case 'pending_payroll':
      return t('bank.state.pending_payroll')
    case 'approved':
      return t('bank.state.approved')
    case 'applied':
      return t('bank.state.applied')
    case 'rejected':
      return t('bank.state.rejected')
    case 'needs_correction':
      return t('bank.state.needs_correction')
    case 'withdrawn':
      return t('bank.state.withdrawn')
    default:
      return t('bank.state.none')
  }
}

function nextStepCopy(
  state: string,
  hasVerified: boolean,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string {
  switch (state) {
    case 'draft':
      return t('bank.next.draft')
    case 'pending_hr':
    case 'pending_review':
      return t('bank.next.pending_hr')
    case 'pending_payroll':
      return t('bank.next.pending_payroll')
    case 'approved':
      return t('bank.next.approved')
    case 'applied':
      return t('bank.next.applied')
    case 'rejected':
      return t('bank.next.rejected')
    case 'needs_correction':
      return t('bank.next.needs_correction')
    case 'withdrawn':
      return t('bank.next.withdrawn')
    default:
      return hasVerified ? t('bank.next.noneVerified') : t('bank.next.noneMissing')
  }
}

export function BankLoadingView() {
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.content}>
        <Wordmark compact align="center" />
        <ContentSkeleton />
      </View>
    </SafeAreaView>
  )
}

/** Company opt-out or controlled rollout: explain, then offer a way back. */
export function BankUnavailableView({ onBack }: { onBack: () => void }) {
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  return (
    <SafeAreaView style={[styles.safe, { direction: isRTL ? 'rtl' : 'ltr' }]} edges={['top']}>
      <View style={[styles.content, styles.errorWrap]}>
        <Text style={[styles.cardTitle, align]}>{t('bank.unavailableTitle')}</Text>
        <Text style={[styles.body, align]}>{t('bank.unavailableMessage')}</Text>
        <PremiumButton label={t('common.back')} onPress={onBack} />
      </View>
    </SafeAreaView>
  )
}

export function BankErrorView({ onRetry }: { onRetry: () => void }) {
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  return (
    <SafeAreaView style={[styles.safe, { direction: isRTL ? 'rtl' : 'ltr' }]} edges={['top']}>
      <View style={[styles.content, styles.errorWrap]}>
        <Text style={[styles.cardTitle, align]}>{t('common.error')}</Text>
        <Text style={[styles.body, align]}>{t('error.generic')}</Text>
        <PremiumButton label={t('common.retry')} onPress={onRetry} />
      </View>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  screen: { flex: 1 },
  content: {
    paddingHorizontal: layout.pageMargin,
    paddingTop: layout.pageTop,
    paddingBottom: layout.scrollBottom,
    gap: layout.sectionGap,
  },
  nav: { minHeight: layout.touchTarget, flexDirection: 'row', alignItems: 'center' },
  backButton: {
    width: layout.touchTarget,
    height: layout.touchTarget,
    alignItems: 'center',
    justifyContent: 'center',
  },
  navSpacer: { width: layout.touchTarget },
  hero: { gap: spacing.sm },
  subtitle: { color: colors.subtle, fontSize: font.body, lineHeight: 22 },
  card: { gap: spacing.sm },
  /** A stated fact, not a card: neutral surface, hairline edge, no elevation. */
  statusLine: {
    gap: spacing.xs,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  footnotes: { gap: spacing.xs },
  cardHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: spacing.sm,
    flexWrap: 'wrap',
  },
  cardTitle: { color: colors.ink, fontSize: font.h3, fontWeight: '700' },
  subTitle: { color: colors.text, fontSize: font.small, fontWeight: '700' },
  body: { color: colors.text, fontSize: font.small, lineHeight: 20 },
  note: { color: colors.subtle, fontSize: font.tiny, lineHeight: 16 },
  fieldList: { gap: spacing.xs, marginTop: 4 },
  fieldRow: { gap: 2 },
  fieldLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700' },
  // IBANs and account holders are long: they wrap rather than truncate, and stay
  // selectable so the full value can always be copied.
  fieldValue: { color: colors.ink, fontSize: font.body, fontWeight: '600' },
  fieldBlock: { gap: 4, marginTop: spacing.sm },
  input: {
    minHeight: 48,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    color: colors.ink,
    fontSize: font.body,
  },
  inputError: {
    borderColor: colors.danger,
    borderWidth: 1,
  },
  reasonBox: {
    marginTop: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth * 2,
    borderColor: colors.danger,
    gap: 4,
  },
  reasonTitle: { color: colors.danger, fontSize: font.tiny, fontWeight: '800' },
  reasonText: { color: colors.danger, fontSize: font.small, lineHeight: 18, fontWeight: '600' },
  evidenceList: { gap: spacing.xs, marginTop: spacing.sm },
  evidenceRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, minHeight: 44 },
  evidenceName: { flex: 1, color: colors.ink, fontSize: font.small, fontWeight: '600' },
  actionRow: { gap: spacing.sm, marginTop: spacing.sm },
  linkButton: { minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  linkText: { color: colors.text, fontWeight: '700', textDecorationLine: 'underline' },
  securityRow: { flexDirection: 'row', gap: spacing.sm, alignItems: 'flex-start' },
  flex: { flex: 1 },
  errorWrap: { flex: 1, justifyContent: 'center', gap: spacing.md },
})
