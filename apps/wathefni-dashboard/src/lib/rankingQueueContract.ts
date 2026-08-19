/** Client mirror of ranking.pool.* display contract (no predicate changes). */

import type { RecruitingLocale } from '@/lib/recruitingLifecycle'

export type RankingPoolCounts = {
  matching_count?: number
  total_matching?: number
  rankable_count?: number
  total_rankable?: number
  eligible_count?: number
  not_met_count?: number
  unknown_count?: number
  restricted_held_count?: number
  not_applicable_count?: number
}

/** Mirrors ranking.pool.rankable membership for client display tests. */
export function isRankable(item: {
  eligibility_bucket?: string
  required_evidence_complete?: boolean
}) {
  const bucket = String(item.eligibility_bucket || '')
  if (!['eligible', 'not_applicable'].includes(bucket)) return false
  if (item.required_evidence_complete === false) return false
  return true
}

/** ranking.run.top_n — slice only from rankable; never fill with unrankable. */
export function topNRankable<T extends { eligibility_bucket?: string; required_evidence_complete?: boolean }>(
  items: T[],
  topN: number,
) {
  return items.filter(isRankable).slice(0, Math.max(0, topN))
}

export function rankingMatchingCount(counts?: RankingPoolCounts | null): number {
  return Number(counts?.matching_count ?? counts?.total_matching ?? 0)
}

export function rankingRankableCount(counts?: RankingPoolCounts | null, shownFallback = 0): number {
  return Number(counts?.rankable_count ?? counts?.total_rankable ?? shownFallback ?? 0)
}

export function rankingEligibleCount(counts?: RankingPoolCounts | null): number {
  return Number(counts?.eligible_count ?? 0)
}

/** Excluded from leaderboard but retained for explanation (not cards). */
export function rankingExcludedCount(counts?: RankingPoolCounts | null): number {
  const matching = rankingMatchingCount(counts)
  const rankable = rankingRankableCount(counts)
  if (matching > rankable) return matching - rankable
  const explicit =
    Number(counts?.not_met_count || 0) +
    Number(counts?.unknown_count || 0) +
    Number(counts?.restricted_held_count || 0)
  return Math.max(0, explicit)
}

export function rankingCopy(locale: RecruitingLocale | undefined, key: RankingCopyKey): string {
  return (locale === 'ar' ? AR : EN)[key]
}

export type RankingCopyKey =
  | 'title'
  | 'subtitle'
  | 'select_job'
  | 'run'
  | 'rerun'
  | 'in_review_order'
  | 'job_matches'
  | 'meets_all_requirements'
  | 'eligible_helper'
  | 'excluded_note'
  | 'state_no_job'
  | 'state_no_run'
  | 'state_running'
  | 'state_stale'
  | 'state_failed'
  | 'state_failed_previous'
  | 'state_none_rankable'
  | 'state_empty_ranked'
  | 'open_profile'
  | 'fit_summary'
  | 'advisory_score'
  | 'ranking_status'
  | 'strengths'
  | 'gaps'
  | 'next_step'
  | 'show_evidence'
  | 'cv_evidence'
  | 'assessment_evidence'
  | 'score_components'
  | 'not_captured'
  | 'fit_profile'
  | 'fit_profile_detail'
  | 'eligible_bucket'
  | 'not_applicable_bucket'
  | 'requirement_not_met_bucket'
  | 'insufficient_information_bucket'

const EN: Record<RankingCopyKey, string> = {
  title: 'Candidate ranking',
  subtitle: 'Select a job to see who HR should review first, with evidence and recommended next steps.',
  select_job: 'Select a job',
  run: 'Run ranking',
  rerun: 'Re-rank',
  in_review_order: 'In review order',
  job_matches: 'Job matches',
  meets_all_requirements: 'Meets all requirements',
  eligible_helper:
    'In review order includes candidates with complete evidence who are eligible or where hard requirements do not apply. Meets all requirements counts only hard-criteria eligible — so it can be 0 while people still appear in review order.',
  excluded_note:
    '{excluded} matching application(s) are not in review order (incomplete evidence, requirements not met, or held by policy). They are not ranked.',
  state_no_job: 'Select a job first.',
  state_no_run: 'No ranking result yet. Press Run ranking.',
  state_running: 'Ranking in progress…',
  state_stale: 'This result may be out of date. Re-rank to refresh.',
  state_failed: 'Ranking could not be loaded. Try Run ranking again.',
  state_failed_previous:
    'Fresh ranking could not be loaded. Results below are previous, not a new ranking.',
  state_none_rankable:
    'There are matching applications, but none are ready for review order yet (missing evidence or not rankable).',
  state_empty_ranked: 'No ranked candidates in the current result.',
  open_profile: 'Open profile',
  fit_summary: 'Fit summary',
  advisory_score: 'Advisory score',
  ranking_status: 'Ranking status',
  strengths: 'Top strengths',
  gaps: 'Key gaps / missing information',
  next_step: 'Recommended next step',
  show_evidence: 'Show evidence and score components',
  cv_evidence: 'CV evidence',
  assessment_evidence: 'Assessment evidence (job-approved)',
  score_components: 'Score components',
  not_captured: 'Not captured yet.',
  fit_profile: 'Fit profile',
  fit_profile_detail: 'Ranking uses this hiring lens together with available candidate evidence.',
  eligible_bucket: 'Meets all requirements',
  not_applicable_bucket: 'Hard requirements do not apply',
  requirement_not_met_bucket: 'Requirements not met',
  insufficient_information_bucket: 'Insufficient information',
}

const AR: Record<RankingCopyKey, string> = {
  title: 'ترتيب المرشحين',
  subtitle: 'اختر وظيفة لعرض من يجب مراجعته أولاً، مع الأدلة والخطوة التالية.',
  select_job: 'اختر وظيفة',
  run: 'تشغيل الترتيب',
  rerun: 'إعادة الترتيب',
  in_review_order: 'بترتيب المراجعة',
  job_matches: 'مطابق للوظيفة',
  meets_all_requirements: 'يستوفي كل المتطلبات',
  eligible_helper:
    'بترتيب المراجعة يشمل المرشحين بأدلة مكتملة ممن يستوفون الشروط أو لا تنطبق عليهم الشروط الصارمة. يستوفي كل المتطلبات يحسب المستوفين للشروط الصارمة فقط — لذلك قد يكون 0 بينما ما زال هناك مرشحون في ترتيب المراجعة.',
  excluded_note:
    '{excluded} طلب(ات) مطابقة ليست ضمن ترتيب المراجعة (أدلة ناقصة أو متطلبات غير مستوفاة أو مقيّدة بالسياسة). لا تُرتَّب.',
  state_no_job: 'اختر وظيفة أولاً.',
  state_no_run: 'لا توجد نتيجة ترتيب بعد. اضغط تشغيل الترتيب.',
  state_running: 'جاري الترتيب…',
  state_stale: 'قد تكون هذه النتيجة قديمة. أعد الترتيب للتحديث.',
  state_failed: 'تعذّر تحميل الترتيب. حاول تشغيل الترتيب مرة أخرى.',
  state_failed_previous: 'تعذّر تحميل ترتيب محدّث. النتائج أدناه سابقة وليست ترتيباً جديداً.',
  state_none_rankable: 'توجد طلبات مطابقة، لكن لا أحد جاهزاً لترتيب المراجعة بعد (أدلة ناقصة أو غير قابل للترتيب).',
  state_empty_ranked: 'لا يوجد مرشحون في نتيجة الترتيب الحالية.',
  open_profile: 'فتح الملف',
  fit_summary: 'ملخص التوافق',
  advisory_score: 'درجة استشارية',
  ranking_status: 'حالة الترتيب',
  strengths: 'أبرز نقاط القوة',
  gaps: 'الفجوات أو المعلومات الناقصة',
  next_step: 'الخطوة التالية المقترحة',
  show_evidence: 'عرض الأدلة ومكوّنات الدرجة',
  cv_evidence: 'أدلة السيرة الذاتية',
  assessment_evidence: 'أدلة التقييم (معتمدة للوظيفة)',
  score_components: 'مكوّنات الدرجة',
  not_captured: 'غير مسجّل بعد.',
  fit_profile: 'ملف التوافق',
  fit_profile_detail: 'يستخدم الترتيب ملف الوظيفة مع الأدلة المتاحة للمرشح.',
  eligible_bucket: 'يستوفي كل المتطلبات',
  not_applicable_bucket: 'لا تنطبق الشروط الصارمة',
  requirement_not_met_bucket: 'المتطلبات غير مستوفاة',
  insufficient_information_bucket: 'معلومات غير كافية',
}

export function rankingEligibilityLabel(
  locale: RecruitingLocale | undefined,
  bucket?: string | null,
  presentationLabel?: string | null,
): string {
  const key = String(bucket || '').trim().toLowerCase()
  if (key === 'eligible') return rankingCopy(locale, 'eligible_bucket')
  if (key === 'not_applicable') return rankingCopy(locale, 'not_applicable_bucket')
  if (key === 'requirement_not_met') return rankingCopy(locale, 'requirement_not_met_bucket')
  if (key === 'insufficient_information') return rankingCopy(locale, 'insufficient_information_bucket')
  const label = String(presentationLabel || '').trim()
  if (label) return label
  if (!key) return '—'
  return key
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (ch) => ch.toUpperCase())
}

/** Assessment may appear only when job policy explicitly enables it. */
export function rankingAssessmentEvidenceEnabled(policy?: {
  sources?: { assessment?: string }
} | null): boolean {
  const mode = String(policy?.sources?.assessment || 'unused').toLowerCase()
  return mode === 'required' || mode === 'optional'
}
