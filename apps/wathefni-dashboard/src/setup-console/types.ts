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
