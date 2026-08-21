import { Profiler as ReactProfiler, useCallback, useState } from 'react'
import { Loader2, Search } from 'lucide-react'

import { rankingComponentRows, rankingDecisionFor, rankingScoreLabel } from '@/lib/rankingPresentation'
import {
  rankingAssessmentEvidenceEnabled,
  rankingCopy,
  rankingEligibilityLabel,
  rankingEligibleCount,
  rankingExcludedCount,
  rankingMatchingCount,
  rankingRankableCount,
} from '@/lib/rankingQueueContract'
import {
  dashboardPerfMarkInteractionStart,
  dashboardPerfMarkNetworkComplete,
  dashboardPerfMarkProfilerCommit,
} from '@/lib/perf/dashboardPerf'
import { type RecruitingLocale } from '@/lib/recruitingLifecycle'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { EmptyState, ScoreBreakdown } from '@/pages/shared/primitives'
import { ResourceState } from '@/pages/shared/dataState'
import { stageLabel } from '@/pages/shared/format'
import type { ApplicationSummary, PositionSummary, RankingCandidate, RankingResponse } from '@/types'

function RankingProfiler({ id, children }: { id: string; children: React.ReactNode }) {
  const onRender = useCallback(
    (
      profilerId: string,
      phase: 'mount' | 'update' | 'nested-update',
      actualDuration: number,
      baseDuration: number,
    ) => {
      dashboardPerfMarkProfilerCommit(`ranking:${profilerId}`, {
        phase,
        actualDurationMs: Math.round(actualDuration),
        baseDurationMs: Math.round(baseDuration),
      })
    },
    [],
  )
  return (
    <ReactProfiler id={id} onRender={onRender}>
      {children}
    </ReactProfiler>
  )
}

export function RankingPage({
  busy,
  locale,
  onSelect,
  positions,
  rankPosition,
  ranking,
  rankingError = false,
  runRanking,
  setRankPosition,
}: {
  busy: boolean
  locale: RecruitingLocale
  onSelect: (application: ApplicationSummary, opts?: { returnFocusEl?: HTMLElement | null }) => void
  positions: PositionSummary[]
  rankPosition: string
  ranking: RankingResponse | null
  rankingError?: boolean
  runRanking: () => void
  setRankPosition: (value: string) => void
}) {
  const isAr = locale === 'ar'
  const selectedPosition = positions.find((position) => position.position_code === rankPosition)
  const needsRun = Boolean(ranking?.needs_run)
  const stale = Boolean(ranking?.stale)
  const hasCandidates = Boolean(ranking?.candidates?.length)
  const matchingCount = rankingMatchingCount(ranking)
  const rankableCount = rankingRankableCount(ranking, ranking?.candidates?.length || 0)
  const eligibleCount = rankingEligibleCount(ranking)
  const excludedCount = rankingExcludedCount(ranking)
  const assessmentEnabled = rankingAssessmentEvidenceEnabled(
    ranking?.evidence_policy || ranking?.provenance?.evidence_policy,
  )

  function changeJob(value: string) {
    dashboardPerfMarkInteractionStart('ranking_job_switch', { hasJob: Boolean(value) })
    setRankPosition(value)
    dashboardPerfMarkNetworkComplete('ranking_job_switch', { hasJob: Boolean(value) })
  }

  function onRun() {
    dashboardPerfMarkInteractionStart('ranking_run', { force: true })
    runRanking()
    dashboardPerfMarkNetworkComplete('ranking_run', { force: true })
  }

  const stateBanner = !rankPosition
    ? null
    : busy
      ? rankingCopy(locale, 'state_running')
      : rankingError
        ? rankingCopy(locale, 'state_failed')
        : stale && ranking && !needsRun
          ? rankingCopy(locale, 'state_stale')
          : null

  const emptyText = !rankPosition
    ? rankingCopy(locale, 'state_no_job')
    : busy
      ? rankingCopy(locale, 'state_running')
      : rankingError
        ? rankingCopy(locale, 'state_failed')
        : needsRun
          ? rankingCopy(locale, 'state_no_run')
          : matchingCount > 0 && rankableCount === 0
            ? rankingCopy(locale, 'state_none_rankable')
            : rankingCopy(locale, 'state_empty_ranked')

  return (
    <div className="space-y-5" dir={isAr ? 'rtl' : 'ltr'}>
      <Card tone="board">
        <CardHeader>
          <CardTitle className="text-wf-ink">{rankingCopy(locale, 'title')}</CardTitle>
          <CardDescription className="text-wf-ink-muted">{rankingCopy(locale, 'subtitle')}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-[1fr_auto]">
          <select
            className="rounded-xl border border-semantic-line bg-white/80 px-3 py-2 text-sm text-semantic-ink"
            onChange={(event) => changeJob(event.target.value)}
            value={rankPosition}
          >
            <option value="">{rankingCopy(locale, 'select_job')}</option>
            {rankPosition && !positions.some((p) => p.position_code === rankPosition) ? (
              <option value={rankPosition}>{rankPosition}</option>
            ) : null}
            {positions.map((position) => (
              <option key={position.position_code} value={position.position_code}>
                {position.position_title || position.position_code}
              </option>
            ))}
          </select>
          <Button disabled={busy || !rankPosition} onClick={onRun} title={!rankPosition ? rankingCopy(locale, 'state_no_job') : undefined}>
            {busy ? <Loader2 className="animate-spin" size={16} /> : <Search size={16} />}
            {needsRun || !hasCandidates ? rankingCopy(locale, 'run') : rankingCopy(locale, 'rerun')}
          </Button>
        </CardContent>
      </Card>

      <RankingProfiler id="results">
        <Card tone="board">
          <CardHeader>
            <CardTitle className="text-wf-ink">
              {isAr ? 'نتائج الترتيب' : 'Ranked candidates'}
              {selectedPosition ? ` · ${selectedPosition.position_title || selectedPosition.position_code}` : ''}
            </CardTitle>
            {ranking && !needsRun && rankPosition && !rankingError ? (
              <div className="mt-3 space-y-2">
                <div className="flex flex-wrap gap-2 text-xs">
                  <Badge tone="default">
                    {rankingCopy(locale, 'in_review_order')} {rankableCount}
                  </Badge>
                  <Badge tone="muted">
                    {rankingCopy(locale, 'job_matches')} {matchingCount}
                  </Badge>
                  <Badge tone="muted">
                    {rankingCopy(locale, 'meets_all_requirements')} {eligibleCount}
                  </Badge>
                </div>
                <p className="max-w-3xl text-xs leading-5 text-semantic-subtle">{rankingCopy(locale, 'eligible_helper')}</p>
                {excludedCount > 0 ? (
                  <p className="max-w-3xl text-xs leading-5 text-semantic-subtle">
                    {rankingCopy(locale, 'excluded_note').replace('{excluded}', String(excludedCount))}
                  </p>
                ) : null}
              </div>
            ) : null}
          </CardHeader>
          <CardContent className="space-y-3">
            {stateBanner && !rankingError ? (
              <div
                className={cn(
                  'rounded-xl border px-3 py-2 text-sm',
                  stale
                    ? 'border-semantic-warning/60 bg-semantic-warning-soft text-semantic-warning-ink'
                    : 'border-semantic-line bg-semantic-surface/80 text-semantic-subtle',
                )}
              >
                {stateBanner}
              </div>
            ) : null}

            {rankingError ? (
              <ResourceState
                kind="error"
                locale={locale === 'ar' ? 'ar' : 'en'}
                title={
                  hasCandidates
                    ? rankingCopy(locale, 'state_failed_previous')
                    : rankingCopy(locale, 'state_failed')
                }
                onRetry={runRanking}
                retrying={busy}
                testId="ranking-list-state"
              />
            ) : null}

            {!rankingError && ranking?.comparison?.title ? (
              <div className="rounded-2xl border border-semantic-line bg-white/45 p-4">
                <div className="text-sm font-semibold text-semantic-ink">{ranking.comparison.title}</div>
                {ranking.comparison.detail ? <div className="mt-1 text-sm text-semantic-subtle">{ranking.comparison.detail}</div> : null}
              </div>
            ) : null}

            {!rankingError && ranking?.role_profile ? (
              <div className="rounded-2xl border border-semantic-line bg-white/45 p-4">
                <div className="text-sm font-semibold text-semantic-ink">
                  {rankingCopy(locale, 'fit_profile')}: {ranking.role_profile.label || rankingCopy(locale, 'fit_profile')}
                </div>
                <div className="mt-1 text-sm text-semantic-subtle">{rankingCopy(locale, 'fit_profile_detail')}</div>
              </div>
            ) : null}

            {rankingError && hasCandidates ? (
              <div className="space-y-3 opacity-80" data-testid="ranking-previous">
                {(ranking?.candidates || []).map((candidate, index) => (
                  <RankingCandidateCard
                    assessmentEnabled={assessmentEnabled}
                    candidate={candidate}
                    index={index}
                    key={candidate.app_key}
                    locale={locale}
                    onSelect={onSelect}
                  />
                ))}
              </div>
            ) : !rankingError ? (
              (ranking?.candidates || []).map((candidate, index) => (
                <RankingCandidateCard
                  assessmentEnabled={assessmentEnabled}
                  candidate={candidate}
                  index={index}
                  key={candidate.app_key}
                  locale={locale}
                  onSelect={onSelect}
                />
              ))
            ) : null}

            {!rankingError && !hasCandidates ? (
              <EmptyState text={emptyText} />
            ) : null}
          </CardContent>
        </Card>
      </RankingProfiler>
    </div>
  )
}

export function RankingCandidateCard({
  assessmentEnabled,
  candidate,
  index,
  locale,
  onSelect,
}: {
  assessmentEnabled: boolean
  candidate: RankingCandidate
  index: number
  locale: RecruitingLocale
  onSelect: (application: ApplicationSummary, opts?: { returnFocusEl?: HTMLElement | null }) => void
}) {
  const isAr = locale === 'ar'
  const [evidenceOpen, setEvidenceOpen] = useState(false)
  const decision = rankingDecisionFor(candidate)
  const showScore = Boolean(decision.score_state?.show_numeric && decision.advisory_score != null)
  const fitSummary = showScore
    ? (decision.fit_summary || candidate.presentation?.explanation || '')
    : (decision.fit_summary || decision.score_state?.label || (isAr ? 'الدرجة غير متاحة لهذه النتيجة.' : 'Score unavailable for this result.'))
  const strengths = (decision.strengths || []).slice(0, 3)
  const gaps = (decision.gaps || decision.missing_evidence || []).slice(0, 3)
  const evidence = (decision.evidence_references || []).slice(0, 4)
  const components = rankingComponentRows(decision, isAr ? 'ar' : 'en', { assessmentEnabled })
  const cvComponents = components.filter((c) => c.group === 'cv')
  const assessmentComponents = components.filter((c) => c.group === 'assessment')
  const eligibilityLabel = rankingEligibilityLabel(
    locale,
    decision.eligibility?.bucket || candidate.eligibility_bucket,
    decision.eligibility?.label,
  )

  return (
    <article
      className={
        index === 0
          ? 'rounded-2xl bg-wf-accent-priority p-4 text-wf-accent-priority-ink sm:p-5'
          : index === 1
            ? 'rounded-2xl bg-wf-accent-follow p-4 text-wf-accent-follow-ink sm:p-5'
            : index === 2
              ? 'rounded-2xl bg-wf-accent-assess-soft p-4 text-wf-accent-assess-ink sm:p-5'
              : 'rounded-2xl border border-semantic-line bg-wf-surface-raised/90 p-4 sm:p-5'
      }
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div
            className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${
              index < 3 ? 'bg-white/55 text-inherit' : 'text-semantic-subtle'
            }`}
          >
            {isAr ? `الترتيب #${index + 1}` : `Rank #${index + 1}`}
          </div>
          <h3 className={`mt-1 text-lg font-semibold tracking-tight ${index < 3 ? 'text-inherit' : 'text-semantic-ink'}`}>
            {decision.candidate_name || candidate.name || candidate.phone}
          </h3>
          <div className={`mt-1 text-sm ${index < 3 ? 'opacity-75' : 'text-semantic-subtle'}`}>
            {decision.job?.position_title || candidate.position_title || candidate.position_code}
            {' · '}
            {stageLabel(decision.application_stage || candidate.status)}
            {' · '}
            {eligibilityLabel}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={showScore ? 'priority' : 'muted'}>{rankingScoreLabel(decision, isAr ? 'ar' : 'en')}</Badge>
          <Button
            onClick={(event) => {
              dashboardPerfMarkInteractionStart('ranking_open_candidate', { rank: index + 1 })
              onSelect({ app_key: candidate.app_key } as ApplicationSummary, {
                returnFocusEl: event.currentTarget,
              })
              dashboardPerfMarkNetworkComplete('ranking_open_candidate', { rank: index + 1 })
            }}
            size="sm"
          >
            {rankingCopy(locale, 'open_profile')}
          </Button>
        </div>
      </div>

      <div className={`mt-4 rounded-2xl p-4 ${index < 3 ? 'bg-white/50' : 'border border-semantic-line bg-semantic-surface/80'}`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="max-w-3xl">
            <div className={`text-xs font-semibold uppercase tracking-wide ${index < 3 ? 'opacity-70' : 'text-semantic-subtle'}`}>
              {rankingCopy(locale, 'fit_summary')}
            </div>
            <p className={`mt-2 text-base font-medium leading-7 ${index < 3 ? 'text-inherit' : 'text-semantic-ink'}`}>
              {fitSummary || (isAr ? 'لا يوجد ملخص توافق بعد.' : 'No fit summary is stored yet.')}
            </p>
          </div>
          <Badge tone={showScore ? 'success' : 'muted'}>
            {showScore ? rankingCopy(locale, 'advisory_score') : rankingCopy(locale, 'ranking_status')}
          </Badge>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <DecisionSnapshot label={rankingCopy(locale, 'strengths')} values={strengths} locale={locale} />
          <DecisionSnapshot
            label={rankingCopy(locale, 'gaps')}
            values={gaps.length ? gaps : [isAr ? 'لا توجد فجوة رئيسية مسجّلة.' : 'No major gap captured yet.']}
            tone="warning"
            locale={locale}
          />
          <DecisionSnapshot
            label={rankingCopy(locale, 'next_step')}
            values={[decision.recommended_next_action || (isAr ? 'راجع الأدلة ثم قرر يدوياً.' : 'Review evidence and decide manually.')]}
            tone="strong"
            locale={locale}
          />
        </div>
      </div>

      {(evidence.length || cvComponents.length || assessmentComponents.length) ? (
        <details
          className="mt-4 rounded-xl border border-semantic-line bg-semantic-surface/60 p-4"
          onToggle={(event) => {
            const open = (event.currentTarget as HTMLDetailsElement).open
            setEvidenceOpen(open)
            if (open) {
              dashboardPerfMarkInteractionStart('ranking_expand_evidence', { rank: index + 1 })
              dashboardPerfMarkNetworkComplete('ranking_expand_evidence', { rank: index + 1 })
            }
          }}
          open={evidenceOpen}
        >
          <summary className="cursor-pointer text-sm font-semibold text-semantic-ink">
            {rankingCopy(locale, 'show_evidence')}
          </summary>
          {evidence.length ? (
            <div className="mt-4">
              <div className="mb-2 text-sm font-semibold text-semantic-ink">{rankingCopy(locale, 'cv_evidence')}</div>
              <ul className="space-y-2 text-sm leading-6 text-semantic-subtle">
                {evidence.map((item) => (
                  <li className="flex gap-2" key={item}>
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-semantic-ink/35" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {cvComponents.length ? (
            <div className="mt-4 rounded-xl border border-semantic-line bg-white/50 p-4">
              <div className="mb-3 text-sm font-semibold text-semantic-ink">{rankingCopy(locale, 'score_components')}</div>
              <div className="grid gap-2 md:grid-cols-3">
                {cvComponents.map((item) => (
                  <ScoreBreakdown key={item.key} label={item.label} max={item.max} value={item.value} />
                ))}
              </div>
            </div>
          ) : null}
          {assessmentEnabled && assessmentComponents.length ? (
            <div className="mt-3 rounded-xl border border-dashed border-semantic-line bg-white/35 p-4">
              <div className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-semantic-subtle">
                {rankingCopy(locale, 'assessment_evidence')}
              </div>
              <div className="grid gap-2 md:grid-cols-3">
                {assessmentComponents.map((item) => (
                  <ScoreBreakdown key={item.key} label={item.label} max={item.max} value={item.value} />
                ))}
              </div>
            </div>
          ) : null}
        </details>
      ) : null}
    </article>
  )
}

export function DecisionSnapshot({
  label,
  locale,
  tone = 'default',
  values,
}: {
  label: string
  locale: RecruitingLocale
  tone?: 'default' | 'strong' | 'warning'
  values: string[]
}) {
  return (
    <div className="rounded-xl border border-semantic-line bg-white/45 p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-semantic-subtle">{label}</div>
      <div className={cn('mt-2 text-sm leading-6', tone === 'strong' ? 'text-semantic-ink' : 'text-semantic-subtle')}>
        {values.filter(Boolean).slice(0, 2).join(' ') || rankingCopy(locale, 'not_captured')}
      </div>
    </div>
  )
}
