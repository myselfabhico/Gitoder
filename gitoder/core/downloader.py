"""GitHub zipball download: link parsing, streaming to Downloads, .part rename."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from ..utils.paths import unique_destination
from .errors import CancelledError, InvalidLinkError, NotFoundError

log = logging.getLogger("gitoder.downloader")

_GIT_SSH_RE = re.compile(r"^git@github\.com:([^/\s:]+)/([^/\s]+?)(?:\.git)?/?$", re.I)
_SHORT_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9-]*)/([A-Za-z0-9._-]+?)(?:\.git)?/?$")
_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?"
    r"(?:/(?:tree|blob)/(.+?))?/?$",
    re.I,
)


def parse_repo_link(text: str) -> tuple[str, str, str | None]:
    """Return (owner, repo, ref|None). Raises InvalidLinkError for anything else."""
    text = (text or "").strip().strip("\"'")
    if not text:
        raise InvalidLinkError()
    m = _URL_RE.match(text)
    if m:
        owner, repo, ref = m.group(1), m.group(2), m.group(3)
        if repo.endswith(".git"):
            repo = repo[:-4]
        return owner, repo, ref or None
    m = _GIT_SSH_RE.match(text)
    if m:
        repo = m.group(2)
        if repo.endswith(".git"):
            repo = repo[:-4]
        return m.group(1), repo, None
    m = _SHORT_RE.match(text)
    if m:
        return m.group(1), m.group(2), None
    raise InvalidLinkError()


def repo_display_name(owner: str, repo: str, ref: str | None) -> str:
    """Zip filename stem: repo, or repo-branch with branch slashes flattened."""
    if ref:
        flat = re.sub(r"[^A-Za-z0-9._-]+", "-", ref)
        return f"{repo}-{flat}"
    return repo


class Downloader:
    """Stream a repo zipball into Downloads with .part protection."""

    def __init__(self, client) -> None:
        self.client = client
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def download(self, link: str, dest_dir: Path,
                 progress=lambda done, total, speed: None) -> Path:
        owner, repo, ref = parse_repo_link(link)
        if ref is None:
            repo_info = self.client.get_repo(owner, repo)
            if repo_info is None:
                raise NotFoundError()
            ref = repo_info.get("default_branch") or "main"

        resp = self.client.zipball(owner, repo, ref)
        total = int(resp.headers.get("Content-Length") or 0)
        filename = repo_display_name(owner, repo, ref) + ".zip"

        target = unique_destination(Path(dest_dir), filename)
        part = target.with_name(target.name + ".part")
        log.info("Downloading %s/%s@%s -> %s", owner, repo, ref, target.name)

        try:
            done = 0
            last_t = time.monotonic()
            last_done = 0
            speed = 0.0
            with open(part, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=256 * 1024):
                    if self._cancelled:
                        raise CancelledError()
                    if chunk:
                        fh.write(chunk)
                        done += len(chunk)
                    now = time.monotonic()
                    if now - last_t >= 0.5:
                        speed = (done - last_done) / (now - last_t)
                        last_t = now
                        last_done = done
                    progress(done, total, speed)
            part.rename(target)
            log.info("Saved %s (%d bytes)", target.name, done)
            return target
        except BaseException:
            try:
                part.unlink(missing_ok=True)
            except OSError:
                pass
            raise
