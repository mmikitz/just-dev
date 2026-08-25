from __future__ import annotations

import base64
import os
import signal
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from just_dev.broker import MAX_TTL_SECONDS, BrokerClient, BrokerManager, KeePassProfile, validate_profile
from just_dev.errors import AuthenticationError, BrokerError, ConfigurationError


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
