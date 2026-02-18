"""Impact timeline widget rendering."""

from ..models import ImpactWeek
from ..themes import THEMES
from ..utils import card_wrapper


def render_impact_widget(weeks: list[ImpactWeek], theme_name: str = "dark", period: str = "6mo") -> str:
    """Renders the impact timeline chart widget."""
    t = THEMES[theme_name]
    if not weeks:
        return ""

    w, h = 380, 200
    chart_x, chart_y = 40, 8
    chart_w, chart_h = 316, 82

    max_commits = max((wk.commits for wk in weeks), default=1) or 1
    n = len(weeks)

    # Build area path
    points = []
    for i, wk in enumerate(weeks):
        px = chart_x + (i / max(n - 1, 1)) * chart_w
        py = chart_y + chart_h - (wk.commits / max_commits) * chart_h
        points.append((px, py))

    if not points:
        return ""

    # Smooth curve using cardinal spline
    path_d = f"M {points[0][0]:.1f} {points[0][1]:.1f}"
    for i in range(1, len(points)):
        cx = (points[i-1][0] + points[i][0]) / 2
        path_d += f" C {cx:.1f} {points[i-1][1]:.1f}, {cx:.1f} {points[i][1]:.1f}, {points[i][0]:.1f} {points[i][1]:.1f}"

    area_d = path_d + f" L {points[-1][0]:.1f} {chart_y + chart_h} L {points[0][0]:.1f} {chart_y + chart_h} Z"

    # Y-axis labels
    y_labels = ""
    for i in range(3):
        val = int(max_commits * (1 - i / 2))
        yy = chart_y + (i / 2) * chart_h
        y_labels += f'<text x="{chart_x - 6}" y="{yy + 4}" text-anchor="end" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="9" fill="{t["text_secondary"]}">{val}</text>'
        y_labels += f'<line x1="{chart_x}" y1="{yy}" x2="{chart_x + chart_w}" y2="{yy}" stroke="{t["grid"]}" stroke-width="0.5" stroke-dasharray="3,3"/>'

    # X-axis labels
    x_labels = ""
    label_indices = [0, n // 2, n - 1] if n > 2 else list(range(n))
    for idx in label_indices:
        if idx < len(weeks):
            px = chart_x + (idx / max(n - 1, 1)) * chart_w
            x_labels += f'<text x="{px:.1f}" y="{chart_y + chart_h + 14}" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="9" fill="{t["text_secondary"]}">{weeks[idx].week_start[:7]}</text>'

    # Summary
    total = sum(wk.commits for wk in weeks)
    summary_y = chart_y + chart_h + 46

    inner = f'''
    <defs>
      <linearGradient id="areaGrad" x1="0" y1="{chart_y}" x2="0" y2="{chart_y + chart_h}" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stop-color="{t["accent"]}" stop-opacity="0.35"/>
        <stop offset="100%" stop-color="{t["accent"]}" stop-opacity="0.02"/>
      </linearGradient>
    </defs>
    {y_labels}
    {x_labels}
    <path d="{area_d}" fill="url(#areaGrad)"/>
    <path d="{path_d}" fill="none" stroke="{t["accent"]}" stroke-width="2" stroke-linecap="round"/>
    <g transform="translate(20, {summary_y})">
      <text x="0" y="0" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="13" font-weight="700" fill="{t["text"]}">{total:,}</text>
      <text x="0" y="14" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
            font-size="9" fill="{t["text_secondary"]}">commits over {period}</text>
    </g>'''

    return card_wrapper(inner, w, h, t, "Impact Timeline")
