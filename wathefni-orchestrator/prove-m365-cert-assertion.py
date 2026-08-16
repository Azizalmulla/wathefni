#!/usr/bin/env python3
"""Controlled Microsoft certificate-assertion proof (no client secret, never log private key).

Usage (after public cert is uploaded to Entra and App ID / Tenant ID are known):

  export WATHEFNI_M365_CLIENT_ID=...
  export WATHEFNI_M365_TENANT_ID=...
  export WATHEFNI_M365_CERT_BUNDLE_PATH=/secure/path/wathefni-m365.bundle.pem
  .venv/bin/python prove-m365-cert-assertion.py

Without CLIENT_ID/TENANT_ID this script only proves local assertion shape (x5t/x5t#S256).
"""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _decode_jwt_part(part: str) -> dict:
    pad = "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(part + pad))


def main() -> int:
    import platform_connection_c6 as c6

    client_id = (os.environ.get("WATHEFNI_M365_CLIENT_ID") or "").strip()
    tenant_id = (os.environ.get("WATHEFNI_M365_TENANT_ID") or "").strip()
    bundle_path = (os.environ.get("WATHEFNI_M365_CERT_BUNDLE_PATH") or "").strip()

    results: dict = {"proofs": {}}

    def record(name: str, ok: bool, **details):
        # Never include PEM/private key material in details.
        safe = {k: v for k, v in details.items() if "pem" not in k.lower() and "private" not in k.lower() and "key" not in k.lower()}
        results["proofs"][name] = {"ok": ok, **safe}
        print(("PASS" if ok else "FAIL"), name, json.dumps(safe)[:240])

    # --- Local generation + assertion shape proof ---
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from datetime import datetime, timedelta, timezone

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Wathefni Platform Integration")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=730))
        .sign(key, hashes.SHA256())
    )
    public_pem = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    bundle = public_pem + private_pem

    meta = c6.microsoft_certificate_metadata(bundle)
    assertion = c6._microsoft_cert_assertion(
        tenant_id=tenant_id or "00000000-0000-0000-0000-000000000001",
        client_id=client_id or "00000000-0000-0000-0000-000000000002",
        certificate_pem=bundle,
    )
    header = _decode_jwt_part(assertion.split(".", 1)[0])
    payload = _decode_jwt_part(assertion.split(".")[1])
    record(
        "assertion_has_x5t",
        header.get("x5t") == meta["x5t"] and bool(header.get("x5t")),
        x5t=header.get("x5t"),
        thumbprint_sha1_hex=meta["thumbprint_sha1_hex"],
    )
    record(
        "assertion_has_x5t_s256",
        header.get("x5t#S256") == meta["x5t#S256"],
        x5t_s256=header.get("x5t#S256"),
    )
    record("assertion_alg_rs256", header.get("alg") == "RS256", alg=header.get("alg"))
    record("assertion_has_iat", "iat" in payload)
    try:
        c6._microsoft_cert_assertion(
            tenant_id="00000000-0000-0000-0000-000000000001",
            client_id="00000000-0000-0000-0000-000000000002",
            certificate_pem=private_pem,
        )
        record("rejects_private_key_only", False, error="unexpectedly_accepted")
    except Exception as exc:
        record("rejects_private_key_only", getattr(exc, "code", "") == "certificate_public_missing", error=getattr(exc, "code", type(exc).__name__))

    # Optional: write public cert only to a temp path for Entra upload instructions (no private key).
    evid = Path(os.environ.get("C6B_EVID") or tempfile.mkdtemp(prefix="m365-cert-proof-"))
    evid.mkdir(parents=True, exist_ok=True)
    public_path = evid / "wathefni-m365-public.cer.pem"
    public_path.write_text(public_pem)
    os.chmod(public_path, 0o644)
    record("public_cert_export_only", public_path.exists(), path=str(public_path), subject=meta.get("subject"))

    # --- Live Entra token mint (requires uploaded public cert + App ID + Tenant ID; no client secret) ---
    if client_id and tenant_id and bundle_path:
        path = Path(bundle_path)
        if not path.exists():
            record("live_token_mint", False, error="bundle_path_missing")
        else:
            live_bundle = path.read_text()
            # Never print live_bundle.
            live_meta = c6.microsoft_certificate_metadata(live_bundle)
            try:
                token = c6.mint_microsoft_app_token(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    certificate_pem=live_bundle,
                )
                record(
                    "live_token_mint",
                    bool(token) and len(token) > 20,
                    token_len=len(token or ""),
                    thumbprint_sha1_hex=live_meta.get("thumbprint_sha1_hex"),
                    note="access_token acquired via certificate client_assertion; no client secret used",
                )
            except Exception as exc:
                record(
                    "live_token_mint",
                    False,
                    error=getattr(exc, "code", type(exc).__name__),
                    message=str(getattr(exc, "message", exc))[:200],
                    thumbprint_sha1_hex=live_meta.get("thumbprint_sha1_hex"),
                )
    else:
        record(
            "live_token_mint",
            False,
            blocked_reason="set WATHEFNI_M365_CLIENT_ID, WATHEFNI_M365_TENANT_ID, WATHEFNI_M365_CERT_BUNDLE_PATH after uploading public cert to Entra",
        )

    # Wipe sensitive locals
    del private_pem, bundle, key, cert, assertion
    if "live_bundle" in locals():
        del live_bundle

    out = evid / "m365-cert-assertion-proof.json"
    out.write_text(json.dumps(results, indent=2))
    print("EVID", evid)
    print("SUMMARY", json.dumps({k: v.get("ok") for k, v in results["proofs"].items()}))
    # Local shape proofs must pass; live mint may remain blocked until Entra upload.
    shape_ok = all(
        results["proofs"][n]["ok"]
        for n in (
            "assertion_has_x5t",
            "assertion_has_x5t_s256",
            "assertion_alg_rs256",
            "assertion_has_iat",
            "rejects_private_key_only",
            "public_cert_export_only",
        )
    )
    return 0 if shape_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
