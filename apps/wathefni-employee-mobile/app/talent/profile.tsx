import { useState } from 'react'
import { StyleSheet, TextInput, View } from 'react-native'

import { useAuth } from '@/auth/AuthProvider'
import { FeatureUnavailableState } from '@/components/AccessStates'
import { ErrorState, LoadingState } from '@/components/States'
import { PageScreen, PageScrollView } from '@/components/layout'
import { ListRow, PageBackButton, QuietEmpty } from '@/components/lists'
import { EditorialHeading, PremiumButton } from '@/components/premium'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { useAppQuery } from '@/lib/hooks'
import { HIGH_CHURN_STALE_MS } from '@/lib/employeeSoftRefresh'
import { colors, font, spacing } from '@/theme'

type Fact = { fact_id?: string; title_en?: string; dimension_kind?: string }
type Skill = { skill_id?: string; name_en?: string; skill_code?: string }
type Detail = { facts?: Fact[]; skills?: Skill[] }

export default function TalentProfileScreen() {
  const { t, isRTL } = useI18n()
  const { hasFeature, can, request } = useAuth()
  const enabled = hasFeature('talent')
  const query = useAppQuery<Detail>(['talent', 'profile'], '/app/talent/profile', {
    enabled,
    staleTime: HIGH_CHURN_STALE_MS,
  })
  const align = readingEdgeAlign(isRTL)
  const [title, setTitle] = useState('')
  const [skillCode, setSkillCode] = useState('')
  const [mobility, setMobility] = useState('')
  const [busy, setBusy] = useState(false)

  if (!enabled) return <FeatureUnavailableState feature="talent" />
  if (query.isLoading && !query.data) return <LoadingState />
  if (query.isError && !query.data) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  }

  const facts = query.data?.facts || []
  const skills = query.data?.skills || []

  return (
    <PageScreen>
      <PageScrollView gap={spacing.xl} refreshing={query.isFetching} onRefresh={() => void query.refetch()}>
        <PageBackButton />
        <EditorialHeading>{t('talent.profile')}</EditorialHeading>
        {facts.length === 0 ? <QuietEmpty title={t('talent.emptyAspirations')} /> : null}
        {facts.map((row) => (
          <ListRow key={String(row.fact_id)} title={row.title_en || t('talent.aspirations')} subtitle={row.dimension_kind} />
        ))}
        {skills.length === 0 ? <QuietEmpty title={t('talent.emptySkills')} /> : null}
        {skills.map((row) => (
          <ListRow key={String(row.skill_id)} title={row.name_en || row.skill_code || t('talent.skills')} />
        ))}
        {can('talent', 'update') ? (
          <View style={styles.update}>
            <TextInput
              value={title}
              onChangeText={setTitle}
              placeholder={t('talent.aspirations')}
              placeholderTextColor={colors.navMuted}
              style={[styles.input, align, { writingDirection: isRTL ? 'rtl' : 'ltr' }]}
            />
            <PremiumButton
              label={t('talent.save')}
              disabled={busy || !title.trim()}
              busy={busy}
              onPress={async () => {
                setBusy(true)
                try {
                  await request('/app/talent/aspirations', { method: 'POST', json: { title_en: title } })
                  setTitle('')
                  await query.refetch()
                } finally {
                  setBusy(false)
                }
              }}
            />
            <TextInput
              value={skillCode}
              onChangeText={setSkillCode}
              placeholder={t('talent.skillCode')}
              placeholderTextColor={colors.navMuted}
              style={[styles.input, align, { writingDirection: isRTL ? 'rtl' : 'ltr' }]}
            />
            <PremiumButton
              label={t('talent.skills')}
              disabled={busy || !skillCode.trim()}
              busy={busy}
              onPress={async () => {
                setBusy(true)
                try {
                  await request('/app/talent/skills', {
                    method: 'POST',
                    json: { skill_code: skillCode, name_en: skillCode },
                  })
                  setSkillCode('')
                  await query.refetch()
                } finally {
                  setBusy(false)
                }
              }}
            />
            <TextInput
              value={mobility}
              onChangeText={setMobility}
              placeholder={t('talent.mobility')}
              placeholderTextColor={colors.navMuted}
              style={[styles.input, align, { writingDirection: isRTL ? 'rtl' : 'ltr' }]}
            />
            <PremiumButton
              label={t('talent.mobility')}
              disabled={busy || !mobility.trim()}
              busy={busy}
              onPress={async () => {
                setBusy(true)
                try {
                  await request('/app/talent/mobility', { method: 'POST', json: { title_en: mobility } })
                  setMobility('')
                  await query.refetch()
                } finally {
                  setBusy(false)
                }
              }}
            />
          </View>
        ) : null}
      </PageScrollView>
    </PageScreen>
  )
}

const styles = StyleSheet.create({
  update: { gap: spacing.sm },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    color: colors.text,
    fontSize: font.body,
  },
})
