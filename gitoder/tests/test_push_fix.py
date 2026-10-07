"""Regression tests for the Create-Repo push failure the user hit.

Real GitHub answers 409 Conflict ("Git Repository is empty") when you ask for
the branch head of a brand-new repo with no commits. Gitoder used to treat
only 404 as "empty" and failed every push to a fresh empty repo with
"Something went wrong". These tests pin the correct behavior at both layers:

- the real GithubClient maps a 409 ref response to "no branch head yet";
- the Uploader then bootstraps the first commit and uploads everything.

Run: python -m unittest discover -s gitoder/tests -t . -v
"""

from __future__ import annotations

import base64
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # project root

from gitoder.core.errors import CancelledError, GitoderError, NotFoundError  # noqa: E402
from gitoder.core.uploader import Uploader, scan_folder  # noqa: E402


def _scan_of(files: dict[str, bytes]):
    root = Path(tempfile.mkdtemp(prefix="gitoder_409_"))
    for name, data in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return scan_folder(root)


def _fake_response(status: int, payload=None, headers=None):
    """Minimal requests.Response stand-in for _raise_for_status tests."""
    import json as _json

    class R:
        def __init__(self):
            self.status_code = status
            self.headers = headers or {}
            self._payload = payload if payload is not None else {}
            self.text = _json.dumps(self._payload)

        def json(self):
            return self._payload

    return R()


REPO = {"owner": {"login": "me"}, "name": "proj",
        "default_branch": "main", "html_url": "https://github.com/me/proj"}


class TestClient409Mapping(unittest.TestCase):
    """Layer 1: the real GithubClient must read 409 as 'empty repo'."""

    def test_409_ref_response_means_no_branch(self):
        from gitoder.core.github_client import GithubClient

        c = GithubClient.__new__(GithubClient)   # skip __init__ (no network)
        resp = _fake_response(409, {"message": "Git Repository is empty."})
        with unittest.mock.patch.object(c, "request", return_value=resp):
            self.assertIsNone(c.get_branch_head("me", "proj", "main"))

    def test_404_ref_response_still_means_no_branch(self):
        from gitoder.core.github_client import GithubClient

        c = GithubClient.__new__(GithubClient)
        resp = _fake_response(404, {"message": "Not Found"})
        with unittest.mock.patch.object(c, "request", return_value=resp):
            self.assertIsNone(c.get_branch_head("me", "proj", "main"))

    def test_real_head_sha_is_returned(self):
        from gitoder.core.github_client import GithubClient

        c = GithubClient.__new__(GithubClient)
        resp = _fake_response(200, {"object": {"sha": "abc123"}})
        with unittest.mock.patch.object(c, "request", return_value=resp):
            self.assertEqual(c.get_branch_head("me", "proj", "main"), "abc123")

    def test_500_ref_response_still_raises(self):
        from gitoder.core.github_client import GithubClient

        c = GithubClient.__new__(GithubClient)
        resp = _fake_response(500, {})
        with unittest.mock.patch.object(c, "request", return_value=resp), \
                self.assertRaises(GitoderError):
            c.get_branch_head("me", "proj", "main")


class FakeRealGitHub:
    """Uploader-level fake mimicking the FIXED client's observable contract:
    get_branch_head returns None for an empty repo (GitHub's 409/404 mapped
    away by GithubClient — pinned separately in TestClient409Mapping)."""

    def __init__(self):
        self.refs: dict = {}
        self.stored: dict = {}
        self.blobs: dict = {}
        self.last_tree: list = []
        self.last_base_tree = None
        self._next = 1

    def get_branch_head(self, owner, name, branch):
        return self.refs.get((owner, name, branch))   # None = empty repo

    def put_contents(self, owner, name, path, message, content, branch):
        sha = f"commit-{self._next}"
        self._next += 1
        self.refs[(owner, name, branch)] = sha
        self.stored.setdefault((owner, name), {})[path] = content
        return {"commit": {"sha": sha}}

    def create_blob(self, owner, name, b64):
        sha = f"blob-{self._next}"
        self._next += 1
        self.blobs[sha] = base64.b64decode(b64)
        return sha

    def get_commit(self, owner, name, sha):
        return {"sha": sha, "tree": {"sha": f"tree-of-{sha}"}}

    def create_tree(self, owner, name, tree, base_tree):
        self.last_tree = list(tree)
        self.last_base_tree = base_tree
        return f"tree-{self._next}"

    def create_commit(self, owner, name, message, tree_sha, parents):
        sha = f"commit-{self._next}"
        self._next += 1
        self.last_commit = {"sha": sha, "tree": {"sha": tree_sha}}
        # model: landing the commit makes every file in the tree exist
        store = self.stored.setdefault((owner, name), {})
        for e in self.last_tree:
            if e.get("sha") in self.blobs:
                store[e["path"]] = self.blobs[e["sha"]]
        return sha

    def get_repo_tree(self, owner, name, sha, recursive=True):
        if sha.startswith("tree-") and sha != f"tree-{self._next}":
            return {"tree": [{"path": e["path"], "type": "blob"}
                             for e in self.last_tree]}
        return {"tree": []}

    def update_ref(self, owner, name, branch, sha):
        self.refs[(owner, name, branch)] = sha

    def create_ref(self, owner, name, branch, sha):
        self.refs[(owner, name, branch)] = sha


class TestEmptyRepoPush(unittest.TestCase):
    """The user's exact scenario: Create -> empty repo -> 409 -> push."""

    def test_push_to_empty_repo_with_409_succeeds(self):
        """The user's scenario end-to-end at the uploader layer."""
        client = FakeRealGitHub()
        scan = _scan_of({"main.py": b"print('hi')", "docs/readme.md": b"# hi"})
        result = Uploader(client).push(scan, dict(REPO), mode="create")

        self.assertEqual(result["files"], 2)
        self.assertTrue(result["bootstrapped"])
        stored = client.stored[("me", "proj")]
        self.assertEqual(stored["main.py"], b"print('hi')")
        self.assertEqual(stored["docs/readme.md"], b"# hi")
        self.assertEqual(client.refs[("me", "proj", "main")], result["commit"])

    def test_push_to_fresh_repo_bootstraps_and_uploads(self):
        """Client maps empty-repo 409/404 to None; uploader must bootstrap."""
        client = FakeRealGitHub()                     # empty: head -> None
        scan = _scan_of({"a.txt": b"A"})
        result = Uploader(client).push(scan, dict(REPO), mode="create")
        self.assertEqual(result["files"], 1)
        self.assertTrue(result["bootstrapped"])
        self.assertEqual(client.stored[("me", "proj")]["a.txt"], b"A")

    def test_bootstrap_uses_smallest_file(self):
        client = FakeRealGitHub()
        scan = _scan_of({"tiny.txt": b"x", "big.bin": b"Y" * 10_000})
        Uploader(client).push(scan, dict(REPO), mode="create")
        # bootstrap PUTs the smallest file first via the Contents API
        self.assertIn("tiny.txt", client.stored[("me", "proj")])

    def test_repo_with_existing_head_pushes_without_bootstrap(self):
        client = FakeRealGitHub()
        client.put_contents("me", "proj", ".keep", "keep", b"", "main")
        scan = _scan_of({"a.txt": b"A"})
        result = Uploader(client).push(scan, dict(REPO), mode="create")
        self.assertFalse(result["bootstrapped"])

    def test_create_mode_sends_base_tree(self):
        """Generated README etc. survive where the user's folder lacks them."""
        client = FakeRealGitHub()
        client.put_contents("me", "proj", "README.md", "auto", b"# auto", "main")
        scan = _scan_of({"app.py": b"x"})
        Uploader(client).push(scan, dict(REPO), mode="create")
        self.assertIsNotNone(client.last_base_tree)


class TestPushCancellation(unittest.TestCase):
    """Cancel during a push must actually stop the work."""

    def test_uploader_cancel_between_blobs_raises_cancelled(self):
        client = FakeRealGitHub()
        original = client.create_blob

        def slow(owner, name, b64):
            time.sleep(0.02)
            return original(owner, name, b64)

        client.create_blob = slow
        files = {f"f{i}.txt": b"data" * 50 for i in range(30)}
        scan = _scan_of(files)
        up = Uploader(client)
        outcome: list = []

        def run():
            try:
                up.push(scan, dict(REPO), mode="create")
                outcome.append("done")
            except CancelledError:
                outcome.append("cancelled")
            except Exception as e:  # noqa: BLE001
                outcome.append(f"error:{e!r}")

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        time.sleep(0.04)          # let it get into the blob loop
        up.cancel()               # UI-thread cancel mid-push
        worker.join(timeout=15)

        self.assertEqual(outcome, ["cancelled"],
                         "cancel during push must raise CancelledError, "
                         f"got {outcome}")

    def test_pushworker_cancel_reaches_uploader(self):
        """PushWorker.cancel() must flag its uploader (the old bug: no-op)."""
        from gitoder.core.workers import PushWorker

        scan = _scan_of({"a.txt": b"A"})
        w = PushWorker(None, scan, dict(REPO), mode="create")
        self.assertFalse(w._uploader._cancelled)
        w.cancel()
        self.assertTrue(w._uploader._cancelled)
        self.assertTrue(w._cancelled)


class TestZipballEmptyRepo(unittest.TestCase):
    """Download of an empty repo must give a friendly message, not 'Not found'."""

    def _stub_client(self, repo_info):
        c = unittest.mock.MagicMock()
        c.request.return_value = _fake_response(404, {})
        c.get_repo.return_value = repo_info
        return c

    def test_empty_repo_download_message(self):
        from gitoder.core.github_client import GithubClient

        c = self._stub_client({"size": 0, "name": "empty"})
        with self.assertRaises(GitoderError) as ctx:
            GithubClient.zipball(c, "me", "empty", "main")
        self.assertIn("empty", str(ctx.exception.message).lower())

    def test_wrong_ref_download_message(self):
        from gitoder.core.github_client import GithubClient

        c = self._stub_client({"size": 500, "name": "proj"})
        with self.assertRaises(GitoderError) as ctx:
            GithubClient.zipball(c, "me", "proj", "nope")
        self.assertIn("branch", str(ctx.exception.message).lower())

    def test_missing_repo_raises_not_found(self):
        from gitoder.core.github_client import GithubClient

        c = self._stub_client(None)
        with self.assertRaises(NotFoundError):
            GithubClient.zipball(c, "me", "ghost", "main")


if __name__ == "__main__":
    unittest.main(verbosity=2)
