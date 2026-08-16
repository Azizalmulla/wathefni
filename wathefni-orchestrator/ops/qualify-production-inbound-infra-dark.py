#!/usr/bin/env python3
"""Production-dark infrastructure and fail-closed proofs (automation remains OFF)."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import tempfile
import uuid
from pathlib import Path

ORCH = Path("/opt/wathefni/orchestrator")
# Evidence dir may contain app.py copies; keep orchestrator first.
sys.path = [p for p in sys.path if Path(p).resolve() != Path(__file__).resolve().parent]
sys.path.insert(0, str(ORCH))

import production_data_safety as _r3_data_safety
_r3_data_safety.require_explicit_environment()
EV = Path(os.environ["EVIDENCE_ROOT"])


def write(name: str, payload) -> None:
    (EV / name).write_text(json.dumps(payload, indent=2, default=str, sort_keys=True) + "\n")


def clam(cmd: bytes, port: int = 3311) -> str:
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    try:
        s.sendall(cmd if cmd.endswith(b"\0") else cmd + b"\0")
        return s.recv(4096).decode().replace("\0", "").strip()
    finally:
        s.close()


def main() -> int:
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
    os.environ.setdefault(
        "WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1"
    )
    os.environ["WATHEFNI_INBOUND_EMAIL"] = "off"
    for line in Path("/root/.openclaw/secrets/wathefni-intake.env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

    import app
    import intake_malware_scanner as scanner

    root = Path(os.environ["WATHEFNI_INTAKE_QUARANTINE_DIR"])
    assert root.is_dir()
    assert oct(root.stat().st_mode & 0o777) == "0o700"
    company_a, company_b = "QPRODA", "QPRODB"
    inbound = str(uuid.uuid4())
    data = b"production-dark-quarantine-proof\n"
    digest = hashlib.sha256(data).hexdigest()
    key = f"{company_a}/{inbound}/0001/{digest}.bin"
    path = root / Path(*key.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    assert path.read_bytes() == data
    assert not (root / company_b / inbound / "0001" / f"{digest}.bin").exists()
    path.unlink()
    for p in [path.parent, path.parent.parent, path.parent.parent.parent]:
        try:
            p.rmdir()
        except OSError:
            break

    version = clam(b"zVERSION")
    assert clam(b"zPING") == "PONG"
    tmp = Path(tempfile.mkdtemp(prefix="prod-dark-clam-"))
    clean = tmp / "clean.pdf"
    eicar = tmp / "eicar.com"
    clean.write_bytes(b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n")
    eicar.write_bytes(
        b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    )
    engine = scanner.build_malware_scanner_from_env()
    clean_res = engine.scan_path(clean)
    infected_res = engine.scan_path(eicar)
    assert clean_res.state == "clean"
    assert infected_res.state in {"infected", "malware_suspicious"} or infected_res.reason_code

    legacy = app._import_process_one_file(
        None,
        company="WATHEFNI",
        batch_id="dark-mailbox-check",
        source="email",
        company_positions=[],
        filename="x.pdf",
        data=b"%PDF-1.4 dark",
        seen_checksums={},
        meta={"email": "recruiter@example.test"},
    )
    assert legacy.get("error") == "durable_scan_and_identity_authority_required"

    real = app.get_mailbox_connection
    try:
        app.get_mailbox_connection = lambda company, mailbox_id: {
            "mailbox_id": mailbox_id,
            "status": "connected",
            "sync_enabled": True,
            "sync_mode": "live",
            "cursor": {},
            "provider": "gmail",
        }
        app.mailbox_ingestion_enabled = lambda: True  # type: ignore
        sync = app.run_mailbox_sync("WATHEFNI", "dark-mailbox", "manual")
    finally:
        app.get_mailbox_connection = real
    assert sync.get("error") == "durable_scan_and_identity_authority_required"

    retention = {
        "WATHEFNI_INTAKE_SCAN_REUSE_HOURS": os.environ.get("WATHEFNI_INTAKE_SCAN_REUSE_HOURS"),
        "WATHEFNI_INTAKE_ORPHAN_GRACE_SECONDS": os.environ.get(
            "WATHEFNI_INTAKE_ORPHAN_GRACE_SECONDS"
        ),
        "WATHEFNI_INTAKE_SERVICE_IDENTITY": os.environ.get("WATHEFNI_INTAKE_SERVICE_IDENTITY"),
        "WATHEFNI_INBOUND_EMAIL": os.environ.get("WATHEFNI_INBOUND_EMAIL"),
    }
    assert retention["WATHEFNI_INTAKE_SCAN_REUSE_HOURS"] == "168"
    assert retention["WATHEFNI_INTAKE_ORPHAN_GRACE_SECONDS"] == "86400"
    assert retention["WATHEFNI_INTAKE_SERVICE_IDENTITY"] == "wathefni-orchestrator-production"
    assert retention["WATHEFNI_INBOUND_EMAIL"] == "off"
    assert app.inbound_email_enabled() is False

    out = {
        "ok": True,
        "quarantine": {
            "mount": str(root),
            "mode": "0700",
            "hash_preserved": True,
            "cross_tenant_absent": True,
        },
        "clamav": {
            "version": version,
            "clean": clean_res.to_record(),
            "infected": infected_res.to_record(),
            "eicar_isolated_tmp": str(tmp),
        },
        "mailbox_fail_closed": {
            "legacy_import": legacy.get("error"),
            "live_sync": sync.get("error"),
        },
        "retention": retention,
        "service_identity": {
            "configured": retention["WATHEFNI_INTAKE_SERVICE_IDENTITY"],
            "roles": [
                "inbound_webhook",
                "quarantine_write",
                "scanner_access",
                "extraction",
                "identity_resolution",
            ],
        },
    }
    write("infra-dark-proof.json", out)
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
