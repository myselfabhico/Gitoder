"""Inline SVG icon set. 2px strokes, ink color with terracotta accents.

Every icon is drawn here as a 24x24 line icon — no emoji, no icon fonts,
no downloaded packs. Icons render crisply at any DPI through QSvgRenderer.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import theme

_SVGS: dict[str, str] = {
    # ---- feature icons -------------------------------------------------
    "create": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <path d='M3 7.5V18a1.5 1.5 0 0 0 1.5 1.5h15A1.5 1.5 0 0 0 21 18V9a1.5 1.5 0 0 0-1.5-1.5h-7L10 5H4.5A1.5 1.5 0 0 0 3 6.5v1z' stroke='{ink}' stroke-width='2' stroke-linejoin='round'/>
  <path d='M12 10.5v6M9 13.5h6' stroke='{accent}' stroke-width='2' stroke-linecap='round'/>
</svg>""",
    "delete": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <path d='M4 6.5h16' stroke='{ink}' stroke-width='2' stroke-linecap='round'/>
  <path d='M9.5 6.5V5a1.5 1.5 0 0 1 1.5-1.5h2A1.5 1.5 0 0 1 14.5 5v1.5' stroke='{ink}' stroke-width='2'/>
  <path d='M6 6.5l1 12a1.5 1.5 0 0 0 1.5 1.4h7a1.5 1.5 0 0 0 1.5-1.4l1-12' stroke='{ink}' stroke-width='2' stroke-linejoin='round'/>
  <path d='M10 10.5v6M14 10.5v6' stroke='{accent}' stroke-width='2' stroke-linecap='round'/>
</svg>""",
    "update": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <path d='M3 17.5V19a1.5 1.5 0 0 0 1.5 1.5h15A1.5 1.5 0 0 0 21 19v-8a1.5 1.5 0 0 0-1.5-1.5h-7L10 7H4.5A1.5 1.5 0 0 0 3 8.5v2z' stroke='{ink}' stroke-width='2' stroke-linejoin='round'/>
  <path d='M14.5 2.5a5.5 5.5 0 0 1 5.3 4M19.9 3.4l-.1 3.1-3.1-.1' stroke='{accent}' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/>
</svg>""",
    "download": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <path d='M12 3.5V13M8.5 9.5L12 13l3.5-3.5' stroke='{accent}' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/>
  <path d='M4 14.5V19a1.5 1.5 0 0 0 1.5 1.5h13A1.5 1.5 0 0 0 20 19v-4.5' stroke='{ink}' stroke-width='2' stroke-linecap='round'/>
</svg>""",
    # ---- utility icons -------------------------------------------------
    "back": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <path d='M14.5 5.5L8 12l6.5 6.5' stroke='{ink}' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/>
</svg>""",
    "check": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <path d='M5 12.5l4.5 4.5L19 7.5' stroke='{ink}' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/>
</svg>""",
    "warning": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <path d='M12 4L2.8 19.5h18.4L12 4z' stroke='{ink}' stroke-width='2' stroke-linejoin='round'/>
  <path d='M12 10v4.5' stroke='{accent}' stroke-width='2' stroke-linecap='round'/>
  <circle cx='12' cy='17.2' r='1.1' fill='{accent}'/>
</svg>""",
    "error": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <circle cx='12' cy='12' r='8.5' stroke='{ink}' stroke-width='2'/>
  <path d='M9 9l6 6M15 9l-6 6' stroke='{accent}' stroke-width='2' stroke-linecap='round'/>
</svg>""",
    "info": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <circle cx='12' cy='12' r='8.5' stroke='{ink}' stroke-width='2'/>
  <path d='M12 11v5.5' stroke='{accent}' stroke-width='2' stroke-linecap='round'/>
  <circle cx='12' cy='7.8' r='1.1' fill='{accent}'/>
</svg>""",
    "folder": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <path d='M3 7.5V18a1.5 1.5 0 0 0 1.5 1.5h15A1.5 1.5 0 0 0 21 18V9a1.5 1.5 0 0 0-1.5-1.5h-7L10 5H4.5A1.5 1.5 0 0 0 3 6.5v1z' stroke='{ink}' stroke-width='2' stroke-linejoin='round'/>
</svg>""",
    "lock": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <rect x='5' y='10.5' width='14' height='9' rx='1.5' stroke='{ink}' stroke-width='2'/>
  <path d='M8 10.5V8a4 4 0 0 1 8 0v2.5' stroke='{ink}' stroke-width='2'/>
  <circle cx='12' cy='15' r='1.2' fill='{accent}'/>
</svg>""",
    "globe": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <circle cx='12' cy='12' r='8.5' stroke='{ink}' stroke-width='2'/>
  <path d='M3.5 12h17M12 3.5c2.5 2.3 3.8 5.2 3.8 8.5s-1.3 6.2-3.8 8.5c-2.5-2.3-3.8-5.2-3.8-8.5s1.3-6.2 3.8-8.5z' stroke='{ink}' stroke-width='2'/>
</svg>""",
    "key": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <circle cx='8' cy='14' r='4.5' stroke='{ink}' stroke-width='2'/>
  <path d='M11.5 10.5L19 3M15.5 6.5l2.5 2.5M13 9l2 2' stroke='{accent}' stroke-width='2' stroke-linecap='round'/>
</svg>""",
    "close": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <path d='M6 6l12 12M18 6L6 18' stroke='{ink}' stroke-width='2' stroke-linecap='round'/>
</svg>""",
    "external": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <path d='M13 5h6v6' stroke='{accent}' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/>
  <path d='M19 5l-8.5 8.5' stroke='{accent}' stroke-width='2' stroke-linecap='round'/>
  <path d='M10 6H6.5A1.5 1.5 0 0 0 5 7.5v10A1.5 1.5 0 0 0 6.5 19h10a1.5 1.5 0 0 0 1.5-1.5V14' stroke='{ink}' stroke-width='2' stroke-linecap='round'/>
</svg>""",
    "refresh": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <path d='M19.5 12a7.5 7.5 0 1 1-2.2-5.3L19.5 8.9' stroke='{ink}' stroke-width='2' stroke-linecap='round'/>
  <path d='M19.8 4.5v4.4h-4.4' stroke='{accent}' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/>
</svg>""",
    "copy": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <rect x='8.5' y='8.5' width='11' height='11' rx='1.5' stroke='{ink}' stroke-width='2'/>
  <path d='M5.5 14.5h-.2A1.3 1.3 0 0 1 4 13.2V5.3A1.3 1.3 0 0 1 5.3 4h7.9a1.3 1.3 0 0 1 1.3 1.3v.2' stroke='{accent}' stroke-width='2' stroke-linecap='round'/>
</svg>""",
    "eye": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <path d='M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z' stroke='{ink}' stroke-width='2' stroke-linejoin='round'/>
  <circle cx='12' cy='12' r='3' stroke='{accent}' stroke-width='2'/>
</svg>""",
    "eye-off": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <path d='M4 4l16 16' stroke='{accent}' stroke-width='2' stroke-linecap='round'/>
  <path d='M9.9 5.9A9.6 9.6 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-3.3 4M6 8a16.6 16.6 0 0 0-3.5 4S6 18.5 12 18.5c1 0 2-.2 2.9-.5' stroke='{ink}' stroke-width='2' stroke-linecap='round'/>
</svg>""",
    "search": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <circle cx='10.5' cy='10.5' r='6.5' stroke='{ink}' stroke-width='2'/>
  <path d='M15.5 15.5L20.5 20.5' stroke='{accent}' stroke-width='2' stroke-linecap='round'/>
</svg>""",
    "dot": """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none'>
  <circle cx='12' cy='12' r='4' fill='{accent}'/>
</svg>""",
}

_cache: dict[tuple[str, str, int], QIcon] = {}


def svg_bytes(name: str, *, ink: str | None = None, accent: str | None = None) -> QByteArray:
    """Raw SVG for one icon, recolored from palette tokens."""
    body = _SVGS[name]
    body = body.replace("{ink}", ink or theme.INK)
    body = body.replace("{accent}", accent or theme.PRIMARY)
    return QByteArray(body.encode("utf-8"))


def pixmap(name: str, size: int = 24, *, ink: str | None = None,
           accent: str | None = None, dpr: float = 2.0) -> QPixmap:
    """Render one icon to a pixmap at devicePixelRatio for crisp edges."""
    renderer = QSvgRenderer(svg_bytes(name, ink=ink, accent=accent))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    renderer.render(p, QRectF(0, 0, size * dpr, size * dpr))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, size: int = 24, *, ink: str | None = None,
         accent: str | None = None) -> QIcon:
    """QIcon for buttons, labels, window chrome."""
    key = (name, ink or "", accent or "")
    if key not in _cache:
        _cache[key] = icon_uncached(name, size, ink=ink, accent=accent)
    return _cache[key]


def icon_uncached(name: str, size: int = 24, *, ink: str | None = None,
                  accent: str | None = None) -> QIcon:
    from PySide6.QtGui import QGuiApplication
    dpr = QGuiApplication.primaryScreen().devicePixelRatio() if QGuiApplication.primaryScreen() else 2.0
    ic = QIcon()
    for s in (16, 24, 32, 48):
        ic.addPixmap(pixmap(name, s, ink=ink, accent=accent, dpr=dpr))
    return ic


# ---------------------------------------------------------------- app icon

APP_ICON_SVG = """\
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
  <rect x='2' y='2' width='60' height='60' rx='14' fill='{bg}'/>
  <rect x='2' y='2' width='60' height='60' rx='14' fill='none' stroke='{ink}' stroke-width='3'/>
  <path d='M44 22a14 14 0 1 0 2 12' fill='none' stroke='{accent}' stroke-width='7' stroke-linecap='round'/>
  <path d='M46 12v12H34' fill='none' stroke='{accent}' stroke-width='7' stroke-linecap='round' stroke-linejoin='round'/>
</svg>"""


def app_icon_pixmap(size: int = 256) -> QPixmap:
    """Warm 'G' glyph in terracotta on charcoal — window/taskbar/exe icon."""
    body = (APP_ICON_SVG
            .replace("{bg}", theme.INK)
            .replace("{ink}", theme.INK)
            .replace("{accent}", theme.PRIMARY))
    renderer = QSvgRenderer(QByteArray(body.encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    renderer.render(p, QRectF(0, 0, size, size))
    p.end()
    return pm


def app_icon() -> QIcon:
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(app_icon_pixmap(s))
    return ic
