import type { ReactNode } from 'react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

import { EmployeeAppAccessPolicyCard } from './EmployeeAppAccessPolicyCard'
import { ModuleCompanyPoliciesCard } from './ModuleCompanyPoliciesCard'
import { NotificationDeliveryPoliciesCard } from './NotificationDeliveryPoliciesCard'
import { PayrollSetupCard } from './PayrollSetupCard'
import { findModule, isPolicySurfaceReady } from './policySurfaces'
import { SetupEffectiveStateBanner } from './SetupEffectiveStateBanner'
import type { AvailableModule, SetupCredentials } from './types'
import { Wave1HireReadyPoliciesCard } from './Wave1HireReadyPoliciesCard'
import { Wave2WorkforceTruthPoliciesCard } from './Wave2WorkforceTruthPoliciesCard'
import { Wave3EmployeeLifecyclePoliciesCard } from './Wave3EmployeeLifecyclePoliciesCard'
import { Wave4PerformancePoliciesCard, Wave4TalentPoliciesCard } from './Wave4PerformanceTalentPoliciesCard'
import { Wave5HrIntelligencePoliciesCard } from './Wave5HrIntelligencePoliciesCard'
import { Wave6BenefitsPoliciesCard } from './Wave6BenefitsPoliciesCard'
import { Wave6CompensationPlanningPoliciesCard } from './Wave6CompensationPlanningPoliciesCard'
import { Wave6EmployeeRelationsPoliciesCard } from './Wave6EmployeeRelationsPoliciesCard'
import { Wave6EngagementPoliciesCard } from './Wave6EngagementPoliciesCard'
import { Wave6JobArchitecturePoliciesCard } from './Wave6JobArchitecturePoliciesCard'
import { Wave6LearningPoliciesCard } from './Wave6LearningPoliciesCard'
import { Wave6WorkforcePlanningPoliciesCard } from './Wave6WorkforcePlanningPoliciesCard'

function UnavailablePolicy({
  titleEn,
  titleAr,
  module,
  locale,
}: {
  titleEn: string
  titleAr: string
  module?: AvailableModule
  locale: 'en' | 'ar'
}) {
  const isAr = locale === 'ar'
  return (
    <Card data-policy-unavailable={module?.key || titleEn} data-ownership="enterprise_policy_unavailable">
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle>{isAr ? titleAr : titleEn}</CardTitle>
          <Badge variant="outline">{isAr ? 'غير متاح' : 'Unavailable'}</Badge>
        </div>
        <CardDescription>
          {isAr
            ? 'سياسات الموجة ٤–٦ تظهر هنا فقط عندما تكون الوحدة مخوّلة ومنشورة في هذا النشر.'
            : 'Wave 4–6 policies appear here only when the module is entitled and deployed in this environment.'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {module ? (
          <SetupEffectiveStateBanner state={module.effective_state} locale={locale} />
        ) : (
          <p className="text-sm text-subtle">
            {isAr ? 'هذه الوحدة ليست في كتالوج الشركة الحالي.' : 'This module is not in the current company catalog.'}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function EnterprisePolicy({
  moduleKey,
  titleEn,
  titleAr,
  modules,
  locale,
  children,
}: {
  moduleKey: string
  titleEn: string
  titleAr: string
  modules: AvailableModule[]
  locale: 'en' | 'ar'
  children: ReactNode
}) {
  const module = findModule(modules, moduleKey)
  if (!isPolicySurfaceReady(module)) {
    return <UnavailablePolicy titleEn={titleEn} titleAr={titleAr} module={module} locale={locale} />
  }
  return <>{children}</>
}

export function PoliciesWorkflowsPage({
  credentials,
  companyCode,
  locale = 'en',
  modules,
  onChanged,
  onError,
}: {
  credentials: SetupCredentials
  companyCode: string
  locale?: 'en' | 'ar'
  modules: AvailableModule[]
  onChanged: () => Promise<void>
  onError: (error: unknown) => void
}) {
  const isAr = locale === 'ar'
  return (
    <div className="space-y-6" data-testid="policies-workflows" dir={isAr ? 'rtl' : 'ltr'} lang={locale}>
      <div>
        <h2 className="text-2xl font-semibold tracking-[-0.035em]">
          {isAr ? 'السياسات ومسارات العمل' : 'Policies & Workflows'}
        </h2>
        <p className="mt-1 text-sm text-subtle">
          {isAr
            ? 'سياسات التشغيل الأساسية متاحة دائماً. بطاقات الموجة ٤–٦ تظهر فقط عند التخويل والنشر الفعلي.'
            : 'Core operating policies stay available. Wave 4–6 editors open only when the company is entitled and the runtime is actually deployed.'}
        </p>
      </div>

      <EmployeeAppAccessPolicyCard
        credentials={credentials}
        companyCode={companyCode}
        locale={locale}
        moduleEnabled={Boolean(
          findModule(modules, 'employee_app')?.configured || findModule(modules, 'employee_app')?.effective,
        )}
        onChanged={onChanged}
        onError={onError}
      />

      <PayrollSetupCard
        credentials={credentials}
        companyCode={companyCode}
        locale={locale}
        moduleEnabled={Boolean(findModule(modules, 'payroll')?.configured || findModule(modules, 'payroll')?.effective)}
        onChanged={onChanged}
        onError={onError}
      />

      <ModuleCompanyPoliciesCard
        credentials={credentials}
        companyCode={companyCode}
        locale={locale}
        availableModules={modules}
        onChanged={onChanged}
        onError={onError}
      />

      <Wave1HireReadyPoliciesCard credentials={credentials} companyCode={companyCode} locale={locale} onError={onError} />
      <Wave2WorkforceTruthPoliciesCard credentials={credentials} companyCode={companyCode} locale={locale} onError={onError} />
      <Wave3EmployeeLifecyclePoliciesCard credentials={credentials} companyCode={companyCode} locale={locale} onError={onError} />

      <EnterprisePolicy
        moduleKey="performance"
        titleEn="Performance policies"
        titleAr="سياسات الأداء"
        modules={modules}
        locale={locale}
      >
        <Wave4PerformancePoliciesCard credentials={credentials} companyCode={companyCode} locale={locale} onError={onError} />
      </EnterprisePolicy>

      <EnterprisePolicy moduleKey="talent" titleEn="Talent policies" titleAr="سياسات المواهب" modules={modules} locale={locale}>
        <Wave4TalentPoliciesCard credentials={credentials} companyCode={companyCode} locale={locale} onError={onError} />
      </EnterprisePolicy>

      <EnterprisePolicy
        moduleKey="analytics"
        titleEn="HR Intelligence policies"
        titleAr="سياسات ذكاء الموارد البشرية"
        modules={modules}
        locale={locale}
      >
        <Wave5HrIntelligencePoliciesCard credentials={credentials} companyCode={companyCode} locale={locale} onError={onError} />
      </EnterprisePolicy>

      <Wave6JobArchitecturePoliciesCard credentials={credentials} companyCode={companyCode} locale={locale} onError={onError} />

      <EnterprisePolicy
        moduleKey="learning"
        titleEn="Learning policies"
        titleAr="سياسات التعلم"
        modules={modules}
        locale={locale}
      >
        <Wave6LearningPoliciesCard credentials={credentials} companyCode={companyCode} locale={locale} onError={onError} />
      </EnterprisePolicy>

      <EnterprisePolicy
        moduleKey="benefits"
        titleEn="Benefits policies"
        titleAr="سياسات المزايا"
        modules={modules}
        locale={locale}
      >
        <Wave6BenefitsPoliciesCard credentials={credentials} companyCode={companyCode} locale={locale} onError={onError} />
      </EnterprisePolicy>

      <EnterprisePolicy
        moduleKey="employee_relations"
        titleEn="Employee Relations policies"
        titleAr="سياسات علاقات الموظفين"
        modules={modules}
        locale={locale}
      >
        <Wave6EmployeeRelationsPoliciesCard credentials={credentials} companyCode={companyCode} locale={locale} onError={onError} />
      </EnterprisePolicy>

      <EnterprisePolicy
        moduleKey="engagement"
        titleEn="Engagement policies"
        titleAr="سياسات المشاركة"
        modules={modules}
        locale={locale}
      >
        <Wave6EngagementPoliciesCard credentials={credentials} companyCode={companyCode} locale={locale} onError={onError} />
      </EnterprisePolicy>

      <EnterprisePolicy
        moduleKey="comp_planning"
        titleEn="Compensation Planning policies"
        titleAr="سياسات تخطيط التعويضات"
        modules={modules}
        locale={locale}
      >
        <Wave6CompensationPlanningPoliciesCard credentials={credentials} companyCode={companyCode} locale={locale} onError={onError} />
      </EnterprisePolicy>

      <EnterprisePolicy
        moduleKey="workforce_planning"
        titleEn="Workforce Planning policies"
        titleAr="سياسات تخطيط القوى العاملة"
        modules={modules}
        locale={locale}
      >
        <Wave6WorkforcePlanningPoliciesCard credentials={credentials} companyCode={companyCode} locale={locale} onError={onError} />
      </EnterprisePolicy>

      <NotificationDeliveryPoliciesCard
        credentials={credentials}
        companyCode={companyCode}
        locale={locale}
        onError={onError}
      />
    </div>
  )
}
