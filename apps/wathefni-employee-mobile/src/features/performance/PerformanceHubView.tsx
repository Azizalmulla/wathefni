import { Pressable, StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'

import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, PageBackButton, QuietEmpty } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, spacing, typeScaling } from '@/theme'

type HubProps = {
  goals: number
  reviews: number
  checkIns: number
  development: number
  okrCycleName?: string | null
  refreshing?: boolean
  onRefresh?: () => void
}

export function PerformanceHubView({
  goals,
  reviews,
  checkIns,
  development,
  okrCycleName,
  refreshing,
  onRefresh,
}: HubProps) {
  const router = useRouter()
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const empty = goals + reviews + checkIns + development === 0

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl} refreshing={refreshing} onRefresh={onRefresh}>
        <PageBackButton />
        <FadeIn>
          <EditorialHeading>{t('performance.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('performance.subtitle')}
          </Text>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {okrCycleName ? `${t('performance.okrCycle')}: ${okrCycleName}` : t('performance.noOkrCycle')}
          </Text>
        </FadeIn>
        {empty ? <QuietEmpty title={t('performance.empty')} /> : null}
        <View>
          <Pressable onPress={() => router.push('/performance/goals')}>
            <ListRow title={t('performance.goals')} subtitle={String(goals)} icon="flag-outline" showChevron />
          </Pressable>
          <Pressable onPress={() => router.push('/performance/reviews')}>
            <ListRow title={t('performance.reviews')} subtitle={String(reviews)} icon="create-outline" showChevron />
          </Pressable>
          <Pressable onPress={() => router.push('/performance/check-ins')}>
            <ListRow title={t('performance.checkIns')} subtitle={String(checkIns)} icon="chatbubble-ellipses-outline" showChevron />
          </Pressable>
          <Pressable onPress={() => router.push('/performance/development')}>
            <ListRow title={t('performance.development')} subtitle={String(development)} icon="leaf-outline" showChevron />
          </Pressable>
        </View>
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
})
