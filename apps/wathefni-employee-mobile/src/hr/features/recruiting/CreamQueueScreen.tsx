/** Shared cream list chrome for recruiting queues (Candidates / Interviews / Jobs). */

import type { ReactNode } from 'react'
import { StyleSheet, Text, View } from 'react-native'

import type { ResourceState } from '@hr/api/state'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip, type StatusTone } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, spacing, typeScaling } from '@/theme'

export type CreamQueueItem = {
  id: string
  title: string
  subtitle?: string | null
  meta?: string | null
  status?: string | null
  tone?: StatusTone
}

export function CreamQueueScreen({
  eyebrow,
  title,
  state,
  items,
  onOpen,
  onRetry,
  onBack,
  emptyTitle,
  emptyBody,
  headerExtra,
  banner,
}: {
  eyebrow: string
  title: string
  state: ResourceState
  items: CreamQueueItem[]
  onOpen?: (item: CreamQueueItem) => void
  onRetry?: () => void
  onBack?: () => void
  emptyTitle?: string
  emptyBody?: string
  headerExtra?: ReactNode
  banner?: ReactNode
}) {
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl}>
        <HrPushedNav onBack={onBack || (() => undefined)} accessibilityLabel={t('common.back')} />
        <FadeIn style={styles.hero}>
          <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.eyebrow, align]}>
            {eyebrow}
          </Text>
          <EditorialHeading>{title}</EditorialHeading>
          {headerExtra}
        </FadeIn>

        {banner}

        {state === 'loading' ? <ListRow title={t('home.dataLoading')} icon="hourglass-outline" /> : null}

        {state === 'permission' ? (
          <ListRow title={t('state.permissionTitle')} subtitle={t('state.permissionBody')} />
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

        {state === 'empty' ? (
          <ListRow title={emptyTitle || t('state.emptyTitle')} subtitle={emptyBody || t('state.emptyBody')} />
        ) : null}

        {state === 'ready' ? (
          <View style={styles.section}>
            <SectionHeader title={title} count={items.length} />
            {items.map((item) => (
              <ListRow
                key={item.id}
                title={item.title}
                subtitle={[item.subtitle, item.meta].filter(Boolean).join(' · ') || undefined}
                showChevron={Boolean(onOpen)}
                onPress={onOpen ? () => onOpen(item) : undefined}
                trailing={
                  item.status ? <StatusChip label={item.status} tone={item.tone || 'neutral'} /> : undefined
                }
                style={styles.row}
              />
            ))}
          </View>
        ) : null}
      </PageScrollView>
    </PageScreen>
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
  row: { backgroundColor: colors.surface },
})
