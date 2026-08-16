"""
QR code generator for job positions.
Generates QR codes that open WhatsApp with a pre-filled APPLY message.
"""
import io
import os

import qrcode
from PIL import Image

from app.config import get_settings

settings = get_settings()


def _apply_whatsapp_number(phone_number: str | None = None) -> str:
    """Env-owned APPLY destination; fail closed when unconfigured."""
    if phone_number:
        number = "".join(ch for ch in str(phone_number).strip() if ch.isdigit())
        if number:
            return number
    # Prefer process env so runtime systemd/env updates win over cached settings.
    number = "".join(ch for ch in str(os.environ.get("WATHEFNI_APPLY_WHATSAPP_NUMBER") or "").strip() if ch.isdigit())
    if not number:
        number = "".join(ch for ch in str(os.environ.get("WATHEFNI_WHATSAPP_NUMBER") or "").strip() if ch.isdigit())
    if not number:
        try:
            number = settings.apply_whatsapp_number()
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
    if not number:
        raise ValueError("WATHEFNI_APPLY_WHATSAPP_NUMBER is not configured for this environment.")
    return number


def generate_qr_code(company_code: str, position_code: str, phone_number: str = None) -> str:
    """
    Generate a QR code image that opens WhatsApp with a pre-filled APPLY message.
    
    Returns the file path of the saved QR code image.
    """
    number = _apply_whatsapp_number(phone_number)
    apply_code = f"APPLY-{company_code}-{position_code}"
    wa_url = f"https://wa.me/{number}?text={apply_code}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(wa_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # Save to uploads directory
    os.makedirs(os.path.join(settings.upload_dir, "qr"), exist_ok=True)
    filename = f"{company_code}_{position_code}.png"
    filepath = os.path.join(settings.upload_dir, "qr", filename)

    img.save(filepath)
    return filepath


def get_qr_bytes(company_code: str, position_code: str, phone_number: str = None) -> bytes:
    """Generate QR code and return as bytes (for sending via WhatsApp)."""
    number = _apply_whatsapp_number(phone_number)
    apply_code = f"APPLY-{company_code}-{position_code}"
    wa_url = f"https://wa.me/{number}?text={apply_code}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(wa_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()
