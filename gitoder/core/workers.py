"""QThread workers: run core operations off the UI thread, report via signals.

Core modules contain no Qt; these adapters own the threading and signals only.
"""

from __future__ import annotations

import logging
import traceback

from PySide6.QtCore import QObject, QThread, Signal

from ..core.errors import CancelledError, GitoderError, RateLimitError
from ..core.github_client import GithubClient
from ..core.uploader import ScanResult, Uploader
from ..core.downloader import Downloader
from ..utils.paths import downloads_dir

log = logging.getLogger("gitoder.workers")


class WorkerSignals(QObject):
    stage = Signal(str)
    progress = Signal(int, int, int, int)      # generic 4-int progress
    download_progress = Signal(int, int, float)  # done, total, speed
    succeeded = Signal(object)
    failed = Signal(object)                    # GitoderError
    rate_wait = Signal(int)                    # seconds the client will sleep
    finished = Signal()


class LongWorker(QThread):
    """Base: run() executes _run in a thread; errors become typed failures."""

    signals: WorkerSignals

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.signals = WorkerSignals()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:  # noqa: D102 - Qt override
        try:
            result = self._run()
            if not self._cancelled:
                self.signals.succeeded.emit(result)
        except CancelledError:
            log.info("Worker cancelled: %s", type(self).__name__)
        except RateLimitError as exc:
            self.signals.failed.emit(exc)
        except GitoderError as exc:
            log.warning("Worker failed: %s (%s)", exc.title, exc.detail)
            self.signals.failed.emit(exc)
        except Exception as exc:  # noqa: BLE001 - last resort
            log.error("Unexpected worker error: %s\n%s", exc, traceback.format_exc())
            from ..core.errors import UnexpectedError
            self.signals.failed.emit(UnexpectedError(detail=repr(exc)))
        finally:
            self.signals.finished.emit()

    def _run(self):
        raise NotImplementedError


class PushWorker(LongWorker):
    """Create/Update push pipeline. Emits stage + 4-int progress signals."""

    def __init__(self, client: GithubClient, scan: ScanResult, repo: dict, *,
                 mode: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.client = client
        self.scan = scan
        self.repo = repo
        self.mode = mode
        # Plain-python object, no Qt affinity: safe to build here so Cancel
        # works even if the user cancels before the thread starts running.
        self._uploader: Uploader = Uploader(client)

    def _run(self):
        uploader = self._uploader

        def stage(text: str) -> None:
            if not self._cancelled:
                self.signals.stage.emit(text)

        def progress(done_f, total_f, done_b, total_b) -> None:
            if not self._cancelled:
                self.signals.progress.emit(int(done_f), int(total_f), int(done_b), int(total_b))

        return uploader.push(
            self.scan, self.repo, mode=self.mode,
            on_stage=stage, on_progress=progress,
        )

    def cancel(self) -> None:
        """Stop the push: flag the thread AND tell the running uploader to abort.

        The uploader checks cancellation between stages, per file read, and
        between blob uploads, so a cancelled push stops within seconds instead
        of silently continuing to GitHub.
        """
        super().cancel()
        self._uploader.cancel()


class DownloadWorker(LongWorker):
    def __init__(self, client: GithubClient, link: str, *,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.client = client
        self.link = link
        self._downloader: Downloader | None = None

    def _run(self):
        self._downloader = Downloader(self.client)

        def progress(done: int, total: int, speed: float) -> None:
            if not self._cancelled:
                self.signals.download_progress.emit(done, total, speed)

        return self._downloader.download(self.link, downloads_dir(), progress)

    def cancel(self) -> None:
        super().cancel()
        if self._downloader is not None:
            self._downloader.cancel()


class ListReposWorker(LongWorker):
    def __init__(self, client: GithubClient, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.client = client

    def _run(self):
        return self.client.list_repos()


class FetchOptionsWorker(LongWorker):
    """Licenses + gitignore templates, with offline fallback lists."""

    FALLBACK_LICENSES = [
        {"key": "mit", "name": "MIT License"},
        {"key": "apache-2.0", "name": "Apache License 2.0"},
        {"key": "gpl-3.0", "name": "GNU General Public License v3.0"},
        {"key": "bsd-3-clause", "name": "BSD 3-Clause License"},
        {"key": "mpl-2.0", "name": "Mozilla Public License 2.0"},
    ]
    FALLBACK_GITIGNORE = ["Python", "Node", "Java", "C++", "Go", "Rust", "VisualStudio"]

    def __init__(self, client: GithubClient, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.client = client

    def _run(self):
        licenses = self.client.licenses() or self.FALLBACK_LICENSES
        ignores = self.client.gitignore_templates() or self.FALLBACK_GITIGNORE
        return {"licenses": licenses, "gitignores": ignores}


class ScanWorker(LongWorker):
    def __init__(self, folder: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.folder = folder

    def _run(self):
        from ..core.uploader import scan_folder
        return scan_folder(__import__("pathlib").Path(self.folder))


class DeleteRepoWorker(LongWorker):
    def __init__(self, client: GithubClient, owner: str, name: str, *,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.client = client
        self.owner = owner
        self.name = name

    def _run(self):
        self.client.delete_repo(self.owner, self.name)
        return {"owner": self.owner, "name": self.name}


class CreateRepoWorker(LongWorker):
    def __init__(self, client: GithubClient, payload: dict, *,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.client = client
        self.payload = payload

    def _run(self):
        return self.client.create_repo(self.payload)
