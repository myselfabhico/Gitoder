"""Sign-In: premium two-column hero — brand story left, token card right."""

from __future__ import annotations

import logging
import webbrowser

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from .. import theme as T
from ..dialogs import show_error_dialog
from ..widgets import (
    PaperSurface,
    PrimaryButton,
    SecondaryButton,
    body_font,
    display_font,
    micro_font,
    section_font,
    sig_path,
    show_toast,
    stagger_entrance,
)
from ...core.auth import REQUIRED_SCOPES_URL, TokenStore, looks_like_token, validate_token
from ...core.workers import LongWorker

log = logging.getLogger("gitoder.ui.signin")

GUIDE_URL = ("https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/"
             "creating-a-personal-access-token")


class SignInScreen(PaperSurface):
    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        self._worker: LongWorker | None = None

        root = QHBoxLayout(self)
        root.setContentsMargins(56, 48, 56, 48)
        root.setSpacing(48)

        root.addLayout(self._build_story_column(), 5)
        root.addLayout(self._build_card_column(), 4)

        stagger_entrance([self._story_host, self._card_host])

    # ------------------------------------------------------------ left

    def _build_story_column(self) -> QHBoxLayout:
        host = QWidget(objectName="storyHost")
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        self._story_host = host

        mark = QLabel("Gitoder")
        mark.setFont(display_font(58))
        mark.setStyleSheet(f"color: {T.INK}; background: transparent;")
        lay.addWidget(mark)

        tag = QLabel("Git, minus the headaches.")
        tag.setFont(body_font(19, QFont.Medium))
        tag.setStyleSheet(f"color: {T.INK}; background: transparent;")
        lay.addWidget(tag)
        lay.addSpacing(18)

        for icon_name, text in [
            ("lock", "Your token lives in Windows Credential Manager — "
                     "never in a file, never in a log."),
            ("check", "Pushes are verified file-by-file before Gitoder ever "
                      "says success."),
            ("create", "Create, update, delete and download repositories — "
                       "no terminal, no git commands."),
        ]:
            row = QHBoxLayout()
            row.setSpacing(12)
            ic = QLabel()
            ic.setPixmap(icons.pixmap(icon_name, 20))
            ic.setFixedSize(24, 24)
            ic.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
            row.addWidget(ic)
            lbl = QLabel(text)
            lbl.setFont(body_font(15))
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {T.INK}; background: transparent;")
            row.addWidget(lbl, 1)
            lay.addLayout(row)
            lay.addSpacing(4)

        lay.addStretch(1)
        chips = QHBoxLayout()
        chips.setSpacing(8)
        for chip_text in ("Credential Manager", "Never logged", "Revocable anytime"):
            chips.addWidget(_Chip(chip_text))
        chips.addStretch(1)
        lay.addLayout(chips)
        return _wrap(host)

    # ------------------------------------------------------------ right

    def _build_card_column(self) -> QHBoxLayout:
        card = QFrame()
        card.setObjectName("tokenCard")
        card.setMaximumWidth(560)
        card.setStyleSheet(
            f"#tokenCard {{ background: {T.SURFACE};"
            f"border: 1px solid {T.LINE}; border-radius: {T.RADIUS_SOFT}px; }}"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(32, 30, 32, 28)
        lay.setSpacing(12)
        self._card_host = card

        head = QLabel("Connect your GitHub account.")
        head.setFont(section_font(24))
        head.setWordWrap(True)
        head.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        head.setStyleSheet(f"color: {T.INK}; background: transparent;")
        lay.addWidget(head)

        sub = QLabel("Gitoder needs a token to act on your behalf. Three quick steps:")
        sub.setFont(body_font(14))
        sub.setWordWrap(True)
        sub.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        sub.setStyleSheet(f"color: {T.INK}; background: transparent;")
        lay.addWidget(sub)
        lay.addSpacing(6)

        for i, text in enumerate([
            "Click 'Create my token' — GitHub opens with both permissions "
            "(repo, delete_repo) already checked.",
            "Scroll down and click 'Generate token'.",
            "Copy the token and paste it below.",
        ]):
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(_StepBadge(i + 1))
            lbl = QLabel(text)
            lbl.setFont(body_font(14))
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            lbl.setStyleSheet(f"color: {T.INK}; background: transparent;")
            row.addWidget(lbl, 1)
            lay.addLayout(row)
            lay.addSpacing(2)

        lay.addSpacing(8)
        self.token_btn = SecondaryButton("Create my token", icon_name="external")
        self.token_btn.setFixedHeight(44)
        lay.addWidget(self.token_btn, 0, Qt.AlignLeft)

        guide_link = LinkLabel(
            "Step-by-step guide: how to obtain a token", GUIDE_URL)
        lay.addWidget(guide_link)

        lay.addSpacing(6)
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {T.LINE}; border: none;")
        lay.addWidget(divider)
        lay.addSpacing(2)

        cap = QLabel("TOKEN")
        cap.setFont(micro_font())
        cap.setStyleSheet(f"color: {T.INK}; background: transparent;")
        lay.addWidget(cap)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.token_edit = QLineEdit()
        self.token_edit.setPlaceholderText("ghp_… or github_pat_…")
        self.token_edit.setEchoMode(QLineEdit.Password)
        self.token_edit.setFixedHeight(46)
        self.token_edit.setAccessibleName("Personal access token")
        input_row.addWidget(self.token_edit, 1)
        self.eye_btn = _EyeButton()
        input_row.addWidget(self.eye_btn)
        lay.addLayout(input_row)

        self.status_lbl = QLabel()
        self.status_lbl.setFont(body_font(13, QFont.DemiBold))
        self.status_lbl.setWordWrap(True)
        self.status_lbl.hide()
        lay.addWidget(self.status_lbl)

        lay.addSpacing(6)
        self.connect_btn = PrimaryButton("Connect")
        self.connect_btn.setFixedHeight(50)
        lay.addWidget(self.connect_btn)

        lay.addStretch(1)

        self.banner = QLabel()
        self.banner.setFont(body_font(13, QFont.Medium))
        self.banner.setWordWrap(True)
        self.banner.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.banner.setStyleSheet(
            f"background: {T.NOTICE}; border: 1px solid {T.INK}; border-radius: 3px;"
            f"padding: 10px 12px; color: {T.INK};"
        )
        self.banner.hide()
        lay.addWidget(self.banner)

        self.token_btn.clicked.connect(self._open_token_page)
        self.eye_btn.toggled.connect(self._toggle_echo)
        self.connect_btn.clicked.connect(self._connect)
        self.token_edit.returnPressed.connect(self._connect)
        return _wrap(card)

    # ------------------------------------------------------------ state

    def set_banner(self, text: str) -> None:
        self.banner.setText(text)
        self.banner.show()

    def _toggle_echo(self, show: bool) -> None:
        self.token_edit.setEchoMode(QLineEdit.Normal if show else QLineEdit.Password)

    def _open_token_page(self) -> None:
        webbrowser.open(REQUIRED_SCOPES_URL)

    def _connect(self) -> None:
        token = self.token_edit.text().strip()
        if not looks_like_token(token):
            self._set_status(False, "That doesn't look like a full token — "
                                    "copy it again from GitHub.")
            return
        self._set_status(True, "Connecting…")
        self.connect_btn.set_loading(True, "Connecting")
        self._worker = _ValidateWorker(self.ctx.store, token)
        self._worker.signals.succeeded.connect(self._on_ok)
        self._worker.signals.failed.connect(self._on_fail)
        self.ctx.track(self._worker)
        self._worker.start()

    def _set_status(self, ok: bool, msg: str) -> None:
        color = T.INK_DEEP if ok else T.DANGER
        self.status_lbl.setText(("✔ " if ok else "✖ ") + msg)
        self.status_lbl.setStyleSheet(
            f"color: {color}; background: transparent;")
        self.status_lbl.show()

    def _on_ok(self, payload: object) -> None:
        user, token = payload
        self.connect_btn.set_loading(False)
        self.token_edit.clear()
        self._set_status(True, f"Connected as {user.get('login', '')}")
        self.ctx.set_signed_in(user, token)

    def _on_fail(self, exc: object) -> None:
        self.connect_btn.set_loading(False)
        self._set_status(False, getattr(exc, "message", "Sign-in failed."))
        show_error_dialog(self.window(), exc)


class _ValidateWorker(LongWorker):
    def __init__(self, store: TokenStore, token: str) -> None:
        super().__init__()
        self.store = store
        self.token = token

    def _run(self):
        from ...core.github_client import GithubClient

        client = GithubClient(self.token)
        user = validate_token(self.token, client)
        self.store.save(self.token)
        log.info("Token validated and stored for user %s", user.get("login"))
        return (user, self.token)


# ---------------------------------------------------------------- pieces

def _wrap(w: QWidget) -> QHBoxLayout:
    box = QHBoxLayout()
    box.setContentsMargins(0, 0, 0, 0)
    box.addWidget(w, 1)
    return box


class _StepBadge(QWidget):
    def __init__(self, n: int) -> None:
        super().__init__()
        self._n = n
        self.setFixedSize(28, 28)

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(T.ACCENT))
        p.setPen(QPen(QColor(T.INK), 1.4))
        p.drawEllipse(1, 1, 25, 25)
        p.setPen(QColor(T.BG))
        p.setFont(body_font(13, QFont.Bold))
        p.drawText(self.rect(), Qt.AlignCenter, str(self._n))


class _Chip(QLabel):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setFont(micro_font())
        self.setStyleSheet(
            f"color: {T.INK}; background: {T.SURFACE_2};"
            f"border: 1px solid {T.MUTED}; border-radius: 3px; padding: 5px 10px;"
        )


class _EyeButton(QWidget):
    """Styled show/hide toggle (replaces the raw QToolButton)."""

    toggled = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._checked = False
        self._hover = False
        self.setFixedSize(46, 46)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName("Show or hide token")
        self.setFocusPolicy(Qt.StrongFocus)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        self._checked = not self._checked
        self.toggled.emit(self._checked)
        self.update()

    def enterEvent(self, e) -> None:  # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:  # noqa: N802
        self._hover = False
        self.update()

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        face = QColor(T.PRIMARY_2 if self._hover else T.SURFACE_2)
        p.setPen(QPen(QColor(T.LINE), 1))
        p.setBrush(face)
        p.drawRoundedRect(r, 3, 3)
        pm = icons.pixmap("eye" if self._checked else "eye-off", 20)
        p.drawPixmap((self.width() - 20) // 2, (self.height() - 20) // 2, pm)
        if self.hasFocus():
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(T.FOCUS), 2))
            p.drawRoundedRect(r.adjusted(-2, -2, 2, 2), 4, 4)


class LinkLabel(QLabel):
    """Underlined, warm link label that opens a URL — always words, never color alone."""

    def __init__(self, text: str, url: str) -> None:
        super().__init__(f'<a href="{url}" style="color:#AB7044;'
                         f'text-decoration:underline;">{text}</a>')
        self.setFont(body_font(14, QFont.DemiBold))
        self.setOpenExternalLinks(True)
        self.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.setAccessibleName(text)
