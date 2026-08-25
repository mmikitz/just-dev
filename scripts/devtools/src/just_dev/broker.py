"""A local, HMAC-authenticated credential broker with no token persistence."""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from multiprocessing.connection import AuthenticationError as ConnectionAuthenticationError
from multiprocessing.connection import Client, Listener
from platformdirs import user_cache_dir, user_config_dir, user_runtime_dir
from pydantic import Field, ValidationError

from .errors import (
    AuthenticationError,
    BrokerError,
    ConfigurationError,
    ConflictError,
    DevtoolsError,
    InputValidationError,
    NetworkError,
    PermissionDeniedError,
)
from .models import BrokerStatus, StrictModel
from .redaction import redact_data, redact_text


APP_NAME = "just-dev"
REQUIRED_SCOPES = frozenset({"jira", "confluence", "bitbucket", "jenkins"})
MAX_TTL_SECONDS = 8 * 60 * 60


class KeePassProfile(StrictModel):
    version: int = 1
    database: str
    keyfile: str | None = None
    entries: dict[str, str] = Field(default_factory=dict)


class BrokerState(StrictModel):
    endpoint: str
    family: str
    auth_key: str
    expires_at: datetime
    platform: str
    pid: int


def _private_directory(path: Path) -> Path:
    try:
        path.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            path.chmod(0o700)
    except OSError as exc:
        raise BrokerError(f"Unable to prepare private credential-broker storage at {path}.") from exc
    return path


def _config_directory() -> Path:
    return _private_directory(Path(user_config_dir(APP_NAME)))


def _runtime_directory() -> Path:
    raw_path = user_runtime_dir(APP_NAME)
    path = Path(raw_path) if raw_path else Path(user_cache_dir(APP_NAME)) / "runtime"
    return _private_directory(path)


def _safe_profile_name(name: str) -> str:
    if not name or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in name):
        raise InputValidationError("Profile names may contain only letters, numbers, underscores, and hyphens.")
    return name


def _atomic_json_write(path: Path, value: Mapping[str, Any]) -> None:
    """Write metadata with owner-only permissions; it must never contain raw tokens."""

    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


class ProfileStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = _private_directory(directory or (_config_directory() / "profiles"))

    def path_for(self, profile: str) -> Path:
        return self.directory / f"{_safe_profile_name(profile)}.json"

    def save(self, profile: str, value: KeePassProfile) -> Path:
        path = self.path_for(profile)
        _atomic_json_write(path, value.model_dump(mode="json"))
        return path

    def load(self, profile: str) -> KeePassProfile:
        path = self.path_for(profile)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return KeePassProfile.model_validate(raw)
        except FileNotFoundError as exc:
            raise ConfigurationError(f"No local auth profile named '{profile}'. Run configure-auth first.") from exc
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise ConfigurationError(f"Cannot read local auth profile '{profile}': {exc}") from exc


def validate_profile(profile: KeePassProfile) -> None:
    database = Path(profile.database).expanduser()
    if not database.is_file():
        raise ConfigurationError(f"KeePass database was not found: {database}")
    if profile.keyfile and not Path(profile.keyfile).expanduser().is_file():
        raise ConfigurationError(f"KeePass keyfile was not found: {Path(profile.keyfile).expanduser()}")
    missing = REQUIRED_SCOPES - set(profile.entries)
    unknown = set(profile.entries) - REQUIRED_SCOPES
    if missing or unknown or any(not value.strip() for value in profile.entries.values()):
        details: list[str] = []
        if missing:
            details.append("missing entries: " + ", ".join(sorted(missing)))
        if unknown:
            details.append("unknown entries: " + ", ".join(sorted(unknown)))
        raise ConfigurationError("KeePass profile entry UUIDs are invalid (" + "; ".join(details) + ").")
    for scope, entry_uuid in profile.entries.items():
        try:
            UUID(entry_uuid)
        except ValueError as exc:
            raise ConfigurationError(f"KeePass entry UUID for {scope} is invalid.") from exc


def read_keepass_tokens(profile: KeePassProfile, password: str) -> dict[str, str]:
    """Read only the named UUID entries and retain their values in process memory."""

    validate_profile(profile)
    try:
        from pykeepass import PyKeePass
    except ImportError as exc:  # pragma: no cover - dependency is declared, guard helps direct source use.
        raise ConfigurationError("pykeepass is not installed; run uv sync in scripts/devtools.") from exc

    try:
        database = PyKeePass(
            str(Path(profile.database).expanduser()),
            password=password,
            keyfile=str(Path(profile.keyfile).expanduser()) if profile.keyfile else None,
        )
    except Exception as exc:  # KeePass has several backend-specific exception classes.
        raise AuthenticationError("Unable to unlock the KeePass database.") from exc

    tokens: dict[str, str] = {}
    for scope, entry_uuid in profile.entries.items():
        try:
            entry = database.find_entries(uuid=UUID(entry_uuid), first=True)
        except Exception as exc:
            raise ConfigurationError(f"KeePass entry UUID for {scope} is invalid.") from exc
        if entry is None or not entry.password:
            raise AuthenticationError(f"KeePass entry for {scope} is missing or has no password value.")
        tokens[scope] = entry.password
    return tokens


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def _read_exact(fd: int, size: int) -> bytes:
    pieces = bytearray()
    while len(pieces) < size:
        chunk = os.read(fd, size - len(pieces))
        if not chunk:
            raise BrokerError("Credential broker bootstrap pipe closed unexpectedly.")
        pieces.extend(chunk)
    return bytes(pieces)


def _read_bootstrap(fd: int) -> dict[str, Any]:
    size = int.from_bytes(_read_exact(fd, 4), "big")
    if size <= 0 or size > 1024 * 1024:
        raise BrokerError("Credential broker received an invalid bootstrap payload.")
    try:
        payload = json.loads(_read_exact(fd, size).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrokerError("Credential broker received an invalid bootstrap payload.") from exc
    if not isinstance(payload, dict):
        raise BrokerError("Credential broker received an invalid bootstrap payload.")
    return payload


def _send_json(connection: Any, payload: Mapping[str, Any]) -> None:
    connection.send_bytes(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _recv_json(connection: Any) -> dict[str, Any]:
    try:
        payload = json.loads(connection.recv_bytes().decode("utf-8"))
    except (EOFError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrokerError("Credential broker received malformed IPC data.") from exc
    if not isinstance(payload, dict):
        raise BrokerError("Credential broker received malformed IPC data.")
    return payload


def _error_payload(error: Exception, tokens: Mapping[str, str]) -> dict[str, Any]:
    if isinstance(error, DevtoolsError):
        return {"ok": False, "exit_code": error.exit_code, "message": redact_text(error, list(tokens.values()))}
    return {"ok": False, "exit_code": 27, "message": redact_text(error, list(tokens.values()))}


def _remove_socket(endpoint: str, family: str) -> None:
    if family == "AF_UNIX":
        try:
            Path(endpoint).unlink(missing_ok=True)
        except OSError:
            pass


def _broker_child(fd: int, endpoint: str, family: str, expires_at: float) -> int:
    """Run in a detached process. Only this function sees raw token values."""

    bootstrap = _read_bootstrap(fd)
    os.close(fd)
    encoded_key = bootstrap.get("auth_key")
    tokens = bootstrap.get("tokens")
    if not isinstance(encoded_key, str) or not isinstance(tokens, dict) or not all(isinstance(value, str) for value in tokens.values()):
        raise BrokerError("Credential broker bootstrap payload is incomplete.")
    try:
        auth_key = base64.urlsafe_b64decode(encoded_key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise BrokerError("Credential broker bootstrap authentication key is invalid.") from exc

    _remove_socket(endpoint, family)
    listener = Listener(address=endpoint, family=family, authkey=auth_key)
    shutdown = threading.Event()

    def expire() -> None:
        # accept() cannot be interrupted portably; hard-exit prevents a stale broker from retaining tokens.
        shutdown.set()
        os._exit(0)  # noqa: SLF001 - intentional isolated child-process expiry.

    timer = threading.Timer(max(0.0, expires_at - time.time()), expire)
    timer.daemon = True
    timer.start()
    try:
        while not shutdown.is_set():
            try:
                connection = listener.accept()
            except ConnectionAuthenticationError:
                # A failed HMAC challenge must not terminate a valid broker session.
                continue
            try:
                request = _recv_json(connection)
                kind = request.get("kind")
                if kind == "status":
                    _send_json(connection, {"ok": True, "expires_at": datetime.fromtimestamp(expires_at, UTC).isoformat()})
                elif kind == "shutdown":
                    _send_json(connection, {"ok": True})
                    shutdown.set()
                elif kind == "operation":
                    operation = request.get("operation")
                    payload = request.get("payload")
                    if not isinstance(operation, str) or not isinstance(payload, dict):
                        raise InputValidationError("Credential broker operation request is invalid.")
                    from .operations import execute_operation

                    result = execute_operation(tokens, operation, payload)
                    _send_json(connection, {"ok": True, "result": redact_data(result, list(tokens.values()))})
                else:
                    raise InputValidationError("Credential broker operation is not allowed.")
            except Exception as exc:  # Serialized error path must never reveal tokens.
                _send_json(connection, _error_payload(exc, tokens))
            finally:
                connection.close()
    finally:
        timer.cancel()
        listener.close()
        _remove_socket(endpoint, family)
        tokens.clear()
    return 0


_ERROR_BY_CODE: dict[int, type[DevtoolsError]] = {
    21: AuthenticationError,
    22: PermissionDeniedError,
    23: ConflictError,
    24: NetworkError,
    25: InputValidationError,
}


class BrokerClient:
    def __init__(self, state: BrokerState) -> None:
        self.state = state

    def request(self, kind: str, **payload: Any) -> dict[str, Any]:
        try:
            auth_key = base64.urlsafe_b64decode(self.state.auth_key.encode("ascii"))
            connection = Client(self.state.endpoint, family=self.state.family, authkey=auth_key)
            try:
                _send_json(connection, {"kind": kind, **payload})
                response = _recv_json(connection)
            finally:
                connection.close()
        except (OSError, EOFError, ValueError, ConnectionAuthenticationError, BrokerError) as exc:
            if isinstance(exc, BrokerError):
                raise
            raise BrokerError("Credential broker is unavailable; run unlock-secrets again.") from exc
        if response.get("ok"):
            return response
        error_type = _ERROR_BY_CODE.get(int(response.get("exit_code", 27)), BrokerError)
        raise error_type(redact_text(response.get("message", "Credential broker operation failed.")))

    def invoke(self, operation: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        response = self.request("operation", operation=operation, payload=dict(payload))
        result = response.get("result")
        if not isinstance(result, dict):
            raise BrokerError("Credential broker returned an invalid operation result.")
        return result


class BrokerManager:
    """Manages a single per-profile broker for the current OS/WSL environment."""

    def __init__(
        self,
        *,
        runtime_directory: Path | None = None,
        state_directory: Path | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.runtime_directory = _private_directory(runtime_directory or _runtime_directory())
        self.state_directory = _private_directory(state_directory or (_config_directory() / "sessions"))
        self.clock = clock

    def state_path(self, profile: str) -> Path:
        return self.state_directory / f"{_safe_profile_name(profile)}.json"

    @contextmanager
    def _unlock_lock(self, profile: str):
        """Use an atomic directory lock so concurrent unlocks share one broker."""

        lock_path = self.state_directory / f".{_safe_profile_name(profile)}.unlock-lock"
        deadline = time.monotonic() + 20
        while True:
            try:
                lock_path.mkdir(mode=0o700)
                break
            except FileExistsError:
                try:
                    # A killed parent may leave this non-secret lock behind.
                    if time.time() - lock_path.stat().st_mtime > 120:
                        lock_path.rmdir()
                        continue
                except FileNotFoundError:
                    continue
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise BrokerError("Timed out waiting for another credential unlock to finish.")
                time.sleep(0.05)
            except OSError as exc:
                raise BrokerError("Unable to lock credential-broker startup.") from exc
        try:
            yield
        finally:
            try:
                lock_path.rmdir()
            except OSError:
                pass

    def _load_state(self, profile: str) -> BrokerState | None:
        path = self.state_path(profile)
        try:
            state = BrokerState.model_validate_json(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValidationError):
            return None
        if state.expires_at.timestamp() <= self.clock():
            self._clear_state(profile, state)
            return None
        return state

    def _save_state(self, profile: str, state: BrokerState) -> None:
        _atomic_json_write(self.state_path(profile), state.model_dump(mode="json"))

    def _clear_state(self, profile: str, state: BrokerState | None = None) -> None:
        try:
            self.state_path(profile).unlink(missing_ok=True)
        except OSError:
            pass
        if state:
            _remove_socket(state.endpoint, state.family)

    def _endpoint(self, profile: str) -> tuple[str, str]:
        suffix = f"{_safe_profile_name(profile)}-{uuid4().hex}"
        if os.name == "nt":
            return rf"\\.\pipe\just-dev-{suffix}", "AF_PIPE"
        # Short names avoid AF_UNIX's platform-specific path-length limit.
        return str(self.runtime_directory / f"b-{uuid4().hex[:16]}.sock"), "AF_UNIX"

    def status(self, profile: str = "default") -> BrokerStatus:
        state = self._load_state(profile)
        if state is None:
            return BrokerStatus(active=False)
        try:
            response = BrokerClient(state).request("status")
            expires_at = datetime.fromisoformat(str(response["expires_at"]))
        except DevtoolsError:
            self._clear_state(profile, state)
            return BrokerStatus(active=False)
        return BrokerStatus(active=True, expires_at=expires_at, platform=state.platform, pid=state.pid)

    def client(self, profile: str = "default") -> BrokerClient:
        state = self._load_state(profile)
        if state is None:
            raise AuthenticationError("No active credential broker. Run unlock-secrets first.")
        status = self.status(profile)
        if not status.active:
            raise AuthenticationError("Credential broker has expired. Run unlock-secrets again.")
        return BrokerClient(state)

    def unlock(self, tokens: Mapping[str, str], *, profile: str = "default", ttl_seconds: int = MAX_TTL_SECONDS) -> BrokerStatus:
        """Start a broker after its tokens arrive over an inherited anonymous pipe."""

        _safe_profile_name(profile)
        with self._unlock_lock(profile):
            return self._unlock_locked(tokens, profile=profile, ttl_seconds=ttl_seconds)

    def _unlock_locked(self, tokens: Mapping[str, str], *, profile: str, ttl_seconds: int) -> BrokerStatus:
        ttl_seconds = min(max(1, ttl_seconds), MAX_TTL_SECONDS)
        current = self.status(profile)
        if current.active:
            return current
        missing = REQUIRED_SCOPES - set(tokens)
        if missing or any(not tokens.get(scope, "") for scope in REQUIRED_SCOPES):
            raise AuthenticationError("KeePass profile does not supply all required scoped tokens.")
        endpoint, family = self._endpoint(profile)
        auth_key = secrets.token_bytes(32)
        encoded_key = base64.urlsafe_b64encode(auth_key).decode("ascii")
        expires_at = self.clock() + ttl_seconds
        read_fd, write_fd = os.pipe()
        os.set_inheritable(read_fd, True)
        command = [
            sys.executable,
            "-m",
            "just_dev.broker",
            "--child",
            "--fd",
            str(read_fd),
            "--endpoint",
            endpoint,
            "--family",
            family,
            "--expires-at",
            str(expires_at),
        ]
        try:
            if os.name == "nt":
                process = subprocess.Popen(command, close_fds=False, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                process = subprocess.Popen(command, close_fds=True, pass_fds=(read_fd,), start_new_session=True)
        except OSError as exc:
            os.close(read_fd)
            os.close(write_fd)
            raise BrokerError("Could not start the credential broker.") from exc
        finally:
            try:
                os.close(read_fd)
            except OSError:
                pass

        bootstrap = json.dumps(
            {"auth_key": encoded_key, "tokens": dict(tokens)}, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        try:
            _write_all(write_fd, len(bootstrap).to_bytes(4, "big") + bootstrap)
        finally:
            os.close(write_fd)

        state = BrokerState(
            endpoint=endpoint,
            family=family,
            auth_key=encoded_key,
            expires_at=datetime.fromtimestamp(expires_at, UTC),
            platform=sys.platform,
            pid=process.pid,
        )
        # Wait briefly for the listener. This avoids persisting a state for a failed child startup.
        for _ in range(30):
            try:
                BrokerClient(state).request("status")
                self._save_state(profile, state)
                return self.status(profile)
            except BrokerError:
                time.sleep(0.05)
        try:
            process.terminate()
        except OSError:
            pass
        _remove_socket(endpoint, family)
        raise BrokerError("Credential broker did not start successfully.")

    def unlock_from_keepass(
        self,
        profile: str = "default",
        *,
        password_provider: Callable[[str], str] = getpass.getpass,
        ttl_seconds: int = MAX_TTL_SECONDS,
        profile_store: ProfileStore | None = None,
    ) -> BrokerStatus:
        local_profile = (profile_store or ProfileStore()).load(profile)
        password = password_provider("KeePass master password: ")
        try:
            tokens = read_keepass_tokens(local_profile, password)
            return self.unlock(tokens, profile=profile, ttl_seconds=ttl_seconds)
        finally:
            # Python cannot securely zero immutable strings; ensure it is not retained by this manager.
            password = ""

    def lock(self, profile: str = "default") -> BrokerStatus:
        _safe_profile_name(profile)
        with self._unlock_lock(profile):
            return self._lock_locked(profile)

    def _lock_locked(self, profile: str) -> BrokerStatus:
        state = self._load_state(profile)
        if state is None:
            return BrokerStatus(active=False)
        try:
            BrokerClient(state).request("shutdown")
        except DevtoolsError:
            pass
        self._clear_state(profile, state)
        return BrokerStatus(active=False)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--fd", type=int)
    parser.add_argument("--endpoint")
    parser.add_argument("--family")
    parser.add_argument("--expires-at", type=float)
    args = parser.parse_args(argv)
    if not args.child or args.fd is None or not args.endpoint or not args.family or args.expires_at is None:
        return 2
    try:
        return _broker_child(args.fd, args.endpoint, args.family, args.expires_at)
    except Exception:
        # The parent presents a redacted generic startup failure; never print child diagnostics that could contain tokens.
        return 1


if __name__ == "__main__":  # pragma: no cover - exercised by BrokerManager subprocess tests.
    raise SystemExit(_main())
