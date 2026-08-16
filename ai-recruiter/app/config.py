from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://recruiter:recruiter@localhost:5432/ai_recruiter"

    # Anthropic
    anthropic_api_key: str = ""

    # WhatsApp Cloud API (production)
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = "ai-recruiter-verify-token"
    # Candidate APPLY destination — same authority as Wathefni orchestrator.
    # Prefer WATHEFNI_APPLY_WHATSAPP_NUMBER; fall back to WATHEFNI_WHATSAPP_NUMBER.
    # No silent hardcoded product default.
    wathefni_apply_whatsapp_number: str = ""
    wathefni_whatsapp_number: str = ""
    wathefni_hr_orchestrator_url: str = "http://127.0.0.1:8010/orchestrator/whatsapp-turn"
    wathefni_internal_token: str = ""

    # File storage
    upload_dir: str = "./uploads"

    # Google Sheets dashboard sync, powered by gog CLI
    google_sheet_id: str = ""
    google_account: str = ""
    gog_bin: str = "gog"
    employees_sheet_name: str = "Employees"
    compliance_sheet_name: str = "Compliance"

    # App
    secret_key: str = "change-this-to-a-random-string"
    debug: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Allow WATHEFNI_APPLY_WHATSAPP_NUMBER style env names
        env_nested_delimiter = "__"

    def apply_whatsapp_number(self) -> str:
        number = "".join(ch for ch in str(self.wathefni_apply_whatsapp_number or "").strip() if ch.isdigit())
        if not number:
            number = "".join(ch for ch in str(self.wathefni_whatsapp_number or "").strip() if ch.isdigit())
        if not number:
            raise ValueError(
                "WATHEFNI_APPLY_WHATSAPP_NUMBER is not configured for this environment."
            )
        return number


@lru_cache()
def get_settings() -> Settings:
    return Settings()
