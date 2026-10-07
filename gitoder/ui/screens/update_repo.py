"""Update Repo wizard: 1 Select repo -> 2 Folder -> 3 Update -> Result."""

from __future__ import annotations

import logging
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from .. import theme as T
from ..dialogs import show_error_dialog
from ..widgets import (
    EmptyState,
    NoticeBanner,
    PaperSurface,
    PathStrip,
    PrimaryButton,
    ProgressBar,
    RepoRow,
    SecondaryButton,
    SkeletonRow,
    StepIndicator,
    body_font,
    display_font,
    section_font,
    show_toast,
)
from ...core.errors import CancelledError
from ...core.workers import ListReposWorker, PushWorker, ScanWorker

log = logging.getLogger("gitoder.ui.update")

STEP_TITLES = ["Select repo", "Folder", "Update"]


class UpdateRepoScreen(PaperSurface):
    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        self._repos: list[dict] = []
        self._selected: dict | None = None
        self._scan = None
        self._ack = False
        self._push_worker: PushWorker | None = None
        self._worker: ListReposWorker | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(56, 28, 56, 32)
        outer.setSpacing(12)

        self.title = QLabel("Update a repository.")
        self.title.setFont(display_font(34))
        self.title.setStyleSheet(f"color: {T.INK};")
        outer.addWidget(self.title)
        self.steps = StepIndicator(STEP_TITLES, 0)
        outer.addWidget(self.steps)

        self.stack = QStackedLayout()
        outer.addLayout(self.stack, 1)
        self.stack.addWidget(self._page_select())
        self.stack.addWidget(self._page_folder())
        self.stack.addWidget(self._page_review())
        self.stack.addWidget(self._page_result())

    # ------------------------------------------------------------ step 1

    def _page_select(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(12)

        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search your repositories…")
        self.search.setFixedHeight(44)
        self.search.setAccessibleName("Search repositories")
        self.search.setStyleSheet(
            f"background: {T.SURFACE}; border: 1px solid {T.FOCUS};"
            f"border-radius: 3px; padding: 0 12px; color: {T.INK};"
        )
        self.search.textChanged.connect(self._render_rows)
        search_row.addWidget(self.search, 1)
        self.reload_btn = SecondaryButton("Refresh", icon_name="refresh")
        self.reload_btn.clicked.connect(self.reload)
        search_row.addWidget(self.reload_btn)
        lay.addLayout(search_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.list_container = QWidget()
        self.rows_lay = QVBoxLayout(self.list_container)
        self.rows_lay.setContentsMargins(0, 4, 0, 4)
        self.rows_lay.setSpacing(10)
        self.scroll.setWidget(self.list_container)
        lay.addWidget(self.scroll, 1)

        self.empty = EmptyState("No repositories found.",
                                "Nothing to update yet — create one first.")
        self.empty.hide()
        lay.addWidget(self.empty)

        row = QHBoxLayout()
        self.back0 = SecondaryButton("Back")
        self.back0.clicked.connect(self._go_home)
        row.addWidget(self.back0)
        row.addStretch(1)
        self.next1 = PrimaryButton("Next")
        self.next1.setFixedWidth(160)
        self.next1.setEnabled(False)
        self.next1.clicked.connect(self._to_folder)
        row.addWidget(self.next1)
        lay.addLayout(row)
        return w

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

    def _render_rows(self) -> None:
        self._clear_rows()
        needle = self.search.text().strip().lower()
        visible = [r for r in self._repos if needle in r.get("name", "").lower()]
        if not visible:
            self.scroll.setVisible(False)
            self.empty.setVisible(True)
            return
        self.scroll.setVisible(True)
        self.empty.setVisible(False)
        for repo in visible:
            row = RepoRow(repo, kind="select")
            row.selected.connect(self._on_select)
            self.rows_lay.addWidget(row)
        self.rows_lay.addStretch(1)

    def _on_select(self, row: RepoRow) -> None:
        self._selected = row.repo
        for i in range(self.rows_lay.count()):
            w = self.rows_lay.itemAt(i).widget()
            if isinstance(w, RepoRow):
                w.set_selected(w is row)
        self.next1.setEnabled(True)

    def _to_folder(self) -> None:
        self.goto(1)

    # ------------------------------------------------------------ step 2

    def _page_folder(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(14)

        head = QLabel("Pick the folder with your latest project files.")
        head.setFont(section_font(22))
        head.setStyleSheet(f"color: {T.INK};")
        lay.addWidget(head)

        browse_row = QHBoxLayout()
        self.browse_btn = SecondaryButton("Browse files", icon_name="folder")
        self.browse_btn.setFixedHeight(52)
        browse_row.addWidget(self.browse_btn)
        browse_row.addStretch(1)
        lay.addLayout(browse_row)

        self.path_strip = PathStrip()
        lay.addWidget(self.path_strip)

        self.scan_summary = QLabel("No folder selected yet.")
        self.scan_summary.setFont(body_font(15))
        self.scan_summary.setStyleSheet(f"color: {T.INK};")
        lay.addWidget(self.scan_summary)

        self.preview = QLabel("")
        self.preview.setFont(body_font(13))
        self.preview.setStyleSheet(f"color: {T.INK};")
        self.preview.setWordWrap(True)
        lay.addWidget(self.preview)

        self.warnings_banner = NoticeBanner("")
        self.warnings_banner.hide()
        lay.addWidget(self.warnings_banner)

        self.ack_row = QWidget()
        ack_lay = QHBoxLayout(self.ack_row)
        ack_lay.setContentsMargins(0, 0, 0, 0)
        from ..widgets import ToggleSwitch

        self.ack_toggle = ToggleSwitch(False)
        self.ack_toggle.setEnabled(False)
        self.ack_toggle.toggled.connect(self._on_ack)
        self.ack_toggle.setAccessibleName("I understand the warnings, continue")
        ack_lay.addWidget(self.ack_toggle)
        ack_lbl = QLabel("I understand, continue")
        ack_lbl.setFont(body_font(15, QFont.DemiBold))
        ack_lbl.setStyleSheet(f"color: {T.INK};")
        ack_lay.addWidget(ack_lbl)
        ack_lay.addStretch(1)
        self.ack_row.hide()
        lay.addWidget(self.ack_row)

        lay.addStretch(1)
        row = QHBoxLayout()
        self.back1 = SecondaryButton("Back")
        self.back1.clicked.connect(lambda: self.goto(0))
        row.addWidget(self.back1)
        row.addStretch(1)
        self.next2 = PrimaryButton("Next")
        self.next2.setFixedWidth(160)
        self.next2.setEnabled(False)
        self.next2.clicked.connect(self._to_review)
        row.addWidget(self.next2)
        lay.addLayout(row)

        self.browse_btn.clicked.connect(self._browse)
        return w

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose your project folder")
        if not folder:
            return
        self.path_strip.set_path(folder)
        self.scan_summary.setText("Reading folder…")
        self.preview.setText("")
        self._scan = None
        self.next2.setEnabled(False)
        self._scan_worker = ScanWorker(folder)
        self._scan_worker.signals.succeeded.connect(self._on_scanned)
        self._scan_worker.signals.failed.connect(self._on_scan_failed)
        self.ctx.track(self._scan_worker)
        self._scan_worker.start()

    def _on_scan_failed(self, exc) -> None:
        self.scan_summary.setText("That folder can't be read. Pick a different folder.")
        show_error_dialog(self.window(), exc)

    def _on_scanned(self, scan) -> None:
        self._scan = scan
        self._ack = False
        self.ack_toggle.blockSignals(True)
        self.ack_toggle.setChecked(False)
        self.ack_toggle.blockSignals(False)
        self.ack_toggle.setEnabled(False)

        if not scan.files:
            self.scan_summary.setText("No files to upload in that folder.")
        else:
            size_mb = scan.total_bytes / (1024 * 1024)
            self.scan_summary.setText(
                f"{len(scan.files)} files · {size_mb:.1f} MB ready to upload"
                + (f" · {scan.ignored_count} items ignored" if scan.ignored_count else "")
            )
        names = [f.rel_posix for f in scan.files[:8]]
        more = len(scan.files) - len(names)
        self.preview.setText(
            "\n".join(f"  {n}" for n in names) + (f"\n  … and {more} more" if more > 0 else "")
        )

        if scan.blocking:
            self.warnings_banner.show_text("Cannot push: " + " ".join(scan.blocking),
                                           tone="blocking")
            self.warnings_banner.show()
            self.ack_row.hide()
            self.next2.setEnabled(False)
        elif scan.warnings:
            self.warnings_banner.show_text(" ".join(scan.warnings), tone="warning")
            self.warnings_banner.show()
            self.ack_row.show()
            self.ack_toggle.setEnabled(True)
            self.next2.setEnabled(False)
        else:
            self.warnings_banner.hide()
            self.ack_row.hide()
            self.next2.setEnabled(True)

    def _on_ack(self, on: bool) -> None:
        self._ack = on
        self.next2.setEnabled(on and self._scan is not None)

    # ------------------------------------------------------------ step 3

    def _page_review(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(14)

        head = QLabel("Review and update.")
        head.setFont(section_font(22))
        head.setStyleSheet(f"color: {T.INK};")
        lay.addWidget(head)

        self.review_panel = QLabel("")
        self.review_panel.setFont(body_font(15))
        self.review_panel.setWordWrap(True)
        self.review_panel.setTextFormat(Qt.RichText)
        self.review_panel.setStyleSheet(
            f"background: {T.SURFACE}; border: 1px solid {T.LINE};"
            f"border-radius: 14px; padding: 16px; color: {T.INK};"
        )
        lay.addWidget(self.review_panel)

        self.replace_banner = NoticeBanner("")
        lay.addWidget(self.replace_banner)

        self.atomic_note = QLabel(
            "Because the replacement is one atomic commit, cancelling before the final "
            "step leaves your repository completely untouched."
        )
        self.atomic_note.setFont(body_font(14))
        self.atomic_note.setWordWrap(True)
        self.atomic_note.setStyleSheet(f"color: {T.INK};")
        lay.addWidget(self.atomic_note)

        lay.addStretch(1)
        row = QHBoxLayout()
        self.back2 = SecondaryButton("Back")
        self.back2.clicked.connect(lambda: self.goto(1))
        row.addWidget(self.back2)
        row.addStretch(1)
        self.update_btn = PrimaryButton("Update")
        self.update_btn.setFixedWidth(180)
        self.update_btn.clicked.connect(self._begin_update)
        row.addWidget(self.update_btn)
        lay.addLayout(row)
        return w

    def _to_review(self) -> None:
        repo = self._selected or {}
        scan = self._scan
        n = len(scan.files) if scan else 0
        size = (scan.total_bytes / (1024 * 1024)) if scan else 0
        self.review_panel.setText(
            f"<b>{repo.get('full_name', repo.get('name', ''))}</b>"
            f" · {'Private' if repo.get('private') else 'Public'}<br>"
            f"Folder: {self.path_strip.path()}<br>"
            f"{n} files · {size:.1f} MB"
        )
        self.replace_banner.show_text(
            f"All existing files in {repo.get('name', 'the repository')} will be "
            "replaced by the files from your folder.", tone="info")
        self.goto(2)

    def _begin_update(self) -> None:
        if self._selected is None or self._scan is None:
            return
        self.goto(3)
        self.ctx.set_busy(True)
        self.push_stage.setText("Reading files…")
        self.push_bar.set_indeterminate(True)
        self._push_worker = PushWorker(self.ctx.client, self._scan, self._selected,
                                       mode="update")
        self._push_worker.signals.stage.connect(self.push_stage.setText)
        self._push_worker.signals.progress.connect(self._on_progress)
        self._push_worker.signals.succeeded.connect(self._on_pushed)
        self._push_worker.signals.failed.connect(self._on_push_failed)
        self.ctx.track(self._push_worker)
        self._push_worker.start()

    # ---------------------------------------------------------- result

    def _page_result(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(14)

        self.push_stage = QLabel("Preparing…")
        self.push_stage.setFont(display_font(26))
        self.push_stage.setStyleSheet(f"color: {T.INK};")
        lay.addWidget(self.push_stage)

        self.push_detail = QLabel("")
        self.push_detail.setFont(body_font(15))
        self.push_detail.setStyleSheet(f"color: {T.INK};")
        lay.addWidget(self.push_detail)

        self.push_bar = ProgressBar()
        lay.addWidget(self.push_bar)

        self.cancel_btn = SecondaryButton("Cancel")
        self.cancel_btn.setFixedWidth(140)
        self.cancel_btn.clicked.connect(self._cancel_push)
        lay.addWidget(self.cancel_btn, 0, Qt.AlignLeft)

        self.done_head = QLabel("Your repo has been updated.")
        self.done_head.setFont(display_font(30))
        self.done_head.setStyleSheet(f"color: {T.INK};")
        self.done_head.hide()
        lay.addWidget(self.done_head)

        row = QHBoxLayout()
        row.addStretch(1)
        self.open_btn = PrimaryButton("Open on GitHub")
        self.open_btn.clicked.connect(self._open_repo)
        row.addWidget(self.open_btn)
        self.home_btn = SecondaryButton("Back to Home")
        self.home_btn.clicked.connect(self._go_home)
        row.addWidget(self.home_btn)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)

        self.result_row = row
        for a in (self.done_head, self.open_btn, self.home_btn):
            a.hide()
        return w

    # ------------------------------------------------------------ flow

    def goto(self, i: int) -> None:
        self.stack.setCurrentIndex(i)
        self.steps.set_current(min(i, 2))
        if i == 0 and not self._repos and (self._worker is None or not self._worker.isRunning()):
            self.reload()
        if i != 3:
            for a in (self.done_head, self.open_btn, self.home_btn):
                a.hide()
            self.push_stage.show()
            self.push_bar.show()
            self.cancel_btn.show()

    def _on_progress(self, done_f: int, total_f: int, done_b: int, total_b: int) -> None:
        if total_f > 0:
            self.push_bar.set_value(100.0 * done_b / max(1, total_b))
            self.push_detail.setText(f"Uploading files {done_f} / {total_f}")

    def _on_pushed(self, result: dict) -> None:
        self.ctx.set_busy(False)
        self.push_stage.hide()
        self.push_detail.setText(
            f"{result['files']} files · branch {result.get('branch', 'main')} · verified")
        self.push_bar.set_value(100)
        self.done_head.show()
        self.open_btn.show()
        self.home_btn.show()
        self.cancel_btn.hide()
        show_toast(self, "Update pushed and verified", "success")

    def _on_push_failed(self, exc) -> None:
        self.ctx.set_busy(False)
        if isinstance(exc, CancelledError):
            self.push_stage.setText("Update cancelled.")
            self.push_detail.setText(
                "Your repository was left completely untouched — the replacement "
                "never went through.")
            return
        show_error_dialog(self.window(), exc)
        self.push_stage.setText("Update didn't finish.")
        self.push_detail.setText(getattr(exc, "message", ""))

    def _cancel_push(self) -> None:
        if self._push_worker is not None:
            self._push_worker.cancel()

    def _open_repo(self) -> None:
        if self._selected:
            webbrowser.open(self._selected.get("html_url", ""))

    def _go_home(self) -> None:
        self.ctx.go("home")
