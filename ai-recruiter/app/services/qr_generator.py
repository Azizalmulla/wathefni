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

# Replace with your actual AI Recruiter WhatsApp number
WHATSAPP_NUMBER = "96599338566"


def generate_qr_code(company_code: str, position_code: str, phone_number: str = None) -> str:
    """
    Generate a QR code image that opens WhatsApp with a pre-filled APPLY message.
    
    Returns the file path of the saved QR code image.
    """
    number = phone_number or WHATSAPP_NUMBER
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
    number = phone_number or WHATSAPP_NUMBER
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
