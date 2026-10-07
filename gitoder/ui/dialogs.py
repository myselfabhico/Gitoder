"""Modal dialogs: delete confirmation, warnings, friendly errors with Copy details."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressDialog,
    QVBoxLayout,
    QWidget,
)

from . import icons
from . import theme as T
from .widgets import (
    DangerButton,
    PrimaryButton,
    SecondaryButton,
    body_font,
    display_font,
    micro_font,
    section_font,
)

log = logging.getLogger("gitoder.dialogs")


class ModalBase(QDialog):
    """Soft-cornered modal over a dimmed backdrop. Esc = reject."""

    def __init__(self, parent: QWidget | None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Gitoder")
        self.setFixedWidth(480)

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(T.SURFACE))

        from .widgets import sig_path
        r = self.rect().adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(T.INK), 1.5))
        p.drawPath(sig_path(r, T.RADIUS_SOFT, T.RADIUS_SOFT, T.RADIUS_SOFT, T.RADIUS_SOFT))


class DeleteConfirmDialog(ModalBase):
    """Warning modal: red Confirm (not default), Cancel default-focused, Esc cancels."""

    def __init__(self, parent: QWidget | None, repo_name: str) -> None:
        super().__init__(parent)
        self.setFixedWidth(520)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 30, 32, 28)
        outer.setSpacing(14)

        top = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(icons.pixmap("warning", 42, ink=T.DANGER, accent=T.DANGER))
        top.addWidget(ic)
        top.addStretch(1)
        outer.addLayout(top)

        title = QLabel("Delete this repository?")
        title.setFont(display_font(30))
        title.setStyleSheet(f"color: {T.INK};")
        outer.addWidget(title)

        name_lbl = QLabel(repo_name)
        name_lbl.setFont(body_font(18, QFont.Bold))
        name_lbl.setWordWrap(True)
        name_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        name_lbl.setStyleSheet(f"color: {T.DANGER};")
        outer.addWidget(name_lbl)

        body = QLabel(
            "This permanently deletes the repository, its files, issues, and history. "
            "This cannot be undone."
        )
        body.setFont(body_font(16))
        body.setWordWrap(True)
        body.setStyleSheet(f"color: {T.INK};")
        outer.addWidget(body)

        outer.addSpacing(8)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_btn = SecondaryButton("Cancel")
        self.cancel_btn.setDefault(True)
        self.cancel_btn.setFocus()
        buttons.addWidget(self.cancel_btn)
        self.confirm_btn = DangerButton("Confirm")
        buttons.addWidget(self.confirm_btn)
        outer.addLayout(buttons)

        self.cancel_btn.clicked.connect(self.reject)
        self.confirm_btn.clicked.connect(self.accept)


class WarningDialog(ModalBase):
    """Generic warning with configurable buttons."""

    def __init__(self, parent: QWidget | None, title: str, message: str,
                 continue_label: str = "I understand, continue",
                 cancel_label: str = "Go back") -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 30, 32, 28)
        outer.setSpacing(14)

        ic = QLabel()
        ic.setPixmap(icons.pixmap("warning", 42))
        outer.addWidget(ic)

        t = QLabel(title)
        t.setFont(display_font(28))
        t.setStyleSheet(f"color: {T.INK};")
        outer.addWidget(t)

        m = QLabel(message)
        m.setFont(body_font(16))
        m.setWordWrap(True)
        m.setStyleSheet(f"color: {T.INK};")
        outer.addWidget(m)

        outer.addSpacing(8)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_btn = SecondaryButton(cancel_label)
        cancel_btn.setDefault(True)
        buttons.addWidget(cancel_btn)
        go_btn = PrimaryButton(continue_label)
        buttons.addWidget(go_btn)
        outer.addLayout(buttons)

        cancel_btn.clicked.connect(self.reject)
        go_btn.clicked.connect(self.accept)


def show_error_dialog(parent: QWidget | None, exc, log_path: str | None = None) -> None:
    """Friendly error dialog. Never shows raw tracebacks; Copy details is sanitized."""
    from .widgets import LinkButton

    dlg = ModalBase(parent)
    outer = QVBoxLayout(dlg)
    outer.setContentsMargins(32, 30, 32, 28)
    outer.setSpacing(14)

    ic = QLabel()
    ic.setPixmap(icons.pixmap("error", 42, ink=T.DANGER, accent=T.DANGER))
    outer.addWidget(ic)

    t = QLabel(getattr(exc, "title", "Something went wrong"))
    t.setFont(display_font(28))
    t.setStyleSheet(f"color: {T.INK};")
    outer.addWidget(t)

    m = QLabel(getattr(exc, "message", str(exc)))
    m.setFont(body_font(16))
    m.setWordWrap(True)
    m.setStyleSheet(f"color: {T.INK};")
    outer.addWidget(m)

    detail = getattr(exc, "detail", "")
    detail = detail if isinstance(detail, str) else repr(detail)
    safe = " | ".join(part for part in (detail, log_path) if part)

    row = QHBoxLayout()
    copy_btn = SecondaryButton("Copy details", icon_name="copy")
    row.addWidget(copy_btn)
    if log_path:
        link = LinkButton("Open log folder")
        link.clicked.connect(lambda: _open_containing(log_path))
        row.addWidget(link)
    row.addStretch(1)
    outer.addLayout(row)

    ok = PrimaryButton("OK")
    outer.addWidget(ok, 0, Qt.AlignRight)
    ok.clicked.connect(dlg.accept)
    copy_btn.clicked.connect(lambda: _copy_safe(dlg, getattr(exc, "title", ""), safe))
    dlg.exec()


def _copy_safe(dlg, title: str, safe: str) -> None:
    from PySide6.QtWidgets import QApplication

    text = f"Gitoder error: {title}\n{safe}\n(no private data included)"
    QApplication.clipboard().setText(text)


def _open_containing(path: str) -> None:
    import os
    import subprocess

    try:
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    except OSError:
        pass
