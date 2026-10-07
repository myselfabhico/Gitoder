"""E-Sense custom painted widgets: asymmetric corners, hard offset shadows, real states."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import random
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import icons
from . import theme as T

log = logging.getLogger("gitoder.widgets")

# ----------------------------------------------------------------- motion

_REDUCED_MOTION: bool | None = None


def reduced_motion() -> bool:
    """Windows reduced-motion preference (SPI_GETCLIENTAREAANIMATION)."""
    global _REDUCED_MOTION
    if _REDUCED_MOTION is None:
        try:
            flag = wt.BOOL()
            SPI_GETCLIENTAREAANIMATION = 0x1042
            ok = ctypes.windll.user32.SystemParametersInfoW(
                SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(flag), 0
            )
            _REDUCED_MOTION = bool(ok) and not bool(flag.value)
        except Exception:  # noqa: BLE001 - non-Windows or API failure
            _REDUCED_MOTION = False
    return _REDUCED_MOTION


# ------------------------------------------------------------------ fonts

def _asset_root() -> Path:
    """Bundled-asset root: PyInstaller bundle when frozen, source tree otherwise."""
    import sys

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)                      # exe: datas land at <bundle>/assets
    return Path(__file__).resolve().parent.parent  # source: <repo>/assets


def load_fonts() -> list[str]:
    """Load every bundled TTF; return families that registered."""
    families = []
    fonts_dir = _asset_root() / "assets" / "fonts"
    for ttf in sorted(fonts_dir.glob("*.ttf")):
        fid = QFontDatabase.addApplicationFont(str(ttf))
        if fid >= 0:
            families.extend(QFontDatabase.applicationFontFamilies(fid))
    if not families:
        log.warning("No fonts loaded from %s — text falls back to system fonts",
                    fonts_dir)
    else:
        log.info("Loaded fonts: %s", families)
    return families


def font_pixel(family: str, px: int, weight: QFont.Weight = QFont.Normal,
               letter_spacing: float = 0.0) -> QFont:
    f = QFont(family)
    f.setPixelSize(px)
    f.setWeight(QFont.Weight(weight))
    if letter_spacing:
        f.setLetterSpacing(QFont.AbsoluteSpacing, letter_spacing)
    return f


def display_font(px: int = T.DISPLAY_SIZE, weight: QFont.Weight = QFont.Black) -> QFont:
    return font_pixel(T.FONT_DISPLAY, px, weight, -0.02 * px / 10)


def title_font(px: int = T.TITLE_SIZE) -> QFont:
    return font_pixel(T.FONT_DISPLAY, px, QFont.DemiBold)


def section_font(px: int = T.SECTION_SIZE) -> QFont:
    return font_pixel(T.FONT_DISPLAY, px, QFont.DemiBold)


def body_font(px: int = T.BODY_SIZE, weight: QFont.Weight = QFont.Normal) -> QFont:
    return font_pixel(T.FONT_BODY, px, weight)


def micro_font() -> QFont:
    return font_pixel(T.FONT_BODY, T.LABEL_SIZE, QFont.Bold, 1.2)


# ----------------------------------------------------------------- shapes

def sig_path(rect: QRectF, tl: float, tr: float, br: float, bl: float) -> QPainterPath:
    """Arbitrary-corner rounded rectangle path (clockwise from top-left)."""
    p = QPainterPath()
    p.moveTo(rect.left() + tl, rect.top())
    p.lineTo(rect.right() - tr, rect.top())
    p.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + tr)
    p.lineTo(rect.right(), rect.bottom() - br)
    p.quadTo(rect.right(), rect.bottom(), rect.right() - br, rect.bottom())
    p.lineTo(rect.left() + bl, rect.bottom())
    p.quadTo(rect.left(), rect.bottom(), rect.left(), rect.bottom() - bl)
    p.lineTo(rect.left(), rect.top() + tl)
    p.quadTo(rect.left(), rect.top(), rect.left() + tl, rect.top())
    return p


def _children_transparent(w: QWidget) -> None:
    for child in w.findChildren(QWidget):
        child.setAttribute(Qt.WA_TransparentForMouseEvents)


# ================================================================ buttons

class _ShadowButton(QAbstractButton):
    """Base hard-shadow button. Shapes: pill / micro / soft. Lifts on hover."""

    def __init__(self, text: str = "", shape: str = "pill", *,
                 face: str | None = None, face_hover: str | None = None,
                 text_color: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._shape = shape
        self._face = face or T.PRIMARY
        self._face_hover = face_hover or T.PRIMARY_2
        self._text_color = text_color or T.INK
        self._lift = 0.0
        self._lift_anim: QVariantAnimation | None = None
        self._loading = False
        self._load_phase = 0.0
        self._load_anim: QVariantAnimation | None = None
        self.setText(text)
        self.setFont(body_font(16, QFont.DemiBold))   # real metrics for sizeHint + paint
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.setMinimumHeight(44)
        self.setAttribute(Qt.WA_Hover, True)

    # state -------------------------------------------------------------
    def set_loading(self, loading: bool, text: str = "Working…") -> None:
        self._loading = loading
        self._load_text = text
        self.setEnabled(not loading)
        if loading and not reduced_motion():
            self._load_anim = QVariantAnimation(self)
            self._load_anim.setStartValue(0.0)
            self._load_anim.setEndValue(1.0)
            self._load_anim.setDuration(1200)
            self._load_anim.setLoopCount(-1)
            self._load_anim.valueChanged.connect(lambda _v: self.update())
            self._load_anim.start()
        elif self._load_anim is not None:
            self._load_anim.stop()
            self._load_anim = None
        self.update()

    def _radius_for(self, h: int) -> float:
        if self._shape == "pill":
            return h / 2
        if self._shape == "micro":
            return T.RADIUS_MICRO
        return T.RADIUS_SOFT

    def sizeHint(self) -> QSize:  # noqa: N802
        """Real text-driven hint: QAbstractButton's default collapses custom paints."""
        fm = QFontMetrics(body_font(16, QFont.DemiBold))
        lead = getattr(self, "_lead_icon", None)
        icon_w = (int(lead.width() / max(1.0, lead.devicePixelRatio())) + 10) if lead is not None else 0
        text_w = fm.horizontalAdvance(self.text() or " ")
        pad = 56 if self._shape == "pill" else 36
        chrome = T.SHADOW_OFFSET_HOVER + 6
        return QSize(text_w + icon_w + pad + chrome, max(48, fm.height() + 24))

    # animation -----------------------------------------------------------
    def _animate_lift(self, target: float) -> None:
        if reduced_motion():
            self._lift = target
            self.update()
            return
        if self._lift_anim is not None:
            self._lift_anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(self._lift)
        anim.setEndValue(target)
        anim.setDuration(170)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(self._on_lift)
        anim.finished.connect(lambda: setattr(self, "_lift_anim", None))
        self._lift_anim = anim
        anim.start()

    def _on_lift(self, v: float) -> None:
        self._lift = float(v)
        self.update()

    def enterEvent(self, e) -> None:  # noqa: N802
        if self.isEnabled():
            self._animate_lift(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:  # noqa: N802
        self._animate_lift(0.0)
        super().leaveEvent(e)

    # paint ----------------------------------------------------------------
    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        margin = T.SHADOW_OFFSET_HOVER + 3
        r = QRectF(self.rect()).adjusted(margin, margin, -margin, -margin)
        pressed = self.isDown()
        hover = self.underMouse() and self.isEnabled()

        lift = 0.0 if pressed else self._lift
        off = 5.0 if not pressed else 3.0
        dy = (-2.0 * lift) if not pressed else 2.0

        if self.isEnabled():
            shadow = sig_path(r.translated(off, off), *(self._corners(r)))
            p.fillPath(shadow, QColor(T.SHADOW_COLOR))
        face = QColor(self._face if not hover else self._face_hover)
        if not self.isEnabled():
            face = QColor(T.FILL_SUBTLE)
        body = sig_path(r.translated(0, dy), *(self._corners(r)))
        p.fillPath(body, face)
        if self._shape == "micro":
            p.setPen(QPen(QColor(T.LINE), 1))
            p.drawPath(body)

        if self.hasFocus():
            focus = sig_path(r.translated(0, dy).adjusted(-4, -4, 4, 4), *(self._corners(r)))
            p.setPen(QPen(QColor(T.FOCUS), 2))
            p.drawPath(focus)

        p.setPen(QColor(T.MUTED if not self.isEnabled() else self._text_color))
        p.setFont(body_font(16, QFont.DemiBold))
        text = self._load_text if self._loading and hasattr(self, "_load_text") else self.text()
        if self._loading and self._load_anim is not None:
            dots = "." * (1 + int(self._load_phase * 3) % 3)
            text = text + dots
        # icon + text drawn as ONE centered group; elide rather than vanish
        fm = p.fontMetrics()
        lead = getattr(self, "_lead_icon", None)
        icon_w = 0
        if lead is not None and not self._loading:
            icon_w = int(lead.width() / max(1.0, lead.devicePixelRatio())) + 10
        avail = r.width() - 16 - icon_w
        shown = fm.elidedText(text, Qt.ElideRight, int(max(10, avail)))
        text_w = fm.horizontalAdvance(shown)
        base_x = r.left() + (r.width() - (icon_w + text_w)) / 2
        if icon_w:
            p.drawPixmap(int(round(base_x)), int(r.top() + dy + (r.height() - 18) / 2), lead)
        text_rect = QRectF(base_x + icon_w, r.top() + dy, r.right() - (base_x + icon_w) - 4,
                           r.height())
        p.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, shown)

    def _corners(self, r: QRectF) -> tuple[float, float, float, float]:
        rad = self._radius_for(int(r.height()))
        return (rad, rad, rad, rad)


class PrimaryButton(_ShadowButton):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, "pill", face=T.PRIMARY, face_hover=T.PRIMARY_2,
                         text_color=T.INK, parent=parent)
        self.setAccessibleName(text or "Primary action")


class SecondaryButton(_ShadowButton):
    def __init__(self, text: str, icon_name: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(text, "micro", face=T.SURFACE_2, face_hover=T.PRIMARY_2,
                         text_color=T.INK, parent=parent)
        self._lead_icon = icons.pixmap(icon_name, 18) if icon_name else None
        self.setAccessibleName(text or "Secondary action")


class DangerButton(_ShadowButton):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, "pill", face=T.DANGER, face_hover=T.DANGER,
                         text_color=T.BG, parent=parent)
        self.setAccessibleName(text or "Destructive action")


class LinkButton(QAbstractButton):
    """Quiet text button: ink text with copper underline (never color alone)."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setFont(body_font(14, QFont.DemiBold))
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(text)

    def sizeHint(self) -> QSize:  # noqa: N802
        # 44px tall: the full widget is the click target; only the text band is painted
        metrics = QFontMetrics(self.font())
        return QSize(metrics.horizontalAdvance(self.text()) + 12, 44)

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(body_font(14, QFont.DemiBold))
        fm = p.fontMetrics()
        text = self.text()
        w = fm.horizontalAdvance(text)
        p.setPen(QColor(T.LINK if self.underMouse() else T.INK))
        p.drawText(self.rect(), Qt.AlignCenter, text)
        p.setPen(QPen(QColor(T.LINK), 1.4))
        y = self.height() // 2 + fm.descent() + 2
        p.drawLine(2, y, 2 + w, y)
        if self.hasFocus():
            p.setPen(QPen(QColor(T.FOCUS), 2))
            p.drawRoundedRect(0, 0, self.width() - 1, self.height() - 1, 3, 3)


# ================================================================= card

class SignatureCard(QAbstractButton):
    """The signature shape: 0 / 28 / 0 / 28 corners + hard offset shadow + lift."""

    def __init__(self, heading: str, description: str, icon_name: str, *,
                 surface: str = T.SURFACE, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._surface = surface
        self._lift = 0.0
        self._lift_anim: QVariantAnimation | None = None
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAccessibleName(f"{heading}: {description}")
        self.setAttribute(Qt.WA_Hover, True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 26, 28, 24)
        lay.setSpacing(12)

        icon_host = QLabel()
        icon_host.setPixmap(icons.pixmap(icon_name, 44, accent=T.PRIMARY))
        icon_host.setFixedSize(52, 52)
        icon_host.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon_host)

        h = QLabel(heading)
        h.setFont(section_font(T.CARD_H_SIZE))
        h.setStyleSheet(f"color: {T.INK}; background: transparent;")
        lay.addWidget(h)

        d = QLabel(description)
        d.setFont(body_font(15))
        d.setWordWrap(True)
        d.setStyleSheet(f"color: {T.INK}; background: transparent;")
        lay.addWidget(d)

        lay.addStretch(1)
        cue_row = QHBoxLayout()
        cue = QLabel("Open")
        cue.setFont(body_font(14, QFont.DemiBold))
        cue.setStyleSheet(f"color: {T.INK}; background: transparent;")
        arrow = QLabel()
        arrow.setPixmap(_flip_x(icons.pixmap("back", 16, ink=T.PRIMARY), 16))
        cue_row.addWidget(cue)
        cue_row.addWidget(arrow)
        cue_row.addStretch(1)
        lay.addLayout(cue_row)

        _children_transparent(self)

    def _animate_lift(self, target: float) -> None:
        if reduced_motion():
            self._lift = target
            self.update()
            return
        if self._lift_anim is not None:
            self._lift_anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(self._lift)
        anim.setEndValue(target)
        anim.setDuration(190)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(self._on_lift)
        self._lift_anim = anim
        anim.start()

    def _on_lift(self, v: float) -> None:
        self._lift = float(v)
        self.update()

    def enterEvent(self, e) -> None:  # noqa: N802
        self._animate_lift(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:  # noqa: N802
        self._animate_lift(0.0)
        super().leaveEvent(e)

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        margin = T.SHADOW_OFFSET_HOVER + 3
        r = QRectF(self.rect()).adjusted(margin, margin, -margin, -margin)
        pressed = self.isDown()
        off = T.SHADOW_OFFSET if not pressed else 3.0
        off += T.SHADOW_OFFSET_HOVER - T.SHADOW_OFFSET if self._lift > 0.5 and not pressed else 0.0
        dy = -2 if (self._lift > 0.5 and not pressed) else (2 if pressed else 0)

        shadow = sig_path(r.translated(off, off), *T.SIGNATURE_CORNERS)
        p.fillPath(shadow, QColor(T.SHADOW_COLOR))
        body = sig_path(r.translated(0, dy), *T.SIGNATURE_CORNERS)
        p.fillPath(body, QColor(self._surface))
        p.setPen(QPen(QColor(T.LINE), 1))
        p.drawPath(body)

        if self.hasFocus():
            p.setPen(QPen(QColor(T.FOCUS), 2))
            p.drawPath(sig_path(r.translated(0, dy).adjusted(-4, -4, 4, 4), *T.SIGNATURE_CORNERS))


def _flip_x(pm: QPixmap, size: int) -> QPixmap:
    from PySide6.QtGui import QTransform
    return pm.transformed(QTransform().scale(-1, 1))


# ============================================================= form field

class FormField(QWidget):
    """Label + micro-corner input + inline status line (icon + words)."""

    textChanged = Signal(str)

    def __init__(self, label: str, placeholder: str = "", *,
                 password: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        cap = QLabel(label.upper())
        cap.setFont(micro_font())
        cap.setStyleSheet(f"color: {T.INK}; background: transparent;")
        lay.addWidget(cap)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setObjectName("microInput")
        self.edit.setFixedHeight(44)
        self.edit.setFont(body_font(16))
        self.edit.setAccessibleName(label)
        if password:
            self.edit.setEchoMode(QLineEdit.Password)
        self.edit.textChanged.connect(self.textChanged)
        self.edit.textChanged.connect(lambda _t: self.clear_status())
        lay.addWidget(self.edit)

        self._status = QLabel()
        self._status.setFont(body_font(14, QFont.Medium))
        self._status.setStyleSheet(f"color: {T.INK}; background: transparent;")
        self._status.hide()
        lay.addWidget(self._status)

    def text(self) -> str:
        return self.edit.text()

    def set_text(self, t: str) -> None:
        self.edit.setText(t)

    def set_status(self, ok: bool, message: str) -> None:
        icon_name = "check" if ok else "error"
        color = T.INK_DEEP if ok else T.DANGER
        self._status.setText(message)
        self._status.setStyleSheet(
            f"color: {color}; background: transparent; font-weight: 600;"
        )
        pm = icons.pixmap(icon_name, 15, ink=color, accent=color)
        self._status.setPixmap(pm)
        self._status.show()

    def clear_status(self) -> None:
        self._status.hide()

    def set_enabled_input(self, on: bool) -> None:
        self.edit.setEnabled(on)


# =============================================================== toggle

class ToggleSwitch(QAbstractButton):
    """On/off pill toggle. Uses QAbstractButton's built-in toggled signal."""

    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(56, 32)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        track = QColor(T.PRIMARY if self.isChecked() else T.FILL_SUBTLE)
        p.setPen(QPen(QColor(T.INK if self.isChecked() else T.MUTED), 1.4))
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        knob_r = r.height() - 8
        x = r.width() - knob_r - 4 if self.isChecked() else 4
        p.setBrush(QColor(T.BG))
        p.setPen(QPen(QColor(T.INK), 1.4))
        p.drawEllipse(QRectF(x, 4, knob_r, knob_r))
        if self.hasFocus():
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(T.FOCUS), 2))
            p.drawRoundedRect(r.adjusted(-3, -3, 3, 3), r.height() / 2, r.height() / 2)


# ===================================================== segmented control

class SegmentedControl(QWidget):
    """Two-option selector (Public/Private) with icons, border + check state."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str, str]], current: str, *,
                 parent: QWidget | None = None) -> None:
        """options: list of (value, label, icon_name)."""
        super().__init__(parent)
        self._values = [o[0] for o in options]
        self._current = current
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for value, label, icon_name in options:
            opt = _SegmentOption(label, icon_name)
            opt.setCheckable(True)
            opt.setChecked(value == current)
            self._group.addButton(opt)
            opt.clicked.connect(lambda _c=False, v=value: self._on_pick(v))
            lay.addWidget(opt)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def _on_pick(self, value: str) -> None:
        if value != self._current:
            self._current = value
            self.changed.emit(value)

    def value(self) -> str:
        return self._current


class _SegmentOption(QAbstractButton):
    def __init__(self, label: str, icon_name: str) -> None:
        super().__init__()
        self._label = label
        self._icon_name = icon_name
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(190, 48)
        self.setAccessibleName(label)

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        selected = self.isChecked()
        p.setPen(QPen(QColor(T.INK), 2) if selected else QPen(QColor(T.LINE), 1))
        p.setBrush(QColor(T.CTA_SOFT if selected else T.SURFACE_2))
        path = sig_path(r, T.RADIUS_MICRO, T.RADIUS_MICRO, T.RADIUS_MICRO, T.RADIUS_MICRO)
        p.drawPath(path)

        pm = icons.pixmap(self._icon_name, 20)
        p.drawPixmap(14, (self.height() - 20) // 2, pm)
        p.setPen(QColor(T.INK))
        p.setFont(body_font(15, QFont.DemiBold))
        p.drawText(r.adjusted(44, 0, -34, 0), Qt.AlignVCenter, self._label)
        if selected:
            check = icons.pixmap("check", 18, ink=T.INK_DEEP, accent=T.INK_DEEP)
            p.drawPixmap(self.width() - 28, (self.height() - 18) // 2, check)
        if self.hasFocus():
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(T.FOCUS), 2))
            p.drawPath(sig_path(r.adjusted(-3, -3, 3, 3),
                                T.RADIUS_MICRO, T.RADIUS_MICRO, T.RADIUS_MICRO, T.RADIUS_MICRO))


# ========================================================= step indicator

class StepIndicator(QWidget):
    def __init__(self, steps: list[str], current: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._steps = steps
        self._current = current
        self.setFixedHeight(64)
        self.setAccessibleName("Steps: " + ", ".join(steps))

    def set_current(self, i: int) -> None:
        self._current = i
        self.update()

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = len(self._steps)
        fm_w = self.width()
        step_w = fm_w / n
        for i, label in enumerate(self._steps):
            cx = step_w * i + step_w / 2
            cy = 24
            done = i < self._current
            active = i == self._current
            if done:
                p.setBrush(QColor(T.INK))
                p.setPen(QPen(QColor(T.INK), 1.5))
            elif active:
                p.setBrush(QColor(T.ACCENT))
                p.setPen(QPen(QColor(T.ACCENT), 1.5))
            else:
                p.setBrush(QColor(T.SURFACE))
                p.setPen(QPen(QColor(T.MUTED), 1.5))
            p.drawEllipse(QRectF(cx - 13, cy - 13, 26, 26))
            p.setPen(QColor(T.BG if (done or active) else T.MUTED))
            p.setFont(body_font(13, QFont.Bold))
            p.drawText(QRectF(cx - 13, cy - 13, 26, 26), Qt.AlignCenter,
                       "✓" if done else str(i + 1))
            p.setPen(QColor(T.INK if active else (T.INK if done else T.MUTED)))
            p.setFont(body_font(14, QFont.DemiBold if active else QFont.Medium))
            p.drawText(QRectF(cx - step_w / 2, cy + 20, step_w, 22),
                       Qt.AlignHCenter, label)
            if i < n - 1:
                p.setPen(QPen(QColor(T.LINE if not done else T.INK), 2))
                p.drawLine(int(cx + 20), cy, int(cx + step_w - 20), cy)


# ============================================================ progress bar

class ProgressBar(QWidget):
    """Sharp-cornered bar: TRACK background, PRIMARY fill, sharp end cap."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = 0.0        # 0..100
        self._indeterminate = False
        self._sweep = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setFixedHeight(14)

    def set_value(self, pct: float) -> None:
        self._indeterminate = False
        self._timer.stop()
        self._value = max(0.0, min(100.0, pct))
        self.update()

    def set_indeterminate(self, on: bool) -> None:
        self._indeterminate = on
        if on and not reduced_motion():
            self._timer.start(40)
        elif not on:
            self._timer.stop()
        self.update()

    def _tick(self) -> None:
        self._sweep = (self._sweep + 0.02) % 1.4
        self.update()

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setPen(QPen(QColor(T.INK), 1.2))
        p.setBrush(QColor(T.TRACK))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.PRIMARY))
        if self._indeterminate:
            w = self.width() * 0.3
            x = (self.width() + w) * (self._sweep if self._sweep <= 1 else 1.4 - self._sweep) - w
            p.drawRect(QRect(max(0, int(x)), 1, min(int(w), self.width() - max(0, int(x)) - 1),
                             self.height() - 2))
        else:
            w = int((self.width() - 2) * self._value / 100)
            p.drawRect(1, 1, w, self.height() - 2)


# ===================================================== path strip / banners

class PathStrip(QWidget):
    """Sharp-cornered full folder path display. Copies on click."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path = ""
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(40)
        self.setAccessibleName("Selected folder path")
        self.setToolTip("Click to copy the path")

    def set_path(self, path: str) -> None:
        self._path = path
        self.update()

    def path(self) -> str:
        return self._path

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        fm = p.fontMetrics()
        text = self._path or "Pick a folder above"
        while text and fm.horizontalAdvance(text) > self.width() - 90:
            text = "…" + text[4:]
        p.setFont(body_font(14, QFont.Medium))
        p.fillRect(self.rect(), QColor(T.SURFACE_2))
        p.setPen(QPen(QColor(T.INK), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        pm = icons.pixmap("folder", 16)
        p.drawPixmap(10, (self.height() - 16) // 2, pm)
        p.setPen(QColor(T.INK))
        p.drawText(QRect(34, 0, self.width() - 44, self.height()), Qt.AlignVCenter, text)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if self._path:
            from PySide6.QtWidgets import QApplication

            QApplication.clipboard().setText(self._path)
            show_toast(self.window(), "Path copied")


class NoticeBanner(QFrame):
    """Inline note: info (violet), warning (apricot), blocking (apricot + danger text)."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)
        self.icon_lbl = QLabel()
        lay.addWidget(self.icon_lbl)
        self.text_lbl = QLabel(text)
        self.text_lbl.setWordWrap(True)
        self.text_lbl.setFont(body_font(14, QFont.Medium))
        lay.addWidget(self.text_lbl, 1)
        self.hide()

    def show_text(self, text: str, tone: str = "info") -> None:
        mapping = {
            "info": ("info", T.NOTICE, T.INK),
            "warning": ("warning", T.HINT, T.INK),
            "blocking": ("error", T.HINT, T.DANGER),
        }
        icon_name, bg, fg = mapping.get(tone, mapping["info"])
        self.icon_lbl.setPixmap(icons.pixmap(icon_name, 18, ink=fg, accent=T.PRIMARY))
        self.text_lbl.setText(text)
        self.text_lbl.setStyleSheet(f"color: {fg};")
        self.setStyleSheet(
            f"NoticeBanner {{ background: {bg}; border: 1px solid {T.INK};"
            f"border-radius: 3px; }}"
        )
        self.show()



# ================================================================ toast

class Toast(QFrame):
    """Non-blocking message that fades in/out near the window bottom."""

    def __init__(self, parent: QWidget, text: str, kind: str = "info") -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        icon_name = {"info": "info", "success": "check", "error": "error"}.get(kind, "info")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(10)
        ic = QLabel()
        tint = T.INK_DEEP if kind == "success" else (T.DANGER if kind == "error" else T.ACCENT)
        ic.setPixmap(icons.pixmap(icon_name, 18, ink=tint, accent=tint))
        lay.addWidget(ic)
        lbl = QLabel(text)
        lbl.setFont(body_font(15, QFont.Medium))
        lbl.setStyleSheet(f"color: {T.INK};")
        lay.addWidget(lbl)
        self.setStyleSheet(
            f"background: {T.NOTICE}; border: 1px solid {T.INK};"
        )
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(0.0)
        self.adjustSize()

    def popup(self, ms: int = 2800) -> None:
        parent = self.parentWidget()
        if parent:
            self.move((parent.width() - self.width()) // 2, parent.height() - 72)
        self.show()
        self.raise_()
        anim = QPropertyAnimation(self._effect, b"opacity", self)
        anim.setDuration(180 if not reduced_motion() else 0)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start(QPropertyAnimation.DeleteWhenStopped)
        QTimer.singleShot(ms, self._fade_out)

    def _fade_out(self) -> None:
        anim = QPropertyAnimation(self._effect, b"opacity", self)
        anim.setDuration(260 if not reduced_motion() else 0)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self.close)
        anim.start(QPropertyAnimation.DeleteWhenStopped)


def show_toast(parent: QWidget, text: str, kind: str = "info") -> None:
    Toast(parent, text, kind).popup()


# ============================================================= repo rows

class RepoRow(QFrame):
    """One repository row: name, visibility tag, updated date, language.

    kind="delete": red DangerButton at the right edge.
    kind="select": single-select with check mark + border + tone.
    """

    deleteRequested = Signal(object)
    selected = Signal(object)

    def __init__(self, repo: dict, kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repo = repo
        self.kind = kind
        self._selected = False
        self.setObjectName("repoRow")
        self.setCursor(Qt.PointingHandCursor if kind == "select" else Qt.ArrowCursor)
        self.setMinimumHeight(64)
        if kind == "select":
            self.setFocusPolicy(Qt.StrongFocus)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 12, 14, 12)
        lay.setSpacing(14)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        name = QLabel(repo["name"])
        name.setFont(body_font(17, QFont.Bold))
        name.setStyleSheet(f"color: {T.INK};")
        text_col.addWidget(name)
        meta_bits = []
        if repo.get("language"):
            meta_bits.append(repo["language"])
        if repo.get("updated_at"):
            date = str(repo["updated_at"])[:10]
            meta_bits.append(f"Updated {date}")
        meta = QLabel(" · ".join(meta_bits))
        meta.setFont(body_font(13))
        meta.setStyleSheet(f"color: {T.INK};")
        text_col.addWidget(meta)
        lay.addLayout(text_col)
        lay.addStretch(1)

        vis = QLabel("Private" if repo.get("private") else "Public")
        vis.setFont(body_font(12, QFont.Bold))
        vis.setStyleSheet(
            f"color: {T.INK}; background: {T.TRACK};"
            f"border: 1px solid {T.MUTED}; border-radius: 3px;"
            f"padding: 3px 10px;"
        )
        vis.setAccessibleName(f"{'Private' if repo.get('private') else 'Public'} repository")
        lay.addWidget(vis)

        if kind == "delete":
            btn = DangerButton("Delete")
            btn.setFixedHeight(38)
            btn.clicked.connect(lambda: self.deleteRequested.emit(self))
            lay.addWidget(btn)
        else:
            self._check = QLabel()
            self._check.setPixmap(icons.pixmap("check", 20, ink=T.INK_DEEP, accent=T.INK_DEEP))
            self._check.hide()
            lay.addWidget(self._check)

        self._check_lbl = getattr(self, "_check", None)

    def set_selected(self, on: bool) -> None:
        self._selected = on
        if self._check_lbl is not None:
            self._check_lbl.setVisible(on)
        self.setStyleSheet("")
        self.update()
        self._sync_style()

    def _sync_style(self) -> None:
        if self._selected:
            self.setStyleSheet(f"RepoRow {{ border: 2px solid {T.INK}; background: {T.CTA_SOFT}; border-radius: 14px; }}")
        else:
            self.setStyleSheet(f"RepoRow {{ border: 1px solid {T.LINE}; background: {T.SURFACE_2}; border-radius: 14px; }}")

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        self._sync_style()

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if self.kind == "select":
            self.selected.emit(self)
        super().mousePressEvent(e)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if self.kind == "select" and e.key() in (Qt.Key_Return, Qt.Key_Space):
            self.selected.emit(self)
            e.accept()
            return
        super().keyPressEvent(e)


# ====================================================== skeleton / empty

class SkeletonRow(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(64)
        self._pulse = 0.0
        self._anim: QVariantAnimation | None = None

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        if self._anim is None and not reduced_motion():
            self._anim = QVariantAnimation(self)
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.setDuration(900)
            self._anim.setLoopCount(-1)
            self._anim.valueChanged.connect(self._on_pulse)
            self._anim.start()

    def _on_pulse(self, v: float) -> None:
        self._pulse = abs(1.0 - 2.0 * float(v))
        self.update()

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(T.LINE), 1))
        p.setBrush(QColor(T.SURFACE_2))
        path = sig_path(r, T.RADIUS_SOFT, T.RADIUS_SOFT, T.RADIUS_SOFT, T.RADIUS_SOFT)
        p.drawPath(path)
        alpha = 0.5 + 0.3 * self._pulse
        p.setPen(Qt.NoPen)
        mq = QColor(T.MUTED)
        base_a = int(255 * alpha * 0.35)
        p.setBrush(QColor(mq.red(), mq.green(), mq.blue(), base_a))
        p.drawRoundedRect(QRectF(18, 16, 200, 14), 4, 4)
        p.drawRoundedRect(QRectF(18, 38, 130, 10), 4, 4)
        p.drawRoundedRect(QRectF(self.width() - 150, 18, 90, 26), 4, 4)


class EmptyState(QWidget):
    """Palette-shape illustration + message."""

    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 40, 24, 40)
        lay.setSpacing(10)
        art = _EmptyArt()
        art.setFixedHeight(110)
        lay.addWidget(art, 0, Qt.AlignHCenter)
        t = QLabel(title)
        t.setFont(section_font(22))
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet(f"color: {T.INK};")
        lay.addWidget(t)
        s = QLabel(subtitle)
        s.setFont(body_font(15))
        s.setAlignment(Qt.AlignCenter)
        s.setWordWrap(True)
        s.setStyleSheet(f"color: {T.INK};")
        lay.addWidget(s)


class _EmptyArt(QWidget):
    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx = self.width() / 2
        p.setPen(QPen(QColor(T.INK), 2))
        p.setBrush(QColor(T.CTA_SOFT))
        p.drawRoundedRect(QRectF(cx - 70, 10, 140, 88), 0, 0)
        p.setBrush(QColor(T.PRIMARY))
        p.drawRoundedRect(QRectF(cx - 70, 10, 60, 20), 0, 0)
        p.setBrush(QColor(T.NOTICE))
        p.drawEllipse(QRectF(cx + 44, 66, 34, 34))
        p.setBrush(QColor(T.TRACK))
        p.drawEllipse(QRectF(cx - 96, 58, 24, 24))
        p.setPen(QPen(QColor(T.ACCENT), 3, Qt.DotLine))
        p.drawLine(int(cx - 110), 98, int(cx + 110), 98)


# =============================================================== avatar

class AvatarLabel(QWidget):
    """Circle-cropped avatar with initial-letter fallback."""

    def __init__(self, size: int = 34, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._size = size
        self._pixmap: QPixmap | None = None
        self._initial: str = "?"
        self.setFixedSize(size, size)

    def set_initial(self, name: str) -> None:
        self._initial = (name or "?").strip()[:1].upper() or "?"
        self._pixmap = None
        self.update()

    def set_image_bytes(self, data: bytes | None) -> None:
        if not data:
            return
        pm = QPixmap()
        if pm.loadFromData(data) and not pm.isNull():
            self._pixmap = pm.scaled(
                self._size * 2, self._size * 2,
                Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            self.update()

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0.5, 0.5, self._size - 1, self._size - 1)
        path = QPainterPath()
        path.addEllipse(r)
        p.setClipPath(path)
        if self._pixmap is not None:
            p.drawPixmap(0, 0, self._size, self._size, self._pixmap)
        else:
            p.fillRect(r, QColor(T.INK))
            p.setPen(QColor(T.BG))
            p.setFont(display_font(int(self._size * 0.55)))
            p.drawText(r, Qt.AlignCenter, self._initial)
        p.setClipping(False)
        p.setPen(QPen(QColor(T.INK), 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(r)


# =========================================================== grain base

class PaperSurface(QWidget):
    """Warm beige base with a very faint procedural paper grain (4%)."""

    _grain: QPixmap | None = None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    @classmethod
    def grain_pixmap(cls) -> QPixmap:
        if cls._grain is None:
            pm = QPixmap(160, 160)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            rng = random.Random(7)
            for _ in range(420):
                x, y = rng.randrange(160), rng.randrange(160)
                a = rng.randint(4, 10)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(43, 58, 66, a))
                p.drawEllipse(x, y, 1, 1)
            p.end()
            cls._grain = pm
        return cls._grain

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(T.BG))
        p.drawTiledPixmap(self.rect(), self.grain_pixmap())


# ====================================================== entrance motion

def stagger_entrance(widgets: list[QWidget], *, distance: int = 18,
                     duration: int = 480, stagger_ms: int = 55) -> None:
    """Staggered fade + translate-up when a screen appears. Reduced-motion aware."""
    if reduced_motion():
        return
    for i, w in enumerate(widgets):
        if w is None:
            continue
        effect = QGraphicsOpacityEffect(w)
        effect.setOpacity(0.0)
        w.setGraphicsEffect(effect)
        QTimer.singleShot(
            i * stagger_ms,
            lambda w=w, eff=effect: _run_entrance(w, eff, distance, duration),
        )


def _run_entrance(w: QWidget, effect: QGraphicsOpacityEffect,
                  distance: int, duration: int) -> None:
    if not w.isVisible():
        effect.setOpacity(1.0)
        w.setGraphicsEffect(None)
        return
    start = w.pos()
    w.move(start.x(), start.y() + distance)
    fade = QPropertyAnimation(effect, b"opacity", w)
    fade.setDuration(int(duration * 0.7))
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    fade.setEasingCurve(QEasingCurve.OutCubic)
    fade.finished.connect(lambda: w.setGraphicsEffect(None))
    fade.start(QPropertyAnimation.DeleteWhenStopped)
    slide = QPropertyAnimation(w, b"pos", w)
    slide.setDuration(duration)
    slide.setStartValue(w.pos())
    slide.setEndValue(start)
    slide.setEasingCurve(QEasingCurve.OutCubic)
    slide.start(QPropertyAnimation.DeleteWhenStopped)
