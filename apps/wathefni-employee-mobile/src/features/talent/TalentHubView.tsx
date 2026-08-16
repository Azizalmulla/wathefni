import { Pressable, StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'

import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, PageBackButton, QuietEmpty } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, spacing, typeScaling } from '@/theme'

type HubProps = {
  facts: number
  skills: number
  mobility: number
  refreshing?: boolean
  onRefresh?: () => void
}

export function TalentHubView({ facts, skills, mobility, refreshing, onRefresh }: HubProps) {
  const router = useRouter()
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const empty = facts + skills + mobility === 0

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl} refreshing={refreshing} onRefresh={onRefresh}>
        <PageBackButton />
        <FadeIn>
          <EditorialHeading>{t('talent.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('talent.subtitle')}
          </Text>
        </FadeIn>
        {empty ? <QuietEmpty title={t('talent.empty')} /> : null}
        <View>
          <Pressable onPress={() => router.push('/talent/profile')}>
            <ListRow title={t('talent.profile')} subtitle={String(facts + skills + mobility)} icon="person-outline" showChevron />
          </Pressable>
        </View>
        <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.hint, align]}>
          {t('talent.hiddenJudgments')}
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
  hint: {
    color: colors.textSecondary,
    fontSize: font.caption,
  },
})
