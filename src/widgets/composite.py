"""Composite widget builder for combining multiple widgets."""

import re
import base64
from ..themes import THEMES
from ..utils import escape


def compose_widget(
    widgets: dict[str, str],
    enabled: list[str],
    theme_name: str = "dark",
    username: str = "",
    avatar_b64: str = "",
) -> str:
    """
    Takes rendered SVG strings for each widget type and composes them
    into a single unified profile widget.
    """
    t = THEMES[theme_name]
    total_w = 420
    header_h = 60
    padding = 20
    gap = 16

    # Parse each widget's height from its SVG
    parts = []
    for key in enabled:
        if key in widgets and widgets[key]:
            svg = widgets[key]
            hm = re.search(r'height="(\d+)"', svg)
            h = int(hm.group(1)) if hm else 160
            parts.append((key, svg, h))

    content_h = sum(h for _, _, h in parts) + gap * max(len(parts) - 1, 0)
    total_h = header_h + content_h + padding * 2 + 10

    # Header
    avatar_svg = ""
    if avatar_b64:
        avatar_svg = f'''
    <defs><clipPath id="mainAvatarClip"><circle cx="30" cy="30" r="16"/></clipPath></defs>
    <image x="14" y="14" width="32" height="32" href="data:image/png;base64,{avatar_b64}" clip-path="url(#mainAvatarClip)"/>'''
    else:
        avatar_svg = f'<circle cx="30" cy="30" r="16" fill="{t["accent"]}" opacity="0.3"/>'

    header = f'''
    {avatar_svg}
    <text x="54" y="38" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
          font-size="16" font-weight="700" fill="{t["text"]}">{escape(username or "Developer")}</text>
    <line x1="{padding}" y1="{header_h}" x2="{total_w - padding}" y2="{header_h}"
          stroke="{t["card_border"]}" stroke-width="0.5"/>'''

    # Stack widgets via base64 data URI embedding
    y_offset = header_h + padding
    embedded = ""
    for key, svg, h in parts:
        svg_b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        embedded += f'''
    <image x="{padding}" y="{y_offset}" width="380" height="{h}"
           href="data:image/svg+xml;base64,{svg_b64}"/>'''
        y_offset += h + gap

    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     width="{total_w}" height="{total_h}" viewBox="0 0 {total_w} {total_h}">
  <rect width="{total_w}" height="{total_h}" rx="16" fill="{t["bg"]}"/>
  <rect x="0.5" y="0.5" width="{total_w-1}" height="{total_h-1}" rx="16"
        fill="none" stroke="{t["card_border"]}" stroke-width="1"/>
  {header}
  {embedded}
  <text x="{total_w // 2}" y="{total_h - 8}" text-anchor="middle"
        font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
        font-size="9" fill="{t["text_secondary"]}" opacity="0.5">Generated with ♥</text>
</svg>'''
