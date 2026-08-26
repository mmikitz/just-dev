"""Validation and tenant-metadata lookup for Atlassian Cloud sites."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import UUID

from .errors import ConfigurationError, NetworkError

_SITE_HOST = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.atlassian\.net", re.IGNORECASE)
_TENANT_INFO_PATH = "/_edge/tenant_info"


def is_cloud_id(value: str) -> bool:
    """Return whether *value* is a UUID without changing its configured spelling."""

    try:
        UUID(value)
    except (TypeError, ValueError, AttributeError):
        return False
    return True


def normalize_site_url(value: str) -> str:
    """Return the one accepted form of an Atlassian Cloud site URL.

    Root-path spelling and host casing are normalized so a profile has one stable
    cache key for a site. API, proxy, product, and tenant-information URLs are
    deliberately not accepted as project configuration.
    """

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("must be a canonical https://<site>.atlassian.net URL") from exc
    host = parsed.hostname
    if (
        parsed.scheme != "https"
        or not host
        or not _SITE_HOST.fullmatch(host)
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("must be a canonical https://<site>.atlassian.net URL")
    return f"https://{host.lower()}"


def site_url_from_configured_cloud_id(value: str) -> str | None:
    """Return a normalized site URL when configuration uses one, otherwise None."""

    if is_cloud_id(value):
        return None
    return normalize_site_url(value)


def validate_cloud_id_or_site_url(value: str) -> str:
    """Validate the public ``atlassian.cloud_id`` input and normalize only URLs."""

    if is_cloud_id(value):
        return value
    return normalize_site_url(value)


def resolve_site_cloud_id(
    site_url: str,
    *,
    opener: Callable[..., Any] | None = None,
    timeout_seconds: float = 10.0,
) -> str:
    """Resolve an Atlassian Cloud ID through the site's public tenant metadata.

    The endpoint receives no credentials. Scoped API-token calls still go only
    through ``api.atlassian.com/ex/<product>/<cloud-id>`` after this lookup.
    """

    normalized_site = normalize_site_url(site_url)
    request = Request(
        f"{normalized_site}{_TENANT_INFO_PATH}",
        headers={"Accept": "application/json", "User-Agent": "just-dev/0.1"},
        method="GET",
    )
    try:
        response = (opener or urlopen)(request, timeout=timeout_seconds)
        try:
            raw = response.read()
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
    except HTTPError as exc:
        raise NetworkError(
            f"Could not resolve the Atlassian Cloud ID for {normalized_site}: tenant metadata returned HTTP {exc.code}."
        ) from exc
    except (URLError, OSError, TimeoutError) as exc:
        raise NetworkError(
            f"Could not resolve the Atlassian Cloud ID for {normalized_site}. Check network access and the site URL."
        ) from exc

    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Atlassian tenant metadata for {normalized_site} did not return valid JSON.") from exc
    cloud_id = decoded.get("cloudId") if isinstance(decoded, dict) else None
    if not isinstance(cloud_id, str) or not is_cloud_id(cloud_id):
        raise ConfigurationError(f"Atlassian tenant metadata for {normalized_site} did not contain a valid Cloud ID.")
    return str(UUID(cloud_id))
