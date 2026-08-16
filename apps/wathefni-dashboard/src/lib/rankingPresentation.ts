import type { RankingCandidate, RankingDecision, RankingPresentation } from '@/types'
import { rankingAssessmentEvidenceEnabled } from '@/lib/rankingQueueContract'

const CV_COMPONENT_LABELS: Array<{ key: string; labelEn: string; labelAr: string; max: number; group: 'cv' | 'assessment' }> = [
  { key: 'skills_alignment', labelEn: 'Skills match', labelAr: 'توافق المهارات', max: 30, group: 'cv' },
  { key: 'experience_alignment', labelEn: 'Relevant experience', labelAr: 'الخبرة ذات الصلة', max: 25, group: 'cv' },
  { key: 'education_cert_alignment', labelEn: 'Education', labelAr: 'التعليم والشهادات', max: 15, group: 'cv' },
  { key: 'semantic_alignment', labelEn: 'CV relevance', labelAr: 'أدلة السيرة الذاتية', max: 15, group: 'cv' },
  { key: 'assessment_evidence', labelEn: 'Assessment evidence', labelAr: 'أدلة التقييم', max: 15, group: 'assessment' },
]

function asTextList(values: unknown, limit = 5): string[] {
  if (!Array.isArray(values)) return []
  const out: string[] = []
  for (const item of values) {
    if (typeof item === 'string' || typeof item === 'number') {
      const text = String(item).trim()
      if (!text || looksTechnical(text)) continue
      out.push(text)
    } else if (item && typeof item === 'object') {
      const label = String((item as { label?: string }).label || '').trim()
      const value = String((item as { value?: string }).value || '').trim()
      const text = label && value ? `${label}: ${value}` : label || value
      if (!text || looksTechnical(text)) continue
      out.push(text)
    }
    if (out.length >= limit) break
  }
  return out
}

function looksTechnical(text: string) {
  return /ck_ranking|undefinedfunction|eligibility=|coverage=|run_id|item_id|[{}\[\]]|cv_education|semantic_content_hash/i.test(
    text,
  )
}

export function rankingDecisionFor(candidate: RankingCandidate): RankingDecision {
  if (candidate.ranking_decision) return candidate.ranking_decision
  const presentation = candidate.presentation
  const score = presentation?.score
  const showNumeric = Boolean(score?.show_numeric && score.value != null && Number.isFinite(Number(score.value)))
  return {
    ranking_status: presentation?.card_mode || candidate.eligibility_bucket || 'unavailable',
    eligibility: {
      bucket: candidate.eligibility_bucket || presentation?.state?.code,
      label: presentation?.state?.label,
      fit_label: presentation?.fit?.label,
    },
    advisory_score: showNumeric ? Number(score?.value) : null,
    score_state: {
      show_numeric: showNumeric,
      label: score?.label || (showNumeric ? undefined : 'Score unavailable'),
      reason: score?.reason,
    },
    fit_summary: presentation?.verdict || presentation?.explanation || candidate.gpt_evaluation?.fit_summary || null,
    strengths: asTextList(presentation?.strengths || candidate.gpt_evaluation?.strengths, 3),
    gaps: asTextList(presentation?.gaps || candidate.gpt_evaluation?.gaps, 4),
    missing_evidence: asTextList(presentation?.missing || candidate.gpt_evaluation?.gaps, 4),
    component_scores: candidate.component_scores || candidate.score_breakdown || {},
    recommended_next_action:
      presentation?.recommended_next_step || candidate.gpt_evaluation?.recommended_next_step || undefined,
    evidence_references: asTextList(presentation?.evidence_highlights || candidate.evidence, 5),
    application_stage: candidate.status,
    job: { position_code: candidate.position_code, position_title: candidate.position_title },
    candidate_name: presentation?.candidate_name || candidate.name,
  }
}

export function rankingScoreLabel(decision: RankingDecision, locale: 'en' | 'ar' = 'en') {
  if (decision.score_state?.show_numeric && decision.advisory_score != null) {
    const value = Math.round(Number(decision.advisory_score))
    return `${value} / 100`
  }
  return decision.score_state?.label || (locale === 'ar' ? 'الدرجة غير متاحة' : 'Score unavailable')
}

export function rankingComponentRows(
  decision: RankingDecision,
  locale: 'en' | 'ar' = 'en',
  opts?: { assessmentEnabled?: boolean },
) {
  const components = decision.component_scores || {}
  const assessmentOn = Boolean(opts?.assessmentEnabled)
  return CV_COMPONENT_LABELS.flatMap((item) => {
    if (item.group === 'assessment' && !assessmentOn) return []
    if (!(item.key in components)) return []
    const raw = components[item.key]
    if (raw == null || raw === undefined) return []
    const value = Number(raw)
    if (!Number.isFinite(value)) return []
    return [
      {
        key: item.key,
        label: locale === 'ar' ? item.labelAr : item.labelEn,
        value,
        max: item.max,
        group: item.group,
      },
    ]
  })
}

export { rankingAssessmentEvidenceEnabled }

export function rankingPresentationSummary(presentation?: RankingPresentation | null) {
  if (!presentation) return ''
  return String(presentation.verdict || presentation.explanation || '').trim()
}
