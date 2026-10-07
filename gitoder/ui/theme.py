"""E-Sense design tokens. The ONLY place raw hex values may appear."""

from __future__ import annotations

import logging
import os

log = logging.getLogger("gitoder.theme")

# ---------------------------------------------------------------- palette
BG          = "#F5F2EB"   # Soft Warm Beige — window background (never white)
SURFACE     = "#F2F2F2"   # Gentle Gray — cards
SURFACE_2   = "#EDEAE4"   # Warm Alabaster — secondary panels, rows
LINE        = "#E7E8D1"   # Soft Oat Milk — dividers, card borders
INK         = "#2B3A42"   # Deep Charcoal Blue — text, shadows, outlines
INK_SOFT    = "#8D6959"   # Acorn Brown — warm secondary text
INK_DEEP    = "#556B2F"   # Muted Olive — organic headings, success
PRIMARY     = "#E29578"   # Soft Terracotta — primary buttons, key highlight
PRIMARY_2   = "#D3A790"   # Muted Coral Clay — hover / secondary buttons
CTA_SOFT    = "#FFE5B4"   # Soft Peach — welcome surface
HINT        = "#FFE9D8"   # Creamy Apricot — tips
ACCENT      = "#735DA5"   # Muted Amethyst — subheads, steps
NOTICE      = "#D3C5E5"   # Heather Violet — notices
LINK        = "#AB7044"   # Soft Copper — inline links
FOCUS       = "#C4BA9D"   # Pale Ochre — focus rings, input borders
SUCCESS     = "#8A9A86"   # Sage Green — success tint
TRACK       = "#A7BEAE"   # Frosted Seafoam — progress track
FILL_SUBTLE = "#BFC5B9"   # Pale Eucalyptus — subtle fills
STROKE      = "#E1C5B3"   # Vintage Sand — icon strokes, minimal borders
MUTED       = "#9F9A8A"   # Stone Khaki — muted labels, tag borders
DANGER      = "#B3412F"   # Soft Brick — ONLY delete/confirm + error text
DANGER_BG   = "#DCAEAF"   # approved list: tint behind destructive-failure text
WHITE       = "#F5F2EB"   # "paper white" is BG, never #FFFFFF
BLACK       = "#2B3A42"   # "ink black" is INK, never #000000

# --------------------------------------------------------------- typography
FONT_DISPLAY = "Syne"
FONT_BODY = "DM Sans"
FALLBACK_STACK = f"'{FONT_DISPLAY}', 'Helvetica Neue', Arial"  # documented fallback
FALLBACK_STACK_BODY = f"'{FONT_BODY}', 'Helvetica Neue', Arial"

DISPLAY_SIZE = 76          # homepage wordmark
TITLE_SIZE = 40            # page title
SECTION_SIZE = 24          # section heading
CARD_H_SIZE = 26           # card heading
BODY_SIZE = 16             # body copy
LABEL_SIZE = 12            # uppercase micro labels

# ------------------------------------------------------------------ shapes
RADIUS_MICRO = 3
RADIUS_SOFT = 14
RADIUS_PILL = 999
SIGNATURE_CORNERS = (0, 28, 0, 28)          # TL, TR, BR, BL — the signature move
SHADOW_OFFSET = 5                            # hard offset shadow: 5px 5px 0
SHADOW_OFFSET_HOVER = 7
SHADOW_COLOR = INK

# ----------------------------------------------------------------- spacing
SP = (4, 8, 12, 16, 24, 32, 48, 64, 96)

# --------------------------------------------------------------- contrast

def _srgb_to_lin(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(hex_color: str) -> float:
    h = hex_color.strip().lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _srgb_to_lin(r) + 0.7152 * _srgb_to_lin(g) + 0.0722 * _srgb_to_lin(b)


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.x contrast ratio between two hex colors."""
    l1 = _luminance(fg)
    l2 = _luminance(bg)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def assert_contrast(fg: str, bg: str, minimum: float = 4.5, label: str = "") -> None:
    """Assert WCAG contrast; runs only in debug mode."""
    if not os.environ.get("GITODER_DEBUG"):
        return
    ratio = contrast_ratio(fg, bg)
    if ratio < minimum:
        log.error("Contrast FAIL %s: %s on %s = %.2f:1 (< %.1f)", label, fg, bg, ratio, minimum)
        raise AssertionError(f"Contrast {ratio:.2f}:1 < {minimum}:1 for {label or (fg, bg)}")


# ------------------------------------------------------------------ QSS
# Micro-corner inputs, warm surfaces, no pure white anywhere.
APP_QSS = f"""
QLineEdit#microInput {{
    background: {SURFACE}; border: 1px solid {FOCUS}; border-radius: {RADIUS_MICRO}px;
    padding: 0 12px; color: {INK}; selection-background-color: {CTA_SOFT};
}}
QLineEdit#microInput:focus {{ border: 2px solid {FOCUS}; }}
QComboBox {{
    background: {SURFACE}; border: 1px solid {FOCUS}; border-radius: {RADIUS_MICRO}px;
    padding: 0 12px; color: {INK}; font-family: '{FONT_BODY}'; font-size: 15px;
}}
QComboBox:focus {{ border: 2px solid {FOCUS}; }}
QComboBox QAbstractItemView {{
    background: {SURFACE}; color: {INK}; border: 1px solid {LINE};
    selection-background-color: {CTA_SOFT}; selection-color: {INK};
    border-radius: {RADIUS_MICRO}px; outline: 0;
}}
QScrollBar:vertical {{ background: {BG}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {FOCUS}; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: {BG}; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {FOCUS}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QToolTip {{ background: {INK}; color: {BG}; border: 1px solid {BG}; padding: 4px 8px; }}
"""


def check_all_pairs() -> None:
    """Debug-mode assertions for every standard text/background pair."""
    assert_contrast(INK, BG, 4.5, "body on window")
    assert_contrast(INK, SURFACE, 4.5, "body on card")
    assert_contrast(INK, SURFACE_2, 4.5, "body on rows")
    assert_contrast(INK, PRIMARY, 4.5, "text on primary button")
    assert_contrast(BG, INK, 4.5, "beige text on ink button")
    assert_contrast(BG, DANGER, 4.5, "beige text on danger button")
    # INK_SOFT (#8D6959) measures 4.37:1 on BG — below the 4.5 body-text bar.
    # Per the palette rule ("verify contrast, else use #2B3A42"), all secondary
    # BODY text uses INK. INK_SOFT is decorative/large-text only (WCAG 3:1 UI bar).
    assert_contrast(INK_SOFT, BG, 3.0, "acorn decorative/large only — body uses INK")
    assert_contrast(INK_SOFT, SURFACE, 3.0, "acorn decorative/large only — body uses INK")
    assert_contrast(INK_DEEP, BG, 4.5, "olive heading on window")
    assert_contrast(ACCENT, BG, 4.5, "amethyst heading on window")
    # LINK copper (#AB7044) is 3.66:1 on BG — links therefore render as INK text
    # with a copper UNDERLINE (never color alone, per the state rule). The copper
    # itself is a decorative accent (3:1 UI bar).
    assert_contrast(LINK, BG, 3.0, "link accent — link text is INK with copper underline")
    assert_contrast(LINK, SURFACE, 3.0, "link accent — link text is INK with copper underline")
    assert_contrast(DANGER, SURFACE, 4.5, "error text on card")
    assert_contrast(DANGER, BG, 4.5, "error text on window")
    assert_contrast(INK, HINT, 4.5, "body on tip surface")
    assert_contrast(INK, CTA_SOFT, 4.5, "body on peach surface")
    assert_contrast(INK, NOTICE, 4.5, "body on notice banner")
    # SUCCESS sage (#8A9A86) is 2.67:1 as text and 3.94:1 under ink text — it is a
    # DECORATIVE FILL only (painted accents, subtle fills), never text, never a
    # text-chip background. Tag chips use TRACK (seafoam) instead:
    assert_contrast(INK, TRACK, 4.5, "ink text on seafoam tag chip / calm panel")
    log.info("All E-Sense contrast pairs pass")
