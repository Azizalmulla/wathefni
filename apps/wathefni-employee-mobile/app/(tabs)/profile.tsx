import { ScrollView, StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { Button, Card, Row } from '@/components/ui'
import { colors, font, spacing } from '@/theme'

export default function ProfileScreen() {
  const { t } = useI18n()
  const { profile, signOut } = useAuth()
  const router = useRouter()

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Card>
        <Text style={styles.name}>{profile?.name}</Text>
        {profile?.position_title ? <Text style={styles.muted}>{profile.position_title}</Text> : null}
      </Card>

      <Card>
        {profile?.position_title ? <Row label={t('profile.position')} value={profile.position_title} /> : null}
        {profile?.department ? <Row label={t('profile.department')} value={profile.department} /> : null}
        <Row label={t('profile.company')} value={profile?.company_code ?? '—'} />
        <Row label={t('profile.phone')} value={profile?.phone ?? '—'} />
      </Card>

      <Button label={t('settings.title')} variant="secondary" onPress={() => router.push('/settings')} />
      <Button label={t('auth.signOut')} variant="secondary" onPress={() => void signOut()} />
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.lg, gap: spacing.md },
  name: { fontSize: font.h1, fontWeight: '800', color: colors.text },
  muted: { fontSize: font.body, color: colors.subtle },
})
