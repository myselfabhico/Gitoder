"""Delete Repo: paginated list, search, red Delete per row, confirm modal."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from .. import theme as T
from ..dialogs import DeleteConfirmDialog, show_error_dialog
from ..widgets import (
    EmptyState,
    PaperSurface,
    RepoRow,
    SecondaryButton,
    SkeletonRow,
    body_font,
    display_font,
    micro_font,
    show_toast,
)
from ...core.errors import CancelledError
from ...core.workers import DeleteRepoWorker, ListReposWorker

log = logging.getLogger("gitoder.ui.delete")


class DeleteRepoScreen(PaperSurface):
    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        self._repos: list[dict] = []
        self._worker: ListReposWorker | None = None
        self._delete_worker: DeleteRepoWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(56, 28, 56, 32)
        root.setSpacing(12)

        self.title = QLabel("Delete a repository.")
        self.title.setFont(display_font(34))
        self.title.setStyleSheet(f"color: {T.INK};")
        root.addWidget(self.title)

        sub = QLabel("Choose carefully. Deleting is permanent.")
        sub.setFont(body_font(16))
        sub.setStyleSheet(f"color: {T.INK};")
        root.addWidget(sub)

        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search your repositories…")
        self.search.setFixedHeight(44)
        self.search.setAccessibleName("Search repositories")
        self.search.setStyleSheet(
            f"background: {T.SURFACE}; border: 1px solid {T.FOCUS};"
            f"border-radius: 3px; padding: 0 12px; color: {T.INK};"
        )
        self.search.textChanged.connect(self._apply_filter)
        search_row.addWidget(self.search, 1)
        self.reload_btn = SecondaryButton("Refresh", icon_name="refresh")
        self.reload_btn.clicked.connect(self.reload)
        search_row.addWidget(self.reload_btn)
        root.addLayout(search_row)

        self.list_host = QVBoxLayout()
        root.addLayout(self.list_host)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.list_container = QWidget()
        self.rows_lay = QVBoxLayout(self.list_container)
        self.rows_lay.setContentsMargins(0, 4, 0, 4)
        self.rows_lay.setSpacing(10)
        self.scroll.setWidget(self.list_container)
        root.addWidget(self.scroll, 1)

        self.empty = EmptyState("No repositories found.",
                                "Create one from the Home screen — or refresh.")
        self.empty.hide()
        root.addWidget(self.empty)

        root.addSpacing(4)
        bottom = QHBoxLayout()
        self.back = SecondaryButton("Home", icon_name="back")
        bottom.addWidget(self.back)
        bottom.addStretch(1)
        root.addLayout(bottom)
        self.back.clicked.connect(self._go_home)

    # ------------------------------------------------------------ data

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        if not self._repos and self._worker is None:
            self.reload()

    def reload(self) -> None:
        if self.ctx.client is None:
            return  # not signed in; navigation should not reach here
        self._set_loading(True)
        self._worker = ListReposWorker(self.ctx.client)
        self._worker.signals.succeeded.connect(self._on_loaded)
        self._worker.signals.failed.connect(self._on_failed)
        self.ctx.track(self._worker)
        self._worker.start()

    def _set_loading(self, on: bool) -> None:
        self._clear_rows()
        if on:
            for _ in range(6):
                self.rows_lay.addWidget(SkeletonRow())
        self.scroll.setVisible(not on)
        self.empty.setVisible(False)

    def _clear_rows(self) -> None:
        while self.rows_lay.count():
            item = self.rows_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _on_loaded(self, repos: list) -> None:
        self._repos = list(repos)
        self._worker = None
        self._render_rows()

    def _on_failed(self, exc) -> None:
        self._worker = None
        self._set_loading(False)
        show_error_dialog(self.window(), exc)

    def _apply_filter(self, _text: str) -> None:
        self._render_rows()

    def _render_rows(self) -> None:
        self._clear_rows()
        needle = self.search.text().strip().lower()
        visible = [r for r in self._repos if needle in r.get("name", "").lower()]
        if not visible:
            self.scroll.setVisible(False)
            self.empty.setVisible(True)
            if needle:
                self.empty.findChild(QLabel).setText(f"No repositories match “{needle}”.")
            return
        self.scroll.setVisible(True)
        self.empty.setVisible(False)
        for repo in visible:
            row = RepoRow(repo, kind="delete")
            row.deleteRequested.connect(self._confirm_delete)
            self.rows_lay.addWidget(row)
        self.rows_lay.addStretch(1)

    # ------------------------------------------------------------ delete

    def _confirm_delete(self, row: RepoRow) -> None:
        repo = row.repo
        dlg = DeleteConfirmDialog(self.window(), repo.get("full_name", repo.get("name", "")))
        if dlg.exec() != DeleteConfirmDialog.Accepted:
            return  # Cancel: nothing happens
        # Confirm: loading state on the button, then API call
        confirm_btn = self._danger_button_of(row)
        if confirm_btn is None:
            return
        confirm_btn.set_loading(True, "Deleting")
        self.ctx.set_busy(True)
        self._delete_worker = DeleteRepoWorker(self.ctx.client,
                                               repo["owner"]["login"], repo["name"])
        self._delete_worker.signals.succeeded.connect(lambda _r, r=row: self._on_deleted(r))
        self._delete_worker.signals.failed.connect(lambda e, r=row, b=confirm_btn:
                                                   self._on_delete_failed(e, r, b))
        self.ctx.track(self._delete_worker)
        self._delete_worker.start()

    def _danger_button_of(self, row: RepoRow) -> QWidget:
        from ..widgets import DangerButton

        btns = row.findChildren(DangerButton)
        return btns[0] if btns else None

    def _on_deleted(self, row: RepoRow) -> None:
        self.ctx.set_busy(False)
        repo = row.repo
        self._repos = [r for r in self._repos
                       if r.get("id") != repo.get("id")]
        name = repo.get("name", "")
        # animate the row out, then re-render
        def finish() -> None:
            self._render_rows()
            show_toast(self, f"Deleted {name}", "success")

        from ..widgets import reduced_motion

        if reduced_motion():
            finish()
        else:
            from PySide6.QtCore import QPropertyAnimation, QEasingCurve

            anim = QPropertyAnimation(row, b"maximumHeight")
            anim.setStartValue(row.height())
            anim.setEndValue(0)
            anim.setDuration(240)
            anim.setEasingCurve(QEasingCurve.InCubic)
            anim.finished.connect(finish)
            anim.start(QPropertyAnimation.DeleteWhenStopped)

    def _on_delete_failed(self, exc, row, btn) -> None:
        self.ctx.set_busy(False)
        btn.set_loading(False)
        show_error_dialog(self.window(), exc)

    def _go_home(self) -> None:
        self.ctx.go("home")
