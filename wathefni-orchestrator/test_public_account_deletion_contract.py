import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PUBLIC_ROOT = ROOT.parent / "apps" / "octohr-public"
CADDYFILE = ROOT.parent / "ops" / "caddy" / "api.wathefni.ai.Caddyfile"


class PublicAccountDeletionContract(unittest.TestCase):
    def test_public_page_is_a_real_bilingual_request_form(self) -> None:
        page = (PUBLIC_ROOT / "delete-account.html").read_text(encoding="utf-8")
        client = (PUBLIC_ROOT / "delete-account.js").read_text(encoding="utf-8")
        self.assertIn('id="deletion-request-form"', page)
        self.assertIn('name="company_code"', page)
        self.assertIn('name="identity"', page)
        self.assertIn('name="confirmed"', page)
        self.assertIn('lang="ar" dir="rtl"', page)
        self.assertIn("365 days after employment ends", page)
        self.assertIn("https://api.octo-hr.com/public/account-deletion/request", client)
        self.assertIn("method: 'POST'", client)

    def test_public_page_discloses_controller_and_retention_exceptions(self) -> None:
        page = (PUBLIC_ROOT / "delete-account.html").read_text(encoding="utf-8")
        for disclosure in (
            "Your employer is the data controller",
            "payroll and payslip records",
            "security/audit evidence",
            "legal hold",
            "irreversibly anonymized",
        ):
            self.assertIn(disclosure, page)

    def test_public_form_network_access_is_narrowly_scoped(self) -> None:
        config = (PUBLIC_ROOT / "vercel.json").read_text(encoding="utf-8")
        self.assertIn("connect-src 'self' https://api.octo-hr.com", config)
        self.assertNotIn("connect-src *", config)

    def test_production_proxy_exposes_only_the_exact_public_adapter(self) -> None:
        caddy = CADDYFILE.read_text(encoding="utf-8")
        self.assertIn("handle /public/account-deletion/request {", caddy)
        self.assertNotIn("handle /public/*", caddy)


if __name__ == "__main__":
    result = unittest.main(exit=False)
    if result.result.wasSuccessful():
        print("PUBLIC_ACCOUNT_DELETION_CONTRACT_PASS")
