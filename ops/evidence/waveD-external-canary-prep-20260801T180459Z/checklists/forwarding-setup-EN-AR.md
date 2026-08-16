# Forwarding setup checklist — EN / AR

Primary address (fill after create): `<PRIMARY_ADDRESS>@inbound.wathefni.ai`  
Optional job alias: `<JOB_ALIAS>@inbound.wathefni.ai` → open role `<POSITION_CODE>`

---

## English

**Summary:** Forward CVs from your company recruitment email to the Wathefni intake address. Wathefni receives a copy via secure inbound mail, scans attachments, and holds candidates until HR reviews identity and admits them to a role. Wathefni does **not** open or sync your Microsoft/Google mailbox in this canary — forwarding is the only intake path.

### Steps
1. Create or choose the recruitment mailbox your company already uses (for example `careers@yourcompany.com`).
2. Add a forward (or inbox rule) so every message with a CV attachment is copied to `<PRIMARY_ADDRESS>@inbound.wathefni.ai`.
3. **Microsoft 365 / Outlook:** Settings → Mail → Forwarding, or create a rule “if has attachment → redirect/forward to Wathefni”.
4. **Gmail:** Settings → Forwarding and POP/IMAP → Add a forwarding address, then confirm; optionally filter “Has attachment” to that address.
5. Send one test CV from an **external** address and confirm Wathefni shows a recent received time on Settings → Email & document intake.
6. Optional: create a job-specific Wathefni alias for a single open role. Without a role alias, CVs are held as **needs role** until HR assigns one.
7. Wathefni does not open or sync your Microsoft/Google inbox in this phase — forwarding is the only intake path.

### Do / Don’t
- **Do** forward only recruitment/CV traffic.
- **Do** keep HR review explicit (Held → assign/admit).
- **Don’t** enable Gmail/M365 connector sync (not part of this canary).
- **Don’t** auto-admit without review during canary week 1.

---

## العربية

**الملخص:** حوّل السير الذاتية من بريد التوظيف في شركتك إلى عنوان استقبال وظفني. يستلم وظفني نسخة عبر بريد وارد آمن، يفحص المرفقات، ويُبقي المرشحين معلّقين حتى تراجع الموارد البشرية الهوية وتضيفهم إلى وظيفة. وظفني **لا** يفتح ولا يزامن صندوق بريد مايكروسوفت/جوجل في هذه التجربة — التحويل هو مسار الاستقبال الوحيد.

### الخطوات
1. أنشئ أو اختر صندوق بريد التوظيف الذي تستخدمه الشركة بالفعل (مثل `careers@yourcompany.com`).
2. أضف تحويلاً (أو قاعدة وارد) بحيث تُنسخ كل رسالة تحتوي مرفق سيرة ذاتية إلى `<PRIMARY_ADDRESS>@inbound.wathefni.ai`.
3. **Microsoft 365 / Outlook:** الإعدادات ← البريد ← التحويل، أو أنشئ قاعدة «إذا وُجد مرفق ← إعادة توجيه إلى وظفني».
4. **Gmail:** الإعدادات ← التحويل وPOP/IMAP ← أضف عنوان تحويل ثم أكّده؛ ويمكنك تصفية «يحتوي مرفقاً» إلى ذلك العنوان.
5. أرسل سيرة ذاتية تجريبية من عنوان **خارجي** وتأكد أن وظفني يعرض وقت استلام حديث في الإعدادات ← البريد والمستندات.
6. اختياري: أنشئ اسماً مستعاراً خاصاً بوظيفة مفتوحة. بدون تعيين وظيفة تُحفظ السير كـ **تحتاج دوراً** حتى يعيّنها الموارد البشرية.
7. وظفني لا يفتح ولا يزامن صندوق بريد مايكروسوفت/جوجل في هذه المرحلة — التحويل هو مسار الاستقبال الوحيد.

### افعل / لا تفعل
- **افعل** تحويل بريد التوظيف/السير فقط.
- **افعل** الإبقاء على مراجعة صريحة (معلّق ← تعيين/قبول).
- **لا** تفعّل مزامنة موصل Gmail/M365 (ليست ضمن هذه التجربة).
- **لا** تقبل تلقائياً دون مراجعة في الأسبوع الأول.
