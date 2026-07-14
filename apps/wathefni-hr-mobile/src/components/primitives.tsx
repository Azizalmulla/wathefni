import { useEffect, useRef, type ReactNode } from 'react'
import {
  ActivityIndicator,
  Animated,
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
import { SafeAreaView } from 'react-native-safe-area-context'

import { useLocale } from '@/i18n'
import { motion, useReducedMotion } from '@/motion'
import { colors, radius, shadows, spacing, type as typography } from '@/theme'

export function Screen({
  children,
  scroll = true,
  contentStyle,
}: {
  children: ReactNode
  scroll?: boolean
  contentStyle?: StyleProp<ViewStyle>
}) {
  const body = <View style={[styles.screenContent, contentStyle]}>{children}</View>
  return (
    <SafeAreaView style={styles.safe}>
      {scroll ? (
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          {body}
        </ScrollView>
      ) : (
        body
      )}
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
  const { t, locale, isRTL } = useLocale()
  return (
    <Text
      accessibilityRole="header"
      accessibilityLabel={t('brand.wordmark')}
      maxFontSizeMultiplier={1.2}
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
      {t('brand.wordmark')}
    </Text>
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
}: {
  company: string
  scopeLabel?: string
  onLocale?: () => void
}) {
  const { locale, isRTL } = useLocale()
  return (
    <View style={[styles.workspaceHeader, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
      <View style={styles.headerText}>
        <Wordmark compact />
        <View style={[styles.companyRow, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
          <View style={styles.companyDot} />
          <Text style={[styles.company, { textAlign: isRTL ? 'right' : 'left' }]}>{company}</Text>
          {scopeLabel ? <Text style={styles.scopeLabel}>· {scopeLabel}</Text> : null}
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
  const { isRTL } = useLocale()
  return (
    <Pressable
      accessibilityRole={onPress ? 'button' : undefined}
      accessibilityLabel={`${title}. ${summary}. ${status}`}
      onPress={onPress}
      disabled={!onPress}
      style={({ pressed }) => [styles.priorityCard, pressed && styles.pressed]}
    >
      <View style={[styles.priorityTop, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
        <Text style={[styles.priorityTitle, { textAlign: isRTL ? 'right' : 'left' }]}>{title}</Text>
        <StatusBadge label={status} tone={severity === 'high' ? 'danger' : 'attention'} />
      </View>
      <Text style={[styles.prioritySummary, { textAlign: isRTL ? 'right' : 'left' }]}>{summary}</Text>
      {meta ? <Text style={[styles.priorityMeta, { textAlign: isRTL ? 'right' : 'left' }]}>{meta}</Text> : null}
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
}: {
  label: string
  onPress?: () => void
  tone?: 'primary' | 'secondary' | 'danger'
  disabled?: boolean
  loading?: boolean
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: disabled || loading, busy: loading }}
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [
        styles.action,
        actionTones[tone],
        (disabled || loading) && styles.disabled,
        pressed && styles.pressed,
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
}: {
  visible: boolean
  value: ConfirmationView | null
  onCancel: () => void
  onConfirm: () => void
  loading?: boolean
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
      <View style={styles.modalBackdrop}>
        <View style={styles.sheet} accessibilityViewIsModal>
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
          <View style={[styles.sheetActions, { flexDirection: isRTL ? 'row-reverse' : 'row' }]}>
            <View style={styles.flex}>
              <ActionButton label={t('common.cancel')} tone="secondary" onPress={onCancel} disabled={loading} />
            </View>
            <View style={styles.flex}>
              <ActionButton label={t('common.confirm')} tone="danger" onPress={onConfirm} loading={loading} />
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
  safe: { flex: 1, backgroundColor: colors.canvas },
  scroll: { flex: 1, backgroundColor: colors.canvas },
  scrollContent: { flexGrow: 1 },
  screenContent: { width: '100%', maxWidth: 720, alignSelf: 'center', padding: spacing.xl, gap: spacing.xl },
  headingWrap: { gap: spacing.sm },
  eyebrow: { color: colors.plum, fontSize: typography.label, fontWeight: '800', letterSpacing: 0.8, textTransform: 'uppercase' },
  hero: { color: colors.ink, fontSize: typography.hero, lineHeight: 43, fontWeight: '500', letterSpacing: -1.1 },
  wordmark: { color: colors.ink, fontSize: 24, lineHeight: 32, letterSpacing: -0.5 },
  wordmarkCompact: { fontSize: 18, lineHeight: 24 },
  workspaceHeader: { alignItems: 'center', justifyContent: 'space-between', gap: spacing.md },
  headerText: { flex: 1, gap: spacing.xs },
  companyRow: { alignItems: 'center', gap: 6 },
  companyDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.sage },
  company: { color: colors.muted, fontSize: typography.label, fontWeight: '700' },
  scopeLabel: { color: colors.faint, fontSize: typography.micro },
  localeButton: { minWidth: 44, minHeight: 44, borderRadius: 22, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.line },
  localeText: { color: colors.ink, fontWeight: '800', fontSize: 15 },
  badge: { borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 6 },
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
  modalBackdrop: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(28,26,24,0.38)' },
  sheet: { backgroundColor: colors.canvas, padding: spacing.xl, paddingBottom: spacing.xxxl, borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, gap: spacing.lg, ...shadows.floating },
  sheetHandle: { width: 42, height: 4, borderRadius: 2, backgroundColor: colors.line, alignSelf: 'center' },
  sheetTitle: { color: colors.ink, fontSize: typography.title, fontWeight: '800' },
  confirmRow: { gap: spacing.xs, borderBottomWidth: 1, borderBottomColor: colors.line, paddingBottom: spacing.md },
  confirmLabel: { color: colors.faint, fontSize: typography.micro, fontWeight: '800', textTransform: 'uppercase' },
  confirmValue: { color: colors.ink, fontSize: typography.body, lineHeight: 22, fontWeight: '600' },
  sheetActions: { gap: spacing.md },
  flex: { flex: 1 },
  statePanel: { minHeight: 260, alignItems: 'center', justifyContent: 'center', gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.xl, padding: spacing.xxl, borderWidth: 1, borderColor: colors.line },
  stateIcon: { width: 54, height: 54, borderRadius: 20, backgroundColor: colors.plumSoft, alignItems: 'center', justifyContent: 'center' },
  stateTitle: { color: colors.ink, fontSize: typography.section, fontWeight: '800' },
  stateBody: { color: colors.muted, fontSize: typography.body, lineHeight: 22 },
  skeletonCard: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md, borderWidth: 1, borderColor: colors.line },
  skeletonLine: { height: 15, borderRadius: radius.pill, backgroundColor: colors.line },
})
