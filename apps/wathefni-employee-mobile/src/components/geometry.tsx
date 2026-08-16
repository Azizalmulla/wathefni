import { StyleSheet, useWindowDimensions, View, type StyleProp, type ViewStyle } from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'

import { useI18n } from '@/i18n'
import { ambient, colors } from '@/theme'

/**
 * Wathefni decorative geometry.
 *
 * Three motifs, each taken from something the product actually does, so the
 * decoration says "employment record" rather than "nice shape":
 *
 *   RecordSheet     a page with a turned-down corner — the employee record.
 *   Seal            an open ring — verification, an approved item.
 *   CheckpointTrack nodes on a rule — stages of a request or a journey.
 *
 * Everything is drawn with plain views and border radii. That is deliberate:
 * `react-native-svg` is a native module, so reaching for it would cost a new
 * native build and take these screens off the OTA channel for a decoration.
 *
 * The grammar is fixed. Variants change scale and crop only — never the motifs,
 * their order, or their colour assignment — so the mark stays recognisable
 * wherever it appears.
 */

export function RecordSheet({
  width = 54,
  height = 66,
  style,
}: {
  width?: number
  height?: number
  style?: StyleProp<ViewStyle>
}) {
  const fold = Math.round(Math.min(width, height) * 0.33)
  return (
    <View style={[styles.sheet, { width, height }, style]}>
      <View style={[styles.fold, { width: fold, height: fold }]} />
      <View style={[styles.sheetLine, { width: width * 0.48, top: height * 0.48 }]} />
      <View style={[styles.sheetLine, { width: width * 0.34, top: height * 0.65 }]} />
    </View>
  )
}

export function Seal({ size = 44, style }: { size?: number; style?: StyleProp<ViewStyle> }) {
  return (
    <View
      style={[styles.seal, { width: size, height: size, borderRadius: size / 2 }, style]}
    >
      <Ionicons name="checkmark" size={size * 0.48} color={colors.ink} />
    </View>
  )
}

/**
 * Nodes on a rule. The last node is solid because a journey has a position in
 * it; an evenly weighted row of dots would just be a pattern.
 */
export function CheckpointTrack({
  width = 100,
  nodes = 3,
  style,
}: {
  width?: number
  nodes?: number
  style?: StyleProp<ViewStyle>
}) {
  return (
    <View style={[styles.track, { width }, style]}>
      <View style={styles.trackRule} />
      <View style={styles.trackNodes}>
        {Array.from({ length: nodes }).map((_, index) => (
          <View
            key={index}
            style={[styles.node, index === nodes - 1 && styles.nodeReached]}
          />
        ))}
      </View>
    </View>
  )
}

/**
 * The composed hero mark: a record, verified, moving through its stages.
 *
 * Mirrored in Arabic so the fold and the track read from the same edge the page
 * does. It is hidden from assistive technology — it carries no information a
 * screen reader user is missing.
 *
 * It also yields entirely once text is enlarged. The mark holds a fixed 116pt
 * beside the page title, which is affordable at the default text size and not
 * affordable at the accessibility sizes — at which point a heading with room to
 * breathe matters more than a decoration.
 */
export function WathefniMark({
  variant = 'hero',
  style,
}: {
  variant?: 'hero' | 'quiet'
  style?: StyleProp<ViewStyle>
}) {
  const { isRTL } = useI18n()
  const { fontScale } = useWindowDimensions()
  if (fontScale >= 1.35) return null
  const scale = variant === 'quiet' ? 0.72 : 1
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      pointerEvents="none"
      style={[
        styles.mark,
        { transform: [{ scale }, ...(isRTL ? [{ scaleX: -1 }] : [])] },
        style,
      ]}
    >
      <Seal style={styles.markSeal} />
      <RecordSheet style={styles.markSheet} />
      <CheckpointTrack style={styles.markTrack} />
    </View>
  )
}

const styles = StyleSheet.create({
  sheet: {
    borderRadius: 10,
    // The corner the fold occupies is squared off, so the deeper tone below
    // reads as the page turning rather than as a sticker.
    borderTopRightRadius: 0,
    backgroundColor: ambient.payslips.fill,
    overflow: 'hidden',
  },
  fold: {
    position: 'absolute',
    top: 0,
    right: 0,
    borderBottomLeftRadius: 8,
    backgroundColor: ambient.payslips.accent,
  },
  sheetLine: {
    position: 'absolute',
    left: 10,
    height: 2,
    borderRadius: 1,
    backgroundColor: colors.ink,
    opacity: 0.45,
  },
  seal: {
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 3,
    borderColor: ambient.documents.accent,
    backgroundColor: 'transparent',
  },
  track: { height: 10, justifyContent: 'center' },
  trackRule: {
    position: 'absolute',
    left: 4,
    right: 4,
    height: 2,
    borderRadius: 1,
    backgroundColor: ambient.schedule.accent,
  },
  trackNodes: { flexDirection: 'row', justifyContent: 'space-between' },
  node: {
    width: 9,
    height: 9,
    borderRadius: 4.5,
    borderWidth: 2,
    borderColor: ambient.schedule.accent,
    backgroundColor: colors.bg,
  },
  nodeReached: { backgroundColor: ambient.schedule.accent },
  mark: { width: 116, height: 104 },
  markSeal: { position: 'absolute', top: 2, right: 4 },
  markSheet: { position: 'absolute', top: 18, right: 42, transform: [{ rotate: '-7deg' }] },
  markTrack: { position: 'absolute', bottom: 0, right: 8 },
})
