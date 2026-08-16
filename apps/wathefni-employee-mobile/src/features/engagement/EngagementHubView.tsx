import { Pressable, StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'

import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, PageBackButton, QuietEmpty } from '@/components/lists'
import { EditorialHeading, FadeIn } from '@/components/premium'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, spacing, typeScaling } from '@/theme'

type Survey = {
  campaign_id?: string
  title_en?: string
  title_ar?: string
  privacy_mode?: string
  privacy_mode_label_en?: string
  privacy_mode_label_ar?: string
  anonymous?: boolean
  identified?: boolean
  participation_status?: string
  state?: string
}

type HubProps = {
  surveys: Survey[]
  refreshing?: boolean
  onRefresh?: () => void
}

export function EngagementHubView({ surveys, refreshing, onRefresh }: HubProps) {
  const router = useRouter()
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const titleOf = (row: Survey) =>
    isRTL ? row.title_ar || row.title_en || t('engagement.survey') : row.title_en || row.title_ar || t('engagement.survey')
  const open = surveys.filter((row) => row.state === 'open')
  const submitted = surveys.filter((row) => row.state === 'submitted')
  const closed = surveys.filter((row) => row.state === 'closed')

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl} refreshing={refreshing} onRefresh={onRefresh}>
        <PageBackButton />
        <FadeIn>
          <EditorialHeading>{t('engagement.title')}</EditorialHeading>
          <Text style={[styles.sub, align]}>{t('engagement.subtitle')}</Text>
        </FadeIn>
        {surveys.length === 0 ? <QuietEmpty title={t('engagement.empty')} /> : null}
        <View>
          <Text style={[styles.section, align]}>{t('engagement.open')}</Text>
          {open.length === 0 ? <QuietEmpty title={t('engagement.emptyOpen')} /> : null}
          {open.map((row) => (
            <Pressable
              key={String(row.campaign_id)}
              onPress={() => router.push({ pathname: '/engagement/survey', params: { campaign_id: String(row.campaign_id) } })}
            >
              <ListRow
                title={titleOf(row)}
                subtitle={isRTL ? row.privacy_mode_label_ar : row.privacy_mode_label_en}
                showChevron
              />
            </Pressable>
          ))}
        </View>
        <View>
          <Text style={[styles.section, align]}>{t('engagement.submitted')}</Text>
          {submitted.length === 0 ? <QuietEmpty title={t('engagement.emptySubmitted')} /> : null}
          {submitted.map((row) => (
            <ListRow key={String(row.campaign_id)} title={titleOf(row)} subtitle={t('engagement.submitted')} />
          ))}
        </View>
        <View>
          <Text style={[styles.section, align]}>{t('engagement.closed')}</Text>
          {closed.length === 0 ? <QuietEmpty title={t('engagement.emptyClosed')} /> : null}
          {closed.map((row) => (
            <ListRow key={String(row.campaign_id)} title={titleOf(row)} subtitle={t('engagement.closed')} />
          ))}
        </View>
        <Text style={[styles.bound, align]}>{t('engagement.boundaries')}</Text>
      </PageScrollView>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  sub: { ...font.body, fontSize: typeScaling.meta, color: colors.textSecondary, marginTop: spacing.sm },
  section: { ...font.subtitle, marginBottom: spacing.sm },
  bound: { ...font.body, fontSize: typeScaling.meta, color: colors.textSecondary },
})
