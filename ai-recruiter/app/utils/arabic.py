"""
Arabic text utilities for Kuwait-specific processing.
"""


def is_arabic(text: str) -> bool:
    """Check if text contains mostly Arabic characters."""
    if not text:
        return False
    arabic_chars = sum(1 for c in text if "\u0600" <= c <= "\u06FF")
    return arabic_chars > len(text) * 0.3


def normalize_phone(phone: str) -> str:
    """
    Normalize a Kuwait phone number to international format.
    Handles: 99338566, +96599338566, 96599338566, 009659933856
    """
    phone = phone.strip().replace(" ", "").replace("-", "")

    # Remove leading + or 00
    if phone.startswith("+"):
        phone = phone[1:]
    elif phone.startswith("00"):
        phone = phone[2:]

    # Add country code if missing
    if len(phone) == 8:
        phone = "965" + phone

    return "+" + phone
