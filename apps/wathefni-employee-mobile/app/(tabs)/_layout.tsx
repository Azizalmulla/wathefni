import { Tabs } from 'expo-router'
import Ionicons from '@expo/vector-icons/Ionicons'
import { useSafeAreaInsets } from 'react-native-safe-area-context'

import { useAuth } from '@/auth/AuthProvider'
import { useI18n } from '@/i18n'
import { colors, layout, radius, shadows, spacing } from '@/theme'

function TabIcon({
  name,
  focused,
  color,
}: {
  name: 'home' | 'wallet' | 'calendar' | 'umbrella' | 'person'
  focused: boolean
  color: string
}) {
  const iconName = (focused ? name : `${name}-outline`) as keyof typeof Ionicons.glyphMap
  return <Ionicons name={iconName} size={21} color={color} />
}

export default function TabsLayout() {
  const { t } = useI18n()
  const { hasFeature } = useAuth()
  const insets = useSafeAreaInsets()
  // Home and Profile are the shell; Schedule, Leave and Payslips are the places an
  // employee actually works, and each disappears entirely when its entitlement is
  // off rather than leaving a dead slot. Inbox is not here on purpose: it is a
  // surface you visit when something arrives, so it sits behind the unread bell in
  // the Home header and its tab slot goes to a module instead.
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        title: '',
        headerTitle: '',
        tabBarHideOnKeyboard: true,
        tabBarActiveTintColor: colors.ink,
        tabBarInactiveTintColor: colors.subtle,
        tabBarLabelStyle: { fontSize: 10.5, fontWeight: '700' },
        tabBarStyle: {
          // The bar was a flat 72pt, so on devices with a home indicator the
          // labels sat in the inset. Height is now content plus the real inset,
          // and screens read this measured height back for their own bottom
          // clearance via useScrollBottomPadding.
          height: layout.tabBarBase + insets.bottom,
          paddingTop: spacing.sm,
          paddingBottom: insets.bottom,
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
      {/* One Schedule tab over Shifts and Attendance — either entitlement shows it. */}
      <Tabs.Screen
        name="schedule"
        options={{
          title: t('tabs.schedule'),
          href: hasFeature('shifts') || hasFeature('attendance') ? undefined : null,
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
        name="payslips"
        options={{
          title: t('tabs.payslips'),
          href: hasFeature('payslips') ? undefined : null,
          tabBarIcon: ({ color, focused }) => <TabIcon name="wallet" focused={focused} color={color} />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{ title: t('tabs.profile'), tabBarIcon: ({ color, focused }) => <TabIcon name="person" focused={focused} color={color} /> }}
      />
    </Tabs>
  )
}
