import { useEffect, useRef, useState, type ReactNode } from 'react'
import {
  ActivityIndicator,
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
import Ionicons from '@expo/vector-icons/Ionicons'

import { readingEdgeAlign, useI18n } from '@/i18n'
import { motion, useReducedMotion } from '@/motion'
import { lightImpactFeedback } from '@/native/haptics'
import { colors, font, radius, shadows, spacing, typeScaling } from '@/theme'

/** Ambient brand tones. These carry module identity and warmth, never status. */
export type PastelTone = 'lilac' | 'butter' | 'pink' | 'olive' | 'sky' | 'cream'

const pastelColors: Record<PastelTone, string> = {
  lilac: colors.lilac,
  butter: colors.butter,
  pink: colors.pink,
  olive: colors.olive,
  sky: colors.sky,
  cream: colors.surface,
}

export const wordmarkRules = {
  englishFont: 'Newsreader_600SemiBold',
  arabicFont: 'NotoKufiArabic_600SemiBold',
  englishTracking: -0.55,
  arabicTracking: -0.1,
  clearSpaceEm: 0.6,
  minimumSize: 15,
} as const

export function editorialFont(locale: string): string {
  if (Platform.OS === 'ios') return locale === 'ar' ? 'Geeza Pro' : 'Georgia'
  return locale === 'ar' ? 'sans-serif' : 'serif'
}

export function FadeIn({
  children,
  style,
  delay = 0,
  /** Vertical lift in pt. Default 0 — opacity-only enter feels calmer on first paint. */
  lift = 0,
}: {
  children: ReactNode
  style?: StyleProp<ViewStyle>
  delay?: number
  lift?: number
}) {
  const reducedMotion = useReducedMotion()
  // iOS Safari has composited blank-layer bugs with overflow clipping + translateY.
  // Keep motion on web to opacity only so the first paint cannot vanish.
  const useLift = Platform.OS !== 'web' && lift > 0
  const opacity = useRef(new Animated.Value(reducedMotion ? 1 : 0)).current
  const translateY = useRef(new Animated.Value(reducedMotion || !useLift ? 0 : lift)).current

  useEffect(() => {
    if (reducedMotion) {
      opacity.setValue(1)
      translateY.setValue(0)
      return
    }
    const animations = [
      Animated.timing(opacity, {
        toValue: 1,
        duration: motion.duration.quick,
        delay,
        easing: motion.easing.standard,
        useNativeDriver: true,
      }),
    ]
    if (useLift) {
      animations.push(
        Animated.timing(translateY, {
          toValue: 0,
          duration: motion.duration.quick,
          delay,
          easing: motion.easing.standard,
          useNativeDriver: true,
        }),
      )
    }
    Animated.parallel(animations).start()
  }, [delay, lift, opacity, reducedMotion, translateY, useLift])

  return (
    <Animated.View
      style={[style, { opacity }, useLift ? { transform: [{ translateY }] } : null]}
    >
      {children}
    </Animated.View>
  )
}

export function Wordmark({
  compact = false,
  align,
}: {
  compact?: boolean
  align?: 'start' | 'center'
}) {
  const { locale, isRTL } = useI18n()
  const arabic = locale === 'ar'
  return (
    <View
      accessibilityRole="header"
      accessibilityLabel="OctoHR"
      style={[
        styles.wordmarkWrap,
        align === 'center' && styles.wordmarkCentered,
        align !== 'center' && (isRTL ? styles.wordmarkEnd : styles.wordmarkStart),
      ]}
    >
      <Text
        maxFontSizeMultiplier={1.25}
        style={[
          styles.wordmark,
          compact && styles.wordmarkCompact,
          {
            fontFamily: arabic ? wordmarkRules.arabicFont : wordmarkRules.englishFont,
            letterSpacing: arabic ? wordmarkRules.arabicTracking : wordmarkRules.englishTracking,
            writingDirection: arabic ? 'rtl' : 'ltr',
          },
        ]}
      >
        OctoHR
      </Text>
    </View>
  )
}

// Four fixed organic forms create one repeatable Wathefni decorative grammar.
// Variant controls scale and crop; color order, overlap, and proportions stay fixed.
export function WathefniBloom({
  variant = 'corner',
  mirrored,
  style,
}: {
  variant?: 'corner' | 'ribbon' | 'watermark'
  mirrored?: boolean
  style?: StyleProp<ViewStyle>
}) {
  const { isRTL } = useI18n()
  const flip = mirrored ?? isRTL
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[
        styles.bloom,
        variant === 'corner' && styles.bloomCorner,
        variant === 'ribbon' && styles.bloomRibbon,
        variant === 'watermark' && styles.bloomWatermark,
        flip && styles.bloomMirrored,
        style,
      ]}
    >
      <View style={[styles.bloomShape, styles.bloomLilac]} />
      <View style={[styles.bloomShape, styles.bloomButter]} />
      <View style={[styles.bloomShape, styles.bloomPink]} />
      <View style={[styles.bloomShape, styles.bloomOlive]} />
    </View>
  )
}

export function EditorialHeading({
  children,
  size = 'large',
  style,
  accessibilityRole = 'header',
}: {
  children: ReactNode
  size?: 'large' | 'medium'
  style?: StyleProp<TextStyle>
  accessibilityRole?: 'header' | 'text' | 'none'
}) {
  const { locale, isRTL } = useI18n()
  return (
    <Text
      accessibilityRole={accessibilityRole === 'none' ? undefined : accessibilityRole}
      maxFontSizeMultiplier={size === 'large' ? typeScaling.display : typeScaling.heading}
      style={[
        size === 'large' ? styles.editorialLarge : styles.editorialMedium,
        { fontFamily: editorialFont(locale), ...readingEdgeAlign(isRTL) },
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
        { opacity: pressed ? 0.88 : 1, transform: [{ scale: pressed ? 0.992 : 1 }] },
      ]}
    >
      {body}
    </Pressable>
  )
}

export function PremiumButton({
  label,
  onPress,
  disabled = false,
  busy = false,
  success = false,
  showDirection = false,
  icon,
  tone = 'primary',
  testID,
}: {
  label: string
  onPress?: () => void
  disabled?: boolean
  busy?: boolean
  success?: boolean
  showDirection?: boolean
  icon?: keyof typeof Ionicons.glyphMap
  /** Primary = ink fill. Secondary = quiet outline — never two identical giant blacks. */
  tone?: 'primary' | 'secondary'
  /** Stable Maestro / UI-test anchor. Optional — never required for product UX. */
  testID?: string
}) {
  const { isRTL } = useI18n()
  const reducedMotion = useReducedMotion()
  const scale = useRef(new Animated.Value(1)).current
  const unavailable = disabled || busy || success
  const secondary = tone === 'secondary'
  const spinnerColor = secondary ? colors.ink : colors.surface
  const labelColor = success ? colors.surface : secondary ? colors.ink : colors.surface
  const iconColor = labelColor

  const animate = (toValue: number) => {
    if (reducedMotion) return
    Animated.spring(scale, {
      toValue,
      useNativeDriver: true,
      speed: motion.spring.speed,
      bounciness: motion.spring.bounciness,
    }).start()
  }

  return (
    <Animated.View style={{ transform: [{ scale }] }}>
      <Pressable
        testID={testID}
        accessibilityRole="button"
        accessibilityLabel={label}
        accessibilityState={{ disabled: unavailable, busy }}
        disabled={unavailable}
        onPress={() => {
          if (!unavailable) onPress?.()
        }}
        onPressIn={() => {
          // Primary CTAs only — light tactile on press, never secondary/outline.
          if (!secondary && !unavailable) lightImpactFeedback()
          animate(0.985)
        }}
        onPressOut={() => animate(1)}
        style={[
          styles.premiumButton,
          secondary && styles.premiumButtonSecondary,
          disabled && (secondary ? styles.premiumButtonSecondaryDisabled : styles.premiumButtonDisabled),
          success && styles.premiumButtonSuccess,
        ]}
      >
        {busy ? (
          <ActivityIndicator size="small" color={spinnerColor} />
        ) : (
          <View style={styles.buttonContent}>
            {success ? <Ionicons name="checkmark" size={18} color={iconColor} /> : null}
            {icon && !success ? <Ionicons name={icon} size={18} color={iconColor} /> : null}
            <Text
              maxFontSizeMultiplier={typeScaling.body}
              numberOfLines={2}
              style={[styles.premiumButtonText, { color: labelColor }]}
            >
              {label}
            </Text>
            {showDirection && !success ? (
              <Ionicons name={isRTL ? 'arrow-back' : 'arrow-forward'} size={17} color={iconColor} />
            ) : null}
          </View>
        )}
      </Pressable>
    </Animated.View>
  )
}

export function MotionProgressBar({
  value,
  color = colors.accent,
}: {
  value: number
  color?: string
}) {
  const normalized = Math.max(0, Math.min(1, value))
  const reducedMotion = useReducedMotion()
  const progress = useRef(new Animated.Value(reducedMotion ? normalized : 0)).current
  const [trackWidth, setTrackWidth] = useState(0)

  useEffect(() => {
    if (reducedMotion) {
      progress.setValue(normalized)
      return
    }
    Animated.timing(progress, {
      toValue: normalized,
      duration: motion.duration.progress,
      easing: motion.easing.standard,
      useNativeDriver: false,
    }).start()
  }, [normalized, progress, reducedMotion])

  const width = progress.interpolate({
    inputRange: [0, 1],
    outputRange: [0, trackWidth],
  })
  return (
    <View
      style={styles.progressTrack}
      onLayout={(event) => setTrackWidth(event.nativeEvent.layout.width)}
      accessibilityRole="progressbar"
      accessibilityValue={{ min: 0, max: 100, now: Math.round(normalized * 100) }}
    >
      <Animated.View style={[styles.progressFill, { width, backgroundColor: color }]} />
    </View>
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

export function ContentSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <View style={styles.skeletonWrap}>
      {Array.from({ length: rows }).map((_, index) => (
        <View key={index} style={[styles.skeleton, { width: index === rows - 1 ? '68%' : '100%' }]} />
      ))}
    </View>
  )
}

const styles = StyleSheet.create({
  wordmarkWrap: { alignSelf: 'flex-start', minHeight: 30, justifyContent: 'center' },
  wordmarkCentered: { alignSelf: 'center' },
  wordmarkStart: { alignSelf: 'flex-start' },
  wordmarkEnd: { alignSelf: 'flex-end' },
  wordmark: {
    color: colors.ink,
    fontSize: 22,
    lineHeight: 30,
    fontWeight: '600',
  },
  wordmarkCompact: { fontSize: 17, lineHeight: 24 },
  bloom: { position: 'absolute', overflow: 'hidden' },
  bloomCorner: { width: 108, height: 94, top: -12, right: -6 },
  bloomRibbon: { position: 'relative', width: '100%', height: 58, opacity: 0.82 },
  bloomWatermark: { width: 92, height: 88, top: -4, right: -8, opacity: 0.68 },
  bloomMirrored: { transform: [{ scaleX: -1 }] },
  bloomShape: { position: 'absolute', borderRadius: 28 },
  bloomLilac: {
    width: 49,
    height: 28,
    right: 34,
    top: 5,
    backgroundColor: colors.lilac,
    transform: [{ rotate: '24deg' }],
  },
  bloomButter: {
    width: 34,
    height: 50,
    right: 6,
    top: 18,
    backgroundColor: colors.butter,
    transform: [{ rotate: '-18deg' }],
  },
  bloomPink: {
    width: 45,
    height: 30,
    right: 43,
    top: 46,
    backgroundColor: colors.pink,
    transform: [{ rotate: '-28deg' }],
  },
  bloomOlive: {
    width: 31,
    height: 33,
    right: 16,
    top: 58,
    backgroundColor: colors.olive,
    transform: [{ rotate: '15deg' }],
  },
  editorialLarge: {
    color: colors.ink,
    fontSize: font.display,
    lineHeight: 36,
    letterSpacing: -0.7,
    fontWeight: '500',
  },
  editorialMedium: {
    color: colors.ink,
    fontSize: font.h1,
    lineHeight: 32,
    letterSpacing: -0.4,
    fontWeight: '500',
  },
  pastelCard: {
    borderRadius: radius.xl,
    padding: spacing.lg,
    overflow: 'hidden',
    ...shadows.card,
  },
  premiumButton: {
    // minHeight, not height: the label must be able to grow with Dynamic Type
    // rather than clip inside a fixed box.
    minHeight: 48,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    backgroundColor: colors.ink,
    shadowColor: colors.ink,
    shadowOpacity: 0.12,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
    elevation: 2,
  },
  premiumButtonSecondary: {
    backgroundColor: 'transparent',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    shadowOpacity: 0,
    elevation: 0,
  },
  premiumButtonDisabled: {
    backgroundColor: colors.subtle,
    shadowOpacity: 0,
  },
  premiumButtonSecondaryDisabled: {
    backgroundColor: 'transparent',
    borderColor: colors.navMuted,
    opacity: 0.55,
    shadowOpacity: 0,
  },
  premiumButtonSuccess: { backgroundColor: colors.success },
  buttonContent: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.sm },
  premiumButtonText: { color: colors.surface, fontSize: font.body, fontWeight: '700', letterSpacing: -0.1 },
  progressTrack: {
    height: 6,
    overflow: 'hidden',
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceMuted,
  },
  progressFill: { height: '100%', borderRadius: radius.pill },
  iconBadge: {
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceMuted,
  },
  iconBadgeInverted: { backgroundColor: colors.ink },
  skeletonWrap: { gap: spacing.md },
  skeleton: {
    height: 15,
    borderRadius: radius.pill,
    backgroundColor: colors.border,
  },
})
