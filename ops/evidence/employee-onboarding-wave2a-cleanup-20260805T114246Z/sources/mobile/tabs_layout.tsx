import { Tabs } from 'expo-router'
import Ionicons from '@expo/vector-icons/Ionicons'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { colors, radius, shadows } from '@/theme'

function TabIcon({
  name,
  focused,
  color,
}: {
  name: 'home' | 'mail' | 'calendar' | 'umbrella' | 'person'
  focused: boolean
  color: string
}) {
  const iconName = (focused ? name : `${name}-outline`) as keyof typeof Ionicons.glyphMap
  return <Ionicons name={iconName} size={21} color={color} />
}

export default function TabsLayout() {
  const { t } = useI18n()
  const { hasFeature } = useAuth()
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        title: '',
        headerTitle: '',
        tabBarHideOnKeyboard: true,
        tabBarActiveTintColor: colors.ink,
        tabBarInactiveTintColor: colors.subtle,
        tabBarLabelStyle: { fontSize: 10.5, fontWeight: '700', paddingBottom: 5 },
        tabBarStyle: {
          height: 72,
          paddingTop: 8,
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
        options={{ title: t('tabs.home'), tabBarIcon: ({ color, focused }) => <TabIcon name="home" focused={focused} color={color} /> }}
      />
      <Tabs.Screen
        name="notifications"
        options={{ title: t('tabs.notifications'), tabBarIcon: ({ color, focused }) => <TabIcon name="mail" focused={focused} color={color} /> }}
      />
      <Tabs.Screen
        name="shifts"
        options={{
          title: t('tabs.shifts'),
          href: hasFeature('shifts') ? undefined : null,
          tabBarIcon: ({ color, focused }) => <TabIcon name="calendar" focused={focused} color={color} />,
        }}
      />
      <Tabs.Screen
        name="leave"
        options={{
          title: t('tabs.leave'),
          href: hasFeature('leave') ? undefined : null,
          tabBarIcon: ({ color, focused }) => <TabIcon name="umbrella" focused={focused} color={color} />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{ title: t('tabs.profile'), tabBarIcon: ({ color, focused }) => <TabIcon name="person" focused={focused} color={color} /> }}
      />
    </Tabs>
  )
}
