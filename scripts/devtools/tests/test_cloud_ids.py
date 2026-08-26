from __future__ import annotations

import json
import stat

import pytest

from just_dev.atlassian import resolve_site_cloud_id
from just_dev.broker import CloudIdCache, KeePassProfile, ProfileStore
from just_dev.errors import ConfigurationError, NetworkError

SITE = "https://example.atlassian.net"
CLOUD_ID = "00000000-0000-4000-8000-000000000111"


def _store_with_profile(tmp_path) -> tuple[ProfileStore, object]:
    database = tmp_path / "credentials.kdbx"
    database.touch()
    store = ProfileStore(tmp_path / "profiles")
    store.save("default", KeePassProfile(database=str(database), entries={}))
    return store, database


def test_cloud_id_cache_persists_normalized_site_mapping_with_private_permissions(tmp_path) -> None:
    store, _ = _store_with_profile(tmp_path)
    calls: list[str] = []
    cache = CloudIdCache(store, resolver=lambda site: calls.append(site) or CLOUD_ID)

    first = cache.resolve("https://EXAMPLE.atlassian.net/", profile="default")
    second = cache.resolve(SITE, profile="default")

    assert first == CLOUD_ID
    assert second == CLOUD_ID
    assert calls == [SITE]
    profile = store.load("default")
    assert profile.version == 2
    assert profile.cloud_ids == {SITE: CLOUD_ID}
    if stat.S_ISREG(store.path_for("default").stat().st_mode):
        assert stat.S_IMODE(store.path_for("default").stat().st_mode) == 0o600


def test_configure_style_refresh_keeps_a_good_cached_mapping_when_metadata_fails(tmp_path) -> None:
    store, _ = _store_with_profile(tmp_path)
    store.save(
        "default",
        KeePassProfile(database=store.load("default").database, cloud_ids={SITE: CLOUD_ID}),
    )
    warnings: list[str] = []

    def failing_resolver(site: str) -> str:
        raise NetworkError(f"offline for {site}")

    value = CloudIdCache(store, resolver=failing_resolver).resolve(
        SITE,
        profile="default",
        refresh=True,
        required=False,
        warning_sink=warnings.append,
    )

    assert value == CLOUD_ID
    assert store.load("default").cloud_ids == {SITE: CLOUD_ID}
    assert warnings and "keeping the existing mapping" in warnings[0]


def test_changed_site_resolves_and_an_unresolvable_new_site_has_recovery_guidance(tmp_path) -> None:
    store, _ = _store_with_profile(tmp_path)
    old_site = "https://old-site.atlassian.net"
    new_site = "https://new-site.atlassian.net"
    new_cloud_id = "00000000-0000-4000-8000-000000000222"
    store.save(
        "default",
        KeePassProfile(database=store.load("default").database, cloud_ids={old_site: CLOUD_ID}),
    )
    cache = CloudIdCache(store, resolver=lambda site: new_cloud_id if site == new_site else CLOUD_ID)

    assert cache.resolve(new_site, profile="default") == new_cloud_id
    assert store.load("default").cloud_ids == {old_site: CLOUD_ID, new_site: new_cloud_id}

    missing_site = "https://missing-site.atlassian.net"
    with pytest.raises(ConfigurationError, match="Run `just configure-auth`"):
        CloudIdCache(store, resolver=lambda site: (_ for _ in ()).throw(NetworkError("offline"))).resolve(
            missing_site, profile="default"
        )


def test_existing_version_one_profile_migrates_without_losing_its_auth_values(tmp_path) -> None:
    database = tmp_path / "credentials.kdbx"
    database.touch()
    store = ProfileStore(tmp_path / "profiles")
    store.path_for("legacy").write_text(
        json.dumps(
            {
                "version": 1,
                "database": str(database),
                "keyfile": None,
                "entries": {"jira": "00000000-0000-4000-8000-000000000001"},
            }
        ),
        encoding="utf-8",
    )

    profile = store.load("legacy")

    assert profile.version == 2
    assert profile.entries == {"jira": "00000000-0000-4000-8000-000000000001"}
    assert profile.cloud_ids == {}
    assert json.loads(store.path_for("legacy").read_text(encoding="utf-8"))["version"] == 2


def test_tenant_metadata_resolution_uses_only_the_canonical_site_endpoint() -> None:
    captured = {}

    class Response:
        def read(self) -> bytes:
            return b'{"cloudId":"00000000-0000-4000-8000-000000000333"}'

        def close(self) -> None:
            pass

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["authorization"] = request.get_header("Authorization")
        return Response()

    cloud_id = resolve_site_cloud_id("https://EXAMPLE.atlassian.net/", opener=opener)

    assert cloud_id == "00000000-0000-4000-8000-000000000333"
    assert captured == {
        "url": "https://example.atlassian.net/_edge/tenant_info",
        "timeout": 10.0,
        "authorization": None,
    }
