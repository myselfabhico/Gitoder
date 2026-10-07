"""Gitoder unit tests. Run: python -m unittest discover -s gitoder/tests -v"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # project root on path

from gitoder.core.downloader import parse_repo_link, repo_display_name  # noqa: E402
from gitoder.core.errors import (  # noqa: E402
    AuthError,
    InvalidLinkError,
    NetworkError,
    NotFoundError,
    ScopeError,
)
from gitoder.core.uploader import scan_folder, validate_repo_name  # noqa: E402
from gitoder.utils.paths import unique_destination  # noqa: E402


class TestLinkParsing(unittest.TestCase):
    CASES = [
        ("https://github.com/owner/repo", ("owner", "repo", None)),
        ("https://github.com/owner/repo/", ("owner", "repo", None)),
        ("https://github.com/owner/repo.git", ("owner", "repo", None)),
        ("http://www.github.com/owner/repo", ("owner", "repo", None)),
        ("github.com/owner/repo", ("owner", "repo", None)),
        ("https://github.com/owner/repo/tree/main", ("owner", "repo", "main")),
        ("https://github.com/owner/repo/tree/feature/cool-thing",
         ("owner", "repo", "feature/cool-thing")),
        ("git@github.com:owner/repo.git", ("owner", "repo", None)),
        ("owner/repo", ("owner", "repo", None)),
    ]

    def test_accepts_all_documented_formats(self):
        for link, expected in self.CASES:
            with self.subTest(link=link):
                self.assertEqual(parse_repo_link(link), expected)

    def test_rejects_garbage(self):
        for bad in ["", "hello world", "https://gitlab.com/a/b",
                    "https://github.com/onlyone", "not a link"]:
            with self.subTest(bad=bad):
                with self.assertRaises(InvalidLinkError):
                    parse_repo_link(bad)

    def test_display_name(self):
        self.assertEqual(repo_display_name("o", "repo", None), "repo")
        self.assertEqual(repo_display_name("o", "repo", "feature/x"), "repo-feature-x")


class TestScanner(unittest.TestCase):
    def _make(self, files: dict[str, bytes], gitignore: str | None = None) -> Path:
        root = Path(tempfile.mkdtemp(prefix="gitoder_scan_"))
        for name, data in files.items():
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        if gitignore is not None:
            (root / ".gitignore").write_text(gitignore, encoding="utf-8")
        return root

    def test_scans_and_computes_sizes(self):
        root = self._make({"main.py": b"print(1)", "data/blob.bin": b"x" * 10})
        scan = scan_folder(root)
        self.assertEqual({f.rel_posix for f in scan.files},
                         {"main.py", "data/blob.bin"})
        self.assertEqual(scan.total_bytes, 18)  # 8 + 10 bytes
        self.assertTrue(scan.can_push)

    def test_skips_junk_and_git_dir(self):
        root = self._make({"a.py": b"1", "__pycache__/a.cpython-314.pyc": b"junk",
                           ".git/config": b"junk", "Thumbs.db": b"junk"})
        scan = scan_folder(root)
        self.assertEqual([f.rel_posix for f in scan.files], ["a.py"])

    def test_honors_gitignore(self):
        root = self._make({"keep.py": b"1", "node_modules/x.js": b"junk",
                           "secret.log": b"junk"}, gitignore="node_modules\n*.log\n")
        scan = scan_folder(root)
        self.assertEqual(sorted(f.rel_posix for f in scan.files),
                         [".gitignore", "keep.py"])

    def test_fully_ignored_folder_blocks_push(self):
        root = self._make({"node_modules/x.js": b"junk"}, gitignore="node_modules\n")
        scan = scan_folder(root)
        self.assertFalse(scan.can_push)
        self.assertTrue(scan.blocking)

    def test_100mb_limit_blocks(self):
        big = b"\0" * (100 * 1024 * 1024 + 1)
        root = self._make({"big.bin": big})
        scan = scan_folder(root)
        self.assertFalse(scan.can_push)
        self.assertTrue(any("100 MB" in b for b in scan.blocking))

    def test_secret_warning(self):
        root = self._make({".env": b"SECRET=1"})
        scan = scan_folder(root)
        self.assertTrue(scan.can_push)          # warning, not blocking
        self.assertTrue(any("secret" in w.lower() for w in scan.warnings))

    def test_name_validation(self):
        self.assertIsNone(validate_repo_name("my-repo_1.0"))
        self.assertIsNotNone(validate_repo_name(""))
        self.assertIsNotNone(validate_repo_name("has space"))
        self.assertIsNotNone(validate_repo_name(".."))
        self.assertIsNotNone(validate_repo_name("a" * 101))


class FakeClient:
    """In-memory GitHub for the end-to-end push test."""

    def __init__(self):
        self.repos = {}
        self.blobs = {}
        self.refs = {}
        self._next = 1

    def get_branch_head(self, owner, name, branch):
        return self.refs.get((owner, name, branch))

    def put_contents(self, owner, name, path, message, content, branch):
        sha = f"commit-{self._next}"
        self._next += 1
        self.refs[(owner, name, branch)] = sha
        self.repos.setdefault((owner, name), {})[path] = content
        return {"commit": {"sha": sha}}

    def create_blob(self, owner, name, b64):
        import base64

        sha = f"blob-{self._next}"
        self._next += 1
        self.blobs[sha] = base64.b64decode(b64)
        return sha

    def create_tree(self, owner, name, tree, base_tree):
        self.last_tree = tree
        self.last_base_tree = base_tree
        self._last_tree_id = f"tree-{self._next}"
        self._next += 1
        return self._last_tree_id

    def get_repo_tree(self, owner, name, sha, recursive=True):
        if getattr(self, "_last_tree_id", None) == sha:
            return {"tree": [{"path": e["path"], "type": "blob"}
                             for e in self.last_tree]}
        if sha.startswith("tree-base-"):
            return {"tree": [{"path": "README.md", "type": "blob"}]}
        return {"tree": []}

    def create_commit(self, owner, name, message, tree_sha, parents):
        sha = f"commit-{self._next}"
        self._next += 1
        self._last_commit = {"sha": sha, "tree": {"sha": tree_sha}}
        return sha

    def get_commit(self, owner, name, sha):
        # used on "create" to fetch the head commit's tree
        if sha.startswith("commit-"):
            return {"sha": sha, "tree": {"sha": f"tree-base-{sha}"}}
        raise KeyError(sha)

    def update_ref(self, owner, name, branch, sha):
        self.refs[(owner, name, branch)] = sha

    def create_ref(self, owner, name, branch, sha):
        self.refs[(owner, name, branch)] = sha


class TestUploaderE2E(unittest.TestCase):
    def _scan_of(self, files: dict[str, bytes]) -> tuple:
        root = Path(tempfile.mkdtemp(prefix="gitoder_push_"))
        for name, data in files.items():
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        return scan_folder(root), root

    def test_update_push_fully_replaces_and_verifies(self):
        from gitoder.core.uploader import Uploader

        scan, root = self._scan_of({"new.py": b"print('new')", "sub/b.txt": b"B"})
        client = FakeClient()
        client.refs[("me", "proj", "main")] = "commit-0"
        client.repos[("me", "proj")] = {"old.py": b"old"}

        up = Uploader(client)
        stages = []
        result = up.push(
            scan, {"owner": {"login": "me"}, "name": "proj",
                   "default_branch": "main", "html_url": "https://github.com/me/proj"},
            mode="update",
            on_stage=stages.append,
        )
        self.assertEqual(result["files"], 2)
        self.assertIn("Verifying", stages[-1])
        # no base_tree on update -> atomic full replace
        self.assertIsNone(client.last_base_tree)
        paths = [e["path"] for e in client.last_tree]
        self.assertEqual(sorted(paths), ["new.py", "sub/b.txt"])

    def test_create_push_merges_on_base_tree(self):
        from gitoder.core.uploader import Uploader

        scan, root = self._scan_of({"README.md": b"# mine", "app.py": b"x"})
        client = FakeClient()
        client.refs[("me", "newrepo", "main")] = "commit-0"

        up = Uploader(client)
        up.push(scan, {"owner": {"login": "me"}, "name": "newrepo",
                       "default_branch": "main"}, mode="create")
        # base_tree present on create (generated README survives where user has none)
        self.assertIsNotNone(client.last_base_tree)
        paths = [e["path"] for e in client.last_tree]
        self.assertIn("README.md", paths)
        self.assertIn("app.py", paths)

    def test_cancellation_raises_cancelled(self):
        from gitoder.core.errors import CancelledError
        from gitoder.core.uploader import Uploader

        scan, root = self._scan_of({"a.py": b"1"})
        up = Uploader(FakeClient())
        up.cancel()
        with self.assertRaises(CancelledError):
            up.push(scan, {"owner": {"login": "me"}, "name": "p",
                           "default_branch": "main"}, mode="update")


class TestUniqueDestination(unittest.TestCase):
    def test_never_overwrites(self):
        base = Path(tempfile.mkdtemp(prefix="gitoder_dest_"))
        first = unique_destination(base, "repo.zip")
        first.write_bytes(b"x")
        second = unique_destination(base, "repo.zip")
        self.assertEqual(second.name, "repo (1).zip")
        second.write_bytes(b"x")
        third = unique_destination(base, "repo.zip")
        self.assertEqual(third.name, "repo (2).zip")


class TestErrorMapping(unittest.TestCase):
    def test_friendly_defaults(self):
        self.assertIn("internet", NetworkError().message.lower())
        self.assertIn("permission", ScopeError().message.lower())
        self.assertIn("token", AuthError().message.lower())
        self.assertIn("exist", NotFoundError().message.lower())


if __name__ == "__main__":
    unittest.main()
