"""Logging configuration for the meditation_mixer package.

Provides `setup_logging()` (idempotent — safe to call on every Streamlit
rerun) and `rss_mb()` for memory instrumentation.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_CONFIGURED = False

_LOG_DIR = Path("logs")
_LOG_FILE = _LOG_DIR / "moodscape.log"
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging() -> None:
    """Configure the 'meditation_mixer' package logger.

    Idempotent: repeated calls (Streamlit reruns) do NOT add duplicate
    handlers. Attaches a console StreamHandler (INFO) and a RotatingFileHandler
    writing to logs/moodscape.log.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("meditation_mixer")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    formatter = logging.Formatter(_FORMAT)

    # Console handler — INFO level.
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # Rotating file handler.
    file_h = logging.handlers.RotatingFileHandler(
        str(_LOG_FILE),
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_h.setLevel(logging.DEBUG)
    file_h.setFormatter(formatter)
    logger.addHandler(file_h)

    _CONFIGURED = True


def rss_mb() -> float | None:
    """Best-effort resident-set size in MB. Returns None on failure."""
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS reports bytes; Linux reports KiB.
        if sys.platform == "darwin":
            return usage / (1024 * 1024)
        else:
            return usage / 1024
    except Exception:
        return None
