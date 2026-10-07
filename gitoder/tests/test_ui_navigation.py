"""UI regression tests: sign-in → Home navigation, avatar fetch, font loading.

Offscreen (QT_QPA_PLATFORM=offscreen) so the suite runs headless on CI and in
the build sandbox. These tests exist because `fetch_avatar` once imported a
phantom `gitoder.ui.workers` module, which crashed sign-in *after* the token
was saved and left the app stuck on the sign-in page.

Run: python -m unittest discover -s gitoder/tests -t . -v
"""

from __future__ import annotations

import os
import sys
import time
import unittest
import unittest.mock
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # project root

from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)

from gitoder.core.auth import TokenStore  # noqa: E402
from gitoder.ui.main_window import AppContext, MainWindow  # noqa: E402
from gitoder.ui.widgets import _asset_root, load_fonts  # noqa: E402


def _png_bytes() -> bytes:
    """A real 1x1 PNG so QPixmap.loadFromData succeeds."""
    pm = QPixmap(1, 1)
    pm.fill()
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    pm.save(buf, "PNG")
    return bytes(buf.data())


class MemoryStore(TokenStore):
    """Keyring-free store so tests never touch Credential Manager."""

    def __init__(self) -> None:
        super().__init__()
        self._token: str | None = None

    def load(self):
        return self._token

    def save(self, token: str) -> None:
        self._token = token

    def clear(self) -> None:
        self._token = None


class FakeGithubClient:
    """Offline stand-in for GithubClient (only what these tests touch)."""

    def __init__(self, token: str = "t") -> None:
        self.token = token

    def avatar_bytes(self, url: str):
        return _png_bytes()


USER = {
    "login": "octocat",
    "name": "Octo Cat",
    "avatar_url": "https://avatars.githubusercontent.com/u/1?v=4",
}


class WindowCase(unittest.TestCase):
    def setUp(self) -> None:
        self.win = MainWindow(None, MemoryStore(), None)
        self.ctx = AppContext(self.win)   # same object screens receive
        self.win.show()

    def tearDown(self) -> None:
        for w in list(self.win._tracked):
            try:
                w.wait(2000)
            except Exception:  # noqa: BLE001
                pass
        self.win.close()
        self.win.deleteLater()

    def _pump(self, ms: int) -> None:
        """Process events (and let QThreads finish) for ~ms milliseconds."""
        app = QApplication.instance()
        end = time.monotonic() + ms / 1000
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.01)


class TestSignInFlow(WindowCase):
    """The exact user-reported path: paste token → Connect → land on Home."""

    def test_signed_in_navigates_home(self):
        self.assertIsNone(self.win.user)
        self.assertEqual(self.win.stack.currentWidget(), self.win.signin_screen)

        self.ctx.set_signed_in(dict(USER, avatar_url=""), "tok")

        self.assertIsNotNone(self.win.client)
        self.assertEqual(self.win.user["login"], "octocat")
        self.assertIs(self.win.stack.currentWidget(), self.win.home_screen)
        self.assertTrue(self.win.topbar.isVisible())
        self.assertIn("octocat", self.win.user_lbl.text())

    def test_signed_in_with_avatar_full_path(self):
        """Regression: the avatar fetch that crashed sign-in must not raise.

        The original bug raised ModuleNotFoundError inside fetch_avatar AFTER
        the status label said "Connected", leaving the UI stuck on sign-in.
        """
        with unittest.mock.patch(
            "gitoder.core.github_client.GithubClient", FakeGithubClient
        ):
            self.ctx.set_signed_in(dict(USER), "tok")  # must not raise

        self.assertIs(self.win.stack.currentWidget(), self.win.home_screen)
        self.assertTrue(self.win.topbar.isVisible())

        # the worker should complete and deliver image bytes to the avatar
        got: list = []
        self.win.fetch_avatar("https://x/y.png", got.append)
        self._pump(1500)
        self.assertTrue(got and got[0], "avatar callback never fired")

    def test_refresh_user_called_once_on_signin(self):
        """navigate('home') already refreshes; on_signed_in must not double it."""
        calls: list = []
        original = self.win.home_screen.refresh_user
        self.win.home_screen.refresh_user = lambda: calls.append(1) or original()
        with unittest.mock.patch(
            "gitoder.core.github_client.GithubClient", FakeGithubClient
        ):
            self.ctx.set_signed_in(dict(USER, avatar_url=""), "tok")
        self.assertEqual(len(calls), 1)

    def test_fetch_avatar_with_no_client_is_silent(self):
        self.win.fetch_avatar("https://x/y.png", lambda data: self.fail("called"))
        self._pump(150)  # nothing should explode, nothing should be fetched

    def test_sign_out_returns_to_signin(self):
        self.ctx.set_signed_in(dict(USER, avatar_url=""), "tok")
        self.assertIs(self.win.stack.currentWidget(), self.win.home_screen)
        self.win._sign_out()
        self.assertIsNone(self.win.user)
        self.assertIs(self.win.stack.currentWidget(), self.win.signin_screen)
        self.assertFalse(self.win.topbar.isVisible())

    def test_store_keeps_token_through_signin(self):
        store = self.win.store
        store.save("tok")
        self.ctx.set_signed_in(dict(USER, avatar_url=""), "tok")
        self.assertEqual(store.load(), "tok")


class TestFontLoading(unittest.TestCase):
    def test_fonts_load_from_source_tree(self):
        fams = load_fonts()
        self.assertTrue(fams, "no fonts registered — E-Sense typography broken")
        self.assertIn("Syne", fams)
        self.assertTrue(any(f.startswith("DM Sans") for f in fams))

    def test_asset_root_exists(self):
        root = _asset_root()
        self.assertTrue((root / "assets" / "fonts").is_dir())

    def test_missing_font_dir_is_not_fatal(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:  # noqa: SIM117
            import gitoder.ui.widgets as w

            original = w._asset_root
            w._asset_root = lambda: Path(td)
            try:
                fams = load_fonts()  # must return [] without raising
            finally:
                w._asset_root = original
            self.assertEqual(fams, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
