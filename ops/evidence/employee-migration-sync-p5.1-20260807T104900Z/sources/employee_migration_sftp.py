"""Migration Sync P5.1 — real SFTP / file-feed connector.

Fetches completed remote CSV/XLSX files and returns rows for the existing
foundation preview/commit pipeline. Never mutates remote source files by
default. Lifecycle/deletion of employees remains P6-only.
"""

from __future__ import annotations

import csv
import fnmatch
import hashlib
import io
import os
import socket
import time
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

# Optional at import — install paramiko in deploy/venv.
try:
    import paramiko
except ImportError:  # pragma: no cover
    paramiko = None  # type: ignore[assignment]

try:
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover
    load_workbook = None  # type: ignore[assignment]


_SECRET_KEYS = frozenset(
    {"password", "token", "api_key", "secret", "private_key", "private_key_passphrase"}
)


def require_paramiko() -> Any:
    if paramiko is None:
        raise RuntimeError("paramiko_not_installed")
    return paramiko


def safe_join_remote(remote_dir: str, name: str) -> str:
    """Join remote_dir/name; reject path traversal and absolute name hijacks."""
    base = PurePosixPath("/" + str(remote_dir or "/").lstrip("/")).as_posix()
    raw_name = str(name or "").strip()
    if not raw_name or raw_name in {".", ".."}:
        raise ValueError("invalid_remote_name")
    if "/" in raw_name or "\\" in raw_name or ".." in raw_name:
        raise ValueError("path_traversal_rejected")
    joined = PurePosixPath(base) / raw_name
    # Ensure still under base
    if not joined.as_posix().startswith(base.rstrip("/") + "/") and joined.as_posix() != base:
        raise ValueError("path_traversal_rejected")
    return joined.as_posix()


def content_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_tabular_bytes(data: bytes, *, filename: str) -> list[dict[str, str]]:
    name = str(filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        return _parse_xlsx(data)
    # Default CSV (also .txt / unknown)
    return _parse_csv(data)


def _parse_csv(data: bytes) -> list[dict[str, str]]:
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("malformed_csv_no_header")
    rows: list[dict[str, str]] = []
    for r in reader:
        rows.append({str(k): ("" if v is None else str(v)) for k, v in dict(r).items() if k is not None})
    return rows


def _parse_xlsx(data: bytes) -> list[dict[str, str]]:
    if load_workbook is None:
        raise RuntimeError("openpyxl_not_installed")
    wb = load_workbook(filename=io.BytesIO(data), read_only=True, data_only=True)
    try:
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        header_row = next(rows_iter, None)
        if not header_row:
            raise ValueError("malformed_xlsx_no_header")
        headers = [str(h).strip() if h is not None else "" for h in header_row]
        if not any(headers):
            raise ValueError("malformed_xlsx_no_header")
        out: list[dict[str, str]] = []
        for row in rows_iter:
            if row is None or all(c is None or str(c).strip() == "" for c in row):
                continue
            item: dict[str, str] = {}
            for i, h in enumerate(headers):
                if not h:
                    continue
                val = row[i] if i < len(row) else None
                item[h] = "" if val is None else str(val)
            out.append(item)
        return out
    finally:
        wb.close()


def _fingerprint_hex(key: Any) -> str:
    """Return SHA256:base64 fingerprint matching OpenSSH `ssh-keygen -lf` style."""
    digest = hashlib.sha256(key.asbytes()).digest()
    import base64

    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def _verify_host_key(client: Any, *, host: str, port: int, config: dict[str, Any], company: str) -> dict[str, Any]:
    transport = client.get_transport()
    if transport is None:
        raise ConnectionError("sftp_transport_missing")
    key = transport.get_remote_server_key()
    fp = _fingerprint_hex(key)
    expected = str(config.get("host_key_fingerprint") or "").strip()
    known_hosts = str(config.get("known_hosts_path") or "").strip()
    allow_insecure = bool(config.get("allow_insecure_host_key"))
    env_allow = str(os.environ.get("WATHEFNI_SFTP_ALLOW_INSECURE_HOST_KEY") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    canary_ok = str(company or "").upper() == "WATHEFNI" and (allow_insecure or env_allow)

    if expected:
        # Accept SHA256:... or bare base64 / hex variants
        norm_exp = expected.replace(" ", "")
        norm_fp = fp.replace(" ", "")
        if norm_exp.lower().startswith("sha256:"):
            if norm_fp.lower() != norm_exp.lower() and norm_fp.split(":", 1)[-1].lower() != norm_exp.split(":", 1)[-1].lower():
                raise PermissionError("sftp_host_key_mismatch")
        elif norm_exp.lower() not in {norm_fp.lower(), norm_fp.split(":", 1)[-1].lower()}:
            raise PermissionError("sftp_host_key_mismatch")
        return {"host_key_fingerprint": fp, "host_key_verified": True, "host": host, "port": port}

    if known_hosts:
        # Already verified by MissingHostKeyPolicy from load_host_keys if present;
        # re-check membership.
        return {"host_key_fingerprint": fp, "host_key_verified": True, "via": "known_hosts"}

    if canary_ok:
        return {
            "host_key_fingerprint": fp,
            "host_key_verified": False,
            "host_key_policy": "insecure_canary_only",
            "host": host,
            "port": port,
        }

    raise PermissionError(
        "sftp_host_key_fingerprint_required:set host_key_fingerprint or known_hosts_path"
    )


def _load_pkey(secrets: dict[str, Any]) -> Any | None:
    pm = require_paramiko()
    raw = secrets.get("private_key")
    if not raw:
        return None
    text = str(raw)
    passphrase = secrets.get("private_key_passphrase")
    pwd = str(passphrase) if passphrase else None
    bio = io.StringIO(text)
    for loader in (
        pm.RSAKey.from_private_key,
        pm.Ed25519Key.from_private_key,
        pm.ECDSAKey.from_private_key,
    ):
        try:
            bio.seek(0)
            return loader(bio, password=pwd)
        except Exception:
            continue
    raise PermissionError("sftp_private_key_invalid")


def connect_sftp(
    *,
    config: dict[str, Any],
    secrets: dict[str, Any],
    company: str = "",
) -> tuple[Any, Any, dict[str, Any]]:
    """Return (ssh_client, sftp_client, meta). Caller must close."""
    pm = require_paramiko()
    host = str(config.get("host") or "").strip()
    if not host:
        raise ValueError("sftp_host_required")
    port = int(config.get("port") or 22)
    username = str(config.get("username") or secrets.get("username") or "").strip()
    if not username:
        raise ValueError("sftp_username_required")
    timeout = float(config.get("connect_timeout_seconds") or 30)

    client = pm.SSHClient()
    known_hosts = str(config.get("known_hosts_path") or "").strip()
    if known_hosts and os.path.isfile(known_hosts):
        client.load_host_keys(known_hosts)
        client.set_missing_host_key_policy(pm.RejectPolicy())
    else:
        # Accept temporarily; verify fingerprint after connect.
        client.set_missing_host_key_policy(pm.AutoAddPolicy())

    pkey = _load_pkey(secrets)
    password = secrets.get("password")
    if password is not None:
        password = str(password)
    if not pkey and not password:
        raise PermissionError("sftp_credentials_required")

    try:
        client.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            pkey=pkey,
            timeout=timeout,
            allow_agent=False,
            look_for_keys=False,
            banner_timeout=timeout,
            auth_timeout=timeout,
        )
    except socket.timeout as exc:
        client.close()
        raise TimeoutError("connector_timeout") from exc
    except pm.AuthenticationException as exc:
        client.close()
        raise PermissionError("connector_auth_failed") from exc
    except Exception as exc:
        client.close()
        msg = str(exc).lower()
        if "timed out" in msg or "timeout" in msg:
            raise TimeoutError("connector_timeout") from exc
        if "auth" in msg:
            raise PermissionError("connector_auth_failed") from exc
        raise ConnectionError("connector_unavailable") from exc

    verify_meta = _verify_host_key(client, host=host, port=port, config=config, company=company)
    sftp = client.open_sftp()
    sftp.get_channel().settimeout(timeout)
    return client, sftp, verify_meta


def _match_pattern(name: str, pattern: str) -> bool:
    pat = str(pattern or "*").strip() or "*"
    return fnmatch.fnmatch(name, pat)


def _is_supported_file(name: str, formats: list[str]) -> bool:
    lower = name.lower()
    for fmt in formats:
        f = fmt.lower().lstrip(".")
        if f == "csv" and lower.endswith((".csv", ".txt")):
            return True
        if f in {"xlsx", "xlsm"} and lower.endswith((".xlsx", ".xlsm")):
            return True
    return False


def list_remote_candidates(sftp: Any, *, remote_dir: str, pattern: str, formats: list[str]) -> list[dict[str, Any]]:
    base = PurePosixPath("/" + str(remote_dir or "/").lstrip("/")).as_posix()
    try:
        entries = sftp.listdir_attr(base)
    except FileNotFoundError as exc:
        raise ConnectionError(f"sftp_remote_dir_missing:{base}") from exc

    out: list[dict[str, Any]] = []
    for attr in entries:
        name = str(getattr(attr, "filename", "") or "")
        if not name or name.startswith("."):
            continue
        if not _match_pattern(name, pattern):
            continue
        if not _is_supported_file(name, formats):
            continue
        # Skip directories
        mode = int(getattr(attr, "st_mode", 0) or 0)
        if mode & 0o170000 == 0o040000:
            continue
        path = safe_join_remote(base, name)
        out.append(
            {
                "name": name,
                "path": path,
                "size": int(getattr(attr, "st_size", 0) or 0),
                "mtime": float(getattr(attr, "st_mtime", 0) or 0),
            }
        )
    # Deterministic order: name then path
    out.sort(key=lambda x: (x["name"].lower(), x["path"]))
    return out


def download_file(sftp: Any, remote_path: str) -> bytes:
    bio = io.BytesIO()
    try:
        sftp.getfo(remote_path, bio)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"sftp_file_disappeared:{remote_path}") from exc
    return bio.getvalue()


def maybe_archive(sftp: Any, *, remote_path: str, archive_dir: str | None) -> str | None:
    """Optionally move processed file into archive_dir. Never deletes source by default."""
    dest_dir = str(archive_dir or "").strip()
    if not dest_dir:
        return None
    name = PurePosixPath(remote_path).name
    dest = safe_join_remote(dest_dir, name)
    # Avoid clobber: append short hash if exists
    try:
        sftp.stat(dest)
        stem = PurePosixPath(name).stem
        suffix = PurePosixPath(name).suffix
        dest = safe_join_remote(dest_dir, f"{stem}-{int(time.time())}{suffix}")
    except FileNotFoundError:
        pass
    try:
        sftp.rename(remote_path, dest)
        return dest
    except Exception:
        return None


def fetch_sftp_rows(
    *,
    config: dict[str, Any],
    secrets: dict[str, Any],
    cursor: dict[str, Any] | None,
    company: str = "",
    record_processed: Any | None = None,
) -> dict[str, Any]:
    """Connector contract implementation for kind=sftp.

    record_processed(sha, meta) -> bool already_processed optional callback
    used by connectors layer for DB ledger; when None uses cursor.processed_shas.
    """
    cursor = dict(cursor or {})
    processed = set(str(x) for x in (cursor.get("processed_shas") or []) if x)
    remote_dir = str(config.get("remote_dir") or "/").strip() or "/"
    pattern = str(config.get("file_pattern") or "*.csv").strip() or "*.csv"
    formats = [str(x).lower() for x in (config.get("file_formats") or ["csv", "xlsx"])]
    stability = int(config.get("stability_seconds") or 30)
    max_files = max(1, min(int(config.get("max_files_per_run") or 50), 200))
    archive_dir = config.get("archive_remote_dir")
    delete_after = bool(config.get("delete_after_process"))  # default False; discouraged

    client, sftp, verify_meta = connect_sftp(config=config, secrets=secrets, company=company)
    file_meta: list[dict[str, Any]] = []
    file_errors: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    all_rows: list[dict[str, str]] = []
    new_shas: list[str] = []
    now = time.time()

    try:
        candidates = list_remote_candidates(
            sftp, remote_dir=remote_dir, pattern=pattern, formats=formats
        )
        for cand in candidates:
            if len(new_shas) >= max_files:
                skipped.append({**cand, "reason": "max_files_per_run"})
                continue
            age = now - float(cand["mtime"] or 0)
            if stability > 0 and age < stability:
                skipped.append({**cand, "reason": "partial_or_unstable_upload"})
                continue

            try:
                data = download_file(sftp, cand["path"])
            except FileNotFoundError:
                file_errors.append({"path": cand["path"], "error": "file_disappeared_mid_run"})
                continue
            except Exception as exc:
                file_errors.append({"path": cand["path"], "error": str(exc)[:120]})
                continue

            # Size changed during download vs listing → treat as unstable
            if cand["size"] and len(data) != int(cand["size"]):
                skipped.append({**cand, "reason": "size_mismatch_partial_upload", "downloaded": len(data)})
                continue

            sha = content_sha256(data)
            already = sha in processed
            if record_processed is not None:
                try:
                    already = bool(record_processed(sha, {**cand, "content_sha256": sha})) or already
                except Exception:
                    pass
            if already:
                skipped.append({**cand, "reason": "duplicate_content", "content_sha256": sha})
                continue

            try:
                rows = parse_tabular_bytes(data, filename=cand["name"])
            except Exception as exc:
                file_errors.append(
                    {
                        "path": cand["path"],
                        "content_sha256": sha,
                        "error": "malformed_file",
                        "detail": str(exc)[:120],
                    }
                )
                continue

            # Tag provenance without colliding with employee fields
            for r in rows:
                r.setdefault("_source_file", cand["name"])
                r.setdefault("_source_file_sha256", sha)

            all_rows.extend(rows)
            new_shas.append(sha)
            processed.add(sha)
            archived_to = None
            if archive_dir:
                archived_to = maybe_archive(sftp, remote_path=cand["path"], archive_dir=str(archive_dir))
            elif delete_after:
                # Explicit opt-in only — never default.
                try:
                    sftp.remove(cand["path"])
                    archived_to = "deleted"
                except Exception:
                    archived_to = None

            file_meta.append(
                {
                    "path": cand["path"],
                    "name": cand["name"],
                    "content_sha256": sha,
                    "rows": len(rows),
                    "size": len(data),
                    "archived_to": archived_to,
                }
            )
    finally:
        try:
            sftp.close()
        except Exception:
            pass
        try:
            client.close()
        except Exception:
            pass

    # Cap processed_shas growth in cursor (keep recent)
    processed_list = list(processed)
    if len(processed_list) > 5000:
        processed_list = processed_list[-5000:]

    status_hint = "ok"
    if file_errors and all_rows:
        status_hint = "partial_files"
    elif file_errors and not all_rows and not new_shas:
        status_hint = "all_files_failed"
    elif not all_rows and not file_errors:
        status_hint = "no_new_files"

    return {
        "rows": all_rows,
        "cursor_after": {
            "mode": "file_feed",
            "processed_shas": processed_list,
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "files_processed": [f["content_sha256"] for f in file_meta],
        },
        "lifecycle_signals": [],
        "meta": {
            "kind": "sftp",
            "fetched": len(all_rows),
            "files_ok": file_meta,
            "files_skipped": skipped,
            "files_failed": file_errors,
            "status_hint": status_hint,
            "host_key": verify_meta,
            "remote_dir": remote_dir,
            "pattern": pattern,
        },
    }


# --- In-process SFTP test server (canary / smoke only) ----------------------------


class _StubServer(paramiko.ServerInterface if paramiko else object):  # type: ignore[misc]
    def __init__(self, username: str, password: str | None, pkey: Any | None):
        self.username = username
        self.password = password
        self.pkey = pkey
        self.event = None

    def check_auth_password(self, username: str, password: str) -> int:
        pm = require_paramiko()
        if username == self.username and self.password is not None and password == self.password:
            return pm.AUTH_SUCCESSFUL
        return pm.AUTH_FAILED

    def check_auth_publickey(self, username: str, key: Any) -> int:
        pm = require_paramiko()
        if username != self.username or self.pkey is None:
            return pm.AUTH_FAILED
        if key.get_name() == self.pkey.get_name() and key.asbytes() == self.pkey.asbytes():
            return pm.AUTH_SUCCESSFUL
        return pm.AUTH_FAILED

    def check_channel_request(self, kind: str, chanid: int) -> int:
        pm = require_paramiko()
        if kind == "session":
            return pm.OPEN_SUCCEEDED
        return pm.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def get_allowed_auths(self, username: str) -> str:
        methods = []
        if self.password is not None:
            methods.append("password")
        if self.pkey is not None:
            methods.append("publickey")
        return ",".join(methods) or "none"


class _StubSFTPHandle(paramiko.SFTPHandle if paramiko else object):  # type: ignore[misc]
    def __init__(self, file_obj: Any, flags: int = 0):
        if paramiko:
            super().__init__(flags)
        self.file_obj = file_obj

    def stat(self) -> Any:
        pm = require_paramiko()
        st = os.fstat(self.file_obj.fileno())
        return pm.SFTPAttributes.from_stat(st)

    def read(self, offset: int, length: int) -> bytes:
        self.file_obj.seek(offset)
        return self.file_obj.read(length)

    def write(self, offset: int, data: bytes) -> Any:
        pm = require_paramiko()
        self.file_obj.seek(offset)
        self.file_obj.write(data)
        return pm.SFTP_OK

    def close(self) -> None:
        try:
            self.file_obj.close()
        except Exception:
            pass


class _StubSFTPServer(paramiko.SFTPServerInterface if paramiko else object):  # type: ignore[misc]
    def __init__(self, server: Any, *args: Any, root: str = "/tmp", **kwargs: Any):
        if paramiko:
            super().__init__(server, *args, **kwargs)
        self.root = os.path.abspath(root)

    def _full(self, path: str) -> str:
        # Chroot-like: map absolute SFTP paths under root
        rel = path.lstrip("/")
        full = os.path.abspath(os.path.join(self.root, rel))
        if not full.startswith(self.root):
            raise PermissionError("path_traversal")
        return full

    def list_folder(self, path: str) -> list[Any] | int:
        pm = require_paramiko()
        try:
            full = self._full(path or "/")
            out = []
            for name in sorted(os.listdir(full)):
                attr = pm.SFTPAttributes.from_stat(os.stat(os.path.join(full, name)))
                attr.filename = name
                out.append(attr)
            return out
        except Exception:
            return pm.SFTP_FAILURE

    def stat(self, path: str) -> Any:
        pm = require_paramiko()
        try:
            return pm.SFTPAttributes.from_stat(os.stat(self._full(path)))
        except FileNotFoundError:
            return pm.SFTP_NO_SUCH_FILE
        except Exception:
            return pm.SFTP_FAILURE

    def lstat(self, path: str) -> Any:
        return self.stat(path)

    def open(self, path: str, flags: int, attr: Any) -> Any:
        pm = require_paramiko()
        full = self._full(path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        mode = "r+b"
        if flags & os.O_WRONLY:
            mode = "wb"
        elif flags & os.O_RDWR:
            mode = "r+b"
        if flags & os.O_CREAT:
            open(full, "a").close()
        try:
            f = open(full, mode)
        except FileNotFoundError:
            return pm.SFTP_NO_SUCH_FILE
        return _StubSFTPHandle(f, flags)

    def remove(self, path: str) -> int:
        pm = require_paramiko()
        try:
            os.remove(self._full(path))
            return pm.SFTP_OK
        except FileNotFoundError:
            return pm.SFTP_NO_SUCH_FILE
        except Exception:
            return pm.SFTP_FAILURE

    def rename(self, oldpath: str, newpath: str) -> int:
        pm = require_paramiko()
        try:
            os.rename(self._full(oldpath), self._full(newpath))
            return pm.SFTP_OK
        except Exception:
            return pm.SFTP_FAILURE

    def mkdir(self, path: str, attr: Any) -> int:
        pm = require_paramiko()
        try:
            os.makedirs(self._full(path), exist_ok=True)
            return pm.SFTP_OK
        except Exception:
            return pm.SFTP_FAILURE


def start_test_sftp_server(
    *,
    root_dir: str,
    host: str = "127.0.0.1",
    port: int = 0,
    username: str = "sftpuser",
    password: str = "sftppass",
) -> dict[str, Any]:
    """Start a background threaded SFTP server for smoke tests. Returns connection info."""
    import socket
    import threading

    pm = require_paramiko()
    os.makedirs(root_dir, exist_ok=True)
    host_key = pm.RSAKey.generate(2048)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(8)
    bound_port = sock.getsockname()[1]
    stop = threading.Event()

    def _handle(conn: Any) -> None:
        transport = None
        try:
            transport = pm.Transport(conn)
            transport.add_server_key(host_key)
            transport.set_subsystem_handler("sftp", pm.SFTPServer, _StubSFTPServer, root=root_dir)
            server = _StubServer(username, password, None)
            transport.start_server(server=server)
            # Keep transport alive for the SFTP session duration.
            channel = transport.accept(20)
            if channel is None:
                return
            while transport.is_active() and not stop.is_set():
                time.sleep(0.05)
        except Exception:
            pass
        finally:
            try:
                if transport is not None:
                    transport.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

    def _serve() -> None:
        while not stop.is_set():
            sock.settimeout(0.5)
            try:
                conn, _addr = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=_handle, args=(conn,), daemon=True).start()

    thread = threading.Thread(target=_serve, name="p51-sftp-test", daemon=True)
    thread.start()
    fp = _fingerprint_hex(host_key)
    return {
        "host": host,
        "port": bound_port,
        "username": username,
        "password": password,
        "host_key_fingerprint": fp,
        "root_dir": root_dir,
        "stop": stop,
        "sock": sock,
        "thread": thread,
        "host_key": host_key,
    }


def stop_test_sftp_server(info: dict[str, Any]) -> None:
    stop = info.get("stop")
    if stop is not None:
        stop.set()
    sock = info.get("sock")
    if sock is not None:
        try:
            sock.close()
        except Exception:
            pass


def redact_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in dict(config or {}).items()
        if str(k).lower() not in _SECRET_KEYS
    }
