"""Composite widget builder for combining multiple widgets."""

import re
from ..themes import THEMES
from ..utils import escape


def _extract_inner(svg: str, widget_key: str) -> tuple[str, int]:
    """Extract the inner content from a widget SVG and rewrite IDs to be unique.

    Returns (inner_svg_content, height).
    """
    # Parse height
    hm = re.search(r'height="(\d+)"', svg)
    h = int(hm.group(1)) if hm else 160

    # Rewrite IDs to avoid conflicts: shadow, avatarClip, areaGrad, etc.
    # Prefix all id="..." and url(#...) and href="#..." references
    prefix = f"{widget_key}_"

    # Find all IDs in the SVG
    ids = re.findall(r'id="([^"]+)"', svg)
    inner = svg
    for old_id in ids:
        new_id = f"{prefix}{old_id}"
        inner = inner.replace(f'id="{old_id}"', f'id="{new_id}"')
        inner = inner.replace(f'url(#{old_id})', f'url(#{new_id})')
        inner = inner.replace(f'href="#{old_id}"', f'href="#{new_id}"')

    # Strip the outer <svg> and </svg> tags to get just the content
    inner = re.sub(r'<svg[^>]*>', '', inner, count=1)
    inner = re.sub(r'</svg>\s*$', '', inner)

    return inner, h


def compose_widget(
    widgets: dict[str, str],
    enabled: list[str],
    theme_name: str = "dark",
    username: str = "",
    avatar_b64: str = "",
) -> str:
    """
    Takes rendered SVG strings for each widget type and composes them
    into a single unified profile widget by inlining widget SVGs directly.
    """
    t = THEMES[theme_name]
    total_w = 420
    header_h = 60
    padding = 20
    gap = 16

    # Extract inner content from each widget SVG
    parts = []
    for key in enabled:
        if key in widgets and widgets[key]:
            inner, h = _extract_inner(widgets[key], key)
            parts.append((key, inner, h))

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

    # Inline widgets using <svg> sub-documents positioned with x/y
    y_offset = header_h + padding
    embedded = ""
    for key, inner, h in parts:
        embedded += f'''
    <svg x="{padding}" y="{y_offset}" width="380" height="{h}" viewBox="0 0 380 {h}">
      {inner}
    </svg>'''
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
        font-size="9" fill="{t["text_secondary"]}" opacity="0.5">Generated with gh-stats</text>
</svg>'''
