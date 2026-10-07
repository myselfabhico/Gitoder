"""All GitHub REST calls: session, retries, backoff, pagination, typed error mapping.

The token never appears in logs, exceptions, or error details.
"""

from __future__ import annotations

import base64
import logging
import random
import time
from typing import Any, Iterator
from urllib.parse import quote

import requests

from .errors import (
    AuthError,
    GitoderError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ScopeError,
    TimeoutError_,
)

log = logging.getLogger("gitoder.github")

API = "https://api.github.com"
MAX_RETRIES = 3
BACKOFF_BASE = 1.0
BACKOFF_CAP = 30.0


class GithubClient:
    """Thin, resilient wrapper over the GitHub REST API."""

    def __init__(self, token: str) -> None:
        self._token = token
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Gitoder",
        })

    # ------------------------------------------------------------------ core

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json_body: Any = None,
        headers: dict | None = None,
        stream: bool = False,
        timeout: float = 30.0,
    ) -> requests.Response:
        """One API call with retries on 5xx / connection errors / rate limits."""
        full_url = url if url.startswith("http") else API + url
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self._session.request(
                    method, full_url, params=params, json=json_body,
                    headers=headers, stream=stream, timeout=timeout,
                )
            except requests.exceptions.Timeout as exc:
                if attempt > MAX_RETRIES:
                    raise TimeoutError_(detail=str(exc.__class__.__name__)) from exc
                self._sleep_backoff(attempt)
                continue
            except requests.exceptions.RequestException as exc:
                if attempt > MAX_RETRIES:
                    raise NetworkError(detail=exc.__class__.__name__) from exc
                self._sleep_backoff(attempt)
                continue

            retry_after = self._rate_limit_wait(resp)
            if retry_after and attempt <= MAX_RETRIES + 2:
                log.info("Rate limited; waiting %.1fs (attempt %d)", retry_after, attempt)
                time.sleep(retry_after)
                continue

            if resp.status_code >= 500 and attempt <= MAX_RETRIES:
                self._sleep_backoff(attempt)
                continue

            return resp

    @staticmethod
    def _sleep_backoff(attempt: int) -> None:
        delay = min(BACKOFF_CAP, BACKOFF_BASE * (2 ** (attempt - 1)))
        delay *= 0.75 + random.random() * 0.5  # jitter
        log.info("Retry %d in %.1fs", attempt, delay)
        time.sleep(delay)

    @staticmethod
    def _rate_limit_wait(resp: requests.Response) -> float | None:
        """Return seconds to wait if this response is a rate limit, else None."""
        if resp.status_code not in (403, 429):
            return None
        body_sniff = ""
        try:
            body_sniff = (resp.text or "")[:300].lower()
        except Exception:  # noqa: BLE001 - body may not be readable when streamed
            pass
        retry_header = resp.headers.get("Retry-After")
        if retry_header:
            try:
                return min(120.0, float(retry_header) + 0.5)
            except ValueError:
                pass
        if resp.headers.get("X-RateLimit-Remaining") == "0":
            reset = resp.headers.get("X-RateLimit-Reset")
            if reset:
                wait = float(reset) - time.time() + 1.0
                return max(1.0, min(120.0, wait))
            return 30.0
        if "secondary rate limit" in body_sniff or "abuse detection" in body_sniff:
            return 20.0
        return None

    @staticmethod
    def _raise_for_status(resp: requests.Response, context: str) -> None:
        """Map a failed response to the right typed error."""
        if resp.status_code < 400:
            return
        if resp.status_code in (401,):
            raise AuthError(detail=f"{context}: 401")
        if resp.status_code == 403:
            remaining = resp.headers.get("X-RateLimit-Remaining")
            body = ""
            try:
                body = (resp.text or "")[:300].lower()
            except Exception:  # noqa: BLE001
                pass
            if remaining == "0" or "secondary rate limit" in body or "abuse" in body:
                raise RateLimitError(detail=f"{context}: rate limited")
            raise ScopeError(detail=f"{context}: 403 forbidden")
        if resp.status_code == 404:
            raise NotFoundError(detail=f"{context}: 404")
        if resp.status_code == 422:
            raise GitoderError(
                "GitHub rejected the request. Check the values you entered and try again.",
                detail=f"{context}: 422",
            )
        raise GitoderError(
            "GitHub returned an unexpected answer. Please try again.",
            detail=f"{context}: {resp.status_code}",
        )

    # ------------------------------------------------------------- helpers

    def _iter_paginated(self, url: str, params: dict | None = None) -> Iterator[dict]:
        """Follow Link headers; per_page=100."""
        params = dict(params or {})
        params["per_page"] = 100
        page_url: str | None = url
        first = True
        while page_url:
            resp = self.request("GET", page_url, params=params if first else None)
            first = False
            if resp.status_code >= 400:
                self._raise_for_status(resp, f"GET {url}")
            items = resp.json()
            if not isinstance(items, list):
                return
            yield from items
            page_url = resp.links.get("next", {}).get("url")

    def paginated(self, url: str, params: dict | None = None) -> list[dict]:
        return list(self._iter_paginated(url, params))

    # ---------------------------------------------------------------- auth

    def validate_token(self) -> tuple[dict, list[str]]:
        """GET /user -> (user, scopes). Raises AuthError / ScopeError."""
        resp = self.request("GET", "/user")
        if resp.status_code == 401:
            raise AuthError(detail="GET /user: 401")
        self._raise_for_status(resp, "GET /user")
        scopes_raw = resp.headers.get("X-OAuth-Scopes", "")
        scopes = [s.strip() for s in scopes_raw.split(",") if s.strip()]
        return resp.json(), scopes

    # ---------------------------------------------------------------- repos

    def list_repos(self) -> list[dict]:
        """All repos the token's user owns, most recently updated first."""
        return self.paginated(
            "/user/repos",
            {"affiliation": "owner", "sort": "updated", "direction": "desc"},
        )

    def get_repo(self, owner: str, name: str) -> dict | None:
        resp = self.request("GET", f"/repos/{quote(owner)}/{quote(name)}")
        if resp.status_code == 404:
            return None
        self._raise_for_status(resp, f"GET /repos/{owner}/{name}")
        return resp.json()

    def create_repo(self, payload: dict) -> dict:
        resp = self.request("POST", "/user/repos", json_body=payload)
        if resp.status_code == 422:
            raise GitoderError(
                "GitHub couldn't create that repository — the name is likely taken "
                "or invalid. Pick another name.",
                detail="POST /user/repos: 422",
            )
        self._raise_for_status(resp, "POST /user/repos")
        return resp.json()

    def delete_repo(self, owner: str, name: str) -> None:
        resp = self.request("DELETE", f"/repos/{quote(owner)}/{quote(name)}")
        if resp.status_code == 204:
            return
        self._raise_for_status(resp, f"DELETE /repos/{owner}/{name}")

    # ------------------------------------------------------- create options

    def gitignore_templates(self) -> list[str]:
        resp = self.request("GET", "/gitignore/templates")
        if resp.status_code == 200 and isinstance(resp.json(), list):
            return sorted(resp.json())
        return []

    def licenses(self) -> list[dict]:
        resp = self.request("GET", "/licenses")
        if resp.status_code == 200 and isinstance(resp.json(), list):
            return resp.json()
        return []

    # ------------------------------------------------------------- git data

    def get_branch_head(self, owner: str, name: str, branch: str) -> str | None:
        resp = self.request("GET", f"/repos/{quote(owner)}/{quote(name)}/git/ref/heads/{quote(branch)}")
        if resp.status_code in (404, 409):
            # 404: branch does not exist. 409: GitHub answers Conflict
            # ("Git Repository is empty") for a brand-new repo with no commits
            # — same situation: there is no branch head yet, and the push
            # pipeline bootstraps the first commit itself.
            return None
        self._raise_for_status(resp, f"GET ref {branch}")
        return resp.json()["object"]["sha"]

    def get_commit(self, owner: str, name: str, sha: str) -> dict:
        resp = self.request(
            "GET", f"/repos/{quote(owner)}/{quote(name)}/git/commits/{quote(sha)}"
        )
        self._raise_for_status(resp, "GET commit")
        return resp.json()

    def get_repo_tree(self, owner: str, name: str, sha: str, recursive: bool = True) -> dict:
        params = {"recursive": "1"} if recursive else None
        resp = self.request(
            "GET", f"/repos/{quote(owner)}/{quote(name)}/git/trees/{sha}", params=params
        )
        self._raise_for_status(resp, "GET tree")
        return resp.json()

    def create_blob(self, owner: str, name: str, content_b64: str) -> str:
        resp = self.request(
            "POST", f"/repos/{quote(owner)}/{quote(name)}/git/blobs",
            json_body={"content": content_b64, "encoding": "base64"},
        )
        self._raise_for_status(resp, "POST blobs")
        return resp.json()["sha"]

    def create_tree(self, owner: str, name: str, tree: list[dict], base_tree: str | None) -> str:
        body: dict[str, Any] = {"tree": tree}
        if base_tree:
            body["base_tree"] = base_tree
        resp = self.request(
            "POST", f"/repos/{quote(owner)}/{quote(name)}/git/trees", json_body=body
        )
        self._raise_for_status(resp, "POST trees")
        return resp.json()["sha"]

    def create_commit(self, owner: str, name: str, message: str, tree_sha: str,
                      parents: list[str]) -> str:
        resp = self.request(
            "POST", f"/repos/{quote(owner)}/{quote(name)}/git/commits",
            json_body={"message": message, "tree": tree_sha, "parents": parents},
        )
        self._raise_for_status(resp, "POST commits")
        return resp.json()["sha"]

    def update_ref(self, owner: str, name: str, branch: str, commit_sha: str) -> None:
        resp = self.request(
            "PATCH",
            f"/repos/{quote(owner)}/{quote(name)}/git/refs/heads/{quote(branch)}",
            json_body={"sha": commit_sha, "force": True},
        )
        self._raise_for_status(resp, f"PATCH ref {branch}")

    def create_ref(self, owner: str, name: str, branch: str, commit_sha: str) -> None:
        resp = self.request(
            "POST", f"/repos/{quote(owner)}/{quote(name)}/git/refs",
            json_body={"ref": f"refs/heads/{branch}", "sha": commit_sha},
        )
        self._raise_for_status(resp, f"POST ref {branch}")

    # ------------------------------------------------------------- contents

    def get_contents(self, owner: str, name: str, path: str, ref: str | None = None) -> dict | None:
        params = {"ref": ref} if ref else None
        resp = self.request(
            "GET", f"/repos/{quote(owner)}/{quote(name)}/contents/{quote(path)}", params=params
        )
        if resp.status_code == 404:
            return None
        self._raise_for_status(resp, f"GET contents {path}")
        return resp.json()

    def put_contents(self, owner: str, name: str, path: str, message: str,
                     content_bytes: bytes, branch: str) -> dict:
        resp = self.request(
            "PUT", f"/repos/{quote(owner)}/{quote(name)}/contents/{quote(path)}",
            json_body={
                "message": message,
                "content": base64.b64encode(content_bytes).decode("ascii"),
                "branch": branch,
            },
        )
        self._raise_for_status(resp, f"PUT contents {path}")
        return resp.json()

    def delete_contents(self, owner: str, name: str, path: str, message: str,
                        branch: str, sha: str) -> None:
        resp = self.request(
            "DELETE", f"/repos/{quote(owner)}/{quote(name)}/contents/{quote(path)}",
            json_body={"message": message, "sha": sha, "branch": branch},
        )
        self._raise_for_status(resp, f"DELETE contents {path}")

    # ------------------------------------------------------------ download

    def zipball(self, owner: str, name: str, ref: str) -> requests.Response:
        """Streaming response for the repo zipball (follows redirects)."""
        url = f"{API}/repos/{quote(owner)}/{quote(name)}/zipball/{quote(ref)}"
        resp = self.request("GET", url, stream=True, timeout=60.0)
        if resp.status_code == 404:
            # Distinguish: repo missing vs empty repo vs wrong branch in the link
            info = self.get_repo(owner, name)
            if info is not None and not info.get("size"):
                raise GitoderError(
                    "This repository is empty — there is nothing to download yet.",
                    title="Nothing to download",
                    detail=f"zipball 404; repo {owner}/{name} is empty",
                )
            if info is not None:
                raise GitoderError(
                    "That branch or tag doesn't exist in this repository. "
                    "Check the link and try again.",
                    title="Branch not found",
                    detail=f"zipball 404; ref {ref}",
                )
            raise NotFoundError(detail="zipball 404")
        self._raise_for_status(resp, "zipball")
        return resp

    def avatar_bytes(self, url: str) -> bytes | None:
        """Download the avatar image (no auth header sent for CDN URLs)."""
        if not url:
            return None
        try:
            resp = self._session.get(url, timeout=15.0)
            if resp.status_code == 200:
                return resp.content
        except requests.exceptions.RequestException:
            return None
        return None
