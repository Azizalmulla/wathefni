(() => {
  const form = document.getElementById('deletion-request-form');
  const status = document.getElementById('form-status');
  if (!form || !status) return;

  const button = form.querySelector('button[type="submit"]');
  const setStatus = (message, kind) => {
    status.textContent = message;
    status.dataset.kind = kind || '';
  };

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;

    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    setStatus('Sending your request… / جارٍ إرسال طلبك…', 'pending');

    try {
      const response = await fetch('https://api.octo-hr.com/public/account-deletion/request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company_code: form.elements.company_code.value.trim(),
          identity: form.elements.identity.value.trim(),
          reason: form.elements.reason.value.trim() || null,
          confirmed: form.elements.confirmed.checked,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload?.detail?.message || 'request_failed');

      form.reset();
      setStatus(
        'Request received. If the details match an OctoHR employee account, it has been sent to your employer’s HR team. / تم استلام الطلب. إذا تطابقت البيانات مع حساب موظف في OctoHR، فقد تم إرساله إلى فريق الموارد البشرية في شركتك.',
        'success',
      );
    } catch (error) {
      setStatus(
        'We could not submit the request right now. Please try again or email privacy@octo-hr.com. / تعذر إرسال الطلب الآن. يرجى المحاولة مرة أخرى أو مراسلة privacy@octo-hr.com.',
        'error',
      );
    } finally {
      button.disabled = false;
      button.removeAttribute('aria-busy');
    }
  });
})();
