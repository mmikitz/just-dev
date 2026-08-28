from __future__ import annotations

import base64
import json
import os
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from types import ModuleType

import pytest

from just_dev.broker import (
    MAX_TTL_SECONDS,
    BrokerClient,
    BrokerManager,
    BrokerState,
    KeePassProfile,
    _error_payload,
    read_keepass_tokens,
    validate_profile,
)
from just_dev.errors import AuthenticationError, BrokerError, ConfigurationError, InputValidationError


def test_broker_unlock_status_bad_hmac_and_lock_leave_no_token_on_disk(tmp_path) -> None:
    manager = BrokerManager(runtime_directory=tmp_path / "runtime", state_directory=tmp_path / "state")
    tokens = {"jira": "jira-secret", "confluence": "conf-secret", "bitbucket": "bb-secret", "jenkins": "jenkins-secret"}
    try:
        status = manager.unlock(tokens, ttl_seconds=60)
        assert status.active is True
        assert manager.status().active is True
        state_text = manager.state_path("default").read_text(encoding="utf-8")
        assert all(token not in state_text for token in tokens.values())

        state = manager._load_state("default")
        assert state is not None
        bad_state = state.model_copy(update={"auth_key": base64.urlsafe_b64encode(b"x" * 32).decode("ascii")})
        with pytest.raises(BrokerError):
            BrokerClient(bad_state).request("status")
        assert manager.status().active is True
    finally:
        manager.lock()
    assert manager.status().active is False


def test_unlock_clamps_ttl_to_the_eight_hour_cap(tmp_path) -> None:
    # The broker child enforces its TTL against the real wall clock (broker.py's
    # _broker_child), so this must not fake BrokerManager's clock: a synthetic clock far from
    # "now" would make the child compute an already-elapsed timer and self-terminate instantly.
    manager = BrokerManager(runtime_directory=tmp_path / "runtime", state_directory=tmp_path / "state")
    tokens = {"jira": "jira", "confluence": "confluence", "bitbucket": "bitbucket", "jenkins": "jenkins"}
    before = time.time()
    try:
        status = manager.unlock(tokens, ttl_seconds=MAX_TTL_SECONDS * 100)
        after = time.time()
        assert status.expires_at is not None
        assert before + MAX_TTL_SECONDS <= status.expires_at.timestamp() <= after + MAX_TTL_SECONDS
    finally:
        manager.lock()


def test_status_and_client_recover_after_the_broker_process_is_killed(tmp_path) -> None:
    manager = BrokerManager(runtime_directory=tmp_path / "runtime", state_directory=tmp_path / "state")
    tokens = {"jira": "jira", "confluence": "confluence", "bitbucket": "bitbucket", "jenkins": "jenkins"}
    status = manager.unlock(tokens, ttl_seconds=60)
    assert status.active is True
    state = manager._load_state("default")
    assert state is not None

    os.kill(state.pid, signal.SIGKILL)

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and manager.status().active:
        time.sleep(0.05)

    assert manager.status().active is False
    with pytest.raises(AuthenticationError):
        manager.client()


def test_parallel_unlocks_reuse_one_broker(tmp_path) -> None:
    runtime = tmp_path / "runtime"
    state = tmp_path / "state"
    tokens = {"jira": "jira", "confluence": "confluence", "bitbucket": "bitbucket", "jenkins": "jenkins"}
    managers = [BrokerManager(runtime_directory=runtime, state_directory=state) for _ in range(2)]
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(lambda manager: manager.unlock(tokens, ttl_seconds=60), managers))
        assert all(status.active for status in statuses)
        assert statuses[0].pid == statuses[1].pid
    finally:
        managers[0].lock()


def test_profile_rejects_non_uuid_entries(tmp_path) -> None:
    database = tmp_path / "secrets.kdbx"
    database.touch()
    profile = KeePassProfile(
        database=str(database),
        entries={"jira": "not-a-uuid", "confluence": "not-a-uuid", "bitbucket": "not-a-uuid", "jenkins": "not-a-uuid"},
    )
    with pytest.raises(ConfigurationError, match="UUID"):
        validate_profile(profile)


def test_partial_profile_warns_for_missing_or_empty_entries_and_unlocks_available_tokens(tmp_path, monkeypatch) -> None:
    database = tmp_path / "secrets.kdbx"
    database.touch()
    jira_uuid = "00000000-0000-4000-8000-000000000001"

    class Entry:
        password = "jira-secret"

    class FakeKeePass:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def find_entries(self, uuid, first):
            assert first is True
            return Entry() if str(uuid) == jira_uuid else None

    module = ModuleType("pykeepass")
    module.PyKeePass = FakeKeePass
    monkeypatch.setitem(sys.modules, "pykeepass", module)
    profile = KeePassProfile(
        database=str(database),
        entries={"jira": jira_uuid, "confluence": ""},
    )
    warnings: list[str] = []

    tokens = read_keepass_tokens(profile, "master-password", warning_sink=warnings.append)

    assert tokens == {"jira": "jira-secret"}
    assert any("confluence" in warning for warning in warnings)
    assert any("bitbucket" in warning for warning in warnings)
    manager = BrokerManager(runtime_directory=tmp_path / "runtime", state_directory=tmp_path / "state")
    try:
        status = manager.unlock(tokens, ttl_seconds=60)
        assert status.active is True
    finally:
        manager.lock()


def test_lock_keeps_state_until_an_authenticated_broker_has_exited(tmp_path) -> None:
    manager = BrokerManager(runtime_directory=tmp_path / "runtime", state_directory=tmp_path / "state")
    try:
        status = manager.unlock({"jira": "jira-secret"}, ttl_seconds=60)
        assert status.active is True
        assert manager.state_path("default").is_file()

        locked = manager.lock()

        assert locked.active is False
        assert not manager.state_path("default").exists()
        assert manager.status().active is False
    finally:
        manager.lock()


def test_lock_retains_metadata_when_a_live_broker_cannot_be_authenticated(tmp_path) -> None:
    manager = BrokerManager(runtime_directory=tmp_path / "runtime", state_directory=tmp_path / "state")
    try:
        manager.unlock({"jira": "jira-secret"}, ttl_seconds=60)
        state = manager._load_state("default")
        assert state is not None
        corrupted = state.model_copy(update={"auth_key": base64.urlsafe_b64encode(b"x" * 32).decode("ascii")})
        manager._save_state("default", corrupted)

        with pytest.raises(BrokerError, match="metadata was retained"):
            manager.lock()

        assert manager.state_path("default").exists()
        manager._save_state("default", state)
    finally:
        manager.lock()


def test_error_payload_carries_a_devtools_errors_status_code_when_set() -> None:
    """R2b's 404 signal must survive the broker child's JSON-over-IPC serialization,
    or it would never reach a local-broker caller (only a CI one, which shares the
    process and never serializes at all)."""

    with_status = InputValidationError("Remote service rejected the request (404).")
    with_status.status_code = 404

    payload = _error_payload(with_status, {})

    assert payload == {
        "ok": False,
        "exit_code": 25,
        "message": "Remote service rejected the request (404).",
        "status_code": 404,
    }


def test_error_payload_omits_status_code_when_unset() -> None:
    payload = _error_payload(InputValidationError("Some other 4xx."), {})

    assert "status_code" not in payload


class _FakeIpcConnection:
    def __init__(self, response: bytes) -> None:
        self._response = response

    def send_bytes(self, data: bytes) -> None:
        del data

    def recv_bytes(self) -> bytes:
        return self._response

    def close(self) -> None:
        pass


def test_broker_client_request_reconstructs_the_status_code_from_the_ipc_response(monkeypatch) -> None:
    response = json.dumps(
        {
            "ok": False,
            "exit_code": 25,
            "message": "Remote service rejected the request (404).",
            "status_code": 404,
        }
    ).encode("utf-8")
    monkeypatch.setattr("just_dev.broker.Client", lambda *args, **kwargs: _FakeIpcConnection(response))
    state = BrokerState(
        endpoint="unused",
        family="AF_UNIX",
        auth_key=base64.urlsafe_b64encode(b"x" * 32).decode("ascii"),
        expires_at=datetime.now(UTC),
        platform="linux",
        pid=os.getpid(),
    )

    with pytest.raises(InputValidationError) as raised:
        BrokerClient(state).request("operation", operation="jira.read_issue", payload={})

    assert raised.value.status_code == 404


def test_broker_client_request_leaves_status_code_unset_when_the_response_omits_it(monkeypatch) -> None:
    response = json.dumps({"ok": False, "exit_code": 21, "message": "Remote service rejected credentials."}).encode(
        "utf-8"
    )
    monkeypatch.setattr("just_dev.broker.Client", lambda *args, **kwargs: _FakeIpcConnection(response))
    state = BrokerState(
        endpoint="unused",
        family="AF_UNIX",
        auth_key=base64.urlsafe_b64encode(b"x" * 32).decode("ascii"),
        expires_at=datetime.now(UTC),
        platform="linux",
        pid=os.getpid(),
    )

    with pytest.raises(AuthenticationError) as raised:
        BrokerClient(state).request("operation", operation="jira.read_issue", payload={})

    assert raised.value.status_code is None
