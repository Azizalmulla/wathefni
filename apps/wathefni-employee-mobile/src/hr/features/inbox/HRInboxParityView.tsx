import { useMemo } from 'react'
import { StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'
import { useQuery } from '@tanstack/react-query'

import type { PrioritiesResponse } from '@hr/api/types'
import { useAuth } from '@hr/auth/AuthProvider'
import { destinationAvailable } from '@hr/capabilities'
import { toHrPath } from '@hr/navigation'
import { filterPrioritySections, INBOX_SECTION_TYPES } from '@hr/shell/ia'
import { QueueContinuation } from '@hr/components/QueueContinuation'
import { useRefetchOnScreenFocus } from '@hr/lib/hrRefresh'
import { serverPriorityTotal } from '@hr/features/home/homeParityComposition'
import {
  flattenInboxDecisions,
  groupInboxDecisions,
  inboxDecisionBody,
  INBOX_DECISION_PAGE,
  PRIORITIES_LIMIT,
} from '@hr/features/inbox/inboxComposition'
import {
  InboxCalmNote,
  InboxLedger,
  InboxLedgerRow,
  InboxLedgerSection,
} from '@/components/inboxLedger'
import { PageScreen, PageScrollView } from '@/components/layout'
import { SectionHeader, ShowMoreButton, usePagedList } from '@/components/lists'
import { EditorialHeading, FadeIn, Wordmark } from '@/components/premium'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { formatDateTime, formatNumber, formatRelativeTime } from '@/lib/format'
import { ambient, colors, font, spacing, typeScaling } from '@/theme'

/**
 * HR Inbox — same visual language as Employee Notifications.
 * Content is decision-only (leave / onboarding / attendance / …).
 */
export function HRInboxParityView() {
  const router = useRouter()
  const { me, request, refreshMe } = useAuth()
  const { t, locale, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)

  const priorities = useQuery({
    queryKey: ['mobile-priorities', me?.principal.user_id],
    queryFn: ({ signal }) =>
      request<PrioritiesResponse>(`/dashboard/mobile/priorities?limit=${PRIORITIES_LIMIT}`, {
        signal,
      }),
    enabled: Boolean(me),
  })
  useRefetchOnScreenFocus(() => void priorities.refetch(), Boolean(me))

  const sections = useMemo(() => {
    if (!me) return []
    return filterPrioritySections(priorities.data?.sections || [], INBOX_SECTION_TYPES)
      .map((section) => {
        const items = section.items.filter((item) => destinationAvailable(me, item.destination))
        const hidden = section.items.length - items.length
        const reported = Math.max(
          Number(section.total ?? section.items.length) || 0,
          section.items.length,
        )
        return { ...section, items, total: hidden > 0 ? items.length : reported }
      })
      .filter((section) => section.items.length > 0)
  }, [me, priorities.data?.sections])

  const flat = useMemo(() => flattenInboxDecisions(sections), [sections])
  const groups = useMemo(() => groupInboxDecisions(flat), [flat])
  // Section totals are company-wide; the response only carries a window of each.
  const sectionTotals = useMemo(
    () => Object.fromEntries(sections.map((section) => [section.type, section.total])),
    [sections],
  )
  const waitingCount = serverPriorityTotal(sections)

  const subtitle = waitingCount
    ? t('hrInbox.waitingCount', { count: formatNumber(waitingCount, locale, 0) })
    : t('hrInbox.clear')

  if (!me) return null

  const loading = priorities.isLoading && !priorities.data
  const error = Boolean(priorities.error) && !priorities.data

  return (
    <PageScreen>
      <PageScrollView
        refreshing={priorities.isRefetching}
        onRefresh={() => {
          void refreshMe()
          void priorities.refetch()
        }}
      >
        <View style={styles.nav}>
          <Wordmark />
        </View>
        <FadeIn style={styles.hero}>
          <EditorialHeading>{t('hrInbox.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {subtitle}
          </Text>
        </FadeIn>

        {loading ? <InboxCalmNote message={t('home.dataLoading')} /> : null}

        {error ? (
          <InboxLedgerRow
            title={t('home.dataUnavailable')}
            body={t('home.dataUnavailableHint')}
            emphasized
            accentColor={ambient.onboarding.fill}
            onPress={() => {
              void refreshMe()
              void priorities.refetch()
            }}
            accessibilityLabel={t('home.dataUnavailable')}
          />
        ) : null}

        {!loading && !error && waitingCount === 0 ? (
          <InboxCalmNote message={t('hrInbox.empty')} />
        ) : null}

        {!loading && !error
          ? groups.map((group) => (
              <InboxDecisionGroup
                key={group.sectionType}
                label={t(group.labelKey)}
                rows={group.rows}
                total={sectionTotals[group.sectionType] ?? group.rows.length}
                accentColor={group.accentColor}
                onOpen={(destination) => router.push(toHrPath(destination) as never)}
              />
            ))
          : null}
      </PageScrollView>
    </PageScreen>
  )
}

function InboxDecisionGroup({
  label,
  rows,
  total,
  accentColor,
  onOpen,
}: {
  label: string
  rows: ReturnType<typeof flattenInboxDecisions>
  /** Company-wide count for this section, which can exceed the fetched window. */
  total: number
  accentColor: string
  onOpen: (destination: string) => void
}) {
  const { t, locale } = useI18n()
  const page = usePagedList(rows, INBOX_DECISION_PAGE)
  return (
    <InboxLedgerSection>
      <SectionHeader title={label} count={Math.max(total, rows.length)} />
      <InboxLedger>
        {page.visible.map((row) => {
          const when = formatRelativeTime(row.item.timestamp, locale, t)
          const exact = formatDateTime(row.item.timestamp, locale)
          const body = inboxDecisionBody(row.item, t)
          const state = t('notifications.unreadItem')
          return (
            <InboxLedgerRow
              key={row.key}
              title={row.item.summary}
              body={body}
              when={when}
              emphasized
              accentColor={accentColor}
              onPress={() => onOpen(row.item.destination)}
              accessibilityLabel={`${row.item.summary}. ${state}. ${when}${exact ? ` (${exact})` : ''}. ${body}`}
              accessibilityHint={t('notifications.openHint')}
            />
          )
        })}
      </InboxLedger>
      {page.hidden ? (
        <ShowMoreButton
          label={t('common.showMore', { count: formatNumber(page.hidden, locale, 0) })}
          onPress={page.showMore}
        />
      ) : null}
      {/* Inbox shows a window of each queue; the full list lives in its own
          screen, so say what is missing instead of ending silently. */}
      <QueueContinuation
        loaded={rows.length}
        total={Math.max(total, rows.length)}
        hasMore={false}
        loadingMore={false}
        onLoadMore={() => {}}
      />
    </InboxLedgerSection>
  )
}

const styles = StyleSheet.create({
  nav: { minHeight: 42, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  hero: { gap: spacing.xs },
  subtitle: { color: colors.subtle, fontSize: font.small, lineHeight: 20, maxWidth: 360 },
})
