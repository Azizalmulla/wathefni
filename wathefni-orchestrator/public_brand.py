"""Public OctoHR support surface on the existing technical app-link host."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter()


_SUPPORT_HTML = """<!doctype html>
<html lang="en" dir="ltr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="description" content="OctoHR app support and contact information." />
  <title>OctoHR Support</title>
  <style>
    :root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif; }
    body { margin: 0; background: #f8f2e8; color: #1c1b19; }
    main { max-width: 760px; margin: 0 auto; padding: 56px 24px 72px; }
    .brand { font-size: 18px; font-weight: 800; letter-spacing: -.02em; }
    h1 { margin: 42px 0 14px; font-size: clamp(36px, 7vw, 62px); line-height: 1; letter-spacing: -.055em; }
    p { font-size: 17px; line-height: 1.65; }
    section { margin-top: 32px; padding: 24px; border: 2px solid #1c1b19; border-radius: 24px; background: #fff; }
    h2 { margin: 0 0 10px; font-size: 21px; }
    .muted { color: #625f59; font-size: 14px; }
    [lang="ar"] { direction: rtl; text-align: right; }
  </style>
</head>
<body>
<main>
  <div class="brand">OctoHR</div>
  <h1>Support</h1>
  <p>For employment records, company access, HR decisions, or help using the OctoHR app, contact your employer's HR team. They can escalate platform issues to OctoHR Support.</p>
  <section>
    <h2>App support</h2>
    <p>Tell us which device you use, what you were trying to do, and the error shown. Do not email activation codes, passwords, PINs, Civil IDs, bank details, or other sensitive documents.</p>
    <p class="muted">Your HR team can include the device type, the action attempted, and the exact error when escalating a platform issue.</p>
  </section>
  <section lang="ar">
    <h2>دعم التطبيق</h2>
    <p>للسجلات الوظيفية أو صلاحيات الشركة أو قرارات الموارد البشرية أو المساعدة في استخدام تطبيق OctoHR، تواصل مع فريق الموارد البشرية لدى جهة عملك. ويمكن للفريق تصعيد مشكلات المنصة إلى دعم OctoHR.</p>
    <p>اذكر نوع جهازك وما الذي كنت تحاول تنفيذه ورسالة الخطأ الظاهرة. لا ترسل رموز التفعيل أو كلمات المرور أو الرقم السري أو البطاقة المدنية أو البيانات البنكية أو مستندات حساسة عبر البريد.</p>
  </section>
</main>
</body>
</html>"""


@router.get("/support", response_class=HTMLResponse)
@router.get("/employee-app/support", response_class=HTMLResponse)
def public_support() -> HTMLResponse:
    return HTMLResponse(_SUPPORT_HTML, headers={"Cache-Control": "public, max-age=300"})
