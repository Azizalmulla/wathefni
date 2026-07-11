export type SetupCredentials = {
  token: string
  phone: string
}

export type CompanySummary = {
  company_code: string
  name?: string | null
  country?: string | null
  timezone?: string | null
  currency?: string | null
  ready?: boolean
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
  [key: string]: unknown
}

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

export type ChannelAccountInput = {
  provider: string
  provider_account_id: string
  sender_phone: string
  audiences: string[]
  status?: 'pending_verification' | 'active' | 'disabled'
  verification_reference?: string
}
