"""Rotating log setup. INFO to file, WARNING to stderr. Tokens are never logged."""

from __future__ import annotations

import logging
import logging.handlers
import sys

from .paths import logs_dir

MAX_BYTES = 1_000_000
BACKUPS = 3
TOKEN_PREFIXES = ("ghp_", "github_pat_", "Bearer ")


def _redact(text: str) -> str:
    for token in TOKEN_substrings:
        text = text.replace(token, "[redacted]")
    return text


class RedactingFilter(logging.Filter):
    """Drops anything that looks like a token prefix or an Authorization header."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        if "authorization" in msg.lower():
            return False
        for token in TOKEN_PREFIXES:
            if token in msg:
                return False
        return True


def setup_logging(level: int = logging.INFO) -> str:
    """Install handlers; return the log file path."""
    log_file = logs_dir() / "gitoder.log"
    root = logging.getLogger()
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    rf = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8"
    )
    rf.setFormatter(fmt)
    rf.addFilter(RedactingFilter())

    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.WARNING)
    sh.setFormatter(fmt)
    sh.addFilter(RedactingFilter())

    root.handlers.clear()
    root.addHandler(rf)
    root.addHandler(sh)
    return str(log_file)
