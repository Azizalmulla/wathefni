import { useState } from 'react'
import { Text } from 'react-native'
import { useLocalSearchParams } from 'expo-router'

import { useAuth } from '@/auth/AuthProvider'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, PageBackButton, QuietEmpty } from '@/components/lists'
import { EditorialHeading, PremiumButton } from '@/components/premium'
import { ErrorState, LoadingState } from '@/components/States'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'
import { colors, font, spacing, typeScaling } from '@/theme'

type Payload = {
  resource_state?: string
  plan?: { title_en?: string; title_ar?: string; code?: string; effective_version?: number; description_en?: string; description_ar?: string }
  enrollments?: Array<{ enrollment_id?: string; status?: string; elected?: boolean; waived?: boolean; coverage_active?: boolean }>
  coverage?: Array<{ coverage_id?: string; start_date?: string; end_date?: string; status?: string; provider_confirmed?: boolean; plan_version?: number }>
  contributions?: Array<{ contribution_id?: string; kind?: string; mode?: string; amount?: number; percent?: number; currency?: string }>
  member_refs?: Array<{ member_ref_id?: string; provider_status_confirmed?: boolean }>
  dependents?: Array<{ dependent_id?: string; name_en?: string; name_ar?: string; relationship?: string; exists?: boolean; covered?: boolean }>
  latest_eligible?: boolean
}

export default function BenefitsPlanScreen() {
  const { hasFeature, can, request } = useAuth()
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const params = useLocalSearchParams<{ plan_id?: string }>()
  const planId = String(params.plan_id || '')
  const enabled = hasFeature('benefits')
  const query = useAppQuery<Payload>(['benefits', 'plan', planId], `/app/benefits/plans/${planId}`, {
    enabled: enabled && Boolean(planId),
    staleTime: HIGH_CHURN_STALE_MS,
  })
  const [busy, setBusy] = useState(false)

  if (!enabled) return <FeatureUnavailableState feature="benefits" />
  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  }
  if (query.data?.resource_state === 'unavailable') {
    return <FeatureUnavailableState feature="benefits" />
  }

  const plan = query.data?.plan
  const title = isRTL ? plan?.title_ar || plan?.title_en || t('benefits.plan') : plan?.title_en || plan?.title_ar || t('benefits.plan')
  const enrollment = (query.data?.enrollments || [])[0]
  const coverage = query.data?.coverage || []
  const contribs = query.data?.contributions || []
  const members = query.data?.member_refs || []
  const dependents = query.data?.dependents || []
  const canAct =
    !enrollment?.coverage_active &&
    !enrollment?.elected &&
    !enrollment?.waived &&
    (enrollment?.status === 'enrollment_open' || enrollment?.status === 'eligible' || !enrollment)
  const submit = (waive: boolean) => {
    setBusy(true)
    void request('/app/benefits/elections', {
      method: 'POST',
      json: {
        plan_id: planId,
        enrollment_id: enrollment?.enrollment_id,
        waive,
        tier: waive ? undefined : 'employee_only',
        reason: waive ? 'employee waive' : 'employee elect',
      },
    })
      .then(() => query.refetch())
      .finally(() => setBusy(false))
  }

  return (
    <PageScreen>
      <PageScrollView>
        <PageBackButton />
        <EditorialHeading>{title}</EditorialHeading>
        <Text maxFontSizeMultiplier={typeScaling.body} style={[{ marginTop: spacing.sm, color: colors.textSecondary, fontSize: font.body }, align]}>
          {[plan?.code, plan?.effective_version != null ? `${t('benefits.version')} ${plan.effective_version}` : '']
            .filter(Boolean)
            .join(' · ')}
        </Text>
        {query.data?.latest_eligible === false ? (
          <ListRow title={t('benefits.notEligible')} subtitle={t('benefits.boundaries')} />
        ) : null}
        {enrollment ? (
          <ListRow
            title={
              enrollment.coverage_active
                ? t('benefits.coverageActive')
                : enrollment.waived
                  ? t('benefits.waived')
                  : enrollment.elected
                    ? t('benefits.enrolled')
                    : String(enrollment.status || '')
            }
          />
        ) : null}
        {coverage.length === 0 ? <QuietEmpty title={t('benefits.emptyCoverage')} /> : null}
        {coverage.map((row) => (
          <ListRow
            key={String(row.coverage_id)}
            title={t('benefits.coverage')}
            subtitle={[
              row.start_date ? `${t('benefits.effectiveFrom')} ${row.start_date}` : '',
              row.end_date ? `${t('benefits.effectiveUntil')} ${row.end_date}` : '',
              row.provider_confirmed ? t('benefits.providerConfirmed') : t('benefits.internalOnly'),
            ]
              .filter(Boolean)
              .join(' · ')}
          />
        ))}
        {contribs.map((row) => (
          <ListRow
            key={String(row.contribution_id)}
            title={row.kind === 'employer' ? t('benefits.employerShare') : t('benefits.employeeShare')}
            subtitle={`${row.amount ?? row.percent ?? '—'} ${row.currency || ''} · ${t('benefits.notDeduction')}`}
          />
        ))}
        {members.map((row) => (
          <ListRow
            key={String(row.member_ref_id)}
            title={t('benefits.provider')}
            subtitle={row.provider_status_confirmed ? t('benefits.providerConfirmed') : t('benefits.internalOnly')}
          />
        ))}
        {dependents.length === 0 ? <QuietEmpty title={t('benefits.emptyDependents')} /> : null}
        {dependents.map((row) => (
          <ListRow
            key={String(row.dependent_id)}
            title={isRTL ? row.name_ar || row.name_en || '' : row.name_en || row.name_ar || ''}
            subtitle={[
              row.relationship,
              row.covered ? t('benefits.dependentCovered') : t('benefits.dependentNotCovered'),
            ]
              .filter(Boolean)
              .join(' · ')}
          />
        ))}
        {canAct && can('benefits', 'enroll') ? (
          <PremiumButton label={t('benefits.enroll')} disabled={busy} onPress={() => submit(false)} />
        ) : null}
        {canAct && can('benefits', 'waive') ? (
          <PremiumButton label={t('benefits.waive')} disabled={busy} onPress={() => submit(true)} />
        ) : null}
        <Text maxFontSizeMultiplier={typeScaling.body} style={[{ marginTop: spacing.lg, color: colors.textSecondary, fontSize: font.caption }, align]}>
          {t('benefits.boundaries')}
        </Text>
      </PageScrollView>
    </PageScreen>
  )
}
