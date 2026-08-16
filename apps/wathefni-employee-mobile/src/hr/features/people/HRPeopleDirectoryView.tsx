import { useEffect, useMemo, useState } from 'react'
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'
import Ionicons from '@expo/vector-icons/Ionicons'
import { useRouter } from 'expo-router'
import { useInfiniteQuery } from '@tanstack/react-query'

import { mobileApi } from '@hr/api/mobile'
import type { EmployeeSummary, MobileMe } from '@hr/api/types'
import { useAuth } from '@hr/auth/AuthProvider'
import { routeAvailable } from '@hr/capabilities'
import { toHrPath } from '@hr/navigation'
import { useHrSafeBack } from '@hr/useHrSafeBack'
import { HrPushedNav } from '@hr/components/HrPushedNav'
import {
  PEOPLE_PAGE_SIZE,
  filterPeopleRows,
  peopleExceptionChip,
  peopleSecondaryLine,
  uniqueDepartments,
  type PeopleFilterPanel,
  type PeopleStatusFilter,
} from '@hr/features/people/peopleComposition'
import { PageScreen, useScrollBottomPadding } from '@/components/layout'
import { ListRow } from '@/components/lists'
import { EditorialHeading, Wordmark } from '@/components/premium'
import { StatusChip } from '@/components/ui'
import { useI18n, readingEdgeAlign } from '@/i18n'
import { colors, font, layout, radius, spacing, typeScaling } from '@/theme'
import { resolveCompanyBrand } from '@/branding/CompanyBrand'

/**
 * People root — directory / search. Not a status dashboard.
 * Search primary · lightweight filters · dense rows · exceptional chips only.
 */
export function HRPeopleDirectoryView({ showBack = false }: { showBack?: boolean }) {
  const router = useRouter()
  const onBack = useHrSafeBack()
  const { me, request } = useAuth()
  const { t, isRTL } = useI18n()
  const align = readingEdgeAlign(isRTL)
  const paddingBottom = useScrollBottomPadding()
  const permitted = routeAvailable(me, 'employees')

  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<PeopleStatusFilter>('active')
  const [department, setDepartment] = useState<string | null>(null)
  const [onboardingOpenOnly, setOnboardingOpenOnly] = useState(false)
  const [panel, setPanel] = useState<PeopleFilterPanel>(null)

  useEffect(() => {
    const handle = setTimeout(() => setSearch(searchInput.trim()), 280)
    return () => clearTimeout(handle)
  }, [searchInput])

  const query = useInfiniteQuery({
    queryKey: ['hr-people', me?.principal.user_id, search],
    enabled: Boolean(me) && permitted,
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) =>
      mobileApi.employees(request, {
        search,
        offset: pageParam,
        limit: PEOPLE_PAGE_SIZE,
        signal,
      }),
    getNextPageParam: (last) => {
      if (!last.has_more) return undefined
      const offset = typeof last.offset === 'number' ? last.offset : 0
      const limit = typeof last.limit === 'number' ? last.limit : PEOPLE_PAGE_SIZE
      return offset + limit
    },
  })

  const loaded = useMemo(
    () => (query.data?.pages || []).flatMap((page) => page.items),
    [query.data],
  )

  const departments = useMemo(() => uniqueDepartments(loaded), [loaded])
  const rows = useMemo(
    () =>
      filterPeopleRows(loaded, {
        status: statusFilter,
        department,
        onboardingOpenOnly,
      }),
    [loaded, statusFilter, department, onboardingOpenOnly],
  )

  const resetFilters = () => {
    setStatusFilter('active')
    setDepartment(null)
    setOnboardingOpenOnly(false)
    setPanel(null)
  }

  const statusLabel =
    statusFilter === 'left'
      ? t('hrPeople.filterLeft')
      : statusFilter === 'all'
        ? t('hrPeople.filterEveryone')
        : t('hrPeople.filterActive')

  if (!me) return null

  return (
    <PageScreen>
      <FlatList
        data={rows}
        keyExtractor={(item) => item.employee_key}
        contentContainerStyle={{
          paddingHorizontal: layout.pageMargin,
          paddingTop: layout.pageTop,
          paddingBottom,
          gap: spacing.xs,
          flexGrow: 1,
        }}
        keyboardShouldPersistTaps="handled"
        automaticallyAdjustKeyboardInsets
        refreshing={query.isRefetching && !query.isFetchingNextPage}
        onRefresh={() => void query.refetch()}
        onEndReached={() => {
          if (query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage()
        }}
        onEndReachedThreshold={0.4}
        ListHeaderComponent={
          <View style={styles.headerBlock}>
            {showBack ? (
              <HrPushedNav onBack={onBack} accessibilityLabel={t('common.back')} />
            ) : (
              <Wordmark />
            )}
            <EditorialHeading>{t('hrPeople.heading')}</EditorialHeading>
            <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.subtitle, align]}>
              {t('hrPeople.subtitle')}
            </Text>

            <View style={styles.searchWrap}>
              <Ionicons name="search-outline" size={18} color={colors.subtle} />
              <TextInput
                accessibilityLabel={t('hrPeople.searchPlaceholder')}
                value={searchInput}
                onChangeText={setSearchInput}
                placeholder={t('hrPeople.searchPlaceholder')}
                placeholderTextColor={colors.navMuted}
                autoCorrect={false}
                autoCapitalize="none"
                returnKeyType="search"
                style={[styles.searchInput, align]}
              />
              {searchInput ? (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={t('hrPeople.clearSearch')}
                  hitSlop={8}
                  onPress={() => setSearchInput('')}
                >
                  <Ionicons name="close-circle" size={18} color={colors.subtle} />
                </Pressable>
              ) : null}
            </View>

            <View style={styles.filterRow}>
              <FilterChip
                label={t('hrPeople.filterAll')}
                active={statusFilter === 'active' && !department && !onboardingOpenOnly}
                onPress={resetFilters}
              />
              <FilterChip
                label={department || t('hrPeople.filterDepartment')}
                active={Boolean(department) || panel === 'department'}
                onPress={() => setPanel((p) => (p === 'department' ? null : 'department'))}
              />
              <FilterChip
                label={statusLabel}
                active={statusFilter !== 'active' || panel === 'status'}
                onPress={() => setPanel((p) => (p === 'status' ? null : 'status'))}
              />
              <FilterChip
                label={t('hrPeople.filterMore')}
                active={onboardingOpenOnly || panel === 'more'}
                onPress={() => setPanel((p) => (p === 'more' ? null : 'more'))}
              />
            </View>

            {panel === 'department' ? (
              <View style={styles.subFilters}>
                <FilterChip
                  label={t('hrPeople.anyDepartment')}
                  active={!department}
                  onPress={() => {
                    setDepartment(null)
                    setPanel(null)
                  }}
                />
                {departments.map((dept) => (
                  <FilterChip
                    key={dept}
                    label={dept}
                    active={department === dept}
                    onPress={() => {
                      setDepartment(dept)
                      setPanel(null)
                    }}
                  />
                ))}
              </View>
            ) : null}

            {panel === 'status' ? (
              <View style={styles.subFilters}>
                {(
                  [
                    ['active', 'hrPeople.filterActive'],
                    ['left', 'hrPeople.filterLeft'],
                    ['all', 'hrPeople.filterEveryone'],
                  ] as const
                ).map(([value, key]) => (
                  <FilterChip
                    key={value}
                    label={t(key)}
                    active={statusFilter === value}
                    onPress={() => {
                      setStatusFilter(value)
                      setPanel(null)
                    }}
                  />
                ))}
              </View>
            ) : null}

            {panel === 'more' ? (
              <View style={styles.subFilters}>
                <FilterChip
                  label={t('hrPeople.filterOnboardingOpen')}
                  active={onboardingOpenOnly}
                  onPress={() => setOnboardingOpenOnly((v) => !v)}
                />
              </View>
            ) : null}
          </View>
        }
        ListEmptyComponent={
          <PeopleEmpty
            me={me}
            permitted={permitted}
            loading={query.isLoading}
            error={Boolean(query.error)}
            searching={Boolean(search)}
            onRetry={() => void query.refetch()}
          />
        }
        ListFooterComponent={
          query.isFetchingNextPage ? (
            <View style={styles.footerLoad}>
              <ActivityIndicator color={colors.subtle} />
            </View>
          ) : query.hasNextPage ? (
            <Pressable
              accessibilityRole="button"
              onPress={() => void query.fetchNextPage()}
              style={styles.loadMore}
            >
              <Text style={styles.loadMoreText}>{t('hrPeople.loadMore')}</Text>
            </Pressable>
          ) : null
        }
        renderItem={({ item }) => {
          const chip = peopleExceptionChip(item.employee)
          const canOpenOnboarding =
            chip?.key === 'onboarding' && routeAvailable(me, 'onboarding')
          return (
            <PeopleRow
              item={item}
              onPress={() =>
                router.push(
                  toHrPath(`/employees/${encodeURIComponent(item.employee_key)}`) as never,
                )
              }
              onOnboardingPress={
                canOpenOnboarding
                  ? () =>
                      router.push(
                        toHrPath(
                          `/onboarding/${encodeURIComponent(item.employee_key)}`,
                        ) as never,
                      )
                  : undefined
              }
            />
          )
        }}
      />
    </PageScreen>
  )
}

function PeopleRow({
  item,
  onPress,
  onOnboardingPress,
}: {
  item: EmployeeSummary
  onPress: () => void
  /** Onboarding chip only — never hijacks the row's profile path. */
  onOnboardingPress?: () => void
}) {
  const { t } = useI18n()
  const chip = peopleExceptionChip(item.employee)
  const secondary = peopleSecondaryLine(item.employee)
  const trailing =
    chip?.key === 'onboarding' && onOnboardingPress ? (
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={t(chip.labelKey)}
        hitSlop={8}
        onPress={onOnboardingPress}
      >
        <StatusChip label={t(chip.labelKey)} tone={chip.tone} />
      </Pressable>
    ) : chip ? (
      <StatusChip label={t(chip.labelKey)} tone={chip.tone} />
    ) : null
  return (
    <ListRow
      title={item.employee.name}
      subtitle={secondary || null}
      trailing={trailing}
      showChevron
      onPress={onPress}
      accessibilityLabel={
        chip ? `${item.employee.name}. ${t(chip.labelKey)}` : item.employee.name
      }
      style={styles.row}
    />
  )
}

function FilterChip({
  label,
  active,
  onPress,
}: {
  label: string
  active: boolean
  onPress: () => void
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      onPress={onPress}
      style={[styles.chip, active ? styles.chipActive : null]}
    >
      <Text
        maxFontSizeMultiplier={typeScaling.chip}
        numberOfLines={1}
        style={[styles.chipText, active ? styles.chipTextActive : null]}
      >
        {label}
      </Text>
    </Pressable>
  )
}

function PeopleEmpty({
  me,
  permitted,
  loading,
  error,
  searching,
  onRetry,
}: {
  me: MobileMe
  permitted: boolean
  loading: boolean
  error: boolean
  searching: boolean
  onRetry: () => void
}) {
  const { t, isRTL, locale } = useI18n()
  const align = readingEdgeAlign(isRTL)
  if (!permitted) {
    return (
      <ListRow
        title={t('hrPeople.permissionTitle')}
        subtitle={t('hrPeople.permissionBody')}
        icon="lock-closed-outline"
      />
    )
  }
  if (loading) {
    return <ListRow title={t('home.dataLoading')} icon="hourglass-outline" />
  }
  if (error) {
    return (
      <ListRow
        title={t('home.dataUnavailable')}
        subtitle={t('home.dataUnavailableHint')}
        icon="cloud-offline-outline"
        emphasis="warning"
        showChevron
        onPress={onRetry}
      />
    )
  }
  return (
    <View style={styles.empty}>
      <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.emptyTitle, align]}>
        {searching ? t('hrPeople.emptySearch') : t('hrPeople.empty')}
      </Text>
      <Text maxFontSizeMultiplier={typeScaling.body} style={[styles.emptyBody, align]}>
        {searching
          ? t('hrPeople.emptySearchBody')
          : t('hrPeople.emptyBody', { company: resolveCompanyBrand(me.company_identity, locale).name })}
      </Text>
    </View>
  )
}

const styles = StyleSheet.create({
  headerBlock: {
    gap: spacing.md,
    marginBottom: spacing.md,
  },
  subtitle: {
    fontSize: font.small,
    color: colors.subtle,
    marginTop: -spacing.xs,
  },
  searchWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    minHeight: layout.touchTarget,
  },
  searchInput: {
    flex: 1,
    fontSize: font.body,
    color: colors.ink,
    paddingVertical: spacing.sm,
  },
  filterRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  subFilters: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceMuted,
  },
  chipActive: {
    backgroundColor: colors.ink,
  },
  chipText: {
    fontSize: font.tiny,
    fontWeight: '700',
    color: colors.subtle,
  },
  chipTextActive: {
    color: colors.primaryText,
  },
  row: {
    backgroundColor: colors.surface,
  },
  footerLoad: {
    paddingVertical: spacing.lg,
    alignItems: 'center',
  },
  loadMore: {
    alignItems: 'center',
    paddingVertical: spacing.md,
  },
  loadMoreText: {
    fontSize: font.small,
    fontWeight: '700',
    color: colors.subtle,
  },
  empty: {
    paddingVertical: spacing.xxl,
    gap: spacing.sm,
  },
  emptyTitle: {
    fontSize: font.body,
    fontWeight: '700',
    color: colors.ink,
  },
  emptyBody: {
    fontSize: font.small,
    color: colors.subtle,
  },
})
