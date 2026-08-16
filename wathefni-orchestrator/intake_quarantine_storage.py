"""Backend-neutral quarantine storage for durable email ingress.

Authority (intake documents, checksums, manifests, signed access, orphan sweep,
and deletion policy) must remain identical across backends. Only the object
transport changes.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Protocol


UTC = timezone.utc


class QuarantineStorageError(RuntimeError):
    code = "quarantine_storage_error"

    def __init__(self, code: str | None = None, detail: str | None = None) -> None:
        self.code = code or self.code
        self.detail = detail or self.code
        super().__init__(self.detail)


class QuarantineConflictError(QuarantineStorageError):
    code = "quarantine_object_conflict"


class QuarantineMissingError(QuarantineStorageError):
    code = "quarantine_object_missing"


class QuarantineIntegrityError(QuarantineStorageError):
    code = "quarantine_checksum_mismatch"


def _safe_company(value: str | None) -> str:
    company = re.sub(r"[^A-Z0-9_-]", "", str(value or "").strip().upper())
    if not company:
        raise QuarantineStorageError("company_scope_missing")
    return company


def quarantine_object_key(
    *,
    company_code: str,
    inbound_id: str,
    ordinal: int,
    content_sha256: str,
) -> str:
    company = _safe_company(company_code)
    inbound = str(uuid.UUID(str(inbound_id)))
    digest = str(content_sha256).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise QuarantineStorageError("invalid_attachment_checksum")
    return f"{company}/{inbound}/{int(ordinal):04d}/{digest}.bin"


@dataclass(frozen=True)
class QuarantineObjectRef:
    key: str
    content_sha256: str
    size_bytes: int
    backend: str
    reused: bool = False


class QuarantineStorage(Protocol):
    """Permanent production storage contract for intake source objects."""

    backend_name: str

    def object_key(
        self,
        *,
        company_code: str,
        inbound_id: str,
        ordinal: int,
        content_sha256: str,
    ) -> str: ...

    def write(
        self,
        *,
        company_code: str,
        inbound_id: str,
        ordinal: int,
        content_sha256: str,
        data: bytes,
    ) -> QuarantineObjectRef: ...

    def verify(
        self, key: str, expected_sha256: str, expected_size: int
    ) -> QuarantineObjectRef: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> bool: ...

    def iter_object_keys(self) -> Iterator[str]: ...

    @contextmanager
    def open_for_scan(self, key: str) -> Iterator[Path]:
        """Yield a local readable path for malware scanning without changing authority."""
        ...

    def health(self) -> dict[str, Any]: ...


class LocalVolumeQuarantineStorage:
    """Encrypted-volume or local-disk adapter used for staging."""

    backend_name = "local_volume"

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()

    def object_key(
        self,
        *,
        company_code: str,
        inbound_id: str,
        ordinal: int,
        content_sha256: str,
    ) -> str:
        return quarantine_object_key(
            company_code=company_code,
            inbound_id=inbound_id,
            ordinal=ordinal,
            content_sha256=content_sha256,
        )

    def path_for_key(self, key: str) -> Path:
        pure = PurePosixPath(str(key))
        if pure.is_absolute() or ".." in pure.parts or len(pure.parts) != 4:
            raise QuarantineStorageError("invalid_quarantine_key")
        path = (self.root / Path(*pure.parts)).resolve()
        if self.root != path and self.root not in path.parents:
            raise QuarantineStorageError("quarantine_scope_violation")
        return path

    def write(
        self,
        *,
        company_code: str,
        inbound_id: str,
        ordinal: int,
        content_sha256: str,
        data: bytes,
    ) -> QuarantineObjectRef:
        key = self.object_key(
            company_code=company_code,
            inbound_id=inbound_id,
            ordinal=ordinal,
            content_sha256=content_sha256,
        )
        target = self.path_for_key(key)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(target.parent, 0o700)
        except OSError:
            pass
        if target.exists():
            existing = target.read_bytes()
            if (
                len(existing) != len(data)
                or hashlib.sha256(existing).hexdigest() != content_sha256
            ):
                raise QuarantineConflictError()
            return QuarantineObjectRef(
                key=key,
                content_sha256=content_sha256,
                size_bytes=len(data),
                backend=self.backend_name,
                reused=True,
            )
        fd, tmp_name = tempfile.mkstemp(prefix=".ingress-", dir=str(target.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, target)
            dir_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return QuarantineObjectRef(
            key=key,
            content_sha256=content_sha256,
            size_bytes=len(data),
            backend=self.backend_name,
            reused=False,
        )

    def verify(
        self, key: str, expected_sha256: str, expected_size: int
    ) -> QuarantineObjectRef:
        path = self.path_for_key(key)
        if not path.is_file() or path.is_symlink():
            raise QuarantineMissingError()
        data = path.read_bytes()
        if len(data) != int(expected_size):
            raise QuarantineIntegrityError("quarantine_size_mismatch")
        digest = hashlib.sha256(data).hexdigest()
        if digest != str(expected_sha256):
            raise QuarantineIntegrityError()
        return QuarantineObjectRef(
            key=key,
            content_sha256=digest,
            size_bytes=len(data),
            backend=self.backend_name,
            reused=True,
        )

    def exists(self, key: str) -> bool:
        try:
            path = self.path_for_key(key)
        except QuarantineStorageError:
            return False
        return path.is_file() and not path.is_symlink()

    def delete(self, key: str) -> bool:
        path = self.path_for_key(key)
        if not path.exists():
            return False
        path.unlink(missing_ok=True)
        return True

    def iter_object_keys(self) -> Iterator[str]:
        if not self.root.exists():
            return
        for path in self.root.rglob("*.bin"):
            if path.is_file() and not path.is_symlink():
                yield path.relative_to(self.root).as_posix()

    @contextmanager
    def open_for_scan(self, key: str) -> Iterator[Path]:
        path = self.path_for_key(key)
        if not path.is_file() or path.is_symlink():
            raise QuarantineMissingError()
        yield path

    def health(self) -> dict[str, Any]:
        writable = False
        fsync_ok = False
        probe = self.root / ".health-probe"
        try:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.root, 0o700)
            with open(probe, "wb") as handle:
                handle.write(b"ok")
                handle.flush()
                os.fsync(handle.fileno())
            writable = True
            fsync_ok = True
            probe.unlink(missing_ok=True)
        except OSError as exc:
            detail = type(exc).__name__
        else:
            detail = None
        return {
            "backend": self.backend_name,
            "root": str(self.root),
            "exists": self.root.exists(),
            "writable": writable,
            "fsync_ok": fsync_ok,
            "detail": detail,
            "checked_at": datetime.now(UTC).isoformat(),
        }


class S3CompatibleQuarantineStorage:
    """Production object-storage adapter.

    Uses the same logical object keys and checksum/manifest contract as the
    local volume adapter. Requires boto3 only when constructed.
    """

    backend_name = "s3_compatible"

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "email-intake",
        endpoint_url: str | None = None,
        region_name: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        sse: str | None = "AES256",
    ) -> None:
        try:
            import boto3
            from botocore.config import Config as BotoConfig
        except ImportError as exc:  # pragma: no cover - optional until production
            raise QuarantineStorageError(
                "s3_sdk_missing", "boto3 is required for s3_compatible quarantine"
            ) from exc
        self.bucket = str(bucket).strip()
        if not self.bucket:
            raise QuarantineStorageError("s3_bucket_required")
        self.prefix = str(prefix or "email-intake").strip().strip("/")
        self.sse = sse
        kwargs: dict[str, Any] = {
            "service_name": "s3",
            "config": BotoConfig(signature_version="s3v4"),
        }
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        if region_name:
            kwargs["region_name"] = region_name
        if access_key_id and secret_access_key:
            kwargs["aws_access_key_id"] = access_key_id
            kwargs["aws_secret_access_key"] = secret_access_key
        self._client = boto3.client(**kwargs)

    def object_key(
        self,
        *,
        company_code: str,
        inbound_id: str,
        ordinal: int,
        content_sha256: str,
    ) -> str:
        return quarantine_object_key(
            company_code=company_code,
            inbound_id=inbound_id,
            ordinal=ordinal,
            content_sha256=content_sha256,
        )

    def _s3_key(self, key: str) -> str:
        pure = PurePosixPath(str(key))
        if pure.is_absolute() or ".." in pure.parts or len(pure.parts) != 4:
            raise QuarantineStorageError("invalid_quarantine_key")
        return f"{self.prefix}/{key}"

    def write(
        self,
        *,
        company_code: str,
        inbound_id: str,
        ordinal: int,
        content_sha256: str,
        data: bytes,
    ) -> QuarantineObjectRef:
        key = self.object_key(
            company_code=company_code,
            inbound_id=inbound_id,
            ordinal=ordinal,
            content_sha256=content_sha256,
        )
        s3_key = self._s3_key(key)
        if self.exists(key):
            self.verify(key, content_sha256, len(data))
            return QuarantineObjectRef(
                key=key,
                content_sha256=content_sha256,
                size_bytes=len(data),
                backend=self.backend_name,
                reused=True,
            )
        extra: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": s3_key,
            "Body": data,
            "ContentType": "application/octet-stream",
            "Metadata": {
                "content-sha256": content_sha256,
                "size-bytes": str(len(data)),
            },
        }
        if self.sse:
            extra["ServerSideEncryption"] = self.sse
        self._client.put_object(**extra)
        return QuarantineObjectRef(
            key=key,
            content_sha256=content_sha256,
            size_bytes=len(data),
            backend=self.backend_name,
            reused=False,
        )

    def verify(
        self, key: str, expected_sha256: str, expected_size: int
    ) -> QuarantineObjectRef:
        s3_key = self._s3_key(key)
        try:
            obj = self._client.get_object(Bucket=self.bucket, Key=s3_key)
        except Exception as exc:
            raise QuarantineMissingError() from exc
        body = obj["Body"].read()
        if len(body) != int(expected_size):
            raise QuarantineIntegrityError("quarantine_size_mismatch")
        digest = hashlib.sha256(body).hexdigest()
        if digest != str(expected_sha256):
            raise QuarantineIntegrityError()
        return QuarantineObjectRef(
            key=key,
            content_sha256=digest,
            size_bytes=len(body),
            backend=self.backend_name,
            reused=True,
        )

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=self._s3_key(key))
            return True
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        if not self.exists(key):
            return False
        self._client.delete_object(Bucket=self.bucket, Key=self._s3_key(key))
        return True

    def iter_object_keys(self) -> Iterator[str]:
        prefix = f"{self.prefix}/"
        token = None
        while True:
            kwargs: dict[str, Any] = {"Bucket": self.bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            response = self._client.list_objects_v2(**kwargs)
            for item in response.get("Contents") or []:
                full = str(item.get("Key") or "")
                if full.startswith(prefix) and full.endswith(".bin"):
                    yield full[len(prefix) :]
            if not response.get("IsTruncated"):
                break
            token = response.get("NextContinuationToken")

    @contextmanager
    def open_for_scan(self, key: str) -> Iterator[Path]:
        s3_key = self._s3_key(key)
        try:
            obj = self._client.get_object(Bucket=self.bucket, Key=s3_key)
        except Exception as exc:
            raise QuarantineMissingError() from exc
        body = obj["Body"].read()
        fd, tmp_name = tempfile.mkstemp(prefix="quarantine-scan-")
        path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(path, 0o600)
            yield path
        finally:
            path.unlink(missing_ok=True)

    def health(self) -> dict[str, Any]:
        probe_key = f"HEALTHCHECK/{uuid.uuid4()}/0001/{'0' * 64}.bin"
        # health uses a throwaway non-canonical probe under HEALTHCHECK tenant-like prefix
        # without going through object_key validation for inbound UUIDs.
        try:
            s3_key = f"{self.prefix}/.health/{uuid.uuid4().hex}"
            extra: dict[str, Any] = {
                "Bucket": self.bucket,
                "Key": s3_key,
                "Body": b"ok",
            }
            if self.sse:
                extra["ServerSideEncryption"] = self.sse
            self._client.put_object(**extra)
            self._client.delete_object(Bucket=self.bucket, Key=s3_key)
            ok = True
            detail = None
        except Exception as exc:
            ok = False
            detail = type(exc).__name__
        return {
            "backend": self.backend_name,
            "bucket": self.bucket,
            "prefix": self.prefix,
            "writable": ok,
            "sse": self.sse,
            "detail": detail,
            "checked_at": datetime.now(UTC).isoformat(),
            "probe_key_shape": probe_key,
        }


def build_quarantine_storage_from_env(
    workspace: Path | str | None = None,
) -> QuarantineStorage:
    backend = str(os.environ.get("WATHEFNI_INTAKE_QUARANTINE_BACKEND") or "local_volume").strip().lower()
    if backend in {"local", "local_volume", "filesystem", "volume"}:
        base = Path(workspace or os.environ.get("WATHEFNI_WORKSPACE") or ".")
        root = Path(
            os.environ.get("WATHEFNI_INTAKE_QUARANTINE_DIR")
            or base / "quarantine" / "email-intake"
        )
        return LocalVolumeQuarantineStorage(root)
    if backend in {"s3", "s3_compatible", "object"}:
        return S3CompatibleQuarantineStorage(
            bucket=str(os.environ.get("WATHEFNI_INTAKE_S3_BUCKET") or ""),
            prefix=str(os.environ.get("WATHEFNI_INTAKE_S3_PREFIX") or "email-intake"),
            endpoint_url=os.environ.get("WATHEFNI_INTAKE_S3_ENDPOINT") or None,
            region_name=os.environ.get("WATHEFNI_INTAKE_S3_REGION") or None,
            access_key_id=os.environ.get("WATHEFNI_INTAKE_S3_ACCESS_KEY") or None,
            secret_access_key=os.environ.get("WATHEFNI_INTAKE_S3_SECRET_KEY") or None,
            sse=os.environ.get("WATHEFNI_INTAKE_S3_SSE") or "AES256",
        )
    raise QuarantineStorageError("unsupported_quarantine_backend", backend)
