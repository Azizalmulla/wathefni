import { useContext, type ReactNode } from 'react'
import {
  RefreshControl,
  ScrollView,
  StyleSheet,
  type StyleProp,
  type ViewStyle,
} from 'react-native'
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context'
import { BottomTabBarHeightContext } from '@react-navigation/bottom-tabs'

import { useI18n } from '@/i18n'
import { colors, layout } from '@/theme'

/**
 * Bottom clearance for a scrolling page.
 *
 * Tab scenes are already laid out *above* the tab bar by React Navigation.
 * Adding the measured tab-bar height again created a large empty cream zone
 * under the last row — scroll felt unbounded on dense screens and tight on
 * screens that overwrote padding. Pushed stack screens (Inbox, Settings, …)
 * have no tab bar, so they still need the home-indicator inset.
 */
export function useScrollBottomPadding(extra: number = layout.scrollBottom): number {
  const insets = useSafeAreaInsets()
  const tabBarHeight = useContext(BottomTabBarHeightContext)
  const insideTabs = typeof tabBarHeight === 'number' && tabBarHeight > 0
  return insideTabs ? extra : insets.bottom + extra
}

/** Page frame: cream ground plus the top safe area. Bottom is owned by the scroller. */
export function PageScreen({
  children,
  style,
}: {
  children: ReactNode
  style?: StyleProp<ViewStyle>
}) {
  const { isRTL } = useI18n()
  return (
    <SafeAreaView
      edges={['top']}
      style={[styles.screen, { direction: isRTL ? 'rtl' : 'ltr' }, style]}
    >
      {children}
    </SafeAreaView>
  )
}

/**
 * The one scrolling body used by every employee page: a single horizontal
 * margin, a single section rhythm, and correct bottom clearance.
 */
export function PageScrollView({
  children,
  refreshing,
  onRefresh,
  gap = layout.sectionGap,
  contentStyle,
  keyboardInsets = false,
}: {
  children: ReactNode
  refreshing?: boolean
  onRefresh?: () => void
  gap?: number
  contentStyle?: StyleProp<ViewStyle>
  /**
   * Opt-in keyboard avoidance. Off by default: enabling it on every page
   * left a stale bottom inset after dismiss (phantom scroll into empty cream).
   * Forms with TextInputs (Bank, leave request) pass true. Android is included
   * so submit actions stay reachable (R7 PH-2/PH-3).
   */
  keyboardInsets?: boolean
}) {
  const paddingBottom = useScrollBottomPadding()
  return (
    <ScrollView
      style={styles.flex}
      contentContainerStyle={[
        {
          paddingHorizontal: layout.pageMargin,
          paddingTop: layout.pageTop,
          paddingBottom,
          gap,
        },
        contentStyle,
      ]}
      // Safe area is owned by PageScreen (top) + useScrollBottomPadding (bottom).
      // Leaving iOS on "automatic" double-counted the home indicator on pushed screens.
      contentInsetAdjustmentBehavior="never"
      showsVerticalScrollIndicator={false}
      keyboardShouldPersistTaps="handled"
      keyboardDismissMode="interactive"
      automaticallyAdjustKeyboardInsets={keyboardInsets}
      refreshControl={
        onRefresh ? (
          <RefreshControl refreshing={Boolean(refreshing)} onRefresh={onRefresh} tintColor={colors.ink} />
        ) : undefined
      }
    >
      {children}
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
})
