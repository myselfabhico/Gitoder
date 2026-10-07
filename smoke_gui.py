"""Offscreen GUI smoke test: instantiate, navigate, render every screen, save shots."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import faulthandler  # noqa: E402

faulthandler.dump_traceback_later(25, exit=True)  # diagnose hangs: dump + exit

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from gitoder.ui.widgets import load_fonts  # noqa: E402

families = load_fonts()
assert families, "SMOKE-FAIL: no fonts registered — bundled TTFs not loading"
assert "Syne" in families, f"SMOKE-FAIL: Syne missing from {families}"

from gitoder.core.auth import TokenStore  # noqa: E402
from gitoder.ui.main_window import MainWindow  # noqa: E402

OUT = Path("shots")
OUT.mkdir(exist_ok=True)

FAKE_USER = {
    "login": "octocat",
    "name": "Octo Cat",
    "avatar_url": "",
}


def shot(widget, name: str) -> None:
    widget.resize(1280, 800)
    widget.show()
    app.processEvents()
    app.processEvents()
    pm = widget.grab()
    pm.save(str(OUT / f"{name}.png"))
    print("shot:", name)


def main() -> int:
    # 1) signed-out: sign-in screen
    win = MainWindow(None, TokenStore(), None)
    shot(win, "01-signin")
    win.close()

    # 2) signed-in: home + every feature screen
    win = MainWindow(None, TokenStore(), dict(FAKE_USER))
    shot(win, "02-home")
    for key in ("create", "delete", "update", "download"):
        win.navigate(key)
        app.processEvents()
        shot(win, f"10-{key}")
        app.processEvents()

    # exercise a few in-screen states
    win.navigate("delete")
    screen = win.stack.currentWidget()
    screen._on_loaded([
        {"id": 1, "name": "my-vibe-project", "full_name": "octocat/my-vibe-project",
         "private": True, "language": "Python", "updated_at": "2026-10-01T10:00:00Z",
         "owner": {"login": "octocat"}, "html_url": "https://github.com/octocat/my-vibe-project"},
        {"id": 2, "name": "portfolio", "full_name": "octocat/portfolio",
         "private": False, "language": "JavaScript", "updated_at": "2026-09-20T10:00:00Z",
         "owner": {"login": "octocat"}, "html_url": "https://github.com/octocat/portfolio"},
    ])
    app.processEvents()
    shot(win, "20-delete-populated")

    win.navigate("update")
    screen = win.stack.currentWidget()
    screen.goto(1)
    screen._on_scanned(_fake_scan())
    app.processEvents()
    shot(win, "21-update-folder")

    win.navigate("download")
    screen = win.stack.currentWidget()
    screen.link_edit.setText("https://github.com/octocat/Spoon-Knife")
    screen._validate(screen.link_edit.text())
    screen.panel.reset()
    screen.panel.on_progress(4_000_000, 10_000_000, 900_000.0)
    screen.panel.show()
    app.processEvents()
    shot(win, "22-download-anim")

    win.navigate("create")
    screen = win.stack.currentWidget()
    screen.pages.setCurrentIndex(2)
    screen.push_stage.setText("Uploading files…")
    screen.push_detail.setText("Uploading files 42 / 118")
    screen.push_bar.set_value(35)
    app.processEvents()
    shot(win, "23-create-pushing")

    win.close()
    print("SMOKE-OK")
    return 0


def _fake_scan():
    """Build a ScanResult without touching the filesystem."""

    from gitoder.core.uploader import ScanResult, ScannedFile

    scan = ScanResult(root=Path("C:/proj/demo"))
    names = ["main.py", "README.md", "app/ui.py", "assets/logo.png",
             "tests/test_app.py", "requirements.txt", "data.csv", "notes.txt",
             "docs/guide.md"]
    for i, n in enumerate(names):
        scan.files.append(ScannedFile(rel_posix=n, absolute=Path("C:/proj/demo") / n,
                                      size=1200 + i * 800))
    scan.total_bytes = sum(f.size for f in scan.files)
    return scan


if __name__ == "__main__":
    sys.exit(main())
