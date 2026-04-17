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

    # File storage
    upload_dir: str = "./uploads"

    # App
    secret_key: str = "change-this-to-a-random-string"
    debug: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
