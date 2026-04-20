"""Streaks widget rendering."""

from datetime import date
from ..models import StreakData
from ..themes import THEMES
from ..utils import escape, card_wrapper


_FLAME_SVG = (
    '<path d="M12 2c1 4 5 5 5 10a5 5 0 1 1-10 0c0-2 1-3 2-4 0 1 1 2 2 2 '
    '-1-2 0-5 1-8z" fill="{color}" opacity="0.95"/>'
)

_TROPHY_SVG = (
    '<path d="M6 3h12v3a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V3z" fill="none" '
    'stroke="{color}" stroke-width="1.6"/>'
    '<path d="M4 4h2v2a2 2 0 0 1-2 2H3V5a1 1 0 0 1 1-1zM20 4h-2v2a2 2 0 0 0 2 '
    '2h1V5a1 1 0 0 0-1-1z" fill="none" stroke="{color}" stroke-width="1.4"/>'
    '<rect x="9" y="11" width="6" height="3" fill="{color}"/>'
    '<rect x="7" y="14" width="10" height="2" rx="0.5" fill="{color}"/>'
)


def _fmt_date(iso: str) -> str:
    if not iso:
        return ""
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return ""
    return d.strftime("%b %d, %Y")


def _fmt_range(start: str, end: str) -> str:
    s = _fmt_date(start)
    e = _fmt_date(end)
    if s and e:
        return f"{s} – {e}"
    return s or e


def render_streaks_widget(
    data: StreakData,
    theme_name: str = "dark",
    settings: dict | None = None,
) -> str:
    """Render the streaks widget.

    Settings:
        show_dates (bool): Show date captions below each number. Default True.
    """
    t = THEMES[theme_name]
    s = settings or {}
    show_dates = bool(s.get("show_dates", True))

    width = 380
    height = 170
    col_w = width / 2

    current_color = t["accent"]
    max_color = t.get("text", "#e6e6e6")

    current_sub = _fmt_date(data.current_start) if data.current_start else "—"
    max_sub = _fmt_range(data.max_start, data.max_end) if (data.max_start or data.max_end) else ""

    date_lines = ""
    if show_dates:
        date_lines = f'''
    <text x="{col_w / 2}" y="130" text-anchor="middle"
          font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="9" fill="{t["text_secondary"]}">{escape("since " + current_sub) if data.current > 0 else ""}</text>
    <text x="{col_w + col_w / 2}" y="130" text-anchor="middle"
          font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="9" fill="{t["text_secondary"]}">{escape(max_sub)}</text>'''

    inner = f'''
    <g transform="translate({col_w / 2 - 12}, 14)">{_FLAME_SVG.format(color=current_color)}</g>
    <text x="{col_w / 2}" y="78" text-anchor="middle"
          font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="40" font-weight="800" fill="{current_color}">{data.current}</text>
    <text x="{col_w / 2}" y="108" text-anchor="middle"
          font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="11" fill="{t["text_secondary"]}" letter-spacing="0.5">Current Streak</text>

    <line x1="{col_w}" y1="24" x2="{col_w}" y2="{height - 24 - 36}" stroke="{t["grid"]}" stroke-width="1"/>

    <g transform="translate({col_w + col_w / 2 - 12}, 14)">{_TROPHY_SVG.format(color=max_color)}</g>
    <text x="{col_w + col_w / 2}" y="78" text-anchor="middle"
          font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="40" font-weight="800" fill="{max_color}">{data.max}</text>
    <text x="{col_w + col_w / 2}" y="108" text-anchor="middle"
          font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="11" fill="{t["text_secondary"]}" letter-spacing="0.5">Longest Streak</text>
    {date_lines}'''

    return card_wrapper(inner, width, height, t, "")
