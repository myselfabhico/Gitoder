"""Token storage (Windows Credential Manager via keyring), validation, scope check."""

from __future__ import annotations

import logging
import re

import keyring
from keyring.errors import KeyringError

from .errors import AuthError, ScopeError
from .github_client import GithubClient

log = logging.getLogger("gitoder.auth")

SERVICE = "Gitoder"
ACCOUNT = "github_pat"
# classic tokens ghp_/github_pat_; fine-grained PATs work for repo access but
# cannot delete repos, so the sign-in flow requires a classic PAT.
TOKEN_RE = re.compile(r"^(ghp_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})$")
REQUIRED_SCOPES = ("repo", "delete_repo")
REQUIRED_SCOPES_URL = "https://github.com/settings/tokens/new?scopes=repo,delete_repo&description=Gitoder"


class TokenStore:
    """Wraps keyring so tests can substitute an in-memory store."""

    def __init__(self, service: str = SERVICE, account: str = ACCOUNT) -> None:
        self.service = service
        self.account = account

    def load(self) -> str | None:
        try:
            return keyring.get_password(self.service, self.account)
        except KeyringError as exc:
            log.warning("Keyring read failed: %s", exc.__class__.__name__)
            return None

    def save(self, token: str) -> None:
        keyring.set_password(self.service, self.account, token)

    def clear(self) -> None:
        try:
            keyring.delete_password(self.service, self.account)
        except KeyringError:
            pass


def validate_token(token: str, client: GithubClient) -> dict:
    """Validate via GET /user and require repo+delete_repo. Returns the user dict.

    Raises AuthError (bad token) or ScopeError (missing scopes).
    """
    user, scopes = client.validate_token()
    lowered = {s.lower() for s in scopes}
    missing = [s for s in REQUIRED_SCOPES if s not in lowered]
    if missing:
        raise ScopeError(
            "This token is missing the '"
            + "', '".join(missing)
            + "' permission. Use the 'Create my token' link to make a new one "
              "with both 'repo' and 'delete_repo' checked, then paste it here.",
            detail=f"missing scopes: {missing}",
        )
    return user


def looks_like_token(text: str) -> bool:
    return bool(TOKEN_RE.match(text.strip()))
