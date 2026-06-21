"""Tests for meditation_mixer.logging_setup.

Verifies idempotency of setup_logging(), log directory creation, and
rss_mb() returning a sensible value.
"""
import importlib
import logging
import logging.handlers
from pathlib import Path

import pytest

import meditation_mixer.logging_setup as ls


@pytest.fixture(autouse=True)
def _reset_logging_state(tmp_path, monkeypatch):
    """Reset the module-level _CONFIGURED flag and redirect logs to tmp."""
    # Reset the flag so each test starts fresh.
    monkeypatch.setattr(ls, "_CONFIGURED", False)
    # Redirect log output to tmp_path to avoid polluting the repo.
    monkeypatch.setattr(ls, "_LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(ls, "_LOG_FILE", tmp_path / "logs" / "moodscape.log")
    # Remove any handlers left from prior tests.
    pkg_logger = logging.getLogger("meditation_mixer")
    pkg_logger.handlers.clear()
    yield
    pkg_logger.handlers.clear()


def _our_handlers(logger):
    """Return only the handlers we installed (not pytest's LogCaptureHandler)."""
    return [
        h for h in logger.handlers
        if isinstance(h, (logging.StreamHandler, logging.handlers.RotatingFileHandler))
        and not type(h).__name__.startswith("LogCapture")
    ]


class TestSetupLoggingIdempotent:
    """Calling setup_logging() multiple times must not duplicate handlers."""

    def test_single_call_adds_handlers(self):
        ls.setup_logging()
        pkg = logging.getLogger("meditation_mixer")
        assert len(_our_handlers(pkg)) == 2  # console + file

    def test_double_call_same_count(self):
        ls.setup_logging()
        ls.setup_logging()
        pkg = logging.getLogger("meditation_mixer")
        assert len(_our_handlers(pkg)) == 2

    def test_propagate_false(self):
        ls.setup_logging()
        pkg = logging.getLogger("meditation_mixer")
        assert pkg.propagate is False


class TestSetupLoggingCreatesDir:
    """setup_logging() creates the log directory and file."""

    def test_log_dir_created(self, tmp_path):
        ls.setup_logging()
        assert (tmp_path / "logs").is_dir()

    def test_log_file_writable(self, tmp_path):
        ls.setup_logging()
        # Emit a record and flush to ensure it reaches disk.
        pkg = logging.getLogger("meditation_mixer")
        pkg.info("test message")
        for h in pkg.handlers:
            h.flush()
        # Verify file handler was created and wrote to the expected path.
        file_handlers = [
            h for h in pkg.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert file_handlers, "No RotatingFileHandler found on logger"
        log_file = Path(file_handlers[0].baseFilename)
        assert log_file.exists()
        assert "test message" in log_file.read_text()


class TestRssMb:
    """rss_mb() returns a positive float or None (never raises)."""

    def test_returns_positive_or_none(self):
        val = ls.rss_mb()
        if val is not None:
            assert isinstance(val, float)
            assert val > 0.0

    def test_no_exception_on_failure(self, monkeypatch):
        # Force failure by making resource unavailable.
        import sys
        monkeypatch.setitem(sys.modules, "resource", None)
        # rss_mb imports resource inside; patch the import mechanism.
        # Simplest: monkeypatch the function internals.
        original = ls.rss_mb

        def broken_rss():
            import builtins
            real_import = builtins.__import__

            def fake_import(name, *args, **kwargs):
                if name == "resource":
                    raise ImportError("no resource")
                return real_import(name, *args, **kwargs)

            monkeypatch.setattr(builtins, "__import__", fake_import)
            return original()

        result = broken_rss()
        # Should return None, not raise.
        assert result is None or isinstance(result, float)
