"""Gitoder entry point: bootstrap, fonts, single-instance guard, exception hook."""

from __future__ import annotations

import logging
import sys

APP_NAME = "Gitoder"
VERSION = "1.0"


def _single_instance_guard() -> None:
    """Named mutex so two copies cannot run conflicting operations (safety net 6)."""
    import ctypes

    ctypes.windll.kernel32.CreateMutexW(None, False, "Gitoder_SingleInstance_Mutex")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        print("Gitoder is already running. Check the system tray or taskbar.",
              file=sys.stderr)
        sys.exit(0)


def _install_exception_hook(log_path: str) -> None:
    from PySide6.QtWidgets import QMessageBox

    def hook(exc_type, exc_value, exc_tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        import traceback

        tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logging.getLogger("gitoder").error("Unhandled exception\n%s", tb)
        try:
            from gitoder.core.errors import UnexpectedError

            err = UnexpectedError(detail=f"see log: {log_path}")
            QMessageBox.warning(
                None, err.title,
                err.message + f"\n\nTechnical details: {log_path}",
            )
        except Exception:  # noqa: BLE001 - never crash the crash handler
            print(tb, file=sys.stderr)

    sys.excepthook = hook


def main() -> int:
    # logging first (tokens never logged; see logging_setup)
    from gitoder.utils.logging_setup import setup_logging

    log_path = setup_logging()
    log = logging.getLogger("gitoder")

    _single_instance_guard()

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setOrganizationName("Gitoder")

    from gitoder.ui.widgets import load_fonts

    load_fonts()
    try:
        from gitoder.ui.theme import check_all_pairs

        check_all_pairs()
    except AssertionError as exc:  # debug-only; log and continue
        log.error("Contrast check failed: %s", exc)

    _install_exception_hook(log_path)

    from gitoder.core.auth import TokenStore
    from gitoder.ui.main_window import MainWindow

    store = TokenStore()
    user = None
    token = store.load()
    client = None
    if token:
        # silent auto-login; a revoked token sends the user to Sign-In with a banner
        from gitoder.core.github_client import GithubClient
        from gitoder.core.errors import AuthError, ScopeError, NetworkError
        from gitoder.core.auth import validate_token

        probe = GithubClient(token)
        try:
            user = validate_token(token, probe)
            client = probe
        except AuthError:
            log.info("Stored token invalid/revoked; sign-in required")
            client = None
            token = None
        except ScopeError:
            # keep the token but the user must re-sign-in with proper scopes
            log.info("Stored token missing scopes; sign-in required")
            client = None
            token = None
        except NetworkError:
            # offline: start anyway; screens show friendly errors per request
            user = None
            client = probe
            token = token  # noqa: F841 - kept for reuse

    window = MainWindow(client, store, user)
    if user is None and token:
        window.signin_screen.set_banner(
            "Your saved GitHub connection couldn't be verified — "
            "sign in again with a fresh token.")

    window.show()
    log.info("Gitoder %s started (log: %s)", VERSION, log_path)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
