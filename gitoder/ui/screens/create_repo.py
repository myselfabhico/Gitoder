"""Create Repo wizard: 1 Details -> 2 Folder -> 3 Push -> Result."""

from __future__ import annotations

import logging
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from .. import theme as T
from ..dialogs import show_error_dialog
from ..widgets import (
    FormField,
    NoticeBanner,
    PaperSurface,
    PathStrip,
    PrimaryButton,
    ProgressBar,
    SecondaryButton,
    SegmentedControl,
    StepIndicator,
    ToggleSwitch,
    body_font,
    display_font,
    micro_font,
    section_font,
    show_toast,
    stagger_entrance,
)
from ...core.errors import CancelledError, GitoderError
from ...core.uploader import validate_repo_name
from ...core.workers import (
    CreateRepoWorker,
    FetchOptionsWorker,
    LongWorker,
    PushWorker,
    ScanWorker,
)

log = logging.getLogger("gitoder.ui.create")

STEP_TITLES = ["Details", "Folder", "Push"]


class CreateRepoScreen(PaperSurface):
    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        self._scan = None
        self._warnings_ack = False
        self._repo: dict | None = None
        self._push_worker: PushWorker | None = None
        self._name_timer = QTimer(self)
        self._name_timer.setSingleShot(True)
        self._name_timer.setInterval(450)
        self._name_timer.timeout.connect(self._check_name)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(56, 28, 56, 32)
        outer.setSpacing(12)

        self.title = QLabel("Create a repository.")
        self.title.setFont(display_font(34))
        self.title.setStyleSheet(f"color: {T.INK};")
        outer.addWidget(self.title)
        self.steps = StepIndicator(STEP_TITLES, 0)
        outer.addWidget(self.steps)

        self.pages = QStackedLayout()
        self.pages.addWidget(self._build_details_page())
        self.pages.addWidget(self._build_folder_page())
        self.pages.addWidget(self._build_push_page())
        self.pages.addWidget(self._build_result_page())
        outer.addLayout(self.pages, 1)

    # ------------------------------------------------------------ page 1

    def _build_details_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(14)

        self.name_field = FormField("Repository name", "my-project")
        self.name_field.textChanged.connect(self._on_name_changed)
        lay.addWidget(self.name_field)

        desc = FormField("Description (optional)", "What is this project about?")
        lay.addWidget(desc)
        self.desc_field = desc

        vis_cap = QLabel("VISIBILITY")
        vis_cap.setFont(micro_font())
        vis_cap.setStyleSheet(f"color: {T.INK};")
        lay.addWidget(vis_cap)
        self.vis_seg = SegmentedControl(
            [("private", "Private", "lock"), ("public", "Public", "globe")], "private")
        self.vis_seg.changed.connect(self._on_vis_changed)
        lay.addWidget(self.vis_seg)
        self.vis_hint = QLabel()
        self.vis_hint.setFont(body_font(14))
        self.vis_hint.setStyleSheet(f"color: {T.INK};")
        self._on_vis_changed("private")
        lay.addWidget(self.vis_hint)

        readme_row = QHBoxLayout()
        self.readme_toggle = ToggleSwitch(True)
        self.readme_toggle.setAccessibleName("Add a README")
        readme_row.addWidget(self.readme_toggle)
        readme_lbl = QLabel("Add a README")
        readme_lbl.setFont(body_font(15, QFont.DemiBold))
        readme_lbl.setStyleSheet(f"color: {T.INK};")
        readme_row.addWidget(readme_lbl)
        readme_hint = QLabel("Adds a README.md with your repo name.")
        readme_hint.setFont(body_font(13))
        readme_hint.setStyleSheet(f"color: {T.INK};")
        readme_row.addWidget(readme_hint)
        readme_row.addStretch(1)
        lay.addLayout(readme_row)

        picks = QHBoxLayout()
        picks.setSpacing(16)
        lic_col = QVBoxLayout()
        lic_cap = QLabel("LICENSE")
        lic_cap.setFont(micro_font())
        lic_cap.setStyleSheet(f"color: {T.INK};")
        lic_col.addWidget(lic_cap)
        self.license_combo = QComboBox()
        self.license_combo.setFixedHeight(44)
        self.license_combo.setAccessibleName("License")
        lic_col.addWidget(self.license_combo)
        picks.addLayout(lic_col, 1)

        gi_col = QVBoxLayout()
        gi_cap = QLabel(".GITIGNORE TEMPLATE")
        gi_cap.setFont(micro_font())
        gi_cap.setStyleSheet(f"color: {T.INK};")
        gi_col.addWidget(gi_cap)
        self.gitignore_combo = QComboBox()
        self.gitignore_combo.setFixedHeight(44)
        self.gitignore_combo.setEditable(True)
        self.gitignore_combo.setInsertPolicy(QComboBox.NoInsert)
        self.gitignore_combo.setAccessibleName("Gitignore template")
        gi_col.addWidget(self.gitignore_combo)
        picks.addLayout(gi_col, 1)
        lay.addLayout(picks)

        lay.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.next_btn = PrimaryButton("Next")
        self.next_btn.setFixedWidth(160)
        self.next_btn.setEnabled(False)
        row.addWidget(self.next_btn)
        lay.addLayout(row)

        self.next_btn.clicked.connect(self._to_folder)
        return w

    def _on_name_changed(self, text: str) -> None:
        err = validate_repo_name(text)
        if err:
            self.name_field.set_status(False, err)
            self.next_btn.setEnabled(False)
            return
        self.name_field.set_status(True, "Checking if the name is free…")
        self._name_timer.start()

    def _check_name(self) -> None:
        name = self.name_field.text().strip()
        if not name or validate_repo_name(name):
            return
        login = (self.ctx.user or {}).get("login", "")
        if not login:
            self.next_btn.setEnabled(True)   # cannot check; let GitHub decide
            return
        self._name_worker = _NameCheckWorker(self.ctx.client, login, name)
        self._name_worker.signals.succeeded.connect(self._on_name_checked)
        self._name_worker.signals.failed.connect(lambda _e: self._on_name_checked(None))
        self.ctx.track(self._name_worker)
        self._name_worker.start()

    def _on_name_checked(self, free: object) -> None:
        current = self.name_field.text().strip()
        if free is None:
            self.name_field.set_status(False, "Couldn't check availability — continue and "
                                              "GitHub will confirm.")
            return
        if bool(free):
            self.name_field.set_status(True, "Name is available")
            self.next_btn.setEnabled(True)
        else:
            self.name_field.set_status(False, "You already have a repo with that name.")

    def _on_vis_changed(self, value: str) -> None:
        self.vis_hint.setText(
            "Only you can see this repository." if value == "private"
            else "Anyone on the internet can see this repository."
        )

    def refresh_options(self) -> None:
        if self.license_combo.count() == 0:
            self._options_worker = FetchOptionsWorker(self.ctx.client)
            self._options_worker.signals.succeeded.connect(self._on_options)
            self._options_worker.signals.failed.connect(lambda _e: self._on_options(None))
            self.ctx.track(self._options_worker)
            self._options_worker.start()

    def _on_options(self, payload: object) -> None:
        if not payload:
            payload = {"licenses": FetchOptionsWorker.FALLBACK_LICENSES,
                       "gitignores": FetchOptionsWorker.FALLBACK_GITIGNORE}
        self.license_combo.clear()
        self.license_combo.addItem("None", None)
        for lic in payload["licenses"]:
            self.license_combo.addItem(lic.get("name", lic.get("key", "?")),
                                       lic.get("key"))
        self.gitignore_combo.clear()
        self.gitignore_combo.addItem("None", None)
        for gi in payload["gitignores"]:
            self.gitignore_combo.addItem(gi if isinstance(gi, str) else str(gi), gi)

    # ------------------------------------------------------------ page 2

    def _build_folder_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(14)

        head = QLabel("Pick the project folder you want to upload.")
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
        row.addWidget(self.back1)
        row.addStretch(1)
        self.push_btn = PrimaryButton("Push")
        self.push_btn.setFixedWidth(180)
        self.push_btn.setEnabled(False)
        row.addWidget(self.push_btn)
        lay.addLayout(row)

        self.browse_btn.clicked.connect(self._browse)
        self.back1.clicked.connect(lambda: self.goto(0))
        self.push_btn.clicked.connect(self._begin_push)
        return w

    def _browse(self) -> None:
        start = str(Path.home() / "Desktop")
        folder = QFileDialog.getExistingDirectory(self, "Choose your project folder", start)
        if not folder:
            return
        self.path_strip.set_path(folder)
        self.scan_summary.setText("Reading folder…")
        self.preview.setText("")
        self._scan = None
        self.push_btn.setEnabled(False)
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
        self._warnings_ack = False
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
            self.warnings_banner.show_text(
                "Cannot push: " + " ".join(scan.blocking), tone="blocking")
            self.warnings_banner.show()
            self.ack_row.hide()
            self.push_btn.setEnabled(False)
        elif scan.warnings:
            self.warnings_banner.show_text(" ".join(scan.warnings), tone="warning")
            self.warnings_banner.show()
            self.ack_row.show()
            self.ack_toggle.setEnabled(True)
            self.push_btn.setEnabled(False)
        else:
            self.warnings_banner.hide()
            self.ack_row.hide()
            self.push_btn.setEnabled(True)

    def _on_ack(self, on: bool) -> None:
        self._warnings_ack = on
        self.push_btn.setEnabled(on and self._scan is not None)

    # ------------------------------------------------------------ page 3

    def _build_push_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(18)

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
        lay.addWidget(self.cancel_btn, 0, Qt.AlignLeft)

        self.partial_panel = QWidget()
        pp = QVBoxLayout(self.partial_panel)
        pp.setContentsMargins(0, 12, 0, 0)
        pp.setSpacing(12)
        pp_msg = QLabel("Your repository was created, but the upload didn't finish.")
        pp_msg.setFont(body_font(16, QFont.DemiBold))
        pp_msg.setStyleSheet(f"color: {T.INK};")
        pp.addWidget(pp_msg)
        pp_row = QHBoxLayout()
        self.retry_btn = PrimaryButton("Retry upload")
        pp_row.addWidget(self.retry_btn)
        self.open_after_fail = SecondaryButton("Open repo on GitHub", icon_name="external")
        pp_row.addWidget(self.open_after_fail)
        self.home_after_fail = SecondaryButton("Back to Home")
        pp_row.addWidget(self.home_after_fail)
        pp_row.addStretch(1)
        pp.addLayout(pp_row)
        self.partial_panel.hide()
        lay.addWidget(self.partial_panel)
        lay.addStretch(1)

        self.cancel_btn.clicked.connect(self._cancel_push)
        self.retry_btn.clicked.connect(self._retry_upload)
        self.open_after_fail.clicked.connect(self._open_repo)
        self.home_after_fail.clicked.connect(self._go_home)
        return w

    # ---------------------------------------------------------- result

    def _build_result_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(14)

        self.check_anim = _CheckDraw()
        self.check_anim.setFixedSize(84, 84)
        lay.addWidget(self.check_anim, 0, Qt.AlignHCenter)

        self.result_head = QLabel("Your project is live on GitHub.")
        self.result_head.setFont(display_font(30))
        self.result_head.setStyleSheet(f"color: {T.INK};")
        lay.addWidget(self.result_head, 0, Qt.AlignHCenter)

        self.result_summary = QLabel("")
        self.result_summary.setFont(body_font(15))
        self.result_summary.setAlignment(Qt.AlignCenter)
        self.result_summary.setWordWrap(True)
        self.result_summary.setStyleSheet(f"color: {T.INK};")
        lay.addWidget(self.result_summary)

        row = QHBoxLayout()
        row.addStretch(1)
        self.open_btn = PrimaryButton("Open on GitHub", )
        self.open_btn.setIcon(icons.icon("external", 18, ink=T.INK))
        row.addWidget(self.open_btn)
        self.copy_btn = SecondaryButton("Copy link", icon_name="copy")
        row.addWidget(self.copy_btn)
        self.home_btn = SecondaryButton("Back to Home")
        row.addWidget(self.home_btn)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)

        self.open_btn.clicked.connect(self._open_repo)
        self.copy_btn.clicked.connect(self._copy_link)
        self.home_btn.clicked.connect(self._go_home)
        return w

    # ------------------------------------------------------------ flow

    def goto(self, i: int) -> None:
        self.pages.setCurrentIndex(i)
        self.steps.set_current(min(i, 2))
        if i == 0:
            self.refresh_options()
        self.ctx.set_busy(self.pages.currentIndex() == 2 and self._pushing())

    def _pushing(self) -> bool:
        return self._push_worker is not None and self._push_worker.isRunning()

    def can_go_back(self) -> bool:
        idx = self.pages.currentIndex()
        if idx == 2 and self._pushing():
            return False
        return True

    def request_back(self) -> None:
        idx = self.pages.currentIndex()
        if idx == 0:
            self._go_home()
        elif idx in (1, 2, 3):
            if idx == 2 and self._pushing():
                return
            self.goto(0)

    def _to_folder(self) -> None:
        self.goto(1)

    def _begin_push(self) -> None:
        if self._scan is None:
            return
        name = self.name_field.text().strip()
        payload: dict = {"name": name, "private": self.vis_seg.value() == "private"}
        description = self.desc_field.text().strip()
        if description:
            payload["description"] = description
        readme = self.readme_toggle.isChecked()
        lic = self.license_combo.currentData()
        gi = self.gitignore_combo.currentData()
        if readme or lic or gi:
            payload["auto_init"] = True
        if lic:
            payload["license_template"] = lic
        if gi:
            payload["gitignore_template"] = gi
        self._pending_payload = payload

        self.goto(2)
        self.push_stage.setText("Creating repository…")
        self.push_bar.set_indeterminate(True)
        self.ctx.set_busy(True)
        self._create_worker = CreateRepoWorker(self.ctx.client, payload)
        self._create_worker.signals.succeeded.connect(self._on_repo_created)
        self._create_worker.signals.failed.connect(self._on_create_failed)
        self.ctx.track(self._create_worker)
        self._create_worker.start()

    def _on_repo_created(self, repo: dict) -> None:
        self._repo = repo
        self._start_push()

    def _on_create_failed(self, exc) -> None:
        self.ctx.set_busy(False)
        show_error_dialog(self.window(), exc)
        self.goto(0)

    def _start_push(self) -> None:
        self.push_stage.setText("Reading files…")
        self.push_bar.set_indeterminate(True)
        self._push_worker = PushWorker(self.ctx.client, self._scan, self._repo, mode="create")
        self._push_worker.signals.stage.connect(self.push_stage.setText)
        self._push_worker.signals.progress.connect(self._on_progress)
        self._push_worker.signals.succeeded.connect(self._on_pushed)
        self._push_worker.signals.failed.connect(self._on_push_failed)
        self.ctx.track(self._push_worker)
        self._push_worker.start()

    def _retry_upload(self) -> None:
        if self._repo is None:
            return
        self.partial_panel.hide()
        self._start_push()

    def _on_progress(self, done_f: int, total_f: int, done_b: int, total_b: int) -> None:
        if total_f > 0:
            pct = 100.0 * done_b / max(1, total_b)
            self.push_bar.set_value(pct)
            self.push_detail.setText(f"Uploading files {done_f} / {total_f}")

    def _on_pushed(self, result: dict) -> None:
        self.ctx.set_busy(False)
        vis = "Private" if (self._repo or {}).get("private") else "Public"
        lic = self.license_combo.currentText()
        gi = self.gitignore_combo.currentText()
        readme = "on" if self.readme_toggle.isChecked() else "off"
        # auto_init means GitHub generated starting files (README/license/.gitignore)
        auto_init = bool((getattr(self, "_pending_payload", {}) or {}).get("auto_init"))
        self.result_summary.setText(
            f"{result['files']} files uploaded · {vis}"
            f" · License: {lic} · README: {readme} · .gitignore: {gi}"
            + ("\nGitHub's starting files were kept where your folder didn't include its own."
               if auto_init else "")
        )
        self.check_anim.start_anim()
        self.pages.setCurrentIndex(3)
        self.steps.set_current(2)
        show_toast(self, "Pushed and verified", "success")

    def _on_push_failed(self, exc) -> None:
        self.ctx.set_busy(False)
        if isinstance(exc, CancelledError):
            self.push_stage.setText("Upload cancelled.")
            self.push_detail.setText(
                "Nothing was changed on GitHub." if self._repo is None
                else "The repository exists, but the upload stopped. Nothing extra was added."
            )
            self.partial_panel.show()
            return
        if self._repo is not None and not isinstance(exc, GitoderError):
            pass
        if self._repo is not None:
            # repo exists: never recreate, offer retry
            self.push_stage.setText(getattr(exc, "title", "Upload didn't finish"))
            self.push_detail.setText(getattr(exc, "message", ""))
            self.partial_panel.show()
        else:
            show_error_dialog(self.window(), exc)
            self.goto(0)

    def _cancel_push(self) -> None:
        if self._push_worker is not None:
            self._push_worker.cancel()

    def _open_repo(self) -> None:
        if self._repo:
            webbrowser.open(self._repo.get("html_url", ""))

    def _copy_link(self) -> None:
        from PySide6.QtWidgets import QApplication

        if self._repo:
            QApplication.clipboard().setText(self._repo.get("html_url", ""))
            show_toast(self, "Link copied")

    def _go_home(self) -> None:
        self.ctx.go("home")


class _NameCheckWorker(LongWorker):
    """GET /repos/owner/name -> True when the name is free (404)."""

    def __init__(self, client, login: str, name: str) -> None:
        super().__init__()
        self.client = client
        self.login = login
        self.name = name

    def _run(self) -> bool:
        from ...core.errors import NotFoundError

        try:
            info = self.client.get_repo(self.login, self.name)
        except NotFoundError:
            return True
        return info is None


class _CheckDraw(QWidget):
    """Calm celebratory check mark that draws itself."""

    def __init__(self) -> None:
        super().__init__()
        self._t = 0.0

    def start_anim(self) -> None:
        from PySide6.QtCore import QVariantAnimation, QEasingCurve

        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(700)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(self._set)
        anim.start(QVariantAnimation.DeleteWhenStopped)

    def _set(self, v: float) -> None:
        self._t = float(v)
        self.update()

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(T.CTA_SOFT))
        p.setPen(QPen(QColor(T.INK), 2))
        p.drawEllipse(4, 4, 76, 76)
        pen = QPen(QColor(T.INK_DEEP), 6)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        # polyline (20,40) -> (36,56) -> (62,26) drawn progressively
        pts = [(20, 40), (36, 56), (62, 26)]
        segs = [(pts[0], pts[1]), (pts[1], pts[2])]
        total = 22.6 + 40.0
        drawn = total * self._t
        acc = 0.0
        import math

        for a, b in segs:
            seg_len = math.hypot(b[0] - a[0], b[1] - a[1])
            if drawn <= acc:
                break
            frac = min(1.0, (drawn - acc) / seg_len)
            x2 = a[0] + (b[0] - a[0]) * frac
            y2 = a[1] + (b[1] - a[1]) * frac
            p.drawLine(int(a[0]), int(a[1]), int(x2), int(y2))
            acc += seg_len
