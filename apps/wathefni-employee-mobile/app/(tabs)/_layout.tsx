import { Tabs } from 'expo-router'
import { Text } from 'react-native'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { colors, font, radius, shadows } from '@/theme'

// Lightweight text glyph tab icons (no extra icon dependency for V1).
function TabIcon({ glyph, color }: { glyph: string; color: string }) {
  return <Text style={{ fontSize: 18, color }}>{glyph}</Text>
}

export default function TabsLayout() {
  const { t } = useI18n()
  const { hasFeature } = useAuth()
  return (
    <Tabs
      screenOptions={{
        headerShown: true,
        headerStyle: { backgroundColor: colors.bg },
        headerShadowVisible: false,
        headerTitleStyle: { color: colors.text, fontWeight: '700', fontSize: font.h3 },
        tabBarActiveTintColor: colors.ink,
        tabBarInactiveTintColor: colors.subtle,
        tabBarLabelStyle: { fontSize: 11, fontWeight: '600', paddingBottom: 4 },
        tabBarStyle: {
          height: 68,
          paddingTop: 7,
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          borderTopLeftRadius: radius.xl,
          borderTopRightRadius: radius.xl,
          ...shadows.card,
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: t('tabs.home'), headerShown: false, tabBarIcon: ({ color }) => <TabIcon glyph="⌂" color={color} /> }}
      />
      <Tabs.Screen
        name="notifications"
        options={{ title: t('tabs.notifications'), tabBarIcon: ({ color }) => <TabIcon glyph="✉" color={color} /> }}
      />
      <Tabs.Screen
        name="shifts"
        options={{
          title: t('tabs.shifts'),
          href: hasFeature('shifts') ? undefined : null,
          tabBarIcon: ({ color }) => <TabIcon glyph="◷" color={color} />,
        }}
      />
      <Tabs.Screen
        name="leave"
        options={{
          title: t('tabs.leave'),
          href: hasFeature('leave') ? undefined : null,
          tabBarIcon: ({ color }) => <TabIcon glyph="✈" color={color} />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{ title: t('tabs.profile'), tabBarIcon: ({ color }) => <TabIcon glyph="☻" color={color} /> }}
      />
    </Tabs>
  )
}
