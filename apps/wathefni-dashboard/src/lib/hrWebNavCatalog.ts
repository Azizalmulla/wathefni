/**
 * HR Web nav catalog — presentation only.
 *
 * Destination offerability stays in resolveWorkspaceAuthority (backend modules +
 * permissions). This file supplies icons/labels for every capability nav page so
 * App.tsx cannot silently omit a Surface Registry destination.
 */

import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  BadgeDollarSign,
  BarChart3,
  Bell,
  BriefcaseBusiness,
  CalendarCheck,
  CalendarClock,
  CalendarRange,
  ClipboardCheck,
  ClipboardList,
  Clock,
  GraduationCap,
  HeartHandshake,
  Inbox,
  Layers,
  LayoutDashboard,
  Medal,
  MessageCircle,
  Network,
  Scale,
  Settings,
  ShieldCheck,
  Smile,
  Sparkles,
  Target,
  Timer,
  UserCheck,
  UserPlus,
  Users,
  Wallet,
  Waypoints,
} from 'lucide-react'

import { WORKSPACE_SURFACES, type NavGroup } from '@/lib/workspaceCapability'
import { HR_WEB_PAGE_IDS } from '@/lib/hrWebSurfaceRegistry'
import type { Page } from '@/types'

export type DashboardNavItem = {
  id: Page
  label: string
  icon: LucideIcon
  module?: string
  group: NavGroup
}

const PAGE_ICONS: Record<string, LucideIcon> = {
  overview: LayoutDashboard,
  ai: MessageCircle,
  jobs: BriefcaseBusiness,
  requisitions: ClipboardList,
  candidates: Users,
  interviews: CalendarCheck,
  calendar: CalendarRange,
  assessments: ClipboardCheck,
  ranking: Medal,
  reports: BarChart3,
  employees: Users,
  workforce: Network,
  inbox: Inbox,
  preboarding: UserPlus,
  onboarding: UserCheck,
  probation: Timer,
  attendance: CalendarCheck,
  leave: CalendarClock,
  performance: Target,
  talent: Sparkles,
  learning: GraduationCap,
  benefits: HeartHandshake,
  'employee-relations': Scale,
  engagement: Smile,
  'compensation-planning': BadgeDollarSign,
  'workforce-planning': Waypoints,
  'job-architecture': Layers,
  shifts: Clock,
  payroll: Wallet,
  analytics: BarChart3,
  compliance: ShieldCheck,
  notifications: Bell,
  activity: Activity,
  settings: Settings,
}

export const DASHBOARD_NAV_CATALOG: DashboardNavItem[] = WORKSPACE_SURFACES.filter(
  (surface) => surface.kind === 'nav' && surface.page,
).map((surface) => {
  const id = String(surface.page)
  const icon = PAGE_ICONS[id]
  if (!icon) throw new Error(`Missing nav icon for page ${id}`)
  return {
    id: id as Page,
    label: surface.label,
    icon,
    module: surface.module || undefined,
    group: surface.group || 'settings',
  }
})

const REGISTERED_PAGES = new Set<string>(HR_WEB_PAGE_IDS)

export function isRegisteredDashboardPage(page: string | null | undefined): page is Page {
  return Boolean(page && REGISTERED_PAGES.has(page))
}

export function navCatalogById(): Record<string, DashboardNavItem> {
  return Object.fromEntries(DASHBOARD_NAV_CATALOG.map((item) => [item.id, item]))
}
