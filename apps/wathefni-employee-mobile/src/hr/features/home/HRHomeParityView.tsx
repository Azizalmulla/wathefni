import { useState } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'
import { useRouter } from 'expo-router'
import { useQuery } from '@tanstack/react-query'

import type { MobileMe, PrioritiesResponse, PriorityItem, PrioritySection } from '@hr/api/types'
import { useAuth } from '@hr/auth/AuthProvider'
import { destinationAvailable } from '@hr/capabilities'
import { toHrPath } from '@hr/navigation'
import {
  filterPrioritySections,
  HOME_SECTION_TYPES,
  INBOX_SECTION_TYPES,
} from '@hr/shell/ia'
import {
  hrHomeProgressTone,
  hrHomeStatusKey,
  iconForSection,
  sectionLabelKey,
  serverPriorityTotal,
  splitHomePriorities,
  type FlatPriority,
} from '@hr/features/home/homeParityComposition'
import { PRIORITIES_LIMIT } from '@hr/features/inbox/inboxComposition'
import { useRefetchOnScreenFocus } from '@hr/lib/hrRefresh'
import { AmbientCard, AmbientIconTile } from '@/components/ambient'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow } from '@/components/lists'
import { EditorialHeading, FadeIn, Wordmark, editorialFont } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { formatNumber, kuwaitDayPart } from '@/lib/format'
import { colors, font, homeComposition, layout, radius, spacing, typeScaling } from '@/theme'

/**
 * HR Home — Employee visual composition, HR decision content.
 * One ambient emphasis max; remaining rows; overflow → Inbox.
 */
export function HRHomeParityView({
  me,
  priorities,
  loading,
  error,
  refreshing,
  onRetry,
}: {
  me: MobileMe
  priorities: PrioritiesResponse | undefined
  loading: boolean
  error: boolean
  /** Pull-to-refresh only — never background/window fetch. */
  refreshing: boolean
  onRetry: () => void
}) {
  const router = useRouter()
  const { t, isRTL, locale } = useI18n()
  const align = readingEdgeAlign(isRTL)

  // Keep the server's company-wide `total` unless this viewer's permissions
  // actually hid rows — then the visible count is the only honest number.
  const scopeSection = (section: PrioritySection) => {
    const items = section.items.filter((item) => destinationAvailable(me, item.destination))
    const hidden = section.items.length - items.length
    const reported = Math.max(Number(section.total ?? section.items.length) || 0, section.items.length)
    return { ...section, items, total: hidden > 0 ? items.length : reported }
  }

  const sections = filterPrioritySections(priorities?.sections || [], HOME_SECTION_TYPES)
    .map(scopeSection)
    .filter((section) => section.items.length > 0)

  const inboxCount = serverPriorityTotal(
    filterPrioritySections(priorities?.sections || [], INBOX_SECTION_TYPES).map(scopeSection),
  )

  const { hero, rows, overflow, total } = splitHomePriorities(sections)
  const sparse = total <= 1
  const firstName = (me.principal.display_name || '').split(/\s+/).filter(Boolean)[0] || ''
  const initials = (me.principal.display_name || 'W')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('')

  const dayPart = kuwaitDayPart()
  const greetingKey =
    dayPart === 'morning'
      ? 'home.greetingMorning'
      : dayPart === 'afternoon'
        ? 'home.greetingAfternoon'
        : 'home.greetingEvening'

  const scopeLabel = me.scope.restricted ? t('hrHome.scopeTeam') : t('hrHome.scopeCompany')

  const openDestination = (destination: string) => {
    router.push(toHrPath(destination) as never)
  }

  return (
    <PageScreen>
      <PageScrollView
        gap={sparse ? spacing.xxl : spacing.xl}
        contentStyle={[styles.pageContent, sparse ? styles.pageContentSparse : null]}
        refreshing={refreshing}
        onRefresh={onRetry}
      >
        <View style={styles.header}>
          <Wordmark />
          <View style={styles.headerActions}>
            <InboxBell
              count={inboxCount}
              onPress={() => router.push('/hr/inbox' as never)}
            />
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={t('hrHome.openMore')}
              hitSlop={8}
              onPress={() => router.push('/hr/more' as never)}
              style={({ pressed }) => [styles.avatar, pressed && styles.avatarPressed]}
            >
              <Text maxFontSizeMultiplier={1.2} numberOfLines={1} style={styles.avatarText}>
                {initials || 'W'}
              </Text>
            </Pressable>
          </View>
        </View>

        <FadeIn style={{ gap: sparse ? spacing.xxl : spacing.xl }}>
          <View style={[styles.hero, sparse ? styles.heroSparse : null]}>
            <Text maxFontSizeMultiplier={typeScaling.heading} style={[styles.eyebrow, align]}>
              {t(greetingKey, { name: firstName || t('home.employee') })}
            </Text>
            <EditorialHeading>{t('hrHome.heading')}</EditorialHeading>
            <View style={styles.contextChip}>
              <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.contextChipText}>
                {me.principal.company_code} · {scopeLabel}
              </Text>
            </View>
          </View>

          {loading && !priorities ? (
            <ListRow title={t('home.dataLoading')} icon="hourglass-outline" />
          ) : null}

          {error && !priorities ? (
            <ListRow
              title={t('home.dataUnavailable')}
              subtitle={t('home.dataUnavailableHint')}
              icon="cloud-offline-outline"
              emphasis="warning"
              showChevron
              onPress={onRetry}
            />
          ) : null}

          {!loading && !error && total === 0 ? (
            <AmbientCard module="schedule" style={sparse ? styles.caughtUpSparse : undefined}>
              <View style={styles.caughtUpTop}>
                <View style={styles.contextChip}>
                  <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.contextChipText}>
                    {me.principal.company_code}
                  </Text>
                </View>
                <AmbientIconTile module="schedule" icon="checkmark-circle-outline" size={sparse ? 40 : 34} />
              </View>
              <Text
                maxFontSizeMultiplier={typeScaling.display}
                style={[styles.caughtUpTitle, align, !isRTL ? styles.tightTracking : null]}
              >
                {t('hrHome.caughtUpTitle')}
              </Text>
              <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.caughtUpBody, align]}>
                {t('hrHome.caughtUpBody')}
              </Text>
            </AmbientCard>
          ) : null}

          {hero ? (
            <HeroActionCard
              entry={hero}
              onPress={() => openDestination(hero.item.destination)}
            />
          ) : null}

          {rows.length > 0 ? (
            <View style={styles.section}>
              <Text
                accessibilityRole="header"
                maxFontSizeMultiplier={typeScaling.heading}
                style={[styles.sectionTitle, align, { fontFamily: editorialFont(locale) }]}
              >
                {t('hrHome.waitingSection')}
              </Text>
              {rows.map(({ section, item }) => (
                <PriorityListRow
                  key={`${item.type}-${item.target_id}`}
                  item={item}
                  sectionType={section.type}
                  onPress={() => openDestination(item.destination)}
                />
              ))}
            </View>
          ) : null}

          {overflow > 0 ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={t('hrHome.seeInbox')}
              onPress={() => router.push('/hr/inbox' as never)}
              style={({ pressed }) => [styles.inboxPill, pressed ? styles.pressed : null]}
            >
              <Ionicons name="file-tray-outline" size={18} color={colors.ink} />
              <Text maxFontSizeMultiplier={typeScaling.body} style={styles.inboxPillLabel}>
                {t('hrHome.seeInbox')}
              </Text>
              <Text style={styles.inboxPillCount}>{formatNumber(overflow, locale, 0)}</Text>
            </Pressable>
          ) : null}
        </FadeIn>
      </PageScrollView>
    </PageScreen>
  )
}

function HeroActionCard({ entry, onPress }: { entry: FlatPriority; onPress: () => void }) {
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const warmStatus = t(hrHomeStatusKey(entry.item.status))
  const section = t(sectionLabelKey(entry.section.type))

  // Green hero is intentional for this Home composition pass.
  return (
    <AmbientCard
      module="leave"
      onPress={onPress}
      accessibilityLabel={`${entry.item.summary}. ${warmStatus}`}
      style={styles.actionCard}
    >
      <View style={styles.actionTop}>
        <View style={styles.softChip}>
          <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.softChipText}>
            {section}
          </Text>
        </View>
        <AmbientIconTile module="leave" icon={iconForSection(entry.section.type)} size={36} />
      </View>
      <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.actionTitle, align]}>
        {entry.item.summary}
      </Text>
      <View style={[styles.actionMetaRow, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
        <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.actionMeta, align]}>
          {warmStatus}
        </Text>
        <View style={styles.actionOrb}>
          <Ionicons
            name={isRTL ? 'chevron-back' : 'chevron-forward'}
            size={15}
            color={colors.ink}
          />
        </View>
      </View>
    </AmbientCard>
  )
}

function PriorityListRow({
  item,
  sectionType,
  onPress,
}: {
  item: PriorityItem
  sectionType: string
  onPress: () => void
}) {
  const { t } = useI18n()
  const warmStatus = t(hrHomeStatusKey(item.status))
  const section = t(sectionLabelKey(sectionType))
  const tone = hrHomeProgressTone(item.status)

  return (
    <ListRow
      title={item.summary}
      subtitle={section}
      icon={iconForSection(sectionType)}
      iconTint={colors.surfaceMuted}
      showChevron
      onPress={onPress}
      trailing={<StatusChip label={warmStatus} tone={tone} />}
      accessibilityLabel={`${item.summary}. ${warmStatus}`}
    />
  )
}

function InboxBell({ count, onPress }: { count: number; onPress: () => void }) {
  const { t, locale, isRTL } = useI18n()
  const label =
    count > 0 ? t('home.unreadMessages', { count: formatNumber(count, locale, 0) }) : t('hrHome.openInbox')
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={({ pressed }) => [styles.bell, pressed ? styles.pressed : null]}
    >
      <Ionicons name="notifications-outline" size={22} color={colors.ink} />
      {count > 0 ? (
        <View style={[styles.badge, isRTL ? styles.badgeRTL : styles.badgeLTR]}>
          <Text maxFontSizeMultiplier={1.2} style={styles.badgeText}>
            {count > 99 ? '99+' : formatNumber(count, locale, 0)}
          </Text>
        </View>
      ) : null}
    </Pressable>
  )
}

export function HRHomeParityRoute() {
  const { me, request, refreshMe } = useAuth()
  const [pullRefreshing, setPullRefreshing] = useState(false)
  const priorities = useQuery({
    queryKey: ['mobile-priorities', me?.principal.user_id],
    queryFn: ({ signal }) =>
      request<PrioritiesResponse>(`/dashboard/mobile/priorities?limit=${PRIORITIES_LIMIT}`, {
        signal,
      }),
    enabled: Boolean(me),
  })
  useRefetchOnScreenFocus(() => void priorities.refetch(), Boolean(me))
  if (!me) return null
  const initialLoading = priorities.isLoading && !priorities.data
  const hardError = Boolean(priorities.error) && !priorities.data
  return (
    <HRHomeParityView
      me={me}
      priorities={priorities.data}
      loading={initialLoading}
      error={hardError}
      refreshing={pullRefreshing}
      onRetry={() => {
        void (async () => {
          setPullRefreshing(true)
          try {
            await Promise.all([refreshMe(), priorities.refetch()])
          } finally {
            setPullRefreshing(false)
          }
        })()
      }}
    />
  )
}

const styles = StyleSheet.create({
  pageContent: { paddingTop: spacing.lg },
  pageContentSparse: { paddingTop: spacing.xl },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  headerActions: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  bell: {
    width: layout.touchTarget,
    height: layout.touchTarget,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badge: {
    position: 'absolute',
    top: 4,
    minWidth: 18,
    height: 18,
    borderRadius: radius.pill,
    backgroundColor: colors.danger,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 4,
  },
  badgeLTR: { right: 2 },
  badgeRTL: { left: 2 },
  badgeText: { color: colors.primaryText, fontSize: 10, fontWeight: '800' },
  avatar: {
    width: 36,
    height: 36,
    borderRadius: radius.pill,
    backgroundColor: colors.pink,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarPressed: { opacity: 0.82 },
  avatarText: { color: colors.ink, fontSize: font.small, fontWeight: '800' },
  hero: { gap: 4, paddingTop: spacing.xs },
  heroSparse: { gap: spacing.sm, paddingTop: spacing.sm },
  eyebrow: { color: colors.subtle, fontSize: font.body, fontWeight: '500' },
  contextChip: {
    alignSelf: 'flex-start',
    paddingVertical: 5,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    marginTop: spacing.xs,
  },
  contextChipText: { color: colors.ink, fontSize: font.tiny, fontWeight: '700' },
  section: { gap: spacing.md },
  sectionTitle: {
    color: colors.ink,
    fontSize: font.h2,
    lineHeight: 26,
    fontWeight: '600',
    letterSpacing: -0.3,
  },
  actionCard: { gap: spacing.md },
  actionTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  softChip: {
    alignSelf: 'flex-start',
    paddingVertical: 5,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
  },
  softChipText: { color: colors.ink, fontSize: font.tiny, fontWeight: '700' },
  actionTitle: { color: colors.ink, fontSize: font.h3, fontWeight: '700' },
  actionMetaRow: { alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  actionMeta: { color: colors.ink, fontSize: font.tiny, fontWeight: '700', opacity: 0.72, flex: 1 },
  actionOrb: {
    width: 28,
    height: 28,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  inboxPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    alignSelf: 'stretch',
    backgroundColor: homeComposition.requestLeave.fill,
    borderRadius: radius.pill,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
  },
  inboxPillLabel: { flex: 1, color: colors.ink, fontSize: font.body, fontWeight: '700' },
  inboxPillCount: { color: colors.ink, fontSize: font.small, fontWeight: '800', opacity: 0.7 },
  caughtUpTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  caughtUpSparse: {
    gap: spacing.lg,
    paddingVertical: spacing.xxl,
    paddingHorizontal: spacing.xl,
  },
  caughtUpTitle: { color: colors.ink, fontSize: font.h1, fontWeight: '800' },
  caughtUpBody: { color: colors.ink, fontSize: font.body, lineHeight: 22, opacity: 0.78 },
  tightTracking: { letterSpacing: -0.45 },
  pressed: { opacity: 0.88 },
})
