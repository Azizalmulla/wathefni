"""
File storage service.
Handles CV uploads and file management.
For v1: local filesystem storage.
For production: swap to S3-compatible storage.
"""
import os
import uuid

from app.config import get_settings

settings = get_settings()


def save_file(file_bytes: bytes, original_filename: str, subfolder: str = "cvs") -> str:
    """
    Save uploaded file to local storage.
    Returns the file path.
    """
    os.makedirs(os.path.join(settings.upload_dir, subfolder), exist_ok=True)

    # Generate unique filename to avoid collisions
    ext = os.path.splitext(original_filename)[1] if original_filename else ".pdf"
    unique_name = f"{uuid.uuid4()}{ext}"
    filepath = os.path.join(settings.upload_dir, subfolder, unique_name)

    with open(filepath, "wb") as f:
        f.write(file_bytes)

    return filepath


def get_file(filepath: str) -> bytes:
    """Read a file from storage."""
    with open(filepath, "rb") as f:
        return f.read()


def delete_file(filepath: str) -> bool:
    """Delete a file from storage."""
    try:
        os.remove(filepath)
        return True
    except FileNotFoundError:
        return False
