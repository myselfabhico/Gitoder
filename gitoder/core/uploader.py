"""Folder scan, pre-flight validation, Git Data API push, verification, bootstrap."""

from __future__ import annotations

import base64
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import CancelledError as FuturesCancelled
from dataclasses import dataclass, field
from pathlib import Path

import pathspec

from .errors import (
    CancelledError,
    EmptyFolderError,
    FileTooLargeError,
    GitoderError,
    NetworkError,
    NotFoundError,
)

log = logging.getLogger("gitoder.uploader")

MAX_FILE_BYTES = 100 * 1024 * 1024          # GitHub hard limit per file
WARN_TOTAL_BYTES = 500 * 1024 * 1024        # warn above ~500 MB total
BLOB_WORKERS = 6

JUNK_NAMES = {"__pycache__", ".DS_Store", "Thumbs.db", "desktop.ini", ".git"}
SECRET_HINTS = (".env", ".pem", "id_rsa", "credentials.json", ".p12", ".pfx", ".keystore")


@dataclass
class ScannedFile:
    rel_posix: str          # forward-slash path relative to the folder root
    absolute: Path
    size: int


@dataclass
class ScanResult:
    root: Path
    files: list[ScannedFile] = field(default_factory=list)
    total_bytes: int = 0
    warnings: list[str] = field(default_factory=list)   # non-blocking
    blocking: list[str] = field(default_factory=list)   # must fix before push
    ignored_count: int = 0

    @property
    def can_push(self) -> bool:
        return not self.blocking and bool(self.files)


def _load_gitignore_spec(root: Path) -> pathspec.GitIgnoreSpec | None:
    gi = root / ".gitignore"
    if not gi.is_file():
        return None
    try:
        lines = gi.read_text(encoding="utf-8", errors="replace").splitlines()
        return pathspec.GitIgnoreSpec.from_lines(lines)
    except OSError:
        return None


def scan_folder(root: Path) -> ScanResult:
    """Recursively scan a folder for upload. Never raises for scan-level issues."""
    result = ScanResult(root=root)
    if not root.is_dir():
        result.blocking.append("That folder can't be read. Pick a different folder.")
        return result

    spec = _load_gitignore_spec(root)

    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        # Prune junk directories in place
        pruned = []
        for d in list(dirnames):
            rel_d = (rel_dir / d).as_posix() if str(rel_dir) != "." else d
            if d in JUNK_NAMES or (d.startswith(".") and d != ".git" and d not in (".github",)):
                dirnames.remove(d)
                result.ignored_count += 1
                continue
            if spec is not None and spec.match_file(rel_d + "/"):
                dirnames.remove(d)
                result.ignored_count += 1
                continue
            pruned.append(d)
        if rel_dir != Path(".") and not pruned and not filenames:
            # empty directory: git cannot store it
            result.ignored_count += 1
            continue

        for fname in filenames:
            rel = (rel_dir / fname) if str(rel_dir) != "." else Path(fname)
            rel_posix = rel.as_posix()
            if fname in JUNK_NAMES:
                result.ignored_count += 1
                continue
            if fname == ".gitignore" and rel_dir == Path("."):
                pass  # the folder's own .gitignore IS uploaded
            if spec is not None and rel_posix != ".gitignore" and spec.match_file(rel_posix):
                result.ignored_count += 1
                continue
            absolute = Path(dirpath) / fname
            try:
                size = absolute.stat().st_size
            except OSError:
                result.blocking.append(f"Can't read file: {rel_posix}")
                continue
            result.files.append(ScannedFile(rel_posix=rel_posix, absolute=absolute, size=size))
            result.total_bytes += size

    result.files.sort(key=lambda f: f.rel_posix)

    # ----- pre-flight messages
    over_limit = [f for f in result.files if f.size > MAX_FILE_BYTES]
    for f in over_limit:
        result.blocking.append(
            f"{f.rel_posix} is {f.size / (1024 * 1024):.1f} MB — GitHub's limit is 100 MB."
        )
    if not result.files and not result.blocking:
        result.blocking.append(
            "This folder has no files to upload (everything was ignored or it is empty)."
        )
    elif (spec is not None and [f.rel_posix for f in result.files] == [".gitignore"]):
        # the only surviving file is the .gitignore that ignored everything else
        result.blocking.append(
            "Every file was ignored by your .gitignore — nothing to upload."
        )
        result.files = []
        result.total_bytes = 0
    if result.total_bytes > WARN_TOTAL_BYTES:
        result.warnings.append(
            f"The folder is {result.total_bytes / (1024 * 1024):.0f} MB in total. "
            "Large uploads can take a long time."
        )
    for f in result.files:
        low = f.rel_posix.lower()
        if any(h in low for h in SECRET_HINTS):
            result.warnings.append(
                f"'{f.rel_posix}' looks like it may contain a secret (passwords, keys). "
                "Uploading it to GitHub can expose it."
            )
            break
    risky = risky_root_reason(root)
    if risky:
        result.warnings.append(risky)
    return result


def risky_root_reason(root: Path) -> str | None:
    """Human warning if the folder looks like a drive root or a user home folder."""
    try:
        r = root.resolve()
    except OSError:
        return None
    if r.parent == r:
        return f"'{r}' is a drive root. Make sure you really want to upload everything on it."
    home = Path.home().resolve()
    if r == home:
        return "This is your user home folder. Uploading it would share every personal file."
    for special in ("Desktop", "Documents", "Downloads"):
        if r == home / special:
            return f"This is your {special} folder. Consider picking a specific project folder."
    return None


def validate_repo_name(name: str) -> str | None:
    """Return an error message, or None when the name is acceptable to GitHub."""
    if not name or not name.strip():
        return "Give the repository a name."
    name = name.strip()
    if len(name) > 100:
        return "Names can be at most 100 characters."
    if name in (".", ".."):
        return "This name isn't allowed."
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    if any(ch not in allowed for ch in name):
        return "Use only letters, digits, '-', '_' and '.'. No spaces."
    if name.endswith("."):
        return "Names can't end with a dot."
    if name.endswith(".lock"):
        return "Names can't end with '.lock'."
    return None


class Uploader:
    """Pushes a scanned folder to a repo with the Git Data API. Runs off-UI-thread."""

    def __init__(self, client) -> None:
        self.client = client
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def _check_cancel(self) -> None:
        if self._cancelled:
            raise CancelledError()

    # ------------------------------------------------------------- public

    def push(
        self,
        scan: ScanResult,
        repo: dict,
        *,
        mode: str,                      # "create" | "update"
        branch: str | None = None,
        commit_message: str | None = None,
        on_stage=None,
        on_progress=None,               # (files_done, files_total, bytes_done, bytes_total)
    ) -> dict:
        owner = repo["owner"]["login"]
        name = repo["name"]
        branch = branch or repo.get("default_branch") or "main"
        message = commit_message or (
            "Initial commit via Gitoder" if mode == "create" else "Update files via Gitoder"
        )
        stage = on_stage or (lambda text: None)
        progress = on_progress or (lambda *a: None)

        self._check_cancel()
        stage("Reading files…")
        contents = self._read_all(scan, progress)

        stage("Checking repository…")
        head = self.client.get_branch_head(owner, name, branch)
        bootstrapped = False
        if head is None:
            stage("Preparing repository…")
            head = self._bootstrap_first_commit(owner, name, branch, contents, message)
            bootstrapped = True

        stage("Uploading files…")
        blob_shas = self._upload_blobs(owner, name, contents, progress)

        stage("Building tree…")
        base_tree = None
        if mode == "create" and head:
            head_commit = self.client.get_commit(owner, name, head)
            base_tree = (head_commit.get("tree") or {}).get("sha")
        entries = [
            {"path": f.rel_posix, "mode": "100755" if _is_exec(f) else "100644",
             "type": "blob", "sha": blob_shas[f.rel_posix]}
            for f in scan.files
        ]
        tree_sha = self.client.create_tree(owner, name, entries, base_tree)

        stage("Finalizing commit…")
        commit_sha = self.client.create_commit(owner, name, message, tree_sha, [head] if head else [])
        try:
            self.client.update_ref(owner, name, branch, commit_sha)
        except NotFoundError:
            self.client.create_ref(owner, name, branch, commit_sha)

        stage("Verifying…")
        self._verify(owner, name, tree_sha, scan, base_tree, bootstrapped)

        return {
            "commit": commit_sha,
            "branch": branch,
            "files": len(scan.files),
            "bootstrapped": bootstrapped,
            "html_url": repo.get("html_url", f"https://github.com/{owner}/{name}"),
        }

    # ------------------------------------------------------------ internal

    def _read_all(self, scan: ScanResult, progress) -> dict[str, bytes]:
        total = scan.total_bytes or 1
        done_bytes = 0
        contents: dict[str, bytes] = {}
        for f in scan.files:
            self._check_cancel()
            try:
                data = f.absolute.read_bytes()
            except OSError as exc:
                raise GitoderError(
                    f"Couldn't read '{f.rel_posix}' from your folder.",
                    detail=f"read error: {exc.__class__.__name__}",
                ) from exc
            contents[f.rel_posix] = data
            done_bytes += len(data)
            progress(0, len(scan.files), done_bytes, total)
        return contents

    def _bootstrap_first_commit(self, owner: str, name: str, branch: str,
                                contents: dict[str, bytes], message: str) -> str:
        """Empty repo: put the smallest real file via the Contents API, return new head."""
        if not contents:
            raise EmptyFolderError()
        smallest = min(contents, key=lambda p: len(contents[p]))
        resp = self.client.put_contents(
            owner, name, smallest, message, contents[smallest], branch
        )
        head = (resp.get("commit") or {}).get("sha")
        if not head:
            raise NetworkError("GitHub didn't confirm the first commit.", detail="no sha")
        log.info("Bootstrapped empty repo with %s", smallest)
        return head

    def _upload_blobs(self, owner: str, name: str, contents: dict[str, bytes], progress) -> dict:
        total_files = len(contents)
        total_bytes = sum(len(v) for v in contents.values()) or 1
        done_files = 0
        done_bytes = 0
        shas: dict[str, str] = {}

        def work(item: tuple[str, bytes]) -> tuple[str, str]:
            path, data = item
            b64 = base64.b64encode(data).decode("ascii")
            return path, self.client.create_blob(owner, name, b64)

        with ThreadPoolExecutor(max_workers=BLOB_WORKERS) as pool:
            futures = {pool.submit(work, item): item[0] for item in contents.items()}
            from concurrent.futures import as_completed

            for fut in as_completed(list(futures)):
                self._check_cancel()
                path, sha = fut.result()
                shas[path] = sha
                done_files += 1
                done_bytes += len(contents[path])
                progress(done_files, total_files, done_bytes, total_bytes)
                if done_files % 10 == 0:
                    log.info("Blobs %d/%d", done_files, total_files)
        if len(shas) != total_files:  # pragma: no cover - defensive
            raise NetworkError("Some files didn't upload.", detail="blob count mismatch")
        return shas

    def _verify(self, owner: str, name: str, tree_sha: str, scan: ScanResult,
                base_tree: str | None, bootstrapped: bool) -> None:
        """Never show success unless the resulting tree holds exactly the right files."""
        tree = self.client.get_repo_tree(owner, name, tree_sha, recursive=True)
        entries = [e for e in tree.get("tree", []) if e.get("type") == "blob"]
        got = {e["path"] for e in entries}
        sent = {f.rel_posix for f in scan.files}

        expected = set(sent)
        if base_tree:
            base_entries = self.client.get_repo_tree(owner, name, base_tree, recursive=True)
            for e in base_entries.get("tree", []):
                if e.get("type") != "blob":
                    continue
                if e["path"] not in sent:      # user files win; others are kept
                    expected.add(e["path"])
        if bootstrapped:
            # the bootstrap file is one of the user's own files; already in `sent`
            pass

        missing = expected - got
        extra = got - expected
        if missing or extra:
            log.error("Verify mismatch: missing=%d extra=%d", len(missing), len(extra))
            raise GitoderError(
                "The upload finished but Gitoder could not confirm every file arrived. "
                "Use Retry upload to try again — nothing is shown as successful.",
                title="Upload verification failed",
            )


def _is_exec(f: ScannedFile) -> bool:
    try:
        return bool(f.absolute.stat().st_mode & 0o111)
    except OSError:
        return False
