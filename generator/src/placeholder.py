"""Placeholder SVG renderer — three variants for unknown / rate-limited / not-found users.

Uses the same card wrapper + theme system as real widgets so they look consistent.
"""
from .themes.themes import THEMES
from .utils.svg_helpers import card_wrapper, escape

_MESSAGES = {
    "building":     ("Building @{u}'s widget\u2026", "This usually takes under a minute."),
    "rate_limited": ("Too many new users today",  "Try again tomorrow."),
    "not_found":    ("GitHub user @{u} doesn't exist", "Check the spelling of the username."),
}


def render(variant: str, username: str, theme: str = "dark") -> str:
    if variant not in _MESSAGES:
        raise ValueError(f"unknown placeholder variant: {variant}")
    title_tpl, subtitle = _MESSAGES[variant]
    title = title_tpl.format(u=username)
    palette = THEMES.get(theme, THEMES["dark"])

    inner = (
        f'<text x="24" y="56" font-family="-apple-system,Segoe UI,sans-serif" '
        f'font-size="18" font-weight="600" fill="{palette["text"]}">{escape(title)}</text>'
        f'<text x="24" y="82" font-family="-apple-system,Segoe UI,sans-serif" '
        f'font-size="13" fill="{palette["text_secondary"]}">{escape(subtitle)}</text>'
    )
    return card_wrapper(inner, width=400, height=120, theme=palette)
