import { useMemo, useState } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'

import type { CandidateReview } from '@hr/api/types'
import type { ResourceState } from '@hr/api/state'
import { hasAnyAllowedAction, visibleActions } from '@hr/api/actions'
import {
  candidateIsTerminal,
  candidateStageTone,
  formatOfferSalary,
  hasRenderableOffer,
  parseCandidateOffer,
} from '@hr/features/recruiting/candidateComposition'
import {
  intakeLabel,
  lifecycleCommunicationLabel,
  lifecycleStageLabel,
  workflowLabel,
} from '@hr/features/recruiting/lifecycle'
import {
  ConfirmationSheet,
  type ConfirmationView,
} from '@hr/components/primitives'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, radius, spacing, typeScaling } from '@/theme'

export type CandidateViewState = ResourceState | 'already_decided'

/**
 * HR Candidate decision detail — cream system, honest stage/offer/CV, SOD confirm.
 */
export function CandidateReviewView({
  review,
  state = 'ready',
  onPrepareDecision,
  onConfirmDecision,
  onScheduleInterview,
  onOpenCV,
  onRetry,
  onBack,
}: {
  review: CandidateReview
  state?: CandidateViewState
  company?: string
  onPrepareDecision?: (action: 'shortlist' | 'reject' | 'hire') => Promise<ConfirmationView>
  onConfirmDecision?: () => Promise<void>
  onScheduleInterview?: () => void
  onOpenCV?: (action: 'preview' | 'download') => void
  onRetry?: () => void
  onLocale?: () => void
  onBack?: () => void
}) {
  const { t, isRTL, locale } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const appLocale = locale === 'ar' ? 'ar' : 'en'
  const [confirmation, setConfirmation] = useState<ConfirmationView | null>(null)
  const [preparing, setPreparing] = useState(false)
  const [confirming, setConfirming] = useState(false)

  const name = review.overview.candidate?.name || t('hrCandidate.title')
  const role = review.overview.position?.title || review.overview.position?.code || '—'
  const stage = review.overview.canonical_stage || review.overview.status
  const latestCommunication = review.communication_status[0]
  const communication =
    review.overview.communication?.status || String(latestCommunication?.status || '')
  const automaticActivity = review.overview.automatic_activity || []
  const waitingForHR = review.overview.waiting_for_hr || []
  const offer = parseCandidateOffer(review.offer)
  const offerCurrent = offer?.current
  const canShortlist = visibleActions(review.allowed_actions, ['shortlist']).length > 0
  const canReject = visibleActions(review.allowed_actions, ['reject']).length > 0
  const canHire = visibleActions(review.allowed_actions, ['hire']).length > 0
  const canSchedule = visibleActions(review.allowed_actions, ['schedule_interview']).length > 0
  const canPreviewCv =
    Boolean(review.cv.available) &&
    hasAnyAllowedAction(review.allowed_actions, ['preview_cv', 'cv_preview', 'preview'])
  const canDownloadCv =
    Boolean(review.cv.available) &&
    hasAnyAllowedAction(review.allowed_actions, ['download_cv', 'cv_download', 'download'])
  const actionable = state === 'ready' && (canShortlist || canReject || canHire || canSchedule)

  const salaryText = useMemo(() => {
    if (!offerCurrent) return null
    if (offerCurrent.compensation_redacted) return t('hrCandidate.offerSalaryRedacted')
    return formatOfferSalary(offerCurrent.currency, offerCurrent.base_salary, false)
  }, [offerCurrent, t])

  const prepare = async (action: 'shortlist' | 'reject' | 'hire') => {
    setPreparing(true)
    try {
      const view = await onPrepareDecision?.(action)
      if (view) setConfirmation(view)
    } finally {
      setPreparing(false)
    }
  }

  const confirm = async () => {
    setConfirming(true)
    try {
      await onConfirmDecision?.()
      setConfirmation(null)
    } finally {
      setConfirming(false)
    }
  }

  const evidenceItems = (items: string[], emptyKey: string) =>
    (items.length ? items : [t(emptyKey)]).map((item, index) => (
      <Text key={`${item}-${index}`} maxFontSizeMultiplier={typeScaling.body} style={[styles.bullet, align]}>
        • {item}
      </Text>
    ))

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl}>
        <HrPushedNav onBack={onBack || (() => undefined)} accessibilityLabel={t('common.back')} />

        <FadeIn style={styles.hero}>
          <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.eyebrow, align]}>
            {t('hrCandidate.eyebrow')}
          </Text>
          <EditorialHeading>{name}</EditorialHeading>
          {stage ? (
            <StatusChip label={lifecycleStageLabel(stage, appLocale)} tone={candidateStageTone(stage)} />
          ) : null}
        </FadeIn>

        {state === 'loading' ? <ListRow title={t('home.dataLoading')} icon="hourglass-outline" /> : null}

        {state === 'permission' ? (
          <ListRow title={t('hrCandidate.permissionTitle')} subtitle={t('hrCandidate.permissionBody')} />
        ) : null}

        {state === 'error' || state === 'offline' ? (
          <ListRow
            title={t('home.dataUnavailable')}
            subtitle={t('home.dataUnavailableHint')}
            emphasis="warning"
            showChevron
            onPress={onRetry}
          />
        ) : null}

        {state === 'already_decided' ? (
          <ListRow
            title={t('hrCandidate.alreadyDecided')}
            subtitle={t('hrCandidate.alreadyDecidedBody')}
            icon="checkmark-done-outline"
          />
        ) : null}

        {state === 'success' ? (
          <ListRow
            title={t('hrCandidate.successTitle')}
            subtitle={t('hrCandidate.successBody')}
            icon="checkmark-circle-outline"
          />
        ) : null}

        {state === 'stale' ? (
          <ListRow
            title={t('hrCandidate.staleTitle')}
            subtitle={t('hrCandidate.staleBody')}
            emphasis="warning"
            showChevron
            onPress={onRetry}
          />
        ) : null}

        {state === 'revoked' ? (
          <ListRow
            title={t('hrCandidate.revokedTitle')}
            subtitle={t('hrCandidate.revokedBody')}
            emphasis="warning"
          />
        ) : null}

        {(state === 'ready' || state === 'already_decided') && review.app_key ? (
          <>
            <View style={styles.section}>
              <SectionHeader title={t('hrCandidate.sectionRequest')} />
              <Fact label={t('hrCandidate.stage')} value={lifecycleStageLabel(stage, appLocale)} />
              <Fact label={t('hrCandidate.position')} value={role} />
              <Fact
                label={t('hrCandidate.entryMethod')}
                value={intakeLabel(review.overview.intake_source, appLocale)}
              />
              {review.overview.candidate?.email ? (
                <Fact label={t('common.email')} value={review.overview.candidate.email} />
              ) : null}
              <Fact
                label={t('hrCandidate.communication')}
                value={lifecycleCommunicationLabel(communication, appLocale)}
              />
              <Fact
                label={t('hrCandidate.score')}
                value={
                  review.ranking.score == null
                    ? t('hrCandidate.scoreUnavailable')
                    : `${review.ranking.score}/100`
                }
              />
              <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.observeNote, align]}>
                {t('hrCandidate.advisory')}
              </Text>
            </View>

            {review.overview.communication?.stage_changed_without_contact ? (
              <View style={styles.callout}>
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.calloutBody, align]}>
                  {t('hrCandidate.notInformed')}
                </Text>
              </View>
            ) : null}

            <View style={styles.section}>
              <SectionHeader title={t('hrCandidate.automaticActions')} />
              {(automaticActivity.length ? automaticActivity : [null]).map((item, index) => (
                <Text
                  key={item || index}
                  maxFontSizeMultiplier={typeScaling.body}
                  style={[styles.bullet, align]}
                >
                  • {item ? workflowLabel(item, appLocale) : t('hrCandidate.noAutomaticActions')}
                </Text>
              ))}
            </View>

            <View style={styles.section}>
              <SectionHeader title={t('hrCandidate.waitingForHR')} />
              {(waitingForHR.length ? waitingForHR : [null]).map((item, index) => (
                <Text
                  key={item || index}
                  maxFontSizeMultiplier={typeScaling.body}
                  style={[styles.bullet, align]}
                >
                  • {item ? workflowLabel(item, appLocale) : t('hrCandidate.noPendingHR')}
                </Text>
              ))}
            </View>

            <View style={styles.section}>
              <SectionHeader title={t('hrCandidate.sectionEvidence')} />
              <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.subhead, align]}>
                {t('hrCandidate.evidence')}
              </Text>
              {evidenceItems(review.ranking.evidence, 'hrCandidate.noEvidence')}
              <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.subhead, align]}>
                {t('hrCandidate.interpretation')}
              </Text>
              {evidenceItems(review.ranking.reasons, 'hrCandidate.noEvidence')}
              <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.subhead, align]}>
                {t('hrCandidate.concerns')}
              </Text>
              {evidenceItems(review.ranking.concerns, 'hrCandidate.noEvidence')}
              <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.subhead, align]}>
                {t('hrCandidate.missing')}
              </Text>
              {evidenceItems(review.ranking.missing_evidence, 'hrCandidate.noEvidence')}
              <Fact
                label={t('hrCandidate.confidence')}
                value={String(review.ranking.confidence || t('common.none'))}
              />
            </View>

            <View style={styles.section}>
              <SectionHeader title={t('hrCandidate.cv')} />
              <Fact
                label={t('hrCandidate.cv')}
                value={review.cv.filename || t('hrCandidate.cvUnavailable')}
              />
              {(canPreviewCv || canDownloadCv) && (
                <View style={[styles.actions, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
                  {canPreviewCv ? (
                    <Pressable
                      onPress={() => onOpenCV?.('preview')}
                      style={[styles.btn, styles.btnQuiet]}
                      accessibilityRole="button"
                      accessibilityLabel={t('hrCandidate.previewCV')}
                    >
                      <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.btnQuietText}>
                        {t('hrCandidate.previewCV')}
                      </Text>
                    </Pressable>
                  ) : null}
                  {canDownloadCv ? (
                    <Pressable
                      onPress={() => onOpenCV?.('download')}
                      style={[styles.btn, styles.btnQuiet]}
                      accessibilityRole="button"
                      accessibilityLabel={t('hrCandidate.downloadCV')}
                    >
                      <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.btnQuietText}>
                        {t('hrCandidate.downloadCV')}
                      </Text>
                    </Pressable>
                  ) : null}
                </View>
              )}
            </View>

            {hasRenderableOffer(review.offer) ? (
              <View style={styles.section}>
                <SectionHeader title={t('hrCandidate.sectionOffer')} />
                <Fact
                  label={t('hrCandidate.offerStatus')}
                  value={String(offerCurrent?.status_label || offerCurrent?.status || '—')}
                />
                <Fact
                  label={t('hrCandidate.offerRole')}
                  value={String(offerCurrent?.position_title || offerCurrent?.position_code || role)}
                />
                {salaryText ? <Fact label={t('hrCandidate.offerSalary')} value={salaryText} /> : null}
                {offerCurrent?.proposed_start_date ? (
                  <Fact label={t('hrCandidate.offerStart')} value={String(offerCurrent.proposed_start_date)} />
                ) : null}
              </View>
            ) : null}

            {review.interview ? (
              <View style={styles.section}>
                <SectionHeader title={t('hrCandidate.interview')} />
                <Fact
                  label={t('hrCandidate.interview')}
                  value={String(review.interview.status || t('hrCandidate.interviewScheduled'))}
                />
                {review.interview.notes ? (
                  <Fact label={t('hrCandidate.interviewNotes')} value={String(review.interview.notes)} />
                ) : null}
              </View>
            ) : null}

            {actionable ? (
              <View style={styles.section}>
                <SectionHeader title={t('hrCandidate.sectionDecide')} />
                {canShortlist ? (
                  <Pressable
                    onPress={() => void prepare('shortlist')}
                    disabled={preparing}
                    style={[styles.btn, styles.btnQuiet, preparing && styles.btnDisabled]}
                    accessibilityRole="button"
                    accessibilityLabel={t('hrCandidate.shortlist')}
                  >
                    <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.btnQuietText}>
                      {preparing ? t('common.loading') : t('hrCandidate.shortlist')}
                    </Text>
                  </Pressable>
                ) : null}
                <View style={[styles.actions, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
                  {canReject ? (
                    <Pressable
                      onPress={() => void prepare('reject')}
                      disabled={preparing}
                      style={[styles.btn, styles.btnQuiet, preparing && styles.btnDisabled]}
                      accessibilityRole="button"
                      accessibilityLabel={t('hrCandidate.reject')}
                    >
                      <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.btnQuietText}>
                        {preparing ? t('common.loading') : t('hrCandidate.reject')}
                      </Text>
                    </Pressable>
                  ) : null}
                  {canHire ? (
                    <Pressable
                      onPress={() => void prepare('hire')}
                      disabled={preparing}
                      style={[styles.btn, styles.btnPrimary, preparing && styles.btnDisabled]}
                      accessibilityRole="button"
                      accessibilityLabel={t('hrCandidate.hire')}
                    >
                      <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.btnPrimaryText}>
                        {preparing ? t('common.loading') : t('hrCandidate.hire')}
                      </Text>
                    </Pressable>
                  ) : null}
                </View>
                {canSchedule ? (
                  <Pressable
                    onPress={onScheduleInterview}
                    style={[styles.btn, styles.btnQuiet]}
                    accessibilityRole="button"
                    accessibilityLabel={t('hrCandidate.scheduleInterview')}
                  >
                    <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.btnQuietText}>
                      {t('hrCandidate.scheduleInterview')}
                    </Text>
                  </Pressable>
                ) : null}
              </View>
            ) : state === 'ready' && !candidateIsTerminal(stage) ? (
              <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.bullet, align]}>
                {t('hrCandidate.noActions')}
              </Text>
            ) : null}
          </>
        ) : null}

        <ConfirmationSheet
          visible={Boolean(confirmation)}
          value={confirmation}
          onCancel={() => setConfirmation(null)}
          onConfirm={() => void confirm()}
          loading={confirming}
        />
      </PageScrollView>
    </PageScreen>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  const { isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  return (
    <View style={styles.fact}>
      <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.factLabel, align]}>
        {label}
      </Text>
      <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.factValue, align]}>
        {value}
      </Text>
    </View>
  )
}

const styles = StyleSheet.create({
  hero: { gap: spacing.sm },
  eyebrow: {
    color: colors.subtle,
    fontSize: font.tiny,
    fontWeight: '700',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  section: { gap: spacing.sm },
  fact: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    gap: 4,
  },
  factLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700' },
  factValue: { color: colors.ink, fontSize: font.body, lineHeight: 22 },
  callout: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.warning,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  calloutBody: { color: colors.ink, fontSize: font.body, lineHeight: 22, fontWeight: '600' },
  observeNote: { color: colors.subtle, fontSize: font.tiny, lineHeight: 18 },
  subhead: { color: colors.subtle, fontSize: font.tiny, fontWeight: '700', marginTop: spacing.sm },
  bullet: { color: colors.ink, fontSize: font.body, lineHeight: 22 },
  actions: { gap: spacing.sm },
  btn: {
    flex: 1,
    minHeight: 48,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
  },
  btnPrimary: { backgroundColor: colors.ink },
  btnPrimaryText: { color: colors.bg, fontWeight: '700', fontSize: font.small },
  btnQuiet: {
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  btnQuietText: { color: colors.ink, fontWeight: '700', fontSize: font.small },
  btnDisabled: { opacity: 0.45 },
})
