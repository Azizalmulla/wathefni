"""R2 — fail-closed signing secrets for public capability links.

Public assessment and async video-interview links are bearer capabilities: whoever
holds a validly signed link reaches candidate-facing state. Before R2 the signing
key silently fell back to a constant committed to this repository, and then to
`WATHEFNI_DATABASE_URL`. Either fallback makes every link forgeable.

R2 contract:

* Dedicated environment variable per purpose. No inheritance from dashboard
  tokens, database URLs, or any other credential.
* Known-bad values are rejected by name, including the two constants that were
  previously committed, so tokens minted under the old fallback cannot verify.
* Minimum length and character diversity are enforced.
* Missing or unusable secret means the capability is unavailable (fail closed),
  never "sign with something else".
* A minimal rotation contract: `<VAR>_PREVIOUS` may hold retired secrets that
  still verify but never sign. Retired secrets face the same validation.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("wathefni.security.link_secrets")

CONTRACT_VERSION = "r2-link-secrets-v1"

MIN_SECRET_LENGTH = 32
MIN_DISTINCT_CHARS = 12

# Values that must never be accepted as signing key material, in any variable.
# The first two were the committed fallbacks removed in R2.
BANNED_SECRETS = frozenset(
    {
        "wathefni-assessment-dev-secret",
        "wathefni-video-interview-dev-secret",
        "changeme",
        "secret",
        "dev-secret",
        "test-secret",
    }
)

# Credentials that used to be borrowed as signing keys. If a deployment points a
# link-secret variable at one of these, treat it as misconfiguration.
_BORROWED_CREDENTIAL_VARS = (
    "WATHEFNI_DATABASE_URL",
    "DATABASE_URL",
    "WATHEFNI_DASHBOARD_TOKEN",
    "AI_OCTOPUS_DASHBOARD_TOKEN",
    "DASHBOARD_TOKEN",
    "WATHEFNI_INTERNAL_TOKEN",
)

_DB_URL_PREFIXES = ("postgres://", "postgresql://", "mysql://", "redis://", "amqp://")


class LinkSecretUnavailable(RuntimeError):
    """Raised when a purpose has no usable dedicated signing secret."""

    def __init__(self, purpose: str, reason: str) -> None:
        super().__init__(f"{purpose}:{reason}")
        self.purpose = purpose
        self.reason = reason


@dataclass(frozen=True)
class LinkSecretPurpose:
    purpose: str
    env_var: str
    description: str

    @property
    def previous_env_var(self) -> str:
        return f"{self.env_var}_PREVIOUS"


PURPOSES: dict[str, LinkSecretPurpose] = {
    "assessment": LinkSecretPurpose(
        purpose="assessment",
        env_var="WATHEFNI_ASSESSMENT_LINK_SECRET",
        description="Public candidate assessment capability links.",
    ),
    "video_interview": LinkSecretPurpose(
        purpose="video_interview",
        env_var="WATHEFNI_VIDEO_INTERVIEW_LINK_SECRET",
        description="Public async video interview capability links.",
    ),
}


def _borrowed_credentials() -> set[str]:
    values: set[str] = set()
    for name in _BORROWED_CREDENTIAL_VARS:
        raw = str(os.environ.get(name) or "").strip()
        if raw:
            values.add(raw)
    return values


def validate_secret(candidate: str | None, *, purpose: str) -> tuple[bool, str]:
    """Returns (ok, reason). Reason is a stable machine code, never the secret."""
    raw = str(candidate or "").strip()
    if not raw:
        return False, "missing"
    if raw.lower() in BANNED_SECRETS:
        return False, "banned_known_value"
    if any(raw.lower().startswith(prefix) for prefix in _DB_URL_PREFIXES):
        return False, "looks_like_connection_string"
    if raw in _borrowed_credentials():
        return False, "reuses_other_credential"
    if len(raw) < MIN_SECRET_LENGTH:
        return False, "too_short"
    if len(set(raw)) < MIN_DISTINCT_CHARS:
        return False, "insufficient_entropy"
    return True, "ok"


def _purpose(purpose: str) -> LinkSecretPurpose:
    spec = PURPOSES.get(purpose)
    if spec is None:
        raise KeyError(f"unknown_link_secret_purpose:{purpose}")
    return spec


def signing_secret(purpose: str) -> bytes:
    """Active secret used to MINT links. Fails closed."""
    spec = _purpose(purpose)
    raw = os.environ.get(spec.env_var)
    ok, reason = validate_secret(raw, purpose=purpose)
    if not ok:
        logger.error("link signing secret unusable purpose=%s var=%s reason=%s", purpose, spec.env_var, reason)
        raise LinkSecretUnavailable(purpose, reason)
    return str(raw).strip().encode("utf-8")


def verification_secrets(purpose: str) -> list[bytes]:
    """Active secret first, then any valid retired secrets (rotation window)."""
    spec = _purpose(purpose)
    secrets_out: list[bytes] = [signing_secret(purpose)]
    retired_raw = str(os.environ.get(spec.previous_env_var) or "").strip()
    for candidate in [part.strip() for part in retired_raw.split(",") if part.strip()]:
        ok, reason = validate_secret(candidate, purpose=purpose)
        if not ok:
            logger.warning(
                "retired link secret ignored purpose=%s var=%s reason=%s",
                purpose,
                spec.previous_env_var,
                reason,
            )
            continue
        secrets_out.append(candidate.encode("utf-8"))
    return secrets_out


def available(purpose: str) -> bool:
    try:
        signing_secret(purpose)
        return True
    except LinkSecretUnavailable:
        return False


def secret_fingerprint(purpose: str) -> str | None:
    """Non-reversible identifier so operators can confirm which key is live."""
    try:
        secret = signing_secret(purpose)
    except LinkSecretUnavailable:
        return None
    return hashlib.sha256(secret).hexdigest()[:12]


def status() -> dict[str, Any]:
    """Readiness view. Never returns secret material."""
    out: dict[str, Any] = {"contract_version": CONTRACT_VERSION, "purposes": {}}
    healthy = True
    for name, spec in PURPOSES.items():
        ok, reason = validate_secret(os.environ.get(spec.env_var), purpose=name)
        retired = [
            part.strip()
            for part in str(os.environ.get(spec.previous_env_var) or "").split(",")
            if part.strip()
        ]
        out["purposes"][name] = {
            "env_var": spec.env_var,
            "configured": ok,
            "reason": reason,
            "fingerprint": secret_fingerprint(name),
            "retired_keys_accepted": sum(1 for r in retired if validate_secret(r, purpose=name)[0]),
        }
        healthy = healthy and ok
    out["ok"] = healthy
    return out


def compare(expected: bytes, provided: bytes) -> bool:
    """Constant-time comparison helper so call sites cannot regress to `==`."""
    return hmac.compare_digest(expected, provided)


def compare_text(expected: str | None, provided: str | None) -> bool:
    return hmac.compare_digest(str(expected or "").encode("utf-8"), str(provided or "").encode("utf-8"))
