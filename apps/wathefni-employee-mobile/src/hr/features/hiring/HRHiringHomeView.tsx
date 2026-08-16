import { useMemo } from 'react'
import { StyleSheet, Text, View } from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'
import { useRouter } from 'expo-router'
import { useQuery } from '@tanstack/react-query'

import { mobileApi } from '@hr/api/mobile'
import type { PrioritiesResponse } from '@hr/api/types'
import { useAuth } from '@hr/auth/AuthProvider'
import { destinationAvailable, hasAnyCapability } from '@hr/capabilities'
import { toHrPath } from '@hr/navigation'
import { tabHiringEnabled } from '@hr/shell/ia'
import {
  browseDestination,
  browseKeysForCapabilities,
  composeHiringHome,
  type HiringBrowseKey,
  type HiringHomeModel,
  type HiringPriority,
  type HiringUpcomingItem,
} from '@hr/features/hiring/hiringComposition'
import { isHiringDemoId } from '@hr/features/hiring/hiringDemoGate'
import { AmbientCard } from '@/components/ambient'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn, Wordmark } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { formatNumber } from '@/lib/format'
import {
  ambient,
  colors,
  font,
  homeComposition,
  radius,
  scheduleComposition,
  spacing,
  typeScaling,
} from '@/theme'

/**
 * Hiring home — mobile-native recruiting surface.
 * Cream/black foundation; pink/blue/yellow/green used sparingly for meaning.
 */
export function HRHiringHomeView() {
  const router = useRouter()
  const { me, request, refreshMe } = useAuth()
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const permitted = tabHiringEnabled(me)

  const canCandidates = Boolean(
    me &&
      hasAnyCapability(me, 'recruiting', [
        'candidate_rankings',
        'candidate_summary',
        'candidate_evidence',
      ]),
  )
  const canInterviews = Boolean(
    me && hasAnyCapability(me, 'recruiting', ['interview_status', 'interview_notes']),
  )
  const canRequisitions = Boolean(me && hasAnyCapability(me, 'recruiting', ['requisitions_review']))

  const priorities = useQuery({
    queryKey: ['mobile-priorities', me?.principal.user_id],
    queryFn: ({ signal }) => request<PrioritiesResponse>('/dashboard/mobile/priorities', { signal }),
    enabled: Boolean(me) && permitted,
  })
  const positions = useQuery({
    queryKey: ['hr-hiring-positions', me?.principal.user_id],
    queryFn: ({ signal }) => mobileApi.positions(request, { status: 'open', limit: 50, signal }),
    enabled: Boolean(me) && permitted && canCandidates,
  })
  const interviews = useQuery({
    queryKey: ['hr-hiring-interviews', me?.principal.user_id],
    queryFn: ({ signal }) => mobileApi.interviews(request, signal),
    enabled: Boolean(me) && permitted && canInterviews,
  })

  const browse = useMemo(
    () =>
      browseKeysForCapabilities({
        canCandidates,
        canInterviews,
        canRequisitions,
      }),
    [canCandidates, canInterviews, canRequisitions],
  )

  const model: HiringHomeModel = useMemo(
    () =>
      composeHiringHome({
        sections: (priorities.data?.sections || []).map((section) => ({
          ...section,
          items: section.items.filter((item) => destinationAvailable(me, item.destination)),
        })),
        positions: positions.data?.items || [],
        interviews: interviews.data?.items || [],
        browse,
      }),
    [priorities.data?.sections, positions.data?.items, interviews.data?.items, browse, me],
  )

  const loading =
    permitted &&
    ((canCandidates && positions.isLoading && !positions.data) ||
      (canInterviews && interviews.isLoading && !interviews.data) ||
      (priorities.isLoading && !priorities.data)) &&
    !model.demo

  const error =
    permitted &&
    !model.demo &&
    ((canCandidates && positions.error && !positions.data) ||
      (canInterviews && interviews.error && !interviews.data) ||
      (priorities.error && !priorities.data))

  const open = (destination: string, id?: string) => {
    // Same capability gate Home/Inbox use — never navigate to an unavailable module.
    if (!destinationAvailable(me, destination)) return
    // Demo ids never hit detail decision routes — browse the real workflow lists.
    if (id && isHiringDemoId(id)) {
      router.push(toHrPath(destination) as never)
      return
    }
    router.push(toHrPath(destination) as never)
  }

  const retry = () => {
    void refreshMe()
    void priorities.refetch()
    void positions.refetch()
    void interviews.refetch()
  }

  if (!me) return null

  return (
    <PageScreen>
      <PageScrollView refreshing={priorities.isRefetching} onRefresh={retry} gap={spacing.xl}>
        <View style={styles.nav}>
          <Wordmark />
        </View>

        <FadeIn style={styles.hero}>
          <EditorialHeading>{t('hrHiring.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('hrHiring.subtitle')}
          </Text>
          {model.demo ? (
            <View style={styles.demoBanner} accessibilityRole="summary">
              <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.demoBannerText}>
                {t('hrHiring.demoBanner')}
              </Text>
            </View>
          ) : null}
        </FadeIn>

        {!permitted ? (
          <ListRow
            title={t('hrHiring.permissionTitle')}
            subtitle={t('hrHiring.permissionBody')}
            icon="lock-closed-outline"
          />
        ) : null}

        {permitted && loading ? (
          <ListRow title={t('home.dataLoading')} icon="hourglass-outline" />
        ) : null}

        {permitted && error ? (
          <ListRow
            title={t('home.dataUnavailable')}
            subtitle={t('home.dataUnavailableHint')}
            icon="cloud-offline-outline"
            emphasis="warning"
            showChevron
            onPress={retry}
          />
        ) : null}

        {permitted && !loading && !error ? (
          <>
            <SummaryStrip model={model} />

            {model.priority ? (
              <PriorityCard priority={model.priority} onPress={() => open(model.priority!.destination, model.priority!.id)} />
            ) : (
              <View style={styles.emptyPriority}>
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.emptyPriorityTitle, align]}>
                  {t('hrHiring.caughtUpTitle')}
                </Text>
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.emptyPriorityBody, align]}>
                  {t('hrHiring.caughtUpBody')}
                </Text>
              </View>
            )}

            {model.upcoming.length ? (
              <View style={styles.section}>
                <SectionHeader title={t('hrHiring.upcoming')} count={model.upcoming.length} />
                {model.upcoming.map((item) => (
                  <UpcomingRow key={item.id} item={item} onPress={() => open(item.destination, item.id)} />
                ))}
              </View>
            ) : (
              <View style={styles.section}>
                <SectionHeader title={t('hrHiring.upcoming')} />
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.quietEmpty, align]}>
                  {t('hrHiring.upcomingEmpty')}
                </Text>
              </View>
            )}

            {model.browse.length ? (
              <View style={styles.section}>
                <SectionHeader title={t('hrHiring.browse')} />
                {model.browse.map((key) => (
                  <BrowseRow
                    key={key}
                    browseKey={key}
                    onPress={() => open(browseDestination(key))}
                  />
                ))}
              </View>
            ) : null}
          </>
        ) : null}
      </PageScrollView>
    </PageScreen>
  )
}

function SummaryStrip({ model }: { model: HiringHomeModel }) {
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const cells: { label: string; value: number; color: string }[] = [
    {
      label: t('hrHiring.statJobs'),
      value: model.summary.activeJobs,
      color: ambient.onboarding.fill,
    },
    {
      label: t('hrHiring.statCandidates'),
      value: model.summary.activeCandidates,
      color: ambient.schedule.fill,
    },
    {
      label: t('hrHiring.statInterviews'),
      value: model.summary.interviewsSoon,
      color: scheduleComposition.planned.fill,
    },
  ]
  return (
    <View style={styles.summary} accessibilityRole="summary">
      {cells.map((cell) => (
        <View key={cell.label} style={styles.summaryCell}>
          <View style={[styles.summaryDot, { backgroundColor: cell.color }]} />
          <Text maxFontSizeMultiplier={typeScaling.heading} style={styles.summaryValue}>
            {formatNumber(cell.value, locale, 0)}
          </Text>
          <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.summaryLabel, align]}>
            {cell.label}
          </Text>
        </View>
      ))}
    </View>
  )
}

function PriorityCard({ priority, onPress }: { priority: HiringPriority; onPress: () => void }) {
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const title = priority.titleKey
    ? t(priority.titleKey, { position: priority.positionCode || '' })
    : priority.title
  const body = priority.bodyKey
    ? t(priority.bodyKey, {
        position: priority.positionCode || t('hrHiring.thisRole'),
      })
    : priority.body
  return (
    <AmbientCard
      module="onboarding"
      onPress={onPress}
      accessibilityLabel={`${title}. ${body}`}
      style={styles.priorityCard}
    >
      <View style={styles.softChip}>
        <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.softChipText}>
          {t('hrHiring.needsAttention')}
        </Text>
      </View>
      <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.priorityTitle, align]}>
        {title}
      </Text>
      <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.priorityBody, align]}>
        {body}
      </Text>
    </AmbientCard>
  )
}

function UpcomingRow({ item, onPress }: { item: HiringUpcomingItem; onPress: () => void }) {
  const { t } = useI18n()
  const icon =
    item.kind === 'interview'
      ? 'calendar-outline'
      : item.kind === 'feedback'
        ? 'create-outline'
        : item.kind === 'offer'
          ? 'ribbon-outline'
          : 'people-outline'
  return (
    <ListRow
      title={item.title}
      subtitle={item.subtitle}
      icon={icon}
      iconTint={colors.surfaceMuted}
      showChevron
      onPress={onPress}
      trailing={<StatusChip label={t(item.statusLabelKey)} tone={item.statusTone} />}
      style={styles.row}
    />
  )
}

function BrowseRow({
  browseKey,
  onPress,
}: {
  browseKey: HiringBrowseKey
  onPress: () => void
}) {
  const { t } = useI18n()
  const meta: Record<
    HiringBrowseKey,
    { titleKey: string; subtitleKey: string; icon: keyof typeof Ionicons.glyphMap; tint: string }
  > = {
    jobs: {
      titleKey: 'hrHiring.browseJobs',
      subtitleKey: 'hrHiring.browseJobsBody',
      icon: 'briefcase-outline',
      tint: ambient.payslips.fill,
    },
    candidates: {
      titleKey: 'hrHiring.browseCandidates',
      subtitleKey: 'hrHiring.browseCandidatesBody',
      icon: 'people-outline',
      tint: ambient.schedule.fill,
    },
    interviews: {
      titleKey: 'hrHiring.browseInterviews',
      subtitleKey: 'hrHiring.browseInterviewsBody',
      icon: 'calendar-outline',
      tint: scheduleComposition.planned.fill,
    },
    ranking: {
      titleKey: 'hrHiring.browseRanking',
      subtitleKey: 'hrHiring.browseRankingBody',
      icon: 'analytics-outline',
      tint: ambient.onboarding.fill,
    },
    assessments: {
      titleKey: 'hrHiring.browseAssessments',
      subtitleKey: 'hrHiring.browseAssessmentsBody',
      icon: 'school-outline',
      tint: homeComposition.requestLeave.fill,
    },
    requisitions: {
      titleKey: 'hrHiring.browseRequisitions',
      subtitleKey: 'hrHiring.browseRequisitionsBody',
      icon: 'clipboard-outline',
      tint: ambient.payslips.fill,
    },
  }
  const row = meta[browseKey]
  return (
    <ListRow
      title={t(row.titleKey)}
      subtitle={t(row.subtitleKey)}
      icon={row.icon}
      iconTint={row.tint}
      showChevron
      onPress={onPress}
      style={styles.row}
    />
  )
}

const styles = StyleSheet.create({
  nav: { minHeight: 42, justifyContent: 'center' },
  hero: { gap: spacing.xs },
  subtitle: { color: colors.subtle, fontSize: font.small, lineHeight: 20, maxWidth: 360 },
  demoBanner: {
    alignSelf: 'flex-start',
    marginTop: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceMuted,
  },
  demoBannerText: { color: colors.subtle, fontWeight: '700', fontSize: font.tiny },
  summary: {
    flexDirection: 'row',
    backgroundColor: colors.surface,
    borderRadius: radius.xl,
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.md,
    gap: spacing.sm,
  },
  summaryCell: { flex: 1, alignItems: 'center', gap: 4 },
  summaryDot: { width: 8, height: 8, borderRadius: 4 },
  summaryValue: { color: colors.ink, fontSize: font.h2, fontWeight: '800' },
  summaryLabel: { color: colors.subtle, fontSize: font.tiny, fontWeight: '600', textAlign: 'center' },
  priorityCard: { gap: spacing.md, padding: spacing.lg },
  softChip: {
    backgroundColor: 'rgba(27,26,23,0.08)',
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  softChipText: { color: colors.ink, fontSize: font.tiny, fontWeight: '700' },
  priorityTitle: { color: colors.ink, fontSize: font.h3, fontWeight: '800', lineHeight: 26 },
  priorityBody: { color: colors.ink, opacity: 0.72, fontSize: font.small, lineHeight: 18 },
  section: { gap: spacing.sm },
  row: { backgroundColor: colors.surface },
  emptyPriority: { gap: spacing.sm, paddingVertical: spacing.md },
  emptyPriorityTitle: { color: colors.ink, fontSize: font.body, fontWeight: '700' },
  emptyPriorityBody: { color: colors.subtle, fontSize: font.small, lineHeight: 20 },
  quietEmpty: { color: colors.subtle, fontSize: font.small, paddingVertical: spacing.sm },
})
