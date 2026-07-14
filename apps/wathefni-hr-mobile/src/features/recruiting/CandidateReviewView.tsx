import { useState } from 'react'
import { StyleSheet, Text, View } from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'

import type { CandidateReview } from '@/api/types'
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
  StatePanel,
  StatusBadge,
  WorkspaceHeader,
  type ConfirmationView,
} from '@/components/primitives'
import { colors, spacing, type as typography } from '@/theme'

export type CandidateViewState = 'ready' | 'loading' | 'error' | 'revoked' | 'stale' | 'success'

export function CandidateReviewView({
  review,
  company = 'WATHEFNI',
  state = 'ready',
  onPrepareDecision,
  onConfirmDecision,
  onOpenCV,
  onRetry,
  onLocale,
}: {
  review: CandidateReview
  company?: string
  state?: CandidateViewState
  onPrepareDecision?: (action: 'shortlist' | 'reject' | 'hire') => Promise<ConfirmationView>
  onConfirmDecision?: () => Promise<void>
  onOpenCV?: () => void
  onRetry?: () => void
  onLocale?: () => void
}) {
  const { t, isRTL } = useLocale()
  const [confirmation, setConfirmation] = useState<ConfirmationView | null>(null)
  const [preparing, setPreparing] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const name = review.overview.candidate?.name || 'Candidate'
  const role = review.overview.position?.title || review.overview.position?.code || 'Role'

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
      ) : state === 'error' ? (
        <StatePanel title={t('state.errorTitle')} body={t('state.errorBody')} action={t('common.retry')} onAction={onRetry} icon="alert-circle-outline" />
      ) : state === 'revoked' ? (
        <StatePanel title={t('state.revokedTitle')} body={t('state.revokedBody')} action={t('common.retry')} onAction={onRetry} icon="lock-closed-outline" />
      ) : state === 'stale' ? (
        <StatePanel title={t('state.staleTitle')} body={t('state.staleBody')} action={t('common.retry')} onAction={onRetry} icon="refresh-circle-outline" />
      ) : state === 'success' ? (
        <StatePanel title={t('state.successTitle')} body={t('state.successBody')} icon="checkmark-done-circle-outline" />
      ) : (
        <>
          <Card tone="cream">
            <View style={[styles.topRow, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
              <StatusBadge label={review.overview.status || 'review pending'} tone="info" />
              <Text style={styles.appKey}>#{review.app_key.slice(0, 8)}</Text>
            </View>
            <IdentityRow name={name} subtitle={role} meta={review.overview.candidate?.email} />
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

          <EvidenceCard title={t('candidate.evidence')} items={review.ranking.evidence.length ? review.ranking.evidence : review.ranking.reasons} tone="evidence" icon="checkmark-circle-outline" />
          <EvidenceCard title={t('candidate.concerns')} items={review.ranking.concerns.length ? review.ranking.concerns : [t('candidate.noEvidence')]} tone="concern" icon="alert-circle-outline" />
          <EvidenceCard title={t('candidate.missing')} items={review.ranking.missing_evidence.length ? review.ranking.missing_evidence : [t('candidate.noEvidence')]} tone="missing" icon="help-circle-outline" />

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
              {review.cv.available ? (
                <ActionButton label={t('common.view')} tone="secondary" onPress={onOpenCV} />
              ) : null}
            </View>
          </Card>

          {review.interview ? (
            <Card tone="lilac">
              <Fact title="Interview" value={String(review.interview.status || 'Scheduled')} />
              <Fact title="Notes" value={String(review.interview.notes || 'No notes yet.')} />
            </Card>
          ) : null}

          <View style={styles.actions}>
            {review.allowed_actions.includes('shortlist') ? (
              <ActionButton label={t('candidate.shortlist')} tone="secondary" loading={preparing} onPress={() => void prepare('shortlist')} />
            ) : null}
            <View style={[styles.decisionRow, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
              {review.allowed_actions.includes('reject') ? (
                <View style={styles.flex}>
                  <ActionButton label={t('candidate.reject')} tone="secondary" loading={preparing} onPress={() => void prepare('reject')} />
                </View>
              ) : null}
              {review.allowed_actions.includes('hire') ? (
                <View style={styles.flex}>
                  <ActionButton label={t('candidate.hire')} loading={preparing} onPress={() => void prepare('hire')} />
                </View>
              ) : null}
            </View>
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
  cvTitle: { color: colors.ink, fontSize: typography.body, fontWeight: '800' },
  cvMeta: { color: colors.muted, fontSize: typography.label },
  fact: { gap: spacing.xs },
  factTitle: { color: colors.muted, fontSize: typography.label, fontWeight: '800' },
  factValue: { color: colors.ink, fontSize: typography.body, lineHeight: 22 },
  actions: { gap: spacing.md },
  decisionRow: { gap: spacing.md },
  flex: { flex: 1 },
})
