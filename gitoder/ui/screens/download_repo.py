"""Download Repo: link parsing UI, animated progress panel, success/failure states."""

from __future__ import annotations

import logging
import os
import subprocess

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from .. import theme as T
from ..dialogs import show_error_dialog
from ..widgets import (
    NoticeBanner,
    PaperSurface,
    PrimaryButton,
    ProgressBar,
    SecondaryButton,
    body_font,
    display_font,
    micro_font,
    show_toast,
)
from ...core.downloader import parse_repo_link, repo_display_name
from ...core.errors import InvalidLinkError
from ...core.workers import DownloadWorker

log = logging.getLogger("gitoder.ui.download")


class DownloadRepoScreen(PaperSurface):
    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        self._worker: DownloadWorker | None = None
        self._target_path: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(56, 28, 56, 32)
        root.setSpacing(14)

        self.title = QLabel("Download a repository.")
        self.title.setFont(display_font(34))
        self.title.setStyleSheet(f"color: {T.INK};")
        root.addWidget(self.title)

        sub = QLabel("Paste any GitHub repo link and Gitoder will save it as a .zip "
                     "in your Downloads folder.")
        sub.setFont(body_font(16))
        sub.setStyleSheet(f"color: {T.INK};")
        sub.setWordWrap(True)
        root.addWidget(sub)

        cap = QLabel("REPOSITORY LINK")
        cap.setFont(micro_font())
        cap.setStyleSheet(f"color: {T.INK};")
        root.addWidget(cap)

        row = QHBoxLayout()
        self.link_edit = QLineEdit()
        self.link_edit.setPlaceholderText("github.com/owner/repo  ·  owner/repo  ·  git@…")
        self.link_edit.setFixedHeight(52)
        self.link_edit.setAccessibleName("GitHub repository link")
        self.link_edit.setStyleSheet(
            f"background: {T.SURFACE}; border: 1px solid {T.FOCUS};"
            f"border-radius: 3px; padding: 0 14px; color: {T.INK}; font-size: 16px;"
        )
        self.link_edit.textChanged.connect(self._validate)
        row.addWidget(self.link_edit, 1)
        self.paste_btn = SecondaryButton("Paste")
        self.paste_btn.setFixedHeight(52)
        self.paste_btn.clicked.connect(self._paste)
        row.addWidget(self.paste_btn)
        self.dl_btn = PrimaryButton("Download")
        self.dl_btn.setFixedWidth(170)
        self.dl_btn.setFixedHeight(52)
        self.dl_btn.setEnabled(False)
        self.dl_btn.clicked.connect(self._start)
        row.addWidget(self.dl_btn)
        root.addLayout(row)

        self.hint = QLabel("")
        self.hint.setFont(body_font(14, QFont.Medium))
        self.hint.setStyleSheet(f"color: {T.INK};")
        root.addWidget(self.hint)

        self.panel = DownloadPanel()
        self.panel.hide()
        root.addWidget(self.panel)

        self.success_box = QWidget()
        sb = QVBoxLayout(self.success_box)
        sb.setContentsMargins(0, 0, 0, 0)
        sb.setSpacing(8)
        self.saved_lbl = QLabel("")
        self.saved_lbl.setFont(body_font(16, QFont.DemiBold))
        self.saved_lbl.setStyleSheet(f"color: {T.INK};")
        sb.addWidget(self.saved_lbl)
        self.path_lbl = QLabel("")
        self.path_lbl.setFont(body_font(14))
        self.path_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.path_lbl.setStyleSheet(f"color: {T.INK};")
        sb.addWidget(self.path_lbl)
        srow = QHBoxLayout()
        self.show_btn = SecondaryButton("Show in folder", icon_name="folder")
        srow.addWidget(self.show_btn)
        self.again_btn = SecondaryButton("Download another")
        srow.addWidget(self.again_btn)
        self.home_btn = SecondaryButton("Back to Home")
        srow.addWidget(self.home_btn)
        srow.addStretch(1)
        sb.addLayout(srow)
        self.success_box.hide()
        root.addWidget(self.success_box)

        root.addStretch(1)
        bottom = QHBoxLayout()
        self.back = SecondaryButton("Home", icon_name="back")
        self.back.clicked.connect(self._go_home)
        bottom.addWidget(self.back)
        bottom.addStretch(1)
        root.addLayout(bottom)

        self.show_btn.clicked.connect(self._show_in_folder)
        self.again_btn.clicked.connect(self._reset)
        self.home_btn.clicked.connect(self._go_home)

    # ------------------------------------------------------------ flow

    def _validate(self, text: str) -> None:
        try:
            owner, repo, ref = parse_repo_link(text)
        except InvalidLinkError:
            if text.strip():
                self.hint.setText("That doesn't look like a GitHub repository link.")
                self.hint.setStyleSheet(f"color: {T.DANGER};")
            else:
                self.hint.setText("")
            self.dl_btn.setEnabled(False)
            return
        self.hint.setText(f"Ready: {owner}/{repo}" + (f" · branch {ref}" if ref else ""))
        self.hint.setStyleSheet(f"color: {T.INK_DEEP};")
        self.dl_btn.setEnabled(True)

    def _paste(self) -> None:
        from PySide6.QtWidgets import QApplication

        text = QApplication.clipboard().text()
        self.link_edit.setText(text.strip())

    def _start(self) -> None:
        try:
            parse_repo_link(self.link_edit.text())
        except InvalidLinkError:
            return
        self.dl_btn.setEnabled(False)
        self.link_edit.setEnabled(False)
        self.paste_btn.setEnabled(False)
        self.success_box.hide()
        self.panel.reset()
        self.panel.show()
        self.ctx.set_busy(True)
        self._worker = DownloadWorker(self.ctx.client, self.link_edit.text())
        self._worker.signals.download_progress.connect(self.panel.on_progress)
        self._worker.signals.succeeded.connect(self._on_done)
        self._worker.signals.failed.connect(self._on_fail)
        self.ctx.track(self._worker)
        self._worker.start()

    def _on_done(self, path) -> None:
        self.ctx.set_busy(False)
        self._target_path = str(path)
        self.panel.finish()
        self.success_box.show()
        self.saved_lbl.setText("Saved to your Downloads folder")
        self.path_lbl.setText(str(path))
        show_toast(self, "Download complete", "success")

    def _on_fail(self, exc) -> None:
        self.ctx.set_busy(False)
        self.panel.fail(getattr(exc, "message", "The download failed."))
        self.link_edit.setEnabled(True)
        self.paste_btn.setEnabled(True)
        if isinstance(exc, InvalidLinkError):
            self.dl_btn.setEnabled(False)
        else:
            self.dl_btn.setEnabled(True)

    def _show_in_folder(self) -> None:
        if self._target_path:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(self._target_path)])

    def _reset(self) -> None:
        self.link_edit.clear()
        self.link_edit.setEnabled(True)
        self.paste_btn.setEnabled(True)
        self.dl_btn.setEnabled(False)
        self.hint.setText("")
        self.panel.hide()
        self.success_box.hide()
        self._target_path = None

    def _go_home(self) -> None:
        self.ctx.go("home")

    def is_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()


class DownloadPanel(QWidget):
    """The download animation: a box that fills with terracotta from the bottom."""

    def __init__(self) -> None:
        super().__init__()
        self._frac = 0.0          # fill fraction
        self._state = "idle"      # idle | running | done | failed
        self._check_t = 0.0
        self._indeterminate = False
        self._sweep = 0.0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 8, 4, 8)
        lay.setSpacing(10)

        row = QHBoxLayout()
        self.art = _FillBox()
        self.art.setFixedSize(72, 72)
        row.addWidget(self.art)
        mid = QVBoxLayout()
        self.pct_lbl = QLabel("")
        self.pct_lbl.setFont(display_font(24))
        self.pct_lbl.setStyleSheet(f"color: {T.INK};")
        mid.addWidget(self.pct_lbl)
        self.bytes_lbl = QLabel("")
        self.bytes_lbl.setFont(body_font(14))
        self.bytes_lbl.setStyleSheet(f"color: {T.INK};")
        mid.addWidget(self.bytes_lbl)
        row.addLayout(mid, 1)
        lay.addLayout(row)

        self.bar = ProgressBar()
        lay.addWidget(self.bar)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.setFixedHeight(140)

    def reset(self) -> None:
        self._state = "running"
        self._frac = 0.0
        self._check_t = 0.0
        self._indeterminate = True
        self.bar.set_indeterminate(True)
        self.pct_lbl.setText("Starting…")
        self.bytes_lbl.setText("")
        self.art.set_state("running", 0.0)
        from ..widgets import reduced_motion

        if not reduced_motion():
            self.timer.start(40)

    def on_progress(self, done: int, total: int, speed: float) -> None:
        self._indeterminate = total <= 0
        self.bar.set_indeterminate(self._indeterminate)
        if total > 0:
            frac = done / total
            self._frac = frac
            self.pct_lbl.setText(f"{int(frac * 100)}%")
            self.bytes_lbl.setText(
                f"{_fmt_bytes(done)} of {_fmt_bytes(total)} · {_fmt_bytes(speed)}/s")
        else:
            self.bytes_lbl.setText(f"{_fmt_bytes(done)} downloaded")
        self.art.set_state("running", self._frac)

    def finish(self) -> None:
        self._state = "done"
        self.timer.stop()
        self.bar.set_value(100)
        self.pct_lbl.setText("100%")
        self.bytes_lbl.setText("Saved")
        self.art.set_state("done", 1.0)
        self.art.bounce()

    def fail(self, message: str) -> None:
        self._state = "failed"
        self.timer.stop()
        self.bar.set_indeterminate(False)
        self.pct_lbl.setText("Couldn't download")
        self.bytes_lbl.setText(message)
        self.art.set_state("failed", self._frac)

    def _tick(self) -> None:
        if self._indeterminate:
            self._sweep = (self._sweep + 0.03) % 1.4
        self.art.update()


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


class _FillBox(QWidget):
    """Custom painted box filling bottom-up with terracotta; check mark on done."""

    def __init__(self) -> None:
        super().__init__()
        self._state = "idle"
        self._frac = 0.0
        self._bounce = 0.0
        self._check = 0.0

    def set_state(self, state: str, frac: float) -> None:
        self._state = state
        self._frac = max(self._frac, frac) if state == "running" else frac
        self.update()

    def bounce(self) -> None:
        from PySide6.QtCore import QVariantAnimation, QEasingCurve

        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(650)
        anim.setEasingCurve(QEasingCurve.OutBack)
        anim.valueChanged.connect(self._on_bounce)
        anim.start(QVariantAnimation.DeleteWhenStopped)

    def _on_bounce(self, v: float) -> None:
        self._bounce = float(v)
        self._check = self._bounce
        self.update()

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        dy = int(-4 * (1 - self._bounce)) if self._bounce > 0 else 0
        p.translate(0, dy)

        # tray
        p.setPen(QPen(QColor(T.INK), 2))
        p.drawLine(8, h - 10, w - 8, h - 10)
        # box outline
        box = QRect(12, 12, w - 24, h - 30)
        fill_h = int((box.height()) * self._frac)
        p.fillRect(box.adjusted(1, box.height() - fill_h, -1, -1), QColor(T.PRIMARY))
        p.drawRect(box)
        p.drawLine(12, box.top() + 10, w - 12, box.top() + 10)  # lid line
        # state marks
        if self._state == "done" and self._check > 0.6:
            pen = QPen(QColor(T.INK_DEEP), 4)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(24, 40, 32, 48)
            p.drawLine(32, 48, 48, 30)
        elif self._state == "failed":
            pm = icons.pixmap("error", 20, ink=T.DANGER, accent=T.DANGER)
            p.drawPixmap(box.center().x() - 10, box.center().y() - 10, pm)
        elif self._state == "running" and self._frac <= 0:
            arrow = icons.pixmap("download", 24)
            p.drawPixmap(box.center().x() - 12, box.center().y() - 12, arrow)
