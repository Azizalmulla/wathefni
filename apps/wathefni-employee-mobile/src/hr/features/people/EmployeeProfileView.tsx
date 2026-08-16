import { StyleSheet, Text, View } from 'react-native'

import type { EmployeeSummary } from '@hr/api/types'
import type { ResourceState } from '@hr/api/state'
import {
  employmentStatusTone,
  localizeEmploymentStatus,
} from '@hr/features/people/employeeComposition'
import { formatDate } from '@hr/i18n/date'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, SectionHeader } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, radius, scheduleComposition, spacing, typeScaling } from '@/theme'

export type EmployeeProfileViewState = ResourceState | 'not_found' | 'unavailable'

/** Unboxed fact — typography only, no surface cards. */
function Fact({ label, value }: { label: string; value?: string | null }) {
  const { isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  if (!value) return null
  return (
    <View style={styles.fact}>
      <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.factLabel, align]}>
        {label}
      </Text>
      <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.factValue, align]}>
        {value}
      </Text>
    </View>
  )
}

function composeLead(position?: string | null, department?: string | null): string | null {
  const parts = [String(position || '').trim(), String(department || '').trim()].filter(Boolean)
  if (!parts.length) return null
  return parts.join(' · ')
}

/**
 * HR Employee quick profile — cream Editorial Entity Detail prototype (facts-only, not E360).
 * One Wathefni accent moment (People blue identity dot); filled status chips — no brown outline.
 */
export function EmployeeProfileView({
  employee,
  state = 'ready',
  onRetry,
  onBack,
}: {
  employee: EmployeeSummary | null
  state?: EmployeeProfileViewState
  onRetry?: () => void
  onBack?: () => void
}) {
  const { t, isRTL, locale } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const appLocale = locale === 'ar' ? 'ar' : 'en'
  const status = employee?.employee.employment_status
  const name = employee?.employee.name
  const lead =
    state === 'ready' && employee
      ? composeLead(employee.employee.position_title, employee.employee.department)
      : null
  const email = employee?.email
  const phone = employee?.phone
  const started = employee?.started_on ? formatDate(employee.started_on, appLocale) : null
  const hasContact = Boolean(email || phone)
  const hasTenure = Boolean(started)

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl}>
        <HrPushedNav onBack={onBack || (() => undefined)} accessibilityLabel={t('common.back')} />

        <FadeIn style={styles.hero}>
          <View style={[styles.eyebrowRow, isRTL ? styles.eyebrowRowRtl : null]}>
            <View
              style={[styles.accentDot, { backgroundColor: scheduleComposition.planned.fill }]}
              accessibilityElementsHidden
            />
            <Text maxFontSizeMultiplier={typeScaling.chip} style={[styles.eyebrow, align]}>
              {t('hrEmployee.eyebrow')}
            </Text>
          </View>
          <EditorialHeading>
            {state === 'ready' && name ? name : t('hrEmployee.title')}
          </EditorialHeading>
          {state === 'ready' && status ? (
            <StatusChip
              label={localizeEmploymentStatus(status, t)}
              tone={employmentStatusTone(status)}
            />
          ) : null}
          {lead ? (
            <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.lead, align]}>
              {lead}
            </Text>
          ) : null}
        </FadeIn>

        {state === 'loading' ? <ListRow title={t('home.dataLoading')} icon="hourglass-outline" /> : null}

        {state === 'permission' ? (
          <ListRow title={t('hrEmployee.permissionTitle')} subtitle={t('hrEmployee.permissionBody')} />
        ) : null}

        {state === 'unavailable' ? (
          <ListRow
            title={t('hrEmployee.unavailableTitle')}
            subtitle={t('hrEmployee.unavailableBody')}
            icon="person-outline"
          />
        ) : null}

        {state === 'not_found' ? (
          <ListRow
            title={t('hrEmployee.notFoundTitle')}
            subtitle={t('hrEmployee.notFoundBody')}
            icon="search-outline"
            showChevron={Boolean(onRetry)}
            onPress={onRetry}
          />
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

        {state === 'stale' ? (
          <ListRow
            title={t('hrEmployee.staleTitle')}
            subtitle={t('hrEmployee.staleBody')}
            emphasis="warning"
            showChevron
            onPress={onRetry}
          />
        ) : null}

        {state === 'ready' && employee ? (
          <View style={styles.groups}>
            {hasContact ? (
              <View style={styles.group}>
                <SectionHeader title={t('hrEmployee.sectionContact')} />
                <Fact label={t('common.email')} value={email} />
                <Fact label={t('common.phone')} value={phone} />
              </View>
            ) : null}
            {hasTenure ? (
              <View style={styles.group}>
                <SectionHeader title={t('hrEmployee.sectionTenure')} />
                <Fact label={t('common.startDate')} value={started} />
              </View>
            ) : null}
            {!hasContact && !hasTenure ? (
              <View style={styles.group}>
                <SectionHeader title={t('hrEmployee.sectionFacts')} />
                <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.quietEmpty, align]}>
                  {t('hrEmployee.factsEmpty')}
                </Text>
              </View>
            ) : null}
          </View>
        ) : null}
      </PageScrollView>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  hero: { gap: spacing.sm },
  eyebrowRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  eyebrowRowRtl: { flexDirection: 'row-reverse' },
  accentDot: {
    width: 8,
    height: 8,
    borderRadius: radius.pill,
  },
  eyebrow: {
    color: colors.subtle,
    fontSize: font.tiny,
    fontWeight: '700',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  lead: {
    color: colors.ink,
    fontSize: font.h3,
    fontWeight: '600',
    lineHeight: 26,
    marginTop: spacing.xs,
    maxWidth: 360,
  },
  groups: { gap: spacing.xxl },
  group: { gap: spacing.md },
  fact: { gap: 2 },
  factLabel: {
    color: colors.subtle,
    fontSize: font.tiny,
    fontWeight: '600',
    letterSpacing: 0.2,
  },
  factValue: {
    color: colors.ink,
    fontSize: font.body,
    fontWeight: '600',
    lineHeight: 22,
  },
  quietEmpty: { color: colors.subtle, fontSize: font.small, lineHeight: 20 },
})
