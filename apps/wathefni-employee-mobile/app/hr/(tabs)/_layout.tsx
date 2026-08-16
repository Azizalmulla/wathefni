import { Tabs } from 'expo-router'
import Ionicons from '@expo/vector-icons/Ionicons'
import { useSafeAreaInsets } from 'react-native-safe-area-context'

import { useAuth } from '@hr/auth/AuthProvider'
import { tabHiringEnabled, tabInboxEnabled, tabPeopleEnabled } from '@hr/shell/ia'
import { useI18n } from '@/i18n'
import { tabFeedback } from '@/native/haptics'
import { colors, layout, radius, spacing } from '@/theme'

function TabIcon({
  name,
  focused,
  color,
}: {
  name: 'home' | 'people' | 'file-tray' | 'briefcase' | 'grid'
  focused: boolean
  color: string
}) {
  const map = {
    home: focused ? 'home' : 'home-outline',
    people: focused ? 'people' : 'people-outline',
    'file-tray': focused ? 'file-tray' : 'file-tray-outline',
    briefcase: focused ? 'briefcase' : 'briefcase-outline',
    grid: focused ? 'grid' : 'grid-outline',
  } as const
  return <Ionicons name={map[name]} size={21} color={color} />
}

/** Employee-parity bottom navigation for HR destinations. */
export default function HrTabsLayout() {
  const { t } = useI18n()
  const { me } = useAuth()
  const insets = useSafeAreaInsets()
  const peopleOn = tabPeopleEnabled(me)
  const inboxOn = tabInboxEnabled(me)
  const hiringOn = tabHiringEnabled(me)

  return (
    <Tabs
      screenListeners={{
        tabPress: () => {
          tabFeedback()
        },
      }}
      screenOptions={{
        headerShown: false,
        title: '',
        headerTitle: '',
        tabBarHideOnKeyboard: true,
        tabBarActiveTintColor: colors.primaryText,
        tabBarInactiveTintColor: colors.navMuted,
        tabBarLabelStyle: { fontSize: 10.5, fontWeight: '700' },
        tabBarStyle: {
          height: layout.tabBarBase + insets.bottom,
          paddingTop: spacing.sm,
          paddingBottom: insets.bottom,
          backgroundColor: colors.ink,
          borderTopColor: colors.ink,
          borderTopLeftRadius: radius.xl,
          borderTopRightRadius: radius.xl,
          shadowColor: colors.ink,
          shadowOpacity: 0.16,
          shadowRadius: 14,
          shadowOffset: { width: 0, height: -3 },
          elevation: 8,
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: t('tabs.home'),
          tabBarButtonTestID: 'e2e.tab.hr.home',
          tabBarIcon: ({ color, focused }) => <TabIcon name="home" focused={focused} color={color} />,
        }}
      />
      <Tabs.Screen
        name="people"
        options={{
          title: t('tabs.people'),
          tabBarButtonTestID: 'e2e.tab.hr.people',
          href: peopleOn ? undefined : null,
          tabBarIcon: ({ color, focused }) => <TabIcon name="people" focused={focused} color={color} />,
        }}
      />
      <Tabs.Screen
        name="inbox"
        options={{
          title: t('tabs.inbox'),
          tabBarButtonTestID: 'e2e.tab.hr.inbox',
          href: inboxOn ? undefined : null,
          tabBarIcon: ({ color, focused }) => (
            <TabIcon name="file-tray" focused={focused} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="hiring"
        options={{
          title: t('tabs.hiring'),
          tabBarButtonTestID: 'e2e.tab.hr.hiring',
          href: hiringOn ? undefined : null,
          tabBarIcon: ({ color, focused }) => (
            <TabIcon name="briefcase" focused={focused} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="more"
        options={{
          title: t('tabs.more'),
          tabBarButtonTestID: 'e2e.tab.hr.more',
          tabBarIcon: ({ color, focused }) => <TabIcon name="grid" focused={focused} color={color} />,
        }}
      />
    </Tabs>
  )
}
