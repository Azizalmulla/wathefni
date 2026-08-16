import { StyleSheet, Text, View } from 'react-native'

import type { MobileMe, PrioritiesResponse } from '@/api/types'
import { destinationAvailable, enabledWorkspaces, workspaceRoutes } from '@/capabilities'
import { useLocale } from '@/i18n'
import { formatDate, formatDateRange } from '@/i18n/date'
import {
  ActionableCard,
  EditorialHeading,
  FadeIn,
  PriorityCard,
  Screen,
  Skeleton,
  StatePanel,
  StatusBadge,
  WorkspaceHeader,
} from '@/components/primitives'
import { colors, spacing, type as typography } from '@/theme'

export type HomeState =
  | 'ready'
  | 'loading'
  | 'empty'
  | 'error'
  | 'offline'
  | 'revoked'
  | 'permission'
  | 'session_expired'
  | 'company_disabled'
  | 'company_archived'
  | 'stale'
  | 'success'

export function HRHomeView({
  me,
  priorities,
  state = 'ready',
  onOpen,
  onRetry,
  onLocale,
}: {
  me: MobileMe
  priorities: PrioritiesResponse
  state?: HomeState
  onOpen?: (destination: string) => void
  onRetry?: () => void
  onLocale?: () => void
}) {
  const { t, isRTL, locale } = useLocale()
  const workspaces = enabledWorkspaces(me)
  const routes = workspaceRoutes(me)
  const visibleSections = priorities.sections
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => destinationAvailable(me, item.destination)),
      total: section.items.filter((item) => destinationAvailable(me, item.destination)).length,
    }))
    .filter((section) => section.items.length > 0)
  const scopeLabel = me.scope.restricted ? t('home.scopeRestricted') : t('home.scopeCompany')

  return (
    <Screen>
      <WorkspaceHeader company={me.principal.company_code} scopeLabel={scopeLabel} onLocale={onLocale} />
      <FadeIn>
        <EditorialHeading eyebrow={t('home.eyebrow')}>{t('home.title')}</EditorialHeading>
      </FadeIn>

      <View style={[styles.workspaceRow, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
        {workspaces.map((workspace) => (
          <StatusBadge
            key={workspace}
            label={workspace === 'hr' ? t('home.workspace.hr') : workspace === 'recruiting' ? t('home.workspace.recruiting') : 'Owner'}
            tone={workspace === 'recruiting' ? 'info' : 'success'}
          />
        ))}
      </View>

      <View style={styles.navigation}>
        {routes.map((route) => (
          <ActionableCard
            key={route.key}
            title={t(navKeys[route.key as keyof typeof navKeys])}
            subtitle={route.workspace === 'hr' ? t('home.workspace.hr') : t('home.workspace.recruiting')}
            onPress={onOpen ? () => onOpen(route.path) : undefined}
          />
        ))}
        <ActionableCard
          title={t('nav.settings')}
          subtitle={t('settings.subtitle')}
          onPress={onOpen ? () => onOpen('/settings') : undefined}
        />
      </View>

      {state === 'loading' ? (
        <View style={styles.stack}>
          <Skeleton lines={4} />
          <Skeleton lines={3} />
          <Skeleton lines={4} />
        </View>
      ) : state === 'error' ? (
        <StatePanel title={t('state.errorTitle')} body={t('state.errorBody')} action={t('common.retry')} onAction={onRetry} icon="cloud-offline-outline" />
      ) : state === 'offline' ? (
        <StatePanel title={t('state.offlineTitle')} body={t('state.offlineBody')} action={t('common.retry')} onAction={onRetry} icon="cloud-offline-outline" />
      ) : state === 'permission' ? (
        <StatePanel title={t('state.permissionTitle')} body={t('state.permissionBody')} action={t('common.retry')} onAction={onRetry} icon="shield-outline" />
      ) : state === 'revoked' ? (
        <StatePanel title={t('state.revokedTitle')} body={t('state.revokedBody')} action={t('common.retry')} onAction={onRetry} icon="lock-closed-outline" />
      ) : state === 'company_disabled' ? (
        <StatePanel title={t('state.companyDisabledTitle')} body={t('state.companyDisabledBody')} icon="business-outline" />
      ) : state === 'company_archived' ? (
        <StatePanel title={t('state.companyArchivedTitle')} body={t('state.companyArchivedBody')} icon="archive-outline" />
      ) : state === 'session_expired' ? (
        <StatePanel title={t('state.sessionExpiredTitle')} body={t('state.sessionExpiredBody')} icon="time-outline" />
      ) : state === 'stale' ? (
        <StatePanel title={t('state.staleTitle')} body={t('state.staleBody')} action={t('common.retry')} onAction={onRetry} icon="refresh-circle-outline" />
      ) : state === 'success' ? (
        <StatePanel title={t('state.successTitle')} body={t('state.successBody')} icon="checkmark-done-circle-outline" />
      ) : state === 'empty' || visibleSections.length === 0 ? (
        <StatePanel title={t('home.clear')} body={t('home.clearBody')} icon="checkmark-circle-outline" />
      ) : (
        <View style={styles.stack}>
          {visibleSections
            .map((section, sectionIndex) => (
              <FadeIn key={section.type} delay={sectionIndex * 45}>
                <View style={styles.section}>
                  <View style={[styles.sectionTitleRow, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
                    <Text style={[styles.sectionTitle, { textAlign: isRTL ? 'right' : 'left' }]}>{section.title}</Text>
                    <Text style={styles.sectionCount}>{section.total}</Text>
                  </View>
                  {section.items.map((item) => (
                    <PriorityCard
                      key={`${item.type}-${item.target_id}`}
                      title={section.title}
                      summary={item.summary}
                      status={item.status}
                      severity={item.severity}
                      meta={formatDue(item.due_context, locale)}
                      onPress={onOpen ? () => onOpen(item.destination) : undefined}
                    />
                  ))}
                </View>
              </FadeIn>
            ))}
        </View>
      )}
    </Screen>
  )
}

function formatDue(value: Record<string, unknown> | null, locale: 'en' | 'ar'): string | null {
  if (!value) return null
  if (typeof value.start_date === 'string' || typeof value.end_date === 'string') {
    return formatDateRange(
      typeof value.start_date === 'string' ? value.start_date : null,
      typeof value.end_date === 'string' ? value.end_date : null,
      locale,
    )
  }
  if (typeof value.date === 'string') return formatDate(value.date, locale)
  if (value.suggested_action) return String(value.suggested_action)
  return null
}

const styles = StyleSheet.create({
  workspaceRow: { flexWrap: 'wrap', gap: spacing.sm },
  navigation: { gap: spacing.md },
  stack: { gap: spacing.xl },
  section: { gap: spacing.md },
  sectionTitleRow: { alignItems: 'center', justifyContent: 'space-between' },
  sectionTitle: { color: colors.ink, fontSize: typography.section, fontWeight: '800' },
  sectionCount: { color: colors.plum, backgroundColor: colors.plumSoft, minWidth: 30, textAlign: 'center', paddingVertical: 5, paddingHorizontal: 9, borderRadius: 999, fontWeight: '900' },
})

const navKeys = {
  tasks: 'nav.tasks',
  leave: 'nav.leave',
  onboarding: 'nav.onboarding',
  documents: 'nav.documents',
  attendance: 'nav.attendance',
  shifts: 'nav.shifts',
  employees: 'nav.employees',
  deliveryAlerts: 'nav.deliveryAlerts',
  candidates: 'nav.candidates',
  interviews: 'nav.interviews',
} as const
