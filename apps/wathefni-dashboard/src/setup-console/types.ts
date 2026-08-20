export type SetupCredentials = {
  token: string
  phone: string
}

export type CompanyLifecycleStatus = 'active' | 'disabled' | 'archived'

export type CompanyLifecycle = {
  status?: CompanyLifecycleStatus | string | null
  reason?: string | null
  disabled_at?: string | null
  archived_at?: string | null
}

export type CompanySummary = {
  company_code: string
  name?: string | null
  country?: string | null
  timezone?: string | null
  currency?: string | null
  ready?: boolean
  status?: CompanyLifecycleStatus | string | null
  lifecycle?: CompanyLifecycle
}

export type CompanyListResponse = {
  companies: CompanySummary[]
  total: number
  total_count?: number
  limit: number
  offset: number
}

export type ReadinessStep = {
  key: string
  label?: string
  done: boolean
  detail?: string | null
}

export type SetupReadiness = {
  company_code: string
  name: string
  country: string
  timezone: string
  currency: string
  modules: string[]
  steps: ReadinessStep[]
  ready: boolean
  status?: CompanyLifecycleStatus | string | null
  lifecycle?: CompanyLifecycle
  [key: string]: unknown
}

import type { SetupEffectiveState } from './SetupEffectiveStateBanner'

export type AvailableModule = {
  key: string
  label: string
  suite: string
  audience?: string | null
  configured: boolean
  platform_available: boolean
  effective: boolean
  depends_on?: string[]
  recommended_with?: string[]
  recommendation_copy?: string
  app_surface_key?: string | null
  app_surface_label?: string | null
  depends_on_labels?: string[]
  recommended_with_labels?: string[]
  can_enable?: boolean
  can_select?: boolean
  usable?: boolean
  stored_enabled?: boolean
  customer_facing_state?: string
  effective_state?: SetupEffectiveState
  required_permission?: string | null
}

export type ModuleBundle = {
  id: string
  label: string
  description: string
  modules: string[]
}

export type ModuleAppSurface = {
  module_key: string
  surface_key: string
  label: string | null
  available_when_app_live?: boolean
}

export type ModuleGuidance = {
  bundles?: ModuleBundle[]
  app_surfaces?: ModuleAppSurface[]
  missing_dependencies?: Array<{ module: string; requires: string; message: string }>
  expanded_modules?: string[]
}

export type SetupUser = {
  id?: string | number
  user_id?: string | number
  name?: string | null
  email?: string | null
  phone?: string | null
  role?: string | null
  status?: string | null
}

export type ChannelPolicySection = Record<string, unknown>

export type ChannelPolicy = {
  pre_hiring?: ChannelPolicySection
  post_hiring?: ChannelPolicySection
  hr_admin?: ChannelPolicySection
  [key: string]: unknown
}

export type ChannelAccount = {
  provider?: string | null
  provider_account_id?: string | null
  sender_phone?: string | null
  audiences?: string[]
  status?: string | null
  verified?: boolean
  platform_available?: boolean
}

export type CompanyDetailResponse = {
  readiness: SetupReadiness
  available_modules: AvailableModule[]
  module_bundles?: ModuleBundle[]
  module_guidance?: ModuleGuidance
  users: SetupUser[]
  channel_policy: ChannelPolicy
  channel_account: ChannelAccount | null
}

export type CompanyCreateInput = {
  company_code: string
  name: string
  country: string
  timezone: string
  currency: string
}

export type CompanyProfileInput = {
  name: string
  country: string
  timezone: string
  currency: string
}

export type OwnerInput = {
  name: string
  email: string
  phone: string
}

export type OwnerResponse = {
  invite_link?: string
  invite_url?: string
  invite_token?: string
  user?: SetupUser
  readiness?: SetupReadiness
}

export type CompanyLifecycleInput = {
  status: CompanyLifecycleStatus
  reason: string
}

export type CompanyLifecycleResponse = {
  ok?: boolean
  company_code?: string
  previous_status?: CompanyLifecycleStatus | string | null
  status?: CompanyLifecycleStatus | string | null
  revoked_sessions?: number
  superseded_invites?: number
  readiness?: SetupReadiness
}

export type ChannelAccountInput = {
  provider: string
  provider_account_id: string
  sender_phone: string
  audiences: string[]
  status?: 'pending_verification' | 'active' | 'disabled'
  verification_reference?: string
}

export type LaunchHonestState =
  | 'not_purchased'
  | 'setup_required'
  | 'blocked'
  | 'ready_for_canary'
  | 'live_controlled'
  | 'paused'

export type LaunchReadinessItem = {
  key: string
  title_en: string
  title_ar: string
  state: LaunchHonestState | string
  purchased: boolean
  configured: boolean
  blocked: boolean
  live: boolean
  summary_en: string
  summary_ar: string
  next_action_en?: string | null
  next_action_ar?: string | null
  deep_link?: string | null
}

export type LaunchReadinessStage = {
  stage: { key: string; label_en: string; label_ar: string }
  items: LaunchReadinessItem[]
}

export type LaunchReadinessResponse = {
  ok: boolean
  wave_a_version?: string
  company_code: string
  company_name?: string | null
  overall_state: LaunchHonestState | string
  overall_label_en?: string
  overall_label_ar?: string
  stages: LaunchReadinessStage[]
  important_blockers: Array<{
    key: string
    title_en: string
    title_ar: string
    summary_en: string
    summary_ar: string
    next_action_en?: string | null
    next_action_ar?: string | null
    deep_link?: string | null
    state: string
  }>
  pause_impact?: {
    title_en: string
    title_ar: string
    bullets_en: string[]
    bullets_ar: string[]
  }
  entitlements_cannot_bypass_gates?: boolean
  honesty?: Record<string, unknown>
}
