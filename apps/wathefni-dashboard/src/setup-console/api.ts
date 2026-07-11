import type {
  ChannelAccountInput,
  CompanyCreateInput,
  CompanyDetailResponse,
  CompanyListResponse,
  CompanyProfileInput,
  CompanySummary,
  OwnerInput,
  OwnerResponse,
  SetupCredentials,
} from './types'

const SETUP_ROOT = '/dashboard/superadmin/setup'

export class SetupConsoleApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'SetupConsoleApiError'
    this.status = status
  }
}

async function request<T>(path: string, credentials: SetupCredentials, init: RequestInit = {}): Promise<T> {
  const token = credentials.token.trim()
  const phone = credentials.phone.trim()
  if (!token || !phone) {
    throw new SetupConsoleApiError(401, 'Operator token and authorised phone are required.')
  }

  const headers = new Headers(init.headers)
  headers.set('Authorization', `Bearer ${token}`)
  headers.set('X-HR-Phone', phone)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')

  const response = await fetch(path, { ...init, headers })
  const payload: unknown = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail =
      payload && typeof payload === 'object' && 'detail' in payload
        ? (payload as { detail: unknown }).detail
        : payload
    const message =
      typeof detail === 'string'
        ? detail
        : detail && typeof detail === 'object' && 'message' in detail
          ? String((detail as { message: unknown }).message)
          : 'The setup request could not be completed.'
    throw new SetupConsoleApiError(response.status, message)
  }
  return payload as T
}

export async function listCompanies(
  credentials: SetupCredentials,
  options: { q: string; limit: number; offset: number },
): Promise<CompanyListResponse> {
  const search = new URLSearchParams({
    q: options.q,
    limit: String(options.limit),
    offset: String(options.offset),
  })
  const payload = await request<
    CompanyListResponse | CompanySummary[] | { items?: CompanySummary[]; total?: number; total_count?: number }
  >(`${SETUP_ROOT}/companies?${search.toString()}`, credentials)

  if (Array.isArray(payload)) {
    return { companies: payload, total: payload.length, limit: options.limit, offset: options.offset }
  }
  const result = payload as Partial<CompanyListResponse> & { items?: CompanySummary[]; total_count?: number }
  const companies = Array.isArray(result.companies)
    ? result.companies
    : Array.isArray(result.items)
      ? result.items
      : []
  return {
    companies,
    total:
      typeof result.total_count === 'number'
        ? result.total_count
        : typeof result.total === 'number'
          ? result.total
          : companies.length,
    limit: typeof result.limit === 'number' ? result.limit : options.limit,
    offset: typeof result.offset === 'number' ? result.offset : options.offset,
  }
}

export function getCompany(credentials: SetupCredentials, companyCode: string) {
  return request<CompanyDetailResponse>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}`,
    credentials,
  )
}

export function createCompany(credentials: SetupCredentials, input: CompanyCreateInput) {
  return request<{ created?: boolean; readiness?: unknown }>(`${SETUP_ROOT}/companies`, credentials, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateCompanyProfile(
  credentials: SetupCredentials,
  companyCode: string,
  input: CompanyProfileInput,
) {
  return request<unknown>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/profile`,
    credentials,
    { method: 'PATCH', body: JSON.stringify(input) },
  )
}

export function updateCompanyModules(
  credentials: SetupCredentials,
  companyCode: string,
  modules: string[],
) {
  return request<unknown>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/modules`,
    credentials,
    { method: 'PATCH', body: JSON.stringify({ modules }) },
  )
}

export function updateCompanySettings(
  credentials: SetupCredentials,
  companyCode: string,
  settings: Record<string, unknown>,
) {
  return request<unknown>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/settings`,
    credentials,
    { method: 'PATCH', body: JSON.stringify(settings) },
  )
}

export function createOwner(credentials: SetupCredentials, companyCode: string, input: OwnerInput) {
  return request<OwnerResponse>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/owner`,
    credentials,
    { method: 'POST', body: JSON.stringify(input) },
  )
}

export function linkHrWhatsApp(credentials: SetupCredentials, companyCode: string, phone: string) {
  return request<unknown>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/whatsapp-link`,
    credentials,
    { method: 'POST', body: JSON.stringify({ phone }) },
  )
}

export function saveChannelAccount(
  credentials: SetupCredentials,
  companyCode: string,
  input: ChannelAccountInput,
) {
  return request<unknown>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/channel-account`,
    credentials,
    { method: 'PUT', body: JSON.stringify(input) },
  )
}

export function deleteChannelAccount(credentials: SetupCredentials, companyCode: string) {
  return request<unknown>(
    `${SETUP_ROOT}/companies/${encodeURIComponent(companyCode)}/channel-account`,
    credentials,
    { method: 'DELETE' },
  )
}
