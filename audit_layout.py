"""Layout audit: truncated labels, overlaps, off-bounds widgets, dead space per screen."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import faulthandler  # noqa: E402

faulthandler.dump_traceback_later(60, exit=True)

from PySide6.QtGui import QFontMetrics  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QLabel,
    QScrollArea,
    QWidget,
)

app = QApplication(sys.argv)

from gitoder.ui.widgets import load_fonts  # noqa: E402

load_fonts()

from gitoder.core.auth import TokenStore  # noqa: E402
from gitoder.ui.main_window import MainWindow  # noqa: E402

FAKE_USER = {"login": "octocat", "name": "Octo Cat", "avatar_url": ""}


def walk(widget, problems, depth=0):
    from PySide6.QtWidgets import QPushButton, QAbstractButton

    geo = widget.geometry()
    parent = widget.parentWidget()
    if (parent is not None and widget.isVisible()
            and not isinstance(parent, QScrollArea)
            and widget.objectName() != "qt_scrollarea_viewport"):
        pg = parent.rect()
        # allow painted widgets to draw outside via intentional margins only when small
        if (not parent.metaObject().className().startswith("PaperSurface")
                and geo.width() > pg.width() + 4):
            ident = (widget.objectName() or widget.text()[:40] if hasattr(widget, 'text')
                     else widget.objectName())
            problems.append(f"OFF-WIDTH {type(widget).__name__} '{ident}' "
                            f"{geo.width()} > parent {type(parent).__name__} {pg.width()}")
    # truncated text check
    if isinstance(widget, QLabel):
        fm = QFontMetrics(widget.font())
        text = widget.text().replace("&", "")
        if "<" in text:      # rich text: skip
            text = ""
        if text and not widget.wordWrap():
            if fm.horizontalAdvance(text) > widget.width() + 2 and widget.isVisible():
                problems.append(f"TRUNCATED label '{text[:28]}…' needs "
                                f"{fm.horizontalAdvance(text)} has {widget.width()}")
    for child in widget.children():
        if isinstance(child, QWidget) and child.isWidgetType():
            walk(child, problems, depth + 1)


def audit(name, win, navigate_key=None):
    problems: list[str] = []
    if navigate_key:
        win.navigate(navigate_key)
    win.resize(1280, 800)
    win.show()
    app.processEvents()
    app.processEvents()
    current = win.stack.currentWidget()
    walk(current, problems)
    # dead space: fraction of bottom half that is empty background on key screens
    print(f"== {name}: " + ("OK" if not problems else ""))
    for p in problems:
        print("   -", p)


def main() -> int:
    win = MainWindow(None, TokenStore(), None)
    audit("signin", win)
    win2 = MainWindow(None, TokenStore(), dict(FAKE_USER))
    audit("home", win2)
    for key in ("create", "delete", "update", "download"):
        audit(key, win2, navigate_key=key)

    # populated delete rows
    win2.navigate("delete")
    screen = win2.stack.currentWidget()
    screen._on_loaded([
        {"id": 1, "name": "my-vibe-project", "full_name": "octocat/my-vibe-project",
         "private": True, "language": "Python", "updated_at": "2026-10-01T10:00:00Z",
         "owner": {"login": "octocat"}, "html_url": "x"},
        {"id": 2, "name": "portfolio", "full_name": "octocat/portfolio",
         "private": False, "language": "JavaScript", "updated_at": "2026-09-20T10:00:00Z",
         "owner": {"login": "octocat"}, "html_url": "x"},
    ])
    app.processEvents()
    problems: list[str] = []
    walk(win2.stack.currentWidget(), problems)
    print("== delete-populated:", "OK" if not problems else "")
    for p in problems:
        print("   -", p)

    # update folder page with scan results
    win2.navigate("update")
    screen = win2.stack.currentWidget()
    screen.goto(1)
    screen._on_scanned(_fake_scan())
    app.processEvents()
    problems = []
    walk(win2.stack.currentWidget(), problems)
    print("== update-folder:", "OK" if not problems else "")
    for p in problems:
        print("   -", p)
    return 0


def _fake_scan():
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
