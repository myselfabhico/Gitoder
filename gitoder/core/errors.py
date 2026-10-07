"""Typed exceptions for Gitoder. Each maps to one friendly, jargon-free message."""

from __future__ import annotations


class GitoderError(Exception):
    """Base for every expected Gitoder failure."""

    title = "Something went wrong"
    message = "An unexpected problem occurred. Please try again."
    retryable = False
    kind = "error"  # error | warning | info

    def __init__(self, message: str | None = None, *, title: str | None = None,
                 retryable: bool | None = None, detail: str = "") -> None:
        self.message = message if message is not None else self.message
        if title is not None:
            self.title = title
        if retryable is not None:
            self.retryable = retryable
        self.detail = detail  # technical context for the log, never shown raw in the UI
        super().__init__(self.message)


class NetworkError(GitoderError):
    title = "Can't reach GitHub"
    message = "Can't reach GitHub. Check your internet connection and try again."
    retryable = True


class TimeoutError_(NetworkError):
    title = "GitHub took too long"
    message = "GitHub took too long to answer. Check your connection and try again."
    retryable = True


class AuthError(GitoderError):
    title = "Sign-in problem"
    message = "That token doesn't work. Make sure you copied the whole token and try again."
    retryable = True


class TokenRevokedError(AuthError):
    title = "Connection expired"
    message = ("Your saved GitHub connection is no longer valid. "
               "Sign in again with a fresh token to continue.")


class ScopeError(GitoderError):
    title = "Missing permission"
    message = ("Your token is missing a permission Gitoder needs. "
               "Create a new token with the 'repo' and 'delete_repo' permissions "
               "using the link on the Sign-In screen.")
    retryable = True


class RateLimitError(GitoderError):
    title = "Slowing down"
    message = "GitHub asked us to slow down. Retrying shortly…"
    retryable = True


class NameTakenError(GitoderError):
    title = "Name already used"
    message = "You already have a repository with that name. Pick another name."


class NotFoundError(GitoderError):
    title = "Not found"
    message = "That repository doesn't exist or you don't have access to it."


class FileTooLargeError(GitoderError):
    title = "File too large"
    message = "Some files are over GitHub's 100 MB limit. Remove them and try again."


class EmptyFolderError(GitoderError):
    title = "Nothing to upload"
    message = "That folder has no files to upload after ignoring junk files."


class InvalidLinkError(GitoderError):
    title = "Not a GitHub link"
    message = "That doesn't look like a GitHub repository link."


class DownloadError(GitoderError):
    title = "Download problem"
    message = "The download failed. Check the link and your connection, then try again."
    retryable = True


class DiskError(GitoderError):
    title = "Can't save the file"
    message = "Couldn't save the file. Check free disk space and permissions, then try again."
    retryable = True


class CancelledError(GitoderError):
    title = "Cancelled"
    message = "The operation was cancelled."
    kind = "info"


class PushVerifyError(GitoderError):
    title = "Upload verification failed"
    message = ("The upload finished but Gitoder could not confirm every file arrived. "
               "Nothing was shown as successful. Use Retry upload to try again.")
    retryable = True


class RepoCreatedUploadFailedError(GitoderError):
    """Creation succeeded but the upload did not finish. The repo must not be recreated."""

    title = "Upload didn't finish"
    message = "Your repository was created, but the upload didn't finish."
    retryable = True


class UnexpectedError(GitoderError):
    title = "Something went wrong"
    message = "Something went wrong. Your details were copied for support — no private data included."
    retryable = True
