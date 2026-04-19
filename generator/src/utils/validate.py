"""Input validation helpers shared across API, worker, and widget renderers.

These sit at the trust boundary between user input and anything that flows
into (a) outbound URLs to GitHub, (b) SVG markup, or (c) persisted settings.
Anything that crosses that boundary must be validated here first.
"""
from __future__ import annotations

import re

# GitHub usernames: 1–39 chars, alphanumeric or single hyphens, cannot start/end
# with a hyphen and cannot have consecutive hyphens. This matches GitHub's own
# signup regex — anything outside it is not a real account and should not be
# forwarded to the fetcher or embedded in URLs / GraphQL.
_USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")

# CSS color accepted by the widget renderers: #rgb, #rrggbb, #rrggbbaa, or a
# short allow-list of named colors that we actually use in themes. Permissive
# parsers let an attacker smuggle quote chars into SVG attribute context.
_COLOR_HEX_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")
_COLOR_NAMES = {
    "transparent", "currentcolor", "none",
    "white", "black", "red", "green", "blue",
}

_MAX_SETTINGS_BYTES = 64 * 1024  # 64 KB — plenty for theme + achievements


def is_valid_username(name: str) -> bool:
    return isinstance(name, str) and bool(_USERNAME_RE.match(name))


def is_valid_color(value: str) -> bool:
    if not isinstance(value, str) or len(value) > 32:
        return False
    return bool(_COLOR_HEX_RE.match(value)) or value.lower() in _COLOR_NAMES


def safe_color(value, fallback: str) -> str:
    """Return `value` if it's a valid color string, else `fallback`."""
    return value if is_valid_color(value) else fallback


def validate_theme_name(name, allowed: set[str], fallback: str = "dark") -> str:
    """Return name if it's in `allowed`, else `fallback`. Prevents KeyError DoS
    on THEMES[name] when a user patches in an unknown theme."""
    if isinstance(name, str) and name in allowed:
        return name
    return fallback


def clip_text(value, max_len: int) -> str:
    """Coerce `value` to a string and truncate. Used for user-authored fields
    that flow into SVG text (title, subtitle, event_date)."""
    if value is None:
        return ""
    s = value if isinstance(value, str) else str(value)
    return s[:max_len]


def settings_size_ok(raw_json: str) -> bool:
    return len(raw_json.encode("utf-8")) <= _MAX_SETTINGS_BYTES
