import {
  DEFAULT_CLASSIFICATION_FILTERS,
  type ClassificationFiltersState,
} from '@/components/candidates/ClassificationFilters'
import type { CandidateFilters } from '@/types'
import type { RecruitingLocale } from '@/lib/recruitingLifecycle'
import { CANDIDATE_LIST_STAGE_FILTERS } from '@/lib/candidatesListPresentation'

export type CandidateFilterChipId =
  | 'followUp'
  | 'reviewStatus'
  | 'assessmentStatus'
  | 'interviewStatus'
  | 'sourceChannel'
  | 'cvStatus'
  | 'sort'
  | 'recruiterOwner'
  | 'cvProcessingState'
  | 'receivedFrom'
  | 'receivedTo'
  | 'activityFrom'
  | 'activityTo'
  | 'hasGroundedEmail'
  | 'hasGroundedPhone'
  | 'factCompleteness'
  | 'departmentIntakeTag'
  | 'overviewCohort'
  | 'classification'

export type CandidateFilterChip = {
  id: CandidateFilterChipId
  label: string
  /** When set, clearing uses this CandidateFilters key (empty string). */
  filterKey?: keyof CandidateFilters
}

function labelFor(
  locale: RecruitingLocale,
  en: string,
  ar: string,
): string {
  return locale === 'ar' ? ar : en
}

function optionLabel(
  locale: RecruitingLocale,
  value: string,
  map: Record<string, { en: string; ar: string }>,
): string {
  const hit = map[value]
  if (!hit) return value
  return locale === 'ar' ? hit.ar : hit.en
}

const SOURCE: Record<string, { en: string; ar: string }> = {
  email: { en: 'Email', ar: 'البريد الإلكتروني' },
  whatsapp: { en: 'WhatsApp', ar: 'واتساب' },
  bulk: { en: 'Manual upload', ar: 'رفع يدوي' },
  dashboard: { en: 'Manual upload', ar: 'رفع يدوي' },
}

const CV_STATUS: Record<string, { en: string; ar: string }> = {
  with_cv: { en: 'CV received', ar: 'تم استلام السيرة' },
  incomplete: { en: 'Started but no CV', ar: 'بدأ بدون سيرة' },
  all: { en: 'All applications', ar: 'كل الطلبات' },
}

const ASSESSMENT: Record<string, { en: string; ar: string }> = {
  awaiting: { en: 'Awaiting assessment', ar: 'بانتظار التقييم' },
  none: { en: 'No assessment yet', ar: 'لا تقييم بعد' },
  pending: { en: 'Pending', ar: 'قيد الانتظار' },
  started: { en: 'Started', ar: 'بدأ' },
  completed: { en: 'Completed', ar: 'مكتمل' },
  expired: { en: 'Expired', ar: 'منتهي' },
}

const INTERVIEW: Record<string, { en: string; ar: string }> = {
  none: { en: 'No interview yet', ar: 'لا مقابلة بعد' },
  scheduled: { en: 'Scheduled', ar: 'مجدولة' },
  completed: { en: 'Completed', ar: 'مكتملة' },
  no_show: { en: 'No-show', ar: 'لم يحضر' },
  cancelled: { en: 'Cancelled', ar: 'ملغاة' },
}

const SORT: Record<string, { en: string; ar: string }> = {
  last_activity: { en: 'Last activity', ar: 'آخر نشاط' },
  ready_for_review: { en: 'Ready for review first', ar: 'جاهز للمراجعة أولاً' },
  assessment_complete: { en: 'Assessment complete first', ar: 'التقييم المكتمل أولاً' },
  ranking_score: { en: 'Ranking score', ar: 'درجة الترتيب' },
}

const CV_PROCESSING: Record<string, { en: string; ar: string }> = {
  ready: { en: 'CV ready', ar: 'سيرة جاهزة' },
  partial: { en: 'CV partial', ar: 'سيرة جزئية' },
  failed: { en: 'CV failed', ar: 'فشل السيرة' },
}

export function classificationActiveCount(filters: ClassificationFiltersState): number {
  return Object.values(filters.dimensionNodes || {}).reduce((sum, ids) => sum + (ids?.length || 0), 0)
    + (filters.confidence ? 1 : 0)
    + (filters.includeMediumAi ? 1 : 0)
    + (filters.authority !== 'confirmed_or_high_ai' ? 1 : 0)
}

/** Specialist / context chips shown on the default bar (not Search / Job / Stage controls). */
export function buildCandidateFilterChips(input: {
  filters: CandidateFilters
  locale: RecruitingLocale
  classificationEnabled?: boolean
  classificationFilters?: ClassificationFiltersState
}): CandidateFilterChip[] {
  const { filters, locale } = input
  const chips: CandidateFilterChip[] = []

  if (filters.followUp === 'needed') {
    chips.push({
      id: 'followUp',
      filterKey: 'followUp',
      label: labelFor(locale, 'Follow-up needed', 'يحتاج متابعة'),
    })
  }
  if (filters.reviewStatus) {
    chips.push({
      id: 'reviewStatus',
      filterKey: 'reviewStatus',
      label: labelFor(locale, `Review: ${filters.reviewStatus}`, `مراجعة: ${filters.reviewStatus}`),
    })
  }
  if (filters.overviewCohort && filters.overviewCohort !== 'follow_up_needed') {
    chips.push({
      id: 'overviewCohort',
      filterKey: 'overviewCohort',
      label: labelFor(locale, `Context: ${filters.overviewCohort}`, `سياق: ${filters.overviewCohort}`),
    })
  }
  if (filters.assessmentStatus) {
    chips.push({
      id: 'assessmentStatus',
      filterKey: 'assessmentStatus',
      label: optionLabel(locale, filters.assessmentStatus, ASSESSMENT),
    })
  }
  if (filters.interviewStatus) {
    chips.push({
      id: 'interviewStatus',
      filterKey: 'interviewStatus',
      label: optionLabel(locale, filters.interviewStatus, INTERVIEW),
    })
  }
  if (filters.sourceChannel) {
    chips.push({
      id: 'sourceChannel',
      filterKey: 'sourceChannel',
      label: optionLabel(locale, filters.sourceChannel, SOURCE),
    })
  }
  if (filters.cvStatus) {
    chips.push({
      id: 'cvStatus',
      filterKey: 'cvStatus',
      label: optionLabel(locale, filters.cvStatus, CV_STATUS),
    })
  }
  if (filters.sort && filters.sort !== 'newest') {
    chips.push({
      id: 'sort',
      filterKey: 'sort',
      label: optionLabel(locale, filters.sort, SORT),
    })
  }
  if (filters.recruiterOwner) {
    chips.push({
      id: 'recruiterOwner',
      filterKey: 'recruiterOwner',
      label: filters.recruiterOwner === 'unassigned'
        ? labelFor(locale, 'Unassigned recruiter', 'مسؤول غير معيّن')
        : filters.recruiterOwner,
    })
  }
  if (filters.cvProcessingState) {
    chips.push({
      id: 'cvProcessingState',
      filterKey: 'cvProcessingState',
      label: optionLabel(locale, filters.cvProcessingState, CV_PROCESSING),
    })
  }
  if (filters.receivedFrom) {
    chips.push({
      id: 'receivedFrom',
      filterKey: 'receivedFrom',
      label: labelFor(locale, `From ${filters.receivedFrom}`, `من ${filters.receivedFrom}`),
    })
  }
  if (filters.receivedTo) {
    chips.push({
      id: 'receivedTo',
      filterKey: 'receivedTo',
      label: labelFor(locale, `To ${filters.receivedTo}`, `إلى ${filters.receivedTo}`),
    })
  }
  if (filters.activityFrom) {
    chips.push({
      id: 'activityFrom',
      filterKey: 'activityFrom',
      label: labelFor(locale, `Activity from ${filters.activityFrom}`, `نشاط من ${filters.activityFrom}`),
    })
  }
  if (filters.activityTo) {
    chips.push({
      id: 'activityTo',
      filterKey: 'activityTo',
      label: labelFor(locale, `Activity to ${filters.activityTo}`, `نشاط إلى ${filters.activityTo}`),
    })
  }
  if (filters.hasGroundedEmail) {
    chips.push({
      id: 'hasGroundedEmail',
      filterKey: 'hasGroundedEmail',
      label: labelFor(locale, 'Grounded email', 'بريد موثّق'),
    })
  }
  if (filters.hasGroundedPhone) {
    chips.push({
      id: 'hasGroundedPhone',
      filterKey: 'hasGroundedPhone',
      label: labelFor(locale, 'Grounded phone', 'هاتف موثّق'),
    })
  }
  if (filters.factCompleteness) {
    chips.push({
      id: 'factCompleteness',
      filterKey: 'factCompleteness',
      label: labelFor(locale, `Completeness: ${filters.factCompleteness}`, `اكتمال: ${filters.factCompleteness}`),
    })
  }
  if (filters.departmentIntakeTag) {
    chips.push({
      id: 'departmentIntakeTag',
      filterKey: 'departmentIntakeTag',
      label: filters.departmentIntakeTag,
    })
  }

  const classFilters = input.classificationFilters || DEFAULT_CLASSIFICATION_FILTERS
  if (input.classificationEnabled && classificationActiveCount(classFilters) > 0) {
    const n = classificationActiveCount(classFilters)
    chips.push({
      id: 'classification',
      label: labelFor(locale, `Classification (${n})`, `التصنيف (${n})`),
    })
  }

  return chips
}

export function stageFilterLabel(status: string, locale: RecruitingLocale): string {
  const hit = CANDIDATE_LIST_STAGE_FILTERS.find((item) => item.value === status)
  if (!hit) return status
  return locale === 'ar' ? hit.ar : hit.en
}
