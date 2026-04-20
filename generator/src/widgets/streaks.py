"""Streaks widget rendering."""

from datetime import date
from ..models import StreakData
from ..themes import THEMES
from ..utils import escape, card_wrapper, safe_color


def _fmt_day(d: date, include_year: bool) -> str:
    # %-d strips leading zero (POSIX-only; the service runs in a Linux container).
    return d.strftime("%b %-d, %Y") if include_year else d.strftime("%b %-d")


def _fmt_current(start_iso: str, today_iso: str) -> str:
    """Caption for the current-streak date, e.g. 'Apr 8 – Today' or
    'Apr 8, 2025 – Today' when the streak spans years."""
    if not start_iso:
        return ""
    try:
        s = date.fromisoformat(start_iso)
        t = date.fromisoformat(today_iso) if today_iso else date.today()
    except ValueError:
        return ""
    return f"{_fmt_day(s, s.year != t.year)} – Today"


def _fmt_longest(start_iso: str, end_iso: str) -> str:
    """Caption for the longest-streak date range. Keeps the year on the end date;
    adds a year to the start date only when start/end straddle years."""
    try:
        s = date.fromisoformat(start_iso) if start_iso else None
        e = date.fromisoformat(end_iso) if end_iso else None
    except ValueError:
        return ""
    if s and e:
        if s.year == e.year:
            return f"{_fmt_day(s, False)} – {_fmt_day(e, True)}"
        return f"{_fmt_day(s, True)} – {_fmt_day(e, True)}"
    if e:
        return _fmt_day(e, True)
    if s:
        return _fmt_day(s, True)
    return ""


def render_streaks_widget(
    data: StreakData,
    theme_name: str = "dark",
    settings: dict | None = None,
) -> str:
    """Render the streaks widget.

    Settings:
        color (str): Hex color for the current-streak number and progress bar
            fill (default theme accent).
    """
    t = THEMES[theme_name]
    s = settings or {}
    current_color = safe_color(s.get("color"), t["accent"])
    max_color = t["text"]

    width, height = 380, 170

    # Inner content is translated 36px down by card_wrapper's title strip, so
    # every y below is measured from that inner origin.
    left_x = 105
    right_x = 275
    divider_x = 190
    bar_x = 50
    bar_w = 280

    fraction = (data.current / data.max) if data.max > 0 else 0.0
    fraction = max(0.0, min(1.0, fraction))
    fill_w = round(bar_w * fraction, 2)

    current_caption = _fmt_current(data.current_start, data.last_active_date) if data.current > 0 else ""
    longest_caption = _fmt_longest(data.max_start, data.max_end)

    # End-cap dot on the progress fill — hidden at 0% so it doesn't float
    # detached at the bar start when the user has no current streak.
    end_dot = ""
    if fill_w > 0:
        end_dot = (
            f'<circle cx="{bar_x + fill_w:.2f}" cy="94.5" r="3.5" '
            f'fill="{current_color}"/>'
        )

    inner = f'''
    <text x="{left_x}" y="22" text-anchor="middle"
          font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="10" font-weight="600" letter-spacing="1.4"
          fill="{t["text_secondary"]}">CURRENT</text>
    <text x="{left_x}" y="66" text-anchor="middle"
          font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="40" font-weight="800" fill="{current_color}">{data.current}</text>

    <text x="{right_x}" y="22" text-anchor="middle"
          font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="10" font-weight="600" letter-spacing="1.4"
          fill="{t["text_secondary"]}">LONGEST</text>
    <text x="{right_x}" y="66" text-anchor="middle"
          font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="40" font-weight="800" fill="{max_color}">{data.max}</text>

    <line x1="{divider_x}" y1="10" x2="{divider_x}" y2="76"
          stroke="{t["card_border"]}" stroke-width="1"/>

    <rect x="{bar_x}" y="92" width="{bar_w}" height="5" rx="2.5" fill="{t["grid"]}"/>
    <rect x="{bar_x}" y="92" width="{fill_w}" height="5" rx="2.5" fill="{current_color}"/>
    {end_dot}

    <text x="{bar_x}" y="116"
          font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="10" fill="{t["text_secondary"]}">{escape(current_caption)}</text>
    <text x="{bar_x + bar_w}" y="116" text-anchor="end"
          font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="10" fill="{t["text_secondary"]}">{escape(longest_caption)}</text>'''

    return card_wrapper(inner, width, height, t, "Streaks")
