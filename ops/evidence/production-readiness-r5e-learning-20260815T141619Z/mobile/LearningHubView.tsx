import { Pressable, StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'

import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, PageBackButton, QuietEmpty } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, spacing, typeScaling } from '@/theme'

type HubProps = {
  required: number
  assigned: number
  upcoming: number
  completed: number
  certificates: number
  catalog: number
  refreshing?: boolean
  onRefresh?: () => void
}

export function LearningHubView({
  required,
  assigned,
  upcoming,
  completed,
  certificates,
  catalog,
  refreshing,
  onRefresh,
}: HubProps) {
  const router = useRouter()
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const empty = required + assigned + upcoming + completed + certificates === 0

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl} refreshing={refreshing} onRefresh={onRefresh}>
        <PageBackButton />
        <FadeIn>
          <EditorialHeading>{t('learning.title')}</EditorialHeading>
          <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
            {t('learning.subtitle')}
          </Text>
        </FadeIn>
        {empty ? <QuietEmpty title={t('learning.empty')} /> : null}
        <View>
          <ListRow title={t('learning.required')} subtitle={String(required)} icon="alert-circle-outline" />
          <ListRow title={t('learning.assigned')} subtitle={String(assigned)} icon="clipboard-outline" />
          <ListRow title={t('learning.upcoming')} subtitle={String(upcoming)} icon="calendar-outline" />
          <ListRow title={t('learning.completed')} subtitle={String(completed)} icon="checkmark-circle-outline" />
          <Pressable onPress={() => router.push('/learning/catalog')}>
            <ListRow title={t('learning.catalog')} subtitle={String(catalog)} icon="library-outline" showChevron />
          </Pressable>
          <Pressable onPress={() => router.push('/learning/certificates')}>
            <ListRow title={t('learning.certificates')} subtitle={String(certificates)} icon="ribbon-outline" showChevron />
          </Pressable>
        </View>
        <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.hint, align]}>
          {t('learning.boundaries')}
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
