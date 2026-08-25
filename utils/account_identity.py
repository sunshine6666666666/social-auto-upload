"""Small, secret-free account identity contract shared by platform uploaders."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


_SECRET_KEY_FRAGMENTS = (
    "cookie",
    "token",
    "authorization",
    "csrf",
    "password",
    "secret",
    "api_key",
    "apikey",
    "sessionid",
)


def _observed_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class AccountIdentity:
    platform: str
    logged_in: bool
    stable_id: str | None
    display_name: str | None
    handle: str | None = None
    profile_url: str | None = None
    browser_name: str | None = None
    cdp_port: int | None = None
    observed_at: str = field(default_factory=_observed_at)
    extra: dict[str, str | int | bool | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.platform:
            raise ValueError("identity platform is required")
        if not self.observed_at.endswith("Z"):
            raise ValueError("identity observed_at must be UTC")
        for key, value in self.extra.items():
            normalized_key = key.lower().replace("-", "_")
            if any(fragment in normalized_key for fragment in _SECRET_KEY_FRAGMENTS):
                raise ValueError("identity extra contains a secret field")
            if not isinstance(value, (str, int, bool)) and value is not None:
                raise ValueError("identity extra values must be JSON scalar values")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        json.dumps(payload)
        return payload


def require_publish_identity(identity: AccountIdentity) -> AccountIdentity:
    if not identity.logged_in or not identity.stable_id or not str(identity.stable_id).strip():
        raise RuntimeError(f"blocked publish identity for {identity.platform}: logged_in/stable_id missing")
    return identity


def assert_same_publish_identity(expected: AccountIdentity, observed: AccountIdentity) -> None:
    require_publish_identity(expected)
    require_publish_identity(observed)
    if expected.platform != observed.platform:
        raise RuntimeError(f"blocked publish identity: platform changed for {expected.platform}")
    if expected.stable_id != observed.stable_id:
        raise RuntimeError(f"blocked publish identity: stable_id changed for {expected.platform}")


def identity_matches(identity: AccountIdentity, selector: str) -> bool:
    """Match only one exact stable ID, handle, or display name."""
    needle = selector.strip() if isinstance(selector, str) else ""
    if not needle:
        raise ValueError("account selector must not be empty")
    if identity.stable_id and identity.stable_id == needle:
        return True
    handle = identity.handle or ""
    handle = handle[1:] if handle.startswith("@") else handle
    candidate = needle[1:] if needle.startswith("@") else needle
    if handle and handle.casefold() == candidate.casefold():
        return True
    return bool(identity.display_name and identity.display_name.strip().casefold() == needle.casefold())


def observation_status(identity: AccountIdentity) -> str:
    return "logged_in" if identity.logged_in and identity.stable_id else "interaction_required"
