import { useEffect, useRef, type ReactNode } from 'react'
import {
  Animated,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type TextStyle,
  type ViewStyle,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'

import { useI18n } from '@/i18n'
import { colors, font, radius, shadows, spacing } from '@/theme'

export type PastelTone = 'lilac' | 'butter' | 'blush' | 'sage' | 'sky' | 'cream'

const pastelColors: Record<PastelTone, string> = {
  lilac: colors.pastelLilac,
  butter: colors.pastelButter,
  blush: colors.pastelBlush,
  sage: colors.pastelSage,
  sky: colors.pastelSky,
  cream: colors.surface,
}

export function editorialFont(locale: string): string {
  if (Platform.OS === 'ios') return locale === 'ar' ? 'Geeza Pro' : 'Georgia'
  return locale === 'ar' ? 'sans-serif' : 'serif'
}

export function FadeIn({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  const opacity = useRef(new Animated.Value(0)).current
  const translateY = useRef(new Animated.Value(8)).current

  useEffect(() => {
    Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration: 340, useNativeDriver: true }),
      Animated.timing(translateY, { toValue: 0, duration: 340, useNativeDriver: true }),
    ]).start()
  }, [opacity, translateY])

  return <Animated.View style={[style, { opacity, transform: [{ translateY }] }]}>{children}</Animated.View>
}

export function BrandLockup({ compact = false }: { compact?: boolean }) {
  const { t, isRTL } = useI18n()
  return (
    <View style={[styles.brand, isRTL && styles.rowReverse]}>
      <View style={[styles.brandMark, compact && styles.brandMarkCompact]} accessibilityElementsHidden>
        <View style={[styles.brandPetal, styles.petalOne]} />
        <View style={[styles.brandPetal, styles.petalTwo]} />
        <View style={[styles.brandPetal, styles.petalThree]} />
      </View>
      <Text style={[styles.brandText, compact && styles.brandTextCompact, { fontFamily: editorialFont(isRTL ? 'ar' : 'en') }]}>
        {t('app.name')}
      </Text>
    </View>
  )
}

export function EditorialHeading({
  children,
  size = 'large',
  style,
}: {
  children: ReactNode
  size?: 'large' | 'medium'
  style?: StyleProp<TextStyle>
}) {
  const { locale, isRTL } = useI18n()
  return (
    <Text
      style={[
        size === 'large' ? styles.editorialLarge : styles.editorialMedium,
        { fontFamily: editorialFont(locale), textAlign: isRTL ? 'right' : 'left' },
        style,
      ]}
    >
      {children}
    </Text>
  )
}

export function PastelCard({
  tone,
  children,
  style,
  containerStyle,
  onPress,
  accessibilityLabel,
}: {
  tone: PastelTone
  children: ReactNode
  style?: StyleProp<ViewStyle>
  containerStyle?: StyleProp<ViewStyle>
  onPress?: () => void
  accessibilityLabel?: string
}) {
  const body = (
    <View style={[styles.pastelCard, { backgroundColor: pastelColors[tone] }, style]}>
      {children}
    </View>
  )
  if (!onPress) return body
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      onPress={onPress}
      style={({ pressed }) => [
        containerStyle,
        { opacity: pressed ? 0.82 : 1, transform: [{ scale: pressed ? 0.99 : 1 }] },
      ]}
    >
      {body}
    </Pressable>
  )
}

export function IconBadge({
  name,
  inverted = false,
  size = 38,
}: {
  name: keyof typeof Ionicons.glyphMap
  inverted?: boolean
  size?: number
}) {
  return (
    <View
      style={[
        styles.iconBadge,
        { width: size, height: size, borderRadius: size / 2 },
        inverted && styles.iconBadgeInverted,
      ]}
    >
      <Ionicons name={name} size={size * 0.47} color={inverted ? colors.surface : colors.ink} />
    </View>
  )
}

export function DirectionalIcon({ size = 18 }: { size?: number }) {
  const { isRTL } = useI18n()
  return <Ionicons name={isRTL ? 'arrow-back' : 'arrow-forward'} size={size} color={colors.surface} />
}

export function PreviewSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <View style={styles.skeletonWrap}>
      {Array.from({ length: rows }).map((_, index) => (
        <View key={index} style={[styles.skeleton, { width: index === rows - 1 ? '68%' : '100%' }]} />
      ))}
    </View>
  )
}

const styles = StyleSheet.create({
  rowReverse: { flexDirection: 'row-reverse' },
  brand: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  brandMark: { width: 29, height: 26, position: 'relative' },
  brandMarkCompact: { transform: [{ scale: 0.86 }] },
  brandPetal: {
    position: 'absolute',
    width: 10,
    height: 22,
    borderRadius: radius.pill,
    backgroundColor: colors.ink,
    bottom: 1,
  },
  petalOne: { left: 2, transform: [{ rotate: '-31deg' }] },
  petalTwo: { left: 10, bottom: 5, transform: [{ rotate: '-15deg' }] },
  petalThree: { right: 0, bottom: 7, height: 17, transform: [{ rotate: '40deg' }] },
  brandText: { color: colors.ink, fontSize: font.h2, fontWeight: '700' },
  brandTextCompact: { fontSize: font.h3 },
  editorialLarge: {
    color: colors.ink,
    fontSize: font.display,
    lineHeight: 43,
    letterSpacing: -1,
    fontWeight: '500',
  },
  editorialMedium: {
    color: colors.ink,
    fontSize: font.h1,
    lineHeight: 34,
    letterSpacing: -0.5,
    fontWeight: '500',
  },
  pastelCard: {
    borderRadius: radius.xl,
    padding: spacing.lg,
    overflow: 'hidden',
    ...shadows.card,
  },
  iconBadge: {
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.72)',
  },
  iconBadgeInverted: { backgroundColor: colors.ink },
  skeletonWrap: { gap: spacing.md },
  skeleton: {
    height: 15,
    borderRadius: radius.pill,
    backgroundColor: colors.skeleton,
  },
})
