import { StyleSheet, Text, View } from 'react-native'

import type { MobileMe, PrioritiesResponse } from '@/api/types'
import { enabledWorkspaces } from '@/capabilities'
import { useLocale } from '@/i18n'
import {
  Card,
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

export type HomeState = 'ready' | 'loading' | 'empty' | 'error' | 'revoked' | 'company_disabled'

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
  const { t, isRTL } = useLocale()
  const workspaces = enabledWorkspaces(me)
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

      {state === 'loading' ? (
        <View style={styles.stack}>
          <Skeleton lines={4} />
          <Skeleton lines={3} />
          <Skeleton lines={4} />
        </View>
      ) : state === 'error' ? (
        <StatePanel title={t('state.errorTitle')} body={t('state.errorBody')} action={t('common.retry')} onAction={onRetry} icon="cloud-offline-outline" />
      ) : state === 'revoked' ? (
        <StatePanel title={t('state.revokedTitle')} body={t('state.revokedBody')} action={t('common.retry')} onAction={onRetry} icon="lock-closed-outline" />
      ) : state === 'company_disabled' ? (
        <StatePanel title={t('state.companyDisabledTitle')} body={t('state.companyDisabledBody')} icon="business-outline" />
      ) : state === 'empty' || priorities.sections.every((section) => section.items.length === 0) ? (
        <StatePanel title={t('home.clear')} body={t('home.clearBody')} icon="checkmark-circle-outline" />
      ) : (
        <View style={styles.stack}>
          {priorities.sections
            .filter((section) => section.items.length > 0)
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
                      meta={formatDue(item.due_context)}
                      onPress={onOpen ? () => onOpen(item.destination) : undefined}
                    />
                  ))}
                </View>
              </FadeIn>
            ))}
          <Card tone="lilac">
            <Text style={[styles.policyTitle, { textAlign: isRTL ? 'right' : 'left' }]}>Calm by design</Text>
            <Text style={[styles.policyBody, { textAlign: isRTL ? 'right' : 'left' }]}>
              Priorities stay in authoritative sections. Wathefni HR does not invent urgency or combine unrelated work into an opaque score.
            </Text>
          </Card>
        </View>
      )}
    </Screen>
  )
}

function formatDue(value: Record<string, unknown> | null): string | null {
  if (!value) return null
  if (value.start_date && value.end_date) return `${value.start_date} — ${value.end_date}`
  if (value.date) return String(value.date)
  if (value.suggested_action) return String(value.suggested_action)
  return null
}

const styles = StyleSheet.create({
  workspaceRow: { flexWrap: 'wrap', gap: spacing.sm },
  stack: { gap: spacing.xl },
  section: { gap: spacing.md },
  sectionTitleRow: { alignItems: 'center', justifyContent: 'space-between' },
  sectionTitle: { color: colors.ink, fontSize: typography.section, fontWeight: '800' },
  sectionCount: { color: colors.plum, backgroundColor: colors.plumSoft, minWidth: 30, textAlign: 'center', paddingVertical: 5, paddingHorizontal: 9, borderRadius: 999, fontWeight: '900' },
  policyTitle: { color: colors.ink, fontSize: typography.body, fontWeight: '800' },
  policyBody: { color: colors.muted, fontSize: typography.label, lineHeight: 19 },
})
