import { useState } from 'react'
import type { ReactNode } from 'react'
import { StyleSheet, Text, TextInput, View } from 'react-native'

import type { ResourceState } from '@hr/api/state'
import {
  ActionableCard,
  ActionButton,
  Card,
  EditorialHeading,
  Screen,
  Skeleton,
  StatePanel,
  StatusBadge,
  WorkspaceHeader,
  type StatusTone,
} from '@hr/components/primitives'
import { useLocale } from '@hr/i18n'
import { colors, radius, spacing, type as typography } from '@hr/theme'

export type OperationalItem = {
  id: string
  title: string
  subtitle?: string | null
  meta?: string | null
  status?: string | null
  tone?: StatusTone
  allowedActions?: string[]
}

export type DetailFact = {
  label: string
  value: string | null | undefined
}

export function ResourcePanel({
  state,
  onRetry,
  emptyTitle,
  emptyBody,
}: {
  state: Exclude<ResourceState, 'ready'>
  onRetry?: () => void
  emptyTitle?: string
  emptyBody?: string
}) {
  const { t } = useLocale()
  const config = {
    loading: null,
    empty: {
      title: emptyTitle || t('state.emptyTitle'),
      body: emptyBody || t('state.emptyBody'),
      icon: 'file-tray-outline' as const,
    },
    error: {
      title: t('state.errorTitle'),
      body: t('state.errorBody'),
      icon: 'alert-circle-outline' as const,
    },
    offline: {
      title: t('state.offlineTitle'),
      body: t('state.offlineBody'),
      icon: 'cloud-offline-outline' as const,
    },
    stale: {
      title: t('state.staleTitle'),
      body: t('state.staleBody'),
      icon: 'refresh-circle-outline' as const,
    },
    success: {
      title: t('state.successTitle'),
      body: t('state.successBody'),
      icon: 'checkmark-done-circle-outline' as const,
    },
    permission: {
      title: t('state.permissionTitle'),
      body: t('state.permissionBody'),
      icon: 'shield-outline' as const,
    },
    revoked: {
      title: t('state.revokedTitle'),
      body: t('state.revokedBody'),
      icon: 'lock-closed-outline' as const,
    },
    company_disabled: {
      title: t('state.companyDisabledTitle'),
      body: t('state.companyDisabledBody'),
      icon: 'business-outline' as const,
    },
    company_archived: {
      title: t('state.companyArchivedTitle'),
      body: t('state.companyArchivedBody'),
      icon: 'archive-outline' as const,
    },
    session_expired: {
      title: t('state.sessionExpiredTitle'),
      body: t('state.sessionExpiredBody'),
      icon: 'time-outline' as const,
    },
  }[state]
  if (!config) {
    return (
      <View style={styles.stack}>
        <Skeleton lines={4} />
        <Skeleton lines={3} />
      </View>
    )
  }
  const retryable = ['error', 'offline', 'stale', 'permission'].includes(state)
  return (
    <StatePanel
      title={config.title}
      body={config.body}
      icon={config.icon}
      action={retryable ? t('common.retry') : undefined}
      onAction={retryable ? onRetry : undefined}
    />
  )
}

export function OperationalListView({
  company,
  eyebrow,
  title,
  items,
  state,
  onOpen,
  onRetry,
  onLocale,
  onBack,
  emptyTitle,
  emptyBody,
  footer,
  actionsForItem,
  onAction,
}: {
  company: string
  eyebrow: string
  title: string
  items: OperationalItem[]
  state: ResourceState
  onOpen?: (item: OperationalItem) => void
  onRetry?: () => void
  onLocale?: () => void
  onBack?: () => void
  emptyTitle?: string
  emptyBody?: string
  footer?: ReactNode
  actionsForItem?: (item: OperationalItem) => Array<{
    key: string
    label: string
    tone?: 'primary' | 'secondary' | 'danger'
  }>
  onAction?: (item: OperationalItem, action: string) => void
}) {
  const { t } = useLocale()
  return (
    <Screen>
      <WorkspaceHeader
        company={company}
        onLocale={onLocale}
        onBack={onBack}
        backAccessibilityLabel={t('common.back')}
      />
      <EditorialHeading eyebrow={eyebrow}>{title}</EditorialHeading>
      {state !== 'ready' ? (
        <ResourcePanel
          state={state}
          onRetry={onRetry}
          emptyTitle={emptyTitle}
          emptyBody={emptyBody}
        />
      ) : (
        <View style={styles.stack}>
          {items.map((item) => {
            const itemActions = actionsForItem?.(item) || []
            return (
              <View key={item.id} style={styles.itemGroup}>
                <ActionableCard
                  title={item.title}
                  subtitle={item.subtitle}
                  meta={item.meta}
                  status={item.status}
                  tone={item.tone}
                  onPress={onOpen ? () => onOpen(item) : undefined}
                />
                {itemActions.length ? (
                  <View style={styles.itemActions}>
                    {itemActions.map((action) => (
                      <ActionButton
                        key={action.key}
                        label={action.label}
                        tone={action.tone}
                        onPress={() => onAction?.(item, action.key)}
                      />
                    ))}
                  </View>
                ) : null}
              </View>
            )
          })}
          {footer}
        </View>
      )}
    </Screen>
  )
}

export function OperationalDetailView({
  company,
  eyebrow,
  title,
  status,
  facts,
  state,
  actions = [],
  onAction,
  onRetry,
  onLocale,
  onBack,
  children,
}: {
  company: string
  eyebrow: string
  title: string
  status?: string | null
  facts: DetailFact[]
  state: ResourceState
  actions?: Array<{ key: string; label: string; tone?: 'primary' | 'secondary' | 'danger' }>
  onAction?: (key: string) => void
  onRetry?: () => void
  onLocale?: () => void
  onBack?: () => void
  children?: ReactNode
}) {
  const { isRTL, t } = useLocale()
  return (
    <Screen>
      <WorkspaceHeader
        company={company}
        onLocale={onLocale}
        onBack={onBack}
        backAccessibilityLabel={t('common.back')}
      />
      <EditorialHeading eyebrow={eyebrow}>{title}</EditorialHeading>
      {state !== 'ready' ? (
        <ResourcePanel state={state} onRetry={onRetry} />
      ) : (
        <>
          <Card tone="cream">
            {status ? (
              <View style={{ alignItems: isRTL ? 'flex-end' : 'flex-start' }}>
                <StatusBadge label={status} tone={toneForStatus(status)} />
              </View>
            ) : null}
            {facts.filter((fact) => fact.value).map((fact) => (
              <View key={fact.label} style={styles.fact}>
                <Text style={[styles.factLabel, { textAlign: isRTL ? 'right' : 'left' }]}>
                  {fact.label}
                </Text>
                <Text style={[styles.factValue, { textAlign: isRTL ? 'right' : 'left' }]}>
                  {fact.value}
                </Text>
              </View>
            ))}
          </Card>
          {children}
          {actions.length ? (
            <View style={[styles.actionRow, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
              {actions.map((action) => (
                <View key={action.key} style={styles.flex}>
                  <ActionButton
                    label={action.label}
                    tone={action.tone}
                    onPress={() => onAction?.(action.key)}
                  />
                </View>
              ))}
            </View>
          ) : null}
        </>
      )}
    </Screen>
  )
}

export function NotesEditor({
  initialValue,
  onSave,
}: {
  initialValue?: string | null
  onSave: (notes: string) => void
}) {
  const { t, isRTL } = useLocale()
  const [notes, setNotes] = useState(initialValue || '')
  return (
    <Card tone="lilac">
      <Text style={[styles.factLabel, { textAlign: isRTL ? 'right' : 'left' }]}>
        {t('interviews.notes')}
      </Text>
      <TextInput
        value={notes}
        onChangeText={setNotes}
        multiline
        maxLength={2000}
        placeholder={t('interviews.notesPlaceholder')}
        placeholderTextColor={colors.faint}
        accessibilityLabel={t('interviews.notes')}
        style={[
          styles.notes,
          { textAlign: isRTL ? 'right' : 'left', writingDirection: isRTL ? 'rtl' : 'ltr' },
        ]}
      />
      <ActionButton label={t('common.save')} onPress={() => onSave(notes.trim())} disabled={!notes.trim()} />
    </Card>
  )
}

export function toneForStatus(status: string): StatusTone {
  const value = status.toLowerCase()
  if (['approved', 'complete', 'completed', 'resolved', 'sent', 'active'].some((key) => value.includes(key))) {
    return 'success'
  }
  if (['rejected', 'failed', 'missing', 'overdue', 'late'].some((key) => value.includes(key))) {
    return 'danger'
  }
  if (['pending', 'review', 'scheduled', 'requested'].some((key) => value.includes(key))) {
    return 'attention'
  }
  return 'info'
}

const styles = StyleSheet.create({
  stack: { gap: spacing.md },
  itemGroup: { gap: spacing.sm },
  itemActions: { gap: spacing.sm },
  fact: { gap: spacing.xs, borderBottomWidth: 1, borderBottomColor: colors.line, paddingBottom: spacing.md },
  factLabel: { color: colors.muted, fontSize: typography.label, fontWeight: '800' },
  factValue: { color: colors.ink, fontSize: typography.body, lineHeight: 22 },
  actionRow: { gap: spacing.md, flexWrap: 'wrap' },
  flex: { flex: 1, minWidth: 130 },
  notes: {
    minHeight: 112,
    color: colors.ink,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radius.md,
    padding: spacing.md,
    fontSize: typography.body,
    textAlignVertical: 'top',
  },
})
