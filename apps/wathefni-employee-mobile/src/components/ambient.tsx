import type { ReactNode } from 'react'
import { Pressable, StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'

import { ambient, colors, radius, shadows, spacing, type AmbientModule } from '@/theme'

/**
 * Surfaces for the two-tone ambient palette.
 *
 * These sit alongside `PastelCard` rather than replacing it. The single-tone
 * cards are still in use on seven other screens, and swapping the token
 * underneath them would silently restyle the whole app; this pilot is meant to
 * be judged on Home before that happens.
 */

/** A large surface. Soft radius + quiet shadow so colour, not outline, carries the card. */
export function AmbientCard({
  module,
  children,
  style,
  containerStyle,
  onPress,
  accessibilityLabel,
}: {
  module: AmbientModule
  children: ReactNode
  style?: StyleProp<ViewStyle>
  containerStyle?: StyleProp<ViewStyle>
  onPress?: () => void
  accessibilityLabel?: string
}) {
  const fill = (
    <View style={[styles.cardFill, { backgroundColor: ambient[module].fill }, style]}>
      {children}
    </View>
  )
  if (!onPress) return <View style={styles.cardShadow}>{fill}</View>
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      onPress={onPress}
      style={({ pressed }) => [
        styles.cardShadow,
        containerStyle,
        { opacity: pressed ? 0.9 : 1, transform: [{ scale: pressed ? 0.994 : 1 }] },
      ]}
    >
      {fill}
    </Pressable>
  )
}

/**
 * The accent mark. Softly rounded, capped at icon size — chroma this strong
 * never spreads past a mark this small.
 */
export function AmbientIconTile({
  module,
  icon,
  size = 42,
}: {
  module: AmbientModule
  icon: keyof typeof Ionicons.glyphMap
  size?: number
}) {
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[
        styles.tile,
        {
          width: size,
          height: size,
          borderRadius: Math.round(size * 0.36),
          backgroundColor: ambient[module].accent,
        },
      ]}
    >
      <Ionicons name={icon} size={Math.round(size * 0.46)} color={colors.ink} />
    </View>
  )
}

const styles = StyleSheet.create({
  // Shadow lives outside the clipped fill. Combining `overflow: hidden` and an
  // iOS shadow on one view clips the shadow and wastes the elevation work.
  cardShadow: {
    borderRadius: radius.xxl,
    ...shadows.card,
  },
  cardFill: {
    borderRadius: radius.xxl,
    padding: spacing.lg + 2,
    overflow: 'hidden',
  },
  tile: { alignItems: 'center', justifyContent: 'center' },
})
