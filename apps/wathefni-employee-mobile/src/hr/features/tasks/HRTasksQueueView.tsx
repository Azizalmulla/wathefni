import { useMemo } from 'react'
import { StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'

import { mobileApi } from '@hr/api/mobile'
import { useHrQueue } from '@hr/api/useHrQueue'
import { QueueContinuation } from '@hr/components/QueueContinuation'
import type { HRTask } from '@hr/api/types'
import { useAuth } from '@hr/auth/AuthProvider'
import { routeAvailable } from '@hr/capabilities'
import {
  buildTasksDemoQueue,
  queueSubtitle,
  taskPriorityLabelKey,
  taskPriorityTone,
} from '@hr/features/tasks/tasksComposition'
import { tasksDemoEnabled } from '@hr/features/tasks/tasksDemoGate'
import { toHrPath } from '@hr/navigation'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, radius, spacing, typeScaling } from '@/theme'

/**
 * HR Tasks — open follow-up queue only (not done/dismissed history).
 */
export function HRTasksQueueView() {
  const router = useRouter()
  const onBack = useHrSafeBack()
  const { me, request, refreshMe } = useAuth()
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const permitted = routeAvailable(me, 'tasks')
  const demo = tasksDemoEnabled()

  const queue = useHrQueue<HRTask>({
    queryKey: ['hr-tasks', 'open', me?.principal.user_id],
    enabled: Boolean(me) && permitted && !demo,
    fetchPage: ({ offset, limit, signal }) =>
      mobileApi.tasks(request, { status: 'open', offset, limit, signal }),
  })

  const demoModel = useMemo(() => (demo ? buildTasksDemoQueue() : null), [demo])
  const items: HRTask[] = demoModel?.open || queue.items

  const loading = !demo && queue.loading
  const error = !demo && queue.error

  if (!me) return null

  return (
    <PageScreen>
      <PageScrollView
        gap={spacing.xl}
        refreshing={!demo && queue.refreshing}
        onRefresh={() => {
          void refreshMe()
          queue.refetch()
        }}
      >
        <HrPushedNav onBack={onBack} accessibilityLabel={t('common.back')} />
        <FadeIn style={styles.hero}>
          <EditorialHeading>{t('hrTasks.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('hrTasks.subtitle')}
          </Text>
          {demo ? (
            <View style={styles.demoBanner}>
              <Text maxFontSizeMultiplier={typeScaling.chip} style={styles.demoBannerText}>
                {t('hrTasks.demoBanner')}
              </Text>
            </View>
          ) : null}
        </FadeIn>

        {!permitted ? (
          <ListRow
            title={t('hrTasks.permissionTitle')}
            subtitle={t('hrTasks.permissionBody')}
            icon="lock-closed-outline"
          />
        ) : null}

        {permitted && loading ? <ListRow title={t('home.dataLoading')} icon="hourglass-outline" /> : null}
        {permitted && error ? (
          <ListRow
            title={t('home.dataUnavailable')}
            subtitle={t('home.dataUnavailableHint')}
            icon="cloud-offline-outline"
            emphasis="warning"
            showChevron
            onPress={() => queue.refetch()}
          />
        ) : null}

        {permitted && !loading && !error ? (
          <View style={styles.section}>
            <SectionHeader
              title={t('hrTasks.queueTitle')}
              count={demo ? items.length : Math.max(queue.total, items.length)}
            />
            <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.footnote, align]}>
              {t('hrTasks.queueHint')}
            </Text>
            {items.length === 0 ? (
              <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.empty, align]}>
                {t('hrTasks.emptyQueue')}
              </Text>
            ) : (
              items.map((item) => (
                <ListRow
                  key={item.task_id}
                  title={item.title}
                  subtitle={queueSubtitle(item, t)}
                  icon="checkbox-outline"
                  iconTint={colors.surfaceMuted}
                  showChevron
                  onPress={() =>
                    router.push(toHrPath(`/tasks/${encodeURIComponent(item.task_id)}`) as never)
                  }
                  trailing={
                    <StatusChip
                      label={t(taskPriorityLabelKey(item.priority))}
                      tone={taskPriorityTone(item.priority)}
                    />
                  }
                  style={styles.row}
                />
              ))
            )}
            {demo ? null : (
              <QueueContinuation
                loaded={queue.loaded}
                total={queue.total}
                hasMore={queue.hasMore}
                loadingMore={queue.loadingMore}
                onLoadMore={queue.loadMore}
              />
            )}
          </View>
        ) : null}
      </PageScrollView>
    </PageScreen>
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
  section: { gap: spacing.sm },
  row: { backgroundColor: colors.surface },
  empty: { color: colors.subtle, fontSize: font.small, paddingVertical: spacing.md },
  footnote: { color: colors.subtle, fontSize: font.tiny },
})
