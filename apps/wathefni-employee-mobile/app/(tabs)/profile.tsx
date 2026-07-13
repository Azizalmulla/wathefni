import { ScrollView, StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { Button, Card, Row, SectionTitle } from '@/components/ui'
import { colors, font, radius, spacing } from '@/theme'

export default function ProfileScreen() {
  const { t } = useI18n()
  const { profile, signOut } = useAuth()
  const router = useRouter()
  const initials = (profile?.name || '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('')

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Card tone="accent" style={styles.hero}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>{initials || 'W'}</Text>
        </View>
        <View style={styles.identity}>
          <Text style={styles.name}>{profile?.name}</Text>
          {profile?.position_title ? <Text style={styles.muted}>{profile.position_title}</Text> : null}
        </View>
      </Card>

      <SectionTitle>{t('profile.details')}</SectionTitle>
      <Card>
        {profile?.position_title ? <Row label={t('profile.position')} value={profile.position_title} /> : null}
        {profile?.department ? <Row label={t('profile.department')} value={profile.department} /> : null}
        <Row label={t('profile.company')} value={profile?.company_code ?? '—'} />
        <Row label={t('profile.phone')} value={profile?.phone ?? '—'} />
      </Card>

      <SectionTitle>{t('profile.account')}</SectionTitle>
      <Button label={t('settings.title')} variant="secondary" onPress={() => router.push('/settings')} />
      <Button label={t('auth.signOut')} variant="secondary" onPress={() => void signOut()} />
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.lg, paddingBottom: spacing.xxxl, gap: spacing.md },
  hero: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg, padding: spacing.xl },
  avatar: {
    width: 60,
    height: 60,
    borderRadius: radius.pill,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { color: colors.primaryText, fontSize: font.h2, fontWeight: '800' },
  identity: { flex: 1, gap: spacing.xs },
  name: { fontSize: font.h1, fontWeight: '800', color: colors.text },
  muted: { fontSize: font.body, color: colors.subtle },
})
