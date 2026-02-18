"""SVG helper functions and utilities."""


def escape(text: str) -> str:
    """Escape special characters for SVG text."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def card_wrapper(inner_svg: str, width: int, height: int, theme: dict, title: str = "") -> str:
    """Wraps content in a styled card with rounded corners and border."""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none">
  <defs>
    <filter id="shadow" x="-2%" y="-2%" width="104%" height="104%">
      <feDropShadow dx="0" dy="1" stdDeviation="2" flood-color="#000" flood-opacity="0.15"/>
    </filter>
    <clipPath id="avatarClip"><circle cx="0" cy="0" r="18"/></clipPath>
  </defs>
  <rect x="1" y="1" width="{width-2}" height="{height-2}" rx="10" ry="10"
        fill="{theme["card_bg"]}" stroke="{theme["card_border"]}" stroke-width="1" filter="url(#shadow)"/>
  {f'<text x="20" y="30" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Noto Sans,Helvetica,Arial,sans-serif" font-size="11" font-weight="600" fill="{theme["text_secondary"]}" letter-spacing="0.8" opacity="0.7">{escape(title.upper())}</text>' if title else ''}
  <g transform="translate(0, {36 if title else 0})">
    {inner_svg}
  </g>
</svg>'''


def icon_svg(kind: str, color: str) -> str:
    """Returns SVG for stat icons (14x14)."""
    icons = {
        "commits": f'<circle cx="7" cy="7" r="3" fill="none" stroke="{color}" stroke-width="1.4"/><circle cx="7" cy="7" r="1" fill="{color}"/><line x1="7" y1="10" x2="7" y2="14" stroke="{color}" stroke-width="1.4"/><line x1="7" y1="0" x2="7" y2="4" stroke="{color}" stroke-width="1.4"/>',
        "prs": f'<circle cx="4" cy="4" r="2" fill="none" stroke="{color}" stroke-width="1.2"/><circle cx="10" cy="10" r="2" fill="none" stroke="{color}" stroke-width="1.2"/><path d="M4 6v4c0 1.1.9 2 2 2h2" fill="none" stroke="{color}" stroke-width="1.2"/>',
        "stars": f'<path d="M7 1l1.8 3.6 4 .6-2.9 2.8.7 4L7 10.2 3.4 12l.7-4L1.2 5.2l4-.6z" fill="{color}" opacity="0.85"/>',
        "repos": f'<rect x="2" y="1" width="10" height="12" rx="1.5" fill="none" stroke="{color}" stroke-width="1.2"/><line x1="5" y1="4" x2="9" y2="4" stroke="{color}" stroke-width="1"/><line x1="5" y1="6.5" x2="9" y2="6.5" stroke="{color}" stroke-width="1"/><line x1="5" y1="9" x2="7" y2="9" stroke="{color}" stroke-width="1"/>',
        "followers": f'<circle cx="5" cy="4" r="2.5" fill="none" stroke="{color}" stroke-width="1.2"/><path d="M0.5 12c0-2.5 2-4 4.5-4s4.5 1.5 4.5 4" fill="none" stroke="{color}" stroke-width="1.2"/><circle cx="11" cy="3.5" r="1.8" fill="none" stroke="{color}" stroke-width="1"/><path d="M10 7.5c1.5 0 3.5 1 3.5 3" fill="none" stroke="{color}" stroke-width="1"/>',
    }
    return f'<g>{icons.get(kind, "")}</g>'
