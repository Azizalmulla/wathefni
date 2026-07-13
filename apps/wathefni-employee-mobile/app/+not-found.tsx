import { StyleSheet, Text, View } from 'react-native'
import { useRouter } from 'expo-router'

import { useI18n } from '@/i18n'
import { Button } from '@/components/ui'
import { colors, font, spacing } from '@/theme'

export default function NotFoundScreen() {
  const { t } = useI18n()
  const router = useRouter()
  return (
    <View style={styles.screen}>
      <Text style={styles.title}>{t('notFound.title')}</Text>
      <Text style={styles.message}>{t('notFound.message')}</Text>
      <Button label={t('feature.backHome')} onPress={() => router.replace('/(tabs)')} />
    </View>
  )
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.md,
    padding: spacing.xl,
    backgroundColor: colors.bg,
  },
  title: { fontSize: font.h2, fontWeight: '700', color: colors.text, textAlign: 'center' },
  message: { fontSize: font.body, color: colors.subtle, textAlign: 'center' },
})
