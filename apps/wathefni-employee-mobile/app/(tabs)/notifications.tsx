import { useCallback } from 'react'
import { FlatList, Pressable, StyleSheet, Text, View } from 'react-native'
import { useQueryClient } from '@tanstack/react-query'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { EmptyState, ErrorState, LoadingState } from '@/components/States'
import { formatDate } from '@/lib/format'
import { colors, font, spacing } from '@/theme'
import type { NotificationItem, NotificationsResponse } from '@/api/types'

export default function NotificationsScreen() {
  const { t, locale } = useI18n()
  const { request } = useAuth()
  const queryClient = useQueryClient()
  const query = useAppQuery<NotificationsResponse>(['notifications'], '/app/notifications')

  const markRead = useCallback(
    async (item: NotificationItem) => {
      if (item.read) return
      try {
        await request(`/app/notifications/${item.id}/read`, { method: 'POST' })
        await queryClient.invalidateQueries({ queryKey: ['notifications'] })
      } catch {
        // Non-critical: the unread dot simply stays until the next refresh.
      }
    },
    [request, queryClient],
  )

  if (query.isLoading) return <LoadingState />
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />
  const items = query.data?.notifications ?? []
  if (!items.length) return <EmptyState message={t('notifications.empty')} />

  return (
    <FlatList
      style={styles.screen}
      contentContainerStyle={styles.content}
      data={items}
      keyExtractor={(item) => item.id}
      refreshing={query.isRefetching}
      onRefresh={() => query.refetch()}
      renderItem={({ item }) => (
        <Pressable
          style={[styles.row, !item.read && styles.unread]}
          onPress={() => markRead(item)}
          accessibilityRole="button"
        >
          <View style={styles.flex}>
            <Text style={styles.title}>{item.title}</Text>
            {item.body ? <Text style={styles.body}>{item.body}</Text> : null}
            <Text style={styles.date}>{formatDate(item.created_at, locale)}</Text>
          </View>
          {!item.read ? <View style={styles.dot} /> : null}
        </Pressable>
      )}
    />
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.lg, gap: spacing.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderRadius: 14,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.lg,
  },
  unread: { borderColor: colors.accent },
  flex: { flex: 1, gap: 2 },
  title: { fontSize: font.body, fontWeight: '600', color: colors.text },
  body: { fontSize: font.small, color: colors.subtle },
  date: { fontSize: font.tiny, color: colors.subtle, marginTop: 2 },
  dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.accent, marginTop: 4 },
})
