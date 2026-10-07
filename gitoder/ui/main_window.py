"""QMainWindow: stack navigation, slim top bar (Home, title, avatar, Sign out), busy lock."""

from __future__ import annotations

import logging
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import icons
from . import theme as T
from ..core.workers import LongWorker
from .widgets import (
    AvatarLabel,
    LinkButton,
    SecondaryButton,
    body_font,
    display_font,
    show_toast,
)

log = logging.getLogger("gitoder.ui.main_window")

SCREEN_TITLES = {
    "home": "Gitoder",
    "create": "Create Repo",
    "delete": "Delete Repo",
    "update": "Update Repo",
    "download": "Download Repo",
    "signin": "Sign in",
}
CARD_KEYS = ["create", "delete", "update", "download"]   # HomeScreen card order


class AppContext:
    """Shared application context passed to every screen."""

    def __init__(self, window: "MainWindow") -> None:
        self.window = window

    @property
    def client(self):
        return self.window.client

    @property
    def store(self):
        return self.window.store

    @property
    def user(self):
        return self.window.user

    def set_signed_in(self, user: dict, token: str) -> None:
        self.window.on_signed_in(user, token)

    def go(self, target) -> None:
        self.window.navigate(target)

    def set_busy(self, busy: bool) -> None:
        self.window.set_busy(busy)

    def track(self, worker) -> None:
        self.window.track_worker(worker)

    def fetch_avatar(self, url: str, callback) -> None:
        self.window.fetch_avatar(url, callback)


class MainWindow(QMainWindow):
    def __init__(self, client, store, user: dict | None, *, version: str = "1.0") -> None:
        super().__init__()
        self.client = client
        self.store = store
        self.user = user
        self.version = version
        self._busy = False
        self._tracked: list = []
        self._screens: dict = {}
        self._avatar_url: str | None = None
        self._avatar_bytes: bytes | None = None

        self.setWindowTitle("Gitoder")
        self.setWindowIcon(icons.app_icon())
        self.setStyleSheet(T.APP_QSS)
        self.resize(1280, 800)
        self.setMinimumSize(1024, 680)

        self.topbar = self._build_topbar()
        self.stack = QStackedWidget()

        self.root = QWidget()
        root_lay = QVBoxLayout(self.root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)
        root_lay.addWidget(self.topbar)
        root_lay.addWidget(self.stack)
        self.setCentralWidget(self.root)

        from .screens.signin import SignInScreen
        from .screens.home import HomeScreen

        self.signin_screen = SignInScreen(self._ctx())
        self.home_screen = HomeScreen(self._ctx())
        self.stack.addWidget(self.signin_screen)
        self.stack.addWidget(self.home_screen)

        if self.user is None:
            self.stack.setCurrentWidget(self.signin_screen)
            self.topbar.setVisible(False)
        else:
            self.navigate("home")

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(56)
        bar.setStyleSheet(f"QFrame {{ background: {T.BG}; }}")
        tb = QHBoxLayout(bar)
        tb.setContentsMargins(24, 8, 24, 8)
        tb.setSpacing(12)
        self.home_btn = SecondaryButton("Home", icon_name="back")
        self.home_btn.setFixedHeight(36)
        self.home_btn.clicked.connect(self._go_home_clicked)
        tb.addWidget(self.home_btn)
        self.title_lbl = QLabel("Gitoder")
        self.title_lbl.setFont(display_font(18))
        self.title_lbl.setStyleSheet(f"color: {T.INK};")
        tb.addWidget(self.title_lbl)
        tb.addStretch(1)
        self.avatar = AvatarLabel(32)
        tb.addWidget(self.avatar)
        self.user_lbl = QLabel("")
        self.user_lbl.setFont(body_font(14, QFont.Medium))
        self.user_lbl.setStyleSheet(f"color: {T.INK};")
        tb.addWidget(self.user_lbl)
        self.signout = LinkButton("Sign out")
        self.signout.clicked.connect(self._sign_out)
        tb.addWidget(self.signout)
        return bar

    def _ctx(self) -> AppContext:
        return AppContext(self)

    # ------------------------------------------------------- navigation

    def navigate(self, target) -> None:
        if self._busy:
            show_toast(self, "Please wait for the current operation to finish.")
            return
        if self.user is None:
            self.stack.setCurrentWidget(self.signin_screen)
            self.topbar.setVisible(False)
            self.title_lbl.setText(SCREEN_TITLES["signin"])
            return
        key = target.value if hasattr(target, "value") else target
        if isinstance(key, int):           # card index from HomeScreen
            key = CARD_KEYS[key] if 0 <= key < len(CARD_KEYS) else "home"
        key = key if isinstance(key, str) else "home"
        if key == "home":
            self.topbar.setVisible(True)
            self._update_user_pill()
            self.home_screen.refresh_user()
            self.stack.setCurrentWidget(self.home_screen)
            self.title_lbl.setText("Gitoder")
            self.home_btn.setEnabled(False)
            return
        screen = self._get_screen(key)
        self.topbar.setVisible(True)
        self._update_user_pill()
        self.stack.setCurrentWidget(screen)
        self.title_lbl.setText(SCREEN_TITLES.get(key, "Gitoder"))
        self.home_btn.setEnabled(not self._busy)

    def _update_user_pill(self) -> None:
        """Keep the topbar username + avatar in sync with the signed-in user."""
        user = self.user or {}
        self.user_lbl.setText(user.get("login", ""))
        self.avatar.set_initial(user.get("name") or user.get("login", "G"))
        av = user.get("avatar_url")
        if av:
            self.fetch_avatar(av, self.avatar.set_image_bytes)

    def _get_screen(self, key: str):
        if key not in self._screens:
            screen = self._create_screen(key)
            self._screens[key] = screen
            self.stack.addWidget(screen)
        return self._screens[key]

    def _create_screen(self, key: str):
        if key == "create":
            from .screens.create_repo import CreateRepoScreen

            return CreateRepoScreen(self._ctx())
        if key == "delete":
            from .screens.delete_repo import DeleteRepoScreen

            return DeleteRepoScreen(self._ctx())
        if key == "update":
            from .screens.update_repo import UpdateRepoScreen

            return UpdateRepoScreen(self._ctx())
        if key == "download":
            from .screens.download_repo import DownloadRepoScreen

            return DownloadRepoScreen(self._ctx())
        raise KeyError(key)

    # ------------------------------------------------------------- state

    def _go_home_clicked(self) -> None:
        if self._busy:
            show_toast(self, "Please wait for the current operation to finish.")
            return
        self.navigate("home")

    def on_signed_in(self, user: dict, token: str) -> None:
        from ..core.github_client import GithubClient

        self.client = GithubClient(token)
        self.user = user
        self.navigate("home")   # navigate already refreshes the user pill
        show_toast(self, f"Connected as {user.get('login', '')}", "success")

    def _sign_out(self) -> None:
        if self._busy:
            show_toast(self, "Please wait for the current operation to finish.")
            return
        self.store.clear()
        self.user = None
        self.client = None
        self._avatar_url = None
        self._avatar_bytes = None
        self.avatar.set_initial("?")
        self.user_lbl.setText("")
        self.navigate("signin")

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        current = self.stack.currentWidget()
        on_home = current is self.home_screen
        self.home_btn.setEnabled(not busy and not on_home)
        self.signout.setEnabled(not busy)
        for w in self._screens.values():
            back_btn = getattr(w, "back", None) or getattr(w, "back0", None) \
                or getattr(w, "back1", None) or getattr(w, "back2", None)
            if back_btn is not None:
                back_btn.setEnabled(not busy)

    def track_worker(self, worker) -> None:
        self._tracked.append(worker)
        if len(self._tracked) > 40:
            self._tracked = [w for w in self._tracked if w.isRunning()] or self._tracked[-1:]

    def fetch_avatar(self, url: str, callback) -> None:
        if self.client is None:
            return
        if url and url == self._avatar_url and self._avatar_bytes:
            callback(self._avatar_bytes)          # serve from cache
            return
        try:
            w = AvatarWorker(self.client, url)
            w.signals.succeeded.connect(
                lambda data, u=url, cb=callback: self._on_avatar(u, cb, data))
            self.track_worker(w)
            w.start()
        except Exception:  # noqa: BLE001 - an avatar must never break navigation
            log.exception("Avatar fetch failed to start")

    def _on_avatar(self, url: str, callback, data) -> None:
        if data:
            self._avatar_url, self._avatar_bytes = url, data
        callback(data)

    def closeEvent(self, e) -> None:  # noqa: N802
        for w in self._tracked:
            try:
                w.cancel()
                w.wait(1500)
            except Exception:  # noqa: BLE001
                pass
        super().closeEvent(e)


class AvatarWorker(LongWorker):
    """Fetches the signed-in user's avatar bytes off the UI thread."""

    def __init__(self, client, url: str) -> None:
        super().__init__()
        self.client = client
        self.url = url

    def _run(self):
        return self.client.avatar_bytes(self.url)
