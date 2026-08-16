import { useState } from 'react'
import { StyleSheet, Text, View } from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'

import type { CandidateReview } from '@/api/types'
import type { ResourceState } from '@/api/state'
import { hasAnyAllowedAction, visibleActions } from '@/api/actions'
import { ResourcePanel } from '@/features/operations/OperationalViews'
import { useLocale } from '@/i18n'
import {
  ActionButton,
  Card,
  ConfirmationSheet,
  EditorialHeading,
  EvidenceCard,
  IdentityRow,
  Screen,
  Skeleton,
  StatusBadge,
  WorkspaceHeader,
  type ConfirmationView,
} from '@/components/primitives'
import { colors, spacing, type as typography } from '@/theme'
import {
  intakeLabel,
  lifecycleCommunicationLabel,
  lifecycleStageLabel,
  workflowLabel,
} from '@/features/recruiting/lifecycle'

export type CandidateViewState = ResourceState

export function CandidateReviewView({
  review,
  company = 'WATHEFNI',
  state = 'ready',
  onPrepareDecision,
  onConfirmDecision,
  onScheduleInterview,
  onOpenCV,
  onRetry,
  onLocale,
}: {
  review: CandidateReview
  company?: string
  state?: CandidateViewState
  onPrepareDecision?: (action: 'shortlist' | 'reject' | 'hire') => Promise<ConfirmationView>
  onConfirmDecision?: () => Promise<void>
  onScheduleInterview?: () => void
  onOpenCV?: (action: 'preview' | 'download') => void
  onRetry?: () => void
  onLocale?: () => void
}) {
  const { t, isRTL, locale } = useLocale()
  const [confirmation, setConfirmation] = useState<ConfirmationView | null>(null)
  const [preparing, setPreparing] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const name = review.overview.candidate?.name || 'Candidate'
  const role = review.overview.position?.title || review.overview.position?.code || 'Role'
  const stage = review.overview.canonical_stage || review.overview.status
  const latestCommunication = review.communication_status[0]
  const communication = review.overview.communication?.status || String(latestCommunication?.status || '')
  const automaticActivity = review.overview.automatic_activity || []
  const waitingForHR = review.overview.waiting_for_hr || []

  const prepare = async (action: 'shortlist' | 'reject' | 'hire') => {
    setPreparing(true)
    try {
      const labels = {
        shortlist: t('candidate.shortlist'),
        reject: t('candidate.reject'),
        hire: t('candidate.hire'),
      }
      const fallback: ConfirmationView = {
        target: `${name} · ${role}`,
        action: labels[action],
        consequence:
          action === 'hire'
            ? `Hire ${name}. This creates an employee record and starts post-hire setup.`
            : action === 'reject'
              ? `Reject ${name} and remove this application from the active pipeline.`
              : `Move ${name} to the shortlist for ${role}.`,
        currentState: review.overview.status || 'review_pending',
      }
      setConfirmation((await onPrepareDecision?.(action)) || fallback)
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

  return (
    <Screen>
      <WorkspaceHeader company={company} onLocale={onLocale} />
      <EditorialHeading eyebrow={t('candidate.eyebrow')}>{t('candidate.title')}</EditorialHeading>
      {state === 'loading' ? (
        <View style={styles.stack}>
          <Skeleton lines={4} />
          <Skeleton lines={5} />
          <Skeleton lines={3} />
        </View>
      ) : state !== 'ready' ? (
        <ResourcePanel state={state} onRetry={onRetry} />
      ) : (
        <>
          <Card tone="cream">
            <View style={[styles.topRow, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
              <StatusBadge
                label={lifecycleStageLabel(stage, locale)}
                tone="info"
              />
              <Text style={styles.appKey}>#{review.app_key.slice(0, 8)}</Text>
            </View>
            <IdentityRow name={name} subtitle={role} meta={review.overview.candidate?.email} />
            <View style={styles.rule} />
            <Fact title={t('candidate.applicationStage')} value={lifecycleStageLabel(stage, locale)} />
            <Fact title={t('common.position')} value={role} />
            <Fact title={t('candidate.entryMethod')} value={intakeLabel(review.overview.intake_source, locale)} />
            {review.overview.candidate?.email ? (
              <Fact title={t('common.email')} value={review.overview.candidate.email} />
            ) : null}
            <Fact title={t('candidate.communication')} value={lifecycleCommunicationLabel(communication, locale)} />
            <View style={[styles.scoreWrap, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
              <View style={styles.scoreRing}>
                <Text style={styles.score}>{review.ranking.score ?? '—'}</Text>
                <Text style={styles.scoreSuffix}>/100</Text>
              </View>
              <View style={styles.scoreText}>
                <Text style={[styles.scoreLabel, { textAlign: isRTL ? 'right' : 'left' }]}>{t('candidate.score')}</Text>
                <Text style={[styles.advisory, { textAlign: isRTL ? 'right' : 'left' }]}>{t('candidate.advisory')}</Text>
              </View>
            </View>
          </Card>

          {review.overview.communication?.stage_changed_without_contact ? (
            <Card tone="amber">
              <View style={[styles.alertRow, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
                <Ionicons name="alert-circle-outline" size={22} color={colors.ink} />
                <Text style={[styles.alertText, { textAlign: isRTL ? 'right' : 'left' }]}>{t('candidate.notInformed')}</Text>
              </View>
            </Card>
          ) : null}

          <Card tone="sage">
            <Text style={[styles.sectionTitle, { textAlign: isRTL ? 'right' : 'left' }]}>{t('candidate.automaticActions')}</Text>
            {(automaticActivity.length ? automaticActivity : [null]).map((item, index) => (
              <Text key={item || index} style={[styles.sectionLine, { textAlign: isRTL ? 'right' : 'left' }]}>
                {item ? `• ${workflowLabel(item, locale)}` : t('candidate.noAutomaticActions')}
              </Text>
            ))}
          </Card>

          <Card tone="cream">
            <Text style={[styles.sectionTitle, { textAlign: isRTL ? 'right' : 'left' }]}>{t('candidate.waitingForHR')}</Text>
            {(waitingForHR.length ? waitingForHR : [null]).map((item, index) => (
              <Text key={item || index} style={[styles.sectionLine, { textAlign: isRTL ? 'right' : 'left' }]}>
                {item ? `• ${workflowLabel(item, locale)}` : t('candidate.noPendingHR')}
              </Text>
            ))}
          </Card>

          <EvidenceCard title={t('candidate.evidence')} items={review.ranking.evidence.length ? review.ranking.evidence : [t('candidate.noEvidence')]} tone="evidence" icon="document-text-outline" />
          <EvidenceCard
            title={t('candidate.interpretation')}
            items={review.ranking.reasons.length ? review.ranking.reasons : [t('candidate.noEvidence')]}
            tone="missing"
            icon="analytics-outline"
          />
          <EvidenceCard title={t('candidate.concerns')} items={review.ranking.concerns.length ? review.ranking.concerns : [t('candidate.noEvidence')]} tone="concern" icon="alert-circle-outline" />
          <EvidenceCard title={t('candidate.missing')} items={review.ranking.missing_evidence.length ? review.ranking.missing_evidence : [t('candidate.noEvidence')]} tone="missing" icon="help-circle-outline" />
          <Card tone="lilac">
            <Fact title={t('candidate.confidence')} value={String(review.ranking.confidence || t('common.none'))} />
            <Text style={[styles.advisory, { textAlign: isRTL ? 'right' : 'left' }]}>{t('candidate.advisory')}</Text>
          </Card>

          <Card tone="sky">
            <View style={[styles.cvRow, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
              <View style={styles.cvIcon}>
                <Ionicons name="document-text-outline" size={22} color={colors.sky} />
              </View>
              <View style={styles.cvText}>
                <Text style={[styles.cvTitle, { textAlign: isRTL ? 'right' : 'left' }]}>{t('candidate.cv')}</Text>
                <Text style={[styles.cvMeta, { textAlign: isRTL ? 'right' : 'left' }]}>
                  {review.cv.filename || 'No CV available'}
                </Text>
              </View>
              <View style={styles.cvActions}>
                {review.cv.available && hasAnyAllowedAction(review.allowed_actions, ['preview_cv', 'cv_preview', 'preview']) ? (
                  <ActionButton label={t('candidate.previewCV')} tone="secondary" onPress={() => onOpenCV?.('preview')} />
                ) : null}
                {review.cv.available && hasAnyAllowedAction(review.allowed_actions, ['download_cv', 'cv_download', 'download']) ? (
                  <ActionButton label={t('candidate.downloadCV')} tone="secondary" onPress={() => onOpenCV?.('download')} />
                ) : null}
              </View>
            </View>
          </Card>

          {review.interview ? (
            <Card tone="lilac">
              <Fact title={t('interviews.detailTitle')} value={String(review.interview.status || t('interviews.scheduled'))} />
              <Fact title={t('interviews.notes')} value={String(review.interview.notes || t('common.none'))} />
            </Card>
          ) : null}

          {review.communication_status.length ? (
            <Card tone="sky">
              <Text style={[styles.communicationTitle, { textAlign: isRTL ? 'right' : 'left' }]}>
                {t('interviews.delivery')}
              </Text>
              {review.communication_status.map((entry, index) => (
                <Fact
                  key={index}
                  title={String(entry.message_kind || entry.channel || t('interviews.delivery'))}
                  value={lifecycleCommunicationLabel(String(entry.status || ''), locale)}
                />
              ))}
            </Card>
          ) : null}

          <View style={styles.actions}>
            <Text style={[styles.sectionTitle, { textAlign: isRTL ? 'right' : 'left' }]}>{t('candidate.nextActions')}</Text>
            {visibleActions(review.allowed_actions, ['shortlist']).length ? (
              <ActionButton label={t('candidate.shortlist')} tone="secondary" loading={preparing} onPress={() => void prepare('shortlist')} />
            ) : null}
            <View style={[styles.decisionRow, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
              {visibleActions(review.allowed_actions, ['reject']).length ? (
                <View style={styles.flex}>
                  <ActionButton label={t('candidate.reject')} tone="secondary" loading={preparing} onPress={() => void prepare('reject')} />
                </View>
              ) : null}
              {visibleActions(review.allowed_actions, ['hire']).length ? (
                <View style={styles.flex}>
                  <ActionButton label={t('candidate.hire')} loading={preparing} onPress={() => void prepare('hire')} />
                </View>
              ) : null}
            </View>
            {visibleActions(review.allowed_actions, ['schedule_interview']).length ? (
              <>
                <ActionButton label={t('candidate.viewInterviews')} tone="secondary" onPress={onScheduleInterview} />
                <Text style={[styles.sectionLine, { textAlign: isRTL ? 'right' : 'left' }]}>
                  {t('candidate.scheduleOnWeb')}
                </Text>
              </>
            ) : null}
            {!visibleActions(review.allowed_actions, ['shortlist', 'reject', 'hire', 'schedule_interview']).length ? (
              <Text style={[styles.sectionLine, { textAlign: isRTL ? 'right' : 'left' }]}>{t('candidate.noActions')}</Text>
            ) : null}
          </View>
        </>
      )}
      <ConfirmationSheet
        visible={Boolean(confirmation)}
        value={confirmation}
        onCancel={() => setConfirmation(null)}
        onConfirm={() => void confirm()}
        loading={confirming}
      />
    </Screen>
  )
}

function Fact({ title, value }: { title: string; value: string }) {
  const { isRTL } = useLocale()
  return (
    <View style={styles.fact}>
      <Text style={[styles.factTitle, { textAlign: isRTL ? 'right' : 'left' }]}>{title}</Text>
      <Text style={[styles.factValue, { textAlign: isRTL ? 'right' : 'left' }]}>{value}</Text>
    </View>
  )
}

const styles = StyleSheet.create({
  stack: { gap: spacing.xl },
  topRow: { justifyContent: 'space-between', alignItems: 'center' },
  rule: { height: 1, backgroundColor: colors.line },
  appKey: { color: colors.faint, fontSize: typography.micro, fontWeight: '700' },
  scoreWrap: { alignItems: 'center', gap: spacing.lg, paddingTop: spacing.sm },
  scoreRing: { width: 84, height: 84, borderRadius: 42, backgroundColor: colors.plumSoft, borderWidth: 5, borderColor: colors.plum, alignItems: 'center', justifyContent: 'center' },
  score: { color: colors.plum, fontSize: 28, fontWeight: '900', letterSpacing: -0.8 },
  scoreSuffix: { color: colors.plum, fontSize: typography.micro, fontWeight: '800' },
  scoreText: { flex: 1, gap: spacing.xs },
  scoreLabel: { color: colors.ink, fontSize: typography.section, fontWeight: '800' },
  advisory: { color: colors.muted, fontSize: typography.label, lineHeight: 19 },
  cvRow: { alignItems: 'center', gap: spacing.md },
  cvIcon: { width: 46, height: 46, borderRadius: 16, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
  cvText: { flex: 1, gap: 3 },
  cvActions: { gap: spacing.sm },
  cvTitle: { color: colors.ink, fontSize: typography.body, fontWeight: '800' },
  cvMeta: { color: colors.muted, fontSize: typography.label },
  fact: { gap: spacing.xs },
  factTitle: { color: colors.muted, fontSize: typography.label, fontWeight: '800' },
  factValue: { color: colors.ink, fontSize: typography.body, lineHeight: 22 },
  communicationTitle: { color: colors.ink, fontSize: typography.section, fontWeight: '800' },
  sectionTitle: { color: colors.ink, fontSize: typography.section, fontWeight: '800' },
  sectionLine: { color: colors.muted, fontSize: typography.body, lineHeight: 22 },
  alertRow: { alignItems: 'center', gap: spacing.sm },
  alertText: { flex: 1, color: colors.ink, fontSize: typography.body, fontWeight: '800', lineHeight: 22 },
  actions: { gap: spacing.md },
  decisionRow: { gap: spacing.md },
  flex: { flex: 1 },
})
