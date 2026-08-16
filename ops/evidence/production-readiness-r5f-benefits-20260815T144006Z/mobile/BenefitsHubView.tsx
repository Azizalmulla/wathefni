import { Pressable, StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'

import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, PageBackButton, QuietEmpty } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, spacing, typeScaling } from '@/theme'

type Plan = { plan_id?: string; title_en?: string; title_ar?: string; code?: string; status?: string }
type Enrollment = {
  enrollment_id?: string
  plan_id?: string
  title_en?: string
  title_ar?: string
  status?: string
  elected?: boolean
  waived?: boolean
  coverage_active?: boolean
}
type Coverage = {
  coverage_id?: string
  plan_id?: string
  title_en?: string
  title_ar?: string
  status?: string
  start_date?: string
  provider_confirmed?: boolean
}

type HubProps = {
  plans: Plan[]
  enrollments: Enrollment[]
  coverage: Coverage[]
  refreshing?: boolean
  onRefresh?: () => void
}

export function BenefitsHubView({ plans, enrollments, coverage, refreshing, onRefresh }: HubProps) {
  const router = useRouter()
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const titleOf = (row: { title_en?: string; title_ar?: string; code?: string }) =>
    isRTL ? row.title_ar || row.title_en || row.code || '' : row.title_en || row.title_ar || row.code || ''
  const empty = plans.length + enrollments.length + coverage.length === 0

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl} refreshing={refreshing} onRefresh={onRefresh}>
        <PageBackButton />
        <FadeIn>
          <EditorialHeading>{t('benefits.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('benefits.subtitle')}
          </Text>
        </FadeIn>
        {empty ? <QuietEmpty title={t('benefits.empty')} /> : null}
        <View>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.section, align]}>
            {t('benefits.eligible')}
          </Text>
          {plans.length === 0 ? <QuietEmpty title={t('benefits.emptyPlans')} /> : null}
          {plans.map((plan) => (
            <Pressable
              key={String(plan.plan_id)}
              onPress={() => router.push({ pathname: '/benefits/plan', params: { plan_id: String(plan.plan_id) } })}
            >
              <ListRow title={titleOf(plan)} subtitle={plan.code} icon="heart-outline" showChevron />
            </Pressable>
          ))}
        </View>
        <View>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.section, align]}>
            {t('benefits.enrolled')}
          </Text>
          {enrollments.map((row) => (
            <Pressable
              key={String(row.enrollment_id)}
              onPress={() =>
                row.plan_id
                  ? router.push({ pathname: '/benefits/plan', params: { plan_id: String(row.plan_id) } })
                  : undefined
              }
            >
              <ListRow
                title={titleOf(row)}
                subtitle={[
                  row.coverage_active ? t('benefits.coverageActive') : row.waived ? t('benefits.waived') : row.elected ? t('benefits.enrolled') : String(row.status || ''),
                ].join(' · ')}
                showChevron={Boolean(row.plan_id)}
              />
            </Pressable>
          ))}
        </View>
        <View>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.section, align]}>
            {t('benefits.coverage')}
          </Text>
          {coverage.length === 0 ? <QuietEmpty title={t('benefits.emptyCoverage')} /> : null}
          {coverage.map((row) => (
            <ListRow
              key={String(row.coverage_id)}
              title={titleOf(row)}
              subtitle={[
                row.start_date ? `${t('benefits.effectiveFrom')} ${row.start_date}` : '',
                row.provider_confirmed ? t('benefits.providerConfirmed') : t('benefits.internalOnly'),
              ]
                .filter(Boolean)
                .join(' · ')}
            />
          ))}
        </View>
        <Pressable onPress={() => router.push('/benefits/history')}>
          <ListRow title={t('benefits.history')} icon="time-outline" showChevron />
        </Pressable>
        <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.hint, align]}>
          {t('benefits.boundaries')}
        </Text>
      </PageScrollView>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  subtitle: {
    marginTop: spacing.sm,
    color: colors.textSecondary,
    fontSize: font.body,
  },
  section: {
    marginBottom: spacing.sm,
    color: colors.textSecondary,
    fontSize: font.caption,
  },
  hint: {
    color: colors.textSecondary,
    fontSize: font.caption,
  },
})
