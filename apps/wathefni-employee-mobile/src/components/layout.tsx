import { useContext, type ReactNode } from 'react'
import {
  Platform,
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
 * Inside the tab navigator this is the tab bar's own measured height, which
 * already includes the home-indicator inset. On a screen pushed above the tabs
 * there is no tab bar, but the home indicator still has to be cleared. Either
 * way no screen carries a hand-tuned number, which is what previously left the
 * last element on Home, Schedule and Profile sitting under the tab bar.
 */
export function useScrollBottomPadding(extra: number = layout.scrollBottom): number {
  const insets = useSafeAreaInsets()
  const tabBarHeight = useContext(BottomTabBarHeightContext)
  return (tabBarHeight ?? insets.bottom) + extra
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
}: {
  children: ReactNode
  refreshing?: boolean
  onRefresh?: () => void
  gap?: number
  contentStyle?: StyleProp<ViewStyle>
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
      showsVerticalScrollIndicator={false}
      keyboardShouldPersistTaps="handled"
      keyboardDismissMode="interactive"
      // Keeps the focused field above the keyboard on the leave-request form
      // without any screen having to manage keyboard offsets itself.
      automaticallyAdjustKeyboardInsets={Platform.OS === 'ios'}
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
