import type { RecruitingLocale } from '@/lib/recruitingLifecycle'

const AUTH_COPY = {
  en: {
    authSignIn: 'Sign in',
    authSignInTitle: 'Sign in to OctoHR',
    authAcceptInvite: 'Accept your invite',
    authSignInDescription: 'Enter your work email, password, and company code.',
    authInviteDescription: 'Create your workspace password to join this company.',
    authBrandBlurb: 'Human resources for your company workspace.',
    authWorkEmail: 'Work email',
    authPassword: 'Password',
    authCompanyCode: 'Company code',
    authName: 'Name',
    authPhoneOptional: 'Phone (optional)',
    authYourName: 'Your name',
    authCreatePassword: 'Create a password',
    authPhonePlaceholder: 'Phone number',
    authPasswordPlaceholder: 'Password',
    authAcceptInviteAction: 'Accept invite',
    authCheckingSession: 'Checking your session',
    authSessionExpired: 'Your session expired. Please sign in again.',
    authIncorrectCredentials: 'Incorrect email or password. Please try again.',
    authCompanyRequired: 'Enter your company code to open this workspace.',
    authInviteNamePassword: 'Enter your name and a password with at least 8 characters.',
    authCouldNotSignIn: 'Could not sign in.',
    authCouldNotAcceptInvite: 'Could not accept invite.',
    authInviteAccepted: 'Invite accepted. You’re signed in.',
    authSignedIn: 'You’re signed in.',
    authAccessNotAllowed: 'Access not allowed for this company',
    authAccessNotAllowedBody: 'This account is not registered for the selected company. Check the company code, then sign in again.',
    authRoleCannotOpen: 'Your role cannot open this workspace',
    authRoleCannotOpenBody: 'Your role does not include access to this workspace. Ask a company Owner or HR Manager to update your role.',
    authAccountInactive: 'Your account is not active',
    authAccountInactiveBody: 'Your account is not active. Ask a company Owner or HR Manager to restore access.',
  },
  ar: {
    authSignIn: 'تسجيل الدخول',
    authSignInTitle: 'تسجيل الدخول إلى OctoHR',
    authAcceptInvite: 'قبول الدعوة',
    authSignInDescription: 'أدخل بريد العمل وكلمة المرور ورمز الشركة.',
    authInviteDescription: 'أنشئ كلمة مرور لمساحة العمل للانضمام إلى هذه الشركة.',
    authBrandBlurb: 'الموارد البشرية لمساحة عمل شركتك.',
    authWorkEmail: 'البريد الإلكتروني للعمل',
    authPassword: 'كلمة المرور',
    authCompanyCode: 'رمز الشركة',
    authName: 'الاسم',
    authPhoneOptional: 'الهاتف (اختياري)',
    authYourName: 'اسمك',
    authCreatePassword: 'أنشئ كلمة مرور',
    authPhonePlaceholder: 'رقم الهاتف',
    authPasswordPlaceholder: 'كلمة المرور',
    authAcceptInviteAction: 'قبول الدعوة',
    authCheckingSession: 'جارٍ التحقق من الجلسة',
    authSessionExpired: 'انتهت صلاحية جلستك. يرجى تسجيل الدخول مرة أخرى.',
    authIncorrectCredentials: 'البريد الإلكتروني أو كلمة المرور غير صحيحة. حاول مرة أخرى.',
    authCompanyRequired: 'أدخل رمز الشركة لفتح مساحة العمل هذه.',
    authInviteNamePassword: 'أدخل اسمك وكلمة مرور من 8 أحرف على الأقل.',
    authCouldNotSignIn: 'تعذر تسجيل الدخول.',
    authCouldNotAcceptInvite: 'تعذر قبول الدعوة.',
    authInviteAccepted: 'تم قبول الدعوة. أنت داخل مساحة العمل.',
    authSignedIn: 'تم تسجيل الدخول.',
    authAccessNotAllowed: 'غير مسموح بالوصول لهذه الشركة',
    authAccessNotAllowedBody: 'هذا الحساب غير مسجّل في الشركة المحددة. تحقق من رمز الشركة ثم سجّل الدخول مرة أخرى.',
    authRoleCannotOpen: 'لا يشمل دورك صلاحية فتح مساحة العمل',
    authRoleCannotOpenBody: 'لا يشمل دورك صلاحية الوصول إلى مساحة العمل هذه. اطلب من مالك الشركة أو مدير الموارد البشرية تحديث الدور.',
    authAccountInactive: 'حسابك غير نشط',
    authAccountInactiveBody: 'حسابك غير نشط. اطلب من مالك الشركة أو مدير الموارد البشرية استعادة الوصول.',
  },
} as const

export type AuthCopyKey = keyof (typeof AUTH_COPY)['en']

export function authCopy(locale: RecruitingLocale, key: AuthCopyKey): string {
  return AUTH_COPY[locale][key] || AUTH_COPY.en[key]
}

export function isDefaultAuthPrompt(text: string): boolean {
  return (
    text === AUTH_COPY.en.authSignInDescription
    || text === AUTH_COPY.ar.authSignInDescription
    || text === AUTH_COPY.en.authInviteDescription
    || text === AUTH_COPY.ar.authInviteDescription
  )
}
