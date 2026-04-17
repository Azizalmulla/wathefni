"""
WhatsApp Cloud API client.
Handles sending messages, media, and processing webhooks.

For testing: we use OpenClaw + personal WhatsApp number.
For production: swap to Meta WhatsApp Cloud API.
"""
import httpx

from app.config import get_settings

settings = get_settings()

CLOUD_API_URL = "https://graph.facebook.com/v21.0"


async def send_text_message(to: str, message: str) -> dict:
    """
    Send a text message via WhatsApp Cloud API.
    
    For testing with OpenClaw, messages are sent through OpenClaw's gateway instead.
    This function is the production-ready Cloud API implementation.
    """
    if not settings.whatsapp_token:
        # Testing mode — log instead of sending
        print(f"[WhatsApp] Would send to {to}: {message[:100]}...")
        return {"status": "test_mode", "to": to}

    url = f"{CLOUD_API_URL}/{settings.whatsapp_phone_number_id}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.whatsapp_token}",
                "Content-Type": "application/json",
            },
        )
        return response.json()


async def send_image(to: str, image_url: str, caption: str = "") -> dict:
    """Send an image via WhatsApp Cloud API."""
    if not settings.whatsapp_token:
        print(f"[WhatsApp] Would send image to {to}: {image_url}")
        return {"status": "test_mode", "to": to}

    url = f"{CLOUD_API_URL}/{settings.whatsapp_phone_number_id}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "image",
        "image": {"link": image_url, "caption": caption},
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.whatsapp_token}",
                "Content-Type": "application/json",
            },
        )
        return response.json()


async def send_document(to: str, document_url: str, filename: str, caption: str = "") -> dict:
    """Send a document (PDF, CSV, etc.) via WhatsApp Cloud API."""
    if not settings.whatsapp_token:
        print(f"[WhatsApp] Would send document to {to}: {filename}")
        return {"status": "test_mode", "to": to}

    url = f"{CLOUD_API_URL}/{settings.whatsapp_phone_number_id}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "document",
        "document": {
            "link": document_url,
            "filename": filename,
            "caption": caption,
        },
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.whatsapp_token}",
                "Content-Type": "application/json",
            },
        )
        return response.json()


async def download_media(media_id: str) -> bytes:
    """Download media (CV, image) from WhatsApp Cloud API."""
    if not settings.whatsapp_token:
        return b""

    # First, get the media URL
    url = f"{CLOUD_API_URL}/{media_id}"
    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
        )
        media_url = response.json().get("url")

        if not media_url:
            return b""

        # Then download the actual file
        file_response = await client.get(
            media_url,
            headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
        )
        return file_response.content


def parse_webhook_message(body: dict) -> dict | None:
    """
    Parse an incoming WhatsApp Cloud API webhook payload.
    Returns a simplified message dict or None if not a user message.
    """
    try:
        entry = body["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        if "messages" not in value:
            return None

        message = value["messages"][0]
        contact = value["contacts"][0]

        return {
            "from": message["from"],
            "name": contact["profile"]["name"],
            "message_id": message["id"],
            "timestamp": message["timestamp"],
            "type": message["type"],
            "text": message.get("text", {}).get("body", ""),
            "document": message.get("document"),
            "image": message.get("image"),
        }
    except (KeyError, IndexError):
        return None
