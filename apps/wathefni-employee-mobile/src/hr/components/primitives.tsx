import { useEffect, useRef, type ReactNode } from 'react'
import {
  ActivityIndicator,
  Animated,
  Image,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context'
import { keyboardSafeBehavior, keyboardSafeOffset } from '@/components/keyboardSafe'

import { useLocale } from '@hr/i18n'
import { motion, useReducedMotion } from '@hr/motion'
import { usePreviewEmbed } from '@hr/preview/PreviewEmbedContext'
import { colors, radius, shadows, spacing, type as typography } from '@hr/theme'
import { resolveCompanyBrand, useCompanyBrandIdentity } from '@/branding/CompanyBrand'

export function Screen({
  children,
  scroll = true,
  contentStyle,
}: {
  children: ReactNode
  scroll?: boolean
  contentStyle?: StyleProp<ViewStyle>
}) {
  const embed = usePreviewEmbed()
  const insets = useSafeAreaInsets()
  const body = <View style={[styles.screenContent, contentStyle]}>{children}</View>
  const shouldScroll = scroll && !embed
  if (embed) {
    return <View style={styles.safeEmbed}>{body}</View>
  }
  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={keyboardSafeBehavior()}
        keyboardVerticalOffset={keyboardSafeOffset(insets.top)}
      >
        {shouldScroll ? (
          <ScrollView
            style={styles.scroll}
            contentContainerStyle={styles.scrollContent}
            showsVerticalScrollIndicator={false}
            keyboardShouldPersistTaps="handled"
            automaticallyAdjustKeyboardInsets
          >
            {body}
          </ScrollView>
        ) : (
          body
        )}
      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}

export function FadeIn({ children, delay = 0 }: { children: ReactNode; delay?: number }) {
  const reduced = useReducedMotion()
  const opacity = useRef(new Animated.Value(reduced ? 1 : 0)).current
  const translate = useRef(new Animated.Value(reduced || Platform.OS === 'web' ? 0 : 7)).current
  useEffect(() => {
    if (reduced) return
    Animated.parallel([
      Animated.timing(opacity, {
        toValue: 1,
        duration: motion.enter,
        delay,
        useNativeDriver: true,
      }),
      Animated.timing(translate, {
        toValue: 0,
        duration: motion.enter,
        delay,
        useNativeDriver: true,
      }),
    ]).start()
  }, [delay, opacity, reduced, translate])
  return (
    <Animated.View style={{ opacity, transform: [{ translateY: translate }] }}>
      {children}
    </Animated.View>
  )
}

export function Wordmark({ compact = false }: { compact?: boolean }) {
  const { locale, isRTL } = useLocale()
  const identity = useCompanyBrandIdentity()
  const brand = resolveCompanyBrand(identity, locale)
  return (
    <View
      accessibilityRole="header"
      accessibilityLabel={brand.name}
      style={[styles.wordmarkRow, isRTL && styles.wordmarkRowRTL]}
    >
      {brand.logoUrl ? (
        <Image
          accessibilityIgnoresInvertColors
          accessible={false}
          source={{ uri: brand.logoUrl }}
          style={[styles.wordmarkLogo, compact && styles.wordmarkLogoCompact]}
        />
      ) : null}
      <Text
        maxFontSizeMultiplier={1.2}
        numberOfLines={1}
        style={[
          styles.wordmark,
          compact && styles.wordmarkCompact,
          {
            fontFamily: locale === 'ar' ? 'NotoKufiArabic_600SemiBold' : 'Newsreader_600SemiBold',
            textAlign: isRTL ? 'right' : 'left',
            writingDirection: isRTL ? 'rtl' : 'ltr',
          },
        ]}
      >
        {brand.name}
      </Text>
    </View>
  )
}

export function EditorialHeading({
  eyebrow,
  children,
}: {
  eyebrow?: string
  children: ReactNode
}) {
  const { locale, isRTL } = useLocale()
  return (
    <View style={styles.headingWrap}>
      {eyebrow ? (
        <Text style={[styles.eyebrow, { textAlign: isRTL ? 'right' : 'left' }]}>{eyebrow}</Text>
      ) : null}
      <Text
        maxFontSizeMultiplier={1.7}
        style={[
          styles.hero,
          {
            fontFamily: Platform.OS === 'ios' ? (locale === 'ar' ? 'Geeza Pro' : 'Georgia') : undefined,
            textAlign: isRTL ? 'right' : 'left',
            writingDirection: isRTL ? 'rtl' : 'ltr',
          },
        ]}
      >
        {children}
      </Text>
    </View>
  )
}

export function WorkspaceHeader({
  company,
  scopeLabel,
  onLocale,
  onBack,
  backAccessibilityLabel,
}: {
  company: string
  scopeLabel?: string
  onLocale?: () => void
  onBack?: () => void
  backAccessibilityLabel?: string
}) {
  const { locale, isRTL, t } = useLocale()
  return (
    <View style={[styles.workspaceHeader, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
      <View style={[styles.headerLeading, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
        {onBack ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={backAccessibilityLabel || t('common.back')}
            onPress={onBack}
            hitSlop={8}
            style={styles.headerBack}
          >
            <Ionicons name={isRTL ? 'arrow-forward' : 'arrow-back'} size={19} color={colors.ink} />
          </Pressable>
        ) : null}
        <View style={styles.headerText}>
          <Wordmark compact />
          <View style={[styles.companyRow, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
            <View style={styles.companyDot} />
            <Text style={[styles.company, { textAlign: isRTL ? 'right' : 'left' }]}>{company}</Text>
            {scopeLabel ? <Text style={styles.scopeLabel}>· {scopeLabel}</Text> : null}
          </View>
        </View>
      </View>
      {onLocale ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={locale === 'ar' ? 'Switch to English' : 'التبديل إلى العربية'}
          onPress={onLocale}
          style={styles.localeButton}
        >
          <Text style={styles.localeText}>{locale === 'ar' ? 'EN' : 'ع'}</Text>
        </Pressable>
      ) : null}
    </View>
  )
}

export type StatusTone = 'neutral' | 'attention' | 'success' | 'danger' | 'info'

export function StatusBadge({ label, tone = 'neutral' }: { label: string; tone?: StatusTone }) {
  return (
    <View style={[styles.badge, badgeTones[tone]]}>
      <Text style={[styles.badgeText, badgeTextTones[tone]]}>{label.replaceAll('_', ' ')}</Text>
    </View>
  )
}

export function IdentityRow({
  name,
  subtitle,
  meta,
}: {
  name: string
  subtitle?: string | null
  meta?: string | null
}) {
  const { isRTL } = useLocale()
  const initials = name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()
  return (
    <View style={[styles.identityRow, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
      <View style={styles.avatar}>
        <Text style={styles.avatarText}>{initials || 'W'}</Text>
      </View>
      <View style={styles.identityText}>
        <Text style={[styles.identityName, { textAlign: isRTL ? 'right' : 'left' }]}>{name}</Text>
        {subtitle ? (
          <Text style={[styles.identitySubtitle, { textAlign: isRTL ? 'right' : 'left' }]}>{subtitle}</Text>
        ) : null}
        {meta ? <Text style={[styles.identityMeta, { textAlign: isRTL ? 'right' : 'left' }]}>{meta}</Text> : null}
      </View>
    </View>
  )
}

export function Card({
  children,
  tone = 'cream',
  style,
}: {
  children: ReactNode
  tone?: 'cream' | 'lilac' | 'sage' | 'amber' | 'coral' | 'sky'
  style?: StyleProp<ViewStyle>
}) {
  return <View style={[styles.card, cardTones[tone], style]}>{children}</View>
}

export function PriorityCard({
  title,
  summary,
  status,
  severity,
  meta,
  onPress,
}: {
  title: string
  summary: string
  status: string
  severity?: string | null
  meta?: string | null
  onPress?: () => void
}) {
  const { isRTL, t } = useLocale()
  const reduced = useReducedMotion()
  return (
    <Pressable
      accessibilityRole={onPress ? 'button' : undefined}
      accessibilityLabel={`${title}. ${summary}. ${status}`}
      onPress={onPress}
      disabled={!onPress}
      style={({ pressed }) => [
        styles.priorityCard,
        pressed && (reduced ? styles.pressedReduced : styles.pressed),
      ]}
    >
      <View style={[styles.priorityTop, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
        <Text style={[styles.priorityTitle, { textAlign: isRTL ? 'right' : 'left' }]}>{title}</Text>
        <StatusBadge label={status} tone={severity === 'high' ? 'danger' : 'attention'} />
      </View>
      <Text style={[styles.prioritySummary, { textAlign: isRTL ? 'right' : 'left' }]}>{summary}</Text>
      {meta ? <Text style={[styles.priorityMeta, { textAlign: isRTL ? 'right' : 'left' }]}>{meta}</Text> : null}
      {onPress ? (
        <View style={[styles.reviewRow, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
          <Text style={styles.reviewText}>{t('common.review')}</Text>
          <Ionicons
            name={isRTL ? 'chevron-back' : 'chevron-forward'}
            size={16}
            color={colors.plum}
          />
        </View>
      ) : null}
    </Pressable>
  )
}

export function ActionableCard({
  title,
  subtitle,
  meta,
  status,
  tone = 'neutral',
  onPress,
}: {
  title: string
  subtitle?: string | null
  meta?: string | null
  status?: string | null
  tone?: StatusTone
  onPress?: () => void
}) {
  const { isRTL, t } = useLocale()
  const reduced = useReducedMotion()
  return (
    <Pressable
      accessibilityRole={onPress ? 'button' : undefined}
      accessibilityLabel={[title, subtitle, status, onPress ? t('common.review') : null]
        .filter(Boolean)
        .join('. ')}
      disabled={!onPress}
      onPress={onPress}
      style={({ pressed }) => [
        styles.actionableCard,
        pressed && (reduced ? styles.pressedReduced : styles.pressedLift),
      ]}
    >
      <View style={[styles.actionableTop, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
        <Text style={[styles.actionableTitle, { textAlign: isRTL ? 'right' : 'left' }]}>{title}</Text>
        {status ? <StatusBadge label={status} tone={tone} /> : null}
      </View>
      {subtitle ? (
        <Text style={[styles.actionableSubtitle, { textAlign: isRTL ? 'right' : 'left' }]}>
          {subtitle}
        </Text>
      ) : null}
      <View style={[styles.actionableBottom, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
        <Text style={[styles.actionableMeta, { textAlign: isRTL ? 'right' : 'left' }]}>
          {meta || ''}
        </Text>
        {onPress ? (
          <View style={[styles.reviewRow, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
            <Text style={styles.reviewText}>{t('common.review')}</Text>
            <Ionicons
              name={isRTL ? 'chevron-back' : 'chevron-forward'}
              size={16}
              color={colors.plum}
            />
          </View>
        ) : null}
      </View>
    </Pressable>
  )
}

export function EvidenceCard({
  title,
  items,
  tone,
  icon,
}: {
  title: string
  items: string[]
  tone: 'evidence' | 'concern' | 'missing'
  icon: keyof typeof Ionicons.glyphMap
}) {
  const { isRTL } = useLocale()
  return (
    <Card tone={tone === 'evidence' ? 'sage' : tone === 'concern' ? 'coral' : 'amber'}>
      <View style={[styles.evidenceTitleRow, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
        <Ionicons name={icon} size={18} color={colors.ink} />
        <Text style={styles.evidenceTitle}>{title}</Text>
      </View>
      {items.map((item, index) => (
        <View
          key={`${title}-${index}`}
          style={[styles.evidenceRow, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}
        >
          <View style={styles.bullet} />
          <Text style={[styles.evidenceText, { textAlign: isRTL ? 'right' : 'left' }]}>{item}</Text>
        </View>
      ))}
    </Card>
  )
}

export function ActionButton({
  label,
  onPress,
  tone = 'primary',
  disabled = false,
  loading = false,
  testID,
}: {
  label: string
  onPress?: () => void
  tone?: 'primary' | 'secondary' | 'danger'
  disabled?: boolean
  loading?: boolean
  testID?: string
}) {
  const reduced = useReducedMotion()
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: disabled || loading, busy: loading }}
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [
        styles.action,
        actionTones[tone],
        (disabled || loading) && styles.disabled,
        pressed && (reduced ? styles.pressedReduced : styles.pressed),
      ]}
    >
      {loading ? (
        <ActivityIndicator color={tone === 'secondary' ? colors.ink : colors.white} />
      ) : (
        <Text style={[styles.actionText, tone === 'secondary' && styles.actionTextDark]}>{label}</Text>
      )}
    </Pressable>
  )
}

export type ConfirmationView = {
  target: string
  action: string
  consequence: string
  currentState: string
  reason?: string | null
}

export function ConfirmationSheet({
  visible,
  value,
  onCancel,
  onConfirm,
  loading = false,
  error = null,
}: {
  visible: boolean
  value: ConfirmationView | null
  onCancel: () => void
  onConfirm: () => void
  loading?: boolean
  error?: string | null
}) {
  const { t, isRTL } = useLocale()
  if (!value) return null
  const rows = [
    [t('confirm.target'), value.target],
    [t('confirm.action'), value.action],
    [t('confirm.consequence'), value.consequence],
    [t('confirm.currentState'), value.currentState],
    ...(value.reason ? [[t('confirm.reason'), value.reason]] : []),
  ]
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}>
      <View style={styles.modalBackdrop} testID="e2e.confirm.backdrop">
        <View style={styles.sheet} accessibilityViewIsModal testID="e2e.confirm.sheet">
          <View style={styles.sheetHandle} />
          <Text style={[styles.sheetTitle, { textAlign: isRTL ? 'right' : 'left' }]}>
            {t('confirm.title')}
          </Text>
          {rows.map(([label, content]) => (
            <View key={label} style={styles.confirmRow}>
              <Text style={[styles.confirmLabel, { textAlign: isRTL ? 'right' : 'left' }]}>{label}</Text>
              <Text style={[styles.confirmValue, { textAlign: isRTL ? 'right' : 'left' }]}>{content}</Text>
            </View>
          ))}
          {error ? (
            <Text
              accessibilityLiveRegion="polite"
              accessibilityRole="alert"
              testID="e2e.confirm.error"
              style={[styles.confirmError, { textAlign: isRTL ? 'right' : 'left' }]}
            >
              {error}
            </Text>
          ) : null}
          <View style={[styles.sheetActions, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
            <View style={styles.flex}>
              <ActionButton
                testID="e2e.confirm.cancel"
                label={t('common.cancel')}
                tone="secondary"
                onPress={onCancel}
                disabled={loading}
              />
            </View>
            <View style={styles.flex}>
              <ActionButton
                testID="e2e.confirm.submit"
                label={t('common.confirm')}
                tone="danger"
                onPress={onConfirm}
                loading={loading}
              />
            </View>
          </View>
        </View>
      </View>
    </Modal>
  )
}

export function StatePanel({
  title,
  body,
  icon = 'sparkles-outline',
  action,
  onAction,
}: {
  title: string
  body: string
  icon?: keyof typeof Ionicons.glyphMap
  action?: string
  onAction?: () => void
}) {
  const { isRTL } = useLocale()
  return (
    <View style={styles.statePanel}>
      <View style={styles.stateIcon}>
        <Ionicons name={icon} size={24} color={colors.plum} />
      </View>
      <Text style={[styles.stateTitle, { textAlign: isRTL ? 'right' : 'left' }]}>{title}</Text>
      <Text style={[styles.stateBody, { textAlign: isRTL ? 'right' : 'left' }]}>{body}</Text>
      {action ? <ActionButton label={action} onPress={onAction} tone="secondary" /> : null}
    </View>
  )
}

export function Skeleton({ lines = 4 }: { lines?: number }) {
  return (
    <View accessibilityLabel="Loading" accessibilityRole="progressbar" style={styles.skeletonCard}>
      {Array.from({ length: lines }).map((_, index) => (
        <View
          key={index}
          style={[styles.skeletonLine, { width: index === lines - 1 ? '62%' : `${92 - index * 7}%` }]}
        />
      ))}
    </View>
  )
}

const cardTones = StyleSheet.create({
  cream: { backgroundColor: colors.surface },
  lilac: { backgroundColor: colors.lilac },
  sage: { backgroundColor: colors.sageSoft },
  amber: { backgroundColor: colors.amberSoft },
  coral: { backgroundColor: colors.coralSoft },
  sky: { backgroundColor: colors.skySoft },
})
const badgeTones = StyleSheet.create({
  neutral: { backgroundColor: colors.surfaceStrong },
  attention: { backgroundColor: colors.amberSoft },
  success: { backgroundColor: colors.sageSoft },
  danger: { backgroundColor: colors.dangerSoft },
  info: { backgroundColor: colors.skySoft },
})
const badgeTextTones = StyleSheet.create({
  neutral: { color: colors.muted },
  attention: { color: colors.amber },
  success: { color: colors.sage },
  danger: { color: colors.danger },
  info: { color: colors.sky },
})
const actionTones = StyleSheet.create({
  primary: { backgroundColor: colors.ink },
  secondary: { backgroundColor: colors.surface, borderColor: colors.line, borderWidth: 1 },
  danger: { backgroundColor: colors.danger },
})

const styles = StyleSheet.create({
  flex: { flex: 1 },
  safe: { flex: 1, backgroundColor: colors.canvas },
  safeEmbed: { width: '100%', backgroundColor: colors.canvas },
  scroll: { flex: 1, backgroundColor: colors.canvas },
  scrollContent: { flexGrow: 1 },
  screenContent: { width: '100%', maxWidth: 720, alignSelf: 'center', padding: spacing.xl, gap: spacing.xl },
  headingWrap: { gap: spacing.sm },
  eyebrow: { color: colors.plum, fontSize: typography.label, fontWeight: '800', letterSpacing: 0.8, textTransform: 'uppercase' },
  hero: { color: colors.ink, fontSize: typography.hero, lineHeight: 43, fontWeight: '500', letterSpacing: -1.1 },
  wordmark: { color: colors.ink, fontSize: 24, lineHeight: 32, letterSpacing: -0.5 },
  wordmarkCompact: { fontSize: 18, lineHeight: 24 },
  wordmarkRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, maxWidth: '82%' },
  wordmarkRowRTL: { flexDirection: 'row-reverse' },
  wordmarkLogo: { width: 34, height: 34, borderRadius: 9, resizeMode: 'contain' },
  wordmarkLogoCompact: { width: 26, height: 26, borderRadius: 7 },
  workspaceHeader: { alignItems: 'center', justifyContent: 'space-between', gap: spacing.md },
  headerLeading: { flex: 1, alignItems: 'center', gap: spacing.sm, minWidth: 0 },
  headerBack: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  headerText: { flex: 1, minWidth: 0, gap: 2 },
  companyRow: { alignItems: 'center', gap: 6 },
  companyDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.sage },
  company: { color: colors.muted, fontSize: typography.label, fontWeight: '700' },
  scopeLabel: { color: colors.faint, fontSize: typography.micro },
  localeButton: { minWidth: 44, minHeight: 44, borderRadius: 22, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.line },
  localeText: { color: colors.ink, fontWeight: '800', fontSize: 15 },
  badge: { minHeight: 28, justifyContent: 'center', borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 6 },
  badgeText: { fontSize: typography.micro, fontWeight: '800', textTransform: 'capitalize' },
  identityRow: { gap: spacing.md, alignItems: 'center' },
  avatar: { width: 52, height: 52, borderRadius: 18, backgroundColor: colors.plumSoft, alignItems: 'center', justifyContent: 'center' },
  avatarText: { color: colors.plum, fontWeight: '900', fontSize: 16 },
  identityText: { flex: 1, gap: 2 },
  identityName: { color: colors.ink, fontSize: 19, fontWeight: '800' },
  identitySubtitle: { color: colors.muted, fontSize: typography.body },
  identityMeta: { color: colors.faint, fontSize: typography.label },
  card: { borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md, ...shadows.card },
  priorityCard: { minHeight: 122, backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md, borderWidth: 1, borderColor: colors.line, ...shadows.card },
  priorityTop: { alignItems: 'center', justifyContent: 'space-between', gap: spacing.md },
  priorityTitle: { flex: 1, color: colors.ink, fontSize: typography.label, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.45 },
  prioritySummary: { color: colors.ink, fontSize: 17, lineHeight: 24, fontWeight: '700' },
  priorityMeta: { color: colors.muted, fontSize: typography.label, lineHeight: 18 },
  reviewRow: { minHeight: 28, alignItems: 'center', gap: 2, alignSelf: 'flex-end' },
  reviewText: { color: colors.plum, fontSize: typography.label, fontWeight: '800' },
  actionableCard: { minHeight: 116, backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm, borderWidth: 1, borderColor: colors.line, ...shadows.card },
  actionableTop: { alignItems: 'flex-start', justifyContent: 'space-between', gap: spacing.md },
  actionableTitle: { flex: 1, color: colors.ink, fontSize: 17, lineHeight: 23, fontWeight: '800' },
  actionableSubtitle: { color: colors.muted, fontSize: typography.body, lineHeight: 21 },
  actionableBottom: { minHeight: 28, alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  actionableMeta: { flex: 1, color: colors.faint, fontSize: typography.label },
  evidenceTitleRow: { alignItems: 'center', gap: spacing.sm },
  evidenceTitle: { color: colors.ink, fontSize: typography.section, fontWeight: '800' },
  evidenceRow: { gap: spacing.sm, alignItems: 'flex-start' },
  bullet: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.ink, marginTop: 7 },
  evidenceText: { flex: 1, color: colors.ink, fontSize: typography.body, lineHeight: 22 },
  action: { minHeight: 50, borderRadius: radius.md, paddingHorizontal: spacing.lg, alignItems: 'center', justifyContent: 'center' },
  actionText: { color: colors.white, fontSize: typography.body, fontWeight: '800' },
  actionTextDark: { color: colors.ink },
  disabled: { opacity: 0.46 },
  pressed: { opacity: 0.78, transform: [{ scale: 0.992 }] },
  pressedReduced: { opacity: 0.78 },
  pressedLift: { opacity: 0.9, transform: [{ translateY: 1 }, { scale: 0.995 }] },
  modalBackdrop: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(28,26,24,0.38)' },
  sheet: { backgroundColor: colors.canvas, padding: spacing.xl, paddingBottom: spacing.xxxl, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, gap: spacing.lg, ...shadows.floating },
  sheetHandle: { width: 42, height: 4, borderRadius: 2, backgroundColor: colors.line, alignSelf: 'center' },
  sheetTitle: { color: colors.ink, fontSize: typography.title, fontWeight: '800' },
  confirmRow: { gap: spacing.xs, borderBottomWidth: 1, borderBottomColor: colors.line, paddingBottom: spacing.md },
  confirmLabel: { color: colors.faint, fontSize: typography.micro, fontWeight: '800', textTransform: 'uppercase' },
  confirmValue: { color: colors.ink, fontSize: typography.body, lineHeight: 22, fontWeight: '600' },
  confirmError: { color: colors.danger, fontSize: typography.label, lineHeight: 20, fontWeight: '600', marginTop: 4 },
  sheetActions: { gap: spacing.md },
  statePanel: { minHeight: 260, alignItems: 'center', justifyContent: 'center', gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.xl, padding: spacing.xxl, borderWidth: 1, borderColor: colors.line },
  stateIcon: { width: 54, height: 54, borderRadius: 20, backgroundColor: colors.plumSoft, alignItems: 'center', justifyContent: 'center' },
  stateTitle: { color: colors.ink, fontSize: typography.section, fontWeight: '800' },
  stateBody: { color: colors.muted, fontSize: typography.body, lineHeight: 22 },
  skeletonCard: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md, borderWidth: 1, borderColor: colors.line },
  skeletonLine: { height: 15, borderRadius: radius.pill, backgroundColor: colors.line },
})
