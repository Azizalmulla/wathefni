#!/usr/bin/env python3
"""Attendance Wave 2B — outbound on-prem Wathefni capture agent.

LAN BioTime poll → durable sqlite outbox/checkpoint → upload to ingest callback.
Credentials encrypted at rest (Fernet). No biometric payloads stored.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from cryptography.fernet import Fernet, InvalidToken

from attendance_capture_biotime import BioTimeAuthError, BioTimeClient, pull_transactions_paginated
from attendance_capture_contract import CONNECTOR_VERSION, CanonicalPunch, ConnectorHealth


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class CredentialVault:
    """Encrypt connector secrets at rest; supports dual-credential rotation window."""

    def __init__(self, key: bytes | str | None = None) -> None:
        if key is None:
            key = os.environ.get("WATHEFNI_CAPTURE_CREDENTIAL_KEY")
        if not key:
            # Ephemeral key for local tests only — production must set env key.
            key = Fernet.generate_key()
            self.ephemeral = True
        else:
            if isinstance(key, str):
                key = key.encode("utf-8")
            self.ephemeral = False
        self._fernet = Fernet(key)

    @staticmethod
    def generate_key() -> str:
        return Fernet.generate_key().decode("ascii")

    def seal(self, secrets: dict[str, Any]) -> str:
        raw = json.dumps(secrets, sort_keys=True).encode("utf-8")
        return self._fernet.encrypt(raw).decode("ascii")

    def open(self, token: str) -> dict[str, Any]:
        try:
            raw = self._fernet.decrypt(token.encode("ascii"))
        except InvalidToken as exc:
            raise RuntimeError("credential_decrypt_failed") from exc
        return json.loads(raw.decode("utf-8"))


SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_event_id TEXT NOT NULL UNIQUE,
  company_code TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  delivered_at TEXT
);
CREATE TABLE IF NOT EXISTS checkpoints (
  connector_id TEXT PRIMARY KEY,
  checkpoint TEXT,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS health (
  connector_id TEXT PRIMARY KEY,
  payload_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS credentials (
  connector_id TEXT PRIMARY KEY,
  sealed TEXT NOT NULL,
  rotated_at TEXT,
  previous_sealed TEXT
);
CREATE TABLE IF NOT EXISTS processed_files (
  file_sha256 TEXT PRIMARY KEY,
  filename TEXT,
  processed_at TEXT NOT NULL
);
"""


class AgentStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def set_checkpoint(self, connector_id: str, checkpoint: str | None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO checkpoints(connector_id, checkpoint, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(connector_id) DO UPDATE SET checkpoint=excluded.checkpoint, updated_at=excluded.updated_at",
                (connector_id, checkpoint, _utcnow()),
            )
            conn.commit()

    def get_checkpoint(self, connector_id: str) -> str | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT checkpoint FROM checkpoints WHERE connector_id=?", (connector_id,)).fetchone()
            return None if not row else row["checkpoint"]

    def enqueue(self, punch: CanonicalPunch | dict[str, Any]) -> bool:
        data = punch.to_dict() if isinstance(punch, CanonicalPunch) else dict(punch)
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO outbox(source_event_id, company_code, payload_json, created_at) VALUES(?,?,?,?)",
                    (data["source_event_id"], data["company_code"], json.dumps(data), _utcnow()),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def pending(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM outbox WHERE delivered_at IS NULL ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_delivered(self, source_event_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE outbox SET delivered_at=? WHERE source_event_id=?",
                (_utcnow(), source_event_id),
            )
            conn.commit()

    def mark_attempt(self, source_event_id: str, error: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE outbox SET attempts=attempts+1, last_error=? WHERE source_event_id=?",
                (error[:500], source_event_id),
            )
            conn.commit()

    def save_health(self, health: ConnectorHealth) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO health(connector_id, payload_json, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(connector_id) DO UPDATE SET payload_json=excluded.payload_json, updated_at=excluded.updated_at",
                (health.connector_id, json.dumps(health.to_dict()), _utcnow()),
            )
            conn.commit()

    def get_health(self, connector_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT payload_json FROM health WHERE connector_id=?", (connector_id,)).fetchone()
            return None if not row else json.loads(row["payload_json"])

    def store_credentials(self, connector_id: str, sealed: str, *, keep_previous: bool = True) -> None:
        with self._lock, self._connect() as conn:
            prev = None
            if keep_previous:
                row = conn.execute("SELECT sealed FROM credentials WHERE connector_id=?", (connector_id,)).fetchone()
                prev = None if not row else row["sealed"]
            conn.execute(
                "INSERT INTO credentials(connector_id, sealed, rotated_at, previous_sealed) VALUES(?,?,?,?) "
                "ON CONFLICT(connector_id) DO UPDATE SET "
                "previous_sealed=COALESCE(?, credentials.sealed), sealed=excluded.sealed, rotated_at=excluded.rotated_at",
                (connector_id, sealed, _utcnow(), prev, prev),
            )
            conn.commit()

    def load_credentials(self, connector_id: str) -> tuple[str | None, str | None]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT sealed, previous_sealed FROM credentials WHERE connector_id=?",
                (connector_id,),
            ).fetchone()
            if not row:
                return None, None
            return row["sealed"], row["previous_sealed"]

    def mark_file_processed(self, file_sha256: str, filename: str) -> bool:
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO processed_files(file_sha256, filename, processed_at) VALUES(?,?,?)",
                    (file_sha256, filename, _utcnow()),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def file_already_processed(self, file_sha256: str) -> bool:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT 1 FROM processed_files WHERE file_sha256=?", (file_sha256,)).fetchone()
            return row is not None


UploadFn = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class AgentConfig:
    company_code: str
    connector_id: str
    biotime_base_url: str
    db_path: str
    poll_interval_s: float = 0.0  # 0 = manual tick only (tests)
    page_size: int = 50


class WathefniCaptureAgent:
    """Outbound agent: poll BioTime, queue, deliver, checkpoint, health."""

    def __init__(
        self,
        config: AgentConfig,
        *,
        vault: CredentialVault | None = None,
        upload: UploadFn | None = None,
        biotime_client: BioTimeClient | None = None,
    ) -> None:
        self.config = config
        self.vault = vault or CredentialVault()
        self.store = AgentStore(config.db_path)
        self.upload = upload
        self.client = biotime_client
        self.version = CONNECTOR_VERSION
        self._error_count = 0
        self._last_error: str | None = None

    def set_biotime_secrets(self, *, username: str, password: str, token: str | None = None) -> None:
        sealed = self.vault.seal({"username": username, "password": password, "token": token})
        self.store.store_credentials(self.config.connector_id, sealed, keep_previous=True)
        if self.client is None:
            self.client = BioTimeClient(base_url=self.config.biotime_base_url, username=username, password=password, token=token)
        else:
            self.client.rotate_credentials(username=username, password=password, token=token)

    def rotate_biotime_secrets(self, *, username: str, password: str, token: str | None = None) -> None:
        self.set_biotime_secrets(username=username, password=password, token=token)

    def _ensure_client(self) -> BioTimeClient:
        if self.client is not None:
            return self.client
        sealed, previous = self.store.load_credentials(self.config.connector_id)
        if not sealed:
            raise BioTimeAuthError("missing_credentials")
        try:
            secrets = self.vault.open(sealed)
        except RuntimeError:
            if not previous:
                raise
            secrets = self.vault.open(previous)
        self.client = BioTimeClient(
            base_url=self.config.biotime_base_url,
            username=secrets.get("username"),
            password=secrets.get("password"),
            token=secrets.get("token"),
        )
        return self.client

    def poll_biotime_once(self, *, start_time: str | None = None, end_time: str | None = None) -> dict[str, Any]:
        client = self._ensure_client()
        checkpoint = self.store.get_checkpoint(self.config.connector_id)
        try:
            result = pull_transactions_paginated(
                client,
                company_code=self.config.company_code,
                connector_id=self.config.connector_id,
                start_time=start_time,
                end_time=end_time,
                page_size=self.config.page_size,
                after_checkpoint=checkpoint,
            )
        except BioTimeAuthError as exc:
            self._error_count += 1
            self._last_error = str(exc)
            self._write_health(status="error")
            return {"ok": False, "error": str(exc), "auth_error": True}
        except Exception as exc:  # noqa: BLE001
            self._error_count += 1
            self._last_error = repr(exc)
            self._write_health(status="error")
            return {"ok": False, "error": repr(exc)}

        enqueued = 0
        for punch in result["punches"]:
            if self.store.enqueue(punch):
                enqueued += 1
        if result.get("checkpoint"):
            self.store.set_checkpoint(self.config.connector_id, result["checkpoint"])
        self._write_health(status="ok", events=enqueued, checkpoint=result.get("checkpoint"))
        return {
            "ok": True,
            "enqueued": enqueued,
            "privacy_fails": result.get("privacy_fails") or [],
            "quarantined": result.get("quarantined") or [],
            "checkpoint": result.get("checkpoint"),
            "pages": result.get("pages"),
        }

    def flush_outbox(self, *, limit: int = 100) -> dict[str, Any]:
        if self.upload is None:
            return {"ok": False, "error": "upload_not_configured"}
        pending = self.store.pending(limit=limit)
        delivered = 0
        errors = []
        for row in pending:
            payload = json.loads(row["payload_json"])
            try:
                resp = self.upload(payload)
                if resp.get("ok"):
                    self.store.mark_delivered(row["source_event_id"])
                    delivered += 1
                else:
                    err = str(resp.get("error") or "upload_rejected")
                    self.store.mark_attempt(row["source_event_id"], err)
                    errors.append(err)
            except Exception as exc:  # noqa: BLE001
                self.store.mark_attempt(row["source_event_id"], repr(exc))
                errors.append(repr(exc))
        status = "ok" if not errors else "degraded"
        self._write_health(status=status, events=delivered)
        return {"ok": not errors, "delivered": delivered, "pending": len(pending) - delivered, "errors": errors[:5]}

    def replay_outbox(self) -> dict[str, Any]:
        """Reconnect replay: flush anything not yet delivered."""
        return self.flush_outbox(limit=1000)

    def _write_health(self, *, status: str, events: int = 0, checkpoint: str | None = None) -> None:
        now = _utcnow()
        cp = checkpoint if checkpoint is not None else self.store.get_checkpoint(self.config.connector_id)
        health = ConnectorHealth(
            connector_id=self.config.connector_id,
            connector_version=self.version,
            company_code=self.config.company_code.upper(),
            status=status,
            last_sync_at=now,
            last_success_at=now if status == "ok" else None,
            lag_seconds=0.0 if status == "ok" else None,
            events_in_window=events,
            error_count=self._error_count,
            last_error=self._last_error,
            checkpoint=cp,
        )
        if status != "ok" and health.last_success_at is None:
            prev = self.store.get_health(self.config.connector_id) or {}
            health.last_success_at = prev.get("last_success_at")
        self.store.save_health(health)

    def health(self) -> dict[str, Any]:
        return self.store.get_health(self.config.connector_id) or {
            "connector_id": self.config.connector_id,
            "status": "offline",
            "connector_version": self.version,
        }

    def simulate_offline_enqueue(self, punches: list[CanonicalPunch]) -> int:
        """Test helper: enqueue without poll (offline capture)."""
        n = 0
        for p in punches:
            if self.store.enqueue(p):
                n += 1
        self._write_health(status="offline", events=n)
        return n
